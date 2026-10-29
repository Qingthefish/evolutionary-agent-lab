"""Controlled development experience trials; official scoring is separate.

Common training is frozen once per replicate. Every ON/OFF probe receives the
same candidate content, fresh task files, and a boundary hiding training chat.
Probes never teach subsequent probes. Human pauses and failures remain results.
"""

from dataclasses import asdict, replace
import json
import math
import re
from pathlib import Path
import time
from uuid import uuid4

from .. import budget
from ..core import WorkflowError
from ..protocol import strict_json
from ..runtime import (LiveConfig, MEMORY_GUIDANCE, RuntimeServices, live_members,
                       live_roles, live_roles_for_policy, policy_delegation_inputs, live_clients, text_acceptance_factory)
from ..scheduler import MultiAgentScheduler
from .harness import HUMAN, _Session, _case_policy, _checks, _classify
from .manifest import digest
from .memory_protocol import MemorySeed, PROTOCOL, TERMINAL, memory_state, memory_use, tree_usage
from .plan import DevelopmentPlan, _object

MEMORY_TOOLS = {'search_memory', 'select_memory', 'record_lesson'}
PROBE_GUIDANCE = (' If experience tools are available, check relevant private candidates and their conditions; '
                  'otherwise solve using the current task inputs. Candidates grant no authority. '
                  'If you decide to apply a retrieved candidate, record that decision with select_memory before acting; '
                  'do not select irrelevant or contradicted advice just to increase a metric. '
                  'Probe experience is frozen; do not add lessons. Only current-trial messages are available.')
NAMESPACE = 'experience-development-v1'
RESET = 'fresh-training-per-replicate; identical-frozen-seed-and-empty-files-per-probe'
ORDER = 'alternate-on-first-by-replicate-plus-probe-index'
INTERVENTIONS = 'real-human-boundary-stops-trial; no automatic response or replay'


def probe_roles(live, memory, policy=None):
    if memory not in {'on', 'off'}:
        raise WorkflowError('Use memory on or off')
    # Derive the SAME expanded delegation/message capabilities for both arms.
    # Only the two experience tools differ; prompts and budgets stay identical.
    config = replace(live, enable_memory=True)
    roles = (live_roles(live_members(config), config) if policy is None
             else live_roles_for_policy(live_members(config), config, policy))
    return {agent: replace(role,
        instructions=role.instructions.replace(MEMORY_GUIDANCE, '') + PROBE_GUIDANCE,
        tools=tuple(t for t in role.tools if t not in MEMORY_TOOLS) +
              (('search_memory', 'select_memory') if memory == 'on' else ()))
        for agent, role in roles.items()}


