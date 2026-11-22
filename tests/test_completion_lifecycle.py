"""Cross-scenario completion lifecycle under adversarial agents (completion-protocol-v2, proposed 2026-11-21).

Roles use the real Software / Newsroom / Securities tool sets (official_live.POLICIES,
tools_for_role, with_completion_tools) without the three service-backed tools
(run_python, search_web, retrieve_text), which these scripted agents never call;
scripted workers also have no delegation tools.
The Software lead keeps having no file tools; the Newsroom chief editor and the
Securities fund manager keep theirs.

Agents are scripted and deliberately uncooperative: they keep working or stalling
whenever any non-completion tool is offered. Assertions are lifecycle outcomes and
invariants, never the mere presence of a message. Scripted agents prove the
scheduler's structure only; they say nothing about live HKGAI compliance.
"""

import itertools
import json
from pathlib import Path
import tempfile
import unittest

from agent_lab import budget, completion
from agent_lab.budget import FinishPolicy
from agent_lab.core import Workflow
from agent_lab.deepseek import DeepSeekClient
from agent_lab.evaluation.official_live import POLICIES, review_proposal, tools_for_role, with_completion_tools
from agent_lab.files import FileTools
from agent_lab.runner import Limits, REPEAT_GRACE
from agent_lab.scheduler import MultiAgentScheduler, Role

R = FinishPolicy().finish_requests
SERVICES = {"run_python", "search_web", "retrieve_text"}
DELEGATION = {"delegate_task", "delegate_with_inputs", "retry_failed_task"}
SCENARIOS = {"software-engineering": ("lead", ("dev", "qa", "release")),
             "newsroom": ("chief_editor", ("reporter", "fact_checker", "editor")),
             "securities-fund": ("fund_manager", ("research", "risk", "marketing"))}
_IDS = itertools.count()


def reply(*calls):
    tool_calls = [{"id": f"c{next(_IDS)}", "type": "function",
                   "function": {"name": name, "arguments": json.dumps(args)}} for name, args in calls]
    return json.dumps({"id": "r", "model": "synthetic-lifecycle", "usage": {
        "prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        "choices": [{"finish_reason": "tool_calls",
                     "message": {"role": "assistant", "content": None, "tool_calls": tool_calls}}]}).encode()


def cut_off():
    return json.dumps({"id": "t", "model": "synthetic-lifecycle", "usage": {
        "prompt_tokens": 3, "completion_tokens": 4096, "total_tokens": 4099},
        "choices": [{"finish_reason": "length", "message": {"role": "assistant", "content": None}}]}).encode()


def offered(payload):
    return {tool["function"]["name"] for tool in json.loads(payload)["tools"]}


def context(payload):
    return json.loads(json.loads(payload)["messages"][1]["content"])


def terms(payload):
    return context(payload).get("execution_budget", {}).get("completion") or {}


def window(payload):
    return bool(terms(payload).get("finish_mode", {}).get("active"))


def results(payload):
    return [json.loads(m["content"]) for m in json.loads(payload)["messages"] if m["role"] == "tool"]


def receipts(payload):
    return [r["result"] for r in results(payload) if r.get("ok") and {"path", "sha256"} <= set(r.get("result") or {})]


def child_offers(payload):
    found = []
    for message in json.loads(payload)["messages"]:
        if message["role"] == "user":
            try:
                body = json.loads(message["content"])
            except ValueError:
                continue
            if isinstance(body, dict) and body.get("kind") == "child_task_result":
                found += [(body["task_id"], offer) for offer in body["offered_artifacts"]]
    return found


class Agent:
    def __init__(self, decide):
        self.decide, self.requests, self.state = decide, [], {}

    def __call__(self, payload):
        self.requests.append(payload)
        return self.decide(payload, len(self.requests), self.state)


# --- Worker behaviours (child tasks). Each writes at least one file first. -------------------------

