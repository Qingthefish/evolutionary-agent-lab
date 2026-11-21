"""Finish-window guarantees at the hard limits (completion-protocol-v2, proposed 2026-11-21).

Which guarantees hold under the existing limits, without enlarging any of them:

- requests and tool calls are counted before they are used, so other open tasks'
  unspent finish windows can be held: the window is guaranteed (tests below);
- wall-clock duration and reported tokens are only known while or after a request
  runs, and human waiting counts toward duration by design: the window is NOT
  guaranteed. These tests pin the honest, bounded, labelled failure instead;
- the window is derived from persisted events, so it survives pauses, reviews,
  rejections and a process restart.

Scripted agents only; no model capability or live HKGAI compliance is claimed.
"""

import itertools
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_lab import budget, completion
from agent_lab.budget import FinishPolicy
from agent_lab.core import Workflow
from agent_lab.deepseek import DeepSeekClient, ProviderError
from agent_lab.evaluation.official_live import reconcile, review_proposal
from agent_lab.files import FileTools
from agent_lab.runner import Limits, TaskRunner
from agent_lab.scheduler import MultiAgentScheduler, Role
import test_completion_lifecycle as lc
from test_completion_lifecycle import Agent, context, finish, offered, receipts, reply, results, terms, user_bodies, window

R = FinishPolicy().finish_requests
FINISH = "Finish window used without a valid submission or blocker report"
WORKER = ("create_text", "read_text", "offer_artifact", "post_message", "report_blocker", "submit_for_verification")
PARENT = ("delegate_task", "accept_artifact", "read_text", "post_message", "offer_artifact", "retry_failed_task",
          "report_blocker", "submit_for_verification")


def heavy(tokens):
    """A reply builder reporting `tokens` total usage (the token cap counts reported usage)."""
    def build(*calls):
        data = json.loads(reply(*calls))
        data["usage"] = {"prompt_tokens": tokens - 2, "completion_tokens": 2, "total_tokens": tokens}
        return json.dumps(data).encode()
    return build


