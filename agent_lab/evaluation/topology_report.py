"""Recompute and report a C07 paired topology run from its raw slot records.

Headline numbers are always recomputed; edited summaries are ignored. Unrun,
interrupted and failed runs stay in denominators. Missing usage is reported as
unknown, never zero. Fixture runs are engineering validation only.
"""

import json
import math

from .cases import parse_case
from .harness import _classify
from .manifest import digest
from .memory_protocol import TERMINAL
from .topology import ORDER, PROTOCOL, TOPOLOGIES, planned_slots, validate_pair

FIXTURE_MODEL = "offline-c07-replay-fixture"
_STATES = TERMINAL | {"pending", "running", "waiting_input", "waiting_approval"}
_RELEASES = {"structural_handoff", "human_review", "other_trusted_checks", None}
_COST = {"status": "unavailable",
         "reason": "No verified price model is configured; reported usage is shown separately and is not billing."}


class EvidenceError(ValueError):
    """Saved evidence is malformed, edited or inconsistent with its conditions."""


def _nonnegative(value, *, integer=False):
    if type(value) not in ((int,) if integer else (int, float)) or not math.isfinite(value) or value < 0:
        raise EvidenceError("Counts and timings must be finite and nonnegative")


def _validate(report):
    data = json.loads(json.dumps(report, allow_nan=False))
    if data["schema_version"] != 1 or data["protocol"] != PROTOCOL or data["benchmark_valid"] is not False:
        raise EvidenceError("Unsupported report schema, protocol or benchmark label")
    conditions = data["conditions"]
    if data["conditions_sha256"] != digest(conditions):
        raise EvidenceError("Recorded conditions differ from their fingerprint")
    records = conditions["conditions"]
    plan = {"identity": conditions["identity"], "shared": conditions["shared"], "conditions": records,
            "fairness": conditions["fairness"]}
    if data["plan_sha256"] != digest(plan):
        raise EvidenceError("Recorded plan fingerprint does not match the recorded experiment conditions")
    recomputed = validate_pair(records["single_agent"], records["multi_agent"])
    if recomputed != conditions["fairness"] or recomputed["status"] != "valid":
        raise EvidenceError("Recorded fairness validation is missing, failed or no longer reproduces")
    shared = conditions["shared"]
    if shared["procedure"]["order"] != ORDER:
        raise EvidenceError("Unsupported execution order")
    mode, evidence = data["mode"], data["evidence_class"]
    if mode == "offline_fixture":
        if evidence != "engineering_validation" or data["model_calls"] != 0:
            raise EvidenceError("Offline fixture runs can only be engineering validation with zero model calls")
    elif mode == "live":
        if evidence not in {"pilot_model", "pilot_smoke"} or conditions["identity"]["evidence_class"] != evidence:
            raise EvidenceError("Live runs must come from a pilot_model or pilot_smoke manifest")
    else:
        raise EvidenceError("Unknown evidence mode")
    definitions = {c["id"]: c for c in shared["runtime"]["cases"]}
    case_ids = [t["id"] for t in records["single_agent"]["tasks"]]
    if set(case_ids) != definitions.keys():
        raise EvidenceError("Case inventory differs between plan and conditions")
    planned = [(p["slot"], p["replicate"], p["case_id"], p["topology"], p["pair_position"])
               for p in planned_slots(shared["procedure"]["replicates"], case_ids)]
    rows = data["results"]
    if len(rows) != len(planned):
        raise EvidenceError("Planned runs are missing or duplicated")
    for row, identity in zip(rows, planned):
        if (row["slot"], row["replicate"], row["case_id"], row["topology"], row["pair_position"]) != identity:
            raise EvidenceError("Run order, topology or case assignment changed")
        content = next(t["content_sha256"] for t in records[row["topology"]]["tasks"] if t["id"] == row["case_id"])
        summary = {k: row["case"][k] for k in ("id", "title", "goal", "driver", "split", "control", "constraints", "expected")}
        defined = {k: definitions[row["case_id"]][k] for k in summary}
        if row["case_sha256"] != content or digest(summary) != digest(defined):
            raise EvidenceError("A run's case content differs from the inspected plan")
        if row["status"] not in {"executed", "not_run", "running"}:
            raise EvidenceError("Unknown run status")
        if row["status"] != "executed":
            continue
        _nonnegative(row["duration_seconds"])
        workflow = row["workflow"]
        if workflow is None:
            if row["classification"] != "driver_error":
                raise EvidenceError("Executed run lacks workflow evidence without a recorded driver error")
            continue
        outcomes = workflow["task_outcomes"]
        roots = [t for t in outcomes if t["parent"] is None]
        if len(roots) != 1 or roots[0]["task_id"] != row["root"] or workflow["root_task"] != row["root"]:
            raise EvidenceError("Missing or ambiguous root task evidence")
        for task in outcomes:
            if type(task["verified_success"]) is not bool or task["state"] not in _STATES:
                raise EvidenceError("Malformed task outcome")
            if task["verified_success"] and task["state"] != "succeeded":
                raise EvidenceError("An unfinished or failed task cannot count as verified")
            _nonnegative(task["elapsed_seconds"])
            _nonnegative(task["human_wait_seconds"])
            if (task["state"] in TERMINAL) != (task["final_duration_seconds"] is not None):
                raise EvidenceError("Terminal timing evidence is inconsistent")
            if "acceptance_basis" in task and task["acceptance_basis"] not in (
                    {"case_criteria"} if task["parent"] is None else _RELEASES):
                raise EvidenceError("Recorded acceptance basis is inconsistent with the task's position")
        checks = row["checks"]
        if not checks or any(type(v) is not bool for v in checks.values()):
            raise EvidenceError("Independent acceptance checks are missing or malformed")
        case = parse_case({k: v for k, v in definitions[row["case_id"]].items() if k != "source"})
        if _classify(case, checks, workflow) != row["classification"]:
            raise EvidenceError("Recorded classification disagrees with the independent checks")
        if row["classification"] == "completed" and not roots[0]["verified_success"]:
            raise EvidenceError("Accepted goal lacks trusted completion evidence")
        usage = row["usage"]
        if usage is not None:
            for value in usage.values():
                _nonnegative(value, integer=True)
            if usage["unknown_usage_attempts"] > usage["reserved_model_attempts"]:
                raise EvidenceError("Unknown-usage attempts exceed reserved attempts")
        models = workflow["observed_models"]
        if not isinstance(models, list) or any(not isinstance(m, str) or not m for m in models):
            raise EvidenceError("Observed model identity is malformed")
        if mode == "offline_fixture" and set(models) - {FIXTURE_MODEL}:
            raise EvidenceError("Offline run reports a non-fixture model; fixtures cannot be relabelled as model evidence")
    return data, rows


