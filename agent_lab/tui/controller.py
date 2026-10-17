"""UI-independent control-center service. Imports no Textual code.

Every backend object (SQLite connection, file broker descriptors, scheduler)
is created and used on one dedicated backend thread, so SQLite thread ownership
stays correct and UI workers never block the Textual event loop. Methods return
plain JSON-compatible data; workflow, scheduler, and approval rules are enforced
by the existing backend APIs rather than reimplemented here.
"""

from concurrent.futures import Future
from dataclasses import dataclass, field
import json
from pathlib import Path
import queue
import threading
import time

from ..core import Workflow, WorkflowError
from ..deepseek import DeepSeekClient, DeepSeekHTTP
from ..files import FileTools
from ..inspection import ArtifactInspector
from ..memory import ExperienceMemory
from ..queries import TERMINAL, WorkflowQueries, redact, require_human
from ..scheduler import MultiAgentScheduler, Role
from .. import offline_scenarios

MEMORY_NAMESPACE = "tui-development"


class ControllerError(WorkflowError):
    """A control-center request that cannot be performed as asked."""


@dataclass(frozen=True)
class LiveConfig:
    """Explicit live-provider settings. Only DeepSeek is supported today.

    HKGAI needs its issued interface details. There is no environment-key
    discovery and no fallback: absent configuration means offline mode.
    """
    model: str
    api_key: str = field(repr=False)
    provider: str = "deepseek"
    max_output_tokens: int = 2048

    def __post_init__(self):
        if self.provider != "deepseek":
            raise ControllerError("Only the DeepSeek adapter is implemented; HKGAI awaits its official interface")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ControllerError("Live mode needs an explicit course-approved model identifier")


_LIVE_ROLES = {
    "coordinator": ("Decompose the goal, delegate to eligible specialists, accept their offered artifacts, and deliver the result.",
                    ("delegate_task", "accept_artifact", "post_message", "ask_human", "read_text", "create_text")),
    "writer": ("Draft Markdown or plain-text deliverables and offer them to your parent task.",
               ("create_text", "read_text", "update_text", "offer_artifact", "accept_artifact", "ask_human", "post_message")),
    "editor": ("Review and revise text deliverables; offer the revised snapshot to your parent task.",
               ("create_text", "read_text", "update_text", "offer_artifact", "accept_artifact", "ask_human")),
    "researcher": ("Collect information from supplied files only; internet search is not configured.",
                   ("create_text", "read_text", "offer_artifact", "ask_human")),
}


def live_roles(members):
    """Roles for agents present in a conversation; delegation stays inside it."""
    present = [agent for agent in _LIVE_ROLES if agent in members]
    roles = {}
    for agent in present:
        instructions, tools = _LIVE_ROLES[agent]
        delegates = tuple(a for a in present if a != agent) if "delegate_task" in tools else ()
        if "delegate_task" in tools and not delegates:
            tools = tuple(t for t in tools if t != "delegate_task")
        roles[agent] = Role(instructions, tools, delegates)
    return roles


