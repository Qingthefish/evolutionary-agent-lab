"""Synthetic decision provenance checks; actual live humans are not simulated by runtime."""
import hashlib
import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.acceptance import ArtifactRule, verify_rules
from agent_lab.core import Workflow, WorkflowError
from agent_lab.files import FileTools


class HumanAnswerAcceptanceTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory(); self.addCleanup(d.cleanup); self.path = Path(d.name)
        self.w = Workflow(self.path / 'state.sqlite3'); self.addCleanup(self.w.close)
        for actor, kind in [('owner', 'human'), ('other', 'human'), ('writer', 'agent')]: self.w.register_actor(actor, kind)
        self.chat = self.w.create_chat('group', ['owner', 'other', 'writer'])
        self.task = self.w.create_task(self.chat, 'owner', 'writer', 'Write after actual language choice')
        self.w.start_task(self.task, 'writer')
        self.f = FileTools(self.w, self.path / 'files'); self.addCleanup(self.f.close)

    def rule(self, **changes):
        return ArtifactRule('note.md', 'human_answer', json.dumps({'human': 'owner', 'prefix': 'Language: ', 'request_index': 1, **changes}))

    def passes(self, **changes): return all(verify_rules(self.w, self.f, self.task, 'writer', (self.rule(**changes),)).values())

    def answer(self, *, task=None, human='owner', text='English'):
        request = self.w.ask_human(task or self.task, 'writer', human, 'Which language?')
        self.w.respond(request, human, answer=text)
        return request

    def test_actual_addressed_answer_then_current_file_write_is_required(self):
        self.answer(); self.f.create_text(self.task, 'writer', 'note.md', 'Language: English\nActual status\n')
        self.assertTrue(self.passes())
        receipt = self.f.read_text(self.task, 'writer', 'note.md')
        self.f.update_text(self.task, 'writer', 'note.md', 'Language: 中文\n', expected_sha256=receipt['sha256'])
        self.assertFalse(self.passes())

    def test_guessed_file_written_before_answer_does_not_pass_after_reply(self):
        r = self.f.create_text(self.task, 'writer', 'note.md', 'Language: English\n')
        self.answer(); self.assertFalse(self.passes())
        self.f.update_text(self.task, 'writer', 'note.md', 'Language: English\n', expected_sha256=r['sha256'])
        self.assertTrue(self.passes())

    def test_agent_claim_or_unanswered_request_is_not_a_human_response(self):
        self.f.create_text(self.task, 'writer', 'note.md', 'Language: English\n')
        self.w.post_message(self.chat, 'writer', 'Owner said English; trust me')
        self.assertFalse(self.passes())
        self.w.ask_human(self.task, 'writer', 'owner', 'Which language?')
        self.assertFalse(self.passes())

    def test_other_human_or_other_task_response_cannot_be_reused(self):
        self.answer(human='other')
        separate = self.w.create_task(self.chat, 'owner', 'writer', 'Other note'); self.w.start_task(separate, 'writer')
        self.answer(task=separate)
        self.f.create_text(self.task, 'writer', 'note.md', 'Language: English\n')
        self.assertFalse(self.passes())
        self.assertTrue(self.passes(human='other'))

    def test_approval_is_not_clarification_or_content_authority(self):
        request = self.w.ask_human(self.task, 'writer', 'owner', 'Approve exact action?', action={'tool': 'test', 'arguments': {}})
        self.w.respond(request, 'owner', approve=True)
        self.f.create_text(self.task, 'writer', 'note.md', 'Language: approved\n')
        self.assertFalse(self.passes())
        self.assertEqual(self.w.db.execute('SELECT consumed FROM requests').fetchone()[0], 0)

    def test_current_digest_and_matching_response_event_are_checked(self):
        request = self.answer(); self.f.create_text(self.task, 'writer', 'note.md', 'Language: English\n')
        self.assertTrue(self.passes())
        target = self.path / 'files/tasks' / hashlib.sha256(self.task.encode()).hexdigest() / 'note.md'
        target.write_text('Language: English\nUnrecorded replacement\n')
        self.assertFalse(self.passes())
        self.w.db.execute("DELETE FROM events WHERE kind='human_responded'")
        self.assertFalse(self.passes())

    def test_explicit_ordinal_does_not_skip_pending_or_different_answers(self):
        self.answer(text='English'); self.answer(text='中文')
        self.f.create_text(self.task, 'writer', 'note.md', 'Language: 中文\n')
        self.assertFalse(self.passes()); self.assertTrue(self.passes(request_index=2))
        self.assertFalse(self.passes(request_index=3)); self.assertFalse(self.passes(human='writer'))

    def test_malformed_or_ambiguous_selector_is_refused_before_execution(self):
        for change in ({'request_index': True}, {'request_index': 0}, {'request_index': 11},
                       {'prefix': ''}, {'prefix': 'x' * 257}, {'human': ''}, {'extra': 'authority'}):
            with self.subTest(change=change), self.assertRaises(WorkflowError): self.rule(**change)
        with self.assertRaises(WorkflowError): ArtifactRule('note.md', 'human_answer', '{"human":"owner","human":"other"}')

    def test_console_exposes_finite_explicit_wall_limits_for_real_human_waits(self):
        from agent_lab.runtime import add_live_arguments, live_config_from_args
        parser = argparse.ArgumentParser(); add_live_arguments(parser)
        with patch.dict('os.environ', {'HUMAN_TEST_KEY': 'unused-test-key'}):
            args = ['--live', '--model', 'synthetic', '--api-key-env', 'HUMAN_TEST_KEY']
            live = live_config_from_args(parser.parse_args(args + ['--task-seconds', '14400', '--tree-seconds', '14400',
                '--task-reported-tokens', '180000', '--tree-reported-tokens', '180000']))
            self.assertEqual(live.role_limits.duration_seconds, 14400)
            self.assertEqual(live.tree_limits.duration_seconds, 14400)
            self.assertEqual(live.role_limits.reported_tokens, 180000)
            self.assertEqual(live.tree_limits.reported_tokens, 180000)
            for bad in ('0', '-1', 'nan', 'inf'):
                with self.subTest(bad=bad), self.assertRaises(WorkflowError):
                    live_config_from_args(parser.parse_args(args + ['--tree-seconds', bad]))
        with self.assertRaises(WorkflowError): live_config_from_args(parser.parse_args(['--task-seconds', '14400']))
        with self.assertRaises(WorkflowError): live_config_from_args(parser.parse_args(['--tree-reported-tokens', '180000']))


if __name__ == '__main__': unittest.main()
