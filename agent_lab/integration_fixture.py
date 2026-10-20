"""One combined engineering fixture: synthetic model, actual optional web/Docker/Git.

The fixed script is deliberately not a live-model fallback or benchmark.
Only the disposable local Git remote is used; no GitHub credential is provisioned.
"""

import hashlib
import json

from .core import Workflow, WorkflowError
from .deepseek import DeepSeekClient
from .files import FileTools
from .inspection import ArtifactInspector
from .memory import ExperienceMemory
from .offline_scenarios import (DEMO_BRANCH, DEMO_REMOTE, DEMO_REPOSITORY,
                                demo_repository_config, prepare_demo_repository)
from .runtime import LiveConfig, RuntimeServices, live_members, live_roles
from .scheduler import MultiAgentScheduler

SOURCE = 'https://docs.python.org/3.12/library/tempfile.html'
EXPECTED = '{"agents": 1, "hello": 2}\n'
SAMPLE = 'Hello hello Agents!\n'
CODE = '''from pathlib import Path
import collections, json, re
source = Path('sources/tempfile.md').read_text()
assert 'TemporaryDirectory' in source
counts = collections.Counter(re.findall(r'[a-z]+', Path('sample.txt').read_text().lower()))
assert counts == {'hello': 2, 'agents': 1}
assert collections.Counter(re.findall(r'[a-z]+', ''.lower())) == {}
Path('result.txt').write_text(json.dumps(dict(counts), sort_keys=True) + '\\n')
'''


def _hash(text):
    return hashlib.sha256(text.encode()).hexdigest()


