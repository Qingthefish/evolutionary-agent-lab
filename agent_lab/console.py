"""Minimal persistent text interface; uses the same service as the optional TUI.

No Textual dependency and no implicit model calls. Creating a task schedules it;
advance is explicit. Human answers, approval and release are separate commands.
"""

import argparse
import json
import sys
from pathlib import Path

from .core import WorkflowError
from .protocol import strict_json
from .runtime import policy_from_spec, add_live_arguments, live_config_from_args, live_members
from .tui.controller import ControlCenter


def main(argv=None):
    parser=argparse.ArgumentParser(prog='python -m agent_lab.console')
    parser.add_argument('--state-dir',default='runs/console-session')
    parser.add_argument('--human',default='operator')
    add_live_arguments(parser)
    commands=parser.add_subparsers(dest='command',required=True)
    new=commands.add_parser('new',help='Create a real task; never executes it implicitly')
    new.add_argument('--goal',required=True)
    new.add_argument('--policy',help='Trusted JSON with artifacts and optional child_rules; no model-generated criteria')
    new.add_argument('--chat',help='Existing conversation ID; omit to create a group')
    new.add_argument('--assignee',default='coordinator',help='Agent member to receive the task (default: coordinator)')
    chat=commands.add_parser('chat',help='Create or inspect conversations; messages do not execute tasks')
    chats=chat.add_subparsers(dest='chat_command',required=True)
    create_chat=chats.add_parser('new')
    create_chat.add_argument('--kind',choices=('private','group'),required=True)
    create_chat.add_argument('--participant',action='append',required=True,help='Registered actor ID (repeatable); the current human is added automatically')
    chats.add_parser('list')
    chats.add_parser('feed').add_argument('chat')
    requests=commands.add_parser('requests',help='Inspect clarification/approval requests and recorded effects')
    request_filter=requests.add_mutually_exclusive_group()
    request_filter.add_argument('--request',help='Inspect one request and its recorded outcome')
    request_filter.add_argument('--pending',action='store_true',help='Show only unanswered requests addressed to the current human')
    commands.add_parser('status',help='Read task, request and runtime state').add_argument('--task')
    commands.add_parser('advance',help='Run until paused, blocked or terminal').add_argument('task')
    answer=commands.add_parser('answer');answer.add_argument('request');answer.add_argument('text')
    decide=commands.add_parser('decide');decide.add_argument('request');decide.add_argument('decision',choices=('approve','deny'))
    commands.add_parser('release',help='Execute one exact approved action').add_argument('request')
    review=commands.add_parser('review');review.add_argument('task');review.add_argument('decision',choices=('accept','reject'))
    review.add_argument('--feedback',default='')
    message=commands.add_parser('message');message.add_argument('chat');message.add_argument('text')
    args=parser.parse_args(argv)
    center=None
    try:
        live=live_config_from_args(args)
        center=ControlCenter(args.state_dir,human=args.human,live=live)
        if args.command=='new':
            data={}
            if args.policy:
                data=strict_json(Path(args.policy).read_text())
            policy=policy_from_spec(data,live)
            if not args.chat and args.assignee not in live_members(live):
                raise WorkflowError('Assignee is not an agent in the default group; select a configured agent or an existing conversation')
            chat=args.chat or center.create_conversation('group',list(live_members(live)))
            result=center.create_task(chat,args.assignee,args.goal,constraints=tuple(data.get('constraints',())),expected_artifacts=policy.root_artifacts,child_rules=policy.child_rules,root_criteria=policy.root_criteria)
            result['chat']=chat
        elif args.command=='chat':
            if args.chat_command=='new':
                result={'chat':center.create_conversation(args.kind,args.participant),'kind':args.kind}
            elif args.chat_command=='list':result=center.conversations()
            elif args.chat_command=='feed':result=center.feed(args.chat)
        elif args.command=='requests':
            result=center.request_detail(args.request) if args.request else center.requests(pending_only=args.pending)
        elif args.command=='status':
            result=center.task_detail(args.task) if args.task else {'runtimes':center.runtimes(),'tasks':center.tasks(),'requests':center.requests()}
        elif args.command=='advance':result=center.advance(args.task)
        elif args.command=='answer':result=center.answer(args.request,args.text)
        elif args.command=='decide':result=center.decide(args.request,args.decision=='approve')
        elif args.command=='release':result=center.release(args.request)
        elif args.command=='review':result=center.review(args.task,accept=args.decision=='accept',feedback=args.feedback)
        elif args.command=='message':result=center.post_message(args.chat,args.text)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (WorkflowError,OSError,ValueError,TypeError,KeyError) as error:
        parser.exit(1,f'Operation failed: {error}\n')
    finally:
        if center is not None:center.close()


if __name__=='__main__':sys.exit(main())
