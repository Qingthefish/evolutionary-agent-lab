"""Shared runtime contracts. No actual provider request is made."""

import argparse
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.budget import TreeLimits
from agent_lab.core import WorkflowError
from agent_lab.deepseek import DeepSeekClient, DeepSeekHTTP, ProviderError
from agent_lab.evaluation import CaseError, Evaluator, parse_case
from agent_lab.evaluation.harness import HUMAN, _Session, _drive_live
from agent_lab.runner import Limits
from agent_lab.runtime import (LIVE_AGENTS, LiveConfig, RuntimeSetupError, TaskPolicy,
    add_live_arguments, bind_task_policy, build_live_scheduler, live_config_from_args, live_roles)
from agent_lab.scheduler import MultiAgentScheduler
from agent_lab.tui.controller import ControlCenter


def config(**changes):
    return LiveConfig(model="explicit-test-model", api_key="unused-test-key", **changes)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def session(self, name):
        directory = self.path / name
        directory.mkdir()
        session = _Session(directory, "runtime-test")
        self.addCleanup(session.close)
        chat = session.workflow.create_chat("group", [HUMAN, *LIVE_AGENTS])
        root = session.workflow.create_task(chat, HUMAN, "coordinator", "Deliver the original goal")
        return session, chat, root

    def test_ui_and_evaluation_share_roles_limits_tools_and_acceptance(self):
        live = config(constraints=("Retain attribution",), role_limits=Limits(model_attempts=2),
                      tree_limits=TreeLimits(model_attempts=6), tool_calls=5, max_output_tokens=128)
        center = ControlCenter(self.path / "ui", live=live)
        self.addCleanup(center.close)
        chat = center.create_conversation("group", list(LIVE_AGENTS))
        ui_root = center.create_task(chat, "coordinator", "Deliver the original goal",
            constraints=["Use Markdown"], expected_artifacts={"result.md": "Checked\n"})["task"]
        ui_config = center.call(lambda b: json.loads(b.workflow.db.execute(
            "SELECT config FROM scheduler_runs WHERE root=?", (ui_root,)).fetchone()[0]))
        directory = self.path / "eval"
        directory.mkdir()
        session = _Session(directory, "runtime-eval")
        self.addCleanup(session.close)
        case = parse_case({"id": "runtime-case", "title": "Shared configuration", "goal": "Deliver the original goal",
            "driver": "live_scheduler", "constraints": ["Use Markdown"],
            "expected": {"final_state": "succeeded", "artifacts": {"result.md": "Checked\n"}}})
        with patch.object(MultiAgentScheduler, "run", return_value={"state": "blocked"}), \
                patch.object(DeepSeekHTTP, "__call__", side_effect=AssertionError("No model calls in setup checks")) as http:
            root, _ = _drive_live(case, session, live)
            http.assert_not_called()
        evaluation_config = json.loads(session.workflow.db.execute(
            "SELECT config FROM scheduler_runs WHERE root=?", (root,)).fetchone()[0])
        # Different supervising human IDs are local identity, not a policy difference.
        ui_config.pop("human")
        evaluation_config.pop("human")
        self.assertEqual(ui_config, evaluation_config)
        self.assertEqual(ui_config["constraints"], ["Retain attribution", "Use Markdown"])
        for role in ui_config["roles"].values():
            self.assertEqual((role["limits"]["model_attempts"], role["tool_calls"]), (2, 5))
            self.assertFalse(set(role["tools"]) & {"run_python", "git_push", "search_memory", "select_memory"})
        tree_limits = json.loads(session.workflow.db.execute("SELECT limits FROM tree_budgets WHERE root=?", (root,)).fetchone()[0])
        self.assertEqual(tree_limits["model_attempts"], 6)
        self.assertNotIn(live.api_key, json.dumps(evaluation_config))

    def test_restart_restores_original_constraints_for_root_and_child(self):
        live = config(constraints=("Original global constraint",))
        directory = self.path / "restart"
        center = ControlCenter(directory, live=live)
        try:
            chat = center.create_conversation("group", list(LIVE_AGENTS))
            root = center.create_task(chat, "coordinator", "Original user goal", constraints=["Original task constraint"])["task"]
        finally:
            center.close()
        center = ControlCenter(directory, live=replace(live, constraints=("New-session default",)))
        self.addCleanup(center.close)

        def inspect(backend):
            scheduler = backend.scheduler(root)
            backend.workflow.start_task(root, "coordinator")
            child = backend.workflow.create_task(chat, "coordinator", "writer", "A focused child", parent=root)
            backend.workflow.start_task(child, "writer")
            for task in (root, child):
                scheduler.runner(task)
            return scheduler.constraints, [json.loads(r[0]) for r in backend.workflow.db.execute(
                "SELECT transcript FROM runner_sessions ORDER BY rowid")]
        constraints, transcripts = center.call(inspect)
        self.assertEqual(constraints, ["Original global constraint", "Original task constraint"])
        for transcript in transcripts:
            context = json.loads(transcript[1]["content"])
            self.assertIn("Original user goal", json.dumps(context))
            self.assertIn("Original task constraint", json.dumps(context))
            self.assertNotIn("New-session default", json.dumps(context))

    def test_policy_changes_and_changed_budgets_cannot_silently_resume(self):
        session, _, root = self.session("immutable")
        policy = TaskPolicy(["Keep the source"], {"result.md": "Expected\n"})
        build_live_scheduler(session.workflow, session.files, root, human=HUMAN, live=config(), policy=policy)
        before = session.workflow.db.execute("SELECT policy FROM runtime_task_policies WHERE root=?", (root,)).fetchone()[0]
        for changed in (TaskPolicy(["Discard the source"], {"result.md": "Expected\n"}),
                        TaskPolicy(["Keep the source"], {"result.md": "Different\n"})):
            with self.assertRaises(WorkflowError):
                build_live_scheduler(session.workflow, session.files, root, human=HUMAN, live=config(), policy=changed)
        with self.assertRaises(WorkflowError):
            build_live_scheduler(session.workflow, session.files, root, human=HUMAN,
                                 live=config(role_limits=Limits(model_attempts=1)))
        self.assertEqual(session.workflow.task(root, HUMAN)["state"], "pending")
        self.assertEqual(before, session.workflow.db.execute("SELECT policy FROM runtime_task_policies WHERE root=?", (root,)).fetchone()[0])

    def test_shared_acceptance_reads_actual_root_artifact_and_leaves_children_for_review(self):
        session, chat, root = self.session("acceptance")
        scheduler = build_live_scheduler(session.workflow, session.files, root, human=HUMAN, live=config(),
                                        policy=TaskPolicy(root_artifacts={"result.md": "Expected\n"}))
        session.workflow.start_task(root, "coordinator")
        child = session.workflow.create_task(chat, "coordinator", "writer", "Draft result", parent=root)
        self.assertIsNone(scheduler.verifier_factory(session.workflow.task(child, HUMAN)))
        session.workflow.start_task(child, "writer")
        session.workflow.finish_task(child, "writer", checks={"trusted_test_review": True})
        verifier, _ = scheduler.verifier_factory(session.workflow.task(root, HUMAN))
        session.files.create_text(root, "coordinator", "result.md", "Wrong\n")
        with self.assertRaisesRegex(WorkflowError, "Artifact verification failed"):
            session.workflow.finish_task(root, "coordinator", verifier=verifier)
        receipt = session.files.read_text(root, "coordinator", "result.md")
        session.files.update_text(root, "coordinator", "result.md", "Expected\n", expected_sha256=receipt["sha256"])
        session.workflow.finish_task(root, "coordinator", verifier=verifier)
        self.assertEqual(session.workflow.task(root, HUMAN)["state"], "succeeded")

    def test_explicit_network_opt_in_and_no_secret_in_saved_policy(self):
        session, _, root = self.session("network-off")
        live = config(constraints=["Preserve constraints"])
        scheduler = build_live_scheduler(session.workflow, session.files, root, human=HUMAN, live=live)
        self.assertEqual(scheduler.constraints, ["Preserve constraints"])
        with patch("urllib.request.build_opener") as opener:
            with self.assertRaises(ProviderError):
                scheduler.clients["coordinator"].transport(b"{}")
            opener.assert_not_called()
        saved = session.workflow.db.execute("SELECT policy FROM runtime_task_policies WHERE root=?", (root,)).fetchone()[0]
        self.assertNotIn(live.api_key, saved)
        self.assertNotIn(live.api_key, repr(live))

    def test_legacy_ui_human_review_task_keeps_its_existing_contract(self):
        session, _, root = self.session("legacy")
        roles = live_roles(LIVE_AGENTS)
        live = config()
        old = MultiAgentScheduler(session.workflow, session.files, root, human=HUMAN, roles=roles,
            clients={a: DeepSeekClient(live.model, DeepSeekHTTP(live.api_key)) for a in roles},
            mode="live", constraints=[], acceptance_id="tui-live-human-review-v1", verifier_factory=lambda task: None)
        resumed = build_live_scheduler(session.workflow, session.files, root, human=HUMAN, live=live)
        self.assertEqual(resumed.acceptance_id, old.acceptance_id)
        self.assertIsNone(resumed.verifier_factory(session.workflow.task(root, HUMAN)))
        with self.assertRaises(WorkflowError):
            build_live_scheduler(session.workflow, session.files, root, human=HUMAN, live=live,
                                 policy=TaskPolicy(["New rule"]))

    def test_nonmember_and_agent_cannot_bind_policy(self):
        session, _, root = self.session("membership")
        session.workflow.register_actor("outsider", "human")
        for actor in ("outsider", "coordinator"):
            with self.assertRaises(WorkflowError):
                bind_task_policy(session.workflow, root, actor, TaskPolicy())

    def test_live_settings_reject_unsupported_or_invalid_setup(self):
        for change in ({"provider": "hkgai"}, {"provider": "openai"}, {"max_output_tokens": True},
                       {"max_output_tokens": 0}, {"allow_network": 1}, {"socket_timeout": float("inf")},
                       {"tool_calls": 0}, {"constraints": "not-an-array"}, {"role_limits": {}}, {"tree_limits": {}}):
            with self.subTest(change=change), self.assertRaises(WorkflowError):
                config(**change)

    def test_shared_cli_settings_require_explicit_mode_and_named_key(self):
        parser = argparse.ArgumentParser()
        add_live_arguments(parser)
        with patch.dict("os.environ", {"A02_TEST_KEY": "unused-test-key"}, clear=True):
            self.assertIsNone(live_config_from_args(parser.parse_args([])))
            for argv in (["--model", "m"], ["--live"], ["--live", "--model", "m", "--api-key-env", "MISSING"],
                         ["--constraint", "Retain source"]):
                with self.assertRaises(WorkflowError):
                    live_config_from_args(parser.parse_args(argv))
            live = live_config_from_args(parser.parse_args(["--live", "--model", "m", "--api-key-env", "A02_TEST_KEY",
                "--constraint", "Retain source", "--task-attempts", "2", "--tree-attempts", "4"]))
        self.assertTrue(live.allow_network)
        self.assertEqual((live.constraints, live.role_limits.model_attempts, live.tree_limits.model_attempts),
                         (("Retain source",), 2, 4))

    def test_case_constraints_are_explicit_and_not_claimed_for_scripted_fixtures(self):
        data = {"id": "constraint-case", "title": "Constraint", "goal": "Write a note", "driver": "live_scheduler",
                "constraints": ["Preserve citations"], "expected": {"final_state": "succeeded"}}
        self.assertEqual(parse_case(data).summary()["constraints"], ["Preserve citations"])
        for change in ({"driver": "offline_delegation"}, {"constraints": "text"}, {"constraints": [""]}):
            with self.assertRaises(CaseError):
                parse_case(data | change)

    def test_direct_setup_cannot_omit_or_duplicate_launch_constraints(self):
        session, _, root = self.session("combined")
        live = config(constraints=["Launch constraint"])
        policy = TaskPolicy(["Task constraint"])
        first = build_live_scheduler(session.workflow, session.files, root, human=HUMAN, live=live, policy=policy)
        again = build_live_scheduler(session.workflow, session.files, root, human=HUMAN, live=live, policy=policy)
        self.assertEqual(first.constraints, ["Launch constraint", "Task constraint"])
        self.assertEqual(again.constraints, first.constraints)

    def test_combined_constraint_limit_is_checked_before_creating_an_evaluation(self):
        case = parse_case({"id": "constraint-case", "title": "Constraint", "goal": "Write a note",
            "driver": "live_scheduler", "constraints": ["Task constraint"], "expected": {"final_state": "succeeded"}})
        destination = self.path / "not-created"
        with self.assertRaises(WorkflowError):
            Evaluator([case], output_root=destination, live=config(constraints=["Launch constraint"] * 100))
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
