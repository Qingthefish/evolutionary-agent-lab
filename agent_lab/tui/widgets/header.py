"""Persistent application header: title, execution mode, session, agent, runtimes."""

from rich.markup import escape
from textual.reactive import reactive
from textual.widgets import Static


class StatusHeader(Static):
    status = reactive(None, layout=True)
    selected_agent = reactive("—")

    def render(self):
        status = self.status or {}
        mode = status.get("mode", "…")
        mode_text = ("[b black on yellow] OFFLINE · scripted providers [/]" if mode == "offline"
                     else "[b black on green3] LIVE · " + escape(status.get("provider", "")) + " [/]"
                     if mode == "live" else "[b] … [/]")
        runtimes = status.get("runtimes", {})
        runtime_text = "  ".join(f"{escape(k)}: {escape(v)}" for k, v in runtimes.items())
        pending = status.get("pending_requests", 0) + status.get("awaiting_release", 0)
        attention = f"  [b]! {pending} awaiting you[/]" if pending else ""
        uncertain = f"  [b]⚠ {status['uncertain']} uncertain[/]" if status.get("uncertain") else ""
        return (f"[b]Evolutionary Agent Lab — Multi-Agent Control Center[/]  {mode_text}{attention}{uncertain}\n"
                f"session: {escape(status.get('session', '…'))}  human: {escape(status.get('human', '…'))}  "
                f"agent: {escape(self.selected_agent)}  ·  {runtime_text}")
