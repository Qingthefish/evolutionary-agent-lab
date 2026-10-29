"""Exact-version repair of task-owned exports; simulated engine, no model calls."""
import json
import unittest
from unittest.mock import patch

from agent_lab.core import WorkflowError
from agent_lab.gateway import ToolGateway
from agent_lab.sandbox import ProcessResult
import test_execution_proof as fixture
from test_runner import tool


class SandboxReplacementTests(unittest.TestCase):
    setUp = fixture.ExecutionProofTests.setUp
    run_job = fixture.ExecutionProofTests.run_job
    check = fixture.ExecutionProofTests.check

    def prepare(self):
        first = self.run_job()
        old = self.f.read_text(self.task,'coder','result.txt')
        code = self.f.update_text(self.task,'coder','main.py','print(43)\n',expected_sha256=self.source['sha256'])
        self.job['input_files']['main.py'] = code['sha256']
        self.fake.exports = {'result.txt':'43\n'}
        return first,old

    def gateway(self, update=True):
        return ToolGateway(self.w,self.f,self.task,'coder',human='human',executor=self.executor,
            allowed=('run_python','create_text','update_text') if update else ('run_python','create_text'))

    def test_old_call_shape_and_optional_schema_are_preserved(self):
        gateway = self.gateway(); spec = next(s['function']['parameters'] for s in gateway.tools() if s['function']['name']=='run_python')
        self.assertIn('replace_outputs',spec['properties']);self.assertNotIn('replace_outputs',spec['required'])
        before=len(self.fake.commands);gateway.validate_batch([tool('run_python',self.job)])
        self.assertEqual(before,len(self.fake.commands))
        self.assertTrue(json.loads(gateway.dispatch(tool('run_python',self.job))['content'])['ok'])
        self.assertTrue(self.check())

    def test_missing_entrypoint_gives_actionable_feedback_before_any_batch_effect(self):
        data = self.f.create_text(self.task, 'coder', 'data.txt', 'Input\n')
        args = {**self.job, 'input_files': {'data.txt': data['sha256']}}
        gateway = self.gateway(); before = (self.w.db.total_changes, len(self.fake.commands))
        with self.assertRaisesRegex(WorkflowError, 'Include the entrypoint script in input_files'):
            gateway.validate_batch([tool('create_text', {'path': 'never.txt', 'content': 'No effect'}, 'first'),
                                    tool('run_python', args, 'second')])
        self.assertEqual(before, (self.w.db.total_changes, len(self.fake.commands)))
        with self.assertRaisesRegex(WorkflowError, 'no execution started'):
            self.executor.run_python(self.task, 'coder', **args)
        self.assertEqual(before, (self.w.db.total_changes, len(self.fake.commands)))
        self.assertEqual(self.w.db.execute('SELECT count(*) FROM sandbox_runs').fetchone()[0], 0)
        self.assertEqual(self.w.db.execute('SELECT count(*) FROM tool_calls').fetchone()[0], 0)

    def test_delivery_guidance_names_owned_imports_without_creating_an_offer(self):
        gateway = self.gateway()
        result = json.loads(gateway.dispatch(tool('run_python', self.job))['content'])['result']
        self.assertEqual(result['output_delivery'], {'kind': 'current_task_import_receipts',
            'task_id': self.task, 'requires_accept_artifact': False})
        self.assertEqual([r['path'] for r in result['artifacts']], ['result.txt'])
        self.assertEqual(result['artifacts'][0]['sha256'], self.f.read_text(self.task, 'coder', 'result.txt')['sha256'])
        self.assertEqual(self.w.db.execute('SELECT count(*) FROM artifacts').fetchone()[0], 0)
        stored = json.loads(self.w.db.execute('SELECT result FROM sandbox_runs WHERE id=?', (result['run_id'],)).fetchone()[0])
        self.assertNotIn('output_delivery', stored)  # Guidance cannot become execution proof.
        self.assertTrue(self.check())

    def test_failed_execution_does_not_claim_output_delivery(self):
        self.fake.execution = ProcessResult(9, b'', b'Actual failed check')
        result = json.loads(self.gateway().dispatch(tool('run_python', self.job))['content'])['result']
        self.assertEqual(result['execution']['exit_code'], 9)
        self.assertEqual(result['artifacts'], [])
        self.assertNotIn('output_delivery', result)
        self.assertEqual(self.w.db.execute('SELECT count(*) FROM artifacts').fetchone()[0], 0)
        self.assertFalse(self.check())

    def test_partial_import_guidance_cannot_invent_receipts_for_missing_outputs(self):
        self.fake.exports = {'result.txt': '42\n', 'other.txt': 'Other\n'}
        original = self.f.create_text
        def interrupted(task, actor, path, content):
            if path == 'other.txt': raise OSError('Synthetic second import interruption')
            return original(task, actor, path, content)
        with patch.object(self.f, 'create_text', side_effect=interrupted):
            result = json.loads(self.gateway().dispatch(tool('run_python', {
                **self.job, 'outputs': ['result.txt', 'other.txt']}))['content'])['result']
        self.assertIn('import failed', result['error'])
        self.assertEqual([r['path'] for r in result['artifacts']], ['result.txt'])
        self.assertEqual(result['output_delivery']['task_id'], self.task)
        self.assertEqual(self.w.db.execute('SELECT count(*) FROM artifacts').fetchone()[0], 0)
        with self.assertRaises(WorkflowError): self.f.read_text(self.task, 'coder', 'other.txt')

    def test_checked_repair_updates_exact_version_and_binds_a_new_run(self):
        first,old=self.prepare();gateway=self.gateway()
        args={**self.job,'replace_outputs':{'result.txt':old['sha256']}}
        before=(self.w.db.total_changes,len(self.fake.commands));gateway.validate_batch([tool('run_python',args)])
        self.assertEqual(before,(self.w.db.total_changes,len(self.fake.commands)))
        result=json.loads(gateway.dispatch(tool('run_python',args))['content'])['result']
        self.assertNotEqual(first['run_id'],result['run_id'])
        self.assertEqual(self.f.read_text(self.task,'coder','result.txt')['content'],'43\n');self.assertTrue(self.check())
        self.assertEqual(self.w.db.execute('SELECT count(*) FROM sandbox_runs').fetchone()[0],2)
        self.assertEqual(self.w.db.execute("SELECT count(*) FROM events WHERE kind='sandbox_artifact_imported'").fetchone()[0],2)

    def test_stale_missing_or_foreign_version_rejected_before_batch_effects(self):
        _,old=self.prepare();gateway=self.gateway();before=(self.w.db.total_changes,len(self.fake.commands))
        for values in ({'result.txt':'0'*64},{'missing.txt':old['sha256']}):
            args={**self.job,'replace_outputs':values,'outputs':list(values)}
            with self.assertRaises(WorkflowError):
                gateway.validate_batch([tool('create_text',{'path':'never.txt','content':'no side effect'},'write'),tool('run_python',args)])
            self.assertEqual(before,(self.w.db.total_changes,len(self.fake.commands)))
        with self.assertRaises(WorkflowError):self.executor.validate_replacements(self.task,'other',{'result.txt':old['sha256']})

    def test_run_capability_does_not_grant_update_capability(self):
        _,old=self.prepare();before=len(self.fake.commands)
        with self.assertRaisesRegex(WorkflowError,'update_text capability'):
            self.gateway(False).dispatch(tool('run_python',{**self.job,'replace_outputs':{'result.txt':old['sha256']}}))
        self.assertEqual(before,len(self.fake.commands))

    def test_failed_process_cannot_replace_old_output(self):
        _,old=self.prepare();self.fake.execution=ProcessResult(9,b'',b'failed check')
        result=self.run_job(replace_outputs={'result.txt':old['sha256']})
        self.assertEqual(result['execution']['exit_code'],9)
        self.assertEqual(self.f.read_text(self.task,'coder','result.txt')['sha256'],old['sha256']);self.assertFalse(self.check())

    def test_concurrent_file_change_prevents_import_and_recovery(self):
        _,old=self.prepare();original=self.executor._invoke
        def changed(args,**kwargs):
            result=original(args,**kwargs)
            if args[:2]==['container','exec'] and '65533:65533' in args:
                self.f.update_text(self.task,'coder','result.txt','Intervening edit\n',expected_sha256=old['sha256'])
            return result
        with patch.object(self.executor,'_invoke',side_effect=changed):result=self.run_job(replace_outputs={'result.txt':old['sha256']})
        self.assertIn('import failed',result['error']);self.assertFalse(self.check())
        self.assertEqual(self.f.read_text(self.task,'coder','result.txt')['content'],'Intervening edit\n')
        with self.assertRaises(WorkflowError):self.executor.recover_exports(result['run_id'],'coder')

    def test_interrupted_replacement_recovers_without_executing_or_rewriting_other_versions(self):
        _,old=self.prepare()
        with patch.object(self.f,'update_text',side_effect=OSError('Synthetic interrupted import')):
            result=self.run_job(replace_outputs={'result.txt':old['sha256']})
        before=len(self.fake.commands)
        self.assertFalse(self.executor.recover_exports(result['run_id'],'coder')['effects_replayed'])
        self.assertEqual(before,len(self.fake.commands));self.assertTrue(self.check())
        self.assertEqual(self.f.read_text(self.task,'coder','result.txt')['content'],'43\n')
        self.executor.recover_exports(result['run_id'],'coder');self.assertEqual(before,len(self.fake.commands))

    def test_invalid_replacement_map_cannot_expand_export_or_input_scope(self):
        for replacements in ([],{'main.py':self.source['sha256']},{'result.txt':False},{'../escape':'0'*64}):
            with self.subTest(replacements=replacements),self.assertRaises(WorkflowError):self.run_job(replace_outputs=replacements)


if __name__=='__main__':unittest.main()
