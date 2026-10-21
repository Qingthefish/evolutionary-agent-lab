"""Trusted data criteria are independent of candidate-produced assertions."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from agent_lab.acceptance import ArtifactRule, parse_rules, verify_rules
from agent_lab.core import Workflow, WorkflowError
from agent_lab.files import FileTools
from agent_lab.runtime import TaskPolicy, ChildTextRule, bind_task_policy, policy_from_spec, text_acceptance_factory
from agent_lab.evaluation import parse_case
from agent_lab.evaluation.harness import _case_policy


class ArtifactAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.path=Path(self.temp.name)
        self.w=Workflow(self.path/'state.sqlite3'); self.f=FileTools(self.w,self.path/'files')
        for actor,kind in [('user','human'),('coordinator','agent'),('writer','agent')]: self.w.register_actor(actor,kind)
        self.chat=self.w.create_chat('group',['user','coordinator','writer'])
        self.root=self.w.create_task(self.chat,'user','coordinator','Deliver checked artifacts')
        self.w.start_task(self.root,'coordinator')

    def tearDown(self):
        self.f.close(); self.w.close(); self.temp.cleanup()

    def checks(self,rules): return verify_rules(self.w,self.f,self.root,'coordinator',rules)

    def test_root_requires_actual_sections_size_and_absence(self):
        policy=TaskPolicy(root_criteria=[ArtifactRule('report.md','contains','## Sources',min_bytes=20),
                                        ArtifactRule('scratch.txt','absent')])
        receipt=self.f.create_text(self.root,'coordinator','report.md','Looks done')
        verifier,_=text_acceptance_factory(self.w,self.f,self.root,policy)(self.w.task(self.root,'user'))
        with self.assertRaisesRegex(WorkflowError,'criterion:'):
            self.w.finish_task(self.root,'coordinator',verifier=verifier)
        self.f.update_text(self.root,'coordinator','report.md','## Result\nA report\n## Sources\nSource\n',expected_sha256=receipt['sha256'])
        self.w.finish_task(self.root,'coordinator',verifier=verifier)
        self.assertEqual(self.w.task(self.root,'user')['state'],'succeeded')

    def test_json_is_structural_finite_unambiguous_and_strict_about_types(self):
        rule=ArtifactRule('data.json','json_equals','{"count":1,"ok":true}')
        current=self.f.create_text(self.root,'coordinator','data.json','{ "ok": true, "count": 1 }')
        self.assertTrue(all(self.checks([rule]).values()))
        for bad in ('{"count":true,"ok":true}','{"count":1,"count":2,"ok":true}','{"count":NaN,"ok":true}'):
            current=self.f.update_text(self.root,'coordinator','data.json',bad,expected_sha256=current['sha256'])
            self.assertFalse(all(self.checks([rule]).values()))

    def test_digest_reads_current_file_not_a_self_reported_test_result(self):
        self.f.create_text(self.root,'coordinator','tests.txt','ALL TESTS PASSED')
        digest=hashlib.sha256(b'correct').hexdigest()
        self.assertFalse(all(self.checks([ArtifactRule('solution.py','sha256',digest)]).values()))
        self.f.create_text(self.root,'coordinator','solution.py','wrong')
        self.assertFalse(all(self.checks([ArtifactRule('solution.py','sha256',digest)]).values()))

    def test_symlink_is_not_proof_of_absence_or_allowed_content(self):
        self.f.create_text(self.root,'coordinator','seed.txt','seed')
        directory=self.path/'files/tasks'/hashlib.sha256(self.root.encode()).hexdigest()
        outside=self.path/'outside.txt';outside.write_text('secret')
        os.symlink(outside,directory/'escape.txt')
        self.assertFalse(all(self.checks([ArtifactRule('escape.txt','absent')]).values()))
        self.assertFalse(all(self.checks([ArtifactRule('escape.txt','contains','secret')]).values()))

    def test_version_three_policy_round_trip_and_immutability(self):
        spec={'criteria':[{'path':'report.md','kind':'contains','expected':'## Sources'}],
              'child_rules':[{'assignee':'writer','title':'Write data','criteria':[
                  {'path':'data.json','kind':'json_equals','expected':'{"count":1}'}]}]}
        policy=policy_from_spec(spec)
        self.assertEqual(policy.record()['version'],3)
        bind_task_policy(self.w,self.root,'user',policy)
        self.assertEqual(bind_task_policy(self.w,self.root,'user'),policy)
        with self.assertRaises(WorkflowError): bind_task_policy(self.w,self.root,'user',TaskPolicy())

    def test_legacy_policies_keep_versions_and_record_shape(self):
        self.assertEqual(set(TaskPolicy(root_artifacts={'note.txt':'ok'}).record()),{'version','constraints','root_artifacts'})
        policy=TaskPolicy(child_rules=[ChildTextRule('writer','Write',{'note.txt':'ok'})])
        self.assertEqual(policy.record()['version'],2)
        self.assertNotIn('criteria',policy.record()['child_rules'][0])

    def test_invalid_criteria_and_contradictory_policy_fail_before_execution(self):
        for records in ({},[{}],[{'path':'../escape','kind':'exists'}],[{'path':'a.txt','kind':'command','expected':'run'}],
                        [{'path':'a.txt','kind':'exists','max_bytes':True}],[{'path':'a.txt','kind':'json_equals','expected':'NaN'}]):
            with self.assertRaises(WorkflowError): parse_rules(records)
        with self.assertRaises(WorkflowError):
            TaskPolicy(root_artifacts={'a.txt':'ok'},root_criteria=[ArtifactRule('a.txt','absent')])

    def test_case_criteria_reach_root_and_child_runtime_acceptance(self):
        case=parse_case({'id':'file-criteria','title':'Check files','goal':'Deliver data','driver':'live_scheduler',
            'expected':{'final_state':'succeeded','criteria':[{'path':'report.md','kind':'contains','expected':'## Sources'}],
                'subtasks':[{'assignee':'writer','title':'Write data','final_state':'succeeded',
                            'criteria':[{'path':'data.json','kind':'json_equals','expected':'{"count":1}'}]}]}})
        policy=_case_policy(case,None)
        self.assertEqual(policy.root_criteria[0].kind,'contains')
        child=self.w.create_task(self.chat,'coordinator','writer','Write data',parent=self.root)
        self.w.start_task(child,'writer'); self.f.create_text(child,'writer','data.json','{"count":2}')
        verifier,_=text_acceptance_factory(self.w,self.f,self.root,policy)(self.w.task(child,'user'))
        with self.assertRaises(WorkflowError): self.w.finish_task(child,'writer',verifier=verifier)


if __name__=='__main__':unittest.main()
