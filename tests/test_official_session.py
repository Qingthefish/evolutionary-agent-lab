"""Exercise sequential group state and artifact custody using synthetic inputs."""

import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.core import Workflow, WorkflowError
from agent_lab.deepseek import DeepSeekClient
from agent_lab.evaluation.official import OfficialMidTestPlan
from agent_lab.evaluation.official_dataset import load_mid_test
from agent_lab.evaluation.official_session import OfficialScenarioSession
from agent_lab.files import FileTools
from agent_lab.scheduler import MultiAgentScheduler, Role
from official_mid_fixture import README_SHA256, write_archive


def completion(tool=None, args=None):
    message = {"role": "assistant", "content": "Fixture checked." if tool is None else None}
    if tool is not None:
        message["tool_calls"] = [{"id": f"fixture-{tool}", "type": "function",
                                  "function": {"name": tool, "arguments": json.dumps(args)}}]
    return json.dumps({"id": "fixture", "model": "synthetic-mid-session",
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        "choices": [{"message": message, "finish_reason": "tool_calls" if tool else "stop"}]}).encode()


class OfficialSessionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        guard = patch("agent_lab.evaluation.official_dataset._README_SHA256", README_SHA256)
        guard.start()
        self.addCleanup(guard.stop)
        source = Path(__file__).resolve().parents[1] / "evaluation/official/mid-test/plan.json"
        config = self.directory / "plan.json"
        shutil.copyfile(source, config)
        archive = config.with_name("Mid_Test.zip")
        write_archive(archive)
        config.with_name("manifest.json").write_text(json.dumps(load_mid_test(archive)))
        self.plan = OfficialMidTestPlan(config)
        self.open_workflow()
        self.session = OfficialScenarioSession.initialize(
            self.workflow, self.plan, scenario="software-engineering", human="requester",
            plan_sha256=self.plan.sha256)

    def open_workflow(self):
        self.workflow = Workflow(self.directory / "workflow.sqlite3")
        self.addCleanup(self.workflow.close)
        self.files = FileTools(self.workflow, self.directory / "files")
        self.addCleanup(self.files.close)

    def test_same_group_resumes_and_next_root_reads_previous_output(self):
        chat = self.session.chat
        first = self.session.post(1, "lead")["root"]
        self.workflow.start_task(first, "lead")
        self.workflow.post_message(chat, "lead", "Fixture booking data is ready.", task=first)
        original = self.files.create_text(first, "lead", "records.txt", "room-a,60\n")
        self.workflow.finish_task(first, "lead",
            verifier=self.files.text_verifier(first, "lead", {"records.txt": "room-a,60\n"}))
        self.files.close()
        self.workflow.close()
        self.open_workflow()
        self.session = OfficialScenarioSession.open(self.workflow, self.plan)
        second = self.session.post(2, "qa")["root"]
        self.assertEqual(self.session.post(2, "qa")["root"], second)
        self.assertEqual(self.workflow.task(second, "requester")["chat"], chat)
        with self.assertRaisesRegex(WorkflowError, "reviewed SHA"):
            self.session.carry(self.files, source_task=first, source_path="records.txt",
                               sha256="0" * 64, target_path="prior/records.txt")
        self.session.carry(self.files, source_task=first, source_path="records.txt",
                           sha256=original["sha256"], target_path="prior/records.txt")
        self.assertFalse(self.session.status()["tasks"][1]["carried_inputs"][0]["read_by_root"])

        def scripted(payload):
            messages = json.loads(payload)["messages"]
            results = [json.loads(m["content"])["result"] for m in messages if m["role"] == "tool"]
            if not results:
                return completion("read_messages", {"limit": 10})
            if len(results) == 1:
                self.assertEqual([m["body"] for m in results[0]["messages"]], [
                    self.session.scenario["tasks"][0]["prompt"], "Fixture booking data is ready.",
                    self.session.scenario["tasks"][1]["prompt"]])
                return completion("read_text", {"path": "prior/records.txt"})
            if len(results) == 2:
                self.assertEqual(results[1]["sha256"], original["sha256"])
                minutes = sum(int(row.split(",")[1]) for row in results[1]["content"].splitlines())
                return completion("create_text", {"path": "summary.txt", "content": f"{minutes} minutes\n"})
            return completion()

        roles = {role["id"]: Role(role["prompt"], ("read_messages", "read_text", "create_text"))
                 for role in self.session.scenario["roles"]}
        scheduler = MultiAgentScheduler(self.workflow, self.files, second, human="requester", roles=roles,
            clients={role: DeepSeekClient("synthetic-mid-session", scripted) for role in roles},
            mode="offline_fixture", constraints=[], acceptance_id="fixture-mid-session",
            verifier_factory=lambda task: (
                self.files.text_verifier(task["id"], task["assignee"], {"summary.txt": "60 minutes\n"}),
                "fixture-summary"))
        self.assertEqual(scheduler.run()["task_state"], "succeeded")
        report = self.session.status()
        self.assertEqual(report["group"], chat)
        self.assertEqual(report["roles"], ["lead", "dev", "qa", "release"])
        self.assertEqual([t["state"] for t in report["tasks"]], ["succeeded", "succeeded"])
        self.assertTrue(report["tasks"][1]["carried_inputs"][0]["read_by_root"])
        self.assertTrue(report["tasks"][1]["runner"]["synthetic"])
        self.assertFalse(report["benchmark_valid"])

    def test_order_and_failed_first_task_are_retained(self):
        first = self.session.post(1, "lead")["root"]
        self.workflow.start_task(first, "lead")
        self.workflow.ask_human(first, "lead", "requester", "Fixture asks the requester.")
        with self.assertRaisesRegex(WorkflowError, "Task 1 must finish"):
            self.session.post(2, "qa")
        self.assertEqual(self.session.status()["tasks"][1]["state"], "not_posted")
        self.workflow.finish_task(first, "lead", error="Fixture failure")
        self.session.post(2, "qa")
        report = self.session.status()
        self.assertEqual([t["state"] for t in report["tasks"]], ["failed", "pending"])
        self.assertEqual(len(report["tasks"][0]["requests"]), 1)

    def test_post_rolls_back_message_if_root_creation_fails(self):
        with patch.object(self.workflow, "_create_task", side_effect=WorkflowError("fixture")):
            with self.assertRaisesRegex(WorkflowError, "fixture"):
                self.session.post(1, "lead")
        self.assertEqual(self.session.status()["conversation"], [])
        self.assertEqual(self.session.status()["tasks"][0]["state"], "not_posted")
        self.session.post(1, "lead")
        self.assertEqual(len(self.session.status()["conversation"]), 1)


if __name__ == "__main__":
    unittest.main()