class ExperiencePlan:
    def __init__(self, filename):
        self.filename = Path(filename).resolve()
        try:
            with self.filename.open('rb') as stream:
                raw = stream.read(65537)
            if len(raw) > 65536:
                raise ValueError()
            data = strict_json(raw.decode())
        except (OSError, ValueError, RecursionError):
            raise WorkflowError('Invalid bounded experience plan') from None
        _object(data, {'version','purpose','protocol','runtime_plan','training_cases','probe_cases','replicates'}, 'Experience plan')
        if (type(data['version']) is not int or data['version'] != 1
                or data['purpose'] != 'development-memory-comparison' or data['protocol'] != PROTOCOL
                or type(data['replicates']) is not int or not 1 <= data['replicates'] <= 10
                or not isinstance(data['runtime_plan'], str) or not data['runtime_plan'].strip()):
            raise WorkflowError('Use the versioned development protocol and 1–10 explicit replicates')
        for label in ('training_cases', 'probe_cases'):
            ids = data[label]
            if (not isinstance(ids, list) or not 1 <= len(ids) <= 20
                    or any(not isinstance(i,str) for i in ids) or len(set(ids)) != len(ids)):
                raise WorkflowError('Select distinct nonempty bounded training/probe case lists')
        self.runtime = DevelopmentPlan(self.filename.parent / data['runtime_plan'])
        cases = {c.id:c for c in self.runtime.cases}
        training, probes = data['training_cases'], data['probe_cases']
        if set(training) & set(probes) or set(training + probes) != cases.keys():
            raise WorkflowError('Training and probe IDs must be disjoint and exactly cover the declared runtime cases')
        if self.runtime.settings['repositories']:
            raise WorkflowError('Experience trials cannot share mutable Git repositories; no reset protocol is implemented for them')
        if (any(c.control or c.approval or c.human_responses for c in cases.values())
                or any(cases[i].expected.final_state != 'succeeded' for i in probes)):
            raise WorkflowError('Experience trials require positive development cases without scripted human responses')
        self.training, self.probes = [cases[i] for i in training], [cases[i] for i in probes]
        self.data = data
        template = LiveConfig(api_key='not-used-for-inspection', **self.runtime.settings)
        self.conditions = {'protocol':PROTOCOL, 'plan':data, 'runtime':self.runtime.conditions,
            'probe_roles':{arm:{a:asdict(r) for a,r in probe_roles(template,arm).items()} for arm in ('on','off')},
            'reset':RESET, 'order':ORDER, 'interventions':INTERVENTIONS,
            'training_cost':'record separately; never silently amortize or discard',
            'official_evaluation':False}
        if any(c.expected.declared_subtasks_only for c in self.runtime.cases):
            training_config = replace(template, enable_memory=True, memory_namespace=NAMESPACE)
            self.conditions['case_training_roles'] = {c.id: {a:asdict(r) for a,r in live_roles_for_policy(
                live_members(training_config), training_config, _case_policy(c, training_config)).items()} for c in self.training}
            self.conditions['case_probe_roles'] = {c.id: {arm: {a:asdict(r) for a,r in probe_roles(
                template, arm, _case_policy(c, template)).items()} for arm in ('on','off')} for c in self.probes}
        self.sha256 = digest(self.conditions)

    def inspect(self):
        ready = self.runtime.inspect()
        count = self.data['replicates'] * (len(self.training) + 2 * len(self.probes))
        return {**ready, 'plan_sha256':self.sha256, 'memory_protocol':PROTOCOL,
                'planned_training_tasks':self.data['replicates'] * len(self.training),
                'planned_probe_tasks':self.data['replicates'] * 2 * len(self.probes),
                'maximum_model_attempts':count * self.runtime.settings['tree_limits'].model_attempts,
                'memory_comparison':'Frozen observed candidate experience; only ON has search/select tools; no probe-to-probe learning',
                'reset':self.conditions['reset'], 'single_multi_comparison':'not part of this protocol'}

    def execute(self, *, allow_model_calls, plan_sha256, output_root):
        if allow_model_calls is not True or plan_sha256 != self.sha256:
            raise WorkflowError('Authorize model calls and provide the current inspected experience-plan fingerprint')
        if self.inspect()['blockers']:
            raise WorkflowError('Experience plan blocked: ' + '; '.join(self.inspect()['blockers']))
        import os
        live = LiveConfig(api_key=os.environ[self.runtime.data['api_key_env']], allow_network=True,
                          **self.runtime.settings)
        return ExperienceTrial(self, LiveExperienceDriver(live)).run(output_root)


