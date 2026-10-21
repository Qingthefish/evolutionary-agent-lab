"""Versioned C07 experiment manifest and isolated paired-run procedure.

The manifest wraps an existing development runtime plan (model, budgets, cases,
capabilities) and adds the two topologies, memory/human policies, replicates
and order. Loading validates fairness and fails closed. Inspection never calls
a model. Execution needs explicit authorization, the inspected fingerprint and
a pilot budget. Every planned run gets a fresh state directory.
"""

import json
import os
from pathlib import Path
import re
import time
from uuid import uuid4

from .. import budget
from ..core import WorkflowError
from ..deepseek import DeepSeekClient, DeepSeekHTTP
from ..protocol import strict_json
from ..runtime import LiveConfig, RuntimeServices, TaskPolicy, bind_task_policy, text_acceptance_factory
from ..scheduler import MultiAgentScheduler
from .experience import _error
from .harness import HUMAN, _Session, _case_policy, _checks, _classify
from .manifest import digest
from .memory_protocol import tree_usage
from .plan import DevelopmentPlan, _object
from .topology import (CHILD_RELEASE, COORDINATION_TOOLS, HUMAN_POLICIES, MEMORY_POLICIES, ORDER, PROTOCOL, SINGLE_AGENT,
                       STRUCTURAL_HANDOFF, TOPOLOGIES, build_condition, planned_slots, require_valid, single_limits_from,
                       validate_pair)

SCHEMA = "c07-single-multi-topology"
ISOLATION = "fresh-state-directory-per-run-v1"
HANDOFF_CHECK = "c07_handoff:offered_to_parent"
EVIDENCE_CLASSES = ("engineering_validation", "pilot_model", "pilot_smoke")
LIVE_CLASSES = ("pilot_model", "pilot_smoke")
CATEGORIES = ("structured_generation", "text_processing", "python_implementation", "correction_after_failure", "other")
ORACLE_SCOPES = ("exact_text", "structured_json", "artifact_properties_only")
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
_MAX_BYTES = 65536


