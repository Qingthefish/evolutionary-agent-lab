"""Each mid-test scenario has a reviewed tool policy and an offline preflight.

Inputs are the synthetic issued-format archive. No provider request, public
network access or container start happens here; a preflight is not a live run.
"""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from agent_lab import budget
from agent_lab.core import Workflow, WorkflowError
from agent_lab.deepseek import DeepSeekClient
from agent_lab.evaluation import official_live, official_session
from agent_lab.evaluation.official import OfficialMidTestPlan
from agent_lab.evaluation.official_dataset import load_mid_test
from agent_lab.evaluation.official_live import (CONSTRAINTS, POLICIES, TOKENS_PER_REQUEST, TOOL_POLICY, TOOLS,
                                                runtime_config)
from agent_lab.files import FileTools
from agent_lab.runner import Limits
from agent_lab.scheduler import MultiAgentScheduler, Role
from agent_lab.evaluation.topology import tool_classes
from agent_lab.hkgai import HKGAIHTTP
from official_mid_fixture import README_SHA256, SCENARIOS, write_archive

# Reviewed software values recorded from origin/main at 92c5039, not from this code.
SOFTWARE_TOOLS = ("read_messages", "post_message", "list_tasks", "ask_human",
                  "create_text", "read_text", "list_files", "update_text", "append_text", "offer_artifact", "accept_artifact",
                  "delegate_task", "delegate_with_inputs", "retry_failed_task", "run_python", "submit_for_verification")
SOFTWARE_CONSTRAINTS_SHA256 = "b9ca0bcae3a767500cfb3bcc1d03653e0e57514b62429482c92943e18f61a372"
IMAGE = "python@sha256:" + "a" * 64
KEY = "synthetic-fixture-key"
ROLES = {identifier: [role for role, _ in roles] for _, identifier, roles in SCENARIOS}


def settings(scenario, **changes):
    return {"provider": "hkgai", "tool_policy": POLICIES[scenario].identifier, "model": "issued-model",
            "per_scenario_model_attempts": 48, "max_output_tokens": 1024, "api_key_env": "COURSE_TEST_KEY"} | changes


def configure(scenario, *, docker=None, **changes):
    session = SimpleNamespace(scenario={"id": scenario})
    plan = SimpleNamespace(config={"runtime": settings(scenario, **changes)})
    backend = docker if docker is not None else (
        ("unix:///test/docker.sock", IMAGE) if POLICIES[scenario].python else (None, None))
    return runtime_config(session, plan, 1, docker_host=backend[0], image=backend[1], allow_network=False,
                          environ={"COURSE_TEST_KEY": KEY})


