"""Opt-in actual-container checks. Never substitute a fake engine or host Python."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from uuid import uuid4

from agent_lab import Workflow, WorkflowError
from agent_lab.files import FileTools
from agent_lab.sandbox import DockerPythonExecutor, SandboxLimits


HOST = os.environ.get("AGENT_LAB_DOCKER_HOST")
IMAGE = os.environ.get("AGENT_LAB_PYTHON_IMAGE")


@unittest.skipUnless(HOST and IMAGE, "Set AGENT_LAB_DOCKER_HOST and a digest-pinned AGENT_LAB_PYTHON_IMAGE for real-container checks")
class DockerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.database = self.root / "workflow.sqlite3"
        self.workflow = Workflow(self.database)
        for actor, kind in [("user", "human"), ("coder", "agent"), ("reviewer", "agent")]:
            self.workflow.register_actor(actor, kind)
        self.chat = self.workflow.create_chat("group", ["user", "coder", "reviewer"])
        self.task = self.new_task("coder")
        self.files = FileTools(self.workflow, self.root / "files")
        self.executor = DockerPythonExecutor(self.workflow, self.files, docker_host=HOST, image=IMAGE)

    def tearDown(self):
        self.executor.close()
        self.files.close()
        self.workflow.close()
        self.directory.cleanup()

    def new_task(self, actor):
        task = self.workflow.create_task(self.chat, "user", actor, "Actual-container integration fixture")
        self.workflow.start_task(task, actor)
        return task

    def run_code(self, code, *, outputs=(), extra_files=None, task=None, actor="coder", executor=None):
        task = task or self.task
        inputs = {}
        for path, text in {"main.py": code, **(extra_files or {})}.items():
            inputs[path] = self.files.create_text(task, actor, path, text)["sha256"]
        result = (executor or self.executor).run_python(task, actor, entrypoint="main.py", input_files=inputs,
                                                      arguments=[], outputs=list(outputs))
        self.assertTrue(result["cleanup_confirmed"], result)
        return result

    def test_actual_multi_file_tests_and_export_require_independent_acceptance(self):
        result = self.run_code(
            "import unittest\nfrom pathlib import Path\nfrom solution import solve\n"
            "class Checks(unittest.TestCase):\n def test_values(self):\n  self.assertEqual(solve([3, -1, 3]), [-1, 3])\n"
            "result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))\n"
            "if not result.wasSuccessful(): raise SystemExit(1)\n"
            "Path('result.txt').write_text('Checked actual execution\\n')\n",
            extra_files={"solution.py": "def solve(values):\n return sorted(set(values))\n"}, outputs=["result.txt"],
        )
        self.assertEqual(result["execution"]["exit_code"], 0, result)
        self.assertIsNone(result["execution"]["interrupted"])
        self.assertIn("OK", result["execution"]["stderr"])
        self.assertEqual(self.workflow.task(self.task, "user")["state"], "running")
        self.files.complete_from_text(self.task, "coder", {"result.txt": "Checked actual execution\n"})

    def test_bad_code_has_real_nonzero_exit_and_no_export(self):
        result = self.run_code("assert 1 == 2, 'independent fixture check failed'\n", outputs=["result.txt"])
        self.assertNotEqual(result["execution"]["exit_code"], 0)
        self.assertIn("AssertionError", result["execution"]["stderr"])
        self.assertEqual(result["artifacts"], [])
        self.assertEqual(self.workflow.task(self.task, "user")["state"], "running")

    def test_network_host_files_secrets_root_writes_and_supervisor_signals_are_blocked(self):
        canary = self.root / "host-only.txt"
        canary.write_text("synthetic host canary; no real private data")
        code = """import json, os, pathlib, signal, socket
blocked = {}
for label, path in [('host_file', __HOST_FILE__), ('workflow_db', __HOST_DB__), ('docker_socket', '/var/run/docker.sock')]:
    blocked[label] = not pathlib.Path(path).exists()
try:
    pathlib.Path('/etc/agent_lab_probe').write_text('blocked')
    blocked['root_write'] = False
