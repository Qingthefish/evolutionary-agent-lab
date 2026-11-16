"""Paired effect descriptions and evidence regressions; all execution is scripted."""

import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.evaluation.experience import compare_experience
from agent_lab.evaluation.experience_effect import analyze_experience, main, read_experience, MAX_BYTES
from agent_lab.evaluation.experience_fixture import run_fixture
from agent_lab.evaluation.experience_fixture import ExperienceFixtureDriver
from agent_lab.evaluation.experience import ExperiencePlan, ExperienceTrial
from agent_lab.evaluation.manifest import digest
from agent_lab.runtime import LiveConfig
from agent_lab.deepseek import DeepSeekClient

ROOT = Path(__file__).resolve().parents[1]


class ExperienceEffectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared = tempfile.TemporaryDirectory()
        cls.original = run_fixture(ROOT/'evaluation/memory-plan.json', cls.shared.name)

    @classmethod
    def tearDownClass(cls):
        cls.shared.cleanup()

    def setUp(self):
        self.report = copy.deepcopy(self.original)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def row(self, arm, replicate=0, case='memory-probe-a'):
        return next(row for row in self.report['results'] if row['phase']=='probe'
                    and row['replicate']==replicate and row['memory']==arm and row['case']['id']==case)

    def fail(self, row):
        row.update(classification='task_failed')
        row['checks']['final_state'] = False
        workflow = row['workflow']
        workflow.update(root_state='failed', task_states={'failed':1}, evidence={'error':'Scripted failure'})
        root = next(task for task in workflow['task_outcomes'] if task['parent'] is None)
        root.update(state='failed', verified_success=False)
        for use in row['memory_use']['uses']:
            if use['task'] == root['task_id']:
                use['outcome'] = 'failed'

    def write(self):
        path = self.directory/'experiment.json'
        path.write_text(json.dumps(self.report))
        return path

    def test_real_offline_fixture_exposes_overhead_without_learning_claim(self):
        result = analyze_experience(self.report)
        self.assertEqual(result['status'], 'engineering_only', result)
        self.assertEqual(result['evidence_class'], 'offline_fixture')
        self.assertFalse(result['learning_improvement_established'])
        self.assertFalse(result['benchmark_valid'])
        self.assertFalse(result['authenticity_verified'])
        self.assertEqual(result['model_calls'], 0)
        self.assertEqual(result['outcomes'], {'planned_pairs':4, 'on_only_success':0,
                                             'off_only_success':0, 'both_succeeded':4, 'neither_succeeded':0})
        self.assertTrue(all(pair['on_minus_off']['reserved_model_attempts'] == 2 for pair in result['pairs']))
        self.assertEqual(result['comparison']['training']['planned'], 4)
        self.assertEqual(result['comparison']['training']['goals_completed'], 2)

    def test_pairs_follow_case_and_replicate_in_counterbalanced_order(self):
        result = analyze_experience(self.report)
        self.assertEqual([(p['replicate'],p['case_id']) for p in result['pairs']],
                         [(0,'memory-probe-a'),(0,'memory-probe-b'),(1,'memory-probe-a'),(1,'memory-probe-b')])
        for pair in result['pairs']:
            self.assertEqual(pair['on']['selected_lesson_task_pairs'], 1)
            self.assertEqual(pair['off']['selected_lesson_task_pairs'], 0)

    def test_benefit_regression_and_failures_remain_in_planned_denominator(self):
        self.fail(self.row('off'))
        self.fail(self.row('on',case='memory-probe-b'))
        self.fail(self.row('on',replicate=1))
        self.fail(self.row('off',replicate=1))
        result = analyze_experience(self.report)
        self.assertEqual(result['outcomes'], {'planned_pairs':4, 'on_only_success':1,
                                             'off_only_success':1, 'both_succeeded':1, 'neither_succeeded':1})
        self.assertEqual(result['comparison']['probes']['on']['goal_completion_rate'], .5)
        for pair in result['pairs']:
            if pair['outcome'] != 'both_succeeded':
                self.assertIsNone(pair['on_minus_off']['successful_goal_final_seconds'])
        failed = next(pair for pair in result['pairs'] if pair['outcome']=='off_only_success')
        self.assertIn('on_selected_but_root_not_completed',failed['diagnostics'])

    def test_timing_delta_has_explicit_direction_and_requires_both_successes(self):
        for arm, seconds in [('on',12.0),('off',10.0)]:
            workflow = self.row(arm)['workflow']
            workflow['workflow_elapsed_seconds'] = seconds
            workflow['task_outcomes'][0].update(elapsed_seconds=seconds,final_duration_seconds=seconds)
        result = analyze_experience(self.report)
        self.assertEqual(result['pairs'][0]['on_minus_off']['successful_goal_final_seconds'],2.0)
        self.assertIn('on_slower_successful_pair',result['pairs'][0]['diagnostics'])

    def test_partial_usage_cannot_produce_token_saving(self):
        self.row('off')['usage']['unknown_usage_attempts'] = 1
        pair = analyze_experience(self.report)['pairs'][0]
        self.assertIsNone(pair['on_minus_off']['reported_tokens'])
        self.assertIn('partial_provider_usage', pair['diagnostics'])
        self.assertEqual(pair['off']['unknown_usage_attempts'],1)

    def test_retrieval_is_a_candidate_count_not_a_search_call_count(self):
        pair = analyze_experience(self.report)['pairs'][0]
        # One scripted search returns multiple candidates from training.
        self.assertGreater(pair['on']['retrieved_candidate_records'],1)
        self.assertNotIn('search_calls',pair['on'])

    def test_retrieval_without_selection_is_not_evidence_of_adoption(self):
        use = self.row('on')['memory_use']
        use.update(selections=0,assessed=0,uses=[])
        pair = analyze_experience(self.report)['pairs'][0]
        self.assertIn('on_retrieved_without_selection',pair['diagnostics'])
        self.assertIn('on_success_without_selection',pair['diagnostics'])

    def test_missing_inputs_or_changed_inputs_refuse_comparison(self):
        for mutation in ({'input.txt':'new data'}, {'input.txt':'different data'}):
            with self.subTest(inputs=mutation):
                self.report = copy.deepcopy(self.original)
                self.row('on')['case']['inputs'] = mutation
                self.assertEqual(compare_experience(self.report)['status'],'not_comparable')
                self.assertEqual(analyze_experience(self.report)['pairs'],[])

    def test_matching_supplied_inputs_are_accepted_but_omission_is_not(self):
        definition = next(c for c in self.report['conditions']['runtime']['cases'] if c['id']=='memory-probe-a')
        definition['inputs'] = {'input.txt':'Unicode 数据\n'}
        for row in self.report['results']:
            if row['case']['id']=='memory-probe-a':
                row['case']['inputs'] = dict(definition['inputs'])
        self.report['conditions_sha256'] = digest(self.report['conditions'])
        self.assertEqual(compare_experience(self.report)['status'],'engineering_only')
        self.row('off')['case'].pop('inputs')
        self.assertEqual(compare_experience(self.report)['status'],'not_comparable')

    def test_missing_usage_counter_cannot_be_silently_counted_as_zero(self):
        for key in list(self.row('on')['usage']):
            with self.subTest(key=key):
                self.report = copy.deepcopy(self.original)
                self.row('on')['usage'].pop(key)
                self.assertEqual(compare_experience(self.report)['status'],'not_comparable')

    def test_selected_use_must_belong_to_actual_assignee_and_be_unique(self):
        for mutation in ('assignee','duplicate'):
            with self.subTest(mutation=mutation):
                self.report = copy.deepcopy(self.original)
                use = self.row('on')['memory_use']
                if mutation == 'assignee':
                    use['uses'][0].update(owner='writer',assignee='writer')
                else:
                    use['uses'].append(copy.deepcopy(use['uses'][0]))
                    use['selections'] += 1
                    use['assessed'] += 1
                self.assertEqual(compare_experience(self.report)['status'],'not_comparable')

    def test_nonfinite_aggregate_is_refused_even_when_scalar_inputs_are_finite(self):
        for row in self.report['results']:
            for task in row['workflow']['task_outcomes']:
                task['human_wait_seconds'] = 1e308
        self.assertEqual(compare_experience(self.report)['status'],'not_comparable')
        json.dumps(analyze_experience(self.report),allow_nan=False)

    def test_edited_summary_is_ignored(self):
        self.report['comparison'] = {'memory_improvement':1000}
        result = analyze_experience(self.report)
        self.assertEqual(result['outcomes']['both_succeeded'],4)
        self.assertNotIn('1000',json.dumps(result))

    def test_synthetic_live_shape_describes_results_without_asserting_causality(self):
        # Metadata/analysis wiring only; all responses were the scripted fixture.
        self.report.update(mode='live',model_calls=None)
        result = analyze_experience(self.report)
        self.assertEqual(result['status'],'compared',result)
        self.assertEqual(result['evidence_class'],'live_development')
        self.assertFalse(result['learning_improvement_established'])
        self.assertFalse(result['authenticity_verified'])
        for row in self.report['results']:
            if row['phase']=='probe':
                row['memory_use'].update(retrievals=0,selections=0,assessed=0,uses=[])
        result = analyze_experience(self.report)
        self.assertEqual(result['status'],'not_exercised',result)
        self.assertTrue(all('on_success_without_selection' in pair['diagnostics'] for pair in result['pairs']))

    def test_unrun_probe_refuses_effect_comparison_and_retains_denominator(self):
        self.row('off').update(status='not_run', classification='not_run', workflow=None,
                               usage=None, memory_use=None, duration_seconds=None)
        result = analyze_experience(self.report)
        self.assertEqual(result['status'],'not_comparable')
        self.assertEqual(result['comparison']['probes']['off']['planned'],4)
        self.assertEqual(result['comparison']['probes']['off']['not_run'],1)
        self.assertEqual(result['pairs'],[])
        self.assertIsNone(result['outcomes'])

    def test_reader_is_read_only_and_sanitized_without_runtime_or_credentials(self):
        self.row('on')['error'] = 'private-test-marker'
        self.row('on')['notes'] = 'private-test-marker'
        path = self.write()
        before = path.read_bytes()
        with (patch('agent_lab.evaluation.harness._Session', side_effect=AssertionError('runtime')),
              patch('os.getenv', side_effect=AssertionError('credentials'))):
            result = read_experience(self.directory)
        self.assertEqual(result['status'],'engineering_only')
        self.assertNotIn('private-test-marker',json.dumps(result))
        self.assertEqual(result['source_sha256'],hashlib.sha256(before).hexdigest())
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual([p.name for p in self.directory.iterdir()],['experiment.json'])

    def test_cli_formats_and_exit_status(self):
        self.write()
        for format in ('json','markdown'):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(['--run',str(self.directory),'--format',format]),0)
            if format == 'json':
                self.assertEqual(json.loads(output.getvalue())['status'],'engineering_only')
            else:
                self.assertIn('ON−OFF',output.getvalue())
                self.assertIn('Learning improvement established: `false`',output.getvalue())
        (self.directory/'experiment.json').write_text('{}')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['--run',str(self.directory)]),2)

    def test_reader_refuses_ambiguous_oversized_and_nonregular_files(self):
        path = self.directory/'experiment.json'
        for raw in ('{"x":1,"x":2}','{"x":NaN}','{"x":1e999}','private-test-marker'):
            path.write_text(raw)
            result = read_experience(self.directory)
            self.assertEqual(result['status'],'not_comparable')
            self.assertNotIn('private-test-marker',json.dumps(result))
        with path.open('wb') as stream:
            stream.truncate(MAX_BYTES+1)
        self.assertEqual(read_experience(self.directory)['status'],'not_comparable')
        path.unlink()
        target = self.directory/'source.json'
        target.write_text(json.dumps(self.report))
        path.symlink_to(target)
        self.assertEqual(read_experience(self.directory)['status'],'not_comparable')
        path.unlink()
        os.mkfifo(path)
        self.assertEqual(read_experience(self.directory)['status'],'not_comparable')


