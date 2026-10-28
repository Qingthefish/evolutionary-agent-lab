"""Independent transfer/read criteria reject correct-looking but unreceived data."""
import json
from pathlib import Path
import tempfile
import unittest

from agent_lab.acceptance import ArtifactRule, verify_rules
from agent_lab.core import Workflow, WorkflowError
from agent_lab.files import FileTools
from agent_lab.gateway import ToolGateway
from test_runner import tool


class SnapshotProvenanceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        self.workflow = Workflow(Path(directory.name) / 'state.sqlite3'); self.addCleanup(self.workflow.close)
        for actor, kind in [('human', 'human'), ('coordinator', 'agent'), ('writer', 'agent'), ('editor', 'agent')]:
            self.workflow.register_actor(actor, kind)
        self.chat = self.workflow.create_chat('group', ['human', 'coordinator', 'writer', 'editor'])
        self.root = self.workflow.create_task(self.chat, 'human', 'coordinator', 'Check transferred data')
        self.workflow.start_task(self.root, 'coordinator')
        self.writer = self.workflow.create_task(self.chat, 'coordinator', 'writer', 'Draft', parent=self.root)
        self.editor = self.workflow.create_task(self.chat, 'coordinator', 'editor', 'Check', parent=self.root)
        self.workflow.start_task(self.writer, 'writer'); self.workflow.start_task(self.editor, 'editor')
        self.files = FileTools(self.workflow, Path(directory.name) / 'files'); self.addCleanup(self.files.close)
        self.content = 'Actual source snapshot\n'
        self.original = self.files.create_text(self.writer, 'writer', 'draft.txt', self.content)
        self.spec = {'assignee': 'writer', 'title': 'Draft', 'path': 'draft.txt', 'allow_relay': True, 'require_read': True}

    def rule(self, **changes):
        return ArtifactRule('input.txt', 'received_from', json.dumps({**self.spec, **changes}))

    def check(self, **changes):
        return all(verify_rules(self.workflow, self.files, self.editor, 'editor', [self.rule(**changes)]).values())

    def offer(self, source=None, source_actor='writer', source_path='draft.txt', target=None):
        return self.files.offer_artifact(source or self.writer, source_actor, source_path, target or self.editor,
                                        expected_sha256=self.original['sha256'])

    def accept(self, offer, target=None, actor='editor', path='input.txt'):
        return self.files.accept_artifact(target or self.editor, actor, offer['artifact_id'], path)

    def test_direct_transfer_needs_an_actual_read_and_checks_inside_completion(self):
        offer = self.offer(); self.accept(offer)
        self.assertFalse(self.check())
        self.assertTrue(self.check(require_read=False))
        with self.assertRaisesRegex(WorkflowError, 'verification failed'):
            self.workflow.finish_task(self.editor, 'editor', verifier=lambda: verify_rules(
                self.workflow, self.files, self.editor, 'editor', [self.rule()]))
        self.assertEqual(self.workflow.task(self.editor, 'editor')['state'], 'running')
        self.files.read_text(self.editor, 'editor', 'input.txt')
        self.workflow.finish_task(self.editor, 'editor', verifier=lambda: verify_rules(
            self.workflow, self.files, self.editor, 'editor', [self.rule()]))
        self.assertEqual(self.workflow.task(self.editor, 'editor')['state'], 'succeeded')

    def test_causal_relay_passes_only_when_relay_is_explicitly_allowed(self):
        first = self.offer(target=self.root); self.accept(first, self.root, 'coordinator', 'relay.txt')
        second = self.offer(self.root, 'coordinator', 'relay.txt'); self.accept(second)
        self.files.read_text(self.editor, 'editor', 'input.txt')
        self.assertTrue(self.check()); self.assertFalse(self.check(allow_relay=False))

    def test_identical_independently_created_file_and_unconsumed_offer_are_insufficient(self):
        self.files.create_text(self.editor, 'editor', 'input.txt', self.content)
        self.files.read_text(self.editor, 'editor', 'input.txt')
        self.assertFalse(self.check())
        self.offer()
        self.assertFalse(self.check())

    def test_modified_target_or_wrong_origin_path_cannot_reuse_an_old_receipt(self):
        offer = self.offer(); self.accept(offer); self.files.read_text(self.editor, 'editor', 'input.txt')
        self.assertFalse(self.check(path='different-source.txt'))
        self.files.update_text(self.editor, 'editor', 'input.txt', 'Changed\n', expected_sha256=self.original['sha256'])
        self.files.read_text(self.editor, 'editor', 'input.txt'); self.assertFalse(self.check())

    def test_other_goal_and_ambiguous_source_cannot_supply_the_required_origin(self):
        other = self.workflow.create_task(self.chat, 'human', 'coordinator', 'Other goal')
        self.workflow.start_task(other, 'coordinator')
        source = self.workflow.create_task(self.chat, 'coordinator', 'writer', 'Draft', parent=other)
        self.workflow.start_task(source, 'writer'); self.files.create_text(source, 'writer', 'draft.txt', self.content)
        self.accept(self.offer(source)); self.files.read_text(self.editor, 'editor', 'input.txt')
        self.assertFalse(self.check())
        self.accept(self.offer(), path='valid.txt'); self.files.read_text(self.editor, 'editor', 'valid.txt')
        rule = ArtifactRule('valid.txt', 'received_from', json.dumps(self.spec))
        valid = lambda: all(verify_rules(self.workflow, self.files, self.editor, 'editor', [rule]).values())
        self.assertTrue(valid())
        self.workflow.create_task(self.chat, 'coordinator', 'writer', 'Draft', parent=self.root)
        self.assertFalse(valid())

    def test_relay_cannot_claim_a_source_that_arrived_after_it_forwarded_a_copy(self):
        self.files.create_text(self.root, 'coordinator', 'copy.txt', self.content)
        self.accept(self.offer(self.root, 'coordinator', 'copy.txt'))
        self.files.read_text(self.editor, 'editor', 'input.txt')
        self.accept(self.offer(target=self.root), self.root, 'coordinator', 'later.txt')
        self.assertFalse(self.check())

    def test_legacy_gateway_result_can_bind_id_but_chronology_alone_cannot(self):
        offer = self.offer()
        gateway = ToolGateway(self.workflow, self.files, self.editor, 'editor', human='human',
                              allowed=('accept_artifact', 'read_text'))
        gateway.dispatch(tool('accept_artifact', {'artifact_id': offer['artifact_id'], 'path': 'input.txt'}, 'accept'))
        gateway.dispatch(tool('read_text', {'path': 'input.txt'}, 'read'))
        row = self.workflow.db.execute("SELECT sequence,detail FROM events WHERE task=? AND kind='artifact_received'", (self.editor,)).fetchone()
        detail = json.loads(row['detail']); self.assertEqual(detail.pop('artifact_id'), offer['artifact_id'])
        self.workflow.db.execute('UPDATE events SET detail=? WHERE sequence=?', (json.dumps(detail), row['sequence']))
        self.assertTrue(self.check())  # Exact ID is already in the trusted successful gateway result.
        self.workflow.db.execute("UPDATE tool_calls SET result=? WHERE task=? AND call_id='accept'", (
            json.dumps({'ok': True, 'result': {**self.original, 'path': 'input.txt'}}), self.editor))
        self.assertFalse(self.check())

    def test_conflicting_explicit_receipts_do_not_prove_delivery(self):
        offer = self.offer(); self.accept(offer); self.files.read_text(self.editor, 'editor', 'input.txt')
        self.assertTrue(self.check())
        row = self.workflow.db.execute("SELECT detail FROM events WHERE task=? AND kind='artifact_received'", (self.editor,)).fetchone()
        self.workflow._event(self.editor, 'editor', 'artifact_received', json.loads(row['detail']))
        self.assertFalse(self.check())

    def test_malformed_legacy_gateway_records_fail_closed_without_a_checker_crash(self):
        offer = self.offer()
        gateway = ToolGateway(self.workflow, self.files, self.editor, 'editor', human='human',
                              allowed=('accept_artifact', 'read_text'))
        gateway.dispatch(tool('accept_artifact', {'artifact_id': offer['artifact_id'], 'path': 'input.txt'}, 'accept'))
        gateway.dispatch(tool('read_text', {'path': 'input.txt'}, 'read'))
        row = self.workflow.db.execute("SELECT sequence,detail FROM events WHERE task=? AND kind='artifact_received'", (self.editor,)).fetchone()
        detail = json.loads(row['detail']); detail.pop('artifact_id')
        self.workflow.db.execute('UPDATE events SET detail=? WHERE sequence=?', (json.dumps(detail), row['sequence']))
        call = dict(self.workflow.db.execute("SELECT * FROM tool_calls WHERE task=? AND call_id='accept'", (self.editor,)).fetchone())
        for field, malformed in [('arguments', '[]'), ('result', '[]'), ('result', '{"ok":true,"result":[]}')]:
            self.workflow.db.execute(f"UPDATE tool_calls SET {field}=? WHERE task=? AND call_id='accept'", (malformed, self.editor))
            self.assertFalse(self.check())
            self.workflow.db.execute(f"UPDATE tool_calls SET {field}=? WHERE task=? AND call_id='accept'", (call[field], self.editor))
        self.assertTrue(self.check())

    def test_failed_source_cannot_certify_an_otherwise_valid_transfer(self):
        offer = self.offer(); self.accept(offer); self.files.read_text(self.editor, 'editor', 'input.txt')
        self.assertTrue(self.check())
        self.workflow.finish_task(self.writer, 'writer', error='Source failed')
        self.assertFalse(self.check())

    def test_source_metadata_is_bounded_unambiguous_and_cannot_grant_access(self):
        invalid = [json.dumps({**self.spec, 'path': '../escape'}), json.dumps({**self.spec, 'allow_relay': 1}),
                   json.dumps({**self.spec, 'extra': 'authority'}), '{"assignee":"writer","assignee":"editor"}']
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(WorkflowError):
                ArtifactRule('input.txt', 'received_from', value)


if __name__ == '__main__': unittest.main()