class _Backend:
    """Owned by the backend thread only."""

    def __init__(self, state_dir, human, live, clock):
        self.state_dir, self.human, self.live = state_dir, human, live
        self.workflow = Workflow(state_dir / "workflow.sqlite3", **({"clock": clock} if clock else {}))
        self.files = None
        try:
            self.workflow.register_actor(human, "human")
            for agent in offline_scenarios.AGENTS:
                self.workflow.register_actor(agent, "agent")
            self.files = FileTools(self.workflow, state_dir / "files")
            self.memory = ExperienceMemory(self.workflow, namespace=MEMORY_NAMESPACE)
            self.queries = WorkflowQueries(self.workflow)
            self.inspector = ArtifactInspector(self.workflow, self.files)
            self.workflow.db.executescript("""
                CREATE TABLE IF NOT EXISTS tui_runs (
                    root TEXT PRIMARY KEY REFERENCES tasks(id), scenario TEXT NOT NULL, created REAL NOT NULL
                );
            """)
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.files is not None:
            self.files.close()
            self.files = None
        self.workflow.close()

    def run_kind(self, root):
        row = self.workflow.db.execute("SELECT scenario FROM tui_runs WHERE root=?", (root,)).fetchone()
        return row["scenario"] if row else None

    def scheduler(self, root):
        kind = self.run_kind(root)
        if kind is None:
            return None
        if kind == "live":
            if self.live is None:
                raise ControllerError("This is a live-model run; reopen the control center in configured live mode to continue it")
            chat = self.workflow.task(root, self.human)["chat"]
            members = {m["id"] for c in self.queries.conversations(self.human) if c["id"] == chat for m in c["members"]}
            roles = live_roles(members)
            transport = DeepSeekHTTP(self.live.api_key, allow_network=True)
            return MultiAgentScheduler(
                self.workflow, self.files, root, human=self.human, roles=roles,
                clients={a: DeepSeekClient(self.live.model, transport, max_tokens=self.live.max_output_tokens) for a in roles},
                mode="live", constraints=[], acceptance_id="tui-live-human-review-v1",
                # No automatic acceptance rule: proposals await the human reviewer.
                verifier_factory=lambda task: None, memory=None)
        return offline_scenarios.scheduler_for(self.workflow, self.files, root, kind, human=self.human, memory=self.memory)

    def root_of(self, task):
        row = self.workflow.task(task, self.human)
        while row["parent"]:
            row = self.workflow.task(row["parent"], self.human)
        return row["id"]


