"""Frozen development experience, copied only into fresh probe workflows.

The private SQLite snapshot preserves original outcome provenance, not files or
approval authority. It is never a model tool or an import into a user session.
"""

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3

from ..core import WorkflowError
from ..memory import _json
from .manifest import digest

PROTOCOL = 'frozen-experience-isolated-probes-v1'
TERMINAL = {'succeeded', 'failed', 'cancelled'}


def memory_state(workflow, memory, chat):
    """Read and integrity-check candidate content, keeping contradictory sources."""
    records = []
    for row in workflow.db.execute(
            'SELECT * FROM lessons WHERE namespace=? AND chat=? ORDER BY id', (memory.namespace, chat)):
        rendered = memory._render(row, 0)
        for source in rendered['sources']:
            _, actual = memory._outcome(source['task_id'], row['owner'])
            if _json(actual) != _json(source):
                raise WorkflowError('Memory provenance no longer matches its original task outcome')
        if not rendered['sources']:
            raise WorkflowError('Candidate lesson lacks observed outcome provenance')
        records.append({'id': row['id'], 'owner': row['owner'], 'chat': row['chat'],
                        'namespace': row['namespace'], 'lesson': row['lesson'], 'tags': json.loads(row['tags']),
                        'status': row['status'], 'sources': rendered['sources']})
    return {'lessons': len(records), 'sources': sum(len(r['sources']) for r in records),
            'active': sum(r['status'] == 'active' for r in records),
            'retired': sum(r['status'] == 'retired' for r in records), 'content_sha256': digest(records)}


def tree_usage(workflow, root):
    from ..budget import descendants
    ids = [t['id'] for t in descendants(workflow, root)]
    marks = ','.join('?' for _ in ids)
    turns = list(workflow.db.execute(f'SELECT response FROM runner_turns WHERE task IN ({marks})', ids)) if _table(workflow, 'runner_turns') else []
    responses = [json.loads(r[0]) for r in turns if r[0] is not None]
    return {'reserved_model_attempts': len(turns), 'unknown_usage_attempts': sum(r[0] is None for r in turns),
            'reported_tokens': sum(r['usage']['total_tokens'] for r in responses),
            'tool_calls': workflow.db.execute(f'SELECT count(*) FROM tool_calls WHERE task IN ({marks})', ids).fetchone()[0]
                          if _table(workflow, 'tool_calls') else 0}


def memory_use(workflow, root):
    from ..budget import descendants
    ids = [t['id'] for t in descendants(workflow, root)]
    marks = ','.join('?' for _ in ids)
    uses = [dict(r) for r in workflow.db.execute(
        f'SELECT u.lesson,u.task,u.outcome,l.owner,l.namespace,l.chat,t.assignee FROM lesson_uses u '
        f'JOIN lessons l ON l.id=u.lesson JOIN tasks t ON t.id=u.task WHERE u.task IN ({marks}) ORDER BY u.task,u.lesson', ids)]
    return {'retrievals': workflow.db.execute(f'SELECT count(*) FROM lesson_retrievals WHERE task IN ({marks})', ids).fetchone()[0],
            'selections': len(uses), 'assessed': sum(r['outcome'] is not None for r in uses), 'uses': uses}


def _table(workflow, name):
    return workflow.db.execute('SELECT 1 FROM sqlite_master WHERE name=?', (name,)).fetchone() is not None


class MemorySeed:
    """One immutable source snapshot per replicate; no probe-to-probe transfer."""
    def __init__(self, directory, info):
        self.directory, self.info = Path(directory).resolve(), info

    @classmethod
    def freeze(cls, session, directory, chat, roots):
        w, memory = session.workflow, session.memory
        # Only a purpose-created, single-conversation training session can seed
        # probes. Never duplicate an arbitrary user's existing workflow.
        actual_roots = {r[0] for r in w.db.execute('SELECT id FROM tasks WHERE parent IS NULL')}
        if (w.db.execute('SELECT count(*) FROM chats').fetchone()[0] != 1
                or not roots or set(roots) != actual_roots or len(set(roots)) != len(roots)):
            raise WorkflowError('Freeze only the complete dedicated training conversation')
        if any(r[0] not in TERMINAL for r in w.db.execute('SELECT state FROM tasks')):
            raise WorkflowError('Training is paused/incomplete; no seed or dependent probes may run')
        if w.db.execute('SELECT 1 FROM requests WHERE approved=1 AND consumed=0').fetchone():
            raise WorkflowError('Unreleased approval prevents training freeze')
        for table, predicate in (
                ('runner_sessions', "status IN ('calling','processing','stopping')"),
                ('runner_turns', "status!='settled'"), ('tool_calls', "status='reserved'"),
                ('sandbox_runs', "status NOT IN ('cleaned','reconciled')"),
                ('git_operations', "status IN ('started','uncertain','unknown')"),
                ('retrieval_records', "status='reserved'")):
            if _table(w, table) and w.db.execute(f'SELECT 1 FROM {table} WHERE {predicate}').fetchone():
                raise WorkflowError('Unknown training effects/usage require reconciliation before freeze')
        for task in w.db.execute('SELECT id FROM tasks'):
            outcome = w.db.execute('SELECT result FROM memory_outcomes WHERE task=? AND namespace=?',
                                   (task[0], memory.namespace)).fetchone()
            if outcome is None or json.loads(outcome[0]).get('status') != 'recorded':
                raise WorkflowError('Training outcome capture is incomplete or failed')
        state = memory_state(w, memory, chat)
        if not state['active']:
            raise WorkflowError('Training produced no active candidate experience')
        directory = Path(directory)
        directory.mkdir(mode=0o700, exist_ok=False)
        target = directory / 'seed.sqlite3'
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        with closing(sqlite3.connect(target)) as destination:
            w.db.backup(destination)
        os.chmod(target, 0o400)
        info = {'protocol': PROTOCOL, 'namespace': memory.namespace, 'chat': chat,
                'training_roots': list(roots), 'memory': state,
                'message_floor': w.db.execute('SELECT coalesce(max(sequence),0) FROM messages WHERE chat=?', (chat,)).fetchone()[0],
                'database_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                'files': 'fresh-empty-per-probe', 'authorization': 'new-task-scoped; none inherited'}
        (directory / 'seed.json').write_text(json.dumps(info, indent=2) + '\n')
        return cls(directory, info)

    def fork(self, directory):
        source = self.directory / 'seed.sqlite3'
        if hashlib.sha256(source.read_bytes()).hexdigest() != self.info['database_sha256']:
            raise WorkflowError('Frozen training database changed; preserve evidence and stop')
        directory = Path(directory)
        directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        path = directory / 'workflow.sqlite3'
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        # Backup is trusted experiment setup, never an operation proposed by an
        # agent. Reset only the NEW COPY's file-root binding; copy no old files.
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as frozen, closing(sqlite3.connect(path)) as target:
            if frozen.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise WorkflowError('Frozen SQLite integrity check failed')
            frozen.backup(target)
            target.execute('DELETE FROM file_root')
            target.commit()
        from .harness import _Session
        session = _Session(directory, self.info['namespace'])
        try:
            if memory_state(session.workflow, session.memory, self.info['chat']) != self.info['memory']:
                raise WorkflowError('Probe memory does not match the frozen training content')
            return session
        except BaseException:
            session.close()
            raise
