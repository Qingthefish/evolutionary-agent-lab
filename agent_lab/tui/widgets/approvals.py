from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Label, Static

from ..models import pretty, request_label, short, state_label
from ..screens.modals import ConfirmScreen, TextPromptScreen
from .base import Pane, banner


class ApprovalsPane(Pane):
    """Clarifications, approval decisions, trusted release, and persistent history."""

    def compose(self) -> ComposeResult:
        yield banner("Three distinct steps: (1) an agent REQUESTS approval and pauses; (2) you APPROVE or REJECT the "
                     "exact action; (3) RELEASE executes that exact action once through the trusted gateway, and its "
                     "verified result is recorded. Rejection cancels the task and its unfinished subtasks.")
        with Horizontal(classes="split"):
            with Vertical(classes="sidebar wide"):
                yield Label("Needs your attention", classes="section")
                yield DataTable(id="approvals-pending", cursor_type="row")
                with Horizontal(classes="button-row"):
                    yield Button("Answer…", id="approval-answer", variant="primary")
                    yield Button("Approve…", id="approval-approve", variant="success")
                    yield Button("Reject…", id="approval-reject", variant="error")
                    yield Button("Release & execute…", id="approval-release", variant="warning")
                yield Label("History (persisted)", classes="section")
                yield DataTable(id="approvals-history", cursor_type="row")
            with VerticalScroll(classes="main"):
                yield Static("Select a request", id="approval-detail", classes="card")

    def on_mount(self):
        for table in ("#approvals-pending", "#approvals-history"):
            self.query_one(table, DataTable).add_columns("Request", "Kind", "Agent", "Status", "Prompt")
        self.records, self.selected = {}, None

    def fetch(self):
        return self.controller.requests()

    def show(self, requests):
        self.records = {r["id"]: r for r in requests}
        pending = self.query_one("#approvals-pending", DataTable)
        history = self.query_one("#approvals-history", DataTable)
        pending.clear()
        history.clear()
        for request in requests:
            actionable = (request["status"] == "pending" and request["responder"] == self.app.human) \
                or request["status"] == "granted_awaiting_release"
            row = (short(request["id"]), request["kind"], request["assignee"], request_label(request), request["prompt"][:60])
            (pending if actionable else history).add_row(*row, key=request["id"])
        if pending.row_count == 0:
            pending.add_row("—", "", "", "✓ nothing awaiting you", "", key="__none__")
        if self.selected in self.records:
            self._describe(self.records[self.selected])

    def _describe(self, request):
        self.selected = request["id"]
        action = (f"\n[b]Exact action (bound by digest {request['digest'][:16]}…):[/]\n{escape(pretty(request['action']))}"
                  if request["action"] else "")
        outcome = ""
        if request["outcome"]:
            outcome = f"\n[b]Execution result:[/] {escape(request['outcome']['kind'])}\n{escape(pretty(request['outcome']['detail']))}"
        self.query_one("#approval-detail", Static).update(
            f"[b]Request[/] {request['id']}  [b]{escape(request['kind'])}[/]\n"
            f"[b]Status:[/] {escape(request_label(request))}\n"
            f"[b]Task:[/] {request['task']} ({escape(state_label(request['task_state']))})  [b]Agent:[/] {escape(request['assignee'])}\n"
            f"[b]Task title:[/] {escape(request['title'])}\n[b]Addressed to:[/] {escape(request['responder'])}\n\n"
            f"[b]Prompt:[/] {escape(request['prompt'])}{action}"
            f"{chr(10) + '[b]Response:[/] ' + escape(str(request['response'])) if request['response'] else ''}{outcome}")

    def on_data_table_row_highlighted(self, event):
        if event.row_key is not None and event.row_key.value in self.records:
            self._describe(self.records[event.row_key.value])

    def _selected(self, *, kind=None, status=None):
        # Buttons act on the highlighted row of "Needs your attention"; the
        # confirmation dialog then shows the exact request and action.
        pending = self.query_one("#approvals-pending", DataTable)
        key = None
        if pending.row_count:
            key = pending.coordinate_to_cell_key((min(pending.cursor_row, pending.row_count - 1), 0)).row_key.value
        request = self.records.get(key)
        if request is None:
            self.app.notify("Highlight a request under 'Needs your attention' first", severity="warning")
            return None
        self._describe(request)
        if (kind and request["kind"] != kind) or (status and request["status"] != status):
            self.app.notify(f"This action needs a {kind or ''} request with status {status}", severity="warning")
            return None
        return request

    def on_button_pressed(self, event):
        button = event.button.id
        if button == "approval-answer":
            request = self._selected(kind="clarification", status="pending")
            if request:
                self.app.push_screen(TextPromptScreen("Answer clarification", request["prompt"], placeholder="Your answer"),
                                     lambda answer: answer and self.app.run_backend(
                                         lambda: self.controller.answer(request["id"], answer),
                                         success="Answer recorded; task resumed", advance=request["task"]))
        elif button in {"approval-approve", "approval-reject"}:
            request = self._selected(kind="approval", status="pending")
            if request:
                approve = button == "approval-approve"
                body = ("Approving records your decision for exactly this action. Nothing executes until you "
                        "separately release it." if approve else
                        "Rejecting cancels this task and all of its unfinished subtasks. This cannot be undone.")
                self.app.push_screen(
                    ConfirmScreen("Approve exact action?" if approve else "Reject and cancel task?", body,
                                  parameters={"request": request["id"], "task": request["task"], "action": request["action"]},
                                  confirm_label="Approve" if approve else "Reject", danger=not approve),
                    lambda ok: ok and self.app.run_backend(
                        lambda: self.controller.decide(request["id"], approve),
                        success="Approval recorded (not executed)" if approve else "Rejected; task cancelled",
                        advance=None if approve else request["task"]))
        elif button == "approval-release":
            request = self._selected(kind="approval", status="granted_awaiting_release")
            if request:
                self.app.push_screen(
                    ConfirmScreen("Release and execute this exact action?",
                                  "The trusted gateway re-validates the exact action, consumes the approval once, and "
                                  "executes it. If execution is interrupted the effect is uncertain and will NOT be retried.",
                                  parameters=request["action"], confirm_label="Release & execute", danger=True),
                    lambda ok: ok and self.app.run_backend(
                        lambda: self.controller.release(request["id"]),
                        success="Action released and executed", advance=request["task"],
                        describe=lambda result: f"Executor result: {result}"))
