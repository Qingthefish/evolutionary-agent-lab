"""Batch evaluation over development cases. Independent of any user interface.

Each case runs in a fresh state directory with its own workflow database, so
cases and memory namespaces never share state. Acceptance checks are computed
by this evaluator from persisted workflow records and actual artifacts, never
from model text. Offline drivers execute fixed scripts: their results are
`offline_fixture` plumbing evidence with `benchmark_valid: false`.
"""

import json
import math
import os
from pathlib import Path
import time
from uuid import uuid4

from ..acceptance import ArtifactRule, verify_rules
from ..core import Workflow, WorkflowError
from ..files import FileTools
from ..inspection import ArtifactInspector, ArtifactMissingError
from ..memory import ExperienceMemory
from ..runtime import (LIVE_AGENTS, ChildTextRule, LiveConfig, RuntimeServices,
                       build_live_scheduler, live_members, policy_for_task)
from .. import offline_scenarios
from .manifest import build_manifest, comparison_conditions, digest

HUMAN = "evaluator"
OFFLINE_DRIVERS = {"offline_delegation", "offline_approval", "offline_git"}
CLASSES = ("completed", "acceptance_failed", "task_failed", "task_cancelled", "blocked", "timeout",
           "driver_error", "not_configured")


class _Session:
    """Fresh, isolated backend objects for one case."""

    def __init__(self, directory, memory_namespace):
        self.directory = directory
        self.workflow = Workflow(directory / "workflow.sqlite3")
        self.files = self.git = None
        self.services = None
        try:
            self.workflow.register_actor(HUMAN, "human")
            for agent in (*offline_scenarios.AGENTS, "coder"):
                self.workflow.register_actor(agent, "agent")
            self.files = FileTools(self.workflow, directory / "files")
            self.memory = ExperienceMemory(self.workflow, namespace=memory_namespace)
            self.inspector = ArtifactInspector(self.workflow, self.files)
        except BaseException:
            self.close()
            raise

    def git_tools(self):
        if self.git is None:
            from ..git_tools import GitTools
            self.git = GitTools(self.workflow, [offline_scenarios.demo_repository_config(self.directory)])
        return self.git

    def close(self):
        if self.services is not None:
            self.services.close()
        if self.git is not None:
            self.git.close()
        if self.files is not None:
            self.files.close()
        self.workflow.close()


def _drive_offline(case, session):
    """Run a fixed offline scenario, applying the case's scripted human decisions."""
    name = {"offline_delegation": "delegation", "offline_approval": "approval", "offline_git": "git"}[case.driver]
    git = session.git_tools() if name == "git" else None
    root, _ = offline_scenarios.start(name, session.workflow, session.files, session.memory, human=HUMAN, git=git)
    scheduler = offline_scenarios.scheduler_for(session.workflow, session.files, root, name, human=HUMAN,
                                                memory=session.memory, git=git)
    answers = list(case.human_responses)
    decided = False
    state = scheduler.run()
    for _ in range(20):
        if state["state"] != "blocked":
            break
        needs = state["needs"]
        progressed = False
        for need in needs:
            for request in need.get("requests", []):
                if request["kind"] == "clarification" and answers:
                    session.workflow.respond(request["id"], HUMAN, answer=answers.pop(0))
                    progressed = True
                elif request["kind"] == "approval" and case.approval and not decided:
                    session.workflow.respond(request["id"], HUMAN, approve=case.approval == "approve")
                    decided = progressed = True
            if need.get("kind") == "trusted_action_release":
                for request_id in need.get("request_ids", []):
                    scheduler.runner(need["task"]).gateway.release_approved(request_id)
                    progressed = True
        if not progressed:
            return root, state
        state = scheduler.run()
    return root, state


