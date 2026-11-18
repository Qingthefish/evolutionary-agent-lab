"""Trusted HTML format selection reaches the system prompt for only fund Task 2."""

import json
from unittest import TestCase
from unittest.mock import patch

from agent_lab.evaluation import official_live
from agent_lab.runner import effective_prompt
from test_official_session import OfficialSessionTests


class OfficialFormatScope(TestCase):
    setUp = OfficialSessionTests.setUp
    open_workflow = OfficialSessionTests.open_workflow
    def test_default_system_prompt_and_html_prompt_are_distinct(self):
        original = effective_prompt(False)
        self.assertIn("Document outputs must be Markdown or plain text;", original)
        allowed = effective_prompt(False, allow_html=True)
        self.assertIn("This task permits HTML slides", allowed)
        self.assertNotIn("Document outputs must be Markdown or plain text;", allowed)

    def test_only_securities_second_root_gets_the_format_override(self):
        from types import SimpleNamespace
        from agent_lab.runner import Limits
        from agent_lab.budget import TreeLimits
        for name, sequence, enabled in (
            ("software-engineering", 1, False), ("newsroom", 2, False),
            ("securities-fund", 1, False), ("securities-fund", 2, True),
        ):
            session = SimpleNamespace(
                scenario={"id": name, "roles": [{"id": "role", "prompt": "Fixture role."}]},
                agents=("role",), human="requester", workflow=None,
                _root=lambda number: {"root": "second-root"},
            )
            root = "second-root" if sequence == 2 else "first-root"
            live = SimpleNamespace(role_limits=Limits(), tree_limits=TreeLimits(), tool_calls=32,
                                   max_output_tokens=1024)
            services = SimpleNamespace(executor=None, retrieval=None)
            with (patch.object(official_live, "live_clients", return_value={}),
                  patch.object(official_live, "MultiAgentScheduler") as factory):
                official_live.make_scheduler(session, root, None, live, services)
            self.assertEqual(factory.call_args.kwargs["allow_html"], enabled)
            self.assertEqual("HTML slides" in " ".join(factory.call_args.kwargs["constraints"]), enabled)
            self.assertIn("output limit of 1024 tokens", factory.call_args.kwargs["constraints"][-1])

    def test_scheduler_passes_html_setting_into_real_runner_context(self):
        from agent_lab.deepseek import DeepSeekClient
        from agent_lab.scheduler import MultiAgentScheduler, Role
        root = self.session.post(1, "lead")["root"]
        roles = {entry["id"]: Role(entry["prompt"], ("create_text",))
                 for entry in self.session.scenario["roles"]}
        scheduler = MultiAgentScheduler(
            self.workflow, self.files, root, human="requester", roles=roles,
            clients={name: DeepSeekClient("fixture", lambda payload: b"{}") for name in roles},
            mode="offline_fixture", constraints=[], verifier_factory=lambda task: None,
            acceptance_id="fixture-html-system", allow_html=True,
        )
        self.workflow.start_task(root, "lead")
        scheduler.runner(root)
        transcript = json.loads(self.workflow.db.execute(
            "SELECT transcript FROM runner_sessions WHERE task=?", (root,)).fetchone()[0])
        self.assertIn("This task permits HTML slides", transcript[0]["content"])
