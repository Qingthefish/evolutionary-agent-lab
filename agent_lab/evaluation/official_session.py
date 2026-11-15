"""Keep the two reviewed mid-test tasks in one durable group conversation."""

import argparse
from contextlib import contextmanager
import json
from pathlib import Path

from ..budget import descendants
from ..core import Workflow, WorkflowError
from ..files import FileTools
from ..inspection import ArtifactInspector
from ..queries import WorkflowQueries
from .official import OfficialMidTestPlan


TERMINAL = {"succeeded", "failed", "cancelled"}
DATABASE = "workflow.sqlite3"


class OfficialScenarioSession:
    def __init__(self, workflow, plan, binding):
        self.workflow = workflow
        self.chat, self.human = binding["chat"], binding["human"]
        if binding["plan_sha256"] != plan.sha256:
            raise WorkflowError("Session requires the same reviewed mid-test plan")
        self.scenario = self._scenario(plan, binding["scenario"])
        self.agents = tuple(role["id"] for role in self.scenario["roles"])
        members = {row["actor"] for row in workflow.db.execute(
            "SELECT actor FROM members WHERE chat=?", (self.chat,))}
        if workflow._row("chats", self.chat)["kind"] != "group" or members != {self.human, *self.agents}:
            raise WorkflowError("Session group membership differs from the reviewed scenario")

    @staticmethod
    def _scenario(plan, identifier):
        for scenario in plan.dataset["scenarios"]:
            if scenario["id"] == identifier:
                return scenario
        raise WorkflowError("Unknown mid-test scenario")

    @classmethod
    def initialize(cls, workflow, plan, *, scenario, human, plan_sha256):
        if plan_sha256 != plan.sha256:
            raise WorkflowError("Initialization requires the current inspected plan SHA-256")
        selected = cls._scenario(plan, scenario)
        agents = [role["id"] for role in selected["roles"]]
        workflow.db.executescript("""
            CREATE TABLE IF NOT EXISTS official_scenario (
                id INTEGER PRIMARY KEY CHECK(id=1),
                plan_sha256 TEXT NOT NULL, scenario TEXT NOT NULL,
                human TEXT NOT NULL REFERENCES actors(id), chat TEXT NOT NULL REFERENCES chats(id)
            );
            CREATE TABLE IF NOT EXISTS official_roots (
                sequence INTEGER PRIMARY KEY CHECK(sequence IN (1,2)),
                root TEXT NOT NULL UNIQUE REFERENCES tasks(id),
                message INTEGER NOT NULL UNIQUE REFERENCES messages(sequence)
            );
        """)
        with workflow._transaction():
            if workflow.db.execute("SELECT 1 FROM chats LIMIT 1").fetchone():
                raise WorkflowError("Use a fresh state directory for each scenario")
            workflow._register_actor(human, "human")
            for agent in agents:
                workflow._register_actor(agent, "agent")
            chat = workflow._create_chat("group", (human, *agents))
            workflow.db.execute("INSERT INTO official_scenario VALUES(1,?,?,?,?)",
                                (plan.sha256, scenario, human, chat))
        return cls.open(workflow, plan)

    @classmethod
    def open(cls, workflow, plan):
        if not workflow.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='official_scenario'"
        ).fetchone():
            raise WorkflowError("Initialize the scenario before opening it")
        binding = workflow.db.execute("SELECT * FROM official_scenario WHERE id=1").fetchone()
        if binding is None:
            raise WorkflowError("Scenario initialization did not finish")
        return cls(workflow, plan, binding)

    def _root(self, sequence):
        return self.workflow.db.execute("SELECT * FROM official_roots WHERE sequence=?",
                                        (sequence,)).fetchone()

    def post(self, sequence, assignee):
        if type(sequence) is not int or sequence not in (1, 2) or assignee not in self.agents:
            raise WorkflowError("Select a task number and one of the source roles")
        task = self.scenario["tasks"][sequence - 1]
        with self.workflow._transaction():
            previous = self._root(sequence)
            if previous is not None:
                if self.workflow.task(previous["root"], self.human)["assignee"] != assignee:
                    raise WorkflowError("This task already has an assigned root")
                return dict(previous)
            if sequence == 2:
                first = self._root(1)
                if first is None or self.workflow.task(first["root"], self.human)["state"] not in TERMINAL:
                    raise WorkflowError("Task 1 must finish before posting Task 2")
            message = self.workflow._post_message(self.chat, self.human, task["prompt"])
            root = self.workflow._create_task(self.chat, self.human, assignee, task["prompt"])
            self.workflow.db.execute("INSERT INTO official_roots VALUES(?,?,?)", (sequence, root, message))
        return {"sequence": sequence, "root": root, "message": message}

    def carry(self, files, *, source_task, source_path, sha256, target_path):
        """Copy a human-selected, broker-recorded version to a pending Task 2."""
        inspector = ArtifactInspector(self.workflow, files)
        with self.workflow._transaction():
            first, second = self._root(1), self._root(2)
            if first is None or second is None:
                raise WorkflowError("Post both tasks before carrying an output")
            if source_task not in {row["id"] for row in descendants(self.workflow, first["root"])}:
                raise WorkflowError("Select an artifact from the Task 1 tree")
            source = self.workflow.task(source_task, self.human)
            if source["state"] not in TERMINAL:
                raise WorkflowError("Select a closed Task 1 artifact")
            current = inspector.read_file(source_task, self.human, source_path)
            entries = inspector.history(source_task, self.human).get(source_path, [])
            writes = [event for event in entries if event["operation"] != "file_read"]
            if (not writes or writes[-1]["operation"] == "file_deleted"
                    or current["sha256"] != sha256 or writes[-1]["sha256"] != sha256):
                raise WorkflowError("Carry requires the current reviewed SHA-256 and a matching broker receipt")
            target = second["root"]
            receipt = files._provide_text(target, self.human, target_path, current["content"])
            evidence = {**receipt, "source_task": source_task, "source_path": source_path,
                        "source_event": writes[-1]["sequence"]}
            self.workflow._event(target, self.human, "official_input_carried", evidence)
            return evidence

    def status(self):
        queries = WorkflowQueries(self.workflow)
        tasks = []
        for source in self.scenario["tasks"]:
            binding = self._root(source["sequence"])
            record = {"id": source["id"], "sequence": source["sequence"], "state": "not_posted"}
            if binding is not None:
                root = binding["root"]
                detail = queries.task_detail(root, self.human)
                record.update(detail["task"], id=source["id"], root=root,
                              message_sequence=binding["message"], runner=detail["runner"],
                              requests=detail["requests"], children=detail["children"])
                events = detail["events"]
                record["carried_inputs"] = [
                    event["detail"] | {"read_by_root": any(
                        later["sequence"] > event["sequence"] and later["kind"] == "file_read"
                        and later["detail"]["path"] == event["detail"]["path"]
                        and later["detail"]["sha256"] == event["detail"]["sha256"] for later in events)}
                    for event in events if event["kind"] == "official_input_carried"]
            tasks.append(record)
        return {"scenario": self.scenario["id"], "group": self.chat, "human": self.human,
                "roles": list(self.agents), "tasks": tasks, "benchmark_valid": False,
                "conversation": self.workflow.messages(self.chat, self.human)}


