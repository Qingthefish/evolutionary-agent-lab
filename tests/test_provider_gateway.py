from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch, MagicMock
import urllib.error

from agent_lab import Workflow, WorkflowError
from agent_lab.deepseek import DeepSeekClient, DeepSeekHTTP, ProviderError, _NoRedirect
from agent_lab.files import FileTools
from agent_lab.gateway import ToolGateway, ToolRequestError
from agent_lab.memory import ExperienceMemory
from agent_lab.__main__ import protocol_demo
from agent_lab.protocol import strict_json


def call(name="create_text", arguments=None, identifier="call-1"):
    return {"id": identifier, "type": "function", "function": {
        "name": name, "arguments": json.dumps(arguments if arguments is not None else {
            "path": "note.txt", "content": "actual text",
        }),
    }}


def completion(tool_calls=None):
    message = {"role": "assistant", "content": None if tool_calls else "Ready for verification"}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {"id": "response-1", "model": "returned-model-id", "choices": [{
        "finish_reason": "tool_calls" if tool_calls else "stop", "message": message,
    }], "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}}


class ProviderTests(unittest.TestCase):
    def client(self, data):
        return DeepSeekClient("explicit-test-model", lambda payload: json.dumps(data).encode())

    def test_roundtrip_keeps_ids_usage_and_reasoning_and_actual_model(self):
        data = completion([call()])
        data["choices"][0]["message"]["reasoning_content"] = "Synthetic protocol field"
        sent = []

        def transport(payload):
            sent.append(json.loads(payload))
            return json.dumps(data).encode()

        client = DeepSeekClient("explicit-test-model", transport)
        result = client.complete([{"role": "user", "content": "test"}], tools=[{"fixture": True}])
        self.assertEqual(result.usage["total_tokens"], 14)
        self.assertEqual(result.model, "returned-model-id")
        self.assertEqual(result.response_id, "response-1")
        client.complete([result.message, {"role": "tool", "tool_call_id": "call-1", "content": "ok"}])
        self.assertEqual(sent[1]["messages"][0], data["choices"][0]["message"])
        self.assertEqual(sent[0]["thinking"], {"type": "disabled"})
        self.assertFalse(sent[0]["stream"])
        self.assertEqual(sent[0]["tools"], [{"fixture": True}])

    def test_incomplete_or_error_finishes_cannot_release_tools(self):
        for reason in ["length", "content_filter", "aborted", "insufficient_system_resource", None]:
            data = completion([call()])
            data["choices"][0]["finish_reason"] = reason
            with self.subTest(reason=reason), self.assertRaises(ProviderError):
                self.client(data).complete([{"role": "user", "content": "test"}])

    def test_invalid_response_shapes_ids_counts_and_tool_consistency(self):
        variants = []
        for changes in [{"choices": []}, {"choices": [None]}, {"usage": {}}, {"model": ""}]:
            variants.append(completion() | changes)
        for counts in [True, -1, 1.5, "10"]:
            item = completion()
            item["usage"]["total_tokens"] = counts
            variants.append(item)
        item = completion([call(), call()])
        variants.append(item)
        item = completion([call()])
        item["choices"][0]["finish_reason"] = "stop"
        variants.append(item)
        for content in [[], {}, "", None]:
            item = completion()
            item["choices"][0]["message"]["content"] = content
            variants.append(item)
        for calls in [{}, "", [None], [call() | {"extra": True}]]:
            item = completion()
            item["choices"][0]["message"]["tool_calls"] = calls
            variants.append(item)
        for item in variants:
            with self.subTest(item=item), self.assertRaises(ProviderError):
                self.client(item).complete([{"role": "user", "content": "test"}])

    def test_bad_json_and_oversized_responses_are_rejected(self):
        for raw in [b'{}', b'{"choices":1,"choices":2}', b'NaN', b'\xff', b'x' * (DeepSeekHTTP.max_bytes + 1)]:
            with self.subTest(size=len(raw)), self.assertRaises(ProviderError):
                DeepSeekClient("test-model", lambda payload: raw).complete([{"role": "user", "content": "test"}])

    def test_configuration_and_request_limits(self):
        for model, tokens in [("", 32), ("model", True), ("model", 0), ("model", 16385)]:
            with self.subTest(model=model, tokens=tokens), self.assertRaises(ProviderError):
                DeepSeekClient(model, lambda payload: b"", max_tokens=tokens)
        transport = MagicMock()
        client = DeepSeekClient("test-model", transport)
        for messages in [[], [{"bad": float("nan")}], [{"content": "x" * DeepSeekHTTP.max_bytes}]]:
            with self.assertRaises(ProviderError):
                client.complete(messages)
        transport.assert_not_called()

    def test_network_is_disabled_by_default_and_secrets_not_in_repr(self):
        transport = DeepSeekHTTP("test-secret")
        self.assertNotIn("test-secret", repr(transport))
        with patch("urllib.request.build_opener") as opener, self.assertRaisesRegex(ProviderError, "Network disabled"):
            transport(b"{}")
        opener.assert_not_called()
        for timeout in [True, 0, float("inf"), -1, 121]:
            with self.assertRaises(ProviderError):
                DeepSeekHTTP("test-secret", timeout=timeout)

    def test_http_request_is_official_bounded_nonstreaming_and_not_retried(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.geturl.return_value = DeepSeekHTTP.endpoint
        response.read.return_value = b"{}"
        opener = MagicMock()
        opener.open.return_value = response
        with patch("urllib.request.build_opener", return_value=opener):
            self.assertEqual(DeepSeekHTTP("test-secret", allow_network=True, timeout=7)(b"{}"), b"{}")
        args, kwargs = opener.open.call_args
        self.assertEqual(args[0].full_url, "https://api.deepseek.com/chat/completions")
        self.assertEqual(args[0].get_header("Authorization"), "Bearer test-secret")
        self.assertEqual(kwargs["timeout"], 7)
        response.read.assert_called_once_with(DeepSeekHTTP.max_bytes + 1)
        self.assertEqual(opener.open.call_count, 1)

    def test_transport_failures_are_sanitized_without_retry_or_redirect(self):
        errors = [TimeoutError("test-secret leaked"), urllib.error.URLError("test-secret leaked"),
                  urllib.error.HTTPError(DeepSeekHTTP.endpoint, 401, "test-secret", {}, io.BytesIO(b"test-secret"))]
        for error in errors:
            opener = MagicMock()
            opener.open.side_effect = error
            with patch("urllib.request.build_opener", return_value=opener):
                with self.assertRaises(ProviderError) as result:
                    DeepSeekHTTP("test-secret", allow_network=True)(b"{}")
            self.assertNotIn("test-secret", str(result.exception))
            self.assertEqual(opener.open.call_count, 1)
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.test"))

    def test_duplicate_and_nonfinite_json_are_never_accepted(self):
        for raw in ['{"a":1,"a":2}', '{"nested":{"a":1,"a":2}}', '{"a":NaN}', '{"a":1e999}']:
            with self.assertRaises(ValueError):
                strict_json(raw)


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.database = self.root / "state.sqlite3"
        self.workflow = Workflow(self.database)
        for actor, kind in [("user", "human"), ("writer", "agent"), ("reviewer", "agent")]:
            self.workflow.register_actor(actor, kind)
        self.chat = self.workflow.create_chat("group", ["user", "writer", "reviewer"])
        self.task = self.workflow.create_task(self.chat, "user", "writer", "Write and verify")
        self.workflow.start_task(self.task, "writer")
        self.files = FileTools(self.workflow, self.root / "files")
        self.memory = ExperienceMemory(self.workflow)
        self.allowed = ["read_text", "create_text", "update_text", "delete_text", "delegate_task", "ask_human",
                        "post_message", "search_memory", "select_memory", "offer_artifact", "accept_artifact"]
        self.gateway = self.new_gateway()

    def tearDown(self):
        self.files.close()
        self.workflow.close()
        self.directory.cleanup()

    def new_gateway(self, **kwargs):
        options = {"human": "user", "allowed": self.allowed, "memory": self.memory, "delegates": ["reviewer"]}
        options.update(kwargs)
        return ToolGateway(self.workflow, self.files, self.task, "writer", **options)

    def dispatch(self, name="create_text", arguments=None, identifier="call-1"):
        result = self.gateway.dispatch(call(name, arguments, identifier))
        self.assertEqual(result["tool_call_id"], identifier)
        return json.loads(result["content"])

    def test_tool_result_is_real_but_cannot_certify_task_completion(self):
        result = self.dispatch()
        self.assertTrue(result["ok"])
        self.assertEqual(self.files.read_text(self.task, "writer", "note.txt")["content"], "actual text")
        self.assertEqual(self.workflow.task(self.task, "user")["state"], "running")
        for name in ["finish_task", "respond", "consume_approval", "execute_code", "run_shell", "git_push"]:
            with self.assertRaises(ToolRequestError):
                self.dispatch(name, {})
        self.files.complete_from_text(self.task, "writer", {"note.txt": "actual text"})

    def test_identity_extra_fields_wrong_types_and_duplicate_json_are_rejected_before_effect(self):
        invalid = [call(arguments={"path": "note.txt", "content": "bad", "actor": "user"}),
                   call(arguments={"path": "note.txt", "content": "bad", "task": "other"}),
                   call(arguments={"path": "note.txt", "content": 3}),
                   call(arguments={"path": "note.txt", "content": "\ud800"}),
                   call() | {"extra": "ignored?"}]
        for raw in ['{"path":"note.txt","path":"other.txt","content":"bad"}', '[]',
                    '{"path":"note.txt","content":NaN}', '{"path":"note.txt","content":1e999}']:
            item = call()
            item["function"]["arguments"] = raw
            invalid.append(item)
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(ToolRequestError):
                self.gateway.dispatch(item)
        self.assertEqual(self.workflow.db.execute("SELECT count(*) FROM tool_calls").fetchone()[0], 0)

    def test_allowlist_is_enforced_and_schema_copy_does_not_change_validation(self):
        gateway = self.new_gateway(allowed=["read_text"])
        tools = gateway.tools()
        self.assertEqual([item["function"]["name"] for item in tools], ["read_text"])
        tools[0]["function"]["parameters"]["properties"]["path"]["maxLength"] = 999999
        with self.assertRaises(ToolRequestError):
            gateway.dispatch(call())
        self.assertEqual(gateway.tools()[0]["function"]["parameters"]["properties"]["path"]["maxLength"], 512)

    def test_replayed_call_is_blocked_after_database_reopen(self):
        self.dispatch()
        self.files.close()
        self.workflow.close()
        self.workflow = Workflow(self.database)
        self.files = FileTools(self.workflow, self.root / "files")
        self.memory = ExperienceMemory(self.workflow)
        self.gateway = self.new_gateway()
        with self.assertRaisesRegex(ToolRequestError, "already reserved"):
            self.dispatch()
        self.assertEqual(self.files.read_text(self.task, "writer", "note.txt")["content"], "actual text")

    def test_crash_after_effect_leaves_reserved_record_and_cannot_replay(self):
        original = self.gateway._execute

        def crash(name, arguments):
            original(name, arguments)
            raise RuntimeError("Simulated process death after disk effect")

        with patch.object(self.gateway, "_execute", side_effect=crash), self.assertRaises(RuntimeError):
            self.dispatch()
        record = self.workflow.db.execute("SELECT status,result FROM tool_calls").fetchone()
        self.assertEqual(tuple(record), ("reserved", None))
        with self.assertRaises(ToolRequestError):
            self.dispatch()
        self.assertEqual(self.files.read_text(self.task, "writer", "note.txt")["content"], "actual text")

    def test_budget_is_persistent_and_failed_tools_consume_a_slot(self):
        other = self.workflow.create_task(self.chat, "user", "writer", "Small budget")
        self.workflow.start_task(other, "writer")
        gateway = ToolGateway(self.workflow, self.files, other, "writer", human="user", allowed=["read_text"], max_calls=1)
        result = gateway.dispatch(call("read_text", {"path": "missing.txt"}))
        self.assertFalse(json.loads(result["content"])["ok"])
        with self.assertRaisesRegex(ToolRequestError, "budget exhausted"):
            gateway.dispatch(call("read_text", {"path": "missing.txt"}, "new-id"))
        with self.assertRaisesRegex(ToolRequestError, "cannot be reset"):
            ToolGateway(self.workflow, self.files, other, "writer", human="user", allowed=["read_text"], max_calls=2)

    def test_deletion_pauses_then_exact_approval_can_release_once(self):
        original = self.dispatch()["result"]
        result = self.dispatch("delete_text", {"path": "note.txt", "expected_sha256": original["sha256"]}, "delete")
        request = result["result"]["request_id"]
        self.assertEqual(result["task_state"], "waiting_approval")
        with self.assertRaises(WorkflowError):
            self.gateway.release_approved(request)
        with self.assertRaises(ToolRequestError):
            self.dispatch("read_text", {"path": "note.txt"}, "paused-read")
        self.workflow.respond(request, "user", approve=True)
        self.assertEqual(self.files.read_text(self.task, "writer", "note.txt")["sha256"], original["sha256"])
        self.gateway.release_approved(request)
        with self.assertRaises(WorkflowError):
            self.gateway.release_approved(request)
        with self.assertRaises(WorkflowError):
            self.files.read_text(self.task, "writer", "note.txt")

    def test_changed_file_never_gets_deleted_using_prior_approval(self):
        original = self.dispatch()["result"]
        result = self.dispatch("delete_text", {"path": "note.txt", "expected_sha256": original["sha256"]}, "delete")
        request = result["result"]["request_id"]
        self.workflow.respond(request, "user", approve=True)
        self.files.update_text(self.task, "writer", "note.txt", "changed", expected_sha256=original["sha256"])
        with self.assertRaisesRegex(ToolRequestError, "released but deletion failed"):
            self.gateway.release_approved(request)
        self.assertEqual(self.files.read_text(self.task, "writer", "note.txt")["content"], "changed")
        with self.assertRaises(WorkflowError):
            self.gateway.release_approved(request)

    def test_denial_never_releases_deletion_and_another_task_cannot_use_approval(self):
        original = self.dispatch()["result"]
        result = self.dispatch("delete_text", {"path": "note.txt", "expected_sha256": original["sha256"]}, "delete")
        request = result["result"]["request_id"]
        other = self.workflow.create_task(self.chat, "user", "writer", "Other task")
        self.workflow.start_task(other, "writer")
        other_gateway = ToolGateway(self.workflow, self.files, other, "writer", human="user", allowed=["delete_text"])
        with self.assertRaisesRegex(ToolRequestError, "another task"):
            other_gateway.release_approved(request)
        self.workflow.respond(request, "user", approve=False)
        with self.assertRaises(WorkflowError):
            self.gateway.release_approved(request)
        # Trusted test-only disk inspection: a cancelled task cannot read through its broker.
        self.assertEqual(len(list((self.root / "files/tasks").rglob("note.txt"))), 1)

    def test_concurrent_same_call_reserves_and_executes_only_once(self):
        ready = threading.Barrier(2)

        def dispatch_once(index):
            workflow = Workflow(self.database)
            files = FileTools(workflow, self.root / "files")
            try:
                gateway = ToolGateway(workflow, files, self.task, "writer", human="user", allowed=["create_text"])
                ready.wait(timeout=5)
                try:
                    return json.loads(gateway.dispatch(call())["content"])["ok"]
                except ToolRequestError:
                    return False
            finally:
                files.close()
                workflow.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(dispatch_once, range(2)))
        self.assertEqual(sorted(outcomes), [False, True])
        events = self.workflow.events(self.task, "user")
        self.assertEqual(sum(event["kind"] == "file_created" for event in events), 1)

    def test_memory_and_artifact_tools_route_to_scoped_real_backends(self):
        previous = self.workflow.create_task(self.chat, "user", "writer", "Earlier failure")
        self.workflow.start_task(previous, "writer")
        self.workflow.finish_task(previous, "writer", error="Text check failed")
        memory_id = self.memory.capture(previous, "writer", lesson="Check text before completion", tags=["text"])
        result = self.dispatch("search_memory", {"query": "text", "limit": 2}, "search")
        self.assertEqual(result["result"][0]["memory_id"], memory_id)
        self.assertTrue(self.dispatch("select_memory", {"memory_id": memory_id}, "select")["ok"])
        source = self.dispatch(identifier="write")["result"]
        child = self.dispatch("delegate_task", {"assignee": "reviewer", "title": "Review text"}, "delegate")["result"]["task_id"]
        offered = self.dispatch("offer_artifact", {"path": "note.txt", "target_task": child,
                                "expected_sha256": source["sha256"]}, "offer")["result"]
        self.workflow.start_task(child, "reviewer")
        recipient = ToolGateway(self.workflow, self.files, child, "reviewer", human="user", allowed=["accept_artifact"])
        received = json.loads(recipient.dispatch(call("accept_artifact", {
            "artifact_id": offered["artifact_id"], "path": "review.txt",
        }))["content"])
        self.assertEqual(received["result"]["sha256"], source["sha256"])
        self.assertEqual(self.files.read_text(child, "reviewer", "review.txt")["content"], "actual text")

    def test_missing_information_pauses_and_no_later_call_runs_until_answer(self):
        request = self.dispatch("ask_human", {"prompt": "Which filename?"})["result"]["request_id"]
        with self.assertRaises(ToolRequestError):
            self.dispatch(identifier="while-paused")
        self.workflow.respond(request, "user", answer="note.txt")
        self.assertTrue(self.dispatch(identifier="after-answer")["ok"])

    def test_delegation_is_bound_to_parent_and_eligible_agent(self):
        with self.assertRaises(ToolRequestError):
            self.dispatch("delegate_task", {"assignee": "user", "title": "bad"})
        result = self.dispatch("delegate_task", {"assignee": "reviewer", "title": "Check the output"})
        child = self.workflow.task(result["result"]["task_id"], "user")
        self.assertEqual(child["parent"], self.task)
        self.assertEqual(child["assignee"], "reviewer")
        self.assertEqual(child["chat"], self.chat)

    def test_paths_stale_hashes_and_memory_failures_remain_real_tool_failures(self):
        self.assertFalse(self.dispatch(arguments={"path": "../escape.txt", "content": "bad"})["ok"])
        self.assertFalse((self.root / "escape.txt").exists())
        self.dispatch(identifier="good")
        result = self.dispatch("update_text", {"path": "note.txt", "content": "bad", "expected_sha256": "0" * 64}, "stale")
        self.assertFalse(result["ok"])
        self.assertIn("digest", result["error"])
        self.assertEqual(self.dispatch("search_memory", {"query": "text", "limit": 2}, "memory")["result"], [])
        with self.assertRaises(ToolRequestError):
            self.dispatch("search_memory", {"query": "text", "limit": True}, "bad-limit")

    def test_message_after_intervening_pause_is_blocked_by_state_transaction(self):
        original = self.gateway._execute

        def pause_then_execute(name, arguments):
            self.workflow.ask_human(self.task, "writer", "user", "Clarify first")
            return original(name, arguments)

        with patch.object(self.gateway, "_execute", side_effect=pause_then_execute):
            result = self.dispatch("post_message", {"body": "should not be sent"})
        self.assertFalse(result["ok"])
        self.assertEqual(self.workflow.messages(self.chat, "user"), [])

    def test_protocol_fixture_is_explicit_and_success_requires_trusted_check(self):
        report = protocol_demo(self.root / "fixture")
        self.assertEqual(report["model_calls"], 0)
        self.assertEqual(report["api_network_calls"], 0)
        self.assertEqual(report["synthetic_protocol_responses"], 2)
        self.assertEqual(report["state_before_trusted_verification"], "running")
        self.assertFalse(report["benchmark_valid"])
        self.assertEqual(report["metrics"]["goals"]["succeeded"], 1)


if __name__ == "__main__":
    unittest.main()
