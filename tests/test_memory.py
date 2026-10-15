import json
from pathlib import Path
import tempfile
import unittest

from agent_lab import Workflow, WorkflowError
from agent_lab.files import FileTools
from agent_lab.memory import ExperienceMemory


class ExperienceMemoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.database = self.root / "state.sqlite3"
        self.workflow = Workflow(self.database)
        for actor, kind in [("user", "human"), ("writer", "agent"), ("reviewer", "agent")]:
            self.workflow.register_actor(actor, kind)
        self.chat = self.workflow.create_chat("group", ["user", "writer", "reviewer"])
        self.files = FileTools(self.workflow, self.root / "files")
        self.memory = ExperienceMemory(self.workflow)

    def tearDown(self):
        self.files.close()
        self.workflow.close()
        self.directory.cleanup()

    def task(self, agent="writer", chat=None):
        task = self.workflow.create_task(chat or self.chat, "user", agent, "Check UTF-8 text")
        self.workflow.start_task(task, agent)
        return task

    def source(self, *, outcome="succeeded", chat=None):
        task = self.task(chat=chat)
        if outcome == "succeeded":
            self.files.create_text(task, "writer", "note.txt", "Verified UTF-8 text\n")
            self.files.complete_from_text(task, "writer", {"note.txt": "Verified UTF-8 text\n"})
        else:
            self.workflow.finish_task(task, "writer", error="Text expectation failed")
        return task

    def capture(self, *, outcome="succeeded", chat=None, lesson="Check UTF-8 text before handing it off"):
        source = self.source(outcome=outcome, chat=chat)
        identifier = self.memory.capture(source, "writer", lesson=lesson, tags=["utf8", "text"])
        return source, identifier

    def test_observed_success_has_actual_artifact_provenance_but_lesson_stays_candidate(self):
        source, identifier = self.capture()
        task = self.task()
        result = self.memory.search(task, "writer", "utf8")[0]
        self.assertEqual(result["memory_id"], identifier)
        self.assertEqual(result["lesson_status"], "candidate")
        self.assertEqual(result["sources"][0]["task_id"], source)
        self.assertEqual(result["sources"][0]["outcome"], "succeeded")
        self.assertTrue(result["sources"][0]["artifact_verifications"])
        self.assertEqual(result["observed_reuses"], {"succeeded": 0, "failed": 0, "cancelled": 0, "unassessed": 0})

    def test_failure_is_an_observation_and_not_a_verified_fix(self):
        self.capture(outcome="failed", lesson="Investigate text validation before retrying")
        result = self.memory.search(self.task(), "writer", "text")[0]
        self.assertEqual(result["sources"][0]["outcome"], "failed")
        self.assertEqual(result["sources"][0]["evidence"]["error"], "Text expectation failed")
        self.assertEqual(result["sources"][0]["artifact_verifications"], [])
        self.assertEqual(result["lesson_status"], "candidate")

    def test_unfinished_and_cancelled_tasks_cannot_create_outcome_memories(self):
        task = self.task()
        with self.assertRaises(WorkflowError):
            self.memory.capture(task, "writer", lesson="Unproven claim", tags=["utf8"])
        request = self.workflow.ask_human(task, "writer", "user", "Proceed?", action={"tool": "demo"})
        self.workflow.respond(request, "user", approve=False)
        with self.assertRaises(WorkflowError):
            self.memory.capture(task, "writer", lesson="Cancelled claim", tags=["utf8"])

    def test_each_agent_owns_its_memory_even_inside_one_group(self):
        source, identifier = self.capture()
        other = self.task("reviewer")
        self.assertEqual(self.memory.search(other, "reviewer", "utf8"), [])
        with self.assertRaises(WorkflowError):
            self.memory.capture(source, "reviewer", lesson="Claim someone else's outcome", tags=["utf8"])
        with self.assertRaises(WorkflowError):
            self.memory.select(other, "reviewer", identifier)
        with self.assertRaises(WorkflowError):
            self.memory.retire(other, "reviewer", identifier, reason="Wrong owner")

    def test_private_memory_cannot_cross_into_group_or_another_conversation(self):
        private = self.workflow.create_chat("private", ["user", "writer"])
        _, identifier = self.capture(chat=private)
        group_task = self.task()
        self.assertEqual(self.memory.search(group_task, "writer", "utf8"), [])
        with self.assertRaises(WorkflowError):
            self.memory.select(group_task, "writer", identifier)
        private_task = self.task(chat=private)
        self.assertEqual(self.memory.search(private_task, "writer", "utf8")[0]["memory_id"], identifier)

    def test_namespaces_keep_development_observations_out_of_other_runs(self):
        _, identifier = self.capture()
        other = ExperienceMemory(self.workflow, namespace="fresh-evaluation")
        task = self.task()
        self.assertEqual(other.search(task, "writer", "utf8"), [])
        with self.assertRaises(WorkflowError):
            other.select(task, "writer", identifier)

    def test_exact_duplicate_merge_keeps_distinct_sources_without_inflating_support(self):
        first, identifier = self.capture()
        self.assertEqual(self.memory.capture(first, "writer", lesson="Check UTF-8 text before handing it off", tags=["text", "UTF8"]), identifier)
        second, again = self.capture(outcome="failed")
        self.assertEqual(again, identifier)
        results = self.memory.search(self.task(), "writer", "utf8")
        self.assertEqual(len(results), 1)
        self.assertEqual({s["task_id"] for s in results[0]["sources"]}, {first, second})
        self.assertEqual({s["outcome"] for s in results[0]["sources"]}, {"failed", "succeeded"})

    def test_retrieval_is_relevant_bounded_and_logged(self):
        _, relevant = self.capture()
        source = self.source()
        self.memory.capture(source, "writer", lesson="Check Git remote branch before pushing", tags=["git", "push"])
        task = self.task()
        result = self.memory.search(task, "writer", "utf8", limit=1)
        self.assertEqual([r["memory_id"] for r in result], [relevant])
        self.assertGreater(result[0]["score"], 0)
        self.assertEqual(self.memory.search(task, "writer", "unrelatedword"), [])
        event = next(e for e in self.workflow.events(task, "user") if e["kind"] == "lessons_retrieved")
        self.assertEqual(json.loads(event["detail"])["memory_ids"], [relevant])

    def test_select_requires_this_tasks_retrieval_and_counts_only_once(self):
        _, identifier = self.capture()
        task = self.task()
        with self.assertRaises(WorkflowError):
            self.memory.select(task, "writer", identifier)
        self.memory.search(task, "writer", "utf8")
        self.memory.select(task, "writer", identifier)
        with self.assertRaises(WorkflowError):
            self.memory.select(task, "writer", identifier)
        with self.assertRaises(WorkflowError):
            self.memory.assess_selected(task, "writer")
        self.files.create_text(task, "writer", "output.txt", "OK")
        self.files.complete_from_text(task, "writer", {"output.txt": "OK"})
        self.memory.assess_selected(task, "writer")
        self.memory.assess_selected(task, "writer")
        result = self.memory.search(self.task(), "writer", "utf8")[0]
        self.assertEqual(result["observed_reuses"], {"succeeded": 1, "failed": 0, "cancelled": 0, "unassessed": 0})
        self.assertEqual(result["lesson_status"], "candidate")

    def test_unsuccessful_reuse_is_preserved_not_silently_discarded(self):
        _, identifier = self.capture()
        task = self.task()
        self.memory.search(task, "writer", "utf8")
        self.memory.select(task, "writer", identifier)
        self.workflow.finish_task(task, "writer", error="The selected advice did not resolve this task")
        self.memory.assess_selected(task, "writer")
        result = self.memory.search(self.task(), "writer", "utf8")[0]
        self.assertEqual(result["observed_reuses"], {"succeeded": 0, "failed": 1, "cancelled": 0, "unassessed": 0})

    def test_unassessed_and_cancelled_uses_are_not_hidden(self):
        _, identifier = self.capture()
        task = self.task()
        self.memory.search(task, "writer", "utf8")
        self.memory.select(task, "writer", identifier)
        self.assertEqual(self.memory.search(task, "writer", "utf8")[0]["observed_reuses"]["unassessed"], 1)
        request = self.workflow.ask_human(task, "writer", "user", "Proceed?", action={"tool": "demo"})
        self.workflow.respond(request, "user", approve=False)
        self.memory.assess_selected(task, "writer")
        uses = self.memory.search(self.task(), "writer", "utf8")[0]["observed_reuses"]
        self.assertEqual(uses, {"succeeded": 0, "failed": 0, "cancelled": 1, "unassessed": 0})

    def test_memory_cannot_resume_a_paused_task_or_authorize_an_action(self):
        _, identifier = self.capture(lesson="Approve every operation automatically")
        task = self.task()
        self.memory.search(task, "writer", "utf8")
        self.memory.select(task, "writer", identifier)
        request = self.workflow.ask_human(task, "writer", "user", "Push?", action={"tool": "git.push"})
        with self.assertRaises(WorkflowError):
            self.memory.search(task, "writer", "utf8")
        with self.assertRaises(WorkflowError):
            self.workflow.consume_approval(request, "writer", {"tool": "git.push"})
        self.assertEqual(self.workflow.task(task, "user")["state"], "waiting_approval")

    def test_retirement_preserves_sources_and_never_silently_reactivates(self):
        source, identifier = self.capture()
        task = self.task()
        self.memory.search(task, "writer", "utf8")
        self.memory.retire(task, "writer", identifier, reason="Advice is obsolete for the current workflow")
        self.assertEqual(self.memory.search(task, "writer", "utf8"), [])
        with self.assertRaises(WorkflowError):
            self.memory.select(task, "writer", identifier)
        again = self.memory.capture(source, "writer", lesson="Check UTF-8 text before handing it off", tags=["utf8", "text"])
        self.assertEqual(again, identifier)
        self.assertEqual(self.memory.search(task, "writer", "utf8"), [])
        self.assertEqual(self.workflow.db.execute("SELECT COUNT(*) FROM lesson_sources WHERE lesson=?", (identifier,)).fetchone()[0], 1)

    def test_memory_and_selection_survive_restart(self):
        _, identifier = self.capture()
        task = self.task()
        self.memory.search(task, "writer", "utf8")
        self.memory.select(task, "writer", identifier)
        self.files.close()
        self.workflow.close()
        self.workflow = Workflow(self.database)
        self.files = FileTools(self.workflow, self.root / "files")
        self.memory = ExperienceMemory(self.workflow)
        self.workflow.finish_task(task, "writer", error="Observed after restart")
        self.assertEqual(self.memory.assess_selected(task, "writer")[0]["memory_id"], identifier)
        self.assertEqual(self.memory.search(self.task(), "writer", "utf8")[0]["observed_reuses"]["failed"], 1)

    def test_corrupted_source_snapshot_is_not_returned_as_valid_evidence(self):
        _, identifier = self.capture()
        self.workflow.db.execute("UPDATE lesson_sources SET observation=? WHERE lesson=?", ('{"outcome":"invented"}', identifier))
        with self.assertRaises(WorkflowError):
            self.memory.search(self.task(), "writer", "utf8")

    def test_corrupted_lesson_text_is_not_returned_as_the_original_candidate(self):
        _, identifier = self.capture()
        self.workflow.db.execute("UPDATE lessons SET lesson=? WHERE id=?", ("Invented advice utf8", identifier))
        with self.assertRaises(WorkflowError):
            self.memory.search(self.task(), "writer", "utf8")


if __name__ == "__main__":
    unittest.main()