def _usage_view(rows):
    """Known totals plus explicit completeness; absent evidence is never zero."""
    executed = [r for r in rows if r["status"] == "executed"]
    with_usage = [r for r in executed if r["usage"] is not None]
    unknown = sum(r["usage"]["unknown_usage_attempts"] for r in with_usage)
    complete = len(with_usage) == len(rows) and unknown == 0
    def total(key):
        return sum(r["usage"][key] for r in with_usage) if with_usage else None
    return {"runs_with_usage_evidence": len(with_usage), "runs_without_usage_evidence": len(rows) - len(with_usage),
            "reserved_model_attempts": total("reserved_model_attempts"), "unknown_usage_attempts": unknown if with_usage else None,
            "reported_tokens_known": total("reported_tokens"),
            "reported_tokens_status": "complete" if complete else ("lower_bound" if with_usage else "unavailable"),
            "tool_calls": total("tool_calls")}


def _status(known, total):
    return "complete" if known == total else ("lower_bound" if known else "unavailable")


def arm_summary(rows, configured_agents=None):
    planned = len(rows)
    executed = [r for r in rows if r["status"] == "executed"]
    goals = []
    for row in executed:
        outcome = next((t for t in ((row["workflow"] or {}).get("task_outcomes") or []) if t["parent"] is None), None)
        goals.append((row, outcome))
    completed = sum(r["classification"] == "completed" and bool(g and g["verified_success"]) for r, g in goals)
    durations = [r["duration_seconds"] for r in executed]
    final = [g["final_duration_seconds"] for _, g in goals if g and g["final_duration_seconds"] is not None]
    coordination = [r["coordination"] for r in executed if r["coordination"] is not None]
    subtasks = [s for c in coordination for s in c["subtasks"]]
    categories = {}
    for row in rows:
        categories[row["failure_category"]] = categories.get(row["failure_category"], 0) + 1
    humans = [len((r["workflow"] or {}).get("human_interventions") or []) for r in executed if r["workflow"] is not None]
    return {
        "planned": planned, "executed": len(executed),
        "not_run": sum(r["status"] == "not_run" for r in rows), "interrupted": sum(r["status"] == "running" for r in rows),
        "goals_verified_completed": completed,
        "goal_completion_rate_planned": completed / planned if planned else None,
        "goal_completion_rate_executed": completed / len(executed) if executed else None,
        "classifications": dict(sorted({c: sum(r["classification"] == c for r in rows)
                                        for c in {r["classification"] for r in rows}}.items())),
        "failure_categories": dict(sorted(categories.items())),
        "mean_observed_run_seconds": sum(durations) / len(durations) if durations else None,
        "mean_goal_final_seconds": sum(final) / len(final) if final else None, "goals_finalized": len(final),
        "usage": _usage_view(rows),
        # Counts derived from workflow records are lower bounds whenever a planned run lacks them.
        "human_interventions": {"known": sum(humans), "status": _status(len(humans), planned)},
        "runs_missing_workflow": sum(r["workflow"] is None for r in executed),
        "coordination": {
            "runs_with_evidence": len(coordination), "status": _status(len(coordination), planned),
            "tasks": sum(c["tasks"] for c in coordination), "delegated_tasks": sum(c["delegated_tasks"] for c in coordination),
            "coordination_tool_calls": sum(c["coordination_tool_calls"] for c in coordination),
            "handoffs_offered": sum(c["handoffs_offered"] for c in coordination),
            "handoffs_accepted": sum(c["handoffs_accepted"] for c in coordination),
            "messages_posted": sum(c["messages_posted"] for c in coordination),
            "failed_tool_calls": sum(c["failed_tool_calls"] for c in coordination)},
        # Child content is never judged by the case oracle; only the release basis is reported.
        "subtasks": {"observed": len(subtasks), "succeeded": sum(s["state"] == "succeeded" for s in subtasks),
                     "released_by_structural_handoff": sum(s["release"] == "structural_handoff" for s in subtasks),
                     "released_by_human_review": sum(s["release"] == "human_review" for s in subtasks),
                     "released_by_other_trusted_checks": sum(s["release"] == "other_trusted_checks" for s in subtasks)},
        "collaboration": {
            "configured_agents": configured_agents, "runs_with_evidence": len(coordination),
            "runs_with_delegation": sum(bool(c.get("delegation_performed")) for c in coordination),
            "participating_agents_min_max": ([min(len(c.get("participating_agents", [])) for c in coordination),
                                              max(len(c.get("participating_agents", [])) for c in coordination)]
                                             if coordination else None)},
    }