def worker(style, summary="Delivered; evidence in the offered file"):
    def decide(payload, n, state):
        mine = receipts(payload)
        if mine:
            state["file"] = (mine[-1]["path"], mine[-1]["sha256"])
        if style == "truncate_twice" and n in (2, 3):
            return cut_off()
        if style == "blocker" and n >= 2:
            return reply(("report_blocker", {"summary": "Inputs are missing; the draft file is partial"}))
        if "create_text" in offered(payload) and not window(payload):
            if style == "comply" and "file" in state:
                return finish(payload, state, summary)
            return reply(("create_text", {"path": f"work{n}.md", "content": f"part {n}"}))  # Keeps working.
        if style == "offschema":  # Ignores the finish window: calls a tool it is no longer offered, alone.
            return reply(("create_text", {"path": f"late{n}.md", "content": "more"}))
        if style == "invalid_then_valid" and not state.get("long"):
            state["long"] = True
            return finish(payload, state, "Delivered. " + "x" * 2123)  # 2,134 characters, as live.
        if style == "no_artifacts":
            return reply(("submit_for_verification", {"summary": "No file deliverable: findings are in this summary"}))
        return finish(payload, state, summary)
    return decide


def finish(payload, state, summary):
    if "file" not in state:  # Nothing written yet (a tight budget): a completion needs no artifact.
        return reply(("submit_for_verification", {"summary": summary + " (no file was produced)"}))
    path, sha = state["file"]
    return reply(("offer_artifact", {"path": path, "target_task": context(payload)["parent_task_id"],
                                     "expected_sha256": sha}),
                 ("submit_for_verification", {"summary": summary}))


# --- Root behaviours. ------------------------------------------------------------------------------

