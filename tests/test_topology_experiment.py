"""C07 paired runs through the real scheduler with replayed (scripted) model turns.

Fixture outcomes are fixed by their scripts. These checks establish that the
runtime, budgets, acceptance, isolation and reporting work, not model quality.
"""
from contextlib import closing, redirect_stdout, redirect_stderr
import copy
import io
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))  # Shared helpers also resolve when run by file path.

from agent_lab.core import WorkflowError
from agent_lab.deepseek import DeepSeekHTTP, ProviderError
from agent_lab.evaluation.__main__ import main
from agent_lab.evaluation.topology_fixture import ReplayTransport, load_fixture, load_fixture_set, run_fixture
from agent_lab.core import Workflow
from agent_lab.evaluation.topology_plan import TopologyExperiment, coordination_metrics
from agent_lab.evaluation.topology_report import FIXTURE_MODEL, compare_topology, topology_markdown
from agent_lab.files import FileTools
from test_topology_fairness import NEGATIVE, ROOT, write_manifest

FIXTURES = ROOT / "evaluation/topology/fixtures"


def one_replicate(directory, **changes):
    procedure = {"replicates": 1, "order": "alternating-by-replicate-and-case-v1",
                 "isolation": "fresh-state-directory-per-run-v1"}
    return write_manifest(directory, procedure=procedure, **changes)


def row(report, case, topology):
    return next(r for r in report["results"] if r["case_id"] == case and r["topology"] == topology)


ORACLE_VALUES = ('"the": 3', '"the":3', '"hello-world"', '"multi-agent"', '"c07-baseline"', "100\n")


def prompt_leaks(request):
    """Oracle values present in the decoded system prompt or task context strings."""
    context = json.loads(request["messages"][1]["content"])
    texts = [request["messages"][0]["content"], context["global_goal"], context["current_assignment"],
             *context["constraints"], json.dumps(context.get("role", {}), ensure_ascii=False)]
    return [value for value in ORACLE_VALUES if any(value in text for text in texts)]


def database(run_dir, result):
    return closing(sqlite3.connect(Path(run_dir) / result["state_directory"] / "workflow.sqlite3"))


class TopologyReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.manifest = one_replicate(cls.temp.name)
        cls.runs = Path(cls.temp.name) / "runs"
        cls.nominal, cls.nominal_driver = run_fixture(cls.manifest, FIXTURES / "nominal-set.json", cls.runs)
        cls.adverse, _ = run_fixture(cls.manifest, FIXTURES / "adverse-set.json", cls.runs)
        cls.nominal_dir = cls.runs / cls.nominal["run_id"]
        cls.adverse_dir = cls.runs / cls.adverse["run_id"]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_nominal_replay_runs_both_topologies_through_the_real_scheduler(self):
        report = self.nominal
        self.assertEqual((report["mode"], report["evidence_class"], report["model_calls"]),
                         ("offline_fixture", "engineering_validation", 0))
        self.assertEqual(report["comparison"]["status"], "engineering_only")
        self.assertFalse(report["comparison"]["superiority_established"])
        self.assertEqual(report["comparison"]["cost"]["status"], "unavailable")
        self.assertEqual({r["classification"] for r in report["results"]}, {"completed"})
        for result in report["results"]:
            self.assertEqual(result["workflow"]["observed_models"], [FIXTURE_MODEL])
            tasks = result["coordination"]["tasks"]
            if result["topology"] == "single_agent":
                self.assertEqual((tasks, result["coordination"]["coordination_tool_calls"]), (1, 0))
            else:
                self.assertGreater(tasks, 1)
                self.assertTrue(all(s["release"] == "structural_handoff" for s in result["coordination"]["subtasks"]))
                with database(self.nominal_dir, result) as db:
                    root = db.execute("SELECT evidence FROM tasks WHERE parent IS NULL").fetchone()[0]
                self.assertNotIn("c07_handoff", root)  # The root is judged by the case's own criteria.
        markdown = (self.nominal_dir / "report.md").read_text()
        self.assertIn("ENGINEERING VALIDATION ONLY", markdown)
        self.assertIn("scripted outcome, not performance", markdown)

    def test_repairs_follow_real_trusted_verification_feedback(self):
        result = row(self.nominal, "c07-text-word-counts", "single_agent")
        with database(self.nominal_dir, result) as db:
            requests = " ".join(r[0] for r in db.execute("SELECT request FROM runner_turns ORDER BY number"))
        self.assertIn("trusted_verification_failure", requests)
        self.assertIn("counts.json:json_equals", requests)
        result = row(self.nominal, "c07-text-word-counts", "multi_agent")
        with database(self.nominal_dir, result) as db:
            requests = " ".join(r[0] for r in db.execute("SELECT request FROM runner_turns"))
        self.assertIn("Assignee is not an eligible delegate", requests)

    def test_adverse_failures_remain_visible_in_every_denominator(self):
        comparison = self.adverse["comparison"]
        single, multi = comparison["arms"]["single_agent"], comparison["arms"]["multi_agent"]
        self.assertEqual(single["failure_categories"], {"human_boundary": 1, "none": 2, "provider_error": 1})
        self.assertEqual(multi["failure_categories"], {"budget_exhausted": 1, "none": 3})
        self.assertEqual((single["planned"], single["goals_verified_completed"], single["goal_completion_rate_planned"]),
                         (4, 2, 0.5))
        self.assertEqual(single["human_interventions"], {"known": 1, "status": "complete"})
        failed = row(self.adverse, "c07-correction-total", "multi_agent")
        self.assertIn("Model attempt budget exhausted", json.dumps(failed["coordination"]["stop_reasons"]))
        self.assertEqual(failed["coordination"]["model_attempts_by_agent"]["coordinator"], 8)
        handoff = row(self.adverse, "c07-structured-release", "multi_agent")
        with database(self.adverse_dir, handoff) as db:
            writer = " ".join(r[0] for r in db.execute(
                "SELECT r.request FROM runner_turns r JOIN tasks t ON t.id=r.task WHERE t.assignee='writer'"))
        self.assertIn("c07_handoff:offered_to_parent", writer)
        self.assertEqual(handoff["classification"], "completed")

    def test_missing_usage_is_reported_as_unknown_never_zero(self):
        provider = row(self.adverse, "c07-python-slugify", "single_agent")
        self.assertEqual(provider["failure_category"], "provider_error")
        self.assertEqual(provider["usage"]["unknown_usage_attempts"], 1)
        usage = self.adverse["comparison"]["arms"]["single_agent"]["usage"]
        self.assertEqual(usage["reported_tokens_status"], "lower_bound")
        self.assertEqual(self.adverse["comparison"]["paired"]["pairs_with_complete_usage"], 3)
        report = copy.deepcopy(self.nominal)
        for result in report["results"]:
            if result["topology"] == "single_agent":
                result.update(classification="driver_error", workflow=None, usage=None, checks={}, failed_checks=[],
                              coordination=None, failure_category="driver_error")
        usage = compare_topology(report)["arms"]["single_agent"]["usage"]
        self.assertEqual((usage["reported_tokens_known"], usage["reported_tokens_status"], usage["reserved_model_attempts"]),
                         (None, "unavailable", None))
        self.assertEqual(usage["runs_without_usage_evidence"], 4)

    def test_interrupted_and_unrun_runs_stay_visible_as_incomplete_pairs(self):
        report = copy.deepcopy(self.nominal)
        report["ended"] = None
        report["results"][3].update(status="running", classification="not_run", workflow=None, usage=None,
                                    failure_category="interrupted")
        report["results"][4].update(status="not_run", classification="not_run", workflow=None, usage=None,
                                    failure_category="not_run")
        comparison = compare_topology(report)
        self.assertEqual(comparison["paired"]["complete_pairs"], 2)
        self.assertEqual(len(comparison["paired"]["incomplete_pairs"]), 2)
        arms = comparison["arms"]
        self.assertEqual(sum(a["planned"] for a in arms.values()), 8)
        self.assertEqual(sum(a["interrupted"] + a["not_run"] for a in arms.values()), 2)
        self.assertIn("Run is still in progress or was interrupted", comparison["reasons"])

    def test_runs_are_isolated_with_fresh_state_and_no_shared_authority(self):
        directories = {r["state_directory"] for r in self.adverse["results"]}
        self.assertEqual(len(directories), len(self.adverse["results"]))
        for result in self.adverse["results"]:
            with database(self.adverse_dir, result) as db:
                roots = db.execute("SELECT id,title FROM tasks WHERE parent IS NULL").fetchall()
                self.assertEqual([r[0] for r in roots], [result["root"]])
                self.assertEqual(db.execute("SELECT count(*) FROM lessons").fetchone()[0], 0)
                requests = db.execute("SELECT count(*) FROM requests").fetchone()[0]
                members = {r[0] for r in db.execute("SELECT actor FROM members")}
            self.assertEqual(requests, 1 if result["failure_category"] == "human_boundary" else 0)
            expected = {"evaluator", "solo"} if result["topology"] == "single_agent" else \
                {"evaluator", "coordinator", "writer", "editor", "researcher"}
            self.assertEqual(members, expected)
            files = Path(self.adverse_dir) / result["state_directory"] / "files"
            self.assertTrue(files.is_dir())

    def test_agent_prompts_never_contain_the_independent_answers(self):
        checked = 0
        for _, transport in self.nominal_driver.transports:
            for request in transport.requests:
                if sum(m["role"] == "assistant" for m in request["messages"]) != 0:
                    continue  # Later turns legitimately contain the agent's own outputs.
                context = json.loads(request["messages"][1]["content"])
                self.assertLessEqual(set(context), {"global_goal", "current_assignment", "constraints", "role", "task_id",
                                                    "parent_task_id", "root_task_id"})
                if context["parent_task_id"] is None:
                    self.assertEqual(prompt_leaks(request), [])
                    checked += 1
        self.assertEqual(checked, 8)
        # The check itself detects an injected answer (guards against a vacuous test).
        leaked = copy.deepcopy(transport.requests[0])
        context = json.loads(leaked["messages"][1]["content"])
        context["global_goal"] += ' Expected: {"the": 3} and "hello-world".'
        leaked["messages"][1]["content"] = json.dumps(context)
        self.assertEqual(prompt_leaks(leaked), ['"the": 3', '"hello-world"'])

    def test_tampered_relabelled_or_unmatched_evidence_is_not_comparable(self):
        def broken(change):
            report = copy.deepcopy(self.nominal)
            change(report)
            return compare_topology(report)["status"]
        changes = {
            "dropped run": lambda r: r["results"].pop(),
            "moved case": lambda r: r["results"][0].update(case_id="c07-python-slugify"),
            "swapped arm": lambda r: r["results"][0].update(topology="multi_agent"),
            "edited check": lambda r: r["results"][0]["checks"].update(final_state=False),
            "edited goal": lambda r: r["results"][1]["case"].update(goal="Something easier"),
            "edited conditions": lambda r: r["conditions"]["conditions"]["multi_agent"]["model"].update(model="other"),
            "edited plan fingerprint": lambda r: r.update(plan_sha256="0" * 64),
            "consistently re-fingerprinted edit": lambda r: (
                r["conditions"]["shared"]["procedure"].update(replicates=2),
                r.update(conditions_sha256=__import__("agent_lab.evaluation.manifest", fromlist=["digest"]).digest(r["conditions"]))),
            "relabelled evidence": lambda r: r.update(evidence_class="pilot_model"),
            "edited expected outcome": lambda r: r["results"][0]["case"]["expected"].update(final_state="failed"),
            "invented success": lambda r: r["results"][0]["workflow"]["task_outcomes"][0].update(state="failed"),
            "negative usage": lambda r: r["results"][0]["usage"].update(reported_tokens=-1),
        }
        for label, change in changes.items():
            self.assertEqual(broken(change), "not_comparable", label)
        relabelled = copy.deepcopy(self.nominal)
        relabelled.update(mode="live", evidence_class="pilot_model", model_calls=None)
        comparison = compare_topology(relabelled)
        self.assertEqual(comparison["status"], "not_comparable")
        self.assertTrue(any("differs from declared" in r for r in comparison["reasons"]))

    def test_trusted_review_policy_blocks_unattended_team_runs(self):
        topologies = json.loads((ROOT / "evaluation/topology-plan.json").read_text())["topologies"]
        topologies["multi_agent"]["child_release"] = "trusted-review"
        with tempfile.TemporaryDirectory() as temp:
            report, _ = run_fixture(one_replicate(temp, topologies=topologies), FIXTURES / "nominal-set.json", Path(temp) / "runs")
        arms = report["comparison"]["arms"]
        self.assertEqual(arms["multi_agent"]["failure_categories"], {"awaiting_trusted_review": 4})
        self.assertEqual(arms["single_agent"]["failure_categories"], {"none": 4})

    def test_fixture_files_and_references_fail_closed(self):
        fixture = json.loads((FIXTURES / "c07-correction-total.single_agent.nominal.json").read_text())
        with tempfile.TemporaryDirectory() as temp:
            for change in ({"provenance": {**fixture["provenance"], "model_evidence": True}},
                           {"scripts": {"solo": [{"final": "done", "tool_calls": []}]}},
                           {"topology": "both"}, {"extra": 1}):
                path = Path(temp) / "fixture.json"
                path.write_text(json.dumps({**fixture, **change}))
                with self.assertRaises(WorkflowError):
                    load_fixture(path)
            data = json.loads((FIXTURES / "nominal-set.json").read_text())
            data["entries"]["c07-correction-total"]["single_agent"] = "../outside.json"
            (Path(temp) / "set.json").write_text(json.dumps(data))
            with self.assertRaises(WorkflowError):
                load_fixture_set(Path(temp) / "set.json")
        transport = ReplayTransport({"scripts": {"solo": [{"tool_calls": [{"name": "update_text", "arguments": {
            "path": "x.txt", "content": "y", "expected_sha256": {"$ref": "file_sha256", "path": "x.txt"}}}]}]}})
        request = {"messages": [{"role": "system", "content": "s"}, {"role": "user", "content": json.dumps(
            {"role": {"agent": "solo"}, "task_id": "t1", "parent_task_id": None})}]}
        with self.assertRaises(ProviderError):
            transport(json.dumps(request).encode())
        other = copy.deepcopy(request)
        other["messages"][1]["content"] = json.dumps({"role": {"agent": "solo"}, "task_id": "t2", "parent_task_id": None})
        with self.assertRaises(ProviderError):
            transport(json.dumps(other).encode())


