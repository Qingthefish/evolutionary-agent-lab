"""Trusted execution controls, never exposed as model tools.

Increasing an operating allowance does not accept work, reset usage, change
capabilities or reconcile uncertain external effects.
"""

from dataclasses import asdict
import hashlib
import json

from . import budget
from .core import WorkflowError
from .runner import Limits, operator_decision_failure


def _json(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def configuration_sha256(workflow, root):
    row = workflow.db.execute('SELECT config FROM scheduler_runs WHERE root=?', (root,)).fetchone()
    if row is None:
        raise WorkflowError('No configured execution exists for this root')
    return hashlib.sha256(row['config'].encode()).hexdigest()


def _inspected_transport_resends(workflow, tasks):
    """Exact failed turns with a later explicit resend decision; history stays intact."""
    released = set()
    for task in tasks:
        failures = set()
        for event in workflow.db.execute(
                "SELECT kind,detail FROM events WHERE task=? AND kind IN "
                "('provider_request_failed','provider_resend_released') ORDER BY sequence", (task,)):
            detail = json.loads(event['detail'])
            if event['kind'] == 'provider_request_failed':
                number, diagnostics = detail.get('number'), detail.get('diagnostics')
                if (type(number) is int and isinstance(diagnostics, dict) and 'kind' in diagnostics
                        and operator_decision_failure(diagnostics)):
                    failures.add(number)
            else:
                number = detail.get('after_attempt')
                if type(number) is int and number in failures:
                    released.add((task, number))
    return released


def extend_execution(workflow, root, human, *, tree_limits, roles, reason, expected_sha256,
                     plan_amendment=None):
    """Atomically extend a stopped quality run; preserve all counters/history.

    `roles` are trusted application records, not model-selected tool arguments.
    Only numeric capacities can grow. Provider, instructions, tools, delegation,
    review policy and output ceiling remain bound to the original configuration.
    """
    if not isinstance(tree_limits, budget.TreeLimits) or not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 4096:
        raise WorkflowError('Supply validated limits and a concrete extension reason')
    with workflow._transaction():
        task = workflow._task(root, human)
        stored = workflow.db.execute('SELECT * FROM scheduler_runs WHERE root=?', (root,)).fetchone()
        if (task['parent'] or task['state'] not in {'pending', 'running', 'waiting_input', 'waiting_approval'}
                or stored is None or stored['owner'] is not None
                or workflow._row('actors', human)['kind'] != 'human'):
            raise WorkflowError('Only an idle, nonterminal root can have its operating allowance extended')
        if configuration_sha256(workflow, root) != expected_sha256:
            raise WorkflowError('Reviewed execution configuration changed')
        settings = json.loads(stored['config'])
        if settings['human'] != human or not settings.get('pause_on_limits'):
            raise WorkflowError('Use the creating human and an explicitly configured quality run')
        ids = [t['id'] for t in budget.descendants(workflow, root)]
        marks = ','.join('?' for _ in ids)
        for table, predicate in (
            ('runner_sessions', "status IN ('calling','processing','stopping','provider_uncertain')"),
            ('tool_calls', "status='reserved'"),
            ('sandbox_runs', "status NOT IN ('cleaned','reconciled')"),
            ('git_operations', "status IN ('started','unknown','uncertain')"),
        ):
            if workflow.db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone() and workflow.db.execute(
                    f'SELECT 1 FROM {table} WHERE task IN ({marks}) AND {predicate}', ids).fetchone():
                raise WorkflowError('Resolve outstanding or uncertain effects before extending execution')
        if workflow.db.execute("SELECT 1 FROM sqlite_master WHERE name='runner_turns'").fetchone():
            released = _inspected_transport_resends(workflow, ids)
            for turn in workflow.db.execute(
                    f"SELECT task,number,status,response,ended FROM runner_turns WHERE task IN ({marks}) "
                    "AND status != 'settled'", ids):
                if (turn['status'] != 'provider_error' or turn['response'] is not None or turn['ended'] is None
                        or (turn['task'], turn['number']) not in released):
                    raise WorkflowError('Resolve outstanding or uncertain effects before extending execution')
        before = budget.status(workflow, root)
        after = asdict(tree_limits)
        if any(after[k] < v for k, v in before['limits'].items()) or after == before['limits']:
            raise WorkflowError('Extend capacities without reducing or resetting the original allowance')
        if set(roles) != set(settings['roles']):
            raise WorkflowError('An extension cannot add or remove roles')
        previous_roles = settings['roles']
        new_roles = {}
        for actor, role in roles.items():
            from .scheduler import Role
            if not isinstance(role, Role):
                raise WorkflowError('Supply validated application roles')
            new = json.loads(_json(asdict(role)))
            old = previous_roles[actor]
            if (not isinstance(role.limits, Limits)
                    or any(new[k] != old[k] for k in old if k not in {'limits', 'tool_calls'})
                    or new['tool_calls'] < old['tool_calls']
                    or new['limits']['repeated_outcomes'] != old['limits']['repeated_outcomes']
                    or any(new['limits'][k] < v for k, v in old['limits'].items())):
                raise WorkflowError('An extension may only increase numeric execution capacities')
            new_roles[actor] = new
        settings['roles'] = new_roles
        # Check every binding before the first mutation; transaction rollback
        # also protects an invalid optional official-plan amendment.
        runners = list(workflow.db.execute(f'SELECT * FROM runner_sessions WHERE task IN ({marks})', ids)) \
            if workflow.db.execute("SELECT 1 FROM sqlite_master WHERE name='runner_sessions'").fetchone() else []
        for row in runners:
            if json.loads(row['config'])['limits'] != previous_roles[row['actor']]['limits']:
                raise WorkflowError('A task limit binding differs from its reviewed role')
            cap = workflow.db.execute('SELECT maximum FROM tool_budgets WHERE task=?', (row['task'],)).fetchone()
            if cap is None or cap[0] != previous_roles[row['actor']]['tool_calls']:
                raise WorkflowError('A task tool allowance differs from its reviewed role')
        if plan_amendment is not None:
            old_sha, new_sha = plan_amendment
            binding = workflow.db.execute('SELECT plan_sha256 FROM official_scenario WHERE id=1').fetchone()
            if (binding is None or binding[0] != old_sha or not isinstance(new_sha, str) or len(new_sha) != 64):
                raise WorkflowError('Official plan amendment does not match the inspected prior binding')
            workflow.db.execute('UPDATE official_scenario SET plan_sha256=? WHERE id=1', (new_sha,))
        workflow.db.execute('UPDATE tree_budgets SET limits=? WHERE root=?', (_json(after), root))
        workflow.db.execute('UPDATE scheduler_runs SET config=? WHERE root=?', (_json(settings), root))
        for row in runners:
            config = json.loads(row['config'])
            config['limits'] = new_roles[row['actor']]['limits']
            # Budget pauses can resume. A stagnation pause requires its own
            # progress decision; an extension alone cannot clear it.
            status = 'ready' if row['status'] == 'budget_paused' else row['status']
            workflow.db.execute('UPDATE runner_sessions SET config=?,status=?,stop_reason=? WHERE task=?',
                (_json(config), status, None if status == 'ready' else row['stop_reason'], row['task']))
            workflow.db.execute('UPDATE tool_budgets SET maximum=? WHERE task=?',
                                (new_roles[row['actor']]['tool_calls'], row['task']))
            if row['status'] == 'budget_paused':
                workflow._event(row['task'], human, 'execution_budget_resumed', {'reason': reason})
        workflow._event(root, human, 'execution_limits_extended', {
            'reason': reason, 'old_limits': before['limits'], 'new_limits': after,
            'usage_unchanged': {k: before[k] for k in ('attempts', 'tokens', 'tool_calls')},
            'old_roles': previous_roles, 'new_roles': new_roles, 'plan_amendment': plan_amendment,
            'automatic_acceptance': False, 'effects_replayed': False})
        return {'root': root, 'budget': budget.status(workflow, root), 'model_calls': 0,
                'configuration_sha256': configuration_sha256(workflow, root)}
