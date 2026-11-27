"""Prototype: expose the classroom platform to a chat UI as one OpenAI-compatible "model".

Proposed 2026-11-27 (prototype, not reviewed). A chat front end such as Open WebUI
talks to this local server instead of a model. Each chat maps to one platform goal:

- the chat's first message is imported as the original task (zero model calls), then
  the goal is advanced until it stops;
- later messages are the operator's actions: ``accept`` (or ``通过``) records a passing
  review, any other text while a proposal awaits review returns it with that text as
  feedback; while a question is pending the text is the answer; ``resend`` / ``重发``
  releases one counted resend after a provider failure; ``status`` / ``状态`` reports
  without advancing; ``show PATH`` / ``查看 PATH`` prints a file; anything else advances.

Every decision is the human operator's own message: nothing is accepted, answered or
resent automatically. HTML files are shown in fenced ``html`` blocks so the chat UI can
render them. The platform's budgets, isolation and review rules are unchanged.
Listens on 127.0.0.1 only and requires the bearer token stored in the local settings.
"""
import argparse
import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import threading
import time
import uuid

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from scripts import classroom  # noqa: E402  (same module object the tests and launcher use)
from agent_lab.core import WorkflowError  # noqa: E402
from agent_lab.tui.controller import ControlCenter  # noqa: E402

MODEL_ID = "agent-lab-classroom"
ACCEPT = {"accept", "通过", "接受"}
RESEND = {"resend", "重发"}
STATUS = {"status", "状态"}
SHOW_PREFIXES = ("show ", "查看 ")
INLINE_TEXT_LIMIT = 6000
INLINE_HTML_LIMIT = 200_000
POLL_SECONDS = 4.0


def _sessions_path():
    return classroom.LOCAL / "webui-sessions.json"


def _load_sessions():
    try:
        return json.loads(_sessions_path().read_text())
    except (OSError, ValueError):
        return {}


def _save_sessions(value):
    classroom.write(_sessions_path(), value)


def chat_key(messages):
    """A stable key for one chat: the digest of its first user message."""
    first = next((m for m in messages if m.get("role") == "user"), None)
    text = _content(first) if first else ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _content(message):
    value = message.get("content", "")
    if isinstance(value, list):  # OpenAI content parts
        return "".join(part.get("text", "") for part in value if isinstance(part, dict))
    return value if isinstance(value, str) else ""


def is_ui_background_task(text):
    """Open WebUI asks the selected model for titles, tags and follow-ups with '### Task:' prompts."""
    return text.lstrip().startswith("### Task:")


def background_reply(text):
    lowered = text.lower()
    if "follow" in lowered:
        return json.dumps({"follow_ups": []})
    if "tag" in lowered:
        return json.dumps({"tags": []})
    if "title" in lowered:
        return json.dumps({"title": "Agent Lab task"})
    return ""


