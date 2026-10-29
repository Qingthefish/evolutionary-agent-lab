"""Synthetic prompts see local reservations; no provider or quota claim."""
from pathlib import Path
import json
import tempfile
import unittest

from agent_lab.budget import configure, TreeLimits, status
from agent_lab.core import Workflow, WorkflowError
from agent_lab.deepseek import DeepSeekClient
from agent_lab.files import FileTools
from agent_lab.gateway import ToolGateway
from agent_lab.runner import TaskRunner, Limits
from test_runner import Script, response, tool


class BudgetContextTests(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory();self.addCleanup(d.cleanup);self.path=Path(d.name);self.now=[1000.0]
        self.w=Workflow(self.path/'state.sqlite3',clock=lambda:self.now[0]);self.addCleanup(self.w.close)
        for actor,kind in [('human','human'),('writer','agent'),('reviewer','agent')]:self.w.register_actor(actor,kind)
        self.chat=self.w.create_chat('group',['human','writer','reviewer'])
        self.root=self.w.create_task(self.chat,'human','writer','Deliver checked note');self.w.start_task(self.root,'writer')
        self.f=FileTools(self.w,self.path/'files');self.addCleanup(self.f.close)

    def runner(self, task, actor, script, strict=True, limits=Limits(model_attempts=3)):
        gateway=ToolGateway(self.w,self.f,task,actor,human='human',allowed=('create_text',),max_calls=4,
            delegation_rules=(('reviewer','Check note'),) if strict else None)
        return TaskRunner(gateway,DeepSeekClient('explicit-synthetic',script),mode='offline_fixture',limits=limits,
            constraints=['Keep the original constraint'],verifier=self.f.text_verifier(task,actor,{'note.txt':'Hello\n'}),verifier_id='checked-note-v1')

    def test_local_counts_refresh_across_restart_without_new_messages_or_tools(self):
        script=Script([response([tool()]),response()]);runner=self.runner(self.root,'writer',script)
        runner.step();first=json.loads(script.requests[0]['messages'][1]['content'])
        self.assertEqual(first['execution_budget']['task']['model_attempts_left_after_current'],2)
        self.assertEqual(first['execution_budget']['task']['tool_calls_left'],4)
        self.assertIsNone(first['execution_budget']['shared'])
        self.now[0]+=5;runner=self.runner(self.root,'writer',script);runner.step()
        last=json.loads(script.requests[1]['messages'][1]['content']);data=last['execution_budget']
        self.assertEqual(data['task']['model_attempts_left_after_current'],1)
        self.assertEqual(data['task']['tool_calls_left'],3)
        self.assertEqual(data['task']['seconds_left'],295)
        self.assertTrue(data['current_request_already_reserved'])
        self.assertEqual(last['constraints'],['Keep the original constraint'])
        self.assertEqual(last['global_goal'],'Deliver checked note')
        self.assertEqual(len([m for m in script.requests[1]['messages'] if m['role']=='user']),1)
        self.assertEqual(runner.status()['task_state'],'succeeded')
        self.assertEqual(self.w.db.execute('SELECT count(*) FROM tool_calls').fetchone()[0],1)

    def test_child_and_parent_observe_same_shared_count_and_finalize_on_last_attempt(self):
        configure(self.w,self.root,TreeLimits(model_attempts=3,tool_calls=5,tasks=4))
        child=self.w.create_task(self.chat,'writer','reviewer','Check note',parent=self.root);self.w.start_task(child,'reviewer')
        self.f.create_text(child,'reviewer','note.txt','Hello\n');child_script=Script([response()])
        self.runner(child,'reviewer',child_script).step()
        child_data=json.loads(child_script.requests[0]['messages'][1]['content'])['execution_budget']['shared']
        self.assertEqual(child_data['model_attempts_left_after_current'],2)
        self.assertEqual(child_data['task_slots_left'],2)  # Counts the root and child, not just this subtree.
        def last_turn():
            request=script.requests[-1];data=json.loads(request['messages'][1]['content'])['execution_budget']
            self.assertEqual(data['shared']['model_attempts_left_after_current'],0)
            self.assertEqual(data['task']['model_attempts_left_after_current'],1)
            return response()
        script=Script([response([tool()]),last_turn]);runner=self.runner(self.root,'writer',script)
        runner.step();runner.step();self.assertEqual(runner.status()['task_state'],'succeeded')
        self.assertEqual(status(self.w,self.root)['attempts'],3)
        runner.step();self.assertEqual(len(script.requests),2)

    def test_budget_context_is_versioned_and_cannot_silently_change_on_resume(self):
        runner=self.runner(self.root,'writer',Script([]));config=json.loads(self.w.db.execute('SELECT config FROM runner_sessions WHERE task=?',(self.root,)).fetchone()[0])
        self.assertEqual(config['budget_context'],'local-reservations-v1')
        with self.assertRaisesRegex(WorkflowError,'Persisted model'):
            self.runner(self.root,'writer',Script([]),strict=False)
        self.assertEqual(self.w.db.execute('SELECT attempts FROM runner_sessions WHERE task=?',(self.root,)).fetchone()[0],0)

    def test_legacy_context_and_config_remain_unchanged(self):
        self.f.create_text(self.root,'writer','note.txt','Hello\n');script=Script([response()]);runner=self.runner(self.root,'writer',script,strict=False)
        runner.step();context=json.loads(script.requests[0]['messages'][1]['content'])
        self.assertNotIn('execution_budget',context)
        config=json.loads(self.w.db.execute('SELECT config FROM runner_sessions WHERE task=?',(self.root,)).fetchone()[0])
        self.assertNotIn('budget_context',config)

    def test_declared_plan_and_manifest_inspect_the_same_context_version(self):
        from agent_lab.evaluation.plan import DevelopmentPlan
        from agent_lab.evaluation.manifest import build_manifest
        from agent_lab.runtime import LiveConfig
        p=DevelopmentPlan(Path(__file__).resolve().parents[1]/'evaluation/checked-collaboration-plan.json')
        expected={c.id:'local-reservations-v1' for c in p.cases}
        live=LiveConfig(api_key='unused-inspection-key',**p.settings)
        self.assertEqual(p.conditions['case_budget_context'],expected)
        self.assertEqual(p.inspect()['budget_context'],expected)
        self.assertEqual(build_manifest(p.cases,live,'off')['runtime']['case_budget_context'],expected)


if __name__=='__main__':unittest.main()