def _case_policy(case, live):
    children = tuple(ChildTextRule(s.assignee, s.title, s.artifacts,
        (*s.criteria, *(ArtifactRule(p,"absent") for p in s.absent_artifacts))) for s in case.expected.subtasks
        if s.final_state == "succeeded" and (s.artifacts or s.criteria or s.absent_artifacts))
    return policy_for_task(live, constraints=case.constraints, root_artifacts=case.expected.artifacts,
        child_rules=children, declared_subtasks_only=case.expected.declared_subtasks_only, root_criteria=(*case.expected.criteria,
            *(ArtifactRule(p,"absent") for p in case.expected.absent_artifacts)) if case.expected.final_state == "succeeded" else ())


def _provide_inputs(case, session, root):
    """Seed only the current case's declared raw inputs, with human attribution."""
    for path, content in case.inputs.items():
        session.files.provide_text(root, HUMAN, path, content)


def _drive_live(case, session, live):
    """Live DeepSeek scheduler run. Unvalidated: no live call has been made yet."""
    members = live_members(live)
    for agent in members:
        session.workflow.register_actor(agent, "agent")
    if session.services is None:
        session.services = RuntimeServices(session.workflow, session.files, live)
    chat = session.workflow.create_chat("group", [HUMAN, *members])
    root = session.workflow.create_task(chat, HUMAN, "coordinator", case.goal)
    _provide_inputs(case, session, root)
    scheduler = build_live_scheduler(session.workflow, session.files, root, human=HUMAN, live=live,
        policy=_case_policy(case, live), services=session.services)
    return root, scheduler.run()


def _artifact_checks(session, task, expected, prefix=""):
    checks = {}
    for path, text in expected.artifacts.items():
        try:
            checks[prefix + "artifact:" + path] = session.inspector.read_file(task, HUMAN, path)["content"] == text
        except WorkflowError:
            checks[prefix + "artifact:" + path] = False
    for path in expected.absent_artifacts:
        try:
            session.inspector.read_file(task, HUMAN, path)
            checks[prefix + "absent:" + path] = False
        except ArtifactMissingError:
            checks[prefix + "absent:" + path] = True
        except WorkflowError:
            # Denied/unsafe/unreadable is not proof of absence.
            checks[prefix + "absent:" + path] = False
    actor = session.workflow.task(task, HUMAN)["assignee"]
    checks.update({prefix+k:v for k,v in verify_rules(session.workflow,session.files,task,actor,expected.criteria).items()})
    return checks


def _human_matches(request, outcome):
    if outcome == "unanswered":
        return not request["answered"]
    if not request["answered"]:
        return False
    if outcome == "answered":
        return True
    if outcome == "rejected":
        return request["approved"] == 0
    if outcome == "approved":
        return request["approved"] == 1
    return outcome == "consumed" and request["approved"] == 1 and bool(request["consumed"])


