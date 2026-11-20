"""Read-only consistency checks for ordinary development batch JSON.

This does not authenticate a run or recheck its artifacts, database or model
responses. Topology, frozen-memory and official protocols have other schemas.
"""

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

from ..core import WorkflowError
from ..protocol import strict_json
from .cases import parse_case
from .harness import CLASSES, OFFLINE_DRIVERS, _classify, _human_matches, summarize
from .manifest import digest

MAX_BYTES = 16 * 1024 * 1024
STATES = {"pending", "running", "waiting_input", "waiting_approval", "succeeded", "failed", "cancelled"}
TERMINAL = {"succeeded", "failed", "cancelled"}
EMPTY_MEMORY = {"lessons": 0, "lesson_sources": 0, "lesson_uses": 0, "lesson_retrievals": 0}


class _Invalid(ValueError):
    def __init__(self, code, location):
        self.code, self.location = code, location


def _need(condition, code, location):
    if not condition:
        raise _Invalid(code, location)


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def _same(left, right):
    # JSON identity distinguishes True from 1, unlike Python equality.
    return digest(left) == digest(right)


def _read(path):
    """Bound memory use; never follow a report symlink or block on a FIFO."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None, None
    except OSError:
        raise _Invalid("unreadable_file", path.name) from None
    try:
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            _need(stat.S_ISREG(info.st_mode) and info.st_size <= MAX_BYTES,
                  "unsupported_file", path.name)
            raw = stream.read(MAX_BYTES + 1)
            _need(len(raw) <= MAX_BYTES, "file_too_large", path.name)
        fingerprint = hashlib.sha256(raw).hexdigest()
        return strict_json(raw.decode("utf-8")), fingerprint
    except _Invalid:
        raise
    except (OSError, ValueError, UnicodeError, RecursionError):
        raise _Invalid("invalid_json", path.name) from None


def _manifest(record, location):
    manifest = record["manifest"]
    required = {"schema_version", "cases", "runtime", "code_sha256", "prompt_sha256", "tools_sha256",
                "interventions", "initial_memory", "condition"}
    _need(isinstance(manifest, dict) and set(manifest) == required
          and type(manifest["schema_version"]) is int and manifest["schema_version"] == 1,
          "unsupported_manifest", location)
    _need(record["manifest_sha256"] == digest(manifest), "manifest_fingerprint", location)
    for key in ("code_sha256", "prompt_sha256", "tools_sha256"):
        _need(isinstance(manifest[key], str) and re.fullmatch("[0-9a-f]{64}", manifest[key]),
              "manifest_identity", location)
    _need(manifest["condition"] in ({"memory": "on"}, {"memory": "off"})
          and isinstance(manifest["runtime"], dict), "manifest_conditions", location)
    _need(_same(manifest["initial_memory"], {"reset": "fresh-per-case", "seed": "empty",
                "scope": "agent+conversation+evaluation-namespace"})
          and _same(manifest["interventions"], {"live": "external-human-pause-no-scripted-responses-v1",
                "offline": "case-defined-scripted-responses-v1", "include_wait_in_elapsed": True}),
          "manifest_protocol", location)
    runtime = manifest["runtime"]
    if runtime.get("provider") is None:
        _need(_same(runtime, {"provider": None, "model": None, "roles": None, "tree_limits": None}),
              "runtime_conditions", location)
    else:
        _need(runtime["provider"] in ("deepseek", "hkgai") and isinstance(runtime["model"], str)
              and bool(runtime["model"]) and isinstance(runtime["roles"], dict) and bool(runtime["roles"])
              and isinstance(runtime["tree_limits"], dict) and bool(runtime["tree_limits"])
              and manifest["condition"]["memory"] == "off"
              and runtime["capabilities"]["memory"] is False, "runtime_conditions", location)
    definitions = manifest["cases"]
    _need(isinstance(definitions, list) and bool(definitions), "missing_cases", location)
    cases = {}
    for index, definition in enumerate(definitions):
        at = f"{location}.manifest.cases[{index}]"
        _need(isinstance(definition, dict), "invalid_case", at)
        # Dataclass manifests include optional assignee=null; the source case
        # parser represents an unspecified selector by an absent key instead.
        source = json.loads(json.dumps(definition))
        for human in source.get("expected", {}).get("human_requests", []):
            if isinstance(human, dict) and human.get("assignee") is None:
                human.pop("assignee", None)
        try:
            case = parse_case(source)
        except (WorkflowError, TypeError, ValueError, AttributeError):
            raise _Invalid("invalid_case", at) from None
        _need(case.split == "development", "unsupported_split", at)
        _need(case.id not in cases, "duplicate_case", at)
        cases[case.id] = case
    _need(list(cases) == sorted(cases), "manifest_case_order", location)
    return cases


def _check_names(case):
    names = {"final_state", "task_count", "within_time"}

    def artifacts(expected, prefix=""):
        names.update(prefix + "artifact:" + path for path in expected.artifacts)
        names.update(prefix + "absent:" + path for path in expected.absent_artifacts)
        names.update(prefix + f"criterion:{i}:{rule.path}:{rule.kind}" for i, rule in enumerate(expected.criteria))

    artifacts(case.expected)
    for index, expected in enumerate(case.expected.subtasks):
        prefix = f"subtask:{index}:"
        names.update({prefix + "unique_match", prefix + "final_state"})
        artifacts(expected, prefix)
    names.update(f"human:{i}:{h.kind}:{h.outcome}" for i, h in enumerate(case.expected.human_requests))
    if case.expected.remote_branch_verified:
        names.add("remote_branch_verified")
    return names


def _workflow(workflow, location):
    _need(isinstance(workflow, dict), "missing_workflow", location)
    tasks = workflow["task_outcomes"]
    _need(isinstance(tasks, list) and bool(tasks), "missing_task_outcomes", location)
    by_id = {}
    for task in tasks:
        identifier = task["task_id"]
        _need(isinstance(identifier, str) and bool(identifier) and identifier not in by_id,
              "duplicate_or_invalid_task", location)
        _need(isinstance(task["state"], str) and task["state"] in STATES
              and type(task["verified_success"]) is bool
              and (not task["verified_success"] or task["state"] == "succeeded"), "task_state", location)
        _need(_number(task["elapsed_seconds"]) and _number(task["human_wait_seconds"]), "task_timing", location)
        final = task["final_duration_seconds"]
        _need((_number(final) and final == task["elapsed_seconds"]) if task["state"] in TERMINAL
              else final is None, "task_final_timing", location)
        by_id[identifier] = task
    roots = [task for task in tasks if task["parent"] is None]
    _need(len(roots) == 1 and roots[0]["task_id"] == workflow["root_task"]
          and roots[0]["state"] == workflow["root_state"], "root_identity", location)
    root = roots[0]
    connected = {root["task_id"]}
    for task in tasks:
        seen = set()
        while task["task_id"] not in connected:
            identifier = task["task_id"]
            _need(identifier not in seen and task["parent"] in by_id, "task_tree", location)
            seen.add(identifier)
            task = by_id[task["parent"]]
        connected.update(seen)
    evidence = workflow["evidence"]
    _need(evidence is None or isinstance(evidence, dict), "root_evidence", location)
    passed = (evidence or {}).get("checks", {})
    _need(isinstance(passed, dict), "root_evidence", location)
    trusted = root["state"] == "succeeded" and bool(passed) and all(value is True for value in passed.values())
    _need(root["verified_success"] == trusted and (root["state"] != "succeeded" or trusted),
          "root_evidence", location)
    _need(type(workflow["tasks"]) is int and workflow["tasks"] == len(tasks)
          and _same(workflow["task_states"], dict(Counter(task["state"] for task in tasks))),
          "task_totals", location)
    _need(_number(workflow["workflow_elapsed_seconds"]) and _number(workflow["human_wait_seconds"]),
          "workflow_timing", location)
    _need(isinstance(workflow["observed_models"], list)
          and all(isinstance(model, str) and model for model in workflow["observed_models"]),
          "model_identity", location)
    return root, by_id


def _human_records(case, workflow, tasks, checks, location):
    interventions = workflow["human_interventions"]
    recorded = workflow["human_request_checks"]
    _need(isinstance(interventions, list) and isinstance(recorded, list), "human_records", location)
    identifiers = set()
    for request in interventions:
        identifier = request["request_id"]
        _need(isinstance(identifier, str) and bool(identifier) and identifier not in identifiers
              and request["task_id"] in tasks and request["assignee"] == tasks[request["task_id"]]["assignee"]
              and request["kind"] in ("approval", "clarification") and type(request["answered"]) is bool
              and type(request["consumed"]) is bool
              and (request["approved"] is None or (type(request["approved"]) is int and request["approved"] in (0, 1)))
              and (request["answered"] or (request["approved"] is None and not request["consumed"]))
              and (request["kind"] != "approval" or not request["answered"] or request["approved"] is not None)
              and (not request["consumed"] or (request["answered"] and request["approved"] == 1))
              and (request["kind"] == "approval" or (request["approved"] is None and not request["consumed"])),
              "human_records", location)
        identifiers.add(identifier)
    expected_records = []
    for index, expected in enumerate(case.expected.human_requests):
        matches = [request for request in interventions if request["kind"] == expected.kind
                   and (expected.assignee is None or request["assignee"] == expected.assignee)
                   and _human_matches(request, expected.outcome)]
        expected_records.append({"kind": expected.kind, "outcome": expected.outcome, "assignee": expected.assignee,
                                 "expected_count": expected.count, "actual_count": len(matches),
                                 "request_ids": [request["request_id"] for request in matches]})
        _need(checks[f"human:{index}:{expected.kind}:{expected.outcome}"] == (len(matches) == expected.count),
              "human_checks", location)
    _need(_same(recorded, expected_records), "human_records", location)


def _rows(record, cases, location):
    results = record["results"]
    _need(isinstance(results, list), "missing_results", location)
    identifiers = []
    for index, row in enumerate(results):
        at = f"{location}.results[{index}]"
        identifier = row["case"]["id"]
        _need(isinstance(identifier, str) and identifier in cases and identifier not in identifiers,
              "unexpected_or_duplicate_case", at)
        identifiers.append(identifier)
        case = cases[identifier]
        expected = case.summary()
        actual = dict(row["case"])
        expected.pop("source")
        actual.pop("source", None)
        _need(_same(actual, expected), "case_content", at)
        _need(row["control"] == case.control and type(row["scripted_human"]) is bool
              and row["scripted_human"] == expected["scripted_human"], "case_labels", at)
        _need(row["mode"] == ("live" if case.driver == "live_scheduler" else "offline_fixture")
              and isinstance(row["classification"], str) and row["classification"] in CLASSES,
              "result_labels", at)
        if row["status"] == "not_configured":
            _need(case.driver == "live_scheduler" and row["classification"] == "not_configured"
                  and row["duration_seconds"] is None and row["workflow"] is None
                  and row["checks"] == {} and row["failed_checks"] == [] and row["initial_memory"] is None,
                  "not_configured_evidence", at)
            continue
        _need(row["status"] == "executed" and _number(row["duration_seconds"]), "result_timing", at)
        _need(record["manifest"]["runtime"]["provider"] in ("deepseek", "hkgai")
              if case.driver == "live_scheduler" else True, "runtime_conditions", at)
        initial = row["initial_memory"]
        if row["classification"] == "driver_error":
            # The driver also records a failure if its fresh-memory check fails;
            # retain those observed nonzero counts rather than reject the error.
            _need(initial is None or (isinstance(initial, dict) and set(initial) == set(EMPTY_MEMORY)
                  and all(type(value) is int and value >= 0 for value in initial.values())), "initial_memory", at)
            _need(row["workflow"] is None and row["checks"] == {} and row["failed_checks"] == [],
                  "driver_error_evidence", at)
            continue
        _need(_same(initial, EMPTY_MEMORY), "initial_memory", at)
        checks = row["checks"]
        _need(isinstance(checks, dict) and set(checks) == _check_names(case)
              and all(type(value) is bool for value in checks.values()), "check_inventory", at)
        _need(row["failed_checks"] == sorted(key for key, value in checks.items() if not value),
              "failed_checks", at)
        root, tasks = _workflow(row["workflow"], at)
        _human_records(case, row["workflow"], tasks, checks, at)
        _need(checks["final_state"] == (root["state"] == case.expected.final_state)
              and checks["task_count"] == (row["workflow"]["tasks"] >= case.expected.min_tasks)
              and checks["within_time"] == (row["duration_seconds"] <= case.expected.max_seconds
                                            and root["elapsed_seconds"] <= case.expected.max_seconds),
              "derived_checks", at)
        _need(row["classification"] == _classify(case, checks, row["workflow"]), "classification", at)
    return identifiers


def _validate(record, location, checkpoint):
    _need(isinstance(record, dict) and "purpose" not in record, "unsupported_layout", location)
    _need(isinstance(record["run_id"], str) and bool(record["run_id"]) and _number(record["started"]),
          "run_identity", location)
    cases = _manifest(record, location)
    identifiers = _rows(record, cases, location)
    # Finite scalar inputs can still overflow while summing. Refuse rather than
    # emitting Infinity or crashing the CLI for a progress-only checkpoint.
    try:
        digest(summarize(record["results"]))
    except (ValueError, OverflowError):
        raise _Invalid("summary_nonfinite", location) from None
    if checkpoint:
        selected = record["selected_case_ids"]
        _need(isinstance(selected, list) and all(isinstance(i, str) for i in selected)
              and len(selected) == len(cases) and set(selected) == set(cases), "selected_cases", location)
        _need(identifiers == selected[:len(identifiers)], "checkpoint_order", location)
        active = record["active_case_id"]
        remaining = selected[len(identifiers):]
        _need(active is None or (bool(remaining) and active == remaining[0]), "checkpoint_active", location)
        _need(record["not_started_case_ids"] == (remaining[1:] if active is not None else remaining),
              "checkpoint_remaining", location)
        _need(record["status"] in ("complete", "incomplete"), "checkpoint_status", location)
        if record["status"] == "complete":
            _need(not remaining and active is None and _number(record["ended"])
                  and record["ended"] >= record["started"], "checkpoint_completion", location)
    else:
        _need(set(identifiers) == set(cases), "missing_result_cases", location)
        _need(_number(record["ended"]) and record["ended"] >= record["started"], "run_timing", location)
        _need(_same(record["summary"], summarize(record["results"])), "summary_mismatch", location)
        live = any(row["mode"] == "live" and row["status"] == "executed" for row in record["results"])
        offline = any(case.driver in OFFLINE_DRIVERS for case in cases.values())
        mode = ("mixed" if offline else "live") if live else "offline_fixture"
        _need(record["mode"] == mode and record["benchmark_valid"] is False
              and record["memory_exercised"] is False
              and record["memory"] == (record["manifest"]["condition"]["memory"] if live else "not_exercised")
              and _same(record["model_calls"], None if live else 0), "run_labels", location)
    return cases, identifiers


def audit_run(directory):
    """Return sanitized findings; never instantiate runtime services or write files.

    Exit/status semantics concern record consistency, not task success. A valid
    batch containing failed goals can be consistent. Unknown live usage stays
    unknown; audit model_calls=0 describes this reader only.
    """
    report = {"schema_version": 1, "evidence_class": "development_run_json_consistency",
              "status": "invalid", "authenticity_verified": False, "benchmark_valid": False,
              "model_calls": 0, "source_usage_verified": False, "files": {}, "findings": [],
              "summary": None, "selected_case_ids": [], "returned_case_ids": [],
              "active_case_id": None, "not_started_case_ids": []}
    records = {}
    for name in ("results.json", "run-progress.json"):
        try:
            value, fingerprint = _read(Path(directory) / name)
            if fingerprint is None:
                continue
            report["files"][name] = {"sha256": fingerprint}
            cases, identifiers = _validate(value, name, name == "run-progress.json")
            records[name] = value
            report["returned_case_ids"] = identifiers
            report["selected_case_ids"] = sorted(cases)
        except _Invalid as error:
            report["findings"].append({"code": error.code, "location": error.location})
        except (KeyError, TypeError, ValueError, AttributeError, RecursionError, OverflowError):
            report["findings"].append({"code": "invalid_structure", "location": name})
    final = records.get("results.json")
    progress = records.get("run-progress.json")
    if final is None and progress is None and not report["findings"]:
        report["findings"].append({"code": "missing_reports", "location": "run"})
    if final is not None:
        report["summary"] = summarize(final["results"])
    if progress is not None:
        report.update({key: progress[key] for key in ("selected_case_ids", "active_case_id", "not_started_case_ids")})
        if final is not None:
            keys = ("run_id", "started", "manifest", "manifest_sha256", "results")
            if any(not _same(final[key], progress[key]) for key in keys) or (
                    progress["status"] == "complete" and not _same(final["ended"], progress["ended"])):
                report["findings"].append({"code": "checkpoint_mismatch", "location": "run"})
        else:
            report["summary"] = summarize(progress["results"])
    if not report["findings"]:
        report["status"] = "consistent" if final is not None and (
            progress is None or progress["status"] == "complete") else "incomplete"
    return report


def markdown_audit(report):
    lines = ["# Development run JSON audit", "", f"Status: **{report['status']}**", "",
             "Internal consistency only; original artifacts, task database and model responses are not verified.",
             "Audit model calls: 0. Source usage is not verified. This is not an official benchmark.", "",
             f"Returned cases: {len(report['returned_case_ids'])}/{len(report['selected_case_ids'])}", "",
             "| Finding | JSON location |", "| --- | --- |"]
    lines += [f"| {item['code']} | {item['location']} |" for item in report["findings"]]
    if not report["findings"]:
        lines.append("| none | — |")
    lines += ["", "## Source fingerprints", ""]
    lines += [f"- `{name}`: `{item['sha256']}`" for name, item in report["files"].items()]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="Ordinary batch directory (results.json and/or run-progress.json)")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    report = audit_run(args.run)
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) if args.format == "json"
          else markdown_audit(report), end="\n" if args.format == "json" else "")
    return {"consistent": 0, "incomplete": 1, "invalid": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
