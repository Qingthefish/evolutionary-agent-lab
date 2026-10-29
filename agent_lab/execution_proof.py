"""Read-only evidence that a current artifact came from an isolated Python job.

This proves the recorded execution/import, not arbitrary program correctness.
Independent content/behavior expectations remain separate trusted criteria.
"""
import hashlib
import json
import re

from .core import WorkflowError
from .files import _parts
from .inspection import ArtifactInspector
from .protocol import strict_json
from .sandbox import SandboxLimits


def execution_spec(text):
    try:
        spec = strict_json(text)
        if not isinstance(spec, dict) or set(spec) != {'entrypoint', 'arguments', 'inputs'}:
            raise ValueError()
        if (not isinstance(spec['inputs'], list) or not 1 <= len(spec['inputs']) <= 20
                or not isinstance(spec['arguments'], list) or len(spec['arguments']) > 16
                or any(not isinstance(a, str) or len(a) > 1024 or '\0' in a for a in spec['arguments'])):
            raise ValueError()
        for path in [spec['entrypoint'], *spec['inputs']]:
            _parts(path)
            if len(path) > 512:
                raise ValueError()
            path.encode('utf-8')
        for argument in spec['arguments']:
            argument.encode('utf-8')
        if len(set(spec['inputs'])) != len(spec['inputs']) or spec['entrypoint'] not in spec['inputs']:
            raise ValueError()
        return {**spec, 'inputs': sorted(spec['inputs'])}
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise WorkflowError('sandbox_output requires bounded entrypoint/arguments and distinct input paths including the entrypoint') from None


def sandbox_output(workflow, files, task, actor, path, digest, size, spec):
    workflow._task(task, actor, assigned=True)
    db = workflow.db
    if not db.execute('SELECT 1 FROM sqlite_master WHERE type="table" AND name="sandbox_runs"').fetchone():
        return False
    inspector = ArtifactInspector(workflow, files)
    current = {}
    for source in spec['inputs']:
        data = inspector._read(task, source)
        if data is None:
            return False
        current[source] = hashlib.sha256(data).hexdigest()
    try:
        for row in db.execute('SELECT * FROM sandbox_runs WHERE task=? AND actor=? ORDER BY rowid DESC', (task, actor)):
            result = strict_json(row['result']) if row['result'] else None
            inputs = strict_json(row['inputs'])
            if not isinstance(result, dict) or not isinstance(inputs, dict) or not isinstance(result.get('job'), dict):
                return False  # Historical unbound job evidence cannot certify this new rule.
            job = result['job']
            if set(job) != {'entrypoint', 'arguments', 'outputs'}:
                return False
            recorded = execution_spec(json.dumps({'entrypoint': job['entrypoint'], 'arguments': job['arguments'], 'inputs': list(inputs)}))
            if any(not isinstance(v, str) or not re.fullmatch('[0-9a-f]{64}', v) for v in inputs.values()):
                return False
            if (job['entrypoint'] != spec['entrypoint'] or job['arguments'] != spec['arguments']
                    or recorded['inputs'] != spec['inputs']):
                continue
            # Use the latest matching assignment, including its failures; never
            # select an older successful run to conceal a later failed check.
            config = strict_json(row['config'])
            execution = result.get('execution')
            exported = strict_json(row['exported']) if row['exported'] else None
            if (row['status'] not in {'cleaned', 'reconciled'} or row['ended'] is None
                    or result.get('run_id') != row['id'] or result.get('process_sandbox') is not True
                    or result.get('cleanup_confirmed') is not True or inputs != current
                    or not isinstance(execution, dict) or type(execution.get('exit_code')) is not int
                    or execution['exit_code'] != 0 or execution.get('interrupted', 'missing') is not None
                    or not isinstance(config, dict) or result.get('configuration') != config
                    or set(config) != {'backend', 'image', 'limits', 'network', 'host_mounts', 'payload_uid', 'supervisor_uid'}
                    or config.get('backend') != 'docker_python_v1' or config.get('network') != 'none'
                    or config.get('host_mounts') is not False
                    or config.get('payload_uid') != 65534 or config.get('supervisor_uid') != 65533
                    or not isinstance(config.get('image'), str)
                    or not re.fullmatch(r'(?:docker.io/library/)?python(?::[A-Za-z0-9._-]+)?@sha256:[0-9a-f]{64}', config['image'])
                    or not isinstance(job['outputs'], list) or not 1 <= len(job['outputs']) <= 8
                    or any(not isinstance(p, str) for p in job['outputs'])
                    or len(set(job['outputs'])) != len(job['outputs']) or path not in job['outputs']
                    or set(job['outputs']) & inputs.keys()
                    or not isinstance(exported, dict) or set(exported) != set(job['outputs'])
                    or not isinstance(result.get('export_sha256'), dict)
                    or set(result['export_sha256']) != set(exported)):
                return False
            SandboxLimits(**config['limits'])
            for output, text in exported.items():
                _parts(output)
                if (not isinstance(text, str) or len(text.encode('utf-8')) > 65536
                        or hashlib.sha256(text.encode('utf-8')).hexdigest() != result['export_sha256'][output]):
                    return False
            data = exported[path].encode('utf-8')
            if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
                return False
            events = []
            for event in db.execute('SELECT * FROM events WHERE task=? ORDER BY sequence', (task,)):
                detail = strict_json(event['detail'])
                if not isinstance(detail, dict):
                    return False
                if detail.get('run_id') == row['id']:
                    events.append((event, detail))
            reserved = [(e, d) for e, d in events if e['kind'] == 'sandbox_reserved']
            stopped = [(e, d) for e, d in events if e['kind'] in {'sandbox_stopped', 'sandbox_cleanup_reconciled'}
                       and d.get('cleanup_confirmed') is True]
            imports = [(e, d) for e, d in events if e['kind'] == 'sandbox_artifact_imported' and d.get('path') == path]
            if len(reserved) != 1 or not stopped or len(imports) != 1:
                return False
            start, start_detail = reserved[0]; imported, detail = imports[0]
            return (start['actor'] == actor and start_detail.get('inputs') == inputs
                    and imported['actor'] == actor and detail.get('sha256') == digest
                    and type(detail.get('bytes')) is int and detail['bytes'] == size
                    and any(e['actor'] == actor and start['sequence'] < e['sequence'] < imported['sequence'] for e, _ in stopped))
    except (WorkflowError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return False
    return False
