"""Trusted review lifecycle regressions. Provider responses are scripted only."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.core import WorkflowError
from agent_lab.deepseek import DeepSeekHTTP
from agent_lab.runtime import LiveConfig
from agent_lab.tui.controller import ControlCenter
from test_runner import Script, response


class HumanReviewStateTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.state = Path(directory.name) / 'session'
        self.now = [1000.0]
        self.live = LiveConfig('explicit-fixture-model', 'unused-fixture-key', allow_network=True)
        self.network = patch.object(DeepSeekHTTP, '__call__', side_effect=AssertionError('No real provider calls'))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.center = self.open_center()
        self.addCleanup(lambda: self.center.close())
        self.chat = self.center.create_conversation('group', ['writer', 'editor', 'coordinator'])
        self.task = self.center.create_task(self.chat, 'writer', 'Produce a proposal for human review')['task']

    def open_center(self, human='operator'):
        return ControlCenter(self.state, human=human, live=self.live, clock=lambda: self.now[0])

    def proposal(self):
        script = Script([response(text='Scripted proposal, not proof of success')])
        with patch.object(DeepSeekHTTP, '__call__', side_effect=script):
            self.center.advance(self.task)
        self.assertEqual(len(script.requests), 1)
        self.assertEqual(self.center.task_detail(self.task)['runner']['status'], 'awaiting_verification')
        return script

    def reviews(self):
        return [e for e in self.center.task_detail(self.task)['events'] if e['kind'] == 'human_review_recorded']

    def runner_status(self, task=None):
        return self.center.call(lambda b: b.scheduler(b.root_of(task or self.task)).runner(task or self.task).status())

    def stored_session(self, task=None):
        return self.center.call(lambda b: dict(b.workflow.db.execute(
            'SELECT * FROM runner_sessions WHERE task=?', (task or self.task,)).fetchone()))

    def test_acceptance_survives_restart_and_read_only_views_preserve_raw_history(self):
        self.proposal()
        self.center.review(self.task, accept=True, feedback='Accepted the draft only')
        self.center.close()
        self.center = self.open_center()
        before = self.stored_session()
        self.assertEqual(before['status'], 'awaiting_verification')  # Historical cache is preserved.
        detail = self.center.task_detail(self.task)
        self.assertEqual((detail['task']['state'], detail['runner']['status']), ('succeeded', 'succeeded'))
        self.assertEqual(detail['task']['evidence']['checks'], {'human_review_accepted': True})
        self.assertEqual(self.runner_status()['runner_state'], 'succeeded')
        self.assertEqual(self.stored_session(), before)
        review, = self.reviews()
        self.assertEqual(review['actor'], 'operator')
        self.assertEqual(review['detail'], {'decision': 'accepted', 'feedback': 'Accepted the draft only',
                                            'proposal_attempt': 1})
        self.assertEqual(detail['runner']['attempts'], 1)

    def test_rejection_retains_actual_human_feedback_then_a_new_proposal_can_be_reviewed(self):
        self.proposal()
        self.center.review(self.task, accept=False, feedback='Supply the missing source evidence')
        detail = self.center.task_detail(self.task)
        self.assertEqual((detail['task']['state'], detail['runner']['status']), ('running', 'ready'))
        review, = self.reviews()
        self.assertEqual(review['actor'], 'operator')
        self.assertEqual(review['detail'], {'decision': 'rejected', 'feedback': 'Supply the missing source evidence',
                                            'proposal_attempt': 1})
        self.center.close()
        self.center = self.open_center()
        script = Script([response()])
        with patch.object(DeepSeekHTTP, '__call__', side_effect=script):
            self.center.advance(self.task)
        self.assertIn('Supply the missing source evidence', json.dumps(script.requests[0]))
        self.center.review(self.task, accept=True, feedback='Revised proposal accepted')
        self.assertEqual([e['detail']['proposal_attempt'] for e in self.reviews()], [1, 2])

    def test_repeat_review_cannot_reopen_completed_task_or_record_another_acceptance(self):
        self.proposal()
        self.center.review(self.task, accept=True, feedback='Actual acceptance')
        before = self.center.task_detail(self.task)
        session = self.stored_session()
        for accept in (True, False):
            with self.assertRaisesRegex(WorkflowError, 'awaiting review'):
                self.center.review(self.task, accept=accept, feedback='Duplicate review')
        with self.assertRaisesRegex(WorkflowError, 'awaiting independent verification'):
            self.center.call(lambda b: b.scheduler(self.task).runner(self.task).review_failed('Stale rejection'))
        self.assertEqual(self.center.task_detail(self.task), before)
        self.assertEqual(self.stored_session(), session)

    def test_budget_refusal_rolls_back_human_acceptance_event_and_success_together(self):
        self.proposal()
        self.now[0] += 10000
        with self.assertRaisesRegex(WorkflowError, 'duration'):
            self.center.review(self.task, accept=True, feedback='This cannot bypass the task deadline')
        self.assertEqual(self.reviews(), [])
        self.assertEqual(self.center.task_detail(self.task)['task']['state'], 'running')
        self.assertEqual(self.runner_status()['runner_state'], 'awaiting_verification')

    def test_incomplete_child_refusal_does_not_leave_a_false_acceptance_event(self):
        self.proposal()
        self.center.call(lambda b: b.workflow.create_task(self.chat, 'writer', 'editor', 'Unfinished check', parent=self.task))
        with self.assertRaisesRegex(WorkflowError, 'delegated work'):
            self.center.review(self.task, accept=True, feedback='Parent cannot skip its child')
        self.assertEqual(self.reviews(), [])
        self.assertEqual(self.center.task_detail(self.task)['task']['state'], 'running')

    def test_failed_and_cancelled_legacy_proposals_are_not_actionable_reviews(self):
        self.proposal()
        self.center.call(lambda b: b.workflow.finish_task(self.task, 'writer', error='Observed failure'))
        self.assertEqual(self.center.task_detail(self.task)['runner']['status'], 'failed')
        self.assertEqual(self.runner_status()['runner_state'], 'failed')
        with self.assertRaises(WorkflowError):
            self.center.review(self.task, accept=False, feedback='Cannot reopen a failure')
        # An actual parent failure cancels a running child whose proposal cache remains pending.
        parent = self.center.create_task(self.chat, 'coordinator', 'Parent that will fail')['task']
        def child_setup(b):
            b.workflow.start_task(parent, 'coordinator')
            child = b.workflow.create_task(self.chat, 'coordinator', 'writer', 'Child proposal', parent=parent)
            b.workflow.start_task(child, 'writer')
            scheduler = b.scheduler(parent)
            scheduler.runner(child)
            return child
        child = self.center.call(child_setup)
        script = Script([response()])
        with patch.object(DeepSeekHTTP, '__call__', side_effect=script):
            self.center.call(lambda b: b.scheduler(parent).runner(child).step())
        self.center.call(lambda b: b.workflow.finish_task(parent, 'coordinator', error='Cancel descendant'))
        self.assertEqual(self.center.task_detail(child)['runner']['status'], 'cancelled')
        self.assertEqual(self.runner_status(child)['runner_state'], 'cancelled')
        self.assertEqual(self.stored_session(child)['status'], 'awaiting_verification')
        with self.assertRaises(WorkflowError):
            self.center.review(child, accept=True, feedback='Cannot revive cancellation')

    def test_nonmember_and_agent_cannot_record_human_review(self):
        self.proposal()
        outsider = self.open_center('outsider')
        try:
            with self.assertRaisesRegex(WorkflowError, 'member'):
                outsider.review(self.task, accept=True, feedback='Unauthorized')
        finally:
            outsider.close()
        with self.assertRaisesRegex(WorkflowError, 'human supervisor'):
            self.center.call(lambda b: b.scheduler(self.task).runner(self.task).review_failed(
                'An agent is not a human reviewer', reviewer='writer'))
        self.assertEqual(self.reviews(), [])
        self.assertEqual(self.runner_status()['runner_state'], 'awaiting_verification')

    def test_invalid_decision_or_feedback_does_not_change_proposal(self):
        self.proposal()
        before = self.stored_session()
        for accept, feedback in ((1, ''), (True, None), (True, 'x' * 4097), (False, '')):
            with self.assertRaises(WorkflowError):
                self.center.review(self.task, accept=accept, feedback=feedback)
        self.assertEqual(self.reviews(), [])
        self.assertEqual(self.stored_session(), before)


if __name__ == '__main__':
    unittest.main()
