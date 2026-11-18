"""Official input preparation preserves continuity without inventing results."""

import contextlib
import io
import json
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.core import WorkflowError
from agent_lab.evaluation.official import OfficialMidTestPlan, main
from agent_lab.evaluation.official_dataset import load_mid_test
from official_mid_fixture import README_SHA256, write_archive


TEMPLATE = Path(__file__).resolve().parents[1] / "evaluation/official/mid-test/plan.json"


class OfficialPlanTests(unittest.TestCase):
    def setUp(self):
        guard = patch("agent_lab.evaluation.official_dataset._README_SHA256", README_SHA256)
        guard.start()
        self.addCleanup(guard.stop)

    def copy_plan(self, directory, *, unresolved_html=False):
        destination = Path(directory) / "inputs"
        destination.mkdir()
        shutil.copyfile(TEMPLATE, destination / "plan.json")
        if unresolved_html:
            # The template records the format decision; keep the unresolved behaviour covered explicitly.
            value = json.loads((destination / "plan.json").read_text())
            value["operator_decisions"]["html_format_conflict"] = None
            (destination / "plan.json").write_text(json.dumps(value))
        archive = destination / "Mid_Test.zip"
        write_archive(archive)
        (destination / "manifest.json").write_text(json.dumps(load_mid_test(archive)))
        return destination / "plan.json"

    def test_inspection_has_all_tasks_and_no_runtime_or_credential_access(self):
        with tempfile.TemporaryDirectory() as temp:
            config = self.copy_plan(temp, unresolved_html=True)
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
            plan = OfficialMidTestPlan(self.copy_plan(temp))
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
            plan = OfficialMidTestPlan(self.copy_plan(temp))
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

    def test_unresolved_html_format_only_affects_the_html_task(self):
        with tempfile.TemporaryDirectory() as temp:
            config = self.copy_plan(temp, unresolved_html=True)
            report = OfficialMidTestPlan(config).inspect()
            self.assertIn("operator_decisions.html_format_conflict", report["unresolved_choices"])
            html_tasks = [task["id"] for task in report["tasks"]
                          if any("HTML" in blocker or "html_format_conflict" in blocker
                                 for blocker in task["blockers"])]
            self.assertEqual(html_tasks, ["scenario-3-task-2"])

    def test_recorded_template_decision_removes_only_the_html_blocker(self):
        with tempfile.TemporaryDirectory() as temp:
            decided = OfficialMidTestPlan(self.copy_plan(temp)).inspect()
        with tempfile.TemporaryDirectory() as temp:
            unresolved = OfficialMidTestPlan(self.copy_plan(temp, unresolved_html=True)).inspect()
        template = json.loads(TEMPLATE.read_text())
        decision = template["operator_decisions"].pop("html_format_conflict")
        self.assertIn("that task only", decision)
        self.assertIn("No tool, file permission or acceptance check is widened", decision)
        self.assertTrue(all(value is None for value in template["operator_decisions"].values()))
        self.assertEqual(set(unresolved["unresolved_choices"]) - set(decided["unresolved_choices"]),
                         {"operator_decisions.html_format_conflict"})
        for before, after in zip(unresolved["tasks"], decided["tasks"]):
            removed = [blocker for blocker in before["blockers"] if blocker not in after["blockers"]]
            self.assertEqual(after["blockers"], [b for b in before["blockers"] if b not in removed])
            self.assertEqual(len(removed), 1 if before["id"] == "scenario-3-task-2" else 0, before["id"])
            self.assertTrue(all("HTML" in blocker for blocker in removed))
        self.assertTrue(decided["tasks"][-1]["blockers"])  # Model, budget and protocol choices stay open.
        self.assertNotEqual(decided["plan_sha256"], unresolved["plan_sha256"])

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
            config = Path(temp) / "plan.json"
            shutil.copyfile(TEMPLATE, config)
            archive = config.with_name("Mid_Test.zip")
            write_archive(archive)
            manifest = config.with_name("manifest.json")
            self.assertEqual(main(["import", "--archive", str(archive), "--output", str(manifest)]), 0)
            self.assertEqual(json.loads(manifest.read_text()), OfficialMidTestPlan(config).dataset)
            self.assertEqual(stat.S_IMODE(manifest.stat().st_mode), 0o600)
            stdout.seek(0); stdout.truncate(0)
            self.assertEqual(main(["inspect", "--config", str(config)]), 0)
            report = json.loads(stdout.getvalue())
            self.assertEqual(report["counts"]["expected_tasks"], 6)
            stdout.seek(0); stdout.truncate(0)
            self.assertEqual(main(["prepare", "--config", str(config), "--plan-sha256", report["plan_sha256"], "--output", str(Path(temp) / "run")]), 0)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                main(["import", "--archive", str(archive), "--output", str(manifest)])
            self.assertEqual(raised.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
