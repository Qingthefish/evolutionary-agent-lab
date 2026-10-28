"""Read-only prerequisites for trusted received-source child contracts.

Prepare inputs before cooperative scheduling waits on a child. This does not
prove child acceptance, create a receipt, or authorize access to another task.
"""
import hashlib

from .acceptance import ArtifactRule, normalize_rules
from .core import WorkflowError
from .inspection import ArtifactInspector
from .provenance import received_from, source_spec, source_task


def normalize_inputs(requirements):
    if requirements is None:
        return ()
    if not isinstance(requirements, tuple) or not 1 <= len(requirements) <= 100:
        raise WorkflowError('Use bounded trusted delegation input requirements')
    normalized = {}
    for item in requirements:
        if (not isinstance(item, tuple) or len(item) != 3
                or any(not isinstance(v, str) or not v.strip() or len(v) > maximum
                       for v, maximum in zip(item[:2], (128, 4096)))
                or not isinstance(item[2], tuple) or not item[2]
                or any(not isinstance(r, ArtifactRule) or r.kind != 'received_from' for r in item[2])):
            raise WorkflowError('Use trusted assignee/title pairs with received_from criteria')
        pair = item[:2]
        if pair in normalized:
            raise WorkflowError('Duplicate delegation input selector')
        normalized[pair] = normalize_rules(item[2])
    return tuple((*pair, rules) for pair, rules in sorted(normalized.items()))


def input_records(requirements):
    return [{'assignee': agent, 'title': title, 'criteria': [r.record() for r in rules]}
            for agent, title, rules in requirements]


def check_inputs(workflow, files, task, actor, pair, inputs, requirements):
    rules = requirements.get(pair)
    if not rules:
        return
    row = workflow._task(task, actor, assigned=True)
    if row['state'] != 'running':
        raise WorkflowError('Only an assigned running task may prepare delegation')
    if not inputs:
        raise WorkflowError('Required source input is not prepared. Accept the declared source snapshot first, '
                            'then use delegate_with_inputs with owned paths and current SHA-256 values; no child created')
    inspector = ArtifactInspector(workflow, files)
    prepared = {}
    for path, expected in inputs.items():
        data = inspector._read(task, path)  # Task identity was checked; no file_read event or foreign access.
        if data is None or hashlib.sha256(data).hexdigest() != expected:
            raise WorkflowError('Delegation input is missing or changed; prepare the current owned snapshot first')
        prepared[path] = (expected, len(data))
    for rule in rules:
        spec = source_spec(rule.expected)
        source = source_task(workflow, task, spec)
        matched = False
        for path, (digest, size) in prepared.items():
            if not rule.min_bytes <= size <= rule.max_bytes:
                continue
            if source == task:
                matched = path == spec['path']
            elif source is not None and spec['allow_relay']:
                matched = received_from(workflow, task, path, digest, size, {**spec, 'require_read': False})
            if matched:
                break
        if not matched:
            raise WorkflowError('Required source snapshot for child path ' + rule.path +
                                ' is not prepared: accept the declared source version before delegate_with_inputs; '
                                'copied values or an unconsumed offer do not prove delivery')