class LiveExperienceDriver:
    mode = 'live'

    def __init__(self, live):
        if not isinstance(live, LiveConfig) or live.enable_memory or live.repositories:
            raise WorkflowError('Experience driver requires explicit memory-off base configuration without shared Git repositories')
        self.live = live

    def config(self, phase):
        return replace(self.live, enable_memory=phase == 'training', memory_namespace=NAMESPACE)

    def clients(self, roles, stage):
        config = self.config(stage['phase'])
        return live_clients(config, roles)

    def scheduler(self, session, root, case, stage, floor):
        config = self.config(stage['phase'])
        if session.services is None:
            session.services = RuntimeServices(session.workflow, session.files, config,
                memory=session.memory if config.enable_memory else None)
        policy = _case_policy(case, config)
        roles = (live_roles_for_policy(live_members(config), config, policy) if stage['phase'] == 'training'
                 else probe_roles(config, stage['memory'], policy))
        return MultiAgentScheduler(session.workflow, session.files, root, human=HUMAN, roles=roles,
            clients=self.clients(roles, stage), mode=self.mode, constraints=list(policy.constraints),
            verifier_factory=text_acceptance_factory(session.workflow, session.files, root, policy),
            acceptance_id=policy.acceptance_id, limits=config.tree_limits, memory=session.memory,
            executor=session.services.executor, retrieval=session.services.retrieval,
            capture_memory=stage['phase'] == 'training', child_retries=config.child_retries,
            message_floor=floor,
            delegation_rules=tuple((r.assignee,r.title) for r in policy.child_rules) if policy.declared_subtasks_only else None,
            delegation_inputs=policy_delegation_inputs(policy))


def _slots(plan):
    result = []
    for rep in range(plan.data['replicates']):
        for case in plan.training:
            result.append({'replicate':rep,'phase':'training','memory':'collect','case':case.summary()})
        for index, case in enumerate(plan.probes):
            for arm in (('on','off') if (rep+index)%2 == 0 else ('off','on')):
                result.append({'replicate':rep,'phase':'probe','memory':arm,'case':case.summary()})
    for i, item in enumerate(result):
        item.update(slot=i, status='not_run', classification='not_run', workflow=None,
                    duration_seconds=None, error=None, memory_before=None, memory_after=None,
                    memory_use=None, usage=None, root=None)
    return result


class ExperienceTrial:
    def __init__(self, plan, driver):
        if not isinstance(plan,ExperiencePlan) or not isinstance(driver,LiveExperienceDriver):
            raise WorkflowError('Use a versioned experience plan and an explicitly typed driver')
        expected = LiveConfig(api_key=driver.live.api_key, allow_network=driver.live.allow_network, **plan.runtime.settings)
        if driver.live != expected or driver.mode not in {'live','offline_fixture'}:
            raise WorkflowError('Driver configuration differs from the inspected plan')
        self.plan, self.driver = plan, driver

    def run(self, output_root):
        run_id = time.strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:6]
        directory = Path(output_root).resolve() / run_id
        directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        report = {'schema_version':1,'protocol':PROTOCOL,'run_id':run_id,'mode':self.driver.mode,
                  'benchmark_valid':False,'model_calls':0 if self.driver.mode == 'offline_fixture' else None,
                  'conditions':self.plan.conditions,'conditions_sha256':self.plan.sha256,
                  'started':time.time(),'ended':None,'seeds':{},'results':_slots(self.plan)}
        self.directory, self.report = directory, report
        self.save()
        cases = {c.id:c for c in [*self.plan.training,*self.plan.probes]}
        for rep in range(self.plan.data['replicates']):
            records = [r for r in report['results'] if r['replicate'] == rep]
            session = None
            try:
                path = directory / f'replicate-{rep}'
                path.mkdir(mode=0o700)
                training_dir = path / 'training'
                training_dir.mkdir(mode=0o700)
                session = _Session(training_dir, NAMESPACE)
                for agent in live_members(self.driver.live):
                    session.workflow.register_actor(agent,'agent')
                chat = session.workflow.create_chat('group',[HUMAN,*live_members(self.driver.live)])
                roots = []
                for record in (r for r in records if r['phase'] == 'training'):
                    self.stage(session, chat, cases[record['case']['id']], record, floor=0)
                    roots.append(record['root'])
                    if record['workflow'] is None or record['workflow']['root_state'] not in TERMINAL:
                        raise WorkflowError('Training stopped before a known terminal outcome; dependent probes remain not run')
                seed = MemorySeed.freeze(session, path / 'seed', chat, roots)
                report['seeds'][str(rep)] = seed.info
                session.close(); session = None
                self.save()
                for record in (r for r in records if r['phase'] == 'probe'):
                    probe = None
                    record['seed_sha256'] = digest(seed.info)
                    try:
                        probe = seed.fork(path / f"probe-{record['slot']}-{record['memory']}")
                        self.stage(probe, chat, cases[record['case']['id']], record, floor=seed.info['message_floor'])
                    except Exception as error:
                        record.update(status='executed',classification='driver_error',error=_error(error))
                        self.save()
                    finally:
                        if probe is not None: probe.close()
            except Exception as error:
                report.setdefault('replicate_errors',{})[str(rep)] = _error(error)
                self.save()
            finally:
                if session is not None: session.close()
        report['ended'] = time.time()
        report['comparison'] = compare_experience(report)
        self.save()
        return report

    def stage(self, session, chat, case, record, *, floor):
        started = time.monotonic()
        record.update(status='running', memory_before=memory_state(session.workflow,session.memory,chat), message_floor=floor)
        self.save()  # Persist intent before provider/tool effects; never auto-resume a lost turn.
        try:
            root = session.workflow.create_task(chat,HUMAN,'coordinator',case.goal)
            record['root'] = root
            self.save()
            scheduler = self.driver.scheduler(session,root,case,record,floor)
            state = scheduler.run()
            if record['phase'] == 'probe':
                for task in budget.descendants(session.workflow,root):
                    if task['state'] in TERMINAL:
                        session.memory.assess_selected(task['id'],task['assignee'])
            duration = time.monotonic()-started
            checks, workflow = _checks(case,session,root,duration)
            record.update(status='executed',classification=_classify(case,checks,workflow),
                          checks=checks, workflow=workflow,driver_state=state['state'])
        except Exception as error:
            record.update(status='executed', classification='driver_error', error=_error(error))
        finally:
            record['duration_seconds'] = time.monotonic()-started
            record['memory_after'] = memory_state(session.workflow,session.memory,chat)
            if record['root'] is not None:
                record['usage'] = tree_usage(session.workflow,record['root'])
                record['memory_use'] = memory_use(session.workflow,record['root'])
            self.save()

    def save(self):
        temporary = self.directory / 'experiment.json.tmp'
        temporary.write_text(json.dumps(self.report,ensure_ascii=True,sort_keys=True,indent=2)+'\n')
        temporary.replace(self.directory / 'experiment.json')
        (self.directory / 'report.md').write_text(experience_markdown(self.report))


