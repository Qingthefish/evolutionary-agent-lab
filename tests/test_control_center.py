"""Control-center backend checks. Standard library only; Textual is not required."""

import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest

from agent_lab.core import WorkflowError
from agent_lab.files import FileToolError
from agent_lab.queries import redact
from agent_lab.tui.controller import ControlCenter, ControllerError, LiveConfig


class ControlCenterTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "session"
        self.center = ControlCenter(self.path)

    def tearDown(self):
        self.center.close()
        self.directory.cleanup()

    def reopen(self):
        self.center.close()
        self.center = ControlCenter(self.path)

    def pending(self, kind):
        return next(r for r in self.center.requests(pending_only=True) if r["kind"] == kind)

    # ---- conversations ----------------------------------------------------
    def test_private_and_group_routing_respects_membership(self):
        private = self.center.create_conversation("private", ["writer"])
        group = self.center.create_conversation("group", ["coordinator", "editor"])
        self.center.post_message(private, "private hello")
        self.center.post_message(group, "group hello")
        self.assertEqual([i["body"] for i in self.center.feed(private)], ["private hello"])
        self.assertEqual([i["body"] for i in self.center.feed(group)], ["group hello"])
        kinds = {c["id"]: c["kind"] for c in self.center.conversations()}
        self.assertEqual(kinds, {private: "private", group: "group"})
        # Another human who is not a member cannot read either conversation.
        self.center.call(lambda b: b.workflow.register_actor("outsider", "human"))
        with self.assertRaises(WorkflowError):
            self.center.call(lambda b: b.queries.conversation_feed(private, "outsider"))
        self.assertEqual(self.center.call(lambda b: b.queries.conversations("outsider")), [])
        with self.assertRaises(WorkflowError):
            self.center.create_conversation("private", ["writer", "editor"])

    def test_posting_a_message_never_creates_or_executes_a_task(self):
        chat = self.center.create_conversation("private", ["writer"])
        self.center.post_message(chat, "Please write a poem")
        self.assertEqual(self.center.tasks(), [])
        result = self.center.create_task(chat, "writer", "Write a short poem")
        self.assertEqual(result["execution"], "not_started")
        task = self.center.task_detail(result["task"])
        self.assertEqual(task["task"]["state"], "pending")
        self.assertIsNone(task["runner"])
        self.assertIsNone(task["run"])
        with self.assertRaises(ControllerError):
            self.center.advance(result["task"])
        feed = self.center.feed(chat)
        self.assertEqual([i["type"] for i in feed], ["message", "task_event"])
        self.assertEqual(feed[1]["kind"], "created")

    def test_task_assignment_requires_agent_member(self):
        chat = self.center.create_conversation("private", ["writer"])
        with self.assertRaises(WorkflowError):
            self.center.create_task(chat, "editor", "Not a member")
        with self.assertRaises(WorkflowError):
            self.center.create_task(chat, "operator", "Humans are not assignees")

    # ---- scenarios, task tree, clarification -------------------------------
    def test_delegation_tree_clarification_and_artifact_transfer(self):
        result = self.center.run_scenario("delegation")
        self.assertEqual((result["mode"], result["model_calls"], result["benchmark_valid"]),
                         ("offline_fixture", 0, False))
        self.assertEqual(result["scheduler"]["state"], "blocked")
        tree = self.center.task_tree()
        self.assertEqual(len(tree), 1)
        root = tree[0]
        self.assertEqual(root["assignee"], "coordinator")
        self.assertEqual(root["children"][0]["assignee"], "writer")
        editor = root["children"][0]["children"][0]
        self.assertEqual((editor["assignee"], editor["state"]), ("editor", "waiting_input"))
        self.assertTrue(editor["waiting_on_human"])
        request = self.pending("clarification")
        self.assertEqual(request["task"], editor["id"])
        with self.assertRaises(WorkflowError):
            self.center.decide(request["id"], True)  # A clarification is not an approval.
        self.center.answer(request["id"], "English, Hello and a newline")
        with self.assertRaises(WorkflowError):
            self.center.answer(request["id"], "again")  # Exactly once.
        final = self.center.advance(editor["id"])
        self.assertEqual(final["task_state"], "succeeded")
        transfers = self.center.transfers()
        self.assertEqual([(t["source_agent"], t["recipient"]) for t in transfers],
                         [("editor", "writer"), ("writer", "coordinator")])
        self.assertTrue(all(t["consumed"] and t["received_path"] == "note.txt" for t in transfers))
        self.assertEqual(self.center.compare_transfer(transfers[0]["artifact_id"])["status"], "identical")
        files = self.center.files(root["id"])
        self.assertEqual([(f["path"], f["matches_receipt"]) for f in files], [("note.txt", True)])
        self.assertEqual(self.center.read_file(root["id"], "note.txt")["content"], "Hello\n")
        detail = self.center.task_detail(root["id"])
        self.assertTrue(detail["runner"]["synthetic"])
        self.assertEqual(detail["runner"]["mode"], "offline_fixture")
        self.assertIn("checks", detail["task"]["evidence"])

    # ---- approvals ----------------------------------------------------------
    def test_approval_grant_release_and_verified_effect_are_distinct(self):
        self.center.run_scenario("approval")
        request = self.pending("approval")
        self.assertEqual(request["action"]["tool"], "delete_text")
        with self.assertRaises(ControllerError):
            self.center.release(request["id"])  # Not approved yet.
        self.center.decide(request["id"], True)
        granted = self.center.request_detail(request["id"])
        self.assertEqual(granted["status"], "granted_awaiting_release")
        self.assertIsNone(granted["outcome"])
        # Approval alone does not execute anything: the file still exists.
        names = {f["path"]: f for f in self.center.files(request["task"])}
        self.assertIsNotNone(names["scratch.txt"]["current"])
        blocked = self.center.advance(request["task"])
        self.assertEqual(blocked["needs"][0]["kind"], "trusted_action_release")
        receipt = self.center.release(request["id"])
        self.assertEqual(receipt["path"], "scratch.txt")
        released = self.center.request_detail(request["id"])
        self.assertEqual((released["status"], released["outcome"]["kind"]), ("released", "file_deleted"))
        with self.assertRaises(ControllerError):
            self.center.release(request["id"])  # Single use.
        self.assertEqual(self.center.advance(request["task"])["task_state"], "succeeded")
        names = {f["path"]: f for f in self.center.files(request["task"])}
        self.assertIsNone(names["scratch.txt"]["current"])

    def test_rejection_cancels_task_and_cannot_release(self):
        self.center.run_scenario("approval")
        request = self.pending("approval")
        self.center.decide(request["id"], False)
        detail = self.center.request_detail(request["id"])
        self.assertEqual((detail["status"], detail["task_state"]), ("denied", "cancelled"))
        with self.assertRaises(ControllerError):
            self.center.release(request["id"])
        self.assertEqual(self.center.advance(request["task"])["task_state"], "cancelled")
        names = {f["path"]: f for f in self.center.files(request["task"])}
        self.assertIsNotNone(names["scratch.txt"]["current"])

    def test_stale_approval_and_wrong_human_are_refused(self):
        self.center.run_scenario("approval")
        request = self.pending("approval")
        self.center.call(lambda b: b.workflow.register_actor("intruder", "human"))
        with self.assertRaises(WorkflowError):
            self.center.call(lambda b: b.workflow.respond(request["id"], "intruder", approve=True))
        self.center.decide(request["id"], True)
        # A trusted failure after approval makes the approval stale.
        self.center.call(lambda b: b.workflow.finish_task(request["task"], "archivist", error="Operator stopped work"))
        self.assertEqual(self.center.request_detail(request["id"])["status"], "granted_stale")
        with self.assertRaises(ControllerError):
            self.center.release(request["id"])

    def test_state_survives_restart_and_resumes_correct_task(self):
        self.center.run_scenario("approval")
        self.center.run_scenario("delegation")
        approval = self.pending("approval")
        clarification = self.pending("clarification")
        self.reopen()
        self.assertEqual({r["id"] for r in self.center.requests(pending_only=True)},
                         {approval["id"], clarification["id"]})
        self.center.decide(approval["id"], True)
        self.reopen()
        self.assertEqual(self.center.request_detail(approval["id"])["status"], "granted_awaiting_release")
        self.center.release(approval["id"])
        self.assertEqual(self.center.advance(approval["task"])["task_state"], "succeeded")
        self.center.answer(clarification["id"], "English")
        self.reopen()
        self.assertEqual(self.center.advance(clarification["task"])["task_state"], "succeeded")
        states = sorted(t["state"] for t in self.center.tasks())
        self.assertEqual(states, ["succeeded"] * 4)

    # ---- threading ----------------------------------------------------------
    def test_backend_calls_from_many_threads_run_on_one_owner_thread(self):
        owners, errors = set(), []

        def work():
            try:
                owners.add(self.center.call(lambda b: threading.get_ident()))
                self.center.status()
            except Exception as error:  # Collected for the assertion below.
                errors.append(error)
        threads = [threading.Thread(target=work) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(owners, {self.center._thread.ident})
        self.assertNotIn(threading.get_ident(), owners)

    def test_backend_errors_are_reported_and_recoverable(self):
        with self.assertRaises(WorkflowError):
            self.center.post_message("missing-chat", "hello")
        self.assertEqual(self.center.activity[-1]["level"], "error")
        self.assertIsInstance(self.center.status(), dict)
        self.center.close()
        with self.assertRaises(ControllerError):
            self.center.status()

    def test_uncertain_states_are_reported_not_replayed(self):
        self.center.run_scenario("approval")
        request = self.pending("approval")
        self.assertEqual(self.center.uncertain(), [])

        def interrupt(b):
            with b.workflow._transaction():
                b.workflow.db.execute("INSERT INTO tool_calls VALUES(?,?,?,?,?,'reserved',NULL)",
                                      (request["task"], "crashed-call", "archivist", "create_text", "{}"))
                b.workflow.db.execute("UPDATE scheduler_runs SET owner='dead-worker'")
        self.center.call(interrupt)
        kinds = {item["kind"] for item in self.center.uncertain()}
        self.assertEqual(kinds, {"tool_reserved", "controller_claim_held"})
        self.assertEqual(self.center.advance(request["task"])["needs"][0]["kind"], "controller_reconciliation_or_busy")
        self.center.recover_claim(request["task"])
        self.assertEqual({i["kind"] for i in self.center.uncertain()}, {"tool_reserved"})

    # ---- file and memory boundaries ----------------------------------------
    def test_file_inspection_boundaries(self):
        self.center.run_scenario("approval")
        task = self.pending("approval")["task"]
        self.assertEqual(self.center.read_file(task, "keep.txt")["language"], "text")
        with self.assertRaises(FileToolError):  # Agents must use their own FileTools path.
            self.center.call(lambda b: b.inspector.read_file(task, "archivist", "keep.txt"))
        self.center.call(lambda b: b.workflow.register_actor("outsider", "human"))
        with self.assertRaises(WorkflowError):
            self.center.call(lambda b: b.inspector.read_file(task, "outsider", "keep.txt"))
        for path in ("../keep.txt", "/etc/passwd", "a/../keep.txt", ""):
            with self.assertRaises(FileToolError):
                self.center.read_file(task, path)
        directory = self.path / "files" / "tasks" / hashlib.sha256(task.encode()).hexdigest()
        os.symlink("/etc/hosts", directory / "link.txt")
        with self.assertRaises(FileToolError):
            self.center.read_file(task, "link.txt")
        (directory / "unrecorded.txt").write_text("changed outside the broker")
        with self.assertRaises(FileToolError):
            self.center.read_file(task, "missing.txt")
        files = {f["path"] for f in self.center.files(task)}
        self.assertNotIn("unrecorded.txt", files)  # Listings come from broker receipts only.

    def test_memory_view_is_scoped_and_labels_candidates(self):
        result = self.center.run_scenario("memory")
        lessons = self.center.memory()
        self.assertEqual(len(lessons), 1)
        lesson = lessons[0]
        self.assertEqual((lesson["lesson_status"], lesson["proven_improvement"], lesson["intact"]),
                         ("candidate", False, True))
        self.assertEqual([u["outcome"] for u in lesson["uses"]], ["succeeded"])
        self.assertEqual(len(lesson["retrievals"]), 1)
        self.assertEqual(lesson["sources"][0]["observation"]["outcome"], "failed")
        self.assertEqual(self.center.memory(namespace="evaluation"), [])
        self.assertEqual(self.center.memory(owner="editor"), [])
        other = self.center.create_conversation("private", ["writer"])
        self.assertEqual(self.center.memory(chat=other), [])
        self.assertEqual(len(self.center.memory(chat=result["summary"]["chat"])), 1)
        self.center.call(lambda b: b.workflow.register_actor("outsider", "human"))
        with self.assertRaises(WorkflowError):
            self.center.call(lambda b: b.queries.memory("outsider", chat=result["summary"]["chat"]))
        self.assertEqual(self.center.call(lambda b: b.queries.memory("outsider")), [])

    # ---- display safety and modes ------------------------------------------
    def test_redaction_hides_credentials_and_bounds_text(self):
        value = redact({"api_key": "abc", "nested": {"note": "ghp_" + "a" * 30},
                        "body": "x" * 3000, "plain": "ok"})
        self.assertEqual(value["api_key"], "[redacted]")
        self.assertIn("redacted", value["nested"]["note"])
        self.assertTrue(value["body"].endswith("more characters]"))
        self.assertEqual(value["plain"], "ok")

    def test_live_mode_is_explicit_and_never_a_fallback(self):
        with self.assertRaises(ControllerError):
            LiveConfig(model="m", api_key="k", provider="openai")
        self.assertNotIn("api_key", repr(LiveConfig(model="deepseek-chat", api_key="secret-key")))
        self.assertEqual(self.center.status()["mode"], "offline")
        chat = self.center.create_conversation("group", ["coordinator", "writer"])
        self.center.close()
        live = ControlCenter(self.path, live=LiveConfig(model="deepseek-chat", api_key="test-key-not-used"))
        try:
            created = live.create_task(chat, "coordinator", "Draft a note")
            self.assertEqual(created["execution"], "scheduled")
            config = live.call(lambda b: b.workflow.db.execute(
                "SELECT config FROM scheduler_runs WHERE root=?", (created["task"],)).fetchone()[0])
            self.assertEqual(json.loads(config)["mode"], "live")
            self.assertNotIn("test-key-not-used", config)
            self.assertEqual(live.status()["mode"], "live")
        finally:
            live.close()
        self.center = ControlCenter(self.path)
        with self.assertRaises(ControllerError):  # Offline restart cannot silently run a live goal.
            self.center.advance(created["task"])


if __name__ == "__main__":
    unittest.main()
