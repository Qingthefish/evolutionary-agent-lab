from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Label, Select, Static, Tree

from ..models import STATE_LABELS, clock, duration, pretty, request_label, short, state_markup, stamp
from ..screens.modals import ConfirmScreen, TextPromptScreen
from .base import Pane

ANY = "__any__"


class TasksPane(Pane):
    """Task tree with filters and a persisted-evidence execution inspector."""

    def compose(self) -> ComposeResult:
        with Horizontal(classes="filters"):
            yield Select([("Any agent", ANY)], value=ANY, allow_blank=False, id="filter-agent")
            yield Select([("Any state", ANY)] + [(f"{s} {l}", k) for k, (s, l, _) in STATE_LABELS.items()],
                         value=ANY, allow_blank=False, id="filter-state")
            yield Select([("Any event", ANY)], value=ANY, allow_blank=False, id="filter-event")
            yield Button("Refresh", id="tasks-refresh")
        with Horizontal(classes="split"):
            with Vertical(classes="sidebar wide"):
                yield Tree("Tasks", id="task-tree")
                with Horizontal(classes="button-row"):
                    yield Button("Advance", id="task-advance", tooltip="Run this task's scheduler until it pauses")
                    yield Button("Review…", id="task-review", tooltip="Accept/reject a proposal awaiting review")
                    yield Button("Recover claim", id="task-recover", variant="warning")
            with VerticalScroll(classes="main", id="task-inspector"):
                yield Static("Select a task", id="task-summary", classes="card")
                yield Label("Events (persisted source of truth)", classes="section")
                yield DataTable(id="task-events", cursor_type="row")
                yield Static("", id="event-detail", classes="card")
                yield Label("Tool invocations (arguments redacted where credential-like)", classes="section")
                yield DataTable(id="task-tools", cursor_type="row")
                yield Static("", id="tool-detail", classes="card")
                yield Label("Model attempts (recorded responses only)", classes="section")
                yield Static("", id="task-runner", classes="card")
                yield Label("Human requests", classes="section")
                yield Static("", id="task-requests", classes="card")

    def on_mount(self):
        self.query_one("#task-tree", Tree).show_root = False
        self.query_one("#task-events", DataTable).add_columns("#", "Time", "Actor", "Event", "Summary")
        self.query_one("#task-tools", DataTable).add_columns("Call", "Tool", "Status", "Result")
        self.detail = None
        self.records = {}
        self._agent_options, self._event_options, self._snapshot = [], [], None

    def fetch(self):
        tasks = self.controller.tasks()
        task = self.app.selected_task
        detail = self.controller.task_detail(task) if task in {t["id"] for t in tasks} else None
        return {"tasks": tasks, "detail": detail}

    def _filtered(self, tasks):
        agent = self.query_one("#filter-agent", Select).value
        state = self.query_one("#filter-state", Select).value
        matches = {t["id"] for t in tasks if (agent == ANY or t["assignee"] == agent)
                   and (state == ANY or t["state"] == state)}
        by_id = {t["id"]: t for t in tasks}
        keep = set()
        for identifier in matches:  # Keep ancestors so the hierarchy stays readable.
            while identifier and identifier not in keep:
                keep.add(identifier)
                identifier = by_id[identifier]["parent"] if identifier in by_id else None
        return keep, matches

    def show(self, data):
        tasks = data["tasks"]
        self.records = {t["id"]: t for t in tasks}
        agents = sorted({t["assignee"] for t in tasks})
        agent_select = self.query_one("#filter-agent", Select)
        if agents != self._agent_options:
            current = agent_select.value
            self._agent_options = agents
            agent_select.set_options([("Any agent", ANY)] + [(a, a) for a in agents])
            agent_select.value = current if current in agents else ANY
        keep, matches = self._filtered(tasks)
        tree = self.query_one("#task-tree", Tree)
        tree.clear()
        nodes = {}
        parents = {t["parent"] for t in tasks if t["id"] in keep}
        for task in tasks:  # Creation order guarantees parents precede children.
            if task["id"] not in keep:
                continue
            parent = nodes.get(task["parent"], tree.root)
            wait = f" · waited {duration(task['human_wait_seconds'])}" if task["human_wait_seconds"] else ""
            run = f" [dim]\\[{task['run']}][/]" if task.get("run") else ""
            dim = "" if task["id"] in matches else "[dim]"
            label = (f"{dim}{state_markup(task['state'])} [b]{escape(task['assignee'])}[/]: "
                     f"{escape(task['title'][:48])} [dim]({duration(task['elapsed_seconds'])}{wait})[/]{run}")
            if task["id"] in parents:
                nodes[task["id"]] = parent.add(label, data=task["id"], expand=True)
            else:
                nodes[task["id"]] = parent.add_leaf(label, data=task["id"])
            if task["id"] == self.app.selected_task:
                self.call_after_refresh(tree.move_cursor, nodes[task["id"]])
        if not tasks:
            tree.root.add_leaf("No tasks yet. Create one (Ctrl+T) or run a Dashboard scenario.")
        self._show_detail(data["detail"])
        self._snapshot = self._filter_values()

    def _filter_values(self):
        return tuple(self.query_one(f"#filter-{name}", Select).value for name in ("agent", "state", "event"))

    def _show_detail(self, detail):
        self.detail = detail
        summary = self.query_one("#task-summary", Static)
        events_table = self.query_one("#task-events", DataTable)
        tools_table = self.query_one("#task-tools", DataTable)
        events_table.clear()
        tools_table.clear()
        for widget in ("#event-detail", "#tool-detail", "#task-runner", "#task-requests"):
            self.query_one(widget, Static).update("")
        if detail is None:
            summary.update("Select a task in the tree")
            return
        task = detail["task"]
        evidence = task["evidence"]
        outcome = ""
        if evidence and "error" in evidence:
            outcome = f"\n[b]Failure reason:[/] {escape(evidence['error'])}"
        elif evidence and "checks" in evidence:
            outcome = "\n[b]Passing trusted checks:[/] " + escape(", ".join(evidence["checks"]))
        run = detail.get("run")
        summary.update(
            f"[b]Task[/] {task['id']}\n[b]Agent:[/] {escape(task['assignee'])}   [b]State:[/] {state_markup(task['state'])}"
            f"   [b]Parent:[/] {short(task['parent'])}   [b]Children:[/] {len(detail['children'])}\n"
            f"[b]Title:[/] {escape(task['title'])}\n"
            f"[b]Created:[/] {stamp(task['created'])}   [b]Ended:[/] {stamp(task['ended'])}   "
            f"[b]Elapsed:[/] {duration(task['elapsed_seconds'])}   [b]Human wait:[/] {duration(task['human_wait_seconds'])}"
            f"{'   [b]⏸ waiting on you[/]' if task['waiting_on_human'] else ''}\n"
            f"[b]Execution:[/] {escape(run) + ' scheduler' if run else 'no scheduler attached (will not execute offline)'}"
            f"{outcome}")
        kinds = sorted({e["kind"] for e in detail["events"]})
        event_select = self.query_one("#filter-event", Select)
        if kinds != self._event_options:
            chosen = event_select.value
            self._event_options = kinds
            event_select.set_options([("Any event", ANY)] + [(k, k) for k in kinds])
            event_select.value = chosen if chosen in kinds else ANY
        for event in detail["events"]:
            if event_select.value != ANY and event["kind"] != event_select.value:
                continue
            brief = ", ".join(f"{k}={str(v)[:24]}" for k, v in event["detail"].items())[:80]
            events_table.add_row(str(event["sequence"]), clock(event["timestamp"]), event["actor"], event["kind"],
                                 brief, key=str(event["sequence"]))
        for call in detail["tool_calls"]:
            result = call["result"] or {}
            text = ("✓ ok" if result.get("ok") else "✗ " + str(result.get("error", ""))[:60]) if result else "⚠ no recorded result"
            tools_table.add_row(call["call_id"][:28], call["name"], call["status"], text, key=call["call_id"])
        runner = detail["runner"]
        if runner is None:
            self.query_one("#task-runner", Static).update("No runner session: no model attempts recorded for this task.")
        else:
            lines = [f"[b]Mode:[/] {escape(str(runner['mode']))}{' (synthetic fixture responses)' if runner['synthetic'] else ''}"
                     f"   [b]Model id:[/] {escape(str(runner['model']))}   [b]Runner:[/] {escape(runner['status'])}"
                     f"   [b]Attempts:[/] {runner['attempts']}   [b]Reported tokens:[/] {runner['reported_tokens']}"
                     f"{' (synthetic)' if runner['synthetic'] else ''}   [b]Verifier:[/] {escape(str(runner['verifier_id']))}"]
            if runner["stop_reason"]:
                lines.append(f"[b]Stop reason:[/] {escape(runner['stop_reason'])}")
            for turn in runner["turns"]:
                usage = turn["usage"]["total_tokens"] if turn["usage"] else "unknown"
                what = (", ".join(turn["tool_names"]) if turn["tool_names"]
                        else f"final: {escape(str(turn['final_text']))[:80]}" if turn["final_text"] else "")
                lines.append(f"  #{turn['number']} {clock(turn['started'])} {escape(turn['status'])} "
                             f"finish={turn['finish_reason'] or '—'} tokens={usage} {escape(what)}"
                             f"{' error=' + escape(turn['error']) if turn['error'] else ''}")
            self.query_one("#task-runner", Static).update("\n".join(lines))
        requests = [f"{short(r['id'])} [{escape(r['kind'])}] {escape(request_label(r))}: {escape(r['prompt'])}"
                    + (f" → {escape(str(r['response']))}" if r["response"] else "") for r in detail["requests"]]
        self.query_one("#task-requests", Static).update("\n".join(requests) or "None")

    def on_tree_node_selected(self, event):
        if event.node.data and event.node.data != self.app.selected_task:
            self.app.selected_task = event.node.data
            self.app.set_agent(self.records.get(event.node.data, {}).get("assignee"))
            self.refresh_data()

    def on_data_table_row_highlighted(self, event):
        if self.detail is None or event.row_key is None:
            return
        if event.data_table.id == "task-events":
            event_record = next((e for e in self.detail["events"] if str(e["sequence"]) == event.row_key.value), None)
            if event_record:
                self.query_one("#event-detail", Static).update(
                    f"[b]{escape(event_record['kind'])}[/] at {stamp(event_record['timestamp'])} by "
                    f"{escape(event_record['actor'])}\n{escape(pretty(event_record['detail']))}")
        elif event.data_table.id == "task-tools":
            call = next((c for c in self.detail["tool_calls"] if c["call_id"] == event.row_key.value), None)
            if call:
                self.query_one("#tool-detail", Static).update(
                    f"[b]{escape(call['name'])}[/] ({escape(call['status'])})\n[b]Arguments:[/]\n"
                    f"{escape(pretty(call['arguments']))}\n[b]Result:[/]\n{escape(pretty(call['result']))}")

    def on_select_changed(self, event):
        # Programmatic option updates also post Changed; refresh only on a real change.
        if event.select.id in {"filter-agent", "filter-state", "filter-event"} and self._filter_values() != self._snapshot:
            self._snapshot = self._filter_values()
            self.refresh_data()

    def on_button_pressed(self, event):
        task = self.app.selected_task
        if event.button.id == "tasks-refresh":
            self.refresh_data()
            return
        if task is None:
            self.app.notify("Select a task first", severity="warning")
            return
        if event.button.id == "task-advance":
            self.app.run_backend(lambda: self.controller.advance(task), success="Scheduler advanced",
                                 describe=lambda result: f"Scheduler state: {result.get('state')} (root {result.get('task_state')})")
        elif event.button.id == "task-review":
            def decided(feedback):
                if feedback is None:
                    return
                accept = feedback.strip().lower() == "accept"
                self.app.run_backend(lambda: self.controller.review(task, accept=accept, feedback=feedback),
                                     success="Review recorded")
            self.app.push_screen(TextPromptScreen(
                "Trusted human review",
                "Type 'accept' to record a passing human review check, or describe what is wrong to return "
                "the proposal for repair. Only use this for proposals awaiting independent verification.",
                placeholder="accept  |  feedback for repair"), decided)
        elif event.button.id == "task-recover":
            def confirmed(ok):
                if ok:
                    self.app.run_backend(lambda: self.controller.recover_claim(task), success="Scheduler claim cleared")
            self.app.push_screen(ConfirmScreen(
                "Clear scheduler claim?",
                "Only do this after confirming no other control center is running this task tree. It clears the "
                "claim only; interrupted provider/tool effects are not replayed and still need inspection.",
                parameters={"task": task}, confirm_label="Clear claim", danger=True), confirmed)