class ScenarioPolicies(unittest.TestCase):
    def test_software_policy_is_the_reviewed_one(self):
        policy = POLICIES["software-engineering"]
        self.assertEqual((TOOL_POLICY, policy.identifier), ("software-files-coordination-python-v1",) * 2)
        self.assertEqual((TOOLS, policy.tools), (SOFTWARE_TOOLS, SOFTWARE_TOOLS))
        for constraints in (CONSTRAINTS, list(policy.constraints)):
            self.assertEqual(hashlib.sha256(json.dumps(constraints).encode()).hexdigest(), SOFTWARE_CONSTRAINTS_SHA256)
        self.assertEqual((policy.web, policy.python, policy.acceptance_id),
                         (False, True, "official-software-trusted-review-v1"))

    def test_new_policies_add_only_reviewed_existing_tools(self):
        self.assertEqual(set(POLICIES), set(ROLES))
        base = set(SOFTWARE_TOOLS)
        news, fund = POLICIES["newsroom"], POLICIES["securities-fund"]
        self.assertEqual(set(news.tools), base - {"run_python"} | {"search_web", "retrieve_text"})
        self.assertEqual(set(fund.tools), base | {"search_web", "retrieve_text"})
        self.assertEqual(((news.web, news.python), (fund.web, fund.python)), ((True, False), (True, True)))
        identifiers = [policy.identifier for policy in POLICIES.values()]
        acceptance = [policy.acceptance_id for policy in POLICIES.values()]
        self.assertEqual((len(set(identifiers)), len(set(acceptance))), (3, 3))
        for policy in POLICIES.values():
            self.assertEqual(len(set(policy.tools)), len(policy.tools))
            self.assertEqual(policy.tools[-1], "submit_for_verification")
            self.assertEqual(set(tool_classes(policy.tools)), set(policy.tools))  # C07 classification is complete.

    def test_new_constraints_are_harness_rules_not_content_or_design_rules(self):
        for name in ("newsroom", "securities-fund"):
            text = " ".join(POLICIES[name].constraints).lower()
            for needed in ("ask the requester", "never instructions", "markdown or plain text",
                           "trusted reviewer decides"):
                self.assertIn(needed, text)
            for absent in ("slide", "html", "single file", "single-file", "offline", "framework", "browser", "deck"):
                self.assertNotIn(absent, text)

    def test_runtime_flags_follow_the_scenario_policy(self):
        software, news, fund = (configure(name) for name in ("software-engineering", "newsroom", "securities-fund"))
        self.assertEqual([c.enable_web for c in (software, news, fund)], [False, True, True])
        self.assertEqual([bool(c.docker_host) for c in (software, news, fund)], [True, False, True])
        for config in (software, news, fund):
            self.assertEqual((config.provider, config.allow_network, config.socket_timeout, config.tool_calls,
                              config.max_output_tokens, config.require_tool_actions, config.repositories),
                             ("hkgai", False, 90, 40, 1024, True, ()))
            self.assertEqual((config.tree_limits.tasks, config.tree_limits.depth, config.tree_limits.model_attempts,
                              config.tree_limits.duration_seconds, config.role_limits.model_attempts),
                             (8, 3, 24, 14400, 24))
            self.assertNotIn(KEY, repr(config))

    def test_unsupported_configurations_are_rejected(self):
        for name in POLICIES:
            other = next(policy.identifier for key, policy in POLICIES.items() if key != name)
            for changes in ({"tool_policy": other}, {"tool_policy": None}, {"max_output_tokens": 1025},
                            {"per_scenario_model_attempts": 161}, {"per_scenario_model_attempts": 1},
                            {"provider": "deepseek"}, {"model": None}):
                with self.subTest(scenario=name, changes=changes), self.assertRaisesRegex(
                        WorkflowError, "bounded scenario budget"):
                    configure(name, **changes)
        with self.assertRaisesRegex(WorkflowError, "isolated Python backend"):
            configure("securities-fund", docker=(None, None))
        with self.assertRaisesRegex(WorkflowError, "isolated Python backend"):
            configure("software-engineering", docker=("unix:///test/docker.sock", None))
        with self.assertRaisesRegex(WorkflowError, "omit the container options"):
            configure("newsroom", docker=("unix:///test/docker.sock", IMAGE))
        with self.assertRaisesRegex(WorkflowError, "No reviewed live tool policy"):
            runtime_config(SimpleNamespace(scenario={"id": "unknown-scenario"}),
                           SimpleNamespace(config={"runtime": settings("newsroom")}), 1,
                           docker_host=None, image=None, allow_network=False, environ={"COURSE_TEST_KEY": KEY})