class Platform:
    """One ControlCenter per chat session directory; calls are serialized per session."""

    def __init__(self, config):
        self.config = config
        self.locks = {}
        self.guard = threading.Lock()

    def _lock(self, directory):
        with self.guard:
            return self.locks.setdefault(str(directory), threading.Lock())

    def session(self, messages, chat_id=None):
        # Open WebUI forwards its chat ID; two chats with the same first message stay separate goals.
        key = ("chat:" + chat_id) if chat_id else chat_key(messages)
        sessions = _load_sessions()
        if key in sessions:
            return Path(sessions[key]), False
        goal_text = _content(next(m for m in messages if m.get("role") == "user"))
        if not goal_text.strip():
            raise ValueError("The first message must be the original task text.")
        staging = classroom.LOCAL / "webui-inputs" / (classroom.stamp() + ".txt")
        staging.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        staging.write_text(goal_text)
        directory = classroom.import_text(self.config, staging)
        sessions[key] = str(directory)
        _save_sessions(sessions)
        return directory, True

    # ---- state read directly from the session database (works while Advance runs) ----
    @staticmethod
    def snapshot(directory):
        db = sqlite3.connect(f"file:{directory / 'state' / 'workflow.sqlite3'}?mode=ro", uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            tasks = [dict(r) for r in db.execute("SELECT id,parent,assignee,state FROM tasks ORDER BY rowid")]
            has_runner = db.execute("SELECT 1 FROM sqlite_master WHERE name='runner_sessions'").fetchone()
            runner = dict(db.execute("SELECT task,status FROM runner_sessions").fetchall()) if has_runner else {}
            requests = [dict(r) for r in db.execute(
                "SELECT id,task,kind,prompt FROM requests WHERE answered=0 ORDER BY rowid")]
            attempts = db.execute("SELECT COUNT(*) FROM runner_turns").fetchone()[0] if has_runner else 0
        finally:
            db.close()
        for task in tasks:
            task["runner"] = runner.get(task["id"])
        return {"tasks": tasks, "requests": requests, "attempts": attempts}

    @staticmethod
    def root(snapshot):
        return next(t for t in snapshot["tasks"] if t["parent"] is None)

    @staticmethod
    def awaiting_review(snapshot):
        return [t for t in snapshot["tasks"] if t["state"] == "running" and t["runner"] == "awaiting_verification"]

    @staticmethod
    def uncertain(snapshot):
        return [t for t in snapshot["tasks"] if t["state"] == "running" and t["runner"] == "provider_uncertain"]

    def center(self, directory):
        return ControlCenter(directory / "state", human="operator", live=classroom.live(self.config))

    # ---- one chat turn ----
    def handle(self, messages, emit, chat_id=None):
        directory, created = self.session(messages, chat_id)
        with self._lock(directory):
            text = _content(messages[-1]).strip() if messages and messages[-1].get("role") == "user" else ""
            snap = self.snapshot(directory)
            root = self.root(snap)
            if created:
                emit(f"已导入原题，任务 `{root['id'][:8]}`（零模型调用）。开始运行…\n\n")
                return self.advance(directory, root["id"], emit)
            lowered = text.lower()
            if lowered in STATUS:
                return emit(self.describe(directory, self.snapshot(directory)))
            for prefix in SHOW_PREFIXES:
                if lowered.startswith(prefix):
                    return emit(self.show(directory, text[len(prefix):].strip()))
            center = self.center(directory)
            try:
                pending = self.awaiting_review(snap)
                questions = snap["requests"]
                stuck = self.uncertain(snap)
                if lowered in RESEND:
                    if not stuck:
                        return emit("没有因网络或服务中断而停住的任务，无需重发。\n")
                    center.resend(stuck[0]["id"], "Operator resend from the chat UI after a provider failure")
                    emit(f"已为 `{stuck[0]['id'][:8]}` 放行一次计数重发（不重放已执行的工具效果）。继续运行…\n\n")
                elif pending:
                    task = pending[0]
                    accept = lowered in ACCEPT
                    feedback = ("Accepted by the human operator in the chat UI after inspecting the files."
                                if accept else text)
                    if not feedback:
                        return emit("请回复 `accept` 通过，或写明需要修改的地方。\n")
                    center.review(task["id"], accept=accept, feedback=feedback)
                    emit(("已通过" if accept else "已退回修改") + f" `{task['assignee']}`（`{task['id'][:8]}`）。继续运行…\n\n")
                elif questions and text:
                    request = next((q for q in questions if q["kind"] == "clarification"), None)
                    if request is None:
                        return emit("有待处理的授权请求；原型暂不支持在聊天中批准，请在平台界面的 Approvals 处理。\n")
                    center.answer(request["id"], text)
                    emit("已记录你的回答。继续运行…\n\n")
            except WorkflowError as error:
                return emit(f"操作未执行：{error}\n")
            finally:
                center.close()
            if self.root(self.snapshot(directory))["state"] in classroom.TERMINAL:
                return emit(self.describe(directory, self.snapshot(directory)))
            return self.advance(directory, root["id"], emit)

    def advance(self, directory, root, emit):
        result, failure = {}, []

        def run():
            center = self.center(directory)
            try:
                result.update(center.advance(root))
            except Exception as error:  # Reported to the chat, state stays preserved.
                failure.append(str(error))
            finally:
                center.close()
        worker = threading.Thread(target=run, daemon=True)
        started = time.monotonic()
        worker.start()
        last = None
        while worker.is_alive():
            worker.join(POLL_SECONDS)
            snap = self.snapshot(directory)
            line = "  ".join(f"{t['assignee']}:{t['state']}" for t in snap["tasks"])
            progress = f"⏳ {int(time.monotonic() - started)}s · 请求 {snap['attempts']} · {line}\n"
            if line != last:
                emit(progress)
                last = line
            else:
                emit("")  # Keep the stream alive without repeating the line.
        if failure:
            emit(f"\n运行停止：{failure[0]}\n")
        emit("\n" + self.describe(directory, self.snapshot(directory)))

    def describe(self, directory, snap):
        root = self.root(snap)
        lines = [f"**目标状态：{root['state']}** · 累计请求 {snap['attempts']}", ""]
        lines += [f"- `{t['id'][:8]}` {t['assignee']}: {t['state']}" + (f"（{t['runner']}）" if t["runner"] else "")
                  for t in snap["tasks"]]
        lines.append("")
        pending, stuck = self.awaiting_review(snap), self.uncertain(snap)
        if root["state"] in classroom.TERMINAL:
            lines.append("目标已结束。下面是协调者的当前文件：\n")
            lines += self.files_block(directory, root["id"])
        elif stuck:
            lines.append(f"⚠️ `{stuck[0]['assignee']}` 因网络或服务中断停住。网络恢复后回复 `resend` 重发一次。")
        elif pending:
            task = pending[0]
            lines.append(f"🔍 **`{task['assignee']}` 提交了结果，等你检查。** 文件如下：\n")
            lines += self.files_block(directory, task["id"])
            lines.append("\n检查后回复 `accept` 通过，或直接写需要修改的地方退回。可用 `show 路径` 查看完整文件。")
        elif snap["requests"]:
            request = snap["requests"][0]
            lines.append(f"❓ **等待你的回答**（{request['kind']}）：\n\n{request['prompt']}\n\n直接回复答案即可。")
        else:
            lines.append("当前没有待处理事项。回复任意内容继续运行，或 `status` 查看状态。")
        return "\n".join(lines) + "\n"

    def files_block(self, directory, task):
        center = self.center(directory)
        try:
            out = []
            for record in center.files(task):
                if not record.get("current") or record.get("error"):
                    continue
                path, size = record["path"], record["current"].get("bytes", 0)
                out.append(f"- `{path}`（{size} 字节）")
                if path.lower().endswith((".html", ".htm")) and size <= INLINE_HTML_LIMIT:
                    out.append("\n```html\n" + center.read_file(task, path)["content"] + "\n```\n")
            return out or ["（没有文件）"]
        finally:
            center.close()

    def show(self, directory, path):
        snap = self.snapshot(directory)
        center = self.center(directory)
        try:
            for task in [*self.awaiting_review(snap), self.root(snap), *snap["tasks"]]:
                try:
                    content = center.read_file(task["id"], path)["content"]
                except WorkflowError:
                    continue
                fence = "html" if path.lower().endswith((".html", ".htm")) else (path.rsplit(".", 1)[-1] if "." in path else "")
                limit = INLINE_HTML_LIMIT if fence == "html" else INLINE_TEXT_LIMIT
                clipped = content if len(content) <= limit else content[:limit] + "\n…（已截断）"
                return f"`{task['assignee']}` 的 `{path}`：\n\n```{fence}\n{clipped}\n```\n"
            return f"找不到文件 `{path}`。\n"
        finally:
            center.close()


def chunk(identifier, text=None, finish=None):
    delta = {} if text is None else {"content": text}
    return {"id": identifier, "object": "chat.completion.chunk", "created": int(time.time()), "model": MODEL_ID,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}


def make_handler(platform, token):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # No request bodies or headers in logs.
            sys.stderr.write("%s %s\n" % (self.command, self.path))

        def _authorized(self):
            given = self.headers.get("Authorization", "")
            return secrets.compare_digest(given, "Bearer " + token)

        def _json(self, status, value):
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self._authorized():
                return self._json(401, {"error": {"message": "unauthorized"}})
            if self.path.rstrip("/") in {"/v1/models", "/models"}:
                return self._json(200, {"object": "list", "data": [
                    {"id": MODEL_ID, "object": "model", "owned_by": "agent-lab"}]})
            self._json(404, {"error": {"message": "not found"}})

        def do_POST(self):
            if not self._authorized():
                return self._json(401, {"error": {"message": "unauthorized"}})
            if self.path.rstrip("/") not in {"/v1/chat/completions", "/chat/completions"}:
                return self._json(404, {"error": {"message": "not found"}})
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                messages = [m for m in body.get("messages", []) if isinstance(m, dict) and m.get("role") != "system"]
            except (ValueError, TypeError):
                return self._json(400, {"error": {"message": "invalid JSON body"}})
            if not messages:
                return self._json(400, {"error": {"message": "no messages"}})
            identifier = "chatcmpl-" + uuid.uuid4().hex
            chat_id = (self.headers.get("X-OpenWebUI-Chat-Id") or "").strip()[:128] or None
            last = _content(messages[-1])
            stream = bool(body.get("stream"))
            if is_ui_background_task(last):
                text = background_reply(last)
                if not stream:
                    return self._json(200, {"id": identifier, "object": "chat.completion", "model": MODEL_ID,
                        "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                                     "finish_reason": "stop"}]})
                return self._stream(identifier, lambda emit: emit(text))
            if not stream:
                parts = []
                try:
                    platform.handle(messages, parts.append, chat_id)
                except (ValueError, WorkflowError, OSError) as error:
                    parts.append(f"已停止并保留现场：{error}\n")
                return self._json(200, {"id": identifier, "object": "chat.completion", "model": MODEL_ID,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": "".join(parts)},
                                 "finish_reason": "stop"}]})
            self._stream(identifier, lambda emit: platform.handle(messages, emit, chat_id))

        def _stream(self, identifier, produce):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True

            def emit(text):
                payload = chunk(identifier, text)
                self.wfile.write(b"data: " + json.dumps(payload, ensure_ascii=False).encode() + b"\n\n")
                self.wfile.flush()
            try:
                emit_role = chunk(identifier)
                emit_role["choices"][0]["delta"] = {"role": "assistant"}
                self.wfile.write(b"data: " + json.dumps(emit_role).encode() + b"\n\n")
                try:
                    produce(emit)
                except (ValueError, WorkflowError, OSError) as error:
                    emit(f"已停止并保留现场：{error}\n")
                self.wfile.write(b"data: " + json.dumps(chunk(identifier, finish="stop")).encode() + b"\n\n")
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass  # The chat UI went away; platform state is unaffected and resumes on the next message.

    return Handler


def adapter_token():
    path = classroom.LOCAL / "webui-token.txt"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_text(secrets.token_urlsafe(32))
        path.chmod(0o600)
    return path.read_text().strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--settings", type=Path, default=classroom.LOCAL / "settings.json")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    config = classroom.settings(args.settings)
    classroom.credential(config)  # Fail early, without printing it, if the course key is unavailable.
    token = adapter_token()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(Platform(config), token))
    print(f"Agent Lab chat adapter on http://127.0.0.1:{args.port}/v1  model: {MODEL_ID}")
    print(f"API key for the chat UI is stored in {classroom.LOCAL / 'webui-token.txt'} (not printed).")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
