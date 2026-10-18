"""Independent C01 acceptance contract, including deliberate false-success traps."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from agent_lab.evaluation import CaseError, Evaluator, load_cases, parse_case, summarize
from agent_lab.evaluation.harness import HUMAN, _Session, _checks, _drive_offline


CASES = Path(__file__).resolve().parents[1] / "evaluation" / "dev"
CHILD_TITLE = "Deliver note.txt containing Hello followed by a newline"


def definition(**expectations):
    return {"id": "contract-case", "title": "Independent acceptance", "goal": "Deliver the note",
            "driver": "offline_delegation", "human_responses": ["English"],
            "expected": {"final_state": "succeeded", "artifacts": {"note.txt": "Hello\n"}, **expectations}}


class AcceptanceContractTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def run_case(self, data):
        return Evaluator([parse_case(data)], output_root=self.root / "runs").run()["results"][0]

    def test_negative_controls_reject_correct_root_with_wrong_process_evidence(self):
        cases = [c for c in load_cases(CASES) if c.id.startswith("dev-negative-")]
        results = Evaluator(cases, output_root=self.root / "controls").run()["results"]
        self.assertEqual(len(results), 5)
        for result in results:
            with self.subTest(case=result["case"]["id"]):
                self.assertEqual(result["classification"], "acceptance_failed", result)
                self.assertTrue(result["checks"]["final_state"])
                self.assertTrue(result["failed_checks"])
                self.assertEqual(result["mode"], "offline_fixture")

    def test_matching_child_state_and_actual_text_pass(self):
        result = self.run_case(definition(subtasks=[{
            "assignee": "writer", "title": CHILD_TITLE, "final_state": "succeeded",
            "artifacts": {"note.txt": "Hello\n"}, "absent_artifacts": ["scratch.txt"]}]))
        self.assertEqual(result["classification"], "completed", result)
        self.assertEqual(result["case"]["expected"]["subtasks"][0]["artifacts"], {"note.txt": "Hello\n"})

    def test_missing_or_ambiguous_child_never_passes_by_task_count(self):
        for title, duplicate in (("A step that does not exist", False), (CHILD_TITLE, True)):
            with self.subTest(title=title):
                case = parse_case(definition(subtasks=[{
                    "assignee": "writer", "title": title, "final_state": "succeeded"}]))
                path = self.root / ("ambiguous" if duplicate else "missing")
                path.mkdir()
                session = _Session(path, "contract")
                try:
                    root, _ = _drive_offline(case, session)
                    if duplicate:
                        # A different root in the same chat must not count.
                        chat = session.workflow.task(root, HUMAN)["chat"]
                        other = session.workflow.create_task(chat, HUMAN, "coordinator", "Other goal")
                        session.workflow.start_task(other, "coordinator")
                        session.workflow.create_task(chat, "coordinator", "writer", CHILD_TITLE, parent=other)
                        checks, _ = _checks(case, session, root, 0.1)
                        self.assertTrue(all(checks.values()), checks)
                        # Duplicate a persisted child to simulate an ambiguous candidate tree.
                        child = session.workflow.db.execute("SELECT * FROM tasks WHERE parent=?", (root,)).fetchone()
                        columns = list(child.keys())
                        values = dict(child) | {"id": "ambiguous-child"}
                        session.workflow.db.execute(
                            f"INSERT INTO tasks({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                            [values[c] for c in columns])
                        session.workflow.db.commit()
                    checks, _ = _checks(case, session, root, 0.1)
                    self.assertTrue(checks["task_count"])
                    self.assertFalse(all(checks.values()), checks)
                finally:
                    session.close()

    def test_human_evidence_is_scoped_to_goal_and_assignee(self):
        case = parse_case(definition(human_requests=[{
            "kind": "approval", "outcome": "approved", "assignee": "coordinator", "count": 1}]))
        session = _Session(self.root, "contract")
        try:
            root, _ = _drive_offline(case, session)
            chat = session.workflow.task(root, HUMAN)["chat"]
            other = session.workflow.create_task(chat, HUMAN, "coordinator", "Unrelated approval")
            session.workflow.start_task(other, "coordinator")
            request = session.workflow.ask_human(other, "coordinator", HUMAN, "Approve unrelated action?",
                                                  action={"operation": "unrelated"})
            session.workflow.respond(request, HUMAN, approve=True)
            checks, _ = _checks(case, session, root, 0.1)
            self.assertFalse(all(checks.values()), checks)
        finally:
            session.close()
        result = self.run_case(definition(human_requests=[{
            "kind": "clarification", "outcome": "answered", "assignee": "writer", "count": 1}]))
        self.assertEqual(result["classification"], "acceptance_failed", result)

    def test_approved_and_consumed_are_distinct_records(self):
        session = _Session(self.root, "contract")
        try:
            chat = session.workflow.create_chat("private", [HUMAN, "writer"])
            root = session.workflow.create_task(chat, HUMAN, "writer", "Request permission")
            session.workflow.start_task(root, "writer")
            action = {"operation": "example"}
            request = session.workflow.ask_human(root, "writer", HUMAN, "May I?", action=action)
            session.workflow.respond(request, HUMAN, approve=True)
            expected = definition(human_requests=[
                {"kind": "approval", "outcome": "approved", "count": 1},
                {"kind": "approval", "outcome": "consumed", "count": 1}])
            case = parse_case(expected)
            checks, _ = _checks(case, session, root, 0.1)
            human = {k: v for k, v in checks.items() if k.startswith("human:")}
            self.assertEqual(sorted(human.values()), [False, True])
            session.workflow.consume_approval(request, "writer", action)
            checks, _ = _checks(case, session, root, 0.1)
            self.assertTrue(all(v for k, v in checks.items() if k.startswith("human:")))
        finally:
            session.close()

    def test_invalid_criteria_fail_before_any_driver_runs(self):
        invalid = [
            definition(min_tasks=True), definition(min_tasks=0), definition(min_tasks=1.5),
            definition(max_seconds=float("nan")), definition(max_seconds=float("inf")),
            definition(max_seconds=True), definition(remote_branch_verified="false"),
            definition(absent_artifacts="note.txt"), definition(artifacts={"../escape": "x"}),
            definition(absent_artifacts=["note.txt"]), definition(artifact={"typo.txt": "x"}),
            definition(subtasks="writer"), definition(subtasks=[{"assignee": "writer"}]),
            definition(subtasks=[{"assignee": "writer", "title": CHILD_TITLE, "final_state": "done"}]),
            definition(human_requests=[{"kind": "clarification", "outcome": "approved", "count": 1}]),
            definition(human_requests=[{"kind": "approval", "outcome": "consumed", "count": True}]),
            definition(human_requests=[{"kind": "approval", "outcome": "approved", "count": -1}]),
        ]
        for field, value in (("id", []), ("title", None), ("goal", {}), ("driver", []),
                             ("human_responses", "English"), ("expected", [])):
            item = definition()
            item[field] = value
            invalid.append(item)
        for item in invalid:
            with self.subTest(item=item):
                with self.assertRaises(CaseError):
                    parse_case(item)

    def test_duplicate_json_keys_and_duplicate_selectors_are_rejected(self):
        # Both values are valid IDs; ordinary json.loads would silently keep the last one.
        (self.root / "bad.json").write_text('{"id":"first",' + json.dumps(definition())[1:])
        with self.assertRaises(CaseError):
            load_cases(self.root)
        child = {"assignee": "writer", "title": CHILD_TITLE, "final_state": "succeeded"}
        human = {"kind": "approval", "outcome": "approved", "count": 1}
        for item in (definition(subtasks=[child, copy.deepcopy(child)]),
                     definition(human_requests=[human, copy.deepcopy(human)])):
            with self.assertRaises(CaseError):
                parse_case(item)

    def test_driver_failure_is_not_a_detected_negative_control(self):
        rows = [{"status": "executed", "control": "negative", "classification": classification,
                 "duration_seconds": 1.0} for classification in
                ("acceptance_failed", "driver_error", "timeout", "blocked", "completed")]
        summary = summarize(rows)
        self.assertEqual((summary["negative_controls"], summary["negative_controls_detected"]), (5, 1))
        self.assertIsNone(summary["completion_rate"])


if __name__ == "__main__":
    unittest.main()
