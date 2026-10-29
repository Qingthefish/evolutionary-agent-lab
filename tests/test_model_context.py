"""Synthetic view contracts, not evidence of live-model reliability."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.core import Workflow, WorkflowError
from agent_lab.deepseek import DeepSeekClient
from agent_lab.files import FileTools
from agent_lab.gateway import ToolGateway
from agent_lab.model_context import CONTEXT_POLICY, peer_description
from agent_lab.runner import effective_prompt, model_context_conditions
from agent_lab.scheduler import MultiAgentScheduler, Role
from agent_lab.sandbox import DockerPythonExecutor, ProcessResult
from test_runner import Script, response, tool
from test_sandbox import FakeDocker, IMAGE


class ModelContextTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory(); self.addCleanup(d.cleanup); self.path = Path(d.name)
        self.w = Workflow(self.path / 'state.sqlite3'); self.addCleanup(self.w.close)
        for a, kind in [('human', 'human'), ('coder', 'agent'), ('coordinator', 'agent')]:
            self.w.register_actor(a, kind)
        self.chat = self.w.create_chat('group', ['human', 'coordinator', 'coder'])
        self.root = self.w.create_task(self.chat, 'human', 'coordinator', 'Preserve exact source and check result')
        self.f = FileTools(self.w, self.path / 'files'); self.addCleanup(self.f.close)

    def scheduler(self, declared=True):
        roles = {'coordinator': Role('Coordinate. ' + 'Shared guidance. ' * 60, ('delegate_task',), ('coder',)),
                 'coder': Role('Implement and test. ' + 'Private operating instructions. ' * 60,
                               ('create_text', 'read_text', 'offer_artifact'))}
        return MultiAgentScheduler(self.w, self.f, self.root, human='human', roles=roles,
            clients={a: DeepSeekClient('synthetic', Script([])) for a in roles}, mode='offline_fixture',
            constraints=['Preserve Unicode and whitespace', 'Never invent authorization'],
            verifier_factory=lambda task: None, acceptance_id='synthetic-view-test-v1',
            delegation_rules=(('coder', 'Implement and test'),) if declared else None)

    def test_declared_peer_view_preserves_own_role_constraints_and_identities(self):
        scheduler = self.scheduler(); self.w.start_task(self.root, 'coordinator')
        runner = scheduler.runner(self.root)
        row = self.w.db.execute('SELECT config,transcript FROM runner_sessions').fetchone()
        config = json.loads(row['config']); transcript = json.loads(row['transcript']); context = config['context']
        self.assertEqual(context['role']['instructions'], scheduler.roles['coordinator'].instructions)
        self.assertEqual(context['constraints'], scheduler.constraints)
        self.assertEqual(context['global_goal'], 'Preserve exact source and check result')
        self.assertEqual(context['task_id'], self.root)
        self.assertEqual(context['role']['eligible_agents'], {'coder': peer_description(scheduler.roles['coder'])})
        self.assertNotIn('Private operating instructions', json.dumps(context))
        self.assertEqual(transcript[0]['content'], effective_prompt(True))
        self.assertEqual(config['prompt_sha256'], hashlib.sha256(transcript[0]['content'].encode()).hexdigest())
        self.assertEqual(config['model_context'], model_context_conditions(True))
        # Same-policy restart is inert; changing the declared policy cannot reopen it.
        scheduler.runner(self.root)
        with self.assertRaisesRegex(WorkflowError, 'Persisted scheduler'):
            self.scheduler(False)
        self.assertEqual(runner.status()['protocol_attempts'], 0)

    def test_legacy_peer_context_and_system_prompt_are_unchanged(self):
        scheduler = self.scheduler(False); self.w.start_task(self.root, 'coordinator'); scheduler.runner(self.root)
        row = self.w.db.execute('SELECT config,transcript FROM runner_sessions').fetchone()
        config = json.loads(row['config'])
        self.assertNotIn('model_context', config)
        self.assertEqual(config['context']['role']['eligible_agents'], {'coder': scheduler.roles['coder'].instructions})
        self.assertEqual(json.loads(row['transcript'])[0]['content'], effective_prompt(False))
        self.assertNotIn('On action turns', effective_prompt(False))

    def test_old_declared_configuration_requires_explicit_migration_not_silent_resume(self):
        scheduler = self.scheduler(); self.w.start_task(self.root, 'coordinator'); scheduler.runner(self.root)
        row = self.w.db.execute('SELECT config FROM runner_sessions').fetchone()
        config = json.loads(row[0]); config.pop('model_context')
        self.w.db.execute('UPDATE runner_sessions SET config=?', (json.dumps(config, sort_keys=True),))
        with self.assertRaisesRegex(WorkflowError, 'Persisted model'):
            scheduler.runner(self.root)
        self.assertEqual(self.w.db.execute('SELECT attempts FROM runner_sessions').fetchone()[0], 0)

    def test_private_memory_tools_do_not_change_peer_directory_between_probe_arms(self):
        from agent_lab.evaluation.experience import ExperiencePlan, probe_roles
        from agent_lab.evaluation.harness import _case_policy
        from agent_lab.runtime import LiveConfig, live_members
        plan = ExperiencePlan(Path(__file__).resolve().parents[1] / 'evaluation/experience-jsonl/plan.json')
        live = LiveConfig(api_key='unused-synthetic', **plan.runtime.settings)
        case = next(c for c in plan.runtime.cases if c.id in plan.data['probe_cases'])
        policy = _case_policy(case, live)
        arms = {a: probe_roles(live, a, policy) for a in ('on', 'off')}
        self.assertEqual(set(arms['on']), set(arms['off']))
        for actor in arms['on']:
            self.assertEqual(peer_description(arms['on'][actor]), peer_description(arms['off'][actor]))
            self.assertNotIn('search_memory', peer_description(arms['on'][actor]))
            self.assertNotIn('record_lesson', peer_description(arms['on'][actor]))
            self.assertEqual(arms['on'][actor].instructions, arms['off'][actor].instructions)

    def execute(self, declared, outcome=None, partial=False):
        task = self.w.create_task(self.chat, 'human', 'coder', 'Run checked Python')
        self.w.start_task(task, 'coder')
        receipt = self.f.create_text(task, 'coder', 'main.py', 'print(42)\n')
        socket = self.path / 'daemon.sock'; socket.touch()
        with patch('agent_lab.sandbox.stat.S_ISSOCK', return_value=True):
            executor = DockerPythonExecutor(self.w, self.f, docker_host='unix://' + str(socket),
                image=IMAGE, docker_binary=sys.executable)
        self.addCleanup(executor.close)
        fake = FakeDocker()
        if outcome is not None: fake.execution = outcome
        if partial:
            fake.exports = {'result.txt': '42\n', 'blocked.txt': 'second\n'}
            self.f.create_text(task, 'coder', 'blocked.txt', 'existing\n')
        gateway = ToolGateway(self.w, self.f, task, 'coder', human='human', allowed=('run_python',), executor=executor,
            delegation_rules=(('coder', 'Run checked Python'),) if declared else None)
        args = {'entrypoint': 'main.py', 'input_files': {'main.py': receipt['sha256']},
                'arguments': [], 'outputs': list(fake.exports)}
        with patch.object(executor, '_invoke', side_effect=fake):
            message = gateway.dispatch(tool('run_python', args, identifier='run-' + task))
        shown = json.loads(message['content'])['result']
        raw_text = self.w.db.execute('SELECT result FROM sandbox_runs WHERE id=?', (shown['run_id'],)).fetchone()[0]
        raw = json.loads(raw_text)
        return task, shown, raw, raw_text

    def test_execution_view_keeps_outcome_and_import_evidence_with_full_raw_record(self):
        task, shown, raw, raw_text = self.execute(True)
        for key in ('run_id', 'process_sandbox', 'job', 'execution', 'artifacts', 'cleanup_confirmed', 'phase', 'elapsed_seconds'):
            self.assertEqual(shown[key], raw[key])
        self.assertEqual(shown['output_delivery']['task_id'], task)
        self.assertFalse(shown['output_delivery']['requires_accept_artifact'])
        for key in ('configuration', 'engine', 'identity'):
            self.assertNotIn(key, shown); self.assertIn(key, raw)
        self.assertEqual(shown['evidence_record']['run_id'], raw['run_id'])
        self.assertEqual(raw_text, self.w.db.execute('SELECT result FROM sandbox_runs WHERE id=?', (raw['run_id'],)).fetchone()[0])
        self.assertEqual(self.f.read_text(task, 'coder', 'result.txt')['sha256'], shown['artifacts'][0]['sha256'])

    def test_execution_failure_retains_exact_diagnostics_and_no_false_delivery(self):
        stderr = ('source line with spaces  \n' * 60).encode()
        task, shown, raw, _ = self.execute(True, ProcessResult(1, b'partial output\n', stderr))
        self.assertEqual(shown['execution'], raw['execution'])
        self.assertEqual(shown['execution']['stderr'], stderr.decode())
        self.assertEqual(shown['artifacts'], [])
        self.assertNotIn('output_delivery', shown)
        self.assertTrue(shown['cleanup_confirmed'])

    def test_partial_import_is_reported_as_partial_with_unchanged_error(self):
        _, shown, raw, _ = self.execute(True, partial=True)
        self.assertEqual(shown['error'], raw['error'])
        self.assertIn('partial receipts', shown['error'])
        self.assertEqual(len(shown['artifacts']), 1)
        self.assertEqual(shown['artifacts'], raw['artifacts'])
        self.assertEqual(len(shown['job']['outputs']), 2)

    def test_legacy_execution_view_retains_full_runtime_record(self):
        _, shown, raw, _ = self.execute(False)
        self.assertEqual({k: v for k, v in shown.items() if k != 'output_delivery'}, raw)
        self.assertNotIn('evidence_record', shown)

    def test_plan_and_manifest_identify_actual_declared_system_prompt(self):
        from agent_lab.evaluation.plan import DevelopmentPlan
        from agent_lab.evaluation.manifest import build_manifest
        from agent_lab.runtime import LiveConfig
        plan = DevelopmentPlan(Path(__file__).resolve().parents[1] / 'evaluation/provided-input-plan.json')
        live = LiveConfig(api_key='unused-synthetic', **plan.settings)
        expected = {c.id: model_context_conditions(c.expected.declared_subtasks_only) for c in plan.cases}
        self.assertEqual(plan.conditions['case_model_context'], expected)
        self.assertEqual(plan.inspect()['model_context'], expected)
        self.assertEqual(build_manifest(plan.cases, live, 'off')['runtime']['case_model_context'], expected)

    def test_last_request_notice_is_local_only_and_cannot_complete_missing_work(self):
        from agent_lab.runner import TaskRunner, Limits
        self.w.start_task(self.root, 'coordinator')
        gateway = ToolGateway(self.w, self.f, self.root, 'coordinator', human='human',
            allowed=('create_text', 'submit_for_verification'), delegation_rules=(('coder', 'Implement and test'),))
        script = Script([response([tool('create_text', {'path': 'wrong.txt', 'content': 'partial'})])])
        runner = TaskRunner(gateway, DeepSeekClient('synthetic', script), mode='offline_fixture', constraints=[],
            limits=Limits(model_attempts=1), verifier=self.f.text_verifier(self.root, 'coordinator', {'required.txt': 'checked'}),
            verifier_id='independent-missing-deliverable-v1')
        runner.step()
        context = json.loads(script.requests[0]['messages'][1]['content'])
        notice = context['execution_budget']['completion_proposal']
        self.assertEqual(notice['requests_left_after_current'], 0)
        self.assertTrue(notice['low_request_budget'])
        self.assertIn('independent verifier', notice['instruction'])
        self.assertEqual(runner.status()['task_state'], 'running')
        runner.step()
        self.assertEqual(runner.status()['task_state'], 'failed')
        self.assertEqual(len(script.requests), 1)


if __name__ == '__main__':
    unittest.main()
