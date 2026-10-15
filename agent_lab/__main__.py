import argparse
import json
from pathlib import Path
import tempfile

from .core import Workflow, WorkflowError
from .files import FileTools, FileToolError
from .memory import ExperienceMemory


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


def main():
    parser = argparse.ArgumentParser(description="Offline workflow foundation; no model runtime yet")
    subcommands = parser.add_subparsers(dest="command", required=True)
    command = subcommands.add_parser("demo", help="Run a deterministic, non-benchmark fixture")
    command.add_argument("--state-dir", help="New directory; existing paths are never overwritten")
    files_command = subcommands.add_parser("files-demo", help="Exercise controlled text CRUD and explicit artifact handoff")
    files_command.add_argument("--state-dir", help="New directory; existing paths are never overwritten")
    memory_command = subcommands.add_parser("memory-demo", help="Exercise scoped candidate memory without claiming learning gains")
    memory_command.add_argument("--state-dir", help="New directory; existing paths are never overwritten")
    args = parser.parse_args()
    try:
        report = {"demo": demo, "files-demo": file_demo, "memory-demo": memory_demo}[args.command](args.state_dir)
    except FileExistsError:
        parser.error("State directory already exists; choose a new path to preserve previous evidence")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
