"""D02 CLI human round trips; all provider turns are explicitly scripted.

Every command opens/closes the real service and SQLite state. File effects and
independent acceptance are real; no live-model performance follows from this.
"""

import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.console import main
from agent_lab.deepseek import DeepSeekHTTP
from agent_lab.runtime import LiveConfig
from agent_lab.tui.controller import ControlCenter
from test_runner import Script, response, tool


class ConsoleInteractionTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.state=self.root/'state'
        self.environment=patch.dict('os.environ',{'D02_TEST_KEY':'unused-fixture-key'},clear=True)
        self.environment.start();self.addCleanup(self.environment.stop)
        network=patch.object(DeepSeekHTTP,'__call__',side_effect=AssertionError('Real provider calls are forbidden in these checks'))
        network.start();self.addCleanup(network.stop)
        self.live=['--live','--model','explicit-test-model','--api-key-env','D02_TEST_KEY','--enable-delete']

    def command(self,*arguments,live=False,human='operator',fails=False):
        stdout,stderr=io.StringIO(),io.StringIO()
        prefix=['--state-dir',str(self.state),'--human',human]+(self.live if live else [])
        with contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
            if fails:
                with self.assertRaises(SystemExit) as raised:main(prefix+list(arguments))
                self.assertNotEqual(raised.exception.code,0)
                return stderr.getvalue()
            self.assertEqual(main(prefix+list(arguments)),0)
        return json.loads(stdout.getvalue())

    def backend(self,function):
        center=ControlCenter(self.state,live=LiveConfig('explicit-test-model','unused-fixture-key',allow_network=True,enable_delete=True))
        try:return center.call(function)
        finally:center.close()

    def private_task(self,*,policy=None):
        chat=self.command('chat','new','--kind','private','--participant','writer')['chat']
        args=['new','--chat',chat,'--assignee','writer','--goal','Produce checked text after human clarification']
        if policy is not None:
            path=self.root/'policy.json';path.write_text(json.dumps(policy))
            args+=['--policy',str(path)]
        return chat,self.command(*args,live=True)['task']

    def pending_approval(self):
        chat,task=self.private_task(policy={'criteria':[{'path':'scratch.txt','kind':'absent'}]})
        content='Disposable fixture\n'
        script=Script([response([tool('create_text',{'path':'scratch.txt','content':content},'create')]),
                       response([tool('delete_text',{'path':'scratch.txt','expected_sha256':hashlib.sha256(content.encode()).hexdigest()},'delete')]),
                       response()])
        with patch.object(DeepSeekHTTP,'__call__',side_effect=script):self.command('advance',task,live=True)
        request=self.command('requests','--pending')[0]['id']
        return chat,task,request,script

    def test_private_group_messages_and_agent_assignment_survive_separate_commands(self):
        with patch.object(DeepSeekHTTP,'__call__',side_effect=AssertionError('No implicit calls')) as http:
            private=self.command('chat','new','--kind','private','--participant','writer')['chat']
            group=self.command('chat','new','--kind','group','--participant','coordinator','--participant','writer')['chat']
            self.command('message',private,'PRIVATE_REFERENCE')
            self.command('message',group,'GROUP_REFERENCE')
            conversations={c['id']:c for c in self.command('chat','list')}
            self.assertEqual(conversations[private]['kind'],'private')
            self.assertEqual(conversations[group]['kind'],'group')
            self.assertNotIn('PRIVATE_REFERENCE',json.dumps(self.command('chat','feed',group)))
            self.assertNotIn('GROUP_REFERENCE',json.dumps(self.command('chat','feed',private)))
            self.assertEqual(self.command('status')['tasks'],[])
            task=self.command('new','--chat',private,'--assignee','writer','--goal','A real pending goal')['task']
            detail=self.command('status','--task',task)
            self.assertEqual((detail['task']['assignee'],detail['task']['state']),('writer','pending'))
            self.command('advance',task,fails=True)
            http.assert_not_called()

    def test_invalid_private_members_and_wrong_task_assignee_do_not_create_tasks(self):
        self.command('new','--assignee','unknown-actor','--goal','Invalid default assignment',fails=True)
        self.assertEqual(self.command('chat','list'),[])
        self.command('chat','new','--kind','private','--participant','writer','--participant','editor',fails=True)
        self.command('chat','new','--kind','private','--participant','unknown-actor',fails=True)
        self.assertEqual(self.command('chat','list'),[])
        chat=self.command('chat','new','--kind','private','--participant','writer')['chat']
        self.command('new','--chat',chat,'--assignee','editor','--goal','Wrong member',fails=True)
        self.command('new','--chat',chat,'--assignee','operator','--goal','Not an agent',fails=True)
        self.assertEqual(self.command('status')['tasks'],[])

    def test_nonmember_cannot_read_private_feed_task_or_request(self):
        chat,task,request,_=self.pending_approval()
        self.command('chat','feed',chat,human='outsider',fails=True)
        self.command('status','--task',task,human='outsider',fails=True)
        self.command('requests','--request',request,human='outsider',fails=True)
        self.assertEqual(self.command('chat','list',human='outsider'),[])
        self.assertEqual(self.command('requests','--pending',human='outsider'),[])

    def test_clarification_then_exact_approval_release_and_verified_output(self):
        chat,task=self.private_task(policy={'artifacts':{'note.txt':'Confirmed\n'},
            'criteria':[{'path':'scratch.txt','kind':'absent'}],'constraints':['Keep the user constraint']})
        group=self.command('chat','new','--kind','group','--participant','coordinator','--participant','writer')['chat']
        scratch='Disposable fixture\n'
        script=Script([
            response([tool('post_message',{'body':'A private agent clarification'},'agent-message'),
                      tool('ask_human',{'prompt':'Confirm the required text'},'clarify')]),
            response([tool('create_text',{'path':'note.txt','content':'Confirmed\n'},'note'),
                      tool('create_text',{'path':'scratch.txt','content':scratch},'scratch')]),
            response([tool('delete_text',{'path':'scratch.txt','expected_sha256':hashlib.sha256(scratch.encode()).hexdigest()},'delete')]),
            response(text='Scripted final proposal; independent checks decide'),
        ])
        with patch.object(DeepSeekHTTP,'__call__',side_effect=script):
            self.command('advance',task,live=True)
            self.assertIn('A private agent clarification',json.dumps(self.command('chat','feed',chat)))
            self.assertNotIn('A private agent clarification',json.dumps(self.command('chat','feed',group)))
            clarification=self.command('requests','--pending')[0]
            self.assertEqual(clarification['kind'],'clarification')
            self.command('decide',clarification['id'],'approve',fails=True)
            self.command('message',chat,'This message is not an answer or approval')
            self.assertEqual(self.command('requests','--request',clarification['id'])['status'],'pending')
            self.command('answer',clarification['id'],'Confirmed',live=True)
            self.command('answer',clarification['id'],'Duplicate',fails=True)
            self.command('advance',task,live=True)
            approval=self.command('requests','--pending')[0]
            self.assertEqual(approval['kind'],'approval')
            self.command('answer',approval['id'],'Yes',fails=True)
            self.command('release',approval['id'],live=True,fails=True)
            self.command('decide',approval['id'],'approve',live=True)
            granted=self.command('requests','--request',approval['id'])
            self.assertEqual(granted['status'],'granted_awaiting_release')
            self.assertIsNone(granted['outcome'])
            self.assertEqual(self.backend(lambda b:b.inspector.read_file(task,b.human,'scratch.txt'))['content'],scratch)
            attempts=len(script.requests)
            self.command('advance',task,live=True)
            self.assertEqual(len(script.requests),attempts)
            self.command('release',approval['id'],live=True)
            released=self.command('requests','--request',approval['id'])
            self.assertEqual((released['status'],released['outcome']['kind']),('released','file_deleted'))
            self.command('release',approval['id'],live=True,fails=True)
            self.command('advance',task,live=True)
        detail=self.command('status','--task',task)
        self.assertEqual(detail['task']['state'],'succeeded')
        self.assertTrue(all(detail['task']['evidence']['checks'].values()))
        self.assertIn('Keep the user constraint',json.dumps(script.requests[-1]))
        self.assertIn('Confirmed',json.dumps(script.requests[1]))
        self.assertFalse(list((self.state/'files/tasks').rglob('scratch.txt')))

    def test_denial_remains_cancelled_after_reopening_cli(self):
        _,task,request,_=self.pending_approval()
        self.command('decide',request,'deny')
        with patch.object(DeepSeekHTTP,'__call__',side_effect=AssertionError('Denied work must stop')) as http:
            self.command('advance',task,live=True)
            self.command('release',request,live=True,fails=True)
            http.assert_not_called()
        request=self.command('requests','--request',request)
        self.assertEqual((request['status'],request['task_state']),('denied','cancelled'))
        self.assertTrue(list((self.state/'files/tasks').rglob('scratch.txt')))

    def test_changed_file_is_unverified_not_successful_and_cannot_replay(self):
        _,task,request,_=self.pending_approval()
        self.command('decide',request,'approve')
        def change(b):
            current=b.files.read_text(task,'writer','scratch.txt')
            b.files.update_text(task,'writer','scratch.txt','Changed\n',expected_sha256=current['sha256'])
        self.backend(change)
        self.assertIn('reconcile',self.command('release',request,live=True,fails=True))
        recorded=self.command('requests','--request',request)
        self.assertEqual((recorded['status'],recorded['outcome']['kind']),('released','unrecorded'))
        self.command('release',request,live=True,fails=True)
        self.assertEqual(self.backend(lambda b:b.inspector.read_file(task,b.human,'scratch.txt'))['content'],'Changed\n')
        self.assertNotEqual(self.command('status','--task',task)['task']['state'],'succeeded')

    def test_non_addressed_group_human_cannot_answer_and_pending_filter_is_personal(self):
        self.command('status',human='second-human')  # Trusted local operator registers this identity.
        chat=self.command('chat','new','--kind','group','--participant','writer','--participant','second-human')['chat']
        task=self.command('new','--chat',chat,'--assignee','writer','--goal','Clarify first',live=True)['task']
        script=Script([response([tool('ask_human',{'prompt':'Confirm the scope'},'ask')])])
        with patch.object(DeepSeekHTTP,'__call__',side_effect=script):self.command('advance',task,live=True)
        request=self.command('requests','--pending')[0]['id']
        self.assertEqual(self.command('requests','--pending',human='second-human'),[])
        self.assertIn('addressed human',self.command('answer',request,'Wrong responder',human='second-human',fails=True))
        self.assertEqual(self.command('requests','--request',request)['status'],'pending')
        self.command('answer',request,'Correct responder')

    def test_trusted_review_records_feedback_and_acceptance_without_faking_checks(self):
        _,task=self.private_task()
        script=Script([response(),response()])
        with patch.object(DeepSeekHTTP,'__call__',side_effect=script):
            self.command('advance',task,live=True)
            self.assertEqual(self.command('status','--task',task)['runner']['status'],'awaiting_verification')
            self.command('review',task,'reject','--feedback','Explain the missing evidence',live=True)
            self.command('advance',task,live=True)
        self.assertIn('Explain the missing evidence',json.dumps(script.requests[-1]))
        self.command('review',task,'accept',live=True)
        detail=self.command('status','--task',task)
        self.assertEqual(detail['task']['state'],'succeeded')
        self.assertEqual(detail['task']['evidence']['checks'],{'human_review_accepted':True})
        self.command('review',task,'accept',live=True,fails=True)

    def test_request_filters_reject_ambiguous_input_before_creating_state(self):
        self.command('requests','--pending','--request','unknown',fails=True)
        self.assertFalse(self.state.exists())

    def test_separate_python_processes_reopen_the_same_private_chat_and_task(self):
        state=self.root/'process-state'
        def invoke(*arguments):
            result=subprocess.run([sys.executable,'-m','agent_lab.console','--state-dir',str(state),*arguments],
                cwd=Path(__file__).resolve().parents[1],text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            return json.loads(result.stdout)
        chat=invoke('chat','new','--kind','private','--participant','writer')['chat']
        invoke('message',chat,'A persisted private message')
        task=invoke('new','--chat',chat,'--assignee','writer','--goal','A pending goal')['task']
        self.assertEqual(invoke('status','--task',task)['task']['state'],'pending')
        self.assertIn('A persisted private message',json.dumps(invoke('chat','feed',chat)))
        self.assertEqual(invoke('requests','--pending'),[])


if __name__=='__main__':unittest.main()
