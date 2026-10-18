"""Development test-case definitions with independent expected outcomes.

Expected outcomes are written by people before a run and checked against
persisted workflow state and actual artifacts. They never come from a model's
self-assessment. These are development cases, not the instructor's held-out set.
"""

from dataclasses import asdict, dataclass, field
import math
from pathlib import Path
import re

from ..core import WorkflowError
from ..files import _parts
from ..protocol import strict_json

DRIVERS = {"offline_delegation", "offline_approval", "offline_git", "live_scheduler"}
STATES = {"succeeded", "failed", "cancelled"}
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")


class CaseError(WorkflowError):
    """An invalid evaluation case definition."""


@dataclass(frozen=True)
class SubtaskExpected:
    assignee: str
    title: str
    final_state: str
    artifacts: dict = field(default_factory=dict)
    absent_artifacts: tuple = ()


@dataclass(frozen=True)
class HumanExpected:
    kind: str
    outcome: str
    count: int = 1
    assignee: str | None = None


@dataclass(frozen=True)
class Expected:
    final_state: str
    artifacts: dict = field(default_factory=dict)     # root-task path -> exact expected text
    absent_artifacts: tuple = ()                      # root-task paths that must not exist
    min_tasks: int = 1
    max_seconds: float = 120.0
    remote_branch_verified: bool = False
    subtasks: tuple = ()                    # exact assignee/title selectors; each must match one descendant
    human_requests: tuple = ()              # exact counts of persisted requests in this task tree


@dataclass(frozen=True)
class EvalCase:
    id: str
    title: str
    goal: str
    driver: str
    split: str = "development"
    control: str | None = None              # "negative": the evaluator is expected to report failure
    human_responses: tuple = ()             # scripted clarification answers, in order
    approval: str | None = None             # "approve" | "reject" scripted human decision
    expected: Expected = field(default_factory=lambda: Expected("succeeded"))
    source: str = ""

    def summary(self):
        return {"id": self.id, "title": self.title, "goal": self.goal, "driver": self.driver, "split": self.split,
                "control": self.control, "scripted_human": bool(self.human_responses or self.approval),
                "expected_state": self.expected.final_state, "expected": asdict(self.expected), "source": self.source}


def _object(value, allowed, required, label):
    if not isinstance(value, dict) or not required <= value.keys() or not value.keys() <= allowed:
        raise CaseError(f"{label}: missing, unknown, or invalid fields")
    return value


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise CaseError(f"{label}: expected nonempty text")
    return value


def _choice(value, choices, label):
    if (value is not None and not isinstance(value, str)) or value not in choices:
        raise CaseError(f"{label}: unsupported value")
    return value


def _array(value, label):
    if not isinstance(value, list):
        raise CaseError(f"{label}: expected a JSON array")
    return value


def _count(value, label, *, minimum=0):
    if type(value) is not int or value < minimum:
        raise CaseError(f"{label}: expected an integer >= {minimum}")
    return value


def _artifact_checks(data):
    artifacts = data.get("artifacts", {})
    absent = _array(data.get("absent_artifacts", []), "absent_artifacts")
    if not isinstance(artifacts, dict) or any(not isinstance(v, str) for v in artifacts.values()):
        raise CaseError("artifacts: expected a path-to-exact-text object")
    for path in [*artifacts, *absent]:
        try:
            _parts(path)
        except WorkflowError:
            raise CaseError("Expected artifacts need safe task-relative POSIX paths") from None
    if len(set(absent)) != len(absent) or set(artifacts) & set(absent):
        raise CaseError("Expected artifact paths must be distinct and cannot be both present and absent")
    return dict(artifacts), tuple(absent)


def parse_case(data, *, source=""):
    """Validate the entire JSON contract before creating any runtime or run directory."""
    _object(data, {"id", "title", "goal", "driver", "split", "control", "human_responses", "approval", "expected"},
            {"id", "title", "goal", "driver", "expected"}, "case")
    identifier = _text(data["id"], "id")
    if not _ID.fullmatch(identifier):
        raise CaseError("Case id must contain 3–64 lowercase letters, digits or hyphens")
    title, goal = _text(data["title"], "title"), _text(data["goal"], "goal")
    driver = _choice(data["driver"], DRIVERS, "driver")
    split = _choice(data.get("split", "development"), {"development", "heldout"}, "split")
    control = _choice(data.get("control"), {None, "negative"}, "control")
    approval = _choice(data.get("approval"), {None, "approve", "reject"}, "approval")
    responses = tuple(_text(v, "human_responses") for v in _array(data.get("human_responses", []), "human_responses"))
    expected = _object(data["expected"], {"final_state", "artifacts", "absent_artifacts", "min_tasks",
                       "max_seconds", "remote_branch_verified", "subtasks", "human_requests"},
                       {"final_state"}, "expected")
    final_state = _choice(expected["final_state"], STATES, "expected.final_state")
    artifacts, absent = _artifact_checks(expected)
    min_tasks = _count(expected.get("min_tasks", 1), "min_tasks", minimum=1)
    seconds = expected.get("max_seconds", 120)
    try:
        valid_seconds = type(seconds) in (int, float) and math.isfinite(seconds) and seconds > 0
    except OverflowError:
        valid_seconds = False
    if not valid_seconds:
        raise CaseError("max_seconds must be positive and finite")
    remote = expected.get("remote_branch_verified", False)
    if type(remote) is not bool:
        raise CaseError("remote_branch_verified must be a boolean")
    subtasks = []
    for item in _array(expected.get("subtasks", []), "subtasks"):
        _object(item, {"assignee", "title", "final_state", "artifacts", "absent_artifacts"},
                {"assignee", "title", "final_state"}, "subtask")
        files, missing = _artifact_checks(item)
        subtasks.append(SubtaskExpected(_text(item["assignee"], "subtask.assignee"),
            _text(item["title"], "subtask.title"), _choice(item["final_state"], STATES, "subtask.final_state"), files, missing))
    if len({(s.assignee, s.title) for s in subtasks}) != len(subtasks):
        raise CaseError("Duplicate subtask selector")
    humans = []
    for item in _array(expected.get("human_requests", []), "human_requests"):
        _object(item, {"kind", "outcome", "count", "assignee"}, {"kind", "outcome"}, "human request")
        kind = _choice(item["kind"], {"approval", "clarification"}, "human.kind")
        outcomes = {"answered", "unanswered"} if kind == "clarification" else {"approved", "rejected", "unanswered", "consumed"}
        humans.append(HumanExpected(kind, _choice(item["outcome"], outcomes, "human.outcome"),
            _count(item.get("count", 1), "human.count"),
            _text(item["assignee"], "human.assignee") if "assignee" in item else None))
    if len({(h.kind, h.outcome, h.assignee) for h in humans}) != len(humans):
        raise CaseError("Duplicate human-request expectation")
    return EvalCase(identifier, title, goal, driver, split, control, responses, approval,
                    Expected(final_state, artifacts, absent, min_tasks, float(seconds), remote,
                             tuple(subtasks), tuple(humans)), source)


def load_cases(directory):
    """Discover `*.json` case files (one case or a list per file), sorted by id."""
    directory = Path(directory)
    if not directory.is_dir():
        raise CaseError(f"Case directory {directory} does not exist")
    cases = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = strict_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError, RecursionError):
            raise CaseError(f"Invalid JSON in case file {path.name}") from None
        for item in data if isinstance(data, list) else [data]:
            cases.append(parse_case(item, source=path.name))
    ids = [case.id for case in cases]
    if len(set(ids)) != len(ids):
        raise CaseError("Duplicate case ids")
    return sorted(cases, key=lambda case: case.id)
