"""Textual application shell for the multi-agent control center."""

from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, TabbedContent, TabPane

from ..core import WorkflowError
from .screens.modals import HelpScreen, NewConversationScreen, NewTaskScreen
from .widgets.approvals import ApprovalsPane
from .widgets.artifacts import ArtifactsPane
from .widgets.base import Pane
from .widgets.conversations import ConversationsPane
from .widgets.dashboard import DashboardPane
from .widgets.header import StatusHeader
from .widgets.logs import LogsPane
from .widgets.memory import MemoryPane
from .widgets.tasks import TasksPane

TABS = [
    ("dashboard", "Dashboard", DashboardPane, "f1"),
    ("conversations", "Conversations", ConversationsPane, "f2"),
    ("tasks", "Tasks", TasksPane, "f3"),
    ("artifacts", "Artifacts", ArtifactsPane, "f4"),
    ("memory", "Memory", MemoryPane, "f5"),
    ("approvals", "Approvals", ApprovalsPane, "f6"),
    ("logs", "Logs", LogsPane, "f7"),
]


class ControlCenterApp(App):
    TITLE = "Evolutionary Agent Lab — Multi-Agent Control Center"
    CSS_PATH = Path(__file__).with_name("theme.tcss")
    # Ctrl+P is used for approvals, so the command palette is disabled.
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        *(Binding(key, f"show_tab('{tab}')", label, show=False) for tab, label, _, key in TABS),
        Binding("ctrl+n", "new_conversation", "New conversation"),
        Binding("ctrl+t", "new_task", "New task"),
        Binding("ctrl+p", "show_tab('approvals')", "Approvals"),
        Binding("ctrl+l", "show_tab('logs')", "Logs"),
        Binding("ctrl+r", "refresh_all", "Refresh"),
        Binding("question_mark", "help", "Help"),
        Binding("ctrl+q", "quit", "Quit", priority=True),
    ]

    def __init__(self, controller, *, refresh_seconds=5.0):
        super().__init__()
        self.controller = controller
        self.human = controller.human
        self.selected_chat = None
        self.selected_task = None
        self.refresh_seconds = refresh_seconds

    def compose(self) -> ComposeResult:
        # Keep direct references: queries on `self` target the active screen,
        # which may be a modal dialog while a background worker finishes.
        self.header = StatusHeader(id="status-header")
        self.tabs = TabbedContent(initial="dashboard", id="tabs")
        self.panes = {tab: pane(id=f"pane-{tab}") for tab, _, pane, _ in TABS}
        yield self.header
        with self.tabs:
            for tab, label, _, key in TABS:
                with TabPane(f"{label} \\[{key.upper()}]", id=tab):
                    yield self.panes[tab]
        yield Footer()

    def on_mount(self):
        self.theme = "textual-dark"
        self.refresh_all()
        if self.refresh_seconds:
            self.set_interval(self.refresh_seconds, self._periodic)

    def _periodic(self):
        self._load_status()
        self.active_pane().refresh_data()

    def active_pane(self) -> Pane:
        return self.panes[self.tabs.active]

    def on_tabbed_content_tab_activated(self, event):
        self.active_pane().refresh_data()

    # ---- refresh -----------------------------------------------------------
    def action_refresh_all(self):
        self.refresh_all()
        self.notify("Refreshed from persisted state")

    def refresh_all(self):
        self._load_status()
        for pane in self.panes.values():
            pane.refresh_data()

    @work(thread=True, exclusive=True, group="status")
    def _load_status(self):
        try:
            status = self.controller.status()
        except Exception as error:
            self._from_thread(self.report_error, f"Status unavailable: {error}")
            return
        self._from_thread(self._set_status, status)

    def _set_status(self, status):
        self.header.status = status

    def _from_thread(self, function, *args):
        try:
            self.call_from_thread(function, *args)
        except RuntimeError:
            pass

    def report_error(self, message):
        self.notify(message, severity="error", timeout=8)

    # ---- backend actions ---------------------------------------------------
    def run_backend(self, function, *, success=None, advance=None, describe=None, then=None, quiet=False):
        """Run a controller call off the event loop, then report and refresh."""
        self._backend_worker(function, success, advance, describe, then, quiet)

    @work(thread=True, group="actions")
    def _backend_worker(self, function, success, advance, describe, then, quiet):
        try:
            result = function()
            note = None
            if advance is not None:
                try:
                    state = self.controller.advance(advance)
                    note = f"Scheduler: {state.get('state')} (goal {state.get('task_state')})"
                except WorkflowError as error:
                    note = f"Not advanced: {error}"
        except WorkflowError as error:
            self._from_thread(self.report_error, str(error))
            self._from_thread(self.refresh_all)
            return
        except Exception as error:  # Unexpected failures stay recoverable.
            self._from_thread(self.report_error, f"Unexpected error: {error!r}")
            return
        if then is not None:
            self._from_thread(then, result)
        messages = [m for m in (success, describe(result) if describe else None, note) if m]
        if messages and not quiet:
            self._from_thread(self.notify, "\n".join(messages))
        if not quiet:
            self._from_thread(self.refresh_all)

    # ---- selection ---------------------------------------------------------
    def select_chat(self, chat):
        self.selected_chat = chat
        self.panes["conversations"].refresh_data()

    def set_agent(self, agent):
        self.header.selected_agent = agent or "—"

    # ---- actions -----------------------------------------------------------
    def action_show_tab(self, tab):
        self.tabs.active = tab

    def action_help(self):
        self.push_screen(HelpScreen())

    def action_new_conversation(self):
        def open_dialog(actors):
            agents = [a["id"] for a in actors if a["kind"] == "agent"]

            def created(choice):
                if choice:
                    self.run_backend(lambda: self.controller.create_conversation(choice["kind"], choice["agents"]),
                                     success=f"Created {choice['kind']} conversation",
                                     then=lambda chat: (setattr(self, "selected_chat", chat), self.action_show_tab("conversations")))
            self.push_screen(NewConversationScreen(agents), created)
        self.run_backend(self.controller.actors, quiet=True, then=open_dialog)

    def action_new_task(self):
        def open_dialog(conversations):
            if not conversations:
                self.notify("Create a conversation first (Ctrl+N)", severity="warning")
                return
            options = [(f"{c['kind']}: {', '.join(m['id'] for m in c['members'] if m['id'] != self.human)} "
                        f"({c['id'][:6]})", c["id"]) for c in conversations]
            agents = {c["id"]: [m["id"] for m in c["members"] if m["kind"] == "agent"] for c in conversations}

            def created(choice):
                if choice:
                    self.run_backend(lambda: self.controller.create_task(choice["chat"], choice["agent"], choice["title"]),
                                     describe=lambda r: r["explanation"],
                                     then=lambda r: setattr(self, "selected_task", r["task"]))
            self.push_screen(NewTaskScreen(options, agents, chat=self.selected_chat,
                                           offline=self.controller.mode == "offline"), created)
        self.run_backend(self.controller.conversations, quiet=True, then=open_dialog)

    async def action_quit(self):
        self.exit()
