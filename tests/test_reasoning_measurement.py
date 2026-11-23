"""HKGAI reasoning is measured where HKGAI reports it (proposed 2026-11-23).

A two-request HKGAI probe on 2026-11-23 returned hidden reasoning under the
message's `reasoning` field and usage.completion_tokens_details.reasoning_tokens
(818 of 975 completion tokens), never `reasoning_content`. Cut-off shapes
therefore always reported zero reasoning. Measurement only: request options,
thinking, budgets and acceptance are unchanged. Scripted replies only.
"""

import json
from pathlib import Path
import tempfile
import unittest

from agent_lab.core import Workflow
from agent_lab.files import FileTools
from agent_lab.gateway import ToolGateway
from agent_lab.runner import TaskRunner

from agent_lab.deepseek import DeepSeekClient, TruncatedCompletion, reported_reasoning_tokens, truncation_shape
from agent_lab.hkgai import HKGAIClient
from agent_lab.runner import output_limit_instruction

SECRET = "synthetic-private-reasoning"


def reply(finish, message, details=None):
    usage = {"prompt_tokens": 10, "completion_tokens": 4096, "total_tokens": 4106}
    if details is not None:
        usage["completion_tokens_details"] = details
    return json.dumps({"id": "r", "model": "m", "usage": usage,
                       "choices": [{"finish_reason": finish, "message": message}]}).encode()


class ReasoningMeasurementTests(unittest.TestCase):
    def test_hkgai_reasoning_field_and_reported_tokens_reach_the_cutoff_shape(self):
        sent = []
        client = HKGAIClient("synthetic", lambda payload: sent.append(json.loads(payload)) or reply(
            "length", {"role": "assistant", "content": "", "reasoning": SECRET * 10},
            {"reasoning_tokens": 4000}))
        with self.assertRaises(TruncatedCompletion) as caught:
            client.complete([{"role": "user", "content": "hi"}])
        shape = caught.exception.shape
        self.assertEqual((shape["reasoning_chars"], shape["reasoning_tokens"]), (len(SECRET) * 10, 4000))
        self.assertNotIn(SECRET, json.dumps(shape))
        self.assertNotIn(SECRET, json.dumps(caught.exception.diagnostics()))
        # Thinking is not switched off: HKGAI still sends no thinking option.
        self.assertNotIn("thinking", sent[0])
        self.assertNotIn("chat_template_kwargs", sent[0])

    def test_notice_names_reasoning_from_either_field_or_reported_tokens_only(self):
        tools = ["create_text", "append_text", "submit_for_verification"]
        by_field = output_limit_instruction(truncation_shape({"reasoning": "r" * 9000}), tools, 4096)
        self.assertIn("reasoning (about 9,000 characters) before any tool call", by_field)
        by_tokens = output_limit_instruction(truncation_shape({}, {"completion_tokens_details": {
            "reasoning_tokens": 4096}}), tools, 4096)
        self.assertIn("reasoning (4,096 reported reasoning tokens) before any tool call", by_tokens)
        neither = output_limit_instruction(truncation_shape({}), tools, 4096)
        self.assertIn("without completing a tool call", neither)
        # DeepSeek's field still wins when present.
        both = truncation_shape({"reasoning_content": "a" * 5, "reasoning": "b" * 50})
        self.assertEqual(both["reasoning_chars"], 5)

    def test_malformed_or_absent_reports_are_ignored(self):
        for usage in (None, {}, {"completion_tokens_details": None}, {"completion_tokens_details": {}},
                      {"completion_tokens_details": {"reasoning_tokens": -1}},
                      {"completion_tokens_details": {"reasoning_tokens": "818"}},
                      {"completion_tokens_details": {"reasoning_tokens": True}}):
            self.assertIsNone(reported_reasoning_tokens(usage))
        self.assertEqual(reported_reasoning_tokens({"completion_tokens_details": {"reasoning_tokens": 0}}), 0)

    def test_completed_replies_report_reasoning_without_changing_strict_usage(self):
        message = {"role": "assistant", "content": "done", "reasoning": SECRET}
        result = HKGAIClient("synthetic", lambda payload: reply("stop", message, {"reasoning_tokens": 818})).complete(
            [{"role": "user", "content": "hi"}])
        self.assertEqual(result.reasoning_tokens, 818)
        self.assertEqual(set(result.usage), {"prompt_tokens", "completion_tokens", "total_tokens"})
        self.assertNotIn("reasoning", result.message)  # The hidden text is not echoed back into the transcript.
        plain = DeepSeekClient("synthetic", lambda payload: reply("stop", {"role": "assistant", "content": "ok"})
                               ).complete([{"role": "user", "content": "hi"}])
        self.assertIsNone(plain.reasoning_tokens)


class RunnerRecordsReasoningTests(unittest.TestCase):
    def test_cutoff_event_and_received_turn_keep_reasoning_sizes_only(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        workflow = Workflow(Path(directory.name) / "state.sqlite3")
        self.addCleanup(workflow.close)
        files = FileTools(workflow, Path(directory.name) / "files")
        self.addCleanup(files.close)
        for actor, kind in (("user", "human"), ("lead", "agent")):
            workflow.register_actor(actor, kind)
        task = workflow.create_task(workflow.create_chat("group", ["user", "lead"]), "user", "lead", "Report briefly")
        workflow.start_task(task, "lead")
        replies = [reply("length", {"role": "assistant", "content": "", "reasoning": SECRET * 20},
                         {"reasoning_tokens": 4096}),
                   reply("stop", {"role": "assistant", "content": "Done.", "reasoning": SECRET},
                         {"reasoning_tokens": 300})]
        sent = []

        def transport(payload):
            sent.append(json.loads(payload))
            return replies.pop(0)

        gateway = ToolGateway(workflow, files, task, "lead", human="user", allowed=["submit_for_verification"])
        TaskRunner(gateway, HKGAIClient("synthetic", transport), mode="offline_fixture", constraints=[]).run()
        (event,) = [json.loads(e["detail"]) for e in workflow.events(task, "user") if e["kind"] == "output_limit_reached"]
        self.assertEqual((event["shape"]["reasoning_chars"], event["shape"]["reasoning_tokens"]),
                         (len(SECRET) * 20, 4096))
        notice = next(m["content"] for m in sent[1]["messages"] if '"output_limit_notice"' in m["content"])
        self.assertIn("reasoning (about", json.loads(notice)["instruction"])
        received = [json.loads(row["response"]) for row in workflow.db.execute(
            "SELECT response FROM runner_turns WHERE task=? AND status!='calling' AND response IS NOT NULL", (task,))]
        self.assertIn(300, [r.get("reasoning_tokens") for r in received])
        stored = json.dumps([dict(e) for e in workflow.events(task, "user")]) + json.dumps(received) + json.dumps(sent)
        self.assertNotIn(SECRET, stored)  # Hidden reasoning text is neither stored nor sent back.


if __name__ == "__main__":
    unittest.main()
