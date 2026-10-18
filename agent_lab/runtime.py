"""Shared trusted setup for live tasks. No UI dependency or network on creation.

Offline scenarios keep their explicit scripted drivers. This module never
selects a fixture, substitutes a provider or enables an unavailable backend.
"""

from dataclasses import dataclass, field, replace
import hashlib
import json
import math
import os

from .budget import TreeLimits
from .core import WorkflowError
from .deepseek import DeepSeekClient, DeepSeekHTTP
from .files import _parts
from .protocol import strict_json
from .runner import Limits
from .scheduler import MultiAgentScheduler, Role


class RuntimeSetupError(WorkflowError):
    """Rejected trusted configuration or local application request."""


def normalize_constraints(value):
    if (not isinstance(value, (list, tuple)) or len(value) > 100
            or any(not isinstance(s, str) or not s.strip() or len(s) > 4096 for s in value)):
        raise RuntimeSetupError("Supply at most 100 nonempty constraints of at most 4096 characters each")
    return tuple(value)


@dataclass(frozen=True)
class LiveConfig:
    model: str
    api_key: str = field(repr=False)
    provider: str = "deepseek"
    max_output_tokens: int = 2048
    allow_network: bool = False
    socket_timeout: float = 30
    role_limits: Limits = Limits()
    tree_limits: TreeLimits = TreeLimits()
    tool_calls: int = 32
    constraints: tuple = ()

    def __post_init__(self):
        if self.provider != "deepseek":
            raise RuntimeSetupError("Only DeepSeek is implemented; HKGAI awaits its official interface; no provider fallback")
        if not isinstance(self.model, str) or not self.model.strip() or len(self.model) > 128:
            raise RuntimeSetupError("Supply an explicit course-approved model identifier")
        if not isinstance(self.api_key, str) or not self.api_key or any(c.isspace() for c in self.api_key):
            raise RuntimeSetupError("Supply a nonempty API key without whitespace")
        if type(self.max_output_tokens) is not int or not 1 <= self.max_output_tokens <= 16384:
            raise RuntimeSetupError("Output token limit must be an integer from 1 to 16384")
        if (type(self.allow_network) is not bool or type(self.socket_timeout) not in (int, float)
                or not 0 < self.socket_timeout <= 120 or not math.isfinite(self.socket_timeout)):
            raise RuntimeSetupError("Use explicit network authorization and a finite socket timeout up to 120 seconds")
        if (not isinstance(self.role_limits, Limits) or not isinstance(self.tree_limits, TreeLimits)
                or type(self.tool_calls) is not int or not 1 <= self.tool_calls <= 1000):
            raise RuntimeSetupError("Supply validated task/tree limits and a bounded per-task tool-call limit")
        object.__setattr__(self, "constraints", normalize_constraints(self.constraints))


@dataclass(frozen=True)
class TaskPolicy:
    """Trusted original constraints and optional root exact-text expectations.

    No expectation means human review; children also require trusted review.
    Subtask acceptance is a separate integration, never guessed from model text.
    """
    constraints: tuple = ()
    root_artifacts: tuple = ()

    def __post_init__(self):
        object.__setattr__(self, "constraints", normalize_constraints(self.constraints))
        items = self.root_artifacts
        if isinstance(items, dict):
            items = tuple(items.items())
        if (not isinstance(items, (list, tuple)) or len(items) > 100
                or any(not isinstance(p, (list, tuple)) or len(p) != 2
                       or not isinstance(p[0], str) or not isinstance(p[1], str) for p in items)):
            raise RuntimeSetupError("Root expectations must be distinct path/exact-text pairs")
        for path, text in items:
            _parts(path)
        if len({p for p, _ in items}) != len(items):
            raise RuntimeSetupError("Duplicate root artifact expectation")
        object.__setattr__(self, "root_artifacts", tuple(sorted((p, t) for p, t in items)))

    def record(self):
        return {"version": 1, "constraints": list(self.constraints), "root_artifacts": dict(self.root_artifacts)}

    @property
    def acceptance_id(self):
        digest = hashlib.sha256(_encode(self.record()).encode()).hexdigest()
        return "runtime-text-or-human-v1-" + digest


