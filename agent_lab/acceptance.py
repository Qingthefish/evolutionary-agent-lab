"""Data-only independent artifact checks; never execute a candidate on the host.

These prove stated file properties, not factual accuracy or program correctness.
Semantic/code acceptance still needs independent tests in a sandbox or review.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import re

from .core import WorkflowError
from .files import _parts
from .inspection import ArtifactInspector
from .protocol import strict_json


@dataclass(frozen=True)
class ArtifactRule:
    path: str
    kind: str
    expected: str | None = None
    min_bytes: int = 0
    max_bytes: int = 65536

    def __post_init__(self):
        _parts(self.path)
        if (not isinstance(self.kind,str) or self.kind not in {'exists','absent','contains','json_equals','sha256'}
                or type(self.min_bytes) is not int or type(self.max_bytes) is not int
                or not 0 <= self.min_bytes <= self.max_bytes <= 65536):
            raise WorkflowError('Supply a supported artifact criterion with byte limits up to 65536')
        if self.kind in {'exists','absent'}:
            if self.expected is not None:
                raise WorkflowError('Existence criteria do not take expected content')
        elif not isinstance(self.expected,str) or not self.expected or len(self.expected.encode('utf-8')) > 65536:
            raise WorkflowError('Content criteria require bounded independently supplied expected text')
        if self.kind == 'sha256' and not re.fullmatch('[0-9a-f]{64}',self.expected):
            raise WorkflowError('Expected digest must be lowercase SHA-256')
        if self.kind == 'json_equals':
            try:
                object.__setattr__(self,'expected',_json(strict_json(self.expected)))
            except (ValueError, RecursionError):
                raise WorkflowError('Expected JSON must be unambiguous and finite') from None

    def record(self):
        return asdict(self)


def _json(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, ensure_ascii=True, separators=(',',':'))


def normalize_rules(rules):
    if (not isinstance(rules,(tuple,list)) or len(rules)>100
            or any(not isinstance(r,ArtifactRule) for r in rules)):
        raise WorkflowError('Supply at most 100 trusted ArtifactRule objects')
    records=[_json(r.record()) for r in rules]
    if len(set(records))!=len(records):
        raise WorkflowError('Duplicate artifact criterion')
    absent={r.path for r in rules if r.kind=='absent'}
    if absent & {r.path for r in rules if r.kind!='absent'}:
        raise WorkflowError('Artifact cannot be required present and absent')
    return tuple(sorted(rules,key=lambda r:_json(r.record())))


def parse_rules(records):
    if not isinstance(records,list):
        raise WorkflowError('Artifact criteria must be an array')
    try:
        return normalize_rules(tuple(ArtifactRule(**r) for r in records))
    except (TypeError,ValueError,RecursionError):
        raise WorkflowError('Invalid artifact criteria') from None


def verify_rules(workflow, files, task, actor, rules):
    workflow._task(task,actor,assigned=True)
    inspector=ArtifactInspector(workflow,files)
    checks={}
    seen={}
    for i,rule in enumerate(rules):
        label=f'criterion:{i}:{rule.path}:{rule.kind}'
        try:
            if rule.path not in seen:
                seen[rule.path]=inspector._read(task,rule.path)
            data=seen[rule.path]
            if rule.kind=='absent':
                checks[label]=data is None
                continue
            passing=data is not None and rule.min_bytes <= len(data) <= rule.max_bytes
            if passing and rule.kind=='contains':
                passing=rule.expected in data.decode('utf-8')
            elif passing and rule.kind=='sha256':
                passing=hashlib.sha256(data).hexdigest()==rule.expected
            elif passing and rule.kind=='json_equals':
                passing=_json(strict_json(data.decode('utf-8')))==rule.expected
            checks[label]=passing
        except (WorkflowError,UnicodeError,ValueError,RecursionError):
            # Unsafe symlinks and malformed JSON are failed checks, not absence.
            checks[label]=False
    return checks
