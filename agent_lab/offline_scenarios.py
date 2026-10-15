"""Reproducible offline scenarios for the control center. Never a live fallback.

Each scenario drives the *real* workflow, tool gateway, file broker, approval
path, and scheduler. Only provider responses (and, where stated, human-like
messages) are scripted. Scripted transports derive their turn from the request
transcript, so a scheduler can be reconstructed after an application restart.
"""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path

from .core import WorkflowError
from .deepseek import DeepSeekClient
from .scheduler import MultiAgentScheduler, Role
from .scheduler_fixture import DelegationFixture, fixture_roles

FIXTURE_MODEL = "offline-scenario-fixture"
AGENTS = ("coordinator", "writer", "editor", "archivist", "researcher", "integrator")
DEMO_REPOSITORY, DEMO_BRANCH, DEMO_REMOTE = "demo", "agent/demo", "origin"


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


class GitScript:
    """Integrator writes a note, commits it to the demo repository, then requests a push."""

    @staticmethod
    def note(task_id):
        return f"# Agent note\n\nWritten by the integrator for task {task_id} (offline scenario).\n"

    def __call__(self, payload):
        request = json.loads(payload)
        stage = sum(m["role"] == "assistant" for m in request["messages"])
        context = json.loads(request["messages"][1]["content"])
        if stage == 0:
            return _response("integrator", stage, [
                _call(stage, "create_text", {"path": "agent-note.md", "content": self.note(context["task_id"])})])
        if stage == 1:
            return _response("integrator", stage, [
                _call(stage, "git_status", {"repository": DEMO_REPOSITORY}),
                _call(stage, "git_commit", {"repository": DEMO_REPOSITORY, "files": {"docs/agent-note.md": "agent-note.md"},
                                            "message": "Add integrator note (offline scenario)"}, 1)])
        if stage == 2:
            return _response("integrator", stage, [_call(stage, "git_push", {
                "repository": DEMO_REPOSITORY, "remote": DEMO_REMOTE, "branch": DEMO_BRANCH})])
        return _response("integrator", stage, text="Synthetic: note committed and pushed; ready for independent checking.")


def git_roles():
    return {"integrator": Role("Commit task notes to the trusted demo repository; pushes need the human's exact approval.",
                               ("create_text", "read_text", "git_status", "git_diff", "git_log", "git_commit", "git_push"))}


def demo_repository_config(state_dir):
    """Trusted configuration for the disposable scenario repository."""
    from .git_tools import TrustedRepository
    base = os.path.realpath(os.path.join(state_dir, "git-demo"))
    return TrustedRepository(DEMO_REPOSITORY, os.path.join(base, "work"), writable_branches=(DEMO_BRANCH,),
                             writable_paths=("docs/",), remotes=((DEMO_REMOTE, os.path.join(base, "remote.git")),))


def prepare_demo_repository(git, repository):
    """Trusted fixture setup: a local work tree and bare remote; never a real GitHub remote."""
    from .git_tools import _SAFE, _run
    work = Path(repository.path)
    remote = repository.remote_url(DEMO_REMOTE)
    if work.exists():
        return False
    work.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    env = git._env() | {"GIT_AUTHOR_NAME": "Scenario fixture", "GIT_AUTHOR_EMAIL": "fixture@agent-lab.invalid",
                        "GIT_COMMITTER_NAME": "Scenario fixture", "GIT_COMMITTER_EMAIL": "fixture@agent-lab.invalid"}

    def run(*arguments, cwd=None):
        code, _, err, interrupted = _run([git.binary, *_SAFE, *arguments], env, seconds=20, output_bytes=65536, cwd=cwd)
        if code != 0 or interrupted:
            raise WorkflowError("Demo repository setup failed: " + err.decode("utf-8", "replace")[:200])
    run("init", "-q", "--bare", remote)
    run("init", "-q", "-b", "main", str(work))
    (work / "docs").mkdir()
    (work / "README.md").write_text("# Disposable demo repository\n\nCreated by the control-center git scenario.\n")
    (work / "docs" / "index.md").write_text("# Notes\n")
    run("add", "README.md", "docs/index.md", cwd=str(work))
    run("commit", "-q", "--no-verify", "-m", "Initial fixture commit", cwd=str(work))
    run("push", "-q", "--no-verify", remote, "main:refs/heads/main", cwd=str(work))
    run("switch", "-q", "-c", DEMO_BRANCH, cwd=str(work))
    return True


def git_verifier(workflow, git, task):
    """Trusted acceptance: a verified push of the expected note exists on the remote."""
    repository = git.repositories[DEMO_REPOSITORY]
    remote = repository.remote_url(DEMO_REMOTE)

    def verify():
        row = workflow.db.execute(
            "SELECT result FROM git_operations WHERE task=? AND operation='push' AND status='verified' "
            "ORDER BY started DESC LIMIT 1", (task,)).fetchone()
        if row is None:
            return {"push_verified": False}
        commit = json.loads(row["result"])["commit"]
        code, out, _, _ = git._remote_git(["--git-dir", remote, "show", f"{commit}:docs/agent-note.md"])
        return {"push_verified": True,
                "remote_branch_at_commit": git._remote_head(remote, DEMO_BRANCH) == commit,
                "remote_note_matches": code == 0 and out.decode("utf-8", "replace") == GitScript.note(task)}
    return verify


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
    "git": Scenario(
        "git", "Git commit and approved push (disposable local repository)",
        "Integrator commits a task note to a local test repository, then requests a fast-forward push. You approve the exact "
        "commit/branch/remote binding, release it, and the remote branch is verified. No GitHub remote is used.",
        scripted=("provider responses (GitScript)", "initial fixture commit"),
        real=("restricted Git CLI", "path/branch allowlists", "approval binding to commit and remote state",
              "post-push remote verification", "independent acceptance check"),
        requires=("git",)),
}


def scheduler_for(workflow, files, root, scenario, *, human, memory=None, git=None):
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
    if scenario == "git":
        if git is None:
            raise WorkflowError("Git tools are not configured in this session")
        roles = git_roles()
        return MultiAgentScheduler(
            workflow, files, root, human=human, roles=roles,
            clients={a: DeepSeekClient(FIXTURE_MODEL, GitScript(), max_tokens=128) for a in roles},
            mode="offline_fixture", constraints=["Never push without exact approval", "Only fast-forward pushes"],
            acceptance_id="tui-git-push-v1", git=git,
            verifier_factory=lambda task: (git_verifier(workflow, git, task["id"]), "tui-git-remote-note-v1"))
    raise KeyError(scenario)


def start(name, workflow, files, memory, *, human, git=None):
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
    if name == "git":
        if git is None or DEMO_REPOSITORY not in git.repositories:
            raise WorkflowError("The demo Git repository is not configured in this session")
        created = prepare_demo_repository(git, git.repositories[DEMO_REPOSITORY])
        chat = workflow.create_chat("private", [human, "integrator"])
        root = workflow.create_task(chat, human, "integrator", "Commit a note to the demo repository and push agent/demo")
        return root, {"chat": chat, "repository_created": created}
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
