"""Audit real offline batches and adversarial saved records; no live calls."""

import contextlib
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.evaluation import Evaluator, load_cases, parse_case, summarize
from agent_lab.evaluation.manifest import digest
from agent_lab.evaluation.run_audit import audit_run, main, MAX_BYTES
from agent_lab.runtime import LiveConfig

CASES = Path(__file__).resolve().parents[1] / "evaluation" / "dev"


class RunAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        cls.original = Evaluator(load_cases(CASES), output_root=cls.fixture.name).run()
        cls.original_progress = json.loads((Path(cls.fixture.name) / cls.original["run_id"] /
                                           "run-progress.json").read_text())

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name)
        self.run = copy.deepcopy(self.original)
        self.progress = copy.deepcopy(self.original_progress)
        self.save()

    def save(self, *, checkpoint=True, final=True):
        for name, enabled, data in (("results.json", final, self.run),
                                    ("run-progress.json", checkpoint, self.progress)):
            path = self.path / name
            if enabled:
                path.write_text(json.dumps(data))
            else:
                path.unlink(missing_ok=True)

    def invalid(self, code=None):
        report = audit_run(self.path)
        self.assertEqual(report["status"], "invalid", report)
        if code:
            self.assertIn(code, {item["code"] for item in report["findings"]}, report)
        return report

    def test_real_batch_preserves_denominators_rejection_and_unknown(self):
        report = audit_run(self.path)
        self.assertEqual(report["status"], "consistent", report)
        self.assertEqual(report["summary"], self.run["summary"])
        self.assertEqual(report["summary"]["completed"], 4)
        self.assertEqual(report["summary"]["goals_verified_completed"], 3)
        self.assertEqual(report["summary"]["negative_controls_detected"], 5)
        self.assertEqual(report["summary"]["not_configured"], 1)
        self.assertFalse(report["authenticity_verified"])
        self.assertFalse(report["benchmark_valid"])
        self.assertFalse(report["source_usage_verified"])
        self.assertEqual(report["model_calls"], 0)

    def test_audit_is_read_only_and_does_not_create_runtime_or_read_credentials(self):
        before = {path.name: path.read_bytes() for path in self.path.iterdir()}
        with patch("agent_lab.evaluation.harness._Session", side_effect=AssertionError("runtime")), \
                patch.dict(os.environ, {"HKGAI_API_KEY": "private-test-secret"}), \
                patch("os.getenv", side_effect=AssertionError("environment")):
            report = audit_run(self.path)
        self.assertEqual(report["status"], "consistent")
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.path.iterdir()})
        self.assertNotIn("private-test-secret", json.dumps(report))

    def test_missing_and_duplicate_result_cases(self):
        for change in (lambda rows: rows.pop(), lambda rows: rows.append(copy.deepcopy(rows[0]))):
            with self.subTest(change=change):
                self.run = copy.deepcopy(self.original)
                change(self.run["results"])
                self.run["summary"] = summarize(self.run["results"])
                self.save(checkpoint=False)
                self.invalid()

    def test_manifest_fingerprint_and_case_content(self):
        self.run["manifest"]["code_sha256"] = "0" * 64
        self.save(checkpoint=False)
        self.invalid("manifest_fingerprint")
        self.run = copy.deepcopy(self.original)
        self.run["results"][0]["case"]["goal"] = "different task"
        self.save(checkpoint=False)
        self.invalid("case_content")

    def test_input_content_is_bound_to_manifest(self):
        case = parse_case({"id": "input-case", "title": "Input", "goal": "Read supplied file",
                           "driver": "live_scheduler", "inputs": {"input.txt": "original\n"},
                           "expected": {"final_state": "succeeded"}})
        run = Evaluator([case], output_root=self.path / "inputs").run()
        directory = self.path / "inputs" / run["run_id"]
        self.assertEqual(audit_run(directory)["status"], "consistent")
        run["results"][0]["case"]["inputs"]["input.txt"] = "changed\n"
        (directory / "results.json").write_text(json.dumps(run))
        self.assertEqual(audit_run(directory)["status"], "invalid")

    def test_summary_cannot_be_edited_or_boolean_coerced(self):
        for value in (999, True):
            with self.subTest(value=value):
                self.run["summary"]["completion_rate"] = value
                self.save(checkpoint=False)
                self.invalid("summary_mismatch")

    def test_deleted_failed_check_and_reclassified_control_are_rejected(self):
        row = next(row for row in self.run["results"] if row["failed_checks"])
        row["checks"].pop(row["failed_checks"][0])
        row["failed_checks"] = []
        row["classification"] = "completed"
        self.run["summary"] = summarize(self.run["results"])
        self.save(checkpoint=False)
        self.invalid("check_inventory")

    def test_failed_check_list_classification_and_derived_checks(self):
        mutations = [lambda row: row.update(failed_checks=["invented"]),
                     lambda row: row.update(classification="timeout"),
                     lambda row: row["checks"].update(final_state=False),
                     lambda row: row["checks"].update(task_count=1)]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.run = copy.deepcopy(self.original)
                mutate(self.run["results"][0])
                self.save(checkpoint=False)
                self.invalid()

    def test_task_tree_timing_state_and_totals(self):
        mutations = [lambda task, workflow: task.update(parent=task["task_id"]),
                     lambda task, workflow: task.update(verified_success=1),
                     lambda task, workflow: task.update(final_duration_seconds=None),
                     lambda task, workflow: task.update(elapsed_seconds=-1),
                     lambda task, workflow: workflow.update(tasks=True),
                     lambda task, workflow: workflow.update(task_states={"succeeded": 100})]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.run = copy.deepcopy(self.original)
                workflow = self.run["results"][0]["workflow"]
                mutate(workflow["task_outcomes"][0], workflow)
                self.save(checkpoint=False)
                self.invalid()

    def test_valid_driver_failure_and_blocked_task_remain_observed(self):
        case = parse_case({"id": "blocked-task", "title": "Blocked", "goal": "Wait for answer",
                           "driver": "offline_delegation", "expected": {"final_state": "succeeded"}})
        for crash in (False, True):
            with self.subTest(crash=crash):
                with patch("agent_lab.offline_scenarios.start", side_effect=RuntimeError("private failure")) if crash \
                        else contextlib.nullcontext():
                    run = Evaluator([case], output_root=self.path / "failures").run()
                report = audit_run(self.path / "failures" / run["run_id"])
                self.assertEqual(report["status"], "consistent", report)
                self.assertEqual(report["summary"]["goal_completion_rate"], 0)
                self.assertEqual(report["summary"]["goals_finalized"], 0)
                self.assertNotIn("private failure", json.dumps(report))

    def test_real_interruption_preserves_returned_active_and_unstarted(self):
        evaluator = Evaluator(load_cases(CASES), output_root=self.path / "interrupted")
        original = evaluator._run_case
        calls = []

        def stop(case, directory):
            calls.append(case.id)
            if len(calls) == 2:
                raise KeyboardInterrupt()
            return original(case, directory)

        with patch.object(evaluator, "_run_case", side_effect=stop):
            with self.assertRaises(KeyboardInterrupt):
                evaluator.run()
        directory = next((self.path / "interrupted").iterdir())
        report = audit_run(directory)
        self.assertEqual(report["status"], "incomplete", report)
        self.assertEqual(report["returned_case_ids"], calls[:1])
        self.assertEqual(report["active_case_id"], calls[1])
        self.assertEqual(len(report["not_started_case_ids"]), len(self.run["results"]) - 2)
        self.assertFalse((directory / "results.json").exists())

    def test_checkpoint_start_and_export_interruption(self):
        selected = self.progress["selected_case_ids"]
        self.progress.update(results=[], status="incomplete", active_case_id=selected[0],
                             not_started_case_ids=selected[1:])
        self.progress.pop("ended")
        self.save(final=False)
        self.assertEqual(audit_run(self.path)["status"], "incomplete")
        self.progress = copy.deepcopy(self.original_progress)
        self.progress["status"] = "incomplete"
        self.progress.pop("ended")
        self.save()
        self.assertEqual(audit_run(self.path)["status"], "incomplete")
        self.save(final=False)
        self.assertEqual(audit_run(self.path)["status"], "incomplete")

    def test_checkpoint_order_active_remaining_and_cross_file_mismatch(self):
        changes = [lambda p: p["results"].reverse(),
                   lambda p: p.update(active_case_id=p["selected_case_ids"][0]),
                   lambda p: p.update(not_started_case_ids=[p["selected_case_ids"][0]]),
                   lambda p: p.update(run_id="different-run")]
        for change in changes:
            with self.subTest(change=change):
                self.progress = copy.deepcopy(self.original_progress)
                change(self.progress)
                self.save()
                self.invalid()

    def test_report_only_and_custom_execution_order(self):
        self.run["results"].reverse()
        self.progress["results"].reverse()
        self.progress["selected_case_ids"].reverse()
        self.run["summary"] = summarize(self.run["results"])
        self.save()
        self.assertEqual(audit_run(self.path)["status"], "consistent")
        self.save(checkpoint=False)
        self.assertEqual(audit_run(self.path)["status"], "consistent")

    def test_offline_memory_switch_does_not_claim_exercised_memory(self):
        self.run["manifest"]["condition"]["memory"] = "on"
        self.run["manifest_sha256"] = digest(self.run["manifest"])
        self.save(checkpoint=False)
        self.assertEqual(audit_run(self.path)["status"], "consistent")

    def test_protocol_labels_and_root_evidence_cannot_contradict_outcomes(self):
        for mutate in (lambda run: run["manifest"]["initial_memory"].update(seed="old-history"),
                       lambda run: run["manifest"]["interventions"].update(include_wait_in_elapsed=False),
                       lambda run: run["results"][0]["workflow"].update(evidence={"error": "failure"}),
                       lambda run: run["results"][0]["workflow"]["task_outcomes"][0].update(verified_success=False),
                       lambda run: (run["results"][0]["workflow"].update(evidence=None),
                                    run["results"][0]["workflow"]["task_outcomes"][0].update(verified_success=False))):
            with self.subTest(mutate=mutate):
                self.run = copy.deepcopy(self.original)
                mutate(self.run)
                self.run["manifest_sha256"] = digest(self.run["manifest"])
                self.run["summary"] = summarize(self.run["results"])
                self.save(checkpoint=False)
                self.invalid()

    def test_human_checks_require_matching_recorded_requests(self):
        for field in ("human_interventions", "human_request_checks"):
            with self.subTest(field=field):
                self.run = copy.deepcopy(self.original)
                self.run["results"][0]["workflow"][field] = []
                self.save(checkpoint=False)
                self.invalid()

    def test_finite_inputs_cannot_overflow_progress_summary(self):
        self.progress["status"] = "incomplete"
        for row in self.progress["results"]:
            if row["workflow"] is not None:
                for task in row["workflow"]["task_outcomes"]:
                    task["human_wait_seconds"] = 1e308
        self.save(final=False)
        self.invalid("summary_nonfinite")
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["--run", str(self.path)]), 2)
        json.loads(output.getvalue())

    def test_synthetic_live_record_preserves_unknown_usage_and_rejects_memory_labels(self):
        case = parse_case({"id": "live-shaped", "title": "Live-shaped", "goal": "Deliver note",
                           "driver": "live_scheduler", "expected": {"final_state": "succeeded",
                                                                        "artifacts": {"note.txt": "Hello\n"}}})

        def synthetic_driver(case, session, live):
            # Real backend state, fixed script: no provider call or capability claim.
            chat = session.workflow.create_chat("private", ["evaluator", "writer"])
            root = session.workflow.create_task(chat, "evaluator", "writer", case.goal)
            session.workflow.start_task(root, "writer")
            session.files.create_text(root, "writer", "note.txt", "Hello\n")
            session.workflow.finish_task(root, "writer", verifier=session.files.text_verifier(
                root, "writer", {"note.txt": "Hello\n"}))
            return root, {"state": "completed"}

        with patch("agent_lab.evaluation.harness._drive_live", side_effect=synthetic_driver):
            run = Evaluator([case], output_root=self.path / "synthetic", live=LiveConfig(
                "synthetic-model", "unused-private-key")).run()
        directory = self.path / "synthetic" / run["run_id"]
        report = audit_run(directory)
        self.assertEqual(report["status"], "consistent", report)
        self.assertIsNone(run["model_calls"])
        self.assertFalse(report["source_usage_verified"])
        (directory / "run-progress.json").unlink()
        run["manifest"]["condition"]["memory"] = "on"
        run["memory"] = "on"
        run["manifest_sha256"] = digest(run["manifest"])
        (directory / "results.json").write_text(json.dumps(run))
        self.assertEqual(audit_run(directory)["status"], "invalid")

    def test_captured_nonfresh_memory_failure_counts_remain_visible(self):
        row = self.run["results"][0]
        row.update(classification="driver_error", workflow=None, checks={}, failed_checks=[],
                   error="Fresh-memory check failed", initial_memory={
                       "lessons": 1, "lesson_sources": 0, "lesson_uses": 0, "lesson_retrievals": 0})
        self.run["summary"] = summarize(self.run["results"])
        self.save(checkpoint=False)
        self.assertEqual(audit_run(self.path)["status"], "consistent")

    def test_strict_json_limits_unsafe_file_types_and_missing_reports(self):
        self.save(checkpoint=False)
        path = self.path / "results.json"
        for raw in ('{"run_id":"a","run_id":"b"}', '{"private":NaN}', '{"private":1e999}', '{'):
            with self.subTest(raw=raw):
                path.write_text(raw)
                self.invalid("invalid_json")
        with path.open("wb") as stream:
            stream.truncate(MAX_BYTES + 1)
        self.invalid("unsupported_file")
        path.unlink()
        self.invalid("missing_reports")
        target = self.path / "private.json"
        target.write_text("private-test-secret")
        path.symlink_to(target)
        self.invalid("unreadable_file")
        path.unlink()
        os.mkfifo(path)
        self.invalid("unsupported_file")

    def test_malformed_shapes_are_sanitized_and_cli_exits(self):
        self.run["results"][0]["notes"] = "private-test-secret"
        self.save()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["--run", str(self.path)]), 2)  # cross-file mismatch
        self.assertNotIn("private-test-secret", output.getvalue())
        self.run = copy.deepcopy(self.original)
        self.save()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["--run", str(self.path), "--format", "markdown"]), 0)
        self.assertIn("Internal consistency only", output.getvalue())
        self.save(final=False)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--run", str(self.path)]), 1)
        for value in ([], {}, {"purpose": "official_mid_preparation", "tasks": []},
                      {"manifest": "private-test-secret"}):
            with self.subTest(value=value):
                (self.path / "results.json").write_text(json.dumps(value))
                report = self.invalid()
                self.assertNotIn("private-test-secret", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
