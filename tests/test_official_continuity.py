"""Task 2 follows Task 1 in the same group in every scenario, including after a failure.

Synthetic inputs and scripted replies only. The scripted answer below stands in
for a requester inside this fixture; official runs use the real person's words.
"""

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from agent_lab import budget
from agent_lab.core import Workflow, WorkflowError
from agent_lab.deepseek import DeepSeekClient
from agent_lab.evaluation.official import OfficialMidTestPlan
from agent_lab.evaluation.official_dataset import load_mid_test
from agent_lab.evaluation.official_live import POLICIES, runtime_config
from agent_lab.evaluation.official_session import OfficialScenarioSession
from agent_lab.files import FileTools
from agent_lab.scheduler import MultiAgentScheduler, Role
from official_mid_fixture import README_SHA256, SCENARIOS, write_archive

TEMPLATE = Path(__file__).resolve().parents[1] / "evaluation/official/mid-test/plan.json"
TOOLS = ("ask_human", "create_text", "read_text")
DRAFT = "Synthetic partial draft\n"


def reply(calls=None, reason=None):
    message = {"role": "assistant", "content": None}
    message["tool_calls"] = [{"id": f"fixture-{n}", "type": "function",
                              "function": {"name": name, "arguments": json.dumps(arguments)}}
                             for n, (name, arguments) in enumerate(calls)]
    return json.dumps({"id": "fixture", "model": "synthetic-continuity",
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        "choices": [{"message": message, "finish_reason": reason or "tool_calls"}]}).encode()