def _goal_success(row):
    outcome = next((t for t in ((row["workflow"] or {}).get("task_outcomes") or []) if t["parent"] is None), None)
    return row["classification"] == "completed" and bool(outcome and outcome["verified_success"])


def paired(rows):
    pairs, incomplete = {}, []
    for row in rows:
        pairs.setdefault((row["replicate"], row["case_id"]), {})[row["topology"]] = row
    concordance = {"both": 0, "single_only": 0, "multi_only": 0, "neither": 0}
    deltas = {"model_attempts": [], "reported_tokens": [], "tool_calls": [], "run_seconds": []}
    complete = 0
    for (rep, case_id), arms in sorted(pairs.items()):
        single, multi = arms["single_agent"], arms["multi_agent"]
        reasons = [f"{t}: {r['status']}" + (" without workflow evidence" if r["status"] == "executed" and r["workflow"] is None else "")
                   for t, r in (("single_agent", single), ("multi_agent", multi))
                   if r["status"] != "executed" or r["workflow"] is None]
        if reasons:
            incomplete.append({"replicate": rep, "case_id": case_id, "reasons": reasons})
            continue
        complete += 1
        a, b = _goal_success(single), _goal_success(multi)
        concordance["both" if a and b else "single_only" if a else "multi_only" if b else "neither"] += 1
        deltas["run_seconds"].append(multi["duration_seconds"] - single["duration_seconds"])
        usable = all(r["usage"] is not None and r["usage"]["unknown_usage_attempts"] == 0 for r in (single, multi))
        if usable:
            deltas["model_attempts"].append(multi["usage"]["reserved_model_attempts"] - single["usage"]["reserved_model_attempts"])
            deltas["reported_tokens"].append(multi["usage"]["reported_tokens"] - single["usage"]["reported_tokens"])
            deltas["tool_calls"].append(multi["usage"]["tool_calls"] - single["usage"]["tool_calls"])
    return {"planned_pairs": len(pairs), "complete_pairs": complete, "incomplete_pairs": incomplete,
            "goal_outcome_concordance": concordance,
            "mean_multi_minus_single": {k: (sum(v) / len(v) if v else None) for k, v in deltas.items()},
            "pairs_with_complete_usage": len(deltas["model_attempts"]),
            "note": "Descriptive paired differences over complete pairs only; no significance test or causal claim."}


