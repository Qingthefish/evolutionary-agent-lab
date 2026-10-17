"""Shared pane behavior: backend reads run in thread workers, UI updates on the loop."""

from rich.markup import escape
from textual import work
from textual.containers import Vertical
from textual.widgets import Static

from ...core import WorkflowError
from ..models import STATE_LABELS, request_label, short, state_markup  # noqa: F401  (re-export for panes)


class Pane(Vertical):
    """A tab body. `fetch` runs off the event loop; `show` runs on it."""

    def fetch(self):
        return None

    def show(self, data):
        pass

    @property
    def controller(self):
        return self.app.controller

    def refresh_data(self):
        self._load()

    @work(thread=True, exclusive=True, group="pane-load")
    def _load(self):
        try:
            data = self.fetch()
        except WorkflowError as error:
            self._from_thread(self.app.report_error, f"{type(self).__name__}: {error}")
            return
        except Exception as error:  # Recoverable UI failure: report and keep running.
            self._from_thread(self.app.report_error, f"{type(self).__name__} failed to load: {error!r}")
            return
        self._from_thread(self._safe_show, data)

    def _safe_show(self, data):
        try:
            self.show(data)
        except Exception as error:
            self.app.report_error(f"{type(self).__name__} failed to render: {error!r}")

    def _from_thread(self, function, *args):
        try:
            self.app.call_from_thread(function, *args)
        except RuntimeError:
            pass  # Application is shutting down.


def banner(text, classes="banner"):
    return Static(escape(text), classes=classes)
