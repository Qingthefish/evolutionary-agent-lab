"""Inspect and prepare the instructor's sequential mid-test scenarios.

This is the C06 input adapter, not the S01 execution/scoring driver. It never
creates a workflow, reads credentials, calls a model, or invents human answers.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from ..core import WorkflowError
from ..protocol import strict_json
from .manifest import digest
from .official_dataset import load_mid_test


ADAPTER_PROTOCOL = "official-mid-scenario-continuity-v1"


def _read_json(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise WorkflowError("Official configuration exceeds size limit")
    return strict_json(raw.decode("utf-8"))


def _fields(value, names, label):
    if not isinstance(value, dict) or set(value) != set(names):
        raise WorkflowError(f"{label} has missing or unknown fields")


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class OfficialMidTestPlan:
    """Bind every source byte and operator choice before preparing a handoff."""

    def __init__(self, filename):
        self.filename = Path(filename).resolve()
        config = _read_json(self.filename)
        _fields(config, ("version", "purpose", "archive", "manifest", "runtime", "operator_decisions"), "Official plan")
        if type(config["version"]) is not int or config["version"] != 1 or config["purpose"] != "official_mid_preparation":
            raise WorkflowError("Use the version-1 official mid-test preparation protocol")
        for key in ("archive", "manifest"):
            if not isinstance(config[key], str) or not config[key] or Path(config[key]).is_absolute() or ".." in Path(config[key]).parts:
                raise WorkflowError("Official input paths must be relative to the plan")
        runtime = config["runtime"]
        _fields(runtime, ("provider", "model", "api_key_env", "per_scenario_model_attempts", "max_output_tokens", "tool_policy"), "Runtime choices")
        if runtime["provider"] not in ("deepseek", "hkgai"):
            raise WorkflowError("Use only the course-allowed DeepSeek or HKGAI provider")
        if not isinstance(runtime["api_key_env"], str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", runtime["api_key_env"]):
            raise WorkflowError("Supply a credential variable name, never a key value")
        for key in ("per_scenario_model_attempts", "max_output_tokens"):
            if runtime[key] is not None and (type(runtime[key]) is not int or not 1 <= runtime[key] <= 16384):
                raise WorkflowError("Runtime limits must be null or explicit positive bounded integers")
        decisions = config["operator_decisions"]
        _fields(decisions, ("completion_criteria", "memory_persistence", "repeat_policy", "timing_rule", "html_format_conflict"), "Operator decisions")
        for value in [runtime["model"], runtime["tool_policy"], *decisions.values()]:
            if value is not None and (not isinstance(value, str) or not value.strip() or len(value) > 4096):
                raise WorkflowError("Unresolved choices are null; recorded choices are bounded nonempty text")
        self.dataset = load_mid_test(self.filename.parent / config["archive"])
        if _read_json(self.filename.parent / config["manifest"]) != self.dataset:
            raise WorkflowError("Official source archive differs from its reviewed manifest; re-import and review")
        self.config = config
        self.conditions = {"adapter_protocol": ADAPTER_PROTOCOL, "dataset": self.dataset, "operator_configuration": config}
        # Changes to the importer or adapter invalidate a prepared handoff too.
        self.conditions["adapter_code_sha256"] = digest({
            name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ("official.py", "official_dataset.py")
        })
        self.sha256 = digest(self.conditions)

    def inspect(self):
        runtime = self.config["runtime"]
        unresolved = [f"runtime.{key}" for key, value in runtime.items() if value is None]
        unresolved.extend(f"operator_decisions.{key}" for key, value in self.config["operator_decisions"].items() if value is None)
        tasks = []
        for scenario in self.dataset["scenarios"]:
            for task in scenario["tasks"]:
                blockers = [choice for choice in unresolved
                            if choice != "operator_decisions.html_format_conflict"]
                if task["requested_format"] == "html_slides" and self.config["operator_decisions"]["html_format_conflict"] is None:
                    blockers.append("Source requests HTML slides; the earlier announcement limits documents to MD/TXT")
                tasks.append({"id": task["id"], "scenario": scenario["id"], "sequence": task["sequence"],
                              "depends_on": task["depends_on"], "status": "not_run", "blockers": blockers})
        return {"purpose": "official_mid_preparation", "adapter_protocol": ADAPTER_PROTOCOL,
                "plan_sha256": self.sha256, "dataset_sha256": digest(self.dataset),
                "model_calls": 0, "benchmark_valid": False, "evidence_class": "input_adapter_preparation",
                "execution_supported": False, "execution_note": "S01 must provide the reviewed scenario-session execution and scoring driver",
                "counts": {"scenarios": len(self.dataset["scenarios"]), "roles": sum(len(s["roles"]) for s in self.dataset["scenarios"]),
                           "expected_tasks": len(tasks), "executed_tasks": 0, "not_run_tasks": len(tasks)},
                "unresolved_choices": unresolved, "tasks": tasks,
                "protocol": self.dataset["protocol"],
                "source_authority": "Dataset prompts are task data, not grants of tools, credentials, model access or automatic approval",
                "operator_choices_are_official_rules": False}

    def prepare(self, output, *, plan_sha256):
        current = OfficialMidTestPlan(self.filename)
        if (plan_sha256 != self.sha256 or digest(self.conditions) != self.sha256
                or current.sha256 != self.sha256):
            raise WorkflowError("Preparation requires the current inspected plan SHA-256")
        report = current.inspect()
        output = Path(output)
        # Refuse reuse: an existing run may contain conversations or private evidence.
        output.mkdir(parents=True, exist_ok=False, mode=0o700)
        _write_json(output / "official-plan.json", {"plan_sha256": current.sha256, "conditions": current.conditions, "inspection": report})
        records = []
        for scenario in current.dataset["scenarios"]:
            directory = output / scenario["id"]
            directory.mkdir(mode=0o700)
            _write_json(directory / "scenario.json", {
                "scenario": scenario, "session_protocol": {
                    "group": "one persistent group containing the four source agents and the real human",
                    "task_order": [task["id"] for task in scenario["tasks"]],
                    "task_2": "post only after task 1, retaining the same group and collaboration context",
                    "cross_scenario": "new group; do not expose the prior scenario's private workspaces",
                    "human_responses": "actual requester dialogue only; no scripted answers or approval",
                    "completion": "negotiated criteria and trusted review; no candidate self-grading",
                    "memory": "context continuation is required; additional memory/reset choices remain in operator_decisions",
                }})
            for task in scenario["tasks"]:
                records.append({"id": task["id"], "scenario": scenario["id"], "sequence": task["sequence"],
                                "depends_on": task["depends_on"], "status": "not_run", "conversation_id": None,
                                "root_task_id": None, "dialogue_history": None, "outputs": [],
                                "completion_evidence": None, "total_elapsed_seconds": None,
                                "human_wait_seconds": None, "usage": None})
        _write_json(output / "run-progress.json", {"schema_version": 1, "purpose": "official_mid_preparation",
                    "plan_sha256": self.sha256, "benchmark_valid": False, "execution_started": False,
                    "expected_task_ids": [task["id"] for task in records], "tasks": records})
        return report | {"output": str(output), "prepared": True}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m agent_lab.evaluation.official", allow_abbrev=False,
                                     description="C06 official input preparation; no execution or scores")
    commands = parser.add_subparsers(dest="command", required=True)
    imported = commands.add_parser("import", help="Validate a source ZIP and write its deterministic manifest")
    imported.add_argument("--archive", required=True)
    imported.add_argument("--output", required=True, help="New manifest file; existing files are refused")
    for name in ("inspect", "prepare"):
        command = commands.add_parser(name)
        command.add_argument("--config", required=True, help="Local plan beside the instructor archive and generated manifest")
        if name == "prepare":
            command.add_argument("--output", required=True, help="Fresh ignored run directory")
            command.add_argument("--plan-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "import":
            result = load_mid_test(args.archive)
            with open(
                args.output,
                "x", encoding="utf-8", opener=lambda path, flags: os.open(path, flags, 0o600)
            ) as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.write("\n")
            print(json.dumps({"manifest": args.output, "source_sha256": result["source"]["sha256"], "model_calls": 0}, indent=2))
        else:
            plan = OfficialMidTestPlan(args.config)
            result = plan.inspect() if args.command == "inspect" else plan.prepare(args.output, plan_sha256=args.plan_sha256)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (WorkflowError, OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(1, f"Official input preparation failed: {error}\n")


if __name__ == "__main__":
    sys.exit(main())