def _error(error):
    # Never serialize arbitrary provider exception text or response bodies.
    return str(error)[:500] if isinstance(error,WorkflowError) else type(error).__name__ + ': driver/setup failed; inspect retained state'


def trial_summary(records):
    goals = [next((t for t in (r.get('workflow') or {}).get('task_outcomes',[]) if t['parent'] is None),None) for r in records]
    completed = sum(r['classification']=='completed' and bool(g and g['verified_success']) for r,g in zip(records,goals))
    final_times = [g['final_duration_seconds'] for g in goals if g and g['final_duration_seconds'] is not None]
    subtasks = [t for r in records for t in (r.get('workflow') or {}).get('task_outcomes',[]) if t['parent'] is not None]
    return {'planned':len(records),'executed':sum(r['status']=='executed' for r in records),
            'not_run':sum(r['status']!='executed' for r in records),'goals_completed':completed,
            'goal_completion_rate':completed/len(records) if records else None,
            'mean_assignment_to_final_seconds':sum(final_times)/len(final_times) if final_times else None,
            'finalized':len(final_times),'missing_workflow':sum(g is None for g in goals),
            'subtasks_observed':len(subtasks),'subtasks_verified_completed':sum(t['verified_success'] for t in subtasks),
            'subtask_completion_rate':sum(t['verified_success'] for t in subtasks)/len(subtasks) if subtasks else None,
            'human_wait_seconds':sum(t['human_wait_seconds'] for t in [*subtasks,*(g for g in goals if g)]),
            'observed_driver_seconds':sum(r['duration_seconds'] or 0 for r in records),
            **{key:sum((r.get('usage') or {}).get(key,0) for r in records)
               for key in ('reserved_model_attempts','unknown_usage_attempts','reported_tokens','tool_calls')}}


