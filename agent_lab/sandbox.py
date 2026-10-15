"""Explicit, digest-pinned Docker Python execution. No host-code fallback."""

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import stat
import subprocess
import tempfile
import time
from uuid import uuid4

from .core import WorkflowError
from .files import _parts
from .protocol import strict_json


class SandboxError(WorkflowError):
    """Execution boundary unavailable, invalid, interrupted, or unreconciled."""


@dataclass(frozen=True)
class SandboxLimits:
    seconds: int = 15
    memory_mib: int = 128
    pids: int = 32
    output_bytes: int = 65536

    def __post_init__(self):
        bounds = {"seconds": (2, 60), "memory_mib": (64, 512),
                  "pids": (8, 64), "output_bytes": (1024, 262144)}
        for name, (low, high) in bounds.items():
            if type(getattr(self, name)) is not int or not low <= getattr(self, name) <= high:
                raise SandboxError("Invalid sandbox limit: " + name)


# Both helpers execute only inside the container. Source code is supplied as data
# to a fixed bootstrap, never interpolated into host shell/Python command text.
_BOOTSTRAP = """
import json, os, pathlib, sys
job = json.load(sys.stdin)
os.umask(0o022)
for name, content in job['files'].items():
    path = pathlib.Path('/work') / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
os.chdir('/work')
os.dup2(os.open('/dev/null', os.O_RDONLY), 0)
os.execv(sys.executable, [sys.executable, '-B', '-u', '/work/' + job['entrypoint'], *job['arguments']])
"""

_EXPORT = """
import json, os, stat, sys
result = {}
for name in json.loads(sys.argv[1]):
    directory = os.open('/work', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts = name.split('/')
        for part in parts[:-1]:
            following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = following
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 65536:
                raise ValueError('Export requires a bounded regular single-link file')
            data = bytearray()
            while len(data) <= 65536:
                chunk = os.read(descriptor, min(8192, 65537 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            if len(data) > 65536:
                raise ValueError('Export exceeds byte limit')
            result[name] = bytes(data).decode('utf-8')
        finally:
            os.close(descriptor)
    finally:
        os.close(directory)
print(json.dumps(result, ensure_ascii=True))
"""

_WORK_OPTIONS = "rw,nosuid,nodev,noexec,size=16m,nr_inodes=1024,uid=65534,gid=65534,mode=0755"
_TMP_OPTIONS = "rw,nosuid,nodev,noexec,size=8m,nr_inodes=1024,mode=1777"


@dataclass
class ProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    interrupted: str | None = None


def bounded_process(argv, *, payload=b"", seconds=5, output_bytes=262144, keep_running=None):
    """Bound pipe memory and wall time, including stdin backpressure. POSIX only."""
    started = time.monotonic()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    interrupted = None
    try:
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, close_fds=True, start_new_session=True,
                                   env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
    except OSError:
        raise SandboxError("Docker CLI could not start; no host-code fallback") from None
    try:
        with selectors.DefaultSelector() as selector:
            for name in ("stdout", "stderr"):
                stream = getattr(process, name)
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            offset = 0
            if payload:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
            else:
                process.stdin.close()
            while selector.get_map():
                if time.monotonic() - started >= seconds:
                    interrupted = "timeout"
                    break
                if keep_running is not None and not keep_running():
                    interrupted = "task_not_running"
                    break
                for key, events in selector.select(timeout=0.05):
                    if key.data == "stdin":
                        try:
                            offset += os.write(key.fd, payload[offset:offset + 8192])
                        except BrokenPipeError:
                            offset = len(payload)
                        except BlockingIOError:
                            continue
                        if offset >= len(payload):
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                        continue
                    try:
                        chunk = os.read(key.fd, 8192)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    remaining = output_bytes - sum(len(value) for value in buffers.values())
                    buffers[key.data].extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        interrupted = "output_limit"
                        break
                if interrupted:
                    break
            while not interrupted and process.poll() is None:
                if time.monotonic() - started >= seconds:
                    interrupted = "timeout"
                elif keep_running is not None and not keep_running():
                    interrupted = "task_not_running"
                else:
                    time.sleep(0.01)
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=5)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()
    return ProcessResult(process.returncode, bytes(buffers["stdout"]), bytes(buffers["stderr"]), interrupted)


