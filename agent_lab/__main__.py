import argparse
import json
from pathlib import Path
import tempfile

from .core import Workflow


def demo(directory):
    """Exercise only deterministic plumbing. No model, shell, or network calls."""
    if directory is None:
        Path("runs").mkdir(exist_ok=True)
        root = Path(tempfile.mkdtemp(prefix="offline-", dir="runs"))
    else:
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=False)
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


def main():
    parser = argparse.ArgumentParser(description="Offline workflow foundation; no model runtime yet")
    subcommands = parser.add_subparsers(dest="command", required=True)
    command = subcommands.add_parser("demo", help="Run a deterministic, non-benchmark fixture")
    command.add_argument("--state-dir", help="New directory; existing paths are never overwritten")
    args = parser.parse_args()
    try:
        report = demo(args.state_dir)
    except FileExistsError:
        parser.error("State directory already exists; choose a new path to preserve previous evidence")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
