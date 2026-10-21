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
    args = parser.parse_args(argv)
    try:
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
