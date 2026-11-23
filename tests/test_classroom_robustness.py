"""Classroom robustness found in a timed rehearsal on 2026-11-23 (proposed).

1. A writer twice used all 8,192 output tokens resending a whole document through
   update_text: replace_text changes one exact passage of the known version.
2. Two HTTP 504s left the goal provider_uncertain with no UI action: the control
   center and the role-package menu now offer one explicit, counted resend.
3. Both classroom paths select streamed replies.
Scripted transports only; no model capability is claimed.
"""
import hashlib
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from scripts import classroom as c
from agent_lab import Workflow
from agent_lab.core import WorkflowError
from agent_lab.deepseek import ProviderError
from agent_lab.evaluation import official_live
from agent_lab.files import FileToolError, FileTools
from agent_lab.gateway import FIX_TOOLS, ToolGateway, ToolRequestError
from agent_lab.hkgai import HKGAIHTTP
from agent_lab.runner import FILE_WRITERS, output_limit_instruction
from agent_lab.runtime import LiveConfig, live_members, live_roles
from agent_lab.tui.controller import ControlCenter, ControllerError


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


DOC = "# Guide\n\n## Install\nRun setup.\n\n## Usage\nOld usage text.\n"


class ReplaceTextTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.workflow = Workflow(Path(directory.name) / "state.sqlite3")
        self.addCleanup(self.workflow.close)
        for actor, kind in (("user", "human"), ("writer", "agent")):
            self.workflow.register_actor(actor, kind)
        self.task = self.workflow.create_task(self.workflow.create_chat("group", ["user", "writer"]), "user", "writer", "Guide")
        self.workflow.start_task(self.task, "writer")
        self.files = FileTools(self.workflow, Path(directory.name) / "files")
        self.addCleanup(self.files.close)
        self.files.create_text(self.task, "writer", "GUIDE.md", DOC)

    def read(self):
        return self.files.read_text(self.task, "writer", "GUIDE.md")["content"]

    def test_one_exact_passage_is_replaced_and_recorded_as_an_update(self):
        receipt = self.files.replace_text(self.task, "writer", "GUIDE.md", "Old usage text.", "python3 app.py --help",
                                          expected_sha256=sha(DOC))
        expected = DOC.replace("Old usage text.", "python3 app.py --help")
        self.assertEqual(self.read(), expected)
        self.assertEqual(receipt["sha256"], sha(expected))
        last = [e for e in self.workflow.events(self.task, "user") if e["kind"] == "file_updated"][-1]
        self.assertEqual(json.loads(last["detail"])["sha256"], sha(expected))
        # Deleting a passage is allowed.
        self.files.replace_text(self.task, "writer", "GUIDE.md", "\n## Install\nRun setup.\n", "",
                                expected_sha256=sha(expected))
        self.assertNotIn("Install", self.read())

    def test_stale_missing_ambiguous_or_empty_passages_change_nothing(self):
        cases = [("Old usage text.", "x", sha("other"), "did not match"),
                 ("Not in the file", "x", sha(DOC), "not found"),
                 ("## ", "x", sha(DOC), "occurs 2 times"),
                 ("", "x", sha(DOC), "nonempty")]
        for old, new, digest, message in cases:
            with self.assertRaisesRegex(FileToolError, message):
                self.files.replace_text(self.task, "writer", "GUIDE.md", old, new, expected_sha256=digest)
        self.assertEqual(self.read(), DOC)
        with self.assertRaises(FileToolError):
            self.files.replace_text(self.task, "writer", "GUIDE.md", "Old usage text.", "x" * (self.files.max_bytes + 1),
                                    expected_sha256=sha(DOC))
        self.assertEqual(self.read(), DOC)

    def test_gateway_offers_validates_and_dispatches_it(self):
        gateway = ToolGateway(self.workflow, self.files, self.task, "writer", human="user",
                              allowed=["replace_text", "read_text"], max_calls=8)
        spec = next(t["function"] for t in gateway.tools() if t["function"]["name"] == "replace_text")
        self.assertEqual(set(spec["parameters"]["required"]), {"path", "old_text", "new_text", "expected_sha256"})

        def call(identifier, **arguments):
            return {"id": identifier, "type": "function", "function": {"name": "replace_text", "arguments": json.dumps(
                {"path": "GUIDE.md", "expected_sha256": sha(DOC), **arguments})}}
        with self.assertRaises(ToolRequestError):
            gateway.validate_batch([call("bad", old_text="", new_text="x")])
        done = json.loads(gateway.dispatch(call("ok", old_text="Old usage text.", new_text="New."))["content"])
        self.assertTrue(done["ok"])
        self.assertIn("New.", self.read())
        self.assertIn("replace_text", FIX_TOOLS & FILE_WRITERS)

    def test_cutoff_notice_points_to_replace_text_only_when_allowed(self):
        shape = {"tool_calls": [{"name": "update_text", "argument_chars": 2}], "content_chars": 0, "reasoning_chars": 0}
        self.assertIn("replace_text", output_limit_instruction(shape, ["create_text", "update_text", "replace_text"], 8192))
        self.assertNotIn("replace_text", output_limit_instruction(shape, ["create_text", "update_text"], 8192))