class ExperienceStopTests(unittest.TestCase):
    def run_stopped(self, phase, pause=False):
        plan = ExperiencePlan(ROOT/'evaluation/memory-plan.json')

        class StopFixture(ExperienceFixtureDriver):
            def __init__(self, live):
                super().__init__(live)
                self.attempts = []

            def clients(self, roles, stage):
                original = super().clients(roles, stage)
                def transport(payload):
                    self.attempts.append((stage['phase'],stage['memory']))
                    if stage['phase'] == phase and (phase == 'training' or stage['memory']=='on'):
                        if pause:
                            return json.dumps({'id':'scripted-pause','model':'offline-fixture',
                                'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2},
                                'choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
                                    'tool_calls':[{'id':'ask','type':'function','function':{'name':'ask_human',
                                        'arguments':json.dumps({'prompt':'Please choose a language'})}}]}}]}).encode()
                        raise OSError('Scripted transport failure; no network call')
                    return original['coordinator'].transport(payload)
                return {actor:DeepSeekClient(self.live.model,transport,max_tokens=self.live.max_output_tokens)
                        for actor in roles}

        driver = StopFixture(LiveConfig(api_key='unused-scripted-key',**plan.runtime.settings))
        with tempfile.TemporaryDirectory() as directory:
            report = ExperienceTrial(plan,driver).run(directory)
        return report, driver.attempts

    def test_unknown_probe_usage_stops_before_off_or_later_replicates(self):
        report, attempts = self.run_stopped('probe')
        self.assertEqual(report['stop'],{'slot':2,'reason':'unknown_provider_usage'})
        self.assertNotIn(('probe','off'),attempts)
        self.assertTrue(all(row['status']=='not_run' for row in report['results'][3:]))
        self.assertEqual(report['comparison']['status'],'not_comparable')
        self.assertEqual(report['results'][2]['usage']['unknown_usage_attempts'],1)

    def test_unknown_training_usage_stops_before_any_other_root(self):
        report, attempts = self.run_stopped('training')
        self.assertEqual(report['stop'],{'slot':0,'reason':'unknown_provider_usage'})
        self.assertEqual(attempts,[('training','collect')])
        self.assertTrue(all(row['status']=='not_run' for row in report['results'][1:]))
        self.assertEqual(report['seeds'],{})

    def test_probe_human_pause_stops_without_scripted_answers_or_next_arm(self):
        report, attempts = self.run_stopped('probe',pause=True)
        self.assertEqual(report['stop'],{'slot':2,'reason':'human_or_unfinished_boundary'},report)
        self.assertNotIn(('probe','off'),attempts)
        self.assertEqual(report['results'][2]['workflow']['root_state'],'waiting_input')
        self.assertTrue(all(row['status']=='not_run' for row in report['results'][3:]))


if __name__ == '__main__':
    unittest.main()
