"""Read-only, membership-checked views of persisted workflow evidence.

These helpers serve trusted local interfaces such as the terminal control
center. They never change workflow state and they apply the same conversation
membership rule as `Workflow` reads. Actor identifiers still require a future
authenticated transport; this is not an authorization service.
"""

import hashlib
import json
import re

from .core import WorkflowError, canonical_action

TERMINAL = frozenset({"succeeded", "failed", "cancelled"})
WAITING = frozenset({"waiting_input", "waiting_approval"})
_SECRET_KEYS = re.compile(r"(pass(word)?|secret|token|api[_-]?key|authorization|credential|private[_-]?key)", re.I)
_SECRET_VALUES = re.compile(
    r"(-----BEGIN [A-Z ]*PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}"
    r"|\bsk-[A-Za-z0-9_-]{16,}|\bAKIA[0-9A-Z]{16}\b|\bxox[abpr]-[A-Za-z0-9-]{10,})")


def redact(value, *, limit=2000):
    """Hide credential-like keys/values and bound long strings for display only."""
    if isinstance(value, dict):
        return {key: "[redacted]" if _SECRET_KEYS.search(str(key)) else redact(item, limit=limit)
                for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, limit=limit) for item in value]
    if isinstance(value, str):
        if _SECRET_VALUES.search(value):
            return "[redacted: credential-like content]"
        if len(value) > limit:
            return value[:limit] + f"... [{len(value) - limit} more characters]"
    return value


def _loads(text, default=None):
    if text is None:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


