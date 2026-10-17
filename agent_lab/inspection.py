"""Read-only artifact inspection for the supervising human.

Agents keep using `FileTools`, where only the assigned agent of a running task
may operate on its files. This view adds one narrow path: a *human member* of
the task's conversation may read (never write) task-local text and offered
snapshots through the same descriptor-anchored, no-follow broker reads. Agents
cannot use it, and no host path outside the broker root is reachable.
"""

import difflib
import hashlib
import json
import os

from .core import WorkflowError
from .files import FileToolError, _parts

_FILE_EVENTS = ("file_created", "file_updated", "file_deleted", "artifact_received", "file_read")
LANGUAGES = {".py": "python", ".md": "markdown", ".txt": "text", ".json": "json", ".toml": "toml",
             ".yml": "yaml", ".yaml": "yaml", ".sh": "bash", ".js": "javascript", ".html": "html"}


def language(path):
    return LANGUAGES.get(os.path.splitext(path)[1].lower(), "text")


class ArtifactMissingError(FileToolError):
    """The authorized inspection positively observed that a file is absent."""


class ArtifactInspector:
    def __init__(self, workflow, files):
        if files.workflow is not workflow:
            raise WorkflowError("Inspector requires the same workflow and file broker")
        self.workflow, self.files = workflow, files

    def _supervisor(self, task, actor):
        row = self.workflow._task(task, actor)
        if self.workflow._row("actors", actor)["kind"] != "human":
            raise FileToolError("Only a human member of this conversation may inspect task files here")
        return row

    def history(self, task, actor):
        """Recorded file receipts per path, oldest first (hashes, not contents)."""
        self._supervisor(task, actor)
        marks = ",".join("?" * len(_FILE_EVENTS))
        versions = {}
        for event in self.workflow.db.execute(
                f"SELECT sequence,kind,detail,timestamp FROM events WHERE task=? AND kind IN ({marks}) ORDER BY sequence",
                (task, *_FILE_EVENTS)):
            detail = json.loads(event["detail"])
            if "path" not in detail:
                continue
            versions.setdefault(detail["path"], []).append({
                "sequence": event["sequence"], "operation": event["kind"], "timestamp": event["timestamp"],
                "sha256": detail.get("sha256"), "bytes": detail.get("bytes"),
                "artifact_id": detail.get("artifact_id")})
        return versions

    def _read(self, task, path):
        _parts(path)
        name = hashlib.sha256(task.encode()).hexdigest()
        try:
            directory = self.files._directory(self.files.tasks_fd, name)
        except FileNotFoundError:
            return None
        try:
            with self.files._parent(directory, path) as (parent, leaf):
                return self.files._read(parent, leaf)
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError) as error:
            raise FileToolError("File cannot be inspected; it is not a bounded regular UTF-8 file") from error
        finally:
            os.close(directory)

    def list_files(self, task, actor):
        """Files known from broker receipts, with their current on-disk state."""
        result = []
        for path, versions in sorted(self.history(task, actor).items()):
            recorded = [v for v in versions if v["operation"] != "file_read"]
            last = recorded[-1] if recorded else versions[-1]
            try:
                data = self._read(task, path)
                current = None if data is None else {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                error = None
            except FileToolError as problem:
                current, error = None, str(problem)
            deleted = last["operation"] == "file_deleted"
            result.append({
                "path": path, "language": language(path), "last_operation": last["operation"],
                "recorded_sha256": None if deleted else last["sha256"], "current": current, "error": error,
                # A disk change without a broker receipt must be visible, not hidden.
                "matches_receipt": (current is None) if deleted else bool(current and current["sha256"] == last["sha256"]),
                "versions": len([v for v in versions if v["operation"] != "file_read"]),
            })
        return result

    def read_file(self, task, actor, path):
        self._supervisor(task, actor)
        data = self._read(task, path)
        if data is None:
            raise ArtifactMissingError("File is absent from this task's directory")
        return {"path": path, "language": language(path), "content": data.decode("utf-8"),
                "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}

    def transfers(self, actor, *, task=None, chat=None):
        """Explicit artifact handoffs visible to a human conversation member."""
        if self.workflow._row("actors", actor)["kind"] != "human":
            raise FileToolError("Only a human supervisor may inspect transfers here")
        if not self.workflow.db.execute("SELECT 1 FROM sqlite_master WHERE name='artifacts'").fetchone():
            return []
        rows = self.workflow.db.execute("""
            SELECT a.*,s.assignee AS source_agent,s.chat,t.title AS target_title,s.title AS source_title
            FROM artifacts a JOIN tasks s ON s.id=a.source_task JOIN tasks t ON t.id=a.target_task
            JOIN members m ON m.chat=s.chat AND m.actor=? ORDER BY a.rowid
        """, (actor,)).fetchall()
        result = []
        for row in rows:
            if task is not None and task not in {row["source_task"], row["target_task"]}:
                continue
            if chat is not None and row["chat"] != chat:
                continue
            offered = self.workflow.db.execute(
                "SELECT sequence,timestamp FROM events WHERE task=? AND kind='artifact_offered' "
                "AND json_extract(detail,'$.artifact_id')=?", (row["source_task"], row["id"])).fetchone()
            received = None
            if row["consumed"] and offered is not None:
                # Receipt events record path and digest; match the first import of
                # this digest into the recipient task after the offer.
                received = self.workflow.db.execute(
                    "SELECT timestamp,detail FROM events WHERE task=? AND kind='artifact_received' "
                    "AND json_extract(detail,'$.sha256')=? AND sequence>? ORDER BY sequence LIMIT 1",
                    (row["target_task"], row["sha256"], offered["sequence"])).fetchone()
            result.append({"artifact_id": row["id"], "source_task": row["source_task"],
                           "source_agent": row["source_agent"], "target_task": row["target_task"],
                           "recipient": row["recipient"], "sha256": row["sha256"], "bytes": row["bytes"],
                           "consumed": bool(row["consumed"]),
                           "offered_at": offered["timestamp"] if offered else None,
                           "received_at": received["timestamp"] if received else None,
                           "received_path": json.loads(received["detail"])["path"] if received else None})
        return result

    def snapshot(self, artifact_id, actor):
        """Offered snapshot text, integrity-checked against its manifest."""
        row = self.workflow._row("artifacts", artifact_id)
        self._supervisor(row["source_task"], actor)
        try:
            data = self.files._read(self.files.handoffs_fd, artifact_id)
        except (OSError, UnicodeError) as error:
            raise FileToolError("Snapshot cannot be inspected") from error
        if hashlib.sha256(data).hexdigest() != row["sha256"] or len(data) != row["bytes"]:
            raise FileToolError("Snapshot failed its manifest integrity check")
        return {"artifact_id": artifact_id, "content": data.decode("utf-8"), "sha256": row["sha256"]}

    def compare_transfer(self, artifact_id, actor):
        """Diff an offered snapshot against the recipient's current imported copy."""
        snap = self.snapshot(artifact_id, actor)
        transfer = next((t for t in self.transfers(actor) if t["artifact_id"] == artifact_id), None)
        if transfer is None or not transfer["received_path"]:
            return {"artifact_id": artifact_id, "status": "not_received", "diff": ""}
        current = self._read(transfer["target_task"], transfer["received_path"])
        if current is None:
            return {"artifact_id": artifact_id, "status": "recipient_copy_absent", "diff": ""}
        text = current.decode("utf-8")
        diff = "".join(difflib.unified_diff(
            snap["content"].splitlines(keepends=True), text.splitlines(keepends=True),
            fromfile="offered:" + artifact_id[:12], tofile="received:" + transfer["received_path"]))
        return {"artifact_id": artifact_id, "status": "identical" if not diff else "changed_since_receipt", "diff": diff}
