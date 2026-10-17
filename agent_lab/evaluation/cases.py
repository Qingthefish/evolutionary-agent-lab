"""Development test-case definitions with independent expected outcomes.

Expected outcomes are written by people before a run and checked against
persisted workflow state and actual artifacts. They never come from a model's
self-assessment. These are development cases, not the instructor's held-out set.
"""

from dataclasses import dataclass, field
import json
from pathlib import Path
import re

from ..core import WorkflowError

DRIVERS = {"offline_delegation", "offline_approval", "offline_git", "live_scheduler"}
STATES = {"succeeded", "failed", "cancelled"}
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")


class CaseError(WorkflowError):
    """An invalid evaluation case definition."""


@dataclass(frozen=True)
class Expected:
    final_state: str
    artifacts: dict = field(default_factory=dict)     # root-task path -> exact expected text
    absent_artifacts: tuple = ()                      # root-task paths that must not exist
    min_tasks: int = 1
    max_seconds: float = 120.0
    remote_branch_verified: bool = False


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
                "expected_state": self.expected.final_state, "source": self.source}


def parse_case(data, *, source=""):
    if not isinstance(data, dict):
        raise CaseError("A case must be a JSON object")
    try:
        expected = data["expected"]
        case = EvalCase(
            id=data["id"], title=data["title"], goal=data["goal"], driver=data["driver"],
            split=data.get("split", "development"), control=data.get("control"),
            human_responses=tuple(data.get("human_responses", ())), approval=data.get("approval"),
            expected=Expected(final_state=expected["final_state"], artifacts=dict(expected.get("artifacts", {})),
                              absent_artifacts=tuple(expected.get("absent_artifacts", ())),
                              min_tasks=int(expected.get("min_tasks", 1)),
                              max_seconds=float(expected.get("max_seconds", 120)),
                              remote_branch_verified=bool(expected.get("remote_branch_verified", False))),
            source=source)
    except (KeyError, TypeError, ValueError) as error:
        raise CaseError(f"Invalid case {source or data.get('id')}: {error}") from None
    if not _ID.fullmatch(case.id) or not case.title.strip() or not case.goal.strip():
        raise CaseError(f"Case {case.id!r} needs a lowercase id, title, and goal")
    if case.driver not in DRIVERS:
        raise CaseError(f"Case {case.id}: unknown driver {case.driver!r}")
    if case.split not in {"development", "heldout"}:
        raise CaseError(f"Case {case.id}: split must be development or heldout")
    if case.control not in {None, "negative"} or case.approval not in {None, "approve", "reject"}:
        raise CaseError(f"Case {case.id}: invalid control or approval decision")
    if case.expected.final_state not in STATES or case.expected.max_seconds <= 0:
        raise CaseError(f"Case {case.id}: invalid expected outcome")
    if any(not isinstance(v, str) for v in case.expected.artifacts.values()):
        raise CaseError(f"Case {case.id}: expected artifacts are exact text")
    return case


def load_cases(directory):
    """Discover `*.json` case files (one case or a list per file), sorted by id."""
    directory = Path(directory)
    if not directory.is_dir():
        raise CaseError(f"Case directory {directory} does not exist")
    cases = []
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for item in data if isinstance(data, list) else [data]:
            cases.append(parse_case(item, source=path.name))
    ids = [case.id for case in cases]
    if len(set(ids)) != len(ids):
        raise CaseError("Duplicate case ids")
    return sorted(cases, key=lambda case: case.id)
