"""Read-only coordination audit: accounting, attribution, missing data and classification.

All inputs are deterministic offline fixtures (scripted provider responses
through the real scheduler, gateway and verifiers). They test the audit's
accounting, never model behaviour.
"""

from contextlib import closing, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.evaluation.coordination_audit import CLASSES, audit_database, audit_run, main, stop_class, tool_class
from agent_lab.gateway import _SPECS
from agent_lab.scheduler_fixture import DelegationFixture, run_fixture

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def by_assignee(result):
    return {t["assignee"]: t for t in result["per_task"]}


class SchedulerFixtureAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.run_dir = Path(cls.directory.name) / "delegation"
        cls.run_dir.mkdir()
        run_fixture(cls.run_dir)
        cls.db = cls.run_dir / "workflow.sqlite3"

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_attempts_are_attributed_per_recorded_action_and_reconciled(self):
        before = digest(self.db)
        result = audit_database(self.db)
        self.assertEqual(digest(self.db), before)  # Source database untouched.
        root = result["roots"][0]
        tasks = by_assignee(root)
        self.assertEqual([a["class"] for a in tasks["coordinator"]["attempt_log"]], ["coordination", "handoff", "completion"])
        self.assertEqual([a["class"] for a in tasks["writer"]["attempt_log"]],
                         ["coordination", "handoff", "handoff", "completion"])
        self.assertEqual([a["class"] for a in tasks["editor"]["attempt_log"]], ["human", "productive", "handoff", "completion"])
        self.assertTrue(all(v for k, v in root["reconciliation"].items() if k.endswith("_match")))
        self.assertEqual(root["totals"]["attempts"], 11)
        self.assertEqual(root["attributed_overhead"]["attempts"], 6)
        self.assertEqual(root["mixed_attempts"], 0)

    def test_parent_attempts_after_all_children_finished_are_counted(self):
        tasks = by_assignee(audit_database(self.db)["roots"][0])
        self.assertEqual(tasks["coordinator"]["after_children_done"]["attempts"], 2)
        self.assertEqual(tasks["writer"]["after_children_done"]["attempts"], 3)
        self.assertEqual(tasks["editor"]["after_children_done"]["attempts"], 0)  # No children.
        self.assertEqual(tasks["coordinator"]["children_succeeded"], 1)

    def test_summary_cli_contains_no_task_text(self):
        title = sqlite3.connect(self.db).execute("SELECT title FROM tasks WHERE parent IS NULL").fetchone()[0]
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            main(["--db", str(self.db), "--summary"])
        output = buffer.getvalue()
        self.assertNotIn(title, output)
        self.assertNotIn("attempt_log", output)
        self.assertEqual(json.loads(output)["roots"][0]["totals"]["attempts"], 11)


class TruncatedReply(DelegationFixture):
    """Same script, but the editor's second reply is cut off at the output limit."""

    def __call__(self, payload):
        request = json.loads(payload)
        context = json.loads(request["messages"][1]["content"])
        stage = sum(m["role"] == "assistant" for m in request["messages"])
        if context["role"]["agent"] == "editor" and stage == 1:
            return json.dumps({"id": "synthetic-length", "model": "offline-delegation-fixture",
                               "usage": {"prompt_tokens": 5, "completion_tokens": 1024, "total_tokens": 1029},
                               "choices": [{"message": {"role": "assistant", "content": "partial"},
                                            "finish_reason": "length"}]}).encode()
        return super().__call__(payload)