class TokenStopThresholds(unittest.TestCase):
    """The request cap is the budget; the reported-token stop only guards against runaway use."""

    def test_thresholds_scale_with_the_request_share_in_every_scenario(self):
        self.assertEqual(TOKENS_PER_REQUEST, 50000)  # Scaled to observed late-task newsroom requests.
        for name in POLICIES:
            for attempts, shares in ((48, (24, 24)), (47, (24, 23)), (2, (1, 1))):
                session = SimpleNamespace(scenario={"id": name})
                plan = SimpleNamespace(config={"runtime": settings(name, per_scenario_model_attempts=attempts)})
                backend = ("unix:///test/docker.sock", IMAGE) if POLICIES[name].python else (None, None)
                for sequence, share in zip((1, 2), shares):
                    live = runtime_config(session, plan, sequence, docker_host=backend[0], image=backend[1],
                                          allow_network=False, environ={"COURSE_TEST_KEY": KEY})
                    self.assertEqual((live.tree_limits.model_attempts, live.role_limits.model_attempts), (share, share))
                    self.assertEqual((live.tree_limits.reported_tokens, live.role_limits.reported_tokens),
                                     (share * 50000,) * 2)
                    self.assertEqual((live.max_output_tokens, live.tool_calls, live.socket_timeout), (1024, 40, 90))

    def test_shared_defaults_used_elsewhere_are_unchanged(self):
        self.assertEqual((Limits().reported_tokens, budget.TreeLimits().reported_tokens), (32000, 128000))
        self.assertEqual((Limits().model_attempts, budget.TreeLimits().model_attempts), (8, 48))

    def run_task(self, live, tokens_per_reply):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        workflow = Workflow(Path(directory.name) / "state.sqlite3")
        self.addCleanup(workflow.close)
        files = FileTools(workflow, Path(directory.name) / "files")
        self.addCleanup(files.close)
        workflow.register_actor("requester", "human")
        workflow.register_actor("lead", "agent")
        root = workflow.create_task(workflow.create_chat("group", ["requester", "lead"]), "requester", "lead", "Fixture")
        replies = []

        def transport(payload):
            replies.append(payload)
            call = {"id": f"call-{len(replies)}", "type": "function", "function": {
                "name": "create_text", "arguments": json.dumps({"path": f"part-{len(replies)}.txt", "content": "x"})}}
            return json.dumps({"id": "fixture", "model": "synthetic-thresholds", "usage": {
                "prompt_tokens": tokens_per_reply - 100, "completion_tokens": 100, "total_tokens": tokens_per_reply},
                "choices": [{"finish_reason": "tool_calls",
                             "message": {"role": "assistant", "content": None, "tool_calls": [call]}}]}).encode()

        scheduler = MultiAgentScheduler(workflow, files, root, human="requester",
            roles={"lead": Role("Fixture role", ("create_text",), (), live.role_limits, live.tool_calls)},
            clients={"lead": DeepSeekClient("synthetic-thresholds", transport)}, mode="offline_fixture",
            constraints=[], acceptance_id="fixture-thresholds", verifier_factory=lambda task: None,
            limits=live.tree_limits)
        state = scheduler.run()
        reason = workflow.db.execute("SELECT stop_reason FROM runner_sessions WHERE task=?", (root,)).fetchone()[0]
        written = workflow.db.execute("SELECT count(*) FROM tool_calls WHERE status='succeeded'").fetchone()[0]
        return state, len(replies), written, reason

    def test_typical_usage_reaches_the_request_cap_and_runaway_usage_still_stops(self):
        live = configure("newsroom")
        # 5,900 reported tokens per reply is the median of the retained HKGAI rounds; a synthetic reply here.
        state, requests, written, reason = self.run_task(live, 5900)
        self.assertEqual((requests, written), (24, 24))  # Under the old 32,000 default this stopped at reply six.
        self.assertIn("attempt", reason)
        self.assertNotIn("token", reason.lower())
        self.assertEqual(state["budget"]["tokens"], 24 * 5900)
        # Far above the ceiling: the guard still stops the task and releases no tools from the last reply.
        # 30,000 per reply, as observed late in live newsroom tasks, also reaches the cap.
        state, requests, written, reason = self.run_task(live, 30000)
        self.assertEqual((requests, written), (24, 24))
        self.assertIn("attempt", reason)
        state, requests, written, reason = self.run_task(live, 120000)
        self.assertEqual((requests, written), (10, 9))
        self.assertIn("reported token budget", reason)
        self.assertEqual(state["task_state"], "failed")


