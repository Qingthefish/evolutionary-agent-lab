"""Durable cooperative task-tree scheduler; model proposals choose delegation.

One controller performs one ready task turn at a time. It yields at human or
independent-review boundaries and never replays an uncertain provider/tool turn.
This is infrastructure, not evidence of live-model collaboration quality.
"""

from dataclasses import asdict, dataclass
import json
from uuid import uuid4

from . import budget, recovery
from .deepseek import DeepSeekClient, DeepSeekHTTP
from .hkgai import HKGAIClient, HKGAIHTTP
from .gateway import ToolGateway, _SPECS
from .runner import Limits, RunnerError, TaskRunner
from .core import WorkflowError
from .delegation import input_records, normalize_inputs
from .model_context import CONTEXT_POLICY, peer_description


@dataclass(frozen=True)
class Role:
    instructions: str
    tools: tuple
    delegates: tuple = ()
    limits: Limits = Limits()
    tool_calls: int = 32

    def __post_init__(self):
        if (not isinstance(self.instructions, str) or not self.instructions.strip()
                or len(self.instructions) > 4096 or not isinstance(self.limits, Limits)
                or not isinstance(self.tools, tuple) or not self.tools
                or any(not isinstance(name, str) for name in self.tools)
                or len(set(self.tools)) != len(self.tools)
                or not isinstance(self.delegates, tuple)
                or any(not isinstance(name, str) or not name.strip() for name in self.delegates)
                or len(set(self.delegates)) != len(self.delegates)
                or type(self.tool_calls) is not int or not 1 <= self.tool_calls <= 1000):
            raise RunnerError("Provide bounded role instructions, distinct tools/delegates, and explicit limits")


