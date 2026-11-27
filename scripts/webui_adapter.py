"""Prototype: expose the classroom platform to a chat UI as one OpenAI-compatible "model".

Proposed 2026-11-27 (prototype, not reviewed). A chat front end such as Open WebUI
talks to this local server instead of a model. Each chat maps to one platform goal:

- the chat's first message is imported as the original task (zero model calls), then
  the goal is advanced until it stops;
- later messages are the operator's actions, mapped to the classroom SOP (send ``帮助``):
  review (``通过`` or feedback), answers, ``重发`` after a provider failure, ``状态``,
  ``文件`` / ``查看 PATH``, ``对话``, ``日志``, ``导出`` (menu 4), ``下一题：TEXT`` (same group),
  ``环境检查`` (menu 5) and, in a new chat, ``继续上次`` (menu 3) for a Terminal-imported task
  with attachments. Role ZIPs and approvals stay in the Terminal interface.

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


HELP_TEXT = """**网页界面可用的操作**（对应《周三现场操作 SOP》的六步）

| 想做的事 | 在对话中发送 | SOP 对应 |
| --- | --- | --- |
| 检查环境（不发请求） | `环境检查` | 菜单 5 |
| 开始新题 | 在**新对话**里直接粘贴老师原题 | 菜单 1 |
| 接着上次 Terminal 导入的题（含附件） | 在新对话里发 `继续上次` | 菜单 3 |
| 推进运行 | `继续` | Advance |
| 看当前状态 | `状态` | Tasks |
| 看所有文件 / 某个文件 | `文件` / `查看 路径` | Artifacts |
| 检查后通过 / 退回 | `通过` / 直接写修改意见 | Tasks → Review… |
| 回答澄清问题 | 直接写答案 | Approvals → Answer… |
| 网络或 HTTP 5xx 中断后重发 | `重发` | Tasks → Resend… |
| 看群聊 / 运行日志 | `对话` / `日志` | Conversations / Logs |
| 同组发下一题 | `下一题：题目原文` | Ctrl+T 选原群 |
| 导出结果 | `导出` | 菜单 4 |

