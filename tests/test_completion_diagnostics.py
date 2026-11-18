"""Rejected completions are classified by a fixed label, never by their content.

Every completion here is synthetic. The labels describe which structural rule
refused a reply; they are not evidence about any live model.
"""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from agent_lab.core import Workflow
from agent_lab.deepseek import DeepSeekClient, FINISH_REASON_LABELS, PARSE_RULES, ProviderError
from agent_lab.files import FileTools
from agent_lab.gateway import ToolGateway
from agent_lab.hkgai import HKGAIClient
from agent_lab.runner import TaskRunner

SENTINEL = "synthetic-private-sentinel"
MESSAGE = "Invalid, incomplete, or unsupported provider completion; no tools released"
TOOLS = [{"type": "function", "function": {"name": "create_text", "parameters": {"type": "object"}}}]


def call(identifier="call-1"):
    return {"id": identifier, "type": "function", "function": {
        "name": "create_text", "arguments": json.dumps({"path": "note.txt", "content": SENTINEL})}}


def reply(*, calls=None, content=SENTINEL, reason=None):
    message = {"role": "assistant", "content": None if calls else content}
    if calls:
        message["tool_calls"] = calls
    return {"id": "synthetic-response", "model": "synthetic-model",
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            "choices": [{"finish_reason": reason or ("tool_calls" if calls else "stop"), "message": message}]}


def changed(edit, **options):
    value = reply(**options)
    edit(value)
    return value


def message_of(value):
    return value["choices"][0]["message"]


# One rejected synthetic completion per label: (reply, expected finish label, tool-call count, content present).
REJECTED = {
    "not_json": (b'{"id": "' + SENTINEL.encode() + b'", ', None, None, None),
    "missing_field": (changed(lambda v: v.pop("choices")), None, None, None),
    "choice_count": (changed(lambda v: v["choices"].append(copy.deepcopy(v["choices"][0]))), None, None, None),
    "finish_reason": (reply(calls=[call()], reason="length"), "length", 1, False),
    "role": (changed(lambda v: message_of(v).update(role="user")), "stop", 0, True),
    "content_type": (changed(lambda v: message_of(v).update(content=[SENTINEL])), "stop", 0, None),
    "reasoning_type": (changed(lambda v: message_of(v).update(reasoning_content=[SENTINEL])), "stop", 0, True),
    "tool_call_shape": (changed(lambda v: message_of(v)["tool_calls"][0].update(extra=SENTINEL), calls=[call()]),
                        "tool_calls", 1, False),
    "tool_call_limit": (reply(calls=[call(f"call-{n}") for n in range(17)]), "tool_calls", 17, False),
    "duplicate_tool_call_id": (reply(calls=[call(), call()]), "tool_calls", 2, False),
    "finish_reason_mismatch": (reply(calls=[call()], reason="stop"), "stop", 1, False),
    "required_tool_missing": (reply(), "stop", 0, True),
    "empty_text": (reply(content="  "), "stop", 0, False),
    "usage": (changed(lambda v: v["usage"].update(total_tokens=99)), "stop", 0, True),
    "identity": (changed(lambda v: v.update(model="")), "stop", 0, True),
}


def rejected(label, client=DeepSeekClient):
    body = REJECTED[label][0]
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    choice = "required" if label == "required_tool_missing" else "auto"
    try:
        client("synthetic-model", lambda payload: raw, tool_choice=choice).complete(
            [{"role": "user", "content": "Synthetic request"}], tools=TOOLS)
    except ProviderError as error:
        return error, raw
    raise AssertionError("Synthetic completion was accepted: " + label)


