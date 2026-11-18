"""Large single-write checks (proposed 2026-11-18): scripted replies, no model capability claim.

Retained live newsroom replies stopped at 1024 output tokens with 4.3-5.7 KB bodies,
and update_text replaces a whole file, so one file is limited by one reply. These
checks confirm the request carries a selected 4096 ceiling and that a single write of
an article-sized Markdown file or a slide-sized HTML file passes parsing and the file
broker unchanged. They do not show that the model will produce such a write.
"""

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from agent_lab.core import Workflow
from agent_lab.evaluation.official_live import TOOL_POLICY, runtime_config
from agent_lab.files import FileTools
from agent_lab.gateway import ToolGateway
from agent_lab.hkgai import HKGAIClient
from agent_lab.runner import TaskRunner
from agent_lab.runtime import live_clients

ARTICLE = ("## Fact check\n\n" + "Detector studies report false positives for some student writing. " * 180)[:12000]
SLIDES = ("<!doctype html><html><body>"
          + "".join(f"<section class='slide'><h2>Slide {n}</h2><p>{'Semiconductor cycle evidence. ' * 30}</p></section>"
                    for n in range(12))
          + "<script>/* keyboard navigation */</script></body></html>")


def reply(path, content):
    call = {"id": "call-1", "type": "function",
            "function": {"name": "create_text", "arguments": json.dumps({"path": path, "content": content})}}
    return json.dumps({"id": "synthetic", "model": "synthetic-large-write",
                       "usage": {"prompt_tokens": 10, "completion_tokens": 3900, "total_tokens": 3910},
                       "choices": [{"finish_reason": "tool_calls",
                                    "message": {"role": "assistant", "content": None, "tool_calls": [call]}}]}).encode()


class LargeSingleWrites(unittest.TestCase):
    def test_selected_ceiling_reaches_the_hkgai_request(self):
        session = SimpleNamespace(scenario={"id": "software-engineering"})
        plan = SimpleNamespace(config={"runtime": {
            "provider": "hkgai", "tool_policy": TOOL_POLICY, "model": "issued-model",
            "per_scenario_model_attempts": 48, "max_output_tokens": 4096, "api_key_env": "COURSE_TEST_KEY"}})
        live = runtime_config(session, plan, 1, docker_host="unix:///test/docker.sock", image="test-image",
                              allow_network=False, environ={"COURSE_TEST_KEY": "dummy-fixture"},
                              output_token_ceiling=4096)
        (client,) = live_clients(live, ["lead"]).values()
        self.assertEqual((type(client), client.max_tokens, live.socket_timeout), (HKGAIClient, 4096, 90))
        sent = []

        def transport(payload):
            sent.append(json.loads(payload))
            return reply("notes.md", "x")

        HKGAIClient("issued-model", transport, max_tokens=client.max_tokens, tool_choice="required").complete(
            [{"role": "user", "content": "fixture"}], tools=[{"type": "function", "function": {
                "name": "create_text", "parameters": {"type": "object"}}}])
        self.assertEqual(sent[0]["max_tokens"], 4096)
        self.assertNotIn("thinking", sent[0])  # The HKGAI adapter sends no thinking setting.

    def test_article_and_slide_sized_files_are_written_in_one_reply(self):
        for path, content in (("article.md", ARTICLE), ("deck.html", SLIDES)):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                workflow = Workflow(root / "state.sqlite3")
                self.addCleanup(workflow.close)
                for actor, kind in (("user", "human"), ("writer", "agent")):
                    workflow.register_actor(actor, kind)
                task = workflow.create_task(workflow.create_chat("group", ["user", "writer"]), "user", "writer", "Write")
                workflow.start_task(task, "writer")
                files = FileTools(workflow, root / "files")
                self.addCleanup(files.close)
                replies = [reply(path, content)]
                runner = TaskRunner(ToolGateway(workflow, files, task, "writer", human="user", allowed=["create_text"]),
                                    HKGAIClient("synthetic-large-write", lambda payload: replies.pop(0) if replies else
                                                json.dumps({"id": "s", "model": "m", "usage": {
                                                    "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                                                    "choices": [{"finish_reason": "stop", "message": {
                                                        "role": "assistant", "content": "Done."}}]}).encode(),
                                                max_tokens=4096),
                                    mode="offline_fixture", constraints=[], allow_html=path.endswith(".html"))
                runner.run()
                self.assertGreater(len(content.encode()), 11000)
                (record,) = workflow.db.execute("SELECT status FROM tool_calls WHERE name='create_text'").fetchall()
                self.assertEqual(record[0], "succeeded")
                written = [p for p in (root / "files").rglob(path)]
                self.assertEqual(len(written), 1)
                self.assertEqual(written[0].read_text(), content)


if __name__ == "__main__":
    unittest.main()
