"""Presentation-Mac entry point. Import/open/export are zero-model-call actions.

The ordinary-task UI and canonical role-package operator use existing platform
services. A ZIP is validated by the existing versioned adapter, never extracted.
No instructor answer, success, approval, model fallback or retry is invented.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import stat
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from agent_lab import Workflow
from agent_lab.core import WorkflowError
from agent_lab.files import FileTools
from agent_lab.inspection import ArtifactInspector
from agent_lab.runner import Limits
from agent_lab.budget import TreeLimits
from agent_lab.runtime import LiveConfig, live_members
from agent_lab.tui.controller import ControlCenter
from agent_lab.evaluation.official import OfficialMidTestPlan
from agent_lab.evaluation.official_dataset import load_mid_test

LOCAL = PROJECT / 'runs/presentation-local'
TERMINAL = {'succeeded', 'failed', 'cancelled'}
POLICIES = {'software-engineering':'software-files-coordination-python-v1',
            'newsroom':'newsroom-files-coordination-web-v1',
            'securities-fund':'securities-files-coordination-web-python-v1'}

def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')

def write(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    path.chmod(0o600)

def read(path):
    return json.loads(Path(path).read_text())

def text_input(path, *, limit=1024*1024):
    """Preserve a bounded regular UTF-8 file, refusing final-component links."""
    with os.fdopen(os.open(path, os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK), 'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size>limit:
            raise ValueError('请选择不超过 1 MiB 的普通 UTF-8 文本文件；不会执行输入代码。')
        data=stream.read(limit+1)
    if len(data)>limit:raise ValueError('输入文件过大。')
    return data.decode('utf-8')

def settings(path):
    value=read(path)
    required={'model','key_env','credential_file','docker_host','python_image'}
    if set(value)!=required or not all(isinstance(v,str) and v for v in value.values()):
        raise ValueError('本机设置尚未准备好；不要在命令行或截图中粘贴密钥。')
    return value

def credential(config, *, required=True):
    key=os.environ.get(config['key_env'])
    if not key:
        try:lines=(PROJECT/config['credential_file']).read_text().splitlines()
        except OSError:
            if required:raise ValueError('课程凭证文件不可用；未发出模型请求。') from None
            return None
        for line in lines:
            name,sep,value=line.partition('=')
            if sep and name==config['key_env']:key=value.strip().strip('"\'')
    if not key or any(c.isspace() for c in key):
        if required:raise ValueError('课程凭证不可用；未发出模型请求。')
        return None
    return key

def live(config):
    return LiveConfig(model=config['model'],api_key=credential(config),provider='hkgai',allow_network=True,
        max_output_tokens=8192,socket_timeout=180,execution_profile='quality',pause_on_limits=True,
        stream_responses=True,
        role_limits=Limits(model_attempts=256,reported_tokens=32768000,duration_seconds=14400),
        tree_limits=TreeLimits(tasks=16,depth=4,model_attempts=256,reported_tokens=32768000,
                               duration_seconds=14400,tool_calls=1536),
        tool_calls=1000,child_retries=8,enable_collaboration=True,require_tool_actions=True,
        docker_host=config['docker_host'],python_image=config['python_image'])

def fresh(kind):
    path=LOCAL/(kind+'-'+stamp());path.mkdir(parents=True,mode=0o700,exist_ok=False)
    return path

def remember(directory,kind):
    write(LOCAL/'current.json',{'directory':str(directory.resolve()),'kind':kind})

def import_text(config, goal_file, inputs=(), *, directory=None):
    goal=text_input(goal_file,limit=65536)
    if not goal.strip():raise ValueError('题目不能为空。')
    paths=[Path(p) for p in inputs]
    if len(paths)>16:raise ValueError('一次最多导入 16 个文本附件。')
    supplied=[('inputs/%02d-%s'%(i+1,p.name),text_input(p)) for i,p in enumerate(paths)]
    # The original goal is also retained as an exact input artifact.
    supplied.insert(0,('inputs/teacher-goal.txt',goal))
    if directory is None:directory=fresh('text')
    elif directory.exists():raise ValueError('新任务使用新目录；旧现场只能继续打开，不能覆盖。')
    else:directory.mkdir(parents=True,mode=0o700)
    center=ControlCenter(directory/'state',human='operator',live=live(config))
    try:
        chat=center.create_conversation('group',list(live_members(center.live)))
        result=center.create_task(chat,'coordinator',goal,constraints=(
            'Inspect the human-provided inputs/* task files and preserve supplied data. '
            'No web search is configured. Delegate input snapshots through the artifact tools. '
            'Document outputs use Markdown or plain text; code executes only in the configured sandbox.',))
        def provide(b):
            return [b.files.provide_text(result['task'],b.human,name,content) for name,content in supplied]
        receipts=center.call(provide)
    finally:center.close()
    write(directory/'session.json',{'kind':'text','chat':chat,'task':result['task'],
        'input_receipts':receipts,'new_model_requests':0,'memory_enabled':False,'web_enabled':False,
        'initial_shared_requests_per_goal':256,'operating_allowance_is_teacher_rule':False,
        'note':'Default platform roles; use the role-package path when the teacher assigns original roles.'})
    remember(directory,'text');return directory

def open_ui(config,directory):
    if importlib.util.find_spec('textual') is None:
        raise ValueError('本机尚未安装界面依赖；请先按操作说明完成准备。输入与现场已保留。')
    from agent_lab.tui.app import ControlCenterApp
    center=ControlCenter(directory/'state',human='operator',live=live(config))
    try:ControlCenterApp(center).run()
    finally:center.close()

def call(module,args,directory,config,*,network=False):
    env={**os.environ,config['key_env']:credential(config) if network else 'offline-no-model-request'}
    result=subprocess.run([sys.executable,'-m',module,*map(str,args)],cwd=PROJECT,env=env,
        capture_output=True,text=True)
    record=directory/('operation-'+stamp())
    record.with_suffix('.stdout').write_text(result.stdout)
    record.with_suffix('.stderr').write_text(result.stderr)
    if result.returncode:raise ValueError(result.stderr.strip()[-2000:] or '操作未完成，记录已保存。')
    return json.loads(result.stdout)

def prepare_zip(config,archive,*,directory=None):
    dataset=load_mid_test(archive)  # Validate before creating a run; never extract.
    directory=directory or fresh('roles')
    directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    if (directory/'session.json').exists():raise ValueError('已有会话不能重新导入。')
    cases={}
    for scenario in dataset['scenarios']:
        case=scenario['id'];d=directory/case;d.mkdir(mode=0o700)
        shutil.copyfile(archive,d/'teacher.zip')
        write(d/'manifest.json',load_mid_test(d/'teacher.zip'))
        plan=read(PROJECT/'evaluation/official/mid-test/plan.json')
        plan.update(archive='teacher.zip',manifest='manifest.json')
        plan['runtime'].update(model=config['model'],api_key_env=config['key_env'],
            per_scenario_model_attempts=512,max_output_tokens=8192,tool_policy=POLICIES[case])
        plan['operator_decisions'].update(completion_criteria='Actual requester clarification and independent output review; no invented score.',
            memory_persistence='Fresh group per scenario; ordered tasks retain that group; no previous trial memory copied.',
            repeat_policy='No automatic replay or provider retry. Original outcomes and usage persist.',
            timing_rule='Record assignment-to-output elapsed time and human waiting; no invented instructor cutoff.')
        write(d/'plan.json',plan);checked=OfficialMidTestPlan(d/'plan.json')
        common=['--config',d/'plan.json','--state-dir',d/'state']
        call('agent_lab.evaluation.official_session',[*common,'init','--scenario',case,'--human','requester','--plan-sha256',checked.sha256],d,config)
        call('agent_lab.evaluation.official_session',[*common,'post','--sequence',1,'--assignee',scenario['roles'][0]['id']],d,config)
        cases[case]={'directory':str(d.resolve()),'role_ids':[r['id'] for r in scenario['roles']],
            'tasks':[t['title'] if 'title' in t else t for t in scenario['tasks']]}
    write(directory/'session.json',{'kind':'roles','cases':cases,'new_model_requests':0,
        'input_adapter':'canonical-mid-test-only; final format must validate independently',
        'original_archive_sha256':__import__('hashlib').sha256(Path(archive).read_bytes()).hexdigest()})
    remember(directory,'roles');return directory

def official(config,directory):
    spec=read(directory/'session.json');cases=list(spec['cases'])
    print('保留老师的原角色和题目。结构未通过适配器的包不会自动改成普通团队。')
    for i,name in enumerate(cases,1):print(i,name)
    index=int(input('选择场景编号：'))
    if not 1<=index<=len(cases):raise ValueError('请选择列出的场景编号。')
    case=cases[index-1];d=Path(spec['cases'][case]['directory'])
    common=['--config',d/'plan.json','--state-dir',d/'state']
    backend=['--execution-profile','quality','--output-token-ceiling',8192,'--socket-timeout',180,'--show-execution-budget',
             '--stream-responses']
    if case!='newsroom':backend+=['--docker-host',config['docker_host'],'--image',config['python_image']]
    with (d/'operator.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        while True:
            status=call('agent_lab.evaluation.official_session',[*common,'status'],d,config)
            tasks=status['tasks']
            for t in tasks:print('第%s题：%s  %s'%(t['sequence'],t['state'],t.get('root','')))
            current=next((t for t in tasks if t['state'] not in TERMINAL and t['state']!='not_posted'),None)
            print('r 继续运行  v 检查/验收  a 回答/决定  u 网络中断后重发  n 发布同组下一题  e 导出  q 返回')
            choice=input('操作：').strip().lower()
            if choice=='q':return
            if choice=='e':
                print(call('agent_lab.evaluation.official_export',[*common,'--output',d/('export-'+stamp())],d,config));continue
            if choice=='n':
                first=tasks[0]
                if first['state'] not in TERMINAL or tasks[1]['state']!='not_posted':raise ValueError('第一题需先结束；第二题不能重复发布。')
                posted=call('agent_lab.evaluation.official_session',[*common,'post','--sequence',2,'--assignee',spec['cases'][case]['role_ids'][0]],d,config)
                if first['state']=='succeeded':
                    w=Workflow(d/'state/workflow.sqlite3');files=FileTools(w,d/'state/files')
                    try:
                        inspector=ArtifactInspector(w,files)
                        paths=inspector.list_files(first['root'],'requester')
                    finally:files.close();w.close()
                    for f in paths:
                        if f['current'] and f['matches_receipt'] and not f['error']:
                            call('agent_lab.evaluation.official_session',[*common,'carry','--source-task',first['root'],
                                '--source-path',f['path'],'--sha256',f['current']['sha256'],'--target-path',f['path']],d,config)
                continue
            if current is None:print('当前没有已发布的活动题目。');continue
            seq=current['sequence'];prefix=[*common,'--sequence',seq]
            if choice=='r':
                # Each advance is counted. No automatic retry/answer/review/renewal.
                import time
                deadline=time.monotonic()+3600
                steps=0
                while time.monotonic()<deadline:
                    value=call('agent_lab.evaluation.official_live',[*prefix,'advance',*backend,'--turns',1],d,config,network=True)
                    steps+=1
                    if steps%5==0 or value.get('state')!='running' or value.get('needs'):
                        print('请求累计',value.get('budget',{}).get('attempts','?'),'状态',value.get('state'))
                    if value.get('state')!='running' or value.get('needs'):print(json.dumps(value.get('needs',[]),ensure_ascii=False,indent=2));break
                else:print('本次连续操作检查点已到，现场保留；不代表内容失败。')
            elif choice=='v':
                value=call('agent_lab.evaluation.official_live',[*prefix,'preflight',*backend],d,config)
                print(json.dumps(value.get('needs',[]),ensure_ascii=False,indent=2))
                task=input('粘贴要检查的 task ID（空行返回）：').strip()
                if not task:continue
                w=Workflow(d/'state/workflow.sqlite3');files=FileTools(w,d/'state/files')
                try:
                    inspector=ArtifactInspector(w,files);print(json.dumps(inspector.list_files(task,'requester'),ensure_ascii=False,indent=2))
                    path=input('输入要查看的文件路径（空行跳过）：').strip()
                    if path:print(inspector.read_file(task,'requester',path)['content'])
                finally:files.close();w.close()
                decision=input('检查实际内容后：accept 通过 / reject 修改 / 空行取消：').strip()
                if decision not in {'accept','reject'}:continue
                feedback=input('写具体检查依据或修改意见：').strip()
                extra=[]
                if decision=='accept':
                    ids=input('如需豁免失败子任务，逐项填入明确 ID（通常留空；不自动豁免）：').split()
                    for identifier in ids:extra+=['--waive-failed-subtask',identifier]
                call('agent_lab.evaluation.official_live',[*prefix,'review',*backend,'--task',task,'--decision',decision,'--feedback',feedback,*extra],d,config)
            elif choice=='u':
                # Proposed 2026-11-23: a 504/connection failure leaves provider_uncertain with no menu action.
                # One counted resend per explicit confirmation; nothing is retried automatically.
                value=call('agent_lab.evaluation.official_live',[*prefix,'preflight',*backend],d,config)
                stuck=list(dict.fromkeys(n['task'] for n in value.get('needs',[])
                    if 'provider_uncertain' in {n.get('runner_state'),n.get('kind')}))
                if not stuck:print('没有因网络中断而停住的任务。');continue
                print('因网络或服务中断停住的任务：',' '.join(stuck))
                print('该次请求可能已被服务处理且计费；重发会再计一次请求，不会重放已执行的工具效果。')
                task=input('确认重发的 task ID（空行取消）：').strip()
                if task not in stuck:continue
                reason=input('写明原因（例如：HTTP 504，网络已恢复）：').strip()
                if not reason:continue
                print(call('agent_lab.evaluation.official_live',[*prefix,'reconcile',*backend,'--task',task,'--action','resend',
                    '--reason',reason,'--confirm-stopped'],d,config))
            elif choice=='a':
                request=input('request ID：').strip()
                print('只填写你本人的真实答案；approve/deny 是对该条精确操作的决定，批准后仍须单独 release。')
                action=input('answer / approve / deny / release（空行返回）：').strip()
                if action=='answer':args=['answer','--request',request,'--text',input('答案：')]
                elif action in {'approve','deny','release'}:
                    print(official_decision(config,d,seq,current['root'],request,action));continue
                else:continue
                print(call('agent_lab.evaluation.official_live',[*prefix,*args],d,config))

def official_decision(config,d,sequence,root,request,action):
    from agent_lab.evaluation.official_session import OfficialScenarioSession
    from agent_lab.evaluation.official_live import runtime_config,runtime_services,make_scheduler
    plan=OfficialMidTestPlan(d/'plan.json');w=Workflow(d/'state/workflow.sqlite3')
    files=FileTools(w,d/'state/files');services=None
    try:
        session=OfficialScenarioSession.open(w,plan)
        python=session.scenario['id']!='newsroom'
        live_settings=runtime_config(session,plan,sequence,docker_host=config['docker_host'] if python else None,
            image=config['python_image'] if python else None,allow_network=False,
            environ={config['key_env']:'offline-human-decision'},output_token_ceiling=8192,
            execution_profile='quality',socket_timeout=180,stream_responses=True)
        services=runtime_services(w,files,live_settings)
        scheduler=make_scheduler(session,root,files,live_settings,services,show_execution_budget=True)
        req=w.request(request,session.human)
        runner=scheduler.runner(req['task'])  # Also verifies membership in this goal.
        if action=='release':result=runner.gateway.release_approved(request)
        else:result=w.respond(request,session.human,approve=action=='approve')
        write(d/('human-action-'+stamp()+'.json'),{'action':action,'request':request,'result':result,'new_model_requests':0})
        return result
    finally:
        if services:services.close()
        files.close();w.close()

def export_text(config,directory):
    output=directory/('export-'+stamp());output.mkdir(mode=0o700)
    center=ControlCenter(directory/'state',human='operator',live=live(config))
    try:
        tasks=center.tasks();records=[]
        for task in tasks:
            identifier=task['id'];folder=output/'files'/identifier;folder.mkdir(parents=True,mode=0o700)
            for f in center.files(identifier):
                if f['current'] and f['matches_receipt'] and not f['error']:
                    value=center.read_file(identifier,f['path']);target=folder/value['path'];target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_text(value['content'])
            records.append(center.task_detail(identifier))
        write(output/'results.json',{'tasks':records,'metrics':center.metrics(),'note':'Intermediate/partial outputs retain their actual states; export is not acceptance.'})
        write(output/'conversations.json',[{'conversation':c,'feed':center.feed(c['id'])} for c in center.conversations()])
    finally:center.close()
    return output

def doctor(config):
    return {'python':sys.version.split()[0],'interface_installed':importlib.util.find_spec('textual') is not None,
        'course_key_available':bool(credential(config,required=False)),
        'docker_socket_present':Path(config['docker_host'][7:]).is_socket(),
        'model':config['model'],'new_model_requests':0,
        'not_tested':['Actual API availability','Wednesday task package and timing','Unknown task correctness']}

def drag_path(prompt):
    parts=shlex.split(input(prompt).strip())
    if len(parts)!=1:raise ValueError('一次拖入一个文件。')
    return Path(parts[0]).expanduser()

def menu(config):
    while True:
        print('\n周三操作入口：1 普通文字题  2 老师角色 ZIP  3 继续上次  4 导出上次  5 环境检查  q 退出')
        try:
            choice=input('选择：').strip()
            if choice=='q':return
            if choice=='5':print(json.dumps(doctor(config),ensure_ascii=False,indent=2));continue
            if choice=='1':
                print('仅用于老师没有指定角色的题目；请把原题保存为 UTF-8 TXT/MD。')
                goal=drag_path('把题目文件拖进窗口，按回车：');inputs=[]
                while input('要附加文本数据文件吗？y / 回车跳过：').strip().lower()=='y':inputs.append(drag_path('拖入一个附件：'))
                directory=import_text(config,goal,inputs);print('现场目录：',directory);open_ui(config,directory)
            elif choice=='2':
                print('仅接受已支持的中期同结构 ZIP；不联网下载、不解压执行、不改写未知格式。')
                directory=prepare_zip(config,drag_path('拖入老师的 ZIP：'));print('现场目录：',directory);official(config,directory)
            elif choice in {'3','4'}:
                current=read(LOCAL/'current.json');directory=Path(current['directory'])
                if choice=='4':
                    if current['kind']=='roles':official(config,directory)
                    else:print('导出目录：',export_text(config,directory))
                elif current['kind']=='roles':official(config,directory)
                else:open_ui(config,directory)
        except (WorkflowError,ValueError,OSError,KeyError) as error:print('已停止并保留记录：',str(error))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--settings',type=Path,default=LOCAL/'settings.json')
    p.add_argument('action',choices=['menu','doctor','text','roles','open','export'])
    p.add_argument('--goal-file',type=Path);p.add_argument('--input',type=Path,action='append',default=[])
    p.add_argument('--archive',type=Path);p.add_argument('--directory',type=Path)
    a=p.parse_args();config=settings(a.settings)
    if a.action=='menu':menu(config)
    elif a.action=='doctor':print(json.dumps(doctor(config),ensure_ascii=False,indent=2))
    elif a.action=='text':
        if not a.goal_file:p.error('text 需要 --goal-file')
        print(import_text(config,a.goal_file,a.input,directory=a.directory))
    elif a.action=='roles':
        if not a.archive:p.error('roles 需要 --archive')
        print(prepare_zip(config,a.archive,directory=a.directory))
    else:
        if not a.directory:p.error('需要 --directory，避免打开错误现场')
        kind=read(a.directory/'session.json')['kind']
        if kind=='roles':official(config,a.directory)
        elif a.action=='open':open_ui(config,a.directory)
        else:print(export_text(config,a.directory))

if __name__=='__main__':
    try:main()
    except (WorkflowError,ValueError,OSError) as error:raise SystemExit('已保留现场：'+str(error))
