"""Opt-in actual Docker/local-Git chain. All model responses stay synthetic."""

import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.core import WorkflowError
from agent_lab.integration_fixture import CODE, run_integrated

HOST=os.environ.get('AGENT_LAB_DOCKER_HOST')
IMAGE=os.environ.get('AGENT_LAB_PYTHON_IMAGE')


@unittest.skipUnless(HOST and IMAGE,'Set explicit Docker socket and pinned image for combined actual-tool checks')
class IntegratedWorkflowTests(unittest.TestCase):
    def test_source_inputs_actual_execution_approval_restart_push_and_memory(self):
        with tempfile.TemporaryDirectory() as path:
            report=run_integrated(Path(path),docker_host=HOST,image=IMAGE)
            self.assertEqual(report['after_restart']['task_state'],'succeeded')
            self.assertEqual(report['later_memory_task']['task_state'],'succeeded')
            self.assertTrue(report['actual_python_sandbox'])
            self.assertFalse(report['github_push_established'] or report['learning_improvement_established'])
            self.assertEqual(report['model_calls'],0)
            self.assertEqual(report['memory_selected_uses'][0]['outcome'],'succeeded')

    def test_wrong_executed_result_never_reaches_commit_or_false_success(self):
        with tempfile.TemporaryDirectory() as path,patch('agent_lab.integration_fixture.CODE',CODE.replace('json.dumps(dict(counts), sort_keys=True)',"'WRONG'")):
            with self.assertRaises(WorkflowError):run_integrated(Path(path),docker_host=HOST,image=IMAGE)
            db=sqlite3.connect(Path(path)/'workflow.sqlite3')
            try:
                root=db.execute('SELECT state FROM tasks WHERE parent IS NULL').fetchone()[0]
                self.assertEqual(root,'failed')
                self.assertEqual(db.execute("SELECT count(*) FROM git_operations WHERE operation='push'").fetchone()[0],0)
                row=db.execute('SELECT result FROM sandbox_runs ORDER BY rowid DESC LIMIT 1').fetchone()
                self.assertTrue(json.loads(row[0])['cleanup_confirmed'])
            finally:db.close()


if __name__=='__main__':unittest.main()