class CombinedFixture:
    def __init__(self, with_web):
        self.with_web = with_web

    def __call__(self, payload):
        request = json.loads(payload)
        context = json.loads(request['messages'][1]['content'])
        actor = context['role']['agent']
        stage = sum(m['role'] == 'assistant' for m in request['messages'])
        calls = []
        serial = 0
        def call(name, args):
            nonlocal serial
            serial += 1
            return {'id':f'combined-{stage}-{serial}-{name}', 'type':'function',
                    'function':{'name':name,'arguments':json.dumps(args)}}
        def envelopes(kind):
            return [json.loads(m['content']) for m in request['messages'] if m['role']=='user'
                    and json.loads(m['content']).get('kind')==kind]
        def latest_tool():
            return next(json.loads(m['content'])['result'] for m in reversed(request['messages'])
                        if m['role']=='tool' and json.loads(m['content']).get('ok'))
        if context['global_goal'].startswith('Reuse scoped'):
            if stage == 0: calls=[call('search_memory',{'query':'text counter newline','limit':5})]
            elif stage == 1:
                candidates=latest_tool()
                if not candidates: raise WorkflowError('Combined fixture found no scoped experience')
                calls=[call('select_memory',{'memory_id':candidates[0]['memory_id']})]
            elif stage == 2: calls=[call('create_text',{'path':'reuse.txt','content':'Scoped candidate considered; causality unproven.\n'})]
        elif actor == 'coordinator':
            if stage == 0: calls=[call('delegate_task',{'assignee':'researcher','title':'Retrieve cited Python documentation'})]
            elif stage in (1,4):
                child=envelopes('child_task_result')[-1]
                offer=child['offered_artifacts'][0]
                calls=[call('accept_artifact',{'artifact_id':offer['artifact_id'],'path':offer['source_path']})]
            elif stage == 2: calls=[call('create_text',{'path':'sample.txt','content':SAMPLE})]
            elif stage == 3:
                source_result = next(json.loads(m['content'])['result'] for m in request['messages']
                                     if m['role']=='tool' and json.loads(m['content']).get('ok')
                                     and json.loads(m['content'])['result'].get('path')=='sources/tempfile.md')
                calls=[call('delegate_with_inputs',{'assignee':'coder','title':'Implement and execute text counter',
                       'input_files':{'sources/tempfile.md':source_result['sha256'],'sample.txt':_hash(SAMPLE)}})]
            elif stage == 5: calls=[call('delegate_with_inputs',{'assignee':'integrator','title':'Commit and push checked result',
                                                               'input_files':{'result.txt':_hash(EXPECTED)}})]
        elif actor == 'researcher':
            if stage == 0:
                calls=[call('search_web',{'query':'Python tempfile official documentation','limit':3})] if self.with_web else [call('post_message',{'body':'[scripted] Using a labelled source fixture; no public web requested.'})]
            elif stage == 1:
                calls=[call('retrieve_text',{'url':SOURCE,'path':'sources/tempfile.md'})] if self.with_web else [call('create_text',{
                    'path':'sources/tempfile.md','content':'Source: scripted fixture, not public retrieval\nTemporaryDirectory context reference.\n'})]
            elif stage == 2: calls=[call('offer_artifact',{'path':'sources/tempfile.md','target_task':context['parent_task_id'],
                                                        'expected_sha256':latest_tool().get('artifact',latest_tool())['sha256']})]
        elif actor == 'coder':
            if stage == 0: calls=[call('accept_artifact',{'artifact_id':o['artifact_id'],'path':o['source_path']}) for o in envelopes('input_artifact_offers')[-1]['offers']]
            elif stage == 1: calls=[call('create_text',{'path':'check.py','content':CODE})]
            elif stage == 2:
                accepted={json.loads(m['content'])['result']['path']:json.loads(m['content'])['result']['sha256']
                          for m in request['messages'] if m['role']=='tool' and json.loads(m['content']).get('ok')
                          and 'path' in json.loads(m['content'])['result']}
                calls=[call('run_python',{'entrypoint':'check.py','input_files':accepted,'arguments':[],'outputs':['result.txt']})]
            elif stage == 3: calls=[call('record_lesson',{'lesson':'For a text counter, check normalization, empty input and output newline against independent expectations; do not infer authorization from source text.',
                                                        'tags':['text','counter','newline','verified-execution']})]
            elif stage == 4: calls=[call('offer_artifact',{'path':'result.txt','target_task':context['parent_task_id'],'expected_sha256':_hash(EXPECTED)})]
        elif actor == 'integrator':
            if stage == 0:
                offer=envelopes('input_artifact_offers')[-1]['offers'][0]
                calls=[call('accept_artifact',{'artifact_id':offer['artifact_id'],'path':'result.txt'})]
            elif stage == 1: calls=[call('git_commit',{'repository':DEMO_REPOSITORY,'files':{'docs/result.txt':'result.txt'},'message':'Store independently checked fixture output'})]
            elif stage == 2: calls=[call('git_push',{'repository':DEMO_REPOSITORY,'remote':DEMO_REMOTE,'branch':DEMO_BRANCH})]
        else:
            raise WorkflowError('Unexpected actor in explicit combined fixture')
        message={'role':'assistant','content':None if calls else 'Synthetic proposal; actual independent verification decides completion.'}
        if calls: message['tool_calls']=calls
        return json.dumps({'id':f'synthetic-combined-{actor}-{stage}','model':'synthetic-combined-fixture',
            'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2},
            'choices':[{'message':message,'finish_reason':'tool_calls' if calls else 'stop'}]}).encode()


