"""Explicit synthetic delegation fixture. Never a live-model fallback."""

import json

from .core import Workflow
from .deepseek import DeepSeekClient
from .files import FileTools
from .scheduler import MultiAgentScheduler, Role


class DelegationFixture:
    """Fixed coordinator -> writer -> editor script, derived from saved turns."""

    def __init__(self):
        self.requests = []

    def __call__(self, payload):
        request = json.loads(payload)
        self.requests.append(request)
        context = json.loads(request["messages"][1]["content"])
        actor = context["role"]["agent"]
        stage = sum(message["role"] == "assistant" for message in request["messages"])

        def call(name, args):
            return {"id": f"fixture-{stage}-{name}", "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)}}

        calls = []
        if actor in {"coordinator", "writer"} and stage == 0:
            calls = [call("delegate_task", {"assignee": "writer" if actor == "coordinator" else "editor",
                                           "title": "Deliver note.txt containing Hello followed by a newline"})]
        elif actor == "editor" and stage == 0:
            calls = [call("ask_human", {"prompt": "Confirm the greeting language for this fixture?"})]
        elif actor == "editor" and stage == 1:
            calls = [call("create_text", {"path": "note.txt", "content": "Hello\n"})]
        elif actor == "editor" and stage == 2:
            result = next(json.loads(message["content"])["result"] for message in reversed(request["messages"])
                          if message["role"] == "tool" and json.loads(message["content"]).get("ok"))
            calls = [call("offer_artifact", {"path": "note.txt", "target_task": context["parent_task_id"],
                                             "expected_sha256": result["sha256"]})]
        elif actor in {"coordinator", "writer"} and stage == 1:
            child = next(json.loads(message["content"]) for message in reversed(request["messages"])
                         if message["role"] == "user" and json.loads(message["content"]).get("kind") == "child_task_result")
            calls = [call("accept_artifact", {"artifact_id": child["offered_artifacts"][0]["artifact_id"], "path": "note.txt"})]
        elif actor == "writer" and stage == 2:
            result = next(json.loads(message["content"])["result"] for message in reversed(request["messages"])
                          if message["role"] == "tool" and json.loads(message["content"]).get("ok"))
            calls = [call("offer_artifact", {"path": "note.txt", "target_task": context["parent_task_id"],
                                             "expected_sha256": result["sha256"]})]
        message = {"role": "assistant", "content": None if calls else "Synthetic deliverable ready for independent checking."}
        if calls:
            message["tool_calls"] = calls
        return json.dumps({"id": f"synthetic-{actor}-{stage}", "model": "offline-delegation-fixture",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "choices": [{"message": message, "finish_reason": "tool_calls" if calls else "stop"}]}).encode()


def fixture_roles():
    return {
        "coordinator": Role("Delegate note preparation and deliver the independently checked final note.",
                            ("delegate_task", "accept_artifact"), ("writer",)),
        "writer": Role("Delegate drafting to the editor, accept the checked snapshot, and offer it to your parent.",
                       ("delegate_task", "accept_artifact", "offer_artifact"), ("editor",)),
        "editor": Role("Clarify the language, create the fixed fixture note, and explicitly offer it to your parent.",
                       ("ask_human", "create_text", "offer_artifact")),
    }


def run_fixture(directory):
    workflow = Workflow(directory / "workflow.sqlite3")
    files = None
    try:
        workflow.register_actor("user", "human")
        roles = fixture_roles()
        for actor in roles:
            workflow.register_actor(actor, "agent")
        chat = workflow.create_chat("group", ["user", *roles])
        root = workflow.create_task(chat, "user", "coordinator", "Deliver the requested note.txt")
        files = FileTools(workflow, directory / "files")

        def scheduler():
            return MultiAgentScheduler(workflow, files, root, human="user", roles=roles,
                clients={actor: DeepSeekClient("offline-delegation-fixture", DelegationFixture(), max_tokens=128) for actor in roles},
                mode="offline_fixture", constraints=["Use English", "Keep the required newline"],
                acceptance_id="fixture-note-policy-v1", verifier_factory=lambda task: (
                    files.text_verifier(task["id"], task["assignee"], {"note.txt": "Hello\n"}), "fixture-note-text-v1"))

        before = scheduler().run()
        if before["state"] != "blocked" or before["needs"][0]["kind"] != "waiting_input":
            raise RuntimeError("Delegation fixture did not reach its expected human pause")
        request = workflow.db.execute("SELECT id FROM requests WHERE answered=0").fetchone()[0]
        files.close()
        workflow.close()
        workflow = Workflow(directory / "workflow.sqlite3")
        files = FileTools(workflow, directory / "files")
        workflow.respond(request, "user", answer="English; Hello followed by a newline")
        after = scheduler().run()
        if after["task_state"] != "succeeded" or after["budget"]["tasks"] != 3:
            raise RuntimeError("Delegation fixture failed independent completion checks")
        report = {"mode": "offline_fixture", "model_calls": 0, "api_network_calls": 0,
            "benchmark_valid": False, "process_sandbox": False,
            "autonomous_model_collaboration_established": False,
            "state_directory": str(directory), "before_restart": before, "after_restart": after,
            "metrics": workflow.metrics(chat, "user")}
        (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report
    finally:
        if files is not None:
            files.close()
        workflow.close()
