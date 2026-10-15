"""Reproducible offline scenarios for the control center. Never a live fallback.

Each scenario drives the *real* workflow, tool gateway, file broker, approval
path, and scheduler. Only provider responses (and, where stated, human-like
messages) are scripted. Scripted transports derive their turn from the request
transcript, so a scheduler can be reconstructed after an application restart.
"""

from dataclasses import dataclass, field
import json

from .core import WorkflowError
from .deepseek import DeepSeekClient
from .scheduler import MultiAgentScheduler, Role
from .scheduler_fixture import DelegationFixture, fixture_roles

FIXTURE_MODEL = "offline-scenario-fixture"
AGENTS = ("coordinator", "writer", "editor", "archivist", "researcher")


@dataclass(frozen=True)
class Scenario:
    name: str
    title: str
    description: str
    scripted: tuple
    real: tuple
    requires: tuple = field(default=())


def _call(stage, name, args, index=0):
    return {"id": f"scenario-{stage}-{index}-{name}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


def _response(actor, stage, calls=(), text=None):
    calls = list(calls)
    message = {"role": "assistant", "content": None if calls else text}
    if calls:
        message["tool_calls"] = calls
    return json.dumps({"id": f"synthetic-{actor}-{stage}", "model": FIXTURE_MODEL,
                       "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                       "choices": [{"message": message, "finish_reason": "tool_calls" if calls else "stop"}]}).encode()


def _tool_results(request):
    return [json.loads(m["content"]) for m in request["messages"] if m["role"] == "tool"]


class ApprovalScript:
    """Archivist creates two files, then proposes deleting the scratch file."""

    KEEP = "Archive index\n- scenario: approval\n"
    SCRATCH = "temporary working notes\n"

    def __call__(self, payload):
        request = json.loads(payload)
        stage = sum(m["role"] == "assistant" for m in request["messages"])
        if stage == 0:
            return _response("archivist", stage, [
                _call(stage, "create_text", {"path": "keep.txt", "content": self.KEEP}),
                _call(stage, "create_text", {"path": "scratch.txt", "content": self.SCRATCH}, 1)])
        if stage == 1:
            created = next(r["result"] for r in _tool_results(request)
                           if r.get("ok") and r["result"].get("path") == "scratch.txt")
            return _response("archivist", stage, [_call(stage, "delete_text", {
                "path": "scratch.txt", "expected_sha256": created["sha256"]})])
        return _response("archivist", stage, text="Synthetic: archive cleaned; ready for independent checking.")


def approval_roles():
    return {"archivist": Role("Maintain archive files. Deleting a file requires the human's exact approval.",
                              ("create_text", "read_text", "delete_text"))}


SCENARIOS = {
    "chat": Scenario(
        "chat", "Private and group message routing",
        "Creates one private and one group conversation and posts messages. Membership checks decide who can read each conversation.",
        scripted=("message text posted on behalf of agents",),
        real=("conversation membership", "message persistence", "read authorization")),
    "delegation": Scenario(
        "delegation", "Multi-agent delegation, clarification, artifact transfer",
        "Coordinator delegates to writer, writer delegates to editor, editor asks you a question, then snapshots flow back to each parent with independent text checks.",
        scripted=("provider responses (DelegationFixture)",),
        real=("scheduler", "tool gateway", "task tree and budgets", "human pause/resume",
              "file broker and artifact handoff", "independent verification")),
    "approval": Scenario(
        "approval", "Critical-action approval and rejection",
        "Archivist creates files and proposes deleting one. You approve or reject the exact action; approval and release are separate steps.",
        scripted=("provider responses (ApprovalScript)",),
        real=("exact-action approval binding", "trusted release path", "file deletion",
              "cancellation on rejection", "independent verification")),
    "memory": Scenario(
        "memory", "Candidate memory capture and reuse",
        "A real text check fails, a candidate lesson is captured, then retrieved and selected by a later task. Fixture code writes the corrected output; no learning is claimed.",
        scripted=("file contents written by fixture code", "lesson text"),
        real=("memory scope (owner/conversation/namespace)", "provenance", "retrieval/selection history",
              "actual text verification")),
}


def scheduler_for(workflow, files, root, scenario, *, human, memory=None):
    """Rebuild the exact persisted configuration for a scenario root."""
    if scenario == "delegation":
        roles = fixture_roles()
        return MultiAgentScheduler(
            workflow, files, root, human=human, roles=roles,
            clients={a: DeepSeekClient("offline-delegation-fixture", DelegationFixture(), max_tokens=128) for a in roles},
            mode="offline_fixture", constraints=["Use English", "Keep the required newline"],
            acceptance_id="tui-delegation-note-v1",
            verifier_factory=lambda task: (files.text_verifier(task["id"], task["assignee"], {"note.txt": "Hello\n"}),
                                           "tui-delegation-note-text-v1"))
    if scenario == "approval":
        roles = approval_roles()
        return MultiAgentScheduler(
            workflow, files, root, human=human, roles=roles,
            clients={a: DeepSeekClient(FIXTURE_MODEL, ApprovalScript(), max_tokens=128) for a in roles},
            mode="offline_fixture", constraints=["Never delete without exact approval"],
            acceptance_id="tui-approval-archive-v1",
            verifier_factory=lambda task: (files.text_verifier(task["id"], task["assignee"],
                                                               {"keep.txt": ApprovalScript.KEEP}),
                                           "tui-approval-keep-text-v1"))
    raise KeyError(scenario)


def start(name, workflow, files, memory, *, human):
    """Create the scenario's conversations/tasks; return (root task or None, summary)."""
    if name == "chat":
        private = workflow.create_chat("private", [human, "researcher"])
        group = workflow.create_chat("group", [human, "coordinator", "writer", "editor"])
        workflow.post_message(private, human, "Private note: only the researcher and I can read this.")
        workflow.post_message(private, "researcher", "[scripted] Acknowledged in the private conversation.")
        workflow.post_message(group, human, "Group kickoff: coordinator, writer, and editor can all read this.")
        workflow.post_message(group, "coordinator", "[scripted] Coordinator acknowledges the group message.")
        return None, {"private_chat": private, "group_chat": group}
    if name == "delegation":
        chat = workflow.create_chat("group", [human, *fixture_roles()])
        workflow.post_message(chat, human, "Please deliver note.txt (offline delegation scenario).")
        root = workflow.create_task(chat, human, "coordinator", "Deliver the requested note.txt")
        return root, {"chat": chat}
    if name == "approval":
        chat = workflow.create_chat("private", [human, "archivist"])
        root = workflow.create_task(chat, human, "archivist", "Prepare keep.txt and remove scratch.txt")
        return root, {"chat": chat}
    if name == "memory":
        return None, _memory(workflow, files, memory, human=human)
    raise KeyError(name)


def _memory(workflow, files, memory, *, human):
    chat = workflow.create_chat("private", [human, "writer"])
    expected = {"summary.txt": "Verified summary\n"}
    first = workflow.create_task(chat, human, "writer", "Produce summary.txt (first attempt)")
    workflow.start_task(first, "writer")
    # Fixture code writes a deliberately wrong output; the real check rejects it.
    files.create_text(first, "writer", "summary.txt", "verified summary")
    try:
        files.complete_from_text(first, "writer", expected)
    except WorkflowError as error:  # The actual verifier rejection is captured below.
        workflow.finish_task(first, "writer", error="Text check failed: " + str(error)[:200])
    lesson = memory.capture(first, "writer", lesson="Match exact capitalization and keep the trailing newline in text deliverables.",
                            tags=["text", "verification", "newline"])
    second = workflow.create_task(chat, human, "writer", "Produce summary.txt (second attempt)")
    workflow.start_task(second, "writer")
    found = memory.search(second, "writer", "text verification newline")
    if found:
        memory.select(second, "writer", found[0]["memory_id"])
    files.create_text(second, "writer", "summary.txt", expected["summary.txt"])
    files.complete_from_text(second, "writer", expected)
    memory.assess_selected(second, "writer")
    return {"chat": chat, "memory_id": lesson, "first_task": first, "second_task": second,
            "learning_improvement_established": False}
