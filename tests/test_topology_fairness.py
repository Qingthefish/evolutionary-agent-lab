"""C07 fairness validation of single/multi-agent conditions; static, no model calls."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import random
import re
import tempfile
import unittest

from agent_lab.budget import TreeLimits
from agent_lab.core import WorkflowError
from agent_lab.evaluation.cases import load_cases, parse_case
from agent_lab.evaluation.harness import _case_policy
from agent_lab.evaluation.topology import (CAPABILITY_CLASSES, CONFOUND_KINDS, COORDINATION_TOOLS, FairnessError, HUMAN_POLICIES,
    MEMORY_POLICIES, build_condition, case_eligibility, effective_ceilings, planned_slots, tool_classes, validate_pair)
from agent_lab.evaluation.topology_plan import TopologyExperiment
from agent_lab.gateway import _SPECS
from agent_lab.runner import Limits
from agent_lab.runtime import LiveConfig, live_members, live_roles

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "evaluation/topology-plan.json"
NEGATIVE = ROOT / "evaluation/topology/negative-control-plan.json"
SINGLE = {"model_attempts": 24, "reported_tokens": 64000, "duration_seconds": 300, "repeated_outcomes": 3, "tool_calls": 64}
# Same budgets as evaluation/topology/runtime.json.
BUDGETS = dict(role_limits=Limits(8, 32000, 300, 3), tree_limits=TreeLimits(16, 4, 24, 64000, 64, 600), tool_calls=32)


def live_config(**changes):
    return LiveConfig(**{"model": "deepseek-chat", "api_key": "unused", **BUDGETS, **changes})


def write_manifest(directory, *, runtime=None, **changes):
    """Copy the shipped manifest with absolute paths and selected overrides."""
    data = json.loads(CONFIG.read_text())
    data["runtime_plan"] = str(ROOT / "evaluation/topology/runtime.json")
    if runtime is not None:
        plan = json.loads((ROOT / "evaluation/topology/runtime.json").read_text())
        plan["cases"] = str(ROOT / "evaluation/topology/cases")
        plan.update(runtime)
        path = Path(directory) / "runtime.json"
        path.write_text(json.dumps(plan))
        data["runtime_plan"] = str(path)
    for key, value in changes.items():
        data[key] = value
    path = Path(directory) / "manifest.json"
    path.write_text(json.dumps(data))
    return path


def conditions(live=None, *, cases=None, single=SINGLE, release="c07-structural-handoff-v1"):
    live = live or live_config()
    cases = cases or [parse_case(c) for c in json.loads((ROOT / "evaluation/topology/cases/c07-cases.json").read_text())]
    policies = {c.id: _case_policy(c, live) for c in cases}
    built = {t: build_condition(t, live, cases=cases, policies=policies, single_limits=single, child_release=release,
                                memory=MEMORY_POLICIES["disabled"], human=HUMAN_POLICIES["boundary-stops-run-v1"])
             for t in ("single_agent", "multi_agent")}
    return copy.deepcopy(built["single_agent"].record), copy.deepcopy(built["multi_agent"].record)


def codes(report):
    return {e["code"] for e in report["errors"]}


class FairnessTests(unittest.TestCase):
    def test_shipped_manifest_is_valid_and_records_confounds(self):
        experiment = TopologyExperiment(CONFIG)
        self.assertEqual(experiment.fairness["status"], "valid")
        recorded = {c["code"] for c in experiment.fairness["confounds"]}
        self.assertTrue({"role_prompts", "coordination_tools", "task_tree", "per_task_limits", "child_release",
                         "root_repair_capability"} <= recorded)
        single, multi = (experiment.conditions[t].record for t in ("single_agent", "multi_agent"))
        self.assertEqual(single["budget"]["effective"]["model_attempts"], multi["budget"]["effective"]["model_attempts"])
        self.assertEqual(single["capabilities"]["tools"], multi["capabilities"]["tools"])
        self.assertEqual(single["capabilities"]["coordination_tools"], [])
        self.assertIn("delegate_task", multi["capabilities"]["coordination_tools"])

    def test_confounds_are_classified_and_never_hide_accidental_asymmetries(self):
        kinds = {c["code"]: c["kind"] for c in validate_pair(*conditions())["confounds"]}
        self.assertEqual(set(kinds.values()), set(CONFOUND_KINDS))
        self.assertEqual({k for k, v in kinds.items() if v == "necessary_coordination_cost"},
                         {"coordination_tools", "child_release"})
        self.assertTrue({"file_ownership", "root_repair_capability", "shared_runner_prompt"} <= set(kinds))
        prompt = next(c for c in validate_pair(*conditions())["confounds"] if c["code"] == "shared_runner_prompt")
        self.assertEqual(prompt["single_agent"], prompt["multi_agent"])
        single, multi = conditions()
        single["capabilities"]["backends"]["web"] = True  # An accidental asymmetry is an error, not a confound.
        report = validate_pair(single, multi)
        self.assertEqual((report["status"], report["confounds"]), ("invalid", []))

    def test_single_agent_is_capability_union_without_coordination_or_extra_privilege(self):
        for live in (live_config(),
                     live_config(enable_web=True, docker_host="unix:///tmp/none.sock",
                                 python_image="python@sha256:" + "0" * 64, enable_delete=True)):
            single, multi = conditions(live)
            team = {t for role in live_roles(live_members(live), live).values() for t in role.tools}
            self.assertEqual(set(single["roles"]["solo"]["tools"]), team - COORDINATION_TOOLS)
            self.assertEqual(validate_pair(single, multi)["status"], "valid")
        self.assertIn("run_python", single["capabilities"]["tools"])
        self.assertIn("search_web", single["capabilities"]["tools"])

    def test_every_gateway_tool_has_exactly_one_capability_class(self):
        self.assertEqual(set(tool_classes(sorted(_SPECS))), set(_SPECS))
        flattened = [t for members in CAPABILITY_CLASSES.values() for t in members]
        self.assertEqual(len(flattened), len(set(flattened)))
        with self.assertRaises(WorkflowError):
            tool_classes(["teleport"])

    def test_different_model_identifiers_and_generation_settings_are_rejected(self):
        single, multi = conditions()
        multi["model"]["model"] = "deepseek-reasoner"
        self.assertIn("model_model_differs", codes(validate_pair(single, multi)))
        single, multi = conditions()
        single["model"]["max_output_tokens"] = 4096
        self.assertIn("model_max_output_tokens_differs", codes(validate_pair(single, multi)))
        single, multi = conditions()
        multi["model"]["provider"] = "hkgai"
        report = validate_pair(single, multi)
        self.assertEqual(report["status"], "invalid")
        self.assertEqual(report["confounds"], [])

    def test_incompatible_tasks_and_unmatched_cases_are_rejected(self):
        single, multi = conditions()
        multi["tasks"][0]["content_sha256"] = "0" * 64
        self.assertIn("case_content_differs", codes(validate_pair(single, multi)))
        single, multi = conditions()
        multi["tasks"] = multi["tasks"][:-1]
        self.assertIn("case_sets_differ", codes(validate_pair(single, multi)))
        single, multi = conditions()
        multi["tasks"].reverse()
        self.assertIn("case_sets_differ", codes(validate_pair(single, multi)))

    def test_different_acceptance_criteria_are_rejected(self):
        data = json.loads((ROOT / "evaluation/topology/cases/c07-cases.json").read_text())
        cases = [parse_case(c) for c in data]
        live = live_config()
        single, _ = conditions(live, cases=cases)
        data[3]["expected"]["artifacts"]["total.txt"] = "100"
        _, multi = conditions(live, cases=[parse_case(c) for c in data])
        self.assertTrue({"acceptance_differs", "case_content_differs"} <= codes(validate_pair(single, multi)))

    def test_aggregate_budget_is_compared_not_per_member_limits(self):
        # Single agent 24 attempts vs each member's 8: valid, because the team shares 24.
        self.assertEqual(validate_pair(*conditions())["status"], "valid")
        report = validate_pair(*conditions(single={**SINGLE, "model_attempts": 8}))
        self.assertIn("effective_model_attempts_differs", codes(report))
        self.assertIn("(8 single vs 24 multi)", next(e["message"] for e in report["errors"]))
        for key, value in (("duration_seconds", 600), ("tool_calls", 32), ("reported_tokens", 32000)):
            self.assertIn(f"effective_{key}_differs", codes(validate_pair(*conditions(single={**SINGLE, key: value}))))
        single, multi = conditions()
        multi["budget"]["aggregate"]["model_attempts"] = 48
        self.assertIn("aggregate_differs", codes(validate_pair(single, multi)))
        self.assertIn("repeated_outcomes_differs",
                      codes(validate_pair(*conditions(single={**SINGLE, "repeated_outcomes": 5}))))

    def test_team_that_cannot_reach_the_shared_ceiling_is_detected(self):
        live = live_config(tree_limits=TreeLimits(2, 4, 24, 64000, 64, 600))
        roles = live_roles(live_members(live), live)
        self.assertEqual(effective_ceilings("multi_agent", roles, "coordinator", live.tree_limits)["model_attempts"], 16)
        self.assertIn("effective_model_attempts_differs", codes(validate_pair(*conditions(live))))

    def test_unauthorized_tool_and_backend_differences_are_detected(self):
        single, multi = conditions()
        single["roles"]["solo"]["tools"].append("run_python")
        single["capabilities"]["tools"].append("run_python")
        report = validate_pair(single, multi)
        self.assertIn("task_tools_differ", codes(report))
        self.assertIn("run_python (code_execution) only in single_agent", " ".join(e["message"] for e in report["errors"]))
        single, multi = conditions()
        multi["capabilities"]["backends"]["web"] = True
        self.assertIn("backends_differ", codes(validate_pair(single, multi)))
        single, multi = conditions()
        single["roles"]["solo"]["tools"].append("delegate_task")
        single["capabilities"]["coordination_tools"].append("delegate_task")
        self.assertTrue({"single_can_delegate", "single_coordination_tools"} <= codes(validate_pair(single, multi)))
        single, multi = conditions()
        single["capabilities"]["tools"].remove("update_text")  # Summary no longer matches roles.
        self.assertIn("capability_summary_mismatch", codes(validate_pair(single, multi)))

    def test_invalid_single_agent_controls_are_rejected(self):
        base = json.loads((ROOT / "evaluation/topology/cases/c07-cases.json").read_text())[3]
        variants = {
            "assignee 'writer'": {"expected": {**base["expected"], "subtasks": [
                {"assignee": "writer", "title": "Draft", "final_state": "succeeded"}]}},
            "forces decomposition": {"expected": {**base["expected"], "min_tasks": 2}},
            "topology-specific agents": {"goal": "Delegate the sum to the writer and return total.txt"},
            "fixed script": {"driver": "offline_delegation", "constraints": []},
            "negative evaluator controls": {"control": "negative"},
            "held-out": {"split": "heldout"},
            "scripted human": {"human_responses": ["yes"]},
            "positive goal": {"expected": {**base["expected"], "final_state": "failed"}},
        }
        for needle, change in variants.items():
            reasons = case_eligibility(parse_case({**base, **change}))
            self.assertTrue(any(needle in r for r in reasons), (needle, reasons))
        self.assertEqual(case_eligibility(parse_case(base)), [])
        with self.assertRaises(FairnessError) as raised:
            TopologyExperiment(NEGATIVE)
        self.assertEqual(codes(raised.exception.report), {"ineligible_case"})
        self.assertIn("prescribes a delegated subtask", str(raised.exception))

    def test_memory_mismatches_and_memory_tools_are_detected(self):
        single, multi = conditions()
        multi["memory"] = {"mode": "frozen", "initial_state": "seeded", "tools": "search"}
        self.assertTrue({"memory_differs", "memory_unsupported"} <= codes(validate_pair(single, multi)))
        single, multi = conditions()
        for record in (single, multi):
            record["memory"]["initial_state"] = "carried-over"
        self.assertIn("memory_policy_altered", codes(validate_pair(single, multi)))
        single, multi = conditions()
        for record in (single, multi):
            record["capabilities"]["tools"].append("search_memory")
            next(iter(record["roles"].values()))["tools"].append("search_memory")
        self.assertIn("memory_tools_present", codes(validate_pair(single, multi)))

    def test_human_intervention_mismatches_are_detected(self):
        single, multi = conditions()
        single["human"]["responder"] = "scripted"
        multi["human"]["responder"] = "live_human"
        report = validate_pair(single, multi)
        self.assertIn("responder_type_differs", codes(report))
        self.assertIn("Methodological difference", " ".join(e["message"] for e in report["errors"]))
        single, multi = conditions()
        multi["human"]["clarification"] = "answered automatically"
        self.assertIn("human_policy_differs", codes(validate_pair(single, multi)))

    def test_malformed_records_and_swapped_topologies_fail_closed(self):
        single, multi = conditions()
        self.assertIn("topology_order", codes(validate_pair(multi, single)))
        del multi["budget"]
        self.assertIn("malformed_record", codes(validate_pair(single, multi)))
        single, multi = conditions()
        multi["roles"] = {"coordinator": multi["roles"]["coordinator"] | {"delegates": []}}
        self.assertIn("multi_not_team", codes(validate_pair(single, multi)))

    def test_counterbalanced_order_alternates_first_arm(self):
        slots = planned_slots(2, ["a", "b"])
        firsts = [s["topology"] for s in slots if s["pair_position"] == 0]
        self.assertEqual(firsts, ["single_agent", "multi_agent", "multi_agent", "single_agent"])
        self.assertEqual([s["slot"] for s in slots], list(range(8)))


SHARED_PREFIXES = (("model",), ("budget", "aggregate"), ("budget", "effective"), ("budget", "repeated_outcomes"),
                   ("capabilities", "backends"), ("memory",), ("human",), ("constraints",), ("tasks",))


def leaves(value, path=()):
    """Every scalar or list-of-scalars position inside a condition record."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield from leaves(item, path + (key,))
    elif isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
        for index, item in enumerate(value):
            yield from leaves(item, path + (index,))
    else:
        yield path


