"""Versioned append writes a file in several responses (proposed 2026-11-18, pending owner merge).

Scripted replies only; no model capability is claimed.
"""

import json
import os
from pathlib import Path
import tempfile
import unittest

from agent_lab.core import Workflow, WorkflowError
from agent_lab.deepseek import DeepSeekClient
from agent_lab.evaluation.official_live import POLICIES
from agent_lab.files import FileTools
from agent_lab.gateway import ToolGateway
from agent_lab.inspection import ArtifactInspector
from agent_lab.runner import TaskRunner


def sha(data):
    import hashlib
    return hashlib.sha256(data.encode()).hexdigest()


class AppendText(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.workflow = Workflow(self.root / "state.sqlite3")
        self.addCleanup(self.workflow.close)
        for actor, kind in (("user", "human"), ("writer", "agent"), ("other", "agent")):
            self.workflow.register_actor(actor, kind)
        self.chat = self.workflow.create_chat("group", ["user", "writer", "other"])
        self.task = self.workflow.create_task(self.chat, "user", "writer", "Write")
        self.workflow.start_task(self.task, "writer")

    def files(self, **options):
        files = FileTools(self.workflow, self.root / "files", **options)
        self.addCleanup(files.close)
        return files

    def test_parts_append_in_order_with_version_checks(self):
        files = self.files()
        first = files.create_text(self.task, "writer", "doc.md", "# Title\n")
        second = files.append_text(self.task, "writer", "doc.md", "part one\n", expected_sha256=first["sha256"])
        third = files.append_text(self.task, "writer", "doc.md", "part two\n", expected_sha256=second["sha256"])
        content = "# Title\npart one\npart two\n"
        self.assertEqual(files.read_text(self.task, "writer", "doc.md")["content"], content)
        self.assertEqual((third["sha256"], third["bytes"]), (sha(content), len(content)))
        with self.assertRaises(WorkflowError):  # A stale version is refused and changes nothing.
            files.append_text(self.task, "writer", "doc.md", "late\n", expected_sha256=second["sha256"])
        with self.assertRaises(WorkflowError):  # Append never creates a file.
            files.append_text(self.task, "writer", "missing.md", "x", expected_sha256=sha(""))
        self.assertEqual(files.read_text(self.task, "writer", "doc.md")["content"], content)
        history = ArtifactInspector(self.workflow, files).history(self.task, "user")["doc.md"]
        writes = [entry for entry in history if entry["operation"] != "file_read"]
        self.assertEqual([entry["operation"] for entry in writes], ["file_created", "file_updated", "file_updated"])
        self.assertEqual(writes[-1]["sha256"], third["sha256"])  # Carry and offers see the current version.
        other = self.workflow.create_task(self.chat, "user", "other", "Receive")
        self.workflow.start_task(other, "other")
        files.offer_artifact(self.task, "writer", "doc.md", other, expected_sha256=third["sha256"])

    def test_combined_size_limit_and_isolation(self):
        files = self.files(max_bytes=32)
        first = files.create_text(self.task, "writer", "doc.md", "x" * 20)
        with self.assertRaises(WorkflowError):
            files.append_text(self.task, "writer", "doc.md", "y" * 20, expected_sha256=first["sha256"])
        self.assertEqual(files.read_text(self.task, "writer", "doc.md")["content"], "x" * 20)
        with self.assertRaises(WorkflowError):  # Another agent cannot write into this task's files.
            files.append_text(self.task, "other", "doc.md", "y", expected_sha256=first["sha256"])
        with self.assertRaises(WorkflowError):
            files.append_text(self.task, "writer", "../escape.md", "y", expected_sha256=first["sha256"])

    def test_symlinked_target_is_refused(self):
        files = self.files()
        files.create_text(self.task, "writer", "real.md", "real")
        task_dir = next((self.root / "files" / "tasks").iterdir())
        os.symlink(task_dir / "real.md", task_dir / "link.md")
        with self.assertRaises(WorkflowError):
            files.append_text(self.task, "writer", "link.md", "more", expected_sha256=sha("real"))
        self.assertEqual(files.read_text(self.task, "writer", "real.md")["content"], "real")

    def test_a_model_writes_a_file_larger_than_one_reply_in_parts(self):
        files = self.files()
        parts = [f"## Section {n}\n" + ("Dashboard summary text. " * 280) + "\n" for n in range(3)]
        sent = []

        def transport(payload):
            sent.append(json.loads(payload))
            done = sum(m["role"] == "tool" for m in sent[-1]["messages"])
            if done == 0:
                call = ("create_text", {"path": "dashboard.md", "content": parts[0]})
            elif done < len(parts):
                receipt = json.loads([m for m in sent[-1]["messages"] if m["role"] == "tool"][-1]["content"])
                call = ("append_text", {"path": "dashboard.md", "content": parts[done],
                                        "expected_sha256": receipt["result"]["sha256"]})
            else:
                return json.dumps({"id": "s", "model": "m", "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                    "total_tokens": 2}, "choices": [{"finish_reason": "stop",
                    "message": {"role": "assistant", "content": "Done."}}]}).encode()
            return json.dumps({"id": "r", "model": "m", "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                "total_tokens": 2}, "choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant",
                "content": None, "tool_calls": [{"id": f"c{done}", "type": "function", "function": {
                    "name": call[0], "arguments": json.dumps(call[1])}}]}}]}).encode()

        gateway = ToolGateway(self.workflow, files, self.task, "writer", human="user",
                              allowed=["create_text", "append_text"])
        self.assertIn("append_text", [tool["function"]["name"] for tool in gateway.tools()])
        TaskRunner(gateway, DeepSeekClient("synthetic", transport), mode="offline_fixture", constraints=[]).run()
        written = files.read_text(self.task, "writer", "dashboard.md")["content"]
        self.assertEqual(written, "".join(parts))
        self.assertGreater(len(written), 20000)
        self.assertTrue(all(len(part) < 8000 for part in parts))  # Each reply stays small.

    def test_truncation_notice_and_official_guidance_name_the_tool(self):
        for policy in POLICIES.values():
            self.assertIn("append_text", policy.tools)
        files = self.files()
        replies = [{"finish_reason": "length", "message": {"role": "assistant", "content": None}},
                   {"finish_reason": "stop", "message": {"role": "assistant", "content": "Done."}}]
        sent = []

        def transport(payload):
            sent.append(payload)
            return json.dumps({"id": "r", "model": "m", "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                "total_tokens": 2}, "choices": [replies.pop(0)]}).encode()

        gateway = ToolGateway(self.workflow, files, self.task, "writer", human="user",
                              allowed=["create_text", "append_text"])
        TaskRunner(gateway, DeepSeekClient("synthetic", transport), mode="offline_fixture", constraints=[]).run()
        self.assertIn(b"create_text then append_text", sent[1])


if __name__ == "__main__":
    unittest.main()