class OfflinePreflight(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        for target, value in (("agent_lab.evaluation.official_dataset._README_SHA256", README_SHA256),):
            guard = patch(target, value)
            guard.start()
            self.addCleanup(guard.stop)
        # Any provider request, container start or changed environment fails the test.
        for guard in (patch.object(HKGAIHTTP, "__call__", side_effect=AssertionError("No provider request")),
                      patch("subprocess.run", side_effect=AssertionError("No container start")),
                      patch("subprocess.Popen", side_effect=AssertionError("No container start")),
                      patch("agent_lab.retrieval.PublicHTTPS.fetch", side_effect=AssertionError("No public fetch")),
                      patch("socket.create_connection", side_effect=AssertionError("No network connection")),
                      patch("agent_lab.sandbox.shutil.which", return_value=sys.executable),
                      patch.dict(os.environ, {"COURSE_HKGAI_API_KEY": KEY})):
            guard.start()
            self.addCleanup(guard.stop)

    def plan(self, scenario):
        inputs = self.directory / (scenario + "-inputs")
        inputs.mkdir()
        template = json.loads((Path(__file__).resolve().parents[1] / "evaluation/official/mid-test/plan.json").read_text())
        template["runtime"].update(model="issued-model", per_scenario_model_attempts=48, max_output_tokens=1024,
                                   tool_policy=POLICIES[scenario].identifier)
        (inputs / "plan.json").write_text(json.dumps(template))
        write_archive(inputs / "Mid_Test.zip")
        (inputs / "manifest.json").write_text(json.dumps(load_mid_test(inputs / "Mid_Test.zip")))
        return inputs / "plan.json"

    def run_cli(self, module, arguments, *, fails=False):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            try:
                code = module.main(arguments)
            except SystemExit as stop:
                code = stop.code
        self.assertEqual(code != 0, fails, errors.getvalue())
        self.assertNotIn(KEY, output.getvalue() + errors.getvalue())
        return errors.getvalue() if fails else json.loads(output.getvalue())

    def prepare(self, scenario):
        config, state = str(self.plan(scenario)), str(self.directory / (scenario + "-state"))
        common = ["--config", config, "--state-dir", state]
        self.run_cli(official_session, [*common, "init", "--scenario", scenario, "--human", "requester",
                                        "--plan-sha256", OfficialMidTestPlan(config).sha256])
        self.run_cli(official_session, [*common, "post", "--sequence", "1", "--assignee", ROLES[scenario][0]])
        return [*common, "--sequence", "1"]

    def docker_options(self):
        # The executor only checks that this is a local Unix socket; nothing listens on it.
        short = tempfile.TemporaryDirectory(dir="/tmp")
        self.addCleanup(short.cleanup)
        path = Path(short.name) / "d.sock"
        listener = socket.socket(socket.AF_UNIX)
        self.addCleanup(listener.close)
        listener.bind(str(path))
        return ["--docker-host", "unix://" + str(path), "--image", IMAGE]

    def test_every_scenario_preflights_offline_in_a_fresh_state(self):
        for scenario, policy in POLICIES.items():
            with self.subTest(scenario=scenario):
                common = self.prepare(scenario)
                options = self.docker_options() if policy.python else []
                report = self.run_cli(official_live, [*common, "preflight", *options])
                self.assertEqual(report["model_calls"], 0)
                self.assertEqual(report["roles"], ROLES[scenario])
                self.assertEqual((report["tool_policy"], report["tools"]), (policy.identifier, list(policy.tools)))
                self.assertEqual((report["mode"], report["task_state"], report["live_model_attempts"]),
                                 ("live", "pending", 0))
                self.assertEqual(report["budget"]["attempts"], 0)
                self.assertEqual((report["budget"]["limits"]["model_attempts"], report["budget"]["limits"]["reported_tokens"]),
                                 (24, 24 * TOKENS_PER_REQUEST))
                web, execution = report["configuration"]["web"], report["configuration"]["execution"]
                self.assertEqual(web is not None, policy.web)
                if policy.web:
                    # Recorded as the run permits it, so advance can reopen this state. Preflight
                    # dispatches no tool: any public fetch or socket here fails the test.
                    self.assertTrue(web["network"])
                self.assertEqual(execution is not None, policy.python)
                if policy.python:
                    self.assertEqual(execution["image"], IMAGE)
                state = Path(common[3])
                self.assertEqual([p for p in (state / "files").rglob("*") if p.is_file()], [])

    def test_web_policies_advance_and_review_the_state_their_preflight_opened(self):
        # Regression: the recorded retrieval network flag differed between preflight and
        # advance, so a later command refused the state as a changed configuration.
        for scenario in ("newsroom", "securities-fund"):
            with self.subTest(scenario=scenario):
                common = self.prepare(scenario)
                options = self.docker_options() if POLICIES[scenario].python else []
                self.run_cli(official_live, [*common, "preflight", *options])
                answer = json.dumps({"id": "fixture", "model": "synthetic-web-policy",
                    "usage": {"prompt_tokens": 9, "completion_tokens": 3, "total_tokens": 12},
                    "choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
                        "tool_calls": [{"id": "ask", "type": "function", "function": {"name": "ask_human",
                            "arguments": json.dumps({"prompt": "Synthetic fixture question?"})}}]}}]}).encode()
                with patch.object(HKGAIHTTP, "__call__", return_value=answer) as provider:
                    blocked = self.run_cli(official_live, [*common, "advance", "--turns", "2", *options])
                self.assertEqual(provider.call_count, 1)
                self.assertEqual(blocked["needs"][0]["requests"][0]["prompt"], "Synthetic fixture question?")
                again = self.run_cli(official_live, [*common, "preflight", *options])
                self.assertEqual((again["budget"]["attempts"], again["model_calls"]), (1, 0))

    def test_container_options_are_checked_per_policy(self):
        news, fund = self.prepare("newsroom"), self.prepare("securities-fund")
        self.assertIn("omit the container options",
                      self.run_cli(official_live, [*news, "preflight", *self.docker_options()], fails=True))
        message = self.run_cli(official_live, [*fund, "preflight"], fails=True)
        self.assertIn("isolated Python backend", message)
        self.assertTrue(message.startswith("Mid-test scenario operation failed"))

    def test_plan_for_another_scenario_is_refused(self):
        common = self.prepare("newsroom")
        plan = Path(common[1])
        changed = json.loads(plan.read_text())
        changed["runtime"]["tool_policy"] = TOOL_POLICY
        other = plan.with_name("other.json")
        other.write_text(json.dumps(changed))
        message = self.run_cli(official_live, ["--config", str(other), *common[2:], "preflight"], fails=True)
        self.assertIn("same reviewed mid-test plan", message)  # The session stays bound to its own plan.


if __name__ == "__main__":
    unittest.main()
