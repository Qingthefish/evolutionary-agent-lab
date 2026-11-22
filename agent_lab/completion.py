"""Completion protocol for open workflows (completion-protocol-v2, proposed 2026-11-21, pending owner review).

Task states are unchanged: running, waiting_*, the runner's awaiting_verification,
succeeded, failed. Each turn this module derives a completion *phase* from the
recorded state and the shared budget, never from the model's own claims:

- working: no structural sign that the deliverable is ready;
- ready: the deliverable looks ready (a subtask has offered files to its parent,
  or every subtask a parent delegated was accepted). Advice only: every tool the
  role has stays available, because integration work may remain;
- finish: the task's last R requests (R = FinishPolicy.finish_requests), or R
  requests after a forced finish (consecutive output-limit replies or repeated
  identical outcomes). Only completion actions the gateway would accept are
  offered: submit_for_verification (any unreplaced failed subtask is attached
  to the proposal for the reviewer) and report_blocker. A human rejection
  reopens the window. A batch that ends with one of them may still
  carry the role's other calls first (a handoff, a last fix, a message) through
  the existing batch mechanism; any other batch is refused.

With tool_choice=required every schema-valid reply in the window is therefore a
proposal for human review or an honest blocker. Neither is success: submission
still waits for the trusted human review, and a blocker ends the task as failed
with its artifacts retained.
"""

import json

from . import budget
from .recovery import links

COMPLETION_TOOLS = frozenset({"submit_for_verification", "report_blocker"})
SUMMARY_LIMIT = 2000
FORCED_REASONS = frozenset({"output_limit", "repeated_outcomes"})


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


def window_record(workflow, task):
    """The task's finish-window record: when it was entered, requests used since, and a forced reason, if any.

    The window is sticky: once entered (budget, output limit or repetition) it lasts
    at most R requests counted from entry, even if other tasks finish and release
    their holds, or a refused batch spends no tool call. A human rejection reopens
    it: the reviewer asked for changes, so the task may work again; if the budget is
    still low, the window is re-entered at once.
    """
    # A human rejection reopens work (proposed 2026-11-22): only window events after the latest reopening count.
    floor = workflow.db.execute("SELECT coalesce(max(sequence),0) FROM events WHERE task=? AND kind='finish_mode_reopened'",
                                (task,)).fetchone()[0]
    forced = workflow.db.execute("SELECT sequence,detail FROM events WHERE task=? AND kind='finish_mode_forced' "
                                 "AND sequence>? ORDER BY sequence DESC LIMIT 1", (task, floor)).fetchone()
    entered = workflow.db.execute("SELECT min(sequence) FROM events WHERE task=? AND kind='finish_mode_entered' "
                                  "AND sequence>?", (task, floor)).fetchone()[0]
    used = (workflow.db.execute("SELECT count(*) FROM events WHERE task=? AND kind='model_attempt_reserved' AND "
                                "sequence>?", (task, entered)).fetchone()[0] if entered else 0)
    return {"entered": entered is not None, "used": used,
            "forced": json.loads(forced["detail"]).get("reason") if forced else None}


def phase(workflow, task, role_left=None):
    """The completion phase for this turn, or None when no finish policy is configured.

    Called after the current request was reserved: `available` counts the requests
    left after this one (the tree share, the role's own limit, and tool calls, of
    which each remaining request needs one), so this request is in the window when
    available < R, or when the window was already entered or forced.
    """
    info = budget.finish_budget(workflow, task)
    if info is None:
        return None
    window = info["finish_requests"]
    available = max(0, min(info["available"], info["tool_calls_left"] - 1,
                           info["available"] if role_left is None else role_left))
    ready = readiness(workflow, task)
    record = window_record(workflow, task)
    if record["entered"] or record["forced"] or available < window:
        left = max(1, min(available + 1, window - record["used"]))
        cause = (f"finish forced after {record['forced'].replace('_', ' ')}" if record["forced"]
                 else "this task's finish window")
        name, reason = "finish", f"{left} request(s) left including this one: {cause}"
    else:
        name, left, reason = ("ready" if ready else "working"), available + 1, ready
    return {"phase": name, "reason": reason, "ready": ready, "available": available, "finish_left": left,
            "finish_requests": window, "forced": record["forced"], "window_used": record["used"],
            "policy": info["policy"], "held_for_other_open_tasks": info["held_for_other_open_tasks"]}


