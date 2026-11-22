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


def provider_pause_seconds(workflow, tasks, now):
    """Seconds the given tasks sat paused for an operator decision after a provider failure.

    A pause starts at a provider_decision_required event and ends at the next
    provider_resend_released event for that task, the task's end, or now.
    Overlapping pauses in one tree count once. Deadlines exclude this time: the
    task could not act, and nothing was retried without the operator.
    """
    intervals = []
    for task in tasks:
        row = workflow.db.execute("SELECT ended FROM tasks WHERE id=?", (task,)).fetchone()
        ended = row["ended"] if row and row["ended"] is not None else now
        # Proposed 2026-11-22: gaps in which no controller ran and nothing awaited a human are excluded too.
        for row in workflow.db.execute("SELECT detail FROM events WHERE task=? AND kind='controller_idle'", (task,)):
            detail = json.loads(row["detail"])
            intervals.append((detail["from"], min(detail["to"], ended)))
        events = workflow.db.execute(
            "SELECT kind,timestamp FROM events WHERE task=? AND kind IN "
            "('provider_decision_required','provider_resend_released') ORDER BY sequence", (task,)).fetchall()
        start = None
        for event in events:
            if event["kind"] == "provider_decision_required" and start is None:
                start = event["timestamp"]
            elif event["kind"] == "provider_resend_released" and start is not None:
                intervals.append((start, event["timestamp"]))
                start = None
        if start is not None:
            intervals.append((start, max(start, min(ended, now))))
    total, covered = 0.0, None
    for start, end in sorted(intervals):
        if covered is not None:
            start = max(start, covered)
        if end > start:
            total += end - start
        covered = end if covered is None else max(covered, end)
    return total


def tree_elapsed(workflow, scope, now):
    """Elapsed seconds against the tree deadline, without operator-decision pauses."""
    tasks = [row["id"] for row in descendants(workflow, scope["root"])]
    return now - scope["created"] - provider_pause_seconds(workflow, tasks, now)


def task_elapsed(workflow, task, now):
    """Elapsed seconds against one task's deadline, without its operator-decision pauses."""
    row = workflow.db.execute("SELECT created FROM tasks WHERE id=?", (task,)).fetchone()
    return now - row["created"] - provider_pause_seconds(workflow, [task], now)


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
    if tree_elapsed(workflow, scope, workflow.clock()) >= limits["duration_seconds"]:
        raise TreeBudgetError("Shared task-tree duration budget exhausted; partial artifacts retained")
    if scope["tokens"] > limits["reported_tokens"] or (not after_response and scope["tokens"] == limits["reported_tokens"]):
        raise TreeBudgetError("Shared task-tree reported token budget exhausted; partial artifacts retained")
    if reserve in {"attempts", "tool_calls"}:
        maximum = limits["model_attempts" if reserve == "attempts" else "tool_calls"]
        # A failed or uncertain HTTP attempt can still be charged. Finish-policy
        # credits must never relax the owner's actual-request ceiling.
        used = scope[reserve]
        if used >= maximum:
            raise TreeBudgetError("Shared task-tree " + reserve + " budget exhausted; partial artifacts retained")
        policy = _policy(workflow, scope)
        if reserve == "attempts" and policy is not None and (
                maximum - used <= held_for_others(workflow, scope["root"], task, policy.finish_requests)):
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
    """Hierarchical completion budget for open workflows (completion-protocol-v2, proposed 2026-11-21).

    finish_requests (R): every open task in a tree is guaranteed its last R requests.
        While a task runs, each other open task (ancestors, siblings and their
        subtasks) holds what is left of its R, so nobody else can spend them. A task's finish window is
        its last R available requests, in which only completion actions are offered.
    min_child: work requests a new subtask needs beyond its own finish window.
    Live roots (2026-11-19..21): accepted children used 10-25 requests; leads needed
    2-5 after their last child. Nothing is completed automatically.
    """
    finish_requests: int = 3
    min_child: int = 10

    def __post_init__(self):
        if (any(type(getattr(self, key)) is not int for key in ("finish_requests", "min_child"))
                or not 1 <= self.finish_requests <= 16 or not self.finish_requests < self.min_child <= 64):
            raise TreeBudgetError("Use small positive finish-policy settings: 1 <= finish_requests <= 16 and "
                                  "finish_requests < min_child <= 64")

    @classmethod
    def from_record(cls, data):
        """Read a stored policy; v1 records (parent_reserve/submit_reserve/ready_fraction) map R to parent_reserve."""
        if "finish_requests" in data:
            return cls(**data)
        return cls(finish_requests=data["parent_reserve"], min_child=data["min_child"])


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
    return FinishPolicy.from_record(json.loads(row["policy"])) if row else None


