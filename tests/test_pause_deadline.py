"""Operator-decision pauses do not use up task deadlines (proposed 2026-11-20).

Live validation run 3: Software Task 1 and Task 2 both ended "duration budget
exhausted" after hours paused in provider_uncertain during an HKGAI outage,
before the operator's resend could reach the model. Scripted transports only;
no model capability is claimed.
"""

import json
from pathlib import Path
import tempfile
import unittest

from agent_lab import budget
from agent_lab.core import Workflow
from agent_lab.deepseek import DeepSeekClient
from agent_lab.evaluation.official_live import reconcile
from agent_lab.files import FileTools
from agent_lab.scheduler import MultiAgentScheduler, Role
from test_transport_pause import Scripted, dropped, stop_reply, write_reply

HOURS = 3600


class PauseDeadline(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.now = [1000.0]
        self.workflow = Workflow(Path(directory.name) / "state.sqlite3", clock=lambda: self.now[0])
        self.addCleanup(self.workflow.close)
        self.files = FileTools(self.workflow, Path(directory.name) / "files")
        self.addCleanup(self.files.close)
        for actor, kind in (("user", "human"), ("lead", "agent")):
            self.workflow.register_actor(actor, kind)
        self.root = self.workflow.create_task(self.workflow.create_chat("group", ["user", "lead"]),
                                              "user", "lead", "Write")

    def scheduler(self, transport, seconds=600):
        return MultiAgentScheduler(self.workflow, self.files, self.root, human="user",
            roles={"lead": Role("Fixture role", ("create_text",), ())},
            clients={"lead": DeepSeekClient("synthetic-transport", transport)}, mode="offline_fixture",
            constraints=[], acceptance_id="fixture-pause-deadline", verifier_factory=lambda task: None,
            limits=budget.TreeLimits(model_attempts=4, duration_seconds=seconds))

    def pause(self, transport):
        scheduler = self.scheduler(transport)
        scheduler.step()
        self.assertEqual(scheduler.step()["state"], "blocked")
        return scheduler

    def test_a_long_outage_pause_leaves_the_deadline_for_the_resent_request(self):
        transport = Scripted(dropped(), write_reply(), stop_reply())
        scheduler = self.pause(transport)
        self.now[0] += 7 * HOURS  # The live Task 2 waited about seven hours for the resend.
        self.assertEqual(scheduler.step()["state"], "blocked")  # Still the operator's decision, not a failure.
        self.assertEqual(self.workflow.task(self.root, "user")["state"], "running")
        reconcile(scheduler, self.root, "resend", "Provider recovered; operator resends", human="user")
        scheduler.step()
        self.assertEqual(transport.calls, 2)  # The resent request reached the model.
        self.assertEqual(self.workflow.task(self.root, "user")["state"], "running")
        self.assertEqual(self.files.read_text(self.root, "lead", "note.txt")["content"], "after resend")

    def test_working_time_still_counts_after_the_pause(self):
        transport = Scripted(dropped(), write_reply(), stop_reply())
        scheduler = self.pause(transport)
        self.now[0] += 7 * HOURS
        reconcile(scheduler, self.root, "resend", "Provider recovered; operator resends", human="user")
        self.now[0] += 601  # Time after the resend is ordinary working time.
        scheduler.step()
        self.assertEqual(transport.calls, 1)
        self.assertEqual(self.workflow.task(self.root, "user")["state"], "failed")

    def test_pause_seconds_count_open_and_overlapping_pauses_once(self):
        child = self.workflow.create_task(self.workflow.task(self.root, "user")["chat"], "user", "lead", "Other")
        for task, kind, at in ((self.root, "provider_decision_required", 100.0),
                               (child, "provider_decision_required", 150.0),
                               (self.root, "provider_resend_released", 200.0),
                               (child, "provider_resend_released", 260.0),
                               (self.root, "provider_decision_required", 300.0)):
            self.workflow.db.execute("INSERT INTO events(task,actor,kind,detail,timestamp) VALUES(?,?,?,?,?)",
                                     (task, "lead", kind, json.dumps({}), at))
        self.assertEqual(budget.provider_pause_seconds(self.workflow, [self.root, child], 340.0), 200.0)
        self.assertEqual(budget.provider_pause_seconds(self.workflow, [self.root], 340.0), 140.0)
        self.assertEqual(budget.provider_pause_seconds(self.workflow, [child], 340.0), 110.0)


if __name__ == "__main__":
    unittest.main()