def offered_tools(workflow, task, allowed, state):
    """In the finish window: only the completion actions the gateway would accept now, else None."""
    if state is None or state["phase"] != "finish":
        return None
    tools = set(allowed) & COMPLETION_TOOLS
    # A failed subtask no longer removes submit_for_verification: a summary that names it may still be reviewed.
    return frozenset(tools) or None


def contract(workflow, task, state, allowed):
    """What every agent sees each turn: how and when its assignment completes."""
    row = workflow.db.execute("SELECT parent FROM tasks WHERE id=?", (task,)).fetchone()
    window = state["finish_requests"]
    rules = ["Complete with submit_for_verification, exactly once and as the last tool in a batch. A human reviewer "
             "decides acceptance; submitting is not success.",
             f"summary: at most {SUMMARY_LIMIT} characters. Keep detailed evidence in a task file and name that file "
             "in the summary. If anything required is unfinished, say so in the summary or use report_blocker.",
             "An invalid argument rejects the whole batch, including handoffs in it; read the error and resend.",
             f"Your last {window} requests are your finish window: only submit_for_verification and report_blocker are "
             "offered then (after a review rejection also file-fix tools, in a batch that ends with one of them). "
             "Finish deliverable work, including writing or integrating final files, before it."]
    if row["parent"]:
        rules.append(f"Offer every deliverable file to your parent task {row['parent']}: with offer_artifact (use that "
                     "task id, not a role name) before, or in the same batch as, the submission.")
    if _children(workflow, task) or "delegate_task" in allowed:
        rules.append("Accept the subtask snapshots you deliver. "
                     "A failed subtask that is not replaced is reported to the reviewer with your proposal: replace "
                     "it if its work is needed, and say in your summary how its work is covered; the reviewer decides.")
    if "report_blocker" in allowed:
        rules.append("If required work cannot be finished, call report_blocker with what is done and what is missing. "
                     "It ends this task as failed and keeps its files; it is the honest alternative to submitting "
                     "incomplete work.")
    finish = state["phase"] == "finish"
    return {"phase": state["phase"], "phase_reason": state["reason"], "deliverable_looks_ready": bool(state["ready"]),
            "requests_available_including_current": state["available"] + 1, "finish_window_requests": window,
            "completion_tool": "submit_for_verification", "rules": rules,
            "finish_mode": {"active": finish, "requests_left_including_current": state["finish_left"] if finish else None,
                            "tools": sorted(offered_tools(workflow, task, allowed, state) or ()) if finish else None,
                            "instruction": _finish_instruction(state) if finish else None}}


def _finish_instruction(state):
    why = (f"Your work was interrupted ({state['forced'].replace('_', ' ')}). " if state["forced"] else "")
    return (f"{why}Finish window: {state['finish_left']} request(s) left including this one. Every response must "
            "end with submit_for_verification or report_blocker; a final handoff (offer_artifact, accept_artifact) "
            "or, after a review rejection, a last file fix may come first in the same batch, but no delegation, "
            "question or re-reading. "
            "Call submit_for_verification only for work that is actually done, and name anything unfinished or "
            "unverified in the summary; call report_blocker if required work is missing. A human reviewer decides; "
            "a blocker is an honest outcome, not a penalty.")


def delegation_refusal(workflow, task):
    """A model-visible refusal when a new subtask would leave either finish window unprotected."""
    info = budget.finish_budget(workflow, task)
    if info is None:
        return None
    window, minimum = info["finish_requests"], info["policy"].min_child
    need = 2 * window + minimum  # This task's window, the subtask's window and its work.
    if info["available"] >= need:
        return None
    return (f"Only {info['available']} shared requests remain for this task; a new subtask needs {need}: {window} for "
            f"your finish window, {window} for its own and at least {minimum} for its work. No subtask was created. "
            "Finish with what is done: submit_for_verification with a summary that lists known limitations, or "
            "report_blocker if required work is missing.")


def unreplaced_failed_subtasks(workflow, task):
    """Failed or cancelled direct subtasks that were not replaced, as [{id, assignee, state}].

    Proposed 2026-11-22: these no longer block a proposal. The runner attaches them to every proposal so the
    human reviewer sees them; acceptance requires explicitly naming each waived child. Before, a lead whose
    deliverable was complete and verified could only report a blocker once a replacement no longer fit the budget.
    """
    from .recovery import links
    replaced = links(workflow)
    return [{"id": child["id"], "assignee": child["assignee"], "state": child["state"]}
            for child in _children(workflow, task) if child["state"] in {"failed", "cancelled"}
            and child["id"] not in replaced]


def submission_refusal(workflow, task):
    """Kept for callers of the earlier protocol: failed subtasks are now disclosed, never a refusal."""
    return None