class WorkflowQueries:
    def __init__(self, workflow):
        self.workflow = workflow
        self.db = workflow.db

    def _table(self, name):
        return self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None

    def _proposal_text(self, task, turn, response):
        if not response:
            return None
        if response['finish_reason'] == 'stop':
            return response['message'].get('content')
        calls = response['message'].get('tool_calls') or []
        if not calls or calls[-1]['function']['name'] != 'submit_for_verification' or not self._table('tool_calls'):
            return None
        call = calls[-1]
        record = self.db.execute('SELECT * FROM tool_calls WHERE task=? AND call_id=?', (task, call['id'])).fetchone()
        floor = _loads(turn['request'], {}).get('event_floor')
        if (record is None or record['status'] != 'succeeded' or record['name'] != 'submit_for_verification'
                or type(floor) is not int or not self.db.execute(
                    "SELECT 1 FROM events WHERE task=? AND sequence>? AND kind='tool_reserved' AND json_extract(detail,'$.call_id')=?",
                    (task, floor, call['id'])).fetchone()):
            return None
        args = _loads(record['arguments'], {})
        result = _loads(record['result'], {})
        if (args != _loads(call['function']['arguments']) or result.get('ok') is not True
                or result.get('result', {}).get('status') != 'verification_requested'):
            return None
        return args.get('summary')

    def _member_chats(self, actor):
        return [row[0] for row in self.db.execute("SELECT chat FROM members WHERE actor=?", (actor,))]

    def actor_kind(self, actor):
        return self.workflow._row("actors", actor)["kind"]

    def actors(self):
        # Actor registry entries are identifiers and kinds only; no private content.
        return [dict(row) for row in self.db.execute("SELECT id,kind FROM actors ORDER BY kind,id")]

    def conversations(self, actor):
        self.workflow._row("actors", actor)
        result = []
        for row in self.db.execute("""
            SELECT c.id,c.kind,
                   (SELECT count(*) FROM messages m WHERE m.chat=c.id) AS message_count,
                   (SELECT max(timestamp) FROM messages m WHERE m.chat=c.id) AS last_message,
                   (SELECT count(*) FROM tasks t WHERE t.chat=c.id) AS task_count
            FROM chats c JOIN members me ON me.chat=c.id AND me.actor=?
            ORDER BY c.rowid
        """, (actor,)):
            members = [dict(m) for m in self.db.execute(
                "SELECT a.id,a.kind FROM members m JOIN actors a ON a.id=m.actor WHERE m.chat=? ORDER BY a.kind,a.id",
                (row["id"],))]
            result.append(dict(row) | {"members": members})
        return result

    def conversation_feed(self, chat, actor):
        """Messages and task communication for one conversation, in time order."""
        items = [{"type": "message", "timestamp": m["timestamp"], "sender": m["sender"], "body": m["body"]}
                 for m in self.workflow.messages(chat, actor)]
        for event in self.db.execute("""
            SELECT e.*,t.title,t.assignee FROM events e JOIN tasks t ON t.id=e.task
            WHERE t.chat=? AND e.kind IN ('created','delegated','started','human_requested',
                'human_responded','approval_consumed','succeeded','failed','cancelled')
            ORDER BY e.sequence
        """, (chat,)):
            items.append({"type": "task_event", "timestamp": event["timestamp"], "sender": event["actor"],
                          "task": event["task"], "title": event["title"], "kind": event["kind"],
                          "detail": redact(_loads(event["detail"], {}))})
        items.sort(key=lambda item: (item["timestamp"], item["type"] != "message"))
        return items

    def _task_record(self, row, now):
        elapsed = max(0, (row["ended"] if row["ended"] is not None else now) - row["created"])
        waiting = row["wait_seconds"] + (max(0, now - row["wait_started"]) if row["wait_started"] is not None else 0)
        return {"id": row["id"], "chat": row["chat"], "parent": row["parent"], "assignee": row["assignee"],
                "title": redact(row["title"]), "state": row["state"], "created": row["created"], "ended": row["ended"],
                "elapsed_seconds": elapsed, "human_wait_seconds": waiting,
                "waiting_on_human": row["state"] in WAITING, "evidence": redact(_loads(row["evidence"]))}

    def tasks(self, actor, *, chat=None):
        """All tasks in conversations the actor belongs to (optionally one chat)."""
        if chat is not None:
            self.workflow._member(chat, actor)
            chats = [chat]
        else:
            chats = self._member_chats(actor)
        if not chats:
            return []
        now = self.workflow.clock()
        marks = ",".join("?" * len(chats))
        return [self._task_record(row, now) for row in self.db.execute(
            f"SELECT * FROM tasks WHERE chat IN ({marks}) ORDER BY created,rowid", chats)]

    def task_tree(self, actor, *, chat=None):
        """Nested roots/children; dependencies are parent-child delegation links only."""
        records = self.tasks(actor, chat=chat)
        nodes = {record["id"]: record | {"children": []} for record in records}
        roots = []
        for record in records:
            parent = nodes.get(record["parent"])
            (parent["children"] if parent else roots).append(nodes[record["id"]])
        return roots

    def task_detail(self, task, actor):
        row = self.workflow._task(task, actor)
        record = self._task_record(row, self.workflow.clock())
        events = [{"sequence": e["sequence"], "timestamp": e["timestamp"], "actor": e["actor"],
                   "kind": e["kind"], "detail": redact(_loads(e["detail"], {}))}
                  for e in self.workflow.events(task, actor)]
        requests = [self._request_record(r) for r in self.db.execute(
            "SELECT r.*,t.state AS task_state,t.revision AS task_revision,t.assignee,t.title,t.chat "
            "FROM requests r JOIN tasks t ON t.id=r.task WHERE r.task=? ORDER BY r.rowid", (task,))]
        tools = []
        if self._table("tool_calls"):
            tools = [{"call_id": c["call_id"], "name": c["name"], "status": c["status"],
                      "arguments": redact(_loads(c["arguments"], {})), "result": redact(_loads(c["result"]))}
                     for c in self.db.execute("SELECT * FROM tool_calls WHERE task=? ORDER BY rowid", (task,))]
        runner = None
        if self._table("runner_sessions"):
            session = self.db.execute("SELECT * FROM runner_sessions WHERE task=?", (task,)).fetchone()
            if session is not None:
                config = _loads(session["config"], {})
                turns = []
                for turn in self.db.execute("SELECT * FROM runner_turns WHERE task=? ORDER BY number", (task,)):
                    response = _loads(turn["response"])
                    turns.append({
                        "number": turn["number"], "status": turn["status"], "started": turn["started"],
                        "ended": turn["ended"], "error": turn["error"],
                        # Missing responses are unknown, never a fabricated zero.
                        "usage": response["usage"] if response else None,
                        "model": response["model"] if response else None,
                        "response_id": response["response_id"] if response else None,
                        "finish_reason": response["finish_reason"] if response else None,
                        "tool_names": [c["function"]["name"] for c in (response["message"].get("tool_calls") or [])]
                                      if response else [],
                        "final_text": redact(self._proposal_text(task, turn, response), limit=600),
                    })
                # Accepted/cancelled proposals need no subsequent model turn to
                # stop appearing in review queues. Keep the stored history intact.
                status = session["status"]
                if status == "awaiting_verification" and row["state"] in TERMINAL:
                    status = row["state"]
                runner = {"mode": config.get("mode"), "model": config.get("model"), "status": status,
                          "attempts": session["attempts"], "reported_tokens": session["tokens"],
                          "stop_reason": session["stop_reason"], "verifier_id": config.get("verifier_id"),
                          "synthetic": config.get("mode") != "live", "turns": turns}
        artifacts = []
        if self._table("artifacts"):
            artifacts = [dict(a) for a in self.db.execute(
                "SELECT * FROM artifacts WHERE source_task=? OR target_task=? ORDER BY rowid", (task, task))]
        return {"task": record, "events": events, "requests": requests, "tool_calls": tools,
                "runner": runner, "artifacts": artifacts,
                "children": [c["id"] for c in self.db.execute("SELECT id FROM tasks WHERE parent=? ORDER BY rowid", (task,))]}

    def _bound_effect(self, row, action):
        """Confirm one request's durable receipt; chronology alone proves nothing.

        Legacy unbound file events stay in task history but cannot certify a
        particular approval. Git's existing operation record supplies that link.
        This reads evidence only; it never reconciles or replays an action.
        """
        try:
            if row["kind"] != "approval" or row["approved"] != 1 or not row["consumed"]:
                return None
            if canonical_action(action)[1] != row["digest"]:
                return None
            consumed = []
            for event in self.db.execute("SELECT * FROM events WHERE task=? AND kind='approval_consumed'", (row["task"],)):
                detail = _loads(event["detail"], {})
                if isinstance(detail, dict) and detail.get("request") == row["id"]:
                    consumed.append(event)
            if len(consumed) != 1:
                return None
            released = consumed[0]
            if released["actor"] != row["assignee"] or _loads(released["detail"]).get("digest") != row["digest"]:
                return None
            candidates = []
            for event in self.db.execute("SELECT * FROM events WHERE task=? AND kind IN "
                    "('file_deleted','git_push_verified','git_push_failed','git_push_uncertain')", (row["task"],)):
                detail = _loads(event["detail"], {})
                if not isinstance(detail, dict):
                    continue
                tool = action.get("tool")
                if tool == "delete_text" and event["kind"] == "file_deleted" and detail.get("request_id") == row["id"]:
                    args = action["arguments"]
                    if (set(action) != {"tool", "arguments"} or set(args) != {"path", "expected_sha256"}
                            or detail.get("path") != args["path"] or detail.get("sha256") != args["expected_sha256"]
                            or type(detail.get("bytes")) is not int or detail["bytes"] < 0):
                        return None
                elif tool == "git_push" and event["kind"].startswith("git_push_") and self._table("git_operations"):
                    if not isinstance(detail.get("operation_id"), str):
                        continue
                    operation = self.db.execute("SELECT * FROM git_operations WHERE id=?", (detail["operation_id"],)).fetchone()
                    if operation is None:
                        continue
                    arguments, result = _loads(operation["arguments"], {}), _loads(operation["result"])
                    if not isinstance(arguments, dict) or arguments.get("request_id") != row["id"]:
                        continue
                    binding, args = action["binding"], action["arguments"]
                    if (set(action) != {"tool", "arguments", "binding"}
                            or set(args) != {"repository", "remote", "branch"}
                            or any(binding.get(k) != args[k] for k in args)
                            or arguments != {**binding, "request_id": row["id"]}
                            or operation["task"] != row["task"] or operation["actor"] != row["assignee"]
                            or operation["repository"] != binding["repository"]
                            or operation["operation"] != "push" or operation["status"] != event["kind"].removeprefix("git_push_")
                            or not isinstance(result, dict) or detail != {"operation_id": operation["id"], **result}):
                        return None
                    if (any(result.get(k) != binding[k] for k in ("repository", "branch", "commit", "remote"))
                            or (operation["status"] == "verified" and (result.get("remote_observed") is not True
                                or result.get("observed_remote") != binding["commit"]
                                or type(result.get("exit_code")) is not int or result["exit_code"] != 0
                                or result.get("interrupted") is not None))):
                        return None
                else:
                    continue
                if event["sequence"] <= released["sequence"] or event["actor"] != row["assignee"]:
                    return None
                candidates.append(event)
            if len(candidates) == 1:
                return candidates[0]
        except (KeyError, TypeError, ValueError, AttributeError):
            return None
        return None

    def _request_record(self, row):
        action = _loads(row["action"])
        # A granted approval is distinct from a released (consumed) action, and
        # both are distinct from a verified external effect recorded later.
        if not row["answered"]:
            status = "pending"
        elif row["kind"] == "clarification":
            status = "answered"
        elif not row["approved"]:
            status = "denied"
        elif row["consumed"]:
            status = "released"
        elif row["task_state"] == "running" and row["task_revision"] == row["resume_revision"]:
            status = "granted_awaiting_release"
        else:
            status = "granted_stale"
        outcome = None
        if row["consumed"]:
            effect = self._bound_effect(row, action)
            outcome = ({"kind": effect["kind"], "detail": redact(_loads(effect["detail"], {})),
                        "timestamp": effect["timestamp"]} if effect else
                       {"kind": "unrecorded", "detail": "Released; no uniquely bound execution result is confirmed. Inspect evidence and reconcile before any retry."})
        return {"id": row["id"], "task": row["task"], "kind": row["kind"], "responder": row["responder"],
                "prompt": redact(row["prompt"]), "action": redact(action) if action else None, "digest": row["digest"],
                "response": redact(row["response"]), "status": status, "outcome": outcome,
                "task_state": row["task_state"], "assignee": row["assignee"], "title": redact(row["title"]),
                "chat": row["chat"]}

    def requests(self, actor, *, pending_only=False):
        """Human requests in the actor's conversations, newest last."""
        chats = self._member_chats(actor)
        if not chats:
            return []
        marks = ",".join("?" * len(chats))
        query = (f"SELECT r.*,t.state AS task_state,t.revision AS task_revision,t.assignee,t.title,t.chat "
                 f"FROM requests r JOIN tasks t ON t.id=r.task WHERE t.chat IN ({marks})")
        if pending_only:
            query += " AND r.answered=0 AND r.responder=?"
        rows = self.db.execute(query + " ORDER BY r.rowid", [*chats, *([actor] if pending_only else [])])
        return [self._request_record(row) for row in rows]

    def request_detail(self, request, actor):
        self.workflow.request(request, actor)
        row = self.db.execute(
            "SELECT r.*,t.state AS task_state,t.revision AS task_revision,t.assignee,t.title,t.chat "
            "FROM requests r JOIN tasks t ON t.id=r.task WHERE r.id=?", (request,)).fetchone()
        return self._request_record(row)

    def uncertain(self, actor):
        """Interrupted or ambiguous execution evidence; never replayed automatically."""
        visible = {task["id"] for task in self.tasks(actor)}
        found = []
        if self._table("runner_sessions"):
            for row in self.db.execute(
                    "SELECT task,status FROM runner_sessions WHERE status IN ('calling','processing','stopping')"):
                if row["task"] in visible:
                    found.append({"task": row["task"], "kind": "runner_" + row["status"],
                                  "detail": "Provider/tool turn interrupted; inspect evidence before abort or recovery"})
        if self._table("tool_calls"):
            for row in self.db.execute("SELECT task,call_id,name FROM tool_calls WHERE status='reserved'"):
                if row["task"] in visible:
                    found.append({"task": row["task"], "kind": "tool_reserved",
                                  "detail": f"{row['name']} call {row['call_id']} has an uncertain effect"})
        if self._table("scheduler_runs"):
            for row in self.db.execute("SELECT root FROM scheduler_runs WHERE owner IS NOT NULL"):
                if row["root"] in visible:
                    found.append({"task": row["root"], "kind": "controller_claim_held",
                                  "detail": "A scheduler claim is held; confirm the previous worker stopped before recovery"})
        for request in self.requests(actor):
            if request["outcome"] and request["outcome"]["kind"] in {"unrecorded", "git_push_uncertain"}:
                found.append({"task": request["task"], "kind": "released_action_unconfirmed",
                              "detail": f"Request {request['id']} was released without a confirmed result"})
        return found

    def metrics(self, actor):
        return {chat: self.workflow.metrics(chat, actor) for chat in self._member_chats(actor)}

    def memory(self, actor, *, chat=None, owner=None, namespace=None):
        """Read-only candidate lessons from conversations the actor belongs to.

        Every record keeps its own owner/conversation/namespace scope; nothing is
        merged across scopes. Lessons are candidates, never proven improvements.
        """
        if not self._table("lessons"):
            return []
        chats = [chat] if chat is not None else self._member_chats(actor)
        for item in chats:
            self.workflow._member(item, actor)
        if not chats:
            return []
        marks = ",".join("?" * len(chats))
        query, args = f"SELECT * FROM lessons WHERE chat IN ({marks})", list(chats)
        if owner is not None:
            query, args = query + " AND owner=?", args + [owner]
        if namespace is not None:
            query, args = query + " AND namespace=?", args + [namespace]
        def digest(text):
            return hashlib.sha256(text.encode()).hexdigest()

        result = []
        for row in self.db.execute(query + " ORDER BY created,id", args):
            tags = _loads(row["tags"], [])
            canonical = json.dumps({"lesson": row["lesson"], "tags": tags}, sort_keys=True,
                                   ensure_ascii=True, separators=(",", ":"))
            sources = [{"task": s["task"], "observation": _loads(s["observation"], {}),
                        "intact": digest(s["observation"]) == s["digest"]}
                       for s in self.db.execute("SELECT * FROM lesson_sources WHERE lesson=? ORDER BY task", (row["id"],))]
            retrievals = [dict(r) for r in self.db.execute(
                "SELECT task,score,timestamp FROM lesson_retrievals WHERE lesson=? ORDER BY sequence", (row["id"],))]
            uses = [{"task": u["task"], "outcome": u["outcome"] or "unassessed", "selected": u["selected"]}
                    for u in self.db.execute("SELECT * FROM lesson_uses WHERE lesson=? ORDER BY selected", (row["id"],))]
            result.append({"memory_id": row["id"], "owner": row["owner"], "chat": row["chat"],
                           "namespace": row["namespace"], "lesson": row["lesson"], "tags": tags,
                           "status": row["status"], "lesson_status": "candidate", "created": row["created"],
                           "intact": digest(canonical) == row["fingerprint"] and all(s["intact"] for s in sources),
                           "sources": sources, "retrievals": retrievals, "uses": uses,
                           "proven_improvement": False})
        return result

    def namespaces(self, actor):
        if not self._table("lessons"):
            return []
        chats = self._member_chats(actor)
        if not chats:
            return []
        marks = ",".join("?" * len(chats))
        return [row[0] for row in self.db.execute(
            f"SELECT DISTINCT namespace FROM lessons WHERE chat IN ({marks}) ORDER BY namespace", chats)]


def require_human(queries, actor):
    if queries.actor_kind(actor) != "human":
        raise WorkflowError("Only a human supervisor may use this inspection view")
