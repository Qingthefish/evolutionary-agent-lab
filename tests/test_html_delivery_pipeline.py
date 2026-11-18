"""An agent-written HTML file survives creation, handoff and reading byte for byte.

Non-official development fixture: placeholder notes about a fictional kite
shop, scripted replies and the synthetic issued-format archive. It proves the
scheduler, gateway and file broker plumbing only. It is not model capability,
not an official task and not a presentation design.
"""

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.core import Workflow
from agent_lab.deepseek import DeepSeekClient
from agent_lab.evaluation.official import OfficialMidTestPlan
from agent_lab.evaluation.official_dataset import load_mid_test
from agent_lab.evaluation.official_live import POLICIES
from agent_lab.evaluation.official_session import OfficialScenarioSession
from agent_lab.files import FileTools
from agent_lab.retrieval import WebRetrieval
from agent_lab.sandbox import DockerPythonExecutor
from agent_lab.scheduler import MultiAgentScheduler, Role
from official_mid_fixture import README_SHA256, write_archive
from test_runner import response, tool

HOST = os.environ.get("AGENT_LAB_DOCKER_HOST")
IMAGE = os.environ.get("AGENT_LAB_PYTHON_IMAGE")
TEMPLATE = Path(__file__).resolve().parents[1] / "evaluation/official/mid-test/plan.json"
FRAGMENTS = {
    "parts/01.html": "<!doctype html>\n<title>Fixture kite shop</title>\n<section>Placeholder one</section>\n",
    "parts/02.html": "<section>Placeholder two</section>\n",
}
DECK = "".join(FRAGMENTS.values())
JOIN = ("from pathlib import Path\n"
        "parts = sorted(Path('parts').glob('*.html'))\n"
        "Path('deck.html').write_text(''.join(p.read_text(encoding='utf-8') for p in parts), encoding='utf-8')\n")
TITLE = "Assemble the fixture deck.html from the placeholder notes and offer it"


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


