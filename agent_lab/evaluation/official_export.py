"""Export one mid-test scenario's execution record for review, read-only.

The source database is opened read-only and copied with the SQLite backup API;
existing query helpers run on that temporary copy. Nothing is written inside
the state directory, no model is called and no credential is read. The export
reports what was recorded: it does not score, repair or complete anything.
"""

import argparse
from contextlib import closing, ExitStack
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import tempfile

from ..budget import descendants
from ..core import Workflow, WorkflowError
from ..files import FileTools
from ..queries import WorkflowQueries, redact
from .official import OfficialMidTestPlan
from .official_session import DATABASE, OfficialScenarioSession

SCHEMA = "official-scenario-export-v1"
SOURCES = ("agent_lab/evaluation/official.py", "agent_lab/evaluation/official_dataset.py",
           "agent_lab/evaluation/official_session.py", "agent_lab/evaluation/official_live.py",
           "agent_lab/evaluation/official_export.py", "agent_lab/scheduler.py", "agent_lab/runner.py",
           "agent_lab/gateway.py", "agent_lab/files.py", "agent_lab/deepseek.py", "agent_lab/hkgai.py",
           "agent_lab/retrieval.py", "agent_lab/sandbox.py")
_FULL = 10 ** 9  # Keep whole recorded text; credential-like keys and values are still hidden.


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _rows(db, table, tasks):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
        return []
    marks = ",".join("?" * len(tasks))
    rows = []
    for row in db.execute(f"SELECT * FROM {table} WHERE task IN ({marks}) ORDER BY rowid", tuple(tasks)):
        record = {}
        for key in row.keys():
            value = row[key]
            if isinstance(value, str) and value[:1] in "{[":
                try:
                    value = json.loads(value)
                except ValueError:
                    pass
            record[key] = value
        rows.append(redact(record, limit=_FULL))
    return rows


def _code_identity():
    root = Path(__file__).resolve().parents[2]
    commit = None
    try:
        done = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=10, check=False)
        if done.returncode == 0 and len(done.stdout.strip()) == 40:
            commit = done.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return {"commit": commit, "source_sha256": {
        name: _sha((root / name).read_bytes()) for name in SOURCES if (root / name).is_file()}}


