"""Parent integration after a verified child, replayed with synthetic transport only.

The retained C07 audit found three declared-policy training roots whose child
was verified while the parent exhausted the shared attempt cap, spending one
response per call: accept_artifact, read_text, create_text, then record_lesson
or post_message, and never a completion proposal. These checks pin the facts
behind the declared-view handoff hint and the unchanged acceptance contract.
They script model replies; they do not show what a live model will choose.
"""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from agent_lab import budget
from agent_lab.acceptance import ArtifactRule
from agent_lab.core import Workflow
from agent_lab.deepseek import DeepSeekClient
from agent_lab.files import FileTools
from agent_lab.model_context import CONTEXT_POLICY, HANDOFF_INTEGRATION
from agent_lab.runtime import ChildTextRule, TaskPolicy, bind_task_policy, text_acceptance_factory
from agent_lab.scheduler import MultiAgentScheduler, Role
from test_runner import Script, response, tool

TITLE = "Write checked note.txt"
NOTE = "Hello\n"
REPORT = "Records: 1\n\n## Checks\nReceived and read note.txt.\n"


class HandoffIntegration(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)
        self.workflow = Workflow(self.path / "state.sqlite3")
        self.files = FileTools(self.workflow, self.path / "files")
        for actor, kind in (("user", "human"), ("coordinator", "agent"), ("writer", "agent")):
            self.workflow.register_actor(actor, kind)
        chat = self.workflow.create_chat("group", ["user", "coordinator", "writer"])
        self.root = self.workflow.create_task(chat, "user", "coordinator", "Deliver report.md from the writer's note")
        received = json.dumps({"assignee": "writer", "title": TITLE, "path": "note.txt",
                               "allow_relay": False, "require_read": True})
        self.policy = TaskPolicy(["Keep attribution"], (), [ChildTextRule("writer", TITLE, {"note.txt": NOTE})],
                                 (ArtifactRule("note.txt", "received_from", received),
                                  ArtifactRule("report.md", "contains", "Records: 1")), declared_subtasks_only=True)
        bind_task_policy(self.workflow, self.root, "user", self.policy)
        self.roles = {
            "coordinator": Role("Delegate the note, receive it and write the report.",
                                ("delegate_task", "accept_artifact", "read_text", "create_text", "post_message"), ("writer",)),
            "writer": Role("Write the note and offer it to your parent.", ("create_text", "offer_artifact")),
        }
        self.writer = Script([
            response([tool("create_text", {"path": "note.txt", "content": NOTE}, "w1"),
                      tool("offer_artifact", {"path": "note.txt", "target_task": self.root,
                                              "expected_sha256": hashlib.sha256(NOTE.encode()).hexdigest()}, "w2")]),
            response()])

    def tearDown(self):
        self.files.close()
        self.workflow.close()
        self.directory.cleanup()

    def offer(self):
        return self.workflow.db.execute("SELECT id FROM artifacts WHERE target_task=?", (self.root,)).fetchone()[0]

    def accept(self, identifier="p-accept"):
        return tool("accept_artifact", {"artifact_id": self.offer(), "path": "note.txt"}, identifier)

    def run_tree(self, parent_replies, *, attempts=6, declared=True):
        self.coordinator = Script([response([tool("delegate_task", {"assignee": "writer", "title": TITLE}, "p-delegate")]),
                                   *parent_replies])
        scripts = {"coordinator": self.coordinator, "writer": self.writer}
        policy = bind_task_policy(self.workflow, self.root, "user")
        return MultiAgentScheduler(self.workflow, self.files, self.root, human="user", roles=self.roles,
            clients={a: DeepSeekClient("synthetic-model", s) for a, s in scripts.items()}, mode="offline_fixture",
            constraints=list(policy.constraints), acceptance_id=policy.acceptance_id,
            verifier_factory=text_acceptance_factory(self.workflow, self.files, self.root, policy),
            limits=budget.TreeLimits(model_attempts=attempts),
            delegation_rules=((("writer", TITLE),) if declared else None)).run()

    def child_results(self):
        return [json.loads(m["content"]) for m in self.coordinator.requests[-1]["messages"]
                if m["role"] == "user" and json.loads(m["content"]).get("kind") == "child_task_result"]

    def test_batched_integration_completes_within_the_cap_the_recorded_sequence_exhausts(self):
        # Delegate (1) + writer (2) leaves three of six shared attempts for the parent.
        result = self.run_tree([lambda: response([self.accept(), tool("read_text", {"path": "note.txt"}, "p-read")]),
                                response([tool("create_text", {"path": "report.md", "content": REPORT}, "p-report")]),
                                response()])
        self.assertEqual(result["task_state"], "succeeded")
        self.assertEqual(result["budget"]["attempts"], 6)
        evidence = json.loads(self.workflow.task(self.root, "user")["evidence"])["checks"]
        self.assertTrue(evidence["criterion:1:note.txt:received_from"])  # Unchanged ordered receipt-then-read check.

    def test_recorded_one_call_per_response_sequence_exhausts_the_same_cap(self):
        result = self.run_tree([lambda: response([self.accept()]),
                                response([tool("read_text", {"path": "note.txt"}, "p-read")]),
                                response([tool("create_text", {"path": "report.md", "content": REPORT}, "p-report")]),
                                response([tool("post_message", {"body": "Report written."}, "p-status")])])
        self.assertEqual(result["task_state"], "failed")
        self.assertEqual(result["budget"]["attempts"], 6)
        self.assertEqual(len(self.coordinator.requests), 4)  # The status message was never reached.
        self.assertTrue(self.workflow.db.execute(
            "SELECT 1 FROM events WHERE task=? AND kind='file_created'", (self.root,)).fetchone())  # Deliverable existed.

    def test_reading_before_the_receipt_in_one_batch_still_fails_acceptance(self):
        result = self.run_tree([lambda: response([tool("read_text", {"path": "note.txt"}, "p-read"), self.accept()]),
                                response([tool("create_text", {"path": "report.md", "content": REPORT}, "p-report")]),
                                response()])
        self.assertEqual(result["task_state"], "failed")  # Rejected proposal, then the same cap.
        session = self.workflow.db.execute("SELECT transcript FROM runner_sessions WHERE task=?", (self.root,)).fetchone()[0]
        self.assertIn("trusted_verification_failure", session)

    def test_declared_child_result_carries_the_versioned_hint(self):
        self.run_tree([lambda: response([self.accept(), tool("read_text", {"path": "note.txt"}, "p-read")]),
                       response([tool("create_text", {"path": "report.md", "content": REPORT}, "p-report")]), response()])
        (handed,) = self.child_results()
        self.assertEqual(handed["state"], "succeeded")
        self.assertEqual(handed["integration"], HANDOFF_INTEGRATION)
        self.assertEqual(CONTEXT_POLICY, "declared-concise-actions-v3")
        config = json.loads(self.workflow.db.execute("SELECT config FROM scheduler_runs WHERE root=?", (self.root,)).fetchone()[0])
        self.assertEqual(config["model_context"], CONTEXT_POLICY)

    def test_original_view_used_by_c07_and_legacy_runs_is_unchanged(self):
        self.run_tree([lambda: response([self.accept(), tool("read_text", {"path": "note.txt"}, "p-read")]),
                       response([tool("create_text", {"path": "report.md", "content": REPORT}, "p-report")]), response()],
                      declared=False)
        (handed,) = self.child_results()
        self.assertEqual(set(handed), {"kind", "task_id", "assignee", "assignment", "state", "evidence",
                                       "offered_artifacts", "instruction"})

    def test_no_hint_without_an_unconsumed_offer(self):
        self.writer = Script([response([tool("create_text", {"path": "note.txt", "content": NOTE}, "w1")]), response()])
        self.run_tree([response([tool("create_text", {"path": "report.md", "content": REPORT}, "p-report")]), response()],
                      attempts=5)  # Without a receipt the proposal is rejected; stop at the cap.
        (handed,) = self.child_results()
        self.assertEqual(handed["offered_artifacts"], [])
        self.assertNotIn("integration", handed)


if __name__ == "__main__":
    unittest.main()
