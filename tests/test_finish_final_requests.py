"""Finish Mode's last requests only complete or hand over (proposed 2026-11-21, pending owner review).

Live Software run on 2026-11-21 (48-request tree): QA entered Finish Mode with 2
requests left and the lead with 2 left; both spent them on read_text and the run
ended "attempts budget exhausted" with no submission and no blocker report.
Scripted agents only; no model capability is claimed.
"""

import unittest

from agent_lab import budget, completion
from agent_lab.budget import FinishPolicy
from agent_lab.deepseek import DeepSeekClient
from agent_lab.evaluation.official_live import review_proposal
from agent_lab.runner import Limits
from agent_lab.scheduler import MultiAgentScheduler, Role
import test_completion_protocol as protocol
from test_completion_protocol import Agent, child_offer, context, contract, last_sha, offered, reply, tool_results


def reader_qa(give_up=False):
    """Writes a report and notes; in Finish Mode rereads its files whenever reading is offered (the live behaviour)."""
    def decide(payload, n, state):
        if n == 1:
            return reply(("create_text", {"path": "QA_REPORT.md", "content": "Race condition: lost updates"}))
        found = last_sha(payload)
        if found and found[0] == "QA_REPORT.md":
            state["report"] = found
        terms = contract(payload)
        if not (terms and terms["finish_mode"]["active"]):
            return reply(("create_text", {"path": f"notes{n}.txt", "content": f"check {n}"}))
        if "read_text" in offered(payload):
            state["read"] = state.get("read", 1) + 1
            return reply(("read_text", {"path": f"notes{state['read']}.txt"}))
        if give_up:  # Ignores the final instruction and keeps working.
            return reply(("create_text", {"path": f"extra{n}.txt", "content": "more checks"}))
        path, sha = state["report"]
        return reply(("offer_artifact", {"path": path, "target_task": context(payload)["parent_task_id"],
                                         "expected_sha256": sha}),
                     ("submit_for_verification", {"summary": "QA found a lost-update race; see QA_REPORT.md"}))
    return decide


def reading_lead(payload, n, state):
    """Delegates QA once, then rereads whenever reading is offered; at the end submits or reports a blocker."""
    if n == 1:
        return reply(("delegate_task", {"assignee": "qa", "title": "Test the booking tool adversarially"}))
    offer = child_offer(payload)
    if offer and not state.get("accepted") and "accept_artifact" in offered(payload):
        state["accepted"] = True
        return reply(("accept_artifact", {"artifact_id": offer["artifact_id"], "path": "QA_REPORT.md"}))
    if "read_text" in offered(payload):
        return reply(("read_text", {"path": f"review{n}.txt"}))
    if any("was not completed or replaced" in r.get("error", "") for r in tool_results(payload)):
        return reply(("report_blocker", {"summary": "QA did not finish; its partial report shows a lost-update race. "
                                                   "Booking code exists but is not verified."}))
    return reply(("submit_for_verification", {"summary": "Booking tool delivered with the QA report"}))


class FinalRequests(unittest.TestCase):
    setUp = protocol.CompletionProtocol.setUp
    drive = protocol.CompletionProtocol.drive
    task_of = protocol.CompletionProtocol.task_of
    events = protocol.CompletionProtocol.events

    def build(self, agents, *, cap, policy=FinishPolicy()):
        tools = {"lead": ("delegate_task", "accept_artifact", "read_text", "post_message", "retry_failed_task"),
                 "dev": ("create_text", "read_text", "offer_artifact"),
                 "qa": ("create_text", "read_text", "offer_artifact")}
        delegates = {"lead": ("dev", "qa"), "dev": (), "qa": ()}
        roles = {actor: Role(f"{actor} fixture", (*names, "report_blocker", "submit_for_verification"),
                             delegates[actor], Limits(model_attempts=cap)) for actor, names in tools.items()}
        self.scheduler = MultiAgentScheduler(self.workflow, self.files, self.root, human="user", roles=roles,
            clients={actor: DeepSeekClient("synthetic-completion", agents.get(actor, Agent(lambda p, n, s: reply())))
                     for actor in roles},
            mode="offline_fixture", constraints=[], acceptance_id="fixture-final-requests",
            verifier_factory=lambda task: None, limits=budget.TreeLimits(model_attempts=cap),
            show_execution_budget=True, finish_policy=policy, child_retries=2)
        return self.scheduler

    def test_a_rereading_qa_still_submits_on_its_final_requests(self):
        qa = Agent(reader_qa())
        self.build({"lead": Agent(reading_lead), "qa": qa}, cap=16)
        state = self.drive()
        (qa_task,) = self.task_of("qa")
        self.assertEqual(state["needs"][0], {"task": qa_task["id"], "kind": "independent_verification"})
        (final,) = self.events("final_requests_entered", qa_task["id"])
        self.assertEqual(final[1]["tools"], ["offer_artifact", "report_blocker", "submit_for_verification"])
        last = qa.requests[-1]
        self.assertNotIn("read_text", offered(last))
        self.assertTrue(contract(last)["finish_mode"]["final_requests"])
        self.assertIn("Final requests", contract(last)["finish_mode"]["instruction"])
        review_proposal(self.scheduler, qa_task["id"], "accept", "Reviewer accepted the QA report")
        state = self.drive()
        self.assertEqual(state["needs"][0], {"task": self.root, "kind": "independent_verification"})
        review_proposal(self.scheduler, self.root, "accept", "Requester accepted")
        self.assertEqual(self.workflow.task(self.root, "user")["state"], "succeeded")

    def test_a_rereading_lead_with_a_failed_child_ends_with_an_honest_blocker(self):
        self.build({"lead": Agent(reading_lead), "qa": Agent(reader_qa(give_up=True))}, cap=16)
        state = self.drive()
        (qa_task,) = self.task_of("qa")
        self.assertEqual(qa_task["state"], "failed")
        root = self.workflow.task(self.root, "user")
        self.assertEqual(root["state"], "failed")
        self.assertTrue(self.events("final_requests_entered", self.root))
        reasons = [detail for _, detail in self.events("failed", self.root)]
        evidence = (root.get("evidence") or "") + str(reasons) + str(state)
        self.assertIn("Blocker reported by the agent", evidence)
        self.assertNotIn("attempts budget exhausted", evidence)

    def test_final_requests_start_at_the_submission_reserve_and_keep_handoff(self):
        policy = FinishPolicy()
        base = {"phase": "finish", "reason": "x", "own_reserve": 3, "finish_window": 4, "policy": policy}
        allowed = {"read_text", "post_message", "offer_artifact", "accept_artifact", "report_blocker",
                   "submit_for_verification", "create_text"}
        wide = completion.offered_tools(allowed, base | {"available": 3, "final": False})
        narrow = completion.offered_tools(allowed, base | {"available": 2, "final": True})
        self.assertIn("read_text", wide)
        self.assertEqual(narrow, {"offer_artifact", "accept_artifact", "report_blocker", "submit_for_verification"})
        self.assertIsNone(completion.offered_tools(allowed, base | {"phase": "working", "available": 9}))


if __name__ == "__main__":
    unittest.main()
