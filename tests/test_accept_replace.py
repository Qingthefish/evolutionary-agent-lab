"""Accepting an offered version over an existing file only with its exact current digest.

Live Software runs (2026-11-22): leads could not accept a fixed file at a path that already
existed, saw only a generic refusal, stored the fixes under other names and shipped the old
versions. Replacement is explicit and version-checked, like update_text.
"""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from agent_lab import Workflow
from agent_lab.files import FileToolError, FileTools
from agent_lab.gateway import ToolGateway, ToolRequestError
from agent_lab.inspection import ArtifactInspector


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


class AcceptReplaceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = self.root = Path(directory.name)
        self.workflow = Workflow(root / "state.sqlite3")
        self.addCleanup(self.workflow.close)
        for actor, kind in (("user", "human"), ("lead", "agent"), ("dev", "agent")):
            self.workflow.register_actor(actor, kind)
        chat = self.workflow.create_chat("group", ["user", "lead", "dev"])
        self.lead = self.workflow.create_task(chat, "user", "lead", "Integrate the fix")
        self.workflow.start_task(self.lead, "lead")
        self.dev = self.workflow.create_task(chat, "lead", "dev", "Fix core.py", parent=self.lead)
        self.workflow.start_task(self.dev, "dev")
        self.files = FileTools(self.workflow, root / "files")
        self.addCleanup(self.files.close)
        self.files.create_text(self.lead, "lead", "app/core.py", "old\n")

    def offer(self, text="fixed\n"):
        receipt = self.files.create_text(self.dev, "dev", "core.py", text)
        return self.files.offer_artifact(self.dev, "dev", "core.py", self.lead, expected_sha256=receipt["sha256"])

    def content(self, path="app/core.py"):
        return self.files.read_text(self.lead, "lead", path)["content"]

    def consumed(self, artifact):
        return self.workflow.db.execute("SELECT consumed FROM artifacts WHERE id=?", (artifact,)).fetchone()[0]

    def test_existing_path_is_refused_with_a_clear_next_step_and_nothing_changes(self):
        offer = self.offer()
        with self.assertRaisesRegex(FileToolError, "already exists.*replace_sha256"):
            self.files.accept_artifact(self.lead, "lead", offer["artifact_id"], "app/core.py")
        self.assertEqual(self.content(), "old\n")
        self.assertEqual(self.consumed(offer["artifact_id"]), 0)  # Still acceptable after the refusal.

    def test_creating_over_an_existing_file_gets_the_same_clear_message(self):
        with self.assertRaisesRegex(FileToolError, "already exists"):
            self.files.create_text(self.lead, "lead", "app/core.py", "other\n")

    def test_replace_with_the_current_digest_swaps_the_file_and_records_both_versions(self):
        offer = self.offer()
        receipt = self.files.accept_artifact(self.lead, "lead", offer["artifact_id"], "app/core.py",
                                             replace_sha256=sha("old\n"))
        self.assertEqual(self.content(), "fixed\n")
        self.assertEqual((receipt["sha256"], receipt["replaced_sha256"]), (sha("fixed\n"), sha("old\n")))
        self.assertEqual(self.consumed(offer["artifact_id"]), 1)
        detail = json.loads(self.workflow.db.execute(
            "SELECT detail FROM events WHERE kind='artifact_received' ORDER BY sequence DESC LIMIT 1").fetchone()[0])
        self.assertEqual(detail, {"path": "app/core.py", "sha256": sha("fixed\n"), "bytes": 6,
                                  "artifact_id": offer["artifact_id"], "replaced_sha256": sha("old\n")})
        # The broker history shows the accepted version as the latest write (what Task 2 carry checks).
        history = ArtifactInspector(self.workflow, self.files).history(self.lead, "user")["app/core.py"]
        writes = [entry for entry in history if entry["operation"] != "file_read"]
        self.assertEqual((writes[-1]["operation"], writes[-1]["sha256"]), ("artifact_received", sha("fixed\n")))
        self.assertEqual(list((self.root / "files").rglob(".write-*")), [])

    def test_stale_digest_or_missing_file_is_refused_and_the_offer_stays_open(self):
        offer = self.offer()
        with self.assertRaisesRegex(FileToolError, "did not match"):
            self.files.accept_artifact(self.lead, "lead", offer["artifact_id"], "app/core.py",
                                       replace_sha256=sha("something else\n"))
        with self.assertRaisesRegex(FileToolError, "No such file"):
            self.files.accept_artifact(self.lead, "lead", offer["artifact_id"], "app/missing.py",
                                       replace_sha256=sha("old\n"))
        self.assertEqual(self.content(), "old\n")
        self.assertEqual(self.consumed(offer["artifact_id"]), 0)
        self.files.accept_artifact(self.lead, "lead", offer["artifact_id"], "app/new.py")  # Plain accept still works.
        self.assertEqual(self.content("app/new.py"), "fixed\n")

    def test_a_consumed_offer_cannot_replace_twice(self):
        offer = self.offer()
        self.files.accept_artifact(self.lead, "lead", offer["artifact_id"], "app/core.py", replace_sha256=sha("old\n"))
        with self.assertRaisesRegex(FileToolError, "consumed"):
            self.files.accept_artifact(self.lead, "lead", offer["artifact_id"], "app/core.py",
                                       replace_sha256=sha("fixed\n"))

    def test_gateway_offers_the_optional_argument_and_validates_it(self):
        gateway = ToolGateway(self.workflow, self.files, self.lead, "lead", human="user",
                              allowed=["accept_artifact", "read_text"], max_calls=8)
        spec = next(t["function"] for t in gateway.tools() if t["function"]["name"] == "accept_artifact")
        self.assertIn("replace_sha256", spec["parameters"]["properties"])
        self.assertNotIn("replace_sha256", spec["parameters"]["required"])
        self.assertIn("replace_sha256", spec["description"])
        offer = self.offer()

        def call(identifier, **arguments):
            return {"id": identifier, "type": "function", "function": {"name": "accept_artifact",
                    "arguments": json.dumps({"artifact_id": offer["artifact_id"], "path": "app/core.py", **arguments})}}
        with self.assertRaises(ToolRequestError):
            gateway.validate_batch([call("bad", replace_sha256="not-a-digest")])
        refused = json.loads(gateway.dispatch(call("plain"))["content"])
        self.assertIn("already exists", refused["error"])
        done = json.loads(gateway.dispatch(call("replace", replace_sha256=sha("old\n")))["content"])
        self.assertTrue(done["ok"])
        self.assertEqual(self.content(), "fixed\n")


if __name__ == "__main__":
    unittest.main()
