"""Inspect without access; execute only the reviewed bounded conditions."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.core import WorkflowError
from agent_lab.deepseek import DeepSeekHTTP
from agent_lab.evaluation.plan import DevelopmentPlan
from agent_lab.evaluation.__main__ import main

SOURCE=Path(__file__).resolve().parents[1]/'evaluation/development-plan.json'


class DevelopmentPlanTests(unittest.TestCase):
    def test_inspection_never_calls_model_or_exposes_secret(self):
        with patch.dict('os.environ',{'COURSE_DEEPSEEK_API_KEY':'secret-never-serialized'},clear=True), \
             patch.object(DeepSeekHTTP,'__call__',side_effect=AssertionError('No model request')) as call:
            planned=DevelopmentPlan(SOURCE); report=planned.inspect()
            self.assertEqual(report['maximum_model_attempts'],48)
            self.assertFalse(report['configured_to_attempt'])  # model still unissued
            self.assertNotIn('secret-never-serialized',json.dumps(report))
            self.assertNotIn('secret-never-serialized',json.dumps(planned.conditions))
            call.assert_not_called()

    def plan_file(self,path,**changes):
        data=json.loads(SOURCE.read_text());data.update(changes)
        data['cases']=str(SOURCE.parent/'connection')
        target=path/'plan.json';target.write_text(json.dumps(data));return target

    def test_key_presence_does_not_change_review_fingerprint(self):
        with patch.dict('os.environ',{},clear=True): a=DevelopmentPlan(SOURCE)
        with patch.dict('os.environ',{'COURSE_DEEPSEEK_API_KEY':'different'},clear=True): b=DevelopmentPlan(SOURCE)
        self.assertEqual(a.sha256,b.sha256)

    def test_scoped_search_plan_binds_roles_and_requires_web_access(self):
        source = SOURCE.with_name('search-source-plan.json')
        planned = DevelopmentPlan(source)
        self.assertTrue(planned.settings['enable_python_docs_search'])
        self.assertIn('site:docs.python.org <module>', planned.inspect()['scoped_search'])
        self.assertIn('site:docs.python.org <module>', planned.conditions['roles']['coordinator']['instructions'])
        with tempfile.TemporaryDirectory() as temp:
            data = json.loads(source.read_text())
            data['cases'] = str(source.parent / data['cases'])
            data['capabilities']['web'] = False
            path = Path(temp) / 'plan.json'
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(WorkflowError, 'requires explicit public web access'):
                DevelopmentPlan(path)

    def test_unissued_missing_permission_and_stale_plan_cannot_execute(self):
        with tempfile.TemporaryDirectory() as temp:
            planned=DevelopmentPlan(SOURCE)
            with patch('agent_lab.evaluation.plan.Evaluator') as evaluator:
                for permission,sha in ((False,planned.sha256),(True,'0'*64),(True,planned.sha256)):
                    with self.assertRaises(WorkflowError):
                        planned.execute(allow_model_calls=permission,plan_sha256=sha,output_root=Path(temp)/'runs')
                evaluator.assert_not_called()
                self.assertFalse((Path(temp)/'runs').exists())

    def test_interrupted_execution_preserves_reviewed_plan_and_completed_outcomes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); filename=self.plan_file(root,model='explicit-issued-model')
            output=root/'runs'
            with patch.dict('os.environ',{'COURSE_DEEPSEEK_API_KEY':'issued-secret'},clear=True), \
                 patch('agent_lab.evaluation.harness._drive_live') as driver:
                planned=DevelopmentPlan(filename)
                selected = [case.id for case in planned.cases]
                observations = []

                def interrupt(case, session, live):
                    run = next(output.iterdir())
                    snapshot = run / 'development-plan.json'
                    progress = run / 'run-progress.json'
                    observations.append((live.model, live.allow_network,
                                         snapshot.read_text() if snapshot.exists() else None,
                                         progress.read_text() if progress.exists() else None))
                    if case.id == selected[0]:
                        raise RuntimeError('injected driver failure')
                    raise KeyboardInterrupt

                driver.side_effect = interrupt
                with self.assertRaises(KeyboardInterrupt):
                    planned.execute(allow_model_calls=True,plan_sha256=planned.sha256,output_root=output)

            self.assertEqual(len(observations), len(selected))
            for index, (model, network, snapshot, checkpoint) in enumerate(observations):
                self.assertEqual((model, network), ('explicit-issued-model', True))
                self.assertIsNotNone(snapshot)
                self.assertEqual(json.loads(snapshot)['plan_sha256'], planned.sha256)
                self.assertNotIn('issued-secret', snapshot)
                self.assertIsNotNone(checkpoint)
                progress = json.loads(checkpoint)
                self.assertEqual(progress['active_case_id'], selected[index])
                self.assertEqual(progress['not_started_case_ids'], selected[index + 1:])
                self.assertNotIn('issued-secret', checkpoint)
            run = next(output.iterdir())
            progress = json.loads((run / 'run-progress.json').read_text())
            self.assertEqual(progress['status'], 'incomplete')
            self.assertEqual(progress['selected_case_ids'], selected)
            self.assertEqual(progress['active_case_id'], selected[1])
            self.assertEqual(progress['not_started_case_ids'], [])
            self.assertEqual([(r['case']['id'], r['classification']) for r in progress['results']],
                             [(selected[0], 'driver_error')])
            self.assertFalse((run / 'results.json').exists())

    def test_budget_change_changes_fingerprint_and_hkgai_has_no_provider_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); original=DevelopmentPlan(SOURCE)
            data=json.loads(SOURCE.read_text());data['tree_limits']['model_attempts']=12
            path=self.plan_file(root,tree_limits=data['tree_limits'],provider='hkgai',model='issued-hkgai')
            planned=DevelopmentPlan(path)
            self.assertNotEqual(original.sha256,planned.sha256)
            self.assertEqual(planned.settings['provider'], 'hkgai')
            with patch.dict('os.environ',{},clear=True),self.assertRaises(WorkflowError):
                planned.execute(allow_model_calls=True,plan_sha256=planned.sha256,output_root=root/'runs')

    def test_unknown_secret_field_empty_selection_and_memory_label_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            caps=json.loads(SOURCE.read_text())['capabilities'];caps['memory']=True
            for changes in ({'api_key':'literal-secret'},{'case_ids':[]},{'purpose':'official'},
                            {'capabilities':caps},{'task_limits':{}},{'case_ids':['missing-case']}):
                with self.assertRaises(WorkflowError): DevelopmentPlan(self.plan_file(root,**changes))

    def test_cli_inspects_without_creating_run_state(self):
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):
            self.assertEqual(main(['plan','--config',str(SOURCE)]),0)
        self.assertEqual(json.loads(stream.getvalue())['model_calls'],0)


if __name__=='__main__':unittest.main()
