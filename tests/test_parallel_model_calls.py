"""Opt-in overlapping provider calls for independent ready tasks (proposed 2026-11-21, pending owner review).

Scripted transports with real thread synchronisation prove that two provider
calls are in flight at the same time; they say nothing about HKGAI's own
concurrency limits or model quality. Selection, reservation, response
recording and tool effects must stay on the controller thread.
"""

import hashlib
import itertools
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from agent_lab import budget
from agent_lab.budget import FinishPolicy
from agent_lab.core import Workflow
from agent_lab.deepseek import DeepSeekClient, ProviderError
from agent_lab.evaluation import official_live
from agent_lab.evaluation.official_live import advance, reconcile, review_proposal
from agent_lab.files import FileTools
from agent_lab.runner import Limits, PreparedTurn, RunnerError
from agent_lab.scheduler import MultiAgentScheduler, Role

_IDS = itertools.count()
ROOT_TOOLS = ("delegate_task", "accept_artifact", "read_text", "ask_human", "report_blocker", "submit_for_verification")
CHILD_TOOLS = ("create_text", "offer_artifact", "ask_human", "report_blocker", "submit_for_verification")


def reply(*calls, tokens=5):
    tool_calls = [{"id": f"c{next(_IDS)}", "type": "function",
                   "function": {"name": name, "arguments": json.dumps(args)}} for name, args in calls]
    return json.dumps({"id": "r", "model": "synthetic-parallel", "usage": {
        "prompt_tokens": tokens - 1, "completion_tokens": 1, "total_tokens": tokens},
        "choices": [{"finish_reason": "tool_calls",
                     "message": {"role": "assistant", "content": None, "tool_calls": tool_calls}}]}).encode()


def context(payload):
    return json.loads(json.loads(payload)["messages"][1]["content"])


def bodies(payload):
    found = []
    for message in json.loads(payload)["messages"]:
        if message["role"] == "user":
            try:
                body = json.loads(message["content"])
            except ValueError:
                continue
            if isinstance(body, dict):
                found.append(body)
    return found


def receipts(payload):
    out = []
    for message in json.loads(payload)["messages"]:
        if message["role"] == "tool":
            result = json.loads(message["content"])
            if result.get("ok") and {"path", "sha256"} <= set(result.get("result") or {}):
                out.append(result["result"])
    return out


class Probe:
    """Counts provider calls in flight across threads and records which thread made each call."""

    def __init__(self, delay=0.15):
        self.lock, self.inflight, self.peak, self.delay = threading.Lock(), 0, 0, delay
        self.threads, self.calls = [], 0

    def __call__(self, inner):
        def transport(payload):
            with self.lock:
                self.inflight += 1
                self.calls += 1
                self.peak = max(self.peak, self.inflight)
                self.threads.append(threading.current_thread().name)
            try:
                time.sleep(self.delay)
                return inner(payload)
            finally:
                with self.lock:
                    self.inflight -= 1
        return transport


def worker(name, *, barrier=None, fail=None):
    """Writes one file, then offers it to the parent and submits. `barrier` proves overlap of the first call."""
    state = {"n": 0}

    def decide(payload):
        if fail and not state.get("failed"):
            state["failed"] = True
            raise fail  # The failed attempt is not a step of the worker's script.
        state["n"] += 1
        if state["n"] == 1:
            if barrier is not None:
                barrier.wait(timeout=3)  # Passes only while the sibling's call is also in flight.
            return reply(("create_text", {"path": "part.md", "content": f"written by {name}"}))
        mine = receipts(payload)[-1]
        return reply(("offer_artifact", {"path": mine["path"], "target_task": context(payload)["parent_task_id"],
                                         "expected_sha256": mine["sha256"]}),
                     ("submit_for_verification", {"summary": f"{name} delivered part.md"}))
    return decide


