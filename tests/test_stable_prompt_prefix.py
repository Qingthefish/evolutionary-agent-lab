"""Opt-in stable prompt prefix: the live budget moves to a trailing message (synthetic; no provider).

By default the runner rewrites the first task message with the current execution budget on
every request, so everything after it differs from the previous request. With the opt-in, the
stored transcript stays append-only and the same budget view is sent as the last message.
"""

from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from agent_lab.budget import TreeLimits, configure
from agent_lab.core import Workflow
from agent_lab.deepseek import DeepSeekClient
from agent_lab.evaluation import official_live
from agent_lab.files import FileTools
from agent_lab.gateway import ToolGateway
from agent_lab.runner import CURRENT_BUDGET_SCOPE, Limits, RunnerError, TaskRunner
from agent_lab.scheduler import MultiAgentScheduler, Role
from test_runner import Script, response, tool


def note(identifier, n):
    return tool("create_text", {"path": f"part{n}.txt", "content": f"Part {n}\n"}, identifier)


class StablePromptPrefixTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path, self.now = Path(directory.name), [1000.0]
        self.w = Workflow(self.path / "state.sqlite3", clock=lambda: self.now[0])
        self.addCleanup(self.w.close)
        for actor, kind in (("human", "human"), ("writer", "agent")):
            self.w.register_actor(actor, kind)
        chat = self.w.create_chat("group", ["human", "writer"])
        self.task = self.w.create_task(chat, "human", "writer", "Write the parts")
        self.w.start_task(self.task, "writer")
        configure(self.w, self.task, TreeLimits(model_attempts=9, tool_calls=12, tasks=2))
        self.f = FileTools(self.w, self.path / "files")
        self.addCleanup(self.f.close)

    def runner(self, script, *, stable):
        gateway = ToolGateway(self.w, self.f, self.task, "writer", human="human",
                              allowed=("create_text", "submit_for_verification"), max_calls=12)
        return TaskRunner(gateway, DeepSeekClient("explicit-synthetic", script), mode="offline_fixture",
                          constraints=["Keep the original constraint"], limits=Limits(model_attempts=9),
                          show_execution_budget=True, stable_prompt_prefix=stable)

    def turns(self, stable, count=3):
        script = Script([response([note(f"c{n}", n)]) for n in range(count)])
        runner = self.runner(script, stable=stable)
        for _ in range(count):
            self.now[0] += 7
            runner.step()
        return script.requests

    def stored(self):
        return json.loads(self.w.db.execute("SELECT transcript FROM runner_sessions").fetchone()[0])

    # --- Default unchanged ----------------------------------------------------------------------
    def test_default_rewrites_the_first_task_message_as_before(self):
        requests = self.turns(stable=False)
        for request in requests:
            self.assertIn("execution_budget", json.loads(request["messages"][1]["content"]))
            self.assertNotEqual(json.loads(request["messages"][-1]["content"]).get("kind"), "execution_budget")
        # The discriminating property: the first task message differs on every request.
        self.assertNotEqual(requests[0]["messages"][1], requests[1]["messages"][1])

    # --- Opt-in ---------------------------------------------------------------------------------
    def test_every_request_extends_the_previous_one_unchanged(self):
        requests = self.turns(stable=True)
        for before, after in zip(requests, requests[1:]):
            sent_before = before["messages"][:-1]  # Without its trailing budget view.
            self.assertEqual(after["messages"][:len(sent_before)], sent_before)
            self.assertEqual(before["tools"], after["tools"])
        for request in requests:
            self.assertNotIn("execution_budget", json.loads(request["messages"][1]["content"]))
            last = json.loads(request["messages"][-1]["content"])
            self.assertEqual((request["messages"][-1]["role"], last["kind"], last["scope"]),
                             ("user", "execution_budget", CURRENT_BUDGET_SCOPE))

    def test_the_model_sees_the_same_budget_and_task_context(self):
        stable = self.turns(stable=True, count=1)[0]["messages"]
        self.tearDown_and_reset()
        default = self.turns(stable=False, count=1)[0]["messages"]
        default_context = json.loads(default[1]["content"])
        budget_view = default_context.pop("execution_budget")
        self.assertEqual(json.loads(stable[1]["content"]), default_context)
        self.assertEqual(json.loads(stable[-1]["content"])["execution_budget"], budget_view)
        self.assertIn("completion_proposal", budget_view)
        self.assertEqual(len(stable), len(default) + 1)

    def tearDown_and_reset(self):
        self.doCleanups()
        self.setUp()

    def test_budget_counts_stay_current_on_each_request(self):
        requests = self.turns(stable=True)
        left = [json.loads(r["messages"][-1]["content"])["execution_budget"]["task"]["model_attempts_left_after_current"]
                for r in requests]
        self.assertEqual(left, [8, 7, 6])
        # Only the latest view is ever sent: earlier views are not kept in the conversation.
        for request in requests:
            kinds = [json.loads(m["content"]).get("kind") for m in request["messages"] if m["role"] == "user"
                     and m["content"].startswith("{")]
            self.assertEqual(kinds.count("execution_budget"), 1)

    def test_stored_transcript_holds_no_budget_but_the_request_record_shows_what_was_sent(self):
        requests = self.turns(stable=True, count=2)
        transcript = self.stored()
        self.assertNotIn("execution_budget", json.loads(transcript[1]["content"]))
        self.assertFalse(any(m["role"] == "user" and "execution_budget" in m["content"] for m in transcript))
        recorded = [json.loads(r[0]) for r in self.w.db.execute("SELECT request FROM runner_turns ORDER BY number")]
        self.assertEqual([r["messages"] for r in recorded], [r["messages"] for r in requests])

    def test_resume_switches_layout_without_a_configuration_change(self):
        script = Script([response([note("a", 1)]), response([note("b", 2)]), response([note("c", 3)])])
        self.runner(script, stable=False).step()
        config = self.w.db.execute("SELECT config FROM runner_sessions").fetchone()[0]
        self.runner(script, stable=True).step()  # Resuming existing state with the opt-in.
        self.assertEqual(self.w.db.execute("SELECT config FROM runner_sessions").fetchone()[0], config)
        second = script.requests[1]["messages"]
        self.assertNotIn("execution_budget", json.loads(second[1]["content"]))
        self.assertEqual(json.loads(second[-1]["content"])["kind"], "execution_budget")
        self.runner(script, stable=False).step()  # And back again.
        third = script.requests[2]["messages"]
        self.assertIn("execution_budget", json.loads(third[1]["content"]))
        self.assertEqual(self.w.db.execute("SELECT count(*) FROM tool_calls").fetchone()[0], 3)

    def test_option_is_validated(self):
        for bad in (None, 1, "yes"):
            with self.assertRaises(RunnerError):
                self.runner(Script([]), stable=bad)

    # --- Wiring -----------------------------------------------------------------------------------
    def test_scheduler_passes_the_option_to_every_runner(self):
        roles = {"writer": Role("Write parts", ("create_text", "submit_for_verification"), (), Limits(model_attempts=9))}
        for stable in (False, True):
            scheduler = MultiAgentScheduler(
                self.w, self.f, self.task, human="human", roles=roles,
                clients={"writer": DeepSeekClient("explicit-synthetic", Script([]))}, mode="offline_fixture",
                constraints=[], verifier_factory=lambda task: None, acceptance_id="stable-prefix-test",
                limits=TreeLimits(model_attempts=9, tool_calls=12, tasks=2), show_execution_budget=True,
                stable_prompt_prefix=stable)
            self.assertIs(scheduler.runner(self.task).stable_prompt_prefix, stable)
        with self.assertRaises(RunnerError):
            MultiAgentScheduler(self.w, self.f, self.task, human="human", roles=roles, clients={}, mode="offline_fixture",
                                constraints=[], verifier_factory=lambda task: None, acceptance_id="x",
                                stable_prompt_prefix="yes")

    def official_kwargs(self, *flags):
        services = SimpleNamespace(retrieval=None, executor=None, close=lambda: None)

        @contextmanager
        def workflow(_):
            yield Mock()
        with (patch.object(official_live, "OfficialMidTestPlan"), patch.object(official_live, "_workflow", workflow),
              patch.object(official_live, "OfficialScenarioSession"), patch.object(official_live, "_posted_root"),
              patch.object(official_live, "runtime_config"), patch.object(official_live, "FileTools"),
              patch.object(official_live, "runtime_services", return_value=services),
              patch.object(official_live, "make_scheduler", side_effect=_Stop) as factory):
            with self.assertRaises(_Stop):
                official_live.main(["--config", "plan.json", "--state-dir", "state", "--sequence", "1",
                                    "advance", *flags])
        return factory.call_args.kwargs

    def test_official_driver_defaults_off_and_passes_the_opt_in(self):
        self.assertIs(self.official_kwargs()["stable_prompt_prefix"], False)
        self.assertIs(self.official_kwargs("--stable-prompt-prefix")["stable_prompt_prefix"], True)


class _Stop(Exception):
    pass


if __name__ == "__main__":
    unittest.main()
