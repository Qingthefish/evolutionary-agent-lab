"""Read-only goal metadata never grants access to files, other goals or approvals."""
import json
from pathlib import Path
import tempfile
import unittest

from agent_lab.core import Workflow, WorkflowError
from agent_lab.files import FileTools
from agent_lab.gateway import ToolGateway
from test_runner import tool


class TaskDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.workflow = Workflow(Path(self.temp.name) / 'state.sqlite3'); self.addCleanup(self.workflow.close)
        for actor, kind in [('human', 'human'), ('writer', 'agent'), ('editor', 'agent'), ('outsider', 'agent')]:
            self.workflow.register_actor(actor, kind)
        self.chat = self.workflow.create_chat('group', ['human', 'writer', 'editor'])
        self.root = self.workflow.create_task(self.chat, 'human', 'writer', 'Visible goal')
        self.workflow.start_task(self.root, 'writer')
        self.child = self.workflow.create_task(self.chat, 'writer', 'editor', 'Visible child', parent=self.root)
        self.workflow.start_task(self.child, 'editor')
        self.files = FileTools(self.workflow, Path(self.temp.name) / 'files'); self.addCleanup(self.files.close)
        self.files.create_text(self.root, 'writer', 'private.txt', 'PRIVATE_FILE_CONTENT')
        self.other = self.workflow.create_task(self.chat, 'human', 'writer', 'OTHER_GOAL_PRIVATE_TITLE')
        chat = self.workflow.create_chat('private', ['human', 'outsider'])
        self.secret = self.workflow.create_task(chat, 'human', 'outsider', 'OTHER_CHAT_PRIVATE_TITLE')

    def gateway(self, task=None, actor='editor'):
        return ToolGateway(self.workflow, self.files, task or self.child, actor, human='human', allowed=('list_tasks',))

    def test_descendant_sees_only_own_goal_metadata_without_file_or_authority_leak(self):
        result = json.loads(self.gateway().dispatch(tool('list_tasks', {'limit': 64}))['content'])
        self.assertTrue(result['ok']); data = result['result']
        self.assertEqual((data['root_task_id'], data['current_task_id']), (self.root, self.child))
        self.assertEqual({t['id'] for t in data['tasks']}, {self.root, self.child})
        self.assertFalse(data['truncated'])
        self.assertEqual(set(data['tasks'][0]), {'id', 'parent', 'assignee', 'title', 'state'})
        encoded = json.dumps(data)
        for text in ('OTHER_GOAL_PRIVATE_TITLE', 'OTHER_CHAT_PRIVATE_TITLE', 'PRIVATE_FILE_CONTENT', 'private.txt'):
            self.assertNotIn(text, encoded)
        self.assertEqual(self.workflow.task(self.child, 'editor')['state'], 'running')
        self.assertEqual(self.workflow.db.execute('SELECT count(*) FROM requests').fetchone()[0], 0)

    def test_bounded_directory_reports_truncation_and_rejects_unknown_or_invalid_arguments(self):
        data = json.loads(self.gateway().dispatch(tool('list_tasks', {'limit': 1}))['content'])['result']
        self.assertTrue(data['truncated']); self.assertEqual(len(data['tasks']), 1)
        for args in ({'limit': 0}, {'limit': 65}, {'limit': True}, {'limit': 2, 'root': self.other}):
            with self.subTest(args=args), self.assertRaises(WorkflowError):
                self.gateway().dispatch(tool('list_tasks', args, 'invalid'))

    def test_wrong_actor_and_terminal_task_cannot_use_directory_to_bypass_access(self):
        with self.assertRaises(WorkflowError): self.gateway(actor='outsider')
        with self.assertRaises(WorkflowError): self.gateway(actor='writer')
        gateway = self.gateway()
        self.workflow.finish_task(self.child, 'editor', error='Stopped task')
        with self.assertRaises(WorkflowError): gateway.dispatch(tool('list_tasks', {'limit': 4}))
        self.assertEqual(self.workflow.db.execute('SELECT count(*) FROM tool_calls').fetchone()[0], 0)


if __name__ == '__main__': unittest.main()
