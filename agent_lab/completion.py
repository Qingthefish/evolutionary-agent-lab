"""Completion protocol for open workflows (proposed 2026-11-19, pending owner review).

Task states are unchanged: running, waiting_*, the runner's awaiting_verification,
succeeded, failed. Each turn this module derives a completion *phase* from the
recorded state and the shared budget, never from the model's own claims:

- working: no structural sign that the deliverable is ready;
- ready: the deliverable looks ready (a subtask has offered files to its parent,
  or every subtask a parent delegated was accepted) - this never means success;
- finish: the task must finish now. Only finishing tools are offered: submit,
  report a blocker, hand over, read, message or ask the requester.

Finish starts when the task's available requests reach its own reserve, or when
the deliverable looks ready and few requests remain. Submission still goes to
the trusted human review; a blocker ends the task as an honest failure.
"""

from . import budget
from .recovery import links

COMPLETION_TOOLS = frozenset({"submit_for_verification", "report_blocker"})
# Tools a task keeps in Finish Mode: hand over, inspect, communicate and complete.
FINISH_TOOLS = COMPLETION_TOOLS | frozenset({"offer_artifact", "accept_artifact", "read_text", "post_message",
                                             "read_messages", "ask_human", "list_tasks"})
# The last requests (at or below the submission reserve) keep only completion and
# handoff: in live Software run 2026-11-21, QA and the lead spent their final Finish
# Mode requests on read_text and ended without a submission or a blocker report.
FINAL_TOOLS = COMPLETION_TOOLS | frozenset({"offer_artifact", "accept_artifact"})
SUMMARY_LIMIT = 2000


def _children(workflow, task):
    replaced = links(workflow)
    return [row for row in workflow.db.execute(
        "SELECT id,assignee,state FROM tasks WHERE parent=? ORDER BY rowid", (task,)) if row["id"] not in replaced]


def readiness(workflow, task):
    """A structural readiness signal, or None. Never a success judgement."""
    children = _children(workflow, task)
    if children:
        if all(child["state"] == "succeeded" for child in children):
            return "every delegated subtask was accepted"
        return None
    parent = workflow.db.execute("SELECT parent FROM tasks WHERE id=?", (task,)).fetchone()["parent"]
    if parent and workflow.db.execute("SELECT 1 FROM artifacts WHERE source_task=? AND target_task=? LIMIT 1",
                                      (task, parent)).fetchone():
        return "deliverables were offered to the parent task"
    return None


def phase(workflow, task):
    """The completion phase for this turn, or None when no finish policy is configured."""
    info = budget.finish_budget(workflow, task)
    if info is None:
        return None
    policy, available, own = info["policy"], info["available"], info["own_reserve"]
    ready = readiness(workflow, task)
    window = max(own, int(info["cap"] * policy.ready_fraction))
    if available <= own:
        name, reason = "finish", f"{available} request(s) left, within the {own} kept for this task's own finish"
    elif ready and available <= window:
        name, reason = "finish", f"{ready} and {available} request(s) left"
    else:
        name, reason = ("ready", ready) if ready else ("working", None)
    final = name == "finish" and available <= policy.submit_reserve
    return {"phase": name, "reason": reason, "final": final, "available": available, "own_reserve": own, "finish_window": window,
            "depth": info["depth"], "reserved_for_ancestors": info["reserved_for_ancestors"], "policy": policy}


def offered_tools(allowed, state):
    """Finish Mode offers only finishing tools the task already has; its last requests only complete or hand over."""
    if state is None or state["phase"] != "finish":
        return None
    return frozenset(allowed) & (FINAL_TOOLS if state.get("final") else FINISH_TOOLS)


def contract(workflow, task, state, allowed):
    """What every agent sees each turn: how and when its assignment completes."""
    row = workflow.db.execute("SELECT parent FROM tasks WHERE id=?", (task,)).fetchone()
    rules = ["Complete with submit_for_verification, exactly once and as the last tool in a batch. A human reviewer "
             "decides acceptance; submitting is not success.",
             f"summary: at most {SUMMARY_LIMIT} characters. Keep detailed evidence in a task file and name that file "
             "in the summary.",
             "An invalid argument rejects the whole batch, including handoffs in it; read the error and resend."]
    if row["parent"]:
        rules.append(f"Offer every deliverable file to your parent task {row['parent']} with offer_artifact (use that "
                     "task id, not a role name) in the same batch as, or before, the submission.")
    if _children(workflow, task) or "delegate_task" in allowed:
        rules.append("Accept the subtask snapshots you deliver. A failed subtask that is not replaced blocks this "
                     "task's success.")
    if "report_blocker" in allowed:
        rules.append("If required work cannot be finished, call report_blocker with what is done and what is missing. "
                     "It ends this task as failed; it is the honest alternative to submitting incomplete work.")
    finish = state["phase"] == "finish"
    return {"phase": state["phase"], "phase_reason": state["reason"],
            "requests_available_after_current": state["available"],
            "requests_kept_for_own_finish": state["own_reserve"],
            "finish_mode_starts_at": {"requests_left": state["own_reserve"],
                                      "or_when_ready_with_requests_left": state["finish_window"]},
            "completion_tool": "submit_for_verification", "rules": rules,
            "finish_mode": {"active": finish, "final_requests": bool(finish and state.get("final")),
                            "tools": sorted(offered_tools(allowed, state) or ()) if finish else None,
                            "instruction": _finish_instruction(state) if finish else None}}


def _finish_instruction(state):
    if state.get("final"):
        return (f"Final requests: {state['available']} left after this one. Reading, messaging and new work are no "
                "longer available. In this batch, call submit_for_verification with the work that is done (offer or "
                "accept deliverables first in the same batch if needed), or report_blocker if required work is "
                "missing. A batch that does not end with one of them is refused and runs nothing.")
    return ("Finish Mode: submit the work that is done now, or report a blocker if required work is missing. Do not "
            "start optional tests, rewrites, packaging or improvements. A genuine critical defect can be reported in "
            "the summary or raised with the requester.")


def delegation_refusal(workflow, task):
    """A model-visible refusal when a new subtask would leave no finish for the caller."""
    info = budget.finish_budget(workflow, task)
    if info is None:
        return None
    need = info["policy"].parent_reserve + info["policy"].min_child
    if info["available"] >= need:
        return None
    return (f"Only {info['available']} shared requests remain for this task; {info['policy'].parent_reserve} are kept "
            f"for your own finish and a new subtask needs at least {info['policy'].min_child}. No subtask was created. "
            "Finish with what is done: submit_for_verification with a summary that lists known limitations, or "
            "report_blocker if required work is missing.")


def submission_refusal(workflow, task):
    """Refuse a proposal that review could never accept: an unreplaced failed subtask."""
    if budget.finish_budget(workflow, task) is None:
        return None
    failed = [child for child in _children(workflow, task) if child["state"] in {"failed", "cancelled"}]
    if not failed:
        return None
    names = ", ".join(f"{child['id']} ({child['assignee']}, {child['state']})" for child in failed)
    return (f"submit_for_verification: subtask {names} was not completed or replaced, so this task cannot be "
            "accepted. Replace it with retry_failed_task if enough requests remain, or call report_blocker "
            "explaining what is done and what is missing.")
