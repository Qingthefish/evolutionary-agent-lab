from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_lab import Workflow
from agent_lab.budget import TreeBudgetError, TreeLimits, configure
from agent_lab.deepseek import DeepSeekClient, DeepSeekHTTP
from agent_lab.files import FileTools
from agent_lab.runner import Limits, RunnerError
from agent_lab.scheduler import MultiAgentScheduler, Role
from agent_lab.scheduler_fixture import DelegationFixture, fixture_roles, run_fixture
from test_runner import Script, response, tool


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)
        self.now = [1000.0]
        self.workflow = Workflow(self.path / "state.sqlite3", clock=lambda: self.now[0])
        self.roles = fixture_roles()
        self.workflow.register_actor("user", "human")
        for actor in self.roles:
            self.workflow.register_actor(actor, "agent")
        self.chat = self.workflow.create_chat("group", ["user", *self.roles])
        self.root = self.workflow.create_task(self.chat, "user", "coordinator", "Deliver the greeting note")
        self.files = FileTools(self.workflow, self.path / "files")
        self.scripts = {actor: DelegationFixture() for actor in self.roles}

    def tearDown(self):
        self.files.close()
        self.workflow.close()
        self.directory.cleanup()

    def acceptance(self, task):
        return self.files.text_verifier(task["id"], task["assignee"], {"note.txt": "Hello\n"}), "note-v1"

    def scheduler(self, **changes):
        options = dict(human="user", roles=self.roles,
            clients={actor: DeepSeekClient("fixture", script, max_tokens=128) for actor, script in self.scripts.items()},
            mode="offline_fixture", constraints=["Use English", "Keep the required newline"],
            verifier_factory=self.acceptance, acceptance_id="acceptance-v1")
        options.update(changes)
        return MultiAgentScheduler(self.workflow, self.files, self.root, **options)

    def child(self, parent=None, actor="coordinator", assignee="writer"):
        return self.workflow.create_task(self.chat, actor, assignee, "Deliver a checked note", parent=parent or self.root)

    def task_rows(self):
        return self.workflow.db.execute("SELECT * FROM tasks ORDER BY rowid").fetchall()

    def transcript(self, task):
        return json.loads(self.workflow.db.execute("SELECT transcript FROM runner_sessions WHERE task=?", (task,)).fetchone()[0])

    def test_three_roles_delegate_handoff_restart_and_verify_actual_files(self):
        demo = self.path / "demo"
        demo.mkdir()
        report = run_fixture(demo)
        self.assertEqual(report["before_restart"]["budget"]["attempts"], 3)
        self.assertEqual(report["after_restart"]["budget"]["attempts"], 11)
        self.assertEqual(report["after_restart"]["budget"]["tool_calls"], 8)
        self.assertTrue(all(item["state"] == "succeeded" for item in report["after_restart"]["tasks"]))
        self.assertEqual(report["model_calls"], 0)
        self.assertEqual(report["api_network_calls"], 0)
        self.assertFalse(report["autonomous_model_collaboration_established"])
        self.assertFalse(report["benchmark_valid"])

    def test_parent_waits_without_spending_attempts_or_copying_private_context(self):
        scheduler = self.scheduler()
        scheduler.step()
        parent_runner = scheduler.runner(self.root)
        self.assertEqual(parent_runner.step()["needs"], "child_tasks")
        self.assertEqual(parent_runner.status()["protocol_attempts"], 1)
        scheduler.run()
        for task in self.task_rows():
            context = json.loads(self.transcript(task["id"])[1]["content"])
            self.assertEqual(context["constraints"], ["Use English", "Keep the required newline"])
            self.assertEqual(context["global_goal"], "Deliver the greeting note")
            self.assertEqual(context["parent_task_id"], task["parent"])
            self.assertEqual(context["role"]["agent"], task["assignee"])
        request = self.workflow.db.execute("SELECT id FROM requests").fetchone()[0]
        self.workflow.respond(request, "user", answer="English")
        # A private child-side user context is deliberately not part of its
        # explicitly offered artifact or verified-result envelope.
        editor = next(task for task in self.task_rows() if task["assignee"] == "editor")
        transcript = self.transcript(editor["id"]) + [{"role": "user", "content": '{"private": "PRIVATE_SENTINEL"}'}]
        self.workflow.db.execute("UPDATE runner_sessions SET transcript=? WHERE task=?", (json.dumps(transcript), editor["id"]))
        self.assertEqual(scheduler.run()["task_state"], "succeeded")
        for actor in ("coordinator", "writer"):
            task = next(task for task in self.task_rows() if task["assignee"] == actor)
            messages = self.transcript(task["id"])
            self.assertNotIn("PRIVATE_SENTINEL", json.dumps(messages))
            results = [json.loads(item["content"]) for item in messages if item["role"] == "user"
                       and json.loads(item["content"]).get("kind") == "child_task_result"]
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["state"], "succeeded")
            self.assertEqual(len(results[0]["offered_artifacts"]), 1)

    def test_unverifiable_child_yields_for_independent_review(self):
        self.roles["writer"] = Role("Write the note", ("create_text",))
        self.scripts["coordinator"] = Script([response([tool("delegate_task", {"assignee": "writer", "title": "Write note"})]), response()])
        self.scripts["writer"] = Script([response([tool()]), response()])
        scheduler = self.scheduler(verifier_factory=lambda task: None)
        result = scheduler.run()
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(result["needs"][0]["kind"], "independent_verification")
        child = self.task_rows()[1]["id"]
        self.assertEqual(self.workflow.task(child, "user")["state"], "running")
        self.assertEqual(len(self.scripts["coordinator"].requests), 1)
        scheduler.run()
        self.assertEqual(len(self.scripts["writer"].requests), 2)
        self.files.complete_from_text(child, "writer", {"note.txt": "Hello\n"})
        self.assertEqual(scheduler.run()["needs"][0]["task"], self.root)
        self.assertEqual(self.workflow.task(self.root, "user")["state"], "running")

    def test_ready_sibling_runs_while_another_waits_for_human(self):
        self.scripts["editor"] = Script([response()])
        scheduler = self.scheduler(verifier_factory=lambda task: None)
        self.workflow.start_task(self.root, "coordinator")
        waiting = self.child()
        self.workflow.start_task(waiting, "writer")
        self.workflow.ask_human(waiting, "writer", "user", "Need clarification")
        ready = self.child(assignee="editor")
        result = scheduler.run()
        self.assertEqual(result["state"], "blocked")
        self.assertEqual({item["kind"] for item in result["needs"]}, {"waiting_input", "independent_verification"})
        self.assertEqual(self.workflow.task(ready, "user")["state"], "running")
        self.assertEqual(len(self.scripts["editor"].requests), 1)

    def test_child_failure_fails_goal_and_cancels_sibling_without_false_success(self):
        scheduler = self.scheduler()
        self.workflow.start_task(self.root, "coordinator")
        child, sibling = self.child(), self.child(assignee="editor")
        self.workflow.start_task(child, "writer")
        self.files.create_text(child, "writer", "partial.txt", "retain this evidence")
        self.workflow.finish_task(child, "writer", error="Independent check failed")
        result = scheduler.run()
        self.assertEqual(result["task_state"], "failed")
        self.assertEqual(self.workflow.task(sibling, "user")["state"], "cancelled")
        self.assertIn("Independent check failed", self.workflow.task(child, "user")["evidence"])
        self.assertEqual(len(list((self.path / "files/tasks").rglob("partial.txt"))), 1)
        self.assertEqual(self.workflow.metrics(self.chat, "user")["goals"]["success_fraction"], 0)

    def test_shared_attempt_budget_cannot_be_reset_by_delegation_or_restart(self):
        scheduler = self.scheduler(limits=TreeLimits(model_attempts=1))
        scheduler.step()
        scheduler = self.scheduler(limits=TreeLimits(model_attempts=1))
        result = scheduler.run()
        self.assertEqual(result["task_state"], "failed")
        self.assertEqual(result["budget"]["attempts"], 1)
        self.assertIn("attempts budget", self.workflow.task(self.task_rows()[1]["id"], "user")["evidence"])

    def test_shared_token_overrun_in_child_releases_no_child_tools(self):
        scheduler = self.scheduler(limits=TreeLimits(reported_tokens=3))
        result = scheduler.run()
        self.assertEqual(result["task_state"], "failed")
        self.assertEqual(result["budget"]["tokens"], 4)
        self.assertEqual(result["budget"]["tasks"], 2)
        self.assertEqual(result["budget"]["tool_calls"], 1)

    def test_shared_tool_budget_cannot_be_reset_in_child(self):
        scheduler = self.scheduler(limits=TreeLimits(tool_calls=1))
        result = scheduler.run()
        self.assertEqual(result["task_state"], "failed")
        self.assertEqual(result["budget"]["tool_calls"], 1)
        self.assertEqual(result["budget"]["tasks"], 2)

    def test_task_count_and_depth_limits_apply_to_direct_workflow_delegation(self):
        scheduler = self.scheduler(limits=TreeLimits(tasks=2, depth=1))
        self.workflow.start_task(self.root, "coordinator")
        child = self.child()
        with self.assertRaises(TreeBudgetError):
            self.child()
        self.workflow.start_task(child, "writer")
        with self.assertRaises(TreeBudgetError):
            self.child(child, "writer", "editor")
        self.assertEqual(scheduler.status()["budget"]["tasks"], 2)

    def test_repeated_fresh_delegations_stop_at_shared_task_bound(self):
        self.roles["coordinator"] = replace(self.roles["coordinator"], delegates=("coordinator",))
        self.scripts["coordinator"] = Script([response([tool("delegate_task", {
            "assignee": "coordinator", "title": "Further delegation"}, str(index))]) for index in range(8)])
        scheduler = self.scheduler(limits=TreeLimits(tasks=3), verifier_factory=lambda task: None)
        result = scheduler.run()
        self.assertEqual(result["task_state"], "failed")
        self.assertEqual(result["budget"]["tasks"], 3)
        self.assertEqual(result["budget"]["attempts"], 5)  # 2 delegations + 3 repeated rejected outcomes

    def test_shared_deadline_expires_during_human_wait_and_preserves_state(self):
        scheduler = self.scheduler(limits=TreeLimits(duration_seconds=10))
        scheduler.run()
        self.now[0] += 11
        result = scheduler.run()
        self.assertEqual(result["task_state"], "failed")
        self.assertEqual(result["budget"]["attempts"], 3)
        editor = next(task for task in self.task_rows() if task["assignee"] == "editor")
        self.assertEqual(editor["state"], "cancelled")
        self.assertEqual(editor["wait_seconds"], 11)

    def test_parent_deadline_applies_even_while_child_is_ready(self):
        self.roles["coordinator"] = replace(self.roles["coordinator"], limits=Limits(duration_seconds=10))
        scheduler = self.scheduler()
        scheduler.step()
        self.now[0] += 11
        self.assertEqual(scheduler.run()["task_state"], "failed")
        self.assertEqual(len(self.scripts["writer"].requests), 0)

    def test_restart_cannot_change_roles_constraints_or_shared_limits(self):
        self.scheduler()
        for changes in ({"constraints": ["Drop original constraints"]}, {"acceptance_id": "different"},
                        {"limits": TreeLimits(model_attempts=999)},
                        {"roles": {**self.roles, "editor": replace(self.roles["editor"], tools=("read_text",))}}):
            with self.subTest(changes=changes), self.assertRaises((RunnerError, TreeBudgetError)):
                self.scheduler(**changes)

    def test_unknown_provider_attempt_is_not_replayed_after_restart(self):
        self.scripts["coordinator"] = Script([RuntimeError("Simulated worker death")])
        scheduler = self.scheduler()
        with self.assertRaises(RuntimeError):
            scheduler.run()
        resumed = self.scheduler()
        self.assertEqual(resumed.run()["needs"][0]["kind"], "reconciliation")
        self.assertEqual(resumed.status()["budget"]["attempts"], 1)
        self.assertEqual(len(self.scripts["coordinator"].requests), 1)
        resumed.runner(self.root).abort("Outcome unknown; stop before another run")
        self.assertEqual(resumed.run()["task_state"], "failed")

    def test_committed_delegation_recovers_without_duplicate_child(self):
        scheduler = self.scheduler()
        from agent_lab.gateway import ToolGateway
        original = ToolGateway.dispatch

        def crash(gateway, call):
            original(gateway, call)
            raise RuntimeError("Crash after committed delegation result")
        with patch.object(ToolGateway, "dispatch", crash), self.assertRaises(RuntimeError):
            scheduler.step()
        self.assertEqual(scheduler.run()["needs"][0]["kind"], "reconciliation")
        scheduler.runner(self.root).recover_tools()
        scheduler.run()
        self.assertEqual(len(self.task_rows()), 3)
        self.assertEqual(sum(task["assignee"] == "writer" for task in self.task_rows()), 1)

    def test_persisted_controller_claim_requires_explicit_worker_reconciliation(self):
        scheduler = self.scheduler()
        self.workflow.db.execute("UPDATE scheduler_runs SET owner='interrupted-worker'")
        self.assertEqual(self.scheduler().run()["needs"][0]["kind"], "controller_reconciliation_or_busy")
        self.assertEqual(scheduler.status()["budget"]["attempts"], 0)
        scheduler.recover_controller()
        self.assertEqual(scheduler.step()["state"], "running")

    def test_another_controller_cannot_advance_during_provider_call(self):
        scheduler = None

        def inspect_second_controller():
            result = self.scheduler().step()
            self.assertEqual(result["needs"][0]["kind"], "controller_reconciliation_or_busy")
            return response()
        self.scripts["coordinator"] = Script([inspect_second_controller])
        scheduler = self.scheduler(verifier_factory=lambda task: None)
        result = scheduler.run()
        self.assertEqual(result["budget"]["attempts"], 1)

    def test_budget_must_attach_at_root_before_delegation(self):
        self.workflow.start_task(self.root, "coordinator")
        child = self.child()
        with self.assertRaises(TreeBudgetError):
            configure(self.workflow, self.root, TreeLimits())
        with self.assertRaises(TreeBudgetError):
            configure(self.workflow, child, TreeLimits())

    def test_other_root_does_not_spend_this_goals_budget(self):
        scheduler = self.scheduler()
        other = self.workflow.create_task(self.chat, "user", "coordinator", "Other goal")
        self.workflow.start_task(other, "coordinator")
        self.child(other)
        self.assertEqual(scheduler.status()["budget"]["tasks"], 1)
        self.assertEqual(scheduler.status()["budget"]["attempts"], 0)

    def test_mixed_models_and_transport_modes_are_rejected_before_execution(self):
        clients = {actor: DeepSeekClient("fixture", Script([])) for actor in self.roles}
        clients["editor"] = DeepSeekClient("different", Script([]))
        with self.assertRaises(RunnerError):
            self.scheduler(clients=clients)
        clients["editor"] = DeepSeekClient("fixture", DeepSeekHTTP("fake-key"))
        with self.assertRaises(RunnerError):
            self.scheduler(clients=clients)

    def test_shared_expiry_blocks_approved_effect_and_late_verification(self):
        scheduler = self.scheduler(limits=TreeLimits(duration_seconds=10))
        self.workflow.start_task(self.root, "coordinator")
        action = {"tool": "delete_text", "arguments": {"path": "old.txt", "expected_sha256": hashlib.sha256(b"old").hexdigest()}}
        request = self.workflow.ask_human(self.root, "coordinator", "user", "Approve exact deletion?", action=action)
        self.workflow.respond(request, "user", approve=True)
        self.now[0] += 11
        with self.assertRaises(TreeBudgetError):
            self.workflow.consume_approval(request, "coordinator", action)
        self.assertFalse(self.workflow.request(request, "user")["consumed"])
        # Remove approval as a competing rejection to exercise deadline checks
        # at the trusted success boundary on a different root with its own scope.
        other = self.workflow.create_task(self.chat, "user", "editor", "Other checked task")
        configure(self.workflow, other, TreeLimits(duration_seconds=1))
        self.workflow.start_task(other, "editor")

        def late():
            self.now[0] += 2
            return {"independent": True}
        with self.assertRaises(TreeBudgetError):
            self.workflow.finish_task(other, "editor", verifier=late)
        self.assertEqual(self.workflow.task(other, "user")["state"], "running")

    def test_shared_batch_preflight_does_not_release_first_effect_when_batch_exceeds_cap(self):
        self.roles["coordinator"] = Role("Write two files", ("create_text",))
        self.scripts["coordinator"] = Script([response([tool(), tool(arguments={"path": "other.txt", "content": "Other"}, identifier="other")])])
        result = self.scheduler(limits=TreeLimits(tool_calls=1)).run()
        self.assertEqual(result["task_state"], "failed")
        self.assertEqual(result["budget"]["tool_calls"], 0)
        self.assertEqual(list((self.path / "files/tasks").rglob("note.txt")), [])

    def test_distinct_task_reservations_atomically_share_last_attempt(self):
        from concurrent.futures import ThreadPoolExecutor
        from agent_lab.budget import check
        self.scheduler(limits=TreeLimits(model_attempts=1))
        self.workflow.start_task(self.root, "coordinator")
        children = [self.child(), self.child(assignee="editor")]

        def reserve(task):
            workflow = Workflow(self.path / "state.sqlite3", clock=lambda: self.now[0])
            try:
                with workflow._transaction():
                    check(workflow, task, reserve="attempts")
                return True
            except TreeBudgetError:
                return False
            finally:
                workflow.close()

        with ThreadPoolExecutor(max_workers=2) as workers:
            self.assertEqual(sorted(workers.map(reserve, children)), [False, True])
        self.assertEqual(self.workflow.db.execute("SELECT attempts FROM tree_budgets").fetchone()[0], 1)

    def test_approval_wait_requires_exact_trusted_release_before_more_model_calls(self):
        self.roles["editor"] = Role("Clean and create note", ("create_text", "delete_text"))
        self.scripts["editor"] = Script([response([tool()]), response()])
        scheduler = self.scheduler()
        self.workflow.start_task(self.root, "coordinator")
        child = self.child(assignee="editor")
        self.workflow.start_task(child, "editor")
        receipt = self.files.create_text(child, "editor", "old.txt", "old")
        gateway = scheduler.runner(child).gateway
        gateway.dispatch(tool("delete_text", {"path": "old.txt", "expected_sha256": receipt["sha256"]}, "delete-old"))
        request = self.workflow.db.execute("SELECT id FROM requests WHERE task=?", (child,)).fetchone()[0]
        waiting = scheduler.run()
        self.assertEqual(waiting["needs"][0]["requests"][0]["id"], request)
        self.workflow.respond(request, "user", approve=True)
        self.assertEqual(scheduler.run()["needs"][0]["kind"], "trusted_action_release")
        self.assertEqual(len(self.scripts["editor"].requests), 0)
        gateway.release_approved(request)
        # Stop before the root's fixture script: only the verified child is the
        # acceptance target of this approval/release check.
        scheduler.step()
        scheduler.step()
        self.assertEqual(self.workflow.task(child, "user")["state"], "succeeded")
        self.assertEqual(list((self.path / "files/tasks").rglob("old.txt")), [])

    def test_invalid_role_capabilities_fail_before_any_task_turn(self):
        for tools in (("approve",), ("run_python",), ("search_memory",)):
            with self.subTest(tools=tools), self.assertRaises(RunnerError):
                self.scheduler(roles={**self.roles, "editor": Role("Unsupported role", tools)})

    def test_budget_cannot_be_retrofitted_after_existing_runner_execution(self):
        from agent_lab.gateway import ToolGateway
        from agent_lab.runner import TaskRunner
        self.workflow.start_task(self.root, "coordinator")
        gateway = ToolGateway(self.workflow, self.files, self.root, "coordinator", human="user", allowed=["create_text"])
        runner = TaskRunner(gateway, DeepSeekClient("fixture", Script([response([tool()])])), mode="offline_fixture", constraints=[])
        runner.step()
        with self.assertRaises(TreeBudgetError):
            configure(self.workflow, self.root, TreeLimits())


if __name__ == "__main__":
    unittest.main()
