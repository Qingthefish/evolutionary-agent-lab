"""Official budget view and specific missing-path errors (proposed 2026-11-18, pending owner merge).

Scripted replies and a simulated engine, plus one opt-in real-container check.
No model capability is claimed.
"""

import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from agent_lab import budget
from agent_lab.core import Workflow, WorkflowError
from agent_lab.deepseek import DeepSeekClient
from agent_lab.evaluation import official_live
from agent_lab.files import FileTools
from agent_lab.runner import Limits
from agent_lab.sandbox import DockerPythonExecutor, ProcessResult
from agent_lab.scheduler import MultiAgentScheduler, Role
import test_sandbox

HOST = os.environ.get("AGENT_LAB_DOCKER_HOST")
REAL_IMAGE = os.environ.get("AGENT_LAB_PYTHON_IMAGE")


def write(n):
    call = {"id": f"c{n}", "type": "function", "function": {
        "name": "create_text", "arguments": json.dumps({"path": f"part-{n}.txt", "content": "x"})}}
    return json.dumps({"id": "r", "model": "m", "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        "choices": [{"finish_reason": "tool_calls",
                     "message": {"role": "assistant", "content": None, "tool_calls": [call]}}]}).encode()


class BudgetView(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.workflow = Workflow(Path(directory.name) / "state.sqlite3")
        self.addCleanup(self.workflow.close)
        self.files = FileTools(self.workflow, Path(directory.name) / "files")
        self.addCleanup(self.files.close)
        self.workflow.register_actor("user", "human")
        self.workflow.register_actor("lead", "agent")
        self.root = self.workflow.create_task(self.workflow.create_chat("group", ["user", "lead"]), "user", "lead", "Write")

    def run_scheduler(self, budget_visible, attempts=8):
        sent = []

        def transport(payload):
            sent.append(json.loads(payload))
            return write(len(sent))

        scheduler = MultiAgentScheduler(self.workflow, self.files, self.root, human="user",
            roles={"lead": Role("Fixture role", ("create_text",), (), Limits(model_attempts=attempts))},
            clients={"lead": DeepSeekClient("synthetic", transport)}, mode="offline_fixture", constraints=[],
            acceptance_id="fixture-budget", verifier_factory=lambda task: None,
            limits=budget.TreeLimits(model_attempts=attempts), budget_visible=budget_visible)
        scheduler.run()
        return sent

    def test_official_runs_enable_the_budget_view(self):
        session = SimpleNamespace(scenario={"id": "newsroom", "roles": [{"id": "role", "prompt": "Fixture."}]},
                                  agents=("role",), human="requester", workflow=None, _root=lambda number: None)
        live = SimpleNamespace(role_limits=Limits(), tree_limits=budget.TreeLimits(), tool_calls=32, max_output_tokens=4096)
        with (patch.object(official_live, "live_clients", return_value={}),
              patch.object(official_live, "MultiAgentScheduler") as factory):
            official_live.make_scheduler(session, "root", None, live, SimpleNamespace(executor=None, retrieval=None))
        self.assertIs(factory.call_args.kwargs["budget_visible"], True)

    def test_visible_budget_counts_down_and_flags_the_last_requests_without_a_new_prompt(self):
        sent = self.run_scheduler(True)
        self.assertEqual(len(sent), 8)
        views = [json.loads(request["messages"][1]["content"])["execution_budget"] for request in sent]
        self.assertEqual([view["shared"]["model_attempts_left_after_current"] for view in views], list(range(7, -1, -1)))
        flagged = [view["shared"].get("low_shared_budget", False) for view in views]
        self.assertEqual(flagged, [False] * 3 + [True] * 5)  # Flagged at max(4, 8 // 4) or fewer left.
        self.assertIn("Prefer handing over", views[-1]["shared"]["instruction"])
        hidden_root = self.workflow.create_task(self.workflow.create_chat("group", ["user", "lead"]), "user", "lead", "Write")
        self.root = hidden_root
        hidden = self.run_scheduler(False)
        self.assertNotIn("execution_budget", json.loads(hidden[0]["messages"][1]["content"]))
        self.assertEqual(sent[0]["messages"][0], hidden[0]["messages"][0])  # Same system prompt.

    def test_budget_visibility_must_be_explicit(self):
        with self.assertRaises(WorkflowError):
            MultiAgentScheduler(self.workflow, self.files, self.root, human="user",
                roles={"lead": Role("Fixture role", ("create_text",))},
                clients={"lead": DeepSeekClient("synthetic", lambda payload: b"{}")}, mode="offline_fixture",
                constraints=[], acceptance_id="fixture-budget", verifier_factory=lambda task: None, budget_visible=1)


class MissingPathErrors(unittest.TestCase):
    # Reuse the simulated-engine fixture without re-running its own tests here.
    setUp, tearDown, run_job = (test_sandbox.SandboxTests.setUp, test_sandbox.SandboxTests.tearDown,
                                test_sandbox.SandboxTests.run_job)

    def test_missing_file_reads_name_the_problem(self):
        with self.assertRaisesRegex(WorkflowError, "No such file or directory"):
            self.files.read_text(self.task, "coder", "build/storage.py")
        with self.assertRaisesRegex(WorkflowError, "No such file or directory"):
            self.files.read_text(self.task, "coder", "absent.txt")

    def test_undeclared_write_names_the_missing_declared_output(self):
        original = self.fake.__call__

        def missing_export(args, **kwargs):
            if args[:2] == ["container", "exec"] and "65534:65534" not in args:
                return ProcessResult(3, b"", json.dumps({"missing_outputs": ["result.txt"]}).encode())
            return original(args, **kwargs)

        self.mock.stop()
        self.mock = patch.object(self.executor, "_invoke", side_effect=missing_export)
        self.mock.start()
        result = self.run_job()
        self.assertIn("Declared outputs were not produced under /work: result.txt", result["error"])
        self.assertEqual(result["artifacts"], [])
        with self.assertRaisesRegex(WorkflowError, "No such file"):
            self.files.read_text(self.task, "coder", "result.txt")

    def test_unrecognized_export_failure_keeps_the_generic_message(self):
        original = self.fake.__call__

        def odd_export(args, **kwargs):
            if args[:2] == ["container", "exec"] and "65534:65534" not in args:
                return ProcessResult(3, b"", json.dumps({"missing_outputs": ["not-declared.txt"]}).encode())
            return original(args, **kwargs)

        self.mock.stop()
        self.mock = patch.object(self.executor, "_invoke", side_effect=odd_export)
        self.mock.start()
        self.assertIn("Docker operation failed", self.run_job()["error"])


@unittest.skipUnless(HOST and REAL_IMAGE, "Set AGENT_LAB_DOCKER_HOST and AGENT_LAB_PYTHON_IMAGE for real-container checks")
class MissingDeclaredOutputRealContainer(unittest.TestCase):
    def test_program_that_writes_elsewhere_gets_a_named_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = Workflow(root / "state.sqlite3")
            files = FileTools(workflow, root / "files")
            executor = DockerPythonExecutor(workflow, files, docker_host=HOST, image=REAL_IMAGE)
            try:
                for actor, kind in (("user", "human"), ("coder", "agent")):
                    workflow.register_actor(actor, kind)
                task = workflow.create_task(workflow.create_chat("group", ["user", "coder"]), "user", "coder", "Patch")
                workflow.start_task(task, "coder")
                script = files.create_text(task, "coder", "patch.py",
                                           "open('storage.py', 'w').write('patched\\n')\nprint('patched OK')\n")
                result = executor.run_python(task, "coder", entrypoint="patch.py",
                                             input_files={"patch.py": script["sha256"]}, arguments=[],
                                             outputs=["build/storage.py"])
                self.assertEqual(result["execution"]["exit_code"], 0)
                self.assertIn("Declared outputs were not produced under /work: build/storage.py", result["error"])
                self.assertEqual((result["artifacts"], result["cleanup_confirmed"]), ([], True))
            finally:
                executor.close()
                files.close()
                workflow.close()


if __name__ == "__main__":
    unittest.main()
