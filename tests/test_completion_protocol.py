"""Completion protocol lifecycle (proposed 2026-11-19, pending owner review).

Scripted agents reproduce the live S01 software failures. Each test asserts the
lifecycle outcome (who proposed, who was reviewed, final states), not merely that
a message appeared. No model capability is claimed; nothing completes without its
own proposal and a recorded human review.
"""

import itertools
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from agent_lab import budget, completion
from agent_lab.budget import FinishPolicy, TreeBudgetError
from agent_lab.core import Workflow, WorkflowError
from agent_lab.deepseek import DeepSeekClient, ProviderError
from agent_lab.evaluation import official_live
from agent_lab.evaluation.official_live import reconcile, review_proposal
from agent_lab.files import FileTools
from agent_lab.runner import Limits, RunnerError
from agent_lab.scheduler import MultiAgentScheduler, Role

_IDS = itertools.count()


def reply(*calls):
    tool_calls = [{"id": f"c{next(_IDS)}", "type": "function",
                   "function": {"name": name, "arguments": json.dumps(args)}} for name, args in calls]
    return json.dumps({"id": "r", "model": "synthetic-completion", "usage": {
        "prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        "choices": [{"finish_reason": "tool_calls",
                     "message": {"role": "assistant", "content": None, "tool_calls": tool_calls}}]}).encode()


def offered(payload):
    return {tool["function"]["name"] for tool in json.loads(payload)["tools"]}


def context(payload):
    return json.loads(json.loads(payload)["messages"][1]["content"])


def contract(payload):
    return context(payload).get("execution_budget", {}).get("completion")


def user_messages(payload):
    found = []
    for message in json.loads(payload)["messages"]:
        if message["role"] == "user":
            try:
                found.append(json.loads(message["content"]))
            except ValueError:
                pass
    return found


def kinds(payload):
    return [m.get("kind") for m in user_messages(payload) if isinstance(m, dict)]


def tool_results(payload):
    return [json.loads(m["content"]) for m in json.loads(payload)["messages"] if m["role"] == "tool"]


def last_sha(payload):
    for result in reversed(tool_results(payload)):
        if result.get("ok") and {"sha256", "path"} <= set(result.get("result") or {}):
            return result["result"]["path"], result["result"]["sha256"]
    return None


def child_offer(payload):
    for message in reversed(user_messages(payload)):
        if isinstance(message, dict) and message.get("kind") == "child_task_result" and message["offered_artifacts"]:
            return message["offered_artifacts"][-1]
    return None


class Agent:
    def __init__(self, decide):
        self.decide, self.requests, self.state = decide, [], {}

    def __call__(self, payload):
        self.requests.append(payload)
        result = self.decide(payload, len(self.requests), self.state)
        if isinstance(result, Exception):
            raise result
        return result


def writer(stop_when, then):
    """A worker that writes files until `stop_when(payload)`, then calls `then(payload, state)`."""
    def decide(payload, n, state):
        if not stop_when(payload, state):
            return reply(("create_text", {"path": f"w{n}.txt", "content": "x"}))
        return then(payload, state)
    return decide


def in_finish(payload, state=None):
    terms = contract(payload)
    return bool(terms and terms["finish_mode"]["active"])


def offer_and_submit(summary="Done; evidence in the files offered"):
    def then(payload, state):
        path, sha = last_sha(payload) or state["file"]
        state["file"] = (path, sha)
        return reply(("offer_artifact", {"path": path, "target_task": context(payload)["parent_task_id"],
                                         "expected_sha256": sha}),
                     ("submit_for_verification", {"summary": summary}))
    return then


