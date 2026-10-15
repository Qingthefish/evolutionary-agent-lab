from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from agent_lab import Workflow, WorkflowError
from agent_lab.deepseek import DeepSeekClient, DeepSeekHTTP, ProviderError
from agent_lab.files import FileTools
from agent_lab.gateway import ToolGateway
from agent_lab.runner import Limits, RunnerError, TaskRunner
from agent_lab.__main__ import runner_demo


def tool(name="create_text", arguments=None, identifier="create"):
    return {"id": identifier, "type": "function", "function": {
        "name": name, "arguments": json.dumps(arguments if arguments is not None else {
            "path": "note.txt", "content": "Hello\n",
        }),
    }}


def response(calls=None, text="Ready for independent checking"):
    message = {"role": "assistant", "content": None if calls else text}
    if calls:
        message["tool_calls"] = calls
    return {"id": "synthetic-response", "model": "synthetic-model", "usage": {
        "prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8,
    }, "choices": [{"finish_reason": "tool_calls" if calls else "stop", "message": message}]}


class Script:
    """Explicit synthetic transport; not a provider fallback or model result."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, payload):
        self.requests.append(json.loads(payload))
        if not self.replies:
            raise AssertionError("Unexpected extra synthetic request")
        item = self.replies.pop(0)
        if isinstance(item, BaseException):
            raise item
        if callable(item):
            item = item()
        return json.dumps(item).encode()


_DEFAULT = object()


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.database = self.root / "state.sqlite3"
        self.now = [1000.0]
        self.workflow = Workflow(self.database, clock=lambda: self.now[0])
        for actor, kind in [("user", "human"), ("writer", "agent"), ("reviewer", "agent")]:
            self.workflow.register_actor(actor, kind)
        self.chat = self.workflow.create_chat("group", ["user", "writer", "reviewer"])
        self.task = self.workflow.create_task(self.chat, "user", "writer", "Write note.txt containing Hello and a newline")
        self.workflow.start_task(self.task, "writer")
        self.files = FileTools(self.workflow, self.root / "files")
        self.allowed = ["create_text", "read_text", "update_text", "delete_text", "ask_human", "delegate_task"]
        self.gateway = self.new_gateway()

    def tearDown(self):
        self.files.close()
        self.workflow.close()
        self.directory.cleanup()

    def new_gateway(self, **kwargs):
        return ToolGateway(self.workflow, self.files, self.task, "writer", human="user", allowed=self.allowed,
                           delegates=["reviewer"], **kwargs)

    def runner(self, replies=(), *, verifier=_DEFAULT, **kwargs):
        self.script = replies if isinstance(replies, Script) else Script(replies)
        client = DeepSeekClient("explicit-fixture-model", self.script, max_tokens=128)
        options = {"mode": "offline_fixture", "constraints": ["Use English", "Keep the required newline"]}
        if verifier is _DEFAULT:
            options.update(verifier=self.files.text_verifier(self.task, "writer", {"note.txt": "Hello\n"}),
                           verifier_id="hello-text-v1")
        elif verifier is not None:
            options.update(verifier=verifier, verifier_id="custom-check-v1")
        options.update(kwargs)
        return TaskRunner(self.gateway, client, **options)

    def transcript(self):
        return json.loads(self.workflow.db.execute("SELECT transcript FROM runner_sessions WHERE task=?", (self.task,)).fetchone()[0])

    def test_real_file_tool_loop_succeeds_only_with_trusted_verifier(self):
        runner = self.runner([response([tool()]), response()])
        state = runner.run()
        self.assertEqual(state["task_state"], "succeeded")
        self.assertEqual(state["protocol_attempts"], 2)
        self.assertEqual(state["reported_tokens"], 16)
        self.assertEqual(state["live_model_attempts"], 0)
        self.assertFalse(state["benchmark_valid"])
        self.assertEqual(self.transcript()[3]["role"], "tool")
        events = self.workflow.events(self.task, "user")
        self.assertIn("artifacts_verified", [event["kind"] for event in events])
        self.assertEqual(self.script.requests[1]["messages"][3]["tool_call_id"], "create")

    def test_final_claim_without_verifier_remains_incomplete_and_can_receive_review(self):
        runner = self.runner([response(text="Everything passed"), response([tool()]), response()], verifier=None)
        state = runner.run()
        self.assertEqual(state["runner_state"], "awaiting_verification")
        self.assertEqual(state["task_state"], "running")
        runner.review_failed("note.txt is missing; inspect and produce the required file")
        state = runner.run()
        self.assertEqual(state["runner_state"], "awaiting_verification")
        self.assertEqual(state["task_state"], "running")
        self.files.complete_from_text(self.task, "writer", {"note.txt": "Hello\n"})
        self.assertEqual(runner.step()["task_state"], "succeeded")

    def test_runner_fixture_preserves_pause_and_budget_across_restart(self):
        report = runner_demo(self.root / "demo")
        self.assertEqual(report["before_restart"]["protocol_attempts"], 1)
        self.assertEqual(report["before_restart"]["task_state"], "waiting_input")
        self.assertEqual(report["after_restart"]["protocol_attempts"], 3)
        self.assertEqual(report["after_restart"]["task_state"], "succeeded")
        self.assertEqual(report["model_calls"], 0)
        self.assertEqual(report["api_network_calls"], 0)
        self.assertFalse(report["benchmark_valid"])

    def test_independent_failed_verification_returns_evidence_for_bounded_repair(self):
        wrong = "Wrong\n"
        runner = self.runner([
            response([tool(arguments={"path": "note.txt", "content": wrong})]), response(),
            response([tool("update_text", {"path": "note.txt", "content": "Hello\n",
                                          "expected_sha256": hashlib.sha256(wrong.encode()).hexdigest()}, "repair")]),
            response(),
        ])
        state = runner.run()
        self.assertEqual(state["task_state"], "succeeded")
        feedback = [message for message in self.script.requests[2]["messages"]
                    if "trusted_verification_failure" in (message.get("content") or "")]
        self.assertEqual(len(feedback), 1)
        self.assertIn("artifact:note.txt", feedback[0]["content"])
        self.assertEqual(state["protocol_attempts"], 4)

    def test_clarification_and_context_survive_restart_without_resetting_budget(self):
        script = Script([response([tool("ask_human", {"prompt": "Which greeting language?"}, "question")]),
                         response([tool()]), response()])
        runner = self.runner(script)
        first = runner.run()
        self.assertEqual(first["task_state"], "waiting_input")
        self.assertEqual(first["runner_state"], "paused")
        runner.step()
        self.assertEqual(len(script.requests), 1)
        request = self.workflow.db.execute("SELECT id FROM requests WHERE task=?", (self.task,)).fetchone()[0]
        self.files.close()
        self.workflow.close()
        self.workflow = Workflow(self.database, clock=lambda: self.now[0])
        self.files = FileTools(self.workflow, self.root / "files")
        self.gateway = self.new_gateway()
        self.workflow.respond(request, "user", answer="English")
        resumed = self.runner(script)
        self.assertEqual(resumed.run()["task_state"], "succeeded")
        messages = script.requests[1]["messages"]
        self.assertIn("Use English", messages[1]["content"])
        self.assertIn("Keep the required newline", messages[1]["content"])
        human = [message for message in messages if "recorded_human_response" in (message.get("content") or "")]
        self.assertEqual(len(human), 1)
        self.assertIn('"response": "English"', human[0]["content"])
        self.assertEqual(resumed.status()["protocol_attempts"], 3)

    def test_budget_and_context_changes_are_rejected_on_reconstruction(self):
        self.runner([])
        for options in [{"limits": Limits(model_attempts=99)}, {"constraints": ["Drop earlier constraint"]},
                        {"verifier_id": "changed-v2"}, {"verifier": None}]:
            with self.subTest(options=options), self.assertRaises(RunnerError):
                self.runner([], **options)

    def test_whole_batch_is_validated_before_any_effect(self):
        runner = self.runner([response([tool(), tool("finish_task", {"checks": {"passed": True}}, "forged")])],
                             limits=Limits(model_attempts=1))
        state = runner.run()
        self.assertEqual(state["task_state"], "failed")
        self.assertEqual(self.workflow.db.execute("SELECT count(*) FROM tool_calls").fetchone()[0], 0)
        self.assertEqual(list((self.root / "files/tasks").rglob("note.txt")), [])

    def test_batch_pauses_and_later_proposals_are_not_executed(self):
        runner = self.runner([response([tool("ask_human", {"prompt": "Confirm language?"}, "question"), tool()])])
        state = runner.run()
        self.assertEqual(state["task_state"], "waiting_input")
        results = [json.loads(message["content"]) for message in self.transcript() if message["role"] == "tool"]
        self.assertTrue(results[0]["ok"])
        self.assertFalse(results[1]["ok"])
        self.assertIn("Not executed", results[1]["error"])
        self.assertEqual(self.workflow.db.execute("SELECT count(*) FROM tool_calls").fetchone()[0], 1)

    def test_approved_action_waits_for_trusted_release_not_another_model_call(self):
        receipt = self.files.create_text(self.task, "writer", "old.txt", "delete me")
        runner = self.runner([response([tool("delete_text", {"path": "old.txt", "expected_sha256": receipt["sha256"]}, "delete")]),
                              response([tool()]), response()])
        runner.run()
        request = self.workflow.db.execute("SELECT id FROM requests WHERE task=?", (self.task,)).fetchone()[0]
        self.workflow.respond(request, "user", approve=True)
        waiting = runner.run()
        self.assertEqual(waiting["needs"], "trusted_action_release")
        self.assertEqual(waiting["protocol_attempts"], 1)
        self.gateway.release_approved(request)
        self.assertEqual(runner.run()["task_state"], "succeeded")

    def test_denial_cancels_without_any_followup_model_call(self):
        receipt = self.files.create_text(self.task, "writer", "old.txt", "keep")
        runner = self.runner([response([tool("delete_text", {"path": "old.txt", "expected_sha256": receipt["sha256"]})])])
        runner.run()
        request = self.workflow.db.execute("SELECT id FROM requests WHERE task=?", (self.task,)).fetchone()[0]
        self.workflow.respond(request, "user", approve=False)
        state = runner.run()
        self.assertEqual(state["task_state"], "cancelled")
        self.assertEqual(len(self.script.requests), 1)

    def test_attempt_limit_stops_and_preserves_partial_files_and_failure_metrics(self):
        runner = self.runner([response([tool()])], limits=Limits(model_attempts=1))
        state = runner.run()
        self.assertEqual(state["task_state"], "failed")
        self.assertIn("attempt budget", state["stop_reason"])
        self.assertEqual(state["protocol_attempts"], 1)
        self.assertEqual(len(list((self.root / "files/tasks").rglob("note.txt"))), 1)
        self.assertEqual(self.workflow.metrics(self.chat, "user")["goals"]["success_fraction"], 0)

    def test_reported_token_overrun_stops_before_tools(self):
        runner = self.runner([response([tool()])], limits=Limits(reported_tokens=7))
        state = runner.run()
        self.assertEqual(state["task_state"], "failed")
        self.assertEqual(state["reported_tokens"], 8)
        self.assertIn("no tools released", state["stop_reason"])
        self.assertEqual(self.workflow.db.execute("SELECT count(*) FROM tool_calls").fetchone()[0], 0)

    def test_tool_budget_is_terminal_before_batch_effects(self):
        # A fresh task has no persisted gateway budget yet.
        self.task = self.workflow.create_task(self.chat, "user", "writer", "Limited task")
        self.workflow.start_task(self.task, "writer")
        self.gateway = self.new_gateway(max_calls=1)
        runner = self.runner([response([tool(), tool(arguments={"path": "other.txt", "content": "other"}, identifier="other")])])
        state = runner.run()
        self.assertEqual(state["task_state"], "failed")
        self.assertIn("tool-call budget", state["stop_reason"])
        self.assertEqual(self.workflow.db.execute("SELECT count(*) FROM tool_calls").fetchone()[0], 0)

    def test_repeated_same_tool_outcomes_stop_even_when_ids_differ(self):
        runner = self.runner([response([tool("read_text", {"path": "missing.txt"}, str(index))]) for index in range(3)])
        state = runner.run()
        self.assertEqual(state["task_state"], "failed")
        self.assertIn("Repeated identical", state["stop_reason"])
        self.assertEqual(state["protocol_attempts"], 3)

    def test_deadline_includes_human_wait_and_cancels_descendants(self):
        child = self.workflow.create_task(self.chat, "writer", "reviewer", "Child work", parent=self.task)
        runner = self.runner([response([tool("ask_human", {"prompt": "Which language?"})])],
                             limits=Limits(duration_seconds=10))
        runner.run()
        self.now[0] += 12
        state = runner.run()
        self.assertEqual(state["task_state"], "failed")
        self.assertEqual(self.workflow.task(child, "user")["state"], "cancelled")
        records = self.workflow.metrics(self.chat, "user")["tasks"]
        main = next(item for item in records if item["task_id"] == self.task)
        self.assertEqual(main["human_wait_seconds"], 12)
        self.assertEqual(state["elapsed_seconds"], 12)
        self.assertEqual(state["protocol_attempts"], 1)

    def test_provider_late_response_cannot_dispatch_tools(self):
        def late():
            self.now[0] += 11
            return response([tool()])
        runner = self.runner([late], limits=Limits(duration_seconds=10))
        self.assertEqual(runner.run()["task_state"], "failed")
        self.assertEqual(self.workflow.db.execute("SELECT count(*) FROM tool_calls").fetchone()[0], 0)

    def test_slow_verifier_rolls_back_success_and_stops_on_deadline(self):
        def slow():
            self.now[0] += 11
            return {"independent_check": True}
        runner = self.runner([response()], verifier=slow, limits=Limits(duration_seconds=10))
        self.assertEqual(runner.run()["task_state"], "failed")
        self.assertNotIn("succeeded", [event["kind"] for event in self.workflow.events(self.task, "user")])

    def test_provider_error_is_not_automatically_retried_or_counted_as_zero_usage(self):
        runner = self.runner([ProviderError("Transport interrupted")])
        state = runner.run()
        self.assertEqual(state["task_state"], "failed")
        self.assertEqual(state["unknown_usage_attempts"], 1)
        self.assertEqual(state["protocol_attempts"], 1)
        runner.run()
        self.assertEqual(len(self.script.requests), 1)

    def test_time_limit_after_tool_effect_preserves_artifact_but_records_failure(self):
        runner = self.runner([response([tool()])], limits=Limits(duration_seconds=10))
        original = self.gateway._execute

        def slow_tool(name, arguments):
            result = original(name, arguments)
            self.now[0] += 11
            return result

        with patch.object(self.gateway, "_execute", side_effect=slow_tool):
            state = runner.run()
        self.assertEqual(state["task_state"], "failed")
        self.assertEqual(len(list((self.root / "files/tasks").rglob("note.txt"))), 1)
        self.assertEqual(len(self.script.requests), 1)

    def test_approval_wait_expiry_never_releases_the_pending_action(self):
        receipt = self.files.create_text(self.task, "writer", "old.txt", "keep")
        runner = self.runner([response([tool("delete_text", {
            "path": "old.txt", "expected_sha256": receipt["sha256"],
        })])], limits=Limits(duration_seconds=10))
        runner.run()
        request = self.workflow.db.execute("SELECT id FROM requests WHERE task=?", (self.task,)).fetchone()[0]
        self.now[0] += 11
        self.assertEqual(runner.run()["task_state"], "failed")
        with self.assertRaises(WorkflowError):
            self.workflow.respond(request, "user", approve=True)
        self.assertEqual(len(list((self.root / "files/tasks").rglob("old.txt"))), 1)

    def test_unknown_provider_crash_requires_reconciliation_not_replay(self):
        runner = self.runner([RuntimeError("Simulated worker death")])
        with self.assertRaises(RuntimeError):
            runner.run()
        state = runner.run()
        self.assertEqual(state["runner_state"], "calling")
        self.assertEqual(len(self.script.requests), 1)
        with self.assertRaises(RunnerError):
            runner.recover_tools()
        self.assertEqual(runner.abort("Provider outcome unknown; stop before reconciliation")["task_state"], "failed")

    def test_recorded_tool_result_recovers_after_crash_without_repeating_effect(self):
        runner = self.runner([response([tool()]), response()])
        original = self.gateway.dispatch

        def crash_after_result(proposal):
            original(proposal)
            raise RuntimeError("Worker died after tool commit, before transcript update")
        with patch.object(self.gateway, "dispatch", side_effect=crash_after_result), self.assertRaises(RuntimeError):
            runner.step()
        self.assertEqual(runner.status()["runner_state"], "processing")
        self.assertEqual(runner.recover_tools()["runner_state"], "ready")
        self.assertEqual(runner.run()["task_state"], "succeeded")
        self.assertEqual(sum(event["kind"] == "file_created" for event in self.workflow.events(self.task, "user")), 1)

    def test_uncertain_reserved_tool_is_never_replayed_on_recovery(self):
        runner = self.runner([response([tool()])])
        original = self.gateway._execute

        def crash_after_effect(name, arguments):
            original(name, arguments)
            raise RuntimeError("Disk effect happened without a committed result")
        with patch.object(self.gateway, "_execute", side_effect=crash_after_effect), self.assertRaises(RuntimeError):
            runner.step()
        with self.assertRaisesRegex(RunnerError, "uncertain"):
            runner.recover_tools()
        self.assertEqual(runner.status()["protocol_attempts"], 1)
        self.assertEqual(len(list((self.root / "files/tasks").rglob("note.txt"))), 1)

    def test_unstarted_batch_proposals_are_skipped_during_trusted_recovery(self):
        runner = self.runner([response([tool()])])
        with patch.object(self.gateway, "validate_batch", side_effect=RuntimeError("Crash before dispatch")), self.assertRaises(RuntimeError):
            runner.step()
        runner.recover_tools()
        result = json.loads(self.transcript()[-1]["content"])
        self.assertFalse(result["ok"])
        self.assertIn("interrupted batch", result["error"])
        self.assertEqual(self.workflow.db.execute("SELECT count(*) FROM tool_calls").fetchone()[0], 0)

    def test_prior_turn_tool_result_cannot_be_misattributed_to_interrupted_new_turn(self):
        runner = self.runner([response([tool()]), response([tool()])])
        runner.step()
        with patch.object(self.gateway, "validate_batch", side_effect=RuntimeError("Crash before replay check")), self.assertRaises(RuntimeError):
            runner.step()
        with self.assertRaisesRegex(RunnerError, "predates"):
            runner.recover_tools()

    def test_external_pause_does_not_busy_loop(self):
        runner = self.runner([])
        self.workflow.ask_human(self.task, "writer", "user", "External question")
        state = runner.run()
        self.assertEqual(state["runner_state"], "paused")
        self.assertEqual(state["protocol_attempts"], 0)

    def test_concurrent_runners_reserve_one_provider_attempt(self):
        entered, release = threading.Event(), threading.Event()

        def blocked_response():
            entered.set()
            if not release.wait(timeout=5):
                raise AssertionError("Test worker did not release")
            return response()
        self.runner([], verifier=None)

        def worker():
            workflow = Workflow(self.database, clock=lambda: self.now[0])
            files = FileTools(workflow, self.root / "files")
            try:
                gateway = ToolGateway(workflow, files, self.task, "writer", human="user", allowed=self.allowed,
                                      delegates=["reviewer"])
                client = DeepSeekClient("explicit-fixture-model", Script([blocked_response]), max_tokens=128)
                runner = TaskRunner(gateway, client, mode="offline_fixture", constraints=["Use English", "Keep the required newline"])
                return runner.step()
            finally:
                files.close()
                workflow.close()

        with ThreadPoolExecutor(max_workers=1) as pool:
            running = pool.submit(worker)
            self.assertTrue(entered.wait(timeout=5))
            second = self.runner([], verifier=None)
            self.assertEqual(second.step()["runner_state"], "calling")
            self.assertEqual(second.status()["protocol_attempts"], 1)
            release.set()
            self.assertEqual(running.result(timeout=5)["runner_state"], "awaiting_verification")

    def test_abort_during_provider_call_keeps_late_usage_but_releases_no_tools(self):
        runner = None

        def abort_then_reply():
            runner.abort("Owner stopped during provider call")
            return response([tool()])
        runner = self.runner([abort_then_reply])
        state = runner.run()
        self.assertEqual(state["task_state"], "failed")
        self.assertEqual(state["reported_tokens"], 8)
        self.assertEqual(self.workflow.db.execute("SELECT count(*) FROM tool_calls").fetchone()[0], 0)

    def test_late_transport_error_does_not_replace_a_prior_stop_reason(self):
        runner = None

        def abort_then_error():
            runner.abort("Owner stop must be retained")
            raise ProviderError("Late transport failure")
        runner = self.runner([abort_then_error])
        state = runner.run()
        self.assertEqual(state["stop_reason"], "Owner stop must be retained")
        self.assertEqual(state["unknown_usage_attempts"], 1)

    def test_limits_modes_and_verifier_setup_are_explicit(self):
        for changes in [{"model_attempts": True}, {"reported_tokens": 0}, {"duration_seconds": float("inf")},
                        {"duration_seconds": -1}, {"repeated_outcomes": 0}]:
            with self.assertRaises(RunnerError):
                Limits(**changes)
        client = DeepSeekClient("course-model", DeepSeekHTTP("test-secret"))
        with self.assertRaises(RunnerError):
            TaskRunner(self.gateway, client, mode="offline_fixture", constraints=[])
        with self.assertRaises(RunnerError):
            TaskRunner(self.gateway, DeepSeekClient("fixture", Script([])), mode="live", constraints=[])
        with self.assertRaises(RunnerError):
            TaskRunner(self.gateway, client, mode="live", constraints=[], verifier=lambda: {"check": True})


if __name__ == "__main__":
    unittest.main()
