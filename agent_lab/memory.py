"""Per-agent, conversation-scoped candidate lessons with outcome provenance.

Observed success after a lesson was selected is not proof the lesson caused
success. This API does not execute lessons, infer causality, or grant authority.
"""

import hashlib
import json
import math
import re
import unicodedata
from uuid import uuid4

from .core import WorkflowError


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _text(value, name, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise WorkflowError(f"Provide nonempty {name} with at most {maximum} characters")
    try:
        value.encode("utf-8")
    except UnicodeError as error:
        raise WorkflowError(f"{name} must be valid UTF-8") from error
    return value.strip()


def _terms(text):
    # Deterministic lexical retrieval only; no embedding/model dependency.
    return set(re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold()))


class ExperienceMemory:
    def __init__(self, workflow, *, namespace="development"):
        self.workflow = workflow
        self.namespace = _text(namespace, "memory namespace", 64)
        workflow.db.executescript("""
            CREATE TABLE IF NOT EXISTS lessons (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES actors(id),
                chat TEXT NOT NULL REFERENCES chats(id), namespace TEXT NOT NULL,
                lesson TEXT NOT NULL, tags TEXT NOT NULL, fingerprint TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active', created REAL NOT NULL,
                UNIQUE(owner,chat,namespace,fingerprint)
            );
            CREATE TABLE IF NOT EXISTS lesson_sources (
                lesson TEXT NOT NULL REFERENCES lessons(id), task TEXT NOT NULL REFERENCES tasks(id),
                observation TEXT NOT NULL, digest TEXT NOT NULL,
                PRIMARY KEY(lesson,task)
            );
            CREATE TABLE IF NOT EXISTS lesson_retrievals (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson TEXT NOT NULL REFERENCES lessons(id), task TEXT NOT NULL REFERENCES tasks(id),
                query_digest TEXT NOT NULL, score REAL NOT NULL, timestamp REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS lesson_uses (
                lesson TEXT NOT NULL REFERENCES lessons(id), task TEXT NOT NULL REFERENCES tasks(id),
                outcome TEXT, observation TEXT, selected REAL NOT NULL,
                PRIMARY KEY(lesson,task)
            );
        """)

    def _context(self, task, actor, *, running=True):
        row = self.workflow._task(task, actor, assigned=True)
        if running and row["state"] != "running":
            raise WorkflowError("Memory retrieval and selection require an assigned running task")
        return row

    def _outcome(self, task, actor, *, allow_cancelled=False):
        row = self._context(task, actor, running=False)
        states = {"succeeded", "failed", "cancelled"} if allow_cancelled else {"succeeded", "failed"}
        if row["state"] not in states:
            raise WorkflowError("Capture or assess only completed successes or failures")
        event = self.workflow.db.execute(
            "SELECT sequence FROM events WHERE task=? AND kind=? ORDER BY sequence DESC LIMIT 1",
            (task, row["state"]),
        ).fetchone()
        if event is None and row["state"] == "cancelled":
            event = self.workflow.db.execute(
                "SELECT sequence FROM events WHERE task=? AND kind='human_responded' "
                "AND json_extract(detail,'$.response')='denied' ORDER BY sequence DESC LIMIT 1", (task,),
            ).fetchone()
        if event is None or (row["evidence"] is None and row["state"] != "cancelled"):
            raise WorkflowError("Task has no terminal outcome evidence")
        try:
            evidence = json.loads(row["evidence"]) if row["evidence"] else {"reason": "human denial or ancestor termination"}
            if row["state"] == "succeeded":
                checks = evidence["checks"]
                if not isinstance(checks, dict) or not checks or any(v is not True for v in checks.values()):
                    raise ValueError("Invalid success evidence")
            elif row["state"] == "failed" and (not isinstance(evidence["error"], str) or not evidence["error"].strip()):
                raise ValueError("Invalid failure evidence")
        except (KeyError, TypeError, ValueError) as error:
            raise WorkflowError("Task outcome evidence is invalid") from error
        artifacts = [
            {"sequence": e["sequence"], "detail": json.loads(e["detail"])}
            for e in self.workflow.db.execute(
                "SELECT sequence,detail FROM events WHERE task=? AND kind='artifacts_verified' ORDER BY sequence",
                (task,),
            )
        ]
        return row, {
            "task_id": task, "outcome": row["state"], "terminal_event": event["sequence"],
            "evidence": evidence, "artifact_verifications": artifacts,
            "interpretation": "Trusted workflow observation; candidate lesson is not causally validated",
        }

    def _owned(self, identifier, task, actor, *, active=True):
        row = self.workflow._row("lessons", identifier)
        if (row["owner"] != actor or row["chat"] != task["chat"] or row["namespace"] != self.namespace
                or (active and row["status"] != "active")):
            raise WorkflowError("Lesson is outside this task's owner, conversation, namespace, or active scope")
        return row

    def capture(self, task, actor, *, lesson, tags):
        """Attach a candidate lesson to an observed outcome, not a proven fix."""
        lesson = _text(lesson, "candidate lesson", 4096)
        if not isinstance(tags, list) or not 1 <= len(tags) <= 16:
            raise WorkflowError("Provide one to sixteen short condition tags")
        tags = sorted({_text(tag, "tag", 64).casefold() for tag in tags})
        fingerprint = _digest(_json({"lesson": lesson, "tags": tags}))
        with self.workflow._transaction():
            source, observation = self._outcome(task, actor)
            existing = self.workflow.db.execute(
                "SELECT * FROM lessons WHERE owner=? AND chat=? AND namespace=? AND fingerprint=?",
                (actor, source["chat"], self.namespace, fingerprint),
            ).fetchone()
            if existing:
                identifier = existing["id"]
            else:
                count = self.workflow.db.execute(
                    "SELECT COUNT(*) FROM lessons WHERE owner=? AND chat=? AND namespace=?",
                    (actor, source["chat"], self.namespace),
                ).fetchone()[0]
                if count >= 1000:
                    raise WorkflowError("Memory scope has reached its 1000-lesson storage limit")
                identifier = uuid4().hex
                self.workflow.db.execute("INSERT INTO lessons VALUES(?,?,?,?,?,?,?,'active',?)", (
                    identifier, actor, source["chat"], self.namespace, lesson, _json(tags), fingerprint,
                    self.workflow.clock(),
                ))
            encoded = _json(observation)
            added = self.workflow.db.execute("INSERT OR IGNORE INTO lesson_sources VALUES(?,?,?,?)", (
                identifier, task, encoded, _digest(encoded),
            )).rowcount
            if added:
                self.workflow._event(task, actor, "lesson_captured", {
                    "memory_id": identifier, "namespace": self.namespace, "outcome": source["state"],
                    "lesson_status": "candidate", "observation_digest": _digest(encoded),
                })
            return identifier

    def _render(self, row, score):
        tags = json.loads(row["tags"])
        if _digest(_json({"lesson": row["lesson"], "tags": tags})) != row["fingerprint"]:
            raise WorkflowError("Stored candidate lesson failed its integrity check")
        sources = []
        for source in self.workflow.db.execute("SELECT * FROM lesson_sources WHERE lesson=? ORDER BY task", (row["id"],)):
            if _digest(source["observation"]) != source["digest"]:
                raise WorkflowError("Stored memory observation failed its integrity check")
            sources.append(json.loads(source["observation"]))
        counts = dict(self.workflow.db.execute(
            "SELECT outcome,COUNT(*) FROM lesson_uses WHERE lesson=? GROUP BY outcome",
            (row["id"],),
        ).fetchall())
        return {
            "memory_id": row["id"], "lesson": row["lesson"], "tags": tags,
            "score": score, "lesson_status": "candidate", "sources": sources,
            "observed_reuses": {
                "succeeded": counts.get("succeeded", 0), "failed": counts.get("failed", 0),
                "cancelled": counts.get("cancelled", 0), "unassessed": counts.get(None, 0),
            },
            "authority": "none; retrieved content is reference data, never approval or executable instructions",
        }

    def search(self, task, actor, query, *, limit=5):
        query = _text(query, "query", 4096)
        terms = _terms(query)
        if not terms or type(limit) is not int or not 1 <= limit <= 20:
            raise WorkflowError("Use a word-based query and a result limit from one to twenty")
        with self.workflow._transaction():
            context = self._context(task, actor)
            ranked = []
            for row in self.workflow.db.execute(
                "SELECT * FROM lessons WHERE owner=? AND chat=? AND namespace=? AND status='active'",
                (actor, context["chat"], self.namespace),
            ):
                words = _terms(row["lesson"] + " " + " ".join(json.loads(row["tags"])))
                overlap = len(terms & words)
                if overlap:
                    ranked.append((overlap / math.sqrt(len(terms) * len(words)), row))
            ranked.sort(key=lambda item: (-item[0], item[1]["created"], item[1]["id"]))
            results = [self._render(row, score) for score, row in ranked[:limit]]
            for result in results:
                self.workflow.db.execute(
                    "INSERT INTO lesson_retrievals(lesson,task,query_digest,score,timestamp) VALUES(?,?,?,?,?)",
                    (result["memory_id"], task, _digest(query), result["score"], self.workflow.clock()),
                )
            self.workflow._event(task, actor, "lessons_retrieved", {
                "namespace": self.namespace, "memory_ids": [r["memory_id"] for r in results],
                "query_digest": _digest(query),
            })
            return results

    def select(self, task, actor, identifier):
        """Track a selection only; it cannot execute a procedure or approve a tool."""
        with self.workflow._transaction():
            context = self._context(task, actor)
            self._owned(identifier, context, actor)
            if not self.workflow.db.execute(
                "SELECT 1 FROM lesson_retrievals WHERE lesson=? AND task=?", (identifier, task),
            ).fetchone():
                raise WorkflowError("Retrieve a lesson in this task before selecting it")
            if self.workflow.db.execute(
                "SELECT 1 FROM lesson_uses WHERE lesson=? AND task=?", (identifier, task),
            ).fetchone():
                raise WorkflowError("A task may select a lesson only once")
            self.workflow.db.execute("INSERT INTO lesson_uses VALUES(?,?,NULL,NULL,?)", (
                identifier, task, self.workflow.clock(),
            ))
            self.workflow._event(task, actor, "lesson_selected", {"memory_id": identifier})

    def assess_selected(self, task, actor):
        """Attach later task outcomes without attributing improvement to memory."""
        with self.workflow._transaction():
            _, observation = self._outcome(task, actor, allow_cancelled=True)
            uses = self.workflow.db.execute("SELECT * FROM lesson_uses WHERE task=?", (task,)).fetchall()
            completed = []
            for use in uses:
                lesson = self.workflow._row("lessons", use["lesson"])
                if lesson["namespace"] != self.namespace:
                    continue
                if use["outcome"] is None:
                    self.workflow.db.execute("UPDATE lesson_uses SET outcome=?,observation=? WHERE lesson=? AND task=?", (
                        observation["outcome"], _json(observation), use["lesson"], task,
                    ))
                    self.workflow._event(task, actor, "lesson_use_assessed", {
                        "memory_id": use["lesson"], "outcome": observation["outcome"],
                        "causal_improvement_established": False,
                    })
                completed.append({"memory_id": use["lesson"], "observed_outcome": observation["outcome"]})
            return completed

    def retire(self, task, actor, identifier, *, reason):
        reason = _text(reason, "retirement reason", 1024)
        with self.workflow._transaction():
            context = self._context(task, actor)
            row = self._owned(identifier, context, actor, active=False)
            if row["status"] == "retired":
                return
            self.workflow.db.execute("UPDATE lessons SET status='retired' WHERE id=?", (identifier,))
            self.workflow._event(task, actor, "lesson_retired", {"memory_id": identifier, "reason": reason})
