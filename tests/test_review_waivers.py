"""A review accepts delivered work; waiving a failed child requires exact explicit IDs.

Synthetic lifecycle inputs exercise the actual review transaction, not model quality.
"""

import unittest

from agent_lab.core import WorkflowError
from agent_lab.evaluation.official_live import review_proposal
import test_completion_lifecycle as lifecycle


class ReviewWaiverTests(unittest.TestCase):
    def setUp(self):
        self.fixture = lifecycle.Lifecycle()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

        def chief(payload, number, state):
            if number == 1:
                return lifecycle.reply(("delegate_task", {"assignee": "reporter", "title": "Report"}))
            return lifecycle.reply(("submit_for_verification", {
                "summary": "Delivered the final package; failed reporter work is covered by the chief"}))

        self.fixture.build("newsroom", {
            "chief_editor": lifecycle.Agent(chief),
            "reporter": lifecycle.Agent(lifecycle.worker("blocker")),
        }, cap=40)
        for _ in range(12):
            state = self.fixture.scheduler.step()
            if state["state"] == "blocked":
                break
        self.workflow = self.fixture.workflow
        self.root = self.fixture.root
        self.child = self.workflow.db.execute("SELECT id FROM tasks WHERE parent=?", (self.root,)).fetchone()[0]
        self.assertEqual(self.workflow.task(self.child, "requester")["state"], "failed")

    def accept(self, **kwargs):
        return review_proposal(self.fixture.scheduler, self.root, "accept",
                               "Synthetic review checked the final package against the requested work", **kwargs)

    def assert_unaccepted(self):
        self.assertEqual(self.workflow.task(self.root, "requester")["state"], "running")
        self.assertEqual(self.workflow.db.execute(
            "SELECT count(*) FROM events WHERE kind IN ('human_review_recorded','failed_subtask_waived')").fetchone()[0], 0)

    def test_plain_accept_does_not_implicitly_waive_a_failed_child(self):
        with self.assertRaisesRegex(WorkflowError, "explicit.*waiv"):
            self.accept()
        self.assert_unaccepted()

    def test_exact_explicit_waiver_preserves_the_failed_child(self):
        self.accept(waive_failed_subtasks=[self.child])
        self.assertEqual(self.workflow.task(self.root, "requester")["state"], "succeeded")
        self.assertEqual(self.workflow.task(self.child, "requester")["state"], "failed")
        self.assertEqual(self.workflow.db.execute(
            "SELECT count(*) FROM events WHERE kind='failed_subtask_waived'").fetchone()[0], 1)

    def test_wrong_or_duplicate_waiver_cannot_change_state(self):
        for value in ([self.root], [self.child, self.child], self.child, [42]):
            with self.subTest(value=value), self.assertRaises(WorkflowError):
                self.accept(waive_failed_subtasks=value)
            self.assert_unaccepted()

    def test_a_new_failure_after_the_proposal_requires_a_new_proposal(self):
        task = self.workflow.create_task(self.workflow.task(self.root, "requester")["chat"],
                                         "chief_editor", "editor", "Later work", parent=self.root)
        self.workflow.start_task(task, "editor")
        self.workflow.finish_task(task, "editor", error="Synthetic failure after the proposal")
        with self.assertRaisesRegex(WorkflowError, "changed.*proposal"):
            self.accept(waive_failed_subtasks=[self.child])
        self.assert_unaccepted()

    def test_budget_refusal_rolls_back_the_review_and_waiver(self):
        self.workflow.db.execute("UPDATE tree_budgets SET tokens=999999999")
        with self.assertRaises(WorkflowError):
            self.accept(waive_failed_subtasks=[self.child])
        self.assert_unaccepted()

    def test_rejection_cannot_record_a_waiver(self):
        with self.assertRaises(WorkflowError):
            review_proposal(self.fixture.scheduler, self.root, "reject", "Synthetic missing delivery",
                            waive_failed_subtasks=[self.child])
        self.assert_unaccepted()


if __name__ == "__main__":
    unittest.main()
