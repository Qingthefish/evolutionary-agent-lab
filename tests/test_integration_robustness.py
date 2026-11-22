"""Task-agnostic integration aids (synthetic; no provider): list_files, layout-keeping accepts, delegation notes.

Live Software runs (2026-11-22) failed at the parent's integration step, not in the children's work:
files accepted at the wrong path, a child delegated without the files it needed, and a lead that
could not see what it held.
"""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from agent_lab import Workflow
from agent_lab.files import FileToolError, FileTools
from agent_lab.gateway import ToolGateway


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


class IntegrationRobustnessTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.workflow = Workflow(root / "state.sqlite3")
        self.addCleanup(self.workflow.close)
        for actor, kind in (("user", "human"), ("lead", "agent"), ("dev", "agent")):
            self.workflow.register_actor(actor, kind)
        self.chat = self.workflow.create_chat("group", ["user", "lead", "dev"])
        self.lead = self.workflow.create_task(self.chat, "user", "lead", "Integrate the package")
        self.workflow.start_task(self.lead, "lead")
        self.dev = self.workflow.create_task(self.chat, "lead", "dev", "Build the package", parent=self.lead)
        self.workflow.start_task(self.dev, "dev")
        self.files = FileTools(self.workflow, root / "files")
        self.addCleanup(self.files.close)

    def gateway(self, task, actor, allowed, delegates=()):
        return ToolGateway(self.workflow, self.files, task, actor, human="user", allowed=allowed,
                           delegates=delegates, max_calls=32)

    @staticmethod
    def call(name, identifier="c1", **arguments):
        return {"id": identifier, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}

    def offer(self, path, text):
        receipt = self.files.create_text(self.dev, "dev", path, text)
        return self.files.offer_artifact(self.dev, "dev", path, self.lead, expected_sha256=receipt["sha256"])

    # --- list_files ---------------------------------------------------------------------------------
    def test_list_files_reports_current_versions_from_broker_records(self):
        first = self.files.create_text(self.lead, "lead", "pkg/core.py", "v1\n")
        self.files.update_text(self.lead, "lead", "pkg/core.py", "v2\n", expected_sha256=first["sha256"])
        gone = self.files.create_text(self.lead, "lead", "scratch.txt", "tmp\n")
        self.files.delete_text(self.lead, "lead", "scratch.txt", expected_sha256=gone["sha256"])
        offer = self.offer("pkg/cli.py", "cli\n")
        self.files.accept_artifact(self.lead, "lead", offer["artifact_id"])
        listing = self.files.list_files(self.lead, "lead")
        self.assertEqual(listing["count"], 2)
        self.assertEqual([(f["path"], f["sha256"]) for f in listing["files"]],
                         [("pkg/cli.py", sha("cli\n")), ("pkg/core.py", sha("v2\n"))])
        second = self.workflow.create_task(self.chat, "user", "lead", "Second task with a human input")
        self.files._provide_text(second, "user", "brief.md", "brief\n")  # Inputs to a pending root count too.
        self.workflow.start_task(second, "lead")
        self.assertEqual([f["path"] for f in self.files.list_files(second, "lead")["files"]], ["brief.md"])
        for entry in listing["files"]:  # Matches what read_text sees.
            self.assertEqual(self.files.read_text(self.lead, "lead", entry["path"])["sha256"], entry["sha256"])
        with self.assertRaises(Exception):
            self.files.list_files(self.lead, "dev")  # Only the assigned agent lists its task.

    def test_list_files_is_offered_as_a_read_only_tool(self):
        self.files.create_text(self.lead, "lead", "a.md", "a\n")
        gateway = self.gateway(self.lead, "lead", ["list_files", "read_text"])
        names = {t["function"]["name"] for t in gateway.tools()}
        self.assertIn("list_files", names)
        result = json.loads(gateway.dispatch(self.call("list_files"))["content"])
        self.assertEqual(result["result"]["files"][0]["path"], "a.md")
        self.assertEqual(self.workflow.db.execute("SELECT count(*) FROM events WHERE kind='file_created'").fetchone()[0], 1)

    # --- Accept keeps the producer's layout -----------------------------------------------------------
    def test_accept_without_path_keeps_the_producers_nested_path(self):
        offers = [self.offer(path, path) for path in ("roombook/__init__.py", "roombook/core.py", "tests/test_core.py")]
        for offer in offers:
            receipt = self.files.accept_artifact(self.lead, "lead", offer["artifact_id"])
        self.assertEqual(receipt["path"], "tests/test_core.py")
        self.assertEqual([f["path"] for f in self.files.list_files(self.lead, "lead")["files"]],
                         ["roombook/__init__.py", "roombook/core.py", "tests/test_core.py"])
        explicit = self.offer("notes.md", "n\n")
        self.files.accept_artifact(self.lead, "lead", explicit["artifact_id"], "docs/notes.md")  # Explicit still works.
        self.assertEqual(self.files.read_text(self.lead, "lead", "docs/notes.md")["content"], "n\n")

    def test_gateway_accept_path_is_optional_and_combines_with_replace(self):
        self.files.create_text(self.lead, "lead", "roombook/core.py", "old\n")
        offer = self.offer("roombook/core.py", "new\n")
        gateway = self.gateway(self.lead, "lead", ["accept_artifact"])
        spec = next(t["function"] for t in gateway.tools() if t["function"]["name"] == "accept_artifact")
        self.assertNotIn("path", spec["parameters"]["required"])
        refused = json.loads(gateway.dispatch(self.call("accept_artifact", "a", artifact_id=offer["artifact_id"]))["content"])
        self.assertIn("already exists", refused["error"])
        done = json.loads(gateway.dispatch(self.call("accept_artifact", "b", artifact_id=offer["artifact_id"],
                                                     replace_sha256=sha("old\n")))["content"])
        self.assertTrue(done["ok"])
        self.assertEqual(self.files.read_text(self.lead, "lead", "roombook/core.py")["content"], "new\n")

    # --- Delegation without files is stated, not silent -------------------------------------------------
    def test_delegating_without_inputs_says_the_child_starts_empty(self):
        gateway = self.gateway(self.lead, "lead", ["delegate_task", "delegate_with_inputs"], delegates=("dev",))
        description = next(t["function"]["description"] for t in gateway.tools() if t["function"]["name"] == "delegate_task")
        self.assertIn("starts with no files", description)
        empty = json.loads(gateway.dispatch(self.call("delegate_task", "d1", assignee="dev", title="First"))["content"])
        self.assertNotIn("note", empty["result"])
        self.assertIn("empty", empty["result"]["inputs"])
        self.files.create_text(self.lead, "lead", "roombook/core.py", "core\n")
        held = json.loads(gateway.dispatch(self.call("delegate_task", "d2", assignee="dev", title="Second"))["content"])
        self.assertTrue(held["ok"])
        self.assertIn("You hold 1 task file", held["result"]["note"])
        self.assertIn("delegate_with_inputs", held["result"]["note"])

    def test_retrying_a_failed_child_without_inputs_carries_the_same_note(self):
        from agent_lab import recovery
        recovery.configure(self.workflow, self.lead, 2)
        self.workflow.finish_task(self.dev, "dev", error="Synthetic failure")
        self.files.create_text(self.lead, "lead", "core.py", "core\n")
        gateway = self.gateway(self.lead, "lead", ["retry_failed_task"], delegates=("dev",))
        result = json.loads(gateway.dispatch(self.call("retry_failed_task", "r1", failed_task=self.dev,
                                                       reason="Use the existing package", input_files={}))["content"])
        self.assertTrue(result["ok"], result)
        self.assertIn("You hold 1 task file", result["result"]["note"])

    def test_running_a_script_that_does_not_exist_says_what_can_be_run(self):
        import socket
        import sys
        from agent_lab.sandbox import DockerPythonExecutor, SandboxError
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            path = str(Path(directory) / "d.sock")
            server = socket.socket(socket.AF_UNIX)
            server.bind(path)
            self.addCleanup(server.close)
            executor = DockerPythonExecutor(self.workflow, self.files, docker_host="unix://" + path,
                                            image="python@sha256:" + "a" * 64, docker_binary=sys.executable)
            self.addCleanup(executor.close)
            with self.assertRaisesRegex(SandboxError, "does not exist in your task.*list_files"):
                executor.run_python(self.lead, "lead", entrypoint="verify.py", input_files={"verify.py": "0" * 64},
                                    arguments=[], outputs=[])
            self.assertEqual(self.workflow.db.execute("SELECT count(*) FROM sandbox_runs").fetchone()[0], 0)

    def test_submission_summaries_that_describe_nothing_are_refused(self):
        from agent_lab.gateway import submission_summary_problem
        for bad in ("x", "Placeholder", "placeholder2", "Placeholder check batch header - see following actions",
                    "TODO", " ", "lorem ipsum dolor"):
            with self.subTest(bad=bad):
                self.assertIsNotNone(submission_summary_problem(bad))
        for good in ("Done", "Delivered", "Delivered booking.py with 15 passing tests; see README.md",
                     "已完成报告，见 report.md"):
            with self.subTest(good=good):
                self.assertIsNone(submission_summary_problem(good))

    def test_a_missing_source_path_needs_an_explicit_path(self):
        receipt = self.files.create_text(self.dev, "dev", "x.md", "x\n")
        offer = self.files.offer_artifact(self.dev, "dev", "x.md", self.lead, expected_sha256=receipt["sha256"])
        self.workflow.db.execute("DELETE FROM artifact_labels WHERE artifact=?", (offer["artifact_id"],))
        with self.assertRaisesRegex(FileToolError, "explicit path"):
            self.files.accept_artifact(self.lead, "lead", offer["artifact_id"])



