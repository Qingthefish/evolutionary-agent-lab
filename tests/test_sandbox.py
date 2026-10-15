import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from agent_lab import Workflow, WorkflowError
from agent_lab.files import FileTools
from agent_lab.gateway import ToolGateway, ToolRequestError
from agent_lab.sandbox import DockerPythonExecutor, ProcessResult, SandboxError, SandboxLimits, bounded_process


IMAGE = "python:3.12-slim@sha256:" + "a" * 64


class FakeDocker:
    """Explicit unit-test simulation, never used by CLI demos or live runs."""

    def __init__(self):
        self.commands = []
        self.created = False
        self.run_id = None
        self.tamper = None
        self.cleanup_fails = False
        self.engine_id = "test-engine"
        self.execution = ProcessResult(0, b"42\n", b"")
        self.exports = {"result.txt": "42\n"}

    def __call__(self, args, **kwargs):
        self.commands.append((args, kwargs))
        output = b""
        if args[0] == "info":
            if args[-1] == "{{.ID}}":
                output = self.engine_id.encode() + b"\n"
            else:
                output = json.dumps({"ID": self.engine_id, "OSType": "linux", "MemoryLimit": True,
                    "SwapLimit": True, "CpuCfsQuota": True, "PidsLimit": True,
                    "SecurityOptions": ["name=seccomp,profile=builtin"]}).encode()
        elif args[0] == "create":
            self.created = True
            self.run_id = args[args.index("--label") + 1].split("=", 1)[1]
            self.image = args[args.index("--entrypoint") + 2]
            self.memory = int(args[args.index("--memory") + 1][:-1]) * 1024 * 1024
            self.pids = int(args[args.index("--pids-limit") + 1])
            self.tmpfs = dict(args[index + 1].split(":", 1) for index, value in enumerate(args) if value == "--tmpfs")
            output = b"b" * 64 + b"\n"
        elif args[:2] == ["container", "inspect"]:
            inspection = {"Id": "b" * 64, "Image": "sha256:" + "a" * 64,
                "Config": {"Image": self.image, "User": "65533:65533", "WorkingDir": "/work",
                    "Entrypoint": ["/usr/local/bin/python3"], "Labels": {"agent_lab.run": self.run_id}},
                "HostConfig": {"NetworkMode": "none", "ReadonlyRootfs": True, "Privileged": False,
                    "Init": True, "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges"],
                    "Memory": self.memory, "MemorySwap": self.memory, "NanoCpus": 500000000,
                    "PidsLimit": self.pids, "IpcMode": "private", "LogConfig": {"Type": "none"}, "Tmpfs": self.tmpfs},
                "Mounts": []}
            if self.tamper:
                self.tamper(inspection)
            output = json.dumps([inspection]).encode()
        elif args[:2] == ["container", "exec"]:
            if "65534:65534" in args:
                return self.execution
            output = json.dumps(self.exports).encode()
        elif args[:2] == ["container", "ls"]:
            output = b"b" * 64 + b"\n" if self.created else b""
        elif args[:2] == ["container", "rm"]:
            if self.cleanup_fails:
                return ProcessResult(1, b"", b"simulated cleanup failure")
            self.created = False
        elif args[:2] != ["container", "start"]:
            raise AssertionError("Unexpected fake command: " + repr(args))
        return ProcessResult(0, output, b"")


class SandboxTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.socket_path = self.root / "daemon.sock"
        # Unit tests simulate a daemon endpoint without binding a network socket.
        # Actual Unix-socket validation is exercised by opt-in integration tests.
        self.socket_path.touch()
        self.workflow = Workflow(self.root / "state.sqlite3")
        for actor, kind in [("user", "human"), ("coder", "agent"), ("reviewer", "agent")]:
            self.workflow.register_actor(actor, kind)
        self.chat = self.workflow.create_chat("group", ["user", "coder", "reviewer"])
        self.task = self.workflow.create_task(self.chat, "user", "coder", "Run a Python task")
        self.workflow.start_task(self.task, "coder")
        self.files = FileTools(self.workflow, self.root / "files")
        with patch("agent_lab.sandbox.stat.S_ISSOCK", return_value=True):
            self.executor = DockerPythonExecutor(self.workflow, self.files,
                docker_host="unix://" + str(self.socket_path), image=IMAGE, docker_binary=sys.executable)
        self.fake = FakeDocker()
        self.mock = patch.object(self.executor, "_invoke", side_effect=self.fake)
        self.mock.start()
        self.receipt = self.files.create_text(self.task, "coder", "main.py", "print(42)\n")
        self.job = {"entrypoint": "main.py", "input_files": {"main.py": self.receipt["sha256"]},
                    "arguments": [], "outputs": ["result.txt"]}

    def tearDown(self):
        self.mock.stop()
        self.executor.close()
        self.files.close()
        self.workflow.close()
        self.directory.cleanup()

    def run_job(self, **changes):
        return self.executor.run_python(self.task, "coder", **(self.job | changes))

    def test_explicit_endpoint_digest_and_backend_are_required(self):
        for endpoint, image in [("tcp://localhost:2375", IMAGE), ("unix:///missing.sock", IMAGE),
                                ("unix://" + str(self.socket_path), "python:latest")]:
            with self.assertRaises(SandboxError):
                DockerPythonExecutor(self.workflow, self.files, docker_host=endpoint, image=image, docker_binary=sys.executable)
        with self.assertRaises(ToolRequestError):
            ToolGateway(self.workflow, self.files, self.task, "coder", human="user", allowed=["run_python"])
        with patch("agent_lab.sandbox.stat.S_ISSOCK", return_value=True), self.assertRaisesRegex(SandboxError, "Pin an official"):
            DockerPythonExecutor(self.workflow, self.files, docker_host="unix://" + str(self.socket_path),
                                  image="python:latest", docker_binary=sys.executable)

    def test_exact_snapshot_execution_exports_new_text_without_completing_task(self):
        result = self.run_job(arguments=["--privileged", "$(touch must-not-exist)"])
        self.assertEqual(result["execution"]["exit_code"], 0)
        self.assertTrue(result["cleanup_confirmed"])
        self.assertEqual(self.files.read_text(self.task, "coder", "result.txt")["content"], "42\n")
        self.assertEqual(self.workflow.task(self.task, "user")["state"], "running")
        execution = next((args, options) for args, options in self.fake.commands if "65534:65534" in args)
        payload = json.loads(execution[1]["payload"])
        self.assertEqual(payload["arguments"], ["--privileged", "$(touch must-not-exist)"])
        self.assertNotIn("--privileged", execution[0])
        self.assertEqual(payload["files"], {"main.py": "print(42)\n"})

    def test_invalid_paths_digests_and_other_actor_cannot_start_execution(self):
        for changes in [{"entrypoint": "../main.py"}, {"input_files": {"main.py": "0" * 64}},
                        {"outputs": ["../outside.txt"]}, {"outputs": ["main.py"]},
                        {"arguments": ["bad\0argument"]}, {"outputs": ["x", "x"]}]:
            with self.subTest(changes=changes), self.assertRaises(WorkflowError):
                self.run_job(**changes)
        with self.assertRaises(WorkflowError):
            self.executor.run_python(self.task, "reviewer", **self.job)
        self.assertEqual(self.fake.commands, [])

    def test_policy_tampering_prevents_container_start_and_code_execution(self):
        mutations = [lambda item: item["HostConfig"].update(NetworkMode="host"),
                     lambda item: item["HostConfig"].update(Privileged=True),
                     lambda item: item["HostConfig"].update(Binds=["/:/host"]),
                     lambda item: item["HostConfig"].update(Memory=0),
                     lambda item: item["HostConfig"].update(CapAdd=["SYS_ADMIN"]),
                     lambda item: item["HostConfig"].update(SecurityOpt=["seccomp=unconfined"]),
                     lambda item: item["Config"].update(User="0:0"),
                     lambda item: item["HostConfig"]["Tmpfs"].update({"/work": "rw,exec"})]
        for mutate in mutations:
            self.fake.commands.clear()
            self.fake.tamper = mutate
            result = self.run_job()
            self.assertIn("isolation policy", result["error"])
            self.assertFalse(result["process_sandbox"])
            self.assertTrue(result["cleanup_confirmed"])
            self.assertFalse(any(args[:2] in (["container", "start"], ["container", "exec"]) for args, opts in self.fake.commands))

    def test_nonzero_and_interrupted_execution_do_not_export_or_claim_success(self):
        for execution in [ProcessResult(1, b"", b"Actual check failed"), ProcessResult(-9, b"partial", b"", "timeout"),
                          ProcessResult(-9, b"bounded", b"", "output_limit")]:
            self.fake.execution = execution
            result = self.run_job()
            self.assertEqual(result["execution"]["exit_code"], execution.returncode)
            self.assertEqual(result["artifacts"], [])
            self.assertTrue(result["cleanup_confirmed"])

    def test_invalid_export_cannot_create_unrequested_files(self):
        self.fake.exports = {"../escape.txt": "bad"}
        result = self.run_job()
        self.assertIn("Invalid exported", result["error"])
        self.assertFalse((self.root / "escape.txt").exists())
        self.assertEqual(result["artifacts"], [])

    def test_cleanup_failure_blocks_further_execution_until_trusted_reconciliation(self):
        self.fake.cleanup_fails = True
        with self.assertRaisesRegex(SandboxError, "cleanup unconfirmed"):
            self.run_job()
        row = self.workflow.db.execute("SELECT * FROM sandbox_runs").fetchone()
        self.assertEqual(row["status"], "cleanup_failed")
        with self.assertRaisesRegex(SandboxError, "unreconciled"):
            self.run_job()
        with self.assertRaises(SandboxError):
            self.executor.reconcile_cleanup(row["id"], "reviewer")
        self.fake.cleanup_fails = False
        self.assertFalse(self.executor.reconcile_cleanup(row["id"], "coder")["effects_replayed"])
        recovered = self.executor.recover_exports(row["id"], "coder")
        self.assertFalse(recovered["effects_replayed"])
        self.assertEqual(len(recovered["artifacts"]), 1)

    def test_export_checkpoint_recovers_after_import_interruption_without_code_replay(self):
        with patch.object(self.files, "create_text", side_effect=OSError("Simulated import failure")):
            result = self.run_job()
        self.assertIn("import failed", result["error"])
        execution_count = sum("65534:65534" in args for args, opts in self.fake.commands)
        first = self.executor.recover_exports(result["run_id"], "coder")
        second = self.executor.recover_exports(result["run_id"], "coder")
        self.assertEqual(first, second)
        self.assertEqual(execution_count, sum("65534:65534" in args for args, opts in self.fake.commands))
        current = self.files.read_text(self.task, "coder", "result.txt")
        self.files.update_text(self.task, "coder", "result.txt", "changed", expected_sha256=current["sha256"])
        with self.assertRaisesRegex(SandboxError, "changed"):
            self.executor.recover_exports(result["run_id"], "coder")

    def test_changed_engine_cannot_falsely_confirm_old_cleanup(self):
        self.fake.cleanup_fails = True
        with self.assertRaises(SandboxError):
            self.run_job()
        row = self.workflow.db.execute("SELECT * FROM sandbox_runs").fetchone()
        self.fake.cleanup_fails = False
        self.fake.engine_id = "different-engine"
        with self.assertRaisesRegex(SandboxError, "unconfirmed"):
            self.executor.reconcile_cleanup(row["id"], "coder")
        self.assertTrue(self.fake.created)

    def test_corrupted_export_checkpoint_is_rejected_before_import(self):
        result = self.run_job()
        self.workflow.db.execute("UPDATE sandbox_runs SET exported=? WHERE id=?", (
            json.dumps({"result.txt": "corrupted text"}), result["run_id"],
        ))
        with self.assertRaisesRegex(SandboxError, "integrity mismatch"):
            self.executor.recover_exports(result["run_id"], "coder")
        self.assertEqual(self.files.read_text(self.task, "coder", "result.txt")["content"], "42\n")

    def test_model_cannot_override_runtime_policy_or_host_arguments(self):
        gateway = ToolGateway(self.workflow, self.files, self.task, "coder", human="user", allowed=["run_python"], executor=self.executor)
        for extras in [{"image": "other"}, {"privileged": True}, {"actor": "user"}, {"timeout": 999}]:
            proposal = {"id": "bad", "type": "function", "function": {
                "name": "run_python", "arguments": json.dumps(self.job | extras),
            }}
            with self.assertRaises(ToolRequestError):
                gateway.dispatch(proposal)
        for changes in [{"input_files": []}, {"outputs": ["../outside"]}, {"arguments": [False]}]:
            proposal = {"id": "bad", "type": "function", "function": {
                "name": "run_python", "arguments": json.dumps(self.job | changes),
            }}
            with self.assertRaises(ToolRequestError):
                gateway.validate_batch([proposal])
        self.assertEqual(self.fake.commands, [])

    def test_supervisor_bounds_output_and_time_of_trusted_host_test_helpers(self):
        # Fixed, trusted IO fixtures only. Generated/model code never uses this path.
        result = bounded_process([sys.executable, "-c", "print('x' * 1000000)"], output_bytes=1024)
        self.assertEqual(result.interrupted, "output_limit")
        self.assertLessEqual(len(result.stdout) + len(result.stderr), 1024)
        result = bounded_process([sys.executable, "-c", "import time; time.sleep(10)"], seconds=0.15)
        self.assertEqual(result.interrupted, "timeout")
        result = bounded_process([sys.executable, "-c", "import time; time.sleep(10)"],
                                 payload=b"x" * 1024 * 1024, seconds=0.15)
        self.assertEqual(result.interrupted, "timeout")


if __name__ == "__main__":
    unittest.main()
