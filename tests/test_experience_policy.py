"""Inspect experience policies without a provider call or execution backend."""
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.core import WorkflowError
from agent_lab.deepseek import DeepSeekHTTP
from agent_lab.evaluation.experience import ExperiencePlan, LiveExperienceDriver, NAMESPACE, _validate_roles
from agent_lab.evaluation.harness import HUMAN, _Session
from agent_lab.evaluation.manifest import digest
from agent_lab.runtime import LiveConfig
from test_runner import tool

ROOT = Path(__file__).resolve().parents[1]


class ExperiencePolicyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup); self.path = Path(tmp.name)
        cases = self.path / 'cases'; cases.mkdir()
        definitions = []
        for identifier in ('strict-train', 'strict-probe'):
            goal = 'Deliver checked note ' + identifier
            definitions.append({'id':identifier, 'title':goal, 'goal':goal, 'driver':'live_scheduler',
                'expected':{'final_state':'succeeded','artifacts':{'note.txt':'Hello\n'},'declared_subtasks_only':True,
                    'subtasks':[{'assignee':'writer','title':'Write note','final_state':'succeeded',
                        'artifacts':{'note.txt':'Hello\n'},'criteria':[{'path':'input.txt','kind':'received_from',
                            'expected':json.dumps({'assignee':'coordinator','title':goal,'path':'seed.txt','allow_relay':False,'require_read':True})}]}]}})
        (cases / 'tasks.json').write_text(json.dumps(definitions))
        runtime = json.loads((ROOT / 'evaluation/memory/runtime.json').read_text())
        runtime.update(model='explicit-unused-test-model', cases='cases', case_ids=['strict-train','strict-probe'])
        (self.path / 'runtime.json').write_text(json.dumps(runtime))
        (self.path / 'plan.json').write_text(json.dumps({'version':1,'purpose':'development-memory-comparison',
            'protocol':'frozen-experience-isolated-probes-v1','runtime_plan':'runtime.json',
            'training_cases':['strict-train'],'probe_cases':['strict-probe'],'replicates':1}))
        self.plan = ExperiencePlan(self.path / 'plan.json')
        self.live = LiveConfig(api_key='unused-test-key',allow_network=True,**self.plan.runtime.settings)

    def inspect_scheduler(self, phase, arm):
        path = self.path / (phase + arm); path.mkdir()
        with patch.object(DeepSeekHTTP, '__call__', side_effect=AssertionError('No provider calls')):
            session = _Session(path, NAMESPACE)
            try:
                for agent in ('coordinator','writer','editor','researcher'):
                    session.workflow.register_actor(agent,'agent')
                chat = session.workflow.create_chat('group',[HUMAN,'coordinator','writer','editor','researcher'])
                case = self.plan.training[0] if phase == 'training' else self.plan.probes[0]
                root = session.workflow.create_task(chat,HUMAN,'coordinator',case.goal)
                scheduler = LiveExperienceDriver(self.live).scheduler(session,root,case,{'phase':phase,'memory':arm},0)
                roles = json.loads(json.dumps({a:asdict(r) for a,r in scheduler.roles.items()}))
                config = json.loads(session.workflow.db.execute('SELECT config FROM scheduler_runs WHERE root=?',(root,)).fetchone()[0])
                session.workflow.start_task(root,'coordinator'); gateway = scheduler.runner(root).gateway
                with self.assertRaisesRegex(WorkflowError,'trusted assignee/title pairs'):
                    gateway.dispatch(tool('delegate_task',{'assignee':'writer','title':'Unknown expanded title'}))
                with self.assertRaisesRegex(WorkflowError,'delegate_with_inputs'):
                    gateway.dispatch(tool('delegate_task',{'assignee':'writer','title':'Write note'}))
                self.assertEqual(session.workflow.db.execute('SELECT count(*) FROM tasks').fetchone()[0],1)
                self.assertEqual(session.workflow.db.execute('SELECT count(*) FROM tool_calls').fetchone()[0],0)
                return roles,config
            finally:session.close()

    def test_training_and_both_probes_use_inspected_roles_and_input_guards(self):
        for phase,arm in [('training','collect'),('probe','on'),('probe','off')]:
            with self.subTest(phase=phase,arm=arm):
                roles,config = self.inspect_scheduler(phase,arm)
                expected = (self.plan.conditions['case_training_roles']['strict-train'] if phase=='training'
                            else self.plan.conditions['case_probe_roles']['strict-probe'][arm])
                self.assertEqual(roles,json.loads(json.dumps(expected)))
                self.assertEqual(config['delegation_rules'],[['writer','Write note']])
                self.assertEqual(config['delegation_inputs'][0]['title'],'Write note')
                self.assertIn('list_tasks',roles['coordinator']['tools'])
                self.assertEqual('record_lesson' in roles['writer']['tools'],phase=='training')
                self.assertEqual('search_memory' in roles['writer']['tools'],phase=='training' or arm=='on')

    def test_effective_probe_arms_differ_only_in_memory_access(self):
        arms = json.loads(json.dumps(self.plan.conditions['case_probe_roles']['strict-probe'])); _validate_roles(arms)
        changed = json.loads(json.dumps(arms)); changed['off']['writer']['tools'].remove('list_tasks')
        with self.assertRaisesRegex(ValueError,'Non-memory tools'): _validate_roles(changed)
        self.assertEqual(self.plan.sha256,digest(self.plan.conditions))

    def test_legacy_memory_plan_keeps_previous_metadata_shape(self):
        old = ExperiencePlan(ROOT / 'evaluation/memory-plan.json')
        self.assertNotIn('case_training_roles',old.conditions)
        self.assertNotIn('case_probe_roles',old.conditions)
        self.assertTrue(all('list_tasks' not in r['tools'] for arm in old.conditions['probe_roles'].values() for r in arm.values()))


if __name__ == '__main__':unittest.main()
