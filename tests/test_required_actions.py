"""Synthetic required-action contracts; provider support needs separate live evidence."""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.core import Workflow, WorkflowError
from agent_lab.deepseek import DeepSeekClient, ProviderError
from agent_lab.files import FileTools
from agent_lab.gateway import ToolGateway
from agent_lab.hkgai import HKGAIClient
from agent_lab.runner import TaskRunner, Limits, effective_prompt, model_context_conditions
from agent_lab.runtime import LiveConfig, add_live_arguments, live_config_from_args, live_clients, live_members, live_roles_for_policy
from agent_lab.evaluation.plan import DevelopmentPlan
from agent_lab.evaluation.manifest import build_manifest
from agent_lab.evaluation.experience import ExperiencePlan, probe_roles
from agent_lab.evaluation.harness import _case_policy
from test_runner import Script, response, tool
from test_verification_submission import submit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = object()


class RequiredActionTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory(); self.addCleanup(d.cleanup); self.path = Path(d.name)
        self.w = Workflow(self.path / 'state.sqlite3'); self.addCleanup(self.w.close)
        for a, kind in [('human', 'human'), ('writer', 'agent')]: self.w.register_actor(a, kind)
        self.chat = self.w.create_chat('group', ['human', 'writer'])
        self.task = self.w.create_task(self.chat, 'human', 'writer', 'Deliver independently checked note')
        self.w.start_task(self.task, 'writer')
        self.f = FileTools(self.w, self.path / 'files'); self.addCleanup(self.f.close)

    def runner(self, script, *, required=True, verifier=DEFAULT, allowed=None):
        gateway = ToolGateway(self.w, self.f, self.task, 'writer', human='human',
            allowed=allowed or ('create_text', 'update_text', 'ask_human', 'submit_for_verification'),
            delegation_rules=(('writer', 'Deliver independently checked note'),))
        if verifier is DEFAULT: verifier = self.f.text_verifier(self.task, 'writer', {'note.txt': 'Hello\n'})
        return TaskRunner(gateway, HKGAIClient('synthetic-model', script, tool_choice='required' if required else 'auto'),
            mode='offline_fixture', constraints=['Preserve original human boundaries'], limits=Limits(model_attempts=3),
            verifier=verifier, verifier_id='independent-note-v1' if verifier else None)

    def test_both_allowed_clients_send_explicit_required_without_changing_default_fields(self):
        for cls in (DeepSeekClient, HKGAIClient):
            script = Script([response([tool()])]); client = cls('synthetic', script, max_tokens=1024, tool_choice='required')
            client.complete([{'role': 'user', 'content': 'Synthetic test'}], tools=[{'type': 'function'}])
            self.assertEqual(script.requests[0]['tool_choice'], 'required')
            self.assertEqual(script.requests[0]['max_tokens'], 1024)
            self.assertEqual('thinking' in script.requests[0], cls is DeepSeekClient)
        script = Script([response()]); HKGAIClient('synthetic', script).complete([{'role': 'user', 'content': 'legacy'}])
        self.assertNotIn('tool_choice', script.requests[0])

    def test_invalid_selection_and_required_without_tools_do_not_call_transport(self):
        for value in (None, True, {}, 'none', 'any'):
            with self.subTest(value=value), self.assertRaises(ProviderError): HKGAIClient('synthetic', Script([]), tool_choice=value)
        script = Script([])
        with self.assertRaises(ProviderError) as caught:
            HKGAIClient('synthetic', script, tool_choice='required').complete([{'role': 'user', 'content': 'test'}])
        self.assertFalse(caught.exception.diagnostics()['request_may_have_been_processed'])
        self.assertEqual(script.requests, [])

    def test_ignored_or_truncated_required_reply_never_releases_tools_or_falls_back(self):
        for reply in (response(), response([tool()]) | {'choices': [{'finish_reason': 'length', 'message': response([tool()])['choices'][0]['message']}]}):
            script = Script([reply]); client = HKGAIClient('synthetic', script, tool_choice='required')
            with self.assertRaises(ProviderError): client.complete([{'role': 'user', 'content': 'test'}], tools=[{'type': 'function'}])
            self.assertEqual(len(script.requests), 1)
            self.assertEqual(script.requests[0]['tool_choice'], 'required')

    def test_unsupported_provider_option_stops_runner_without_retry(self):
        script = Script([ProviderError('Sanitized HTTP rejection', kind='http_status', phase='opening', http_status=400)])
        runner = self.runner(script); state = runner.step()
        self.assertEqual(state['task_state'], 'failed'); runner.step()
        self.assertEqual(len(script.requests), 1)
        self.assertEqual(self.w.db.execute('SELECT count(*) FROM tool_calls').fetchone()[0], 0)

    def test_required_proposal_rejects_wrong_artifact_then_repairs_with_independent_checks(self):
        script = Script([response([tool(arguments={'path': 'note.txt', 'content': 'Wrong\n'}), submit()]),
            response([tool('update_text', {'path': 'note.txt', 'content': 'Hello\n',
                'expected_sha256': hashlib.sha256(b'Wrong\n').hexdigest()}, 'repair'), submit('repaired')])])
        runner = self.runner(script); self.assertEqual(runner.step()['task_state'], 'running')
        self.assertIn('trusted_verification_failure', self.w.db.execute('SELECT transcript FROM runner_sessions').fetchone()[0])
        runner = self.runner(script); self.assertEqual(runner.step()['task_state'], 'succeeded')
        self.assertTrue(all(r['tool_choice'] == 'required' for r in script.requests))
        self.assertEqual(script.requests[0]['messages'][0]['content'], effective_prompt(True, require_tool_actions=True))
        self.assertEqual(json.loads(script.requests[0]['messages'][1]['content'])['constraints'], ['Preserve original human boundaries'])
        self.assertNotIn('or send a final response', script.requests[0]['messages'][1]['content'])

    def test_missing_verifier_still_needs_real_independent_review(self):
        script = Script([response([tool(), submit()])]); runner = self.runner(script, verifier=None)
        state = runner.step(); self.assertEqual(state['task_state'], 'running')
        self.assertEqual(state['runner_state'], 'awaiting_verification'); runner.step()
        self.assertEqual(len(script.requests), 1)
        self.assertEqual(self.w.db.execute("SELECT count(*) FROM events WHERE kind='human_review_recorded'").fetchone()[0], 0)

    def test_human_clarification_stops_later_tools_and_does_not_create_an_answer(self):
        script = Script([response([tool('ask_human', {'prompt': 'Which authorized scope?'}, 'ask'), tool(), submit()])])
        state = self.runner(script).step(); self.assertEqual(state['task_state'], 'waiting_input')
        self.assertEqual(self.w.db.execute('SELECT count(*) FROM requests WHERE answered=1').fetchone()[0], 0)
        self.assertEqual(self.w.db.execute("SELECT count(*) FROM tool_calls WHERE name='create_text'").fetchone()[0], 0)

    def test_required_configuration_cannot_silently_resume_as_auto_or_without_proposal_tool(self):
        self.runner(Script([]))
        with self.assertRaisesRegex(WorkflowError, 'Persisted model'): self.runner(Script([]), required=False)
        with self.assertRaisesRegex(WorkflowError, 'verification proposal tool'):
            self.runner(Script([]), allowed=('create_text',))
        self.assertEqual(self.w.db.execute('SELECT attempts FROM runner_sessions').fetchone()[0], 0)

    def test_versioned_plan_manifest_and_both_frozen_probe_arms_match_required_protocol(self):
        p = ExperiencePlan(ROOT / 'evaluation/required-actions-experience-plan.json'); live = LiveConfig(api_key='unused-test-key', **p.runtime.settings)
        self.assertTrue(live.require_tool_actions); self.assertEqual(p.inspect()['maximum_model_attempts'], 48)
        manifest = build_manifest(p.runtime.cases, live, 'off')
        for case in p.runtime.cases:
            expected = model_context_conditions(case.expected.declared_subtasks_only, require_tool_actions=True)
            self.assertEqual(p.runtime.conditions['case_model_context'][case.id], expected)
            self.assertEqual(manifest['runtime']['case_model_context'][case.id], expected)
            policy = _case_policy(case, live); roles = live_roles_for_policy(live_members(live), live, policy)
            self.assertTrue(all('submit_for_verification' in r.tools for r in roles.values()))
            self.assertTrue(all(c.tool_choice == 'required' for c in live_clients(live, roles).values()))
            if case.id in p.data['probe_cases']:
                on, off = probe_roles(live, 'on', policy), probe_roles(live, 'off', policy)
                self.assertTrue(all(on[a].instructions == off[a].instructions for a in on))

    def test_version_three_requires_explicit_boolean_and_older_plans_reject_new_option(self):
        data = json.loads((ROOT / 'evaluation/required-actions-runtime.json').read_text())
        data['cases'] = str(ROOT / 'evaluation/experience-jsonl/cases')
        variants = [dict(data, version=2)]
        for value in ('yes', 1, None):
            d = json.loads(json.dumps(data)); d['capabilities']['require_tool_actions'] = value; variants.append(d)
        missing = json.loads(json.dumps(data)); missing['capabilities'].pop('require_tool_actions'); variants.append(missing)
        for d in variants:
            file = self.path / 'plan.json'; file.write_text(json.dumps(d))
            with self.subTest(version=d['version']), self.assertRaises(WorkflowError): DevelopmentPlan(file)

    def test_cli_option_requires_live_and_invalid_booleans_are_refused(self):
        parser = argparse.ArgumentParser(); add_live_arguments(parser)
        with self.assertRaises(WorkflowError): live_config_from_args(parser.parse_args(['--require-tool-actions']))
        with patch.dict('os.environ', {'SYNTHETIC_KEY': 'unused-test-key'}):
            config = live_config_from_args(parser.parse_args(['--live', '--model', 'synthetic', '--api-key-env', 'SYNTHETIC_KEY', '--require-tool-actions']))
        self.assertTrue(config.require_tool_actions)
        with self.assertRaises(WorkflowError): replace(config, require_tool_actions=1)


if __name__ == '__main__': unittest.main()
