"""Transactional task, chat, and human-response bookkeeping using SQLite.

This is a trusted local application API, not a network authentication service.
Actor identifiers must eventually come from an authenticated transport, never
from a model's unverified assertion. File-system/process isolation is separate.
"""

from contextlib import contextmanager
import hashlib
import json
import sqlite3
import time
from uuid import uuid4


class WorkflowError(ValueError):
    """An invalid or unauthorized workflow operation."""


def canonical_action(action):
    if not isinstance(action, dict) or not action:
        raise WorkflowError("An approval requires a nonempty structured action")
    try:
        encoded = json.dumps(action, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise WorkflowError("Action must contain JSON-compatible finite values") from exc
    return encoded, hashlib.sha256(encoded.encode()).hexdigest()


class Workflow:
    def __init__(self, database, *, clock=time.time):
        self.clock = clock
        self.db = sqlite3.connect(database, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA busy_timeout = 5000")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS actors (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('human','agent'))
            );
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('private','group'))
            );
            CREATE TABLE IF NOT EXISTS members (
                chat TEXT REFERENCES chats(id), actor TEXT REFERENCES actors(id),
                PRIMARY KEY(chat, actor)
            );
            CREATE TABLE IF NOT EXISTS messages (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                chat TEXT NOT NULL REFERENCES chats(id), sender TEXT NOT NULL REFERENCES actors(id),
                body TEXT NOT NULL, timestamp REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, chat TEXT NOT NULL REFERENCES chats(id),
                parent TEXT REFERENCES tasks(id), assignee TEXT NOT NULL REFERENCES actors(id),
                title TEXT NOT NULL, state TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL,
                ended REAL, wait_started REAL, wait_seconds REAL NOT NULL DEFAULT 0,
                evidence TEXT
            );
            CREATE TABLE IF NOT EXISTS requests (
                id TEXT PRIMARY KEY, task TEXT NOT NULL REFERENCES tasks(id),
                kind TEXT NOT NULL, responder TEXT NOT NULL REFERENCES actors(id),
                prompt TEXT NOT NULL, action TEXT, digest TEXT, response TEXT,
                approved INTEGER, answered INTEGER NOT NULL DEFAULT 0,
                resume_revision INTEGER, consumed INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT NOT NULL REFERENCES tasks(id), actor TEXT NOT NULL REFERENCES actors(id),
                kind TEXT NOT NULL, detail TEXT NOT NULL, timestamp REAL NOT NULL
            );
        """)

    def close(self):
        self.db.close()

    @contextmanager
    def _transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        else:
            self.db.execute("COMMIT")

    def _row(self, table, identifier):
        # Table names are internal constants, never externally supplied SQL.
        row = self.db.execute(f"SELECT * FROM {table} WHERE id = ?", (identifier,)).fetchone()
        if row is None:
            raise WorkflowError(f"Unknown {table} identifier")
        return row

    def _member(self, chat, actor):
        if not self.db.execute(
            "SELECT 1 FROM members WHERE chat = ? AND actor = ?", (chat, actor)
        ).fetchone():
            raise WorkflowError("Actor is not a member of this conversation")

    def _task(self, identifier, actor, *, assigned=False):
        row = self._row("tasks", identifier)
        self._member(row["chat"], actor)
        if assigned and row["assignee"] != actor:
            raise WorkflowError("Only the assigned agent may perform this operation")
        return row

    def _event(self, task, actor, kind, detail=None):
        self.db.execute(
            "INSERT INTO events(task,actor,kind,detail,timestamp) VALUES(?,?,?,?,?)",
            (task, actor, kind, json.dumps(detail or {}, sort_keys=True), self.clock()),
        )

    def _transition(self, row, state):
        now = self.clock()
        waited = row["wait_seconds"]
        if row["wait_started"] is not None:
            waited += max(0, now - row["wait_started"])
        terminal = state in {"succeeded", "failed", "cancelled"}
        self.db.execute(
            "UPDATE tasks SET state=?,revision=revision+1,ended=?,wait_started=?,wait_seconds=? WHERE id=?",
            (state, now if terminal else None,
             now if state in {"waiting_input", "waiting_approval"} else None, waited, row["id"]),
        )

    def register_actor(self, actor, kind):
        if not isinstance(actor, str) or not actor.strip() or kind not in {"human", "agent"}:
            raise WorkflowError("Provide an actor identifier and human/agent kind")
        with self._transaction():
            previous = self.db.execute("SELECT kind FROM actors WHERE id=?", (actor,)).fetchone()
            if previous and previous["kind"] != kind:
                raise WorkflowError("An actor's kind cannot be changed")
            self.db.execute("INSERT OR IGNORE INTO actors VALUES(?,?)", (actor, kind))

    def create_chat(self, kind, participants):
        people = set(participants)
        with self._transaction():
            kinds = [self._row("actors", p)["kind"] for p in people]
            if kind not in {"private", "group"} or not {"human", "agent"}.issubset(kinds):
                raise WorkflowError("A conversation requires a human and an agent")
            if kind == "private" and len(people) != 2:
                raise WorkflowError("A private conversation has exactly two participants")
            identifier = uuid4().hex
            self.db.execute("INSERT INTO chats VALUES(?,?)", (identifier, kind))
            self.db.executemany("INSERT INTO members VALUES(?,?)", [(identifier, p) for p in people])
        return identifier

    def post_message(self, chat, actor, body):
        if not isinstance(body, str) or not body.strip():
            raise WorkflowError("A message cannot be empty")
        with self._transaction():
            self._member(chat, actor)
            self.db.execute(
                "INSERT INTO messages(chat,sender,body,timestamp) VALUES(?,?,?,?)",
                (chat, actor, body, self.clock()),
            )

    def messages(self, chat, actor):
        self._member(chat, actor)
        return [dict(r) for r in self.db.execute(
            "SELECT sequence,sender,body,timestamp FROM messages WHERE chat=? ORDER BY sequence", (chat,)
        )]

    def create_task(self, chat, actor, assignee, title, *, parent=None):
        if not isinstance(title, str) or not title.strip():
            raise WorkflowError("A task needs a description")
        with self._transaction():
            self._member(chat, actor)
            self._member(chat, assignee)
            if self._row("actors", assignee)["kind"] != "agent":
                raise WorkflowError("Tasks must be assigned to an agent")
            if parent:
                source = self._task(parent, actor, assigned=True)
                if source["state"] != "running" or source["chat"] != chat:
                    raise WorkflowError("Delegate only from a running task in the same conversation")
            elif self._row("actors", actor)["kind"] != "human":
                raise WorkflowError("An agent needs a parent task to delegate work")
            identifier = uuid4().hex
            self.db.execute(
                "INSERT INTO tasks(id,chat,parent,assignee,title,state,created) VALUES(?,?,?,?,?,'pending',?)",
                (identifier, chat, parent, assignee, title, self.clock()),
            )
            self._event(identifier, actor, "delegated" if parent else "created", {"assignee": assignee})
        return identifier

    def task(self, identifier, actor):
        return dict(self._task(identifier, actor))

    def events(self, identifier, actor):
        self._task(identifier, actor)
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM events WHERE task=? ORDER BY sequence", (identifier,)
        )]

    def start_task(self, identifier, actor):
        with self._transaction():
            row = self._task(identifier, actor, assigned=True)
            if row["state"] != "pending":
                raise WorkflowError("Only a pending task can start")
            self._transition(row, "running")
            self._event(identifier, actor, "started")

    def ask_human(self, identifier, actor, human, prompt, *, action=None):
        if not isinstance(prompt, str) or not prompt.strip():
            raise WorkflowError("A human request needs a concrete question")
        encoded, digest = canonical_action(action) if action is not None else (None, None)
        kind = "approval" if action is not None else "clarification"
        with self._transaction():
            row = self._task(identifier, actor, assigned=True)
            self._member(row["chat"], human)
            if self._row("actors", human)["kind"] != "human" or row["state"] != "running":
                raise WorkflowError("A running task must address an actual human member")
            request = uuid4().hex
            self.db.execute(
                "INSERT INTO requests(id,task,kind,responder,prompt,action,digest) VALUES(?,?,?,?,?,?,?)",
                (request, identifier, kind, human, prompt, encoded, digest),
            )
            self._transition(row, "waiting_approval" if action is not None else "waiting_input")
            self._event(identifier, actor, "human_requested", {"request": request, "kind": kind})
        return request

    def request(self, identifier, actor):
        row = self._row("requests", identifier)
        self._task(row["task"], actor)
        return dict(row)

    def respond(self, identifier, actor, *, answer=None, approve=None):
        with self._transaction():
            request = self._row("requests", identifier)
            task = self._task(request["task"], actor)
            if request["responder"] != actor or request["answered"]:
                raise WorkflowError("Only the addressed human can answer, exactly once")
            if request["kind"] == "approval":
                if task["state"] != "waiting_approval" or type(approve) is not bool or answer is not None:
                    raise WorkflowError("Approval requires an explicit boolean decision")
                response = "approved" if approve else "denied"
            else:
                if (task["state"] != "waiting_input" or approve is not None
                        or not isinstance(answer, str) or not answer.strip()):
                    raise WorkflowError("Clarification requires a nonempty answer")
                response = answer
            self._transition(task, "cancelled" if approve is False else "running")
            self.db.execute(
                "UPDATE requests SET response=?,approved=?,answered=1,resume_revision=? WHERE id=?",
                (response, approve, task["revision"] + 1, identifier),
            )
            self._event(task["id"], actor, "human_responded", {"request": identifier, "response": response})
            if approve is False:
                self._cancel_descendants(task["id"], actor)

    def consume_approval(self, identifier, actor, action):
        """Release one exact action to a future executor; this does not execute it.

        Consumption occurs before an external effect. A crash in between needs
        reconciliation and a new approval, rather than automatic re-execution.
        """
        _, digest = canonical_action(action)
        with self._transaction():
            request = self._row("requests", identifier)
            task = self._task(request["task"], actor, assigned=True)
            if (request["kind"] != "approval" or request["approved"] != 1
                    or request["consumed"] or request["digest"] != digest
                    or task["state"] != "running"
                    or task["revision"] != request["resume_revision"]):
                raise WorkflowError("Approval is missing, stale, consumed, or for another action")
            self.db.execute("UPDATE requests SET consumed=1 WHERE id=?", (identifier,))
            self._event(task["id"], actor, "approval_consumed", {"request": identifier, "digest": digest})
        return json.loads(request["action"])

    def finish_task(self, identifier, actor, *, checks=None, error=None):
        """Record trusted-caller checks, not a model's self-reported success.

        A real artifact verifier is not implemented in this foundation.
        """
        success = error is None
        if success:
            if (not isinstance(checks, dict) or not checks
                    or any(not isinstance(k, str) or not k.strip() or v is not True
                           for k, v in checks.items())):
                raise WorkflowError("Success requires named passing checks from the trusted caller")
        elif not isinstance(error, str) or not error.strip():
            raise WorkflowError("A failure requires an explanation")
        with self._transaction():
            row = self._task(identifier, actor, assigned=True)
            if row["state"] != "running":
                raise WorkflowError("Only a running task can finish")
            children = self.db.execute("SELECT state FROM tasks WHERE parent=?", (identifier,)).fetchall()
            if success and any(c["state"] != "succeeded" for c in children):
                raise WorkflowError("A parent cannot succeed while delegated work is incomplete or failed")
            if success and self.db.execute(
                "SELECT 1 FROM requests WHERE task=? AND approved=1 AND consumed=0 AND resume_revision=?",
                (identifier, row["revision"]),
            ).fetchone():
                raise WorkflowError("Approved action has not been released or reconciled")
            self._transition(row, "succeeded" if success else "failed")
            self.db.execute("UPDATE tasks SET evidence=? WHERE id=?", (
                json.dumps({"checks": checks} if success else {"error": error}, sort_keys=True), identifier,
            ))
            self._event(identifier, actor, "succeeded" if success else "failed")
            if not success:
                self._cancel_descendants(identifier, actor)

    def _cancel_descendants(self, identifier, actor):
        descendants = self.db.execute("""
            WITH RECURSIVE descendants(id) AS (
                SELECT id FROM tasks WHERE parent=?
                UNION ALL SELECT t.id FROM tasks t JOIN descendants d ON t.parent=d.id
            ) SELECT t.* FROM tasks t JOIN descendants d ON t.id=d.id
        """, (identifier,)).fetchall()
        for child in descendants:
            if child["state"] not in {"succeeded", "failed", "cancelled"}:
                self._transition(child, "cancelled")
                self._event(child["id"], actor, "cancelled", {"reason": "parent terminated"})

    def metrics(self, chat, actor):
        self._member(chat, actor)
        now = self.clock()
        records = []
        for row in self.db.execute("SELECT * FROM tasks WHERE chat=? ORDER BY created,id", (chat,)):
            elapsed = max(0, (row["ended"] if row["ended"] is not None else now) - row["created"])
            waiting = row["wait_seconds"]
            if row["wait_started"] is not None:
                waiting += max(0, now - row["wait_started"])
            records.append({
                "task_id": row["id"], "parent": row["parent"], "state": row["state"],
                "elapsed_seconds": elapsed, "human_wait_seconds": waiting,
            })
        def summarize(items):
            total = len(items)
            successes = sum(r["state"] == "succeeded" for r in items)
            return {"assigned": total, "succeeded": successes,
                    "success_fraction": successes / total if total else None}
        return {
            "interpretation": "Trusted workflow accounting; not a model-performance benchmark",
            "goals": summarize([r for r in records if r["parent"] is None]),
            "subtasks": summarize([r for r in records if r["parent"] is not None]),
            "tasks": records,
        }
