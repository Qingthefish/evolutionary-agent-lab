from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest

from agent_lab import Workflow, WorkflowError
from agent_lab.files import FileTools, FileToolError
from agent_lab.__main__ import file_demo


class FileToolsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.database = self.root / "workflow.sqlite3"
        self.files_root = self.root / "files"
        self.workflow = Workflow(self.database)
        for actor, kind in [("user", "human"), ("writer", "agent"), ("reviewer", "agent")]:
            self.workflow.register_actor(actor, kind)
        self.chat = self.workflow.create_chat("group", ["user", "writer", "reviewer"])
        self.source = self.new_task("writer")
        self.target = self.new_task("reviewer")
        self.files = FileTools(self.workflow, self.files_root)

    def tearDown(self):
        self.files.close()
        self.workflow.close()
        self.directory.cleanup()

    def new_task(self, agent, chat=None):
        task = self.workflow.create_task(chat or self.chat, "user", agent, "Test file task")
        self.workflow.start_task(task, agent)
        return task

    def task_path(self, task):
        # Test-only direct access simulates hostile directory entries and corruption.
        return self.files_root / "tasks" / hashlib.sha256(task.encode()).hexdigest()

    def offer(self, text="Original text"):
        receipt = self.files.create_text(self.source, "writer", "note.txt", text)
        return self.files.offer_artifact(
            self.source, "writer", "note.txt", self.target, expected_sha256=receipt["sha256"],
        )

    def test_crud_uses_receipts_and_rejects_stale_updates_and_deletes(self):
        original = self.files.create_text(self.source, "writer", "nested/note.txt", "first")
        self.assertEqual(self.files.read_text(self.source, "writer", "nested/note.txt")["content"], "first")
        updated = self.files.update_text(
            self.source, "writer", "nested/note.txt", "second", expected_sha256=original["sha256"],
        )
        for operation in [lambda: self.files.update_text(
            self.source, "writer", "nested/note.txt", "overwrite", expected_sha256=original["sha256"],
        ), lambda: self.files.delete_text(
            self.source, "writer", "nested/note.txt", expected_sha256=original["sha256"],
        )]:
            with self.assertRaises(FileToolError):
                operation()
        self.assertEqual(self.files.read_text(self.source, "writer", "nested/note.txt")["content"], "second")
        self.files.delete_text(self.source, "writer", "nested/note.txt", expected_sha256=updated["sha256"])
        with self.assertRaises(FileToolError):
            self.files.read_text(self.source, "writer", "nested/note.txt")
        events = [event["kind"] for event in self.workflow.events(self.source, "user")]
        self.assertIn("file_created", events)
        self.assertIn("file_updated", events)
        self.assertIn("file_deleted", events)

    def test_create_never_overwrites_an_existing_file(self):
        self.files.create_text(self.source, "writer", "note.txt", "keep")
        with self.assertRaises(FileToolError):
            self.files.create_text(self.source, "writer", "note.txt", "replace")
        self.assertEqual(self.files.read_text(self.source, "writer", "note.txt")["content"], "keep")

    def test_task_and_actor_ownership_is_enforced(self):
        self.files.create_text(self.source, "writer", "note.txt", "private")
        with self.assertRaises(WorkflowError):
            self.files.read_text(self.source, "reviewer", "note.txt")
        with self.assertRaises(FileToolError):
            self.files.read_text(self.target, "reviewer", "note.txt")
        sibling = self.new_task("writer")
        with self.assertRaises(FileToolError):
            self.files.read_text(sibling, "writer", "note.txt")

    def test_absolute_traversal_and_ambiguous_paths_are_rejected(self):
        paths = ["../escape.txt", "/tmp/escape.txt", "a/../../escape.txt", "a//note.txt",
                 "a/./note.txt", "a\\note.txt", "", "a/", "nul\0.txt"]
        for path in paths:
            with self.subTest(path=path), self.assertRaises(FileToolError):
                self.files.create_text(self.source, "writer", path, "blocked")
        self.assertFalse((self.root / "escape.txt").exists())

    def test_symlink_file_and_parent_cannot_escape(self):
        self.files.create_text(self.source, "writer", "seed.txt", "seed")
        outside = self.root / "outside.txt"
        outside.write_text("keep")
        link = self.task_path(self.source) / "link.txt"
        link.symlink_to(outside)
        (self.task_path(self.source) / "outside-dir").symlink_to(self.root, target_is_directory=True)
        for operation in [lambda: self.files.read_text(self.source, "writer", "link.txt"),
                          lambda: self.files.update_text(self.source, "writer", "link.txt", "bad", expected_sha256="x"),
                          lambda: self.files.delete_text(self.source, "writer", "link.txt", expected_sha256="x"),
                          lambda: self.files.create_text(self.source, "writer", "outside-dir/new.txt", "bad")]:
            with self.assertRaises(FileToolError):
                operation()
        self.assertEqual(outside.read_text(), "keep")
        self.assertFalse((self.root / "new.txt").exists())

    def test_hard_links_and_nonregular_files_are_rejected(self):
        self.files.create_text(self.source, "writer", "seed.txt", "seed")
        outside = self.root / "outside.txt"
        outside.write_text("private")
        os.link(outside, self.task_path(self.source) / "hard.txt")
        os.mkfifo(self.task_path(self.source) / "pipe.txt")
        for path in ["hard.txt", "pipe.txt"]:
            with self.assertRaises(FileToolError):
                self.files.read_text(self.source, "writer", path)
        self.assertEqual(outside.read_text(), "private")

    def test_file_size_and_utf8_are_checked_for_existing_files(self):
        small = FileTools(self.workflow, self.files_root, max_bytes=8)
        try:
            with self.assertRaises(FileToolError):
                small.create_text(self.source, "writer", "large.txt", "123456789")
            small.create_text(self.source, "writer", "small.txt", "ok")
            (self.task_path(self.source) / "injected.txt").write_bytes(b"x" * 9)
            (self.task_path(self.source) / "binary.txt").write_bytes(b"\xff")
            for path in ["injected.txt", "binary.txt"]:
                with self.assertRaises(FileToolError):
                    small.read_text(self.source, "writer", path)
        finally:
            small.close()

    def test_artifact_is_a_snapshot_not_a_live_shared_path(self):
        offer = self.offer()
        original = self.files.read_text(self.source, "writer", "note.txt")
        self.files.update_text(self.source, "writer", "note.txt", "Later content", expected_sha256=original["sha256"])
        received = self.files.accept_artifact(self.target, "reviewer", offer["artifact_id"], "inbox/note.txt")
        self.assertEqual(received["sha256"], offer["sha256"])
        self.assertEqual(self.files.read_text(self.target, "reviewer", "inbox/note.txt")["content"], "Original text")
        with self.assertRaises(FileToolError):
            self.files.accept_artifact(self.target, "reviewer", offer["artifact_id"], "second.txt")

    def test_wrong_task_cannot_accept_an_offer_even_with_same_actor(self):
        offer = self.offer()
        different = self.new_task("reviewer")
        with self.assertRaises(FileToolError):
            self.files.accept_artifact(different, "reviewer", offer["artifact_id"], "note.txt")
        with self.assertRaises(WorkflowError):
            self.files.accept_artifact(self.target, "writer", offer["artifact_id"], "note.txt")

    def test_cross_conversation_handoff_is_rejected(self):
        other = self.workflow.create_chat("group", ["user", "writer", "reviewer"])
        target = self.new_task("reviewer", other)
        receipt = self.files.create_text(self.source, "writer", "note.txt", "private")
        with self.assertRaises(FileToolError):
            self.files.offer_artifact(self.source, "writer", "note.txt", target, expected_sha256=receipt["sha256"])

    def test_snapshot_corruption_is_detected_before_import(self):
        offer = self.offer()
        (self.files_root / "handoffs" / offer["artifact_id"]).write_text("tampered")
        with self.assertRaises(FileToolError):
            self.files.accept_artifact(self.target, "reviewer", offer["artifact_id"], "note.txt")
        self.assertFalse((self.task_path(self.target) / "note.txt").exists())

    def test_failed_source_cannot_supply_an_artifact(self):
        offer = self.offer()
        self.workflow.finish_task(self.source, "writer", error="Source output invalid")
        with self.assertRaises(FileToolError):
            self.files.accept_artifact(self.target, "reviewer", offer["artifact_id"], "note.txt")

    def test_artifact_and_files_survive_reopening(self):
        offer = self.offer()
        self.files.complete_from_text(self.source, "writer", {"note.txt": "Original text"})
        self.files.close()
        self.workflow.close()
        self.workflow = Workflow(self.database)
        self.files = FileTools(self.workflow, self.files_root)
        self.files.accept_artifact(self.target, "reviewer", offer["artifact_id"], "note.txt")
        self.files.complete_from_text(self.target, "reviewer", {"note.txt": "Original text"})
        self.assertEqual(self.workflow.task(self.target, "user")["state"], "succeeded")

    def test_concurrent_import_is_at_most_once(self):
        offer = self.offer()
        ready = threading.Barrier(2)

        def accept(index):
            workflow = Workflow(self.database)
            files = FileTools(workflow, self.files_root)
            try:
                ready.wait(timeout=5)
                try:
                    files.accept_artifact(self.target, "reviewer", offer["artifact_id"], f"copy-{index}.txt")
                    return True
                except WorkflowError:
                    return False
            finally:
                files.close()
                workflow.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(accept, range(2)))
        self.assertEqual(sorted(outcomes), [False, True])
        self.assertEqual(len(list(self.task_path(self.target).glob("copy-*.txt"))), 1)

    def test_mismatched_or_missing_artifact_never_completes_task(self):
        self.files.create_text(self.source, "writer", "note.txt", "actual")
        for expected in [{"note.txt": "wrong"}, {"missing.txt": "expected"}, {}]:
            with self.assertRaises(WorkflowError):
                self.files.complete_from_text(self.source, "writer", expected)
            self.assertEqual(self.workflow.task(self.source, "user")["state"], "running")
        self.files.complete_from_text(self.source, "writer", {"note.txt": "actual"})
        self.assertEqual(self.workflow.task(self.source, "user")["state"], "succeeded")
        event = next(e for e in self.workflow.events(self.source, "user") if e["kind"] == "artifacts_verified")
        proof = json.loads(event["detail"])["artifacts"][0]
        self.assertEqual(proof["actual_sha256"], hashlib.sha256(b"actual").hexdigest())
        self.assertEqual(proof["actual_sha256"], proof["expected_sha256"])

    def test_paused_or_terminated_tasks_cannot_mutate_files(self):
        request = self.workflow.ask_human(self.source, "writer", "user", "Proceed?")
        with self.assertRaises(FileToolError):
            self.files.create_text(self.source, "writer", "note.txt", "blocked")
        self.workflow.respond(request, "user", answer="Proceed")
        self.workflow.finish_task(self.source, "writer", error="Cancelled execution")
        with self.assertRaises(FileToolError):
            self.files.create_text(self.source, "writer", "note.txt", "blocked")

    def test_database_cannot_be_silently_rebound_to_a_different_root(self):
        with self.assertRaises(FileToolError):
            FileTools(self.workflow, self.root / "different-root")

    def test_insecure_or_symlink_root_is_rejected(self):
        shared = self.root / "shared"
        shared.mkdir(mode=0o755)
        shared.chmod(0o755)
        with self.assertRaises(FileToolError):
            FileTools(self.workflow, shared)
        linked = self.root / "linked"
        linked.symlink_to(self.files_root, target_is_directory=True)
        with self.assertRaises((FileToolError, OSError)):
            FileTools(self.workflow, linked)

    def test_missing_sandbox_cannot_fall_back_to_host_execution(self):
        marker = self.root / "must-not-exist"
        with self.assertRaises(FileToolError):
            self.files.execute_code(self.source, "writer", [sys.executable, "-c", f"open({str(marker)!r}, 'w').close()"])
        self.assertFalse(marker.exists())
        self.assertEqual(self.workflow.task(self.source, "user")["state"], "running")

    def test_file_fixture_checks_actual_copies_without_claiming_a_model_result(self):
        location = self.root / "demo"
        report = file_demo(location)
        self.assertEqual(report["source_receipt"]["sha256"], report["received_receipt"]["sha256"])
        self.assertEqual(report["metrics"]["subtasks"]["succeeded"], 2)
        self.assertEqual(report["code_execution"], "unavailable_no_process_sandbox")
        self.assertFalse(report["process_sandbox"])
        self.assertFalse(report["benchmark_valid"])
        self.assertEqual(report["model_calls"], 0)
        self.assertEqual(len(list((location / "files/tasks").rglob("*.txt"))), 2)


if __name__ == "__main__":
    unittest.main()
