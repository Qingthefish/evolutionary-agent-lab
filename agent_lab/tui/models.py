"""Textual-free presentation helpers. Status is always text plus a symbol, never color alone."""

from datetime import datetime
import json

STATE_LABELS = {
    "pending": ("○", "pending", "state-pending"),
    "running": ("▶", "running", "state-running"),
    "waiting_input": ("?", "waiting: clarification", "state-waiting"),
    "waiting_approval": ("!", "waiting: approval", "state-waiting"),
    "succeeded": ("✓", "succeeded", "state-ok"),
    "failed": ("✗", "failed", "state-bad"),
    "cancelled": ("⊘", "cancelled", "state-bad"),
}
REQUEST_LABELS = {
    "pending": "? pending human response",
    "answered": "✓ answered",
    "denied": "✗ rejected (task cancelled)",
    "granted_awaiting_release": "! approved; not executed yet",
    "granted_stale": "⊘ approved but stale (task moved on)",
    "released": "▶ released to trusted executor",
}
OUTCOME_LABELS = {
    "file_deleted": "✓ executed: file deleted (verified by broker)",
    "git_push_verified": "✓ executed: remote branch verified",
    "git_push_failed": "✗ execution failed",
    "git_push_uncertain": "⚠ execution uncertain: reconcile, do not retry",
    "unrecorded": "⚠ released; no execution result recorded",
}
STATE_STYLES = {"state-pending": "grey62", "state-running": "deep_sky_blue1", "state-waiting": "yellow",
                "state-ok": "green3", "state-bad": "indian_red1"}


def state_label(state):
    symbol, label, _ = STATE_LABELS.get(state, ("·", state, "state-pending"))
    return f"{symbol} {label}"


def state_markup(state):
    symbol, label, style = STATE_LABELS.get(state, ("·", state, "state-pending"))
    return f"[{STATE_STYLES[style]}]{symbol} {label}[/]"


def request_label(request):
    label = REQUEST_LABELS.get(request["status"], request["status"])
    if request.get("outcome"):
        label += " → " + OUTCOME_LABELS.get(request["outcome"]["kind"], request["outcome"]["kind"])
    return label


def short(identifier, size=8):
    return identifier[:size] if identifier else "—"


def clock(timestamp):
    return datetime.fromtimestamp(timestamp).strftime("%H:%M:%S") if timestamp else "—"


def stamp(timestamp):
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S") if timestamp else "—"


def duration(seconds):
    if seconds is None:
        return "—"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"


def pretty(value):
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


def conversation_label(conversation, human):
    others = [m["id"] for m in conversation["members"] if m["id"] != human]
    kind = "🔒 private" if conversation["kind"] == "private" else "👥 group"
    return f"{kind} · {', '.join(others)} ({short(conversation['id'], 6)})"


def escape(text):
    return str(text).replace("[", r"\[")