TERMINAL = frozenset({"succeeded", "failed", "cancelled"})


def _open_others(workflow, root, task):
    """Open tasks in the tree other than `task`; each holds what is left of its own finish window."""
    return [row["id"] for row in descendants(workflow, root) if row["id"] != task and row["state"] not in TERMINAL]


def window_used(workflow, task):
    """Requests a task has already spent inside its finish window (0 before it is entered)."""
    entered = workflow.db.execute("SELECT min(sequence) FROM events WHERE task=? AND kind='finish_mode_entered'",
                                  (task,)).fetchone()[0]
    if entered is None:
        return 0
    return workflow.db.execute("SELECT count(*) FROM events WHERE task=? AND kind='model_attempt_reserved' AND "
                               "sequence>?", (task, entered)).fetchone()[0]


def held_for_others(workflow, root, task, window):
    """Requests `task` must leave: each other open task's unspent finish window.

    A fixed R per other task would count a window twice once its owner has spent
    it: a blocked sibling (awaiting review) could then be left with nothing.
    """
    return sum(max(0, window - window_used(workflow, other)) for other in _open_others(workflow, root, task))


def finish_budget(workflow, task):
    """Shared requests `task` may still use after every other open task's finish window, or None when unconfigured."""
    scope = _scope(workflow, task)
    policy = _policy(workflow, scope)
    if policy is None:
        return None
    cap = json.loads(scope["limits"])["model_attempts"]
    shared_left = max(0, cap - scope["attempts"])
    others = _open_others(workflow, scope["root"], task)
    held = held_for_others(workflow, scope["root"], task, policy.finish_requests)
    task_calls = workflow.db.execute("SELECT maximum FROM tool_budgets WHERE task=?", (task,)).fetchone() if \
        workflow.db.execute("SELECT 1 FROM sqlite_master WHERE name='tool_budgets'").fetchone() else None
    used_calls = workflow.db.execute("SELECT count(*) FROM tool_calls WHERE task=?", (task,)).fetchone()[0] if \
        task_calls else 0
    tool_left = json.loads(scope["limits"])["tool_calls"] - scope["tool_calls"] - held
    if task_calls:
        tool_left = min(tool_left, task_calls["maximum"] - used_calls)
    return {"policy": policy, "depth": scope["depth"], "cap": cap, "shared_left": shared_left,
            "held_for_other_open_tasks": held, "open_other_tasks": len(others),
            "available": max(0, shared_left - held), "tool_calls_left": max(0, tool_left),
            "finish_requests": policy.finish_requests}


def record_tokens(workflow, task, count):
    # Always retain late/aborted usage. Reservation already counted the attempt;
    # missing responses remain unknown usage rather than a fabricated zero.
    scope = _scope(workflow, task)
    if scope is not None:
        workflow.db.execute("UPDATE tree_budgets SET tokens=tokens+? WHERE root=?", (count, scope["root"]))


def preflight_tools(workflow, task, count):
    check(workflow, task)
    scope = _scope(workflow, task)
    if scope is None:
        return
    limit = json.loads(scope["limits"])["tool_calls"]
    if scope["tool_calls"] + count > limit:
        raise TreeBudgetError("Shared task-tree tool_calls budget cannot accommodate this batch")
    policy = _policy(workflow, scope)
    held = held_for_others(workflow, scope["root"], task, policy.finish_requests) if policy else 0
    if held and scope["tool_calls"] + count > limit - held:
        # Each unspent finish-window request of another open task keeps one tool call for its completion.
        raise TreeBudgetError(f"Shared task-tree tool_calls budget cannot accommodate this batch: "
                              f"{max(0, limit - scope['tool_calls'] - held)} call(s) are free for this task and "
                              f"{held} are kept for other open tasks' finish windows; send fewer calls")


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
        "limits": json.loads(scope["limits"]), "tasks": len(descendants(workflow, root)),
        "refunded_attempts": refunded(workflow, scope["root"])}


# Read legacy credits for audit only. No new credits are issued and neither
# current nor historical credits alter a task/tree's real-request limit.
def _refunds_table(workflow):
    return workflow.db.execute("SELECT 1 FROM sqlite_master WHERE name='budget_refunds' AND type='table'").fetchone()


def refunded(workflow, root):
    if not _refunds_table(workflow):
        return 0
    return workflow.db.execute("SELECT count(*) FROM budget_refunds WHERE root=?", (root,)).fetchone()[0]
