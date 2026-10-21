"""Explicit repository-scoped credential injection, never ambient user credentials."""

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.core import Workflow, WorkflowError
from agent_lab.git_tools import GitTools, TrustedRepository, load_trusted_repositories


class GitCredentialTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(); self.path=Path(self.directory.name)
        self.workflow=Workflow(self.path/'state.sqlite3')
        self.repository=TrustedRepository('test',str(self.path/'repo'),('agent-test',),('docs/',),
            (('origin','https://github.com/example/designated-test.git'),),True,credential_env='RUNTIME_GIT_TEST_TOKEN')

    def tearDown(self):
        self.workflow.close();self.directory.cleanup()

    def test_explicit_env_credential_is_scoped_and_absent_from_argv_or_configuration(self):
        token='synthetic-test-value-only'
        with patch.dict('os.environ',{'RUNTIME_GIT_TEST_TOKEN':token},clear=True):
            git=GitTools(self.workflow,[self.repository]);self.addCleanup(git.close)
        with patch.object(git,'_exec',return_value=(0,b'',b'',None)) as execute:
            git._remote_git(['ls-remote','--refs',self.repository.remote_url('origin'),'refs/heads/agent-test'])
        argv,env,_=execute.call_args.args
        self.assertNotIn(token,' '.join(argv));self.assertNotIn(token,json.dumps(git.configuration()))
        self.assertEqual(env['GIT_CONFIG_KEY_0'],'http.https://github.com/example/designated-test.git.extraHeader')
        self.assertIn('http.followRedirects=false',argv)
        self.assertIn('protocol.https.allow=always',argv)
        self.assertNotIn('HTTPS_PROXY',env)
        with self.assertRaises(WorkflowError):git._remote_git(['ls-remote','https://github.com/another/repo.git'])
        with patch('agent_lab.git_tools._run',return_value=(1,token.encode(),token.encode(),None)):
            _,out,err,_=git._exec(['git'],{},1)
        self.assertNotIn(token.encode(),out+err)

    def test_missing_secret_or_unsafe_remote_is_refused(self):
        with patch.dict('os.environ',{},clear=True),self.assertRaises(WorkflowError):GitTools(self.workflow,[self.repository])
        for change in ({'allow_network':'false'}, {'remotes':(('origin','https://u:p@github.com/example/repo.git'),)},
                       {'remotes':(('origin','https://attacker.example/repo.git'),)}, {'credential_env':'TOKEN;cmd'}):
            with self.subTest(change=change),self.assertRaises(WorkflowError):replace(self.repository,**change)

    def test_config_loader_rejects_coerced_permissions_and_literal_secrets(self):
        base={'name':'test','path':str(self.path/'repo'),'writable_branches':['agent-test'],'writable_paths':['docs/']}
        file=self.path/'repos.json'
        for change in ({'allow_network':'false'}, {'token':'literal-credential'}, {'writable_branches':'main'}):
            file.write_text(json.dumps({'repositories':[base|change]}))
            with self.assertRaises(WorkflowError):load_trusted_repositories(file)
        file.write_text('{"repositories":[],"repositories":[]}')
        with self.assertRaises(ValueError):load_trusted_repositories(file)


if __name__=='__main__':unittest.main()