class ReviewRegressionTests(unittest.TestCase):
    """Reporting invariants: release basis, missing evidence and actual collaboration."""

    def test_child_release_basis_never_claims_content_verification(self):
        with tempfile.TemporaryDirectory() as temp:
            workflow = Workflow(Path(temp) / "w.sqlite3")
            files = FileTools(workflow, Path(temp) / "files")
            try:
                workflow.register_actor("h", "human")
                for agent in ("a", "b", "c"):
                    workflow.register_actor(agent, "agent")
                chat = workflow.create_chat("group", ["h", "a", "b", "c"])
                root = workflow.create_task(chat, "h", "a", "goal")
                workflow.start_task(root, "a")
                expected = {"b": ({"human_review_accepted": True}, "human_review"),
                            "c": ({"c07_handoff:offered_to_parent": True}, "structural_handoff")}
                for agent, (checks, _) in expected.items():
                    child = workflow.create_task(chat, "a", agent, "part " + agent, parent=root)
                    workflow.start_task(child, agent)
                    workflow.finish_task(child, agent, checks=checks)
                subtasks = coordination_metrics(workflow, root)["subtasks"]
            finally:
                files.close()
                workflow.close()
        self.assertEqual({s["assignee"]: s["release"] for s in subtasks}, {a: b for a, (_, b) in expected.items()})

    def test_raw_outcomes_record_how_each_task_was_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            report, _ = run_fixture(one_replicate(temp), FIXTURES / "nominal-set.json", Path(temp) / "runs")
        for result in report["results"]:
            for outcome in result["workflow"]["task_outcomes"]:
                basis = "case_criteria" if outcome["parent"] is None else "structural_handoff"
                self.assertEqual(outcome["acceptance_basis"], basis)
        subtasks = compare_topology(report)["arms"]["multi_agent"]["subtasks"]
        self.assertNotIn("content_verified", subtasks)
        self.assertEqual(subtasks["released_by_structural_handoff"], subtasks["succeeded"])
        self.assertIn("content not independently verified", topology_markdown(report))

    def test_missing_workflow_makes_derived_counts_lower_bounds(self):
        with tempfile.TemporaryDirectory() as temp:
            report, _ = run_fixture(one_replicate(temp), FIXTURES / "adverse-set.json", Path(temp) / "runs")
        report = copy.deepcopy(report)
        row(report, "c07-text-word-counts", "single_agent").update(
            classification="driver_error", workflow=None, usage=None, checks={}, failed_checks=[], coordination=None,
            failure_category="driver_error")
        arm = compare_topology(report)["arms"]["single_agent"]
        self.assertEqual(arm["human_interventions"], {"known": 0, "status": "lower_bound"})
        self.assertEqual(arm["coordination"]["status"], "lower_bound")
        self.assertEqual(compare_topology(report)["arms"]["multi_agent"]["human_interventions"]["status"], "complete")

    def test_configured_team_is_distinguished_from_actual_collaboration(self):
        with tempfile.TemporaryDirectory() as temp:
            fixtures = Path(temp) / "fixtures"
            shutil.copytree(FIXTURES, fixtures)
            alone = json.loads((fixtures / "c07-correction-total.multi_agent.nominal.json").read_text())
            alone.update(fixture_id="test-coordinator-alone", description="Coordinator solves without delegating",
                         scripts={"coordinator": [{"tool_calls": [{"name": "create_text", "arguments": {
                             "path": "total.txt", "content": "100\n"}}]}, {"final": "Done without delegating."}]})
            (fixtures / "alone.json").write_text(json.dumps(alone))
            index = json.loads((fixtures / "nominal-set.json").read_text())
            index["entries"]["c07-correction-total"]["multi_agent"] = "alone.json"
            (fixtures / "nominal-set.json").write_text(json.dumps(index))
            report, _ = run_fixture(one_replicate(temp), fixtures / "nominal-set.json", Path(temp) / "runs")
        solo_team = row(report, "c07-correction-total", "multi_agent")
        self.assertEqual(solo_team["classification"], "completed")  # Not a failure; reported accurately.
        self.assertEqual((solo_team["coordination"]["delegation_performed"], solo_team["coordination"]["participating_agents"]),
                         (False, ["coordinator"]))
        team = compare_topology(report)["arms"]["multi_agent"]["collaboration"]
        self.assertEqual((team["configured_agents"], team["runs_with_delegation"], team["runs_with_evidence"]), (4, 3, 4))
        self.assertEqual(team["participating_agents_min_max"], [1, 2])
        self.assertIn("Runs with actual delegation", topology_markdown(report))


