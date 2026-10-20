"""Course metrics and matched-condition checks; comparisons below are synthetic."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

from agent_lab.core import WorkflowError
from agent_lab.evaluation import Evaluator, compare_memory, load_cases, parse_case, summarize
from agent_lab.evaluation.harness import HUMAN, _Session, _checks
from agent_lab.evaluation.manifest import build_manifest, digest
from agent_lab.runtime import LiveConfig

CASES = Path(__file__).resolve().parents[1] / "evaluation" / "dev"


def live_case(**changes):
    return parse_case({"id": "matched-case", "title": "Matched", "goal": "Deliver note.txt",
        "driver": "live_scheduler", "expected": {"final_state": "succeeded", "artifacts": {"note.txt": "Hello\n"}}, **changes})


def synthetic_pair():
    """Only comparison arithmetic/schema; no model invocation or performance claim."""
    cases = [live_case()]
    live = LiveConfig("test-model", "unused-secret-key")
    pair = []
    for memory, succeeded in (("on", True), ("off", False)):
        manifest = build_manifest(cases, live, memory)
        task = {"task_id": "root", "parent": None, "state": "succeeded" if succeeded else "failed",
                "verified_success": succeeded, "elapsed_seconds": 3.0, "final_duration_seconds": 3.0, "human_wait_seconds": 1.0}
        results = [{"case": cases[0].summary(), "control": None, "status": "executed", "mode": "live",
                    "classification": "completed" if succeeded else "task_failed", "duration_seconds": 4.0,
                    "workflow": {"task_outcomes": [task], "observed_models": ["served-model-v1"]},
                    "initial_memory": {"lessons": 0, "lesson_sources": 0, "lesson_uses": 0, "lesson_retrievals": 0}}]
        pair.append({"mode": "live", "memory": memory, "memory_exercised": succeeded,
                     "results": results, "manifest": manifest, "manifest_sha256": digest(manifest),
                     "summary": summarize(results)})
    return pair


class EvaluationReportingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def test_correct_rejection_is_acceptance_not_a_completed_goal(self):
        run = Evaluator(load_cases(CASES), output_root=self.path).run()
        summary = run["summary"]
        self.assertEqual((summary["expected"], summary["executed"], summary["completed"]), (5, 4, 4))
        self.assertEqual(summary["acceptance_pass_rate"], 1.0)
        self.assertEqual((summary["goals_verified_completed"], summary["goal_completion_rate"]), (3, .75))
        self.assertEqual(summary["goal_states"]["cancelled"], 1)
        self.assertEqual((summary["subtasks_observed"], summary["subtasks_verified_completed"]), (2, 2))
        self.assertEqual(summary["goals_finalized"], 4)
        self.assertEqual(summary["goals_missing_evidence"], 0)
        self.assertEqual(run["model_calls"], 0)
        self.assertFalse(run["benchmark_valid"])
        report = (self.path / run["run_id"] / "report.md").read_text()
        self.assertIn("Contract acceptance rate", report)
        self.assertIn("Goal completion rate", report)
        self.assertIn("Verified subtasks", report)
        self.assertEqual(run["manifest_sha256"], digest(run["manifest"]))

    def test_final_timing_comes_from_assignment_and_includes_human_wait(self):
        session = _Session(self.path, "timing")
        try:
            tick = [100.0]
            session.workflow.clock = lambda: tick[0]
            chat = session.workflow.create_chat("private", [HUMAN, "writer"])
            root = session.workflow.create_task(chat, HUMAN, "writer", "Deliver note.txt")
            session.workflow.start_task(root, "writer")
            tick[0] = 102
            request = session.workflow.ask_human(root, "writer", HUMAN, "Which text?")
            tick[0] = 109
            session.workflow.respond(request, HUMAN, answer="Hello")
            session.files.create_text(root, "writer", "note.txt", "Hello\n")
            tick[0] = 112
            session.workflow.finish_task(root, "writer", verifier=session.files.text_verifier(root, "writer", {"note.txt": "Hello\n"}))
            _, state = _checks(live_case(), session, root, duration=.1)
            task = state["task_outcomes"][0]
            self.assertEqual((task["elapsed_seconds"], task["final_duration_seconds"], task["human_wait_seconds"]), (12, 12, 7))
            self.assertEqual(state["human_interventions"][0]["response_sha256"], digest("Hello"))
            short = replace(live_case(), expected=replace(live_case().expected, max_seconds=5))
            checks, _ = _checks(short, session, root, duration=.1)
            self.assertFalse(checks["within_time"])
        finally:
            session.close()

    def test_blocked_goal_has_observed_elapsed_time_and_no_final_duration(self):
        case = parse_case({"id": "blocked-case", "title": "Blocked", "goal": "Deliver note",
            "driver": "offline_delegation", "expected": {"final_state": "succeeded"}})
        run = Evaluator([case], output_root=self.path).run()
        summary = run["summary"]
        self.assertEqual((summary["blocked"], summary["goals_finalized"], summary["goal_completion_rate"]), (1, 0, 0))
        self.assertIsNone(summary["mean_assignment_to_final_seconds"])
        self.assertGreaterEqual(summary["mean_observed_goal_elapsed_seconds"], 0)

    def test_missing_workflow_evidence_cannot_count_as_goal_success(self):
        summary = summarize([{"status": "executed", "control": None, "classification": "driver_error", "duration_seconds": 1}])
        self.assertEqual((summary["goals_missing_evidence"], summary["goal_completion_rate"]), (1, 0))
        self.assertEqual(summary["subtasks_observed"], 0)
        self.assertIsNone(summary["subtask_completion_rate"])

    def test_case_initialization_failure_is_reported_and_counted(self):
        case = parse_case({"id": "setup-error", "title": "Setup", "goal": "Deliver note", "driver": "offline_delegation",
                           "expected": {"final_state": "succeeded"}})
        with patch("agent_lab.evaluation.harness._Session", side_effect=RuntimeError("setup failed")):
            run = Evaluator([case], output_root=self.path).run()
        self.assertEqual(run["results"][0]["classification"], "driver_error")
        self.assertEqual((run["summary"]["executed"], run["summary"]["goals_missing_evidence"]), (1, 1))
        self.assertEqual(run["summary"]["goal_completion_rate"], 0)

    def test_synthetic_matched_pair_and_failures_are_retained(self):
        on, off = synthetic_pair()
        compared = compare_memory(on, off)
        self.assertEqual(compared["status"], "compared", compared)
        self.assertEqual(compared["goal_completion_rate"], {"on": 1.0, "off": 0.0})
        self.assertIn("no causal claim", compared["note"])
        # Do not trust an edited summary over persisted per-case result evidence.
        off["summary"]["goal_completion_rate"] = 1.0
        self.assertEqual(compare_memory(on, off)["goal_completion_rate"]["off"], 0.0)

    def test_same_case_ids_with_changed_conditions_are_rejected(self):
        on, original = synthetic_pair()
        paths = [("cases", 0, "goal"), ("cases", 0, "expected", "artifacts", "note.txt"),
                 ("runtime", "model"), ("runtime", "provider"), ("runtime", "roles", "writer", "limits", "model_attempts"),
                 ("runtime", "roles", "writer", "instructions"), ("runtime", "roles", "writer", "tools"),
                 ("prompt_sha256",), ("tools_sha256",), ("code_sha256",), ("interventions", "live")]
        for path in paths:
            with self.subTest(path=path):
                off = copy.deepcopy(original)
                target = off["manifest"]
                for key in path[:-1]:
                    target = target[key]
                old = target[path[-1]]
                target[path[-1]] = old + ["delete_text"] if isinstance(old, list) else (
                    old + 1 if type(old) is int else ("a" * 64 if str(path[-1]).endswith("sha256") else str(old) + "-changed"))
                off["manifest_sha256"] = digest(off["manifest"])
                self.assertEqual(compare_memory(on, off)["status"], "not_comparable")

    def test_missing_corrupt_initial_or_observed_model_evidence_is_rejected(self):
        on, original = synthetic_pair()
        mutations = [lambda r: r.pop("manifest"), lambda r: r.update(manifest_sha256="incorrect"),
                     lambda r: r["results"][0].pop("initial_memory"),
                     lambda r: r["results"][0]["initial_memory"].update(lessons=1),
                     lambda r: r["results"][0]["workflow"].update(observed_models=[]),
                     lambda r: r["results"][0]["workflow"].update(observed_models=["different-model"]),
                     lambda r: r["results"][0]["workflow"].update(observed_models="different-model"),
                     lambda r: r["results"][0]["workflow"]["task_outcomes"][0].update(verified_success="false"),
                     lambda r: r["results"][0]["workflow"]["task_outcomes"][0].update(final_duration_seconds=float("nan")),
                     lambda r: r["results"].append(copy.deepcopy(r["results"][0])),
                     lambda r: r["results"][0].update(status="not_configured"),
                     lambda r: r["results"][0]["case"].update(goal="Different executed task"),
                     lambda r: r["results"][0].update(control="negative"),
                     lambda r: r["results"][0].update(duration_seconds=float("nan"))]
        for mutate in mutations:
            off = copy.deepcopy(original)
            mutate(off)
            self.assertEqual(compare_memory(on, off)["status"], "not_comparable")
        self.assertEqual(compare_memory(None, original)["status"], "not_comparable")

    def test_manifest_uses_content_not_location_and_excludes_credentials(self):
        case = live_case()
        live = LiveConfig("test-model", "unused-secret-key")
        first = build_manifest([case], live, "off")
        relocated = copy.deepcopy(case)
        object.__setattr__(relocated, "source", "another-file.json")
        self.assertEqual(first, build_manifest([relocated], live, "off"))
        self.assertNotIn(live.api_key, json.dumps(first))

    def test_empty_or_duplicate_case_selection_is_rejected_before_output(self):
        case = live_case()
        for cases, selected in (([], None), ([case], []), ([case, case], None), ([case], [case.id, case.id])):
            output = self.path / "not-created"
            with self.assertRaises(WorkflowError):
                Evaluator(cases, output_root=output).run(selected)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
