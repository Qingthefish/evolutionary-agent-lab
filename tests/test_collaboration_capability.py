"""Independent collaboration capability; all provider decisions here are scripted."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.budget import TreeLimits
from agent_lab.core import WorkflowError
from agent_lab.hkgai import HKGAIHTTP
from agent_lab.evaluation.manifest import build_manifest
from agent_lab.evaluation.plan import DevelopmentPlan
from agent_lab.runtime import (LIVE_AGENTS, LiveConfig, RuntimeServices, add_live_arguments,
    live_config_from_args, live_members, live_roles)
from agent_lab.tui.controller import ControlCenter
from test_runner import response, tool

ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/'evaluation/collaboration-plan.json'


class CollaborationCapabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def config(self, **changes):
        return LiveConfig(model='synthetic-model',api_key='unused-collaboration-secret',provider='hkgai',
            enable_collaboration=True,**changes)

    def center(self, name, live):
        center=ControlCenter(self.root/name,live=live)
        self.addCleanup(center.close)
        return center

    def script(self):
        replies={
            'coordinator':[response([tool('post_message',{'body':'Fixture: draft first, request independent checking.'},'scope'),
                tool('delegate_task',{'assignee':'writer','title':'Fixture draft'},'draft')])],
            'writer':[response([tool('read_messages',{'limit':10},'read-scope'),
                tool('delegate_task',{'assignee':'editor','title':'Fixture independent check'},'check')])],
            'editor':[response([tool('create_text',{'path':'check.md','content':'Fixture check: 2*12 + 3*8 + 5*6 = 78.\n'},'file')]),response()]
        }
        calls=[]
        def http(payload):
            request=json.loads(payload);actor=json.loads(request['messages'][1]['content'])['role']['agent']
            calls.append((actor,request))
            if not replies.get(actor):raise AssertionError('Unexpected additional provider request')
            return json.dumps(replies[actor].pop(0)).encode()
        return calls,http

    def test_all_present_specialists_can_coordinate_without_other_backends(self):
        config=self.config();roles=live_roles(live_members(config),config)
        self.assertEqual(set(roles),set(LIVE_AGENTS))
        for actor,role in roles.items():
            self.assertEqual(set(role.delegates),set(LIVE_AGENTS)-{actor})
            self.assertTrue({'delegate_task','delegate_with_inputs','post_message','read_messages'}<=set(role.tools))
            self.assertFalse(set(role.tools)&{'search_web','retrieve_text','run_python','git_push','delete_text','search_memory','record_lesson'})
            self.assertEqual(len(role.tools),len(set(role.tools)))

    def test_disabled_legacy_roles_and_manifest_shape_are_unchanged(self):
        config=replace(self.config(),enable_collaboration=False);roles=live_roles(live_members(config),config)
        self.assertIn('delegate_task',roles['coordinator'].tools)
        for actor in ('writer','editor','researcher'):
            self.assertFalse(set(roles[actor].tools)&{'delegate_task','delegate_with_inputs','read_messages'})
        plan=DevelopmentPlan(ROOT/'evaluation/hkgai-smoke-plan.json')
        manifest=build_manifest(plan.cases,config,'off')
        self.assertNotIn('collaboration',manifest['runtime']['capabilities'])

    def test_single_present_role_never_gets_self_or_unavailable_delegate(self):
        config=self.config();role=live_roles(('writer',),config)['writer']
        self.assertEqual(role.delegates,())
        self.assertFalse(set(role.tools)&{'delegate_task','delegate_with_inputs'})
        self.assertIn('read_messages',role.tools)

    def test_cli_requires_live_explicit_key_and_strict_boolean(self):
        parser=argparse.ArgumentParser();add_live_arguments(parser)
        with self.assertRaises(WorkflowError):live_config_from_args(parser.parse_args(['--enable-collaboration']))
        with patch.dict('os.environ',{'COLLAB_TEST_KEY':'not-persisted'},clear=True):
            config=live_config_from_args(parser.parse_args(['--live','--provider','hkgai','--model','m',
                '--api-key-env','COLLAB_TEST_KEY','--enable-collaboration']))
            self.assertTrue(config.enable_collaboration);self.assertFalse(config.enable_web or config.enable_memory)
        for value in (1,'true',None):
            with self.subTest(value=value),self.assertRaises(WorkflowError):
                replace(config,enable_collaboration=value)

    def test_scripted_specialist_chain_pauses_at_real_review_without_auto_pass(self):
        center=self.center('chain',self.config());chat=center.create_conversation('group',list(LIVE_AGENTS))
        root=center.create_task(chat,'coordinator','Fixture team goal',constraints=['Retain all input rows'])['task']
        calls,http=self.script()
        with patch.object(HKGAIHTTP,'__call__',side_effect=http):
            status=center.advance(root)
            self.assertEqual(status['state'],'blocked',status)
            self.assertEqual([actor for actor,_ in calls],['coordinator','writer','editor','editor'])
            before=len(calls);center.advance(root);self.assertEqual(len(calls),before)
        def inspect(backend):
            tasks=[dict(r) for r in backend.workflow.db.execute('SELECT id,parent,assignee,state FROM tasks ORDER BY rowid')]
            sessions=[dict(r) for r in backend.workflow.db.execute('SELECT actor,status,config FROM runner_sessions')]
            return tasks,sessions
        tasks,sessions=center.call(inspect)
        self.assertEqual([t['assignee'] for t in tasks],['coordinator','writer','editor'])
        self.assertEqual(tasks[2]['parent'],tasks[1]['id'])
        self.assertTrue(all(t['state']!='succeeded' for t in tasks))
        self.assertEqual(next(s['status'] for s in sessions if s['actor']=='editor'),'awaiting_verification')
        for _,request in calls:
            self.assertIn('Retain all input rows',json.dumps(request['messages']))
            self.assertNotIn('unused-collaboration-secret',json.dumps(request))

    def test_shared_attempt_limit_still_stops_specialist_chain_across_reopen(self):
        live=self.config(tree_limits=TreeLimits(model_attempts=2))
        center=self.center('budget',live);chat=center.create_conversation('group',list(LIVE_AGENTS))
        root=center.create_task(chat,'coordinator','Fixture budget goal')['task'];calls,http=self.script()
        with patch.object(HKGAIHTTP,'__call__',side_effect=http):
            state=center.advance(root)
        self.assertEqual(len(calls),2);self.assertEqual(state['task_state'],'failed',state)
        center.close();reopened=self.center('budget',live)
        with patch.object(HKGAIHTTP,'__call__',side_effect=AssertionError('No reset after restart')):
            self.assertEqual(reopened.advance(root)['task_state'],'failed')

    def test_new_capability_cannot_be_added_or_removed_on_an_existing_run(self):
        old=replace(self.config(),enable_collaboration=False)
        center=self.center('resume',old);chat=center.create_conversation('group',list(LIVE_AGENTS))
        root=center.create_task(chat,'coordinator','Original goal')['task'];center.close()
        changed=self.center('resume',self.config())
        with patch.object(HKGAIHTTP,'__call__',side_effect=AssertionError('Reject before provider')) as network:
            with self.assertRaises(WorkflowError):changed.advance(root)
            network.assert_not_called()

    def test_plan_v2_is_explicit_and_v1_rejects_silent_capability_additions(self):
        raw=json.loads(PLAN.read_text());raw['cases']=str(PLAN.parent/'collaboration')
        for version,caps in [(1,raw['capabilities']),(2,{k:v for k,v in raw['capabilities'].items() if k!='collaboration'}),
                (2,{**raw['capabilities'],'collaboration':'true'})]:
            path=self.root/'invalid.json';path.write_text(json.dumps({**raw,'version':version,'capabilities':caps}))
            with self.subTest(version=version,caps=caps),self.assertRaises(WorkflowError):DevelopmentPlan(path)
        first=DevelopmentPlan(PLAN);raw['capabilities']['collaboration']=False
        path=self.root/'disabled.json';path.write_text(json.dumps(raw));second=DevelopmentPlan(path)
        self.assertNotEqual(first.sha256,second.sha256)

    def test_plan_inspection_is_bounded_has_no_predetermined_child_titles_and_never_calls_model(self):
        with patch.dict('os.environ',{},clear=True),patch.object(HKGAIHTTP,'__call__') as network:
            plan=DevelopmentPlan(PLAN);record=plan.inspect()
            self.assertEqual(record['maximum_model_attempts'],24)
            self.assertEqual(plan.settings['max_output_tokens'],1024)
            self.assertEqual(plan.conditions['acceptance'][0].get('child_rules',[]),[])
            self.assertIn('actual trusted review',record['child_review_boundary'])
            self.assertIn('alone does not establish',record['a03_acceptance'])
            self.assertEqual(record['model_calls'],0);network.assert_not_called()


if __name__=='__main__':unittest.main()