class Boundaries(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.now = [1000.0]
        self.path = Path(self.directory.name) / "run"
        self.path.mkdir()
        self.root = None

    def build(self, roles, agents, *, cap, tree=None, role=None, calls=32):
        """roles: actor -> (tools, delegates); the first actor owns the root. Rebuilding reopens the same state."""
        self.workflow = Workflow(self.path / "state.sqlite3", clock=lambda: self.now[0])
        self.addCleanup(self.workflow.close)
        self.files = FileTools(self.workflow, self.path / "files")
        self.addCleanup(self.files.close)
        actors = list(roles)
        self.workflow.register_actor("requester", "human")
        for actor in actors:
            self.workflow.register_actor(actor, "agent")
        if self.root is None:
            chat = self.workflow.create_chat("group", ["requester", *actors])
            self.root = self.workflow.create_task(chat, "requester", actors[0], "Official task")
        self.agents = {actor: agents.get(actor) or Agent(lc.worker("comply")) for actor in actors}
        limits = Limits(model_attempts=cap, **(role or {}))
        self.scheduler = MultiAgentScheduler(self.workflow, self.files, self.root, human="requester",
            roles={actor: Role(f"{actor} fixture", tools, delegates, limits, calls)
                   for actor, (tools, delegates) in roles.items()},
            clients={actor: DeepSeekClient("synthetic-boundary", agent) for actor, agent in self.agents.items()},
            mode="offline_fixture", constraints=[], acceptance_id="fixture-boundaries",
            verifier_factory=lambda task: None, limits=budget.TreeLimits(model_attempts=cap, **(tree or {})),
            show_execution_budget=True, finish_policy=FinishPolicy(), child_retries=2)
        self.cap = cap

    events = lc.Lifecycle.events
    outcome = lc.Lifecycle.outcome

    def drive(self, review=lambda task, round_: "accept", steps=400):
        return lc.Lifecycle.drive(self, review, steps)

    def task(self, actor):
        return dict(self.workflow.db.execute("SELECT * FROM tasks WHERE assignee=? ORDER BY rowid DESC LIMIT 1",
                                             (actor,)).fetchone())

    def window_requests(self, actor):
        return sum(window(p) for p in self.agents[actor].requests)

    # --- 1. Duration: not reservable; the honest outcome is a labelled, bounded failure. -----------
    def test_duration_running_out_inside_the_window_ends_it_early_and_says_so(self):
        def lead(payload, n, state):
            self.now[0] += 100  # Each request takes 100 s; the tree has 1,250 s.
            return reply(("read_text", {"path": f"x{n}.md"}))  # Never completes, inside or outside the window.

        self.build({"lead": (WORKER, ())}, {"lead": Agent(lead)}, cap=14, tree={"duration_seconds": 1250},
                   role={"duration_seconds": 10 ** 6})
        self.drive()
        lead_task = self.task("lead")
        self.assertIn(FINISH, lead_task["evidence"])
        self.assertIn("duration", lead_task["evidence"])
        self.assertLess(self.window_requests("lead"), R)  # Time, not requests, ended the window: no guarantee.

    def test_review_waiting_counts_toward_duration_and_the_scheduler_can_void_a_proposal(self):
        # Limitation by design: "Task duration budget exhausted (including human wait)".
        self.build({"lead": (WORKER, ())}, {"lead": Agent(lambda p, n, s: reply(
            ("submit_for_verification", {"summary": "Done"})))}, cap=8, role={"duration_seconds": 600})
        state = self.drive(review=lambda task, round_: None)
        self.assertEqual(state["needs"][0]["kind"], "independent_verification")
        self.now[0] += 601  # The reviewer takes longer than the task's duration.
        state = self.scheduler.step()
        self.assertEqual(self.task("lead")["state"], "failed")
        self.assertIn("duration", self.task("lead")["evidence"])
        self.assertEqual(len(self.events("completion_proposed")), 1)  # The proposal existed, but was never reviewed.

    # --- 2. Reported tokens: usage is known only after the reply. -------------------------------
    def test_a_valid_submission_whose_reply_crosses_the_token_cap_is_discarded_and_labelled(self):
        def lead(payload, n, state):
            if not window(payload):
                return reply(("read_text", {"path": f"x{n}.md"}))
            return heavy(5000)(("submit_for_verification", {"summary": "Done"}))  # Crosses the 4,000 cap.

        self.build({"lead": (WORKER, ())}, {"lead": Agent(lead)}, cap=8, tree={"reported_tokens": 4000})
        self.drive()
        self.assertEqual(self.events("completion_proposed"), [])  # "No tools released": the cap holds.
        self.assertIn(FINISH, self.task("lead")["evidence"])
        self.assertIn("token", self.task("lead")["evidence"])

    def test_tokens_can_run_out_before_the_window_starts(self):
        def lead(payload, n, state):
            return heavy(1500)(("read_text", {"path": f"x{n}.md"}))

        self.build({"lead": (WORKER, ())}, {"lead": Agent(lead)}, cap=20, tree={"reported_tokens": 4000})
        self.drive()
        evidence = self.task("lead")["evidence"]
        self.assertIn("token", evidence)
        self.assertNotIn(FINISH, evidence)  # Never reached its window: a documented limitation.
        self.assertEqual(self.window_requests("lead"), 0)

    # --- 3. Shared tree tool calls: counted before use, so they can be held. --------------------
    def test_a_sibling_burning_tool_calls_cannot_take_the_calls_a_blocked_sibling_needs(self):
        def early(payload, n, state):
            mine = receipts(payload)
            if mine:
                state["file"] = (mine[-1]["path"], mine[-1]["sha256"])
            if n == 1:
                return reply(("create_text", {"path": "part.md", "content": "first"}))
            if any(m.get("kind") == "trusted_verification_failure" for m in user_bodies(payload)):
                state["resubmitted"] = True
                return reply(("submit_for_verification", {"summary": "Resubmitted with the reviewer's note"}))
            return finish(payload, state, "First part")

        def burner(payload, n, state):  # Spends tool calls in large batches until refused, then submits late.
            if window(payload):
                mine = receipts(payload)
                return reply(("submit_for_verification", {"summary": f"Burnt {len(mine)} files"}))
            return reply(*[("create_text", {"path": f"b{n}-{i}.md", "content": "x"}) for i in range(8)])

        roles = {"lead": (PARENT, ("first", "second")), "first": (WORKER, ()), "second": (WORKER, ())}
        agents = {"lead": Agent(lc.coordinator(("first", "second"), "stall_schema")), "first": Agent(early),
                  "second": Agent(burner)}
        self.build(roles, agents, cap=40, tree={"tool_calls": 40}, calls=40)
        rejected = False
        for _ in range(400):
            state = self.scheduler.step()
            if state["state"] == "running":
                continue
            waiting = sorted(n["task"] for n in state.get("needs") or [] if n.get("kind") == "independent_verification")
            first = self.task("first")["id"]
            if not rejected and first in waiting and len(waiting) == 2:
                rejected = True
                review_proposal(self.scheduler, first, "reject", "Synthetic fixture review: reject")
            elif waiting:
                review_proposal(self.scheduler, waiting[0], "accept", "Synthetic fixture review: accept")
            else:
                break
        self.assertTrue(rejected)
        self.assertTrue(self.agents["first"].state.get("resubmitted"))
        used = self.workflow.db.execute("SELECT tool_calls FROM tree_budgets").fetchone()[0]
        self.assertLessEqual(used, 40)
        self.assertEqual(self.task("first")["state"], "succeeded")
        refusals = [r["error"] for p in self.agents["second"].requests for r in results(p) if not r.get("ok")]
        self.assertTrue(any("kept for other open tasks' finish windows" in e for e in refusals))

    def test_nested_tasks_each_keep_tool_calls_for_their_completion(self):
        def mid(payload, n, state):
            if n == 1:
                return reply(("delegate_task", {"assignee": "leaf", "title": "Leaf work"}))
            if "submit_for_verification" not in offered(payload):  # Over the failed leaf only a blocker is offered.
                return reply(("report_blocker", {"summary": "The leaf failed; mid-level work is partial"}))
            return reply(("submit_for_verification", {"summary": "Mid level delivered"}))

        def leaf(payload, n, state):
            if window(payload):
                return reply(("report_blocker", {"summary": "The leaf could not finish its files within its requests"}))
            return reply(*[("create_text", {"path": f"l{n}-{i}.md", "content": "x"}) for i in range(8)])

        roles = {"lead": (PARENT, ("mid",)), "mid": (PARENT, ("leaf",)), "leaf": (WORKER, ())}
        agents = {"lead": Agent(lc.coordinator(("mid",), "stall_schema")), "mid": Agent(mid), "leaf": Agent(leaf)}
        self.build(roles, agents, cap=60, tree={"tool_calls": 50}, calls=60)
        self.drive()
        self.assertEqual(self.outcome(self.task("leaf")), "blocker")
        mid_task, lead_task = self.task("mid"), self.task("lead")
        self.assertEqual(self.outcome(mid_task), "blocker")  # Over a failed leaf only a blocker was offered ...
        self.assertTrue(self.window_requests("mid"))  # ... and mid still had requests and calls for it.
        self.assertEqual(self.outcome(lead_task), "blocker")
        self.assertLessEqual(self.workflow.db.execute("SELECT tool_calls FROM tree_budgets").fetchone()[0], 50)

    def test_a_task_short_of_its_own_tool_calls_enters_its_window_in_time(self):
        def chatty(schema):
            def decide(payload, n, state):  # One call per request; live chief editor used 57 of 80.
                if window(payload) and schema:
                    return reply(("submit_for_verification", {"summary": "Coordinated; see the messages"}))
                return reply(("post_message", {"body": f"update {n}"}))
            return decide

        for schema, expected in ((True, "proposed"), (False, "exhausted")):
            with self.subTest(schema_following=schema):
                self.setUp()
                agent = Agent(chatty(schema))
                self.build({"lead": (WORKER, ())}, {"lead": agent}, cap=40, calls=12)
                self.drive()
                lead_task = self.task("lead")
                self.assertEqual(self.outcome(lead_task), expected)
                self.assertNotIn("Task tool-call budget cannot accommodate", lead_task["evidence"] or "")
                self.assertEqual(self.window_requests("lead"), 1 if schema else R)

    # --- 4. Persistence across pauses, review, rejection and restart. ---------------------------
    def stalling(self):
        def lead(payload, n, state):
            return reply(("read_text", {"path": f"x{n}.md"}))  # Ignores even its window.
        return Agent(lead)

    def test_a_restart_inside_the_window_continues_it_instead_of_opening_a_new_one(self):
        self.build({"lead": (WORKER, ())}, {"lead": self.stalling()}, cap=10)
        while self.window_requests("lead") < 1:
            self.scheduler.step()
        before = self.window_requests("lead")
        self.workflow.close()
        self.files.close()
        self.build({"lead": (WORKER, ())}, {"lead": self.stalling()}, cap=10)  # A new process, the same state.
        self.drive()
        self.assertEqual(before + self.window_requests("lead"), R)  # Exactly R across both processes.
        self.assertIn(FINISH, self.task("lead")["evidence"])
        self.assertEqual(len(self.events("finish_mode_entered")), 1)

    def test_a_rejection_after_a_restart_keeps_the_window_accounting(self):
        def lead(payload, n, state):
            if not window(payload):
                return reply(("read_text", {"path": f"x{n}.md"}))
            if any(m.get("kind") == "trusted_verification_failure" for m in user_bodies(payload)):
                return reply(("report_blocker", {"summary": "Cannot revise the draft within the requests left in this task"}))
            return reply(("submit_for_verification", {"summary": "Done"}))

        self.build({"lead": (WORKER, ())}, {"lead": Agent(lead)}, cap=10)
        self.drive(review=lambda task, round_: None)
        self.workflow.close()
        self.files.close()
        self.build({"lead": (WORKER, ())}, {"lead": Agent(lead)}, cap=10)
        review_proposal(self.scheduler, self.root, "reject", "Synthetic fixture review: reject")
        self.drive()
        self.assertEqual(self.outcome(self.task("lead")), "proposed")
        self.assertIn("Blocker reported by the agent", self.task("lead")["evidence"])

    def test_a_provider_failure_inside_the_window_is_paused_and_counts_against_the_window(self):
        def lead(payload, n, state):
            if not window(payload):
                return reply(("read_text", {"path": f"x{n}.md"}))
            if not state.get("failed"):
                state["failed"] = True
                raise ProviderError("Provider HTTP status 502; no automatic retry", kind="http_status",
                                    phase="opening", http_status=502)
            return reply(("submit_for_verification", {"summary": "Done after the resend"}))

        agent = Agent(lead)
        self.build({"lead": (WORKER, ())}, {"lead": agent}, cap=10)
        state = self.drive()
        self.assertEqual(state["needs"][0]["runner_state"], "provider_uncertain")
        reconcile(self.scheduler, self.root, "resend", "Operator resend after HTTP 502", human="requester")
        self.drive()
        self.assertEqual(self.task("lead")["state"], "succeeded")
        self.assertEqual(budget.window_used(self.workflow, self.root), 2)  # The failed request used the window too.

    def test_waiting_for_the_requester_inside_the_window_spends_no_window_request(self):
        def lead(payload, n, state):
            if not window(payload):
                return reply(("read_text", {"path": f"x{n}.md"}))
            if not state.get("asked"):  # ask_human is closed in the window; the batch is refused.
                state["asked"] = True
                return reply(("ask_human", {"prompt": "Which audience?"}),
                             ("submit_for_verification", {"summary": "Done"}))
            return reply(("submit_for_verification", {"summary": "Done"}))

        self.build({"lead": (WORKER + ("ask_human",), ())}, {"lead": Agent(lead)}, cap=10)
        self.drive()
        self.assertEqual(self.task("lead")["state"], "succeeded")
        errors = [r["error"] for p in self.agents["lead"].requests for r in results(p) if not r.get("ok")]
        self.assertTrue(any(e.startswith("ask_human: Finish window") for e in errors))

    # --- 5. A blocker is the task's final evidence: it must explain the failure. ----------------
    def test_placeholder_blockers_are_refused_and_a_real_explanation_is_kept(self):
        def risk(payload, n, state):  # Live Securities 2026-11-21: report_blocker {"summary": "placeholder"}.
            if not window(payload):
                return reply(("read_text", {"path": f"x{n}.md"}))
            if not any("not a meaningful failure explanation" in r.get("error", "") for r in results(payload)):
                return reply(("report_blocker", {"summary": "placeholder"}))
            return reply(("report_blocker", {"summary": "Stress table computed in stress.py; the written risk "
                                                        "assessment is missing because the requests ran out"}))

        agent = Agent(risk)
        self.build({"lead": (WORKER, ())}, {"lead": agent}, cap=10)
        self.drive()
        evidence = self.task("lead")["evidence"]
        self.assertIn("Blocker reported by the agent: Stress table computed", evidence)
        self.assertNotIn("placeholder", evidence)
        errors = [r["error"] for p in agent.requests for r in results(p) if not r.get("ok")]
        self.assertTrue(any(e.startswith("report_blocker: summary is not a meaningful failure explanation: it is "
                                         "placeholder text") for e in errors))

    def test_a_model_that_only_sends_placeholders_still_ends_honestly_and_bounded(self):
        agent = Agent(lambda p, n, s: reply(("report_blocker", {"summary": "TODO"})) if window(p)
                      else reply(("read_text", {"path": f"x{n}.md"})))
        self.build({"lead": (WORKER, ())}, {"lead": agent}, cap=10)
        self.drive()
        lead_task = self.task("lead")
        self.assertEqual(lead_task["state"], "failed")
        self.assertIn(FINISH, lead_task["evidence"])  # A labelled failure with no invented explanation.
        self.assertNotIn("Blocker reported", lead_task["evidence"])
        self.assertLessEqual(self.window_requests("lead"), R)

    def test_blocker_explanations_are_judged_by_content_not_role(self):
        from agent_lab.gateway import blocker_summary_problem
        for bad in ("placeholder", "TODO", "n/a", "Blocked.", "x x x x x x x x", "Leaf could not finish", " ",
                    "无法完成"):
            with self.subTest(bad=bad):
                self.assertIsNotNone(blocker_summary_problem(bad))
        for good in ("Inputs are missing; the draft file is partial",
                     "研究报告已完成，但风险评估缺失，因为请求次数已用完，无法继续撰写。 Missing: risk_assessment.md",
                     "研究报告已经完成但风险评估文件缺失因为本任务的请求次数已经全部用完无法继续撰写"):
            with self.subTest(good=good):
                self.assertIsNone(blocker_summary_problem(good))

    # --- Validity of the matrix: mutants of the mechanism must be caught. -----------------------
    def test_the_lifecycle_tests_catch_each_mutant_of_the_mechanism(self):
        real_phase, real_budget = completion.phase, budget.finish_budget
        mutants = {
            "no holds for other open tasks": [patch.object(budget, "held_for_others", lambda *a, **k: 0)],
            "window not sticky": [patch.object(completion, "window_record",
                                               lambda *a, **k: {"entered": False, "used": 0, "forced": None})],
            "every tool offered in the window": [patch.object(completion, "offered_tools", lambda *a, **k: None)],
            "role limit ignored": [patch.object(completion, "phase",
                                                lambda w, t, role_left=None: real_phase(w, t))],
            "tool scarcity ignored": [patch.object(budget, "finish_budget",
                                                   lambda w, t: (lambda i: i and {**i, "tool_calls_left": 10 ** 6})(
                                                       real_budget(w, t)))],
            "no forced finish": [patch.object(TaskRunner, "_force_finish", lambda self, reason: None)],
        }
        names = ["test_siblings_and_ancestors_each_keep_a_full_finish_window",
                 "test_a_sibling_blocked_in_review_keeps_its_window_while_the_other_spends_everything",
                 "test_a_forced_window_that_is_ignored_ends_after_R_requests",
                 "test_a_root_cut_off_twice_is_routed_to_its_finish_window_not_stopped",
                 "test_replay_newsroom_chief_packages_its_files_in_the_final_requests",
                 "test_a_task_short_of_its_own_tool_calls_enters_its_window_in_time",
                 "test_budget_sweep_every_limit_stop_comes_after_a_finish_window"]
        caught = {}
        for label, patches in mutants.items():
            suite = unittest.TestSuite()
            for name in names:
                owner = Boundaries if hasattr(Boundaries, name) else lc.Lifecycle
                suite.addTest(owner(name))
            result = unittest.TestResult()
            for active in patches:
                active.start()
            try:
                suite.run(result)
            finally:
                for active in patches:
                    active.stop()
            caught[label] = len(result.failures) + len(result.errors)
        self.assertTrue(all(caught.values()), caught)

    # --- Budget sweep with tight caps and smaller role limits. ----------------------------------
    def test_budget_sweep_every_limit_stop_comes_after_a_finish_window(self):
        cases = 0
        for cap, role_cap, tight, width, style in itertools.product(range(6, 46, 6), (None, "half"), (False, True),
                                                                    (0, 1, 2), ("offschema", "stall_schema")):
            self.setUp()
            members = ("a", "b")[:width]
            roles = {"lead": (PARENT, members) if members else (WORKER, ())}
            roles.update({m: (WORKER, ()) for m in members})
            agents = {"lead": Agent(lc.coordinator(members, style))}
            agents.update({m: Agent(lc.worker(style)) for m in members})
            self.build(roles, agents, cap=cap, calls=max(2, cap // 3) if tight else cap * 4)
            if role_cap == "half":  # A role limit below the tree share, as a generic runtime may configure.
                for role in self.scheduler.roles.values():
                    object.__setattr__(role, "limits", Limits(model_attempts=max(1, cap // 2)))
            self.drive()
            cases += 1
            used = self.workflow.db.execute("SELECT attempts FROM tree_budgets").fetchone()[0]
            self.assertLessEqual(used, cap)
            for task in (dict(r) for r in self.workflow.db.execute("SELECT * FROM tasks")):
                if task["state"] != "failed":
                    continue
                evidence = task["evidence"] or ""
                with self.subTest(cap=cap, role=role_cap, tight=tight, width=width, style=style, task=task["assignee"]):
                    # Reachability: a limit stop always comes after the task had its finish window.
                    self.assertTrue("Blocker reported" in evidence or FINISH in evidence, evidence)
        self.assertEqual(cases, 7 * 2 * 2 * 3 * 2)


if __name__ == "__main__":
    unittest.main()