class ContinuityAfterFailure(unittest.TestCase):
    def setUp(self):
        guard = patch("agent_lab.evaluation.official_dataset._README_SHA256", README_SHA256)
        guard.start()
        self.addCleanup(guard.stop)

    def open(self, scenario):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        config = json.loads(TEMPLATE.read_text())
        config["runtime"].update(model="issued-model", per_scenario_model_attempts=47, max_output_tokens=1024,
                                 tool_policy=POLICIES[scenario].identifier)
        (root / "plan.json").write_text(json.dumps(config))
        write_archive(root / "Mid_Test.zip")
        (root / "manifest.json").write_text(json.dumps(load_mid_test(root / "Mid_Test.zip")))
        plan = OfficialMidTestPlan(root / "plan.json")
        workflow = Workflow(root / "workflow.sqlite3")
        self.addCleanup(workflow.close)
        files = FileTools(workflow, root / "files")
        self.addCleanup(files.close)
        session = OfficialScenarioSession.initialize(workflow, plan, scenario=scenario, human="requester",
                                                     plan_sha256=plan.sha256)
        return plan, workflow, files, session

    def scheduler(self, workflow, files, session, root, transport, attempts):
        roles = {role["id"]: Role(role["prompt"], TOOLS) for role in session.scenario["roles"]}
        return MultiAgentScheduler(workflow, files, root, human="requester", roles=roles,
            clients={role: DeepSeekClient("synthetic-continuity", transport) for role in roles},
            mode="offline_fixture", constraints=[], acceptance_id="fixture-continuity",
            verifier_factory=lambda task: None, limits=budget.TreeLimits(model_attempts=attempts))

    def shares(self, session, plan):
        backend = ("unix:///test/docker.sock", "python@sha256:" + "a" * 64) if POLICIES[session.scenario["id"]].python \
            else (None, None)
        return [runtime_config(SimpleNamespace(scenario=session.scenario), plan, sequence, docker_host=backend[0],
                               image=backend[1], allow_network=False,
                               environ={"COURSE_HKGAI_API_KEY": "synthetic-fixture-key"}).tree_limits.model_attempts
                for sequence in (1, 2)]

    def test_failed_first_task_keeps_its_record_and_second_task_continues_in_the_group(self):
        for _, scenario, roles in SCENARIOS:
            with self.subTest(scenario=scenario):
                plan, workflow, files, session = self.open(scenario)
                first_role, second_role = roles[0][0], roles[2][0]
                first_share, second_share = self.shares(session, plan)
                self.assertEqual((first_share, second_share), (24, 23))
                with self.assertRaisesRegex(WorkflowError, "Task 1 must finish"):
                    session.post(2, second_role)  # Not even posted yet.
                first = session.post(1, first_role)["root"]
                replies = [reply([("create_text", {"path": "draft.txt", "content": DRAFT}),
                                  ("ask_human", {"prompt": "Synthetic fixture question?"})]),
                           # A reply cut off at the output limit: rejected, no tool released.
                           reply([("create_text", {"path": "late.txt", "content": "never written"})], reason="length"),
                           # Cutoffs consume this fixture's three-call allowance without tool effects.
                           reply([("create_text", {"path": "late.txt", "content": "never written"})], reason="length")]
                one = self.scheduler(workflow, files, session, first, lambda payload: replies.pop(0), 3)
                self.assertEqual(one.run()["state"], "blocked")
                with self.assertRaisesRegex(WorkflowError, "Task 1 must finish"):
                    session.post(2, second_role)  # Waiting on the requester is not terminal.
                self.assertEqual(session.status()["tasks"][1]["state"], "not_posted")
                request = workflow.db.execute("SELECT id FROM requests WHERE task=?", (first,)).fetchone()[0]
                workflow.respond(request, "requester", answer="Synthetic fixture answer")
                self.assertEqual(one.run()["task_state"], "failed")

                second = session.post(2, second_role)
                self.assertEqual(workflow.task(second["root"], "requester")["chat"], session.chat)
                report = session.status()
                self.assertEqual(report["group"], session.chat)
                self.assertEqual(report["roles"], [role for role, _ in roles])
                prompts = [task["prompt"] for task in session.scenario["tasks"]]
                self.assertEqual([m["body"] for m in report["conversation"] if m["sender"] == "requester"], prompts)
                self.assertEqual(workflow.task(second["root"], "requester")["title"], prompts[1])
                failed, pending = report["tasks"]
                self.assertEqual((failed["state"], pending["state"]), ("failed", "pending"))
                self.assertEqual([r["prompt"] for r in failed["requests"]], ["Synthetic fixture question?"])
                self.assertTrue(failed["runner"]["synthetic"])
                # Both cutoffs count; the fixture's explicit shared allowance stops further requests.
                self.assertEqual(failed["runner"]["attempts"], 3)
                self.assertIn("budget exhausted", failed["runner"]["stop_reason"])
                for turn in failed["runner"]["turns"][1:]:  # Received in full: usage is known, nothing ran.
                    self.assertEqual((turn["finish_reason"], turn["usage"], turn["tool_names"]),
                                     ("length", {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}, []))

                original = next(e for e in workflow.events(first, "requester") if e["kind"] == "file_created")
                digest = json.loads(original["detail"])["sha256"]
                for wrong in ("0" * 64, digest[::-1]):
                    with self.assertRaisesRegex(WorkflowError, "reviewed SHA"):
                        session.carry(files, source_task=first, source_path="draft.txt", sha256=wrong,
                                      target_path="prior/draft.txt")
                with self.assertRaises(WorkflowError):  # The rejected reply never wrote its file.
                    session.carry(files, source_task=first, source_path="late.txt", sha256=digest,
                                  target_path="prior/late.txt")
                carried = session.carry(files, source_task=first, source_path="draft.txt", sha256=digest,
                                        target_path="prior/draft.txt")
                self.assertEqual((carried["sha256"], carried["source_task"]), (digest, first))

                two = self.scheduler(workflow, files, session, second["root"],
                                     lambda payload: self.fail("No Task 2 request in this check"), second_share)
                used = [budget.status(workflow, root) for root in (first, second["root"])]
                self.assertEqual([(u["attempts"], u["limits"]["model_attempts"]) for u in used], [(3, 3), (0, 23)])
                self.assertEqual(two.status()["task_state"], "pending")
                after = session.status()["tasks"]
                self.assertEqual((after[0]["state"], after[0]["root"]), ("failed", first))
                self.assertEqual(after[1]["carried_inputs"][0]["read_by_root"], False)


if __name__ == "__main__":
    unittest.main()
