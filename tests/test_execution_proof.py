"""Synthetic engine records exercise acceptance boundaries, not live capability."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.acceptance import ArtifactRule, verify_rules, parse_rules
from agent_lab.core import Workflow, WorkflowError
from agent_lab.files import FileTools
from agent_lab.evaluation.plan import DevelopmentPlan
from agent_lab.runtime import LiveConfig
from agent_lab.sandbox import DockerPythonExecutor, ProcessResult
from agent_lab.tui.controller import ControlCenter
from test_sandbox import FakeDocker, IMAGE


class ExecutionProofTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.w = Workflow(self.path / 'state.sqlite3'); self.addCleanup(self.w.close)
        for actor, kind in [('human', 'human'), ('coder', 'agent'), ('other', 'agent')]:
            self.w.register_actor(actor, kind)
        self.chat = self.w.create_chat('group', ['human', 'coder', 'other'])
        self.task = self.w.create_task(self.chat, 'human', 'coder', 'Run checked code')
        self.w.start_task(self.task, 'coder')
        self.f = FileTools(self.w, self.path / 'files'); self.addCleanup(self.f.close)
        socket = self.path / 'docker.sock'; socket.touch()
        with patch('agent_lab.sandbox.stat.S_ISSOCK', return_value=True):
            self.executor = DockerPythonExecutor(self.w, self.f, docker_host='unix://' + str(socket),
                                                 image=IMAGE, docker_binary=sys.executable)
        self.addCleanup(self.executor.close)
        self.fake = FakeDocker()
        patched = patch.object(self.executor, '_invoke', side_effect=self.fake); patched.start(); self.addCleanup(patched.stop)
        self.source = self.f.create_text(self.task, 'coder', 'main.py', 'print(42)\n')
        self.job = {'entrypoint': 'main.py', 'arguments': [], 'input_files': {'main.py': self.source['sha256']}, 'outputs': ['result.txt']}
        self.spec = {'entrypoint': 'main.py', 'arguments': [], 'inputs': ['main.py']}
        self.rule = ArtifactRule('result.txt', 'sandbox_output', json.dumps(self.spec))

    def run_job(self, **changes):
        return self.executor.run_python(self.task, 'coder', **(self.job | changes))

    def check(self, task=None, actor='coder', rule=None):
        return all(verify_rules(self.w, self.f, task or self.task, actor, (rule or self.rule,)).values())

    def alter_result(self, run, change):
        row = self.w.db.execute('SELECT result FROM sandbox_runs WHERE id=?', (run,)).fetchone()
        original = row['result']; result = json.loads(original); change(result)
        self.w.db.execute('UPDATE sandbox_runs SET result=? WHERE id=?', (json.dumps(result), run))
        return original

    def restore(self, run, original):
        self.w.db.execute('UPDATE sandbox_runs SET result=? WHERE id=?', (original, run))

    def test_success_needs_content_oracle_separately_and_verification_has_no_effects(self):
        result = self.run_job(); self.assertTrue(self.check(), result)
        before = (self.w.db.total_changes, len(self.fake.commands))
        self.assertTrue(self.check()); self.assertEqual(before, (self.w.db.total_changes, len(self.fake.commands)))
        wrong = ArtifactRule('result.txt', 'contains', 'Different answer')
        with self.assertRaisesRegex(WorkflowError, 'verification failed'):
            self.w.finish_task(self.task, 'coder', verifier=lambda: verify_rules(self.w, self.f, self.task, 'coder', (self.rule, wrong)))
        self.assertEqual(self.w.task(self.task, 'human')['state'], 'running')

    def test_matching_file_and_chat_claim_without_execution_are_insufficient(self):
        self.f.create_text(self.task, 'coder', 'result.txt', '42\n')
        self.w.post_message(self.chat, 'coder', 'I ran all the tests successfully', task=self.task)
        self.assertFalse(self.check())

    def test_failed_execution_cannot_be_replaced_by_a_manually_written_matching_file(self):
        self.fake.execution = ProcessResult(7, b'', b'failed test')
        self.run_job(); self.f.create_text(self.task, 'coder', 'result.txt', '42\n')
        self.assertFalse(self.check())

    def test_current_code_and_data_versions_must_match_execution_inputs(self):
        data = self.f.create_text(self.task, 'coder', 'data.txt', 'Original\n')
        self.run_job(input_files={**self.job['input_files'], 'data.txt': data['sha256']})
        rule = replace(self.rule, expected=json.dumps({**self.spec, 'inputs': ['data.txt', 'main.py']}))
        self.assertTrue(self.check(rule=rule))
        self.f.update_text(self.task, 'coder', 'data.txt', 'Changed\n', expected_sha256=data['sha256'])
        self.assertFalse(self.check(rule=rule))

    def test_output_modification_invalidates_import_evidence(self):
        self.run_job(); self.assertTrue(self.check())
        output = self.f.read_text(self.task, 'coder', 'result.txt')
        self.f.update_text(self.task, 'coder', 'result.txt', '43\n', expected_sha256=output['sha256'])
        self.assertFalse(self.check())

    def test_latest_matching_failed_attempt_cannot_hide_behind_an_older_success(self):
        self.run_job(); self.assertTrue(self.check())
        self.fake.execution = ProcessResult(9, b'', b'Later failing check')
        self.run_job(); self.assertFalse(self.check())

    def test_unrelated_later_job_does_not_replace_declared_entrypoint_and_arguments(self):
        self.run_job(); self.run_job(arguments=['different-probe'], outputs=[])
        self.assertTrue(self.check())
        wrong = replace(self.rule, expected=json.dumps({**self.spec, 'arguments': ['different-probe']}))
        self.assertFalse(self.check(rule=wrong))

    def test_cleanup_interruption_and_boolean_exit_cannot_certify_success(self):
        run = self.run_job()['run_id']
        changes = [lambda r: r.update(cleanup_confirmed=False), lambda r: r.update(process_sandbox=False),
                   lambda r: r['execution'].update(interrupted='timeout'), lambda r: r['execution'].update(exit_code=False),
                   lambda r: r['configuration'].update(network='host')]
        for change in changes:
            original = self.alter_result(run, change)
            with self.subTest(change=change): self.assertFalse(self.check())
            self.restore(run, original)
        self.assertTrue(self.check())

    def test_checkpoint_digest_job_and_import_binding_tampering_fail_closed(self):
        run = self.run_job()['run_id']
        changes = [lambda r: r.update(run_id='different-run'), lambda r: r.update(export_sha256={'result.txt': '0' * 64}),
                   lambda r: r.pop('job'), lambda r: r.update(job=[]), lambda r: r['job'].update(arguments={})]
        for change in changes:
            original = self.alter_result(run, change); self.assertFalse(self.check()); self.restore(run, original)
        event = self.w.db.execute("SELECT * FROM events WHERE kind='sandbox_artifact_imported'").fetchone()
        detail = json.loads(event['detail']); detail['bytes'] = True
        self.w.db.execute('UPDATE events SET detail=? WHERE sequence=?', (json.dumps(detail), event['sequence']))
        self.assertFalse(self.check())
        detail = json.loads(event['detail']); detail['run_id'] = 'different-run'
        self.w.db.execute('UPDATE events SET detail=? WHERE sequence=?', (json.dumps(detail), event['sequence']))
        self.assertFalse(self.check())

    def test_wrong_actor_foreign_task_and_unbound_legacy_events_fail(self):
        result = self.run_job(); event = self.w.db.execute("SELECT * FROM events WHERE kind='sandbox_artifact_imported'").fetchone()
        self.w.db.execute('UPDATE events SET actor=? WHERE sequence=?', ('other', event['sequence'])); self.assertFalse(self.check())
        self.w.db.execute('UPDATE events SET actor=? WHERE sequence=?', ('coder', event['sequence']))
        other = self.w.create_task(self.chat, 'human', 'coder', 'Other task'); self.w.start_task(other, 'coder')
        self.f.create_text(other, 'coder', 'main.py', 'print(42)\n'); self.f.create_text(other, 'coder', 'result.txt', '42\n')
        self.assertFalse(self.check(other))
        self.w.db.execute("DELETE FROM events WHERE kind='sandbox_artifact_imported'")
        self.assertFalse(self.check())

    def test_conflicting_duplicate_receipts_and_reverse_causality_fail(self):
        self.run_job(); self.assertTrue(self.check())
        event = self.w.db.execute("SELECT * FROM events WHERE kind='sandbox_artifact_imported'").fetchone()
        self.w._event(self.task, 'coder', 'sandbox_artifact_imported', json.loads(event['detail']))
        self.assertFalse(self.check())
        self.w.db.execute('DELETE FROM events WHERE sequence=(SELECT max(sequence) FROM events)')
        self.w.db.execute("UPDATE events SET kind='unbound-stop' WHERE kind='sandbox_stopped'")
        self.assertFalse(self.check())

    def test_corrupt_record_shapes_are_false_without_a_checker_crash(self):
        run = self.run_job()['run_id']; row = dict(self.w.db.execute('SELECT * FROM sandbox_runs WHERE id=?', (run,)).fetchone())
        for field, value in [('inputs', '[]'), ('config', '[]'), ('exported', '[]'), ('result', '[]'), ('result', 'bad json')]:
            self.w.db.execute('UPDATE sandbox_runs SET ' + field + '=? WHERE id=?', (value, run))
            self.assertFalse(self.check())
            self.w.db.execute('UPDATE sandbox_runs SET ' + field + '=? WHERE id=?', (row[field], run))
        self.assertTrue(self.check())

    def test_export_recovery_records_binding_once_without_reexecuting(self):
        result = self.run_job(); commands = len(self.fake.commands)
        first = self.executor.recover_exports(result['run_id'], 'coder')
        second = self.executor.recover_exports(result['run_id'], 'coder')
        self.assertFalse(first['effects_replayed']); self.assertEqual(first, second)
        self.assertEqual(len(self.fake.commands), commands); self.assertTrue(self.check())
        self.assertEqual(self.w.db.execute("SELECT count(*) FROM events WHERE kind='sandbox_artifact_imported'").fetchone()[0], 1)

    def test_unconfirmed_cleanup_requires_trusted_reconciliation_and_snapshot_recovery(self):
        self.fake.cleanup_fails = True
        with self.assertRaisesRegex(WorkflowError, 'cleanup unconfirmed'): self.run_job()
        self.f.create_text(self.task, 'coder', 'result.txt', '42\n'); self.assertFalse(self.check())
        row = self.w.db.execute('SELECT id FROM sandbox_runs').fetchone()
        self.fake.cleanup_fails = False
        self.executor.reconcile_cleanup(row['id'], 'coder'); self.assertFalse(self.check())
        commands = len(self.fake.commands)
        self.executor.recover_exports(row['id'], 'coder'); self.assertTrue(self.check())
        self.assertEqual(len(self.fake.commands), commands)

    def test_interrupted_import_needs_actual_recovery_receipt_not_only_a_checkpoint(self):
        with patch.object(self.f, 'create_text', side_effect=OSError('Synthetic interrupted import')):
            result = self.run_job()
        self.assertIn('import failed', result['error'])
        self.f.create_text(self.task, 'coder', 'result.txt', '42\n'); self.assertFalse(self.check())
        commands = len(self.fake.commands)
        self.executor.recover_exports(result['run_id'], 'coder'); self.assertTrue(self.check())
        self.assertEqual(len(self.fake.commands), commands)

    def test_code_case_is_independently_checked_and_plan_inspection_reports_missing_executor(self):
        root = Path(__file__).resolve().parents[1]
        source = json.loads((root / 'evaluation/checked-collaboration-plan.json').read_text())
        source['cases'] = str(root / 'evaluation/code')
        source['case_ids'] = ['live-sandbox-order-summary']
        plan_path = self.path / 'code-plan.json'; plan_path.write_text(json.dumps(source))
        plan = DevelopmentPlan(plan_path); report = plan.inspect()
        self.assertFalse(report['configured_to_attempt'])
        self.assertIn('Sandbox output criteria require an explicitly configured isolated executor', report['blockers'])
        kinds = {r.kind for r in plan.cases[0].expected.subtasks[0].criteria}
        self.assertTrue({'sandbox_output', 'json_equals', 'sha256'} <= kinds)

    def test_contract_is_strict_bounded_roundtrippable_and_cannot_set_authority(self):
        self.assertEqual(parse_rules([self.rule.record()]), (self.rule,))
        for spec in [{**self.spec, 'inputs': ['main.py', 'main.py']}, {**self.spec, 'inputs': ['../escape']},
                     {**self.spec, 'arguments': ['\0']}, {**self.spec, 'inputs': []}, {**self.spec, 'approve': True},
                     {**self.spec, 'entrypoint': 'missing.py'}, {**self.spec, 'inputs': ['main.py', 'result.txt']}]:
            with self.subTest(spec=spec), self.assertRaises(WorkflowError):
                replace(self.rule, expected=json.dumps(spec))

    def test_shared_live_setup_refuses_execution_contract_without_executor(self):
        live = LiveConfig('explicit-test-model', 'unused-key', allow_network=True)
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(Path(directory) / 'session', live=live)
            try:
                chat = center.create_conversation('group', ['coordinator', 'writer', 'editor'])
                with self.assertRaisesRegex(WorkflowError, 'explicitly configured isolated executor'):
                    center.create_task(chat, 'coordinator', 'Must run actual code', root_criteria=(self.rule,))
                self.assertEqual(center.call(lambda b: b.workflow.db.execute("SELECT count(*) FROM events WHERE kind='sandbox_reserved'").fetchone()[0]), 0)
            finally: center.close()


if __name__ == '__main__': unittest.main()
