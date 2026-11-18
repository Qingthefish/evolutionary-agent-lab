"""An interrupted official advance can be resolved without replay, then Task 2 can follow.

Synthetic issued-format archive and scripted provider replies through the real
CLIs. The provider transport is patched; no network, model or human is used.
Interruptions are simulated as KeyboardInterrupt (Ctrl-C) or a held claim (a
killed process). This is plumbing evidence, not a live run.
"""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.evaluation import official_live, official_session
from agent_lab.evaluation.official import OfficialMidTestPlan
from agent_lab.evaluation.official_dataset import load_mid_test
from agent_lab.gateway import ToolGateway
from agent_lab.hkgai import HKGAIHTTP
from official_mid_fixture import README_SHA256, write_archive

TEMPLATE = Path(__file__).resolve().parents[1] / "evaluation/official/mid-test/plan.json"
KEY = "synthetic-reconcile-key"


def reply(*names):
    calls = [{"id": f"call-{n}", "type": "function", "function": {"name": "create_text", "arguments": json.dumps(
        {"path": f"{name}.txt", "content": name + "\n"})}} for n, name in enumerate(names)]
    return json.dumps({"id": "fixture", "model": "synthetic-reconcile",
        "usage": {"prompt_tokens": 9, "completion_tokens": 3, "total_tokens": 12},
        "choices": [{"finish_reason": "tool_calls",
                     "message": {"role": "assistant", "content": None, "tool_calls": calls}}]}).encode()