except OSError:
    blocked['root_write'] = True
try:
    connection = socket.create_connection(('1.1.1.1', 80), timeout=0.2)
    connection.close()
    blocked['network'] = False
except OSError:
    blocked['network'] = True
try:
    os.kill(1, signal.SIGSTOP)
    blocked['supervisor_signal'] = False
except PermissionError:
    blocked['supervisor_signal'] = True
blocked['host_environment'] = 'AGENT_LAB_HOST_CANARY' not in os.environ
blocked['unprivileged_uid'] = os.getuid() == 65534
status = pathlib.Path('/proc/self/status').read_text()
blocked['no_capabilities'] = 'CapEff:\\t0000000000000000' in status
blocked['no_new_privileges'] = 'NoNewPrivs:\\t1' in status
blocked['seccomp'] = 'Seccomp:\\t2' in status
blocked['memory_cgroup'] = pathlib.Path('/sys/fs/cgroup/memory.max').read_text().strip() == '134217728'
blocked['pids_cgroup'] = pathlib.Path('/sys/fs/cgroup/pids.max').read_text().strip() == '32'
print(json.dumps(blocked))
assert all(blocked.values()), blocked
""".replace("__HOST_FILE__", repr(str(canary))).replace("__HOST_DB__", repr(str(self.database)))
        # Use a synthetic value, without reading or transmitting any real API key.
        previous = os.environ.get("AGENT_LAB_HOST_CANARY")
        os.environ["AGENT_LAB_HOST_CANARY"] = "must-stay-on-host"
        try:
            result = self.run_code(code)
        finally:
            if previous is None:
                os.environ.pop("AGENT_LAB_HOST_CANARY", None)
            else:
                os.environ["AGENT_LAB_HOST_CANARY"] = previous
        self.assertEqual(result["execution"]["exit_code"], 0, result)
        self.assertTrue(all(json.loads(result["execution"]["stdout"]).values()))

    def test_another_agents_workspace_is_not_visible_and_inputs_are_private(self):
        self.files.create_text(self.task, "coder", "private.txt", "synthetic coder-only data")
        private_path = self.root / "files"
        other = self.new_task("reviewer")
        result = self.run_code(
            "from pathlib import Path\n"
            "assert not Path('private.txt').exists()\n"
            f"assert not Path({str(private_path)!r}).exists()\n"
            "print('private workspaces remain separate')\n", task=other, actor="reviewer",
        )
        self.assertEqual(result["execution"]["exit_code"], 0, result)
        with self.assertRaises(WorkflowError):
            self.executor.run_python(self.task, "reviewer", entrypoint="private.txt", input_files={
                "private.txt": "0" * 64}, arguments=[], outputs=[])

    def test_timeout_kills_the_container_and_its_descendants(self):
        limited = DockerPythonExecutor(self.workflow, self.files, docker_host=HOST, image=IMAGE, limits=SandboxLimits(seconds=2))
        try:
            result = self.run_code(
                "import subprocess, sys, time\n"
                "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                "time.sleep(60)\n", executor=limited,
            )
        finally:
            limited.close()
        self.assertEqual(result["execution"]["interrupted"], "timeout", result)
        self.assertLess(result["elapsed_seconds"], 10)
        remaining = self.executor._checked(["container", "ls", "--all", "--quiet", "--filter", "label=agent_lab.run=" + result["run_id"]])
        self.assertEqual(remaining.strip(), b"")

    def test_output_flood_is_bounded_then_container_is_removed(self):
        result = self.run_code("import os\nwhile True: os.write(1, b'x' * 8192)\n")
        self.assertEqual(result["execution"]["interrupted"], "output_limit", result)
        self.assertLessEqual(len(result["execution"]["stdout"].encode()) + len(result["execution"]["stderr"].encode()), 65536)

    def test_memory_limit_terminates_oversized_allocation(self):
        result = self.run_code("data = bytearray(512 * 1024 * 1024)\nprint('unexpectedly allocated')\n")
        self.assertNotEqual(result["execution"]["exit_code"], 0, result)
        self.assertEqual(result["artifacts"], [])

    def test_process_limit_rejects_additional_children(self):
        result = self.run_code("""import errno, os, signal, time
