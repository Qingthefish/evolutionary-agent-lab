"""Explicit scripted engineering checks; never a model-learning experiment.

Scripts KNOW the expected fixture outputs. Both probe arms produce the same
fixed answers; memory retrieval/selection does not cause those answers.
"""
import json

from ..deepseek import DeepSeekClient
from ..runtime import LiveConfig
from .experience import ExperiencePlan, ExperienceTrial, LiveExperienceDriver


class ExperienceFixtureDriver(LiveExperienceDriver):
    mode = 'offline_fixture'

    def __init__(self, live):
        super().__init__(live)
        self.requests = []

    def clients(self, roles, stage):
        def scripted(payload):
            request = json.loads(payload)
            self.requests.append({'phase':stage['phase'],'memory':stage['memory'],'request':request})
            turn = sum(m['role']=='assistant' for m in request['messages'])
            calls = []
            def call(name,args):
                return {'id':f'fixture-{turn}-{name}','type':'function',
                        'function':{'name':name,'arguments':json.dumps(args)}}
            expected = stage['case']['expected']['artifacts']['note.txt']
            if stage['phase'] == 'training':
                if turn == 0:
                    # One genuine terminal failure and one success exercise
                    # contradictory-source retention. Neither is live output.
                    content = 'Wrong fixture output' if stage['case']['id'].endswith('-a') else expected
                    calls = [call('create_text',{'path':'note.txt','content':content}),
                             call('record_lesson',{'lesson':'For newline-sensitive text tasks, preserve the required trailing newline and verify it; this is a candidate, not a guarantee.',
                                                  'tags':['newline','text']}),
                             call('post_message',{'body':'TRAINING_CHAT_SHOULD_NOT_APPEAR'})]
            elif turn == 0:
                calls = [call('read_messages',{'limit':20})]
            elif stage['memory'] == 'on' and turn == 1:
                calls = [call('search_memory',{'query':'newline text','limit':5})]
            elif stage['memory'] == 'on' and turn == 2:
                result = next(json.loads(m['content'])['result'] for m in reversed(request['messages'])
                              if m['role']=='tool')
                candidate = next(r for r in result if len(r['sources'])>1)
                calls = [call('select_memory',{'memory_id':candidate['memory_id']})]
            elif turn == (3 if stage['memory']=='on' else 1):
                calls = [call('create_text',{'path':'note.txt','content':expected})]
            message = {'role':'assistant','content':None if calls else 'Scripted fixture proposes completion.'}
            if calls: message['tool_calls'] = calls
            return json.dumps({'id':f'offline-{turn}','model':'offline-experience-fixture',
                'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2},
                'choices':[{'finish_reason':'tool_calls' if calls else 'stop','message':message}]}).encode()
        return {a:DeepSeekClient(self.live.model,scripted,max_tokens=self.live.max_output_tokens) for a in roles}


def run_fixture(config, output_root):
    plan = ExperiencePlan(config)
    # No environment key, network, web backend or engine is enabled by this demo.
    if (plan.runtime.settings['enable_web'] or plan.runtime.settings['docker_host']
            or plan.runtime.settings['repositories']):
        raise ValueError('The scripted experience demo requires the text-only fixture plan')
    driver = ExperienceFixtureDriver(LiveConfig(api_key='unused-offline-fixture-key',**plan.runtime.settings))
    return ExperienceTrial(plan,driver).run(output_root)