class DockerPythonExecutor:
    def __init__(self, workflow, files, *, docker_host, image, limits=SandboxLimits(), docker_binary=None):
        if os.name != "posix" or files.workflow is not workflow or not isinstance(limits, SandboxLimits):
            raise SandboxError("Executor requires POSIX and the same controlled-file workflow")
        try:
            local_socket = (isinstance(docker_host, str) and docker_host.startswith("unix:///")
                            and "\0" not in docker_host and stat.S_ISSOCK(os.stat(docker_host[7:]).st_mode))
        except OSError:
            local_socket = False
        if not local_socket:
            raise SandboxError("Select an explicit local Docker Unix socket")
        if not isinstance(image, str) or re.fullmatch(
            r"(?:docker.io/library/)?python(?::[A-Za-z0-9._-]+)?@sha256:[0-9a-f]{64}", image,
        ) is None:
            raise SandboxError("Pin an official Python image by content digest; no automatic pulls")
        binary = docker_binary or shutil.which("docker")
        if not binary or not Path(binary).is_absolute() or not Path(binary).is_file():
            raise SandboxError("Docker CLI is unavailable; no host-code fallback")
        self.workflow, self.files = workflow, files
        self.docker_host, self.image, self.limits = docker_host, image, limits
        self._config = tempfile.TemporaryDirectory(prefix="agent-lab-docker-")
        self._prefix = [binary, "--config", self._config.name, "--host", docker_host]
        self.workflow.db.executescript("""
            CREATE TABLE IF NOT EXISTS sandbox_backend (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1), endpoint_digest TEXT NOT NULL, engine_id TEXT
            );
            CREATE TABLE IF NOT EXISTS sandbox_runs (
                id TEXT PRIMARY KEY, task TEXT NOT NULL REFERENCES tasks(id), actor TEXT NOT NULL,
                container_name TEXT NOT NULL, config TEXT NOT NULL, inputs TEXT NOT NULL,
                status TEXT NOT NULL, started REAL NOT NULL, ended REAL, result TEXT, exported TEXT
            );
        """)
        with self.workflow._transaction():
            digest = hashlib.sha256(docker_host.encode()).hexdigest()
            bound = self.workflow.db.execute("SELECT * FROM sandbox_backend WHERE singleton=1").fetchone()
            if bound and bound["endpoint_digest"] != digest:
                self.close()
                raise SandboxError("Workflow is already bound to another Docker endpoint")
            self.workflow.db.execute("INSERT OR IGNORE INTO sandbox_backend VALUES(1,?,NULL)", (digest,))

    def close(self):
        self._config.cleanup()

    def configuration(self):
        # No socket paths, user credentials, or Docker config enter model context.
        return {"backend": "docker_python_v1", "image": self.image, "limits": asdict(self.limits),
                "network": "none", "host_mounts": False, "payload_uid": 65534, "supervisor_uid": 65533}

    def _invoke(self, arguments, **kwargs):
        return bounded_process(self._prefix + arguments, **kwargs)

    def _checked(self, arguments, **kwargs):
        result = self._invoke(arguments, **kwargs)
        if result.returncode != 0 or result.interrupted:
            raise SandboxError("Docker operation failed or exceeded its limit; no host-code fallback")
        return result.stdout

    def _create_arguments(self, name, run_id):
        limits = self.limits
        return ["create", "--name", name, "--label", "agent_lab.run=" + run_id,
                "--pull", "never", "--network", "none", "--read-only", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "--pids-limit", str(limits.pids),
                "--memory", f"{limits.memory_mib}m", "--memory-swap", f"{limits.memory_mib}m",
                "--cpus", "0.5", "--user", "65533:65533", "--init", "--ipc", "private",
                "--log-driver", "none", "--stop-timeout", "0", "--shm-size", "8m",
                "--ulimit", "nofile=64:64", "--ulimit", "fsize=1048576:1048576", "--ulimit", "core=0:0",
                "--tmpfs", "/work:" + _WORK_OPTIONS,
                "--tmpfs", "/tmp:" + _TMP_OPTIONS,
                "--workdir", "/work", "--entrypoint", "/usr/local/bin/python3", self.image,
                "-I", "-u", "-c", f"import time; time.sleep({limits.seconds + 5})"]

    def _validate_engine(self):
        info = strict_json(self._checked(["info", "--format", "{{json .}}"], output_bytes=131072))
        if (info.get("OSType") != "linux" or not all(info.get(key) is True for key in
                ("MemoryLimit", "SwapLimit", "CpuCfsQuota", "PidsLimit"))
                or "name=seccomp,profile=builtin" not in info.get("SecurityOptions", [])):
            raise SandboxError("Docker engine lacks required Linux resource limits or default seccomp")
        with self.workflow._transaction():
            bound = self.workflow.db.execute("SELECT engine_id FROM sandbox_backend WHERE singleton=1").fetchone()[0]
            if not isinstance(info.get("ID"), str) or not info["ID"] or (bound and bound != info["ID"]):
                raise SandboxError("Docker engine identity changed; reconcile existing runs explicitly")
            self.workflow.db.execute("UPDATE sandbox_backend SET engine_id=? WHERE singleton=1", (info["ID"],))
        return {"server_version": info.get("ServerVersion"), "kernel": info.get("KernelVersion"),
                "architecture": info.get("Architecture"), "security_options": info["SecurityOptions"]}

    def _validate_container(self, name, run_id):
        items = strict_json(self._checked(["container", "inspect", name]))
        if not isinstance(items, list) or len(items) != 1:
            raise SandboxError("Unexpected container inspection")
        item = items[0]
        host, config = item["HostConfig"], item["Config"]
        expected_tmpfs = {"/work", "/tmp"}
        valid = (config["Labels"].get("agent_lab.run") == run_id and config["Image"] == self.image
                 and config["User"] == "65533:65533" and config["WorkingDir"] == "/work"
                 and config["Entrypoint"] == ["/usr/local/bin/python3"]
                 and host["NetworkMode"] == "none" and host["ReadonlyRootfs"] is True
                 and host["Privileged"] is False and host["Init"] is True
                 and host["CapDrop"] == ["ALL"] and not host.get("CapAdd")
                 and host["SecurityOpt"] in (["no-new-privileges"], ["no-new-privileges=true"])
                 and host["Memory"] == host["MemorySwap"] == self.limits.memory_mib * 1024 * 1024
                 and host["NanoCpus"] == 500000000 and host["PidsLimit"] == self.limits.pids
                 and host["IpcMode"] == "private" and host.get("PidMode", "") == ""
                 and host.get("UsernsMode", "") != "host" and host["LogConfig"]["Type"] == "none"
                 and set(host["Tmpfs"]) == expected_tmpfs and not host.get("Binds")
                 and set(host["Tmpfs"]["/work"].split(",")) == set(_WORK_OPTIONS.split(","))
                 and set(host["Tmpfs"]["/tmp"].split(",")) == set(_TMP_OPTIONS.split(","))
                 and not host.get("Devices") and not host.get("VolumesFrom")
                 and all(mount["Type"] == "tmpfs" and mount["Destination"] in expected_tmpfs
                         for mount in item.get("Mounts", [])))
        if not valid:
            raise SandboxError("Container configuration does not match the required isolation policy")
        return {"image_id": item["Image"], "container_id": item["Id"]}

    def _cleanup(self, run_id):
        # Only containers with this persisted run label, never a wildcard/prune.
        try:
            engine = self._checked(["info", "--format", "{{.ID}}"]).decode().strip()
            bound = self.workflow.db.execute("SELECT engine_id FROM sandbox_backend WHERE singleton=1").fetchone()[0]
            if not bound or engine != bound:
                return False
            raw = self._checked(["container", "ls", "--all", "--quiet", "--no-trunc", "--filter", "label=agent_lab.run=" + run_id])
            identifiers = raw.decode("ascii").split()
            if any(re.fullmatch("[0-9a-f]{64}", identifier) is None for identifier in identifiers):
                return False
            for identifier in identifiers:
                self._checked(["container", "rm", "--force", identifier])
            remaining = self._checked(["container", "ls", "--all", "--quiet", "--filter", "label=agent_lab.run=" + run_id])
            return not remaining.strip()
        except (SandboxError, OSError, ValueError, UnicodeError):
            return False

    def reconcile_cleanup(self, run_id, actor):
        row = self.workflow.db.execute("SELECT * FROM sandbox_runs WHERE id=?", (run_id,)).fetchone()
        if row is None or row["actor"] != actor:
            raise SandboxError("Cleanup belongs to another actor or unknown run")
        self.workflow._task(row["task"], actor, assigned=True)
        if self.workflow.db.execute("SELECT engine_id FROM sandbox_backend WHERE singleton=1").fetchone()[0] is None:
            self._validate_engine()
        if not self._cleanup(run_id):
            raise SandboxError("Container cleanup remains unconfirmed; do not start another run")
        with self.workflow._transaction():
            result = json.loads(row["result"]) if row["result"] else {}
            result["cleanup_confirmed"] = True
            self.workflow.db.execute("UPDATE sandbox_runs SET status='reconciled',ended=?,result=? WHERE id=?",
                                     (self.workflow.clock(), json.dumps(result), run_id))
        return {"cleanup_confirmed": True, "effects_replayed": False}

    def recover_exports(self, run_id, actor):
        """Trusted recovery only: import durable text snapshots without code replay."""
        row = self.workflow.db.execute("SELECT * FROM sandbox_runs WHERE id=?", (run_id,)).fetchone()
        if row is None or row["actor"] != actor or row["status"] not in {"cleaned", "reconciled"} or not row["exported"]:
            raise SandboxError("No cleaned export checkpoint belongs to this actor")
        self.workflow._task(row["task"], actor, assigned=True)
        try:
            result, exported = strict_json(row["result"]), strict_json(row["exported"])
            valid = (isinstance(result, dict) and isinstance(exported, dict) and bool(exported)
                     and result.get("cleanup_confirmed") is True
                     and result["execution"]["exit_code"] == 0 and result["execution"]["interrupted"] is None
                     and set(exported) == set(result["export_sha256"])
                     and all(isinstance(text, str) and len(text.encode()) <= 65536
                             and hashlib.sha256(text.encode()).hexdigest() == result["export_sha256"][path]
                             for path, text in exported.items()))
        except (ValueError, TypeError, KeyError, UnicodeError):
            valid = False
        if not valid:
            raise SandboxError("Export checkpoint integrity mismatch")
        receipts = []
        for path, text in exported.items():
            try:
                current = self.files.read_text(row["task"], actor, path)
            except WorkflowError:
                # Creation still refuses existing/symlink paths; no overwrite fallback.
                current = self.files.create_text(row["task"], actor, path, text)
            if current["sha256"] != result["export_sha256"][path]:
                raise SandboxError("An imported artifact has changed; reconcile before recovery")
            receipts.append({key: current[key] for key in ("path", "sha256", "bytes")})
        return {"artifacts": receipts, "effects_replayed": False}

    def run_python(self, task, actor, *, entrypoint, input_files, arguments, outputs):
        self.validate_job(entrypoint, input_files, arguments, outputs)
        snapshots = {}
        for path, digest in input_files.items():
            file = self.files.read_text(task, actor, path)
            if file["sha256"] != digest:
                raise SandboxError("Input file version changed; no execution started")
            snapshots[path] = file["content"]
        payload = json.dumps({"entrypoint": entrypoint, "arguments": arguments, "files": snapshots}).encode()
        if len(payload) > 2 * 1024 * 1024:
            raise SandboxError("Execution input exceeds the byte budget")
        identifier = uuid4().hex
        name = "agent-lab-" + identifier
        with self.workflow._transaction():
            row = self.workflow._task(task, actor, assigned=True)
            if row["state"] != "running":
                raise SandboxError("Only assigned running tasks may execute code")
            if self.workflow.db.execute("SELECT 1 FROM sandbox_runs WHERE status IN ('reserved','active','cleanup_failed')").fetchone():
                raise SandboxError("A previous sandbox is active or unreconciled; inspect/clean it first")
            self.workflow.db.execute("INSERT INTO sandbox_runs VALUES(?,?,?,?,?,?,'reserved',?,NULL,NULL,NULL)", (
                identifier, task, actor, name, json.dumps(self.configuration()), json.dumps(input_files), self.workflow.clock(),
            ))
            self.workflow._event(task, actor, "sandbox_reserved", {"run_id": identifier, "inputs": input_files})
        deadline = time.monotonic() + self.limits.seconds

        def active():
            return self.workflow.task(task, actor)["state"] == "running"

        def remaining():
            value = deadline - time.monotonic()
            if value <= 0:
                raise SandboxError("Sandbox setup/export exceeded its duration budget")
            return value

        result = {"run_id": identifier, "process_sandbox": False, "configuration": self.configuration(),
                  "execution": None, "artifacts": [], "cleanup_confirmed": False}
        exported = None
        creation_requested = False
        try:
            result["phase"] = "engine_validation"
            result["engine"] = self._validate_engine()
            result["phase"] = "container_creation"
            creation_requested = True
            self._checked(self._create_arguments(name, identifier), seconds=min(5, remaining()))
            result["phase"] = "policy_validation"
            result["identity"] = self._validate_container(name, identifier)
            if not active():
                raise SandboxError("Task paused or terminated before container start")
            self._checked(["container", "start", name], seconds=min(5, remaining()))
            result["process_sandbox"] = True
            result["phase"] = "code_execution"
            with self.workflow._transaction():
                self.workflow.db.execute("UPDATE sandbox_runs SET status='active' WHERE id=?", (identifier,))
            execution = self._invoke(["container", "exec", "--interactive", "--user", "65534:65534", name,
                                      "/usr/local/bin/python3", "-I", "-u", "-c", _BOOTSTRAP],
                                     payload=payload, seconds=remaining(), output_bytes=self.limits.output_bytes,
                                     keep_running=active)
            result["execution"] = {"exit_code": execution.returncode, "interrupted": execution.interrupted,
                                   "stdout": execution.stdout.decode("utf-8", errors="replace"),
                                   "stderr": execution.stderr.decode("utf-8", errors="replace"),
                                   "stdout_sha256": hashlib.sha256(execution.stdout).hexdigest(),
                                   "stderr_sha256": hashlib.sha256(execution.stderr).hexdigest()}
            if execution.returncode == 0 and not execution.interrupted and outputs and active():
                result["phase"] = "artifact_export"
                raw = self._checked(["container", "exec", "--user", "65533:65533", name,
                                     "/usr/local/bin/python3", "-I", "-c", _EXPORT, json.dumps(outputs)],
                                    seconds=min(5, remaining()), output_bytes=2 * 1024 * 1024,
                                    keep_running=active)
                exported = strict_json(raw)
                if (not isinstance(exported, dict) or set(exported) != set(outputs)
                        or any(not isinstance(text, str) or len(text.encode("utf-8")) > 65536 for text in exported.values())):
                    raise SandboxError("Invalid exported artifact data")
                result["export_sha256"] = {path: hashlib.sha256(text.encode()).hexdigest() for path, text in exported.items()}
        except (SandboxError, ValueError, OSError, KeyError, TypeError) as error:
            result["error"] = str(error) if isinstance(error, SandboxError) else "Invalid runtime response or IO failure"
        finally:
            result["cleanup_confirmed"] = not creation_requested or self._cleanup(identifier)
            result["elapsed_seconds"] = max(0, self.limits.seconds - (deadline - time.monotonic()))
            # Interrupted controllers remain reserved/active until explicit cleanup.
            with self.workflow._transaction():
                self.workflow.db.execute("UPDATE sandbox_runs SET status=?,ended=?,result=?,exported=? WHERE id=?", (
                    "cleaned" if result["cleanup_confirmed"] else "cleanup_failed",
                    self.workflow.clock(), json.dumps(result), json.dumps(exported) if exported is not None else None, identifier,
                ))
                self.workflow._event(task, actor, "sandbox_stopped", {
                    "run_id": identifier, "cleanup_confirmed": result["cleanup_confirmed"],
                })
        if not result["cleanup_confirmed"]:
            raise SandboxError("Sandbox cleanup unconfirmed; execution blocked until trusted reconciliation")
        if exported is not None and "error" not in result and active():
            result["phase"] = "artifact_import"
            try:
                for path, text in exported.items():
                    result["artifacts"].append(self.files.create_text(task, actor, path, text))
            except (WorkflowError, OSError):
                result["error"] = "Artifact import failed; inspect partial receipts before retry"
        if "error" not in result:
            result["phase"] = "finished"
        with self.workflow._transaction():
            self.workflow.db.execute("UPDATE sandbox_runs SET result=? WHERE id=?", (json.dumps(result), identifier))
        return result

    @staticmethod
    def validate_job(entrypoint, input_files, arguments, outputs):
        if (not isinstance(input_files, dict) or not 1 <= len(input_files) <= 20
                or not isinstance(entrypoint, str) or entrypoint not in input_files
                or not isinstance(arguments, list) or len(arguments) > 16
                or any(not isinstance(arg, str) or len(arg) > 1024 or "\0" in arg for arg in arguments)
                or not isinstance(outputs, list) or len(outputs) > 8
                or any(not isinstance(path, str) for path in outputs)):
            raise SandboxError("Invalid bounded Python execution job")
        if len(set(outputs)) != len(outputs) or set(outputs) & input_files.keys():
            raise SandboxError("Outputs must be distinct new paths, separate from input snapshots")
        for path in [*input_files, *outputs]:
            _parts(path)
            if len(path) > 512:
                raise SandboxError("Execution path is too long")
            try:
                path.encode("utf-8")
            except UnicodeError:
                raise SandboxError("Execution paths must be UTF-8") from None
        for argument in arguments:
            try:
                argument.encode("utf-8")
            except UnicodeError:
                raise SandboxError("Execution arguments must be UTF-8") from None
        for digest in input_files.values():
            if not isinstance(digest, str) or re.fullmatch("[0-9a-f]{64}", digest) is None:
                raise SandboxError("Every input needs an exact content digest")
