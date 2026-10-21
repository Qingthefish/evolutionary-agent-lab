"""Integrated capability contracts; no external service or model calls."""

import argparse
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.core import Workflow, WorkflowError
from agent_lab.budget import configure, TreeLimits
from agent_lab.deepseek import DeepSeekClient, DeepSeekHTTP
from agent_lab.evaluation import Evaluator, parse_case
from agent_lab.files import FileTools
from agent_lab.gateway import ToolGateway
from agent_lab.memory import ExperienceMemory
from agent_lab.runtime import (LiveConfig, RuntimeServices, TaskPolicy, add_live_arguments,
    build_live_scheduler, live_config_from_args, live_members, live_roles)
from agent_lab.scheduler import MultiAgentScheduler, Role
from test_runner import Script, response, tool


class RuntimeToolTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(); self.path=Path(self.directory.name)
        self.workflow=Workflow(self.path/'state.sqlite3')
        for actor,kind in (('human','human'),('coordinator','agent'),('writer','agent'),('researcher','agent')):
            self.workflow.register_actor(actor,kind)
        self.chat=self.workflow.create_chat('group',['human','coordinator','writer','researcher'])
        self.root=self.workflow.create_task(self.chat,'human','coordinator','Deliver checked text')
        configure(self.workflow,self.root,TreeLimits())
        self.workflow.start_task(self.root,'coordinator')
        self.files=FileTools(self.workflow,self.path/'files')
        self.memory=ExperienceMemory(self.workflow,namespace='integration')

    def tearDown(self):
        self.files.close(); self.workflow.close(); self.directory.cleanup()

    def test_candidate_is_staged_then_bound_to_real_failure_and_later_reuse_outcome(self):
        self.memory.propose(self.root,'coordinator',lesson='Under exact-text checks, preserve the newline; applicability must be checked.',tags=['newline','exact-text'])
        self.assertEqual(self.workflow.db.execute('SELECT count(*) FROM lessons').fetchone()[0],0)
        self.workflow.finish_task(self.root,'coordinator',error='artifact:note.txt mismatch')
        first=self.memory.observe_terminal(self.root,'coordinator')
        self.assertEqual(first['status'],'recorded')
        self.assertEqual(self.memory.observe_terminal(self.root,'coordinator'),first)
        self.assertEqual(self.workflow.db.execute('SELECT count(*) FROM lessons').fetchone()[0],2)
        later=self.workflow.create_task(self.chat,'human','coordinator','Produce checked text with newline')
        self.workflow.start_task(later,'coordinator')
        found=self.memory.search(later,'coordinator','newline')
        lesson=next(r for r in found if 'preserve the newline' in r['lesson'])
        self.assertEqual(lesson['sources'][0]['outcome'],'failed')
        self.assertEqual(lesson['lesson_status'],'candidate')
        self.memory.select(later,'coordinator',lesson['memory_id'])
        self.files.create_text(later,'coordinator','note.txt','Checked\n')
        self.files.complete_from_text(later,'coordinator',{'note.txt':'Checked\n'})
        outcome=self.memory.observe_terminal(later,'coordinator')
        self.assertEqual(outcome['assessed_uses'][0]['observed_outcome'],'succeeded')
        self.assertFalse(outcome['learning_improvement_established'])

    def test_proposals_are_bounded_and_other_owner_cannot_stage_or_use_them(self):
        for i in range(8):
            self.memory.propose(self.root,'coordinator',lesson=f'Candidate {i}',tags=['bounded'])
        with self.assertRaises(WorkflowError): self.memory.propose(self.root,'coordinator',lesson='Ninth',tags=['bounded'])
        with self.assertRaises(WorkflowError): self.memory.propose(self.root,'writer',lesson='Wrong owner',tags=['bounded'])
        self.workflow.finish_task(self.root,'coordinator',error='actual failure')
        self.assertEqual(self.memory.observe_terminal(self.root,'coordinator')['status'],'recorded')
        target=self.workflow.create_task(self.chat,'human','writer','Use candidate')
        self.workflow.start_task(target,'writer')
        self.assertEqual(self.memory.search(target,'writer','candidate'),[])
        alternate=ExperienceMemory(self.workflow,namespace='other')
        self.assertEqual(alternate.search(target,'writer','candidate'),[])

    def test_scheduler_captures_terminal_outcomes_once_even_after_reconstruction(self):
        self.workflow.finish_task(self.root,'coordinator',error='Observed failure')
        roles={'coordinator':Role('Inspect memory',('search_memory','select_memory','record_lesson'))}
        def scheduler():
            return MultiAgentScheduler(self.workflow,self.files,self.root,human='human',roles=roles,
                clients={'coordinator':DeepSeekClient('synthetic-model',Script([]))},mode='offline_fixture',constraints=[],
                verifier_factory=lambda t:None,acceptance_id='memory-lifecycle-v1',memory=self.memory,capture_memory=True)
        scheduler().run(); scheduler().run()
        self.assertEqual(self.workflow.db.execute('SELECT count(*) FROM memory_outcomes').fetchone()[0],1)
        self.assertEqual(self.workflow.db.execute('SELECT count(*) FROM lessons').fetchone()[0],1)

    def test_input_delegation_preflights_hash_and_offers_before_parent_waits(self):
        receipt=self.files.create_text(self.root,'coordinator','input.txt','Input\n')
        gateway=ToolGateway(self.workflow,self.files,self.root,'coordinator',human='human',allowed=['delegate_with_inputs'],delegates=['writer'])
        bad=json.loads(gateway.dispatch(tool('delegate_with_inputs',{'assignee':'writer','title':'Use input','input_files':{'input.txt':'0'*64}},'bad'))['content'])
        self.assertFalse(bad['ok'])
        self.assertEqual(self.workflow.db.execute('SELECT count(*) FROM tasks WHERE parent=?',(self.root,)).fetchone()[0],0)
        result=json.loads(gateway.dispatch(tool('delegate_with_inputs',{'assignee':'writer','title':'Use input','input_files':{'input.txt':receipt['sha256']}},'good'))['content'])['result']
        child=result['task_id']; self.workflow.start_task(child,'writer')
        self.files.accept_artifact(child,'writer',artifact_id=result['input_offers'][0]['artifact_id'],path='input.txt')
        self.assertEqual(self.files.read_text(child,'writer','input.txt')['content'],'Input\n')

    def test_input_offer_partial_failure_retains_child_identity(self):
        receipt=self.files.create_text(self.root,'coordinator','input.txt','Input\n')
        gateway=ToolGateway(self.workflow,self.files,self.root,'coordinator',human='human',allowed=['delegate_with_inputs'],delegates=['writer'])
        with patch.object(self.files,'offer_artifact',side_effect=WorkflowError('changed input')):
            result=json.loads(gateway.dispatch(tool('delegate_with_inputs',{'assignee':'writer','title':'Use input','input_files':{'input.txt':receipt['sha256']}},'partial'))['content'])['result']
        self.assertEqual(result['status'],'partial')
        self.assertEqual(self.workflow.task(result['task_id'],'human')['state'],'pending')

    def test_incoming_snapshot_metadata_is_delivered_once_without_raw_file_content(self):
        receipt=self.files.create_text(self.root,'coordinator','input.txt','PRIVATE_FILE_CONTENT')
        child=self.workflow.create_task(self.chat,'coordinator','writer','Use input',parent=self.root)
        offer=self.files.offer_artifact(self.root,'coordinator','input.txt',child,expected_sha256=receipt['sha256'])
        self.workflow.start_task(child,'writer')
        script=Script([response(),response()])
        roles={'coordinator':Role('Coordinate',('delegate_task',),('writer',)), 'writer':Role('Use input',('read_text',))}
        scheduler=MultiAgentScheduler(self.workflow,self.files,self.root,human='human',roles=roles,
            clients={'coordinator':DeepSeekClient('synthetic-model',Script([])), 'writer':DeepSeekClient('synthetic-model',script)},
            mode='offline_fixture',constraints=[],verifier_factory=lambda t:None,acceptance_id='input-envelope-v1')
        scheduler.run()
        messages=script.requests[0]['messages']
        self.assertIn(offer['artifact_id'],json.dumps(messages))
        self.assertNotIn('PRIVATE_FILE_CONTENT',json.dumps(messages))
        self.assertEqual(self.workflow.db.execute('SELECT count(*) FROM runner_inputs_seen').fetchone()[0],1)
        scheduler.run(); self.assertEqual(len(script.requests),1)

    def test_coordination_messages_are_scoped_and_do_not_grant_approval(self):
        self.workflow.post_message(self.chat,'human','Discuss approach; this is not an action approval')
        other=self.workflow.create_chat('private',['human','writer'])
        self.workflow.post_message(other,'human','PRIVATE_CONVERSATION')
        gateway=ToolGateway(self.workflow,self.files,self.root,'coordinator',human='human',allowed=['read_messages'])
        result=json.loads(gateway.dispatch(tool('read_messages',{'limit':20},'read'))['content'])['result']
        self.assertNotIn('PRIVATE_CONVERSATION',json.dumps(result))
        self.assertIn('approval requires',result['authority'])
        self.assertEqual(self.workflow.db.execute('SELECT count(*) FROM requests').fetchone()[0],0)

    def test_optional_live_services_enable_matching_tools_without_provider_calls(self):
        config=LiveConfig('explicit-model','unused-key',enable_web=True,enable_memory=True,memory_namespace='integration')
        services=RuntimeServices(self.workflow,self.files,config,memory=self.memory); self.addCleanup(services.close)
        with patch.object(DeepSeekHTTP,'__call__',side_effect=AssertionError('No model calls')):
            scheduler=build_live_scheduler(self.workflow,self.files,self.root,human='human',live=config,services=services)
        researcher=scheduler.roles['researcher']; writer=scheduler.roles['writer']
        self.assertTrue({'search_web','retrieve_text','delegate_with_inputs','read_messages'}<=set(researcher.tools))
        self.assertTrue({'search_memory','record_lesson','select_memory'}<=set(writer.tools))
        self.assertIn('researcher',writer.delegates)
        with self.assertRaises(WorkflowError):
            build_live_scheduler(self.workflow,self.files,self.root,human='human',live=replace(config,memory_namespace='other'),services=services)
        with self.assertRaises(WorkflowError):
            build_live_scheduler(self.workflow,self.files,self.root,human='human',live=config)

    def test_live_memory_cannot_be_mislabelled_as_off_in_batch_reports(self):
        config=LiveConfig('explicit-model','unused-key',enable_memory=True)
        with self.assertRaisesRegex(WorkflowError,'cross-task/reset protocol'):
            Evaluator([],output_root=self.path/'not-created',live=config)
        self.assertFalse((self.path/'not-created').exists())

    def test_new_cli_capabilities_require_explicit_live_mode(self):
        parser=argparse.ArgumentParser(); add_live_arguments(parser)
        for argv in (['--enable-web'],['--enable-memory'],['--docker-host','unix:///socket']):
            with self.assertRaises(WorkflowError): live_config_from_args(parser.parse_args(argv))
        with patch.dict('os.environ',{'RUNTIME_TEST_KEY':'unused-key'},clear=True):
            config=live_config_from_args(parser.parse_args(['--live','--model','explicit-model','--api-key-env','RUNTIME_TEST_KEY','--enable-web','--enable-memory']))
        self.assertTrue(config.enable_web and config.enable_memory)
        self.assertNotIn(config.api_key,repr(config))


if __name__=='__main__': unittest.main()
