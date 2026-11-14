#!/usr/bin/env python3
"""Reproduce the documented offline setup using this Python interpreter.

Run in a fresh Python >=3.12 venv with no packages installed, for example:
    .venv/bin/python scripts/check_setup.py --output runs/d04-clean-setup
--repo may select a separate, clean checkout. Nothing is installed and no live,
web or Docker command is selected. Logs and failed attempts are preserved.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import time


def first_json(text):
    """Evaluation run prints a JSON document followed by a report-path line."""
    return json.JSONDecoder().raw_decode(text.lstrip())[0]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fixture(report):
    require(report.get("mode") == "offline_fixture", "Expected an offline fixture")
    require(report.get("model_calls") == 0, "Fixture must declare zero model calls")
    require(report.get("benchmark_valid") is False, "Fixture must not claim a benchmark")


def suite_counts(text):
    match = re.search(r"^Ran (\d+) tests? in [\d.]+s$", text, re.MULTILINE)
    require(match is not None, "Could not read unittest's test count")
    counts = {"discovered": int(match[1]), "skipped": 0, "failures": 0,
              "errors": 0, "expected_failures": 0, "unexpected_successes": 0}
    outcome = re.search(r"^(?:OK|FAILED)(?: \(([^\n]+)\))?$", text, re.MULTILINE)
    require(outcome is not None, "Could not read unittest's final outcome")
    names = {"skipped": "skipped", "failures": "failures", "errors": "errors",
             "expected failures": "expected_failures", "unexpected successes": "unexpected_successes"}
    for key, value in re.findall(r"([a-z ]+)=(\d+)", outcome[1] or ""):
        if key.strip() in names:
            counts[names[key.strip()]] = int(value)
    counts["passed"] = counts["discovered"] - sum(counts[k] for k in
        ("skipped", "failures", "errors", "expected_failures", "unexpected_successes"))
    counts["skip_details"] = [{"test": test, "reason": reason} for test, reason in
        re.findall(r"^(.*?) \.\.\. skipped (.+)$", text, re.MULTILINE)]
    return counts


class Reproduction:
    def __init__(self, repo, output, timeout):
        self.repo, self.output, self.timeout = repo, output, timeout
        self.cases = []
        self.env = os.environ.copy()
        # Do not inherit opt-in actual-container settings or a custom import path.
        for name in list(self.env):
            if name in {"AGENT_LAB_DOCKER_HOST", "AGENT_LAB_PYTHON_IMAGE", "PYTHONPATH"} or any(
                    token in name.upper() for token in ("API_KEY", "ACCESS_TOKEN", "SECRET", "CREDENTIAL")):
                self.env.pop(name)
        self.env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
                        PYTHONUTF8="1", GIT_TERMINAL_PROMPT="0")
        self.summary = {
            "evidence_class": "independent_offline_setup_reproduction",
            "benchmark_valid": False, "model_calls": 0,
            "scope": "Existing scripted CLI fixtures, static inspection and engineering tests; no live-model or Docker acceptance",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "python": {"version": platform.python_version(), "executable": sys.executable,
                       "virtual_environment": sys.prefix != sys.base_prefix},
            "platform": {"system": platform.system(), "release": platform.release(), "os_name": os.name},
            "optional_dependencies": {"textual_present": importlib.util.find_spec("textual") is not None,
                                      "actual_container_checks": "disabled by removing Docker opt-in variables"},
            "cases": self.cases,
        }
        self.summary["clean_core_environment"] = (self.summary["python"]["virtual_environment"]
            and not self.summary["optional_dependencies"]["textual_present"])

    def save(self):
        (self.output / "summary.json").write_text(json.dumps(self.summary, indent=2) + "\n", encoding="utf-8")

    def source_identity(self):
        def git(*args):
            return subprocess.run(["git", *args], cwd=self.repo, env=self.env,
                                  capture_output=True, timeout=15, check=True).stdout
        try:
            status = git("status", "--porcelain").decode("utf-8", errors="replace")
            self.summary["source"] = {
                "repository": str(self.repo), "head": git("rev-parse", "HEAD").decode().strip(),
                "dirty": bool(status), "status_porcelain": status.splitlines(),
                "tracked_diff_sha256": hashlib.sha256(git("diff", "--binary", "HEAD", "--")).hexdigest(),
                "diff_scope": "Tracked diff against HEAD; untracked paths appear only in status_porcelain",
            }
        except (OSError, subprocess.SubprocessError) as error:
            self.summary["source"] = {"repository": str(self.repo), "error": type(error).__name__}

    def run(self, name, args, validate=None, *, refused=False, dependency=None):
        number = len(self.cases) + 1
        command = [sys.executable, *args]
        record = {"name": name, "command": command, "expected": "refused" if refused else "success"}
        self.cases.append(record)
        if dependency:
            record.update(status="blocked", reason=dependency, elapsed_seconds=0, exit_code=None)
            self.save()
            return None
        started = time.monotonic()
        stdout, stderr = "", ""
        process = None
        try:
            process = subprocess.Popen(command, cwd=self.repo, env=self.env, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                start_new_session=os.name == "posix")
            try:
                stdout, stderr = process.communicate(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                stdout, stderr = process.communicate()
                raise TimeoutError(f"Command exceeded {self.timeout} seconds")
            record["exit_code"] = process.returncode
            observed = validate(stdout, stderr) if validate else None
            if observed is not None:
                record["observed"] = observed
            require((process.returncode != 0) if refused else (process.returncode == 0),
                    f"Unexpected exit code {process.returncode}")
            record["status"] = "passed"
        except (OSError, ValueError, KeyError, TypeError, TimeoutError) as error:
            record.update(status="failed", reason=f"{type(error).__name__}: {error}")
            record.setdefault("exit_code", process.returncode if process else None)
        finally:
            record["elapsed_seconds"] = round(time.monotonic() - started, 3)
            prefix = f"{number:02d}-{name}"
            for label, content in (("stdout", stdout), ("stderr", stderr)):
                path = self.output / f"{prefix}.{label}.log"
                path.write_text(content, encoding="utf-8")
                record[f"{label}_log"] = path.name
            self.save()
        print(f"{number:02d} {name}: {record['status']}", file=sys.stderr, flush=True)
        return record.get("observed") if record["status"] == "passed" else None

    def execute(self):
        self.source_identity()
        self.save()
        for name in ("demo", "files-demo", "memory-demo", "protocol-demo", "runner-demo", "scheduler-demo"):
            def check(stdout, _stderr):
                report = first_json(stdout)
                fixture(report)
                return {key: report[key] for key in ("mode", "model_calls", "benchmark_valid")}
            self.run(name, ["-m", "agent_lab", name, "--state-dir", str(self.output / name)], check)

        self.run("console-help", ["-m", "agent_lab.console", "--help"],
                 lambda out, err: require("advance" in out and "release" in out, "Missing console commands"))
        console = ["-m", "agent_lab.console", "--state-dir", str(self.output / "console")]
        def created(out, _err):
            data = first_json(out)
            require(data.get("execution") == "not_started" and isinstance(data.get("task"), str),
                    "Unconfigured task must remain unstarted")
            return {"task": data["task"], "execution": data["execution"]}
        new = self.run("console-new", console + ["new", "--goal", "Reproduce offline setup"], created)
        task = new["task"] if new else None
        def status(out, _err):
            data = first_json(out)
            require(data["task"]["state"] == "pending", "Unconfigured task must remain pending")
            return {"state": data["task"]["state"]}
        self.run("console-status", console + ["status", "--task", task or ""], status,
                 dependency=None if task else "console-new did not return a validated task ID")
        self.run("console-advance-refused", console + ["advance", task or ""],
                 lambda out, err: require("offline mode cannot execute arbitrary tasks" in err,
                                          "Expected missing-scheduler refusal"), refused=True,
                 dependency=None if task else "console-new did not return a validated task ID")

        def listed(out, _err):
            cases = [json.loads(line) for line in out.splitlines() if line.strip()]
            require(cases and len({c["id"] for c in cases}) == len(cases), "Expected unique evaluation cases")
            return {"cases": len(cases), "ids": [c["id"] for c in cases]}
        listing = self.run("evaluation-list", ["-m", "agent_lab.evaluation", "list"], listed)
        def evaluated(out, _err):
            data = first_json(out)
            require(data.get("mode") == "offline_fixture" and data.get("benchmark_valid") is False,
                    "Evaluation CLI must identify an offline fixture")
            report = json.loads((self.output / "evaluations" / data["run_id"] / "results.json").read_text(encoding="utf-8"))
            fixture(report)
            require(report["model_calls"] == 0, "Evaluation must make zero model calls")
            require(report["results"], "Evaluation contains no results")
            if listing:
                require(sorted(listing["ids"]) == sorted(r["case"]["id"] for r in report["results"]), "Case list/run mismatch")
            for result in report["results"]:
                expected = ("not_configured" if result["case"]["driver"] == "live_scheduler" else
                            "acceptance_failed" if result["control"] == "negative" else "completed")
                require(result["classification"] == expected, f"Unexpected classification for {result['case']['id']}")
            return report["summary"]
        self.run("evaluation-run", ["-m", "agent_lab.evaluation", "run", "--output", str(self.output / "evaluations")], evaluated)

        def inspected(out, _err):
            data = first_json(out)
            require(data.get("model_calls") == 0 and data.get("benchmark_valid") is False,
                    "Inspection must be offline and not a benchmark")
            require(data.get("configured_to_attempt") is False and data.get("blockers"),
                    "Clean setup should identify missing live configuration")
            require(re.fullmatch(r"[0-9a-f]{64}", data.get("plan_sha256", "")), "Missing inspected fingerprint")
            return {k: data[k] for k in ("plan_sha256", "model_calls", "configured_to_attempt", "blockers")}
        plan = self.run("development-plan", ["-m", "agent_lab.evaluation", "plan", "--config", "evaluation/development-plan.json"], inspected)
        self.run("experience-plan", ["-m", "agent_lab.evaluation", "experience", "plan", "--config", "evaluation/required-actions-experience-plan.json"], inspected)
        forbidden = self.output / "unauthorized-execution"
        def no_permission(out, err):
            require("explicit model-call authorization" in err and not forbidden.exists(),
                    "Unauthorized execution must refuse before creating run state")
        self.run("execute-refused", ["-m", "agent_lab.evaluation", "execute", "--config", "evaluation/development-plan.json",
                 "--plan-sha256", plan["plan_sha256"] if plan else "", "--output", str(forbidden)], no_permission,
                 refused=True, dependency=None if plan else "development-plan did not return a validated fingerprint")
        def tested(out, err):
            counts = suite_counts(out + "\n" + err)
            require(counts["discovered"] > 0, "Engineering suite discovered no tests")
            return counts
        self.run("unittest", ["-m", "unittest", "discover", "-s", "tests", "-v"], tested)
        self.summary.update(ended_at=datetime.now(timezone.utc).isoformat(),
                            passed=sum(c["status"] == "passed" for c in self.cases),
                            failed=sum(c["status"] == "failed" for c in self.cases),
                            blocked=sum(c["status"] == "blocked" for c in self.cases))
        self.summary["success"] = self.summary["passed"] == 16
        self.save()
        print(json.dumps(self.summary, indent=2))
        return 0 if self.summary["success"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1], help="Repository checkout to reproduce")
    parser.add_argument("--output", type=Path, required=True, help="New evidence directory, relative to --repo or absolute; never reused")
    parser.add_argument("--timeout", type=int, default=300, help="Per-command timeout in seconds (1-600; default 300)")
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        parser.error("Use Python 3.12 or newer")
    if not 1 <= args.timeout <= 600:
        parser.error("--timeout must be between 1 and 600 seconds")
    repo = args.repo.resolve()
    if not (repo / "agent_lab" / "__main__.py").is_file() or not (repo / "tests").is_dir():
        parser.error("--repo must select the evolutionary-agent-lab repository root")
    candidate = repo / args.output
    if candidate.exists() or candidate.is_symlink():
        parser.error("Output already exists; choose a new path to preserve previous evidence")
    output = candidate.resolve()
    try:
        output.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        parser.error(f"Cannot create output directory: {error}")
    return Reproduction(repo, output, args.timeout).execute()


if __name__ == "__main__":
    sys.exit(main())