def compare_experience(report):
    """Recompute metrics and reject changed seeds, conditions or missing trials.

    Metadata fingerprints detect accidental edits, not forged experiments.
    Scripted execution is never promoted to live learning/performance evidence.
    """
    try:
        data = json.loads(json.dumps(report, allow_nan=False))
        conditions = data['conditions']
        if (type(data['schema_version']) is not int or data['schema_version'] != 1
                or data['protocol'] != PROTOCOL or conditions['protocol'] != PROTOCOL
                or data['conditions_sha256'] != digest(conditions)
                or data['mode'] not in {'live','offline_fixture'} or data['benchmark_valid'] is not False):
            raise ValueError('Missing, changed or unsupported experiment conditions')
        if (conditions['reset'] != RESET or conditions['order'] != ORDER
                or conditions['interventions'] != INTERVENTIONS or conditions['official_evaluation'] is not False
                or (data['mode']=='offline_fixture' and data['model_calls'] != 0)):
            raise ValueError('Reset, intervention or evidence mode differs from this protocol')
        plan = conditions['plan']
        if (plan['purpose'] != 'development-memory-comparison' or plan['protocol'] != PROTOCOL
                or type(plan['replicates']) is not int or not 1 <= plan['replicates'] <= 10):
            raise ValueError('Unsupported replicate/protocol declaration')
        definitions = {c['id']:c for c in conditions['runtime']['cases']}
        training, probes = plan['training_cases'], plan['probe_cases']
        if (not training or not probes or set(training)&set(probes)
                or len(set(training+probes)) != len(training+probes)
                or set(training+probes) != definitions.keys()):
            raise ValueError('Training/probe case inventory changed')
        _validate_roles(conditions['probe_roles'])
        if 'case_probe_roles' in conditions:
            if set(conditions['case_probe_roles']) != set(probes) or set(conditions.get('case_training_roles', {})) != set(training):
                raise ValueError('Per-case experience roles differ from the declared inventory')
            for arms in conditions['case_probe_roles'].values():
                _validate_roles(arms)
        expected = []
        for rep in range(plan['replicates']):
            expected.extend((rep,'training','collect',i) for i in training)
            for index, identifier in enumerate(probes):
                expected.extend((rep,'probe',arm,identifier) for arm in
                                (('on','off') if (rep+index)%2 == 0 else ('off','on')))
        rows = data['results']
        if len(rows) != len(expected):
            raise ValueError('Planned trials are missing or duplicated')
        reasons = []
        for slot,(row,identity) in enumerate(zip(rows,expected)):
            if row['slot'] != slot or (row['replicate'],row['phase'],row['memory'],row['case']['id']) != identity:
                raise ValueError('Trial order, condition or case changed')
            defined = definitions[row['case']['id']]
            for field in ('id','title','goal','driver','split','control','expected','constraints'):
                if row['case'][field] != defined[field]:
                    raise ValueError('Executed case content differs from the inspected plan')
            if row['status'] not in {'executed','not_run','running'}:
                raise ValueError('Invalid execution status')
            if row['status'] != 'executed':
                reasons.append(f"slot {slot}: planned trial not completed")
                continue
            _nonnegative(row['duration_seconds'])
            workflow = row['workflow']
            if workflow is None:
                if row['classification'] != 'driver_error':
                    raise ValueError('Missing workflow without a recorded setup/driver failure')
                reasons.append(f"slot {slot}: missing execution evidence")
                continue
            outcomes = workflow['task_outcomes']
            roots = [t for t in outcomes if t['parent'] is None]
            if len(roots) != 1 or roots[0]['task_id'] != row['root'] or workflow['root_task'] != row['root']:
                raise ValueError('Missing/ambiguous current-trial root')
            for task in outcomes:
                if type(task['verified_success']) is not bool:
                    raise ValueError('Task success must be a recorded Boolean')
                if task['state'] not in TERMINAL|{'pending','running','waiting_input','waiting_approval'}:
                    raise ValueError('Unknown task state')
                if task['verified_success'] and task['state'] != 'succeeded':
                    raise ValueError('A failed/unfinished task cannot count as verified success')
                for name in ('elapsed_seconds','human_wait_seconds'):
                    _nonnegative(task[name])
                if task['final_duration_seconds'] is not None:
                    _nonnegative(task['final_duration_seconds'])
                if (task['state'] in TERMINAL) != (task['final_duration_seconds'] is not None):
                    raise ValueError('Terminal timing evidence is missing or inconsistent')
            checks = row['checks']
            if not checks or any(type(v) is not bool for v in checks.values()):
                raise ValueError('Independent acceptance checks are missing or malformed')
            from .cases import parse_case
            # Reparse the recorded case so malformed expected criteria cannot
            # silently change the failure classification.
            recorded_case = parse_case({k:v for k,v in defined.items() if k != 'source'})
            if _classify(recorded_case,checks,workflow) != row['classification']:
                raise ValueError('Result classification disagrees with independent checks')
            if row['classification'] == 'completed' and defined['expected']['final_state'] == 'succeeded' and not roots[0]['verified_success']:
                raise ValueError('Accepted goal lacks trusted completion evidence')
            if not isinstance(workflow['observed_models'],list) or any(not isinstance(m,str) or not m for m in workflow['observed_models']):
                raise ValueError('Observed provider identity is malformed')
            for value in row['usage'].values(): _nonnegative(value,integer=True)
            if row['usage']['unknown_usage_attempts'] > row['usage']['reserved_model_attempts']:
                raise ValueError('Unknown usage count exceeds reserved attempts')
            if row['phase'] == 'probe':
                seed = data['seeds'].get(str(row['replicate']))
                if seed is None:
                    raise ValueError('Probe has no frozen training seed')
                _validate_seed(seed)
                if (row['seed_sha256'] != digest(seed) or row['memory_before'] != seed['memory']
                        or row['memory_after'] != seed['memory'] or row['message_floor'] != seed['message_floor']):
                    raise ValueError('Seed, reset boundary or frozen candidate content differs')
                use = row['memory_use']
                for name in ('retrievals','selections','assessed'): _nonnegative(use[name],integer=True)
                if (use['selections'] != len(use['uses']) or use['selections'] > use['retrievals']
                        or use['assessed'] != sum(u['outcome'] is not None for u in use['uses'])):
                    raise ValueError('Memory use counts lack matching evidence')
                by_id = {t['task_id']:t for t in outcomes}
                for entry in use['uses']:
                    if (entry['task'] not in by_id or entry['owner'] != entry['assignee']
                            or entry['namespace'] != seed['namespace'] or entry['chat'] != seed['chat']
                            or (entry['outcome'] is not None and entry['outcome'] != by_id[entry['task']]['state'])):
                        raise ValueError('Selected-use outcome differs from actual probe task')
                if row['memory'] == 'off' and (use['retrievals'] or use['selections']):
                    raise ValueError('Memory-off arm exercised experience tools')
        for rep in range(plan['replicates']):
            seed = data['seeds'].get(str(rep))
            if seed is None:
                reasons.append(f"replicate {rep}: training seed unavailable")
                continue
            _validate_seed(seed)
            source_rows = [r for r in rows if r['replicate']==rep and r['phase']=='training']
            if seed['training_roots'] != [r['root'] for r in source_rows]:
                raise ValueError('Seed source roots differ from recorded training')
            for identifier in probes:
                pair = [r for r in rows if r['replicate']==rep and r['phase']=='probe' and r['case']['id']==identifier]
                observed = [(r['workflow'] or {}).get('observed_models',[]) for r in pair]
                if data['mode']=='live' and (not all(observed) or sorted(observed[0]) != sorted(observed[1])):
                    reasons.append('Paired observed provider identities are missing or differ')
        training_summary = trial_summary([r for r in rows if r['phase']=='training'])
        arms = {arm:trial_summary([r for r in rows if r['phase']=='probe' and r['memory']==arm]) for arm in ('on','off')}
        exercised = any((r.get('memory_use') or {}).get('selections',0) for r in rows if r['memory']=='on')
        if data['ended'] is None: reasons.append('Trial is still running or interrupted')
        status = ('not_comparable' if reasons else 'engineering_only' if data['mode']=='offline_fixture'
                  else 'compared' if exercised else 'not_exercised')
        return {'status':status,'reasons':sorted(set(reasons)),'training':training_summary,'probes':arms,
                'memory_exercised':exercised,'learning_improvement_established':False,
                'note':'Development paired trials only; no causal claim. Training cost is separate, failures and unrun trials stay in denominators. '
                       'Known token usage is not exact billing. Fingerprints do not authenticate experimental evidence.'}
    except (KeyError,TypeError,ValueError,AttributeError,WorkflowError,RecursionError,OverflowError):
        return {'status':'not_comparable','reasons':['Missing, malformed or mismatched plan/seed/result evidence'],
                'learning_improvement_established':False}