def _encode(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, ensure_ascii=True)


def policy_for_task(live=None, *, constraints=(), root_artifacts=()):
    if live is not None and not isinstance(live, LiveConfig):
        raise RuntimeSetupError("Use the shared LiveConfig")
    return TaskPolicy((*(() if live is None else live.constraints), *normalize_constraints(constraints)), root_artifacts)


def bind_task_policy(workflow, root, human, policy=None, *, default=None):
    """Record once; restore without replacing original task constraints on restart."""
    task = workflow.task(root, human)
    if task["parent"] or workflow._row("actors", human)["kind"] != "human":
        raise RuntimeSetupError("Only a human member can configure a root task policy")
    if any(p is not None and not isinstance(p, TaskPolicy) for p in (policy, default)):
        raise RuntimeSetupError("Use a trusted TaskPolicy")
    workflow.db.execute("""CREATE TABLE IF NOT EXISTS runtime_task_policies (
        root TEXT PRIMARY KEY REFERENCES tasks(id), policy TEXT NOT NULL
    )""")
    with workflow._transaction():
        row = workflow.db.execute("SELECT policy FROM runtime_task_policies WHERE root=?", (root,)).fetchone()
        if row:
            try:
                data = strict_json(row["policy"])
                if (set(data) != {"version", "constraints", "root_artifacts"}
                        or type(data["version"]) is not int or data["version"] != 1
                        or not isinstance(data["root_artifacts"], dict)):
                    raise ValueError()
                stored = TaskPolicy(data["constraints"], data["root_artifacts"])
            except (ValueError, TypeError, KeyError, WorkflowError):
                raise RuntimeSetupError("Persisted task policy is invalid; preserve state and reconcile") from None
            if policy is not None and stored != policy:
                raise RuntimeSetupError("Original constraints or acceptance expectations differ; task policy cannot be replaced")
            return stored
        policy = (default or TaskPolicy()) if policy is None else policy
        workflow.db.execute("INSERT INTO runtime_task_policies VALUES(?,?)", (root, _encode(policy.record())))
        return policy


_ROLE_SPECS = {
    "coordinator": ("Decompose the goal, delegate to eligible specialists, accept their offered artifacts, and deliver the result.",
                    ("delegate_task", "accept_artifact", "post_message", "ask_human", "read_text", "create_text")),
    "writer": ("Draft Markdown or plain-text deliverables and offer them to your parent task.",
               ("create_text", "read_text", "update_text", "offer_artifact", "accept_artifact", "ask_human", "post_message")),
    "editor": ("Review and revise text deliverables; offer the revised snapshot to your parent task.",
               ("create_text", "read_text", "update_text", "offer_artifact", "accept_artifact", "ask_human")),
    "researcher": ("Collect information from supplied files only; internet search is not configured.",
                   ("create_text", "read_text", "offer_artifact", "ask_human")),
}
LIVE_AGENTS = tuple(_ROLE_SPECS)


def live_roles(members, config=None):
    present = [a for a in LIVE_AGENTS if a in members]
    roles = {}
    for agent in present:
        instructions, tools = _ROLE_SPECS[agent]
        delegates = tuple(a for a in present if a != agent) if "delegate_task" in tools else ()
        if "delegate_task" in tools and not delegates:
            tools = tuple(t for t in tools if t != "delegate_task")
        roles[agent] = Role(instructions, tools, delegates,
                            Limits() if config is None else config.role_limits,
                            32 if config is None else config.tool_calls)
    return roles


