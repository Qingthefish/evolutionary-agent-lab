"""Exercise the public pause/extend/resume CLI with a synthetic HTTP response."""

from contextlib import redirect_stdout, redirect_stderr, closing
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_lab import budget
from agent_lab.core import Workflow
from agent_lab.evaluation import official_live
from agent_lab.evaluation.official import OfficialMidTestPlan
from agent_lab.evaluation.official_dataset import load_mid_test
from agent_lab.evaluation.official_session import OfficialScenarioSession
from agent_lab.hkgai import HKGAIHTTP
from official_mid_fixture import write_archive, README_SHA256

TEMPLATE=Path(__file__).resolve().parents[1]/'evaluation/official/mid-test/plan.json'


def response(name, arguments, number):
    return json.dumps({'id':'fixture','model':'fixture','usage':{
        'prompt_tokens':1,'completion_tokens':2,'total_tokens':3},'choices':[{
        'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[{
            'id':f'fixture-{number}','type':'function','function':{'name':name,'arguments':json.dumps(arguments)}}]}}]}).encode()


class OfficialQualityControl(unittest.TestCase):
    def setUp(self):
        guard=patch('agent_lab.evaluation.official_dataset._README_SHA256',README_SHA256)
        guard.start();self.addCleanup(guard.stop)
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.home=Path(tmp.name);self.state=self.home/'state';self.state.mkdir()
        write_archive(self.home/'Mid_Test.zip')
        (self.home/'manifest.json').write_text(json.dumps(load_mid_test(self.home/'Mid_Test.zip')))
        self.plan=json.loads(TEMPLATE.read_text())
        self.plan['runtime'].update(provider='hkgai',model='fixture',api_key_env='COURSE_HKGAI_API_KEY',
            per_scenario_model_attempts=4,max_output_tokens=8192,tool_policy='newsroom-files-coordination-web-v1')
        self.old=self.home/'old.json';self.old.write_text(json.dumps(self.plan))
        checked=OfficialMidTestPlan(self.old)
        with closing(Workflow(self.state/'workflow.sqlite3')) as workflow:
            session=OfficialScenarioSession.initialize(workflow,checked,scenario='newsroom',human='requester',plan_sha256=checked.sha256)
            self.root=session.post(1,'chief_editor')['root']
        self.provider=patch.object(HKGAIHTTP,'__call__',side_effect=[
            response('create_text',{'path':'result.md','content':'first'},1),
            response('append_text',{'path':'result.md','content':'-second','expected_sha256':hashlib.sha256(b'first').hexdigest()},2),
            response('submit_for_verification',{'summary':'result.md ready for independent review'},3)])
        self.http=self.provider.start();self.addCleanup(self.provider.stop)
        env=patch.dict('os.environ',{'COURSE_HKGAI_API_KEY':'synthetic-key'});env.start();self.addCleanup(env.stop)

    def command(self, action, *extra, plan=None, fails=False):
        out,err=io.StringIO(),io.StringIO()
        args=['--config',str(plan or self.old),'--state-dir',str(self.state),'--sequence','1',action,
              '--execution-profile','quality','--output-token-ceiling','8192',*map(str,extra)]
        with redirect_stdout(out),redirect_stderr(err):
            try:code=official_live.main(args)
            except SystemExit as e:code=e.code
        self.assertEqual(bool(code),fails,err.getvalue())
        return err.getvalue() if fails else json.loads(out.getvalue())

    def test_public_cli_extends_same_goal_and_keeps_the_two_original_requests(self):
        self.command('preflight')
        paused=self.command('run','--allow-model-requests')
        self.assertEqual(paused['needs'][0]['kind'],'execution_budget')
        self.assertEqual((self.http.call_count,paused['task_state']),(2,'running'))
        inspected=self.command('preflight')
        proposed=json.loads(json.dumps(self.plan));proposed['runtime']['per_scenario_model_attempts']=8
        new=self.home/'new.json';new.write_text(json.dumps(proposed))
        extended=self.command('extend','--new-config',new,'--expected-config-sha256',inspected['configuration_sha256'],
            '--reason','Owner-authorized quality continuation after inspecting the retained partial artifact','--confirm-stopped')
        self.assertEqual((extended['model_calls'],extended['budget']['attempts'],self.http.call_count),(0,2,2))
        after=self.command('advance',plan=new)
        self.assertEqual(after['needs'][0]['kind'],'awaiting_verification')
        self.assertEqual((after['budget']['attempts'],self.http.call_count),(3,3))
        with closing(Workflow(self.state/'workflow.sqlite3')) as workflow:
            self.assertEqual(workflow.task(self.root,'requester')['state'],'running')
            self.assertEqual(budget.status(workflow,self.root)['attempts'],3)
        self.assertIn('same reviewed',self.command('preflight',fails=True))

    def test_extension_cannot_change_provider_model_or_content_rules(self):
        before=self.command('preflight')
        proposed=json.loads(json.dumps(self.plan));proposed['runtime'].update(per_scenario_model_attempts=8,model='different')
        new=self.home/'wrong.json';new.write_text(json.dumps(proposed))
        error=self.command('extend','--new-config',new,'--expected-config-sha256',before['configuration_sha256'],
            '--reason','Synthetic invalid extension','--confirm-stopped',fails=True)
        self.assertIn('only change',error)
        self.assertEqual(self.command('preflight')['configuration_sha256'],before['configuration_sha256'])
        self.assertEqual(self.http.call_count,0)


if __name__=='__main__':unittest.main()
