"""Persisted task-tree budgets, enforced at existing reservation boundaries.

Helpers called by the workflow/gateway/runner run inside their caller's SQLite
transaction. A delegated task cannot reset the root's counters or deadline.
"""

from dataclasses import asdict, dataclass
import json
import math

from .core import WorkflowError


class TreeBudgetError(WorkflowError):
    """The shared execution budget cannot release further work."""


@dataclass(frozen=True)
class TreeLimits:
    tasks: int = 16
    depth: int = 4
    model_attempts: int = 48
    reported_tokens: int = 128000
    tool_calls: int = 128
    duration_seconds: float = 900

    def __post_init__(self):
        for key in ("tasks", "depth", "model_attempts", "reported_tokens", "tool_calls"):
            if type(getattr(self, key)) is not int or getattr(self, key) < 1:
                raise TreeBudgetError("Tree count limits must be positive integers")
        if (type(self.duration_seconds) not in (int, float)
                or not math.isfinite(self.duration_seconds) or self.duration_seconds <= 0):
            raise TreeBudgetError("Tree duration must be positive and finite")


def descendants(workflow, root):
    return workflow.db.execute("""
        WITH RECURSIVE tree(id,depth) AS (
            SELECT ?,0 UNION ALL SELECT t.id,tree.depth+1 FROM tasks t JOIN tree ON t.parent=tree.id
        ) SELECT t.*,tree.depth FROM tasks t JOIN tree ON tree.id=t.id ORDER BY tree.depth DESC,t.rowid
    """, (root,)).fetchall()


def _scope(workflow, task):
    if not workflow.db.execute("SELECT 1 FROM sqlite_master WHERE name='tree_budgets' AND type='table'").fetchone():
        return None
    return workflow.db.execute("""
        WITH RECURSIVE ancestors(id,parent,depth) AS (
            SELECT id,parent,0 FROM tasks WHERE id=?
            UNION ALL SELECT t.id,t.parent,a.depth+1 FROM tasks t JOIN ancestors a ON t.id=a.parent
        ) SELECT b.*,a.depth,t.created FROM ancestors a JOIN tree_budgets b ON b.root=a.id
          JOIN tasks t ON t.id=b.root
    """, (task,)).fetchone()


def check(workflow, task, *, reserve=None, after_response=False):
    scope = _scope(workflow, task)
    if scope is None:
        return
    limits = json.loads(scope["limits"])
    if workflow.clock() - scope["created"] >= limits["duration_seconds"]:
        raise TreeBudgetError("Shared task-tree duration budget exhausted; partial artifacts retained")
    if scope["tokens"] > limits["reported_tokens"] or (not after_response and scope["tokens"] == limits["reported_tokens"]):
        raise TreeBudgetError("Shared task-tree reported token budget exhausted; partial artifacts retained")
    if reserve in {"attempts", "tool_calls"}:
        maximum = limits["model_attempts" if reserve == "attempts" else "tool_calls"]
        if scope[reserve] >= maximum:
            raise TreeBudgetError("Shared task-tree " + reserve + " budget exhausted; partial artifacts retained")
        policy = _policy(workflow, scope)
        if reserve == "attempts" and policy is not None and scope["depth"] > 0 and (
                maximum - scope[reserve] <= policy.parent_reserve * scope["depth"]):
            raise TreeBudgetError("Remaining shared requests are kept for the parent task's finish; "
                                  "this subtask stops and its artifacts are retained")
        workflow.db.execute(f"UPDATE tree_budgets SET {reserve}={reserve}+1 WHERE root=?", (scope["root"],))
    elif reserve == "child":
        if scope["depth"] >= limits["depth"] or len(descendants(workflow, scope["root"])) >= limits["tasks"]:
            raise TreeBudgetError("Shared task-tree task count or delegation depth limit reached")
    elif reserve is not None:
        raise TreeBudgetError("Unknown shared budget reservation")


@dataclass(frozen=True)
class FinishPolicy:
    """Hierarchical completion budget for open workflows (proposed 2026-11-19).

    parent_reserve: requests each ancestor keeps for its own finish while a
        descendant runs (accept results, report, submit, one retry).
    submit_reserve: requests any task keeps for its own submission; inside
        it the task is in Finish Mode (finishing tools only).
    min_child: requests a new subtask needs beyond the caller's own reserve.
    ready_fraction: once deliverables look ready, Finish Mode starts when the
        task's available requests fall to this share of the tree cap.
    Live software roots: accepted children used 10-25 requests; leads needed
    2-5 requests after their last child. Nothing is completed automatically.
    """
    parent_reserve: int = 3
    submit_reserve: int = 2
    min_child: int = 10
    ready_fraction: float = 0.25

    def __post_init__(self):
        if (any(type(getattr(self, key)) is not int for key in ("parent_reserve", "submit_reserve", "min_child"))
                or not 1 <= self.submit_reserve <= self.parent_reserve <= 16 or not 1 <= self.min_child <= 64
                or type(self.ready_fraction) not in (int, float) or not 0 <= self.ready_fraction <= 0.5
                or self.min_child <= self.submit_reserve):
            raise TreeBudgetError("Use small positive finish-policy settings: 1 <= submit_reserve <= parent_reserve, "
                                  "submit_reserve < min_child, 0 <= ready_fraction <= 0.5")


