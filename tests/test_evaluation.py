"""Evaluation harness checks: case loading, independent acceptance, metrics, labels."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.evaluation import (CaseError, Evaluator, compare_memory, list_runs, load_cases, load_run,
                                  parse_case, summarize)
from agent_lab.files import FileToolError
from agent_lab.inspection import ArtifactInspector
from agent_lab.core import WorkflowError

CASES = Path(__file__).resolve().parents[1] / "evaluation" / "dev"


def case(**overrides):
    data = {"id": "case-one", "title": "Title", "goal": "Goal", "driver": "offline_delegation",
            "human_responses": ["English"], "expected": {"final_state": "succeeded", "artifacts": {"note.txt": "Hello\n"}}}
    data.update(overrides)
    return data


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.output = Path(self.directory.name) / "runs"

    def tearDown(self):
        self.directory.cleanup()

    def test_repository_cases_load_and_validate(self):
        cases = load_cases(CASES)
        self.assertEqual([c.id for c in cases], sorted(c.id for c in cases))
        self.assertIn("dev-negative-control", {c.id for c in cases})
        self.assertTrue(all(c.split == "development" for c in cases))
        for bad in (case(driver="openai"), case(id="Bad Id"), case(expected={"final_state": "done"}),
                    case(approval="maybe"), case(expected={"final_state": "succeeded", "artifacts": {"a": 1}}),
                    {"id": "missing-fields"}):
            with self.assertRaises(CaseError):
                parse_case(bad)
        folder = Path(self.directory.name) / "cases"
        folder.mkdir()
        (folder / "a.json").write_text(json.dumps([case(), case()]))
        with self.assertRaises(CaseError):
            load_cases(folder)

    def test_offline_batch_metrics_labels_and_reports(self):
        run = Evaluator(load_cases(CASES), output_root=self.output).run()
        self.assertEqual((run["mode"], run["benchmark_valid"], run["model_calls"], run["memory"]),
                         ("offline_fixture", False, 0, "not_exercised"))
        results = {r["case"]["id"]: r for r in run["results"]}
        self.assertEqual(results["dev-live-summary"]["classification"], "not_configured")
        self.assertIsNone(results["dev-live-summary"]["duration_seconds"])
        control = results["dev-negative-control"]
        self.assertEqual((control["classification"], control["failed_checks"]), ("acceptance_failed", ["artifact:note.txt"]))
        for name in ("dev-delegation-note", "dev-approval-delete", "dev-approval-reject", "dev-git-push"):
            self.assertEqual(results[name]["classification"], "completed", results[name])
            self.assertTrue(all(results[name]["checks"].values()))
        self.assertEqual(results["dev-git-push"]["checks"]["remote_branch_verified"], True)
        self.assertEqual(results["dev-approval-reject"]["workflow"]["root_state"], "cancelled")
        summary = run["summary"]
        # Controls and unconfigured live cases are excluded from the scored denominator.
        self.assertEqual((summary["executed"], summary["completed"], summary["completion_rate"]), (4, 4, 1.0))
        self.assertEqual((summary["negative_controls"], summary["negative_controls_detected"]), (5, 5))
        self.assertEqual(summary["not_configured"], 1)
        report = (self.output / run["run_id"] / "report.md").read_text()
        self.assertIn("`offline_fixture`", report)
        self.assertIn("not a model benchmark", report)
        self.assertIn("**Benchmark valid:** `false`", report)
        self.assertEqual(load_run(self.output, run["run_id"])["summary"], summary)
        self.assertEqual([r["run_id"] for r in list_runs(self.output)], [run["run_id"]])

    def test_failures_are_classified_not_hidden(self):
        cases = [parse_case(case(id="wrong-state", expected={"final_state": "cancelled"})),
                 parse_case(case(id="no-answer", human_responses=[])),
                 parse_case(case(id="driver-crash"))]
        evaluator = Evaluator(cases, output_root=self.output)
        original = evaluator._run_case

        def run_case(item, directory):
            if item.id == "driver-crash":
                with patch("agent_lab.offline_scenarios.start", side_effect=RuntimeError("fixture exploded")):
                    return original(item, directory)
            return original(item, directory)
        with patch.object(evaluator, "_run_case", run_case):
            run = evaluator.run()
        classes = {r["case"]["id"]: r["classification"] for r in run["results"]}
        self.assertEqual(classes, {"wrong-state": "acceptance_failed", "no-answer": "blocked",
                                   "driver-crash": "driver_error"})
        crash = next(r for r in run["results"] if r["case"]["id"] == "driver-crash")
        self.assertIn("fixture exploded", crash["error"])
        self.assertEqual((run["summary"]["completed"], run["summary"]["completion_rate"]), (0, 0.0))

    def test_live_only_batch_reports_not_configured(self):
        live = [parse_case(case(id="live-one", driver="live_scheduler", human_responses=[]))]
        run = Evaluator(live, output_root=self.output).run()
        self.assertIsNone(run["summary"]["completion_rate"])
        self.assertEqual(run["summary"]["executed"], 0)
        self.assertEqual(run["mode"], "offline_fixture")
        self.assertFalse(run["benchmark_valid"])

    def test_summary_arithmetic(self):
        results = [
            {"status": "executed", "control": None, "classification": "completed", "duration_seconds": 2.0},
            {"status": "executed", "control": None, "classification": "task_failed", "duration_seconds": 4.0},
            {"status": "executed", "control": "negative", "classification": "acceptance_failed", "duration_seconds": 9.0},
            {"status": "not_configured", "control": None, "classification": "not_configured", "duration_seconds": None},
        ]
        summary = summarize(results)
        self.assertEqual((summary["executed"], summary["completed"], summary["completion_rate"]), (2, 1, 0.5))
        self.assertEqual((summary["mean_duration_seconds"], summary["total_duration_seconds"]), (3.0, 6.0))
        self.assertEqual(summary["classifications"]["task_failed"], 1)

    def test_memory_comparison_refuses_offline_runs(self):
        run = Evaluator([parse_case(case())], output_root=self.output).run()
        self.assertEqual(compare_memory(run, run)["status"], "not_comparable")
        on = {"mode": "live", "memory": "on", "results": [{"case": {"id": "a"}}],
              "summary": {"completion_rate": 1.0, "mean_duration_seconds": 3.0}}
        off = {"mode": "live", "memory": "off", "results": [{"case": {"id": "a"}}],
               "summary": {"completion_rate": 0.0, "mean_duration_seconds": 5.0}}
        self.assertEqual(compare_memory(on, off)["status"], "not_comparable")
        # Explicit synthetic comparison arithmetic, not an executed experiment.
        on["memory_exercised"] = True
        compared = compare_memory(on, off)
        self.assertEqual(compared["status"], "not_comparable")  # Legacy labels alone do not establish matched conditions.

    def test_absence_requires_missing_file_not_inspection_failure(self):
        item = parse_case(case(expected={"final_state": "succeeded", "artifacts": {"note.txt": "Hello\n"},
                                         "absent_artifacts": ["blocked.txt"]}))
        normal = Evaluator([item], output_root=self.output).run()
        self.assertTrue(normal["results"][0]["checks"]["absent:blocked.txt"])
        original = ArtifactInspector.read_file

        def unreadable(inspector, task, actor, path):
            if path == "blocked.txt":
                raise FileToolError("Unsafe or unreadable file")
            return original(inspector, task, actor, path)

        with patch.object(ArtifactInspector, "read_file", unreadable):
            result = Evaluator([item], output_root=self.output).run()["results"][0]
        self.assertFalse(result["checks"]["absent:blocked.txt"])
        self.assertEqual(result["classification"], "acceptance_failed")

    def test_live_memory_on_refuses_before_any_provider_call(self):
        with self.assertRaisesRegex(WorkflowError, "not implemented"):
            Evaluator([], output_root=self.output, live=object(), memory="on")
        offline = Evaluator([parse_case(case())], output_root=self.output, memory="on").run()
        self.assertEqual(offline["memory"], "not_exercised")
        self.assertFalse(offline["memory_exercised"])

    def test_cases_are_isolated(self):
        cases = [parse_case(case(id="first")), parse_case(case(id="second"))]
        run = Evaluator(cases, output_root=self.output).run()
        databases = sorted((self.output / run["run_id"]).glob("*/workflow.sqlite3"))
        self.assertEqual([p.parent.name for p in databases], ["first", "second"])


if __name__ == "__main__":
    unittest.main()
