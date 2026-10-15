import argparse
import json
from pathlib import Path
import tempfile

from .core import Workflow, WorkflowError
from .files import FileTools, FileToolError
from .memory import ExperienceMemory
from .deepseek import DeepSeekClient
from .gateway import ToolGateway
from .runner import Limits, TaskRunner
from .sandbox import DockerPythonExecutor, SandboxError


def new_run_directory(directory, prefix):
    if directory is None:
        Path("runs").mkdir(exist_ok=True)
        root = Path(tempfile.mkdtemp(prefix=prefix, dir="runs"))
    else:
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=False)
    return root


def demo(directory):
    """Exercise only deterministic plumbing. No model, shell, or network calls."""
    root = new_run_directory(directory, "offline-")
    store = Workflow(root / "workflow.sqlite3")
    try:
        for actor, kind in [("user", "human"), ("coordinator", "agent"), ("writer", "agent")]:
            store.register_actor(actor, kind)
        group = store.create_chat("group", ["user", "coordinator", "writer"])
        private = store.create_chat("private", ["user", "writer"])
        store.post_message(group, "user", "Prepare and verify a short plain-text note.")
        store.post_message(private, "user", "This note belongs to the private conversation.")
        goal = store.create_task(group, "user", "coordinator", "Prepare a verified note")
        store.start_task(goal, "coordinator")
        child = store.create_task(group, "coordinator", "writer", "Write the note", parent=goal)
        store.start_task(child, "writer")
        question = store.ask_human(child, "writer", "user", "What title should the note use?")
        # Close/reopen to exercise a durable human-response boundary.
        store.close()
        store = Workflow(root / "workflow.sqlite3")
        store.respond(question, "user", answer="Offline workflow demonstration")
        operation = {"tool": "demo.write_text", "path": "note.txt", "title": "Offline workflow demonstration"}
        approval = store.ask_human(child, "writer", "user", "Allow this exact demo write?", action=operation)
        store.respond(approval, "user", approve=True)
        approved = store.consume_approval(approval, "writer", operation)
        # This is trusted fixture code, not a model-generated tool invocation or sandbox.
        expected = approved["title"] + "\nThis is an offline fixture, not autonomous agent output.\n"
        note = root / "note.txt"
        note.write_text(expected, encoding="utf-8")
        if note.read_text(encoding="utf-8") != expected:
            raise RuntimeError("Fixture note verification failed")
        store.finish_task(child, "writer", checks={"fixture_note_matches": True})
        store.finish_task(goal, "coordinator", checks={"child_verified": True})
        report = {
            "mode": "offline_fixture", "model_calls": 0, "benchmark_valid": False,
            "state_directory": str(root), "group_chat": group, "private_chat": private,
            "metrics": store.metrics(group, "user"),
        }
        (root / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report
    finally:
        store.close()


def file_demo(directory):
    """Exercise controlled file tools and handoff with trusted fixed expectations."""
    root = new_run_directory(directory, "files-")
    store = Workflow(root / "workflow.sqlite3")
    files = None
    try:
        for actor, kind in [("user", "human"), ("coordinator", "agent"),
                            ("writer", "agent"), ("reviewer", "agent")]:
            store.register_actor(actor, kind)
        chat = store.create_chat("group", ["user", "coordinator", "writer", "reviewer"])
        goal = store.create_task(chat, "user", "coordinator", "Create, hand off, and verify text")
        store.start_task(goal, "coordinator")
        writer = store.create_task(chat, "coordinator", "writer", "Prepare text", parent=goal)
        reviewer = store.create_task(chat, "coordinator", "reviewer", "Receive and check text", parent=goal)
        store.start_task(writer, "writer")
        store.start_task(reviewer, "reviewer")
        files = FileTools(store, root / "files")
        initial = files.create_text(writer, "writer", "draft/note.txt", "Draft\n")
        expected = "Verified file-tool fixture\nThis is scripted, not autonomous agent output.\n"
        final = files.update_text(writer, "writer", "draft/note.txt", expected, expected_sha256=initial["sha256"])
        scratch = files.create_text(writer, "writer", "scratch.txt", "Temporary text")
        files.delete_text(writer, "writer", "scratch.txt", expected_sha256=scratch["sha256"])
        offer = files.offer_artifact(writer, "writer", "draft/note.txt", reviewer, expected_sha256=final["sha256"])
        received = files.accept_artifact(reviewer, "reviewer", offer["artifact_id"], "inbox/note.txt")
        try:
            files.execute_code(writer, "writer", ["python3", "-c", "print('not executed')"])
        except FileToolError:
            execution = "unavailable_no_process_sandbox"
        else:
            raise RuntimeError("Unconfigured code execution unexpectedly succeeded")
        files.complete_from_text(writer, "writer", {"draft/note.txt": expected})
        files.complete_from_text(reviewer, "reviewer", {"inbox/note.txt": expected})
        store.finish_task(goal, "coordinator", checks={"both_artifacts_verified": True})
        report = {
            "mode": "offline_fixture", "model_calls": 0, "benchmark_valid": False,
            "state_directory": str(root), "process_sandbox": False, "code_execution": execution,
            "source_receipt": final, "received_receipt": received, "metrics": store.metrics(chat, "user"),
        }
        (root / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report
    finally:
        if files is not None:
            files.close()
        store.close()


def memory_demo(directory):
    """Scripted retrieval after a real text-check failure; not a learning experiment."""
    root = new_run_directory(directory, "memory-")
    store = Workflow(root / "workflow.sqlite3")
    files = None
    try:
        store.register_actor("user", "human")
        store.register_actor("writer", "agent")
        chat = store.create_chat("group", ["user", "writer"])
        files = FileTools(store, root / "files")
        memory = ExperienceMemory(store, namespace="offline-development-fixture")
        expected = "Verified report\n"
        first = store.create_task(chat, "user", "writer", "Write a verified report")
        store.start_task(first, "writer")
        files.create_text(first, "writer", "report.txt", "Unverified draft\n")
        try:
            files.complete_from_text(first, "writer", {"report.txt": expected})
        except WorkflowError:
            store.finish_task(first, "writer", error="Actual report text did not match the trusted expectation")
        else:
            raise RuntimeError("The fixture's incorrect report unexpectedly passed verification")
        lesson = "Check expected text before declaring the report complete"
        tags = ["text", "verification"]
        identifier = memory.capture(first, "writer", lesson=lesson, tags=tags)
        second = store.create_task(chat, "user", "writer", "Write a second verified report")
        store.start_task(second, "writer")
        retrieved = memory.search(second, "writer", "text verification")
        if not retrieved or retrieved[0]["memory_id"] != identifier:
            raise RuntimeError("The scoped candidate lesson was not retrieved")
        memory.select(second, "writer", identifier)
        # The fixture writes the expected text explicitly. No model learned this behavior.
        files.create_text(second, "writer", "report.txt", expected)
        files.complete_from_text(second, "writer", {"report.txt": expected})
        assessed = memory.assess_selected(second, "writer")
        merged = memory.capture(second, "writer", lesson=lesson, tags=tags)
        report = {
            "mode": "offline_fixture", "model_calls": 0, "benchmark_valid": False,
            "learning_improvement_established": False, "state_directory": str(root),
            "retrieved_before_second_task": retrieved, "assessed_after_second_task": assessed,
            "exact_duplicate_merged": merged == identifier, "metrics": store.metrics(chat, "user"),
        }
        (root / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report
    finally:
        if files is not None:
            files.close()
        store.close()


def protocol_demo(directory):
    """Synthetic HTTP-shaped responses exercise the adapter, never model inference."""
    root = new_run_directory(directory, "protocol-")
    store = Workflow(root / "workflow.sqlite3")
    files = None
    try:
        store.register_actor("user", "human")
        store.register_actor("writer", "agent")
        chat = store.create_chat("private", ["user", "writer"])
        task = store.create_task(chat, "user", "writer", "Write a short note")
        store.start_task(task, "writer")
        files = FileTools(store, root / "files")
        gateway = ToolGateway(store, files, task, "writer", human="user", allowed=["create_text"], max_calls=4)
        call = {"id": "fixture-create", "type": "function", "function": {
            "name": "create_text", "arguments": json.dumps({"path": "note.txt", "content": "Fixture note\n"}),
        }}
        replies = [
            {"role": "assistant", "content": None, "tool_calls": [call]},
            {"role": "assistant", "content": "The fixture note is ready for independent verification."},
        ]
        requests = []

        def fixture_transport(payload):
            requests.append(json.loads(payload))
            if not replies:
                raise RuntimeError("Unexpected fixture request")
            message = replies.pop(0)
            return json.dumps({
                "id": "fixture-" + str(len(requests)), "model": "offline-protocol-fixture",
                "choices": [{"finish_reason": "tool_calls" if "tool_calls" in message else "stop", "message": message}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }).encode()

        client = DeepSeekClient("offline-protocol-fixture", fixture_transport, max_tokens=128)
        messages = [{"role": "user", "content": "Write note.txt with a short note."}]
        first = client.complete(messages, tools=gateway.tools())
        messages.append(first.message)
        messages.append(gateway.dispatch(first.message["tool_calls"][0]))
        final = client.complete(messages, tools=gateway.tools())
        messages.append(final.message)
        before = store.task(task, "user")["state"]
        # Expectations originate in trusted fixture code, not the assistant's proposal.
        files.complete_from_text(task, "writer", {"note.txt": "Fixture note\n"})
        report = {
            "mode": "offline_fixture", "model_calls": 0, "api_network_calls": 0,
            "synthetic_protocol_responses": len(requests), "benchmark_valid": False,
            "process_sandbox": False, "state_before_trusted_verification": before,
            "state_directory": str(root), "metrics": store.metrics(chat, "user"),
        }
        (root / "transcript.json").write_text(json.dumps(messages, indent=2) + "\n", encoding="utf-8")
        (root / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report
    finally:
        if files is not None:
            files.close()
        store.close()


def runner_demo(directory):
    """Scripted clarification/restart/tool/final loop; zero model inference."""
    root = new_run_directory(directory, "runner-")
    store = Workflow(root / "workflow.sqlite3")
    files = None
    try:
        store.register_actor("user", "human")
        store.register_actor("writer", "agent")
        chat = store.create_chat("private", ["user", "writer"])
        task = store.create_task(chat, "user", "writer", "Write note.txt with the requested greeting")
        store.start_task(task, "writer")

        def proposal(name, arguments, identifier):
            return {"role": "assistant", "content": None, "tool_calls": [{
                "id": identifier, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)},
            }]}

        replies = [proposal("ask_human", {"prompt": "Which language and greeting should note.txt use?"}, "clarify"),
                   proposal("create_text", {"path": "note.txt", "content": "Hello\n"}, "write"),
                   {"role": "assistant", "content": "The fixture file is ready for independent checking."}]
        request_count = 0

        def fixture_transport(payload):
            nonlocal request_count
            request_count += 1
            if not replies:
                raise RuntimeError("Unexpected extra fixture request")
            message = replies.pop(0)
            return json.dumps({"id": "fixture-" + str(request_count), "model": "offline-protocol-fixture",
                               "choices": [{"message": message, "finish_reason": "tool_calls" if "tool_calls" in message else "stop"}],
                               "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()

        client = DeepSeekClient("offline-protocol-fixture", fixture_transport, max_tokens=128)

        def create_runner():
            gateway = ToolGateway(store, files, task, "writer", human="user",
                                  allowed=["create_text", "ask_human"], max_calls=4)
            return TaskRunner(gateway, client, mode="offline_fixture", constraints=["Preserve the user's requested language"],
                              limits=Limits(model_attempts=4), verifier_id="fixture-hello-text-v1",
                              verifier=files.text_verifier(task, "writer", {"note.txt": "Hello\n"}))

        files = FileTools(store, root / "files")
        before_restart = create_runner().run()
        if before_restart["task_state"] != "waiting_input":
            raise RuntimeError("The fixture did not pause for clarification")
        request = store.db.execute("SELECT id FROM requests WHERE task=?", (task,)).fetchone()[0]
        files.close()
        store.close()
        store = Workflow(root / "workflow.sqlite3")
        files = FileTools(store, root / "files")
        store.respond(request, "user", answer="English: Hello followed by a newline")
        resumed = create_runner()
        after_restart = resumed.run()
        if after_restart["task_state"] != "succeeded":
            raise RuntimeError("The fixture did not complete its actual text check")
        report = {"mode": "offline_fixture", "model_calls": 0, "api_network_calls": 0,
                  "benchmark_valid": False, "process_sandbox": False, "state_directory": str(root),
                  "synthetic_protocol_responses": request_count, "before_restart": before_restart,
                  "after_restart": after_restart, "metrics": store.metrics(chat, "user")}
        (root / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report
    finally:
        if files is not None:
            files.close()
        store.close()


def sandbox_demo(directory, *, docker_host, image):
    """Run fixed Python sources in a real container; no synthetic engine/model."""
    root = new_run_directory(directory, "sandbox-")
    store = Workflow(root / "workflow.sqlite3")
    files = executor = None
    try:
        store.register_actor("user", "human")
        store.register_actor("coder", "agent")
        chat = store.create_chat("private", ["user", "coder"])
        task = store.create_task(chat, "user", "coder", "Execute and independently check a text-processing fixture")
        store.start_task(task, "coder")
        files = FileTools(store, root / "files")
        executor = DockerPythonExecutor(store, files, docker_host=docker_host, image=image)
        sources = {
            "solution.py": "import re\nfrom collections import Counter\n\ndef word_counts(text):\n    return dict(Counter(re.findall(r'\\w+', text.casefold())))\n",
            "sample.txt": "Hello hello Agents!\n",
            "check.py": "import unittest\nfrom pathlib import Path\nfrom solution import word_counts\n"
                        "class Checks(unittest.TestCase):\n"
                        "    def test_counts(self):\n"
                        "        self.assertEqual(word_counts(Path('sample.txt').read_text()), {'hello': 2, 'agents': 1})\n"
                        "        self.assertEqual(word_counts(''), {})\n"
                        "result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))\n"
                        "if not result.wasSuccessful(): raise SystemExit(1)\n"
                        "Path('result.txt').write_text('Actual Python checks passed.\\n')\n",
        }
        inputs = {path: files.create_text(task, "coder", path, text)["sha256"] for path, text in sources.items()}
        gateway = ToolGateway(store, files, task, "coder", human="user", allowed=["run_python"], executor=executor)
        response = gateway.dispatch({"id": "fixture-python-execution", "type": "function", "function": {
            "name": "run_python", "arguments": json.dumps({"entrypoint": "check.py", "input_files": inputs,
                                                          "arguments": [], "outputs": ["result.txt"]}),
        }})
        tool_result = json.loads(response["content"])
        runtime = tool_result.get("result", {})
        execution = runtime.get("execution") or {}
        passed = (tool_result.get("ok") is True and runtime.get("process_sandbox") is True
                  and runtime.get("cleanup_confirmed") is True and not runtime.get("error")
                  and execution.get("exit_code") == 0 and execution.get("interrupted") is None)
        if passed:
            files.complete_from_text(task, "coder", {"result.txt": "Actual Python checks passed.\n"})
        else:
            store.finish_task(task, "coder", error="Real sandbox fixture failed; inspect its preserved runtime evidence")
        report = {"mode": "sandbox_integration_fixture", "model_calls": 0, "api_network_calls": 0,
                  "benchmark_valid": False, "process_sandbox": runtime.get("process_sandbox", False),
                  "demo_passed": passed, "state_directory": str(root), "tool_result": tool_result,
                  "metrics": store.metrics(chat, "user")}
        (root / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report
    finally:
        if executor is not None:
            executor.close()
        if files is not None:
            files.close()
        store.close()


def main():
    parser = argparse.ArgumentParser(description="Engineering fixtures; no live model calls")
    subcommands = parser.add_subparsers(dest="command", required=True)
    command = subcommands.add_parser("demo", help="Run a deterministic, non-benchmark fixture")
    command.add_argument("--state-dir", help="New directory; existing paths are never overwritten")
    files_command = subcommands.add_parser("files-demo", help="Exercise controlled text CRUD and explicit artifact handoff")
    files_command.add_argument("--state-dir", help="New directory; existing paths are never overwritten")
    memory_command = subcommands.add_parser("memory-demo", help="Exercise scoped candidate memory without claiming learning gains")
    memory_command.add_argument("--state-dir", help="New directory; existing paths are never overwritten")
    protocol_command = subcommands.add_parser("protocol-demo", help="Exercise synthetic provider responses and controlled tool dispatch")
    protocol_command.add_argument("--state-dir", help="New directory; existing paths are never overwritten")
    runner_command = subcommands.add_parser("runner-demo", help="Exercise a bounded synthetic tool loop and restart after human clarification")
    runner_command.add_argument("--state-dir", help="New directory; existing paths are never overwritten")
    scheduler_command = subcommands.add_parser("scheduler-demo", help="Exercise synthetic agent-to-agent delegation, handoff, and restart")
    scheduler_command.add_argument("--state-dir", help="New directory; existing paths are never overwritten")
    sandbox_command = subcommands.add_parser("sandbox-demo", help="Run fixed sources in a real, explicitly configured Docker sandbox")
    sandbox_command.add_argument("--state-dir", help="New directory; existing paths are never overwritten")
    sandbox_command.add_argument("--docker-host", required=True, help="Explicit local Unix socket; no implicit Docker context")
    sandbox_command.add_argument("--image", required=True, help="Already-pulled official Python image pinned by sha256 digest")
    args = parser.parse_args()
    try:
        if args.command == "sandbox-demo":
            report = sandbox_demo(args.state_dir, docker_host=args.docker_host, image=args.image)
        elif args.command == "scheduler-demo":
            from .scheduler_fixture import run_fixture
            report = run_fixture(new_run_directory(args.state_dir, "scheduler-"))
        else:
            report = {"demo": demo, "files-demo": file_demo, "memory-demo": memory_demo,
                      "protocol-demo": protocol_demo, "runner-demo": runner_demo}[args.command](args.state_dir)
    except FileExistsError:
        parser.error("State directory already exists; choose a new path to preserve previous evidence")
    except SandboxError as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))
    if report.get("demo_passed") is False:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