def fanout_root(children, dependent=False):
    """Delegates `children` in one batch (independent), or one after another after acceptance (dependent)."""
    state = {"n": 0, "delegated": 0, "accepted": set()}

    def decide(payload):
        state["n"] += 1
        offers = [(m["task_id"], o) for m in bodies(payload) if m.get("kind") == "child_task_result"
                  for o in m["offered_artifacts"]]
        fresh = [(t, o) for t, o in offers if o["artifact_id"] not in state["accepted"]]
        if fresh:
            for _, offer in fresh:
                state["accepted"].add(offer["artifact_id"])
            return reply(*[("accept_artifact", {"artifact_id": o["artifact_id"], "path": f"in/{t[:6]}.md"})
                           for t, o in fresh])
        if not dependent and state["delegated"] == 0:
            state["delegated"] = len(children)
            return reply(*[("delegate_task", {"assignee": c, "title": f"Part {c}"}) for c in children])
        if dependent and state["delegated"] < len(children):
            child = children[state["delegated"]]
            state["delegated"] += 1
            return reply(("delegate_task", {"assignee": child, "title": f"Part {child}"}))
        return reply(("submit_for_verification", {"summary": "Integrated the accepted parts"}))
    return decide


class ParallelModelCalls(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)

    def build(self, agents, *, parallel, cap=40, children=("a", "b"), finish=True, probe=None):
        self.workflow = Workflow(self.path / f"state{next(_IDS)}.sqlite3")
        self.addCleanup(self.workflow.close)
        self.files = FileTools(self.workflow, self.path / f"files{next(_IDS)}")
        self.addCleanup(self.files.close)
        self.workflow.register_actor("requester", "human")
        for actor in ("lead", *children):
            self.workflow.register_actor(actor, "agent")
        chat = self.workflow.create_chat("group", ["requester", "lead", *children])
        self.root = self.workflow.create_task(chat, "requester", "lead", "Build the parts")
        roles = {"lead": Role("lead fixture", ROOT_TOOLS, children, Limits(model_attempts=cap))}
        roles.update({c: Role(f"{c} fixture", CHILD_TOOLS, (), Limits(model_attempts=cap)) for c in children})
        self.probe = probe or Probe()
        self.scheduler = MultiAgentScheduler(self.workflow, self.files, self.root, human="requester", roles=roles,
            clients={a: DeepSeekClient("synthetic-parallel", self.probe(agents[a])) for a in roles},
            mode="offline_fixture", constraints=[], acceptance_id="fixture-parallel",
            verifier_factory=lambda task: None, limits=budget.TreeLimits(model_attempts=cap),
            show_execution_budget=finish, finish_policy=FinishPolicy() if finish else None, child_retries=2,
            parallel_model_calls=parallel)
        return self.scheduler

    def drive(self, review="accept", steps=200):
        state = None
        for _ in range(steps):
            state = self.scheduler.step()
            if state["state"] == "running":
                continue
            waiting = [n for n in state.get("needs") or [] if n.get("kind") == "independent_verification"]
            if state["state"] != "blocked" or not waiting or review is None:
                return state
            review_proposal(self.scheduler, waiting[0]["task"], review, "Synthetic fixture review")
        return state

    def tasks(self):
        return {r["assignee"]: dict(r) for r in self.workflow.db.execute("SELECT * FROM tasks ORDER BY rowid")}

    def overlapped(self):
        return [json.loads(r[0]) for r in self.workflow.db.execute(
            "SELECT detail FROM events WHERE kind='model_calls_overlapped'")]

    # --- Overlap and dependencies -------------------------------------------------------------
    def test_two_independent_siblings_are_in_flight_at_the_same_time(self):
        barrier = threading.Barrier(2)
        agents = {"lead": fanout_root(("a", "b")), "a": worker("a", barrier=barrier), "b": worker("b", barrier=barrier)}
        self.build(agents, parallel=2)
        self.drive()
        tasks = self.tasks()
        self.assertEqual([tasks[x]["state"] for x in ("lead", "a", "b")], ["succeeded"] * 3)
        self.assertEqual(self.probe.peak, 2)  # The barrier above could only pass with both calls in flight.
        events = self.overlapped()
        self.assertTrue(events and events[0]["max_concurrent"] == 2)
        self.assertEqual({tasks["a"]["id"], tasks["b"]["id"]}, set(events[0]["tasks"]))

    def test_the_overlap_probe_cannot_pass_under_sequential_execution(self):
        barrier = threading.Barrier(2, timeout=0.5)
        agents = {"lead": fanout_root(("a", "b")), "a": worker("a", barrier=barrier), "b": worker("b", barrier=barrier)}
        self.build(agents, parallel=1)
        with self.assertRaises(threading.BrokenBarrierError):  # Proves the probe discriminates.
            self.drive()

    def test_sequential_mode_never_overlaps_and_reaches_the_same_outcome(self):
        outcomes = {}
        for parallel in (1, 2):
            agents = {"lead": fanout_root(("a", "b")), "a": worker("a"), "b": worker("b")}
            self.build(agents, parallel=parallel)
            self.drive()
            tasks = self.tasks()
            status = budget.status(self.workflow, self.root)
            calls = self.workflow.db.execute("SELECT count(*) FROM tool_calls").fetchone()[0]
            outcomes[parallel] = ({k: v["state"] for k, v in tasks.items()}, status["attempts"], status["tokens"], calls)
            if parallel == 1:
                self.assertEqual(self.probe.peak, 1)
                self.assertEqual(self.overlapped(), [])
        self.assertEqual(outcomes[1], outcomes[2])  # Same states, requests, tokens and tool calls.

    def test_a_dependent_chain_runs_one_call_at_a_time(self):
        agents = {"lead": fanout_root(("a", "b"), dependent=True), "a": worker("a"), "b": worker("b")}
        self.build(agents, parallel=2)
        self.drive()
        self.assertEqual(self.tasks()["lead"]["state"], "succeeded")
        self.assertEqual(self.probe.peak, 1)  # b is created only after a's accepted output: nothing to overlap.
        self.assertEqual(self.overlapped(), [])

    def test_a_parent_never_runs_beside_its_open_children(self):
        agents = {"lead": fanout_root(("a", "b")), "a": worker("a"), "b": worker("b")}
        self.build(agents, parallel=2)
        lead_calls = []
        original = self.scheduler.runner

        def watch(task_id):
            runner = original(task_id)
            if task_id == self.root:
                children = self.workflow.db.execute(
                    "SELECT count(*) FROM tasks WHERE parent=? AND state NOT IN ('succeeded','failed','cancelled')",
                    (self.root,)).fetchone()[0]
                lead_calls.append(children)
            return runner
        with patch.object(self.scheduler, "runner", side_effect=watch):
            self.drive()
        self.assertTrue(lead_calls and all(open_children == 0 for open_children in lead_calls))

    # --- One call per task, atomic reservations, finish windows, accounting ------------------
    def test_a_task_has_at_most_one_reserved_call_in_flight(self):
        agents = {"lead": fanout_root(("a", "b")), "a": worker("a"), "b": worker("b")}
        self.build(agents, parallel=2)
        self.drive()
        rows = self.workflow.db.execute("SELECT task, number FROM runner_turns ORDER BY task, number").fetchall()
        for task, numbers in itertools.groupby(rows, key=lambda r: r[0]):
            numbers = [n for _, n in numbers]
            self.assertEqual(numbers, list(range(1, len(numbers) + 1)))  # No duplicate or skipped reservation.
        runner = self.scheduler.runner(self.root)  # A task that is already calling cannot reserve a second call.
        self.workflow.db.execute("UPDATE runner_sessions SET status='calling' WHERE task=?", (self.root,))
        before = budget.status(self.workflow, self.root)["attempts"]
        self.assertNotIsInstance(runner.prepare(), PreparedTurn)
        self.assertEqual(budget.status(self.workflow, self.root)["attempts"], before)

    def test_shared_reservations_are_atomic_and_never_exceed_the_cap(self):
        for cap in range(8, 20):
            with self.subTest(cap=cap):
                agents = {"lead": fanout_root(("a", "b")), "a": worker("a"), "b": worker("b")}
                self.build(agents, parallel=2, cap=cap)
                self.drive()
                status = budget.status(self.workflow, self.root)
                self.assertLessEqual(status["attempts"], cap)
                reserved = self.workflow.db.execute(
                    "SELECT count(*) FROM events WHERE kind='model_attempt_reserved'").fetchone()[0]
                self.assertEqual(reserved, status["attempts"])  # Every reservation is counted exactly once.
                self.assertEqual(self.probe.calls, status["attempts"])  # No unaccounted provider call.

    def test_siblings_ignoring_their_windows_each_keep_exactly_R_window_requests(self):
        def stubborn(payload):
            return reply(("create_text", {"path": f"x{next(_IDS)}.md", "content": "more"}))
        agents = {"lead": fanout_root(("a", "b")), "a": stubborn, "b": stubborn}
        self.build(agents, parallel=2, cap=30)
        self.drive(review=None)
        for child in ("a", "b"):
            task = self.tasks()[child]
            self.assertEqual(task["state"], "failed")
            self.assertIn("Finish window used", task["evidence"])
            self.assertEqual(budget.window_used(self.workflow, task["id"]), FinishPolicy().finish_requests)

    def test_tokens_and_tool_calls_add_up_across_overlapping_calls(self):
        def heavy(name, barrier):
            inner = worker(name, barrier=barrier)
            def decide(payload):
                data = json.loads(inner(payload))
                data["usage"] = {"prompt_tokens": 90, "completion_tokens": 10, "total_tokens": 100}
                return json.dumps(data).encode()
            return decide
        barrier = threading.Barrier(2)
        agents = {"lead": fanout_root(("a", "b")), "a": heavy("a", barrier), "b": heavy("b", barrier)}
        self.build(agents, parallel=2)
        self.drive()
        sessions = self.workflow.db.execute("SELECT coalesce(sum(tokens),0) FROM runner_sessions").fetchone()[0]
        self.assertEqual(budget.status(self.workflow, self.root)["tokens"], sessions)
        recorded = sum(json.loads(r[0])["usage"]["total_tokens"] for r in self.workflow.db.execute(
            "SELECT response FROM runner_turns WHERE response IS NOT NULL"))
        self.assertEqual(sessions, recorded)
        calls = self.workflow.db.execute("SELECT count(*) FROM tool_calls").fetchone()[0]
        self.assertEqual(budget.status(self.workflow, self.root)["tool_calls"], calls)

    # --- Threads never touch the database ----------------------------------------------------
    def test_only_the_controller_thread_uses_the_database(self):
        barrier = threading.Barrier(2)
        agents = {"lead": fanout_root(("a", "b")), "a": worker("a", barrier=barrier), "b": worker("b", barrier=barrier)}
        self.build(agents, parallel=2)
        controller = threading.get_ident()
        seen = set()
        real = self.workflow.db

        class Watched:
            def __getattr__(self, name):
                seen.add(threading.get_ident())
                return getattr(real, name)
        self.workflow.db = Watched()
        try:
            self.drive()
        finally:
            self.workflow.db = real
        self.assertEqual(seen, {controller})
        self.assertTrue(any(name.startswith("model-call") for name in self.probe.threads))

    # --- Failures, crashes, uncertainty and recovery -----------------------------------------
    def test_a_failed_sibling_does_not_undo_the_successful_one(self):
        error = ProviderError("Provider HTTP status 503; no automatic retry", kind="http_status", phase="opening",
                              http_status=503)
        agents = {"lead": fanout_root(("a", "b")), "a": worker("a", fail=error), "b": worker("b")}
        self.build(agents, parallel=2)
        state = self.drive()
        self.assertEqual(state["needs"][0]["runner_state"], "provider_uncertain")
        tasks = self.tasks()
        a_session = self.workflow.db.execute("SELECT status FROM runner_sessions WHERE task=?",
                                             (tasks["a"]["id"],)).fetchone()[0]
        self.assertEqual(a_session, "provider_uncertain")
        b_written = self.workflow.db.execute(
            "SELECT count(*) FROM tool_calls WHERE task=? AND name='create_text' AND status='succeeded'",
            (tasks["b"]["id"],)).fetchone()[0]
        self.assertEqual(b_written, 1)  # b's overlapping response was applied.
        calls = self.probe.calls
        for _ in range(3):
            self.assertEqual(self.scheduler.step()["state"], "blocked")
        self.assertEqual(self.probe.calls, calls)  # Never resent automatically.
        reconcile(self.scheduler, tasks["a"]["id"], "resend", "Operator resend after HTTP 503", human="requester")
        self.drive()
        self.assertEqual(self.tasks()["lead"]["state"], "succeeded")

    def test_a_crash_while_calls_are_in_flight_leaves_both_uncertain_and_never_resends(self):
        barrier = threading.Barrier(2)

        def crashing(name):
            inner = worker(name, barrier=barrier)
            def decide(payload):
                inner(payload)
                raise KeyboardInterrupt("controller killed while waiting")  # Not a provider error.
            return decide
        agents = {"lead": fanout_root(("a", "b")), "a": crashing("a"), "b": crashing("b")}
        self.build(agents, parallel=2)
        with self.assertRaises(KeyboardInterrupt):
            self.drive()
        sessions = dict(self.workflow.db.execute("SELECT t.assignee, s.status FROM runner_sessions s JOIN tasks t "
                                                 "ON t.id=s.task"))
        self.assertEqual((sessions["a"], sessions["b"]), ("calling", "calling"))  # Durable uncertain state.
        calls = self.probe.calls
        self.workflow.db.execute("UPDATE scheduler_runs SET owner=NULL")  # The operator confirms the process exited.
        restarted = MultiAgentScheduler(self.workflow, self.files, self.root, human="requester",
            roles=self.scheduler.roles, clients=self.scheduler.clients, mode="offline_fixture", constraints=[],
            acceptance_id="fixture-parallel", verifier_factory=lambda task: None,
            limits=budget.TreeLimits(model_attempts=40), show_execution_budget=True, finish_policy=FinishPolicy(),
            child_retries=2, parallel_model_calls=2)
        state = restarted.step()
        self.assertEqual(state["state"], "blocked")
        self.assertEqual({n["runner_state"] for n in state["needs"]}, {"calling"})
        self.assertEqual(self.probe.calls, calls)

    # --- Isolation, provenance, human boundaries ---------------------------------------------
    def test_files_stay_isolated_and_handoffs_keep_their_provenance(self):
        barrier = threading.Barrier(2)
        agents = {"lead": fanout_root(("a", "b")), "a": worker("a", barrier=barrier), "b": worker("b", barrier=barrier)}
        self.build(agents, parallel=2)
        self.drive()
        tasks = self.tasks()
        rows = self.workflow.db.execute("SELECT source_task, target_task, sha256 FROM artifacts").fetchall()
        expected = {(tasks[c]["id"], self.root, hashlib.sha256(f"written by {c}".encode()).hexdigest()) for c in "ab"}
        self.assertEqual({tuple(r) for r in rows}, expected)  # Same path, separate tasks, separate content.

    def test_a_pending_review_pauses_only_its_own_task_in_overlapping_advance(self):
        slow_state = {"n": 0}

        def slow(payload):  # b keeps working (four turns) while a waits for review.
            slow_state["n"] += 1
            if slow_state["n"] < 4:
                return reply(("create_text", {"path": f"b{slow_state['n']}.md", "content": "step"}))
            return reply(("submit_for_verification", {"summary": "b done"}))
        agents = {"lead": fanout_root(("a", "b")), "a": worker("a"), "b": slow}
        self.build(agents, parallel=2)
        result = None
        for _ in range(10):
            result = advance(self.scheduler, 1)
            if any(n.get("kind") == "awaiting_verification" for n in result.get("needs") or []):
                break
        tasks = self.tasks()
        a_status = self.workflow.db.execute("SELECT status FROM runner_sessions WHERE task=?",
                                            (tasks["a"]["id"],)).fetchone()[0]
        self.assertEqual(a_status, "awaiting_verification")
        before = slow_state["n"]
        result = advance(self.scheduler, 2)  # a's review is pending; b still advances.
        self.assertGreater(slow_state["n"], before)
        self.assertIn(tasks["a"]["id"], [n["task"] for n in result["needs"]])
        self.assertEqual(self.workflow.db.execute("SELECT status FROM runner_sessions WHERE task=?",
                                                  (tasks["a"]["id"],)).fetchone()[0], "awaiting_verification")

    def test_sequential_official_advance_still_stops_at_any_human_boundary(self):
        agents = {"lead": fanout_root(("a", "b")), "a": worker("a"), "b": worker("b")}
        self.build(agents, parallel=1)
        for _ in range(10):
            result = advance(self.scheduler, 1)
            if result["state"] == "blocked":
                break
        self.assertEqual(result["state"], "blocked")
        calls = self.probe.calls
        self.assertEqual(advance(self.scheduler, 3)["state"], "blocked")
        self.assertEqual(self.probe.calls, calls)  # Unchanged default: nothing runs while a review is pending.

    def test_an_approval_request_during_overlap_releases_no_effect(self):
        def asker(payload):
            if not any(m.get("kind") == "human_response" for m in bodies(payload)):
                return reply(("ask_human", {"prompt": "Which format?"}))
            return reply(("submit_for_verification", {"summary": "Answered"}))
        barrier = threading.Barrier(2)

        def gated_asker(payload):
            barrier.wait(timeout=3)
            return asker(payload)
        agents = {"lead": fanout_root(("a", "b")), "a": gated_asker, "b": worker("b", barrier=barrier)}
        self.build(agents, parallel=2)
        state = None
        for _ in range(6):
            state = advance(self.scheduler, 1)
        tasks = self.tasks()
        self.assertEqual(tasks["a"]["state"], "waiting_input")
        self.assertEqual(self.workflow.db.execute(
            "SELECT count(*) FROM tool_calls WHERE task=? AND status='succeeded' AND name!='ask_human'",
            (tasks["a"]["id"],)).fetchone()[0], 0)  # Nothing of a's ran past its human boundary.
        self.assertTrue(self.overlapped())

    # --- Configuration --------------------------------------------------------------------------
    def test_only_one_or_two_concurrent_calls_are_accepted(self):
        agents = {"lead": fanout_root(("a", "b")), "a": worker("a"), "b": worker("b")}
        for bad in (0, 3, "2", True):
            with self.subTest(bad=bad), self.assertRaises(RunnerError):
                self.build(agents, parallel=bad)

    def test_the_official_driver_passes_the_option_and_defaults_to_sequential(self):
        session = SimpleNamespace(scenario={"id": "software-engineering", "roles": [
            {"id": "lead", "prompt": "Lead."}, {"id": "qa", "prompt": "QA."}]},
            agents=("lead", "qa"), human="requester", workflow=None, _root=lambda number: None)
        live = SimpleNamespace(role_limits=Limits(), tree_limits=budget.TreeLimits(), tool_calls=32, max_output_tokens=4096)
        for value in (1, 2):
            with (patch.object(official_live, "live_clients", return_value={}),
                  patch.object(official_live, "MultiAgentScheduler") as factory):
                official_live.make_scheduler(session, "root", None, live, SimpleNamespace(executor=None, retrieval=None),
                                             parallel_model_calls=value)
            self.assertEqual(factory.call_args.kwargs["parallel_model_calls"], value)
        with (patch.object(official_live, "live_clients", return_value={}),
              patch.object(official_live, "MultiAgentScheduler") as factory):
            official_live.make_scheduler(session, "root", None, live, SimpleNamespace(executor=None, retrieval=None))
        self.assertEqual(factory.call_args.kwargs["parallel_model_calls"], 1)


if __name__ == "__main__":
    unittest.main()
