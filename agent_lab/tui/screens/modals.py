"""Modal dialogs. Each returns a plain value through `dismiss`; Esc cancels."""

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, Select, Static

from ..models import pretty


class _Modal(ModalScreen):
    BINDINGS = [Binding("escape", "cancel", "Close")]

    def action_cancel(self):
        self.dismiss(None)


class ConfirmScreen(_Modal):
    """Critical-operation confirmation that shows exact parameters."""

    def __init__(self, title, body, *, parameters=None, confirm_label="Confirm", danger=False):
        super().__init__()
        self.title_text, self.body, self.parameters = title, body, parameters
        self.confirm_label, self.danger = confirm_label, danger

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self.title_text, classes="dialog-title")
            yield Static(escape(self.body), classes="dialog-body")
            if self.parameters is not None:
                yield Label("Exact parameters:", classes="dialog-label")
                with VerticalScroll(classes="dialog-params"):
                    yield Static(escape(pretty(self.parameters)), id="confirm-parameters")
            with Horizontal(classes="dialog-buttons"):
                yield Button(self.confirm_label, id="confirm", variant="error" if self.danger else "primary")
                yield Button("Cancel", id="cancel")

    def on_mount(self):
        self.query_one("#cancel", Button).focus()

    def on_button_pressed(self, event):
        self.dismiss(event.button.id == "confirm")


class TextPromptScreen(_Modal):
    def __init__(self, title, prompt, *, placeholder=""):
        super().__init__()
        self.title_text, self.prompt, self.placeholder = title, prompt, placeholder

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self.title_text, classes="dialog-title")
            yield Static(escape(self.prompt), classes="dialog-body")
            yield Input(placeholder=self.placeholder, id="prompt-input")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Submit", id="submit", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_mount(self):
        self.query_one(Input).focus()

    def _submit(self):
        value = self.query_one(Input).value.strip()
        if value:
            self.dismiss(value)
        else:
            self.notify("Enter a nonempty response", severity="warning")

    def on_input_submitted(self, event):
        self._submit()

    def on_button_pressed(self, event):
        if event.button.id == "submit":
            self._submit()
        else:
            self.dismiss(None)


class NewConversationScreen(_Modal):
    def __init__(self, agents):
        super().__init__()
        self.agents = agents

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label("New conversation", classes="dialog-title")
            yield Select([("Private (you + one agent)", "private"), ("Group (you + agents)", "group")],
                         value="private", allow_blank=False, id="conversation-kind")
            yield Label("Agents:", classes="dialog-label")
            with VerticalScroll(classes="dialog-params"):
                for agent in self.agents:
                    yield Checkbox(agent, id=f"agent-{agent}")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Create", id="create", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event):
        if event.button.id != "create":
            self.dismiss(None)
            return
        chosen = [a for a in self.agents if self.query_one(f"#agent-{a}", Checkbox).value]
        kind = self.query_one("#conversation-kind", Select).value
        if not chosen or (kind == "private" and len(chosen) != 1):
            self.notify("Private needs exactly one agent; group needs at least one", severity="warning")
            return
        self.dismiss({"kind": kind, "agents": chosen})


class NewTaskScreen(_Modal):
    def __init__(self, conversations, agents_by_chat, *, chat=None, offline=True):
        super().__init__()
        self.conversations, self.agents_by_chat = conversations, agents_by_chat
        self.chat, self.offline = chat, offline

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label("Submit a new task", classes="dialog-title")
            if self.offline:
                yield Static("Offline mode: the task is persisted as pending and will NOT execute without a "
                             "configured DeepSeek/HKGAI model. Use Dashboard scenarios to exercise execution.",
                             classes="dialog-warning")
            yield Select(self.conversations, prompt="Conversation", id="task-chat",
                         value=self.chat if self.chat else Select.NULL)
            yield Select([], prompt="Assign to agent", id="task-agent")
            yield Input(placeholder="Deliverable and constraints", id="task-title")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Create task", id="create", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_mount(self):
        self._sync_agents()

    def _sync_agents(self):
        chat = self.query_one("#task-chat", Select).value
        agents = self.agents_by_chat.get(chat, []) if chat not in (Select.NULL, Select.BLANK) else []
        self.query_one("#task-agent", Select).set_options([(a, a) for a in agents])

    def on_select_changed(self, event):
        if event.select.id == "task-chat":
            self._sync_agents()

    def on_button_pressed(self, event):
        if event.button.id != "create":
            self.dismiss(None)
            return
        chat = self.query_one("#task-chat", Select).value
        agent = self.query_one("#task-agent", Select).value
        title = self.query_one("#task-title", Input).value.strip()
        if chat in (Select.NULL, Select.BLANK) or agent in (Select.NULL, Select.BLANK) or not title:
            self.notify("Choose a conversation, an agent, and describe the task", severity="warning")
            return
        self.dismiss({"chat": chat, "agent": agent, "title": title})


HELP = """\
[b]Navigation[/b]
  F1  Dashboard        F2  Conversations     F3  Tasks
  F4  Artifacts        F5  Memory            F6 / Ctrl+P  Approvals
  F7 / Ctrl+L  Execution logs
  Tab / Shift+Tab  move focus;  arrows and Enter operate lists, trees, tables

[b]Actions[/b]
  Ctrl+N  New conversation        Ctrl+T  New task
  Ctrl+R  Refresh all views       ?       This help (when not typing)
  Esc     Close dialog            Ctrl+Q  Quit (state is persisted)

[b]Status symbols[/b] (never color alone)
  ○ pending  ▶ running  ? waiting: clarification  ! waiting: approval
  ✓ succeeded  ✗ failed  ⊘ cancelled  ⚠ uncertain / needs reconciliation

[b]Approvals[/b]: approving records a decision only. Releasing executes the exact
approved action through the trusted gateway; its verified result is shown separately.

Offline mode: provider responses in scenarios are scripted; workflow state,
tools, files, approvals, and verification are real. No arbitrary task can be
completed without a configured DeepSeek/HKGAI model.
"""


class HelpScreen(_Modal):
    BINDINGS = [Binding("escape", "cancel", "Close"), Binding("question_mark", "cancel", "Close")]

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog dialog-wide"):
            yield Label("Help and shortcuts", classes="dialog-title")
            with VerticalScroll():
                yield Static(HELP)
            with Horizontal(classes="dialog-buttons"):
                yield Button("Close", id="close", variant="primary")

    def on_button_pressed(self, event):
        self.dismiss(None)