def _copy_files(state, task, target):
    """Copy one task's files without following links; report what was skipped."""
    copied, skipped = [], []
    # Anchor every directory and file read to open descriptors as the broker
    # does. The task directory itself may have been replaced after execution.
    with ExitStack() as opened:
        fd = os.open(state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        opened.callback(os.close, fd)
        for name in ("files", "tasks", _sha(task.encode())):
            try:
                fd = FileTools._directory(fd, name)
            except FileNotFoundError:
                return copied, skipped
            opened.callback(os.close, fd)
        reader = object.__new__(FileTools)
        reader.max_bytes = 1024 * 1024

        def walk(directory, prefix=""):
            for name in sorted(os.listdir(directory)):
                relative = prefix + name
                info = os.stat(name, dir_fd=directory, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    child = FileTools._directory(directory, name)
                    try:
                        walk(child, relative + "/")
                    finally:
                        os.close(child)
                elif stat.S_ISREG(info.st_mode):
                    data = reader._read(directory, name)
                    destination = target / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(data)
                    copied.append({"path": relative, "sha256": _sha(data), "bytes": len(data)})
                else:
                    skipped.append(relative)

        walk(fd)
    return copied, skipped


def _write(output, name, value, manifest):
    data = (value if isinstance(value, str) else
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (output / name).write_bytes(data)
    manifest.append({"path": name, "sha256": _sha(data), "bytes": len(data)})


def export(config, state_dir, output):
    """Write a new export directory; a failed export leaves no partial directory behind."""
    created = Path(output).resolve()
    if created == Path(state_dir).resolve() or Path(state_dir).resolve() in created.parents:
        raise WorkflowError("Write the export outside the state directory")
    created.mkdir(parents=True, exist_ok=False, mode=0o700)
    try:
        return _export(config, state_dir, created)
    except BaseException:
        if created.is_dir():
            shutil.rmtree(created)
        raise


def _export(config, state_dir, output):
    plan = OfficialMidTestPlan(config)
    state, output = Path(state_dir).resolve(), Path(output).resolve()
    database = state / DATABASE
    if not database.is_file():
        raise WorkflowError("Scenario workflow database is missing")
    if output == state or state in output.parents:
        raise WorkflowError("Write the export outside the state directory")
    manifest = []
    with tempfile.TemporaryDirectory(prefix="official-export-") as scratch:
        copy = Path(scratch) / DATABASE
        with closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True)) as source, \
             closing(sqlite3.connect(copy)) as target:
            source.execute("PRAGMA query_only=ON")
            source.backup(target)
        snapshot_database_sha256 = _sha(copy.read_bytes())
        database_sha256 = _sha(database.read_bytes())
        workflow = Workflow(copy)
        try:
            session = OfficialScenarioSession.open(workflow, plan)
            status = session.status()
            queries = WorkflowQueries(workflow)
            db = workflow.db
            trees, tasks, files, configuration, modes = [], [], [], [], set()
            for record in status["tasks"]:
                if record["state"] == "not_posted":
                    trees.append({"id": record["id"], "sequence": record["sequence"], "state": "not_posted",
                                  "tasks": []})
                    continue
                members = []
                for row in descendants(workflow, record["root"]):
                    detail = queries.task_detail(row["id"], session.human)
                    runner = detail["runner"]
                    if runner:
                        modes.add("synthetic" if runner["synthetic"] else "live")
                    copied, skipped = _copy_files(state, row["id"], output / "files" / row["id"])
                    for item in copied:
                        manifest.append(item | {"path": f"files/{row['id']}/{item['path']}"})
                    files.append({"task": row["id"], "assignee": row["assignee"], "files": copied,
                                  "skipped_non_regular": skipped})
                    members.append({
                        "task": detail["task"], "depth": row["depth"], "children": detail["children"],
                        "stop_reason": runner["stop_reason"] if runner else None,
                        "runner": runner, "requests": detail["requests"],
                        "provider_failures": [e for e in detail["events"] if e["kind"] == "provider_request_failed"],
                        "reviews": [e for e in detail["events"] if e["kind"] == "human_review_recorded"],
                        "events": detail["events"], "artifacts": detail["artifacts"]})
                    tasks.append(row["id"])
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='scheduler_runs'").fetchone():
                    run = db.execute("SELECT config FROM scheduler_runs WHERE root=?", (record["root"],)).fetchone()
                    if run:
                        configuration.append({"sequence": record["sequence"], "root": record["root"],
                                              "scheduler": redact(json.loads(run["config"]), limit=_FULL)})
                trees.append({"id": record["id"], "sequence": record["sequence"], "state": record["state"],
                              "root": record["root"], "message_sequence": record["message_sequence"],
                              "elapsed_seconds": record["elapsed_seconds"],
                              "human_wait_seconds": record["human_wait_seconds"],
                              "carried_inputs": record["carried_inputs"], "tasks": members})
            evidence = ("no_model_turns" if not modes else "synthetic_offline_fixture" if modes == {"synthetic"}
                        else "live" if modes == {"live"} else "mixed_synthetic_and_live")
            scenario = {
                "schema": SCHEMA, "plan_sha256": plan.sha256, "scenario": status["scenario"],
                "group": status["group"], "human": status["human"], "source_database_sha256": database_sha256,
                "snapshot_database_sha256": snapshot_database_sha256,
                "evidence_class": evidence, "synthetic": "synthetic" in modes, "benchmark_valid": False,
                "roles": session.scenario["roles"],
                "tasks": [{"id": task["id"], "sequence": task["sequence"], "prompt": task["prompt"],
                           "status": tree["state"]} for task, tree in zip(session.scenario["tasks"], trees)],
                "note": "Recorded evidence only. A failed or not-posted task stays in the record; nothing here is a score."}
            _write(output, "scenario.json", scenario, manifest)
            conversation = status["conversation"]
            _write(output, "conversation.json", conversation, manifest)
            lines = [f"# Group conversation: {status['scenario']}", "",
                     f"Evidence class: {evidence}. Plan `{plan.sha256}`.", ""]
            for message in conversation:
                lines += [f"## {message['sequence']}. {message['sender']}", "", message["body"], ""]
            _write(output, "conversation.md", "\n".join(lines), manifest)
            _write(output, "tasks.json", trees, manifest)
            _write(output, "human.json", {
                "requests": [request for tree in trees for member in tree["tasks"] for request in member["requests"]],
                "reviews": [review for tree in trees for member in tree["tasks"] for review in member["reviews"]]},
                manifest)
            _write(output, "tool-calls.json", _rows(db, "tool_calls", tasks) if tasks else [], manifest)
            _write(output, "runner-sessions.json", _rows(db, "runner_sessions", tasks) if tasks else [], manifest)
            _write(output, "retrieval.json", _rows(db, "retrieval_records", tasks) if tasks else [], manifest)
            _write(output, "sandbox.json", _rows(db, "sandbox_runs", tasks) if tasks else [], manifest)
            _write(output, "files.json", files, manifest)
            _write(output, "configuration.json", {
                "plan_runtime": {k: v for k, v in plan.config["runtime"].items() if k != "api_key_env"},
                "operator_decisions": plan.config["operator_decisions"], "recorded_at_first_scheduler_use": configuration},
                manifest)
            _write(output, "code.json", _code_identity(), manifest)
        finally:
            workflow.close()
    summary = {"schema": SCHEMA, "scenario": scenario["scenario"], "plan_sha256": plan.sha256,
               "evidence_class": evidence, "task_states": [tree["state"] for tree in trees],
               "files": sorted(manifest, key=lambda item: item["path"])}
    (output / "manifest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                                          encoding="utf-8")
    return {"output": str(output), "scenario": scenario["scenario"], "evidence_class": evidence,
            "task_states": summary["task_states"], "exported_files": len(manifest), "model_calls": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--config", required=True)
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--output", required=True, help="New directory outside the state directory")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(export(args.config, args.state_dir, args.output), ensure_ascii=False, indent=2))
    except (WorkflowError, OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f"Mid-test export failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
