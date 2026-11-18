"""The software rehearsal keeps its shared limits and stops at human requests."""

from types import SimpleNamespace
import tempfile
import unittest

from agent_lab.core import Workflow, WorkflowError
from agent_lab.evaluation.official_live import TOOL_POLICY, advance, runtime_config


class OfficialLiveTests(unittest.TestCase):
    def test_larger_output_ceiling_needs_explicit_operator_selection(self):
        session = SimpleNamespace(scenario={"id": "software-engineering"})
        settings = {"provider": "hkgai", "tool_policy": TOOL_POLICY, "model": "issued-model",
                    "per_scenario_model_attempts": 44, "max_output_tokens": 4096, "api_key_env": "COURSE_TEST_KEY"}
        plan = SimpleNamespace(config={"runtime": settings})
        backend = {"docker_host": "unix:///test/docker.sock", "image": "test-image",
                   "allow_network": False, "environ": {"COURSE_TEST_KEY": "dummy-fixture"}}
        with self.assertRaisesRegex(WorkflowError, "bounded scenario budget"):
            runtime_config(session, plan, 1, **backend)
        selected = runtime_config(session, plan, 1, output_token_ceiling=4096, **backend)
        self.assertEqual(selected.max_output_tokens, 4096)
        self.assertEqual(selected.tree_limits.model_attempts, 22)
        self.assertEqual(selected.socket_timeout, 90)

    def test_software_budget_allocations_sum_to_the_reviewed_cap(self):
        session = SimpleNamespace(scenario={"id": "software-engineering"})
        settings = {"provider": "hkgai", "tool_policy": TOOL_POLICY, "model": "issued-model",
                    "per_scenario_model_attempts": 47, "max_output_tokens": 1024, "api_key_env": "COURSE_TEST_KEY"}
        plan = SimpleNamespace(config={"runtime": settings})
        backend = {"docker_host": "unix:///test/docker.sock", "image": "test-image",
                   "allow_network": False, "environ": {"COURSE_TEST_KEY": "dummy-fixture"}}
        first = runtime_config(session, plan, 1, **backend)
        second = runtime_config(session, plan, 2, **backend)
        self.assertEqual((first.tree_limits.model_attempts, second.tree_limits.model_attempts), (24, 23))
        self.assertFalse(first.allow_network)
        self.assertFalse(first.enable_web)
        self.assertEqual(first.repositories, ())
        self.assertEqual(first.socket_timeout, 90)
        self.assertEqual((first.tool_calls, first.tree_limits.tool_calls), (40, 128))  # Unchanged up to 24.
        # Proposed 2026-11-18: up to 96 per scenario, 48 per task, with tool caps scaled to the share.
        settings["per_scenario_model_attempts"] = 96
        first, second = runtime_config(session, plan, 1, **backend), runtime_config(session, plan, 2, **backend)
        self.assertEqual((first.tree_limits.model_attempts, second.tree_limits.model_attempts), (48, 48))
        self.assertEqual((first.role_limits.model_attempts, first.tree_limits.reported_tokens), (48, 48 * 50000))
        self.assertEqual((first.tool_calls, first.tree_limits.tool_calls), (80, 256))
        settings["per_scenario_model_attempts"] = 144
        first, second = runtime_config(session, plan, 1, **backend), runtime_config(session, plan, 2, **backend)
        self.assertEqual((first.tree_limits.model_attempts, second.tree_limits.model_attempts), (72, 72))
        self.assertEqual((first.tool_calls, first.tree_limits.tool_calls, first.tree_limits.reported_tokens),
                         (120, 384, 72 * 50000))
        settings["per_scenario_model_attempts"] = 145
        with self.assertRaisesRegex(WorkflowError, "bounded scenario budget"):
            runtime_config(session, plan, 1, **backend)

    def test_advance_stops_before_another_turn_when_request_is_open(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = Workflow(f"{directory}/workflow.sqlite3")
            self.addCleanup(workflow.close)
            workflow.register_actor("operator", "human")
            workflow.register_actor("lead", "agent")
            chat = workflow.create_chat("group", ["operator", "lead"])
            root = workflow.create_task(chat, "operator", "lead", "Fixture")
            workflow.start_task(root, "lead")
            calls = []

            def step():
                calls.append("step")
                workflow.ask_human(root, "lead", "operator", "Fixture clarification")
                return {"state": "running"}

            scheduler = SimpleNamespace(workflow=workflow, root=root, step=step, status=lambda: {"root": root})
            result = advance(scheduler, 8)
            self.assertEqual(calls, ["step"])
            self.assertEqual(result["state"], "blocked")
            self.assertEqual(result["needs"][0]["requests"][0]["prompt"], "Fixture clarification")
            self.assertEqual(advance(scheduler, 1), result)
            self.assertEqual(calls, ["step"])
