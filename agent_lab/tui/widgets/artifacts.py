from rich.markup import escape
from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Label, Markdown, Select, Static

from ..models import clock, short, state_label
from .base import Pane, banner


class ArtifactsPane(Pane):
    """Task-owned files (read-only), hash history, and explicit agent handoffs."""

    def compose(self) -> ComposeResult:
        yield banner("Read-only supervisor view through the file broker: only tasks in your conversations, "
                     "no host filesystem browsing, no editing. Agents still cannot read each other's files.")
        with Horizontal(classes="filters"):
            yield Select([], prompt="Task", id="artifact-task")
            yield Button("Refresh", id="artifacts-refresh")
        with Horizontal(classes="split"):
            with Vertical(classes="sidebar wide"):
                yield Label("Files (from broker receipts)", classes="section")
                yield DataTable(id="artifact-files", cursor_type="row")
                yield Static("", id="artifact-history", classes="card")
                yield Label("Artifact transfers between agents", classes="section")
                yield DataTable(id="artifact-transfers", cursor_type="row")
                yield Button("Compare offered snapshot vs received copy", id="artifact-compare")
            with VerticalScroll(classes="main", id="artifact-viewer-scroll"):
                yield Static("Select a file", id="artifact-meta", classes="card")
                yield Static("", id="artifact-viewer")
                yield Markdown("", id="artifact-markdown")

    def on_mount(self):
        self.query_one("#artifact-files", DataTable).add_columns("Path", "Type", "Last op", "SHA-256", "Bytes", "Receipt")
        self.query_one("#artifact-transfers", DataTable).add_columns("From", "To", "SHA-256", "Bytes", "Offered", "Received as")
        self.query_one("#artifact-markdown", Markdown).display = False
        self.task_options, self.files, self.history, self.transfer_rows = [], {}, {}, {}
        self.selected_transfer = None

    def fetch(self):
        tasks = self.controller.tasks()
        task = self.app.selected_task if self.app.selected_task in {t["id"] for t in tasks} else None
        return {"tasks": tasks, "task": task,
                "files": self.controller.files(task) if task else [],
                "history": self.controller.file_history(task) if task else {},
                "transfers": self.controller.transfers(task) if task else self.controller.transfers()}

    def show(self, data):
        options = [(f"{state_label(t['state'])} · {t['assignee']}: {t['title'][:40]} ({short(t['id'], 6)})", t["id"])
                   for t in data["tasks"]]
        select = self.query_one("#artifact-task", Select)
        if options != self.task_options:
            self.task_options = options
            select.set_options(options)
        if data["task"] and select.value != data["task"]:
            select.value = data["task"]
        self.files = {f["path"]: f for f in data["files"]}
        self.history = data["history"]
        table = self.query_one("#artifact-files", DataTable)
        table.clear()
        for item in data["files"]:
            current = item["current"]
            receipt = ("✓ matches" if item["matches_receipt"] else "⚠ disk differs from receipt") if not item["error"] else "✗ " + item["error"][:30]
            table.add_row(item["path"], item["language"], item["last_operation"],
                          short(current["sha256"], 12) if current else "absent",
                          str(current["bytes"]) if current else "—", receipt, key=item["path"])
        transfers = self.query_one("#artifact-transfers", DataTable)
        transfers.clear()
        self.transfer_rows = {t["artifact_id"]: t for t in data["transfers"]}
        for item in data["transfers"]:
            transfers.add_row(f"{item['source_agent']} ({short(item['source_task'], 6)})",
                              f"{item['recipient']} ({short(item['target_task'], 6)})", short(item["sha256"], 12),
                              str(item["bytes"]), clock(item["offered_at"]),
                              item["received_path"] or ("consumed" if item["consumed"] else "not yet accepted"),
                              key=item["artifact_id"])

    def on_select_changed(self, event):
        if event.select.id == "artifact-task" and event.value not in (Select.NULL, Select.BLANK) \
                and event.value != self.app.selected_task:
            self.app.selected_task = event.value
            self.refresh_data()

    def on_data_table_row_highlighted(self, event):
        if event.row_key is None:
            return
        if event.data_table.id == "artifact-files":
            path = event.row_key.value
            versions = self.history.get(path, [])
            lines = [f"{clock(v['timestamp'])} {v['operation']} {short(v['sha256'], 12)} {v['bytes']}B" for v in versions
                     if v["operation"] != "file_read"]
            self.query_one("#artifact-history", Static).update(
                f"[b]Recorded versions of {escape(path)}[/] (hashes only; earlier contents are not retained)\n"
                + escape("\n".join(lines)))
            self._open(path)
        elif event.data_table.id == "artifact-transfers":
            self.selected_transfer = event.row_key.value

    def _open(self, path):
        task = self.app.selected_task
        if self.files.get(path, {}).get("current") is None:
            self._display(f"[b]{escape(path)}[/]: no current file (deleted or absent)", None, None)
            return
        self.app.run_backend(lambda: self.controller.read_file(task, path), quiet=True,
                             then=lambda f: self._display(
                                 f"[b]{escape(f['path'])}[/]  sha256 {f['sha256']}  {f['bytes']} bytes  ({f['language']})",
                                 f["content"], f["language"]))

    def _display(self, meta, content, language):
        self.query_one("#artifact-meta", Static).update(meta)
        viewer = self.query_one("#artifact-viewer", Static)
        markdown = self.query_one("#artifact-markdown", Markdown)
        if content is None:
            viewer.update("")
            markdown.display = False
        elif language == "markdown":
            viewer.update("")
            markdown.display = True
            markdown.update(content)
        else:
            markdown.display = False
            viewer.update(Syntax(content, language if language != "text" else "text", line_numbers=True,
                                 word_wrap=True, theme="monokai"))

    def on_button_pressed(self, event):
        if event.button.id == "artifacts-refresh":
            self.refresh_data()
        elif event.button.id == "artifact-compare":
            artifact = self.selected_transfer
            if not artifact:
                self.app.notify("Highlight a transfer first", severity="warning")
                return

            def show(result):
                meta = f"[b]Transfer {short(artifact, 12)}[/]: {escape(result['status'])}"
                self._display(meta, result["diff"] or "(no differences)", "diff")
            self.app.run_backend(lambda: self.controller.compare_transfer(artifact), quiet=True, then=show)