@contextmanager
def _workflow(directory, *, fresh=False):
    directory = Path(directory)
    if fresh:
        directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    elif not (directory / DATABASE).is_file():
        raise WorkflowError("Scenario workflow database is missing")
    workflow = Workflow(directory / DATABASE)
    try:
        yield workflow
    finally:
        workflow.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--config", required=True)
    parser.add_argument("--state-dir", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--scenario", required=True)
    init.add_argument("--human", required=True)
    init.add_argument("--plan-sha256", required=True)
    commands.add_parser("status")
    post = commands.add_parser("post")
    post.add_argument("--sequence", required=True, choices=(1, 2), type=int)
    post.add_argument("--assignee", required=True)
    carry = commands.add_parser("carry")
    carry.add_argument("--source-task", required=True)
    carry.add_argument("--source-path", required=True)
    carry.add_argument("--sha256", required=True)
    carry.add_argument("--target-path", required=True)
    args = parser.parse_args(argv)
    try:
        plan = OfficialMidTestPlan(args.config)
        if args.command == "init":
            if args.plan_sha256 != plan.sha256:
                raise WorkflowError("Initialization requires the current inspected plan SHA-256")
            scenario = OfficialScenarioSession._scenario(plan, args.scenario)
            if not args.human.strip() or args.human in {role["id"] for role in scenario["roles"]}:
                raise WorkflowError("Supply a distinct human actor identifier")
        with _workflow(args.state_dir, fresh=args.command == "init") as workflow:
            if args.command == "init":
                session = OfficialScenarioSession.initialize(workflow, plan, scenario=args.scenario,
                                                            human=args.human, plan_sha256=args.plan_sha256)
            else:
                session = OfficialScenarioSession.open(workflow, plan)
            if args.command == "post":
                result = session.post(args.sequence, args.assignee)
            elif args.command == "carry":
                files = FileTools(workflow, Path(args.state_dir) / "files")
                try:
                    result = session.carry(files, source_task=args.source_task, source_path=args.source_path,
                                           sha256=args.sha256, target_path=args.target_path)
                finally:
                    files.close()
            else:
                result = session.status()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (WorkflowError, OSError, ValueError) as error:
        parser.exit(1, f"Mid-test session failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
