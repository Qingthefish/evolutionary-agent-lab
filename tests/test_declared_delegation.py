"""Early trusted-contract feedback; synthetic provider turns, no live capability claim."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.core import WorkflowError
from agent_lab.deepseek import DeepSeekHTTP
from agent_lab.evaluation.cases import load_cases, parse_case
from agent_lab.evaluation.harness import _case_policy
from agent_lab.gateway import ToolGateway
from agent_lab.runtime import ChildTextRule, LiveConfig, TaskPolicy, bind_task_policy, live_members, live_roles
from agent_lab.tui.controller import ControlCenter
from test_runner import Script, response, tool

ROOT = Path(__file__).resolve().parents[1]


class DeclaredDelegationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)
        self.live = LiveConfig('explicit-fixture-model', 'unused-fixture-key', allow_network=True,
                               enable_collaboration=True)
        guard = patch.object(DeepSeekHTTP, '__call__', side_effect=AssertionError('No real provider calls'))
        guard.start(); self.addCleanup(guard.stop)
        self.center = self.open()
        self.addCleanup(lambda: self.center.close())
        self.rules = (ChildTextRule('writer', 'Draft note', {'note.txt': 'Hello\n'}),
                      ChildTextRule('editor', 'Check note', {'checked.txt': 'Checked\n'}))
        self.chat = self.center.create_conversation('group', ['coordinator', 'writer', 'editor'])
        self.task = self.center.create_task(self.chat, 'coordinator', 'Deliver checked text',
            child_rules=self.rules, declared_subtasks_only=True)['task']
        self.center.call(lambda b: b.workflow.start_task(self.task, 'coordinator'))

    def open(self):
        return ControlCenter(self.path / 'session', live=self.live)

    def runner_call(self, function):
        return self.center.call(lambda b: function(b.scheduler(self.task).runner(self.task), b))

    def task_count(self):
        return self.center.call(lambda b: b.workflow.db.execute('SELECT count(*) FROM tasks').fetchone()[0])

    def test_schemas_expose_declared_titles_and_pair_validation_cannot_be_bypassed(self):
        schemas = self.runner_call(lambda r, b: {t['function']['name']: t['function']['parameters'] for t in r.gateway.tools()})
        for name in ('delegate_task', 'delegate_with_inputs'):
            self.assertEqual(schemas[name]['properties']['title']['enum'], ['Check note', 'Draft note'])
            self.assertEqual(schemas[name]['properties']['assignee']['enum'], ['editor', 'writer'])
        for assignee, title in [('writer', 'Check note'), ('editor', 'Long unknown title')]:
            with self.assertRaisesRegex(WorkflowError, 'trusted assignee/title pairs'):
                self.runner_call(lambda r, b: r.gateway.dispatch(tool('delegate_task', {'assignee': assignee, 'title': title})))
        self.assertEqual(self.task_count(), 1)

    def test_unknown_input_delegation_creates_neither_child_nor_artifact(self):
        with self.assertRaisesRegex(WorkflowError, 'Unknown declared child'):
            self.runner_call(lambda r, b: r.gateway.dispatch(tool('delegate_with_inputs', {
                'assignee': 'writer', 'title': 'Expanded title', 'input_files': {'missing.txt': '0' * 64}})))
        self.assertEqual(self.task_count(), 1)
        self.assertEqual(self.center.call(lambda b: b.workflow.db.execute('SELECT count(*) FROM artifacts').fetchone()[0]), 0)

    def test_model_gets_feedback_before_any_batch_effect_then_can_correct_after_restart(self):
        script = Script([response([tool('create_text', {'path': 'must-not-exist.txt', 'content': 'No side effect'}, 'file'),
                                  tool('delegate_task', {'assignee': 'writer', 'title': 'Draft note with extra description'}, 'bad')]),
                         response([tool('delegate_task', {'assignee': 'writer', 'title': 'Draft note'}, 'corrected')])])
        with patch.object(DeepSeekHTTP, '__call__', side_effect=script):
            self.runner_call(lambda r, b: r.step())
        self.assertEqual(self.task_count(), 1)
        self.assertEqual(self.center.files(self.task), [])
        self.center.close(); self.center = self.open()
        with patch.object(DeepSeekHTTP, '__call__', side_effect=script):
            self.runner_call(lambda r, b: r.step())
        self.assertEqual(len(script.requests), 2)
        self.assertIn('Unknown declared child work', json.dumps(script.requests[-1]))
        self.assertIn('Draft note', json.dumps(script.requests[-1]))
        self.assertEqual(self.task_count(), 2)
        child = self.center.call(lambda b: dict(b.workflow.db.execute('SELECT * FROM tasks WHERE parent=?', (self.task,)).fetchone()))
        self.assertEqual((child['assignee'], child['title'], child['state']), ('writer', 'Draft note', 'pending'))

    def test_policy_roundtrip_is_immutable_and_legacy_records_stay_unchanged(self):
        policy = TaskPolicy(child_rules=self.rules, declared_subtasks_only=True)
        self.assertEqual(policy.record()['version'], 4)
        restored = self.center.call(lambda b: bind_task_policy(b.workflow, self.task, b.human))
        self.assertEqual(restored, policy)
        with self.assertRaisesRegex(WorkflowError, 'cannot be replaced'):
            self.center.call(lambda b: bind_task_policy(b.workflow, self.task, b.human,
                                                       replace(policy, declared_subtasks_only=False)))
        for old in (TaskPolicy(), TaskPolicy(child_rules=self.rules)):
            self.assertNotIn('declared_subtasks_only', old.record())
            self.assertIn(old.record()['version'], (1, 2))
        for value in (1, 'true', None):
            with self.subTest(value=value), self.assertRaises(WorkflowError):
                replace(policy, declared_subtasks_only=value)
        with self.assertRaises(WorkflowError):
            TaskPolicy(declared_subtasks_only=True)

    def test_no_eligible_contract_hides_delegation_tools_without_empty_enums(self):
        def schemas(runner, backend):
            # This writer's only eligible delegate is coordinator; no declared
            # contract is assigned to coordinator, so there is no valid child.
            gateway = ToolGateway(backend.workflow, backend.files, self.task, 'coordinator', human=backend.human,
                allowed=('create_text', 'delegate_task', 'delegate_with_inputs'), delegates=('writer',),
                delegation_rules=(('editor', 'Check note'),))
            return [t['function']['name'] for t in gateway.tools()]
        self.assertEqual(self.runner_call(schemas), ['create_text'])

    def test_directory_is_opt_in_and_does_not_expand_existing_comparison_roles(self):
        legacy = live_roles(live_members(self.live), self.live)
        self.assertTrue(all('list_tasks' not in role.tools for role in legacy.values()))
        strict = self.runner_call(lambda r, b: {t['function']['name'] for t in r.gateway.tools()})
        self.assertIn('list_tasks', strict)
        other = self.center.create_task(self.chat, 'coordinator', 'Legacy open-ended task')['task']
        self.center.call(lambda b: b.workflow.start_task(other, 'coordinator'))
        names = self.center.call(lambda b: {t['function']['name'] for t in b.scheduler(other).runner(other).gateway.tools()})
        self.assertNotIn('list_tasks', names)

    def test_malformed_trusted_rules_fail_without_releasing_a_tool(self):
        def construct(runner, backend, rules):
            return ToolGateway(backend.workflow, backend.files, self.task, 'coordinator', human=backend.human,
                allowed=('delegate_task',), delegates=('writer',), delegation_rules=rules)
        for rules in ([], (), (('writer',),), (([], 'Draft note'),), (('writer', ''),), (('writer', 'x'), ('writer', 'x'))):
            with self.subTest(rules=rules), self.assertRaises(WorkflowError):
                self.runner_call(lambda r, b: construct(r, b, rules))
        self.assertEqual(self.task_count(), 1)

    def test_strict_mode_does_not_change_or_skip_actual_child_verification(self):
        def check(backend):
            child = backend.workflow.create_task(self.chat, 'coordinator', 'writer', 'Draft note', parent=self.task)
            backend.workflow.start_task(child, 'writer')
            backend.files.create_text(child, 'writer', 'note.txt', 'Wrong\n')
            runner = backend.scheduler(self.task).runner(child)
            with self.assertRaisesRegex(WorkflowError, 'verification failed'):
                backend.workflow.finish_task(child, 'writer', verifier=runner.verifier)
            return backend.workflow.task(child, 'writer')['state']
        self.assertEqual(self.center.call(check), 'running')

    def test_case_contract_is_explicit_strict_and_rejects_unchecked_children(self):
        case = next(c for c in load_cases(ROOT / 'evaluation/collaboration') if c.id == 'live-checked-order-handover')
        policy = _case_policy(case, self.live)
        self.assertTrue(policy.declared_subtasks_only)
        self.assertEqual(len(policy.child_rules), 2)
        data = json.loads((ROOT / 'evaluation/collaboration/a04-checked-handover.json').read_text())
        for value in ('true', 1, None):
            changed = json.loads(json.dumps(data)); changed['expected']['declared_subtasks_only'] = value
            with self.assertRaises(WorkflowError): parse_case(changed)
        data['expected']['subtasks'][0].pop('criteria')
        with self.assertRaisesRegex(WorkflowError, 'independently checked'): parse_case(data)


if __name__ == '__main__': unittest.main()
