"""Synthetic control checks; never evidence of live-model task capability."""

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from agent_lab import budget
from agent_lab.core import Workflow, WorkflowError
from agent_lab.deepseek import DeepSeekClient, DeepSeekHTTP, ProviderError
from agent_lab.execution_control import configuration_sha256, extend_execution
from agent_lab.evaluation.official_live import runtime_config, tools_for_role, TOOLS, TOOL_POLICY
from agent_lab.files import FileTools
from agent_lab.runner import Limits, RunnerError
from agent_lab.scheduler import MultiAgentScheduler, Role


def reply(name=None, arguments=None, *, identifier='call'):
    message = {'role': 'assistant', 'content': None if name else 'Ready for independent verification.'}
    if name:
        message['tool_calls'] = [{'id': identifier, 'type': 'function', 'function': {
            'name': name, 'arguments': json.dumps(arguments)}}]
    return json.dumps({'id': 'fixture', 'model': 'fixture', 'usage': {
        'prompt_tokens': 2, 'completion_tokens': 3, 'total_tokens': 5}, 'choices': [{
            'finish_reason': 'tool_calls' if name else 'stop', 'message': message}]}).encode()


class QualityExecution(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.now = 0
        self.w = Workflow(Path(tmp.name)/'workflow.sqlite3', clock=lambda: self.now)
        self.addCleanup(self.w.close)
        for actor, kind in [('user', 'human'), ('writer', 'agent'), ('other', 'agent')]:
            self.w.register_actor(actor, kind)
        chat = self.w.create_chat('group', ['user', 'writer', 'other'])
        self.root = self.w.create_task(chat, 'user', 'writer', 'Write the two-part result')
        self.files = FileTools(self.w, Path(tmp.name)/'files')
        self.addCleanup(self.files.close)
        self.requests = []
        self.replies = [reply('create_text', {'path': 'result.md', 'content': 'first'}, identifier='first'),
            reply('append_text', {'path': 'result.md', 'content': '-second',
                'expected_sha256': hashlib.sha256(b'first').hexdigest()}, identifier='second'), reply()]
        def transport(payload):
            self.requests.append(payload)
            return self.replies.pop(0)
        self.client = DeepSeekClient('fixture', transport, max_tokens=128)

    def build(self, attempts=1, *, duration=100, reported_tokens=32000):
        self.roles = {'writer': Role('Write and check the result', ('create_text', 'append_text', 'read_text'),
                                     limits=Limits(model_attempts=attempts, duration_seconds=duration, reported_tokens=reported_tokens))}
        self.limits = budget.TreeLimits(model_attempts=attempts, duration_seconds=duration)
        self.scheduler = self.reopen(self.roles, self.limits)
        return self.scheduler

    def reopen(self, roles, limits):
        return MultiAgentScheduler(self.w, self.files, self.root, human='user', roles=roles,
            clients={'writer': self.client}, mode='offline_fixture', constraints=[],
            verifier_factory=lambda task: None, acceptance_id='fixture-review', limits=limits, pause_on_limits=True)

    def extend(self, roles=None, limits=None, **overrides):
        return extend_execution(self.w, self.root, overrides.pop('human', 'user'),
            tree_limits=limits or replace(self.limits, model_attempts=3),
            roles=roles or {a: replace(r, limits=replace(r.limits, model_attempts=3), tool_calls=64)
                            for a, r in self.roles.items()}, reason='Allow the verified partial file to be completed',
            expected_sha256=overrides.pop('expected_sha256', configuration_sha256(self.w, self.root)), **overrides)

    def test_pause_extend_reopen_append_and_independently_finish_without_reset(self):
        s = self.build()
        self.assertEqual(s.run()['needs'][0]['kind'], 'execution_budget')
        self.assertEqual((len(self.requests), self.w.task(self.root, 'user')['state']), (1, 'running'))
        self.assertEqual(self.files.read_text(self.root, 'writer', 'result.md')['content'], 'first')
        before = budget.status(self.w, self.root)
        self.now = 200  # Paused time does not silently consume the active-time guard.
        changed = self.extend()
        self.assertEqual(changed['budget']['attempts'], before['attempts'])
        self.assertEqual(changed['budget']['tokens'], before['tokens'])
        self.assertEqual(changed['budget']['tool_calls'], before['tool_calls'])
        self.assertEqual(budget.task_elapsed(self.w, self.root, self.now), 0)
        roles = {a: replace(r, limits=replace(r.limits, model_attempts=3), tool_calls=64) for a,r in self.roles.items()}
        resumed = self.reopen(roles, replace(self.limits, model_attempts=3))
        self.assertEqual(resumed.run()['needs'][0]['kind'], 'independent_verification')
        self.assertEqual(len(self.requests), 3)
        self.assertEqual(self.files.read_text(self.root, 'writer', 'result.md')['content'], 'first-second')
        self.assertEqual(self.w.task(self.root, 'user')['state'], 'running')
        checked = self.files.read_text(self.root, 'writer', 'result.md')['content']
        self.w.finish_task(self.root, 'writer', checks={'exact independent expected result': checked=='first-second'})
        self.assertEqual(resumed.run()['task_state'], 'succeeded')
        self.assertEqual(self.w.db.execute("SELECT count(*) FROM events WHERE kind='human_review_recorded'").fetchone()[0], 0)

    def test_rejected_extension_is_atomic_and_cannot_expand_roles_or_reset_limits(self):
        self.build().run()
        before = configuration_sha256(self.w, self.root), budget.status(self.w, self.root)
        bad_roles = {'writer': replace(self.roles['writer'], tools=('read_text',))}
        for kwargs in ({'human': 'writer'}, {'expected_sha256':'0'*64}, {'roles':bad_roles},
                       {'limits':replace(self.limits, model_attempts=1)}):
            with self.subTest(kwargs=kwargs), self.assertRaises(WorkflowError):
                self.extend(**kwargs)
            self.assertEqual((configuration_sha256(self.w,self.root), budget.status(self.w,self.root)), before)
        self.assertEqual(len(self.requests), 1)

    def test_unknown_effects_and_terminal_tasks_cannot_be_extended(self):
        self.build().run()
        self.w.db.execute("UPDATE runner_sessions SET status='provider_uncertain' WHERE task=?", (self.root,))
        self.w.db.commit()
        with self.assertRaisesRegex(WorkflowError, 'uncertain effects'):
            self.extend()
        self.w.db.execute("UPDATE runner_sessions SET status='ready' WHERE task=?", (self.root,));self.w.db.commit()
        self.w.finish_task(self.root, 'writer', error='Preserved failed fixture')
        with self.assertRaisesRegex(WorkflowError, 'nonterminal'):
            self.extend()

    def test_inspected_transport_resend_can_extend_without_erasing_unknown_usage(self):
        scheduler = self.build(2)
        normal_transport = self.client.transport
        self.client.transport = lambda payload: (_ for _ in ()).throw(
            ProviderError('Synthetic connection close', kind='connection_closed', phase='opening'))
        scheduler.run()
        runner = scheduler.runner(self.root)
        self.assertEqual(runner.status()['runner_state'], 'provider_uncertain')
        runner.resend_after_transport_failure('Inspected failed request; no tool was released')
        self.client.transport = normal_transport
        self.assertEqual(scheduler.run()['needs'][0]['kind'], 'execution_budget')
        self.assertEqual(self.files.read_text(self.root, 'writer', 'result.md')['content'], 'first')
        before = budget.status(self.w, self.root)
        roles = {a: replace(r, limits=replace(r.limits, model_attempts=5), tool_calls=64)
                 for a, r in self.roles.items()}
        limits = replace(self.limits, model_attempts=5)
        changed = self.extend(roles=roles, limits=limits)
        for key in ('attempts', 'tokens', 'tool_calls'):
            self.assertEqual(changed['budget'][key], before[key])
        self.assertEqual(self.w.db.execute('SELECT status,response FROM runner_turns WHERE number=1').fetchone()[:],
                         ('provider_error', None))
        resumed = self.reopen(roles, limits)
        self.assertEqual(resumed.run()['needs'][0]['kind'], 'independent_verification')
        self.assertEqual(self.files.read_text(self.root, 'writer', 'result.md')['content'], 'first-second')
        self.assertEqual(resumed.runner(self.root).status()['unknown_usage_attempts'], 1)
        self.assertEqual(budget.status(self.w, self.root)['attempts'], 4)

    def test_resend_for_an_older_failure_cannot_clear_a_later_unresolved_turn(self):
        scheduler = self.build(4)
        self.client.transport = lambda payload: (_ for _ in ()).throw(
            ProviderError('Synthetic connection close', kind='connection_closed', phase='opening'))
        scheduler.run()
        scheduler.runner(self.root).resend_after_transport_failure('Inspect only failed turn one')
        scheduler.run()  # Turn two has not had an operator decision.
        # Even a damaged session label cannot turn the older decision into a waiver.
        self.w.db.execute("UPDATE runner_sessions SET status='ready' WHERE task=?", (self.root,))
        self.w.db.commit()
        before = configuration_sha256(self.w, self.root), budget.status(self.w, self.root)
        with self.assertRaisesRegex(WorkflowError, 'uncertain effects'):
            self.extend(limits=replace(self.limits, model_attempts=6),
                        roles={a: replace(r, limits=replace(r.limits, model_attempts=6))
                               for a, r in self.roles.items()})
        self.assertEqual((configuration_sha256(self.w, self.root), budget.status(self.w, self.root)), before)

    def test_historical_error_with_delivered_response_is_not_effect_free(self):
        scheduler = self.build(2)
        self.client.transport = lambda payload: (_ for _ in ()).throw(
            ProviderError('Synthetic connection close', kind='connection_closed', phase='opening'))
        scheduler.run()
        scheduler.runner(self.root).resend_after_transport_failure('Inspect failed transport')
        self.w.db.execute('UPDATE runner_turns SET response=? WHERE task=? AND number=1',
                          (reply().decode(), self.root))
        self.w.db.commit()
        with self.assertRaisesRegex(WorkflowError, 'uncertain effects'):
            self.extend()

    def test_stagnation_pauses_without_failure_and_needs_a_new_approach(self):
        self.replies = [reply('read_text', {'path':'missing.md'}, identifier=f'read-{n}') for n in range(5)]
        s = self.build(10)
        state = s.run()
        self.assertEqual((state['needs'][0]['kind'], len(self.requests)), ('progress_review', 5))
        self.assertEqual(self.w.task(self.root,'user')['state'],'running')
        s.run();self.assertEqual(len(self.requests),5)
        s.runner(self.root).resume_progress('Create the required result instead of rereading the missing file')
        self.assertEqual(s.runner(self.root).status()['protocol_attempts'],5)
        self.assertEqual(self.w.db.execute("SELECT count(*) FROM requests").fetchone()[0],0)
        self.replies=[reply()]
        self.assertEqual(s.run()['needs'][0]['kind'],'independent_verification')

    def test_duration_budget_pauses_without_cancelling_the_goal(self):
        s = self.build(duration=10);self.now=20
        state=s.run()
        self.assertEqual(state['needs'][0]['kind'],'execution_budget')
        self.assertEqual((len(self.requests),self.w.task(self.root,'user')['state']),(0,'pending'))

    def test_quality_settings_are_persisted_and_cannot_silently_downgrade(self):
        s=self.build();s.step()
        with self.assertRaisesRegex(RunnerError,'Persisted scheduler'):
            MultiAgentScheduler(self.w,self.files,self.root,human='user',roles=self.roles,
                clients={'writer':self.client},mode='offline_fixture',constraints=[],verifier_factory=lambda task:None,
                acceptance_id='fixture-review',limits=self.limits)

    def test_known_over_budget_reply_is_settled_without_releasing_or_replaying_tools(self):
        s=self.build(3,reported_tokens=4)
        self.assertEqual(s.run()['needs'][0]['kind'],'execution_budget')
        self.assertEqual(len(self.requests),1)
        self.assertEqual(self.w.db.execute('SELECT count(*) FROM tool_calls').fetchone()[0],0)
        self.assertEqual(self.w.db.execute('SELECT status FROM runner_turns').fetchone()[0],'settled')
        self.assertEqual(s.runner(self.root).status()['unknown_usage_attempts'],0)
        expanded={a:replace(r,limits=replace(r.limits,reported_tokens=100)) for a,r in self.roles.items()}
        self.extend(roles=expanded,limits=replace(self.limits,reported_tokens=self.limits.reported_tokens+100))
        self.assertEqual(self.w.db.execute('SELECT count(*) FROM tool_calls').fetchone()[0],0)
        self.replies=[reply('create_text',{'path':'after.md','content':'new counted request'},identifier='after')]
        self.reopen(expanded,replace(self.limits,reported_tokens=self.limits.reported_tokens+100)).step()
        self.assert_transcript_tools_paired(json.loads(self.requests[-1])['messages'])
        self.assertEqual(self.w.db.execute('SELECT call_id FROM tool_calls').fetchone()[0],'after')

    def assert_transcript_tools_paired(self, messages):
        pending=set()
        for message in messages:
            if message['role']=='assistant':
                self.assertFalse(pending,'A resumed provider request omitted prior tool results')
                pending={call['id'] for call in message.get('tool_calls',[])}
            elif message['role']=='tool':
                self.assertIn(message['tool_call_id'],pending)
                pending.remove(message['tool_call_id'])
            elif pending:
                self.fail('A control message interrupted an unanswered tool batch')
        self.assertFalse(pending,'A resumed request ended with unanswered tool calls')

    def test_mid_batch_pause_keeps_the_committed_effect_and_skips_the_unstarted_call(self):
        from unittest.mock import patch
        s=self.build(4,duration=10)
        first=json.loads(reply('create_text',{'path':'one.md','content':'first'},identifier='one'))
        second=json.loads(reply('create_text',{'path':'two.md','content':'unstarted'},identifier='two'))
        first['choices'][0]['message']['tool_calls']+=second['choices'][0]['message']['tool_calls']
        self.replies=[json.dumps(first).encode()]
        self.w.start_task(self.root,'writer');runner=s.runner(self.root)
        dispatch=runner.gateway.dispatch
        def slow(call):
            result=dispatch(call);self.now=20;return result
        with patch.object(runner.gateway,'dispatch',side_effect=slow):runner.step()
        self.assertEqual(runner.status()['runner_state'],'budget_paused')
        self.assertEqual(self.files.read_text(self.root,'writer','one.md')['content'],'first')
        with self.assertRaises(WorkflowError):self.files.read_text(self.root,'writer','two.md')
        roles={a:replace(r,limits=replace(r.limits,duration_seconds=100)) for a,r in self.roles.items()}
        tree=replace(self.limits,duration_seconds=100)
        self.extend(roles=roles,limits=tree)
        self.replies=[reply()]
        self.reopen(roles,tree).step()
        self.assert_transcript_tools_paired(json.loads(self.requests[-1])['messages'])
        self.assertEqual(self.w.db.execute('SELECT count(*) FROM tool_calls').fetchone()[0],1)


class QualityConfiguration(unittest.TestCase):
    def test_plan_selected_larger_output_and_allowance_keep_isolation_and_review(self):
        session=SimpleNamespace(scenario={'id':'software-engineering'})
        plan=SimpleNamespace(config={'runtime':{'provider':'hkgai','tool_policy':TOOL_POLICY,'model':'issued',
            'per_scenario_model_attempts':512,'max_output_tokens':8192,'api_key_env':'TEST_KEY'}})
        live=runtime_config(session,plan,1,docker_host='unix:///fixture.sock',image='fixture',
            allow_network=False,environ={'TEST_KEY':'fixture-key'},output_token_ceiling=8192,execution_profile='quality')
        self.assertEqual((live.max_output_tokens,live.tree_limits.model_attempts,live.socket_timeout),(8192,256,180))
        self.assertTrue(live.pause_on_limits);self.assertEqual(live.child_retries,8)
        self.assertEqual(live.repositories,());self.assertFalse(live.allow_network)
        tools=tools_for_role('software-engineering','lead',TOOLS,execution_profile='quality')
        self.assertTrue({'create_text','append_text','submit_for_verification'} <= set(tools))
        self.assertNotIn('delete_text',tools)
        self.assertEqual(DeepSeekHTTP('fixture-key',timeout=180).timeout,180)
        with self.assertRaises(ProviderError):DeepSeekHTTP('fixture-key',timeout=601)


if __name__=='__main__':unittest.main()
