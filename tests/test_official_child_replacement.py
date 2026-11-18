"""Official runs let a parent replace a failed child (proposed 2026-11-18, owner-approved, pending merge).

Scripted replies only; no model capability is claimed. Existing safeguards stay:
a failed child with unknown provider usage still fails the whole task, and files
offered by a failed task cannot be accepted, so a replacement starts fresh with
the failure evidence and only the parent's own snapshots.
"""

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from agent_lab import budget
from agent_lab.core import Workflow
from agent_lab.deepseek import DeepSeekClient
from agent_lab.evaluation import official_live
from agent_lab.evaluation.official_live import CHILD_REPLACEMENTS, POLICIES
from agent_lab.files import FileToolError, FileTools
from agent_lab.runner import Limits
from agent_lab.scheduler import MultiAgentScheduler, Role


def reply(*calls, reason=None):
    tool_calls = [{"id": f"c{n}-{name}", "type": "function",
                   "function": {"name": name, "arguments": json.dumps(args)}} for n, (name, args) in enumerate(calls)]
    message = {"role": "assistant", "content": None if calls else "Done."}
    if calls:
        message["tool_calls"] = tool_calls
    return json.dumps({"id": "r", "model": "synthetic-replacement", "usage": {
        "prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        "choices": [{"finish_reason": reason or ("tool_calls" if calls else "stop"), "message": message}]}).encode()


def messages(payload):
    return json.loads(payload)["messages"]


def context(payload):
    return json.loads(messages(payload)[1]["content"])


def latest(payload, kind):
    for message in reversed(messages(payload)):
        if message["role"] == "user":
            try:
                data = json.loads(message["content"])
            except ValueError:
                continue
            if isinstance(data, dict) and data.get("kind") == kind:
                return data
    return None


def tool_result(payload, name_prefix):
    for message in reversed(messages(payload)):
        if message["role"] == "tool" and message["tool_call_id"].endswith(name_prefix):
            return json.loads(message["content"])
    return None


class OfficialChildReplacement(unittest.TestCase):
    def test_official_scheduler_enables_bounded_replacement_and_the_tool(self):
        self.assertEqual(CHILD_REPLACEMENTS, 2)
        for policy in POLICIES.values():
            self.assertIn("retry_failed_task", policy.tools)
            self.assertEqual(policy.tools[-1], "submit_for_verification")
        session = SimpleNamespace(scenario={"id": "software-engineering", "roles": [{"id": "role", "prompt": "Fixture."}]},
                                  agents=("role",), human="requester", workflow=None, _root=lambda number: None)
        live = SimpleNamespace(role_limits=Limits(), tree_limits=budget.TreeLimits(), tool_calls=32, max_output_tokens=4096)
        with (patch.object(official_live, "live_clients", return_value={}),
              patch.object(official_live, "MultiAgentScheduler") as factory):
            official_live.make_scheduler(session, "root", None, live, SimpleNamespace(executor=None, retrieval=None))
        self.assertEqual(factory.call_args.kwargs["child_retries"], 2)

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.workflow = Workflow(Path(directory.name) / "state.sqlite3")
        self.addCleanup(self.workflow.close)
        self.files = FileTools(self.workflow, Path(directory.name) / "files")
        self.addCleanup(self.files.close)
        self.workflow.register_actor("user", "human")
        for agent in ("lead", "dev"):
            self.workflow.register_actor(agent, "agent")
        chat = self.workflow.create_chat("group", ["user", "lead", "dev"])
        self.root = self.workflow.create_task(chat, "user", "lead", "Build the note")

    def scheduler(self, lead, dev):
        return MultiAgentScheduler(self.workflow, self.files, self.root, human="user",
            roles={"lead": Role("Lead fixture", ("delegate_task", "accept_artifact", "retry_failed_task"), ("dev",)),
                   "dev": Role("Dev fixture", ("create_text", "offer_artifact"))},
            clients={"lead": DeepSeekClient("synthetic-replacement", lead),
                     "dev": DeepSeekClient("synthetic-replacement", dev)},
            mode="offline_fixture", constraints=[], acceptance_id="fixture-replacement",
            verifier_factory=lambda task: None, limits=budget.TreeLimits(model_attempts=12),
            child_retries=CHILD_REPLACEMENTS)

    def test_parent_replaces_a_failed_child_instead_of_the_task_failing(self):
        seen = {"lead": [], "dev": []}

        def lead(payload):
            seen["lead"].append(payload)
            result = latest(payload, "child_task_result")
            if result is None:
                return reply(("delegate_task", {"assignee": "dev", "title": "Write draft.txt"}))
            if result["state"] == "failed" and not tool_result(payload, "retry_failed_task"):
                return reply(("retry_failed_task", {"failed_task": result["task_id"],
                                                    "reason": "Write smaller files after the output-limit failure",
                                                    "input_files": {}}))
            return reply()

        def dev(payload):
            seen["dev"].append(payload)
            ctx = context(payload)
            if "retry" in ctx:  # The replacement sees the failure evidence and the carried input.
                return reply()
            written = tool_result(payload, "create_text")
            if written is None:
                return reply(("create_text", {"path": "draft.txt", "content": "partial draft"}))
            if not tool_result(payload, "offer_artifact"):
                return reply(("offer_artifact", {"path": "draft.txt", "target_task": ctx["parent_task_id"],
                                                 "expected_sha256": written["result"]["sha256"]}))
            return reply(("create_text", {"path": "big.txt", "content": "x"}), reason="length")

        scheduler = self.scheduler(lead, dev)
        for _ in range(12):
            state = scheduler.step()
            if state["state"] != "running":
                break
        tasks = {t["id"]: t for t in budget.descendants(self.workflow, self.root)}
        failed = [t for t in tasks.values() if t["assignee"] == "dev" and t["state"] == "failed"]
        self.assertEqual(len(failed), 1)  # The original failed child stays failed in the record.
        self.assertNotEqual(self.workflow.task(self.root, "user")["state"], "failed")
        (link,) = self.workflow.db.execute("SELECT failed,replacement FROM task_retries").fetchall()
        self.assertEqual(link[0], failed[0]["id"])
        (offered,) = self.workflow.db.execute("SELECT id FROM artifacts WHERE source_task=?", (failed[0]["id"],)).fetchall()
        with self.assertRaises(FileToolError):  # Work offered by the failed child stays unaccepted.
            self.files.accept_artifact(self.root, "lead", offered[0], "draft.txt")
        replacement_context = context(seen["dev"][-1])
        self.assertEqual(replacement_context["retry"]["failed_task"], failed[0]["id"])
        self.assertEqual(state["state"], "blocked")  # The replacement's proposal waits for the human reviewer.
        self.assertIn("independent_verification", [need["kind"] for need in state["needs"]])

    def test_failed_child_with_unknown_provider_usage_still_fails_the_task(self):
        def lead(payload):
            return reply(("delegate_task", {"assignee": "dev", "title": "Write draft.txt"}))

        def dev(payload):  # A rejected completion: no usage was recorded.
            return b'{"id": "r", "model": "m", "choices": []}'

        scheduler = self.scheduler(lead, dev)
        for _ in range(6):
            state = scheduler.step()
            if state["state"] != "running":
                break
        self.assertEqual(self.workflow.task(self.root, "user")["state"], "failed")
        self.assertIn("reconciliation", state["reason"])
        self.assertEqual(self.workflow.db.execute("SELECT count(*) FROM task_retries").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
