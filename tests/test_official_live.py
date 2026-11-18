"""The software rehearsal keeps its shared limits and stops at human requests."""

from types import SimpleNamespace
import tempfile
import unittest

from agent_lab.core import Workflow, WorkflowError
from agent_lab.files import FileTools
from agent_lab.gateway import ToolGateway, ToolRequestError
import json
from pathlib import Path
from agent_lab.evaluation.official_live import TOOL_POLICY, TOOLS, advance, runtime_config, tools_for_role


class OfficialLiveTests(unittest.TestCase):
    def test_lead_cannot_write_source_but_can_delegate_through_the_gateway(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = Workflow(Path(directory) / "workflow.sqlite3")
            self.addCleanup(workflow.close)
            for actor in ("lead", "dev", "qa", "release"):
                workflow.register_actor(actor, "agent")
            workflow.register_actor("operator", "human")
            chat = workflow.create_chat("group", ["operator", "lead", "dev", "qa", "release"])
            root = workflow.create_task(chat, "operator", "lead", "Synthetic implementation task")
            workflow.start_task(root, "lead")
            files = FileTools(workflow, Path(directory) / "files")
            self.addCleanup(files.close)
            gateway = ToolGateway(workflow, files, root, "lead", human="operator",
                                  allowed=tools_for_role("software-engineering", "lead", TOOLS),
                                  delegates=("dev", "qa", "release"))

            def call(name, arguments):
                return {"id": "fixture-" + name, "type": "function",
                        "function": {"name": name, "arguments": json.dumps(arguments)}}

            with self.assertRaises(ToolRequestError):
                gateway.dispatch(call("create_text", {"path": "main.py", "content": "print('fixture')"}))
            self.assertEqual(workflow.db.execute(
                "SELECT count(*) FROM events WHERE kind='file_created'").fetchone()[0], 0)
            response = json.loads(gateway.dispatch(call(
                "delegate_task", {"assignee": "dev", "title": "Synthetic focused implementation"}))["content"])
            self.assertTrue(response["ok"])
            child = workflow.task(response["result"]["task_id"], "operator")
            self.assertEqual((child["assignee"], child["parent"]), ("dev", root))

    def test_software_lead_coordinates_and_specialists_keep_implementation_tools(self):
        lead = tools_for_role("software-engineering", "lead", TOOLS)
        self.assertTrue({"ask_human", "delegate_task", "accept_artifact", "offer_artifact", "read_text"} <= set(lead))
        self.assertFalse({"create_text", "update_text", "run_python"} & set(lead))
        self.assertEqual(tools_for_role("software-engineering", "dev", TOOLS), TOOLS)
        self.assertEqual(tools_for_role("software-engineering", "qa", TOOLS), TOOLS)
        self.assertEqual(tools_for_role("newsroom", "chief_editor", TOOLS), TOOLS)

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
        settings["per_scenario_model_attempts"] = 49
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
