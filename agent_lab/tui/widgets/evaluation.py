from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Label, Static

from ..models import pretty, stamp
from .base import Pane, banner

CLASS_LABELS = {"completed": "✓ completed", "acceptance_failed": "✗ acceptance failed", "task_failed": "✗ task failed",
                "task_cancelled": "⊘ task cancelled", "blocked": "⏸ blocked", "timeout": "⧗ timeout",
                "driver_error": "✗ driver error", "not_configured": "— not configured"}


def seconds(value):
    return "—" if value is None else f"{value:.2f}s"


class EvaluationPane(Pane):
    """Displays the evaluator's actual results; computes no metrics itself."""

    def compose(self) -> ComposeResult:
        yield banner("Offline cases run fixed scripts and are reported as offline_fixture (benchmark_valid: false). "
                     "They test the harness and platform plumbing, not model capability. Live cases show 'Not configured' "
                     "until a DeepSeek/HKGAI runtime is configured; they are never counted as successes.", classes="banner warn")
        with Horizontal(classes="filters"):
            yield Button("Run all cases", id="eval-run-all", variant="primary")
            yield Button("Run highlighted case", id="eval-run-one")
            yield Button("Show report path", id="eval-report")
            yield Button("Refresh", id="eval-refresh")
        with Horizontal(classes="split"):
            with Vertical(classes="sidebar wide"):
                yield Label("Development cases", classes="section")
                yield DataTable(id="eval-cases", cursor_type="row")
                yield Label("Runs (persisted in the session directory)", classes="section")
                yield DataTable(id="eval-runs", cursor_type="row")
                yield Static("", id="eval-memory", classes="card")
            with VerticalScroll(classes="main"):
                yield Static("Select a run", id="eval-summary", classes="card")
                yield Label("Per-case results", classes="section")
                yield DataTable(id="eval-results", cursor_type="row")
                yield Static("", id="eval-detail", classes="card")

    def on_mount(self):
        self.query_one("#eval-cases", DataTable).add_columns("Case", "Driver", "Expected", "Control", "Runtime")
        self.query_one("#eval-runs", DataTable).add_columns("Run", "Mode", "Accepted", "Accept. rate", "Driver time", "Not cfg.")
        self.query_one("#eval-results", DataTable).add_columns("Case", "Class", "Time", "Failed checks")
        self.selected_case, self.selected_run, self.run = None, None, None
        self.query_one("#eval-memory", Static).update(
            "[b]Memory ON/OFF comparison:[/] Not configured — requires two live runs over the same cases "
            "(memory=on, memory=off). Offline fixtures do not exercise memory.")

    def fetch(self):
        runs = self.controller.eval_runs()
        selected = self.selected_run if self.selected_run in {r["run_id"] for r in runs} else (
            runs[0]["run_id"] if runs else None)
        return {"cases": self.controller.eval_cases(), "runs": runs,
                "run": self.controller.eval_result(selected) if selected else None}

    def show(self, data):
        cases = self.query_one("#eval-cases", DataTable)
        cases.clear()
        if data["cases"]["error"]:
            cases.add_row("✗", escape(data["cases"]["error"]), "", "", "")
        for case in data["cases"]["cases"]:
            cases.add_row(case["id"], case["driver"], case["expected_state"], case["control"] or "",
                          "available" if case["configured"] else "Not configured", key=case["id"])
        runs = self.query_one("#eval-runs", DataTable)
        runs.clear()
        for run in data["runs"]:
            summary = run["summary"]
            rate = summary["completion_rate"]
            runs.add_row(run["run_id"], run["mode"], f"{summary['completed']}/{summary['executed']}",
                         "—" if rate is None else f"{rate:.0%}", seconds(summary["mean_duration_seconds"]),
                         str(summary["not_configured"]), key=run["run_id"])
        self._show_run(data["run"])

    def _show_run(self, run):
        self.run = run
        results = self.query_one("#eval-results", DataTable)
        results.clear()
        if run is None:
            self.query_one("#eval-summary", Static).update("No evaluation runs yet. Press 'Run all cases'.")
            return
        self.selected_run = run["run_id"]
        summary = run["summary"]
        rate = summary["completion_rate"]
        self.query_one("#eval-summary", Static).update(
            f"[b]Run[/] {run['run_id']}   [b]Mode:[/] {escape(run['mode'])}   "
            f"[b]benchmark_valid:[/] {str(run['benchmark_valid']).lower()}   [b]Started:[/] {stamp(run['started'])}\n"
            f"{escape(run['benchmark_note'])}\n"
            f"[b]Contract acceptance:[/] {summary['completed']}/{summary['executed']} scored cases "
            f"({'—' if rate is None else f'{rate:.0%}'})   [b]Driver observation time:[/] {seconds(summary['mean_duration_seconds'])}   "
            f"[b]Not configured:[/] {summary['not_configured']}   "
            f"[b]Negative controls detected:[/] {summary['negative_controls_detected']}/{summary['negative_controls']}")
        for result in run["results"]:
            label = CLASS_LABELS.get(result["classification"], result["classification"])
            if result["control"]:
                label += " (negative control)"
            results.add_row(result["case"]["id"], label,
                            "—" if result["duration_seconds"] is None else f"{result['duration_seconds']:.2f}s",
                            ", ".join(result["failed_checks"]) or "—", key=result["case"]["id"])

    def on_data_table_row_highlighted(self, event):
        if event.row_key is None:
            return
        if event.data_table.id == "eval-cases":
            self.selected_case = event.row_key.value
        elif event.data_table.id == "eval-runs" and event.row_key.value != self.selected_run:
            self.selected_run = event.row_key.value
            self.refresh_data()
        elif event.data_table.id == "eval-results" and self.run:
            result = next((r for r in self.run["results"] if r["case"]["id"] == event.row_key.value), None)
            if result:
                checks = "\n".join(f"  {'✓' if ok else '✗'} {name}" for name, ok in sorted(result["checks"].items())) or "  none"
                self.query_one("#eval-detail", Static).update(
                    f"[b]{escape(result['case']['title'])}[/]\n[b]Goal:[/] {escape(result['case']['goal'])}\n"
                    f"[b]Mode:[/] {result['mode']}   [b]Status:[/] {result['status']}   "
                    f"[b]Scripted human input:[/] {'yes' if result['scripted_human'] else 'no'}\n"
                    f"[b]Independent checks[/]\n{checks}\n"
                    f"{'[b]Error:[/] ' + escape(result['error']) + chr(10) if result['error'] else ''}"
                    f"{'[b]Notes:[/] ' + escape(result['notes']) + chr(10) if result['notes'] else ''}"
                    f"[b]Workflow evidence:[/]\n{escape(pretty(result['workflow']))}")

    def on_button_pressed(self, event):
        if event.button.id == "eval-refresh":
            self.refresh_data()
        elif event.button.id in {"eval-run-all", "eval-run-one"}:
            ids = None
            if event.button.id == "eval-run-one":
                if not self.selected_case:
                    self.app.notify("Highlight a case first", severity="warning")
                    return
                ids = [self.selected_case]

            def done(run):
                self.selected_run = run["run_id"]
            self.app.run_backend(lambda: self.controller.eval_run(ids), then=done,
                                 describe=lambda run: f"Evaluation {run['run_id']} ({run['mode']}): "
                                                      f"{run['summary']['completed']}/{run['summary']['executed']} completed")
        elif event.button.id == "eval-report":
            if not self.selected_run:
                self.app.notify("No run selected", severity="warning")
                return
            path = self.controller.evaluations_dir / self.selected_run / "report.md"
            self.app.notify(f"Markdown report: {path}", timeout=10)
