"""Batch evaluation over development cases. Independent of any user interface.

Each case runs in a fresh state directory with its own workflow database, so
cases and memory namespaces never share state. Acceptance checks are computed
by this evaluator from persisted workflow records and actual artifacts, never
from model text. Offline drivers execute fixed scripts: their results are
`offline_fixture` plumbing evidence with `benchmark_valid: false`.
"""

import json
import os
from pathlib import Path
import time
from uuid import uuid4

from ..core import Workflow, WorkflowError
from ..files import FileTools
from ..inspection import ArtifactInspector, ArtifactMissingError
from ..memory import ExperienceMemory
from ..runtime import LIVE_AGENTS, LiveConfig, build_live_scheduler, policy_for_task
from .. import offline_scenarios

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
        try:
            self.workflow.register_actor(HUMAN, "human")
            for agent in offline_scenarios.AGENTS:
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


def _drive_live(case, session, live):
    """Live DeepSeek scheduler run. Unvalidated: no live call has been made yet."""
    members = LIVE_AGENTS
    chat = session.workflow.create_chat("group", [HUMAN, *members])
    root = session.workflow.create_task(chat, HUMAN, "coordinator", case.goal)
    scheduler = build_live_scheduler(session.workflow, session.files, root, human=HUMAN, live=live,
        policy=policy_for_task(live, constraints=case.constraints, root_artifacts=case.expected.artifacts))
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
    subtask_records = []
    for index, expected in enumerate(case.expected.subtasks):
        prefix = f"subtask:{index}:"
        matches = [row for row in tree if row["id"] != root and row["assignee"] == expected.assignee
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
    ids = [row["id"] for row in tree]
    marks = ",".join("?" * len(ids))
    requests = workflow.db.execute(f"""SELECT r.*,t.assignee FROM requests r JOIN tasks t ON t.id=r.task
        WHERE r.task IN ({marks})""", ids).fetchall() if case.expected.human_requests else []
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
    return checks, {"root_state": task["state"], "tasks": len(tree), "task_states": states,
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
            raise WorkflowError("Live memory-on execution is not implemented; refusing a misleading experiment label")
        if live is not None and not isinstance(live, LiveConfig):
            raise WorkflowError("Live evaluation requires the shared explicit LiveConfig")
        self.cases = {case.id: case for case in cases}
        if live is not None:
            for case in self.cases.values():
                if case.driver == "live_scheduler":
                    policy_for_task(live, constraints=case.constraints, root_artifacts=case.expected.artifacts)
        self.output_root = Path(output_root)
        self.live, self.memory = live, memory

    def run(self, case_ids=None, *, label=None):
        selected = [self.cases[i] for i in (case_ids or sorted(self.cases))]
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
               "started": started, "ended": time.time(), "summary": summary, "results": results}
        (directory / "results.json").write_text(json.dumps(run, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (directory / "report.md").write_text(markdown_report(run), encoding="utf-8")
        return run

    def _run_case(self, case, directory):
        base = {"case": case.summary(), "control": case.control, "checks": {}, "failed_checks": [],
                "workflow": None, "error": None, "scripted_human": bool(case.human_responses or case.approval)}
        if case.driver == "live_scheduler" and self.live is None:
            return base | {"status": "not_configured", "classification": "not_configured", "mode": "live",
                           "duration_seconds": None,
                           "notes": "Live DeepSeek/HKGAI runtime is not configured; no result is reported."}
        mode = "live" if case.driver == "live_scheduler" else "offline_fixture"
        directory.mkdir(parents=True, mode=0o700)
        session = _Session(directory, f"evaluation-{case.id}-memory-{self.memory}")
        started = time.monotonic()
        try:
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
            session.close()


def summarize(results):
    scored = [r for r in results if r["status"] == "executed" and r["control"] is None]
    controls = [r for r in results if r["status"] == "executed" and r["control"] == "negative"]
    completed = [r for r in scored if r["classification"] == "completed"]
    durations = [r["duration_seconds"] for r in scored if r["duration_seconds"] is not None]
    classes = {name: sum(r["classification"] == name for r in results) for name in CLASSES}
    return {"cases": len(results), "executed": len(scored), "completed": len(completed),
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
    reasons = []
    if run_on.get("memory") != "on" or run_off.get("memory") != "off":
        reasons.append("runs must be explicitly memory=on and memory=off")
    if run_on.get("mode") != "live" or run_off.get("mode") != "live":
        reasons.append("both runs must be live-model runs; offline fixtures do not use memory")
    if run_on.get("memory_exercised") is not True:
        reasons.append("memory-on execution must be implemented and recorded, not just labelled on")
    ids_on = {r["case"]["id"] for r in run_on.get("results", [])}
    ids_off = {r["case"]["id"] for r in run_off.get("results", [])}
    if ids_on != ids_off:
        reasons.append("runs must cover the same cases")
    if reasons:
        return {"status": "not_comparable", "reasons": reasons}
    on, off = run_on["summary"], run_off["summary"]
    return {"status": "compared", "cases": sorted(ids_on),
            "completion_rate": {"on": on["completion_rate"], "off": off["completion_rate"]},
            "mean_duration_seconds": {"on": on["mean_duration_seconds"], "off": off["mean_duration_seconds"]},
            "note": "Single paired run; no causal claim without repeated controlled trials."}


def _fmt(value, suffix=""):
    if value is None:
        return "—"
    return f"{value:.2f}{suffix}" if isinstance(value, float) else f"{value}{suffix}"


def markdown_report(run):
    summary = run["summary"]
    rate = summary["completion_rate"]
    lines = [
        f"# Evaluation report — {run['run_id']}", "",
        f"- **Mode:** `{run['mode']}`",
        f"- **Benchmark valid:** `{str(run['benchmark_valid']).lower()}` — {run['benchmark_note']}",
        f"- **Model calls:** {'0' if run['model_calls'] == 0 else 'not counted exactly (see attempts)'}",
        f"- **Memory:** {run['memory']}",
        f"- **Started:** {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(run['started']))}", "",
        "## Summary", "",
        "| Metric | Value |", "| --- | --- |",
        f"| Scored cases executed | {summary['executed']} |",
        f"| Completed (all independent checks passed) | {summary['completed']} |",
        f"| Completion rate | {'—' if rate is None else f'{rate:.0%}'}"
        f"{'' if run['mode'] == 'live' else ' (offline_fixture plumbing, not a model benchmark)'} |",
        f"| Mean execution time (s) | {_fmt(summary['mean_duration_seconds'])} |",
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
              "- Execution time is wall-clock time from case start to the last driver step, including scripted human waits.",
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
