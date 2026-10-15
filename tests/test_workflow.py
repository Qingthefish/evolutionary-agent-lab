from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import threading
import unittest

from agent_lab import Workflow, WorkflowError
from agent_lab.__main__ import demo


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / "state.sqlite3"
        self.now = 1000.0
        self.store = Workflow(self.database, clock=lambda: self.now)
        for actor, kind in [("human", "human"), ("other-human", "human"),
                            ("planner", "agent"), ("writer", "agent"), ("outsider", "agent")]:
            self.store.register_actor(actor, kind)
        self.chat = self.store.create_chat("group", ["human", "other-human", "planner", "writer"])
        self.action = {"tool": "git.push", "repository": "test", "branch": "feature", "commit": "abc"}

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def running_task(self, agent="planner"):
        task = self.store.create_task(self.chat, "human", agent, "Test task")
        self.store.start_task(task, agent)
        return task

    def approved_request(self, task):
        request = self.store.ask_human(task, "planner", "human", "Push exact commit?", action=self.action)
        self.store.respond(request, "human", approve=True)
        return request

    def test_private_conversation_blocks_group_members_and_outsiders(self):
        private = self.store.create_chat("private", ["human", "planner"])
        self.store.post_message(private, "human", "Private information")
        self.assertEqual(self.store.messages(private, "planner")[0]["body"], "Private information")
        for actor in ["writer", "outsider"]:
            with self.assertRaises(WorkflowError):
                self.store.messages(private, actor)
            with self.assertRaises(WorkflowError):
                self.store.post_message(private, actor, "Injected message")

    def test_private_chat_requires_exactly_one_human_and_one_agent(self):
        for actors in [["planner", "writer"], ["human", "other-human"], ["human", "planner", "writer"]]:
            with self.assertRaises(WorkflowError):
                self.store.create_chat("private", actors)

    def test_actor_identity_kind_is_immutable(self):
        with self.assertRaises(WorkflowError):
            self.store.register_actor("planner", "human")

    def test_nonmembers_cannot_read_tasks_requests_events_or_metrics(self):
        task = self.running_task()
        request = self.store.ask_human(task, "planner", "human", "Which output?")
        operations = [lambda: self.store.task(task, "outsider"),
                      lambda: self.store.request(request, "outsider"),
                      lambda: self.store.events(task, "outsider"),
                      lambda: self.store.metrics(self.chat, "outsider")]
        for operation in operations:
            with self.assertRaises(WorkflowError):
                operation()

    def test_only_assigned_agent_can_start_or_complete(self):
        task = self.store.create_task(self.chat, "human", "planner", "Task")
        with self.assertRaises(WorkflowError):
            self.store.start_task(task, "writer")
        self.store.start_task(task, "planner")
        with self.assertRaises(WorkflowError):
            self.store.finish_task(task, "writer", checks={"verified": True})

    def test_agent_delegation_tracks_parent_and_blocks_early_parent_success(self):
        parent = self.running_task()
        child = self.store.create_task(self.chat, "planner", "writer", "Child", parent=parent)
        with self.assertRaises(WorkflowError):
            self.store.finish_task(parent, "planner", checks={"verified": True})
        self.store.start_task(child, "writer")
        self.store.finish_task(child, "writer", checks={"output_matches": True})
        self.store.finish_task(parent, "planner", checks={"children_verified": True})
        self.assertEqual(self.store.task(child, "human")["parent"], parent)
        self.assertEqual(self.store.task(parent, "human")["state"], "succeeded")

    def test_delegation_cannot_hijack_another_agents_parent(self):
        parent = self.running_task()
        with self.assertRaises(WorkflowError):
            self.store.create_task(self.chat, "writer", "planner", "Hijack", parent=parent)
        with self.assertRaises(WorkflowError):
            self.store.create_task(self.chat, "planner", "writer", "Agent root")

    def test_grandchild_can_be_delegated_by_a_specialist(self):
        parent = self.running_task()
        child = self.store.create_task(self.chat, "planner", "writer", "Child", parent=parent)
        self.store.start_task(child, "writer")
        grandchild = self.store.create_task(self.chat, "writer", "planner", "Review", parent=child)
        self.assertEqual(self.store.task(grandchild, "human")["parent"], child)

    def test_clarification_survives_restart_and_cannot_be_answered_by_wrong_human(self):
        task = self.running_task()
        request = self.store.ask_human(task, "planner", "human", "Which branch?")
        self.store.close()
        self.now += 20
        self.store = Workflow(self.database, clock=lambda: self.now)
        with self.assertRaises(WorkflowError):
            self.store.respond(request, "other-human", answer="main")
        with self.assertRaises(WorkflowError):
            self.store.finish_task(task, "planner", checks={"verified": True})
        self.store.respond(request, "human", answer="feature")
        self.assertEqual(self.store.task(task, "human")["state"], "running")
        self.assertEqual(self.store.request(request, "planner")["response"], "feature")
        self.assertEqual(self.store.task(task, "human")["wait_seconds"], 20)
        with self.assertRaises(WorkflowError):
            self.store.respond(request, "human", answer="different")

    def test_approval_requires_boolean_and_cannot_be_self_granted(self):
        task = self.running_task()
        request = self.store.ask_human(task, "planner", "human", "Proceed?", action=self.action)
        with self.assertRaises(WorkflowError):
            self.store.respond(request, "planner", approve=True)
        for invalid in ["yes", 1, None]:
            with self.assertRaises(WorkflowError):
                self.store.respond(request, "human", approve=invalid)
        self.assertEqual(self.store.task(task, "human")["state"], "waiting_approval")

    def test_approval_cannot_release_before_human_response(self):
        task = self.running_task()
        request = self.store.ask_human(task, "planner", "human", "Proceed?", action=self.action)
        with self.assertRaises(WorkflowError):
            self.store.consume_approval(request, "planner", self.action)

    def test_approval_binds_exact_action_and_is_single_use_across_restart(self):
        task = self.running_task()
        request = self.approved_request(task)
        for replacement in [dict(self.action, branch="main"), dict(self.action, commit="changed")]:
            with self.assertRaises(WorkflowError):
                self.store.consume_approval(request, "planner", replacement)
        with self.assertRaises(WorkflowError):
            self.store.finish_task(task, "planner", checks={"verified": True})
        self.store.close()
        self.store = Workflow(self.database, clock=lambda: self.now)
        self.assertEqual(self.store.consume_approval(request, "planner", self.action), self.action)
        with self.assertRaises(WorkflowError):
            self.store.consume_approval(request, "planner", self.action)

    def test_approval_becomes_stale_after_another_human_request(self):
        task = self.running_task()
        old = self.approved_request(task)
        question = self.store.ask_human(task, "planner", "human", "A new requirement?")
        self.store.respond(question, "human", answer="Use a different approach")
        with self.assertRaises(WorkflowError):
            self.store.consume_approval(old, "planner", self.action)
        fresh = self.approved_request(task)
        self.store.consume_approval(fresh, "planner", self.action)
        self.store.finish_task(task, "planner", checks={"verified": True})

    def test_denial_cancels_descendants_and_invalidates_their_requests(self):
        parent = self.running_task()
        child = self.store.create_task(self.chat, "planner", "writer", "Child", parent=parent)
        self.store.start_task(child, "writer")
        question = self.store.ask_human(child, "writer", "human", "Which format?")
        request = self.store.ask_human(parent, "planner", "human", "Proceed?", action=self.action)
        self.store.respond(request, "human", approve=False)
        for task in [parent, child]:
            self.assertEqual(self.store.task(task, "human")["state"], "cancelled")
        with self.assertRaises(WorkflowError):
            self.store.respond(question, "human", answer="txt")
        with self.assertRaises(WorkflowError):
            self.store.consume_approval(request, "planner", self.action)

    def test_parent_failure_cancels_running_descendants_and_pending_actions(self):
        parent = self.running_task()
        child = self.store.create_task(self.chat, "planner", "writer", "Child", parent=parent)
        self.store.start_task(child, "writer")
        self.store.finish_task(parent, "planner", error="Execution budget exhausted")
        self.assertEqual(self.store.task(child, "human")["state"], "cancelled")
        with self.assertRaises(WorkflowError):
            self.store.finish_task(child, "writer", checks={"verified": True})

    def test_failed_child_does_not_allow_parent_success(self):
        parent = self.running_task()
        child = self.store.create_task(self.chat, "planner", "writer", "Child", parent=parent)
        self.store.start_task(child, "writer")
        self.store.finish_task(child, "writer", error="Verification failed")
        with self.assertRaises(WorkflowError):
            self.store.finish_task(parent, "planner", checks={"verified": True})

    def test_success_needs_checks_and_terminal_tasks_cannot_restart(self):
        task = self.running_task()
        for checks in [None, {}, {"verified": False}, {"verified": 1}]:
            with self.assertRaises(WorkflowError):
                self.store.finish_task(task, "planner", checks=checks)
        self.store.finish_task(task, "planner", checks={"output_matches": True})
        with self.assertRaises(WorkflowError):
            self.store.start_task(task, "planner")
        with self.assertRaises(WorkflowError):
            self.store.finish_task(task, "planner", error="Late overwrite")

    def test_metrics_include_failed_and_pending_goals_and_all_human_wait(self):
        complete = self.running_task()
        self.now += 5
        request = self.store.ask_human(complete, "planner", "human", "Which output?")
        self.now += 30
        waiting = self.store.metrics(self.chat, "human")["tasks"][0]
        self.assertEqual(waiting["elapsed_seconds"], 35)
        self.assertEqual(waiting["human_wait_seconds"], 30)
        self.store.respond(request, "human", answer="txt")
        self.now += 5
        self.store.finish_task(complete, "planner", checks={"verified": True})
        failed = self.running_task()
        self.store.finish_task(failed, "planner", error="Tool failure")
        self.store.create_task(self.chat, "human", "planner", "Not yet run")
        metrics = self.store.metrics(self.chat, "human")
        self.assertEqual(metrics["goals"], {"assigned": 3, "succeeded": 1, "success_fraction": 1 / 3})
        done = next(t for t in metrics["tasks"] if t["task_id"] == complete)
        self.assertEqual(done["elapsed_seconds"], 40)
        self.assertEqual(done["human_wait_seconds"], 30)
        self.assertIsNone(metrics["subtasks"]["success_fraction"])

    def test_concurrent_release_is_at_most_once(self):
        task = self.running_task()
        request = self.approved_request(task)
        ready = threading.Barrier(2)

        def release():
            other = Workflow(self.database)
            try:
                ready.wait(timeout=5)
                try:
                    other.consume_approval(request, "planner", self.action)
                    return True
                except WorkflowError:
                    return False
            finally:
                other.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: release(), range(2)))
        self.assertEqual(sorted(outcomes), [False, True])

    def test_bad_action_does_not_leave_task_paused(self):
        task = self.running_task()
        for action in [{}, {"value": float("nan")}, {"value": object()}]:
            with self.assertRaises(WorkflowError):
                self.store.ask_human(task, "planner", "human", "Proceed?", action=action)
            self.assertEqual(self.store.task(task, "human")["state"], "running")

    def test_demo_is_offline_and_preserves_existing_run(self):
        location = Path(self.directory.name) / "fixture"
        report = demo(location)
        self.assertEqual(report["mode"], "offline_fixture")
        self.assertEqual(report["model_calls"], 0)
        self.assertFalse(report["benchmark_valid"])
        self.assertEqual(report["metrics"]["goals"]["succeeded"], 1)
        self.assertEqual(report["metrics"]["subtasks"]["succeeded"], 1)
        self.assertEqual(json.loads((location / "report.json").read_text())["mode"], "offline_fixture")
        original = (location / "report.json").read_bytes()
        with self.assertRaises(FileExistsError):
            demo(location)
        self.assertEqual((location / "report.json").read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
