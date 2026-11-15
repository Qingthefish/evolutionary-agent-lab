"""Official input preparation preserves continuity without inventing results."""

import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.core import WorkflowError
from agent_lab.evaluation.official import DEFAULT_CONFIG, OfficialMidTestPlan, main


class OfficialPlanTests(unittest.TestCase):
    def copy_plan(self, directory):
        destination = Path(directory) / "inputs"
        shutil.copytree(DEFAULT_CONFIG.parent, destination)
        return destination / "plan.json"

    def test_inspection_has_all_tasks_and_no_runtime_or_credential_access(self):
        with tempfile.TemporaryDirectory() as temp:
            config = self.copy_plan(temp)
            before = sorted(str(path.relative_to(temp)) for path in Path(temp).rglob("*"))
            with patch("agent_lab.deepseek.DeepSeekHTTP.__call__", side_effect=AssertionError("no model")), \
                 patch("agent_lab.hkgai.HKGAIHTTP.__call__", side_effect=AssertionError("no model")), \
                 patch("os.environ", {"COURSE_HKGAI_API_KEY": "must-never-be-read-or-copied"}):
                plan = OfficialMidTestPlan(config)
                report = plan.inspect()
            after = sorted(str(path.relative_to(temp)) for path in Path(temp).rglob("*"))
            self.assertEqual(before, after)
            self.assertEqual(report["counts"], {"scenarios": 3, "roles": 12, "expected_tasks": 6, "executed_tasks": 0, "not_run_tasks": 6})
            self.assertEqual(report["model_calls"], 0)
            self.assertFalse(report["benchmark_valid"])
            self.assertFalse(report["execution_supported"])
            self.assertTrue(all(row["status"] == "not_run" for row in report["tasks"]))
            self.assertNotIn("must-never-be-read-or-copied", json.dumps(plan.conditions))
            self.assertEqual(report["tasks"][-1]["depends_on"], "scenario-3-task-1")
            self.assertTrue(any("HTML" in value for value in report["tasks"][-1]["blockers"]))

    def test_preparation_exports_source_roles_sequence_and_unknown_outcomes(self):
        with tempfile.TemporaryDirectory() as temp:
            plan = OfficialMidTestPlan()
            output = Path(temp) / "prepared"
            plan.prepare(output, plan_sha256=plan.sha256)
            progress = json.loads((output / "run-progress.json").read_text())
            self.assertEqual(len(progress["expected_task_ids"]), 6)
            self.assertEqual([row["id"] for row in progress["tasks"]], progress["expected_task_ids"])
            self.assertFalse(progress["execution_started"])
            for row in progress["tasks"]:
                self.assertEqual(row["status"], "not_run")
                self.assertIsNone(row["completion_evidence"])
                self.assertIsNone(row["total_elapsed_seconds"])
                self.assertIsNone(row["usage"])
            for original in plan.dataset["scenarios"]:
                scenario = json.loads((output / original["id"] / "scenario.json").read_text())
                self.assertEqual(scenario["scenario"], original)
                self.assertIn("same group", scenario["session_protocol"]["task_2"])
                self.assertEqual(scenario["session_protocol"]["task_order"], [task["id"] for task in original["tasks"]])

    def test_stale_plan_and_existing_output_are_refused_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "run"
            plan = OfficialMidTestPlan()
            with self.assertRaises(WorkflowError):
                plan.prepare(output, plan_sha256="0" * 64)
            self.assertFalse(output.exists())
            plan.prepare(output, plan_sha256=plan.sha256)
            original = (output / "run-progress.json").read_bytes()
            with self.assertRaises(FileExistsError):
                plan.prepare(output, plan_sha256=plan.sha256)
            self.assertEqual((output / "run-progress.json").read_bytes(), original)

    def test_changed_archive_or_reviewed_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            config = self.copy_plan(temp)
            manifest = config.with_name("manifest.json")
            value = json.loads(manifest.read_text())
            value["scenarios"][0]["tasks"][0]["prompt"] = "altered goal"
            manifest.write_text(json.dumps(value))
            with self.assertRaisesRegex(WorkflowError, "differs"):
                OfficialMidTestPlan(config)

    def test_operator_choices_affect_fingerprint_but_do_not_become_official_rules(self):
        with tempfile.TemporaryDirectory() as temp:
            config = self.copy_plan(temp)
            before = OfficialMidTestPlan(config)
            value = json.loads(config.read_text())
            value["runtime"]["per_scenario_model_attempts"] = 12
            value["operator_decisions"]["timing_rule"] = "Proposed: retain total time and human wait separately"
            config.write_text(json.dumps(value))
            after = OfficialMidTestPlan(config)
            self.assertNotEqual(before.sha256, after.sha256)
            self.assertFalse(after.inspect()["operator_choices_are_official_rules"])
            self.assertFalse(after.inspect()["execution_supported"])

    def test_mutated_object_or_changed_source_cannot_export_with_old_fingerprint(self):
        with tempfile.TemporaryDirectory() as temp:
            config = self.copy_plan(temp)
            plan = OfficialMidTestPlan(config)
            plan.dataset["scenarios"][0]["tasks"][0]["prompt"] = "unreviewed change"
            output = Path(temp) / "mutated"
            with self.assertRaises(WorkflowError):
                plan.prepare(output, plan_sha256=plan.sha256)
            self.assertFalse(output.exists())
            plan = OfficialMidTestPlan(config)
            value = json.loads(config.read_text())
            value["runtime"]["model"] = "changed-after-inspection"
            config.write_text(json.dumps(value))
            with self.assertRaises(WorkflowError):
                plan.prepare(output, plan_sha256=plan.sha256)
            self.assertFalse(output.exists())

    def test_browseable_source_copies_match_every_original_document(self):
        from zipfile import ZipFile
        with ZipFile(DEFAULT_CONFIG.with_name("Mid_Test.zip")) as archive:
            expected = [item for item in archive.infolist() if not item.is_dir() and not item.filename.startswith("__MACOSX/")]
            self.assertEqual(len(expected), 10)
            for item in expected:
                self.assertEqual((DEFAULT_CONFIG.parent / "source" / item.filename).read_bytes(), archive.read(item))

    def test_unknown_fields_provider_substitution_and_literal_credentials_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            config = self.copy_plan(temp)
            original = json.loads(config.read_text())
            changes = [("runtime", "provider", "openai"), ("runtime", "api_key_env", "sk-actual-key"),
                       ("runtime", "per_scenario_model_attempts", True), (None, "approval", "auto")]
            for section, key, value in changes:
                data = json.loads(json.dumps(original))
                (data[section] if section else data)[key] = value
                config.write_text(json.dumps(data))
                with self.subTest(key=key), self.assertRaises(WorkflowError):
                    OfficialMidTestPlan(config)

    def test_cli_import_inspect_prepare_and_existing_manifest_refusal(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()) as stdout:
            archive = DEFAULT_CONFIG.with_name("Mid_Test.zip")
            manifest = Path(temp) / "manifest.json"
            self.assertEqual(main(["import", "--archive", str(archive), "--output", str(manifest)]), 0)
            self.assertEqual(json.loads(manifest.read_text()), OfficialMidTestPlan().dataset)
            stdout.seek(0); stdout.truncate(0)
            self.assertEqual(main(["inspect"]), 0)
            report = json.loads(stdout.getvalue())
            self.assertEqual(report["counts"]["expected_tasks"], 6)
            stdout.seek(0); stdout.truncate(0)
            self.assertEqual(main(["prepare", "--plan-sha256", report["plan_sha256"], "--output", str(Path(temp) / "run")]), 0)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                main(["import", "--archive", str(archive), "--output", str(manifest)])
            self.assertEqual(raised.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