class MultiAgentScheduler:
    def __init__(self, workflow, files, root, *, human, roles, clients, mode,
                 constraints, verifier_factory, acceptance_id, limits=budget.TreeLimits(),
                 memory=None, executor=None, git=None, retrieval=None, capture_memory=False, child_retries=0, message_floor=0,
                 delegation_rules=None, delegation_inputs=None):
        self.workflow, self.files, self.root = workflow, files, root
        self.human, self.roles, self.clients = human, dict(roles), dict(clients)
        self.mode, self.constraints = mode, constraints
        self.verifier_factory, self.acceptance_id = verifier_factory, acceptance_id
        self.delegation_rules = delegation_rules
        self.delegation_inputs = normalize_inputs(delegation_inputs)
        if any(a not in self.roles for a, _, _ in self.delegation_inputs):
            raise RunnerError("Delegation input requirements must name configured roles")
        self.memory, self.executor, self.git = memory, executor, git
        self.retrieval, self.capture_memory = retrieval, capture_memory
        if type(capture_memory) is not bool or (capture_memory and memory is None):
            raise RunnerError("Outcome capture requires an explicit memory backend")
        self.child_retries = child_retries
        if type(message_floor) is not int or message_floor < 0:
            raise RunnerError("Message boundary must be a nonnegative sequence number")
        self.message_floor = message_floor
        self.owner = uuid4().hex
        task = workflow.task(root, human)
        if (task["parent"] or not self.roles or len(self.roles) > 16
                or self.roles.keys() != self.clients.keys() or task["assignee"] not in self.roles
                or not callable(verifier_factory) or not isinstance(acceptance_id, str)
                or not acceptance_id.strip() or len(acceptance_id) > 128
                or mode not in {"offline_fixture", "live"}
                or not isinstance(constraints, list) or len(constraints) > 100
                or any(not isinstance(item, str) or not item.strip() or len(item) > 4096 for item in constraints)):
            raise RunnerError("Configure a root goal, eligible roles, constraints, and a versioned trusted acceptance policy")
        if files.workflow is not workflow or workflow._row("actors", human)["kind"] != "human":
            raise RunnerError("Configure matching file tools and a human conversation member")
        if ((memory is not None and memory.workflow is not workflow)
                or (executor is not None and (executor.workflow is not workflow or executor.files is not files))
                or (git is not None and git.workflow is not workflow)
                or (retrieval is not None and (retrieval.workflow is not workflow or retrieval.files is not files))):
            raise RunnerError("Scheduler backends must belong to the same workflow and files")
        self.constraints = list(constraints)
        models = set()
        for agent, role in self.roles.items():
            workflow._member(task["chat"], agent)
            if (workflow._row("actors", agent)["kind"] != "agent" or not isinstance(role, Role)
                    or not set(role.delegates) <= self.roles.keys()
                    or bool(role.delegates) != bool(set(role.tools) & {"delegate_task", "delegate_with_inputs"})
                    or not set(role.tools) <= _SPECS.keys()
                    or (set(role.tools) & {"search_memory", "select_memory", "record_lesson"} and memory is None)
                    or (set(role.tools) & {"search_web", "retrieve_text"} and retrieval is None)
                    or ("run_python" in role.tools and executor is None)
                    or (any(name.startswith("git_") for name in role.tools) and git is None)
                    or not isinstance(self.clients[agent], DeepSeekClient)):
                raise RunnerError("Roles must match trusted capabilities, agents, delegates, and provider clients")
            if self.clients[agent].tool_choice == 'required' and 'submit_for_verification' not in role.tools:
                raise RunnerError("Required-action roles need the independent verification proposal tool")
            models.add(self.clients[agent].model)
            # Validate transport mode before persisting a schedulable run.
            if (mode == "live") != (type(self.clients[agent].transport) in (DeepSeekHTTP, HKGAIHTTP)):
                raise RunnerError("Live and synthetic scheduler transports cannot be interchanged")
            if mode == "live" and type(self.clients[agent]) is not (
                    HKGAIClient if type(self.clients[agent].transport) is HKGAIHTTP else DeepSeekClient):
                raise RunnerError("Live client protocol must match its selected provider")
        if len(models) != 1:
            raise RunnerError("Use the same explicit allowed-model identifier for every role")
        if mode == "live" and len({type(c.transport) for c in self.clients.values()}) != 1:
            raise RunnerError("Use the same explicit allowed provider for every role")
        # The acceptance callable itself remains trusted application code, never
        # a tool argument. Its stable ID must change if its behavior changes.
        settings = {"human": human, "roles": {key: asdict(value) for key, value in self.roles.items()},
            "clients": {key: {"model": client.model, "max_output_tokens": client.max_tokens,
                              **({'tool_choice': client.tool_choice} if client.tool_choice != 'auto' else {})}
                        for key, client in self.clients.items()},
            "mode": mode, "constraints": constraints, "acceptance_id": acceptance_id,
            "memory_namespace": memory.namespace if memory is not None else None,
            "executor": executor.configuration() if executor is not None else None}
        if mode == "live" and type(next(iter(self.clients.values())).transport) is HKGAIHTTP:
            settings["provider"] = {"name": "hkgai", "endpoint": HKGAIHTTP.endpoint}
        if git is not None:  # Absent key keeps configurations persisted before Git support unchanged.
            settings["git"] = git.configuration()
        if retrieval is not None:
            settings["retrieval"] = retrieval.configuration()
        if capture_memory:
            settings["capture_memory"] = "terminal-observation-and-candidate-v1"
        if child_retries:
            settings["child_retries"] = child_retries
        if message_floor:
            settings["message_floor"] = message_floor
        if delegation_rules is not None:
            if (not isinstance(delegation_rules, tuple) or not 1 <= len(delegation_rules) <= 100
                    or any(not isinstance(r, tuple) or len(r) != 2 or not isinstance(r[0], str) or r[0] not in self.roles
                           or not isinstance(r[1], str) or not r[1].strip() or len(r[1]) > 4096 for r in delegation_rules)
                    or len(set(delegation_rules)) != len(delegation_rules)):
                raise RunnerError("Use distinct trusted delegation rules for configured roles")
            settings["delegation_rules"] = sorted(delegation_rules)
            settings["model_context"] = CONTEXT_POLICY
        if self.delegation_inputs:
            settings["delegation_inputs"] = input_records(self.delegation_inputs)
        config = json.dumps(settings, sort_keys=True, allow_nan=False)
        budget.configure(workflow, root, limits)
        workflow.db.execute("""CREATE TABLE IF NOT EXISTS scheduler_runs (
            root TEXT PRIMARY KEY REFERENCES tasks(id), config TEXT NOT NULL, owner TEXT
        )""")
        previous = workflow.db.execute("SELECT * FROM scheduler_runs WHERE root=?", (root,)).fetchone()
        if previous and previous["config"] != config:
            raise RunnerError("Persisted scheduler roles, constraints, model, tools, or acceptance policy differ")
        recovery.configure(workflow, root, child_retries)
        with workflow._transaction():
            previous = workflow.db.execute("SELECT * FROM scheduler_runs WHERE root=?", (root,)).fetchone()
            if previous and previous["config"] != config:
                raise RunnerError("Persisted scheduler roles, constraints, model, tools, or acceptance policy differ")
            workflow.db.execute("INSERT OR IGNORE INTO scheduler_runs VALUES(?,?,NULL)", (root, config))

    def runner(self, task_id):
        """Trusted access for review/reconciliation; not a model-selected factory."""
        tree = {row["id"]: row for row in budget.descendants(self.workflow, self.root)}
        if task_id not in tree:
            raise RunnerError("Task is outside this scheduler's goal")
        task = tree[task_id]
        actor = task["assignee"]
        if actor not in self.roles:
            raise RunnerError("Delegated task has no configured role")
        role = self.roles[actor]
        gateway = ToolGateway(self.workflow, self.files, task_id, actor, human=self.human,
            allowed=role.tools, delegates=role.delegates, memory=self.memory,
            executor=self.executor, max_calls=role.tool_calls, git=self.git, retrieval=self.retrieval, message_floor=self.message_floor,
            delegation_rules=self.delegation_rules, delegation_inputs=self.delegation_inputs or None)
        acceptance = self.verifier_factory(dict(task))
        if acceptance is None:
            verifier, version = None, None
        elif isinstance(acceptance, tuple) and len(acceptance) == 2:
            verifier, version = acceptance
        else:
            raise RunnerError("Acceptance factory returns (trusted callable, version) or explicit review")
        return TaskRunner(gateway, self.clients[actor], mode=self.mode, constraints=self.constraints,
            limits=role.limits, verifier=verifier, verifier_id=version, role={
                "agent": actor, "instructions": role.instructions,
                "eligible_agents": {key: (peer_description(self.roles[key]) if self.delegation_rules is not None
                                         else self.roles[key].instructions) for key in role.delegates},
            })

    def status(self):
        root = self.workflow.task(self.root, self.human)
        shared = budget.status(self.workflow, self.root)
        return {"mode": self.mode, "root_task": self.root, "task_state": root["state"],
            "budget": shared,
            "tasks": [{key: task[key] for key in ("id", "parent", "assignee", "state", "depth")}
                      for task in budget.descendants(self.workflow, self.root)],
            "model_calls": 0 if self.mode == "offline_fixture" else None,
            "live_model_attempts": shared["attempts"] if self.mode == "live" else 0,
            "benchmark_valid": False}

    def _fail(self, reason):
        root = self.workflow.task(self.root, self.human)
        if root["state"] == "pending":
            self.workflow.start_task(self.root, root["assignee"])
        if root["state"] not in {"succeeded", "failed", "cancelled"}:
            self.workflow.finish_task(self.root, root["assignee"], error=reason)
        return self.status() | {"state": "terminal", "reason": reason}

    def _advance(self):
        if self.workflow.task(self.root, self.human)["state"] in {"succeeded", "failed", "cancelled"}:
            return self.status() | {"state": "terminal"}
        try:
            budget.check(self.workflow, self.root, after_response=True)
        except budget.TreeBudgetError as error:
            return self._fail(str(error))
        tasks = budget.descendants(self.workflow, self.root)
        sessions = {}
        if self.workflow.db.execute("SELECT 1 FROM sqlite_master WHERE name='runner_sessions'").fetchone():
            sessions = {row["task"]: row for row in self.workflow.db.execute("""
                WITH RECURSIVE tree(id) AS (
                    SELECT ? UNION ALL SELECT t.id FROM tasks t JOIN tree ON t.parent=tree.id
                ) SELECT s.task,s.status FROM runner_sessions s JOIN tree ON tree.id=s.task
            """, (self.root,))}
        uncertain = [{"task": key, "kind": "reconciliation", "runner_state": row["status"]}
                     for key, row in sessions.items() if row["status"] in {"calling", "processing", "stopping"}]
        if uncertain:
            return self.status() | {"state": "blocked", "needs": uncertain}
        active = recovery.active_tasks(self.workflow, tasks)
        for task in active:
            if task["state"] == "failed" and self.child_retries:
                try:
                    recovery.availability(self.workflow, task["parent"], task["id"], require_running=False)
                except WorkflowError as error:
                    return self._fail(str(error))
                continue
            if task["state"] in {"failed", "cancelled"}:
                return self._fail("Delegated task " + task["id"] + " ended " + task["state"] + "; inspect its evidence before a new plan")
            if task["state"] in {"succeeded", "failed", "cancelled"}:
                continue
            # Deadline checks still apply to human/review/child waiting tasks.
            if task["assignee"] not in self.roles:
                return self._fail("Delegated task has no trusted configured role")
            if self.workflow.clock() - task["created"] >= self.roles[task["assignee"]].limits.duration_seconds:
                return self._fail("Assigned task duration exhausted; partial artifacts retained")
        needs = []
        for task in active:
            if task["state"] in {"succeeded", "failed", "cancelled"}:
                continue
            if task["state"].startswith("waiting_"):
                requests = [dict(row) for row in self.workflow.db.execute(
                    "SELECT id,kind,responder,prompt,action FROM requests WHERE task=? AND answered=0 ORDER BY rowid",
                    (task["id"],))]
                needs.append({"task": task["id"], "kind": task["state"], "requests": requests})
                continue
            if any(child["parent"] == task["id"] and child["state"] not in {"succeeded", "failed"} for child in active):
                continue
            if task["id"] in sessions and sessions[task["id"]]["status"] == "awaiting_verification":
                needs.append({"task": task["id"], "kind": "independent_verification"})
                continue
            if task["state"] == "pending":
                self.workflow.start_task(task["id"], task["assignee"])
            runner = self.runner(task["id"])
            result = runner.step()
            if result.get("needs"):
                request_ids = [row["id"] for row in self.workflow.db.execute(
                    "SELECT id FROM requests WHERE task=? AND approved=1 AND consumed=0 AND resume_revision=?",
                    (task["id"], self.workflow.task(task["id"], task["assignee"])["revision"]))]
                needs.append({"task": task["id"], "kind": result["needs"], "request_ids": request_ids})
                continue
            return self.status() | {"state": "running", "advanced_task": task["id"]}
        return self.status() | {"state": "blocked", "needs": needs}

    def step(self):
        """Advance one ready task turn; a durable claim excludes other controllers."""
        with self.workflow._transaction():
            row = self.workflow.db.execute("SELECT owner FROM scheduler_runs WHERE root=?", (self.root,)).fetchone()
            if row["owner"] is not None:
                return self.status() | {"state": "blocked", "needs": [{"kind": "controller_reconciliation_or_busy"}]}
            self.workflow.db.execute("UPDATE scheduler_runs SET owner=? WHERE root=?", (self.owner, self.root))
        try:
            return self._advance()
        finally:
            with self.workflow._transaction():
                self.workflow.db.execute("UPDATE scheduler_runs SET owner=NULL WHERE root=? AND owner=?", (self.root, self.owner))
            if self.capture_memory:
                for task in budget.descendants(self.workflow, self.root):
                    if task["state"] in {"succeeded", "failed", "cancelled"}:
                        self.memory.observe_terminal(task["id"], task["assignee"])

    def recover_controller(self):
        """Trusted operator only, after confirming the previous worker stopped.

        This clears only the controller claim. Interrupted runner/tool effects
        still require their own inspection; no provider/tool call is replayed.
        """
        with self.workflow._transaction():
            self.workflow.db.execute("UPDATE scheduler_runs SET owner=NULL WHERE root=?", (self.root,))
            actor = self.workflow._row("tasks", self.root)["assignee"]
            self.workflow._event(self.root, actor, "scheduler_claim_reconciled")

    def run(self):
        while True:
            result = self.step()
            if result["state"] != "running":
                return result
