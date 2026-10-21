"""Frozen/reset boundaries and comparison evidence; all model output is scripted."""
import contextlib
from contextlib import closing
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.core import WorkflowError
from agent_lab.deepseek import DeepSeekClient, DeepSeekHTTP
from agent_lab.evaluation.experience import (ExperiencePlan, ExperienceTrial, LiveExperienceDriver,
    NAMESPACE, compare_experience, probe_roles)
from agent_lab.evaluation.experience_fixture import ExperienceFixtureDriver
from agent_lab.evaluation.memory_protocol import MemorySeed, memory_state
from agent_lab.evaluation.harness import HUMAN, _Session
from agent_lab.evaluation.__main__ import main
from agent_lab.gateway import ToolGateway
from agent_lab.memory import ExperienceMemory
from agent_lab.runtime import LiveConfig
from test_runner import response, tool

CONFIG=Path(__file__).resolve().parents[1]/'evaluation/memory-plan.json'


class ExperienceProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared=tempfile.TemporaryDirectory()
        cls.plan=ExperiencePlan(CONFIG)
        cls.live=LiveConfig(api_key='unused-fixture-key',**cls.plan.runtime.settings)
        cls.driver=ExperienceFixtureDriver(cls.live)
        cls.report=ExperienceTrial(cls.plan,cls.driver).run(cls.shared.name)
        cls.run_dir=Path(cls.shared.name)/cls.report['run_id']

    @classmethod
    def tearDownClass(cls): cls.shared.cleanup()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
        self.seed=MemorySeed(self.run_dir/'replicate-0/seed',self.report['seeds']['0'])

    def tearDown(self): self.temp.cleanup()

    def fork(self,name='probe'):
        session=self.seed.fork(self.path/name);self.addCleanup(session.close);return session

    def task(self,session,agent='coordinator',chat=None,title='Probe newline behavior'):
        task=session.workflow.create_task(chat or self.seed.info['chat'],HUMAN,agent,title)
        session.workflow.start_task(task,agent);return task

    def test_fixture_preserves_failed_training_and_explicitly_denies_learning_claim(self):
        report=self.report
        compared=compare_experience(report)
        self.assertEqual((report['mode'],report['model_calls'],report['benchmark_valid']),('offline_fixture',0,False))
        self.assertEqual(compared['status'],'engineering_only',compared)
        self.assertFalse(compared['learning_improvement_established'])
        self.assertEqual(compared['training']['planned'],4)
        self.assertEqual(compared['training']['goals_completed'],2)
        self.assertEqual(compared['training']['goal_completion_rate'],.5)
        self.assertGreater(compared['training']['reserved_model_attempts'],0)
        for arm in ('on','off'):
            self.assertEqual(compared['probes'][arm]['planned'],4)
            self.assertEqual(compared['probes'][arm]['goals_completed'],4)

    def test_on_and_off_start_with_identical_seed_and_each_probe_resets(self):
        for row in self.report['results']:
            if row['phase']!='probe':continue
            seed=self.report['seeds'][str(row['replicate'])]
            self.assertEqual(row['memory_before'],seed['memory'])
            self.assertEqual(row['memory_after'],seed['memory'])
            self.assertEqual(row['seed_sha256'],__import__('agent_lab.evaluation.manifest',fromlist=['digest']).digest(seed))
            if row['memory']=='off': self.assertEqual(row['memory_use']['retrievals'],0)
            else: self.assertEqual((row['memory_use']['selections'],row['memory_use']['assessed']),(1,1))

    def test_probe_model_never_receives_training_chat(self):
        for item in self.driver.requests:
            if item['phase']=='probe':
                self.assertNotIn('TRAINING_CHAT_SHOULD_NOT_APPEAR',json.dumps(item['request']))
                for message in item['request']['messages']:
                    if message['role']=='tool':
                        output=json.loads(message['content']).get('result',{})
                        if isinstance(output,dict) and 'messages' in output:
                            self.assertEqual(output['messages'],[])

    def test_fork_has_no_training_files_and_original_file_binding_is_untouched(self):
        source=self.run_dir/'replicate-0/training/workflow.sqlite3'
        with closing(sqlite3.connect(source)) as db:
            before=db.execute('SELECT device,inode FROM file_root').fetchone()
        session=self.fork();task=self.task(session)
        self.assertEqual(list((self.path/'probe/files/tasks').iterdir()),[])
        with self.assertRaises(WorkflowError): session.files.read_text(task,'coordinator','note.txt')
        self.assertFalse(any(p.is_file() for p in (self.path/'probe/files/tasks').rglob('*')))
        with closing(sqlite3.connect(source)) as db:
            self.assertEqual(before,db.execute('SELECT device,inode FROM file_root').fetchone())
        for old in self.seed.info['training_roots']:
            with self.assertRaises(WorkflowError):session.files.read_text(old,'coordinator','note.txt')

    def test_owner_conversation_and_namespace_boundaries_survive_reset(self):
        session=self.fork();task=self.task(session)
        lessons=session.memory.search(task,'coordinator','newline')
        self.assertTrue(lessons)
        writer=self.task(session,'writer')
        self.assertEqual(session.memory.search(writer,'writer','newline'),[])
        with self.assertRaises(WorkflowError):session.memory.select(writer,'writer',lessons[0]['memory_id'])
        other=ExperienceMemory(session.workflow,namespace='unrelated')
        self.assertEqual(other.search(task,'coordinator','newline'),[])
        chat=session.workflow.create_chat('private',[HUMAN,'coordinator'])
        private=self.task(session,chat=chat)
        self.assertEqual(session.memory.search(private,'coordinator','newline'),[])

    def test_contradictory_sources_and_failed_reuse_remain_visible_but_do_not_leak_forward(self):
        first=self.fork('first');task=self.task(first)
        candidate=next(r for r in first.memory.search(task,'coordinator','newline') if len(r['sources'])==2)
        self.assertEqual({r['outcome'] for r in candidate['sources']},{'succeeded','failed'})
        first.memory.select(task,'coordinator',candidate['memory_id'])
        first.workflow.finish_task(task,'coordinator',error='Candidate did not apply to this probe')
        first.memory.assess_selected(task,'coordinator')
        later=self.task(first)
        reused=next(r for r in first.memory.search(later,'coordinator','newline') if r['memory_id']==candidate['memory_id'])
        self.assertEqual(reused['observed_reuses']['failed'],1)
        fresh=self.fork('fresh');new=self.task(fresh)
        reset=next(r for r in fresh.memory.search(new,'coordinator','newline') if r['memory_id']==candidate['memory_id'])
        self.assertEqual(reset['observed_reuses']['failed'],0)
        self.assertEqual(memory_state(fresh.workflow,fresh.memory,self.seed.info['chat']),self.seed.info['memory'])

    def test_new_task_cannot_treat_old_experience_as_approval(self):
        session=self.fork();task=self.task(session)
        candidate=session.memory.search(task,'coordinator','newline')[0]
        session.memory.select(task,'coordinator',candidate['memory_id'])
        request=session.workflow.ask_human(task,'coordinator',HUMAN,'Delete?',action={'tool':'fixture.delete'})
        with self.assertRaises(WorkflowError):session.workflow.consume_approval(request,'coordinator',{'tool':'fixture.delete'})
        self.assertEqual(session.workflow.task(task,HUMAN)['state'],'waiting_approval')

    def test_only_memory_tools_differ_between_probe_arms(self):
        on,off=probe_roles(self.live,'on'),probe_roles(self.live,'off')
        for actor in on:
            self.assertEqual(on[actor].instructions,off[actor].instructions)
            self.assertEqual(on[actor].limits,off[actor].limits)
            self.assertEqual(on[actor].delegates,off[actor].delegates)
            self.assertEqual(set(on[actor].tools)-set(off[actor].tools),{'search_memory','select_memory'})
            self.assertNotIn('record_lesson',on[actor].tools)

    def test_current_trial_messages_work_and_boundary_cannot_change_on_resume(self):
        session=self.fork();case=self.plan.probes[0]
        root=session.workflow.create_task(self.seed.info['chat'],HUMAN,'coordinator',case.goal)
        stage={'phase':'probe','memory':'on','case':case.summary()}
        scheduler=self.driver.scheduler(session,root,case,stage,self.seed.info['message_floor'])
        session.workflow.start_task(root,'coordinator')
        session.workflow.post_message(self.seed.info['chat'],HUMAN,'CURRENT_TRIAL_MESSAGE')
        gateway=scheduler.runner(root).gateway
        output=json.loads(gateway.dispatch(tool('read_messages',{'limit':20},'read-current'))['content'])
        self.assertEqual([m['body'] for m in output['result']['messages']],['CURRENT_TRIAL_MESSAGE'])
        with self.assertRaises(WorkflowError):self.driver.scheduler(session,root,case,stage,0)

    def test_changed_frozen_database_is_rejected_before_probe_creation(self):
        folder=self.path/'corrupt';folder.mkdir()
        shutil.copyfile(self.seed.directory/'seed.sqlite3',folder/'seed.sqlite3')
        with (folder/'seed.sqlite3').open('ab') as stream:stream.write(b'changed')
        bad=MemorySeed(folder,copy.deepcopy(self.seed.info))
        with self.assertRaisesRegex(WorkflowError,'changed'):bad.fork(self.path/'never-created')
        self.assertFalse((self.path/'never-created').exists())

    def test_probe_directory_cannot_be_reused_or_overwritten(self):
        first=self.fork();marker=self.path/'probe/marker.txt';marker.write_text('Retain evidence')
        with self.assertRaises(FileExistsError):self.seed.fork(self.path/'probe')
        self.assertEqual(marker.read_text(),'Retain evidence')

    def test_changed_scope_budget_seed_or_result_evidence_cannot_be_compared(self):
        mutations=[lambda r:r.update(conditions_sha256='0'*64),lambda r:r['results'].pop(),
            lambda r:r['results'].append(copy.deepcopy(r['results'][2])),
            lambda r:r['results'][2].update(seed_sha256='0'*64),
            lambda r:r['results'][2]['memory_before'].update(lessons=0),
            lambda r:r['results'][2]['memory_after'].update(content_sha256='0'*64),
            lambda r:r['results'][3]['memory_use'].update(retrievals=1),
            lambda r:r['results'][2]['case'].update(goal='Changed task'),
            lambda r:r['results'][2].update(duration_seconds=float('nan')),
            lambda r:r['results'][2]['workflow']['task_outcomes'][0].update(verified_success='yes'),
            lambda r:r['results'][2]['workflow']['task_outcomes'][0].update(final_duration_seconds=None),
            lambda r:r['results'][2]['memory_use']['uses'][0].update(outcome='failed'),
            lambda r:r['results'][2]['memory_use']['uses'][0].update(owner='writer'),
            lambda r:r['results'][2].update(classification='task_failed')]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                report=copy.deepcopy(self.report);mutate(report)
                self.assertEqual(compare_experience(report)['status'],'not_comparable')

    def test_even_rehashed_conditions_reject_non_memory_prompt_or_budget_differences(self):
        from agent_lab.evaluation.manifest import digest
        for field,value in [('instructions','Changed instructions'),('tool_calls',999)]:
            report=copy.deepcopy(self.report)
            report['conditions']['probe_roles']['off']['coordinator'][field]=value
            report['conditions_sha256']=digest(report['conditions'])
            self.assertEqual(compare_experience(report)['status'],'not_comparable')

    def test_edited_summary_is_ignored_and_a_recorded_failure_stays_in_denominator(self):
        report=copy.deepcopy(self.report)
        report['comparison']={'probes':{'off':{'goal_completion_rate':123}}}
        self.assertEqual(compare_experience(report)['probes']['off']['goal_completion_rate'],1)
        failed=report['results'][3]
        failed['classification']='task_failed';failed['checks']['final_state']=False
        failed['workflow']['root_state']='failed'
        failed['workflow']['task_outcomes'][0].update(state='failed',verified_success=False)
        compared=compare_experience(report)
        self.assertEqual(compared['status'],'engineering_only',compared)
        self.assertEqual(compared['probes']['off']['goal_completion_rate'],.75)

    def test_counterbalanced_order_is_declared_and_reproducible(self):
        first=[r['memory'] for r in self.report['results'] if r['phase']=='probe' and r['replicate']==0]
        second=[r['memory'] for r in self.report['results'] if r['phase']=='probe' and r['replicate']==1]
        self.assertEqual(first,['on','off','off','on'])
        self.assertEqual(second,['off','on','on','off'])

    def test_inspection_and_blocked_execute_use_no_model_or_output_directory(self):
        with patch.dict('os.environ',{},clear=True),patch.object(DeepSeekHTTP,'__call__') as model:
            inspected=self.plan.inspect();self.assertEqual(inspected['maximum_model_attempts'],288)
            with self.assertRaises(WorkflowError):self.plan.execute(allow_model_calls=True,plan_sha256=self.plan.sha256,output_root=self.path/'uncreated')
            self.assertFalse((self.path/'uncreated').exists());model.assert_not_called()
        with self.assertRaises(WorkflowError):self.plan.execute(allow_model_calls=False,plan_sha256=self.plan.sha256,output_root=self.path/'uncreated')

    def test_cli_inspect_and_compare_are_read_only(self):
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):self.assertEqual(main(['experience','plan','--config',str(CONFIG)]),0)
        self.assertEqual(json.loads(stream.getvalue())['model_calls'],0)
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):self.assertEqual(main(['experience','compare','--run',str(self.run_dir)]),0)
        self.assertEqual(json.loads(stream.getvalue())['status'],'engineering_only')

    def test_live_entry_uses_typed_http_with_mocked_transport_and_never_serializes_key(self):
        # Mocked HTTP validates wiring only; it is not a real model experiment.
        runtime=self.path/'memory';shutil.copytree(CONFIG.parent/'memory',runtime)
        raw=json.loads((runtime/'runtime.json').read_text());raw['model']='explicit-test-model'
        (runtime/'runtime.json').write_text(json.dumps(raw))
        wrapper=json.loads(CONFIG.read_text());wrapper['replicates']=1
        config=self.path/'plan.json';config.write_text(json.dumps(wrapper))
        plan=ExperiencePlan(config)
        scripted=ExperienceFixtureDriver(LiveConfig(api_key='unused',**plan.runtime.settings))
        lookup={case.goal:case for case in [*plan.training,*plan.probes]}
        def http(http_self,payload):
            request=json.loads(payload)
            context=json.loads(request['messages'][1]['content'])
            case=lookup[context['global_goal']]
            names={t['function']['name'] for t in request['tools']}
            phase='training' if 'record_lesson' in names else 'probe'
            arm='collect' if phase=='training' else 'on' if 'search_memory' in names else 'off'
            stage={'phase':phase,'memory':arm,'case':case.summary()}
            return scripted.clients({'coordinator':None},stage)['coordinator'].transport(payload)
        with patch.dict('os.environ',{'COURSE_DEEPSEEK_API_KEY':'must-not-be-saved'},clear=True), \
             patch.object(DeepSeekHTTP,'__call__',new=http):
            report=plan.execute(allow_model_calls=True,plan_sha256=plan.sha256,output_root=self.path/'live-wiring')
        self.assertEqual(report['comparison']['status'],'compared',report['comparison'])
        self.assertFalse(report['comparison']['learning_improvement_established'])
        self.assertNotIn('must-not-be-saved',json.dumps(report))
        for database in (self.path/'live-wiring').rglob('*.sqlite3'):
            self.assertNotIn(b'must-not-be-saved',database.read_bytes())

    def test_invalid_training_probe_overlap_and_stale_authorization_are_rejected(self):
        raw=json.loads(CONFIG.read_text());raw['runtime_plan']=str(CONFIG.parent/raw['runtime_plan'])
        raw['probe_cases']=raw['training_cases']
        config=self.path/'invalid.json';config.write_text(json.dumps(raw))
        with self.assertRaises(WorkflowError):ExperiencePlan(config)
        with self.assertRaises(WorkflowError):self.plan.execute(allow_model_calls=True,plan_sha256='0'*64,output_root=self.path/'none')


class ExperienceSourceFailureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
        source=self.path/'source';source.mkdir()
        self.session=_Session(source,NAMESPACE)
        self.chat=self.session.workflow.create_chat('group',[HUMAN,'coordinator','writer'])
        self.roots=[]

    def tearDown(self):self.session.close();self.temp.cleanup()

    def observed(self,title='Observed newline task',*,finish=True):
        w=self.session.workflow
        task=w.create_task(self.chat,HUMAN,'coordinator',title);self.roots.append(task)
        w.start_task(task,'coordinator')
        if finish:
            self.session.files.create_text(task,'coordinator','note.txt','Checked\n')
            self.session.files.complete_from_text(task,'coordinator',{'note.txt':'Checked\n'})
            self.session.memory.observe_terminal(task,'coordinator')
        return task

    def test_unfinished_source_cannot_seed_or_run_dependent_probes(self):
        self.observed();self.observed(finish=False)
        with self.assertRaisesRegex(WorkflowError,'incomplete'):
            MemorySeed.freeze(self.session,self.path/'seed',self.chat,self.roots)
        self.assertFalse((self.path/'seed').exists())

    def test_unknown_provider_usage_is_not_erased_by_reset(self):
        task=self.observed();w=self.session.workflow
        w.db.execute('CREATE TABLE runner_turns(task TEXT,status TEXT)')
        w.db.execute("INSERT INTO runner_turns VALUES(?,'provider_error')",(task,))
        with self.assertRaisesRegex(WorkflowError,'Unknown'):
            MemorySeed.freeze(self.session,self.path/'seed',self.chat,self.roots)

    def test_old_released_grant_cannot_authorize_a_new_probe_action(self):
        self.observed();task=self.observed(finish=False);w=self.session.workflow
        action={'tool':'delete_text','arguments':{'path':'note.txt','expected_sha256':'0'*64}}
        request=w.ask_human(task,'coordinator',HUMAN,'Fixture grant',action=action)
        w.respond(request,HUMAN,approve=True);w.consume_approval(request,'coordinator',action)
        w.finish_task(task,'coordinator',error='Fixture grant bookkeeping ended')
        self.session.memory.observe_terminal(task,'coordinator')
        seed=MemorySeed.freeze(self.session,self.path/'seed',self.chat,self.roots)
        fork=seed.fork(self.path/'probe');self.addCleanup(fork.close)
        root=fork.workflow.create_task(self.chat,HUMAN,'coordinator','Unrelated new action')
        fork.workflow.start_task(root,'coordinator')
        gateway=ToolGateway(fork.workflow,fork.files,root,'coordinator',human=HUMAN,allowed=('delete_text',))
        with self.assertRaisesRegex(WorkflowError,'another task'):gateway.release_approved(request)

    def test_unreleased_source_approval_blocks_freeze(self):
        self.observed();task=self.observed(finish=False);w=self.session.workflow
        request=w.ask_human(task,'coordinator',HUMAN,'Effect?',action={'tool':'fixture'})
        w.respond(request,HUMAN,approve=True);w.finish_task(task,'coordinator',error='Not released')
        self.session.memory.observe_terminal(task,'coordinator')
        with self.assertRaisesRegex(WorkflowError,'Unreleased'):
            MemorySeed.freeze(self.session,self.path/'seed',self.chat,self.roots)

    def test_retirement_survives_reset_and_sources_are_preserved(self):
        first=self.observed('Original private newline task')
        old=self.session.workflow.db.execute('SELECT id FROM lessons').fetchone()[0]
        maintenance=self.observed('Retirement maintenance',finish=False)
        self.session.memory.retire(maintenance,'coordinator',old,reason='Not applicable to these probes')
        self.session.workflow.finish_task(maintenance,'coordinator',error='Maintenance fixture ended')
        self.session.memory.observe_terminal(maintenance,'coordinator')
        seed=MemorySeed.freeze(self.session,self.path/'seed',self.chat,self.roots)
        fork=seed.fork(self.path/'probe');self.addCleanup(fork.close)
        self.assertEqual(seed.info['memory']['retired'],1)
        task=fork.workflow.create_task(self.chat,HUMAN,'coordinator','Probe original newline')
        fork.workflow.start_task(task,'coordinator')
        self.assertEqual(fork.memory.search(task,'coordinator','original'),[])
        self.assertEqual(fork.workflow.db.execute('SELECT count(*) FROM lesson_sources WHERE lesson=?',(old,)).fetchone()[0],1)

    def test_unrelated_workflow_or_changed_source_observation_is_rejected(self):
        task=self.observed()
        w=self.session.workflow
        w.db.execute('UPDATE tasks SET evidence=? WHERE id=?',(json.dumps({'checks':{'different':True}}),task))
        with self.assertRaisesRegex(WorkflowError,'provenance'):
            MemorySeed.freeze(self.session,self.path/'seed',self.chat,self.roots)
        w.create_chat('private',[HUMAN,'writer'])
        with self.assertRaisesRegex(WorkflowError,'dedicated'):
            MemorySeed.freeze(self.session,self.path/'seed2',self.chat,self.roots)

    def test_human_pause_keeps_all_planned_probe_slots_and_denominators(self):
        class PausedDriver(ExperienceFixtureDriver):
            def clients(self,roles,stage):
                def wait(payload):return json.dumps(response([tool('ask_human',{'prompt':'Real clarification required'})])).encode()
                return {a:DeepSeekClient(self.live.model,wait) for a in roles}
        plan=ExperiencePlan(CONFIG);driver=PausedDriver(LiveConfig(api_key='unused-key',**plan.runtime.settings))
        report=ExperienceTrial(plan,driver).run(self.path/'runs')
        compared=compare_experience(report)
        self.assertEqual(compared['status'],'not_comparable')
        for arm in ('on','off'):
            self.assertEqual(compared['probes'][arm]['planned'],4)
            self.assertEqual(compared['probes'][arm]['not_run'],4)
            self.assertEqual(compared['probes'][arm]['goal_completion_rate'],0)
        self.assertEqual(sum(r['classification']=='blocked' for r in report['results']),2)


if __name__=='__main__':unittest.main()