def evidence_completeness(rows):
    executed = [r for r in rows if r["status"] == "executed"]
    with_workflow = [r for r in executed if r["workflow"] is not None]
    with_usage = [r for r in executed if r["usage"] is not None]
    reserved = sum(r["usage"]["reserved_model_attempts"] for r in with_usage)
    unknown = sum(r["usage"]["unknown_usage_attempts"] for r in with_usage)
    return {"runs_planned": len(rows), "runs_executed": len(executed), "runs_with_workflow": len(with_workflow),
            "runs_without_observed_model": sum(not r["workflow"]["observed_models"] for r in with_workflow),
            "runs_without_usage_evidence": len(rows) - len(with_usage),
            "attempts_reserved": reserved, "attempts_with_unknown_usage": unknown,
            "provider_responses_received": reserved - unknown}


def compare_topology(report):
    try:
        data, rows = _validate(report)
    except (KeyError, TypeError, ValueError, AttributeError, StopIteration, RecursionError, OverflowError) as error:
        reason = str(error) if isinstance(error, EvidenceError) else "Missing or malformed run evidence"
        return {"status": "not_comparable", "reasons": [reason], "superiority_established": False, "cost": _COST}
    reasons = []
    if data["ended"] is None:
        reasons.append("Run is still in progress or was interrupted")
    declared = data["conditions"]["conditions"]["single_agent"]["model"]["model"]
    if data["mode"] == "live":
        for row in rows:
            observed = set((row["workflow"] or {}).get("observed_models") or [])
            if observed and observed != {declared}:
                reasons.append(f"slot {row['slot']}: observed model {sorted(observed)} differs from declared {declared!r}")
    mismatch = any("differs from declared" in r for r in reasons)
    pairs = paired(rows)
    if pairs["incomplete_pairs"]:
        reasons.append(f"{len(pairs['incomplete_pairs'])} planned pair(s) are incomplete; they are listed, not dropped")
    gaps = evidence_completeness(rows)
    if data["mode"] == "live":
        # Reserved attempts are not successful calls; missing identity or usage is never assumed.
        if gaps["runs_without_observed_model"]:
            reasons.append(f"{gaps['runs_without_observed_model']} executed run(s) have no observed model identity")
        if gaps["attempts_with_unknown_usage"]:
            reasons.append(f"{gaps['attempts_with_unknown_usage']} attempt(s) have unknown usage; token totals are lower bounds")
        if gaps["runs_without_usage_evidence"]:
            reasons.append(f"{gaps['runs_without_usage_evidence']} planned run(s) have no usage evidence")
    evidence = {"offline_fixture": "engineering_validation"}.get(data["mode"], data["evidence_class"] + "_evidence")
    if data["mode"] == "offline_fixture":
        status = "engineering_only"
    elif mismatch:
        status = "not_comparable"
    elif data["evidence_class"] == "pilot_smoke":
        status = "smoke_incomplete" if reasons else "smoke_only"  # Never a topology comparison.
    else:
        status = "pilot_incomplete" if reasons else "pilot_compared"
    configured = {t: len(data["conditions"]["conditions"][t]["roles"]) for t in TOPOLOGIES}
    return {"status": status, "evidence_class": evidence, "reasons": sorted(set(reasons)), "evidence": gaps,
            "arms": {t: arm_summary([r for r in rows if r["topology"] == t], configured[t]) for t in TOPOLOGIES},
            "paired": pairs, "cost": _COST, "superiority_established": False,
            "note": ("Offline replay fixtures exercise the real scheduler, gateway, budgets and acceptance with scripted "
                     "model turns; they say nothing about model capability." if data["mode"] == "offline_fixture" else
                     "Small development pilot; not the instructor's official evaluation. No causal or superiority claim.")}


