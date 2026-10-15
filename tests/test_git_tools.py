"""Restricted Git backend and gateway approval checks using disposable local repositories."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from agent_lab import Workflow
from agent_lab.core import WorkflowError
from agent_lab.files import FileTools
from agent_lab.gateway import ToolGateway, ToolRequestError
from agent_lab.git_tools import GitToolError, GitTools, GitUncertainError, TrustedRepository, load_trusted_repositories

ENV = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": "/nonexistent", "GIT_CONFIG_NOSYSTEM": "1",
       "GIT_CONFIG_GLOBAL": os.devnull, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
       "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid"}


def git(*arguments, cwd=None):
    return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *arguments], cwd=cwd, env=ENV, check=True,
                          capture_output=True, text=True).stdout.strip()


class GitFixture(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self.directory.name))
        self.work, self.remote = base / "work", base / "remote.git"
        git("init", "-q", "--bare", str(self.remote))
        git("init", "-q", "-b", "main", str(self.work))
        (self.work / "docs").mkdir()
        (self.work / "README.md").write_text("readme\n")
        (self.work / "docs" / "a.md").write_text("a\n")
        git("add", ".", cwd=self.work)
        git("commit", "-q", "-m", "initial", cwd=self.work)
        git("push", "-q", str(self.remote), "main", cwd=self.work)
        git("switch", "-q", "-c", "agent/work", cwd=self.work)
        self.config = TrustedRepository("demo", str(self.work), writable_branches=("agent/work",),
                                        writable_paths=("docs/",), remotes=(("origin", str(self.remote)),))
        self.workflow = Workflow(base / "state.sqlite3")
        self.git = GitTools(self.workflow, [self.config])

    def tearDown(self):
        self.git.close()
        self.workflow.close()
        self.directory.cleanup()

    def remote_head(self, branch):
        out = git("ls-remote", str(self.remote), "refs/heads/" + branch)
        return out.split()[0] if out else None


class GitToolsTests(GitFixture):
    def test_read_operations_and_untrusted_repository(self):
        (self.work / "docs" / "a.md").write_text("changed\n")
        (self.work / "docs" / "new.md").write_text("new\n")
        status = self.git.status("demo")
        self.assertEqual(status["branch"], "agent/work")
        self.assertEqual({e["path"]: e["kind"] for e in status["entries"]},
                         {"docs/a.md": "changed", "docs/new.md": "untracked"})
        self.assertIn("+changed", self.git.diff("demo")["diff"])
        self.assertEqual(self.git.diff("demo", staged=True)["diff"], "")
        self.assertEqual([c["subject"] for c in self.git.log("demo")], ["initial"])
        with self.assertRaises(GitToolError):
            self.git.status("other")
        with self.assertRaises(GitToolError):
            TrustedRepository("x", "relative/path", ("b",), ("docs/",))
        with self.assertRaises(GitToolError):
            TrustedRepository("x", "/abs", ("b",), ("docs/",), remotes=(("origin", "https://github.com/a/b"),))

    def test_symlinked_path_and_identity_change_are_rejected(self):
        link = Path(self.directory.name) / "link"
        os.symlink(self.work, link)
        linked = GitTools(self.workflow, [TrustedRepository("linked", str(link), ("agent/work",), ("docs/",))])
        try:
            with self.assertRaises(GitToolError):
                linked.status("linked")
        finally:
            linked.close()
        self.git.status("demo")  # Binds identity.
        os.rename(self.work / ".git", Path(self.directory.name) / "old-git")
        git("init", "-q", str(self.work))
        with self.assertRaises(GitToolError):
            self.git.status("demo")

    def test_dangerous_repository_configuration_is_rejected(self):
        for key, value in (("core.sshCommand", "touch /tmp/pwned"), ("include.path", "/tmp/x"),
                           ("filter.evil.clean", "touch /tmp/pwned"), ("core.hooksPath", "/tmp/hooks"),
                           ("diff.external", "/bin/sh")):
            git("config", key, value, cwd=self.work)
            with self.assertRaises(GitToolError, msg=key):
                self.git.status("demo")
            git("config", "--unset", key, cwd=self.work)
        self.git.status("demo")
        (self.work / ".git" / "objects" / "info" / "alternates").write_text("/tmp\n")
        with self.assertRaises(GitToolError):
            self.git.status("demo")

    def test_commit_stages_only_authorized_paths_and_skips_hooks(self):
        marker = Path(self.directory.name) / "hook-ran"
        hook = self.work / ".git" / "hooks" / "pre-commit"
        hook.write_text(f"#!/bin/sh\ntouch {marker}\n")
        hook.chmod(0o755)
        (self.work / "docs" / "a.md").write_text("updated\n")
        (self.work / "docs" / "unrelated.md").write_text("not requested\n")
        (self.work / "README.md").write_text("outside writable paths\n")
        result = self.git.commit("demo", ["docs/a.md"], "Update a", actor="writer", task=None)
        self.assertEqual(result["paths"], ["docs/a.md"])
        self.assertEqual(git("show", "--name-only", "--format=", "HEAD", cwd=self.work), "docs/a.md")
        self.assertFalse(marker.exists())
        status = {e["path"] for e in self.git.status("demo")["entries"]}
        self.assertEqual(status, {"docs/unrelated.md", "README.md"})
        operation = self.git.operations()[0]
        self.assertEqual((operation["operation"], operation["status"]), ("commit", "succeeded"))

    def test_commit_restrictions(self):
        cases = [(["README.md"], "outside"), (["docs/.env"], "credential"), (["docs/key.pem"], "credential"),
                 (["docs/../README.md"], "traversal"), ([".git/config"], ".git"), (["-rf"], "relative"),
                 (["docs/x.sqlite3"], "credential")]
        for paths, reason in cases:
            with self.assertRaises(GitToolError, msg=reason):
                self.git.commit("demo", paths, "msg", actor="writer")
        (self.work / "docs" / "leak.md").write_text("token = ghp_" + "a" * 36 + "\n")
        with self.assertRaises(GitToolError):
            self.git.commit("demo", ["docs/leak.md"], "msg", actor="writer")
        (self.work / "docs" / "leak.md").unlink()
        (self.work / "docs" / "b.md").write_text("b\n")
        (self.work / "docs" / "c.md").write_text("c\n")
        git("add", "docs/c.md", cwd=self.work)  # Pre-staged unrelated work.
        with self.assertRaises(GitToolError):
            self.git.commit("demo", ["docs/b.md"], "msg", actor="writer")
        git("reset", "-q", cwd=self.work)
        git("switch", "-q", "main", cwd=self.work)
        with self.assertRaises(GitToolError):  # main is not writable.
            self.git.commit("demo", ["docs/b.md"], "msg", actor="writer")
        os.symlink("/etc/hosts", self.work / "docs" / "link.md")
        git("switch", "-q", "agent/work", cwd=self.work)
        with self.assertRaises(GitToolError):
            self.git.commit("demo", ["docs/link.md"], "msg", actor="writer")
        self.assertEqual({op["status"] for op in self.git.operations()}, {"failed"})

    def test_push_preparation_rules(self):
        for branch in ("main", "+agent/work", ":agent/work", "agent/work..x", "-f"):
            with self.assertRaises(GitToolError, msg=branch):
                self.git.prepare_push("demo", "origin", branch)
        with self.assertRaises(GitToolError):
            self.git.prepare_push("demo", "elsewhere", "agent/work")
        binding = self.git.prepare_push("demo", "origin", "agent/work")
        self.assertIsNone(binding["expected_remote"])
        self.assertEqual(binding["commit"], git("rev-parse", "HEAD", cwd=self.work))
        self.assertIsNone(self.remote_head("agent/work"))  # Preparation has no effect.
        # A diverged remote branch is never force-overwritten.
        other = Path(self.directory.name) / "other"
        git("clone", "-q", "-b", "main", str(self.remote), str(other))
        git("switch", "-q", "-c", "agent/work", cwd=other)
        (other / "docs" / "z.md").write_text("z\n")
        git("add", ".", cwd=other)
        git("commit", "-q", "-m", "diverged", cwd=other)
        git("push", "-q", "origin", "agent/work", cwd=other)
        with self.assertRaises(GitToolError):
            self.git.prepare_push("demo", "origin", "agent/work")

    def test_git_environment_excludes_inherited_credentials(self):
        seen = []
        original = self.git._exec

        def spy(argv, env, seconds):
            seen.append((argv, env))
            return original(argv, env, seconds)
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_secret", "GIT_ASKPASS": "/tmp/steal"}), \
                patch.object(self.git, "_exec", spy):
            self.git.status("demo")
        self.assertTrue(seen)
        for argv, env in seen:
            self.assertNotIn("GITHUB_TOKEN", env)
            self.assertEqual(env["GIT_ASKPASS"], "/usr/bin/false")
            self.assertEqual(env["GIT_CONFIG_GLOBAL"], os.devnull)
            self.assertIn("core.hooksPath=/dev/null", argv)
            self.assertIn("credential.helper=", argv)

    def test_output_is_bounded(self):
        limited = GitTools(self.workflow, [self.config], output_bytes=2048)
        try:
            (self.work / "docs" / "a.md").write_text("line\n" * 5000)
            result = limited.diff("demo")
            self.assertTrue(result["truncated"])
            self.assertLessEqual(len(result["diff"]), 2048)
        finally:
            limited.close()

    def test_trusted_repository_file(self):
        path = Path(self.directory.name) / "repos.json"
        path.write_text(json.dumps({"repositories": [{"name": "demo", "path": str(self.work),
            "writable_branches": ["agent/work"], "writable_paths": ["docs/"], "remotes": {"origin": str(self.remote)}}]}))
        self.assertEqual(load_trusted_repositories(path), [self.config])


class GitGatewayTests(GitFixture):
    def setUp(self):
        super().setUp()
        self.files = FileTools(self.workflow, Path(self.directory.name) / "files")
        self.workflow.register_actor("user", "human")
        self.workflow.register_actor("integrator", "agent")
        self.chat = self.workflow.create_chat("private", ["user", "integrator"])
        self.task = self.workflow.create_task(self.chat, "user", "integrator", "Commit and push")
        self.workflow.start_task(self.task, "integrator")
        self.gateway = self.make_gateway()
        self.calls = 0

    def tearDown(self):
        self.files.close()
        super().tearDown()

    def make_gateway(self, allowed=("create_text", "git_status", "git_commit", "git_push")):
        return ToolGateway(self.workflow, self.files, self.task, "integrator", human="user", allowed=allowed, git=self.git)

    def call(self, name, **arguments):
        self.calls += 1
        result = self.gateway.dispatch({"id": f"call-{self.calls}", "type": "function",
                                        "function": {"name": name, "arguments": json.dumps(arguments)}})
        return json.loads(result["content"])

    def commit_note(self, text="note\n"):
        self.call("create_text", path=f"note-{self.calls}.md", content=text)
        source = f"note-{self.calls - 1}.md"
        return self.call("git_commit", repository="demo", files={"docs/note.md": source}, message="Add note")

    def request_push(self):
        result = self.call("git_push", repository="demo", remote="origin", branch="agent/work")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["task_state"], "waiting_approval")
        return result["result"]["request_id"]

    def test_git_tools_need_backend_and_allowlist(self):
        with self.assertRaises(ToolRequestError):
            ToolGateway(self.workflow, self.files, self.task, "integrator", human="user", allowed=["git_status"])
        gateway = self.make_gateway(allowed=("git_status",))
        tools = {t["function"]["name"]: t for t in gateway.tools()}
        self.assertEqual(tools["git_status"]["function"]["parameters"]["properties"]["repository"]["enum"], ["demo"])
        with self.assertRaises(ToolRequestError):
            gateway.dispatch({"id": "x", "type": "function", "function": {
                "name": "git_push", "arguments": json.dumps({"repository": "demo", "remote": "origin", "branch": "agent/work"})}})
        with self.assertRaises(ToolRequestError):
            gateway.dispatch({"id": "y", "type": "function", "function": {
                "name": "git_status", "arguments": json.dumps({"repository": "untrusted"})}})

    def test_commit_from_task_files_then_approved_push_is_verified(self):
        committed = self.commit_note()
        self.assertTrue(committed["ok"], committed)
        commit = committed["result"]["commit"]
        self.assertEqual((self.work / "docs" / "note.md").read_text(), "note\n")
        request = self.request_push()
        self.assertIsNone(self.remote_head("agent/work"))  # Requesting approval pushed nothing.
        record = self.workflow.request(request, "user")
        self.assertEqual(json.loads(record["action"])["binding"]["commit"], commit)
        with self.assertRaises(WorkflowError):
            self.gateway.release_approved(request)  # Not yet approved.
        self.workflow.respond(request, "user", approve=True)
        result = self.gateway.release_approved(request)
        self.assertEqual(result["observed_remote"], commit)
        self.assertEqual(self.remote_head("agent/work"), commit)
        kinds = [e["kind"] for e in self.workflow.events(self.task, "user")]
        self.assertIn("approval_consumed", kinds)
        self.assertEqual(kinds[-1], "git_push_verified")
        with self.assertRaises(WorkflowError):
            self.gateway.release_approved(request)  # Single use.

    def test_denied_push_cancels_task_and_pushes_nothing(self):
        self.commit_note()
        request = self.request_push()
        self.workflow.respond(request, "user", approve=False)
        self.assertEqual(self.workflow.task(self.task, "user")["state"], "cancelled")
        with self.assertRaises(WorkflowError):
            self.gateway.release_approved(request)
        self.assertIsNone(self.remote_head("agent/work"))

    def test_approval_is_bound_to_commit_and_remote_state(self):
        self.commit_note()
        request = self.request_push()
        self.workflow.respond(request, "user", approve=True)
        (self.work / "docs" / "late.md").write_text("late\n")
        self.git.commit("demo", ["docs/late.md"], "Late commit", actor="operator")
        with self.assertRaises(GitToolError):
            self.gateway.release_approved(request)
        self.assertEqual(self.workflow.request(request, "user")["consumed"], 0)  # Not consumed.
        self.assertIsNone(self.remote_head("agent/work"))

    def test_uncertain_push_is_recorded_and_never_retried(self):
        self.commit_note()
        request = self.request_push()
        self.workflow.respond(request, "user", approve=True)
        original = self.git._exec

        def interrupted(argv, env, seconds):
            if "push" in argv:
                original(argv, env, seconds)  # The effect happens, but the process looks interrupted.
                return None, b"", b"", "timeout"
            return original(argv, env, seconds)
        with patch.object(self.git, "_exec", interrupted):
            with self.assertRaises(ToolRequestError) as caught:
                self.gateway.release_approved(request)
        self.assertIn("uncertain", str(caught.exception))
        operation = next(op for op in self.git.operations() if op["operation"] == "push")
        self.assertEqual(operation["status"], "uncertain")
        self.assertEqual(self.workflow.events(self.task, "user")[-1]["kind"], "git_push_uncertain")
        with self.assertRaises(WorkflowError):
            self.gateway.release_approved(request)  # Consumed: no automatic retry.
        observed = self.git.reconcile(operation["id"], actor="user")
        self.assertEqual(observed["outcome"], "remote_shows_commit")
        self.assertEqual(sum(op["operation"] == "push" for op in self.git.operations()), 1)

    def test_rejected_push_is_reported_as_failure(self):
        self.commit_note()
        request = self.request_push()
        self.workflow.respond(request, "user", approve=True)
        original = self.git._exec

        def rejected(argv, env, seconds):
            if "push" in argv:
                return 1, b"", b"! [rejected]", None
            return original(argv, env, seconds)
        with patch.object(self.git, "_exec", rejected):
            with self.assertRaises(ToolRequestError):
                self.gateway.release_approved(request)
        self.assertEqual(self.workflow.events(self.task, "user")[-1]["kind"], "git_push_failed")
        self.assertIsNone(self.remote_head("agent/work"))

    def test_uncertain_release_raises_typed_error_from_backend(self):
        binding = self.git.prepare_push("demo", "origin", "agent/work")
        original = self.git._exec

        def interrupted(argv, env, seconds):
            return (None, b"", b"", "timeout") if "push" in argv else original(argv, env, seconds)
        with patch.object(self.git, "_exec", interrupted):
            with self.assertRaises(GitUncertainError):
                self.git.push_approved(binding, actor="integrator", task=self.task, request_id="r")


if __name__ == "__main__":
    unittest.main()
