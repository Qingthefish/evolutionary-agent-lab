"""Finish reserve for parents in open workflows (proposed 2026-11-19, pending owner review).

Scripted agents reproduce the shapes seen in live software roots: a late delegation
with few shared requests left, a child that would spend every remaining request,
and a parent resuming after all children were accepted. No model capability is
claimed, and no task is completed without its own proposal and a human review.
"""

import itertools
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from agent_lab import budget
from agent_lab.core import Workflow, WorkflowError
from agent_lab.deepseek import DeepSeekClient
from agent_lab.evaluation import official_live
from agent_lab.evaluation.official_live import FINISH_RESERVE, review_proposal
from agent_lab.files import FileTools
from agent_lab.runner import Limits, RunnerError
from agent_lab.scheduler import MultiAgentScheduler, Role


_IDS = itertools.count()


def reply(*calls):
    tool_calls = [{"id": f"c{next(_IDS)}-{name}", "type": "function",
                   "function": {"name": name, "arguments": json.dumps(args)}} for n, (name, args) in enumerate(calls)]
    message = {"role": "assistant", "content": None if calls else "Done."}
    if calls:
        message["tool_calls"] = tool_calls
    return json.dumps({"id": "r", "model": "synthetic-finish", "usage": {
        "prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        "choices": [{"finish_reason": "tool_calls" if calls else "stop", "message": message}]}).encode()


def context(payload):
    return json.loads(json.loads(payload)["messages"][1]["content"])


def user_kinds(payload):
    kinds = []
    for message in json.loads(payload)["messages"]:
        if message["role"] == "user":
            try:
                kinds.append(json.loads(message["content"]).get("kind"))
            except (ValueError, AttributeError):
                pass
    return kinds


def tool_results(payload):
    return [json.loads(m["content"]) for m in json.loads(payload)["messages"] if m["role"] == "tool"]


class Agent:
    """Scripted agent: decide(payload, n) returns the reply; every request is kept."""

    def __init__(self, decide):
        self.decide, self.requests = decide, []

    def __call__(self, payload):
        self.requests.append(payload)
        return self.decide(payload, len(self.requests))


class FinishReserve(unittest.TestCase):
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
        self.root = self.workflow.create_task(chat, "user", "lead", "Build the booking tool")

    def scheduler(self, lead, dev, *, cap, finish_reserve=FINISH_RESERVE, show=True):
        limits = Limits(model_attempts=cap)
        return MultiAgentScheduler(self.workflow, self.files, self.root, human="user",
            roles={"lead": Role("Lead fixture", ("create_text", "delegate_task", "submit_for_verification"),
                                ("dev",), limits),
                   "dev": Role("Dev fixture", ("create_text", "submit_for_verification"), (), limits)},
            clients={"lead": DeepSeekClient("synthetic-finish", lead),
                     "dev": DeepSeekClient("synthetic-finish", dev)},
            mode="offline_fixture", constraints=[], acceptance_id="fixture-finish",
            verifier_factory=lambda task: None, limits=budget.TreeLimits(model_attempts=cap),
            show_execution_budget=show, finish_reserve=finish_reserve,
            child_retries=official_live.CHILD_REPLACEMENTS)  # As in official runs.

    def drive(self, scheduler, steps=60):
        state = None
        for _ in range(steps):
            state = scheduler.step()
            if state["state"] != "running":
                break
        return state

    def tasks(self):
        return {row["assignee"]: dict(row) for row in self.workflow.db.execute("SELECT * FROM tasks")}

    def test_late_delegation_is_refused_and_the_lead_keeps_its_turn_to_finish(self):
        # Live 72-request root: the lead delegated a new fix with 11 shared requests left.
        def lead(payload, n):
            refused = [r for r in tool_results(payload) if not r.get("ok") and "No subtask was created" in r.get("error", "")]
            if refused:
                return reply(("submit_for_verification", {"summary": "Booking tool done; known limitation listed"}))
            if n < 8:
                return reply(("create_text", {"path": f"part{n}.txt", "content": "x"}))
            return reply(("delegate_task", {"assignee": "dev", "title": "Optional polish"}))

        lead_agent, dev_agent = Agent(lead), Agent(lambda payload, n: reply())
        state = self.drive(self.scheduler(lead_agent, dev_agent, cap=16))
        self.assertNotIn("dev", self.tasks())  # No subtask was created.
        self.assertEqual(dev_agent.requests, [])
        refusal = [r for r in tool_results(lead_agent.requests[-1]) if not r.get("ok")][0]["error"]
        self.assertIn("8 shared requests remain", refusal)
        self.assertEqual(state["needs"][0]["kind"], "independent_verification")  # Its own proposal, awaiting a human.
        self.assertEqual(self.workflow.task(self.root, "user")["state"], "running")

    def test_a_child_cannot_spend_the_parents_finish_and_is_warned_first(self):
        # Live 48-request roots: a QA child used 22 of 22 (and 11 of 11) remaining requests.
        def lead(payload, n):
            if n == 1:
                return reply(("delegate_task", {"assignee": "dev", "title": "Implement and test"}))
            return reply(("create_text", {"path": f"lead{n}.txt", "content": "x"}))

        def dev(payload, n):  # Never proposes completion on its own.
            return reply(("create_text", {"path": f"dev{n}.txt", "content": "x"}))

        lead_agent, dev_agent = Agent(lead), Agent(dev)
        state = self.drive(self.scheduler(lead_agent, dev_agent, cap=20))
        tasks = self.tasks()
        self.assertEqual(tasks["dev"]["state"], "failed")
        self.assertIn("kept for the parent task's finish", tasks["dev"]["evidence"])
        self.assertEqual(len(dev_agent.requests), 16)  # 20 - 1 lead request - 3 kept for the lead.
        self.assertEqual(len(lead_agent.requests), 4)  # The lead got its reserved turns after the child stopped.
        warned = [context(p)["execution_budget"]["shared"].get("final_requests", False) for p in dev_agent.requests]
        self.assertEqual(warned, [False] * 13 + [True] * 3)  # Its last three requests (2, 1, 0 left after each).
        self.assertIn("1 request(s) left, including this one",
                      context(dev_agent.requests[-1])["execution_budget"]["shared"]["instruction"])
        self.assertNotIn("delegated_work_accepted", user_kinds(lead_agent.requests[-1]))  # A failed child is no finish.
        self.assertEqual(self.workflow.task(self.root, "user")["state"], "failed")
        self.assertIn("attempts budget exhausted", self.workflow.task(self.root, "user")["evidence"])

    def test_accepted_children_prompt_a_finish_decision_but_never_complete_the_task(self):
        def lead(payload, n):
            if "delegated_work_accepted" in user_kinds(payload):
                return reply(("submit_for_verification", {"summary": "Delivered the tool and the dev's tests"}))
            return reply(("delegate_task", {"assignee": "dev", "title": "Implement and test"}))

        def dev(payload, n):
            if context(payload)["execution_budget"]["shared"].get("final_requests"):
                return reply(("submit_for_verification", {"summary": "Implemented; gaps listed"}))
            return reply(("create_text", {"path": f"dev{n}.txt", "content": "x"}))

        lead_agent, dev_agent = Agent(lead), Agent(dev)
        scheduler = self.scheduler(lead_agent, dev_agent, cap=16)
        state = self.drive(scheduler)
        dev_task = self.tasks()["dev"]["id"]
        self.assertEqual(state["needs"][0], {"task": dev_task, "kind": "independent_verification"})
        review_proposal(scheduler, dev_task, "accept", "Reviewer accepted the dev deliverable")
        state = self.drive(scheduler)
        self.assertEqual(user_kinds(lead_agent.requests[-1]).count("delegated_work_accepted"), 1)
        self.assertEqual(state["needs"][0], {"task": self.root, "kind": "independent_verification"})
        self.assertEqual(self.workflow.task(self.root, "user")["state"], "running")  # Not completed automatically.
        view = context(lead_agent.requests[-1])["execution_budget"]
        self.assertEqual(view["task"]["model_attempts_left_after_current"],
                         view["shared"]["available_to_this_task_after_current"])  # One consistent count.
        self.assertGreaterEqual(view["shared"]["available_to_this_task_after_current"], 1)
        review_proposal(scheduler, self.root, "accept", "Requester accepted the delivered tool")
        self.assertEqual(self.workflow.task(self.root, "user")["state"], "succeeded")

    def test_recorded_live_delegation_points_against_the_reserve(self):
        # Shared requests left at the lead's last delegation in the live software roots.
        cases = {"24-request root": (24, 24), "48-request root #2": (48, 37), "48-request root #3": (48, 26),
                 "72-request root": (72, 61)}
        outcomes = {}
        for label, (cap, used) in cases.items():
            directory = tempfile.TemporaryDirectory()
            self.addCleanup(directory.cleanup)
            workflow = Workflow(Path(directory.name) / "s.sqlite3")
            self.addCleanup(workflow.close)
            workflow.register_actor("user", "human")
            workflow.register_actor("lead", "agent")
            root = workflow.create_task(workflow.create_chat("group", ["user", "lead"]), "user", "lead", "Build")
            budget.configure(workflow, root, budget.TreeLimits(model_attempts=cap))
            budget.configure_finish_reserve(workflow, root, *FINISH_RESERVE)
            workflow.db.execute("UPDATE tree_budgets SET attempts=? WHERE root=?", (used, root))
            outcomes[label] = budget.delegation_refusal(workflow, root) is None
        self.assertEqual(outcomes, {"24-request root": False, "48-request root #2": False,
                                    "48-request root #3": True, "72-request root": False})

    def test_without_the_reserve_behaviour_is_unchanged(self):
        def lead(payload, n):
            if n < 4:
                return reply(("create_text", {"path": f"part{n}.txt", "content": "x"}))
            return reply(("delegate_task", {"assignee": "dev", "title": "Late work"}))

        lead_agent, dev_agent = Agent(lead), Agent(lambda payload, n: reply(("create_text", {"path": f"d{n}.txt", "content": "x"})))
        self.drive(self.scheduler(lead_agent, dev_agent, cap=6, finish_reserve=None))
        self.assertIn("dev", self.tasks())  # Delegation with 2 left is still allowed.
        self.assertEqual(len(lead_agent.requests) + len(dev_agent.requests), 6)
        self.assertFalse(self.workflow.db.execute("SELECT 1 FROM sqlite_master WHERE name='finish_reserves'").fetchone())
        view = context(lead_agent.requests[0])["execution_budget"]
        self.assertNotIn("delegation", view["shared"])

    def test_reserve_requires_the_budget_view_and_a_fixed_configuration(self):
        with self.assertRaises(RunnerError):
            self.scheduler(Agent(lambda p, n: reply()), Agent(lambda p, n: reply()), cap=8, show=False)
        with self.assertRaises(RunnerError):
            self.scheduler(Agent(lambda p, n: reply()), Agent(lambda p, n: reply()), cap=8, finish_reserve=[3, 6])
        self.scheduler(Agent(lambda p, n: reply()), Agent(lambda p, n: reply()), cap=8)
        with self.assertRaises(WorkflowError):  # A resumed run cannot change its reserve.
            self.scheduler(Agent(lambda p, n: reply()), Agent(lambda p, n: reply()), cap=8, finish_reserve=(2, 6))

    def test_official_runs_enable_the_reserve_only_when_selected(self):
        session = SimpleNamespace(scenario={"id": "software-engineering", "roles": [
            {"id": "lead", "prompt": "Lead."}, {"id": "dev", "prompt": "Dev."}]},
            agents=("lead", "dev"), human="requester", workflow=None, _root=lambda number: None)
        live = SimpleNamespace(role_limits=Limits(), tree_limits=budget.TreeLimits(), tool_calls=32, max_output_tokens=4096)
        for selected, expected in ((False, None), (True, (3, 10))):
            with (patch.object(official_live, "live_clients", return_value={}),
                  patch.object(official_live, "MultiAgentScheduler") as factory):
                official_live.make_scheduler(session, "root", None, live, SimpleNamespace(executor=None, retrieval=None),
                                             show_execution_budget=True, reserve_finish=selected)
            self.assertEqual(factory.call_args.kwargs["finish_reserve"], expected)
            self.assertEqual(FINISH_RESERVE, (3, 10))
            lead_tools = factory.call_args.kwargs["roles"]["lead"].tools
            self.assertFalse({"create_text", "update_text", "append_text", "run_python"} & set(lead_tools))


if __name__ == "__main__":
    unittest.main()