class ControllerIdleTests(unittest.TestCase):
    """A long gap with no controller running and nothing awaiting a human is not task time (2026-11-22)."""

    def setUp(self):
        from agent_lab import budget
        from agent_lab.deepseek import DeepSeekClient
        from agent_lab.runner import Limits
        from agent_lab.scheduler import MultiAgentScheduler, Role
        from test_runner import Script, response, tool
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.now = [1000.0]
        self.workflow = Workflow(root / "state.sqlite3", clock=lambda: self.now[0])
        self.addCleanup(self.workflow.close)
        self.workflow.register_actor("user", "human")
        self.workflow.register_actor("lead", "agent")
        chat = self.workflow.create_chat("group", ["user", "lead"])
        self.root = self.workflow.create_task(chat, "user", "lead", "Write notes")
        self.files = FileTools(self.workflow, root / "files")
        self.addCleanup(self.files.close)
        replies = [response([tool("create_text", {"path": f"n{i}.txt", "content": "x"}, f"c{i}")]) for i in range(4)]
        replies.insert(1, response([tool("ask_human", {"prompt": "Which format?"}, "q")]))
        self.script = Script(replies)
        roles = {"lead": Role("lead", ("create_text", "ask_human", "submit_for_verification"), (),
                              Limits(model_attempts=10, duration_seconds=600))}
        self.scheduler = MultiAgentScheduler(
            self.workflow, self.files, self.root, human="user", roles=roles,
            clients={"lead": DeepSeekClient("synthetic", self.script)}, mode="offline_fixture", constraints=[],
            verifier_factory=lambda task: None, acceptance_id="idle-test",
            limits=budget.TreeLimits(model_attempts=10, duration_seconds=600))
        self.budget = budget

    def elapsed(self):
        return self.budget.task_elapsed(self.workflow, self.root, self.now[0])

    def test_an_unattended_gap_is_excluded_but_a_human_wait_still_counts(self):
        from agent_lab.evaluation.official_live import advance
        advance(self.scheduler, 1)  # create_text
        self.now[0] += 7200  # Two hours with nobody running the controller and nothing pending.
        self.assertTrue(advance(self.scheduler, 1))  # ask_human: the task now waits for the requester
        self.assertLess(self.elapsed(), 60)
        idle = [json.loads(r[0]) for r in self.workflow.db.execute("SELECT detail FROM events WHERE kind='controller_idle'")]
        self.assertEqual([round(d["seconds"]) for d in idle], [7200])
        self.now[0] += 500  # The requester takes a while to answer: human time, counted.
        advance(self.scheduler, 1)
        self.assertEqual(self.workflow.db.execute("SELECT count(*) FROM events WHERE kind='controller_idle'").fetchone()[0], 1)
        self.assertGreaterEqual(self.elapsed(), 500)


if __name__ == "__main__":
    unittest.main()