class LivePathTests(unittest.TestCase):
    """The real live driver and DeepSeekHTTP object, with only the HTTP call replaced (no network)."""

    def manifest(self, temp, **changes):
        return one_replicate(temp, runtime={"model": "deepseek-chat"}, **changes)

    def fake_http(self, model, fail=None):
        _, fixtures = load_fixture_set(FIXTURES / "nominal-set.json")
        cases = {c["goal"]: c["id"] for c in json.loads((ROOT / "evaluation/topology/cases/c07-cases.json").read_text())}
        transports, calls = {}, []

        def call(http, payload):
            assert http._allowed is True
            context = json.loads(json.loads(payload)["messages"][1]["content"])
            key = (cases[context["global_goal"]], "single_agent" if context["role"]["agent"] == "solo" else "multi_agent")
            if key == fail:
                raise ProviderError("simulated transport failure before any response")
            response = json.loads(transports.setdefault(key, ReplayTransport(fixtures[key]))(payload))
            response["model"] = model
            calls.append(key)
            return json.dumps(response).encode()
        return call, calls

    def test_authorized_pilot_uses_the_live_driver_and_records_pilot_evidence(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch.dict("os.environ", {"COURSE_DEEPSEEK_API_KEY": "issued-secret-key"}, clear=True):
            experiment = TopologyExperiment(self.manifest(temp))
            self.assertEqual(experiment.inspect()["blockers"], [])
            fake, calls = self.fake_http("deepseek-chat")
            with patch.object(DeepSeekHTTP, "__call__", fake):
                report = experiment.execute(allow_model_calls=True, plan_sha256=experiment.sha256,
                                            output_root=Path(temp) / "runs")
            saved = (Path(temp) / "runs" / report["run_id"] / "experiment.json").read_text()
        self.assertTrue(calls)
        self.assertEqual((report["mode"], report["evidence_class"], report["model_calls"]), ("live", "pilot_model", None))
        self.assertEqual(report["comparison"]["status"], "pilot_compared")
        self.assertEqual(report["comparison"]["evidence_class"], "pilot_model_evidence")
        self.assertFalse(report["comparison"]["superiority_established"])
        self.assertNotIn("issued-secret-key", saved)

    def test_live_evidence_gaps_prevent_a_complete_comparison(self):
        # A run whose only attempt got no response has no observed model and unknown usage.
        with tempfile.TemporaryDirectory() as temp, \
             patch.dict("os.environ", {"COURSE_DEEPSEEK_API_KEY": "issued"}, clear=True):
            experiment = TopologyExperiment(self.manifest(temp))
            fake, _ = self.fake_http("deepseek-chat", fail=("c07-python-slugify", "single_agent"))
            with patch.object(DeepSeekHTTP, "__call__", fake):
                report = experiment.execute(allow_model_calls=True, plan_sha256=experiment.sha256,
                                            output_root=Path(temp) / "runs")
        comparison = report["comparison"]
        self.assertEqual(comparison["status"], "pilot_incomplete")
        self.assertTrue(any("no observed model identity" in r for r in comparison["reasons"]))
        self.assertTrue(any("unknown usage" in r for r in comparison["reasons"]))
        evidence = comparison["evidence"]
        self.assertEqual((evidence["runs_without_observed_model"], evidence["attempts_with_unknown_usage"]), (1, 1))
        self.assertEqual(evidence["provider_responses_received"],
                         evidence["attempts_reserved"] - evidence["attempts_with_unknown_usage"])

    def test_silent_model_substitution_is_not_comparable(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch.dict("os.environ", {"COURSE_DEEPSEEK_API_KEY": "issued"}, clear=True):
            experiment = TopologyExperiment(self.manifest(temp))
            fake, _ = self.fake_http("some-other-model")
            with patch.object(DeepSeekHTTP, "__call__", fake):
                report = experiment.execute(allow_model_calls=True, plan_sha256=experiment.sha256,
                                            output_root=Path(temp) / "runs")
        self.assertEqual(report["comparison"]["status"], "not_comparable")

    def test_execution_is_refused_without_authorization_budget_or_pilot_class(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch.dict("os.environ", {"COURSE_DEEPSEEK_API_KEY": "issued"}, clear=True), \
             patch.object(DeepSeekHTTP, "__call__", side_effect=AssertionError("network")):
            output = Path(temp) / "runs"
            experiment = TopologyExperiment(self.manifest(temp))
            for permission, sha in ((False, experiment.sha256), (True, "0" * 64)):
                with self.assertRaises(WorkflowError):
                    experiment.execute(allow_model_calls=permission, plan_sha256=sha, output_root=output)
            small = TopologyExperiment(self.manifest(temp, pilot_budget={"max_total_model_attempts": 10}))
            self.assertIn("Planned maximum model attempts exceed the declared pilot budget", small.inspect()["blockers"])
            engineering = TopologyExperiment(self.manifest(temp, evidence_class="engineering_validation", pilot_budget=None))
            for planned in (small, engineering):
                with self.assertRaises(WorkflowError):
                    planned.execute(allow_model_calls=True, plan_sha256=planned.sha256, output_root=output)
            self.assertFalse(output.exists())


SMOKE = ROOT / "evaluation/topology/smoke-plan.json"


def smoke_manifest(directory, *, model=None, **changes):
    runtime = json.loads((ROOT / "evaluation/topology/smoke/runtime.json").read_text())
    runtime.update(cases=str(ROOT / "evaluation/topology/cases"), model=model)
    (Path(directory) / "smoke-runtime.json").write_text(json.dumps(runtime))
    data = json.loads(SMOKE.read_text()) | {"runtime_plan": str(Path(directory) / "smoke-runtime.json")} | changes
    path = Path(directory) / "smoke.json"
    path.write_text(json.dumps(data))
    return path


class SmokeConfigurationTests(unittest.TestCase):
    """The live smoke check stays small, matched and separate from the comparison."""

    def test_smoke_plan_is_bounded_matched_and_never_runs_without_authorization(self):
        experiment = TopologyExperiment(SMOKE)
        info = experiment.inspect()
        self.assertEqual((info["fairness"]["status"], info["planned_runs"]), ("valid", 2))
        self.assertLessEqual(info["maximum_model_attempts"], info["pilot_budget"]["max_total_model_attempts"])
        self.assertEqual(info["maximum_reported_tokens"], 32000)
        main_plan = TopologyExperiment(ROOT / "evaluation/topology-plan.json")
        self.assertLess(info["maximum_model_attempts"], main_plan.maximum_model_attempts())
        self.assertNotEqual(experiment.fingerprints["shared"], main_plan.fingerprints["shared"])
        with self.assertRaises(WorkflowError):
            experiment.execute(allow_model_calls=True, plan_sha256=experiment.sha256, output_root="unused")

    def test_smoke_shape_is_enforced(self):
        with tempfile.TemporaryDirectory() as temp:
            for change in ({"procedure": {"replicates": 2, "order": "alternating-by-replicate-and-case-v1",
                                          "isolation": "fresh-state-directory-per-run-v1"}},
                           {"pilot_budget": None}):
                with self.assertRaises(WorkflowError):
                    TopologyExperiment(smoke_manifest(temp, **change))

    def test_live_smoke_result_is_never_reported_as_a_comparison(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch.dict("os.environ", {"COURSE_DEEPSEEK_API_KEY": "issued"}, clear=True):
            experiment = TopologyExperiment(smoke_manifest(temp, model="deepseek-chat"))
            fake, _ = LivePathTests().fake_http("deepseek-chat")
            with patch.object(DeepSeekHTTP, "__call__", fake):
                report = experiment.execute(allow_model_calls=True, plan_sha256=experiment.sha256,
                                            output_root=Path(temp) / "runs")
            markdown = (Path(temp) / "runs" / report["run_id"] / "report.md").read_text()
        self.assertEqual(report["evidence_class"], "pilot_smoke")
        self.assertEqual(report["comparison"]["status"], "smoke_only")
        self.assertEqual(report["comparison"]["evidence_class"], "pilot_smoke_evidence")
        self.assertIn("LIVE SMOKE CHECK", markdown)
        self.assertEqual(len(report["results"]), 2)


class CommandLineTests(unittest.TestCase):
    def test_cli_plan_rejection_demo_and_compare(self):
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit) as code:
            main(["topology", "plan", "--config", str(NEGATIVE)])
        self.assertEqual(code.exception.code, 1)
        self.assertIn("ineligible_case", out.getvalue())
        self.assertIn("fairness error", err.getvalue())
        with tempfile.TemporaryDirectory() as temp:
            manifest = one_replicate(temp)
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(main(["topology", "demo", "--config", str(manifest), "--output", str(Path(temp) / "runs")]), 0)
            run_id = json.loads(out.getvalue().split("\nReport:")[0])["run_id"]
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(main(["topology", "compare", "--run", str(Path(temp) / "runs" / run_id)]), 0)
            self.assertEqual(json.loads(out.getvalue())["status"], "engineering_only")

    def test_existing_evaluation_commands_still_work(self):
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(["list", "--cases", str(ROOT / "evaluation/dev")]), 0)
        self.assertIn("dev-delegation-note", out.getvalue())
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(["plan", "--config", str(ROOT / "evaluation/development-plan.json")]), 0)
        self.assertEqual(json.loads(out.getvalue())["model_calls"], 0)


if __name__ == "__main__":
    unittest.main()
