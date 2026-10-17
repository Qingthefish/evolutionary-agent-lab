from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, RichLog, Static, Tree

from ..models import clock, short
from .base import Pane


class ConversationsPane(Pane):
    """Sidebar of private (per agent) and group conversations plus a merged feed."""

    def compose(self) -> ComposeResult:
        with Horizontal(classes="split"):
            with Vertical(classes="sidebar"):
                yield Tree("Conversations", id="conversation-tree")
                yield Button("New conversation (Ctrl+N)", id="new-conversation")
            with Vertical(classes="main"):
                yield Static("Select a conversation", id="conversation-header", classes="card")
                yield RichLog(id="conversation-feed", wrap=True, markup=True, highlight=False)
                with Horizontal(classes="composer"):
                    yield Input(placeholder="Message (posting never starts or executes a task)", id="message-input")
                    yield Button("Send", id="send-message", variant="primary")
                    yield Button("New task (Ctrl+T)", id="new-task")

    def on_mount(self):
        self.query_one("#conversation-tree", Tree).show_root = False
        self.conversations = {}

    def fetch(self):
        conversations = self.controller.conversations()
        chat = self.app.selected_chat
        feed = self.controller.feed(chat) if chat in {c["id"] for c in conversations} else None
        return {"conversations": conversations, "feed": feed, "chat": chat}

    def show(self, data):
        self.conversations = {c["id"]: c for c in data["conversations"]}
        tree = self.query_one("#conversation-tree", Tree)
        expanded = {"private": True, "group": True}
        tree.clear()
        branches = {"private": tree.root.add("🔒 Private (by agent)", expand=expanded["private"]),
                    "group": tree.root.add("👥 Groups", expand=expanded["group"])}
        human = self.app.human
        for chat in data["conversations"]:
            others = [m["id"] for m in chat["members"] if m["id"] != human]
            label = (f"[dim]{short(chat['id'], 6)}[/] {', '.join(others)} "
                     f"[dim]· {chat['message_count']} msg · {chat['task_count']} task[/]")
            branches[chat["kind"]].add_leaf(label, data=chat["id"])
        self._render_feed(data["chat"], data["feed"])

    def _render_feed(self, chat, feed):
        header = self.query_one("#conversation-header", Static)
        log = self.query_one("#conversation-feed", RichLog)
        log.clear()
        if chat is None or feed is None:
            header.update("Select a conversation in the sidebar")
            return
        conversation = self.conversations[chat]
        members = ", ".join(f"{m['id']} ({m['kind']})" for m in conversation["members"])
        header.update(f"[b]{conversation['kind'].title()} conversation[/] {short(chat)}  ·  members: {escape(members)}")
        for item in feed:
            when = clock(item["timestamp"])
            if item["type"] == "message":
                log.write(f"[dim]{when}[/] [b]{escape(item['sender'])}[/]: {escape(item['body'])}")
            else:
                detail = item["detail"]
                extra = ""
                if item["kind"] in {"created", "delegated"}:
                    extra = f" → {escape(detail.get('assignee', ''))}"
                elif item["kind"] == "human_requested":
                    extra = f" ({escape(detail.get('kind', ''))})"
                elif item["kind"] == "human_responded":
                    extra = f": {escape(str(detail.get('response', ''))[:120])}"
                log.write(f"[dim]{when}[/] [italic]⚙ task {short(item['task'])} «{escape(item['title'][:50])}» "
                          f"{escape(item['kind'])} by {escape(item['sender'])}{extra}[/]")

    def on_tree_node_selected(self, event):
        if event.node.data:
            self.app.select_chat(event.node.data)

    def on_input_submitted(self, event):
        if event.input.id == "message-input":
            self._send()

    def _send(self):
        chat = self.app.selected_chat
        box = self.query_one("#message-input", Input)
        body = box.value.strip()
        if not chat:
            self.app.notify("Select a conversation first", severity="warning")
            return
        if not body:
            return
        box.value = ""
        self.app.run_backend(lambda: self.controller.post_message(chat, body), success="Message posted")

    def on_button_pressed(self, event):
        if event.button.id == "send-message":
            self._send()
        elif event.button.id == "new-task":
            self.app.action_new_task()
        elif event.button.id == "new-conversation":
            self.app.action_new_conversation()