def _counted(value, status):
    return f"{value} ({status.replace('_', ' ')})" if status != "complete" else str(value)


def _fmt(value, pattern="{:.2f}"):
    if value is None:
        return "unknown"
    return pattern.format(value) if isinstance(value, float) else str(value)


def topology_markdown(report):
    comparison = report.get("comparison")
    mode = report["mode"]
    scripted = " (scripted outcome, not performance)" if mode == "offline_fixture" else ""
    banner = ("ENGINEERING VALIDATION ONLY. Scripted development simulation replayed through the real runtime. "
              "These are not model results and not DeepSeek/HKGAI performance." if mode == "offline_fixture" else
              "LIVE SMOKE CHECK. One case, one run per topology, to verify the live path and evidence recording. "
              "Not a comparison and not topology evidence." if report["evidence_class"] == "pilot_smoke" else
              "PILOT MODEL EVIDENCE (development). Small authorized live run; not the official benchmark.")
    lines = [f"# C07 single/multi-agent comparison - {report['run_id']}", "", f"> {banner}", "",
             f"- Mode: `{mode}`; evidence class: `{report['evidence_class']}`; benchmark valid: `false`",
             f"- Plan fingerprint: `{report['plan_sha256']}`",
             f"- Experiment / shared / single / multi fingerprints: " + ", ".join(
                 f"`{report['fingerprints'][k][:12]}`" for k in ("experiment", "shared", "single_agent", "multi_agent")),
             f"- Fairness validation: `{report['conditions']['fairness']['status']}`",
             f"- Cost: unavailable (no verified price model); usage is reported separately."]
    if report.get("fixture"):
        fixture = report["fixture"]
        lines.append(f"- Fixture set: `{fixture['set_id']}` ({fixture['provenance']['kind']}; model evidence: "
                     f"`{str(fixture['provenance']['model_evidence']).lower()}`)")
    lines += ["", "## Recorded confounds", ""]
    lines += [f"- `{c['code']}` ({c.get('kind', 'unclassified').replace('_', ' ')}): {c['description']}"
              for c in report["conditions"]["fairness"]["confounds"]]
    if comparison:
        lines += ["", "## Comparison status", "", f"- Status: `{comparison['status']}`"]
        lines += [f"- {reason}" for reason in comparison.get("reasons", [])]
        if "arms" in comparison:
            arms = comparison["arms"]
            metrics = (
                ("Planned runs", lambda a: a["planned"]), ("Executed", lambda a: a["executed"]),
                ("Not run / interrupted", lambda a: f"{a['not_run']} / {a['interrupted']}"),
                ("Verified goals completed" + scripted, lambda a: a["goals_verified_completed"]),
                ("Goal completion rate (planned denominator)" + scripted,
                 lambda a: _fmt(a["goal_completion_rate_planned"], "{:.0%}")),
                ("Mean observed run time (s)", lambda a: _fmt(a["mean_observed_run_seconds"])),
                ("Model attempts reserved (not all received a response)", lambda a: _fmt(a["usage"]["reserved_model_attempts"])),
                ("Attempts with unknown usage", lambda a: _fmt(a["usage"]["unknown_usage_attempts"])),
                ("Reported tokens" + (" (synthetic fixture placeholders)" if mode == "offline_fixture" else ""),
                 lambda a: f"{_fmt(a['usage']['reported_tokens_known'])} ({a['usage']['reported_tokens_status']})"),
                ("Tool calls", lambda a: _fmt(a["usage"]["tool_calls"])),
                ("Human interventions", lambda a: _counted(a["human_interventions"]["known"], a["human_interventions"]["status"])),
                ("Configured agents", lambda a: _fmt(a["collaboration"]["configured_agents"])),
                ("Runs with actual delegation", lambda a: f"{a['collaboration']['runs_with_delegation']} of "
                                                          f"{a['collaboration']['runs_with_evidence']} with evidence"),
                ("Agents with model attempts per run (min-max)", lambda a: "-".join(map(str, a["collaboration"]["participating_agents_min_max"]))
                 if a["collaboration"]["participating_agents_min_max"] else "unknown"),
                ("Tasks / delegated tasks", lambda a: _counted(f"{a['coordination']['tasks']} / {a['coordination']['delegated_tasks']}",
                                                               a["coordination"]["status"])),
                ("Coordination tool calls", lambda a: _counted(a["coordination"]["coordination_tool_calls"], a["coordination"]["status"])),
                ("Hand-offs offered / accepted", lambda a: _counted(f"{a['coordination']['handoffs_offered']} / "
                                                                    f"{a['coordination']['handoffs_accepted']}", a["coordination"]["status"])),
                ("Subtasks succeeded / released by structural hand-off (content not independently verified)",
                 lambda a: f"{a['subtasks']['succeeded']} / {a['subtasks']['released_by_structural_handoff']}"),
                ("Failed tool calls", lambda a: _counted(a["coordination"]["failed_tool_calls"], a["coordination"]["status"])),
            )
            lines += ["", "## Per-condition summary", "", "| Metric | Single agent | Multi agent |", "| --- | --- | --- |"]
            lines += [f"| {name} | {get(arms['single_agent'])} | {get(arms['multi_agent'])} |" for name, get in metrics]
            gaps = comparison["evidence"]
            lines += ["", "## Evidence completeness", "",
                      f"- Runs planned / executed / with workflow evidence: {gaps['runs_planned']} / {gaps['runs_executed']} / "
                      f"{gaps['runs_with_workflow']}",
                      f"- Model attempts reserved / provider responses received / unknown usage: {gaps['attempts_reserved']} / "
                      f"{gaps['provider_responses_received']} / {gaps['attempts_with_unknown_usage']}",
                      f"- Runs without observed model identity: {gaps['runs_without_observed_model']}; "
                      f"runs without usage evidence: {gaps['runs_without_usage_evidence']}"]
            lines += ["", "## Failure categories", "", "| Category | Single agent | Multi agent |", "| --- | --- | --- |"]
            names = sorted(set(arms["single_agent"]["failure_categories"]) | set(arms["multi_agent"]["failure_categories"]))
            lines += [f"| {n} | {arms['single_agent']['failure_categories'].get(n, 0)} | "
                      f"{arms['multi_agent']['failure_categories'].get(n, 0)} |" for n in names]
            p = comparison["paired"]
            c = p["goal_outcome_concordance"]
            lines += ["", "## Paired outcomes" + scripted, "",
                      f"- Complete pairs: {p['complete_pairs']} of {p['planned_pairs']}; "
                      f"pairs with complete usage: {p['pairs_with_complete_usage']}",
                      f"- Both succeeded {c['both']}, single only {c['single_only']}, multi only {c['multi_only']}, neither {c['neither']}",
                      "- Mean multi minus single: " + ", ".join(f"{k} {_fmt(v)}" for k, v in p["mean_multi_minus_single"].items()),
                      f"- {p['note']}"]
            if mode == "offline_fixture":
                lines.append("- Outcomes and resource differences here are fixed by the replay scripts and synthetic usage "
                             "placeholders. They validate accounting, not either topology.")
            lines += [f"- Incomplete pair: replicate {i['replicate']}, `{i['case_id']}`: {'; '.join(i['reasons'])}"
                      for i in p["incomplete_pairs"]]
        lines += ["", f"_{comparison.get('note', '')}_"]
    lines += ["", "## Runs (execution order)", "",
              "| Slot | Rep | Case | Topology | Status | Class | Failure category | Time (s) | Attempts | Agents used | Failed checks |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for row in report["results"]:
        attempts = row["usage"]["reserved_model_attempts"] if row["usage"] else None
        agents = ", ".join(row["coordination"].get("participating_agents", [])) if row["coordination"] else "unknown"
        lines.append(f"| {row['slot']} | {row['replicate']} | `{row['case_id']}` | {row['topology']} | {row['status']} | "
                     f"{row['classification']} | {row['failure_category']} | {_fmt(row['duration_seconds'])} | "
                     f"{_fmt(attempts)} | {agents or 'none'} | {', '.join(row['failed_checks']) or '-'} |")
    lines += ["", "## Notes", "",
              "- Acceptance is computed from persisted state and actual artifacts, never from an agent's own claim.",
              "- Unrun, interrupted and failed runs remain in every denominator. Unknown usage is never shown as zero.",
              "- Alternating order reduces systematic order effects; it does not remove all confounding.",
              "- Raw per-run state directories and `experiment.json` are retained for audit."]
    return "\n".join(lines) + "\n"


__all__ = ["EvidenceError", "FIXTURE_MODEL", "arm_summary", "compare_topology", "paired", "topology_markdown"]
