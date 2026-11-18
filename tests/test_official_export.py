"""The scenario export is complete, clearly labelled and leaves its source untouched.

The exported scenario is a synthetic fixture with scripted replies and a
scripted stand-in requester. It is plumbing evidence, never a live result.
"""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_lab import budget
from agent_lab.core import Workflow
from agent_lab.deepseek import DeepSeekClient
from agent_lab.evaluation import official_export
from agent_lab.evaluation.official import OfficialMidTestPlan
from agent_lab.evaluation.official_dataset import load_mid_test
from agent_lab.evaluation.official_live import review_proposal
from agent_lab.evaluation.official_session import OfficialScenarioSession
from agent_lab.files import FileTools
from agent_lab.hkgai import HKGAIHTTP
from agent_lab.scheduler import MultiAgentScheduler, Role
from official_mid_fixture import README_SHA256, write_archive

TEMPLATE = Path(__file__).resolve().parents[1] / "evaluation/official/mid-test/plan.json"
KEY = "synthetic-sentinel-api-key-value"
DRAFT = "Synthetic fixture draft\n"


def reply(calls=None, reason=None):
    message = {"role": "assistant", "content": None if calls else "Synthetic proposal."}
    if calls:
        message["tool_calls"] = [{"id": f"fixture-{name}", "type": "function",
                                  "function": {"name": name, "arguments": json.dumps(arguments)}}
                                 for name, arguments in calls]
    return json.dumps({"id": "fixture", "model": "synthetic-export",
        "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
        "choices": [{"message": message, "finish_reason": reason or ("tool_calls" if calls else "stop")}]}).encode()


