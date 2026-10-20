"""Independent child criteria and bounded recovery, with synthetic transport only."""

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.core import Workflow, WorkflowError
from agent_lab.deepseek import DeepSeekClient, DeepSeekHTTP
from agent_lab.evaluation import parse_case
from agent_lab.evaluation.harness import _Session, _drive_live, HUMAN
from agent_lab.files import FileTools
from agent_lab.runner import Limits
from agent_lab.runtime import (ChildTextRule, LiveConfig, TaskPolicy, bind_task_policy,
    build_live_scheduler, text_acceptance_factory)
from agent_lab.scheduler import MultiAgentScheduler, Role
from agent_lab.tui.controller import ControlCenter
from test_runner import Script, response, tool


class ChildAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)
        self.open()
        for actor, kind in (("user", "human"), ("coordinator", "agent"), ("writer", "agent")):
            self.workflow.register_actor(actor, kind)
        self.chat = self.workflow.create_chat("group", ["user", "coordinator", "writer"])
        self.root = self.workflow.create_task(self.chat, "user", "coordinator", "Deliver note.txt")
        self.rule = ChildTextRule("writer", "Draft checked note", {"note.txt": "Hello\n"})
        self.policy = TaskPolicy(["Keep attribution"], {"note.txt": "Hello\n"}, [self.rule])
        bind_task_policy(self.workflow, self.root, "user", self.policy)
        self.roles = {
            "coordinator": Role("Delegate and receive the checked artifact", ("delegate_task", "accept_artifact"), ("writer",)),
            "writer": Role("Draft the note", ("create_text", "update_text", "offer_artifact")),
        }
        self.scripts = {
            "coordinator": Script([response([tool("delegate_task", {"assignee": "writer", "title": self.rule.title})]),
                                   self.accept_offer, response()]),
            "writer": Script([response([tool(arguments={"path": "note.txt", "content": "Wrong\n"})]), response(),
                              response([tool("update_text", {"path": "note.txt", "content": "Hello\n",
                                  "expected_sha256": hashlib.sha256(b"Wrong\n").hexdigest()}, "repair")]),
                              response([tool("offer_artifact", {"path": "note.txt", "target_task": self.root,
                                  "expected_sha256": hashlib.sha256(b"Hello\n").hexdigest()}, "offer")]), response()]),
        }

    def open(self):
        self.workflow = Workflow(self.path / "state.sqlite3")
        self.files = FileTools(self.workflow, self.path / "files")

    def tearDown(self):
        self.files.close()
        self.workflow.close()
        self.directory.cleanup()

    def accept_offer(self):
        artifact = self.workflow.db.execute("SELECT id FROM artifacts WHERE target_task=?", (self.root,)).fetchone()[0]
        return response([tool("accept_artifact", {"artifact_id": artifact, "path": "note.txt"}, "receive")])

    def scheduler(self):
        policy = bind_task_policy(self.workflow, self.root, "user")
        return MultiAgentScheduler(self.workflow, self.files, self.root, human="user", roles=self.roles,
            clients={a: DeepSeekClient("synthetic-model", s) for a, s in self.scripts.items()}, mode="offline_fixture",
            constraints=list(policy.constraints), verifier_factory=text_acceptance_factory(self.workflow, self.files, self.root, policy),
            acceptance_id=policy.acceptance_id)

    def child(self, title=None):
        return self.workflow.create_task(self.chat, "coordinator", "writer", title or self.rule.title, parent=self.root)

    def test_failed_child_repairs_after_restart_then_parent_receives_verified_result(self):
        scheduler = self.scheduler()
        for _ in range(3):
            scheduler.step()  # delegate, wrong file, rejected completion proposal
        child = self.workflow.db.execute("SELECT id FROM tasks WHERE parent=?", (self.root,)).fetchone()[0]
        self.assertEqual(self.workflow.task(child, "user")["state"], "running")
        self.assertEqual(len(self.scripts["coordinator"].requests), 1)
        transcript = self.workflow.db.execute("SELECT transcript FROM runner_sessions WHERE task=?", (child,)).fetchone()[0]
        self.assertIn("trusted_verification_failure", transcript)
        self.assertIn("artifact:note.txt", transcript)
        self.files.close()
        self.workflow.close()
        self.open()
        restored = bind_task_policy(self.workflow, self.root, "user")
        self.assertEqual(restored, self.policy)
        result = self.scheduler().run()
        self.assertEqual(result["task_state"], "succeeded")
        self.assertEqual((result["model_calls"], result["benchmark_valid"]), (0, False))
        self.assertEqual(result["budget"]["attempts"], 8)
        request = self.scripts["coordinator"].requests[1]
        messages = [json.loads(m["content"]) for m in request["messages"] if m["role"] == "user"]
        handed = next(m for m in messages if m.get("kind") == "child_task_result")
        self.assertEqual(handed["state"], "succeeded")
        self.assertTrue(handed["evidence"]["checks"]["artifact:note.txt"])

    def test_repeated_bad_child_cannot_reset_budget_or_resume_parent(self):
        self.roles["writer"] = replace(self.roles["writer"], limits=Limits(model_attempts=3))
        self.scripts["writer"] = Script([response([tool(arguments={"path": "note.txt", "content": "Wrong\n"})]), response(), response()])
        result = self.scheduler().run()
        self.assertEqual(result["task_state"], "failed")
        self.assertEqual(len(self.scripts["writer"].requests), 3)
        self.assertEqual(len(self.scripts["coordinator"].requests), 1)
        self.assertEqual(result["budget"]["attempts"], 4)
        self.assertEqual(len(list((self.path / "files/tasks").rglob("note.txt"))), 1)

    def test_unknown_child_pauses_for_review_without_spending_parent_attempts(self):
        self.scripts["coordinator"] = Script([response([tool("delegate_task", {"assignee": "writer", "title": "Unplanned task"})])])
        self.scripts["writer"] = Script([response()])
        result = self.scheduler().run()
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(result["needs"][0]["kind"], "independent_verification")
        self.assertEqual(len(self.scripts["coordinator"].requests), 1)
        self.assertEqual(self.scheduler().run()["state"], "blocked")
        self.assertEqual(len(self.scripts["writer"].requests), 1)

    def test_duplicate_selector_is_reviewed_and_rechecked_at_completion(self):
        self.workflow.start_task(self.root, "coordinator")
        first = self.child()
        self.workflow.start_task(first, "writer")
        self.files.create_text(first, "writer", "note.txt", "Hello\n")
        factory = text_acceptance_factory(self.workflow, self.files, self.root, self.policy)
        verifier, _ = factory(self.workflow.task(first, "user"))
        second = self.child()
        self.assertIsNone(factory(self.workflow.task(second, "user")))
        with self.assertRaisesRegex(WorkflowError, "child:unique_match"):
            self.workflow.finish_task(first, "writer", verifier=verifier)

    def test_matching_root_file_cannot_skip_a_required_child(self):
        self.workflow.start_task(self.root, "coordinator")
        self.files.create_text(self.root, "coordinator", "note.txt", "Hello\n")
        verifier, _ = text_acceptance_factory(self.workflow, self.files, self.root, self.policy)(
            self.workflow.task(self.root, "user"))
        with self.assertRaisesRegex(WorkflowError, "child:0:unique_match"):
            self.workflow.finish_task(self.root, "coordinator", verifier=verifier)

    def test_changed_or_malformed_child_criteria_cannot_replace_saved_policy(self):
        changed = ChildTextRule("writer", self.rule.title, {"note.txt": "Different\n"})
        with self.assertRaises(WorkflowError):
            bind_task_policy(self.workflow, self.root, "user", replace(self.policy, child_rules=[changed]))
        for rules in ([self.rule, self.rule], [{"assignee": "writer"}], "not-rules"):
            with self.assertRaises(WorkflowError):
                TaskPolicy(child_rules=rules)
        with self.assertRaises(WorkflowError):
            ChildTextRule("writer", self.rule.title, {})
        for bad in ([], {"version": 2, "constraints": [], "root_artifacts": {}, "child_rules": []}):
            self.workflow.db.execute("UPDATE runtime_task_policies SET policy=? WHERE root=?", (json.dumps(bad), self.root))
            with self.assertRaisesRegex(WorkflowError, "Persisted task policy is invalid"):
                bind_task_policy(self.workflow, self.root, "user")

    def test_ui_api_and_evaluator_share_supported_rules_without_weakening_other_checks(self):
        child = {"assignee": "writer", "title": self.rule.title, "final_state": "succeeded", "artifacts": {"note.txt": "Hello\n"}}
        unsupported = child | {"title": "Check absence", "absent_artifacts": ["secret.txt"]}
        case = parse_case({"id": "child-check", "title": "Child integration", "goal": "Deliver note.txt", "driver": "live_scheduler",
                           "expected": {"final_state": "succeeded", "artifacts": {"note.txt": "Hello\n"}, "subtasks": [child, unsupported]}})
        path = self.path / "evaluation"
        path.mkdir()
        session = _Session(path, "child-check")
        self.addCleanup(session.close)
        live = LiveConfig("explicit-test-model", "unused-key")
        with patch.object(MultiAgentScheduler, "run", return_value={"state": "blocked"}), \
                patch.object(DeepSeekHTTP, "__call__", side_effect=AssertionError("No network call")) as http:
            root, _ = _drive_live(case, session, live)
            http.assert_not_called()
        saved = bind_task_policy(session.workflow, root, HUMAN)
        self.assertEqual(saved.child_rules, (self.rule,))
        center = ControlCenter(self.path / "ui", live=live)
        self.addCleanup(center.close)
        chat = center.create_conversation("group", ["coordinator", "writer"])
        root = center.create_task(chat, "coordinator", "Deliver note.txt", expected_artifacts={"note.txt": "Hello\n"}, child_rules=[self.rule])["task"]
        ui = center.call(lambda b: bind_task_policy(b.workflow, root, b.human))
        self.assertEqual(ui, saved)


if __name__ == "__main__":
    unittest.main()
