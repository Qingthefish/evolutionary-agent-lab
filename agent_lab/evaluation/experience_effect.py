"""Describe paired memory ON/OFF outcomes without claiming causal learning.

Read-only analysis of the existing frozen-experience development protocol.
Original model responses, lessons, task text and errors are never printed.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

from ..core import WorkflowError
from ..protocol import strict_json
from .cases import parse_case
from .experience import compare_experience
from .manifest import digest

MAX_BYTES = 16 * 1024 * 1024


def _empty():
    return {'schema_version':1, 'status':'not_comparable', 'evidence_class':'unavailable',
            'benchmark_valid':False, 'authenticity_verified':False, 'model_calls':0,
            'learning_improvement_established':False, 'comparison':None, 'pairs':[],
            'outcomes':None, 'diagnostics':[],
            'interpretation':'Descriptive paired development results only. Selection is not proof of useful application. '
                             'Audit model_calls=0 refers to this reader; source usage is separate. '
                             'No artifacts, database events or provider responses are authenticated.'}


def _goal(row):
    root = next(task for task in row['workflow']['task_outcomes'] if task['parent'] is None)
    return root, row['classification'] == 'completed' and root['verified_success']


def _arm(row):
    root, success = _goal(row)
    use, usage = row['memory_use'], row['usage']
    return {'goal_verified_completed':success, 'classification':row['classification'],
            'final_duration_seconds':root['final_duration_seconds'],
            'observed_elapsed_seconds':root['elapsed_seconds'],
            'reserved_model_attempts':usage['reserved_model_attempts'],
            'reported_tokens':usage['reported_tokens'], 'unknown_usage_attempts':usage['unknown_usage_attempts'],
            'retrieved_candidate_records':use['retrievals'], 'selected_lesson_task_pairs':use['selections'],
            'assessed_lesson_task_pairs':use['assessed']}


def analyze_experience(report):
    """Revalidate evidence, then pair by replicate/case rather than arm order.

    Failed goals stay in outcome counts. Speed is compared only when both goals
    succeeded. Partial token observations never yield a token-saving estimate.
    """
    result = _empty()
    compared = compare_experience(report)
    result['comparison'] = compared
    if compared['status'] == 'not_comparable':
        result['diagnostics'] = ['comparison_unavailable']
        return result
    try:
        # Normalize tuples, reject non-finite aggregates and validate every ID
        # before exposing it, including definitions outside executed slots.
        data = strict_json(json.dumps(report, allow_nan=False))
        for definition in data['conditions']['runtime']['cases']:
            parse_case({key:value for key,value in definition.items() if key != 'source'})
        result['evidence_class'] = 'offline_fixture' if data['mode'] == 'offline_fixture' else 'live_development'
        result['status'] = compared['status']
        rows = {(row['replicate'], row['case']['id'], row['memory']):row for row in data['results']
                if row['phase'] == 'probe'}
        outcomes = dict.fromkeys(('on_only_success','off_only_success','both_succeeded','neither_succeeded'), 0)
        for replicate in range(data['conditions']['plan']['replicates']):
            for identifier in data['conditions']['plan']['probe_cases']:
                on, off = (_arm(rows[(replicate, identifier, arm)]) for arm in ('on','off'))
                if on['goal_verified_completed']:
                    outcome = 'both_succeeded' if off['goal_verified_completed'] else 'on_only_success'
                else:
                    outcome = 'off_only_success' if off['goal_verified_completed'] else 'neither_succeeded'
                outcomes[outcome] += 1
                diagnostics = []
                if not on['retrieved_candidate_records']:
                    diagnostics.append('on_no_retrieved_candidates')
                elif not on['selected_lesson_task_pairs']:
                    diagnostics.append('on_retrieved_without_selection')
                if on['selected_lesson_task_pairs'] > on['assessed_lesson_task_pairs']:
                    diagnostics.append('on_selected_use_unassessed')
                if on['selected_lesson_task_pairs'] and not on['goal_verified_completed']:
                    diagnostics.append('on_selected_but_root_not_completed')
                if on['goal_verified_completed'] and not on['selected_lesson_task_pairs']:
                    diagnostics.append('on_success_without_selection')
                attempts_delta = on['reserved_model_attempts'] - off['reserved_model_attempts']
                if attempts_delta > 0:
                    diagnostics.append('on_more_reserved_attempts')
                both_succeeded = outcome == 'both_succeeded'
                time_delta = (on['final_duration_seconds'] - off['final_duration_seconds']) if both_succeeded else None
                if time_delta is not None and time_delta > 0:
                    diagnostics.append('on_slower_successful_pair')
                usage_complete = not (on['unknown_usage_attempts'] or off['unknown_usage_attempts'])
                if not usage_complete:
                    diagnostics.append('partial_provider_usage')
                result['pairs'].append({'replicate':replicate, 'case_id':identifier,
                    'outcome':outcome, 'on':on, 'off':off, 'diagnostics':diagnostics,
                    'on_minus_off':{'reserved_model_attempts':attempts_delta,
                        'successful_goal_final_seconds':time_delta,
                        'reported_tokens':on['reported_tokens']-off['reported_tokens'] if usage_complete else None}})
        result['outcomes'] = {'planned_pairs':len(result['pairs']), **outcomes}
        if outcomes['on_only_success'] <= outcomes['off_only_success']:
            result['diagnostics'].append('no_positive_net_goal_success_difference')
        result['diagnostics'].append('training_cost_reported_separately')
        digest(result)  # Do not let sums/differences overflow JSON output.
        return result
    except (KeyError, TypeError, ValueError, AttributeError, WorkflowError, RecursionError, OverflowError):
        rejected = _empty()
        rejected['diagnostics'] = ['invalid_effect_evidence']
        return rejected


def read_experience(directory):
    """Bounded strict JSON, regular files only; never open a task database."""
    try:
        path = Path(directory) / 'experiment.json'
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                raise ValueError()
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError()
        result = analyze_experience(strict_json(raw.decode('utf-8')))
        result['source_sha256'] = hashlib.sha256(raw).hexdigest()
        return result
    except (OSError, ValueError, UnicodeError, RecursionError):
        result = _empty()
        result['diagnostics'] = ['unreadable_or_invalid_experiment']
        return result


def markdown_effect(result):
    def value(item):
        return 'unavailable' if item is None else f'{item:.4f}' if type(item) is float else str(item)

    lines = ['# Memory ON/OFF effect description', '', f"Status: `{result['status']}`.",
             f"Evidence: `{result['evidence_class']}`. Benchmark valid: `false`.",
             'Learning improvement established: `false`. Audit model calls: `0`.', '',
             result['interpretation'], '',
             'Positive deltas mean ON used more time/attempts/tokens. Tokens are provider-reported, not billing.', '',
             '| Replicate | Case | Outcome | ON−OFF attempts | ON−OFF successful seconds | ON−OFF reported tokens |',
             '| --- | --- | --- | --- | --- | --- |']
    for pair in result['pairs']:
        delta = pair['on_minus_off']
        lines.append(f"| {pair['replicate']} | {pair['case_id']} | {pair['outcome']} | "
                     f"{delta['reserved_model_attempts']} | {value(delta['successful_goal_final_seconds'])} | "
                     f"{value(delta['reported_tokens'])} |")
    lines += ['', '## Memory-use observations', '']
    for pair in result['pairs']:
        on = pair['on']
        lines.append(f"- Replicate {pair['replicate']}, {pair['case_id']}: ON retrieved "
                     f"{on['retrieved_candidate_records']} candidate records, selected "
                     f"{on['selected_lesson_task_pairs']} lesson/task pairs and assessed "
                     f"{on['assessed_lesson_task_pairs']}; {', '.join(pair['diagnostics']) or 'no diagnostic flags'}.")
    lines += ['', '## Training and planned denominators', '',
              '| Phase | Planned | Executed | Verified goals | Mean final seconds (includes failures) |',
              '| --- | --- | --- | --- | --- |']
    comparison = result['comparison'] or {}
    phases = [('Training',comparison.get('training'))]
    phases += [(arm.upper(),(comparison.get('probes') or {}).get(arm)) for arm in ('on','off')]
    for name, summary in phases:
        if summary is not None:
            lines.append(f"| {name} | {summary['planned']} | {summary['executed']} | {summary['goals_completed']} | "
                         f"{value(summary['mean_assignment_to_final_seconds'])} |")
    lines += ['', '| Phase | Reserved attempts | Known reported tokens | Unknown usage attempts |',
              '| --- | --- | --- | --- |']
    for name, summary in phases:
        if summary is not None:
            lines.append(f"| {name} | {summary['reserved_model_attempts']} | {summary['reported_tokens']} | "
                         f"{summary['unknown_usage_attempts']} |")
    lines += ['', 'Training is separate; unfinished goals have no final duration. Full counters are available in JSON.', '',
              *['- ' + reason for reason in comparison.get('reasons',[])], '',
              'Diagnostics: ' + ', '.join(result['diagnostics']) + '.', '',
              'No statistical/causal claim or official score follows from these descriptive results.']
    if 'source_sha256' in result:
        lines += ['', f"Source experiment.json SHA-256: `{result['source_sha256']}`."]
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, help='Directory containing a frozen-experience experiment.json')
    parser.add_argument('--format', choices=('json','markdown'), default='json')
    args = parser.parse_args(argv)
    result = read_experience(args.run)
    print(json.dumps(result, indent=2, allow_nan=False) if args.format == 'json' else markdown_effect(result),
          end='\n' if args.format == 'json' else '')
    return 2 if result['status'] == 'not_comparable' else 0


if __name__ == '__main__':
    raise SystemExit(main())