def perturbed(value):
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + 1
    if isinstance(value, str):
        return value + "-changed"
    if isinstance(value, list):
        return [v + 1 for v in value] if value and all(isinstance(v, int) for v in value) else value + ["changed"]
    return "changed"  # None


def edit(record, path):
    target = record
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = perturbed(target[path[-1]])


class InvariantTests(unittest.TestCase):
    def shared_paths(self):
        single, _ = conditions()
        return [p for p in leaves(single) if any(p[:len(prefix)] == prefix for prefix in SHARED_PREFIXES)
                and p != ("budget", "effective", "tasks") and p[-1] != "ineligible"]

    def test_any_one_sided_change_to_a_shared_condition_invalidates_the_pair(self):
        paths = self.shared_paths()
        self.assertGreater(len(paths), 30)
        for path in paths:
            for side in (0, 1):
                pair = list(conditions())
                edit(pair[side], path)
                self.assertEqual(validate_pair(*pair)["status"], "invalid", (path, side))

    def test_identical_changes_on_both_sides_keep_the_pair_comparable(self):
        # Memory and human blocks are additionally pinned to declared policies.
        for path in self.shared_paths():
            if path[0] in {"memory", "human"}:
                continue
            single, multi = conditions()
            edit(single, path)
            edit(multi, path)
            self.assertEqual(validate_pair(single, multi)["status"], "valid", path)

    def test_seeded_random_budgets_match_only_when_aggregate_ceilings_match(self):
        rng = random.Random(20261022)
        for _ in range(25):
            tree = TreeLimits(rng.randint(2, 20), rng.randint(1, 6), rng.randint(4, 120), rng.randint(1000, 200000),
                              rng.randint(4, 300), rng.randint(60, 1200))
            live = live_config(role_limits=Limits(rng.randint(1, 20), rng.randint(500, 50000), rng.randint(30, 900),
                                                  rng.randint(1, 5)),
                               tree_limits=tree, tool_calls=rng.randint(1, 64), enable_web=rng.random() < 0.5,
                               enable_delete=rng.random() < 0.5)
            roles = live_roles(live_members(live), live)
            ceilings = effective_ceilings("multi_agent", roles, "coordinator", tree)
            matched = {"model_attempts": ceilings["model_attempts"], "reported_tokens": ceilings["reported_tokens"],
                       "duration_seconds": ceilings["duration_seconds"], "tool_calls": ceilings["tool_calls"],
                       "repeated_outcomes": live.role_limits.repeated_outcomes}
            self.assertEqual(validate_pair(*conditions(live, single=matched))["status"], "valid", (tree, live.role_limits))
            for key in ("model_attempts", "reported_tokens", "duration_seconds", "tool_calls"):
                if matched[key] > 1:
                    report = validate_pair(*conditions(live, single={**matched, key: matched[key] - 1}))
                    self.assertIn(f"effective_{key}_differs", codes(report))
                if matched[key] == getattr(tree, key):  # A limit above the binding tree ceiling changes nothing.
                    roomy = {**matched, key: matched[key] + 7}
                    if key != "tool_calls" or roomy[key] <= 1000:
                        self.assertEqual(validate_pair(*conditions(live, single=roomy))["status"], "valid")

    def test_eligibility_generalizes_to_independently_authored_repository_cases(self):
        verdicts = {c.id: not case_eligibility(c) for directory in ("evaluation/connection", "evaluation/memory/cases",
                                                                     "evaluation/dev")
                    for c in load_cases(ROOT / directory)}
        self.assertFalse(verdicts.pop("live-checked-note"))  # Names agents and prescribes a writer subtask.
        for case_id in ("live-structured-data", "dev-live-summary", "memory-train-a", "memory-train-b",
                        "memory-probe-a", "memory-probe-b"):  # Single-task live cases with topology-neutral goals.
            self.assertTrue(verdicts.pop(case_id), case_id)
        self.assertTrue(verdicts)
        self.assertFalse(any(verdicts.values()))  # Every remaining case uses a fixed offline script.


