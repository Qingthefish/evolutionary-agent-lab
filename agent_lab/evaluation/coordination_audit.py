"""Read-only coordination overhead audit of retained workflow databases.

Attributes recorded model attempts, reported tokens and tool calls to activity
classes using only persisted records: runner turns, tool-call reservations,
task states/events and runner stop reasons. Databases are opened read-only and
never modified. Output contains identifiers, counts, tool names and
framework-authored reasons only: no titles, messages, arguments or file text.

Attribution method (documented limits):
- Tool calls are counted exactly, one class per tool name.
- An attempt is attributed to a class only when every call it proposed belongs
  to that class; otherwise it is "mixed" and listed with its classes. Nothing
  is split fractionally, so attempt and token totals are never double counted.
- A final assistant reply without tools is a "completion" proposal.
- Attempts without a stored response keep unknown usage; they are never zero.
- Classes describe recorded actions, not the model's intent or their value.
"""

import argparse
import json
from pathlib import Path
import sqlite3
import sys

from ..budget import descendants
from .memory_protocol import tree_usage

SCHEMA = "c07-coordination-audit-v1"
CLASSES = {
    "productive": {"create_text", "update_text", "read_text", "delete_text", "run_python", "search_web",
                   "retrieve_text", "git_status", "git_diff", "git_log", "git_commit", "git_push"},
    "coordination": {"delegate_task", "delegate_with_inputs", "post_message", "read_messages", "list_tasks"},
    "handoff": {"offer_artifact", "accept_artifact"},
    "completion": {"submit_for_verification"},
    "recovery": {"retry_failed_task"},
    "human": {"ask_human"},
    "memory": {"search_memory", "select_memory", "record_lesson"},
}
# Coordination overhead in the topology sense: actions that exist only because
# work is split across tasks. Completion proposals are needed by both topologies.
OVERHEAD = ("coordination", "handoff")
POLLING = {"read_messages", "list_tasks"}
TERMINAL = {"succeeded", "failed", "cancelled"}


def tool_class(name):
    for label, names in CLASSES.items():
        if name in names:
            return label
    return "unclassified"


def stop_class(reason):
    """Map framework-authored stop reasons; anything else stays 'other'."""
    if not reason:
        return None
    text = reason.lower()
    for needle, label in (("provider attempt failed", "provider_failure"),
                          ("repeated identical", "repeated_outcomes"),
                          ("delegated task", "child_failure"),
                          ("model attempt budget", "task_attempt_budget"),
                          ("task-tree attempts budget", "shared_attempt_budget"),
                          ("tool_calls budget", "tool_call_budget"), ("tool-call budget", "tool_call_budget"),
                          ("token budget", "token_budget"), ("duration", "duration_budget")):
        if needle in text:
            return label
    return "other"


class _Records:
    """Duck-typed stand-in exposing `.db` for existing read-only helpers."""

    def __init__(self, path):
        self.path = Path(path)
        self.db = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA query_only=ON")

    def table(self, name):
        return self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None

    def close(self):
        self.db.close()


def _loads(text):
    try:
        return json.loads(text) if text else None
    except (TypeError, ValueError):
        return None


def _empty():
    return {"attempts": 0, "known_tokens": 0, "unknown_usage_attempts": 0, "tool_calls": 0,
            "proposed_not_reserved": 0}


def _add(bucket, attempt):
    bucket["attempts"] += 1
    bucket["tool_calls"] += attempt["tool_calls"]
    bucket["proposed_not_reserved"] += attempt["proposed_not_reserved"]
    if attempt["tokens"] is None:
        bucket["unknown_usage_attempts"] += 1
    else:
        bucket["known_tokens"] += attempt["tokens"]