class CompletionClassification(unittest.TestCase):
    def test_every_rejection_path_has_its_own_fixed_label(self):
        self.assertEqual(set(REJECTED), set(PARSE_RULES) - {"other"})
        self.assertEqual(len(set(PARSE_RULES)), len(PARSE_RULES))
        for label, (_, finish, calls, content) in REJECTED.items():
            for client in (DeepSeekClient, HKGAIClient):
                with self.subTest(label=label, client=client.__name__):
                    error, raw = rejected(label, client)
                    record = error.diagnostics()
                    self.assertEqual(str(error), MESSAGE)
                    self.assertEqual((record["kind"], record["phase"]), ("invalid_completion", "parsing"))
                    self.assertEqual(record["response_bytes"], len(raw))
                    self.assertTrue(record["request_may_have_been_processed"])
                    self.assertFalse(record["automatic_retry"])
                    self.assertEqual(record["completion_check"], {
                        "parse_rule": label, "finish_reason": finish, "tool_calls": calls, "content_present": content})
                    self.assertNotIn(SENTINEL, str(error) + json.dumps(record))

    def test_unknown_or_malformed_finish_reasons_are_never_copied(self):
        for value, expected in ((SENTINEL, "other"), (7, "invalid"), (None, "invalid"), ([SENTINEL], "invalid"),
                                ("content_filter", "content_filter"), ("function_call", "function_call")):
            body = json.dumps(reply(reason="stop") | {"choices": [
                {"finish_reason": value, "message": {"role": "assistant", "content": SENTINEL}}]}).encode()
            with self.assertRaises(ProviderError) as caught:
                DeepSeekClient("synthetic-model", lambda payload: body).complete([{"role": "user", "content": "x"}])
            record = caught.exception.diagnostics()
            self.assertEqual((record["completion_check"]["parse_rule"], record["completion_check"]["finish_reason"]),
                             ("finish_reason", expected))
            self.assertNotIn(SENTINEL, json.dumps(record))

    def test_diagnostics_are_a_defensive_copy(self):
        error, _ = rejected("usage")
        record = error.diagnostics()
        record["completion_check"]["parse_rule"] = "changed"
        record["kind"] = "changed"
        self.assertEqual(error.diagnostics()["completion_check"]["parse_rule"], "usage")
        self.assertEqual(error.diagnostics()["kind"], "invalid_completion")

    def test_valid_completions_are_accepted_unchanged(self):
        text = DeepSeekClient("synthetic-model", lambda payload: json.dumps(reply()).encode()).complete(
            [{"role": "user", "content": "x"}])
        self.assertEqual((text.finish_reason, text.message), ("stop", {"role": "assistant", "content": SENTINEL}))
        self.assertEqual(text.usage, {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5})
        tools = DeepSeekClient("synthetic-model", lambda payload: json.dumps(reply(calls=[call()])).encode(),
                               tool_choice="required").complete([{"role": "user", "content": "x"}], tools=TOOLS)
        self.assertEqual((tools.finish_reason, tools.message["tool_calls"]), ("tool_calls", [call()]))
        self.assertEqual((tools.response_id, tools.model), ("synthetic-response", "synthetic-model"))

    def test_only_bounded_labels_are_accepted_as_a_check(self):
        good = {"parse_rule": "usage", "finish_reason": "stop", "tool_calls": 0, "content_present": True}
        self.assertEqual(ProviderError("x", kind="invalid_completion", phase="parsing",
                                       completion_check=good).diagnostics()["completion_check"], good)
        self.assertNotIn("completion_check", ProviderError("x", kind="invalid_completion").diagnostics())
        self.assertIn("other", PARSE_RULES)
        self.assertEqual(set(FINISH_REASON_LABELS), {"stop", "tool_calls", "length", "content_filter", "function_call"})
        for bad in (good | {"parse_rule": SENTINEL}, good | {"finish_reason": SENTINEL}, good | {"extra": 1},
                    good | {"tool_calls": -1}, good | {"tool_calls": True}, good | {"content_present": "yes"},
                    {key: value for key, value in good.items() if key != "tool_calls"}, "usage", [good]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                ProviderError("x", kind="invalid_completion", phase="parsing", completion_check=bad)
        with self.assertRaises(ValueError):  # Only a rejected completion carries a check.
            ProviderError("x", kind="timeout", phase="reading", completion_check=good)


class TruncatedReplyStopsTheTask(unittest.TestCase):
    def test_length_reply_fails_once_without_releasing_its_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = Workflow(root / "state.sqlite3")
            self.addCleanup(workflow.close)
            for actor, kind in (("user", "human"), ("writer", "agent")):
                workflow.register_actor(actor, kind)
            chat = workflow.create_chat("group", ["user", "writer"])
            task = workflow.create_task(chat, "user", "writer", "Write note.txt")
            workflow.start_task(task, "writer")
            files = FileTools(workflow, root / "files")
            self.addCleanup(files.close)
            requests = []

            def transport(payload):
                requests.append(payload)
                return json.dumps(reply(calls=[call()], reason="length")).encode()

            runner = TaskRunner(ToolGateway(workflow, files, task, "writer", human="user", allowed=["create_text"]),
                                DeepSeekClient("synthetic-model", transport, max_tokens=128),
                                mode="offline_fixture", constraints=[])
            state = runner.run()
            self.assertEqual(len(requests), 1)
            self.assertEqual((state["task_state"], state["unknown_usage_attempts"]), ("failed", 1))
            detail = json.loads(workflow.db.execute(
                "SELECT detail FROM events WHERE task=? AND kind='provider_request_failed'", (task,)).fetchone()[0])
            self.assertEqual(detail["diagnostics"]["completion_check"], {
                "parse_rule": "finish_reason", "finish_reason": "length", "tool_calls": 1, "content_present": False})
            self.assertEqual(workflow.db.execute("SELECT count(*) FROM tool_calls").fetchone()[0], 0)
            self.assertEqual([p for p in (root / "files").rglob("*") if p.is_file()], [])
            stored = "".join(str(value) for table in ("events", "runner_turns", "runner_sessions")
                             for row in workflow.db.execute(f"SELECT * FROM {table}") for value in tuple(row))
            self.assertNotIn(SENTINEL, stored)


if __name__ == "__main__":
    unittest.main()
