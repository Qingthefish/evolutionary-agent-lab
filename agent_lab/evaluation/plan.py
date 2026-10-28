"""Versioned development run plans. Inspection never calls a model or engine.

Execution requires explicit permission and the inspected content fingerprint.
No placeholder model or credential is ever passed to the evaluator for execution.
"""
from dataclasses import asdict
import os
from pathlib import Path
import re

from ..budget import TreeLimits
from ..core import WorkflowError
from ..git_tools import load_trusted_repositories
from ..protocol import strict_json
from ..runner import Limits
from ..runtime import LiveConfig, live_members, live_roles, live_roles_for_policy
from .cases import load_cases
from .harness import Evaluator, _case_policy
from .manifest import digest


def _object(value, keys, label):
    if not isinstance(value,dict) or set(value)!=keys:
        raise WorkflowError(label+' has missing or unknown fields')
    return value


class DevelopmentPlan:
    def __init__(self, filename):
        self.filename=Path(filename).resolve()
        try:
            with self.filename.open('rb') as stream:
                raw=stream.read(262145)
            if len(raw)>262144:
                raise ValueError()
            data=strict_json(raw.decode('utf-8'))
        except (OSError,ValueError,RecursionError):
            raise WorkflowError('Cannot read a bounded, unambiguous development plan') from None
        plan_keys={'version','purpose','provider','model','api_key_env','cases','case_ids',
                   'max_output_tokens','task_limits','tree_limits','tool_calls','capabilities'}
        if isinstance(data,dict) and data.get('version')==2: plan_keys.add('socket_timeout')
        _object(data,plan_keys,'Plan')
        if type(data['version']) is not int or data['version'] not in (1,2) or data['purpose']!='development':
            raise WorkflowError('Use version-1/2 development plans; official protocol is separate')
        if data['provider'] not in ('deepseek','hkgai'):
            raise WorkflowError('Plan must use the instructor-allowed provider')
        if data['model'] is not None and (not isinstance(data['model'],str) or not data['model'].strip()):
            raise WorkflowError('Model must be null pending issue, or an explicit approved identifier')
        if not isinstance(data['api_key_env'],str) or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,127}',data['api_key_env']):
            raise WorkflowError('Plan takes a credential variable name, never a literal key')
        capability_keys={'web','memory','child_retries','docker_host','python_image','git_config'}
        if data['version']==2: capability_keys.add('collaboration')
        _object(data['capabilities'],capability_keys,'Capabilities')
        caps=data['capabilities']
        if caps['memory'] is not False:
            raise WorkflowError('Memory-enabled batch plans await a versioned cross-task/reset protocol')
        for name in ('cases',):
            if not isinstance(data[name],str) or not data[name].strip():
                raise WorkflowError('Cases must name a directory relative to the plan')
        if (not isinstance(data['case_ids'],list) or not data['case_ids']
                or any(not isinstance(i,str) for i in data['case_ids'])
                or len(set(data['case_ids']))!=len(data['case_ids'])):
            raise WorkflowError('Select a nonempty distinct development case list')
        all_cases={c.id:c for c in load_cases(self.filename.parent/data['cases'])}
        if not set(data['case_ids'])<=all_cases.keys():
            raise WorkflowError('Selected case is absent from the supplied directory')
        self.cases=[all_cases[i] for i in data['case_ids']]
        if any(c.split!='development' or c.driver!='live_scheduler' for c in self.cases):
            raise WorkflowError('Development plans require live development cases; no fixture or held-out substitution')
        # Explicit budgets, not silently inherited defaults in a later release.
        _object(data['task_limits'],set(asdict(Limits())),'Task limits')
        _object(data['tree_limits'],set(asdict(TreeLimits())),'Tree limits')
        try:
            task_limits=Limits(**data['task_limits']); tree_limits=TreeLimits(**data['tree_limits'])
        except (TypeError,ValueError):
            raise WorkflowError('Invalid development budgets') from None
        repositories=()
        if caps['git_config'] is not None:
            if not isinstance(caps['git_config'],str) or not caps['git_config'].strip():
                raise WorkflowError('Git configuration must name a trusted local file')
            repositories=tuple(load_trusted_repositories(self.filename.parent/caps['git_config']))
        if caps['python_image'] is not None and (not isinstance(caps['python_image'],str) or re.fullmatch(
                r'(?:docker.io/library/)?python(?::[A-Za-z0-9._-]+)?@sha256:[0-9a-f]{64}',caps['python_image']) is None):
            raise WorkflowError('Plan must pin an official Python image by digest')
        if caps['docker_host'] is not None and (not isinstance(caps['docker_host'],str) or not caps['docker_host'].startswith('unix:///')):
            raise WorkflowError('Plan requires an explicit local Docker Unix socket')
        self.settings=dict(model=data['model'] or 'pending-course-model',provider=data['provider'],
            max_output_tokens=data['max_output_tokens'],role_limits=task_limits,tree_limits=tree_limits,
            tool_calls=data['tool_calls'],enable_web=caps['web'],enable_memory=False,
            child_retries=caps['child_retries'],docker_host=caps['docker_host'],python_image=caps['python_image'],
            repositories=repositories)
        if data['version']==2:
            self.settings['enable_collaboration']=caps['collaboration']
            self.settings['socket_timeout']=data['socket_timeout']
        template=LiveConfig(api_key='not-used-for-plan-inspection',**self.settings)
        for case in self.cases: _case_policy(case,template)
        self.data=data
        # Include the code, independently authored cases and effective policies;
        # secret presence/values and configuration-file location are excluded.
        package=Path(__file__).resolve().parents[1]
        sources={str(p.relative_to(package)):digest(p.read_text()) for p in sorted(package.rglob('*.py'))}
        self.conditions={'plan':data,'cases':[{k:v for k,v in asdict(c).items() if k!='source'} for c in self.cases],
            'acceptance':[ _case_policy(c,template).record() for c in self.cases],
            'roles':{a:asdict(r) for a,r in live_roles(live_members(template),template).items()},
            'repositories': [asdict(r) for r in repositories], 'code_sha256':digest(sources)}
        if any(c.expected.declared_subtasks_only for c in self.cases):
            self.conditions['case_roles'] = {c.id: {a:asdict(r) for a,r in live_roles_for_policy(
                live_members(template),template,_case_policy(c,template)).items()} for c in self.cases}
        self.sha256=digest(self.conditions)

    def inspect(self):
        blockers=[]
        if self.data['model'] is None: blockers.append('Course-approved model identifier has not been configured')
        key=os.environ.get(self.data['api_key_env'])
        if not key or any(c.isspace() for c in key): blockers.append('Named model credential variable is missing or invalid')
        for repository in self.settings['repositories']:
            if repository.credential_env and not os.environ.get(repository.credential_env):
                blockers.append('A configured runtime Git credential variable is missing')
        report={'purpose':'development','model_calls':0,'benchmark_valid':False,'plan_sha256':self.sha256,
            'configured_to_attempt':not blockers,'blockers':blockers,
            'selected_cases':[c.id for c in self.cases],
            'maximum_model_attempts':len(self.cases)*self.settings['tree_limits'].model_attempts,
            'per_case_tree_limits':asdict(self.settings['tree_limits']),
            'per_case_task_limits':asdict(self.settings['role_limits']),
            'backend_checks':'Static configuration only; provider, public web, Docker image/engine and Git access are checked on use',
            'human_protocol':'Pause on real clarification/approval/review; no scripted human answers',
            'memory_protocol':'Fresh empty state per case; memory disabled; no learning comparison',
            'automatic_checks_scope':'Only declared file properties; report facts and arbitrary program correctness need independent tests/review'}
        if self.data['version']==2:
            report['provider_request_limits']={'max_output_tokens':self.settings['max_output_tokens'],
                'socket_timeout':self.settings['socket_timeout'],'automatic_retries':0}
        if self.settings.get('enable_collaboration'):
            report['collaboration_protocol']='Model chooses roles/titles/order; scoped specialist delegation/messages enabled; no external backend added'
            report['child_review_boundary']='Children without an exact predeclared criterion pause for actual trusted review; no automatic acceptance'
            report['a03_acceptance']='Inspect actual decomposition, negotiation and specialist-to-specialist delegation separately; a successful root or minimum task count alone does not establish them'
        if 'case_roles' in self.conditions:
            report['declared_child_contracts'] = {c.id: [{'assignee':s.assignee,'title':s.title}
                for s in c.expected.subtasks] for c in self.cases if c.expected.declared_subtasks_only}
            report['effective_roles']='Per-case case_roles includes opt-in task directory; roles is the base role set'
        return report

    def execute(self, *, allow_model_calls, plan_sha256, output_root):
        if allow_model_calls is not True or plan_sha256!=self.sha256:
            raise WorkflowError('Execution requires explicit model-call authorization and the current inspected plan SHA-256')
        readiness=self.inspect()
        if readiness['blockers']:
            raise WorkflowError('Plan is blocked: '+'; '.join(readiness['blockers']))
        live=LiveConfig(api_key=os.environ[self.data['api_key_env']],allow_network=True,**self.settings)
        result=Evaluator(self.cases,output_root=output_root,live=live).run([c.id for c in self.cases])
        # Record the reviewed plan alongside the evaluator's full run manifest.
        import json
        directory=Path(output_root)/result['run_id']
        (directory/'development-plan.json').write_text(json.dumps(
            {'plan_sha256':self.sha256,'conditions':self.conditions},ensure_ascii=True,indent=2)+'\n')
        return result