class ManifestTests(unittest.TestCase):
    def test_fingerprints_are_deterministic_and_separate_identity_shared_and_conditions(self):
        first, second = TopologyExperiment(CONFIG), TopologyExperiment(CONFIG)
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(first.fingerprints, second.fingerprints)
        with tempfile.TemporaryDirectory() as temp:
            reformatted = write_manifest(temp)
            data = json.loads(reformatted.read_text())
            data["runtime_plan"] = str(ROOT / "evaluation/topology/runtime.json")
            reformatted.write_text(json.dumps(data, indent=7, sort_keys=True))
            self.assertEqual(TopologyExperiment(reformatted).sha256, first.sha256)
            renamed = TopologyExperiment(write_manifest(temp, experiment_id="c07-renamed"))
            self.assertNotEqual(renamed.fingerprints["experiment"], first.fingerprints["experiment"])
            self.assertEqual(renamed.fingerprints["shared"], first.fingerprints["shared"])
            self.assertNotEqual(renamed.sha256, first.sha256)
            topologies = json.loads(CONFIG.read_text())["topologies"]
            topologies["multi_agent"]["child_release"] = "trusted-review"
            changed = TopologyExperiment(write_manifest(temp, topologies=topologies))
            self.assertEqual(changed.fingerprints["single_agent"], first.fingerprints["single_agent"])
            self.assertNotEqual(changed.fingerprints["multi_agent"], first.fingerprints["multi_agent"])
            budget = TopologyExperiment(write_manifest(temp, runtime={"max_output_tokens": 1024}))
            self.assertNotEqual(budget.fingerprints["shared"], first.fingerprints["shared"])

    def test_inspection_never_calls_a_model_and_contains_no_secret(self):
        from unittest.mock import patch
        with patch("agent_lab.deepseek.DeepSeekHTTP.__call__", side_effect=AssertionError("network")), \
             patch.dict("os.environ", {"COURSE_DEEPSEEK_API_KEY": "secret-value-123"}):
            info = TopologyExperiment(CONFIG).inspect()
        self.assertEqual(info["model_calls"], 0)
        self.assertNotIn("secret-value-123", json.dumps(info))
        self.assertIn("Course-approved model identifier has not been configured", info["blockers"])
        self.assertEqual(info["maximum_model_attempts"], 16 * 24)
        self.assertEqual(info["maximum_reported_tokens"], 16 * 64000)

    def test_malformed_unknown_and_unsupported_fields_are_rejected(self):
        topologies = json.loads(CONFIG.read_text())["topologies"]
        bad = {  # change -> fragment of the specific rejection reason
            "unknown field": ({"api_key": "sk-123"}, "missing or unknown fields"),
            "official evidence": ({"evidence_class": "official_benchmark"}, "Official benchmark evidence requires"),
            "id": ({"experiment_id": "Bad ID!"}, "experiment_id must be"),
            "memory on": ({"memory": {"mode": "on", "initial_state": "fresh-empty-per-run"}}, "Only memory mode 'disabled'"),
            "scripted human": ({"human": {"policy": "scripted-replies-v1"}}, "boundary-stops-run-v1 human policy"),
            "order": ({"procedure": {"replicates": 1, "order": "random", "isolation": "fresh-state-directory-per-run-v1"}},
                      "procedure needs"),
            "replicates": ({"procedure": {"replicates": 0, "order": "alternating-by-replicate-and-case-v1",
                                          "isolation": "fresh-state-directory-per-run-v1"}}, "procedure needs"),
            "annotations": ({"case_annotations": {}}, "case_annotations must annotate"),
            "pilot without budget": ({"pilot_budget": None}, "must declare an explicit pilot_budget"),
            "single limits": ({"topologies": {**topologies, "single_agent": {**topologies["single_agent"],
                                              "task_limits": {"model_attempts": 24}}}}, "task_limits needs exactly"),
            "agent": ({"topologies": {**topologies, "single_agent": {**topologies["single_agent"], "agent": "coordinator"}}},
                      "single_agent must use agent"),
            "release": ({"topologies": {**topologies, "multi_agent": {**topologies["multi_agent"], "child_release": "auto"}}},
                        "child_release must be"),
        }
        with tempfile.TemporaryDirectory() as temp:
            for label, (change, reason) in bad.items():
                if label == "unknown field":
                    data = json.loads(CONFIG.read_text()) | change
                    data["runtime_plan"] = str(ROOT / "evaluation/topology/runtime.json")
                    path = Path(temp) / "manifest.json"
                    path.write_text(json.dumps(data))
                else:
                    path = write_manifest(temp, **change)
                with self.assertRaisesRegex(WorkflowError, re.escape(reason), msg=label):
                    TopologyExperiment(path)
            (Path(temp) / "broken.json").write_text('{"schema": "c07-single-multi-topology", "schema": 1}')
            with self.assertRaises(WorkflowError):
                TopologyExperiment(Path(temp) / "broken.json")

    def test_runtime_memory_or_unequal_single_budget_fails_closed_at_load(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(WorkflowError):
                TopologyExperiment(write_manifest(temp, runtime={"capabilities": {"web": False, "memory": True,
                    "child_retries": 0, "docker_host": None, "python_image": None, "git_config": None}}))
            topologies = json.loads(CONFIG.read_text())["topologies"]
            topologies["single_agent"]["task_limits"]["model_attempts"] = 8
            with self.assertRaises(FairnessError) as raised:
                TopologyExperiment(write_manifest(temp, topologies=topologies))
            self.assertEqual(codes(raised.exception.report), {"effective_model_attempts_differs"})

    def test_child_retries_are_recorded_as_a_team_only_confound(self):
        with tempfile.TemporaryDirectory() as temp:
            experiment = TopologyExperiment(write_manifest(temp, runtime={"capabilities": {"web": False, "memory": False,
                "child_retries": 1, "docker_host": None, "python_image": None, "git_config": None}}))
        self.assertIn("child_retries", {c["code"] for c in experiment.fairness["confounds"]})
        self.assertEqual(experiment.conditions["single_agent"].record["child_retries"], 0)


if __name__ == "__main__":
    unittest.main()