def lead_finisher(first_child="dev", polish_child=None):
    """Delegates once; resumes, accepts, reports and submits. Starts optional polish only if offered."""
    def decide(payload, n, state):
        if n == 1:
            return reply(("delegate_task", {"assignee": first_child, "title": "Implement and test the tool"}))
        if (polish_child and "delegate_task" in offered(payload) and "delegated_work_accepted" in kinds(payload)
                and not state.get("polish")):
            state["polish"] = True
            return reply(("delegate_task", {"assignee": polish_child, "title": "Optional extra polish"}))
        offer = child_offer(payload)
        if offer and not state.get("accepted"):
            state["accepted"] = True
            return reply(("accept_artifact", {"artifact_id": offer["artifact_id"], "path": "delivered.txt"}),
                         ("post_message", {"body": "Built the tool; usage is in the delivered file"}))
        return reply(("submit_for_verification", {"summary": "Delivered the tool with the accepted subtask work"}))
    return decide


class CompletionProtocol(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.workflow = Workflow(Path(directory.name) / "state.sqlite3")
        self.addCleanup(self.workflow.close)
        self.files = FileTools(self.workflow, Path(directory.name) / "files")
        self.addCleanup(self.files.close)
        self.workflow.register_actor("user", "human")
        for agent in ("lead", "dev", "qa"):
            self.workflow.register_actor(agent, "agent")
        chat = self.workflow.create_chat("group", ["user", "lead", "dev", "qa"])
        self.root = self.workflow.create_task(chat, "user", "lead", "Build the booking tool")

    def build(self, agents, *, cap, policy=FinishPolicy(), show=True):
        base = {"lead": ("delegate_task", "accept_artifact", "read_text", "post_message", "retry_failed_task"),
                "dev": ("create_text", "update_text", "offer_artifact"),
                "qa": ("create_text", "update_text", "offer_artifact")}
        delegates = {"lead": ("dev", "qa"), "dev": (), "qa": ()}
        limits = Limits(model_attempts=cap)
        roles = {actor: Role(f"{actor} fixture", (*tools, *(("report_blocker",) if policy else ()),
                                                  "submit_for_verification"), delegates[actor], limits)
                 for actor, tools in base.items()}
        self.scheduler = MultiAgentScheduler(self.workflow, self.files, self.root, human="user", roles=roles,
            clients={actor: DeepSeekClient("synthetic-completion", agents.get(actor, Agent(lambda p, n, s: reply())))
                     for actor in roles},
            mode="offline_fixture", constraints=[], acceptance_id="fixture-completion",
            verifier_factory=lambda task: None, limits=budget.TreeLimits(model_attempts=cap),
            show_execution_budget=show, finish_policy=policy, child_retries=2)
        return self.scheduler

    def drive(self, steps=120):
        state = None
        for _ in range(steps):
            state = self.scheduler.step()
            if state["state"] != "running":
                break
        return state

    def task_of(self, actor):
        rows = self.workflow.db.execute("SELECT * FROM tasks WHERE assignee=? ORDER BY rowid", (actor,)).fetchall()
        return [dict(row) for row in rows]

    def events(self, kind, task=None):
        query = "SELECT task,detail FROM events WHERE kind=?" + (" AND task=?" if task else "") + " ORDER BY sequence"
        return [(row["task"], json.loads(row["detail"])) for row in
                self.workflow.db.execute(query, (kind, task) if task else (kind,))]

    def used(self):
        return self.workflow.db.execute("SELECT attempts FROM tree_budgets WHERE root=?", (self.root,)).fetchone()[0]

    # 1. Lead completes all child tasks but would keep performing optional work.
    def test_lead_with_accepted_children_finishes_instead_of_polishing(self):
        lead = Agent(lead_finisher(polish_child="qa"))
        dev = Agent(writer(lambda p, s: len(tool_results(p)) >= 22, offer_and_submit()))
        self.build({"lead": lead, "dev": dev}, cap=30)
        state = self.drive()
        (dev_task,) = self.task_of("dev")
        self.assertEqual(state["needs"][0], {"task": dev_task["id"], "kind": "independent_verification"})
        review_proposal(self.scheduler, dev_task["id"], "accept", "Reviewer accepted the dev deliverable")
        state = self.drive()
        self.assertEqual(state["needs"][0], {"task": self.root, "kind": "independent_verification"})
        self.assertEqual(self.task_of("qa"), [])  # No optional polish subtask was started.
        resumed = [p for p in lead.requests if "delegated_work_accepted" in kinds(p)]
        self.assertTrue(resumed and all("delegate_task" not in offered(p) for p in resumed))
        (finish,) = self.events("finish_mode_entered", self.root)
        self.assertIn("every delegated subtask was accepted", finish[1]["reason"])
        self.assertEqual(self.workflow.task(self.root, "user")["state"], "running")  # Proposed, not completed.
        review_proposal(self.scheduler, self.root, "accept", "Requester accepted the delivered tool")
        self.assertEqual(self.workflow.task(self.root, "user")["state"], "succeeded")

    # 2. QA produces a passing report early but would keep rewriting it.
    def test_qa_that_keeps_rewriting_is_moved_to_finish_and_submits(self):
        def qa(payload, n, state):
            if n == 1:
                return reply(("create_text", {"path": "QA_REPORT.md", "content": "All checks pass"}))
            if n == 2:
                path, sha = last_sha(payload)
                return reply(("offer_artifact", {"path": path, "target_task": context(payload)["parent_task_id"],
                                                 "expected_sha256": sha}))
            path, sha = state.get("report") or ("QA_REPORT.md", None)
            found = last_sha(payload)
            if found and found[0] == "QA_REPORT.md":
                path, sha = found
            state["report"] = (path, sha)
            if "update_text" in offered(payload):  # Live QA rewrote its finished report instead of submitting.
                return reply(("update_text", {"path": path, "content": f"All checks pass (rewrite {n})",
                                              "expected_sha256": sha}))
            return reply(("offer_artifact", {"path": path, "target_task": context(payload)["parent_task_id"],
                                             "expected_sha256": sha}),
                         ("submit_for_verification", {"summary": "QA report: all checks pass; see QA_REPORT.md"}))

        qa_agent = Agent(qa)
        self.build({"lead": Agent(lead_finisher(first_child="qa")), "qa": qa_agent}, cap=24)
        state = self.drive()
        (qa_task,) = self.task_of("qa")
        self.assertEqual(state["needs"][0], {"task": qa_task["id"], "kind": "independent_verification"})
        (finish,) = self.events("finish_mode_entered", qa_task["id"])
        self.assertIn("deliverables were offered to the parent task", finish[1]["reason"])
        self.assertLess(len(qa_agent.requests), 24 - 1 - 3)  # Submitted before the reserve stop.
        review_proposal(self.scheduler, qa_task["id"], "accept", "Reviewer accepted the QA report")
        state = self.drive()
        review_proposal(self.scheduler, self.root, "accept", "Requester accepted")
        self.assertEqual([t["state"] for t in self.task_of("qa")] + [self.workflow.task(self.root, "user")["state"]],
                         ["succeeded", "succeeded"])

    # 3. A summary over 2,000 characters: actionable error, whole batch withheld, resend within the reserve.
    def test_oversized_summary_is_reported_precisely_and_resent_in_the_reserve(self):
        def then(payload, state):
            path, sha = state.setdefault("file", last_sha(payload))
            short = any("exceeds maximum length" in r.get("error", "") for r in tool_results(payload))
            summary = "Done; details in the delivered file" if short else "Done. " + "x" * 2128
            return reply(("offer_artifact", {"path": path, "target_task": context(payload)["parent_task_id"],
                                             "expected_sha256": sha}),
                         ("submit_for_verification", {"summary": summary}))

        dev = Agent(writer(in_finish, then))
        self.build({"lead": Agent(lead_finisher()), "dev": dev}, cap=16)
        state = self.drive()
        (dev_task,) = self.task_of("dev")
        self.assertEqual(state["needs"][0], {"task": dev_task["id"], "kind": "independent_verification"})
        errors = [r["error"] for p in dev.requests for r in tool_results(p) if not r.get("ok")]
        self.assertIn("submit_for_verification: summary exceeds maximum length: 2,134 characters; limit: 2,000. "
                      "Shorten the summary and retry. Keep detailed evidence in a task file and name that file in "
                      "the summary. No call in this batch ran", errors)
        offers = self.workflow.db.execute("SELECT count(*) FROM artifacts WHERE source_task=?", (dev_task["id"],)).fetchone()[0]
        self.assertEqual(offers, 1)  # The rejected batch's offer never ran.
        self.assertLessEqual(self.used(), 16 - FinishPolicy().parent_reserve)

    # 4 + 5. A child that never finishes cannot spend the parent's reserve; the parent cannot
    # propose over the failed child and reports an honest blocker instead.
    def test_unfinished_child_stops_and_the_parent_reports_a_blocker_not_a_success(self):
        def dev(payload, n, state):  # Ignores Finish Mode entirely.
            return reply(("create_text", {"path": f"w{n}.txt", "content": "x"}))

        def lead(payload, n, state):
            if n == 1:
                return reply(("delegate_task", {"assignee": "dev", "title": "Implement and test the tool"}))
            refused = [r["error"] for r in tool_results(payload) if "was not completed or replaced" in r.get("error", "")]
            if refused:
                return reply(("report_blocker", {"summary": "The dev subtask stopped unfinished; nothing to deliver"}))
            return reply(("submit_for_verification", {"summary": "Delivered"}))

        dev_agent, lead_agent = Agent(dev), Agent(lead)
        self.build({"lead": lead_agent, "dev": dev_agent}, cap=20)
        self.drive()
        (dev_task,) = self.task_of("dev")
        self.assertEqual(dev_task["state"], "failed")
        self.assertIn("kept for the parent task's finish", dev_task["evidence"])
        finish_errors = [r["error"] for p in dev_agent.requests for r in tool_results(p) if not r.get("ok")]
        self.assertTrue(any(e.startswith("create_text: Finish Mode: create_text is not available now") for e in finish_errors))
        self.assertEqual(len(lead_agent.requests) - 1, 2)  # The lead got its turns after the child stopped.
        self.assertEqual(self.events("completion_proposed", self.root), [])  # The refused proposal never existed.
        root = self.workflow.task(self.root, "user")
        self.assertEqual(root["state"], "failed")
        self.assertIn("Blocker reported by the agent", root["evidence"])

    # 6. Genuinely incomplete work is reported, not forced into a false success; replacement stays auditable.
    def test_a_blocker_is_an_honest_failure_and_replacement_is_audited(self):
        def dev(payload, n, state):
            if context(payload).get("retry"):
                return writer(lambda p, s: len(tool_results(p)) >= 1, offer_and_submit())(payload, n, state)
            return reply(("report_blocker", {"summary": "Cannot finish: the room list is missing from the inputs"}))

        def lead(payload, n, state):
            if n == 1:
                return reply(("delegate_task", {"assignee": "dev", "title": "Implement and test the tool"}))
            failed = [m for m in user_messages(payload) if isinstance(m, dict) and m.get("kind") == "child_task_result"
                      and m["state"] == "failed"]
            if failed and not state.get("retried"):
                state["retried"] = True
                return reply(("retry_failed_task", {"failed_task": failed[-1]["task_id"],
                                                    "reason": "Use the default rooms", "input_files": {}}))
            return lead_finisher()(payload, n, state)

        self.build({"lead": Agent(lead), "dev": Agent(dev)}, cap=40)
        state = self.drive()
        first, replacement = self.task_of("dev")
        self.assertEqual(first["state"], "failed")
        self.assertIn("Blocker reported by the agent: Cannot finish", first["evidence"])
        self.assertEqual(self.events("completion_proposed", first["id"]), [])  # No forced proposal.
        self.assertEqual(len(self.events("child_replaced", self.root)), 1)
        self.assertEqual(state["needs"][0], {"task": replacement["id"], "kind": "independent_verification"})
        review_proposal(self.scheduler, replacement["id"], "reject", "Add the usage notes")
        state = self.drive()  # The rejected replacement resubmits; the review transition is recorded.
        decisions = [d["decision"] for _, d in self.events("human_review_recorded", replacement["id"])]
        self.assertEqual(decisions, ["rejected"])
        self.assertEqual(state["needs"][0], {"task": replacement["id"], "kind": "independent_verification"})
        review_proposal(self.scheduler, replacement["id"], "accept", "Accepted")
        self.drive()
        review_proposal(self.scheduler, self.root, "accept", "Requester accepted")
        self.assertEqual(self.workflow.task(self.root, "user")["state"], "succeeded")

    # 7. A transient server error at the submission deadline: pause, operator resend, submit in the reserve.
    def test_server_error_at_the_deadline_is_resent_inside_the_reserve(self):
        def then(payload, state):
            if not state.get("errored"):
                state["errored"] = True
                return ProviderError("Provider HTTP status 503; no automatic retry", kind="http_status",
                                     phase="opening", http_status=503)
            return offer_and_submit()(payload, state)

        dev = Agent(writer(in_finish, then))
        self.build({"lead": Agent(lead_finisher()), "dev": dev}, cap=16)
        state = self.drive()
        (dev_task,) = self.task_of("dev")
        self.assertEqual(state["needs"][0]["runner_state"], "provider_uncertain")
        reconcile(self.scheduler, dev_task["id"], "resend", "Operator resent after HTTP 503", human="user")
        state = self.drive()
        self.assertEqual(state["needs"][0], {"task": dev_task["id"], "kind": "independent_verification"})
        self.assertLessEqual(self.used(), 16 - FinishPolicy().parent_reserve)  # The lead's reserve is intact.
        review_proposal(self.scheduler, dev_task["id"], "accept", "Accepted")
        self.drive()
        self.assertEqual(self.events("completion_proposed", self.root)[0][0], self.root)

    # 8. Without the protocol, behaviour and tools are unchanged.
    def test_disabled_protocol_keeps_existing_behaviour(self):
        def qa(payload, n, state):
            found = last_sha(payload)
            if found is None:
                return reply(("create_text", {"path": "QA_REPORT.md", "content": "pass"}))
            return reply(("update_text", {"path": found[0], "content": f"pass {n}", "expected_sha256": found[1]}))

        qa_agent, lead = Agent(qa), Agent(lead_finisher(first_child="qa"))
        self.build({"lead": lead, "qa": qa_agent}, cap=12, policy=None, show=False)
        self.drive()
        self.assertEqual(self.events("finish_mode_entered"), [])
        self.assertTrue(all("update_text" in offered(p) and "report_blocker" not in offered(p) for p in qa_agent.requests))
        self.assertTrue(all("execution_budget" not in context(p) for p in qa_agent.requests + lead.requests))
        self.assertEqual(len(lead.requests) + len(qa_agent.requests), 12)  # QA spends the whole cap, as before.
        self.assertEqual(self.workflow.task(self.root, "user")["state"], "failed")
        self.assertFalse(self.workflow.db.execute("SELECT 1 FROM sqlite_master WHERE name='finish_policies'").fetchone())

    def test_every_agent_sees_its_completion_contract(self):
        lead = Agent(lead_finisher())
        dev = Agent(writer(lambda p, s: len(tool_results(p)) >= 2, offer_and_submit()))
        self.build({"lead": lead, "dev": dev}, cap=30)
        self.drive()
        for agent, role in ((lead, "lead"), (dev, "dev")):
            terms = contract(agent.requests[0])
            self.assertEqual(terms["completion_tool"], "submit_for_verification")
            self.assertEqual(terms["phase"], "working")
            self.assertTrue(any("2000 characters" in rule for rule in terms["rules"]))
            self.assertTrue(any("report_blocker" in rule for rule in terms["rules"]))
            view = context(agent.requests[0])["execution_budget"]
            self.assertEqual(view["task"]["model_attempts_left_after_current"], terms["requests_available_after_current"])
        (dev_task,) = self.task_of("dev")
        self.assertTrue(any(self.root in rule for rule in contract(dev.requests[0])["rules"]))  # The parent task id.
        self.assertEqual(contract(dev.requests[0])["requests_kept_for_own_finish"], FinishPolicy().submit_reserve)

    def test_recorded_live_delegation_points_against_the_policy(self):
        cases = {"24-request root": (24, 24, False), "48-request root #2": (48, 37, False),
                 "48-request root #3": (48, 26, True), "72-request root": (72, 61, False)}
        for label, (cap, used, allowed) in cases.items():
            directory = tempfile.TemporaryDirectory()
            self.addCleanup(directory.cleanup)
            workflow = Workflow(Path(directory.name) / "s.sqlite3")
            self.addCleanup(workflow.close)
            workflow.register_actor("user", "human")
            workflow.register_actor("lead", "agent")
            root = workflow.create_task(workflow.create_chat("group", ["user", "lead"]), "user", "lead", "Build")
            budget.configure(workflow, root, budget.TreeLimits(model_attempts=cap))
            budget.configure_finish_policy(workflow, root, FinishPolicy())
            workflow.db.execute("UPDATE tree_budgets SET attempts=? WHERE root=?", (used, root))
            with self.subTest(label=label):
                self.assertEqual(completion.delegation_refusal(workflow, root) is None, allowed)

    def test_policy_is_validated_explicit_and_fixed_for_a_root(self):
        for bad in ({"submit_reserve": 0}, {"parent_reserve": 1, "submit_reserve": 2}, {"min_child": 2},
                    {"ready_fraction": 0.9}):
            with self.subTest(bad=bad), self.assertRaises(TreeBudgetError):
                FinishPolicy(**bad)
        with self.assertRaises(RunnerError):
            self.build({}, cap=8, show=False)
        self.build({}, cap=8)
        with self.assertRaises(WorkflowError):  # A resumed root cannot change its policy.
            self.build({}, cap=8, policy=FinishPolicy(parent_reserve=4))

    def test_official_runs_select_the_policy_and_give_every_role_report_blocker(self):
        session = SimpleNamespace(scenario={"id": "software-engineering", "roles": [
            {"id": "lead", "prompt": "Lead."}, {"id": "qa", "prompt": "QA."}]},
            agents=("lead", "qa"), human="requester", workflow=None, _root=lambda number: None)
        live = SimpleNamespace(role_limits=Limits(), tree_limits=budget.TreeLimits(), tool_calls=32, max_output_tokens=4096)
        for policy in (None, FinishPolicy(parent_reserve=4, submit_reserve=2, min_child=12, ready_fraction=0.2)):
            with (patch.object(official_live, "live_clients", return_value={}),
                  patch.object(official_live, "MultiAgentScheduler") as factory):
                official_live.make_scheduler(session, "root", None, live, SimpleNamespace(executor=None, retrieval=None),
                                             show_execution_budget=True, finish_policy=policy)
            roles = factory.call_args.kwargs["roles"]
            self.assertIs(factory.call_args.kwargs["finish_policy"], policy)
            for role in roles.values():
                self.assertEqual(role.tools[-1], "submit_for_verification")
                self.assertEqual("report_blocker" in role.tools, policy is not None)
            self.assertFalse({"create_text", "update_text", "append_text", "run_python"} & set(roles["lead"].tools))


if __name__ == "__main__":
    unittest.main()
