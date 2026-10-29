"""Model proposals reuse trusted verification; scripted responses are not live evidence."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.budget import configure, TreeLimits, status
from agent_lab.core import Workflow, WorkflowError
from agent_lab.deepseek import DeepSeekClient
from agent_lab.files import FileTools
from agent_lab.gateway import ToolGateway
from agent_lab.queries import WorkflowQueries
from agent_lab.runner import TaskRunner, Limits, RunnerError
from agent_lab.runtime import LiveConfig, TaskPolicy, ChildTextRule, live_members, live_roles_for_policy
from test_runner import Script, response, tool

DEFAULT=object()
class Interrupted(BaseException): pass

def submit(identifier='submit',summary='Deliverable ready for independent checks'):
    return tool('submit_for_verification',{'summary':summary},identifier)


class VerificationSubmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name);self.now=[1000.0];self.open()
        for actor,kind in [('human','human'),('writer','agent'),('reviewer','agent')]:self.w.register_actor(actor,kind)
        self.chat=self.w.create_chat('group',['human','writer','reviewer'])
        self.task=self.w.create_task(self.chat,'human','writer','Deliver checked note');self.w.start_task(self.task,'writer')

    def open(self):
        self.w=Workflow(self.path/'state.sqlite3',clock=lambda:self.now[0]);self.f=FileTools(self.w,self.path/'files')

    def tearDown(self):self.f.close();self.w.close();self.temp.cleanup()

    def runner(self,script,*,verifier=DEFAULT,allowed=None,limits=Limits(),max_tools=32):
        gateway=ToolGateway(self.w,self.f,self.task,'writer',human='human',allowed=allowed or (
            'create_text','read_text','update_text','offer_artifact','ask_human','delegate_task','submit_for_verification'),
            delegates=('reviewer',),max_calls=max_tools)
        if verifier is DEFAULT:verifier=self.f.text_verifier(self.task,'writer',{'note.txt':'Hello\n'})
        return TaskRunner(gateway,DeepSeekClient('synthetic-model',script),mode='offline_fixture',constraints=['Keep input attribution'],
            verifier=verifier,verifier_id='note-check-v1' if verifier else None,limits=limits)

    def test_last_allowed_model_and_tool_slots_can_create_and_propose_with_actual_checks(self):
        configure(self.w,self.task,TreeLimits(model_attempts=1,tool_calls=2))
        script=Script([response([tool(),submit()])]);runner=self.runner(script,limits=Limits(model_attempts=1),max_tools=2)
        state=runner.step();self.assertEqual(state['task_state'],'succeeded');self.assertEqual(len(script.requests),1)
        self.assertEqual(status(self.w,self.task)['attempts'],1);self.assertEqual(status(self.w,self.task)['tool_calls'],2)
        transcript=json.loads(self.w.db.execute('SELECT transcript FROM runner_sessions').fetchone()[0])
        self.assertEqual([m['role'] for m in transcript],['system','user','assistant','tool','tool'])
        self.assertTrue(json.loads(self.w.task(self.task,'human')['evidence'])['checks'])
        runner.step();self.assertEqual(len(script.requests),1)

    def test_rejected_proposal_returns_evidence_and_can_repair_after_restart(self):
        script=Script([response([tool(arguments={'path':'note.txt','content':'Wrong\n'}),submit()]),
            response([tool('update_text',{'path':'note.txt','content':'Hello\n','expected_sha256':hashlib.sha256(b'Wrong\n').hexdigest()},'fix'),submit('fixed')])])
        runner=self.runner(script);self.assertEqual(runner.step()['task_state'],'running')
        self.assertIn('trusted_verification_failure',self.w.db.execute('SELECT transcript FROM runner_sessions').fetchone()[0])
        self.f.close();self.w.close();self.open();state=self.runner(script).step()
        self.assertEqual(state['task_state'],'succeeded');self.assertEqual(len(script.requests),2)
        self.assertEqual(self.w.db.execute("SELECT count(*) FROM events WHERE kind='completion_proposed'").fetchone()[0],2)

    def test_no_verifier_means_real_review_is_still_required(self):
        script=Script([response([tool(),submit(summary='Ready for review')])]);runner=self.runner(script,verifier=None)
        state=runner.step();self.assertEqual(state['runner_state'],'awaiting_verification');self.assertEqual(state['task_state'],'running')
        view=WorkflowQueries(self.w).task_detail(self.task,'human')
        self.assertEqual(view['runner']['turns'][0]['final_text'],'Ready for review')
        self.assertEqual(self.w.db.execute("SELECT count(*) FROM events WHERE kind='human_review_recorded'").fetchone()[0],0)
        runner.step();self.assertEqual(len(script.requests),1)

    def test_gateway_proposal_alone_never_marks_success(self):
        runner=self.runner(Script([]));result=json.loads(runner.gateway.dispatch(submit())['content'])
        self.assertEqual(result['result']['status'],'verification_requested')
        self.assertEqual(self.w.task(self.task,'human')['state'],'running')
        self.assertEqual(self.w.db.execute("SELECT count(*) FROM events WHERE kind='succeeded'").fetchone()[0],0)

    def test_submission_must_be_unique_and_last_before_any_batch_effect(self):
        runner=self.runner(Script([]))
        for calls in [[tool(),submit(),tool('read_text',{'path':'note.txt'},'read')],[submit('one'),submit('two')]]:
            before=self.w.db.total_changes
            with self.assertRaisesRegex(WorkflowError,'exactly once as the last tool'):runner.gateway.validate_batch(calls)
            self.assertEqual(self.w.db.total_changes,before)
        self.assertEqual(self.w.db.execute('SELECT count(*) FROM tool_calls').fetchone()[0],0)
        self.assertFalse((self.path/'files/tasks'/hashlib.sha256(self.task.encode()).hexdigest()/'note.txt').exists())

    def test_human_pause_prevents_submission_and_cannot_show_unexecuted_proposal(self):
        script=Script([response([tool('ask_human',{'prompt':'Which source should be used?'},'ask'),submit()])])
        state=self.runner(script).step();self.assertEqual(state['task_state'],'waiting_input')
        self.assertEqual(self.w.db.execute("SELECT count(*) FROM tool_calls WHERE name='submit_for_verification'").fetchone()[0],0)
        self.assertIsNone(WorkflowQueries(self.w).task_detail(self.task,'human')['runner']['turns'][0]['final_text'])

    def test_parent_cannot_submit_success_with_unfinished_children(self):
        self.f.create_text(self.task,'writer','note.txt','Hello\n')
        script=Script([response([tool('delegate_task',{'assignee':'reviewer','title':'Independent check'},'delegate'),submit()])])
        state=self.runner(script).step();self.assertEqual(state['task_state'],'running')
        self.assertIn('delegated work is incomplete',self.w.db.execute('SELECT transcript FROM runner_sessions').fetchone()[0])
        self.assertEqual(self.w.db.execute("SELECT count(*) FROM tasks WHERE state='pending'").fetchone()[0],1)

    def test_tool_and_token_budgets_cannot_be_bypassed_by_a_submission(self):
        script=Script([response([tool(),submit()])]);state=self.runner(script,max_tools=1).step()
        self.assertEqual(state['task_state'],'failed');self.assertEqual(self.w.db.execute('SELECT count(*) FROM tool_calls').fetchone()[0],0)
        # A separate task has the same tools but an insufficient observed-token stop threshold.
        self.task=self.w.create_task(self.chat,'human','writer','Other checked note');self.w.start_task(self.task,'writer')
        script=Script([response([tool(),submit()])]);state=self.runner(script,limits=Limits(reported_tokens=7)).step()
        self.assertEqual(state['task_state'],'failed');self.assertEqual(self.w.db.execute('SELECT count(*) FROM tool_calls').fetchone()[0],0)

    def test_recovery_keeps_receipts_but_does_not_automatically_reissue_verification(self):
        script=Script([response([tool(),submit()]),response([submit('new-proposal')])]);runner=self.runner(script)
        with patch.object(runner,'_verify',side_effect=Interrupted()),self.assertRaises(Interrupted):runner.step()
        self.f.close();self.w.close();self.open();runner=self.runner(script)
        state=runner.recover_tools();self.assertEqual(state['task_state'],'running');self.assertEqual(state['runner_state'],'ready')
        self.assertEqual(self.w.db.execute("SELECT count(*) FROM events WHERE kind='succeeded'").fetchone()[0],0)
        self.assertEqual(runner.step()['task_state'],'succeeded')
        self.assertEqual(self.w.db.execute("SELECT count(*) FROM events WHERE kind='file_created'").fetchone()[0],1)
        self.assertIn('interrupted_verification_proposal',json.dumps(script.requests[1]))

    def test_uncertain_reserved_tool_cannot_be_recovered_as_a_success(self):
        script=Script([response([tool(),submit()])]);runner=self.runner(script);original=runner.gateway._execute
        def interrupted(name,args):
            if name=='submit_for_verification':raise Interrupted()
            return original(name,args)
        with patch.object(runner.gateway,'_execute',side_effect=interrupted),self.assertRaises(Interrupted):runner.step()
        with self.assertRaisesRegex(RunnerError,'uncertain'):runner.recover_tools()
        self.assertEqual(self.w.task(self.task,'human')['state'],'running');self.assertEqual(len(script.requests),1)

    def test_reused_old_call_id_cannot_display_a_new_submission(self):
        script=Script([response([tool(),submit(summary='First proposal')]),response([submit(summary='Forged new proposal')])])
        runner=self.runner(script,verifier=None);runner.step();runner.review_failed('Needs further evidence',reviewer='human');runner.step()
        turns=WorkflowQueries(self.w).task_detail(self.task,'human')['runner']['turns']
        self.assertEqual(turns[0]['final_text'],'First proposal');self.assertIsNone(turns[1]['final_text'])

    def test_legacy_roles_and_opt_in_persisted_protocol_are_explicit(self):
        live=LiveConfig('synthetic-model','unused-key');legacy=live_roles_for_policy(live_members(live),live,TaskPolicy())
        self.assertTrue(all('submit_for_verification' not in r.tools for r in legacy.values()))
        policy=TaskPolicy(child_rules=(ChildTextRule('writer','Draft',{'note.txt':'Hello\n'}),),declared_subtasks_only=True)
        strict=live_roles_for_policy(live_members(live),live,policy)
        self.assertTrue(all('submit_for_verification' in r.tools for r in strict.values()))
        script=Script([]);self.runner(script)
        config=json.loads(self.w.db.execute('SELECT config FROM runner_sessions').fetchone()[0]);self.assertEqual(config['submission_protocol'],'independent-verification-proposal-v1')
        with self.assertRaisesRegex(RunnerError,'Persisted model'):self.runner(script,allowed=('create_text','read_text'))
        self.assertEqual(self.w.db.execute('SELECT attempts FROM runner_sessions').fetchone()[0],0)

    def test_controller_stop_claim_wins_over_a_late_submission(self):
        runner=self.runner(Script([response([tool(),submit()])]))
        original=runner.gateway._execute
        def stop(name,args):
            result=original(name,args)
            if name=='submit_for_verification':
                self.w.db.execute("UPDATE runner_sessions SET status='stopping',stop_reason='Explicit controller stop'")
            return result
        with patch.object(runner.gateway,'_execute',side_effect=stop):state=runner.step()
        self.assertEqual(state['runner_state'],'stopping');self.assertEqual(state['task_state'],'running')
        self.assertEqual(runner.step()['task_state'],'failed')
        self.assertEqual(self.w.db.execute("SELECT count(*) FROM events WHERE kind='succeeded'").fetchone()[0],0)

    def test_expiry_during_independent_checks_cannot_certify_success(self):
        def verifier():
            checks=self.f.text_verifier(self.task,'writer',{'note.txt':'Hello\n'})()
            self.now[0]+=301
            return checks
        runner=self.runner(Script([response([tool(),submit()])]),verifier=verifier)
        self.assertEqual(runner.step()['task_state'],'running')
        self.assertEqual(runner.step()['task_state'],'failed')
        self.assertEqual(self.w.db.execute("SELECT count(*) FROM events WHERE kind='succeeded'").fetchone()[0],0)

    def test_approved_unreleased_action_cannot_be_skipped_by_submission(self):
        request=self.w.ask_human(self.task,'writer','human','Release this exact action?',
            action={'tool':'delete_text','arguments':{'path':'note.txt','expected_sha256':'0'*64}})
        self.w.respond(request,'human',approve=True)  # Synthetic trusted controller in this unit test.
        script=Script([response([submit()])]);state=self.runner(script).step()
        self.assertEqual(state['needs'],'trusted_action_release');self.assertEqual(len(script.requests),0)
        self.assertEqual(self.w.task(self.task,'human')['state'],'running')


if __name__=='__main__':unittest.main()