def coordinator(children, style):
    """Delegates `children` at once, accepts what arrives, then stalls with whatever it is offered."""
    def decide(payload, n, state):
        if n == 1 and children:
            return reply(*[("delegate_task", {"assignee": child, "title": f"Deliver part {i}"})
                           for i, child in enumerate(children)])
        seen = state.setdefault("accepted", set())
        fresh = [(task, offer) for task, offer in child_offers(payload) if offer["artifact_id"] not in seen]
        tools = offered(payload)
        accepts = [("accept_artifact", {"artifact_id": offer["artifact_id"], "path": f"in/{task[:6]}/{offer['source_path']}"})
                   for task, offer in fresh]
        if window(payload):
            if style == "offschema":
                return reply(("read_text", {"path": f"nothing{n}.md"}))
            seen.update(offer["artifact_id"] for _, offer in fresh)
            if "submit_for_verification" in tools:
                return reply(*accepts, ("submit_for_verification", {"summary": "Integrated the accepted parts"}))
            return reply(("report_blocker", {"summary": "A subtask failed and was not replaced; parts are partial"}))
        if accepts:
            seen.update(offer["artifact_id"] for _, offer in fresh)
            return reply(*accepts)
        if style == "comply" and n > 1:
            return reply(("submit_for_verification", {"summary": "Integrated the accepted parts"}))
        return reply(("post_message", {"body": f"Still coordinating, step {n}"}))  # Stalls (live: reads, packaging).
    return decide


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def build(self, scenario, agents, *, cap):
        root_role, members = SCENARIOS[scenario]
        path = Path(self.directory.name) / f"{next(_IDS)}"
        path.mkdir()
        self.workflow = Workflow(path / "state.sqlite3")
        self.addCleanup(self.workflow.close)
        self.files = FileTools(self.workflow, path / "files")
        self.addCleanup(self.files.close)
        self.workflow.register_actor("requester", "human")
        for actor in (root_role, *members):
            self.workflow.register_actor(actor, "agent")
        chat = self.workflow.create_chat("group", ["requester", root_role, *members])
        self.root = self.workflow.create_task(chat, "requester", root_role, "Official task")
        def tools(actor):
            skip = SERVICES | (set() if actor == root_role else DELEGATION)  # Scripted workers never delegate.
            return tuple(t for t in with_completion_tools(tools_for_role(scenario, actor, POLICIES[scenario].tools))
                         if t not in skip)
        roles = {actor: Role(f"{actor} fixture", tools(actor), members if actor == root_role else (),
                             Limits(model_attempts=cap)) for actor in (root_role, *members)}
        self.agents = {actor: agents.get(actor) or Agent(worker("comply")) for actor in roles}
        self.scheduler = MultiAgentScheduler(self.workflow, self.files, self.root, human="requester", roles=roles,
            clients={actor: DeepSeekClient("synthetic-lifecycle", agent) for actor, agent in self.agents.items()},
            mode="offline_fixture", constraints=[], acceptance_id="fixture-lifecycle",
            verifier_factory=lambda task: None, limits=budget.TreeLimits(model_attempts=cap),
            show_execution_budget=True, finish_policy=FinishPolicy(), child_retries=2)
        self.cap = cap

    def drive(self, review=lambda task, round_: "accept", steps=600):
        rounds = {}
        for _ in range(steps):
            state = self.scheduler.step()
            if state["state"] == "running":
                continue
            needs = [n for n in state.get("needs") or [] if n.get("kind") == "independent_verification"]
            if state["state"] != "blocked" or not needs:
                return state
            task = needs[0]["task"]
            rounds[task] = rounds.get(task, 0) + 1
            decision = review(task, rounds[task])
            if decision is None:
                return state
            review_proposal(self.scheduler, task, decision, f"Synthetic fixture review: {decision}")
        self.fail("lifecycle did not terminate")

    # --- Invariants checked after every run. -----------------------------------------------------
    def events(self, kind, task=None):
        query = "SELECT task,detail FROM events WHERE kind=?" + (" AND task=?" if task else "") + " ORDER BY sequence"
        return [(row["task"], json.loads(row["detail"])) for row in
                self.workflow.db.execute(query, (kind, task) if task else (kind,))]

    def check_invariants(self):
        tasks = [dict(row) for row in self.workflow.db.execute("SELECT * FROM tasks ORDER BY rowid")]
        used = self.workflow.db.execute("SELECT attempts FROM tree_budgets WHERE root=?", (self.root,)).fetchone()[0]
        self.assertLessEqual(used, self.cap)  # I-budget: never more requests than authorised.
        reviewed = {task for task, d in self.events("human_review_recorded") if d["decision"] == "accepted"}
        replaced = {d["failed_task"] for _, d in self.events("child_replaced")}
        for task in tasks:
            if task["state"] == "succeeded":
                self.assertIn(task["id"], reviewed)  # I1/I4: success only through an accepted human review.
                children = [c for c in tasks if c["parent"] == task["id"] and c["id"] not in replaced]
                # I2: every child succeeded, or was disclosed with the proposal and explicitly waived by the reviewer.
                waived = {d["child"] for t, d in self.events("failed_subtask_waived") if t == task["id"]}
                self.assertTrue(all(c["state"] == "succeeded" or c["id"] in waived for c in children))
            if task["state"] == "failed":
                self.assertTrue(task["evidence"])  # I8: a stated reason; artifacts stay in the task.
        for actor, agent in self.agents.items():
            for payload in agent.requests:
                if window(payload):  # I5/I6: the window schema offers completion actions only.
                    self.assertLessEqual(offered(payload), completion.COMPLETION_TOOLS)
        for task, entered in self.events("finish_mode_entered"):
            later = self.workflow.db.execute(
                "SELECT count(*) FROM events WHERE task=? AND kind='model_attempt_reserved' AND sequence>("
                "SELECT max(sequence) FROM events WHERE task=? AND kind='finish_mode_entered')", (task, task)).fetchone()[0]
            self.assertLessEqual(later, R)  # I7: a finish window is bounded by R requests.
        return {task["assignee"]: task for task in tasks}

    def outcome(self, task):
        """'proposed' (own proposal reached review), 'blocker', 'exhausted' or the raw state."""
        if self.events("completion_proposed", task["id"]):
            return "proposed"
        evidence = task["evidence"] or ""
        if "Blocker reported by the agent" in evidence:
            return "blocker"
        if "Finish window used without a valid submission" in evidence:
            return "exhausted"
        return task["state"]

    # --- Matrix ------------------------------------------------------------------------------------
    def test_matrix_every_task_ends_in_review_or_an_honest_bounded_failure(self):
        expected_child = {"comply": "proposed", "stall_schema": "proposed", "invalid_then_valid": "proposed",
                          "truncate_twice": "proposed", "no_artifacts": "proposed", "blocker": "blocker",
                          "offschema": "exhausted"}
        for scenario, (root_role, members) in SCENARIOS.items():
            for child_style, root_style, width in itertools.product(expected_child, ("stall_schema", "offschema"),
                                                                     (0, 1, 2)):
                children = members[:width]
                with self.subTest(scenario=scenario, child=child_style, root=root_style, children=width):
                    agents = {root_role: Agent(coordinator(children, root_style))}
                    agents.update({c: Agent(worker(child_style)) for c in children})
                    self.build(scenario, agents, cap=24 + 18 * width)
                    self.drive()
                    tasks = self.check_invariants()
                    for child in children:
                        self.assertEqual(self.outcome(tasks[child]), expected_child[child_style])
                    root = tasks[root_role]
                    if root_style == "offschema":
                        self.assertIn(self.outcome(root), {"exhausted"})
                    elif child_style in {"blocker", "offschema"} and children:
                        # A proposal over failed children is allowed: the system discloses them with it, and only
                        # the reviewer's acceptance waives exactly those children (I2).
                        self.assertEqual(self.outcome(root), "proposed")
                        disclosed = self.events("completion_proposed", root["id"])[-1][1]["unreplaced_failed_subtasks"]
                        self.assertEqual({c["id"] for c in disclosed}, {tasks[c]["id"] for c in children})
                    else:
                        self.assertEqual(root["state"], "succeeded")  # Proposed and accepted by the review.

    def test_siblings_and_ancestors_each_keep_a_full_finish_window(self):
        for scenario, (root_role, members) in SCENARIOS.items():
            with self.subTest(scenario=scenario):
                children = members[:2]
                agents = {root_role: Agent(coordinator(children, "stall_schema"))}
                agents.update({c: Agent(worker("offschema")) for c in children})  # Both ignore their windows.
                self.build(scenario, agents, cap=40)
                self.drive()
                tasks = self.check_invariants()
                for child in children:
                    window_requests = [p for p in self.agents[child].requests if window(p)]
                    self.assertEqual(len(window_requests), R)  # Neither sibling ate the other's window.
                    self.assertEqual(self.outcome(tasks[child]), "exhausted")
                root_window = [p for p in self.agents[root_role].requests if window(p)]
                self.assertGreaterEqual(len(root_window), 1)
                # Failed children no longer remove the proposal; they are disclosed with it.
                self.assertEqual(offered(root_window[-1]), {"report_blocker", "submit_for_verification"})
                self.assertEqual(self.outcome(tasks[root_role]), "proposed")

    def test_a_sibling_blocked_in_review_keeps_its_window_while_the_other_spends_everything(self):
        def early(payload, n, state):  # Submits at once; after a later rejection it needs its window.
            mine = receipts(payload)
            if mine:
                state["file"] = (mine[-1]["path"], mine[-1]["sha256"])
            if n == 1:
                return reply(("create_text", {"path": "part.md", "content": "first"}))
            if any(m.get("kind") == "trusted_verification_failure" for m in user_bodies(payload)):
                state["after_rejection"] = state.get("after_rejection", 0) + 1
                return reply(("report_blocker", {"summary": "Rejected; cannot revise within the requests left"}))
            return finish(payload, state, "First part")

        def last_moment(payload, n, state):  # Spends its whole window, submits on the last request, stays open.
            mine = receipts(payload)
            if mine:
                state["file"] = (mine[-1]["path"], mine[-1]["sha256"])
            if not window(payload):
                return reply(("create_text", {"path": f"w{n}.md", "content": "x"}))
            if terms(payload)["finish_mode"]["requests_left_including_current"] > 1:
                return reply(("read_text", {"path": f"w{n}.md"}))  # Refused in the window; still a request.
            return finish(payload, state, "Second part, submitted at the last moment")

        for scenario, (root_role, members) in SCENARIOS.items():
            with self.subTest(scenario=scenario):
                first, second = members[:2]
                agents = {root_role: Agent(coordinator((first, second), "stall_schema")),
                          first: Agent(early), second: Agent(last_moment)}
                self.build(scenario, agents, cap=40)
                rejected = False
                for _ in range(400):
                    state = self.scheduler.step()
                    if state["state"] == "running":
                        continue
                    waiting = {n["task"] for n in state.get("needs") or [] if n.get("kind") == "independent_verification"}
                    first_task = completion_task(self.workflow, first)
                    second_task = completion_task(self.workflow, second)
                    if not rejected and {first_task, second_task} <= waiting:
                        rejected = True  # Both siblings open; the second has spent its whole window.
                        review_proposal(self.scheduler, first_task, "reject", "Synthetic fixture review: reject")
                    elif waiting and rejected:
                        review_proposal(self.scheduler, sorted(waiting)[0], "accept", "Synthetic fixture review: accept")
                    else:
                        break
                self.assertTrue(rejected)
                tasks = self.check_invariants()
                self.assertEqual(self.agents[first].state.get("after_rejection"), 1)  # It still got a request.
                self.assertIn("Blocker reported by the agent", tasks[first]["evidence"])
                self.assertEqual(self.outcome(tasks[second]), "proposed")

    # --- Replays of the recorded live failures (also run against the previous implementation). ----
    def test_replay_newsroom_chief_packages_its_files_in_the_final_requests(self):
        def chief(payload, n, state):  # Live 2026-11-21: accept / self-offer instead of submitting.
            if n == 1:
                return reply(("delegate_task", {"assignee": "reporter", "title": "Report"}))
            tools = offered(payload)
            for task, offer in child_offers(payload):
                if not state.get(offer["artifact_id"]) and "accept_artifact" in tools:
                    state[offer["artifact_id"]] = True
                    return reply(("accept_artifact", {"artifact_id": offer["artifact_id"], "path": "draft.md"}))
            for r in receipts(payload):
                state["draft"] = (r["path"], r["sha256"])
            if "offer_artifact" in tools and "draft" in state:
                return reply(("offer_artifact", {"path": state["draft"][0], "target_task": context(payload)["task_id"],
                                                 "expected_sha256": state["draft"][1]}))
            if "read_text" in tools:
                return reply(("read_text", {"path": f"refs/p{n}.md"}))
            return reply(("submit_for_verification", {"summary": "Final package: draft.md with the reporter's work"}))

        self.build("newsroom", {"chief_editor": Agent(chief), "reporter": Agent(worker("comply"))}, cap=30)
        self.drive()
        tasks = self.check_invariants()
        self.assertEqual(tasks["chief_editor"]["state"], "succeeded")
        self.assertEqual(self.workflow.db.execute(
            "SELECT count(*) FROM artifacts WHERE source_task=target_task").fetchone()[0], 0)

    def test_replay_software_qa_and_lead_reread_until_the_budget_ends(self):
        def lead(payload, n, state):  # Live full5 2026-11-21: Finish Mode spent on read_text.
            if n == 1:
                return reply(("delegate_task", {"assignee": "qa", "title": "Adversarial QA"}))
            tools = offered(payload)
            if "read_text" in tools:
                return reply(("read_text", {"path": f"QA_REPORT{n}.md"}))
            return reply(("submit_for_verification", {"summary": "QA delivered"}))

        def qa(payload, n, state):
            if n == 1:
                return reply(("create_text", {"path": "QA_REPORT.md", "content": "lost-update race found"}))
            if "read_text" in offered(payload):
                return reply(("read_text", {"path": "QA_REPORT.md" if n % 2 else "README.md"}))
            state["file"] = ("QA_REPORT.md", self.files.read_text(
                completion_task(self.workflow, "qa"), "qa", "QA_REPORT.md")["sha256"])
            return finish(payload, state, "QA report: race condition; see QA_REPORT.md")

        self.build("software-engineering", {"lead": Agent(lead), "qa": Agent(qa)}, cap=24)
        self.drive()
        tasks = self.check_invariants()
        self.assertEqual(self.outcome(tasks["qa"]), "proposed")
        self.assertEqual(tasks["lead"]["state"], "succeeded")

    def test_replay_oversized_summaries_are_corrected_inside_the_window(self):
        def lead(payload, n, state):  # Live val1: 2,134 then 2,034 characters, generic error, budget gone.
            if not window(payload):
                return reply(("post_message", {"body": f"working {n}"}))
            short = any("exceeds maximum length" in r.get("error", "") for r in results(payload))
            return reply(("submit_for_verification", {"summary": "Done" if short else "D" * 2134}))

        self.build("software-engineering", {"lead": Agent(lead)}, cap=12)
        self.drive()
        tasks = self.check_invariants()
        self.assertEqual(tasks["lead"]["state"], "succeeded")

    # --- Review, truncation, approval and repetition paths. --------------------------------------
    def test_a_rejection_with_budget_left_reopens_the_full_toolset_for_correction(self):
        def lead(payload, n, state):
            rejected = any(m.get("kind") == "trusted_verification_failure" for m in user_bodies(payload))
            if rejected and not state.get("fixed"):
                state["fixed"] = True
                state["tools_after_rejection"] = offered(payload)
                return reply(("create_text", {"path": "fix.md", "content": "correction"}))
            return reply(("submit_for_verification", {"summary": "Delivered" + (" with fix.md" if rejected else "")}))

        agent = Agent(lead)
        self.build("newsroom", {"chief_editor": agent}, cap=20)
        self.drive(review=lambda task, round_: "reject" if round_ == 1 else "accept")
        tasks = self.check_invariants()
        self.assertIn("create_text", agent.state["tools_after_rejection"])  # Correction is a real option.
        self.assertEqual(tasks["chief_editor"]["state"], "succeeded")

    def test_a_rejection_inside_the_window_allows_only_an_honest_resubmission_or_blocker(self):
        def lead(payload, n, state):
            if not window(payload):
                return reply(("post_message", {"body": f"working {n}"}))
            if any(m.get("kind") == "trusted_verification_failure" for m in user_bodies(payload)):
                return reply(("report_blocker", {"summary": "Reviewer asked for changes I cannot make in the requests left"}))
            return reply(("submit_for_verification", {"summary": "Delivered what is done"}))

        self.build("securities-fund", {"fund_manager": Agent(lead)}, cap=10)
        self.drive(review=lambda task, round_: "reject")
        tasks = self.check_invariants()
        self.assertEqual(self.outcome(tasks["fund_manager"]), "proposed")  # It proposed once ...
        self.assertIn("Blocker reported by the agent", tasks["fund_manager"]["evidence"])  # ... then failed honestly.
        self.assertEqual(self.events("human_review_recorded")[0][1]["decision"], "rejected")

    def test_a_root_cut_off_twice_is_routed_to_its_finish_window_not_stopped(self):
        def lead(payload, n, state):  # Live Software Task 2: two consecutive cut-off replies stopped the root.
            if n in (1, 2, 3):  # The window is forced after FORCE_AFTER_CUTOFFS (3) in a row.
                return cut_off()
            assert window(payload), "the forced window must be active"
            return reply(("report_blocker", {"summary": "My briefs kept exceeding the output limit; nothing delegated"}))

        self.build("software-engineering", {"lead": Agent(lead)}, cap=48)
        self.drive()
        tasks = self.check_invariants()
        self.assertEqual(self.outcome(tasks["lead"]), "blocker")
        (forced,) = self.events("finish_mode_forced")
        self.assertEqual(forced[1]["reason"], "output_limit")
        self.assertLess(self.workflow.db.execute("SELECT attempts FROM tree_budgets").fetchone()[0], 48)

    def test_replay_securities_deck_written_in_parts_after_two_cut_offs(self):
        def manager(payload, n, state):  # Live Securities Task 2: the whole HTML deck in one create_text, twice.
            notices = [m for m in user_bodies(payload) if m.get("kind") == "output_limit_notice"]
            mine = receipts(payload)
            if mine:
                state["deck"] = (mine[-1]["path"], mine[-1]["sha256"])
            if not notices:
                return cut_off()
            streak = notices[-1].get("consecutive_cut_offs", 1)
            if streak < 2 and "deck" not in state:
                return cut_off()  # The first notice did not help, as live.
            if "deck" not in state:
                assert "Make the next response small" in notices[-1]["instruction"]
                return reply(("create_text", {"path": "deck.html", "content": "<section>Slide 1</section>"}))
            if not state.get("appended"):
                state["appended"] = True
                path, sha = state["deck"]
                return reply(("append_text", {"path": path, "content": "<section>Slide 2</section>",
                                              "expected_sha256": sha}))
            return reply(("submit_for_verification", {"summary": "deck.html written in two parts"}))

        agent = Agent(manager)
        self.build("securities-fund", {"fund_manager": agent}, cap=30)
        self.drive()
        tasks = self.check_invariants()
        self.assertEqual(tasks["fund_manager"]["state"], "succeeded")
        self.assertEqual(self.events("finish_mode_forced"), [])  # Two cut-offs no longer force the window.
        import hashlib
        final = [r for p in agent.requests for r in results(p) if r.get("ok") and (r.get("result") or {}).get("path") == "deck.html"]
        self.assertEqual(final[-1]["result"]["sha256"],  # The deck's last version holds both parts.
                         hashlib.sha256(b"<section>Slide 1</section><section>Slide 2</section>").hexdigest())

    def test_a_forced_window_that_is_ignored_ends_after_R_requests(self):
        def lead(payload, n, state):
            return cut_off() if n <= 3 else reply(("read_text", {"path": f"x{n}.md"}))

        agent = Agent(lead)
        self.build("newsroom", {"chief_editor": agent}, cap=48)
        self.drive()
        tasks = self.check_invariants()
        self.assertEqual(self.outcome(tasks["chief_editor"]), "exhausted")
        self.assertEqual(len(agent.requests), 3 + R)  # Bounded: three cut-offs, then exactly R window requests.

    def test_waiting_for_the_requester_spends_no_requests_and_keeps_the_window(self):
        def lead(payload, n, state):
            if n == 1:
                return reply(("ask_human", {"prompt": "Which audience matters most?"}))
            return reply(("submit_for_verification", {"summary": "Wrote for the audience the requester named"}))

        self.build("newsroom", {"chief_editor": Agent(lead)}, cap=4)
        state = self.drive()
        self.assertEqual(state["needs"][0]["kind"], "waiting_input")
        before = budget.status(self.workflow, self.root)["attempts"]
        for _ in range(3):
            self.assertEqual(self.scheduler.step()["state"], "blocked")
        self.assertEqual(budget.status(self.workflow, self.root)["attempts"], before)  # No request while waiting.
        request = state["needs"][0]["requests"][0]["id"]
        self.workflow.respond(request, "requester", answer="Students first")
        self.drive()
        tasks = self.check_invariants()
        self.assertEqual(tasks["chief_editor"]["state"], "succeeded")

    def test_repeated_identical_outcomes_force_the_window_instead_of_stopping(self):
        def lead(payload, n, state):
            if not window(payload):
                return reply(("read_text", {"path": "missing.md"}))  # The same failing call every turn.
            return reply(("report_blocker", {"summary": "The required input file missing.md does not exist, so no analysis was possible"}))

        self.build("securities-fund", {"fund_manager": Agent(lead)}, cap=48)
        self.drive()
        tasks = self.check_invariants()
        self.assertEqual(self.outcome(tasks["fund_manager"]), "blocker")
        self.assertEqual(self.events("finish_mode_forced")[0][1]["reason"], "repeated_outcomes")
        # A notice comes first; the window is forced only after REPEAT_GRACE more identical outcomes.
        self.assertEqual(len(self.events("repeated_outcome_warned")), 1)
        reads = self.workflow.db.execute("SELECT count(*) FROM tool_calls WHERE name='read_text'").fetchone()[0]
        self.assertEqual(reads, 3 + REPEAT_GRACE)

    def test_a_rejection_reopens_a_forced_window_so_the_feedback_can_be_acted_on(self):
        def manager(payload, n, state):
            if b"trusted_verification_failure" in payload and not state.get("fixed"):
                if "create_text" not in offered(payload):
                    state["stuck"] = True  # Before the fix: only completion tools after the rejection.
                    return reply(("report_blocker", {"summary": "Rejected inside a forced finish window and unable to change any file"}))
                state["fixed"] = True
                return reply(("create_text", {"path": "proposal.md", "content": "Revised after the review"}))
            if state.get("fixed"):
                return reply(("submit_for_verification", {"summary": "proposal.md revised after the review feedback"}))
            if n <= 3:
                return cut_off()  # Three cut-offs in a row force the finish window.
            return reply(("submit_for_verification", {"summary": "First proposal inside the forced finish window"}))

        self.build("securities-fund", {"fund_manager": Agent(manager)}, cap=40)
        self.drive(review=lambda task, round_: "reject" if round_ == 1 else "accept")
        tasks = self.check_invariants()
        self.assertEqual(self.events("finish_mode_forced")[0][1]["reason"], "output_limit")
        self.assertEqual(len(self.events("finish_mode_reopened")), 1)
        self.assertFalse(self.agents["fund_manager"].state.get("stuck"))
        self.assertEqual(tasks["fund_manager"]["state"], "succeeded")

    def test_a_failed_subtask_is_disclosed_with_the_proposal_and_accepting_waives_it(self):
        def chief(payload, n, state):
            if n == 1:
                return reply(("delegate_task", {"assignee": "reporter", "title": "Report"}))
            return reply(("submit_for_verification", {"summary": "Package complete; the chief editor wrote the report"}))

        self.build("newsroom", {"chief_editor": Agent(chief), "reporter": Agent(worker("blocker"))}, cap=40)
        state = None
        seen = {}

        def review(task, round_):
            need = [n for n in self.scheduler.status().get("needs") or [] if n.get("task") == task]
            seen[task] = self.events("completion_proposed", task)[-1][1].get("unreplaced_failed_subtasks")
            return "accept"
        self.drive(review=review)
        tasks = self.check_invariants()
        reporter, chief_id = tasks["reporter"], tasks["chief_editor"]["id"]
        self.assertEqual(reporter["state"], "failed")
        self.assertEqual([c["id"] for c in seen[chief_id]], [reporter["id"]])  # The system disclosed it.
        self.assertEqual([d["child"] for _, d in self.events("failed_subtask_waived")], [reporter["id"]])
        self.assertEqual(tasks["chief_editor"]["state"], "succeeded")

    def test_a_repeat_notice_lets_the_agent_change_course_without_a_forced_finish(self):
        def lead(payload, n, state):
            if b"repeated_outcome_notice" in payload and not state.get("written"):
                state["written"] = True
                return reply(("create_text", {"path": "analysis.md", "content": "Checked the files; wrote the analysis"}))
            if state.get("written"):
                return reply(("submit_for_verification", {"summary": "analysis.md written after the missing input was confirmed"}))
            return reply(("read_text", {"path": "missing.md"}))

        self.build("securities-fund", {"fund_manager": Agent(lead)}, cap=48)
        self.drive()
        tasks = self.check_invariants()
        self.assertEqual(self.outcome(tasks["fund_manager"]), "proposed")
        self.assertEqual(self.events("finish_mode_forced"), [])
        self.assertEqual(len(self.events("repeated_outcome_warned")), 1)

    def test_a_handoff_batch_ending_in_completion_is_accepted_but_a_handoff_alone_is_not(self):
        def dev(payload, n, state):
            mine = receipts(payload)
            if mine:
                state["file"] = (mine[-1]["path"], mine[-1]["sha256"])
            if not window(payload):
                return reply(("create_text", {"path": f"w{n}.md", "content": "x"}))
            path, sha = state["file"]
            offer = ("offer_artifact", {"path": path, "target_task": context(payload)["parent_task_id"],
                                        "expected_sha256": sha})
            if not state.get("tried_alone"):
                state["tried_alone"] = True
                return reply(offer)  # A handoff alone is not a completion.
            return reply(offer, ("submit_for_verification", {"summary": "Delivered"}))

        dev_agent = Agent(dev)
        self.build("software-engineering", {"lead": Agent(coordinator(("dev",), "stall_schema")), "dev": dev_agent},
                   cap=30)
        self.drive()
        tasks = self.check_invariants()
        errors = [r["error"] for p in dev_agent.requests for r in results(p) if not r.get("ok")]
        self.assertTrue(any("offer_artifact: Finish window: offer_artifact is only accepted in a batch" in e for e in errors))
        self.assertEqual(self.outcome(tasks["dev"]), "proposed")
        self.assertEqual(tasks["lead"]["state"], "succeeded")


def user_bodies(payload):
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


def completion_task(workflow, assignee):
    return workflow.db.execute("SELECT id FROM tasks WHERE assignee=? ORDER BY rowid DESC LIMIT 1",
                               (assignee,)).fetchone()[0]


if __name__ == "__main__":
    unittest.main()