class HtmlDeliveryPipeline(unittest.TestCase):
    def setUp(self):
        guard = patch("agent_lab.evaluation.official_dataset._README_SHA256", README_SHA256)
        guard.start()
        self.addCleanup(guard.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        config = json.loads(TEMPLATE.read_text())
        (self.root / "plan.json").write_text(json.dumps(config))
        write_archive(self.root / "Mid_Test.zip")
        (self.root / "manifest.json").write_text(json.dumps(load_mid_test(self.root / "Mid_Test.zip")))
        plan = OfficialMidTestPlan(self.root / "plan.json")
        self.workflow = Workflow(self.root / "workflow.sqlite3")
        self.addCleanup(self.workflow.close)
        self.files = FileTools(self.workflow, self.root / "files")
        self.addCleanup(self.files.close)
        self.session = OfficialScenarioSession.initialize(self.workflow, plan, scenario="securities-fund",
                                                          human="requester", plan_sha256=plan.sha256)
        self.goal = self.workflow.create_task(self.session.chat, "requester", "fund_manager",
                                              "Development fixture: deliver deck.html built from placeholder notes")

    def transport(self, sandbox):
        def scripted(payload):
            messages = json.loads(payload)["messages"]
            context = json.loads(messages[1]["content"])
            actor = context["role"]["agent"]
            stage = sum(item["role"] == "assistant" for item in messages)
            results = [json.loads(item["content"]) for item in messages if item["role"] == "tool"]
            parts = list(FRAGMENTS.items())
            if actor == "fund_manager":
                if stage == 0:
                    calls = [tool("delegate_task", {"assignee": "marketing", "title": TITLE}, "delegate")]
                elif stage == 1:
                    child = next(json.loads(item["content"]) for item in reversed(messages) if item["role"] == "user"
                                 and json.loads(item["content"]).get("kind") == "child_task_result")
                    offer = child["offered_artifacts"][0]
                    calls = [tool("accept_artifact", {"artifact_id": offer["artifact_id"], "path": "deck.html"}, "accept"),
                             tool("read_text", {"path": "deck.html"}, "read")]
                else:
                    calls = [tool("submit_for_verification", {"summary": "Received and read deck.html"}, "root-submit")]
            elif stage < len(parts):  # One fragment per response, as a size-limited model would write them.
                calls = [tool("create_text", {"path": parts[stage][0], "content": parts[stage][1]}, f"part-{stage}")]
            elif stage == len(parts):
                calls = ([tool("create_text", {"path": "join.py", "content": JOIN}, "script")] if sandbox else
                         [tool("create_text", {"path": "deck.html", "content": DECK}, "deck")])
            elif sandbox and stage == len(parts) + 1:
                calls = [tool("run_python", {"entrypoint": "join.py", "arguments": [], "outputs": ["deck.html"],
                    "input_files": {"join.py": sha(JOIN), **{path: sha(text) for path, text in parts}}}, "join")]
            else:
                last = results[-1]["result"]
                digest = last["export_sha256"]["deck.html"] if sandbox else last["sha256"]
                calls = [tool("offer_artifact", {"path": "deck.html", "target_task": context["parent_task_id"],
                                                 "expected_sha256": digest}, "offer"),
                         tool("submit_for_verification", {"summary": "deck.html assembled and offered"}, "child-submit")]
            return json.dumps(response(calls)).encode()
        return scripted

    def deliver(self, *, executor=None):
        policy = POLICIES["securities-fund"]
        tools = policy.tools if executor else tuple(name for name in policy.tools if name != "run_python")
        roles = {role["id"]: Role(role["prompt"], tools,
                                  tuple(a for a in self.session.agents if a != role["id"]))
                 for role in self.session.scenario["roles"]}
        scripted = self.transport(executor is not None)
        scheduler = MultiAgentScheduler(self.workflow, self.files, self.goal, human="requester", roles=roles,
            clients={role: DeepSeekClient("synthetic-html-pipeline", scripted) for role in roles},
            mode="offline_fixture", constraints=list(policy.constraints), acceptance_id="fixture-html-pipeline",
            verifier_factory=lambda task: (
                self.files.text_verifier(task["id"], task["assignee"], {"deck.html": DECK}), "fixture-deck-bytes"),
            retrieval=WebRetrieval(self.workflow, self.files, allow_network=False), executor=executor)
        state = scheduler.run()
        self.assertEqual((state["task_state"], state["model_calls"], state["benchmark_valid"]), ("succeeded", 0, False))
        self.assertEqual(sorted(self.session.agents), ["fund_manager", "marketing", "research", "risk"])
        child = self.workflow.db.execute("SELECT * FROM tasks WHERE parent=?", (self.goal,)).fetchone()
        self.assertEqual((child["assignee"], child["state"], child["chat"]), ("marketing", "succeeded", self.session.chat))
        calls = {row["call_id"]: json.loads(row["result"])["result"]
                 for row in self.workflow.db.execute("SELECT call_id,result FROM tool_calls WHERE status='succeeded'")}
        expected = sha(DECK)
        made = calls["join"]["export_sha256"]["deck.html"] if executor else calls["deck"]["sha256"]
        self.assertEqual([made, calls["offer"]["sha256"], calls["accept"]["sha256"], calls["read"]["sha256"]],
                         [expected] * 4)
        self.assertEqual(calls["read"]["content"], DECK)
        copies = [p.read_bytes() for p in (self.root / "files").rglob("deck.html") if "tasks" in p.parts]
        self.assertEqual(copies, [DECK.encode()] * 2)  # The author's file and the receiver's accepted copy.
        return calls

    def test_html_written_with_file_tools_is_handed_off_and_read_unchanged(self):
        calls = self.deliver()
        self.assertEqual([calls[f"part-{n}"]["sha256"] for n in range(2)], [sha(t) for t in FRAGMENTS.values()])

    @unittest.skipUnless(HOST and IMAGE, "Set AGENT_LAB_DOCKER_HOST and a digest-pinned AGENT_LAB_PYTHON_IMAGE for real-container checks")
    def test_html_joined_in_the_real_sandbox_is_handed_off_and_read_unchanged(self):
        executor = DockerPythonExecutor(self.workflow, self.files, docker_host=HOST, image=IMAGE)
        self.addCleanup(executor.close)
        calls = self.deliver(executor=executor)
        self.assertTrue(calls["join"]["cleanup_confirmed"])
        self.assertTrue(calls["join"]["process_sandbox"])


if __name__ == "__main__":
    unittest.main()