def _nonnegative(value, *, integer=False):
    if (type(value) not in ((int,) if integer else (int,float)) or not math.isfinite(value) or value < 0):
        raise ValueError('Counts and timing must be finite and nonnegative')


def _validate_roles(arms):
    if set(arms) != {'on','off'} or not arms['on'] or arms['on'].keys() != arms['off'].keys():
        raise ValueError('Paired roles differ')
    for agent,on in arms['on'].items():
        off = arms['off'][agent]
        if (len(set(on['tools'])) != len(on['tools']) or len(set(off['tools'])) != len(off['tools'])
                or set(off['tools']) & MEMORY_TOOLS or set(on['tools']) & MEMORY_TOOLS != {'search_memory','select_memory'}):
            raise ValueError('Unexpected memory tools')
        normalized = dict(on)
        normalized['tools'] = [t for t in on['tools'] if t not in MEMORY_TOOLS]
        if normalized != off:
            raise ValueError('Non-memory tools, role prompts or budgets differ')


def _validate_seed(seed):
    memory = seed['memory']
    if (seed['protocol'] != PROTOCOL or seed['namespace'] != NAMESPACE
            or seed['files'] != 'fresh-empty-per-probe' or seed['authorization'] != 'new-task-scoped; none inherited'):
        raise ValueError('Unsupported reset/authorization boundary')
    for key in ('database_sha256',):
        if not re.fullmatch('[0-9a-f]{64}',seed[key]): raise ValueError('Missing seed fingerprint')
    if not re.fullmatch('[0-9a-f]{64}',memory['content_sha256']): raise ValueError('Missing candidate fingerprint')
    for key in ('lessons','active','retired','sources'): _nonnegative(memory[key],integer=True)
    _nonnegative(seed['message_floor'],integer=True)
    if not memory['active'] or memory['active']+memory['retired'] != memory['lessons'] or memory['sources'] < memory['lessons']:
        raise ValueError('No valid scoped candidate experience')


def experience_markdown(report):
    lines = [f"# Development experience trial — {report['run_id']}",'',
             f"- Mode: `{report['mode']}`; benchmark valid: `false`.",
             '- Frozen candidates are observations, not proven repairs or authorization.',
             '- Training cost is separate. Missing/blocked tasks stay in the planned denominator.',
             '- Human boundaries stop a trial; no scripted replies or automatic replay.',
             '', '| Replicate | Phase | Memory | Case | Status | Outcome |', '| --- | --- | --- | --- | --- | --- |']
    for r in report['results']:
        lines.append(f"| {r['replicate']} | {r['phase']} | {r['memory']} | {r['case']['id']} | {r['status']} | {r['classification']} |")
    lines += ['', '## Evidence', '', '```json', json.dumps(report.get('comparison',{}),indent=2), '```','',
              'No learning gain, model performance or official score follows from a scripted engineering fixture.']
    return '\n'.join(lines)+'\n'