老师给**角色 ZIP** 时仍按 SOP 用 Terminal 菜单 **2**；网页原型只处理普通文字题。
每个决定都要基于你看过的实际内容；网页不会自动通过、代答、代批或重发。
"""

ACCEPT = {"accept", "通过", "接受"}
RESEND = {"resend", "重发"}
STATUS = {"status", "状态"}
HELP = {"help", "帮助", "?", "？"}
DOCTOR = {"doctor", "环境检查", "检查环境"}
CONTINUE_LAST = {"继续上次", "continue last"}
ADVANCE = {"继续", "continue", "advance", "运行"}
FILES = {"files", "文件"}
LOG = {"log", "日志"}
CONVERSATION = {"messages", "对话", "群聊"}
EXPORT = {"export", "导出"}
SHOW_PREFIXES = ("show ", "查看 ")
NEXT_PREFIXES = ("下一题：", "下一题:", "next:")
PAUSED = {"paused": "已暂停", "budget_paused": "到达请求、令牌或时长的运行额度检查点",
          "progress_paused": "到达重复动作检查点"}
LOG_KINDS = {"started", "delegated", "completion_proposed", "human_review_recorded", "human_requested",
             "human_responded", "provider_request_failed", "output_limit_reached", "provider_resend_released",
             "succeeded", "failed", "child_replaced", "finish_window_exhausted", "execution_budget_paused",
             "execution_paused", "failed_subtask_waived"}


def _normalized(text):
    return text.strip().strip("。.!！").strip().lower()


def _prefixed(text, prefixes):
    for prefix in prefixes:
        if text.lower().startswith(prefix):
            return text[len(prefix):].strip()
    return None


class Platform:
    """One ControlCenter per chat session directory; calls are serialized per session."""

    def __init__(self, config):
        self.config = config
        self.locks = {}
        self.guard = threading.Lock()

    def _lock(self, directory):
        with self.guard:
            return self.locks.setdefault(str(directory), threading.Lock())

    # ---- chat <-> platform session -------------------------------------------------
    @staticmethod
    def _key(messages, chat_id):
        # Open WebUI forwards its chat ID; two chats with the same first message stay separate goals.
        return ("chat:" + chat_id) if chat_id else chat_key(messages)

    @staticmethod
    def binding(key):
        value = _load_sessions().get(key)
        if value is None:
            return None
        if isinstance(value, str):  # Earlier prototype records: directory only, first root.
            directory = Path(value)
            return {"directory": directory, "root": json.loads((directory / "session.json").read_text())["task"]}
        return {"directory": Path(value["directory"]), "root": value["root"]}

    @staticmethod
    def bind(key, directory, root):
        sessions = _load_sessions()
        sessions[key] = {"directory": str(directory), "root": root}
        _save_sessions(sessions)

    def import_goal(self, text):
        staging = classroom.LOCAL / "webui-inputs" / (classroom.stamp() + ".txt")
        staging.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        staging.write_text(text)
        directory = classroom.import_text(self.config, staging)
        return directory, json.loads((directory / "session.json").read_text())["task"]

    # ---- state read directly from the session database (works while Advance runs) ----
    @staticmethod
    def snapshot(directory, root):
        db = sqlite3.connect(f"file:{directory / 'state' / 'workflow.sqlite3'}?mode=ro", uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            rows = [dict(r) for r in db.execute("SELECT id,parent,assignee,state,chat FROM tasks ORDER BY rowid")]
            has_runner = db.execute("SELECT 1 FROM sqlite_master WHERE name='runner_sessions'").fetchone()
            runner = dict(db.execute("SELECT task,status FROM runner_sessions").fetchall()) if has_runner else {}
            tree, frontier = [], {root}
            while frontier:  # This goal's tree only; other goals in the same group stay separate.
                level = [r for r in rows if r["id"] in frontier]
                tree += level
                frontier = {r["id"] for r in rows if r["parent"] in {t["id"] for t in level}}
            ids = [t["id"] for t in tree]
            marks = ",".join("?" * len(ids))
            requests = [dict(r) for r in db.execute(
                f"SELECT id,task,kind,prompt,action,answered,approved,consumed FROM requests WHERE task IN ({marks}) "
                f"ORDER BY rowid", ids)]
            attempts = db.execute(f"SELECT COUNT(*) FROM runner_turns WHERE task IN ({marks})", ids).fetchone()[0] \
                if has_runner else 0
        finally:
            db.close()
        for task in tree:
            task["runner"] = runner.get(task["id"])
        return {"tasks": tree, "requests": requests, "attempts": attempts, "root": tree[0] if tree else None}

    @staticmethod
    def running(snapshot, status):
        return [t for t in snapshot["tasks"] if t["state"] == "running" and t["runner"] == status]

    @staticmethod
    def paused(snapshot):
        return [t for t in snapshot["tasks"] if t["state"] == "running" and t["runner"] in PAUSED]

    def center(self, directory):
        return ControlCenter(directory / "state", human="operator", live=classroom.live(self.config))

    # ---- one chat turn ----------------------------------------------------------------
    def handle(self, messages, emit, chat_id=None):
        text = _content(messages[-1]).strip() if messages and messages[-1].get("role") == "user" else ""
        command = _normalized(text)
        if command in HELP:
            return emit(HELP_TEXT)
        if command in DOCTOR:
            return emit(self.doctor())
        key = self._key(messages, chat_id)
        bound = self.binding(key)
        if bound is None:
            if command in CONTINUE_LAST:
                return self.continue_last(key, emit)
            if not text:
                return emit("请在新对话里粘贴老师的原题，或发送 `帮助` 查看可用操作。\n")
            directory, root = self.import_goal(text)
            self.bind(key, directory, root)
            emit(f"已导入原题，任务 `{root[:8]}`（零模型调用）。开始运行…（发送 `帮助` 查看全部操作）\n\n")
            with self._lock(directory):
                return self.advance(directory, root, emit)
        directory, root = bound["directory"], bound["root"]
        with self._lock(directory):
            return self.act(key, directory, root, text, command, emit)

    def act(self, key, directory, root, text, command, emit):
        if command in CONTINUE_LAST:
            return emit("这个对话已经连着一个题目。要接上 Terminal 里的上次现场，请开一个**新对话**再发 `继续上次`。\n")
        if command in STATUS:
            return emit(self.describe(directory, self.snapshot(directory, root)))
        if command in FILES:
            return emit(self.all_files(directory, root))
        if command in LOG:
            return emit(self.log(directory, root))
        if command in CONVERSATION:
            return emit(self.conversation(directory, root))
        if command in EXPORT:
            return emit(self.export(directory, root))
        path = _prefixed(text, SHOW_PREFIXES)
        if path:
            return emit(self.show(directory, root, path))
        next_goal = _prefixed(text, NEXT_PREFIXES)
        if next_goal is not None:
            return self.next_goal(key, directory, root, next_goal, emit)
        snap = self.snapshot(directory, root)
        center = self.center(directory)
        try:
            pending = self.running(snap, "awaiting_verification")
            questions = [q for q in snap["requests"] if not q["answered"] and q["kind"] == "clarification"]
            approvals = [q for q in snap["requests"] if not q["answered"] and q["kind"] == "approval"]
            stuck = self.running(snap, "provider_uncertain")
            if command in RESEND:
                if not stuck:
                    return emit("没有因网络或服务中断而停住的任务，无需重发。\n")
                center.resend(stuck[0]["id"], "Operator resend from the chat UI after a provider failure")
                emit(f"已为 `{stuck[0]['id'][:8]}` 放行一次计数重发（不重放已执行的工具效果）。继续运行…\n\n")
            elif pending and command not in ADVANCE:
                task = pending[0]
                accept = command in ACCEPT
                feedback = "Accepted by the human operator in the chat UI after inspecting the files." if accept else text
                if not feedback:
                    return emit("请回复 `通过`，或写明需要修改的地方。\n")
                center.review(task["id"], accept=accept, feedback=feedback)
                emit(("已通过" if accept else "已退回修改") + f" `{task['assignee']}`（`{task['id'][:8]}`）。继续运行…\n\n")
            elif questions and command not in ADVANCE:
                center.answer(questions[0]["id"], text)
                emit("已记录你的回答。继续运行…\n\n")
            elif approvals:
                return emit(self.describe(directory, snap))
            elif command not in ADVANCE:
                return emit("没有识别这条指令，也没有等你处理的事项。发送 `继续` 推进运行，或 `帮助` 查看全部操作。\n")
        except WorkflowError as error:
            return emit(f"操作未执行：{error}\n")
        finally:
            center.close()
        snap = self.snapshot(directory, root)
        if snap["root"]["state"] in classroom.TERMINAL:
            return emit(self.describe(directory, snap))
        return self.advance(directory, root, emit)

    # ---- SOP actions --------------------------------------------------------------------
    def doctor(self):
        value = classroom.doctor(self.config)
        rows = [("界面依赖", value["interface_installed"]), ("课程凭证", value["course_key_available"]),
                ("Docker socket", value["docker_socket_present"])]
        lines = ["**环境检查**（零模型调用，对应菜单 5）", "", "| 项目 | 结果 |", "| --- | --- |"]
        lines += [f"| {name} | {'✅ true' if ok else '❌ false'} |" for name, ok in rows]
        lines += [f"| 模型 | `{value['model']}` |", "", "未检查：API 当时是否可用、课堂题格式与用时、未知题正确性。"]
        return "\n".join(lines) + "\n"

    def continue_last(self, key, emit):
        try:
            current = json.loads((classroom.LOCAL / "current.json").read_text())
        except (OSError, ValueError):
            return emit("没有找到上次的现场。请先在 Terminal 启动器选 **1** 导入题目（可带附件）。\n")
        if current.get("kind") != "text":
            return emit("上次的现场是**角色 ZIP**，请继续在 Terminal 启动器用菜单 **3**（或 **2** 进入场景）处理。\n")
        directory = Path(current["directory"])
        for other in _load_sessions().values():
            if isinstance(other, dict) and Path(other["directory"]) == directory:
                return emit("上次的现场已经连在另一个网页对话里，请回到那个对话继续。\n")
        root = json.loads((directory / "session.json").read_text())["task"]
        self.bind(key, directory, root)
        emit(f"已接上 Terminal 导入的现场 `{directory.name}`（任务 `{root[:8]}`，不清空文件、不重置次数）。\n\n")
        with self._lock(directory):
            return emit(self.describe(directory, self.snapshot(directory, root)))

    def next_goal(self, key, directory, root, goal, emit):
        if not goal:
            return emit("请在 `下一题：` 后面粘贴下一题的原文。\n")
        snap = self.snapshot(directory, root)
        if snap["root"]["state"] not in classroom.TERMINAL:
            return emit("当前题目还没结束，先处理完再发布同组下一题。\n")
        center = self.center(directory)
        try:
            result = center.create_task(snap["root"]["chat"], "coordinator", goal,
                                        constraints=classroom.TEXT_TASK_CONSTRAINTS)
            task = result["task"]
            center.call(lambda b: b.files.provide_text(task, b.human, "inputs/teacher-goal.txt", goal))
        except WorkflowError as error:
            return emit(f"未发布下一题：{error}\n")
        finally:
            center.close()
        self.bind(key, directory, task)
        emit(f"已在同一群组发布下一题，任务 `{task[:8]}`（零模型调用）。上一题的文件不会自动带过来，"
             "需要的数据请在题目里写明。开始运行…\n\n")
        return self.advance(directory, task, emit)

    def export(self, directory, root):
        output = classroom.export_text(self.config, directory)
        count = sum(1 for path in (output / "files").rglob("*") if path.is_file())
        state = self.snapshot(directory, root)["root"]["state"]
        note = "" if state in classroom.TERMINAL else "\n\n⚠️ 题目尚未结束：这是当前产物，展示时请标“进行中/待核查”。"
        return (f"**已导出**（对应菜单 4，零模型调用）：`{output}`\n\n- `files/任务ID/`：各任务当前文件，共 {count} 个"
                f"\n- `results.json`：状态与指标\n- `conversations.json`：对话{note}\n")

    def all_files(self, directory, root):
        snap = self.snapshot(directory, root)
        lines = ["**全部文件**（发送 `查看 路径` 看内容）", ""]
        center = self.center(directory)
        try:
            for task in snap["tasks"]:
                files = [f for f in center.files(task["id"]) if f.get("current") and not f.get("error")]
                lines.append(f"- `{task['id'][:8]}` {task['assignee']}（{task['state']}）")
                lines += [f"  - `{f['path']}`（{f['current']['bytes']} 字节）" for f in files] or ["  - （没有文件）"]
        finally:
            center.close()
        return "\n".join(lines) + "\n"

    def log(self, directory, root, limit=20):
        ids = {t["id"] for t in self.snapshot(directory, root)["tasks"]}
        center = self.center(directory)
        try:
            events = [e for e in center.recent_events(400) if e["task"] in ids and e["kind"] in LOG_KINDS][-limit:]
        finally:
            center.close()
        lines = [f"**最近 {len(events)} 条运行记录**（对应 Logs）", ""]
        for event in events:
            stamp = time.strftime("%H:%M:%S", time.localtime(event["timestamp"]))
            detail = event["detail"] if isinstance(event["detail"], dict) else {}
            extra = detail.get("diagnostics", {}).get("kind") or detail.get("decision") or detail.get("assignee") or ""
            lines.append(f"- {stamp} `{event['task'][:8]}` {event['actor']} · {event['kind']}" + (f" · {extra}" if extra else ""))
        return "\n".join(lines) + "\n"

    def conversation(self, directory, root, limit=12):
        chat = self.snapshot(directory, root)["root"]["chat"]
        center = self.center(directory)
        try:
            items = [i for i in center.feed(chat) if i["type"] == "message"][-limit:]
        finally:
            center.close()
        lines = [f"**群聊最近 {len(items)} 条**（对应 Conversations）", ""]
        for item in items:
            body = item["body"] if len(item["body"]) <= 500 else item["body"][:500] + "…"
            lines.append(f"- **{item['sender']}**：{body}")
        return "\n".join(lines) + "\n"

    # ---- running and reporting ------------------------------------------------------------
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
            snap = self.snapshot(directory, root)
            line = "  ".join(f"{t['assignee']}:{t['state']}" for t in snap["tasks"])
            if line != last:
                emit(f"⏳ {int(time.monotonic() - started)}s · 请求 {snap['attempts']} · {line}\n")
                last = line
            else:
                emit("")  # Keep the stream alive without repeating the line.
        if failure:
            emit(f"\n运行停止：{failure[0]}\n")
        emit("\n" + self.describe(directory, self.snapshot(directory, root)))

    def describe(self, directory, snap):
        root = snap["root"]
        lines = [f"**目标状态：{root['state']}** · 累计请求 {snap['attempts']}", ""]
        lines += [f"- `{t['id'][:8]}` {t['assignee']}: {t['state']}" + (f"（{t['runner']}）" if t["runner"] else "")
                  for t in snap["tasks"]]
        lines.append("")
        pending, stuck, paused = self.running(snap, "awaiting_verification"), self.running(snap, "provider_uncertain"), \
            self.paused(snap)
        questions = [q for q in snap["requests"] if not q["answered"] and q["kind"] == "clarification"]
        approvals = [q for q in snap["requests"] if q["kind"] == "approval" and (not q["answered"] or (
            q["approved"] and not q["consumed"]))]
        if root["state"] in classroom.TERMINAL:
            lines.append("目标已结束。下面是协调者的当前文件；发送 `导出` 保存结果，或 `下一题：原文` 在同组继续。\n")
            lines += self.files_block(directory, root["id"])
        elif stuck:
            lines.append(f"⚠️ `{stuck[0]['assignee']}` 因网络或 HTTP 5xx 中断停住（provider_uncertain）。"
                         "核对后发送 `重发` 放行一次计数重发；不会自动重试。")
        elif approvals:
            lines.append(f"🔐 有一条授权请求（`{approvals[0]['id'][:8]}`）。普通文字题默认不配置需要授权的动作，"
                         "网页原型不处理授权；请按 SOP 在 Terminal 界面的 Approvals 核对并决定。")
        elif pending:
            task = pending[0]
            lines.append(f"🔍 **`{task['assignee']}` 提交了结果，等你检查。** 文件如下：\n")
            lines += self.files_block(directory, task["id"])
            lines.append("\n检查后回复 `通过`，或直接写需要修改的地方退回。可用 `查看 路径` 看完整文件。")
        elif questions:
            lines.append(f"❓ **等待你的回答**：\n\n{questions[0]['prompt']}\n\n直接回复答案即可。")
        elif paused:
            lines.append(f"⏸️ `{paused[0]['assignee']}` {PAUSED[paused[0]['runner']]}。这不是老师的扣分规则；"
                         "网页原型不会续额或重置计数，请在 Terminal 界面核对进展后按 SOP 处理。")
        else:
            lines.append("当前没有待处理事项。发送 `继续` 推进运行，`状态` 查看，或 `帮助` 查看全部操作。")
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

    def show(self, directory, root, path):
        snap = self.snapshot(directory, root)
        center = self.center(directory)
        try:
            order = [*self.running(snap, "awaiting_verification"), snap["root"], *snap["tasks"]]
            for task in order:
                try:
                    content = center.read_file(task["id"], path)["content"]
                except WorkflowError:
                    continue
                fence = "html" if path.lower().endswith((".html", ".htm")) else (path.rsplit(".", 1)[-1] if "." in path else "")
                limit = INLINE_HTML_LIMIT if fence == "html" else INLINE_TEXT_LIMIT
                clipped = content if len(content) <= limit else content[:limit] + "\n…（已截断）"
                return f"`{task['assignee']}` 的 `{path}`：\n\n```{fence}\n{clipped}\n```\n"
            return f"找不到文件 `{path}`。发送 `文件` 查看全部路径。\n"
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
