"""The output-limit notice names what filled the response (proposed 2026-11-21, pending owner review).

Live Software Task 2 (2026-11-21): the lead, which has no file tools, hit the
4096-token output limit, was told to "split long documents across several
smaller files", hit it again twice and the task stopped. The notice now names
the cut-off tool call and its size, fits the role's tools, and records sizes
only. Scripted replies only; no model capability is claimed.
"""

import json
from pathlib import Path
import tempfile
import unittest

from agent_lab.core import Workflow
from agent_lab.deepseek import DeepSeekClient, TruncatedCompletion, truncation_shape
from agent_lab.files import FileTools
from agent_lab.gateway import ToolGateway
from agent_lab.runner import TaskRunner, output_limit_instruction

SECRET = "synthetic-private-brief"
LEAD_TOOLS = ["delegate_task", "post_message", "read_text", "submit_for_verification"]


def body(choice):
    return json.dumps({"id": "r", "model": "m", "usage": {"prompt_tokens": 5, "completion_tokens": 4096,
        "total_tokens": 4101}, "choices": [choice]}).encode()


def cut_off(*calls, reasoning=None):
    message = {"role": "assistant", "content": None,
               "tool_calls": [{"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": arguments}}
                              for i, (name, arguments) in enumerate(calls)]}
    if reasoning is not None:
        message["reasoning_content"] = reasoning
    return {"finish_reason": "length", "message": message}


def done():
    return {"finish_reason": "stop", "message": {"role": "assistant", "content": "Done."}}


class OutputLimitNotice(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.workflow = Workflow(Path(directory.name) / "state.sqlite3")
        self.addCleanup(self.workflow.close)
        self.files = FileTools(self.workflow, Path(directory.name) / "files")
        self.addCleanup(self.files.close)
        for actor, kind in (("user", "human"), ("lead", "agent"), ("dev", "agent")):
            self.workflow.register_actor(actor, kind)
        self.task = self.workflow.create_task(self.workflow.create_chat("group", ["user", "lead", "dev"]),
                                              "user", "lead", "Extend the booking system with a dashboard")
        self.workflow.start_task(self.task, "lead")

    def run_replies(self, allowed, *choices):
        replies, sent = list(choices), []

        def transport(payload):
            sent.append(json.loads(payload))
            return body(replies.pop(0))

        gateway = ToolGateway(self.workflow, self.files, self.task, "lead", human="user", allowed=allowed,
                              delegates=("dev",) if "delegate_task" in allowed else ())
        TaskRunner(gateway, DeepSeekClient("synthetic", transport), mode="offline_fixture", constraints=[]).run()
        notices = [json.loads(m["content"]) for p in sent for m in p["messages"]
                   if m["role"] == "user" and '"output_limit_notice"' in m["content"]]
        return sent, notices

    def test_the_live_lead_is_told_which_brief_was_too_long_not_to_split_files(self):
        brief = json.dumps({"assignee": "dev", "title": SECRET + " " + "x" * 15000})[:15000]
        sent, notices = self.run_replies(LEAD_TOOLS, cut_off(("delegate_task", brief)), done())
        self.assertEqual(len(sent), 2)  # The task continued after one truncation.
        (notice,) = {json.dumps(n, sort_keys=True) for n in notices}
        notice = json.loads(notice)
        text = notice["instruction"]
        self.assertIn("delegate_task with about 15,000 characters of arguments", text)
        self.assertIn("at most 4,096 characters", text)
        self.assertIn("You cannot write files", text)
        self.assertNotIn("smaller files", text)
        self.assertEqual(notice["cut_off"]["tool_calls"], [{"name": "delegate_task", "argument_chars": 15000}])
        (event,) = [json.loads(e["detail"]) for e in self.workflow.events(self.task, "user")
                    if e["kind"] == "output_limit_reached"]
        self.assertEqual(event["shape"]["tool_calls"][0]["argument_chars"], 15000)
        recorded = json.dumps([dict(e) for e in self.workflow.events(self.task, "user")]) + json.dumps(sent[1])
        self.assertNotIn(SECRET, recorded)  # Sizes only: the discarded brief is never stored or replayed.

    def test_a_file_writer_keeps_the_split_and_append_advice(self):
        _, notices = self.run_replies(["create_text", "append_text", "submit_for_verification"],
                                      cut_off(("create_text", "{\"path\": \"dashboard.html\", \"content\": \"" + "x" * 9000)),
                                      done())
        text = notices[0]["instruction"]
        self.assertIn("create_text with about 9,", text)
        self.assertIn("create_text then append_text", text)
        self.assertNotIn("You cannot write files", text)

    def test_reasoning_and_many_calls_are_named(self):
        reasoning = output_limit_instruction(truncation_shape({"reasoning_content": "r" * 12000}), LEAD_TOOLS)
        self.assertIn("about 12,000 characters reasoning before any tool call", reasoning)
        many = output_limit_instruction(truncation_shape({"tool_calls": [
            {"function": {"name": "read_text", "arguments": "{}"}}] * 6}), LEAD_TOOLS)
        self.assertIn("6 tool call(s)", many)
        self.assertIn("one or two tool calls per response", many)

    def test_the_shape_is_sizes_only_and_names_are_bounded(self):
        shape = truncation_shape({"content": SECRET, "reasoning_content": SECRET, "tool_calls": [
            {"function": {"name": "Not A Tool!", "arguments": SECRET}}, "junk", {"function": None}] + [{}] * 20})
        self.assertEqual(shape["tool_calls"][0], {"name": "unknown", "argument_chars": len(SECRET)})
        self.assertEqual(len(shape["tool_calls"]), 16)
        self.assertNotIn(SECRET, json.dumps(shape))
        client = DeepSeekClient("synthetic", lambda payload: body(cut_off(("delegate_task", SECRET))))
        with self.assertRaises(TruncatedCompletion) as caught:
            client.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(caught.exception.shape["tool_calls"], [{"name": "delegate_task",
                                                                  "argument_chars": len(SECRET)}])
        self.assertNotIn(SECRET, json.dumps(caught.exception.diagnostics()))


if __name__ == "__main__":
    unittest.main()