def _text(value, label, maximum=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise WorkflowError(f"{label} must be nonempty text of at most {maximum} characters")
    return value


class TopologyExperiment:
    """Strict, fingerprinted experiment definition; no secrets, no model calls."""

    def __init__(self, filename):
        self.filename = Path(filename).resolve()
        try:
            with self.filename.open("rb") as stream:
                raw = stream.read(_MAX_BYTES + 1)
            if len(raw) > _MAX_BYTES:
                raise ValueError()
            data = strict_json(raw.decode("utf-8"))
        except (OSError, ValueError, UnicodeError, RecursionError):
            raise WorkflowError("Cannot read a bounded, unambiguous topology experiment manifest") from None
        _object(data, {"schema", "version", "experiment_id", "purpose", "evidence_class", "runtime_plan",
                       "case_annotations", "topologies", "memory", "human", "procedure", "pilot_budget"}, "Topology manifest")
        if data["schema"] != SCHEMA or type(data["version"]) is not int or data["version"] != 1:
            raise WorkflowError(f"Only {SCHEMA} version 1 manifests are implemented")
        if not isinstance(data["experiment_id"], str) or not _ID.fullmatch(data["experiment_id"]):
            raise WorkflowError("experiment_id must be 3-64 lowercase letters, digits or hyphens")
        _text(data["purpose"], "purpose")
        if data["evidence_class"] == "official_benchmark":
            raise WorkflowError("Official benchmark evidence requires the instructor's released dataset and protocol; "
                                "it is never produced by this development manifest")
        if data["evidence_class"] not in EVIDENCE_CLASSES:
            raise WorkflowError("evidence_class must be engineering_validation, pilot_model or pilot_smoke")
        _text(data["runtime_plan"], "runtime_plan", 512)
        self.runtime = DevelopmentPlan(self.filename.parent / data["runtime_plan"])
        self.cases = list(self.runtime.cases)
        annotations = data["case_annotations"]
        if not isinstance(annotations, dict) or set(annotations) != {c.id for c in self.cases}:
            raise WorkflowError("case_annotations must annotate exactly the runtime plan's selected cases")
        for identifier, note in annotations.items():
            _object(note, {"category", "oracle_scope", "note"}, f"Annotation {identifier}")
            if note["category"] not in CATEGORIES or note["oracle_scope"] not in ORACLE_SCOPES:
                raise WorkflowError(f"Annotation {identifier}: unsupported category or oracle scope")
            _text(note["note"], f"Annotation {identifier} note")
        topologies = _object(data["topologies"], set(TOPOLOGIES), "topologies")
        single = _object(topologies["single_agent"], {"agent", "instructions", "task_limits"}, "single_agent")
        multi = _object(topologies["multi_agent"], {"roles", "root", "child_release"}, "multi_agent")
        if single["agent"] != SINGLE_AGENT or single["instructions"] != "c07-single-agent-v1":
            raise WorkflowError(f"single_agent must use agent {SINGLE_AGENT!r} and instructions c07-single-agent-v1")
        if multi["roles"] != "runtime-live-roles-v1" or multi["root"] != "coordinator":
            raise WorkflowError("multi_agent must reuse runtime-live-roles-v1 with the coordinator root")
        if multi["child_release"] not in CHILD_RELEASE:
            raise WorkflowError("multi_agent.child_release must be " + " or ".join(CHILD_RELEASE))
        self.single_limits = single_limits_from(single["task_limits"])
        if not isinstance(data["memory"], dict) or data["memory"].get("mode") not in MEMORY_POLICIES:
            raise WorkflowError("Only memory mode 'disabled' is implemented; memory-on trials use the frozen-memory protocol")
        if data["memory"] != {k: MEMORY_POLICIES["disabled"][k] for k in ("mode", "initial_state")}:
            raise WorkflowError("memory must be exactly {mode: disabled, initial_state: fresh-empty-per-run}")
        _object(data["human"], {"policy"}, "human")
        if data["human"]["policy"] not in HUMAN_POLICIES:
            raise WorkflowError("Only the boundary-stops-run-v1 human policy is implemented; scripted replies are not supported")
        procedure = _object(data["procedure"], {"replicates", "order", "isolation"}, "procedure")
        if (type(procedure["replicates"]) is not int or not 1 <= procedure["replicates"] <= 10
                or procedure["order"] != ORDER or procedure["isolation"] != ISOLATION):
            raise WorkflowError(f"procedure needs 1-10 replicates, order {ORDER} and isolation {ISOLATION}")
        pilot = data["pilot_budget"]
        if pilot is not None:
            _object(pilot, {"max_total_model_attempts"}, "pilot_budget")
            if type(pilot["max_total_model_attempts"]) is not int or pilot["max_total_model_attempts"] < 1:
                raise WorkflowError("pilot_budget.max_total_model_attempts must be a positive integer")
        if data["evidence_class"] in LIVE_CLASSES and pilot is None:
            raise WorkflowError("A pilot_model or pilot_smoke manifest must declare an explicit pilot_budget")
        if data["evidence_class"] == "pilot_smoke" and (procedure["replicates"] != 1 or len(self.cases) != 1):
            # A smoke check verifies the live path once; it is never a comparison sample.
            raise WorkflowError("A pilot_smoke manifest runs exactly one case once per topology")
        self.data = data
        self.template = LiveConfig(api_key="not-used-for-plan-inspection", **self.runtime.settings)
        if self.template.enable_memory:
            raise WorkflowError("Runtime plan must keep memory disabled for this protocol")
        self.policies = {c.id: _case_policy(c, self.template) for c in self.cases}
        self.memory = dict(MEMORY_POLICIES["disabled"])
        self.human = dict(HUMAN_POLICIES[data["human"]["policy"]])
        self.child_release = multi["child_release"]
        self.conditions = {t: build_condition(t, self.template, cases=self.cases, policies=self.policies,
                                              single_limits=self.single_limits, child_release=self.child_release,
                                              memory=self.memory, human=self.human) for t in TOPOLOGIES}
        self.fairness = validate_pair(self.conditions["single_agent"].record, self.conditions["multi_agent"].record)
        require_valid(self.fairness)
        self.identity = {k: data[k] for k in ("schema", "version", "experiment_id", "purpose", "evidence_class")}
        # Shared conditions: runtime plan (code fingerprint, case definitions,
        # acceptance, team roles), annotations and procedure. Credentials and
        # file locations are excluded.
        self.shared = {"protocol": PROTOCOL, "runtime": self.runtime.conditions, "case_annotations": annotations,
                       "memory": self.memory, "human": self.human, "procedure": procedure, "pilot_budget": pilot}
        records = {t: c.record for t, c in self.conditions.items()}
        self.fingerprints = {"experiment": digest(self.identity), "shared": digest(self.shared),
                             "single_agent": digest(records["single_agent"]), "multi_agent": digest(records["multi_agent"])}
        self.sha256 = digest({"identity": self.identity, "shared": self.shared, "conditions": records,
                              "fairness": self.fairness})

    def slots(self):
        return planned_slots(self.data["procedure"]["replicates"], [c.id for c in self.cases])

    def maximum_model_attempts(self):
        ceiling = self.conditions["single_agent"].record["budget"]["effective"]["model_attempts"]
        return len(self.slots()) * ceiling

    def maximum_reported_tokens(self):
        ceiling = self.conditions["single_agent"].record["budget"]["effective"]["reported_tokens"]
        return len(self.slots()) * ceiling

    def inspect(self):
        ready = self.runtime.inspect()
        pilot = self.data["pilot_budget"]
        blockers = list(ready["blockers"])
        if self.data["evidence_class"] not in LIVE_CLASSES:
            blockers.append("Manifest declares engineering_validation; live execution requires pilot_model or pilot_smoke")
        elif self.maximum_model_attempts() > pilot["max_total_model_attempts"]:
            blockers.append("Planned maximum model attempts exceed the declared pilot budget")
        return {"experiment": self.identity, "plan_sha256": self.sha256, "fingerprints": self.fingerprints,
                "model_calls": 0, "benchmark_valid": False, "configured_to_attempt": not blockers, "blockers": blockers,
                "fairness": {"status": self.fairness["status"], "confounds": [c["code"] for c in self.fairness["confounds"]]},
                "conditions": {t: {"root": c.root, "members": list(c.members),
                                   "task_tools": c.record["capabilities"]["tools"],
                                   "coordination_tools": c.record["capabilities"]["coordination_tools"],
                                   "effective_budget": c.record["budget"]["effective"]} for t, c in self.conditions.items()},
                "cases": [{"id": c.id, **self.data["case_annotations"][c.id]} for c in self.cases],
                "planned_runs": len(self.slots()), "order": ORDER, "isolation": ISOLATION,
                "maximum_model_attempts": self.maximum_model_attempts(),
                "maximum_reported_tokens": self.maximum_reported_tokens(), "pilot_budget": pilot,
                "memory": self.memory, "human": self.human,
                "evidence_note": "Inspection only. Offline replay is engineering validation; live runs are pilot "
                                 "development evidence; neither is an official benchmark."}

    def execute(self, *, allow_model_calls, plan_sha256, output_root):
        if allow_model_calls is not True or plan_sha256 != self.sha256:
            raise WorkflowError("Execution requires explicit model-call authorization and the current inspected plan SHA-256")
        readiness = self.inspect()
        if readiness["blockers"]:
            raise WorkflowError("Topology plan is blocked: " + "; ".join(readiness["blockers"]))
        live = LiveConfig(api_key=os.environ[self.runtime.data["api_key_env"]], allow_network=True, **self.runtime.settings)
        return TopologyTrial(self, LiveTopologyDriver(live)).run(output_root)


class LiveTopologyDriver:
    """Explicit DeepSeek transport. The fixture subclass replays recorded turns."""
    mode = "live"

    def __init__(self, live):
        if not isinstance(live, LiveConfig) or live.enable_memory:
            raise WorkflowError("Topology driver requires the shared memory-disabled LiveConfig")
        self.live = live

    def clients(self, roles, slot):
        http = DeepSeekHTTP(self.live.api_key, allow_network=self.live.allow_network, timeout=self.live.socket_timeout)
        return {agent: DeepSeekClient(self.live.model, http, max_tokens=self.live.max_output_tokens) for agent in roles}


def child_release_factory(workflow, files, root, policy, child_release):
    """Root/child acceptance from the shared policy, plus the declared child release.

    Unanticipated delegated children have no independent content oracle. With
    the structural hand-off policy a child is released only after it actually
    offered at least one snapshot to its parent; its content is still judged
    only through the root's independent acceptance.
    """
    base = text_acceptance_factory(workflow, files, root, policy)
    if child_release != STRUCTURAL_HANDOFF:
        return base

    def factory(candidate):
        selected = base(candidate)
        if selected is not None or candidate["id"] == root:
            return selected
        task, parent = candidate["id"], candidate["parent"]

        def verify():
            offered = workflow.db.execute("SELECT count(*) FROM artifacts WHERE source_task=? AND target_task=?",
                                          (task, parent)).fetchone()[0]
            return {HANDOFF_CHECK: offered > 0}
        return verify, STRUCTURAL_HANDOFF
    return factory


def release_basis(checks):
    """How a task's completion was accepted; only the root is judged by the case oracle."""
    if not checks:
        return None
    if set(checks) == {HANDOFF_CHECK}:
        return "structural_handoff"
    if set(checks) == {"human_review_accepted"}:
        return "human_review"
    return "other_trusted_checks"


def coordination_metrics(workflow, root):
    """Observable coordination and failure evidence from persisted records."""
    tasks = budget.descendants(workflow, root)
    ids = [t["id"] for t in tasks]
    marks = ",".join("?" * len(ids))
    calls = [dict(r) for r in workflow.db.execute(
        f"SELECT name,status FROM tool_calls WHERE task IN ({marks})", ids)] if _table(workflow, "tool_calls") else []
    names = {}
    for call in calls:
        names[call["name"]] = names.get(call["name"], 0) + 1
    offers = workflow.db.execute(f"SELECT count(*),coalesce(sum(consumed),0) FROM artifacts WHERE source_task IN ({marks})",
                                 ids).fetchone() if _table(workflow, "artifacts") else (0, 0)
    attempts = {}
    if _table(workflow, "runner_turns"):
        for row in workflow.db.execute(f"SELECT t.assignee,count(*) FROM runner_turns r JOIN tasks t ON t.id=r.task "
                                       f"WHERE r.task IN ({marks}) GROUP BY t.assignee", ids):
            attempts[row[0]] = row[1]
    stops = []
    if _table(workflow, "runner_sessions"):
        stops = [{"task": r["task"], "reason": r["stop_reason"]} for r in workflow.db.execute(
            f"SELECT task,stop_reason FROM runner_sessions WHERE task IN ({marks}) AND stop_reason IS NOT NULL ORDER BY rowid", ids)]
    subtasks = []
    for task in tasks:
        if task["parent"] is None:
            continue
        evidence = json.loads(task["evidence"]) if task["evidence"] else {}
        subtasks.append({"task_id": task["id"], "assignee": task["assignee"], "state": task["state"],
                         "release": release_basis(evidence.get("checks"))})
    # B3: configured membership is not collaboration; report only what records show.
    return {"tasks": len(tasks), "delegated_tasks": len(subtasks), "delegation_performed": bool(subtasks),
            "participating_agents": sorted(attempts),
            "tool_calls_by_name": dict(sorted(names.items())),
            "coordination_tool_calls": sum(n for k, n in names.items() if k in COORDINATION_TOOLS),
            "failed_tool_calls": sum(c["status"] == "failed" for c in calls),
            "messages_posted": names.get("post_message", 0),
            "handoffs_offered": offers[0], "handoffs_accepted": offers[1],
            "model_attempts_by_agent": dict(sorted(attempts.items())), "stop_reasons": stops, "subtasks": subtasks}


def failure_category(row):
    status, classification = row["status"], row["classification"]
    if status == "not_run":
        return "not_run"
    if status == "running":
        return "interrupted"
    if classification == "completed":
        return "none"
    if classification in {"driver_error", "timeout"}:
        return classification
    if classification == "blocked":
        kinds = set(row.get("needs_kinds") or [])
        if kinds & {"waiting_input", "waiting_approval", "trusted_action_release"}:
            return "human_boundary"
        if "independent_verification" in kinds:
            return "awaiting_trusted_review"
        if "reconciliation" in kinds:
            return "reconciliation_required"
        return "blocked_other"
    reasons = " ".join(s["reason"] for s in (row.get("coordination") or {}).get("stop_reasons", []))
    evidence = ((row.get("workflow") or {}).get("evidence") or {}).get("error") or ""
    text = (reasons + " " + evidence).lower()
    for needle, label in (("provider attempt failed", "provider_error"), ("repeated identical", "repeated_outcomes"),
                          ("delegated task", "child_failure"), ("duration", "duration_exhausted"),
                          ("budget", "budget_exhausted")):
        if needle in text:
            return label
    return classification


def _table(workflow, name):
    return workflow.db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (name,)).fetchone() is not None


