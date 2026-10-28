"""Real broker effects with synthetic decisions: prepare before child scheduling."""
from dataclasses import replace
import json
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from agent_lab import recovery
from agent_lab.acceptance import ArtifactRule, verify_rules
from agent_lab.core import Workflow, WorkflowError
from agent_lab.deepseek import DeepSeekHTTP
from agent_lab.delegation import input_records
from agent_lab.evaluation.harness import _case_policy
from agent_lab.evaluation.manifest import build_manifest
from agent_lab.evaluation.plan import DevelopmentPlan
from agent_lab.files import FileTools
from agent_lab.gateway import ToolGateway
from agent_lab.inspection import ArtifactInspector
from agent_lab.runtime import policy_delegation_inputs, LiveConfig, TaskPolicy
from agent_lab.tui.controller import ControlCenter
from test_runner import Script, response, tool

ROOT = Path(__file__).resolve().parents[1]


class DelegationInputTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)
        self.open(); self.addCleanup(lambda: self.close())
        for actor, kind in [('human', 'human'), ('coordinator', 'agent'), ('writer', 'agent'), ('editor', 'agent')]:
            self.w.register_actor(actor, kind)
        self.chat = self.w.create_chat('group', ['human', 'coordinator', 'writer', 'editor'])
        self.root = self.w.create_task(self.chat, 'human', 'coordinator', 'Deliver checked source')
        self.w.start_task(self.root, 'coordinator')
        self.writer = self.w.create_task(self.chat, 'coordinator', 'writer', 'Draft', parent=self.root)
        self.w.start_task(self.writer, 'writer')
        self.original = self.f.create_text(self.writer, 'writer', 'draft.txt', 'Actual source\n')
        self.spec = {'assignee': 'writer', 'title': 'Draft', 'path': 'draft.txt', 'allow_relay': True, 'require_read': True}
        self.rule = ArtifactRule('input.txt', 'received_from', json.dumps(self.spec))

    def open(self):
        self.w = Workflow(self.path / 'state.sqlite3')
        self.f = FileTools(self.w, self.path / 'files')

    def close(self):
        self.f.close(); self.w.close()

    def gateway(self, task=None, actor='coordinator', rule=None, strict=True):
        return ToolGateway(self.w, self.f, task or self.root, actor, human='human',
            allowed=('create_text', 'delegate_task', 'delegate_with_inputs', 'retry_failed_task'),
            delegates=('editor',) if actor == 'writer' else ('writer', 'editor'),
            delegation_rules=(('writer', 'Draft'), ('editor', 'Check')) if strict else None,
            delegation_inputs=(('editor', 'Check', (rule or self.rule,)),))

    def request(self, inputs=None, name=None):
        args = {'assignee': 'editor', 'title': 'Check'}
        if inputs is not None:
            args['input_files'] = inputs
        return tool(name or ('delegate_task' if inputs is None else 'delegate_with_inputs'), args, 'delegate')

    def offer_to_root(self, path='relay.txt'):
        offered = self.f.offer_artifact(self.writer, 'writer', 'draft.txt', self.root,
                                       expected_sha256=self.original['sha256'])
        return offered, self.f.accept_artifact(self.root, 'coordinator', offered['artifact_id'], path)

    def effects(self):
        return {table: self.w.db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                for table in ('tasks', 'events', 'artifacts', 'requests', 'tool_calls')}

    def result(self, gateway, request):
        result = json.loads(gateway.dispatch(request)['content'])
        self.assertTrue(result['ok'], result)
        return result['result']

    def test_bare_delegation_fails_before_any_batch_effect_or_budget_reservation(self):
        gateway = self.gateway(); before = self.effects()
        with self.assertRaisesRegex(WorkflowError, 'delegate_with_inputs'):
            gateway.validate_batch([tool('create_text', {'path': 'never.txt', 'content': 'No side effect'}, 'write'),
                                    self.request()])
        self.assertEqual(before, self.effects())
        self.assertIsNone(ArtifactInspector(self.w, self.f)._read(self.root, 'never.txt'))
        with self.assertRaises(WorkflowError): gateway.dispatch(self.request())
        self.assertEqual(before, self.effects())

    def test_schemas_offer_input_aware_contract_and_preserve_other_pairs(self):
        schemas = {t['function']['name']: t['function']['parameters']['properties'] for t in self.gateway().tools()}
        self.assertEqual(schemas['delegate_task']['assignee']['enum'], ['writer'])
        self.assertEqual(schemas['delegate_task']['title']['enum'], ['Draft'])
        self.assertEqual(schemas['delegate_with_inputs']['title']['enum'], ['Check', 'Draft'])
        self.assertNotIn('delegate_task', {t['function']['name'] for t in self.gateway(self.writer, 'writer').tools()})
        self.assertIn('delegate_with_inputs', {t['function']['name'] for t in self.gateway(self.writer, 'writer').tools()})

    def test_direct_source_owner_can_prepare_child_but_child_still_must_accept_and_read(self):
        gateway = self.gateway(self.writer, 'writer')
        request = self.request({'draft.txt': self.original['sha256']})
        before = self.effects(); gateway.validate_batch([request]); self.assertEqual(before, self.effects())
        result = self.result(gateway, request); child = result['task_id']
        self.w.start_task(child, 'editor')
        checked = lambda: all(verify_rules(self.w, self.f, child, 'editor', (self.rule,)).values())
        self.assertFalse(checked())
        self.f.accept_artifact(child, 'editor', result['input_offers'][0]['artifact_id'], 'input.txt')
        self.assertFalse(checked())
        self.f.read_text(child, 'editor', 'input.txt'); self.assertTrue(checked())

    def test_coordinator_relay_requires_causal_consumed_source_and_survives_restart(self):
        self.offer_to_root('renamed.txt'); gateway = self.gateway()
        request = self.request({'renamed.txt': self.original['sha256']})
        before = self.effects(); gateway.validate_batch([request]); self.assertEqual(before, self.effects())
        self.close(); self.open()
        result = self.result(self.gateway(), request)
        self.assertEqual(result['status'], 'delegated')
        self.assertEqual(result['input_offers'][0]['source_path'], 'renamed.txt')
        self.assertEqual(self.w.task(result['task_id'], 'human')['parent'], self.root)

    def test_copied_bytes_or_unconsumed_offer_cannot_satisfy_source(self):
        self.f.create_text(self.root, 'coordinator', 'copy.txt', 'Actual source\n')
        gateway = self.gateway(); before = self.effects()
        with self.assertRaisesRegex(WorkflowError, 'do not prove delivery'):
            gateway.validate_batch([self.request({'copy.txt': self.original['sha256']})])
        self.assertEqual(before, self.effects())
        self.f.offer_artifact(self.writer, 'writer', 'draft.txt', self.root, expected_sha256=self.original['sha256'])
        before = self.effects()
        with self.assertRaises(WorkflowError): gateway.dispatch(self.request({'copy.txt': self.original['sha256']}))
        self.assertEqual(before, self.effects())

    def test_no_relay_policy_requires_original_source_owner(self):
        self.offer_to_root(); rule = replace(self.rule, expected=json.dumps({**self.spec, 'allow_relay': False}))
        with self.assertRaises(WorkflowError):
            self.gateway(rule=rule).dispatch(self.request({'relay.txt': self.original['sha256']}))
        self.result(self.gateway(self.writer, 'writer', rule), self.request({'draft.txt': self.original['sha256']}))

    def test_missing_wrong_hash_origin_path_size_and_unsafe_path_fail_read_only(self):
        self.f.create_text(self.writer, 'writer', 'copy.txt', 'Actual source\n')
        for inputs, rule in [({'missing.txt': self.original['sha256']}, self.rule),
                             ({'draft.txt': '0' * 64}, self.rule),
                             ({'copy.txt': self.original['sha256']}, self.rule),
                             ({'draft.txt': self.original['sha256']}, replace(self.rule, max_bytes=1)),
                             ({'../draft.txt': self.original['sha256']}, self.rule)]:
            gateway = self.gateway(self.writer, 'writer', rule); before = self.effects()
            with self.subTest(inputs=inputs), self.assertRaises(WorkflowError): gateway.validate_batch([self.request(inputs)])
            self.assertEqual(before, self.effects())

    def test_ambiguous_failed_and_foreign_source_cannot_certify_inputs(self):
        self.offer_to_root(); request = self.request({'relay.txt': self.original['sha256']})
        duplicate = self.w.create_task(self.chat, 'coordinator', 'writer', 'Draft', parent=self.root)
        with self.assertRaises(WorkflowError): self.gateway().dispatch(request)
        self.w.start_task(duplicate, 'writer'); self.w.finish_task(duplicate, 'writer', error='Discarded duplicate')
        self.gateway().validate_batch([request])
        self.w.finish_task(self.writer, 'writer', error='Source failed')
        with self.assertRaises(WorkflowError): self.gateway().dispatch(request)
        other = self.w.create_task(self.chat, 'human', 'writer', 'Draft')
        self.w.start_task(other, 'writer'); self.f.create_text(other, 'writer', 'draft.txt', 'Actual source\n')
        foreign = self.f.offer_artifact(other, 'writer', 'draft.txt', self.root, expected_sha256=self.original['sha256'])
        self.f.accept_artifact(self.root, 'coordinator', foreign['artifact_id'], 'foreign.txt')
        # Another goal cannot restore the failed source in the original goal.
        with self.assertRaises(WorkflowError): self.gateway().dispatch(self.request({'foreign.txt': self.original['sha256']}))
        with self.assertRaises(WorkflowError): self.gateway().dispatch(request)

    def test_changed_file_between_validation_and_execution_creates_no_child(self):
        gateway = self.gateway(self.writer, 'writer'); request = self.request({'draft.txt': self.original['sha256']})
        gateway.validate_batch([request]); execute = gateway._execute
        def change_then_execute(name, args):
            self.f.update_text(self.writer, 'writer', 'draft.txt', 'Changed\n', expected_sha256=self.original['sha256'])
            return execute(name, args)
        count = self.w.db.execute('SELECT count(*) FROM tasks').fetchone()[0]
        with patch.object(gateway, '_execute', side_effect=change_then_execute):
            result = json.loads(gateway.dispatch(request)['content'])
        self.assertFalse(result['ok']); self.assertIn('changed', result['error'])
        self.assertEqual(count, self.w.db.execute('SELECT count(*) FROM tasks').fetchone()[0])

    def test_ownership_and_symlink_boundaries_apply_before_any_prerequisite_read(self):
        gateway = self.gateway(self.writer, 'writer')
        gateway.actor = 'coordinator'  # A caller cannot change the source task identity.
        before = self.effects()
        with self.assertRaises(WorkflowError): gateway.validate_batch([self.request({'draft.txt': self.original['sha256']})])
        self.assertEqual(before, self.effects())
        import hashlib
        task_dir = self.path / 'files' / 'tasks' / hashlib.sha256(self.writer.encode()).hexdigest()
        outside = self.path / 'outside.txt'; outside.write_text('Actual source\n')
        os.symlink(outside, task_dir / 'linked.txt')
        gateway = self.gateway(self.writer, 'writer'); before = self.effects()
        with self.assertRaises(WorkflowError): gateway.validate_batch([self.request({'linked.txt': self.original['sha256']})])
        self.assertEqual(before, self.effects())

    def test_retry_cannot_create_replacement_without_required_inputs(self):
        recovery.configure(self.w, self.root, 2)
        failed = self.w.create_task(self.chat, 'coordinator', 'editor', 'Check', parent=self.root)
        self.w.start_task(failed, 'editor'); self.w.finish_task(failed, 'editor', error='Missing source input')
        gateway = self.gateway(); args = {'failed_task': failed, 'reason': 'Prepare source before starting', 'input_files': {}}
        before = self.effects()
        with self.assertRaisesRegex(WorkflowError, 'not prepared'): gateway.dispatch(tool('retry_failed_task', args))
        self.assertEqual(before, self.effects()); self.assertEqual(recovery.links(self.w), {})
        self.offer_to_root(); args['input_files'] = {'relay.txt': self.original['sha256']}
        result = self.result(gateway, tool('retry_failed_task', args))
        self.assertEqual(result['retry_of'], failed); self.assertEqual(result['status'], 'replaced')
        self.assertEqual(self.w.task(failed, 'human')['state'], 'failed')

    def test_open_contracts_still_enforce_known_inputs_without_blocking_unknown_children(self):
        gateway = self.gateway(strict=False)
        with self.assertRaisesRegex(WorkflowError, 'delegate_with_inputs'): gateway.dispatch(self.request())
        result = self.result(gateway, tool('delegate_task', {'assignee': 'editor', 'title': 'Needs trusted review'}))
        self.assertEqual(self.w.task(result['task_id'], 'human')['title'], 'Needs trusted review')

    def test_malformed_trusted_requirements_fail_at_setup(self):
        invalid = [[], (), (('editor', 'Check', ()),), (('editor', 'Check', (ArtifactRule('input.txt', 'exists'),)),),
                   (('editor', 'Check', [self.rule]),), (('editor', 'Check', (self.rule,)),) * 2,
                   (([], 'Check', (self.rule,)),)]
        for requirements in invalid:
            with self.subTest(requirements=requirements), self.assertRaises(WorkflowError):
                ToolGateway(self.w, self.f, self.root, 'coordinator', human='human', allowed=('create_text',),
                            delegation_inputs=requirements)