def build_live_scheduler(workflow, files, root, *, human, live, policy=None):
    if not isinstance(live, LiveConfig):
        raise RuntimeSetupError("Live execution requires the shared explicit LiveConfig")
    task = workflow.task(root, human)
    members = [r[0] for r in workflow.db.execute("SELECT actor FROM members WHERE chat=?", (task["chat"],))]
    roles = live_roles(members, live)
    if task["assignee"] not in roles:
        raise RuntimeSetupError("Root assignee has no configured live role in this conversation")
    # Retain the known pre-A02 TUI human-review policy without reinterpreting it.
    previous = None
    if workflow.db.execute("SELECT 1 FROM sqlite_master WHERE name='scheduler_runs' AND type='table'").fetchone():
        row = workflow.db.execute("SELECT config FROM scheduler_runs WHERE root=?", (root,)).fetchone()
        previous = strict_json(row["config"]) if row else None
    legacy = previous is not None and previous["acceptance_id"] == "tui-live-human-review-v1"
    if legacy and (previous["constraints"] or (policy is not None and policy != TaskPolicy())):
        raise RuntimeSetupError("Legacy human-review task cannot acquire a different policy")
    if (not legacy and policy is not None and isinstance(policy, TaskPolicy)
            and policy.constraints[:len(live.constraints)] != live.constraints):
        # Direct API callers cannot accidentally omit the launcher's constraints.
        # UI/evaluation already supply this prefix; do not append it twice.
        policy = policy_for_task(live, constraints=policy.constraints, root_artifacts=policy.root_artifacts)
    policy = bind_task_policy(workflow, root, human, TaskPolicy() if legacy else policy,
                              default=TaskPolicy(live.constraints))
    acceptance_id = "tui-live-human-review-v1" if legacy else policy.acceptance_id

    def acceptance(candidate):
        if candidate["id"] == root and policy.root_artifacts:
            return files.text_verifier(root, candidate["assignee"], dict(policy.root_artifacts)), acceptance_id + ":root"
        return None

    transport = DeepSeekHTTP(live.api_key, allow_network=live.allow_network, timeout=live.socket_timeout)
    return MultiAgentScheduler(workflow, files, root, human=human, roles=roles,
        clients={a: DeepSeekClient(live.model, transport, max_tokens=live.max_output_tokens) for a in roles},
        mode="live", constraints=list(policy.constraints), acceptance_id=acceptance_id,
        verifier_factory=acceptance, limits=live.tree_limits, memory=None, executor=None, git=None)


def add_live_arguments(parser):
    parser.add_argument("--live", action="store_true", help="Explicitly enable DeepSeek network calls; requires model and key variable")
    parser.add_argument("--provider", default="deepseek", choices=("deepseek", "hkgai"))
    parser.add_argument("--model", help="Explicit course-approved model identifier")
    parser.add_argument("--api-key-env", help="Name of the environment variable holding the issued key")
    parser.add_argument("--constraint", action="append", default=[], help="Original task constraint (repeatable)")
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    parser.add_argument("--task-attempts", type=int, default=8)
    parser.add_argument("--tree-attempts", type=int, default=48)


def live_config_from_args(args):
    if not args.live:
        if (args.model or args.api_key_env or args.constraint or args.provider != "deepseek"
                or args.max_output_tokens != 2048 or args.task_attempts != 8 or args.tree_attempts != 48):
            raise RuntimeSetupError("Live configuration flags require --live; no implicit credential discovery")
        return None
    if not args.model or not args.api_key_env:
        raise RuntimeSetupError("--live requires --model and --api-key-env")
    key = os.environ.get(args.api_key_env)
    if not key:
        raise RuntimeSetupError("The explicitly named API-key environment variable is not set")
    return LiveConfig(model=args.model, api_key=key, provider=args.provider, allow_network=True,
        constraints=tuple(args.constraint), max_output_tokens=args.max_output_tokens,
        role_limits=replace(Limits(), model_attempts=args.task_attempts),
        tree_limits=replace(TreeLimits(), model_attempts=args.tree_attempts))