def _task_audit(records, task, children):
    tid = task["id"]
    calls = {}
    if records.table("tool_calls"):
        for row in records.db.execute("SELECT call_id,name,arguments,status,result FROM tool_calls WHERE task=? ORDER BY rowid", (tid,)):
            calls[row["call_id"]] = dict(row)
    received, handoff_reads = {}, set()
    failures = {}
    for event in records.db.execute("SELECT kind,detail FROM events WHERE task=? AND kind IN "
                                    "('artifact_received','provider_request_failed','tool_reserved') ORDER BY sequence", (tid,)):
        detail = _loads(event["detail"]) or {}
        if event["kind"] == "artifact_received" and isinstance(detail.get("path"), str):
            received[detail["path"]] = (detail.get("sha256"), detail.get("bytes"))
        elif event["kind"] == "provider_request_failed":
            failures[detail.get("number")] = (detail.get("diagnostics") or {}).get("kind", "unknown")
        elif event["kind"] == "tool_reserved" and detail.get("name") == "read_text":
            call = calls.get(detail.get("call_id"))
            if call is None or call["status"] != "succeeded":
                continue
            result = (_loads(call["result"]) or {}).get("result", {})
            if result.get("sha256") and received.get(result.get("path")) == (result["sha256"], result.get("bytes")):
                handoff_reads.add(call["call_id"])

    def classify(call):
        return "handoff" if call.get("call_id") in handoff_reads else tool_class(call["name"])

    child_done = None
    if children and all(c["state"] in TERMINAL for c in children):
        child_done = max(c["ended"] for c in children if c["ended"] is not None)
    attempts, by_class, after_children = [], {}, _empty()
    session = (records.db.execute("SELECT status,stop_reason,transcript FROM runner_sessions WHERE task=?", (tid,)).fetchone()
               if records.table("runner_sessions") else None)
    turns = (records.db.execute("SELECT number,status,response,started FROM runner_turns WHERE task=? ORDER BY number", (tid,)).fetchall()
             if records.table("runner_turns") else [])
    for turn in turns:
        response = _loads(turn["response"])
        names, labels, reserved = [], set(), 0
        if response is None:
            label = "provider_failure" if turn["status"] == "provider_error" else "unknown_no_response"
        elif response.get("finish_reason") == "stop":
            label = "completion"
        else:
            for proposed in (response.get("message") or {}).get("tool_calls") or []:
                recorded = calls.get(proposed.get("id"))
                reserved += recorded is not None
                call = recorded or {"name": (proposed.get("function") or {}).get("name"), "arguments": None}
                names.append(call["name"])
                labels.add(classify(call))
            label = labels.pop() if len(labels) == 1 else ("mixed" if labels else "unknown_no_calls")
        usage = (response or {}).get("usage") or {}
        attempt = {"number": turn["number"], "class": label, "tools": names,
                   # Reserved calls reconcile with tree_usage; rejected or skipped
                   # proposals never reached the tool-call ledger.
                   "tool_calls": reserved, "proposed_not_reserved": len(names) - reserved,
                   "tokens": usage.get("total_tokens") if isinstance(usage.get("total_tokens"), int) else None,
                   "after_children_done": child_done is not None and turn["started"] >= child_done,
                   "provider_failure_kind": failures.get(turn["number"]) if response is None else None}
        if label == "mixed":
            attempt["mixed_classes"] = sorted({classify(calls.get(p.get("id")) or {"name": n, "arguments": None})
                                               for p, n in zip((response.get("message") or {}).get("tool_calls") or [], names)})
        attempts.append(attempt)
        _add(by_class.setdefault(label, _empty()), attempt)
        if attempt["after_children_done"]:
            _add(after_children, attempt)
    call_classes, seen, repeats, polling = {}, set(), {}, {}
    for call in calls.values():
        label = classify(call)
        call_classes[label] = call_classes.get(label, 0) + 1
        key = (call["name"], call["arguments"])
        if key in seen:
            repeats[call["name"]] = repeats.get(call["name"], 0) + 1
        seen.add(key)
        if call["name"] in POLLING:
            polling[call["name"]] = polling.get(call["name"], 0) + 1
    verification_failures = 0
    if session is not None:
        for message in _loads(session["transcript"]) or []:
            content = _loads(message.get("content")) if isinstance(message, dict) and message.get("role") == "user" else None
            if isinstance(content, dict) and content.get("kind") == "trusted_verification_failure":
                verification_failures += 1
    return {"task_id": tid, "parent": task["parent"], "assignee": task["assignee"], "state": task["state"],
            "depth": task["depth"], "children": [c["id"] for c in children],
            "children_succeeded": sum(c["state"] == "succeeded" for c in children),
            "runner": None if session is None else {"status": session["status"], "stop_reason": session["stop_reason"],
                                                    "stop_class": stop_class(session["stop_reason"])},
            "attempts": len(attempts), "attempts_by_class": dict(sorted(by_class.items())),
            "tool_calls_by_class": dict(sorted(call_classes.items())), "after_children_done": after_children,
            "exact_repeated_calls": dict(sorted(repeats.items())), "polling_calls": dict(sorted(polling.items())),
            "trusted_verification_failures": verification_failures, "attempt_log": attempts}


