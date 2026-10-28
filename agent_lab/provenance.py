"""Read-only snapshot provenance checks, using identity-bound broker receipts.

A matching value or conversational assertion cannot prove delivery. Historical
gateway accept results already bind artifact IDs; unbound chronology does not.
"""
import json

from .budget import descendants
from .core import WorkflowError
from .files import _parts
from .protocol import strict_json
from .recovery import active_tasks


def source_spec(text):
    try:
        spec = strict_json(text)
        if not isinstance(spec, dict) or set(spec) != {'assignee', 'title', 'path', 'allow_relay', 'require_read'}:
            raise ValueError()
        for key, maximum in [('assignee', 128), ('title', 4096)]:
            if not isinstance(spec[key], str) or not spec[key].strip() or len(spec[key]) > maximum:
                raise ValueError()
        _parts(spec['path'])
        if any(type(spec[k]) is not bool for k in ('allow_relay', 'require_read')):
            raise ValueError()
        return spec
    except (ValueError, TypeError, KeyError, RecursionError):
        raise WorkflowError('received_from requires an exact bounded source selector/path and explicit relay/read booleans') from None


def received_from(workflow, task, path, sha256, size, spec):
    """Prove a causal consumed-snapshot route and the requested target read.

    Reads records only. Never repairs historical receipts or grants access.
    """
    db = workflow.db
    if any(not db.execute('SELECT 1 FROM sqlite_master WHERE type="table" AND name=?', (name,)).fetchone()
           for name in ('artifacts', 'artifact_labels')):
        return False
    root = workflow._row('tasks', task)
    while root['parent']:
        root = workflow._row('tasks', root['parent'])
    tasks = {t['id']: t for t in active_tasks(workflow, descendants(workflow, root['id']))
             if t['state'] not in {'failed', 'cancelled'} and t['chat'] == root['chat']}
    sources = [t for t in tasks.values() if t['assignee'] == spec['assignee'] and t['title'] == spec['title']]
    if task not in tasks or len(sources) != 1 or sources[0]['id'] == task:
        return False
    source = sources[0]['id']
    marks = ','.join('?' for _ in tasks)
    events = {}
    try:
        for row in db.execute(f'SELECT * FROM events WHERE task IN ({marks}) ORDER BY sequence', tuple(tasks)):
            detail = strict_json(row['detail'])
            if not isinstance(detail, dict):
                return False
            events.setdefault((row['task'], row['kind']), []).append((row, detail))
    except (ValueError, TypeError, RecursionError):
        return False

    def matching_event(target, kind, predicate):
        found = [(row, detail) for row, detail in events.get((target, kind), []) if predicate(row, detail)]
        return found[0] if len(found) == 1 else None

    def receipt(artifact):
        target = artifact['target_task']; actor = tasks[target]['assignee']
        explicit = [(row, detail) for row, detail in events.get((target, 'artifact_received'), [])
                    if detail.get('artifact_id') == artifact['id']]
        if explicit:
            if len(explicit) != 1:
                return None
            row, detail = explicit[0]
            if row['actor'] != actor or detail.get('sha256') != sha256 or detail.get('bytes') != size:
                return None
            return row['sequence'], detail.get('path')
        # Legacy broker events lacked an artifact ID. Only an already recorded,
        # successful accept tool result with that exact ID can bind them.
        if not db.execute('SELECT 1 FROM sqlite_master WHERE name="tool_calls"').fetchone():
            return None
        found = []
        for call in db.execute('SELECT * FROM tool_calls WHERE task=? AND name="accept_artifact" AND status="succeeded"', (target,)):
            try:
                args = strict_json(call['arguments']); output = strict_json(call['result'])
                result = output['result']
                if (call['actor'] != actor or output.get('ok') is not True
                        or args.get('artifact_id') != artifact['id'] or result.get('artifact_id') != artifact['id']
                        or result.get('sha256') != sha256 or result.get('bytes') != size
                        or args.get('path') != result.get('path')):
                    continue
                event = matching_event(target, 'tool_result', lambda row, detail:
                    row['actor'] == actor and detail.get('call_id') == call['call_id']
                    and detail.get('name') == 'accept_artifact' and detail.get('status') == 'succeeded')
                if event:
                    found.append((event[0]['sequence'], result['path']))
            except (ValueError, TypeError, KeyError, RecursionError):
                return None
        return found[0] if len(found) == 1 else None

    edges = []
    for artifact in db.execute('SELECT a.*,l.path AS source_path FROM artifacts a JOIN artifact_labels l ON l.artifact=a.id '
                               'WHERE a.consumed=1 AND a.sha256=? AND a.bytes=?', (sha256, size)):
        origin, target = artifact['source_task'], artifact['target_task']
        if (origin not in tasks or target not in tasks or artifact['recipient'] != tasks[target]['assignee']):
            continue
        offer = matching_event(origin, 'artifact_offered', lambda row, detail:
            row['actor'] == tasks[origin]['assignee'] and detail.get('artifact_id') == artifact['id']
            and detail.get('target_task') == target and detail.get('sha256') == sha256)
        received = receipt(artifact)
        if offer and received and offer[0]['sequence'] < received[0]:
            edges.append((offer[0]['sequence'], received[0], origin, target, artifact['source_path'], received[1]))
    # A relay must receive the source snapshot BEFORE offering its next copy.
    reachable = {}
    for offered, accepted, origin, target, origin_path, target_path in sorted(edges):
        starts = origin == source and origin_path == spec['path']
        relays = spec['allow_relay'] and origin in reachable and reachable[origin] < offered
        if not (starts or relays):
            continue
        reachable[target] = min(reachable.get(target, accepted), accepted)
        if target != task or target_path != path:
            continue
        if not spec['require_read']:
            return True
        if any(row['actor'] == tasks[task]['assignee'] and row['sequence'] > accepted
               and detail.get('path') == path and detail.get('sha256') == sha256 and detail.get('bytes') == size
               for row, detail in events.get((task, 'file_read'), [])):
            return True
    return False
