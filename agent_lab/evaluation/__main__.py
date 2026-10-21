"""Run development evaluation cases: `python -m agent_lab.evaluation run`."""

import argparse
import json
import sys

from ..core import WorkflowError
from ..runtime import add_live_arguments, live_config_from_args
from .cases import load_cases
from .harness import Evaluator
from .plan import DevelopmentPlan


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m agent_lab.evaluation",
                                     description="Development evaluation harness (offline fixtures unless live is configured)")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Run cases and write results.json and report.md")
    run.add_argument("--cases", default="evaluation/dev", help="Directory of case JSON files")
    run.add_argument("--output", default="runs/evaluations", help="Directory for run results (ignored by Git)")
    run.add_argument("--case", action="append", help="Run only this case id (repeatable)")
    add_live_arguments(run)
    commands.add_parser("list", help="List case definitions").add_argument("--cases", default="evaluation/dev")
    plan = commands.add_parser("plan", help="Inspect a versioned development run without a key or network")
    plan.add_argument("--config", required=True)
    execute = commands.add_parser("execute", help="Execute the inspected development plan with explicit authorization")
    execute.add_argument("--config", required=True)
    execute.add_argument("--allow-model-calls", action="store_true")
    execute.add_argument("--plan-sha256", required=True)
    execute.add_argument("--output", default="runs/evaluations")
    experience = commands.add_parser("experience", help="Frozen-training memory ON/OFF development protocol")
    stages = experience.add_subparsers(dest="experience_command", required=True)
    for action in ("plan", "execute", "demo"):
        command = stages.add_parser(action)
        command.add_argument("--config", default="evaluation/memory-plan.json")
        if action in {"execute", "demo"}:
            command.add_argument("--output", default="runs/experience-development")
        if action == "execute":
            command.add_argument("--allow-model-calls", action="store_true")
            command.add_argument("--plan-sha256", required=True)
    stages.add_parser("compare", help="Validate/recompute a retained trial report; no model calls").add_argument("--run", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "experience":
            from .experience import ExperiencePlan, compare_experience
            if args.experience_command == "compare":
                from pathlib import Path
                from ..protocol import strict_json
                with (Path(args.run) / "experiment.json").open() as stream:
                    raw = stream.read(16 * 1024 * 1024 + 1)
                if len(raw) > 16 * 1024 * 1024:
                    raise WorkflowError("Experience report exceeds size limit")
                print(json.dumps(compare_experience(strict_json(raw)),indent=2))
                return 0
            planned = ExperiencePlan(args.config)
            if args.experience_command == "plan":
                print(json.dumps(planned.inspect(),indent=2))
                return 0
            if args.experience_command == "demo":
                from .experience_fixture import run_fixture
                result = run_fixture(args.config,args.output)
            else:
                result = planned.execute(allow_model_calls=args.allow_model_calls,plan_sha256=args.plan_sha256,output_root=args.output)
            print(json.dumps({k:result[k] for k in ("run_id","mode","benchmark_valid","model_calls","comparison")},indent=2))
            return 0
        if args.command in {"plan", "execute"}:
            planned = DevelopmentPlan(args.config)
            if args.command == "plan":
                print(json.dumps(planned.inspect(), ensure_ascii=False, indent=2))
                return 0
            result = planned.execute(allow_model_calls=args.allow_model_calls,
                                     plan_sha256=args.plan_sha256, output_root=args.output)
            print(json.dumps({k: result[k] for k in ("run_id", "mode", "benchmark_valid", "summary")}, indent=2))
            print(f"Report: {args.output}/{result['run_id']}/report.md")
            return 0
        cases = load_cases(args.cases)
        if args.command == "list":
            for case in cases:
                print(json.dumps(case.summary()))
            return 0
        live = live_config_from_args(args)
        result = Evaluator(cases, output_root=args.output, live=live).run(args.case)
    except (WorkflowError, KeyError, OSError, ValueError, TypeError) as error:
        parser.exit(1, f"Evaluation failed to start: {error}\n")
    print(json.dumps({k: result[k] for k in ("run_id", "mode", "benchmark_valid", "summary")}, indent=2))
    print(f"Report: {args.output}/{result['run_id']}/report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
