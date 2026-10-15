"""Controlled UTF-8 file operations for trusted callers, not a process sandbox.

Directory descriptors and no-follow opens enforce the broker's path boundary.
Untrusted processes must never run on this host or receive these descriptors.
"""

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import stat
from uuid import uuid4

from .core import WorkflowError


class FileToolError(WorkflowError):
    """Rejected file request, invalid content, or unavailable execution boundary."""


def _parts(path):
    if not isinstance(path, str) or not path or "\\" in path or "\0" in path:
        raise FileToolError("Use a nonempty relative POSIX file path")
    parts = path.split("/")
    if any(p in {"", ".", ".."} for p in parts):
        raise FileToolError("Absolute paths, empty components, and traversal are forbidden")
    return parts


def _sha(data):
    return hashlib.sha256(data).hexdigest()


class FileTools:
    def __init__(self, workflow, root, *, max_bytes=1024 * 1024):
        required = [os.open, os.mkdir, os.unlink, os.rename]
        if (not all(function in os.supports_dir_fd for function in required)
                or not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY")):
            raise FileToolError("This platform cannot enforce the required descriptor-based file boundary")
        if type(max_bytes) is not int or max_bytes < 1:
            raise FileToolError("File byte limit must be a positive integer")
        self.workflow = workflow
        self.max_bytes = max_bytes
        self.root_fd = self.tasks_fd = self.handoffs_fd = None
        root = Path(root)
        root.mkdir(parents=True, mode=0o700, exist_ok=True)
        try:
            self.root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            info = os.fstat(self.root_fd)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
                raise FileToolError("File root must be owned by the current user and private (mode 0700)")
            workflow.db.executescript("""
                CREATE TABLE IF NOT EXISTS file_root (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1), device INTEGER, inode INTEGER
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY, source_task TEXT NOT NULL REFERENCES tasks(id),
                    target_task TEXT NOT NULL REFERENCES tasks(id), recipient TEXT NOT NULL REFERENCES actors(id),
                    sha256 TEXT NOT NULL, bytes INTEGER NOT NULL, consumed INTEGER NOT NULL DEFAULT 0
                );
            """)
            with workflow._transaction():
                bound = workflow.db.execute("SELECT * FROM file_root WHERE singleton=1").fetchone()
                if bound and (bound["device"], bound["inode"]) != (info.st_dev, info.st_ino):
                    raise FileToolError("Workflow database is already bound to another file root")
                workflow.db.execute("INSERT OR IGNORE INTO file_root VALUES(1,?,?)", (info.st_dev, info.st_ino))
            self.tasks_fd = self._directory(self.root_fd, "tasks", create=True)
            self.handoffs_fd = self._directory(self.root_fd, "handoffs", create=True)
        except BaseException:
            self.close()
            raise

    def close(self):
        for name in ("handoffs_fd", "tasks_fd", "root_fd"):
            descriptor = getattr(self, name, None)
            if descriptor is not None:
                os.close(descriptor)
                setattr(self, name, None)

    @staticmethod
    def _directory(parent, name, *, create=False):
        if create:
            try:
                os.mkdir(name, mode=0o700, dir_fd=parent)
            except FileExistsError:
                pass
        return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)

    @contextmanager
    def _task_directory(self, task, actor):
        row = self.workflow._task(task, actor, assigned=True)
        if row["state"] != "running":
            raise FileToolError("Only an assigned running task may use file tools")
        directory = self._directory(self.tasks_fd, _sha(task.encode()), create=True)
        try:
            yield directory
        finally:
            os.close(directory)

    @contextmanager
    def _parent(self, task_directory, path, *, create=False):
        parts = _parts(path)
        directory = os.dup(task_directory)
        try:
            for part in parts[:-1]:
                following = self._directory(directory, part, create=create)
                os.close(directory)
                directory = following
            yield directory, parts[-1]
        finally:
            os.close(directory)

    @contextmanager
    def _access(self, task, actor):
        try:
            with self.workflow._transaction(), self._task_directory(task, actor) as directory:
                yield directory
        except (OSError, UnicodeError) as error:
            raise FileToolError("File request rejected; inspect the task path, content, and file type") from error

    def _encode(self, content):
        if not isinstance(content, str):
            raise FileToolError("File tools accept UTF-8 text, not arbitrary binary content")
        try:
            data = content.encode("utf-8")
        except UnicodeError as error:
            raise FileToolError("Content is not valid UTF-8") from error
        if len(data) > self.max_bytes:
            raise FileToolError("File exceeds the configured byte limit")
        return data

    def _read(self, directory, name):
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise FileToolError("Only regular, single-link files may be read or modified")
            if info.st_size > self.max_bytes:
                raise FileToolError("File exceeds the configured byte limit")
            data = bytearray()
            while len(data) <= self.max_bytes:
                chunk = os.read(descriptor, min(65536, self.max_bytes + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            if len(data) > self.max_bytes:
                raise FileToolError("File exceeds the configured byte limit")
            bytes(data).decode("utf-8")
            return bytes(data)
        finally:
            os.close(descriptor)

    @staticmethod
    def _create(directory, name, data):
        descriptor = os.open(
            name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory,
        )
        try:
            remaining = memoryview(data)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise FileToolError("File write made no progress")
                remaining = remaining[written:]
            os.fsync(descriptor)
        except BaseException:
            os.unlink(name, dir_fd=directory)
            raise
        finally:
            os.close(descriptor)

    @staticmethod
    def _expected(data, expected_sha256):
        if not isinstance(expected_sha256, str) or _sha(data) != expected_sha256:
            raise FileToolError("Content digest changed or did not match the expected version")

    def _receipt(self, task, actor, operation, path, data):
        result = {"path": path, "sha256": _sha(data), "bytes": len(data)}
        self.workflow._event(task, actor, operation, result)
        return result

    def read_text(self, task, actor, path):
        with self._access(task, actor) as directory, self._parent(directory, path) as (parent, name):
            data = self._read(parent, name)
            return {**self._receipt(task, actor, "file_read", path, data), "content": data.decode("utf-8")}

    def create_text(self, task, actor, path, content):
        data = self._encode(content)
        with self._access(task, actor) as directory, self._parent(directory, path, create=True) as (parent, name):
            self._create(parent, name, data)
            return self._receipt(task, actor, "file_created", path, data)

    def update_text(self, task, actor, path, content, *, expected_sha256):
        data = self._encode(content)
        with self._access(task, actor) as directory, self._parent(directory, path) as (parent, name):
            self._expected(self._read(parent, name), expected_sha256)
            temporary = ".write-" + uuid4().hex
            self._create(parent, temporary, data)
            try:
                os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
            finally:
                try:
                    os.unlink(temporary, dir_fd=parent)
                except FileNotFoundError:
                    pass
            return self._receipt(task, actor, "file_updated", path, data)

    def delete_text(self, task, actor, path, *, expected_sha256):
        with self._access(task, actor) as directory, self._parent(directory, path) as (parent, name):
            data = self._read(parent, name)
            self._expected(data, expected_sha256)
            os.unlink(name, dir_fd=parent)
            return self._receipt(task, actor, "file_deleted", path, data)

    def offer_artifact(self, task, actor, path, target_task, *, expected_sha256):
        with self._access(task, actor) as directory, self._parent(directory, path) as (parent, name):
            source = self.workflow._task(task, actor, assigned=True)
            target = self.workflow._task(target_task, actor)
            if source["chat"] != target["chat"] or target["state"] not in {"pending", "running"}:
                raise FileToolError("Offer artifacts only to an active task in the same conversation")
            data = self._read(parent, name)
            self._expected(data, expected_sha256)
            identifier = uuid4().hex
            self._create(self.handoffs_fd, identifier, data)
            self.workflow.db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?,0)", (
                identifier, task, target_task, target["assignee"], _sha(data), len(data),
            ))
            self.workflow._event(task, actor, "artifact_offered", {
                "artifact_id": identifier, "target_task": target_task, "sha256": _sha(data),
            })
            return {"artifact_id": identifier, "sha256": _sha(data), "bytes": len(data)}

    def accept_artifact(self, task, actor, artifact_id, path):
        with self._access(task, actor) as directory:
            artifact = self.workflow._row("artifacts", artifact_id)
            source = self.workflow._task(artifact["source_task"], actor)
            if (artifact["target_task"] != task or artifact["recipient"] != actor
                    or artifact["consumed"] or source["state"] in {"failed", "cancelled"}):
                raise FileToolError("Artifact is not offered to this task, is consumed, or its source terminated")
            data = self._read(self.handoffs_fd, artifact_id)
            self._expected(data, artifact["sha256"])
            if len(data) != artifact["bytes"]:
                raise FileToolError("Artifact size does not match its manifest")
            with self._parent(directory, path, create=True) as (parent, name):
                self._create(parent, name, data)
            self.workflow.db.execute("UPDATE artifacts SET consumed=1 WHERE id=?", (artifact_id,))
            result = self._receipt(task, actor, "artifact_received", path, data)
            return {**result, "artifact_id": artifact_id}

    def complete_from_text(self, task, actor, expected):
        """Trusted runner-only verifier; expected contents must not come from a model."""
        if not isinstance(expected, dict) or not expected:
            raise FileToolError("Provide trusted expected text for at least one artifact")
        expected_digests = {path: _sha(self._encode(text)) for path, text in expected.items()}
        for path in expected_digests:
            _parts(path)

        def verify():
            checks = {}
            receipts = []
            try:
                with self._task_directory(task, actor) as directory:
                    for path, digest in expected_digests.items():
                        with self._parent(directory, path) as (parent, name):
                            data = self._read(parent, name)
                        checks["artifact:" + path] = _sha(data) == digest
                        receipts.append({"path": path, "actual_sha256": _sha(data), "expected_sha256": digest})
            except (OSError, UnicodeError) as error:
                raise FileToolError("Artifact verification could not read the expected text") from error
            if all(checks.values()):
                self.workflow._event(task, actor, "artifacts_verified", {"artifacts": receipts})
            return checks

        self.workflow.finish_task(task, actor, verifier=verify)

    def execute_code(self, task, actor, command):
        with self._access(task, actor):
            raise FileToolError("No process sandbox configured; host code execution is unavailable")
