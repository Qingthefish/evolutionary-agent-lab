from rich.markup import escape
from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Label, Select, Static

from ..models import clock, pretty, request_label, short
from ..screens.modals import ConfirmScreen
from .base import Pane, banner

STATUS = {"verified": "✓ verified on remote", "succeeded": "✓ succeeded", "failed": "✗ failed",
          "uncertain": "⚠ uncertain — reconcile", "started": "… started (no result recorded)"}


class GitPane(Pane):
    """Read-only repository view plus Git operation evidence. Uses only the Git backend."""

    def compose(self) -> ComposeResult:
        yield banner("Trusted repositories only. Agents commit through the gateway; every push needs your exact approval "
                     "in Approvals (Ctrl+P), then a separate release, then remote verification. Force pushes and branch "
                     "deletion are not possible. Remote GitHub pushes stay disabled until a test remote and credentials "
                     "are configured.")
        with Horizontal(classes="filters"):
            yield Select([], prompt="Repository", id="git-repository")
            yield Button("Unstaged diff", id="git-unstaged")
            yield Button("Staged diff", id="git-staged")
            yield Button("Refresh", id="git-refresh")
        with Horizontal(classes="split"):
            with Vertical(classes="sidebar wide"):
                yield Static("Select a repository", id="git-summary", classes="card")
                yield Label("Changed files", classes="section")
                yield DataTable(id="git-files", cursor_type="row")
                yield Label("Recent commits", classes="section")
                yield DataTable(id="git-commits", cursor_type="row")
                yield Label("Push approvals", classes="section")
                yield DataTable(id="git-pending", cursor_type="row")
                yield Label("Operation evidence (persisted)", classes="section")
                yield DataTable(id="git-operations", cursor_type="row")
                yield Button("Reconcile selected uncertain push", id="git-reconcile", variant="warning")
            with VerticalScroll(classes="main"):
                yield Static("", id="git-detail", classes="card")
                yield Static("", id="git-diff")

    def on_mount(self):
        self.query_one("#git-files", DataTable).add_columns("Path", "Index", "Worktree", "Kind")
        self.query_one("#git-commits", DataTable).add_columns("Commit", "When", "Author", "Subject")
        self.query_one("#git-pending", DataTable).add_columns("Request", "Branch", "Commit", "Status")
        self.query_one("#git-operations", DataTable).add_columns("When", "Operation", "Status", "Actor", "Summary")
        self.repositories, self.operations, self.staged, self.selected_operation = [], {}, False, None
        self.current = None

    def fetch(self):
        repositories = self.controller.git_repositories()
        names = [r["name"] for r in repositories]
        name = self.current if self.current in names else (names[0] if names else None)
        return {"repositories": repositories, "name": name,
                "overview": self.controller.git_overview(name, staged=self.staged) if name else None,
                "operations": self.controller.git_operations(),
                "requests": [r for r in self.controller.requests()
                             if r["action"] and r["action"].get("tool") == "git_push"]}

    def show(self, data):
        names = [r["name"] for r in data["repositories"]]
        select = self.query_one("#git-repository", Select)
        if names != self.repositories:
            self.repositories = names
            select.set_options([(n, n) for n in names])
        self.current = data["name"]
        if data["name"] and select.value != data["name"]:
            select.value = data["name"]
        overview = data["overview"] or {}
        status, diff, log = overview.get("status", {}), overview.get("diff", {}), overview.get("log", [])
        summary = self.query_one("#git-summary", Static)
        if "error" in status:
            summary.update(f"[b]{escape(str(data['name']))}[/]: ✗ {escape(status['error'])}")
        elif status:
            branch = status["branch"] or "(detached)"
            writable = "✓ writable" if branch in status["writable_branches"] else "⊘ read-only for agents"
            summary.update(
                f"[b]Repository:[/] {escape(status['repository'])}   [b]Branch:[/] {escape(branch)} ({writable})\n"
                f"[b]HEAD:[/] {short(status['head'], 12)}   [b]Upstream:[/] {escape(str(status['upstream']))}\n"
                f"[b]Writable branches:[/] {escape(', '.join(status['writable_branches']))}   "
                f"[b]Writable paths:[/] {escape(', '.join(status['writable_paths']))}\n"
                f"[b]Remotes:[/] {escape(', '.join(status['remotes']) or 'none')}   "
                f"[b]Working tree:[/] {'clean' if not status['entries'] else str(len(status['entries'])) + ' change(s)'}")
        files = self.query_one("#git-files", DataTable)
        files.clear()
        for entry in status.get("entries", []):
            files.add_row(entry["path"], entry["index"], entry["worktree"], entry["kind"])
        commits = self.query_one("#git-commits", DataTable)
        commits.clear()
        for commit in log if isinstance(log, list) else []:
            commits.add_row(short(commit["sha"], 10), clock(commit["timestamp"]), commit["author"], commit["subject"][:50])
        pending = self.query_one("#git-pending", DataTable)
        pending.clear()
        for request in data["requests"]:
            binding = request["action"].get("binding", {})
            pending.add_row(short(request["id"]), binding.get("branch", "?"), short(binding.get("commit"), 10),
                            request_label(request))
        operations = self.query_one("#git-operations", DataTable)
        operations.clear()
        self.operations = {op["id"]: op for op in data["operations"]}
        for op in data["operations"]:
            result = op["result"] or {}
            text = result.get("error") or (short(result.get("commit"), 10) if result.get("commit") else result.get("outcome", ""))
            operations.add_row(clock(op["started"]), op["operation"], STATUS.get(op["status"], op["status"]),
                               op["actor"], str(text)[:60], key=op["id"])
        label = "Staged" if self.staged else "Unstaged"
        diff_view = self.query_one("#git-diff", Static)
        if "error" in diff:
            diff_view.update(f"✗ {escape(diff['error'])}")
        elif diff:
            text = diff["diff"] or f"(no {label.lower()} changes)"
            if diff.get("truncated"):
                text += "\n... [output truncated at the configured limit]"
            diff_view.update(Syntax(text, "diff", word_wrap=True, theme="monokai"))
        if not self.selected_operation:
            self.query_one("#git-detail", Static).update(f"[b]{label} diff[/] for {escape(str(data['name']))}")

    def on_data_table_row_highlighted(self, event):
        if event.data_table.id == "git-operations" and event.row_key is not None and event.row_key.value in self.operations:
            op = self.operations[event.row_key.value]
            self.selected_operation = op["id"]
            self.query_one("#git-detail", Static).update(
                f"[b]{escape(op['operation'])}[/] {STATUS.get(op['status'], op['status'])}\n"
                f"[b]Task:[/] {short(op['task'])}  [b]Actor:[/] {escape(op['actor'])}\n"
                f"[b]Arguments:[/]\n{escape(pretty(op['arguments']))}\n[b]Result / reason:[/]\n{escape(pretty(op['result']))}")

    def on_select_changed(self, event):
        if event.select.id == "git-repository" and event.value not in (Select.NULL, Select.BLANK) \
                and event.value != self.current:
            self.current = event.value
            self.refresh_data()

    def on_button_pressed(self, event):
        if event.button.id in {"git-unstaged", "git-staged"}:
            self.staged = event.button.id == "git-staged"
            self.selected_operation = None
            self.refresh_data()
        elif event.button.id == "git-refresh":
            self.refresh_data()
        elif event.button.id == "git-reconcile":
            op = self.operations.get(self.selected_operation)
            if not op or op["operation"] != "push" or op["status"] != "uncertain":
                self.app.notify("Highlight an uncertain push first", severity="warning")
                return
            self.app.push_screen(
                ConfirmScreen("Reconcile uncertain push?", "Reads the remote branch and records what it shows. "
                              "It never pushes or retries.", parameters=op["arguments"], confirm_label="Observe remote"),
                lambda ok: ok and self.app.run_backend(lambda: self.controller.git_reconcile(op["id"]),
                                                       describe=lambda r: f"Remote outcome: {r['outcome']}"))
