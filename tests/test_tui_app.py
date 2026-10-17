"""Textual UI interaction checks. Skipped when the optional Textual dependency is absent."""

import asyncio
from pathlib import Path
import tempfile
import threading
import unittest

try:
    import textual  # noqa: F401
    HAVE_TEXTUAL = True
except ImportError:
    HAVE_TEXTUAL = False

from agent_lab.tui.controller import ControlCenter


async def settle(app, pilot, rounds=60):
    """Wait for thread workers (including replaced exclusive ones) to finish."""
    from textual.worker import WorkerCancelled, WorkerState
    for _ in range(rounds):
        try:
            await app.workers.wait_for_complete()
        except WorkerCancelled:
            pass
        await pilot.pause()
        if not [w for w in app.workers if w.state in (WorkerState.PENDING, WorkerState.RUNNING)]:
            return


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is optional; install requirements-tui.txt to run UI checks")
class ControlCenterAppTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.center = ControlCenter(Path(self.directory.name) / "session")

    def tearDown(self):
        self.center.close()
        self.directory.cleanup()

    def app(self):
        from agent_lab.tui.app import ControlCenterApp
        return ControlCenterApp(self.center, refresh_seconds=0)

    def pending(self, kind):
        return next(r for r in self.center.requests(pending_only=True) if r["kind"] == kind)

    async def select_request(self, app, pilot, request_id):
        from textual.widgets import DataTable
        table = app.panes["approvals"].query_one("#approvals-pending", DataTable)
        table.move_cursor(row=table.get_row_index(request_id))
        await settle(app, pilot)

    async def test_launch_shows_offline_mode_and_keyboard_navigation(self):
        app = self.app()
        async with app.run_test(size=(160, 48)) as pilot:
            await settle(app, pilot)
            self.assertEqual(app.header.status["mode"], "offline")
            self.assertIn("OFFLINE", str(app.header.render()))
            for key, tab in [("f3", "tasks"), ("ctrl+p", "approvals"), ("ctrl+l", "logs"), ("f1", "dashboard")]:
                await pilot.press(key)
                await settle(app, pilot)
                self.assertEqual(app.tabs.active, tab)
            await pilot.press("question_mark")
            await pilot.pause()
            self.assertEqual(type(app.screen).__name__, "HelpScreen")
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(type(app.screen).__name__, "Screen")

    async def test_run_scenario_and_answer_clarification_from_ui(self):
        from textual.widgets import Input
        app = self.app()
        async with app.run_test(size=(160, 48)) as pilot:
            await settle(app, pilot)
            dashboard = app.panes["dashboard"]
            dashboard.selected_scenario = "delegation"
            await pilot.click("#run-scenario")
            await settle(app, pilot)
            request = self.pending("clarification")
            await pilot.press("f6")
            await settle(app, pilot)
            await self.select_request(app, pilot, request["id"])
            await pilot.click("#approval-answer")
            await pilot.pause()
            self.assertEqual(type(app.screen).__name__, "TextPromptScreen")
            app.screen.query_one(Input).value = "English, with a newline"
            await pilot.press("enter")
            await settle(app, pilot)
            self.assertEqual(self.center.request_detail(request["id"])["status"], "answered")
            # Answering resumed the paused task and the scheduler finished the tree.
            self.assertEqual({t["state"] for t in self.center.tasks()}, {"succeeded"})

    async def test_approve_release_and_reject_through_modals(self):
        app = self.app()
        self.center.run_scenario("approval")
        self.center.run_scenario("approval")
        first, second = [r for r in self.center.requests(pending_only=True)]
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.press("ctrl+p")
            await settle(app, pilot)
            await self.select_request(app, pilot, first["id"])
            await pilot.click("#approval-approve")
            await pilot.pause()
            self.assertEqual(type(app.screen).__name__, "ConfirmScreen")
            self.assertIn("delete_text", str(app.screen.query_one("#confirm-parameters").render()))
            await pilot.press("escape")  # Cancelling records nothing.
            await settle(app, pilot)
            self.assertEqual(self.center.request_detail(first["id"])["status"], "pending")
            await pilot.click("#approval-approve")
            await pilot.pause()
            await pilot.click("#confirm")
            await settle(app, pilot)
            self.assertEqual(self.center.request_detail(first["id"])["status"], "granted_awaiting_release")
            await self.select_request(app, pilot, first["id"])
            await pilot.click("#approval-release")
            await pilot.pause()
            await pilot.click("#confirm")
            await settle(app, pilot)
            released = self.center.request_detail(first["id"])
            self.assertEqual((released["status"], released["outcome"]["kind"]), ("released", "file_deleted"))
            self.assertEqual(self.center.task_detail(first["task"])["task"]["state"], "succeeded")
            await self.select_request(app, pilot, second["id"])
            await pilot.click("#approval-reject")
            await pilot.pause()
            await pilot.click("#confirm")
            await settle(app, pilot)
            self.assertEqual(self.center.task_detail(second["task"])["task"]["state"], "cancelled")

    async def test_invalid_action_is_reported_and_app_keeps_running(self):
        app = self.app()
        self.center.run_scenario("approval")
        request = self.pending("approval")
        async with app.run_test(size=(160, 48)) as pilot:
            app.run_backend(lambda: self.center.release(request["id"]))
            await settle(app, pilot)
            messages = [n.message for n in app._notifications]
            self.assertTrue(any("only a current granted approval" in m for m in messages))
            await pilot.press("f3")
            await settle(app, pilot)
            self.assertEqual(app.tabs.active, "tasks")

    async def test_ui_stays_responsive_during_slow_backend_work(self):
        app = self.app()
        release = threading.Event()
        async with app.run_test(size=(160, 48)) as pilot:
            await settle(app, pilot)
            app.run_backend(lambda: self.center.call(lambda b: release.wait(5)), quiet=True)
            await pilot.press("f2")
            await pilot.pause()
            self.assertEqual(app.tabs.active, "conversations")  # Switched while backend is busy.
            release.set()
            await settle(app, pilot)

    async def test_new_conversation_message_and_task_dialogs(self):
        from textual.widgets import Checkbox, Input, Select
        app = self.app()
        async with app.run_test(size=(160, 48)) as pilot:
            await settle(app, pilot)
            await pilot.press("ctrl+n")
            await settle(app, pilot)
            self.assertEqual(type(app.screen).__name__, "NewConversationScreen")
            app.screen.query_one("#agent-writer", Checkbox).value = True
            await pilot.click("#create")
            await settle(app, pilot)
            chat = self.center.conversations()[0]
            self.assertEqual(sorted(m["id"] for m in chat["members"]), ["operator", "writer"])
            self.assertEqual(app.selected_chat, chat["id"])
            app.panes["conversations"].query_one("#message-input", Input).value = "hello writer"
            await pilot.click("#send-message")
            await settle(app, pilot)
            self.assertEqual([i["body"] for i in self.center.feed(chat["id"])], ["hello writer"])
            await pilot.press("ctrl+t")
            await settle(app, pilot)
            self.assertEqual(type(app.screen).__name__, "NewTaskScreen")
            app.screen.query_one("#task-agent", Select).value = "writer"
            app.screen.query_one("#task-title", Input).value = "Draft notes"
            await pilot.click("#create")
            await settle(app, pilot)
            task = self.center.tasks()[0]
            self.assertEqual((task["assignee"], task["state"]), ("writer", "pending"))
            self.assertTrue(any("will not" in n.message or "stays pending" in n.message for n in app._notifications))

    async def test_git_dashboard_shows_repository_and_verified_push(self):
        from textual.widgets import DataTable
        self.center.run_scenario("git")
        request = self.pending("approval")
        app = self.app()
        async with app.run_test(size=(170, 50)) as pilot:
            await pilot.press("ctrl+g")
            await settle(app, pilot)
            self.assertEqual(app.tabs.active, "git")
            pane = app.panes["git"]
            self.assertIn("agent/demo", str(pane.query_one("#git-summary").render()))
            self.assertIn("pending", str(pane.query_one("#git-pending", DataTable).get_row_at(0)[3]))
            await pilot.press("ctrl+p")
            await settle(app, pilot)
            await self.select_request(app, pilot, request["id"])
            await pilot.click("#approval-approve")
            await pilot.pause()
            self.assertIn("fast_forward_push", str(app.screen.query_one("#confirm-parameters").render()))
            await pilot.click("#confirm")
            await settle(app, pilot)
            await self.select_request(app, pilot, request["id"])
            await pilot.click("#approval-release")
            await pilot.pause()
            await pilot.click("#confirm")
            await settle(app, pilot)
            await pilot.press("ctrl+g")
            await settle(app, pilot)
            operations = pane.query_one("#git-operations", DataTable)
            self.assertIn("verified", str(operations.get_row_at(0)[2]))
            self.assertIn("remote branch verified", str(pane.query_one("#git-pending", DataTable).get_row_at(0)[3]))

    async def test_history_is_visible_after_restart(self):
        from textual.widgets import DataTable
        self.center.run_scenario("approval")
        request = self.pending("approval")
        self.center.decide(request["id"], False)
        path = self.center.state_dir
        self.center.close()
        self.center = ControlCenter(path)
        app = self.app()
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.press("f6")
            await settle(app, pilot)
            history = app.panes["approvals"].query_one("#approvals-history", DataTable)
            self.assertEqual(history.row_count, 1)
            self.assertIn("rejected", str(history.get_row(request["id"])[3]))


if __name__ == "__main__":
    unittest.main()
