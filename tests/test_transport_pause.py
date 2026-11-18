"""A transport failure pauses for an operator decision instead of failing (proposed 2026-11-18).

Scripted transports and a loopback server only; no model capability is claimed.
"""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_lab import budget
from agent_lab.core import Workflow, WorkflowError
from agent_lab.deepseek import DeepSeekClient, ProviderError
from agent_lab.evaluation.official_live import RECONCILE, reconcile
from agent_lab.files import FileTools
from agent_lab.gateway import ToolGateway
from agent_lab.hkgai import HKGAIClient, HKGAIHTTP
from agent_lab.runner import TRANSPORT_FAILURES, RunnerError, TaskRunner, operator_decision_failure
from agent_lab.scheduler import MultiAgentScheduler, Role
from test_provider_diagnostics import loopback


def write_reply():
    call = {"id": "call-1", "type": "function", "function": {
        "name": "create_text", "arguments": json.dumps({"path": "note.txt", "content": "after resend"})}}
    return json.dumps({"id": "r", "model": "synthetic-transport", "usage": {
        "prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        "choices": [{"finish_reason": "tool_calls",
                     "message": {"role": "assistant", "content": None, "tool_calls": [call]}}]}).encode()


def stop_reply():
    return json.dumps({"id": "s", "model": "synthetic-transport", "usage": {
        "prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
        "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "Done."}}]}).encode()


class Scripted:
    """Raises the scripted provider errors in order, then returns the scripted replies."""

    def __init__(self, *steps):
        self.steps, self.calls = list(steps), 0

    def __call__(self, payload):
        self.calls += 1
        step = self.steps.pop(0)
        if isinstance(step, ProviderError):
            raise step
        return step


def dropped():
    return ProviderError("Provider transport failed; reconcile before retrying", kind="connection_closed",
                         phase="opening", request_bytes=10)


class TransportPause(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.workflow = Workflow(self.root / "state.sqlite3")
        self.addCleanup(self.workflow.close)
        for actor, kind in (("user", "human"), ("writer", "agent")):
            self.workflow.register_actor(actor, kind)
        self.chat = self.workflow.create_chat("group", ["user", "writer"])
        self.files = FileTools(self.workflow, self.root / "files")
        self.addCleanup(self.files.close)

    def runner(self, transport):
        task = self.workflow.create_task(self.chat, "user", "writer", "Write note.txt")
        self.workflow.start_task(task, "writer")
        gateway = ToolGateway(self.workflow, self.files, task, "writer", human="user", allowed=["create_text"])
        return task, TaskRunner(gateway, DeepSeekClient("synthetic-transport", transport),
                                mode="offline_fixture", constraints=[])

    def events(self, task, kind):
        return [json.loads(e["detail"]) for e in self.workflow.events(task, "user") if e["kind"] == kind]

    def test_dropped_connection_pauses_and_nothing_is_resent_automatically(self):
        transport = Scripted(dropped())
        task, runner = self.runner(transport)
        state = runner.step()
        self.assertEqual((state["task_state"], state["runner_state"]), ("running", "provider_uncertain"))
        self.assertEqual((state["protocol_attempts"], state["unknown_usage_attempts"]), (1, 1))
        for _ in range(3):  # Further steps wait for the operator and send nothing.
            self.assertEqual(runner.step()["runner_state"], "provider_uncertain")
        self.assertEqual(transport.calls, 1)
        (decision,) = self.events(task, "provider_decision_required")
        self.assertEqual((decision["kind"], decision["automatic_retry"], decision["tools_released"]),
                         ("connection_closed", False, 0))
        self.assertEqual(len(self.events(task, "provider_request_failed")), 1)

    def test_operator_resend_releases_one_counted_attempt_and_keeps_unknown_usage(self):
        transport = Scripted(dropped(), write_reply(), stop_reply())
        task, runner = self.runner(transport)
        runner.step()
        with self.assertRaises(RunnerError):
            runner.resend_after_transport_failure("   ")
        runner.resend_after_transport_failure("Operator chose one resend after connection_closed")
        state = runner.run()
        self.assertEqual(transport.calls, 3)
        self.assertEqual((state["protocol_attempts"], state["unknown_usage_attempts"], state["reported_tokens"]),
                         (3, 1, 13))
        self.assertEqual((self.root / "files").rglob("note.txt").__next__().read_text(), "after resend")
        (released,) = self.events(task, "provider_resend_released")
        self.assertEqual((released["after_attempt"], released["automatic_retry"]), (1, False))
        with self.assertRaises(RunnerError):  # Not paused any more: a second resend is refused.
            runner.resend_after_transport_failure("again")

    def test_resend_still_obeys_the_attempt_limit(self):
        transport = Scripted(dropped(), dropped())
        task = self.workflow.create_task(self.chat, "user", "writer", "Write note.txt")
        self.workflow.start_task(task, "writer")
        from agent_lab.runner import Limits
        runner = TaskRunner(ToolGateway(self.workflow, self.files, task, "writer", human="user", allowed=["create_text"]),
                            DeepSeekClient("synthetic-transport", transport), mode="offline_fixture", constraints=[],
                            limits=Limits(model_attempts=1))
        runner.step()
        runner.resend_after_transport_failure("Operator chose one resend")
        state = runner.step()
        self.assertEqual(transport.calls, 1)  # The cap is reached; no request is sent.
        self.assertEqual(state["task_state"], "failed")
        self.assertIn("attempt budget exhausted", state["stop_reason"])

    def test_operator_abort_fails_the_task_without_a_request(self):
        transport = Scripted(dropped())
        task, runner = self.runner(transport)
        runner.step()
        state = runner.abort("Operator chose to stop after connection_closed")
        self.assertEqual((state["task_state"], state["runner_state"], transport.calls), ("failed", "stopped", 1))

    def test_provider_server_errors_pause_and_can_be_resent(self):
        for status in (500, 502, 503, 504):
            with self.subTest(status=status):
                error = ProviderError(f"Provider HTTP status {status}; no automatic retry", kind="http_status",
                                      phase="opening", http_status=status)
                transport = Scripted(error, write_reply(), stop_reply())
                task, runner = self.runner(transport)
                state = runner.step()
                self.assertEqual((state["task_state"], state["runner_state"]), ("running", "provider_uncertain"))
                self.assertEqual(runner.step()["runner_state"], "provider_uncertain")  # Nothing resent alone.
                self.assertEqual(transport.calls, 1)
                (decision,) = self.events(task, "provider_decision_required")
                self.assertEqual((decision["kind"], decision["http_status"]), ("http_status", status))
                runner.resend_after_transport_failure(f"Operator chose one resend after HTTP {status}")
                state = runner.run()
                self.assertEqual((transport.calls, state["unknown_usage_attempts"]), (3, 1))

    def test_other_provider_failures_still_fail_immediately(self):
        for diagnostics, expected in (({"kind": "http_status", "http_status": 503}, True),
                                      ({"kind": "http_status", "http_status": 429}, False),
                                      ({"kind": "http_status", "http_status": 401}, False),
                                      ({"kind": "http_status", "http_status": None}, False),
                                      ({"kind": "http_protocol"}, False), ({"kind": "connection_closed"}, True)):
            self.assertEqual(operator_decision_failure(diagnostics), expected, diagnostics)
        self.assertNotIn("http_status", TRANSPORT_FAILURES)
        self.assertNotIn("http_protocol", TRANSPORT_FAILURES)
        for error in (ProviderError("HTTP 429", kind="http_status", phase="reading", http_status=429),
                      ProviderError("HTTP 401", kind="http_status", phase="opening", http_status=401),
                      ProviderError("bad", kind="invalid_completion", phase="parsing")):
            with self.subTest(kind=error.diagnostics()["kind"]):
                task, runner = self.runner(Scripted(error))
                state = runner.step()
                self.assertEqual((state["task_state"], state["runner_state"]), ("failed", "stopped"))

    def test_real_http_connection_close_pauses_the_runner(self):
        with loopback("close") as server:
            task = self.workflow.create_task(self.chat, "user", "writer", "Write note.txt")
            self.workflow.start_task(task, "writer")
            gateway = ToolGateway(self.workflow, self.files, task, "writer", human="user", allowed=["create_text"])
            runner = TaskRunner(gateway, HKGAIClient("synthetic", HKGAIHTTP("fake-local-key", allow_network=True, timeout=1)),
                                mode="live", constraints=[])
            state = runner.step()
            self.assertEqual(server.calls, 1)
        self.assertEqual((state["task_state"], state["runner_state"]), ("running", "provider_uncertain"))
        (failure,) = self.events(task, "provider_request_failed")
        self.assertIn(failure["diagnostics"]["kind"], TRANSPORT_FAILURES)

    def test_scheduler_blocks_for_reconciliation_and_the_operator_command_resends(self):
        self.workflow.register_actor("lead", "agent")
        root = self.workflow.create_task(self.workflow.create_chat("group", ["user", "lead"]), "user", "lead", "Write")
        transport = Scripted(dropped(), write_reply(), stop_reply())
        scheduler = MultiAgentScheduler(self.workflow, self.files, root, human="user",
            roles={"lead": Role("Fixture role", ("create_text",), ())},
            clients={"lead": DeepSeekClient("synthetic-transport", transport)}, mode="offline_fixture",
            constraints=[], acceptance_id="fixture-transport", verifier_factory=lambda task: None,
            limits=budget.TreeLimits(model_attempts=4))
        scheduler.step()
        blocked = scheduler.step()
        self.assertEqual(blocked["state"], "blocked")
        self.assertEqual(blocked["needs"], [{"task": root, "kind": "reconciliation", "runner_state": "provider_uncertain"}])
        self.assertEqual(transport.calls, 1)
        self.assertIn("resend", RECONCILE)
        with self.assertRaises(WorkflowError):  # Resend only resolves a transport pause.
            reconcile(scheduler, root, "recover-tools", "wrong action", human="user")
        result = reconcile(scheduler, root, "resend", "Operator chose one resend after connection_closed", human="user")
        self.assertEqual((result["runner_state_before"], result["runner_state_after"]), ("provider_uncertain", "ready"))
        (record,) = [json.loads(e["detail"]) for e in self.workflow.events(root, "user")
                     if e["kind"] == "official_reconciliation_recorded"]
        self.assertEqual((record["action"], record["model_requests"]), ("resend", 0))
        scheduler.step()
        self.assertEqual(transport.calls, 2)  # Only the next advance sends the new attempt.


if __name__ == "__main__":
    unittest.main()
