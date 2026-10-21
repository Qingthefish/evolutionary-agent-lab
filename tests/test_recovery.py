"""Independent criteria, immutable failed history and bounded replacement."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from agent_lab.core import Workflow, WorkflowError
from agent_lab.files import FileTools
from agent_lab.deepseek import DeepSeekClient
from agent_lab.runner import Limits
from agent_lab.scheduler import MultiAgentScheduler, Role
from agent_lab.runtime import TaskPolicy, ChildTextRule, text_acceptance_factory
from agent_lab import recovery
from agent_lab.budget import TreeLimits
from test_runner import Script, response, tool


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.open()
        for actor, kind in [('user','human'), ('coordinator','agent'), ('writer','agent')]:
            self.w.register_actor(actor, kind)
        self.chat = self.w.create_chat('group',['user','coordinator','writer'])
        self.root = self.w.create_task(self.chat,'user','coordinator','Deliver checked note')
        self.policy = TaskPolicy(root_artifacts={'note.txt':'Hello\n'},
            child_rules=[ChildTextRule('writer','Write note',{'note.txt':'Hello\n'})])
        self.roles = {
            'coordinator': Role('Coordinate repairs',('delegate_task','retry_failed_task','accept_artifact'),('writer',)),
            'writer': Role('Write note',('create_text','offer_artifact'), limits=Limits(model_attempts=2)),
        }
        self.scripts = {a:Script([]) for a in self.roles}

    def open(self):
        self.w = Workflow(self.path/'state.sqlite3')
        self.f = FileTools(self.w,self.path/'files')

    def tearDown(self):
        self.f.close(); self.w.close(); self.temp.cleanup()

    def scheduler(self, maximum=2, **kw):
        return MultiAgentScheduler(self.w,self.f,self.root,human='user',roles=self.roles,
            clients={a:DeepSeekClient('synthetic',s) for a,s in self.scripts.items()},mode='offline_fixture',
            constraints=[],verifier_factory=text_acceptance_factory(self.w,self.f,self.root,self.policy),
            acceptance_id=self.policy.acceptance_id,child_retries=maximum,**kw)

    def failed(self):
        self.w.start_task(self.root,'coordinator')
        child=self.w.create_task(self.chat,'coordinator','writer','Write note',parent=self.root)
        self.w.start_task(child,'writer')
        self.f.create_text(child,'writer','note.txt','Wrong\n')
        self.w.finish_task(child,'writer',error='Independent criterion rejected note.txt')
        return child

    def test_checked_replacement_after_restart_preserves_failure_and_shared_counts(self):
        scheduler=self.scheduler()
        failed=self.failed()
        def retry():
            return response([tool('retry_failed_task',{'failed_task':failed,'reason':'Use the required newline'},'retry')])
        def accept():
            artifact=self.w.db.execute('SELECT id FROM artifacts WHERE target_task=?',(self.root,)).fetchone()[0]
            return response([tool('accept_artifact',{'artifact_id':artifact,'path':'note.txt'},'accept')])
        self.scripts['coordinator']=Script([retry,accept,response()])
        # Two task-local turns: create+offer together, then independently checked final.
        def write():
            import hashlib
            return response([tool(arguments={'path':'note.txt','content':'Hello\n'}),
                tool('offer_artifact',{'path':'note.txt','target_task':self.root,
                    'expected_sha256':hashlib.sha256(b'Hello\n').hexdigest()},'offer')])
        self.scripts['writer']=Script([write,response()])
        self.scheduler().step()
        replacement=recovery.links(self.w)[failed]
        self.f.close(); self.w.close(); self.open()
        result=self.scheduler().run()
        self.assertEqual(result['task_state'],'succeeded')
        self.assertEqual(self.w.task(failed,'user')['state'],'failed')
        self.assertEqual(self.w.task(replacement,'user')['state'],'succeeded')
        self.assertEqual(result['budget']['tasks'],3)
        self.assertEqual(result['budget']['attempts'],5)
        context=json.loads(self.scripts['writer'].requests[0]['messages'][1]['content'])
        self.assertEqual(context['retry']['failed_task'],failed)
        self.assertIn('rejected',context['retry']['failure_evidence']['error'])
        self.assertNotIn('Wrong',json.dumps(context))
        self.assertEqual(result['model_calls'],0)
        from types import SimpleNamespace
        from unittest.mock import patch
        from agent_lab.inspection import ArtifactInspector
        from agent_lab.evaluation import parse_case
        from agent_lab.evaluation.harness import _checks
        case=parse_case({'id':'retry-evaluation','title':'Checked recovery','goal':'Deliver checked note',
            'driver':'live_scheduler','expected':{'final_state':'succeeded','artifacts':{'note.txt':'Hello\n'},
            'subtasks':[{'assignee':'writer','title':'Write note','final_state':'succeeded','artifacts':{'note.txt':'Hello\n'}}]}})
        session=SimpleNamespace(workflow=self.w,files=self.f,inspector=ArtifactInspector(self.w,self.f))
        with patch('agent_lab.evaluation.harness.HUMAN','user'):
            checks,evidence=_checks(case,session,self.root,0)
        self.assertTrue(all(checks.values()))
        self.assertEqual(evidence['task_states']['failed'],1)
        failed_record=next(r for r in evidence['task_outcomes'] if r['task_id']==failed)
        self.assertFalse(failed_record['verified_success'])
        self.assertEqual(failed_record['replacement_task'],replacement)

    def test_default_still_fails_root_on_failed_child(self):
        self.scheduler(0); self.failed()
        self.assertEqual(self.scheduler(0).run()['task_state'],'failed')

    def test_no_skip_or_reopen_of_failed_requirement(self):
        self.scheduler(); failed=self.failed()
        with self.assertRaises(WorkflowError):
            self.w.finish_task(self.root,'coordinator',checks={'pretend':True})
        child=recovery.replace_failed(self.w,self.root,'coordinator',failed,'Repair condition')['task_id']
        with self.assertRaises(WorkflowError):
            self.w.finish_task(self.root,'coordinator',checks={'pretend':True})
        with self.assertRaises(WorkflowError):
            recovery.replace_failed(self.w,self.root,'coordinator',failed,'Again')
        self.assertEqual(self.w.task(child,'user')['title'],'Write note')
        with self.assertRaises(WorkflowError): self.w.start_task(failed,'writer')

    def test_budget_and_original_retry_limit_cannot_reset(self):
        self.scheduler(1,limits=TreeLimits(tasks=2)); failed=self.failed()
        with self.assertRaises(WorkflowError):
            recovery.replace_failed(self.w,self.root,'coordinator',failed,'Repair')
        self.assertEqual(len(recovery.links(self.w)),0)
        with self.assertRaises(WorkflowError): self.scheduler(2,limits=TreeLimits(tasks=2))

    def test_global_limit_stops_repeated_bad_replacements(self):
        self.scheduler(1); failed=self.failed()
        child=recovery.replace_failed(self.w,self.root,'coordinator',failed,'Repair')['task_id']
        self.w.start_task(child,'writer'); self.w.finish_task(child,'writer',error='Still wrong')
        self.assertEqual(self.scheduler(1).run()['task_state'],'failed')
        self.assertEqual(len(recovery.links(self.w)),1)

    def test_denied_or_unreleased_effect_blocks_replacement(self):
        self.scheduler(); self.w.start_task(self.root,'coordinator')
        child=self.w.create_task(self.chat,'coordinator','writer','Write note',parent=self.root)
        self.w.start_task(child,'writer')
        request=self.w.ask_human(child,'writer','user','Critical action',action={'tool':'fixture'})
        self.w.respond(request,'user',approve=True)
        self.w.finish_task(child,'writer',error='Stop before release')
        with self.assertRaisesRegex(WorkflowError,'unreleased'):
            recovery.replace_failed(self.w,self.root,'coordinator',child,'Try again')

    def test_unknown_effect_and_wrong_parent_or_actor_are_rejected(self):
        self.scheduler(); failed=self.failed()
        self.w.db.execute('CREATE TABLE sandbox_runs(task TEXT,status TEXT)')
        self.w.db.execute("INSERT INTO sandbox_runs VALUES(?,'cleanup_failed')",(failed,))
        with self.assertRaisesRegex(WorkflowError,'reconciliation'):
            recovery.replace_failed(self.w,self.root,'coordinator',failed,'Repair')
        with self.assertRaises(WorkflowError):
            recovery.replace_failed(self.w,self.root,'writer',failed,'Repair')

    def test_abandoned_descendants_do_not_hide_live_requirements(self):
        self.scheduler(); self.w.start_task(self.root,'coordinator')
        failed=self.w.create_task(self.chat,'coordinator','writer','Write note',parent=self.root)
        self.w.start_task(failed,'writer')
        abandoned=self.w.create_task(self.chat,'writer','coordinator','Old subplan',parent=failed)
        self.w.finish_task(failed,'writer',error='Plan failed')
        replacement=recovery.replace_failed(self.w,self.root,'coordinator',failed,'Repair')['task_id']
        from agent_lab.budget import descendants
        active={t['id'] for t in recovery.active_tasks(self.w,descendants(self.w,self.root))}
        self.assertEqual(active,{self.root,replacement})
        self.assertEqual(self.w.task(abandoned,'user')['state'],'cancelled')

    def test_failed_child_waits_for_parent_clarification_before_retry(self):
        self.scheduler(); failed=self.failed()
        question=self.w.ask_human(self.root,'coordinator','user','Choose repair input')
        result=self.scheduler().run()
        self.assertEqual(result['state'],'blocked')
        self.assertEqual(result['needs'][0]['kind'],'waiting_input')
        self.w.respond(question,'user',answer='Use the original requirement')
        replacement=recovery.replace_failed(self.w,self.root,'coordinator',failed,'Apply clarified input')
        self.assertIn('task_id',replacement)

    def test_mismatched_legacy_resume_cannot_poison_original_retry_configuration(self):
        self.scheduler(0)
        self.w.db.execute('DELETE FROM retry_policies WHERE root=?',(self.root,))
        with self.assertRaises(WorkflowError): self.scheduler(2)
        self.scheduler(0)
        maximum=self.w.db.execute('SELECT maximum FROM retry_policies WHERE root=?',(self.root,)).fetchone()[0]
        self.assertEqual(maximum,0)

    def test_unknown_provider_usage_cannot_be_hidden_by_replacement(self):
        self.scheduler(); failed=self.failed()
        self.w.db.execute('CREATE TABLE runner_turns(task TEXT,status TEXT)')
        self.w.db.execute("INSERT INTO runner_turns VALUES(?,'provider_error')",(failed,))
        with self.assertRaisesRegex(WorkflowError,'reconciliation'):
            recovery.replace_failed(self.w,self.root,'coordinator',failed,'Try again')

    def test_denial_in_a_failed_subtree_cannot_be_avoided_by_replacing_parent(self):
        self.scheduler(); self.w.start_task(self.root,'coordinator')
        failed=self.w.create_task(self.chat,'coordinator','writer','Write note',parent=self.root)
        self.w.start_task(failed,'writer')
        child=self.w.create_task(self.chat,'writer','coordinator','Subplan',parent=failed)
        self.w.start_task(child,'coordinator')
        request=self.w.ask_human(child,'coordinator','user','Push?',action={'tool':'fixture'})
        self.w.respond(request,'user',approve=False)
        self.w.finish_task(failed,'writer',error='Subplan rejected')
        with self.assertRaisesRegex(WorkflowError,'Denied'):
            recovery.replace_failed(self.w,self.root,'coordinator',failed,'Try elsewhere')

    def test_new_attempt_has_no_fresh_root_call_budget(self):
        self.scheduler(limits=TreeLimits(model_attempts=1)); failed=self.failed()
        self.scripts['coordinator']=Script([response([tool('retry_failed_task',
            {'failed_task':failed,'reason':'Use failure evidence'},'retry')])])
        self.scripts['writer']=Script([response()])
        result=self.scheduler(limits=TreeLimits(model_attempts=1)).run()
        self.assertEqual(result['task_state'],'failed')
        self.assertEqual(result['budget']['attempts'],1)
        self.assertEqual(len(self.scripts['writer'].requests),0)


if __name__=='__main__': unittest.main()
