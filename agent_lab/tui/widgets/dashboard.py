from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Label, Static

from ..models import duration, short, state_label
from .base import Pane, banner


class DashboardPane(Pane):
    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Static(id="dashboard-summary", classes="card")
            yield Label("Interrupted or uncertain execution (never replayed automatically)", classes="section")
            yield DataTable(id="dashboard-uncertain", cursor_type="row", classes="short-table")
            yield Label("Workflow accounting per conversation — not a model benchmark", classes="section")
            yield DataTable(id="dashboard-metrics", cursor_type="row", classes="short-table")
            yield Label("Offline demo scenarios", classes="section")
            yield banner("Scenarios drive the real workflow, gateway, file broker, approvals, and verifier. "
                         "Only provider responses (and messages marked [scripted]) are fixture data. "
                         "Results are offline_fixture evidence, never live-model benchmarks.", classes="banner warn")
            with Horizontal(classes="split"):
                yield DataTable(id="dashboard-scenarios", cursor_type="row")
                with Vertical(classes="side"):
                    yield Static(id="scenario-detail", classes="card")
                    yield Button("Run selected scenario", id="run-scenario", variant="primary")

    def on_mount(self):
        self.query_one("#dashboard-uncertain", DataTable).add_columns("Task", "Kind", "Detail")
        self.query_one("#dashboard-metrics", DataTable).add_columns(
            "Conversation", "Goals ✓/total", "Subtasks ✓/total", "Total human wait")
        table = self.query_one("#dashboard-scenarios", DataTable)
        table.add_columns("Scenario", "Title")
        self.scenarios = {s["name"]: s for s in self.controller.scenarios()}
        for name, scenario in self.scenarios.items():
            table.add_row(name, scenario["title"], key=name)
        self._describe(next(iter(self.scenarios)))

    def fetch(self):
        return {"status": self.controller.status(), "uncertain": self.controller.uncertain(),
                "metrics": self.controller.metrics()}

    def show(self, data):
        status = data["status"]
        states = "  ".join(f"{state_label(k)}: {v}" for k, v in sorted(status["task_states"].items())) or "no tasks yet"
        self.query_one("#dashboard-summary", Static).update(
            f"[b]Mode:[/] {escape(status['mode'])}   [b]Provider:[/] {escape(status['provider'])}\n"
            f"[b]Conversations:[/] {status['conversations']}   [b]Tasks:[/] {status['tasks']}   "
            f"[b]Awaiting your response:[/] {status['pending_requests']}   "
            f"[b]Approved, not yet executed:[/] {status['awaiting_release']}   "
            f"[b]Uncertain:[/] {status['uncertain']}\n{escape(states)}")
        uncertain = self.query_one("#dashboard-uncertain", DataTable)
        uncertain.clear()
        for item in data["uncertain"]:
            uncertain.add_row(short(item["task"]), "⚠ " + item["kind"], item["detail"])
        if not data["uncertain"]:
            uncertain.add_row("—", "✓ none", "No interrupted runner, reserved tool, held claim, or unconfirmed release")
        metrics = self.query_one("#dashboard-metrics", DataTable)
        metrics.clear()
        for chat, record in data["metrics"].items():
            goals, subtasks = record["goals"], record["subtasks"]
            wait = sum(task["human_wait_seconds"] for task in record["tasks"])
            metrics.add_row(short(chat), f"{goals['succeeded']}/{goals['assigned']}",
                            f"{subtasks['succeeded']}/{subtasks['assigned']}", duration(wait))

    def _describe(self, name):
        scenario = self.scenarios[name]
        self.selected_scenario = name
        self.query_one("#scenario-detail", Static).update(
            f"[b]{escape(scenario['title'])}[/]\n{escape(scenario['description'])}\n\n"
            f"[b]Scripted:[/] {escape(', '.join(scenario['scripted']))}\n"
            f"[b]Real:[/] {escape(', '.join(scenario['real']))}")

    def on_data_table_row_highlighted(self, event):
        if event.data_table.id == "dashboard-scenarios" and event.row_key is not None:
            self._describe(event.row_key.value)

    def on_button_pressed(self, event):
        if event.button.id == "run-scenario":
            name = self.selected_scenario
            self.app.run_backend(lambda: self.controller.run_scenario(name),
                                 success=f"Scenario '{name}' ran (offline_fixture). Check Approvals and Tasks.")
