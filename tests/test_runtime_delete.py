"""B05 runtime wiring and real file effects; provider responses are mocked.

No real model call or model-performance result follows from these checks.
"""

import argparse
import contextlib
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.acceptance import ArtifactRule
from agent_lab.console import main as console_main
from agent_lab.core import WorkflowError
from agent_lab.deepseek import DeepSeekHTTP
from agent_lab.evaluation.manifest import build_manifest
from agent_lab.evaluation.plan import DevelopmentPlan
from agent_lab.git_tools import TrustedRepository
from agent_lab.runtime import (LiveConfig, add_live_arguments, live_config_from_args,
                               live_members, live_roles)
from agent_lab.tui.controller import ControlCenter
from test_runner import Script, response, tool

SOURCE = Path(__file__).resolve().parents[1]
CONTENT = 'Obsolete fixture text\n'
SHA = hashlib.sha256(CONTENT.encode()).hexdigest()


class RuntimeDeletionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.live = LiveConfig('explicit-test-model', 'unused-fixture-key', enable_delete=True)

    def center(self, *, name='state', live=None):
        center = ControlCenter(self.path/name, live=self.live if live is None else live)
        self.addCleanup(center.close)
        return center

    def task(self, center, *, other_human=False):
        if other_human:
            center.call(lambda b: b.workflow.register_actor('other-human', 'human'))
        chat = center.create_conversation('group' if other_human else 'private',
            ['writer', 'other-human'] if other_human else ['writer'])
        task = center.create_task(chat, 'writer', 'Remove obsolete.txt after approval',
            root_criteria=(ArtifactRule('obsolete.txt', 'absent'),))['task']
        return chat, task

    def begin_deletion(self, *, other_human=False):
        center = self.center()
        chat, task = self.task(center, other_human=other_human)
        script = Script([
            response([tool('create_text', {'path':'obsolete.txt', 'content':CONTENT}, 'create')]),
            response([tool('read_text', {'path':'obsolete.txt'}, 'read')]),
            response([tool('delete_text', {'path':'obsolete.txt', 'expected_sha256':SHA}, 'delete')]),
            response(text='Scripted proposal; independently check file absence.'),
        ])
        with patch.object(DeepSeekHTTP, '__call__', side_effect=script):
            center.advance(task)
        self.assertEqual(center.task_detail(task)['task']['state'], 'waiting_approval')
        self.assertEqual(center.read_file(task, 'obsolete.txt')['content'], CONTENT)
        request = center.requests(pending_only=True)[0]['id']
        return center, chat, task, request, script

    def test_capability_requires_a_boolean_and_explicit_live_cli_mode(self):
        for value in (1, 'true', None):
            with self.subTest(value=value), self.assertRaises(WorkflowError):
                replace(self.live, enable_delete=value)
        parser = argparse.ArgumentParser()
        add_live_arguments(parser)
        with self.assertRaises(WorkflowError):
            live_config_from_args(parser.parse_args(['--enable-delete']))
        with patch.dict('os.environ', {'B05_TEST_KEY':'unused-fixture-key'}, clear=True):
            args = ['--live','--model','explicit-test-model','--api-key-env','B05_TEST_KEY']
            self.assertFalse(live_config_from_args(parser.parse_args(args)).enable_delete)
            self.assertTrue(live_config_from_args(parser.parse_args(args+['--enable-delete'])).enable_delete)

    def test_all_configured_roles_gain_only_the_existing_delete_tool(self):
        repository = TrustedRepository('fixture', str(self.path/'repo'), ('work',), ('notes/',))
        for base in (replace(self.live, enable_delete=False),
                     replace(self.live, enable_delete=False, docker_host='unix:///unused.sock',
                             python_image='python@sha256:'+'0'*64, repositories=(repository,))):
            members = live_members(base)
            off, on = live_roles(members, base), live_roles(members, replace(base, enable_delete=True))
            for agent in members:
                with self.subTest(agent=agent):
                    self.assertNotIn('delete_text', off[agent].tools)
                    self.assertEqual(on[agent].tools, (*off[agent].tools, 'delete_text'))
                    self.assertEqual(on[agent].delegates, off[agent].delegates)
                    self.assertEqual(on[agent].limits, off[agent].limits)
                    self.assertEqual(on[agent].tool_calls, off[agent].tool_calls)
                    self.assertTrue(on[agent].instructions.startswith(off[agent].instructions))
                    self.assertFalse(set(on[agent].tools) & {'release_approved','respond','finish_task','run_shell'})

    def test_default_roles_and_persisted_runs_cannot_silently_acquire_or_lose_permission(self):
        for enabled in (False, True):
            name = 'enabled' if enabled else 'default'
            live = replace(self.live, enable_delete=enabled)
            center = self.center(name=name, live=live)
            _, task = self.task(center)
            before = center.call(lambda b: b.workflow.db.execute(
                'SELECT config FROM scheduler_runs WHERE root=?', (task,)).fetchone()[0])
            center.close()
            changed = self.center(name=name, live=replace(live, enable_delete=not enabled))
            with self.assertRaises(WorkflowError):
                changed.call(lambda b: b.scheduler(task))
            changed.close()
            original = self.center(name=name, live=live)
            original.call(lambda b: b.scheduler(task))
            after = original.call(lambda b: b.workflow.db.execute(
                'SELECT config FROM scheduler_runs WHERE root=?', (task,)).fetchone()[0])
            self.assertEqual(before, after)
            self.assertNotIn(live.api_key, after)

    def test_disabled_gateway_refuses_a_hallucinated_delete_before_side_effects(self):
        center = self.center(live=replace(self.live, enable_delete=False))
        _, task = self.task(center)
        def rejected(b):
            b.workflow.start_task(task, 'writer')
            b.files.create_text(task, 'writer', 'obsolete.txt', CONTENT)
            b.scheduler(task).runner(task).gateway.dispatch(tool('delete_text',
                {'path':'obsolete.txt','expected_sha256':SHA}))
        with self.assertRaises(WorkflowError):
            center.call(rejected)
        self.assertEqual(center.requests(), [])
        self.assertEqual(center.read_file(task, 'obsolete.txt')['content'], CONTENT)

    def test_model_request_approval_restart_release_and_independent_absence_check(self):
        center, _, task, request, script = self.begin_deletion()
        with self.assertRaises(WorkflowError):
            center.release(request)
        center.close()
        center = self.center()
        center.decide(request, True)
        self.assertEqual(center.request_detail(request)['status'], 'granted_awaiting_release')
        self.assertEqual(center.read_file(task, 'obsolete.txt')['content'], CONTENT)
        with patch.object(DeepSeekHTTP, '__call__', side_effect=AssertionError('Do not call model before release')) as http:
            center.advance(task)
            http.assert_not_called()
        center.close()
        center = self.center()
        receipt = center.release(request)
        self.assertEqual(receipt['sha256'], SHA)
        self.assertFalse(list((self.path/'state/files/tasks').rglob('obsolete.txt')))
        with self.assertRaises(WorkflowError):
            center.release(request)
        with patch.object(DeepSeekHTTP, '__call__', side_effect=script):
            center.advance(task)
        result = center.task_detail(task)
        self.assertEqual(result['task']['state'], 'succeeded')
        self.assertTrue(all(result['task']['evidence']['checks'].values()))
        self.assertEqual(sum(e['kind']=='file_deleted' for e in result['events']), 1)
        names = {t['function']['name'] for t in script.requests[0]['tools']}
        self.assertIn('delete_text', names)
        self.assertNotIn('release_approved', names)
        self.assertEqual(len(script.requests), 4)

    def test_denial_survives_restart_and_stops_without_another_provider_attempt(self):
        center, _, task, request, _ = self.begin_deletion()
        center.decide(request, False)
        center.close()
        center = self.center()
        with self.assertRaises(WorkflowError):
            center.release(request)
        with patch.object(DeepSeekHTTP, '__call__', side_effect=AssertionError('Denied action must stop')) as http:
            center.advance(task)
            http.assert_not_called()
        self.assertEqual(center.task_detail(task)['task']['state'], 'cancelled')
        self.assertEqual(center.read_file(task, 'obsolete.txt')['content'], CONTENT)

    def test_changed_file_after_approval_is_not_deleted_or_retried_after_restart(self):
        center, _, task, request, _ = self.begin_deletion()
        center.decide(request, True)
        center.call(lambda b: b.files.update_text(task, 'writer', 'obsolete.txt', 'Changed\n', expected_sha256=SHA))
        center.close()
        center = self.center()
        with self.assertRaisesRegex(WorkflowError, 'deletion failed'):
            center.release(request)
        self.assertEqual(center.read_file(task, 'obsolete.txt')['content'], 'Changed\n')
        self.assertEqual(center.request_detail(request)['status'], 'released')
        center.close()
        center = self.center()
        with self.assertRaises(WorkflowError):
            center.release(request)
        self.assertEqual(center.read_file(task, 'obsolete.txt')['content'], 'Changed\n')
        self.assertFalse(any(e['kind']=='file_deleted' for e in center.task_detail(task)['events']))

    def test_other_task_and_unaddressed_human_cannot_use_the_request(self):
        center, chat, task, request, _ = self.begin_deletion(other_human=True)
        # A real human MEMBER reaches the addressed-responder check, rather
        # than being rejected earlier as an outsider to the conversation.
        with self.assertRaisesRegex(WorkflowError, 'addressed human'):
            center.call(lambda b: b.workflow.respond(request, 'other-human', approve=True))
        center.decide(request, True)
        other = center.create_task(chat, 'writer', 'Unrelated cleanup')['task']
        center.call(lambda b: b.workflow.start_task(other, 'writer'))
        with self.assertRaisesRegex(WorkflowError, 'another task'):
            center.call(lambda b: b.scheduler(other).runner(other).gateway.release_approved(request))
        self.assertEqual(center.request_detail(request)['status'], 'granted_awaiting_release')
        self.assertEqual(center.read_file(task, 'obsolete.txt')['content'], CONTENT)
        center.release(request)

    def test_stale_approval_cannot_be_reused_after_another_human_pause(self):
        center, _, task, request, _ = self.begin_deletion()
        center.decide(request, True)
        clarification = center.call(lambda b: b.workflow.ask_human(task, 'writer', b.human, 'Reconfirm the scope'))
        center.answer(clarification, 'Keep the current scope')
        with self.assertRaises(WorkflowError):
            center.release(request)
        self.assertEqual(center.request_detail(request)['status'], 'granted_stale')
        self.assertEqual(center.read_file(task, 'obsolete.txt')['content'], CONTENT)

    def test_wrong_file_version_at_request_time_creates_no_approval(self):
        center = self.center()
        _, task = self.task(center)
        def attempt(b):
            b.workflow.start_task(task, 'writer')
            b.files.create_text(task, 'writer', 'obsolete.txt', CONTENT)
            return b.scheduler(task).runner(task).gateway.dispatch(tool('delete_text',
                {'path':'obsolete.txt','expected_sha256':'0'*64}))
        result = json.loads(center.call(attempt)['content'])
        self.assertFalse(result['ok'])
        self.assertEqual(center.requests(), [])
        self.assertEqual(center.read_file(task, 'obsolete.txt')['content'], CONTENT)

    def test_interrupted_released_action_is_not_replayed_or_counted_as_deletion(self):
        center, _, task, request, _ = self.begin_deletion()
        center.decide(request, True)
        with patch('agent_lab.files.FileTools.delete_text', side_effect=OSError('Synthetic IO failure')):
            with self.assertRaises(WorkflowError):
                center.release(request)
        center.close()
        center = self.center()
        with self.assertRaises(WorkflowError):
            center.release(request)
        self.assertEqual(center.read_file(task, 'obsolete.txt')['content'], CONTENT)
        self.assertEqual(center.task_detail(task)['task']['state'], 'running')
        self.assertFalse(any(e['kind']=='file_deleted' for e in center.task_detail(task)['events']))

    def test_console_uses_the_same_opt_in_roles_without_implicit_model_calls(self):
        stream = io.StringIO()
        args = ['--state-dir',str(self.path/'console'),'--live','--model','explicit-test-model',
                '--api-key-env','B05_TEST_KEY','--enable-delete','new','--goal','Clean up a task-local note']
        with patch.dict('os.environ', {'B05_TEST_KEY':'unused-fixture-key'}, clear=True), \
             patch.object(DeepSeekHTTP, '__call__', side_effect=AssertionError('No implicit calls')) as http, \
             contextlib.redirect_stdout(stream):
            self.assertEqual(console_main(args), 0)
            http.assert_not_called()
        task = json.loads(stream.getvalue())['task']
        center = self.center(name='console', live=replace(self.live, allow_network=True))
        tools = center.call(lambda b: b.scheduler(task).roles['coordinator'].tools)
        self.assertIn('delete_text', tools)
        self.assertIn('human approval', center.runtimes()['deletion'])

    def test_evaluation_records_permission_and_version_one_plans_keep_it_disabled(self):
        off = build_manifest([], replace(self.live, enable_delete=False), 'off')
        on = build_manifest([], self.live, 'off')
        self.assertNotIn('delete', off['runtime']['capabilities'])
        self.assertEqual(on['runtime']['capabilities']['delete'], 'task-local-exact-version-human-release-v1')
        self.assertNotEqual(on, off)
        plan = DevelopmentPlan(SOURCE/'evaluation/development-plan.json')
        self.assertFalse(LiveConfig(api_key='unused-fixture-key', **plan.settings).enable_delete)
        data = json.loads((SOURCE/'evaluation/development-plan.json').read_text())
        data['capabilities']['delete'] = True
        data['cases'] = str(SOURCE/'evaluation/connection')
        target = self.path/'unsupported-plan.json'
        target.write_text(json.dumps(data))
        with self.assertRaises(WorkflowError):
            DevelopmentPlan(target)


if __name__ == '__main__':
    unittest.main()