def audit_root(records, root):
    """Audit one recorded root tree; totals are reconciled against tree_usage."""
    tree = descendants(records, root)
    if not tree:
        raise ValueError("Root task is not present in this database")
    rows = {t["id"]: t for t in tree}
    tasks = [_task_audit(records, t, [c for c in tree if c["parent"] == t["id"]]) for t in sorted(tree, key=lambda t: t["depth"])]
    totals, by_class = _empty(), {}
    for task in tasks:
        for label, bucket in task["attempts_by_class"].items():
            target = by_class.setdefault(label, _empty())
            for key in target:
                target[key] += bucket[key]
                totals[key] += bucket[key]
    usage = tree_usage(records, root)
    reconciliation = {"tree_usage": usage,
                      "attempts_match": usage["reserved_model_attempts"] == totals["attempts"],
                      "known_tokens_match": usage["reported_tokens"] == totals["known_tokens"],
                      "unknown_usage_match": usage["unknown_usage_attempts"] == totals["unknown_usage_attempts"],
                      "tool_calls_match": usage["tool_calls"] == totals["tool_calls"]}
    overhead = {key: sum(by_class.get(c, _empty())[key] for c in OVERHEAD) for key in totals}
    root_row = rows[root]
    failed_after_children = [t for t in tasks if t["children"] and t["state"] == "failed"
                             and t["children_succeeded"] == len(t["children"])]
    return {"root": root, "root_state": root_row["state"],
            "root_error": ((_loads(root_row["evidence"]) or {}).get("error") or "")[:300] or None,
            "tasks": len(tasks), "totals": totals, "attempts_by_class": dict(sorted(by_class.items())),
            "attributed_overhead": overhead, "mixed_attempts": by_class.get("mixed", _empty())["attempts"],
            "parents_failed_after_all_children_succeeded": [
                {"task_id": t["task_id"], "assignee": t["assignee"], "stop_class": (t["runner"] or {}).get("stop_class"),
                 "after_children_done": t["after_children_done"]} for t in failed_after_children],
            "reconciliation": reconciliation, "per_task": tasks}


def _report_rows(directory, report):
    """Map each recorded run slot to its own database and root; never all roots."""
    for row in report.get("results", []):
        if not row.get("root"):
            yield row, None, "no root recorded (not run or failed before task creation)"
            continue
        if row.get("state_directory"):  # C07 topology runs
            path = directory / row["state_directory"] / "workflow.sqlite3"
        elif row.get("phase") == "training":  # frozen-experience trials
            path = directory / f"replicate-{row['replicate']}" / "training" / "workflow.sqlite3"
        elif row.get("phase") == "probe":
            path = directory / f"replicate-{row['replicate']}" / f"probe-{row['slot']}-{row['memory']}" / "workflow.sqlite3"
        else:
            yield row, None, "unrecognized report layout"
            continue
        resolved = path.resolve()
        if not resolved.is_relative_to(directory):
            yield row, None, "database path is outside the run directory"
            continue
        yield row, resolved, None


def audit_run(directory):
    directory = Path(directory).resolve()
    report = json.loads((directory / "experiment.json").read_text())
    slots, groups = [], {}
    for row, path, problem in _report_rows(directory, report):
        label = {k: row.get(k) for k in ("slot", "replicate", "topology", "phase", "memory", "case_id") if k in row}
        if "case_id" not in label and isinstance(row.get("case"), dict):
            label["case_id"] = row["case"].get("id")
        if problem or not path.is_file():
            slots.append({**label, "status": row.get("status"), "audit": None,
                          "missing": problem or "database not available"})
            continue
        records = _Records(path)
        try:
            result = audit_root(records, row["root"])
        finally:
            records.close()
        slots.append({**label, "status": row.get("status"), "classification": row.get("classification"), "audit": result})
        key = row.get("topology") or (f"{row['phase']}:{row.get('memory')}" if row.get("phase") else "all")
        group = groups.setdefault(key,
                                  {"slots": 0, "totals": _empty(), "attributed_overhead": _empty()})
        group["slots"] += 1
        for key in group["totals"]:
            group["totals"][key] += result["totals"][key]
            group["attributed_overhead"][key] += result["attributed_overhead"][key]
    return {"schema": SCHEMA, "source": {"run_id": report.get("run_id"), "mode": report.get("mode"),
            "protocol": report.get("protocol")}, "slots": slots, "groups": groups,
            "interpretation": "Observational accounting of recorded actions; not causal evidence or a benchmark."}


def audit_database(path, roots=None):
    records = _Records(path)
    try:
        if not roots:
            roots = [r[0] for r in records.db.execute("SELECT id FROM tasks WHERE parent IS NULL ORDER BY rowid")]
        results = [audit_root(records, root) for root in roots]
    finally:
        records.close()
    return {"schema": SCHEMA, "source": {"database": Path(path).name}, "roots": results,
            "warning": None if roots else "No roots found",
            "interpretation": "Observational accounting of recorded actions; not causal evidence or a benchmark. "
                              "Forked probe databases also contain training roots; prefer --run for trial directories."}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m agent_lab.evaluation.coordination_audit",
                                     description="Read-only coordination overhead audit; no model calls, no writes")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--run", help="C07 or experience run directory containing experiment.json")
    source.add_argument("--db", help="A single workflow.sqlite3 database")
    parser.add_argument("--root", action="append", help="Root task id (with --db); default: every top-level task")
    parser.add_argument("--summary", action="store_true", help="Omit per-attempt logs")
    args = parser.parse_args(argv)
    try:
        result = audit_run(args.run) if args.run else audit_database(args.db, args.root)
    except (OSError, ValueError, KeyError, sqlite3.Error) as error:
        parser.exit(1, f"Audit failed: {error}\n")
    if args.summary:
        for item in [*(s["audit"] for s in result.get("slots", []) if s.get("audit")), *result.get("roots", [])]:
            for task in item["per_task"]:
                task.pop("attempt_log", None)
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