children = []
limited = False
try:
    for index in range(80):
        try:
            child = os.fork()
        except OSError as error:
            limited = error.errno == errno.EAGAIN
            break
        if child == 0:
            time.sleep(30)
            os._exit(0)
        children.append(child)
finally:
    for child in children:
        os.kill(child, signal.SIGKILL)
    for child in children:
        os.waitpid(child, 0)
print(len(children), limited)
assert limited and len(children) < 80
""")
        self.assertEqual(result["execution"]["exit_code"], 0, result)
        self.assertIn("True", result["execution"]["stdout"])

    def test_symlink_fifo_and_binary_exports_are_rejected(self):
        for name, code in [
            ("symlink", "import os\nos.symlink('/etc/passwd', 'result.txt')\n"),
            ("fifo", "import os\nos.mkfifo('result.txt')\n"),
            ("binary", "from pathlib import Path\nPath('result.txt').write_bytes(b'\\xff')\n"),
        ]:
            task = self.new_task("coder")
            with self.subTest(kind=name):
                result = self.run_code(code, outputs=["result.txt"], task=task)
                self.assertEqual(result["execution"]["exit_code"], 0, result)
                self.assertIn("error", result)
                self.assertEqual(result["artifacts"], [])
                with self.assertRaises(WorkflowError):
                    self.files.read_text(task, "coder", "result.txt")

    def test_task_cancellation_stops_actual_execution(self):
        entered = threading.Event()

        def worker():
            workflow = Workflow(self.database)
            files = FileTools(workflow, self.root / "files")
            executor = DockerPythonExecutor(workflow, files, docker_host=HOST, image=IMAGE)
            original = executor._invoke

            def observed(arguments, **kwargs):
                if arguments[:2] == ["container", "exec"] and "65534:65534" in arguments:
                    entered.set()
                return original(arguments, **kwargs)
            executor._invoke = observed
            try:
                receipt = files.create_text(self.task, "coder", "main.py", "import time\ntime.sleep(60)\n")
                return executor.run_python(self.task, "coder", entrypoint="main.py",
                                           input_files={"main.py": receipt["sha256"]}, arguments=[], outputs=[])
            finally:
                executor.close()
                files.close()
                workflow.close()

        with ThreadPoolExecutor(max_workers=1) as pool:
            running = pool.submit(worker)
            self.assertTrue(entered.wait(timeout=5))
            time.sleep(0.15)
            self.workflow.finish_task(self.task, "coder", error="Trusted test cancellation")
            result = running.result(timeout=10)
        self.assertEqual(result["execution"]["interrupted"], "task_not_running", result)
        self.assertTrue(result["cleanup_confirmed"])

    def test_independent_watchdog_stops_container_without_host_execution_loop(self):
        limited = DockerPythonExecutor(self.workflow, self.files, docker_host=HOST, image=IMAGE, limits=SandboxLimits(seconds=2))
        run_id = uuid4().hex
        name = "agent-lab-" + run_id
        try:
            limited._validate_engine()
            limited._checked(limited._create_arguments(name, run_id))
            limited._validate_container(name, run_id)
            limited._checked(["container", "start", name])
            limited._checked(["container", "exec", "--detach", "--user", "65534:65534", name,
                              "/usr/local/bin/python3", "-c", "import time; time.sleep(60)"])
            deadline = time.monotonic() + 10
            running = True
            while running and time.monotonic() < deadline:
                running = json.loads(limited._checked(["container", "inspect", "--format", "{{json .State.Running}}", name]))
                if running:
                    time.sleep(0.2)
            self.assertFalse(running, "Independent watchdog did not terminate the container")
        finally:
            self.assertTrue(limited._cleanup(run_id))
            limited.close()


if __name__ == "__main__":
    unittest.main()