def _checks(case, session, root, duration):
    workflow = session.workflow
    task = workflow.task(root, HUMAN)
    tree = workflow.db.execute("""
        WITH RECURSIVE tree(id) AS (SELECT ? UNION ALL SELECT t.id FROM tasks t JOIN tree ON t.parent=tree.id)
        SELECT t.* FROM tasks t JOIN tree ON tree.id=t.id""", (root,)).fetchall()
    checks = {"final_state": task["state"] == case.expected.final_state,
              "task_count": len(tree) >= case.expected.min_tasks,
              "within_time": duration <= case.expected.max_seconds}
    checks.update(_artifact_checks(session, root, case.expected))
    from ..recovery import active_tasks, links
    active = active_tasks(workflow, tree)
    retry_links = links(workflow)
    subtask_records = []
    for index, expected in enumerate(case.expected.subtasks):
        prefix = f"subtask:{index}:"
        selected_tree = active if expected.final_state == "succeeded" else tree
        matches = [row for row in selected_tree if row["id"] != root and row["assignee"] == expected.assignee
                   and row["title"] == expected.title]
        checks[prefix + "unique_match"] = len(matches) == 1
        checks[prefix + "final_state"] = len(matches) == 1 and matches[0]["state"] == expected.final_state
        subtask_records.append({"selector": {"assignee": expected.assignee, "title": expected.title},
                                "matches": [{"task_id": r["id"], "state": r["state"]} for r in matches]})
        if len(matches) == 1:
            checks.update(_artifact_checks(session, matches[0]["id"], expected, prefix))
        else:
            checks.update({prefix + "artifact:" + p: False for p in expected.artifacts})
            checks.update({prefix + "absent:" + p: False for p in expected.absent_artifacts})
            checks.update({prefix+f"criterion:{i}:{r.path}:{r.kind}":False for i,r in enumerate(expected.criteria)})
    ids = [row["id"] for row in tree]
    marks = ",".join("?" * len(ids))
    requests = workflow.db.execute(f"""SELECT r.*,t.assignee FROM requests r JOIN tasks t ON t.id=r.task
        WHERE r.task IN ({marks})""", ids).fetchall()
    human_records = []
    for index, expected in enumerate(case.expected.human_requests):
        matches = [r for r in requests if r["kind"] == expected.kind
                   and (expected.assignee is None or r["assignee"] == expected.assignee)
                   and _human_matches(r, expected.outcome)]
        checks[f"human:{index}:{expected.kind}:{expected.outcome}"] = len(matches) == expected.count
        human_records.append({"kind": expected.kind, "outcome": expected.outcome, "assignee": expected.assignee,
                              "expected_count": expected.count, "actual_count": len(matches),
                              "request_ids": [r["id"] for r in matches]})
    if case.expected.remote_branch_verified:
        verified = workflow.db.execute(
            f"SELECT result FROM git_operations WHERE operation='push' AND status='verified' AND task IN ({marks})",
            ids).fetchone() if session.git is not None else None
        ok = False
        if verified is not None:
            result = json.loads(verified["result"])
            repository = session.git.repositories[result["repository"]]
            ok = session.git._remote_head(repository.remote_url(result["remote"]), result["branch"]) == result["commit"]
        checks["remote_branch_verified"] = ok
    states = {}
    for row in tree:
        states[row["state"]] = states.get(row["state"], 0) + 1
    metrics = workflow.metrics(task["chat"], HUMAN)
    record = next(r for r in metrics["tasks"] if r["task_id"] == root)
    task_records = []
    now = workflow.clock()
    for row in tree:
        elapsed = max(0, (row["ended"] if row["ended"] is not None else now) - row["created"])
        waited = row["wait_seconds"] + (max(0, now - row["wait_started"]) if row["wait_started"] is not None else 0)
        evidence = json.loads(row["evidence"]) if row["evidence"] else {}
        passed = evidence.get("checks", {})
        trusted_success = row["state"] == "succeeded" and bool(passed) and all(v is True for v in passed.values())
        independent = [v for index, match in enumerate(subtask_records)
                       if any(m["task_id"] == row["id"] for m in match["matches"])
                       for name, v in checks.items() if name.startswith(f"subtask:{index}:")]
        task_records.append({"task_id": row["id"], "parent": row["parent"], "assignee": row["assignee"],
                             "state": row["state"], "verified_success": trusted_success and all(independent),
                             "replacement_task": retry_links.get(row["id"]),
                             "elapsed_seconds": elapsed, "final_duration_seconds": elapsed if row["ended"] is not None else None,
                             "human_wait_seconds": waited})
    observed_models = []
    if workflow.db.execute("SELECT 1 FROM sqlite_master WHERE name='runner_turns' AND type='table'").fetchone():
        observed_models = sorted({json.loads(row[0])["model"] for row in workflow.db.execute(
            f"SELECT response FROM runner_turns WHERE task IN ({marks}) AND response IS NOT NULL", ids)})
    root_record = next(r for r in task_records if r["task_id"] == root)
    checks["within_time"] = checks["within_time"] and root_record["elapsed_seconds"] <= case.expected.max_seconds
    return checks, {"root_state": task["state"], "root_task": root, "task_outcomes": task_records,
                    "observed_models": observed_models,
                    "human_interventions": [{"request_id": r["id"], "task_id": r["task"], "assignee": r["assignee"],
                        "kind": r["kind"], "responder": r["responder"], "answered": bool(r["answered"]),
                        "approved": r["approved"], "consumed": bool(r["consumed"]),
                        "prompt_sha256": digest(r["prompt"]), "response_sha256": digest(r["response"]) if r["response"] is not None else None}
                        for r in requests],
                    "tasks": len(tree), "task_states": states,
                    "workflow_elapsed_seconds": record["elapsed_seconds"],
                    "human_wait_seconds": record["human_wait_seconds"],
                    "subtask_checks": subtask_records, "human_request_checks": human_records,
                    "evidence": json.loads(task["evidence"]) if task["evidence"] else None}