def snapshot(directory):
    return {str(path.relative_to(directory)): (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
            for path in sorted(Path(directory).rglob("*")) if path.is_file()}


class ScenarioExport(unittest.TestCase):
    def setUp(self):
        for guard in (patch("agent_lab.evaluation.official_dataset._README_SHA256", README_SHA256),
                      patch.dict(os.environ, {"COURSE_HKGAI_API_KEY": KEY}),
                      patch.object(HKGAIHTTP, "__call__", side_effect=AssertionError("No provider request"))):
            guard.start()
            self.addCleanup(guard.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        inputs = self.root / "inputs"
        inputs.mkdir()
        (inputs / "plan.json").write_text(TEMPLATE.read_text())
        write_archive(inputs / "Mid_Test.zip")
        (inputs / "manifest.json").write_text(json.dumps(load_mid_test(inputs / "Mid_Test.zip")))
        self.config = inputs / "plan.json"
        self.state = self.root / "state"
        self.state.mkdir()

    def build(self, *, run=True):
        """One failed Task 1 with a question, a rejected proposal and a file; Task 2 is not posted."""
        plan = OfficialMidTestPlan(self.config)
        workflow = Workflow(self.state / "workflow.sqlite3")
        files = FileTools(workflow, self.state / "files")
        try:
            session = OfficialScenarioSession.initialize(workflow, plan, scenario="software-engineering",
                                                         human="requester", plan_sha256=plan.sha256)
            if not run:
                return plan, None
            root = session.post(1, "lead")["root"]
            replies = [reply([("create_text", {"path": "notes/draft.txt", "content": DRAFT}),
                              ("ask_human", {"prompt": "Synthetic fixture question?"})]),
                       reply(),
                       reply([("create_text", {"path": "late.txt", "content": "never written"})], reason="length")]
            roles = {role["id"]: Role(role["prompt"], ("ask_human", "create_text", "post_message"))
                     for role in session.scenario["roles"]}
            scheduler = MultiAgentScheduler(workflow, files, root, human="requester", roles=roles,
                clients={role: DeepSeekClient("synthetic-export", lambda payload: replies.pop(0)) for role in roles},
                mode="offline_fixture", constraints=[], acceptance_id="fixture-export",
                verifier_factory=lambda task: None, limits=budget.TreeLimits(model_attempts=6))
            scheduler.run()
            request = workflow.db.execute("SELECT id FROM requests WHERE task=?", (root,)).fetchone()[0]
            workflow.respond(request, "requester", answer="Synthetic fixture answer")
            self.assertEqual(scheduler.run()["needs"][0]["kind"], "independent_verification")
            review_proposal(scheduler, root, "reject", "Synthetic fixture review: draft is incomplete")
            self.assertEqual(scheduler.run()["task_state"], "failed")
            return plan, root
        finally:
            files.close()
            workflow.close()

    def export(self, output, *, fails=False):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = official_export.main(["--config", str(self.config), "--state-dir", str(self.state),
                                             "--output", str(output)])
            except SystemExit as stop:
                code = stop.code
        self.assertEqual(code != 0, fails, err.getvalue())
        return err.getvalue() if fails else json.loads(out.getvalue())

    def test_export_holds_the_full_record_and_leaves_the_state_untouched(self):
        plan, root = self.build()
        before = snapshot(self.state)
        output = self.root / "export"
        summary = self.export(output)
        self.assertEqual(snapshot(self.state), before)  # Database and every file: same bytes, same mtime.
        self.assertEqual((summary["task_states"], summary["evidence_class"], summary["model_calls"]),
                         (["failed", "not_posted"], "synthetic_offline_fixture", 0))

        def load(name):
            return json.loads((output / name).read_text())

        scenario = load("scenario.json")
        self.assertEqual((scenario["plan_sha256"], scenario["scenario"]), (plan.sha256, "software-engineering"))
        self.assertEqual([role["id"] for role in scenario["roles"]], ["lead", "dev", "qa", "release"])
        self.assertTrue(all(role["prompt"] for role in scenario["roles"]))
        self.assertEqual([(t["status"], bool(t["prompt"])) for t in scenario["tasks"]],
                         [("failed", True), ("not_posted", True)])
        self.assertTrue(scenario["synthetic"])
        self.assertFalse(scenario["benchmark_valid"])
        self.assertEqual(scenario["source_database_sha256"], before["workflow.sqlite3"][0])

        conversation = load("conversation.json")
        self.assertEqual(conversation[0]["body"], scenario["tasks"][0]["prompt"])
        readable = (output / "conversation.md").read_text()
        self.assertIn(scenario["tasks"][0]["prompt"], readable)
        self.assertIn("synthetic_offline_fixture", readable)

        first, second = load("tasks.json")
        self.assertEqual((second["state"], second["tasks"]), ("not_posted", []))
        (task,) = first["tasks"]
        self.assertEqual((first["root"], task["task"]["state"]), (root, "failed"))
        self.assertIn("Provider attempt failed", task["stop_reason"])
        self.assertGreaterEqual(first["elapsed_seconds"], 0)
        self.assertGreaterEqual(first["human_wait_seconds"], 0)
        usage = [turn["usage"] for turn in task["runner"]["turns"]]
        self.assertEqual(usage[:2], [{"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6}] * 2)
        self.assertIsNone(usage[2])  # Unknown usage stays unknown.
        (failure,) = task["provider_failures"]
        self.assertEqual(failure["detail"]["diagnostics"]["completion_check"]["finish_reason"], "length")

        human = load("human.json")
        self.assertEqual([(r["prompt"], r["response"]) for r in human["requests"]],
                         [("Synthetic fixture question?", "Synthetic fixture answer")])
        self.assertEqual([(r["detail"]["decision"], r["detail"]["feedback"]) for r in human["reviews"]],
                         [("rejected", "Synthetic fixture review: draft is incomplete")])
        self.assertEqual([call["name"] for call in load("tool-calls.json")], ["create_text", "ask_human"])
        self.assertEqual((load("retrieval.json"), load("sandbox.json")), ([], []))

        (record,) = load("files.json")
        self.assertEqual(record["files"], [{"path": "notes/draft.txt", "bytes": len(DRAFT),
                                            "sha256": hashlib.sha256(DRAFT.encode()).hexdigest()}])
        self.assertEqual((output / "files" / root / "notes/draft.txt").read_text(), DRAFT)
        configuration = load("configuration.json")
        self.assertEqual(configuration["recorded_at_first_scheduler_use"][0]["scheduler"]["mode"], "offline_fixture")
        self.assertNotIn("api_key_env", configuration["plan_runtime"])
        code = load("code.json")
        self.assertIn("agent_lab/evaluation/official_live.py", code["source_sha256"])

        manifest = load("manifest.json")
        listed = {item["path"]: item["sha256"] for item in manifest["files"]}
        actual = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in output.rglob("*") if p.is_file() and p.name != "manifest.json"}
        self.assertEqual(listed, actual)
        everything = "".join(p.read_text() for p in output.rglob("*") if p.is_file())
        self.assertNotIn(KEY, everything)
        self.assertNotIn("never written", everything)  # The rejected reply's arguments were never stored.

    def test_existing_or_nested_output_and_another_plan_are_refused(self):
        self.build()
        before = snapshot(self.state)
        output = self.root / "export"
        self.export(output)
        self.assertIn("File exists", self.export(output, fails=True))
        self.assertIn("outside the state directory", self.export(self.state / "export", fails=True))
        changed = json.loads(self.config.read_text())
        changed["runtime"]["model"] = "another-model"
        self.config.write_text(json.dumps(changed))
        self.assertIn("same reviewed mid-test plan", self.export(self.root / "other", fails=True))
        self.assertFalse((self.root / "other").exists())  # No partial export is left behind.
        self.assertEqual(snapshot(self.state), before)

    def test_scenario_without_a_posted_task_exports_both_as_not_posted(self):
        self.build(run=False)
        before = snapshot(self.state)
        summary = self.export(self.root / "export")
        self.assertEqual((summary["task_states"], summary["evidence_class"]),
                         (["not_posted", "not_posted"], "no_model_turns"))
        self.assertEqual(snapshot(self.state), before)

    def test_symlinked_task_root_cannot_export_other_private_files(self):
        _, root = self.build()
        source = self.state / "files/tasks" / hashlib.sha256(root.encode()).hexdigest()
        source.rename(source.with_name(source.name + "-retained"))
        outside = self.root / "another-task"
        outside.mkdir()
        (outside / "private.txt").write_text("other-task-fixture")
        source.symlink_to(outside, target_is_directory=True)
        output = self.root / "unsafe-export"
        self.export(output, fails=True)
        self.assertFalse(output.exists())
        self.assertEqual((outside / "private.txt").read_text(), "other-task-fixture")

    def test_runner_dialogue_is_exported_without_the_display_text_limit(self):
        _, root = self.build()
        output = self.root / "full-export"
        self.export(output)
        records = json.loads((output / "runner-sessions.json").read_text())
        self.assertEqual([record["task"] for record in records], [root])
        messages = records[0]["transcript"]
        self.assertTrue(any(message["role"] == "tool" for message in messages))
        self.assertTrue(any("Synthetic fixture answer" in (message["content"] or "") for message in messages))


if __name__ == "__main__":
    unittest.main()
