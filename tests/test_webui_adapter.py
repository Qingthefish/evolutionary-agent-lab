"""OpenAI-compatible chat adapter prototype over the classroom platform (proposed 2026-11-27).

Real loopback HTTP to the adapter and a scripted provider transport; no model calls.
"""
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from scripts import classroom as c
from scripts import webui_adapter as w
from agent_lab.hkgai import HKGAIHTTP


import itertools
_IDS = itertools.count()


def tool_reply(*calls):
    return json.dumps({"id": "r", "model": "synthetic", "usage": {"prompt_tokens": 5, "completion_tokens": 2,
        "total_tokens": 7}, "choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
        "tool_calls": [{"id": f"c{next(_IDS)}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
                       for i, (name, args) in enumerate(calls)]}}]}).encode()


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.bind(str(base / "docker.sock"))
        self.addCleanup(self.sock.close)
        config = {"model": "test-no-real-provider", "key_env": "CLASSROOM_TEST_KEY", "credential_file": "not-used",
                  "docker_host": "unix://" + str(base / "docker.sock"), "python_image": "python@sha256:" + "a" * 64}
        for p in (patch.dict("os.environ", {"CLASSROOM_TEST_KEY": "synthetic-test-key"}),
                  patch.object(c, "LOCAL", base / "local"), patch.object(w, "POLL_SECONDS", 0.05)):
            p.start(); self.addCleanup(p.stop)
        self.token = w.adapter_token()
        self.server = w.ThreadingHTTPServer(("127.0.0.1", 0), w.make_handler(w.Platform(config), self.token))
        thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join()))
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"
        self.replies = []
        transport = patch.object(HKGAIHTTP, "__call__", side_effect=lambda payload: self.replies.pop(0))
        transport.start(); self.addCleanup(transport.stop)

    def request(self, path, body=None, token=None, chat_id=None):
        data = None if body is None else json.dumps(body).encode()
        headers = {"Authorization": "Bearer " + (self.token if token is None else token), "Content-Type": "application/json"}
        if chat_id:
            headers["X-OpenWebUI-Chat-Id"] = chat_id
        req = urllib.request.Request(self.url + path, data=data, method="POST" if body else "GET", headers=headers)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=20) as response:
            return response.read().decode()

    def chat(self, *texts, stream=True, chat_id=None):
        messages = []
        for i, text in enumerate(texts):
            messages.append({"role": "user", "content": text})
            if i < len(texts) - 1:
                messages.append({"role": "assistant", "content": "(earlier reply)"})
        raw = self.request("/chat/completions", {"model": w.MODEL_ID, "messages": messages, "stream": stream},
                           chat_id=chat_id)
        if not stream:
            return json.loads(raw)["choices"][0]["message"]["content"]
        out = []
        for line in raw.splitlines():
            if line.startswith("data: ") and line != "data: [DONE]":
                out.append(json.loads(line[6:])["choices"][0]["delta"].get("content", ""))
        self.assertTrue(raw.rstrip().endswith("data: [DONE]"))
        return "".join(out)

    def test_models_require_the_token(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("/models", token="wrong")
        self.assertEqual(caught.exception.code, 401)
        self.assertIn(w.MODEL_ID, self.request("/models"))

    def test_ui_background_tasks_create_no_goal_and_send_no_request(self):
        reply = self.chat("### Task:\nGenerate a concise title for the chat history.", stream=False)
        self.assertEqual(json.loads(reply), {"title": "Agent Lab task"})
        self.assertFalse((c.LOCAL / "webui-sessions.json").exists())

    def test_import_run_review_in_chat_and_html_shown_for_rendering(self):
        goal = "Make a one-page HTML status report."
        html = "<!doctype html><h1>Status</h1>"
        self.replies += [tool_reply(("create_text", {"path": "report.html", "content": html})),
                         tool_reply(("submit_for_verification", {"summary": "Wrote report.html, a one-page status report."}))]
        first = self.chat(goal)
        self.assertIn("已导入原题", first)
        self.assertIn("等你检查", first)
        self.assertIn("```html\n" + html, first)  # Rendered as an artifact by the chat UI.
        self.assertIn("report.html", self.chat(goal, "status"))  # Status does not advance or call the provider.
        shown = self.chat(goal, "status", "show report.html")
        self.assertIn(html, shown)
        done = self.chat(goal, "status", "show report.html", "accept")
        self.assertIn("已通过", done)
        self.assertIn("目标状态：succeeded", done)
        self.assertEqual(self.replies, [])  # Exactly the scripted provider replies were used.
        sessions = json.loads((c.LOCAL / "webui-sessions.json").read_text())
        self.assertEqual(len(sessions), 1)  # One chat, one platform goal.

    def test_feedback_returns_the_proposal_with_the_operators_words(self):
        goal = "Write notes.md."
        self.replies += [tool_reply(("create_text", {"path": "notes.md", "content": "draft"})),
                         tool_reply(("submit_for_verification", {"summary": "Wrote notes.md with the draft notes."})),
                         tool_reply(("submit_for_verification", {"summary": "Revised notes.md after the feedback."}))]
        self.chat(goal)
        returned = self.chat(goal, "Please add a heading.")
        self.assertIn("已退回修改", returned)
        self.assertIn("目标状态：running", returned)
        self.assertEqual(self.replies, [])
        directory = Path(json.loads((c.LOCAL / "webui-sessions.json").read_text()).popitem()[1])
        import sqlite3
        db = sqlite3.connect(directory / "state" / "workflow.sqlite3")
        feedback = [json.loads(r[0]) for r in db.execute("SELECT detail FROM events WHERE kind='human_review_recorded'")]
        db.close()
        self.assertEqual(feedback[0]["feedback"], "Please add a heading.")

    def test_forwarded_chat_ids_keep_identical_first_messages_as_separate_goals(self):
        goal = "Write a.md."
        for _ in range(2):
            self.replies += [tool_reply(("create_text", {"path": "a.md", "content": "x"})),
                             tool_reply(("submit_for_verification", {"summary": "Wrote a.md with the requested text."}))]
        self.assertIn("已导入原题", self.chat(goal, chat_id="chat-one"))
        self.assertIn("已导入原题", self.chat(goal, chat_id="chat-two"))  # Not attached to chat-one's goal.
        sessions = json.loads((c.LOCAL / "webui-sessions.json").read_text())
        self.assertEqual(set(sessions), {"chat:chat-one", "chat:chat-two"})
        self.assertNotEqual(sessions["chat:chat-one"], sessions["chat:chat-two"])
        self.assertNotIn("已导入原题", self.chat(goal, "status", chat_id="chat-one"))


if __name__ == "__main__":
    unittest.main()
