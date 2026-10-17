from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Label, RichLog

from ..models import clock, short
from .base import Pane


class LogsPane(Pane):
    """Control-center activity and the persisted execution event stream."""

    def compose(self) -> ComposeResult:
        with Horizontal(classes="filters"):
            yield Label("Execution log: persisted workflow events (newest last) and this session's UI activity")
            yield Button("Refresh", id="logs-refresh")
        yield RichLog(id="logs-events", wrap=True, markup=True, max_lines=2000)

    def on_mount(self):
        self.last_sequence, self.last_activity = 0, 0

    def fetch(self):
        return {"events": self.controller.recent_events(300), "activity": list(self.controller.activity)}

    def show(self, data):
        log = self.query_one("#logs-events", RichLog)
        for item in data["activity"]:
            if item["seq"] <= self.last_activity:
                continue
            marker = "✗" if item["level"] == "error" else "•"
            log.write(f"[dim]{clock(item['timestamp'])}[/] [b]{marker} ui[/] {escape(item['message'])}")
            self.last_activity = item["seq"]
        for event in data["events"]:
            if event["sequence"] <= self.last_sequence:
                continue
            detail = ", ".join(f"{k}={str(v)[:40]}" for k, v in event["detail"].items())
            log.write(f"[dim]{clock(event['timestamp'])} #{event['sequence']}[/] task {short(event['task'])} "
                      f"[b]{escape(event['kind'])}[/] by {escape(event['actor'])} {escape(detail)}")
            self.last_sequence = event["sequence"]

    def on_button_pressed(self, event):
        if event.button.id == "logs-refresh":
            self.refresh_data()
