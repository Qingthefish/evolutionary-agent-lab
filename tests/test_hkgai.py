"""HKGAI wiring and rejection contracts; every model response here is mocked."""

import argparse
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

from agent_lab.core import WorkflowError
from agent_lab.deepseek import DeepSeekClient, DeepSeekHTTP, ProviderError, _NoRedirect
from agent_lab.hkgai import HKGAIClient, HKGAIHTTP
from agent_lab.evaluation import Evaluator, parse_case
from agent_lab.evaluation.experience import LiveExperienceDriver
from agent_lab.evaluation.harness import HUMAN, _Session
from agent_lab.evaluation.manifest import build_manifest
from agent_lab.evaluation.plan import DevelopmentPlan
from agent_lab.runtime import (LIVE_AGENTS, LiveConfig, TaskPolicy, add_live_arguments,
    build_live_scheduler, live_clients, live_config_from_args, provider_endpoint)
from agent_lab.runner import TaskRunner
from agent_lab.tui.controller import ControlCenter

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / 'evaluation/hkgai-smoke-plan.json'


def completion(*, tool=False, reason=None):
    message = {'role':'assistant','content':None if tool else 'File is ready for independent verification.'}
    if tool:
        message['tool_calls'] = [{'id':'smoke-call','type':'function','function':{
            'name':'create_text','arguments':json.dumps({'path':'probe.txt','content':'hkgai-live-ok\n'})}}]
    return json.dumps({'id':'mock-hkgai-response','model':'observed-hkgai-model',
        'choices':[{'finish_reason':reason or ('tool_calls' if tool else 'stop'),'message':message}],
        'usage':{'prompt_tokens':12,'completion_tokens':8,'total_tokens':20}}).encode()


def config(**changes):
    return LiveConfig(model='same-explicit-model',api_key='test-secret-not-real',provider='hkgai',**changes)


class HKGAITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def session(self, name):
        directory=self.root/name;directory.mkdir()
        session=_Session(directory,'hkgai-contract')
        self.addCleanup(session.close)
        chat=session.workflow.create_chat('group',[HUMAN,*LIVE_AGENTS])
        task=session.workflow.create_task(chat,HUMAN,'coordinator','Write probe.txt')
        return session,task

    def test_http_uses_only_issued_host_with_bearer_and_bounded_read(self):
        response=MagicMock();response.__enter__.return_value=response
        response.status=200;response.geturl.return_value=HKGAIHTTP.endpoint;response.read.return_value=b'{}'
        opener=MagicMock();opener.open.return_value=response
        with patch('urllib.request.build_opener',return_value=opener):
            self.assertEqual(HKGAIHTTP('test-secret',allow_network=True,timeout=9)(b'{}'),b'{}')
        request=opener.open.call_args.args[0]
        self.assertEqual(request.full_url,'https://api1.hkgai.net/v1/chat/completions')
        self.assertEqual(request.get_header('Authorization'),'Bearer test-secret')
        self.assertEqual(opener.open.call_args.kwargs['timeout'],9)
        response.read.assert_called_once_with(HKGAIHTTP.max_bytes+1)
        self.assertIsInstance(opener.open.call_args.args[0].data,bytes)
        self.assertIsNone(_NoRedirect().redirect_request(None,None,302,'',{},'https://elsewhere.test'))

    def test_no_implicit_network_retry_fallback_or_raw_error_secret(self):
        with patch('urllib.request.build_opener') as opener,self.assertRaises(ProviderError):
            HKGAIHTTP('test-secret')(b'{}')
        opener.assert_not_called()
        errors=[TimeoutError('test-secret'),urllib.error.HTTPError(HKGAIHTTP.endpoint,401,'test-secret',{},io.BytesIO(b'test-secret'))]
        for error in errors:
            with self.subTest(error=type(error).__name__),patch('urllib.request.build_opener') as opener:
                opener.return_value.open.side_effect=error
                with self.assertRaises(ProviderError) as caught:
                    HKGAIHTTP('test-secret',allow_network=True)(b'{}')
                self.assertNotIn('test-secret',str(caught.exception))
                self.assertEqual(opener.return_value.open.call_count,1)
        self.assertNotIn('test-secret',repr(HKGAIHTTP('test-secret')))

    def test_unexpected_response_url_is_not_accepted(self):
        response=MagicMock();response.__enter__.return_value=response
        response.status=200;response.geturl.return_value='https://elsewhere.test/completions'
        with patch('urllib.request.build_opener') as opener,self.assertRaises(ProviderError):
            opener.return_value.open.return_value=response
            HKGAIHTTP('test-secret',allow_network=True)(b'{}')
        response.read.assert_not_called()

    def test_hkgai_sends_standard_fields_and_preserves_strict_tool_cycle(self):
        sent=[]
        def http(payload):
            sent.append(json.loads(payload));return completion(tool=len(sent)==1)
        client=HKGAIClient('issued-model',http,max_tokens=512)
        first=client.complete([{'role':'user','content':'Write probe.txt'}],tools=[{'type':'function'}])
        client.complete([first.message,{'role':'tool','tool_call_id':'smoke-call','content':'actual receipt'}])
        self.assertEqual(set(sent[0]),{'model','messages','stream','max_tokens','tools','tool_choice'})
        self.assertFalse(sent[0]['stream']);self.assertEqual(sent[0]['max_tokens'],512)
        self.assertEqual(sent[1]['messages'][1]['tool_call_id'],'smoke-call')
        self.assertEqual(first.model,'observed-hkgai-model');self.assertEqual(first.usage['total_tokens'],20)

    def test_incomplete_missing_usage_and_ambiguous_tools_release_nothing(self):
        missing=json.loads(completion(tool=True));missing.pop('usage')
        duplicate=json.loads(completion(tool=True));duplicate['choices'][0]['message']['tool_calls']*=2
        for raw in (completion(tool=True,reason='length'),json.dumps(missing).encode(),json.dumps(duplicate).encode(),b'{"a":1,"a":2}'):
            with self.subTest(raw=raw[:40]),self.assertRaises(ProviderError):
                HKGAIClient('issued-model',lambda _:raw).complete([{'role':'user','content':'test'}])

    def test_shared_cli_and_experience_select_hkgai_without_network_on_setup(self):
        parser=argparse.ArgumentParser();add_live_arguments(parser)
        with patch.dict('os.environ',{'TEST_HK_KEY':'not-serialized'},clear=True),patch.object(HKGAIHTTP,'__call__') as network:
            live=live_config_from_args(parser.parse_args(['--live','--provider','hkgai','--model','issued-model','--api-key-env','TEST_HK_KEY']))
            clients=live_clients(live,('coordinator',))
            experience=LiveExperienceDriver(live).clients(('coordinator',),{'phase':'probe'})
            for client in (clients['coordinator'],experience['coordinator']):
                self.assertIs(type(client),HKGAIClient);self.assertIs(type(client.transport),HKGAIHTTP)
            network.assert_not_called()
        self.assertNotIn('not-serialized',repr(live))
        with self.assertRaises(WorkflowError):provider_endpoint('openai')

    def test_scheduler_and_runner_reject_mode_protocol_and_provider_swaps(self):
        session,task=self.session('guards');live=config()
        scheduler=build_live_scheduler(session.workflow,session.files,task,human=HUMAN,live=live)
        session.workflow.start_task(task,'coordinator');runner=scheduler.runner(task)
        with self.assertRaises(WorkflowError):
            TaskRunner(runner.gateway,runner.client,mode='offline_fixture',constraints=[])
        with self.assertRaises(WorkflowError):
            TaskRunner(runner.gateway,DeepSeekClient(live.model,HKGAIHTTP(live.api_key)),mode='live',constraints=[])
        with self.assertRaises(WorkflowError):
            build_live_scheduler(session.workflow,session.files,task,human=HUMAN,live=replace(live,provider='deepseek'))
        with self.assertRaises(WorkflowError):
            TaskRunner(runner.gateway,DeepSeekClient(live.model,DeepSeekHTTP(live.api_key)),mode='live',constraints=[])
        for table,column in (('scheduler_runs','root'),('runner_sessions','task')):
            record=json.loads(session.workflow.db.execute(f'SELECT config FROM {table} WHERE {column}=?',(task,)).fetchone()[0])
            self.assertEqual(record['provider'],{'name':'hkgai','endpoint':HKGAIHTTP.endpoint})
            self.assertNotIn(live.api_key,json.dumps(record))

    def test_legacy_deepseek_session_keeps_its_configuration_shape(self):
        session,task=self.session('legacy');live=config();live=replace(live,provider='deepseek')
        scheduler=build_live_scheduler(session.workflow,session.files,task,human=HUMAN,live=live)
        self.assertNotIn('provider',json.loads(session.workflow.db.execute('SELECT config FROM scheduler_runs').fetchone()[0]))
        session.workflow.start_task(task,'coordinator');scheduler.runner(task)
        self.assertNotIn('provider',json.loads(session.workflow.db.execute('SELECT config FROM runner_sessions').fetchone()[0]))
        build_live_scheduler(session.workflow,session.files,task,human=HUMAN,live=live)

    def test_ui_reports_selected_provider_and_creating_task_does_not_call_it(self):
        with patch.object(HKGAIHTTP,'__call__') as network:
            center=ControlCenter(self.root/'ui',live=config())
            self.addCleanup(center.close)
            chat=center.create_conversation('group',list(LIVE_AGENTS))
            center.create_task(chat,'coordinator','Write probe.txt',expected_artifacts={'probe.txt':'hkgai-live-ok\n'})
            self.assertIn('hkgai',center.status()['provider']);self.assertIn('hkgai',center.runtimes()['model'])
            network.assert_not_called()

    def test_bounded_plan_inspection_and_manifests_use_actual_selected_provider(self):
        with patch.dict('os.environ',{},clear=True),patch.object(HKGAIHTTP,'__call__') as network:
            plan=DevelopmentPlan(PLAN);inspection=plan.inspect()
            self.assertEqual(inspection['maximum_model_attempts'],4)
            self.assertFalse(inspection['configured_to_attempt'])
            self.assertEqual(plan.settings['max_output_tokens'],512)
            self.assertEqual(plan.settings['provider'],'hkgai');network.assert_not_called()
            with self.assertRaises(WorkflowError):
                plan.execute(allow_model_calls=True,plan_sha256=plan.sha256,output_root=self.root/'missing-key')
        manifest=build_manifest(plan.cases,config(),'off')
        self.assertEqual(manifest['runtime']['endpoint'],HKGAIHTTP.endpoint)
        self.assertEqual(manifest['runtime']['provider'],'hkgai')
        self.assertNotIn(config().api_key,json.dumps(manifest))

    def test_mocked_full_evaluator_writes_real_file_and_records_actual_model(self):
        plan=DevelopmentPlan(PLAN);sent=[]
        def http(payload):
            sent.append(json.loads(payload));return completion(tool=len(sent)==1)
        with patch.object(HKGAIHTTP,'__call__',side_effect=http),patch.object(DeepSeekHTTP,'__call__',side_effect=AssertionError('No DeepSeek fallback')):
            report=Evaluator(plan.cases,output_root=self.root/'eval',live=config(allow_network=True)).run()
        result=report['results'][0]
        self.assertEqual(result['classification'],'completed',result)
        self.assertEqual(len(sent),2)
        self.assertEqual(report['manifest']['runtime']['provider'],'hkgai')
        self.assertEqual(result['workflow']['observed_models'],['observed-hkgai-model'])
        self.assertTrue(sent[1]['messages'][-1]['role']=='tool')
        for path in (self.root/'eval').rglob('*'):
            if path.is_file():self.assertNotIn(config().api_key.encode(),path.read_bytes())


if __name__ == '__main__':unittest.main()