def configure_finish_policy(workflow, root, policy):
    if not isinstance(policy, FinishPolicy):
        raise TreeBudgetError("Use an explicit finish policy")
    workflow.db.execute("""CREATE TABLE IF NOT EXISTS finish_policies (
        root TEXT PRIMARY KEY REFERENCES tasks(id), policy TEXT NOT NULL
    )""")
    config = json.dumps(asdict(policy), sort_keys=True, allow_nan=False)
    with workflow._transaction():
        workflow._row("tasks", root)
        row = workflow.db.execute("SELECT policy FROM finish_policies WHERE root=?", (root,)).fetchone()
        if row is None:
            workflow.db.execute("INSERT INTO finish_policies VALUES(?,?)", (root, config))
        elif row["policy"] != config:
            raise TreeBudgetError("Finish policy must match the original root configuration")


def _policy(workflow, scope):
    if scope is None or not workflow.db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='finish_policies' AND type='table'").fetchone():
        return None
    row = workflow.db.execute("SELECT policy FROM finish_policies WHERE root=?", (scope["root"],)).fetchone()
    return FinishPolicy(**json.loads(row["policy"])) if row else None


def finish_budget(workflow, task):
    """Shared requests `task` may still use after what its ancestors keep, or None when unconfigured."""
    scope = _scope(workflow, task)
    policy = _policy(workflow, scope)
    if policy is None:
        return None
    cap = json.loads(scope["limits"])["model_attempts"]
    shared_left = max(0, cap - scope["attempts"])
    held = policy.parent_reserve * scope["depth"]
    delegated = workflow.db.execute("SELECT 1 FROM tasks WHERE parent=? LIMIT 1", (task,)).fetchone() is not None
    return {"policy": policy, "depth": scope["depth"], "cap": cap, "shared_left": shared_left,
            "reserved_for_ancestors": held, "available": max(0, shared_left - held),
            "own_reserve": policy.parent_reserve if delegated else policy.submit_reserve}


def record_tokens(workflow, task, count):
    # Always retain late/aborted usage. Reservation already counted the attempt;
    # missing responses remain unknown usage rather than a fabricated zero.
    scope = _scope(workflow, task)
    if scope is not None:
        workflow.db.execute("UPDATE tree_budgets SET tokens=tokens+? WHERE root=?", (count, scope["root"]))


def preflight_tools(workflow, task, count):
    check(workflow, task)
    scope = _scope(workflow, task)
    if scope is not None and scope["tool_calls"] + count > json.loads(scope["limits"])["tool_calls"]:
        raise TreeBudgetError("Shared task-tree tool_calls budget cannot accommodate this batch")


def configure(workflow, root, limits):
    if not isinstance(limits, TreeLimits):
        raise TreeBudgetError("Use explicit task-tree limits")
    workflow.db.execute("""CREATE TABLE IF NOT EXISTS tree_budgets (
        root TEXT PRIMARY KEY REFERENCES tasks(id), limits TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0, tokens INTEGER NOT NULL DEFAULT 0,
        tool_calls INTEGER NOT NULL DEFAULT 0
    )""")
    config = json.dumps(asdict(limits), sort_keys=True, allow_nan=False)
    with workflow._transaction():
        row = workflow._row("tasks", root)
        previous = workflow.db.execute("SELECT * FROM tree_budgets WHERE root=?", (root,)).fetchone()
        if row["parent"] or (previous and previous["limits"] != config):
            raise TreeBudgetError("Shared limits must match the original root configuration")
        if previous is None:
            if row["state"] not in {"pending", "running"} or len(descendants(workflow, root)) != 1:
                raise TreeBudgetError("Attach shared budgets before delegated work begins")
            for table in ("runner_sessions", "tool_calls"):
                if (workflow.db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone()
                        and workflow.db.execute(f"SELECT 1 FROM {table} WHERE task=?", (root,)).fetchone()):
                    raise TreeBudgetError("Cannot retrofit budgets after model/tool execution began")
            workflow.db.execute("INSERT INTO tree_budgets(root,limits) VALUES(?,?)", (root, config))


def status(workflow, root):
    scope = _scope(workflow, root)
    return {key: scope[key] for key in ("attempts", "tokens", "tool_calls")} | {
        "limits": json.loads(scope["limits"]), "tasks": len(descendants(workflow, root))}