class ControlCenter:
    def __init__(self, state_dir, *, human="operator", live=None, clock=None):
        if live is not None and not isinstance(live, LiveConfig):
            raise ControllerError("Live mode requires an explicit LiveConfig")
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.human, self.live = human, live
        self.mode = "live" if live else "offline"
        self.activity, self._activity_seq = [], 0
        self._queue = queue.Queue()
        self._clock = clock
        self._factory_error = None
        self._thread = threading.Thread(target=self._loop, name="agent-lab-backend", daemon=True)
        self._thread.start()
        # Fail fast on an unusable session instead of on the first UI action.
        self.call(lambda backend: None)

    # ---- backend thread -------------------------------------------------
    def _loop(self):
        backend = None
        while True:
            item = self._queue.get()
            if item is None:
                break
            function, future = item
            if not future.set_running_or_notify_cancel():
                continue
            try:
                if backend is None:
                    backend = _Backend(self.state_dir, self.human, self.live, self._clock)
                future.set_result(function(backend))
            except BaseException as error:  # Delivered to the caller's thread.
                future.set_exception(error)
        if backend is not None:
            backend.close()

    def submit(self, function):
        if not self._thread.is_alive():
            raise ControllerError("Control-center backend has shut down")
        future = Future()
        self._queue.put((function, future))
        return future

    def call(self, function, timeout=None):
        return self.submit(function).result(timeout)

    def close(self, timeout=10):
        if self._thread.is_alive():
            self._queue.put(None)
            self._thread.join(timeout)

    def _log(self, message, *, level="info"):
        self._activity_seq += 1
        self.activity.append({"seq": self._activity_seq, "timestamp": time.time(), "level": level, "message": message})
        del self.activity[:-500]

    def _action(self, description, function):
        try:
            result = self.call(function)
        except WorkflowError as error:
            self._log(f"{description} rejected: {error}", level="error")
            raise
        self._log(description)
        return result

    # ---- read-only views ------------------------------------------------
    def status(self):
        def collect(b):
            tasks = b.queries.tasks(b.human)
            states = {}
            for task in tasks:
                states[task["state"]] = states.get(task["state"], 0) + 1
            return {"mode": self.mode, "session": str(self.state_dir), "human": b.human,
                    "provider": (f"{self.live.provider}:{self.live.model}" if self.live else "not configured"),
                    "runtimes": self.runtimes(),
                    "conversations": len(b.queries.conversations(b.human)), "tasks": len(tasks),
                    "task_states": states,
                    "pending_requests": len(b.queries.requests(b.human, pending_only=True)),
                    "awaiting_release": sum(r["status"] == "granted_awaiting_release" for r in b.queries.requests(b.human)),
                    "uncertain": len(b.queries.uncertain(b.human))}
        return self.call(collect)

    def runtimes(self):
        return {"model": "live (DeepSeek)" if self.live else "offline fixtures only",
                "sandbox": "not configured", "search": "disabled", "git": "not configured"}

    def actors(self):
        return self.call(lambda b: b.queries.actors())

    def conversations(self):
        return self.call(lambda b: b.queries.conversations(b.human))

    def feed(self, chat):
        return self.call(lambda b: b.queries.conversation_feed(chat, b.human))

    def tasks(self, chat=None):
        def collect(b):
            records = b.queries.tasks(b.human, chat=chat)
            runs = dict(b.workflow.db.execute("SELECT root,scenario FROM tui_runs").fetchall())
            for record in records:
                record["run"] = runs.get(record["id"])
            return records
        return self.call(collect)

    def task_tree(self, chat=None):
        return self.call(lambda b: b.queries.task_tree(b.human, chat=chat))

    def task_detail(self, task):
        def collect(b):
            detail = b.queries.task_detail(task, b.human)
            detail["run"] = b.run_kind(b.root_of(task))
            return detail
        return self.call(collect)

    def requests(self, *, pending_only=False):
        return self.call(lambda b: b.queries.requests(b.human, pending_only=pending_only))

    def request_detail(self, request):
        return self.call(lambda b: b.queries.request_detail(request, b.human))

    def uncertain(self):
        return self.call(lambda b: b.queries.uncertain(b.human))

    def metrics(self):
        return self.call(lambda b: b.queries.metrics(b.human))

    def recent_events(self, limit=200):
        def collect(b):
            chats = [c["id"] for c in b.queries.conversations(b.human)]
            if not chats:
                return []
            marks = ",".join("?" * len(chats))
            rows = b.workflow.db.execute(
                f"SELECT e.sequence,e.task,e.actor,e.kind,e.detail,e.timestamp FROM events e JOIN tasks t ON t.id=e.task "
                f"WHERE t.chat IN ({marks}) ORDER BY e.sequence DESC LIMIT ?", (*chats, limit)).fetchall()
            return [dict(r) | {"detail": redact(json.loads(r["detail"]))} for r in reversed(rows)]
        return self.call(collect)

    def files(self, task):
        return self.call(lambda b: b.inspector.list_files(task, b.human))

    def read_file(self, task, path):
        return self.call(lambda b: b.inspector.read_file(task, b.human, path))

    def file_history(self, task):
        return self.call(lambda b: b.inspector.history(task, b.human))

    def transfers(self, task=None):
        return self.call(lambda b: b.inspector.transfers(b.human, task=task))

    def compare_transfer(self, artifact_id):
        return self.call(lambda b: b.inspector.compare_transfer(artifact_id, b.human))

    def memory(self, *, chat=None, owner=None, namespace=None):
        def collect(b):
            require_human(b.queries, b.human)
            return b.queries.memory(b.human, chat=chat, owner=owner, namespace=namespace)
        return self.call(collect)

    def namespaces(self):
        return self.call(lambda b: b.queries.namespaces(b.human))

    def scenarios(self):
        return [{"name": s.name, "title": s.title, "description": s.description,
                 "scripted": list(s.scripted), "real": list(s.real)} for s in offline_scenarios.SCENARIOS.values()]

    # ---- actions through existing trusted APIs ---------------------------
    def create_conversation(self, kind, participants):
        participants = list(dict.fromkeys(participants))
        if self.human not in participants:
            participants.insert(0, self.human)
        return self._action(f"Created {kind} conversation with {', '.join(participants)}",
                            lambda b: b.workflow.create_chat(kind, participants))

    def post_message(self, chat, body):
        return self._action(f"Posted message to {chat[:8]}", lambda b: b.workflow.post_message(chat, b.human, body))

    def create_task(self, chat, assignee, title):
        """Create a real task. Posting a message never creates or runs a task."""
        def create(b):
            task = b.workflow.create_task(chat, b.human, assignee, title)
            if self.live is None:
                return {"task": task, "execution": "not_started",
                        "explanation": "Offline mode has no model; the task stays pending. Run a scripted scenario to exercise execution."}
            members = {m["id"] for c in b.queries.conversations(b.human) if c["id"] == chat for m in c["members"]}
            if assignee not in live_roles(members):
                return {"task": task, "execution": "not_started",
                        "explanation": "Assignee has no configured live role; the task stays pending."}
            with b.workflow._transaction():
                b.workflow.db.execute("INSERT INTO tui_runs VALUES(?,?,?)", (task, "live", b.workflow.clock()))
            b.scheduler(task)  # Persist the scheduler configuration before any execution.
            return {"task": task, "execution": "scheduled", "explanation": "Live scheduler attached; use Advance to run it."}
        return self._action(f"Created task for {assignee}: {title[:60]}", create)

    def answer(self, request, text):
        return self._action(f"Answered clarification {request[:8]}",
                            lambda b: b.workflow.respond(request, b.human, answer=text))

    def decide(self, request, approve):
        verb = "Approved" if approve else "Rejected"
        return self._action(f"{verb} request {request[:8]} (approval only; no action released)",
                            lambda b: b.workflow.respond(request, b.human, approve=approve))

    def release(self, request):
        """Release one granted exact action through the trusted gateway path."""
        def run(b):
            row = b.queries.request_detail(request, b.human)
            if row["status"] != "granted_awaiting_release":
                raise ControllerError(f"Request is {row['status']}; only a current granted approval can be released")
            scheduler = b.scheduler(b.root_of(row["task"]))
            if scheduler is None:
                raise ControllerError("No trusted executor is configured for this task's actions")
            return scheduler.runner(row["task"]).gateway.release_approved(request)
        return self._action(f"Released approved action {request[:8]}", run)

    def advance(self, task):
        """Run the task's scheduler until it pauses, blocks, or terminates."""
        def run(b):
            root = b.root_of(task)
            scheduler = b.scheduler(root)
            if scheduler is None:
                raise ControllerError("This task has no scheduler; offline mode cannot execute arbitrary tasks")
            return scheduler.run()
        return self._action(f"Advanced scheduler for {task[:8]}", run)

    def review(self, task, *, accept, feedback):
        """Trusted human review of a proposal awaiting independent verification."""
        def run(b):
            scheduler = b.scheduler(b.root_of(task))
            if scheduler is None:
                raise ControllerError("No scheduler owns this task")
            runner = scheduler.runner(task)
            if runner.status()["runner_state"] != "awaiting_verification":
                raise ControllerError("No proposal from this task is awaiting review")
            if accept:
                assignee = b.workflow.task(task, b.human)["assignee"]
                b.workflow.finish_task(task, assignee, checks={"human_review_accepted": True})
            else:
                runner.review_failed(feedback)
        return self._action(f"{'Accepted' if accept else 'Rejected'} proposal for {task[:8]}", run)

    def recover_claim(self, task):
        def run(b):
            scheduler = b.scheduler(b.root_of(task))
            if scheduler is None:
                raise ControllerError("No scheduler owns this task")
            scheduler.recover_controller()
        return self._action(f"Cleared scheduler claim for {task[:8]} (no replay)", run)

    def run_scenario(self, name):
        if name not in offline_scenarios.SCENARIOS:
            raise ControllerError("Unknown scenario")

        def run(b):
            root, summary = offline_scenarios.start(name, b.workflow, b.files, b.memory, human=b.human)
            result = {"scenario": name, "summary": summary, "mode": "offline_fixture",
                      "model_calls": 0, "benchmark_valid": False}
            if root is not None:
                with b.workflow._transaction():
                    b.workflow.db.execute("INSERT INTO tui_runs VALUES(?,?,?)", (root, name, b.workflow.clock()))
                result["root"] = root
                result["scheduler"] = b.scheduler(root).run()
            return result
        return self._action(f"Ran offline scenario '{name}' (scripted provider responses)", run)

    def terminal(self, state):
        return state in TERMINAL