class TopologyTrial:
    """Run every planned slot in its own fresh workflow, files and namespace."""

    def __init__(self, experiment, driver):
        if not isinstance(experiment, TopologyExperiment) or not isinstance(driver, LiveTopologyDriver):
            raise WorkflowError("Use a validated topology experiment and an explicitly typed driver")
        expected = LiveConfig(api_key=driver.live.api_key, allow_network=driver.live.allow_network,
                              **experiment.runtime.settings)
        if driver.live != expected or driver.mode not in {"live", "offline_fixture"}:
            raise WorkflowError("Driver configuration differs from the inspected plan")
        self.experiment, self.driver = experiment, driver

    def run(self, output_root):
        experiment = self.experiment
        run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:6]
        directory = Path(output_root).resolve() / run_id
        directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        conditions = {"identity": experiment.identity, "shared": experiment.shared,
                      "conditions": {t: c.record for t, c in experiment.conditions.items()},
                      "fairness": experiment.fairness}
        rows = []
        for slot in experiment.slots():
            case = next(c for c in experiment.cases if c.id == slot["case_id"])
            rows.append({**slot, "case": case.summary(),
                         "case_sha256": next(t["content_sha256"] for t in conditions["conditions"][slot["topology"]]["tasks"]
                                             if t["id"] == case.id),
                         "status": "not_run", "classification": "not_run", "failure_category": "not_run",
                         "execution_index": None, "started_at": None, "ended_at": None, "duration_seconds": None,
                         "root": None, "checks": {}, "failed_checks": [], "workflow": None, "usage": None,
                         "coordination": None, "driver_state": None, "needs_kinds": None, "error": None,
                         "state_directory": None})
        self.report = {"schema_version": 1, "protocol": PROTOCOL, "run_id": run_id, "mode": self.driver.mode,
                       "evidence_class": "engineering_validation" if self.driver.mode == "offline_fixture"
                       else experiment.data["evidence_class"],
                       "benchmark_valid": False, "model_calls": 0 if self.driver.mode == "offline_fixture" else None,
                       "plan_sha256": experiment.sha256, "fingerprints": experiment.fingerprints,
                       "conditions": conditions, "conditions_sha256": digest(conditions),
                       "fixture": getattr(self.driver, "fixture_info", None),
                       "started": time.time(), "ended": None, "results": rows}
        self.directory = directory
        self.save()
        for index, row in enumerate(rows):
            self.run_slot(row, index)
        self.report["ended"] = time.time()
        from .topology_report import compare_topology
        self.report["comparison"] = compare_topology(self.report)
        self.save()
        return self.report

    def run_slot(self, row, index):
        experiment, live = self.experiment, self.driver.live
        case = next(c for c in experiment.cases if c.id == row["case_id"])
        condition = experiment.conditions[row["topology"]]
        path = self.directory / f"replicate-{row['replicate']}" / f"slot-{row['slot']:03d}-{case.id}-{row['topology']}"
        started = time.monotonic()
        row.update(status="running", execution_index=index, started_at=time.time(),
                   state_directory=str(path.relative_to(self.directory)))
        self.save()  # Record intent first: a crash leaves a visible interrupted slot, never a silent gap.
        session = None
        try:
            path.mkdir(parents=True, mode=0o700, exist_ok=False)
            session = _Session(path, f"c07-{self.report['run_id']}-slot-{row['slot']}")
            for agent in condition.members:
                session.workflow.register_actor(agent, "agent")
            session.services = RuntimeServices(session.workflow, session.files, live)
            chat = session.workflow.create_chat("group", [HUMAN, *condition.members])
            root = session.workflow.create_task(chat, HUMAN, condition.root, case.goal)
            row["root"] = root
            policy = bind_task_policy(session.workflow, root, HUMAN, experiment.policies[case.id],
                                      default=TaskPolicy(live.constraints))
            release = condition.record["child_release"]
            acceptance = policy.acceptance_id + ("+" + release if release == STRUCTURAL_HANDOFF else "")
            scheduler = MultiAgentScheduler(
                session.workflow, session.files, root, human=HUMAN, roles=condition.roles,
                clients=self.driver.clients(condition.roles, row), mode=self.driver.mode,
                constraints=list(policy.constraints), acceptance_id=acceptance,
                verifier_factory=child_release_factory(session.workflow, session.files, root, policy, release),
                limits=live.tree_limits, executor=session.services.executor, git=session.services.git,
                retrieval=session.services.retrieval, child_retries=live.child_retries)
            state = scheduler.run()
            duration = time.monotonic() - started
            checks, workflow = _checks(case, session, root, duration)
            evidence = {t["id"]: t["evidence"] for t in budget.descendants(session.workflow, root)}
            for outcome in workflow["task_outcomes"]:
                recorded = json.loads(evidence[outcome["task_id"]]) if evidence[outcome["task_id"]] else {}
                outcome["acceptance_basis"] = ("case_criteria" if outcome["parent"] is None
                                               else release_basis(recorded.get("checks")))
            row.update(status="executed", classification=_classify(case, checks, workflow), checks=checks,
                       failed_checks=sorted(k for k, v in checks.items() if not v), workflow=workflow,
                       driver_state=state.get("state"),
                       needs_kinds=sorted({n.get("kind") for n in state.get("needs", []) if n.get("kind")}))
        except Exception as error:  # A failed run is a result, never a crash of the batch.
            row.update(status="executed", classification="driver_error", error=_error(error))
        finally:
            row["duration_seconds"] = time.monotonic() - started
            row["ended_at"] = time.time()
            if session is not None:
                if row["root"] is not None:
                    try:
                        row["usage"] = tree_usage(session.workflow, row["root"])
                        row["coordination"] = coordination_metrics(session.workflow, row["root"])
                    except Exception as error:
                        row["error"] = row["error"] or _error(error)
                session.close()
            row["failure_category"] = failure_category(row)
            self.save()

    def save(self):
        temporary = self.directory / "experiment.json.tmp"
        temporary.write_text(json.dumps(self.report, ensure_ascii=True, sort_keys=True, indent=2) + "\n")
        temporary.replace(self.directory / "experiment.json")
        from .topology_report import topology_markdown
        (self.directory / "report.md").write_text(topology_markdown(self.report))


__all__ = ["LiveTopologyDriver", "TopologyExperiment", "TopologyTrial", "child_release_factory",
           "coordination_metrics", "failure_category"]
