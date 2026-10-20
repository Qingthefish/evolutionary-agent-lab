"""The minimal interface creates and resumes real state without a model fallback."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.console import main
from agent_lab.deepseek import DeepSeekHTTP


class ConsoleTests(unittest.TestCase):
    def test_create_read_restart_and_advance_without_configuration(self):
        with tempfile.TemporaryDirectory() as path:
            prefix=['--state-dir',path]
            stream=io.StringIO()
            with contextlib.redirect_stdout(stream):
                self.assertEqual(main(prefix+['new','--goal','Create a useful report']),0)
            created=json.loads(stream.getvalue()); self.assertEqual(created['execution'],'not_started')
            stream=io.StringIO()
            with contextlib.redirect_stdout(stream): main(prefix+['status','--task',created['task']])
            self.assertEqual(json.loads(stream.getvalue())['task']['state'],'pending')
            with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
                main(prefix+['advance',created['task']])

    def test_live_creation_preserves_trusted_policy_without_calling_model(self):
        with tempfile.TemporaryDirectory() as path:
            policy=Path(path)/'policy.json';policy.write_text(json.dumps({'artifacts':{'note.txt':'Checked\n'},'child_rules':[
                {'assignee':'writer','title':'Draft checked text','artifacts':{'note.txt':'Checked\n'}}]}))
            args=['--state-dir',str(Path(path)/'state'),'--live','--model','explicit-model','--api-key-env','CONSOLE_TEST_KEY','--enable-web','new','--goal','Deliver note.txt','--policy',str(policy)]
            stream=io.StringIO()
            with patch.dict('os.environ',{'CONSOLE_TEST_KEY':'unused-key'},clear=True),patch.object(DeepSeekHTTP,'__call__',side_effect=AssertionError('No implicit request')) as http,contextlib.redirect_stdout(stream):
                main(args);http.assert_not_called()
            created=json.loads(stream.getvalue());self.assertEqual(created['execution'],'scheduled')
            self.assertNotIn('unused-key',stream.getvalue())


if __name__=='__main__':unittest.main()