class FailureAndMissingData(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def test_provider_failure_keeps_unknown_usage_and_classifies_stops(self):
        run = self.path / "truncated"
        run.mkdir()
        with patch("agent_lab.scheduler_fixture.DelegationFixture", TruncatedReply):
            with self.assertRaises(RuntimeError):  # The fixture itself reports the failed completion.
                run_fixture(run)
        result = audit_database(run / "workflow.sqlite3")["roots"][0]
        tasks = by_assignee(result)
        failed = [a for a in tasks["editor"]["attempt_log"] if a["class"] == "provider_failure"]
        self.assertEqual(len(failed), 1)
        self.assertIsNone(failed[0]["tokens"])  # Unknown, never zero.
        self.assertEqual(failed[0]["provider_failure_kind"], "invalid_completion")
        self.assertEqual(result["totals"]["unknown_usage_attempts"], 1)
        self.assertEqual(tasks["editor"]["runner"]["stop_class"], "provider_failure")
        self.assertNotEqual(result["root_state"], "succeeded")
        self.assertTrue(result["reconciliation"]["unknown_usage_match"])
        self.assertEqual(result["parents_failed_after_all_children_succeeded"], [])

    def test_mixed_attempts_repeats_polling_and_handoff_reads(self):
        source = self.path / "source"
        source.mkdir()
        run_fixture(source)
        db = self.path / "edited.sqlite3"
        shutil.copy(source / "workflow.sqlite3", db)  # Test-owned copy; the audit itself never writes.
        with closing(sqlite3.connect(db)) as con:
            task, actor = con.execute("SELECT id,assignee FROM tasks WHERE assignee='coordinator'").fetchone()
            path = json.loads(con.execute("SELECT detail FROM events WHERE task=? AND kind='artifact_received'",
                                          (task,)).fetchone()[0])["path"]
            number = con.execute("SELECT max(number) FROM runner_turns WHERE task=?", (task,)).fetchone()[0] + 1
            proposed = [("poll-1", "read_messages", {"limit": 5}), ("poll-2", "read_messages", {"limit": 5}),
                        ("read-1", "read_text", {"path": path}), ("write-1", "create_text", {"path": "x.txt", "content": ""})]
            message = {"role": "assistant", "content": None, "tool_calls": [
                {"id": i, "type": "function", "function": {"name": n, "arguments": json.dumps(a)}} for i, n, a in proposed]}
            con.execute("INSERT INTO runner_turns VALUES(?,?,?,?,?,?,?,NULL)", (task, number, "settled", "{}", json.dumps({
                "message": message, "finish_reason": "tool_calls", "usage": {"total_tokens": 7},
                "response_id": "t", "model": "m"}), 1e12, 1e12))
            for i, n, a in proposed[:3]:  # The last proposal was never reserved.
                con.execute("INSERT INTO tool_calls VALUES(?,?,?,?,?,'succeeded','{}')",
                            (task, i, actor, n, json.dumps(a, sort_keys=True)))
            con.commit()
        tasks = by_assignee(audit_database(db)["roots"][0])
        coordinator = tasks["coordinator"]
        attempt = coordinator["attempt_log"][-1]
        self.assertEqual(attempt["class"], "mixed")
        self.assertEqual(attempt["mixed_classes"], ["coordination", "handoff", "productive"])
        self.assertEqual((attempt["tool_calls"], attempt["proposed_not_reserved"]), (3, 1))
        self.assertEqual(coordinator["exact_repeated_calls"], {"read_messages": 1})
        self.assertEqual(coordinator["polling_calls"], {"read_messages": 2})
        self.assertEqual(coordinator["tool_calls_by_class"]["handoff"], 2)  # accept_artifact + read of received path

    def test_c07_run_directory_reconciles_and_reports_missing_databases(self):
        from agent_lab.evaluation.topology_fixture import run_fixture as topology_fixture
        report, _ = topology_fixture(ROOT / "evaluation/topology-plan.json",
                                     ROOT / "evaluation/topology/fixtures/nominal-set.json", self.path / "c07")
        run = self.path / "c07" / report["run_id"]
        recorded = {r["slot"]: r["usage"] for r in report["results"]}
        audit = audit_run(run)
        self.assertEqual(set(audit["groups"]), {"single_agent", "multi_agent"})
        for slot in audit["slots"]:
            totals, usage = slot["audit"]["totals"], recorded[slot["slot"]]
            self.assertEqual((totals["attempts"], totals["tool_calls"], totals["known_tokens"]),
                             (usage["reserved_model_attempts"], usage["tool_calls"], usage["reported_tokens"]))
            if slot["topology"] == "single_agent":
                self.assertEqual(slot["audit"]["attributed_overhead"]["attempts"], 0)
        missing = report["results"][0]
        (run / missing["state_directory"] / "workflow.sqlite3").unlink()
        again = {s["slot"]: s for s in audit_run(run)["slots"]}
        self.assertIsNone(again[missing["slot"]]["audit"])
        self.assertEqual(again[missing["slot"]]["missing"], "database not available")

    def test_forked_experience_probes_count_only_their_own_root(self):
        from agent_lab.evaluation.experience_fixture import run_fixture as experience_fixture
        report = experience_fixture(ROOT / "evaluation/memory-plan.json", self.path / "experience")
        run = self.path / "experience" / report["run_id"]
        recorded = {r["slot"]: r["usage"] for r in report["results"]}
        audit = audit_run(run)
        self.assertEqual(set(audit["groups"]), {"training:collect", "probe:on", "probe:off"})
        for slot in audit["slots"]:
            totals, usage = slot["audit"]["totals"], recorded[slot["slot"]]
            self.assertEqual((totals["attempts"], totals["tool_calls"], totals["known_tokens"]),
                             (usage["reserved_model_attempts"], usage["tool_calls"], usage["reported_tokens"]))
        # A probe database is a fork that also holds the training roots; --db would include them.
        probe = next(run.glob("replicate-0/probe-*/workflow.sqlite3"))
        self.assertGreater(len(audit_database(probe)["roots"]), 1)


class Taxonomy(unittest.TestCase):
    def test_every_gateway_tool_has_exactly_one_audit_class(self):
        names = [n for members in CLASSES.values() for n in members]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual({n for n in _SPECS if tool_class(n) == "unclassified"}, set())

    def test_framework_stop_reasons(self):
        cases = {"Provider attempt failed; usage may be unknown; reconcile before retry": "provider_failure",
                 "Model attempt budget exhausted; partial artifacts retained": "task_attempt_budget",
                 "Shared task-tree attempts budget exhausted; partial artifacts retained": "shared_attempt_budget",
                 "Repeated identical proposals/outcomes; stopping without evidence of progress": "repeated_outcomes",
                 "Delegated task abc ended failed; inspect its evidence before a new plan": "child_failure",
                 "Reported token budget exhausted; partial artifacts retained": "token_budget",
                 "Task duration budget exhausted (including human wait); partial artifacts retained": "duration_budget",
                 "Something new": "other", None: None}
        for reason, expected in cases.items():
            self.assertEqual(stop_class(reason), expected, reason)


if __name__ == "__main__":
    unittest.main()
