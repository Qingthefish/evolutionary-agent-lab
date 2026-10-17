from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, DataTable, Select, Static

from ..models import clock, short
from .base import Pane, banner

ANY = "__any__"


class MemoryPane(Pane):
    """Read-only candidate lessons; every record keeps its own owner/conversation/namespace."""

    def compose(self) -> ComposeResult:
        yield banner("Candidate lessons only. A lesson's later success is an observation, NOT a proven performance "
                     "improvement. Records are never merged across conversations or namespaces.", classes="banner warn")
        with Horizontal(classes="filters"):
            yield Select([("Any agent", ANY)], value=ANY, allow_blank=False, id="memory-agent")
            yield Select([("Any namespace", ANY)], value=ANY, allow_blank=False, id="memory-namespace")
            yield Select([("Any conversation", ANY)], value=ANY, allow_blank=False, id="memory-chat")
            yield Button("Refresh", id="memory-refresh")
        with Horizontal(classes="split"):
            yield DataTable(id="memory-table", cursor_type="row", classes="sidebar wide")
            with VerticalScroll(classes="main"):
                yield Static("Select a lesson", id="memory-detail", classes="card")

    def on_mount(self):
        self.query_one("#memory-table", DataTable).add_columns(
            "Owner", "Namespace", "Conv.", "Status", "Lesson", "Uses ✓/✗/?", "Integrity")
        self.lessons, self._options, self._snapshot = {}, None, None

    def _values(self):
        return tuple(self.query_one(f"#memory-{n}", Select).value for n in ("agent", "namespace", "chat"))

    def fetch(self):
        agent, namespace, chat = (None if v == ANY else v for v in self._values())
        return {"lessons": self.controller.memory(owner=agent, namespace=namespace, chat=chat),
                "all": self.controller.memory(), "conversations": self.controller.conversations()}

    def show(self, data):
        options = (sorted({l["owner"] for l in data["all"]}), sorted({l["namespace"] for l in data["all"]}),
                   [c["id"] for c in data["conversations"]])
        if options != self._options:
            self._options = options
            for name, values, label in (("agent", options[0], "Any agent"), ("namespace", options[1], "Any namespace"),
                                        ("chat", options[2], "Any conversation")):
                select = self.query_one(f"#memory-{name}", Select)
                current = select.value
                select.set_options([(label, ANY)] + [(short(v) if name == "chat" else v, v) for v in values])
                select.value = current if current in values else ANY
        self._snapshot = self._values()
        table = self.query_one("#memory-table", DataTable)
        table.clear()
        self.lessons = {l["memory_id"]: l for l in data["lessons"]}
        for lesson in data["lessons"]:
            counts = {k: sum(u["outcome"] == k for u in lesson["uses"]) for k in ("succeeded", "failed", "unassessed")}
            table.add_row(lesson["owner"], lesson["namespace"], short(lesson["chat"], 6),
                          ("● candidate" if lesson["status"] == "active" else "⊘ retired"), lesson["lesson"][:50],
                          f"{counts['succeeded']}/{counts['failed']}/{counts['unassessed']}",
                          "✓ intact" if lesson["intact"] else "✗ integrity failure", key=lesson["memory_id"])
        if not data["lessons"]:
            self.query_one("#memory-detail", Static).update("No candidate lessons in this scope. Run the Dashboard 'memory' scenario.")

    def on_select_changed(self, event):
        if event.select.id.startswith("memory-") and self._values() != self._snapshot:
            self._snapshot = self._values()
            self.refresh_data()

    def on_data_table_row_highlighted(self, event):
        if event.row_key is None or event.row_key.value not in self.lessons:
            return
        lesson = self.lessons[event.row_key.value]
        sources = "\n".join(f"  task {short(s['task'])}: outcome={s['observation'].get('outcome')} "
                            f"evidence={escape(str(s['observation'].get('evidence'))[:100])} "
                            f"{'✓' if s['intact'] else '✗ corrupted'}" for s in lesson["sources"])
        retrievals = "\n".join(f"  {clock(r['timestamp'])} task {short(r['task'])} lexical score {r['score']:.3f}"
                               for r in lesson["retrievals"]) or "  none"
        uses = "\n".join(f"  task {short(u['task'])} selected {clock(u['selected'])} → observed {u['outcome']}"
                         for u in lesson["uses"]) or "  none"
        self.query_one("#memory-detail", Static).update(
            f"[b]Lesson[/] {lesson['memory_id']}  ([b]candidate[/], proven improvement: [b]no[/])\n"
            f"[b]Owner:[/] {escape(lesson['owner'])}  [b]Namespace:[/] {escape(lesson['namespace'])}  "
            f"[b]Conversation:[/] {lesson['chat']}  [b]Validity:[/] {escape(lesson['status'])}\n\n"
            f"{escape(lesson['lesson'])}\n[b]Tags:[/] {escape(', '.join(lesson['tags']))}\n\n"
            f"[b]Source outcomes[/]\n{sources}\n[b]Retrieval history[/]\n{retrievals}\n[b]Selected uses[/]\n{uses}\n\n"
            "[dim]Observed reuse outcomes are not causal evidence of improvement.[/]")

    def on_button_pressed(self, event):
        if event.button.id == "memory-refresh":
            self.refresh_data()