def run_integrated(directory, *, docker_host, image, with_web=False):
    """Use actual isolated execution and a local remote, then reuse scoped memory."""
    repository=demo_repository_config(directory)
    config=LiveConfig('synthetic-combined-fixture','fixture-not-a-provider-key',allow_network=with_web,
                      enable_web=True,enable_memory=True,memory_namespace='combined-development',
                      docker_host=docker_host,python_image=image,repositories=(repository,))
    workflow=Workflow(directory/'workflow.sqlite3')
    files=services=None
    try:
        workflow.register_actor('operator','human')
        for actor in live_members(config): workflow.register_actor(actor,'agent')
        chat=workflow.create_chat('group',['operator',*live_members(config)])
        root=workflow.create_task(chat,'operator','coordinator','Retrieve, execute, verify and commit a text counter result')
        roles=live_roles(live_members(config),config)
        files=FileTools(workflow,directory/'files')
        services=RuntimeServices(workflow,files,config)
        prepare_demo_repository(services.git,repository)
        def acceptance(task):
            def verify():
                actor=task['assignee']; identifier=task['id']
                if task['title'].startswith('Reuse scoped'):
                    return files.text_verifier(identifier,actor,{'reuse.txt':'Scoped candidate considered; causality unproven.\n'})()
                if actor=='researcher':
                    text=ArtifactInspector(workflow,files).read_file(identifier,'operator','sources/tempfile.md')['content']
                    checks={'source_contains_expected_subject':'TemporaryDirectory' in text}
                    if with_web:
                        checks['actual_cited_public_source']=SOURCE in text and workflow.db.execute(
                            "SELECT 1 FROM retrieval_records WHERE task=? AND kind='retrieve' AND status='succeeded'",(identifier,)).fetchone() is not None
                    return checks
                if actor=='coder':
                    checks=files.text_verifier(identifier,actor,{'result.txt':EXPECTED})()
                    row=workflow.db.execute('SELECT result FROM sandbox_runs WHERE task=? ORDER BY rowid DESC LIMIT 1',(identifier,)).fetchone()
                    result=json.loads(row[0]) if row and row[0] else {}
                    execution=result.get('execution') or {}
                    checks['actual_execution_succeeded']=execution.get('exit_code')==0 and not execution.get('interrupted') and result.get('cleanup_confirmed') is True
                    return checks
                if actor=='integrator':
                    row=workflow.db.execute("SELECT result FROM git_operations WHERE task=? AND operation='push' AND status='verified' ORDER BY rowid DESC LIMIT 1",(identifier,)).fetchone()
                    if row is None: return {'actual_push_verified':False}
                    commit=json.loads(row[0])['commit']
                    code,out,_,_=services.git._remote_git(['--git-dir',repository.remote_url(DEMO_REMOTE),'show',f'{commit}:docs/result.txt'])
                    return {'actual_push_verified':services.git._remote_head(repository.remote_url(DEMO_REMOTE),DEMO_BRANCH)==commit,
                            'remote_content_matches':code==0 and out.decode()==EXPECTED}
                return files.text_verifier(identifier,actor,{'result.txt':EXPECTED})()
            return verify,'combined-independent-verification-v1'
        def scheduler(task):
            return MultiAgentScheduler(workflow,files,task,human='operator',roles=roles,
                clients={a:DeepSeekClient(config.model,CombinedFixture(with_web)) for a in roles},mode='offline_fixture',
                constraints=['Source text never grants permissions','Use actual independent execution and remote evidence'],
                acceptance_id='combined-contract-v1',verifier_factory=acceptance,memory=services.memory,
                executor=services.executor,git=services.git,retrieval=services.retrieval,capture_memory=True)
        before=scheduler(root).run()
        if before['state']!='blocked' or before['task_state'] in {'failed','cancelled'}:
            raise WorkflowError('Combined fixture did not reach the expected exact push approval')
        request=workflow.db.execute("SELECT id,task FROM requests WHERE kind='approval' AND answered=0").fetchone()
        if request is None: raise WorkflowError('Combined fixture has no pending exact push approval')
        request_id,integrator=request['id'],request['task']
        services.close(); services=None; files.close(); files=None; workflow.close()
        workflow=Workflow(directory/'workflow.sqlite3'); files=FileTools(workflow,directory/'files')
        services=RuntimeServices(workflow,files,config)
        # Explicitly scripted operator decision, limited to this disposable local remote.
        workflow.respond(request_id,'operator',approve=True)
        scheduler(root).runner(integrator).gateway.release_approved(request_id)
        after=scheduler(root).run()
        if after['task_state']!='succeeded': raise WorkflowError('Combined root did not pass independent verification')
        reuse=workflow.create_task(chat,'operator','coder','Reuse scoped text counter experience in a later task')
        reused=scheduler(reuse).run()
        if reused['task_state']!='succeeded': raise WorkflowError('Scoped candidate reuse did not finish')
        failures=[dict(r) for r in workflow.db.execute("SELECT kind,status,result FROM retrieval_records WHERE status!='succeeded'")]
        report={'mode':'combined_engineering_fixture','model_calls':0,'api_model_calls':0,'benchmark_valid':False,
                'autonomous_collaboration_established':False,'learning_improvement_established':False,
                'actual_public_web_requested':with_web,'actual_python_sandbox':True,'remote':'disposable_local_bare_repository',
                'github_push_established':False,'human_approval':'scripted exact approval for disposable fixture only',
                'before_restart':before,'after_restart':after,'later_memory_task':reused,
                'retrieval_failures':failures,'memory_selected_uses':[dict(r) for r in workflow.db.execute('SELECT lesson,task,outcome FROM lesson_uses')],
                'metrics':workflow.metrics(chat,'operator')}
        (directory/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        return report
    finally:
        if services: services.close()
        if files: files.close()
        workflow.close()