class OfficialReconcile(unittest.TestCase):
    def setUp(self):
        for guard in (patch("agent_lab.evaluation.official_dataset._README_SHA256", README_SHA256),
                      patch.dict(os.environ, {"COURSE_HKGAI_API_KEY": KEY})):
            guard.start()
            self.addCleanup(guard.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        inputs = root / "inputs"
        inputs.mkdir()
        plan = json.loads(TEMPLATE.read_text())
        plan["runtime"].update(model="issued-model", per_scenario_model_attempts=48, max_output_tokens=1024,
                               tool_policy="newsroom-files-coordination-web-v1")
        (inputs / "plan.json").write_text(json.dumps(plan))
        write_archive(inputs / "Mid_Test.zip")
        (inputs / "manifest.json").write_text(json.dumps(load_mid_test(inputs / "Mid_Test.zip")))
        self.state = root / "state"
        self.common = ["--config", str(inputs / "plan.json"), "--state-dir", str(self.state)]
        self.cli(official_session, ["init", "--scenario", "newsroom", "--human", "requester",
                                    "--plan-sha256", OfficialMidTestPlan(inputs / "plan.json").sha256])
        self.root = self.cli(official_session, ["post", "--sequence", "1", "--assignee", "chief_editor"])["root"]
        self.requests = []

    def cli(self, module, arguments, *, fails=False, sequence=None):
        prefix = [*self.common, *(["--sequence", str(sequence)] if sequence else [])]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = module.main([*prefix, *arguments])
            except SystemExit as stop:
                code = stop.code
        self.assertEqual(code != 0, fails, err.getvalue())
        self.assertNotIn(KEY, out.getvalue() + err.getvalue())
        return err.getvalue() if fails else json.loads(out.getvalue())

    def live(self, arguments, *, replies=(), fails=False):
        replies = list(replies)

        def transport(_, payload):
            self.requests.append(payload)
            item = replies.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item

        with patch.object(HKGAIHTTP, "__call__", autospec=True, side_effect=transport):
            return self.cli(official_live, arguments, fails=fails, sequence=1)

    def reconcile(self, action, *, task=None, fails=False, confirm=True):
        return self.live(["reconcile", "--task", task or self.root, "--action", action,
                          "--reason", "Operator closed the terminal during the request",
                          *(["--confirm-stopped"] if confirm else [])], fails=fails)

    def db(self, query, *args):
        with sqlite3.connect(self.state / "workflow.sqlite3") as connection:
            return connection.execute(query, args).fetchall()

    def test_interrupted_provider_request_is_aborted_without_replay_and_task_2_follows(self):
        with self.assertRaises(KeyboardInterrupt):
            self.live(["advance", "--turns", "1"], replies=[KeyboardInterrupt()])
        self.assertEqual(len(self.requests), 1)
        for _ in range(2):  # Before this change, the scenario stayed here permanently.
            self.assertEqual(self.live(["advance", "--turns", "8"])["needs"][0]["kind"], "calling")
        self.assertIn("Task 1 must finish", self.cli(official_session, ["post", "--sequence", "2", "--assignee",
                                                                         "editor"], fails=True))
        self.assertIn("--confirm-stopped", self.reconcile("abort", confirm=False, fails=True))
        self.assertIn("Nothing for recover-tools", self.reconcile("recover-tools", fails=True))
        self.assertIn("Nothing for release-claim", self.reconcile("release-claim", fails=True))
        result = self.reconcile("abort")
        self.assertEqual((result["runner_state_before"], result["runner_state_after"], result["task_state"]),
                         ("calling", "stopped", "failed"))
        self.assertEqual(len(self.requests), 1)  # Reconciliation sent no model request.
        self.assertEqual(self.db("SELECT number,status,response FROM runner_turns"), [(1, "calling", None)])
        self.assertEqual(self.db("SELECT count(*) FROM tool_calls"), [(0,)])
        (event,) = self.db("SELECT actor,detail FROM events WHERE kind='official_reconciliation_recorded'")
        self.assertEqual(event[0], "requester")
        self.assertEqual({k: v for k, v in json.loads(event[1]).items() if k != "reason"}, {
            "action": "abort", "runner_state_before": "calling", "controller_claim_released": False,
            "model_requests": 0, "effects_replayed": False})
        self.assertEqual(self.live(["advance", "--turns", "1"])["state"], "terminal")
        self.assertIn("Nothing for abort", self.reconcile("abort", fails=True))
        self.cli(official_session, ["post", "--sequence", "2", "--assignee", "editor"])
        status = self.cli(official_session, ["status"])
        self.assertEqual([t["state"] for t in status["tasks"]], ["failed", "pending"])
        self.assertIsNone(status["tasks"][0]["runner"]["turns"][0]["usage"])  # Unknown usage stays unknown.
        self.assertIn("Operator reconciliation without replay", status["tasks"][0]["runner"]["stop_reason"])

    def test_committed_tool_results_are_recovered_and_unstarted_calls_are_not_run(self):
        original = ToolGateway.dispatch

        def interrupt_second(gateway, call):
            if call["id"] == "call-1":
                raise KeyboardInterrupt
            return original(gateway, call)

        with patch.object(ToolGateway, "dispatch", autospec=True, side_effect=interrupt_second), \
                self.assertRaises(KeyboardInterrupt):
            self.live(["advance", "--turns", "1"], replies=[reply("first", "second")])
        self.assertEqual(self.live(["advance", "--turns", "1"])["needs"][0]["kind"], "processing")
        result = self.reconcile("recover-tools")
        self.assertEqual((result["runner_state_before"], result["runner_state_after"], result["task_state"]),
                         ("processing", "ready", "running"))
        self.assertEqual(self.db("SELECT call_id,status FROM tool_calls"), [("call-0", "succeeded")])
        transcript = json.loads(self.db("SELECT transcript FROM runner_sessions")[0][0])
        results = [json.loads(m["content"]) for m in transcript if m["role"] == "tool"]
        self.assertEqual([r["ok"] for r in results], [True, False])
        self.assertIn("Not executed", results[1]["error"])
        self.assertEqual(len(self.requests), 1)
        self.live(["advance", "--turns", "1"], replies=[reply("third")])  # The task continues normally.
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(self.db("SELECT count(*) FROM tool_calls WHERE call_id='call-1'"), [(0,)])

    def test_an_uncertain_tool_effect_refuses_recovery_and_can_only_be_aborted(self):
        original = ToolGateway._execute

        def interrupt_inside(gateway, name, arguments):
            if arguments.get("path") == "second.txt":
                raise KeyboardInterrupt  # After the reservation: its effect is unknown.
            return original(gateway, name, arguments)

        with patch.object(ToolGateway, "_execute", autospec=True, side_effect=interrupt_inside), \
                self.assertRaises(KeyboardInterrupt):
            self.live(["advance", "--turns", "1"], replies=[reply("first", "second")])
        self.assertIn("Tool effect is uncertain", self.reconcile("recover-tools", fails=True))
        self.assertEqual(self.db("SELECT status FROM runner_sessions"), [("processing",)])  # Unchanged.
        self.assertEqual(self.db("SELECT call_id,status FROM tool_calls ORDER BY rowid"),
                         [("call-0", "succeeded"), ("call-1", "reserved")])
        self.assertEqual(self.reconcile("abort")["task_state"], "failed")
        self.assertEqual(self.db("SELECT status FROM tool_calls WHERE call_id='call-1'"), [("reserved",)])

    def test_a_stale_controller_claim_is_released_only_when_held(self):
        self.live(["advance", "--turns", "1"], replies=[reply("first")])
        self.db("UPDATE scheduler_runs SET owner='killed-process'")  # A SIGKILL leaves the claim held.
        blocked = self.live(["advance", "--turns", "1"])
        self.assertEqual(blocked["needs"][0]["kind"], "controller_reconciliation_or_busy")
        self.assertIn("Nothing for abort", self.reconcile("abort", fails=True))
        result = self.reconcile("release-claim")
        self.assertEqual((result["controller_claim_released"], result["task_state"]), (True, "running"))
        self.assertEqual(self.db("SELECT owner FROM scheduler_runs"), [(None,)])
        self.assertIn("Nothing for release-claim", self.reconcile("release-claim", fails=True))
        self.live(["advance", "--turns", "1"], replies=[reply("second")])
        self.assertEqual(len(self.requests), 2)

    def test_task_outside_the_tree_or_without_a_reason_is_refused(self):
        self.assertIn("this task tree", self.reconcile("abort", task="not-a-task", fails=True))
        self.assertIn("Nothing for abort", self.reconcile("abort", fails=True))  # Not started.
        message = self.live(["reconcile", "--task", self.root, "--action", "abort", "--reason", " ",
                             "--confirm-stopped"], fails=True)
        self.assertIn("concrete operator reason", message)
        self.assertEqual(self.db("SELECT count(*) FROM events WHERE kind='official_reconciliation_recorded'"), [(0,)])


if __name__ == "__main__":
    unittest.main()