class SharedInputContractTests(unittest.TestCase):
    def test_legacy_no_source_policy_keeps_its_config_and_delegation_schema(self):
        self.assertIsNone(policy_delegation_inputs(TaskPolicy()))
        live = LiveConfig('explicit-fixture-model', 'unused-key', allow_network=True, enable_collaboration=True)
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(Path(directory) / 'session', live=live)
            try:
                chat = center.create_conversation('group', ['coordinator', 'writer', 'editor'])
                root = center.create_task(chat, 'coordinator', 'Legacy open work')['task']
                center.call(lambda b: b.workflow.start_task(root, 'coordinator'))
                config, names = center.call(lambda b: (
                    json.loads(b.workflow.db.execute('SELECT config FROM scheduler_runs WHERE root=?', (root,)).fetchone()[0]),
                    {t['function']['name'] for t in b.scheduler(root).runner(root).gateway.tools()}))
                self.assertNotIn('delegation_inputs', config)
                self.assertIn('delegate_task', names); self.assertIn('delegate_with_inputs', names)
                self.assertNotIn('list_tasks', names)
                center.close(); center = ControlCenter(Path(directory) / 'session', live=live)
                center.call(lambda b: b.scheduler(root))
            finally: center.close()

    def test_plan_runtime_restart_and_manifest_keep_the_same_prerequisites(self):
        plan = DevelopmentPlan(ROOT / 'evaluation/checked-collaboration-plan.json')
        live = LiveConfig(api_key='unused-key', allow_network=True, **plan.settings)
        with tempfile.TemporaryDirectory() as directory, patch.object(DeepSeekHTTP, '__call__', side_effect=AssertionError('No network')):
            center = ControlCenter(Path(directory) / 'session', live=live)
            try:
                case = plan.cases[0]; policy = _case_policy(case, live)
                chat = center.create_conversation('group', ['coordinator', 'writer', 'editor'])
                root = center.create_task(chat, 'coordinator', case.goal, child_rules=policy.child_rules,
                    root_criteria=policy.root_criteria, constraints=policy.constraints, declared_subtasks_only=True)['task']
                expected = input_records(policy_delegation_inputs(policy))
                config = center.call(lambda b: json.loads(b.workflow.db.execute(
                    'SELECT config FROM scheduler_runs WHERE root=?', (root,)).fetchone()[0]))
                self.assertEqual(config['delegation_inputs'], expected)
                self.assertEqual(plan.conditions['case_delegation_inputs'][case.id], expected)
                self.assertEqual(plan.inspect()['delegation_inputs'][case.id], expected)
                self.assertEqual(build_manifest(plan.cases, live, 'off')['runtime']['case_delegation_inputs'][case.id], expected)
                center.close(); center = ControlCenter(Path(directory) / 'session', live=live)
                center.call(lambda b: b.scheduler(root))
                # Persisted settings may not silently drop the new boundary.
                def tamper(b):
                    changed = dict(config); changed.pop('delegation_inputs')
                    b.workflow.db.execute('UPDATE scheduler_runs SET config=? WHERE root=?', (json.dumps(changed, sort_keys=True), root))
                    return b.scheduler(root)
                with self.assertRaisesRegex(WorkflowError, 'Persisted scheduler'): center.call(tamper)
            finally: center.close()

    def test_synthetic_runner_receives_feedback_and_corrects_before_effects(self):
        # The model decisions here are scripted. Actual receipts/files and the
        # gateway are real; this is no new HKGAI capability claim.
        plan = DevelopmentPlan(ROOT / 'evaluation/checked-collaboration-plan.json')
        live = LiveConfig(api_key='unused-key', allow_network=True, **plan.settings)
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(Path(directory) / 'session', live=live)
            try:
                case = plan.cases[0]; policy = _case_policy(case, live)
                chat = center.create_conversation('group', ['coordinator', 'writer', 'editor'])
                root = center.create_task(chat, 'coordinator', case.goal, child_rules=policy.child_rules,
                    root_criteria=policy.root_criteria, declared_subtasks_only=True)['task']
                bad = response([tool('create_text', {'path': 'never.txt', 'content': 'No side effect'}, 'write'),
                                tool('delegate_task', {'assignee': 'editor', 'title': 'Check order totals'}, 'bad')])
                good = response([tool('delegate_task', {'assignee': 'writer', 'title': 'Draft order totals'}, 'correct')])
                script = Script([bad, good])
                with patch('agent_lab.hkgai.HKGAIHTTP.__call__', side_effect=script):
                    center.call(lambda b: b.scheduler(root).step())
                    self.assertEqual(center.files(root), [])
                    center.call(lambda b: b.scheduler(root).step())
                self.assertIn('delegate_with_inputs', json.dumps(script.requests[-1]))
                tasks = center.call(lambda b: [dict(r) for r in b.workflow.db.execute('SELECT title FROM tasks WHERE parent=?', (root,))])
                self.assertEqual(tasks, [{'title': 'Draft order totals'}])
            finally: center.close()


if __name__ == '__main__': unittest.main()
