"""Opt-in, bounded replacement of failed children; terminal history is immutable.

This is retrying the same assignment, not a general dependency-graph planner.
It never copies private files, reuses approvals, or reconciles unknown effects.
"""

import json

from .core import WorkflowError


def configure(workflow, root, maximum):
    if type(maximum) is not int or not 0 <= maximum <= 8:
        raise WorkflowError("Child replacement limit must be an integer from 0 to 8")
    workflow.db.executescript("""
        CREATE TABLE IF NOT EXISTS retry_policies (
            root TEXT PRIMARY KEY REFERENCES tasks(id), maximum INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS task_retries (
            failed TEXT PRIMARY KEY REFERENCES tasks(id),
            replacement TEXT NOT NULL UNIQUE REFERENCES tasks(id),
            parent TEXT NOT NULL REFERENCES tasks(id), reason TEXT NOT NULL
        );
    """)
    with workflow._transaction():
        old = workflow.db.execute("SELECT maximum FROM retry_policies WHERE root=?", (root,)).fetchone()
        if old and old[0] != maximum:
            raise WorkflowError("Original child replacement limit cannot change on resume")
        workflow.db.execute("INSERT OR IGNORE INTO retry_policies VALUES(?,?)", (root, maximum))


def links(workflow):
    if not workflow.db.execute("SELECT 1 FROM sqlite_master WHERE name='task_retries'").fetchone():
        return {}
    return {r['failed']: r['replacement'] for r in workflow.db.execute("SELECT failed,replacement FROM task_retries")}


def active_tasks(workflow, tasks):
    """Hide abandoned branches for scheduling only; metrics retain every task."""
    tasks = list(tasks)
    replaced = links(workflow)
    by_id = {t['id']: t for t in tasks}
    active = []
    for task in tasks:
        if task['id'] in replaced:
            continue
        parent = by_id.get(task['parent'])
        while parent is not None and parent['state'] not in {'failed', 'cancelled'}:
            parent = by_id.get(parent['parent'])
        if parent is None:
            active.append(task)
    return active


def children_complete(workflow, parent):
    replaced = links(workflow)
    return all(t['state'] == 'succeeded' or t['id'] in replaced
               for t in workflow.db.execute("SELECT id,state FROM tasks WHERE parent=?", (parent,)))


def retry_context(workflow, task):
    if not workflow.db.execute("SELECT 1 FROM sqlite_master WHERE name='task_retries'").fetchone():
        return None
    row = workflow.db.execute("SELECT r.failed,r.reason,t.evidence FROM task_retries r JOIN tasks t ON t.id=r.failed WHERE r.replacement=?", (task,)).fetchone()
    return None if row is None else {"failed_task": row['failed'], "reason": row['reason'],
        "failure_evidence": json.loads(row['evidence']) if row['evidence'] else None,
        "instruction": "New attempt at the same assignment and criteria. No previous file access or approval is inherited."}


def availability(workflow, parent, failed, *, require_running=True):
    """Recheck inside the caller's reservation transaction before any mutation."""
    source = workflow._row('tasks', failed)
    caller = workflow._row('tasks', parent)
    if source['parent'] != parent or source['state'] != 'failed' or caller['state'] not in (
            {'running'} if require_running else {'running','waiting_input','waiting_approval'}):
        raise WorkflowError("Retry only a failed direct child of your running task")
    root = caller
    while root['parent']:
        root = workflow._row('tasks', root['parent'])
    if not workflow.db.execute("SELECT 1 FROM sqlite_master WHERE name='retry_policies'").fetchone():
        raise WorkflowError("Child replacement is not configured")
    policy = workflow.db.execute("SELECT maximum FROM retry_policies WHERE root=?", (root['id'],)).fetchone()
    used = workflow.db.execute("""WITH RECURSIVE tree(id) AS (
        SELECT ? UNION ALL SELECT t.id FROM tasks t JOIN tree ON t.parent=tree.id
    ) SELECT count(*) FROM task_retries r JOIN tree ON tree.id=r.parent""", (root['id'],)).fetchone()[0]
    if policy is None or used >= policy[0] or failed in links(workflow):
        raise WorkflowError("Shared child replacement limit exhausted or child already replaced")
    # A failed subtree may have side effects. Never use a new attempt to avoid a
    # denial, an unreleased grant, or a provider/tool/sandbox/Git ambiguity.
    from .budget import descendants
    ids = [t['id'] for t in descendants(workflow, failed)]
    marks = ','.join('?' for _ in ids)
    if workflow.db.execute(f"SELECT 1 FROM requests WHERE task IN ({marks}) AND (approved=0 OR (approved=1 AND consumed=0))", ids).fetchone():
        raise WorkflowError("Denied or unreleased actions prevent automatic child replacement")
    for table, predicate in (
        ('runner_sessions', "status IN ('calling','processing','stopping')"),
        ('runner_turns', "status != 'settled'"),
        ('tool_calls', "status='reserved'"),
        ('sandbox_runs', "status NOT IN ('cleaned','reconciled')"),
        ('git_operations', "status IN ('started','unknown','uncertain')"),
    ):
        if workflow.db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
            if workflow.db.execute(f"SELECT 1 FROM {table} WHERE task IN ({marks}) AND {predicate}", ids).fetchone():
                raise WorkflowError("Unknown execution effects require reconciliation before replacement")
    return source


def replace_failed(workflow, parent, actor, failed, reason):
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 2048:
        raise WorkflowError("Provide a bounded concrete repair reason")
    with workflow._transaction():
        workflow._task(parent, actor, assigned=True)
        source = availability(workflow, parent, failed)
        # Same role/title preserves trusted selector criteria. This operation is
        # not permission to silently delete a requirement or switch acceptance.
        child = workflow._create_task(source['chat'], actor, source['assignee'], source['title'], parent=parent)
        workflow.db.execute("INSERT INTO task_retries VALUES(?,?,?,?)", (failed, child, parent, reason))
        workflow._event(parent, actor, 'child_replaced', {'failed_task': failed, 'replacement_task': child, 'reason': reason})
        return {'task_id': child, 'retry_of': failed, 'inputs': 'none; offer fresh snapshots explicitly'}
