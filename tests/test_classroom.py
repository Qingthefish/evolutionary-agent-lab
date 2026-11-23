"""Presentation entry-point input custody, freshness and zero-call boundaries."""
import json
from pathlib import Path
import socket
import tempfile
import unittest
import io
from contextlib import redirect_stdout
from unittest.mock import patch

from scripts import classroom as c
from agent_lab import Workflow
from agent_lab.files import FileTools
from agent_lab.inspection import ArtifactInspector
from agent_lab.core import WorkflowError


class ClassroomTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.sock=socket.socket(socket.AF_UNIX)
        self.sock.bind(str(self.base/'docker.sock'))
        self.addCleanup(self.sock.close)
        self.config={'model':'test-no-real-provider','key_env':'CLASSROOM_TEST_KEY',
            'credential_file':'not-used','docker_host':'unix://'+str(self.base/'docker.sock'),
            'python_image':'python@sha256:'+'a'*64}
        self.env=patch.dict('os.environ',{'CLASSROOM_TEST_KEY':'synthetic-test-key'})
        self.env.start();self.addCleanup(self.env.stop)
        self.local=patch.object(c,'LOCAL',self.base/'local');self.local.start();self.addCleanup(self.local.stop)

    def goal(self):
        path=self.base/'teacher.txt';path.write_text('原题\nMake a summary from the supplied data.\n')
        return path

    def test_import_preserves_original_goal_and_inputs_without_execution(self):
        data=self.base/'data.csv';data.write_text('item,value\na,2\nb,3\n')
        directory=c.import_text(self.config,self.goal(),[data]);meta=c.read(directory/'session.json')
        w=Workflow(directory/'state/workflow.sqlite3');files=FileTools(w,directory/'state/files')
        try:
            self.assertEqual(w.task(meta['task'],'operator')['state'],'pending')
            self.assertEqual(w.task(meta['task'],'operator')['title'],self.goal().read_text())
            inspector=ArtifactInspector(w,files)
            self.assertEqual(inspector.read_file(meta['task'],'operator','inputs/01-data.csv')['content'],data.read_text())
            self.assertEqual(inspector.read_file(meta['task'],'operator','inputs/teacher-goal.txt')['content'],self.goal().read_text())
            self.assertEqual(w.db.execute("select count(*) from events where kind='model_attempt_reserved'").fetchone()[0],0)
        finally:files.close();w.close()
        self.assertFalse(meta['web_enabled']);self.assertFalse(meta['memory_enabled'])

    def test_new_invocations_use_separate_groups_and_preserve_old_files(self):
        first=c.import_text(self.config,self.goal());before=(first/'session.json').read_bytes()
        second=c.import_text(self.config,self.goal())
        self.assertNotEqual(first,second)
        self.assertNotEqual(c.read(first/'session.json')['chat'],c.read(second/'session.json')['chat'])
        self.assertEqual((first/'session.json').read_bytes(),before)

    def test_existing_run_cannot_be_overwritten(self):
        directory=c.import_text(self.config,self.goal())
        with self.assertRaises(ValueError):c.import_text(self.config,self.goal(),directory=directory)

    def test_utf8_bom_and_crlf_input_bytes_survive_import_and_export(self):
        data=self.base/'windows.csv';raw=b'\xef\xbb\xbfitem,value\r\na,2\r\n';data.write_bytes(raw)
        directory=c.import_text(self.config,self.goal(),[data])
        output=c.export_text(self.config,directory);task=c.read(directory/'session.json')['task']
        self.assertEqual((output/'files'/task/'inputs/01-windows.csv').read_bytes(),raw)

    def test_link_and_non_utf8_inputs_refused_before_task_creation(self):
        goal=self.goal();link=self.base/'link.txt';link.symlink_to(goal)
        with self.assertRaises(OSError):c.import_text(self.config,link)
        binary=self.base/'binary';binary.write_bytes(b'\xff\xfe')
        with self.assertRaises(UnicodeError):c.import_text(self.config,goal,[binary])
        self.assertFalse((self.base/'local/current.json').exists())

    def test_unknown_role_archive_does_not_fall_back_to_default_roles(self):
        from zipfile import ZipFile
        archive=self.base/'different.zip'
        with ZipFile(archive,'w') as z:z.writestr('other.txt','Unknown task format')
        with self.assertRaises(WorkflowError):c.prepare_zip(self.config,archive)
        self.assertFalse((self.base/'local/current.json').exists())

    def test_relocated_role_archive_retains_manifest_roles_and_ordered_goals(self):
        from tests.official_mid_fixture import README_SHA256,write_archive
        from agent_lab.evaluation.official_session import main as session_main
        archive=self.base/'renamed-issued-package.zip';write_archive(archive)
        def local_session(module,args,directory,config,**kwargs):
            self.assertEqual(module,'agent_lab.evaluation.official_session')
            self.assertFalse(kwargs.get('network',False))
            output=io.StringIO()
            with redirect_stdout(output):session_main(list(map(str,args)))
            return json.loads(output.getvalue())
        with patch('agent_lab.evaluation.official_dataset._README_SHA256',README_SHA256),patch.object(c,'call',side_effect=local_session):
            directory=c.prepare_zip(self.config,archive)
            spec=c.read(directory/'session.json')
            self.assertEqual(len(spec['cases']),3)
            for case,item in spec['cases'].items():
                d=Path(item['directory']);plan=c.OfficialMidTestPlan(d/'plan.json')
                scenario=next(s for s in plan.dataset['scenarios'] if s['id']==case)
                w=Workflow(d/'state/workflow.sqlite3')
                try:
                    self.assertEqual({r[0] for r in w.db.execute("select id from actors where kind='agent'")},set(item['role_ids']))
                    self.assertEqual(w.db.execute('select title from tasks').fetchone()[0],scenario['tasks'][0]['prompt'])
                    self.assertEqual(w.db.execute('select count(*) from official_roots').fetchone()[0],1)
                    self.assertEqual(w.db.execute("select count(*) from events where kind='model_attempt_reserved'").fetchone()[0],0)
                finally:w.close()

    def test_export_keeps_pending_state_and_exact_input_contents(self):
        directory=c.import_text(self.config,self.goal());out=c.export_text(self.config,directory)
        result=c.read(out/'results.json')
        task=c.read(directory/'session.json')['task']
        self.assertEqual(result['tasks'][0]['task']['state'],'pending')
        self.assertEqual((out/'files'/task/'inputs/teacher-goal.txt').read_text(),self.goal().read_text())
        w=Workflow(directory/'state/workflow.sqlite3')
        try:self.assertEqual(w.db.execute("select count(*) from events where kind='model_attempt_reserved'").fetchone()[0],0)
        finally:w.close()

    def test_zero_call_doctor_does_not_expose_credential(self):
        report=c.doctor(self.config)
        self.assertTrue(report['course_key_available'])
        self.assertNotIn('synthetic-test-key',json.dumps(report))
        self.assertEqual(report['new_model_requests'],0)


if __name__=='__main__':unittest.main()
