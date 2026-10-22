"""D03 request/effect attribution; real disposable files/local Git, no models."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.core import Workflow, WorkflowError
from agent_lab.files import FileTools
from agent_lab.gateway import ToolGateway
from agent_lab.queries import WorkflowQueries
from agent_lab.tui.controller import ControlCenter
from test_runner import tool


class ActionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name)
        self.workflow=Workflow(self.root/'state.sqlite3')
        self.workflow.register_actor('human','human');self.workflow.register_actor('writer','agent')
        self.chat=self.workflow.create_chat('private',['human','writer'])
        self.task=self.workflow.create_task(self.chat,'human','writer','Inspect actual evidence')
        self.workflow.start_task(self.task,'writer')
        self.files=FileTools(self.workflow,self.root/'files')
        self.gateway=ToolGateway(self.workflow,self.files,self.task,'writer',human='human',allowed=['delete_text'])
        self.queries=WorkflowQueries(self.workflow)

    def tearDown(self):
        self.files.close();self.workflow.close();self.temporary.cleanup()

    def request(self,path='note.txt',content='Fixture\n'):
        receipt=self.files.create_text(self.task,'writer',path,content)
        call=tool('delete_text',{'path':path,'expected_sha256':receipt['sha256']},path)
        request=json.loads(self.gateway.dispatch(call)['content'])['result']['request_id']
        self.workflow.respond(request,'human',approve=True)
        return request,receipt

    def outcome(self,request):
        return self.queries.request_detail(request,'human')['outcome']

    def reopen(self):
        self.files.close();self.workflow.close()
        self.workflow=Workflow(self.root/'state.sqlite3');self.files=FileTools(self.workflow,self.root/'files')
        self.queries=WorkflowQueries(self.workflow)
        self.gateway=ToolGateway(self.workflow,self.files,self.task,'writer',human='human',allowed=['delete_text'])

    def event(self,kind):
        row=self.workflow.db.execute('SELECT * FROM events WHERE task=? AND kind=? ORDER BY sequence DESC LIMIT 1',
                                     (self.task,kind)).fetchone()
        return dict(row)

    def test_later_deletion_does_not_confirm_a_failed_earlier_approval(self):
        first,receipt=self.request('first.txt')
        self.files.update_text(self.task,'writer','first.txt','Changed\n',expected_sha256=receipt['sha256'])
        with self.assertRaises(WorkflowError):self.gateway.release_approved(first)
        self.assertEqual(self.outcome(first)['kind'],'unrecorded')
        second,_=self.request('second.txt');self.gateway.release_approved(second)
        self.reopen()
        self.assertEqual(self.outcome(first)['kind'],'unrecorded')
        self.assertEqual(self.outcome(second)['detail']['request_id'],second)
        self.assertEqual(self.outcome(second)['detail']['path'],'second.txt')
        self.assertEqual(self.files.read_text(self.task,'writer','first.txt')['content'],'Changed\n')
        self.assertTrue(any(first in u['detail'] for u in self.queries.uncertain('human')))

    def test_historical_unbound_effects_stay_raw_and_unconfirmed_without_mutation(self):
        request,receipt=self.request()
        action=json.loads(self.workflow.request(request,'human')['action'])
        self.workflow.consume_approval(request,'writer',action)
        self.files.delete_text(self.task,'writer','note.txt',expected_sha256=receipt['sha256'])
        before=list(map(tuple,self.workflow.db.execute('SELECT * FROM events')))
        changes=self.workflow.db.total_changes
        self.assertEqual(self.outcome(request)['kind'],'unrecorded')
        self.assertEqual(self.workflow.db.total_changes,changes)
        self.assertEqual(before,list(map(tuple,self.workflow.db.execute('SELECT * FROM events'))))
        self.assertEqual(self.event('file_deleted')['kind'],'file_deleted')

    def test_bound_receipt_requires_consumed_exact_task_action_and_is_single_use(self):
        request,receipt=self.request()
        with self.assertRaises(WorkflowError):
            self.files.delete_text(self.task,'writer','note.txt',expected_sha256=receipt['sha256'],request_id=request)
        self.gateway.release_approved(request)
        self.assertEqual(self.outcome(request)['kind'],'file_deleted')
        recreated=self.files.create_text(self.task,'writer','note.txt','Fixture\n')
        with self.assertRaises(WorkflowError):
            self.files.delete_text(self.task,'writer','note.txt',expected_sha256=recreated['sha256'],request_id=request)
        self.assertEqual(self.files.read_text(self.task,'writer','note.txt')['sha256'],recreated['sha256'])

    def test_a_consumed_grant_cannot_bind_a_different_file_or_task(self):
        request,receipt=self.request()
        action=json.loads(self.workflow.request(request,'human')['action'])
        self.workflow.consume_approval(request,'writer',action)
        same=self.files.create_text(self.task,'writer','other.txt','Fixture\n')
        with self.assertRaises(WorkflowError):
            self.files.delete_text(self.task,'writer','other.txt',expected_sha256=same['sha256'],request_id=request)
        other=self.workflow.create_task(self.chat,'human','writer','Other task');self.workflow.start_task(other,'writer')
        self.files.create_text(other,'writer','note.txt','Fixture\n')
        with self.assertRaises(WorkflowError):
            self.files.delete_text(other,'writer','note.txt',expected_sha256=receipt['sha256'],request_id=request)

    def test_model_cannot_supply_the_trusted_receipt_binding(self):
        receipt=self.files.create_text(self.task,'writer','note.txt','Fixture\n')
        with self.assertRaises(WorkflowError):
            self.gateway.dispatch(tool('delete_text',{'path':'note.txt','expected_sha256':receipt['sha256'],
                'request_id':'model-chosen-binding'},'forged-binding'))
        self.assertEqual(self.queries.requests('human'),[])
        self.assertEqual(self.files.read_text(self.task,'writer','note.txt')['content'],'Fixture\n')

    def test_success_after_recreation_does_not_confirm_the_previous_failed_same_path(self):
        first,receipt=self.request()
        self.files.update_text(self.task,'writer','note.txt','New\n',expected_sha256=receipt['sha256'])
        with self.assertRaises(WorkflowError):self.gateway.release_approved(first)
        current=self.files.read_text(self.task,'writer','note.txt')
        call=tool('delete_text',{'path':'note.txt','expected_sha256':current['sha256']},'new-version')
        second=json.loads(self.gateway.dispatch(call)['content'])['result']['request_id']
        self.workflow.respond(second,'human',approve=True);self.gateway.release_approved(second)
        self.assertEqual(self.outcome(first)['kind'],'unrecorded')
        self.assertEqual(self.outcome(second)['detail']['sha256'],current['sha256'])

    def test_conflicting_or_altered_file_receipts_fail_closed(self):
        request,_=self.request();self.gateway.release_approved(request)
        event=self.event('file_deleted');original=json.loads(event['detail'])
        for change in ({'path':'wrong.txt'},{'sha256':'0'*64},{'bytes':True},{'request_id':'unrelated'}):
            self.workflow.db.execute('UPDATE events SET detail=? WHERE sequence=?',
                                     (json.dumps(original|change),event['sequence']))
            self.assertEqual(self.outcome(request)['kind'],'unrecorded')
        self.workflow.db.execute('UPDATE events SET detail=? WHERE sequence=?',(event['detail'],event['sequence']))
        self.workflow._event(self.task,'writer','file_deleted',original)
        self.assertEqual(self.outcome(request)['kind'],'unrecorded')

    def test_missing_release_wrong_actor_and_corrupted_digest_do_not_certify(self):
        request,_=self.request();self.gateway.release_approved(request)
        release=self.event('approval_consumed');original=json.loads(release['detail'])
        self.workflow.db.execute('UPDATE events SET detail=? WHERE sequence=?',
                                 (json.dumps(original|{'digest':'0'*64}),release['sequence']))
        self.assertEqual(self.outcome(request)['kind'],'unrecorded')
        self.workflow.db.execute('UPDATE events SET detail=? WHERE sequence=?',(release['detail'],release['sequence']))
        self.workflow.db.execute('UPDATE events SET actor=? WHERE kind=?',('human','file_deleted'))
        self.assertEqual(self.outcome(request)['kind'],'unrecorded')
        self.workflow.db.execute('DELETE FROM events WHERE sequence=?',(release['sequence'],))
        self.assertEqual(self.outcome(request)['kind'],'unrecorded')

    def test_nonmember_cannot_read_receipts_and_display_redacts_without_changing_source(self):
        secret='ghp_'+'x'*40
        request=self.workflow.ask_human(self.task,'writer','human','Confirm '+secret)
        self.workflow.respond(request,'human',answer='Reply '+secret)
        self.workflow.db.execute('UPDATE tasks SET title=?,evidence=? WHERE id=?',
            ('Title '+secret,json.dumps({'api_key':secret,'checks':{'independent':True}}),self.task))
        display=json.dumps(self.queries.task_detail(self.task,'human'))
        self.assertNotIn(secret,display)
        self.assertIn(secret,self.workflow.request(request,'human')['response'])
        self.assertIn(secret,self.workflow.task(self.task,'human')['evidence'])
        self.workflow.register_actor('outsider','human')
        with self.assertRaises(WorkflowError):self.queries.request_detail(request,'outsider')


class GitActionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.center=ControlCenter(Path(self.temporary.name)/'state')

    def tearDown(self):self.center.close();self.temporary.cleanup()

    def push(self,*,uncertain=False):
        self.center.run_scenario('git')
        request=next(r['id'] for r in self.center.requests(pending_only=True) if r['kind']=='approval')
        self.center.decide(request,True)
        if uncertain:
            def run(b):
                original=b.git._exec
                def interrupted(argv,env,seconds):
                    if 'push' in argv:
                        original(argv,env,seconds);return None,b'',b'','timeout'
                    return original(argv,env,seconds)
                with patch.object(b.git,'_exec',side_effect=interrupted):
                    return b.scheduler(b.root_of(b.queries.request_detail(request,b.human)['task'])).runner(
                        b.queries.request_detail(request,b.human)['task']).gateway.release_approved(request)
            with self.assertRaises(WorkflowError):self.center.call(run)
        else:self.center.release(request)
        operation=next(op for op in self.center.git_operations() if op['operation']=='push')
        return request,operation

    def test_git_uses_its_existing_operation_request_binding(self):
        request,operation=self.push()
        self.assertEqual(self.center.request_detail(request)['outcome']['kind'],'git_push_verified')
        arguments=operation['arguments']|{'request_id':'another-request'}
        self.center.call(lambda b:b.workflow.db.execute('UPDATE git_operations SET arguments=? WHERE id=?',
                        (json.dumps(arguments),operation['id'])))
        self.assertEqual(self.center.request_detail(request)['outcome']['kind'],'unrecorded')

    def test_git_uncertainty_remains_uncertain_after_observation_without_replay(self):
        request,operation=self.push(uncertain=True)
        self.assertEqual(self.center.request_detail(request)['outcome']['kind'],'git_push_uncertain')
        self.center.call(lambda b:b.git.reconcile(operation['id'],actor=b.human))
        self.assertEqual(self.center.request_detail(request)['outcome']['kind'],'git_push_uncertain')
        with self.assertRaises(WorkflowError):self.center.release(request)
        self.assertEqual(sum(op['operation']=='push' for op in self.center.git_operations()),1)

    def test_altered_git_event_or_backend_result_cannot_show_verified(self):
        request,operation=self.push()
        def alter(b):
            row=b.workflow.db.execute("SELECT * FROM events WHERE kind='git_push_verified'").fetchone()
            result=operation['result']|{'observed_remote':'0'*40}
            b.workflow.db.execute('UPDATE git_operations SET result=? WHERE id=?',(json.dumps(result),operation['id']))
            b.workflow.db.execute('UPDATE events SET detail=? WHERE sequence=?',
                                 (json.dumps({'operation_id':operation['id'],**result}),row['sequence']))
        self.center.call(alter)
        self.assertEqual(self.center.request_detail(request)['outcome']['kind'],'unrecorded')


if __name__=='__main__':unittest.main()