def _classify(case, checks, workflow_state):
    if all(checks.values()):
        return "completed"
    if not checks["within_time"]:
        return "timeout"
    root = workflow_state["root_state"]
    if root not in {"succeeded", "failed", "cancelled"}:
        return "blocked"
    if root != case.expected.final_state:
        return {"failed": "task_failed", "cancelled": "task_cancelled"}.get(root, "acceptance_failed")
    return "acceptance_failed"


class Evaluator:
    def __init__(self, cases, *, output_root, live=None, memory="off"):
        if memory not in {"on", "off"}:
            raise WorkflowError("Memory mode must be 'on' or 'off'")
        if live is not None and memory == "on":
            raise WorkflowError("Live memory-on batch comparison protocol is not implemented; refusing a misleading experiment label")
        if live is not None and not isinstance(live, LiveConfig):
            raise WorkflowError("Live evaluation requires the shared explicit LiveConfig")
        if live is not None and live.enable_memory:
            raise WorkflowError("Memory-enabled live batch evaluation awaits its versioned cross-task/reset protocol; runtime task memory is available")
        cases = list(cases)
        if len({case.id for case in cases}) != len(cases):
            raise WorkflowError("Evaluation requires unique case IDs")
        self.cases = {case.id: case for case in cases}
        if live is not None:
            for case in self.cases.values():
                if case.driver == "live_scheduler":
                    _case_policy(case, live)
        self.output_root = Path(output_root)
        self.live, self.memory = live, memory

    def run(self, case_ids=None, *, label=None):
        selected_ids = sorted(self.cases) if case_ids is None else list(case_ids)
        if not selected_ids or len(set(selected_ids)) != len(selected_ids):
            raise WorkflowError("Select a nonempty unique case set")
        selected = [self.cases[i] for i in selected_ids]
        manifest = build_manifest(selected, self.live, self.memory)
        run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:6]
        directory = self.output_root / run_id
        directory.mkdir(parents=True, mode=0o700)
        started = time.time()
        results = [self._run_case(case, directory / case.id) for case in selected]
        drivers = {case.driver for case in selected}
        live_executed = any(r["mode"] == "live" and r["status"] == "executed" for r in results)
        mode = "live" if live_executed and not drivers & OFFLINE_DRIVERS else (
            "mixed" if live_executed else "offline_fixture")
        summary = summarize(results)
        run = {"run_id": run_id, "label": label, "mode": mode, "benchmark_valid": False,
               "benchmark_note": ("Offline fixtures execute fixed scripts; these are plumbing results, not model "
                                  "benchmarks." if mode != "live" else
                                  "Live development cases only; not the instructor's held-out evaluation."),
               "memory": self.memory if live_executed else "not_exercised",
               "memory_exercised": False,
               "model_calls": 0 if not live_executed else None,
               "started": started, "ended": time.time(), "summary": summary, "results": results,
               "manifest": manifest, "manifest_sha256": digest(manifest)}
        (directory / "results.json").write_text(json.dumps(run, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (directory / "report.md").write_text(markdown_report(run), encoding="utf-8")
        return run

    def _run_case(self, case, directory):
        base = {"case": case.summary(), "control": case.control, "checks": {}, "failed_checks": [],
                "workflow": None, "error": None, "initial_memory": None,
                "scripted_human": case.driver in OFFLINE_DRIVERS and bool(case.human_responses or case.approval)}
        if case.driver == "live_scheduler" and self.live is None:
            return base | {"status": "not_configured", "classification": "not_configured", "mode": "live",
                           "duration_seconds": None,
                           "notes": "Live DeepSeek/HKGAI runtime is not configured; no result is reported."}
        mode = "live" if case.driver == "live_scheduler" else "offline_fixture"
        directory.mkdir(parents=True, mode=0o700)
        session = None
        started = time.monotonic()
        try:
            session = _Session(directory, f"evaluation-{case.id}-memory-{self.memory}")
            base["initial_memory"] = {table: session.workflow.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                                      for table in ("lessons", "lesson_sources", "lesson_uses", "lesson_retrievals")}
            if any(base["initial_memory"].values()):
                raise WorkflowError("Evaluation case must start with fresh memory")
            if case.driver == "live_scheduler":
                root, state = _drive_live(case, session, self.live)
            else:
                root, state = _drive_offline(case, session)
            duration = time.monotonic() - started
            checks, workflow_state = _checks(case, session, root, duration)
            classification = _classify(case, checks, workflow_state)
            return base | {"status": "executed", "classification": classification, "mode": mode,
                           "duration_seconds": duration, "checks": checks,
                           "failed_checks": sorted(k for k, v in checks.items() if not v),
                           "workflow": workflow_state, "driver_state": state.get("state"),
                           "notes": "Fixed offline script; the goal text is not interpreted." if mode != "live" else ""}
        except Exception as error:  # Driver failures are results, not crashes of the batch.
            return base | {"status": "executed", "classification": "driver_error", "mode": mode,
                           "duration_seconds": time.monotonic() - started, "error": f"{type(error).__name__}: {error}"[:500],
                           "notes": "Driver raised before acceptance checks completed."}
        finally:
            if session is not None:
                session.close()


def summarize(results):
    scored = [r for r in results if r["status"] == "executed" and r["control"] is None]
    controls = [r for r in results if r["status"] == "executed" and r["control"] == "negative"]
    completed = [r for r in scored if r["classification"] == "completed"]
    durations = [r["duration_seconds"] for r in scored if r["duration_seconds"] is not None]
    classes = {name: sum(r["classification"] == name for r in results) for name in CLASSES}
    roots = []
    subtasks = []
    for result in scored:
        outcomes = (result.get("workflow") or {}).get("task_outcomes", [])
        root_records = [t for t in outcomes if t["parent"] is None]
        if len(root_records) == 1:
            roots.append((result, root_records[0]))
        subtasks.extend(t for t in outcomes if t["parent"] is not None)
    goal_successes = sum(r["classification"] == "completed" and t["verified_success"] for r, t in roots)
    terminal_times = [t["final_duration_seconds"] for _, t in roots if t["final_duration_seconds"] is not None]
    elapsed = [t["elapsed_seconds"] for _, t in roots]
    outcome_summary = {
        "expected": sum(r["control"] is None for r in results),
        "blocked": sum(r["classification"] == "blocked" for r in scored),
        "acceptance_pass_rate": len(completed) / len(scored) if scored else None,
        "goals_with_evidence": len(roots), "goals_missing_evidence": len(scored) - len(roots),
        "goals_verified_completed": goal_successes,
        "goal_completion_rate": goal_successes / len(scored) if scored else None,
        "goal_states": {state: sum(t["state"] == state for _, t in roots) for state in
                         ("pending", "running", "waiting_input", "waiting_approval", "succeeded", "failed", "cancelled")},
        "subtasks_observed": len(subtasks), "subtasks_verified_completed": sum(t["verified_success"] for t in subtasks),
        "subtask_completion_rate": sum(t["verified_success"] for t in subtasks) / len(subtasks) if subtasks else None,
        "goals_finalized": len(terminal_times),
        "mean_assignment_to_final_seconds": sum(terminal_times) / len(terminal_times) if terminal_times else None,
        "mean_observed_goal_elapsed_seconds": sum(elapsed) / len(elapsed) if elapsed else None,
        "cumulative_task_human_wait_seconds": sum(t["human_wait_seconds"] for _, t in roots) + sum(t["human_wait_seconds"] for t in subtasks),
    }
    return outcome_summary | {"cases": len(results), "executed": len(scored), "completed": len(completed),
            "completion_rate": (len(completed) / len(scored)) if scored else None,
            "mean_duration_seconds": (sum(durations) / len(durations)) if durations else None,
            "total_duration_seconds": sum(durations) if durations else None,
            "not_configured": classes["not_configured"],
            "negative_controls": len(controls),
            # A crashed/timed-out driver did not demonstrate a working acceptance check.
            "negative_controls_detected": sum(r["classification"] == "acceptance_failed" for r in controls),
            "classifications": classes}


def compare_memory(run_on, run_off):
    """Future Memory ON/OFF comparison. Refuses comparisons that would mislead."""
    if not isinstance(run_on, dict) or not isinstance(run_off, dict):
        return {"status": "not_comparable", "reasons": ["comparison requires two structured run reports"]}
    reasons = []
    if run_on.get("memory") != "on" or run_off.get("memory") != "off":
        reasons.append("runs must be explicitly memory=on and memory=off")
    if run_on.get("mode") != "live" or run_off.get("mode") != "live":
        reasons.append("both runs must be live-model runs; offline fixtures do not use memory")
    if run_on.get("memory_exercised") is not True:
        reasons.append("memory-on execution must be implemented and recorded, not just labelled on")
    conditions = []
    for label, run in (("on", run_on), ("off", run_off)):
        try:
            conditions.append(comparison_conditions(run))
            for result in run["results"]:
                duration = result.get("duration_seconds")
                if type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0:
                    raise ValueError("missing/non-finite executed-case duration")
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            reasons.append(f"{label}: {error}")
    if len(conditions) == 2 and conditions[0] != conditions[1]:
        reasons.append("case content, runtime, code/prompts/tools, budgets, interventions or initial-memory conditions differ")
    try:
        observed = [sorted({m for r in run.get("results", []) for m in (r.get("workflow") or {}).get("observed_models", [])})
                    for run in (run_on, run_off)]
    except (KeyError, TypeError, AttributeError):
        observed = []
    if len(observed) != 2 or not all(observed) or observed[0] != observed[1]:
        reasons.append("observed provider model identities are missing or differ")
    if reasons:
        return {"status": "not_comparable", "reasons": reasons}
    try:
        on, off = summarize(run_on["results"]), summarize(run_off["results"])
        if not on["executed"] or not off["executed"]:
            raise ValueError("comparison needs executed non-control cases")
    except (KeyError, TypeError, ValueError) as error:
        return {"status": "not_comparable", "reasons": [f"incomplete result evidence: {error}"]}
    fields = ("goal_completion_rate", "subtask_completion_rate", "acceptance_pass_rate",
              "mean_assignment_to_final_seconds", "completion_rate", "mean_duration_seconds")
    return {"status": "compared", "cases": sorted(r["case"]["id"] for r in run_on["results"]),
            **{key: {"on": on[key], "off": off[key]} for key in fields},
            "note": "Single paired run; no causal claim without repeated controlled trials. "
                    "Legacy completion_rate is contract acceptance, not goal completion. "
                    "Fingerprints do not authenticate experimental evidence."}


def _fmt(value, suffix=""):
    if value is None:
        return "—"
    return f"{value:.2f}{suffix}" if isinstance(value, float) else f"{value}{suffix}"


def _rate(value):
    return "—" if value is None else f"{value:.0%}"


def markdown_report(run):
    summary = run["summary"]
    rate = summary["completion_rate"]
    lines = [
        f"# Evaluation report — {run['run_id']}", "",
        f"- **Mode:** `{run['mode']}`",
        f"- **Benchmark valid:** `{str(run['benchmark_valid']).lower()}` — {run['benchmark_note']}",
        f"- **Model calls:** {'0' if run['model_calls'] == 0 else 'not counted exactly (see attempts)'}",
        f"- **Memory:** {run['memory']}",
        f"- **Manifest fingerprint:** `{run.get('manifest_sha256', 'unavailable in legacy run')}`",
        f"- **Started:** {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(run['started']))}", "",
        "## Summary", "",
        "| Metric | Value |", "| --- | --- |",
        f"| Scored cases executed | {summary['executed']} |",
        f"| Contract cases accepted (includes correct rejection behavior) | {summary['completed']} |",
        f"| Contract acceptance rate | {'—' if rate is None else f'{rate:.0%}'}"
        f"{'' if run['mode'] == 'live' else ' (offline_fixture plumbing, not a model benchmark)'} |",
        f"| Mean driver observation time (s) | {_fmt(summary['mean_duration_seconds'])} |",
        f"| Expected non-control cases / executed / blocked | {summary['expected']} / {summary['executed']} / {summary['blocked']} |",
        f"| Verified goals completed / executed requests | {summary['goals_verified_completed']} / {summary['executed']} |",
        f"| Goal completion rate | {_rate(summary['goal_completion_rate'])} |",
        f"| Verified subtasks / observed subtasks | {summary['subtasks_verified_completed']} / {summary['subtasks_observed']} |",
        f"| Subtask completion rate | {_rate(summary['subtask_completion_rate'])} |",
        f"| Goals with final status / missing workflow evidence | {summary['goals_finalized']} / {summary['goals_missing_evidence']} |",
        f"| Mean assignment-to-final-status time (s), including failures/cancellation/waits | {_fmt(summary['mean_assignment_to_final_seconds'])} |",
        f"| Mean observed goal elapsed time (s), including unfinished goals | {_fmt(summary['mean_observed_goal_elapsed_seconds'])} |",
        f"| Cumulative human wait across tasks (s; may overlap) | {_fmt(summary['cumulative_task_human_wait_seconds'])} |",
        f"| Not configured (excluded, not counted as success) | {summary['not_configured']} |",
        f"| Negative controls detected | {summary['negative_controls_detected']}/{summary['negative_controls']} |",
        "", "## Failure classification", "", "| Class | Count |", "| --- | --- |",
        *[f"| {name} | {count} |" for name, count in summary["classifications"].items() if count],
        "", "## Cases", "", "| Case | Driver | Status | Class | Time (s) | Failed checks |", "| --- | --- | --- | --- | --- | --- |"]
    for result in run["results"]:
        case = result["case"]
        control = " (negative control)" if result["control"] else ""
        lines.append(f"| `{case['id']}`{control} | {case['driver']} | {result['status']} | {result['classification']} | "
                     f"{_fmt(result['duration_seconds'])} | {', '.join(result['failed_checks']) or '—'} |")
    lines += ["", "## Notes", "",
              "- Acceptance checks are computed by the evaluator from persisted workflow state and actual artifacts; "
              "model self-assessments are never used as evidence.",
              "- Driver time ends at the last observed step; assignment-to-final-status time comes from persisted task timestamps. "
              "Unfinished goals have observed elapsed time but no final duration. Failed/cancelled durations are retained.",
              "- Cumulative per-task human waits may overlap; they are never silently subtracted from goal wall time.",
              "- A correctly rejected action can pass its contract without completing a goal. Missing workflow evidence is counted, not assumed successful.",
              "- Human responses in offline cases are scripted by the case definition."]
    for result in run["results"]:
        if result["error"] or result["notes"]:
            lines.append(f"- `{result['case']['id']}`: {result['error'] or result['notes']}")
    return "\n".join(lines) + "\n"


def list_runs(output_root):
    root = Path(output_root)
    if not root.is_dir():
        return []
    runs = []
    for path in sorted(root.glob("*/results.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        runs.append({"run_id": data["run_id"], "mode": data["mode"], "started": data["started"],
                     "summary": data["summary"], "benchmark_valid": data["benchmark_valid"],
                     "report": str(path.parent / "report.md")})
    return runs


def load_run(output_root, run_id):
    path = Path(output_root) / run_id / "results.json"
    if os.path.sep in run_id or not path.is_file():
        raise WorkflowError("Unknown evaluation run")
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = ["Evaluator", "compare_memory", "list_runs", "load_run", "markdown_report", "summarize"]