class RoleToolTests(unittest.TestCase):
    def config(self, profile):
        return LiveConfig(model="m", api_key="k", provider="hkgai", execution_profile=profile,
                          docker_host="unix:///tmp/none.sock", python_image="python@sha256:" + "a" * 64)

    def test_quality_default_team_can_append_and_replace_and_legacy_is_unchanged(self):
        for profile, expected in (("quality", True), ("legacy", False)):
            config = self.config(profile)
            roles = live_roles(live_members(config), config)
            for agent in ("writer", "editor", "coder"):
                tools = set(roles[agent].tools)
                self.assertEqual({"append_text", "replace_text"} <= tools, expected, (profile, agent))
            self.assertNotIn("replace_text", roles["researcher"].tools)  # No update_text, no new write tool.

    def test_official_quality_roles_get_replace_text_without_changing_the_legacy_policy(self):
        tools = official_live.TOOLS
        self.assertNotIn("replace_text", tools)
        self.assertIn("replace_text", official_live.tools_for_role("software-engineering", "dev", tools,
                                                                    execution_profile="quality"))
        self.assertEqual(official_live.tools_for_role("software-engineering", "dev", tools), tools)
        self.assertFalse({"create_text", "update_text", "append_text", "replace_text"}
                         & set(official_live.tools_for_role("software-engineering", "lead", tools)))


class ClassroomStreamingAndResendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.bind(str(self.base / "docker.sock"))
        self.addCleanup(self.sock.close)
        self.config = {"model": "test-no-real-provider", "key_env": "CLASSROOM_TEST_KEY", "credential_file": "not-used",
                       "docker_host": "unix://" + str(self.base / "docker.sock"), "python_image": "python@sha256:" + "a" * 64}
        for p in (patch.dict("os.environ", {"CLASSROOM_TEST_KEY": "synthetic-test-key"}),
                  patch.object(c, "LOCAL", self.base / "local")):
            p.start(); self.addCleanup(p.stop)

    def test_both_classroom_paths_select_streaming(self):
        self.assertTrue(c.live(self.config).stream_responses)
        source = Path(c.__file__).read_text()
        self.assertIn("'--stream-responses'", source)
        parser_flags = official_live.runtime_config.__code__.co_varnames
        self.assertIn("stream_responses", parser_flags)

    def test_a_504_can_be_resent_once_from_the_control_center_and_the_goal_continues(self):
        goal = self.base / "teacher.txt"
        goal.write_text("Write a short note.\n")
        directory = c.import_text(self.config, goal)
        task = json.loads((directory / "session.json").read_text())["task"]

        def write(path):
            call = {"id": "w1", "type": "function", "function": {"name": "create_text", "arguments": json.dumps(
                {"path": path, "content": "after resend"})}}
            return json.dumps({"id": "r", "model": "synthetic", "usage": {"prompt_tokens": 5, "completion_tokens": 2,
                "total_tokens": 7}, "choices": [{"finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": None, "tool_calls": [call]}}]}).encode()

        gateway_504 = ProviderError("Provider HTTP status 504; no automatic retry", kind="http_status", phase="opening",
                                    request_bytes=10, http_status=504)
        steps = [gateway_504, write("note.txt"), gateway_504]
        sent = []

        def transport(payload):
            sent.append(payload)
            step = steps.pop(0)
            if isinstance(step, Exception):
                raise step
            return step

        center = ControlCenter(directory / "state", human="operator", live=c.live(self.config))
        self.addCleanup(center.close)
        with patch.object(HKGAIHTTP, "__call__", side_effect=transport):
            first = center.advance(task)
            self.assertIn("provider_uncertain", json.dumps(first["needs"]))
            with self.assertRaises(ControllerError):
                center.resend(task, "   ")
            center.resend(task, "HTTP 504; network restored")
            with self.assertRaises(WorkflowError):
                center.resend(task, "again")  # Only once per failure: the runner is ready, not uncertain.
            center.advance(task)
        self.assertEqual(len(sent), 3)  # 504, resent write, second 504: no automatic retry.
        self.assertEqual(center.read_file(task, "note.txt")["content"], "after resend")
        events = [e["kind"] for e in center.recent_events()]
        self.assertIn("provider_resend_released", events)


try:
    import textual  # noqa: F401
    HAVE_TEXTUAL = True
except ImportError:
    HAVE_TEXTUAL = False


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is optional; install requirements-tui.txt to run UI checks")
class ResendButtonTests(unittest.IsolatedAsyncioTestCase):
    async def test_resend_needs_a_typed_reason_then_resends_once_and_advances(self):
        from unittest.mock import MagicMock
        from textual.widgets import Input
        from agent_lab.tui.app import ControlCenterApp
        from test_tui_app import settle
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        center = ControlCenter(Path(directory.name) / "session")
        self.addCleanup(center.close)
        center.resend = MagicMock(return_value={"runner_state": "ready"})
        center.advance = MagicMock(return_value={"state": "blocked", "task_state": "running"})
        app = ControlCenterApp(center, refresh_seconds=0)
        async with app.run_test(size=(160, 48)) as pilot:
            await settle(app, pilot)
            await pilot.press("f3")
            await settle(app, pilot)
            app.selected_task = "synthetic-task"
            await pilot.click("#task-resend")
            await pilot.pause()
            self.assertEqual(type(app.screen).__name__, "TextPromptScreen")
            await pilot.click("#cancel")  # Cancelling sends nothing.
            await settle(app, pilot)
            center.resend.assert_not_called()
            await pilot.click("#task-resend")
            await pilot.pause()
            app.screen.query_one(Input).value = "HTTP 504; network restored"
            await pilot.press("enter")
            await settle(app, pilot)
        center.resend.assert_called_once_with("synthetic-task", "HTTP 504; network restored")
        center.advance.assert_called_once_with("synthetic-task")


if __name__ == "__main__":
    unittest.main()
