"""Specific tool-argument errors (proposed 2026-11-19, pending owner review).

A live lead's two completion proposals carried 2,134 and 2,034-character summaries
against a 2,000 limit, saw only "Invalid string tool argument", and spent its last
requests. Scripted replies only; no model capability is claimed.
"""

import itertools
import json
from pathlib import Path
import tempfile
import unittest

from agent_lab.core import Workflow
from agent_lab.deepseek import DeepSeekClient
from agent_lab.files import FileTools
from agent_lab.gateway import ToolGateway, ToolRequestError
from agent_lab.runner import TaskRunner

_IDS = itertools.count()
SECRET = "synthetic-private-value"


def call(name, **arguments):
    return {"id": f"c{next(_IDS)}", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


def reply(*calls):
    return json.dumps({"id": "r", "model": "synthetic-arguments", "usage": {
        "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        "choices": [{"finish_reason": "tool_calls",
                     "message": {"role": "assistant", "content": None, "tool_calls": list(calls)}}]}).encode()


class ArgumentErrors(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.workflow = Workflow(Path(directory.name) / "state.sqlite3")
        self.addCleanup(self.workflow.close)
        self.files = FileTools(self.workflow, Path(directory.name) / "files")
        self.addCleanup(self.files.close)
        for actor, kind in (("user", "human"), ("lead", "agent")):
            self.workflow.register_actor(actor, kind)
        self.task = self.workflow.create_task(self.workflow.create_chat("group", ["user", "lead"]), "user", "lead", "Build")
        self.workflow.start_task(self.task, "lead")
        self.gateway = ToolGateway(self.workflow, self.files, self.task, "lead", human="user",
                                   allowed=["create_text", "update_text", "list_tasks", "submit_for_verification"])

    def refusal(self, name, **arguments):
        with self.assertRaises(ToolRequestError) as caught:
            self.gateway.validate_batch([call(name, **arguments)])
        return str(caught.exception)

    def test_the_live_oversized_summary_names_its_length_and_limit(self):
        for size in (2134, 2034):
            message = self.refusal("submit_for_verification", summary="x" * size)
            self.assertEqual(message, f"submit_for_verification: summary exceeds maximum length: {size:,} characters; "
                                      "limit: 2,000. Shorten the summary and retry. Keep detailed evidence in a task "
                                      "file and name that file in the summary. No call in this batch ran")
        self.gateway.validate_batch([call("submit_for_verification", summary="x" * 2000)])  # At the limit: fine.

    def test_other_rules_name_the_argument_but_never_echo_its_value(self):
        cases = {
            "'path' must not be empty": ("create_text", {"path": "   ", "content": SECRET}),
            "'expected_sha256' does not match its required format": (
                "update_text", {"path": "a.txt", "content": "x", "expected_sha256": SECRET}),
            "'limit' must be an integer from 1 to 64": ("list_tasks", {"limit": 65}),
            "'content' must be a string": ("create_text", {"path": "a.txt", "content": 7}),
        }
        for expected, (name, arguments) in cases.items():
            with self.subTest(expected=expected):
                message = self.refusal(name, **arguments)
                self.assertIn(expected, message)
                self.assertNotIn(SECRET, message)

    def test_a_proposal_resent_after_the_specific_error_is_accepted(self):
        sent = []

        def transport(payload):
            sent.append(json.loads(payload))
            errors = [json.loads(m["content"]).get("error", "") for m in sent[-1]["messages"] if m["role"] == "tool"]
            if not errors:
                return reply(call("submit_for_verification", summary="Delivered the booking tool. " + "detail " * 300))
            limit = int(errors[-1].split("limit: ")[1].split(".")[0].replace(",", ""))  # Actionable limit.
            return reply(call("submit_for_verification", summary="Delivered the booking tool."[:limit]))

        runner = TaskRunner(self.gateway, DeepSeekClient("synthetic-arguments", transport),
                            mode="offline_fixture", constraints=[])
        state = runner.run()
        self.assertEqual(len(sent), 2)
        first_error = json.loads([m for m in sent[1]["messages"] if m["role"] == "tool"][-1]["content"])["error"]
        self.assertIn("summary exceeds maximum length: 2,128 characters; limit: 2,000", first_error)
        self.assertEqual(state["runner_state"], "awaiting_verification")  # Its own proposal, for a human to review.
        self.assertEqual(self.workflow.task(self.task, "user")["state"], "running")


if __name__ == "__main__":
    unittest.main()
