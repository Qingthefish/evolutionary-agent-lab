"""Opt-in overlapping of consecutive web-call fetches inside one reply (synthetic; no network).

Fake fetches with real thread synchronisation prove that only the HTTPS fetches overlap, that
the default stays strictly sequential, and that reservations, parsing, artifact writes, records
and model-visible results are identical to sequential execution and stay in call order on the
controller thread.
"""

from contextlib import contextmanager, redirect_stderr
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlencode, urlsplit
from xml.sax.saxutils import escape

from agent_lab.core import Workflow
from agent_lab.deepseek import DeepSeekClient
from agent_lab.evaluation import official_live
from agent_lab.files import FileTools
from agent_lab.gateway import ToolBudgetError, ToolGateway
from agent_lab.queries import WorkflowQueries
from agent_lab.retrieval import RetrievalError, WebRetrieval
from agent_lab.runner import TaskRunner
from test_runner import Script, response, tool

WEB = ["search_web", "retrieve_text", "read_text", "create_text"]


def search(identifier, query):
    return tool("search_web", {"query": query, "limit": 2}, identifier)


def retrieve(identifier, url, path):
    return tool("retrieve_text", {"url": url, "path": path}, identifier)


class FakeWeb:
    """Synthetic public pages; counts fetches in flight and which threads ran them."""

    def __init__(self, *, barrier=None, delay=0.0, missing=(), explode=()):
        self.lock, self.inflight, self.peak, self.urls, self.threads = threading.Lock(), 0, 0, [], []
        self.barrier, self.delay, self.missing, self.explode = barrier, delay, set(missing), set(explode)

    def fetch(self, url):
        with self.lock:
            self.inflight += 1
            self.peak = max(self.peak, self.inflight)
            self.urls.append(url)
            self.threads.append(threading.current_thread().name)
        try:
            if self.barrier is not None:
                try:
                    self.barrier.wait()
                except threading.BrokenBarrierError:  # A lone fetch: reported like a network timeout.
                    raise RetrievalError("Public HTTPS request failed or timed out; no result was fabricated") from None
            time.sleep(self.delay)
            if url in self.explode:
                raise RuntimeError("unexpected fetch crash")
            if url in self.missing:
                raise RetrievalError("Public source returned HTTP 404; no usable result")
            if url.startswith("https://www.bing.com/search?"):
                query = parse_qs(urlsplit(url).query)["q"][0]
                link = "https://www.bing.com/search?" + urlencode({"q": query, "format": "rss"})
                body = (f"<rss><channel><link>{escape(link)}</link>"
                        f"<item><title>About {escape(query)}</title><link>https://docs.example.org/{len(query)}</link>"
                        f"<description>Snippet for {escape(query)}</description></item></channel></rss>").encode()
                kind = "application/rss+xml"
            else:
                body = f"<h1>Page</h1><p>Evidence from {url}</p>".encode()
                kind = "text/html"
            return {"url": url, "content_type": kind, "body": body, "sha256": hashlib.sha256(body).hexdigest(),
                    "redirects": []}
        finally:
            with self.lock:
                self.inflight -= 1


class Fixture:
    def __init__(self, directory, *, workers=1, web=None, max_calls=32):
        self.path = Path(directory)
        self.workflow = Workflow(self.path / "state.sqlite3", clock=lambda: 1000.0)
        for actor, kind in (("user", "human"), ("researcher", "agent")):
            self.workflow.register_actor(actor, kind)
        chat = self.workflow.create_chat("group", ["user", "researcher"])
        self.task = self.workflow.create_task(chat, "user", "researcher", "Collect cited sources")
        self.workflow.start_task(self.task, "researcher")
        self.files = FileTools(self.workflow, self.path / "files")
        self.retrieval = WebRetrieval(self.workflow, self.files)
        self.retrieval.allow_concurrent_fetches(workers)
        self.web = web or FakeWeb()
        self.retrieval.http.fetch = self.web.fetch
        self.gateway = ToolGateway(self.workflow, self.files, self.task, "researcher", human="user", allowed=WEB,
                                   retrieval=self.retrieval, max_calls=max_calls)

    def runner(self, replies):
        client = DeepSeekClient("synthetic-fixture-model", Script(replies), max_tokens=128)
        return TaskRunner(self.gateway, client, mode="offline_fixture", constraints=["Cite sources"], verifier=None)

    def close(self):
        self.files.close()
        self.workflow.close()

    def snapshot(self):
        """Every durable record a later turn, audit or recovery can observe, with random ids normalised."""
        ids = {row[0]: f"source-{n}" for n, row in enumerate(self.workflow.db.execute(
            "SELECT id FROM retrieval_records ORDER BY rowid"))}

        ids[self.task] = "task"

        def clean(text):
            for raw, label in ids.items():
                text = text.replace(raw, label)
            return re.sub(r"tasks/[0-9a-f]{64}", "tasks/<task-directory>", text)
        calls = [(r[0], r[1], r[2], clean(r[3] or "")) for r in self.workflow.db.execute(
            "SELECT call_id, name, status, result FROM tool_calls ORDER BY rowid")]
        records = [tuple(r) for r in self.workflow.db.execute(
            "SELECT kind, request, status, result FROM retrieval_records ORDER BY rowid")]
        records = [(k, q, s, clean(r or "")) for k, q, s, r in records]
        events = [(r[0], clean(r[1])) for r in self.workflow.db.execute(
            "SELECT kind, detail FROM events WHERE kind IN ('tool_result','source_retrieved','file_created','file_read') "
            "ORDER BY sequence")]
        files = {clean(p.relative_to(self.path / "files").as_posix()): p.read_text()
                 for p in sorted((self.path / "files").rglob("*")) if p.is_file()}
        transcript = clean(self.workflow.db.execute("SELECT transcript FROM runner_sessions").fetchone()[0])
        return {"calls": calls, "records": records, "events": events, "files": files, "transcript": transcript}


BATCH = [search("s1", "index fund costs"), search("s2", "S&P 500 history"),
         retrieve("r1", "https://docs.example.org/a", "sources/a.md"),
         retrieve("r2", "https://docs.example.org/b", "sources/b.md"),
         tool("read_text", {"path": "sources/a.md"}, "read")]


class ParallelWebFetchTests(unittest.TestCase):
    def setUp(self):
        self.directories = []

    def tearDown(self):
        for fixture, directory in self.directories:
            fixture.close()
            directory.cleanup()

    def fixture(self, **kwargs):
        directory = tempfile.TemporaryDirectory()
        fixture = Fixture(directory.name, **kwargs)
        self.directories.append((fixture, directory))
        return fixture

    def turn(self, fixture, calls):
        runner = fixture.runner([response(calls)])
        state = runner.step()
        self.assertEqual(fixture.workflow.task(fixture.task, "researcher")["state"], "running", state)
        return state

    # --- Default and configuration -------------------------------------------------------------
    def test_default_is_strictly_sequential(self):
        fixture = self.fixture(web=FakeWeb(delay=0.02))
        self.assertEqual(fixture.retrieval.concurrent_fetches, 1)
        self.assertEqual(fixture.gateway.overlap_length(BATCH, 0), 1)
        self.turn(fixture, BATCH)
        self.assertEqual(fixture.web.peak, 1)
        self.assertEqual(fixture.workflow.db.execute(
            "SELECT count(*) FROM events WHERE kind='web_fetches_overlapped'").fetchone()[0], 0)

    def test_sequential_execution_cannot_pass_the_overlap_barrier(self):
        fixture = self.fixture(web=FakeWeb(barrier=threading.Barrier(2, timeout=0.3)))
        self.turn(fixture, BATCH[:2])  # Each lone fetch breaks the barrier: the probe discriminates.
        statuses = [r[0] for r in fixture.workflow.db.execute("SELECT status FROM retrieval_records ORDER BY rowid")]
        self.assertEqual(statuses, ["failed", "failed"])

    def test_enabled_fetches_really_overlap(self):
        fixture = self.fixture(workers=4, web=FakeWeb(barrier=threading.Barrier(4, timeout=5)))
        self.turn(fixture, BATCH)
        self.assertEqual(fixture.web.peak, 4)
        self.assertTrue(all(name.startswith("web-fetch") for name in fixture.web.threads))
        statuses = [r[0] for r in fixture.workflow.db.execute("SELECT status FROM tool_calls ORDER BY rowid")]
        self.assertEqual(statuses, ["succeeded"] * 5)
        detail = json.loads(fixture.workflow.db.execute(
            "SELECT detail FROM events WHERE kind='web_fetches_overlapped'").fetchone()[0])
        self.assertEqual((detail["calls"], detail["fetches"]), (["s1", "s2", "r1", "r2"], 4))

    def test_option_is_validated_and_not_part_of_the_persisted_configuration(self):
        fixture = self.fixture()
        before = fixture.retrieval.configuration()
        for bad in (0, 5, True, 2.0, "2"):
            with self.assertRaises(RetrievalError):
                fixture.retrieval.allow_concurrent_fetches(bad)
        fixture.retrieval.allow_concurrent_fetches(4)
        self.assertEqual(fixture.retrieval.configuration(), before)  # Existing state directories resume unchanged.

    def test_groups_are_bounded_and_never_cross_other_tools(self):
        fixture = self.fixture(workers=2)
        calls = [search("a", "one"), tool("read_text", {"path": "x.md"}, "b"), search("c", "two"),
                 search("d", "three"), search("e", "four")]
        self.assertEqual([fixture.gateway.overlap_length(calls, i) for i in range(5)], [1, 1, 2, 2, 1])

    # --- Identical observable behaviour ----------------------------------------------------------
    def test_records_results_and_transcript_match_sequential_execution(self):
        sequential, overlapped = self.fixture(workers=1), self.fixture(workers=4, web=FakeWeb(delay=0.02))
        for fixture in (sequential, overlapped):
            self.turn(fixture, BATCH)
        self.assertEqual(overlapped.web.peak, 4)
        self.assertEqual(sequential.snapshot(), overlapped.snapshot())

    def test_results_settle_in_call_order_and_later_tools_see_them(self):
        fixture = self.fixture(workers=4, web=FakeWeb(delay=0.02))
        self.turn(fixture, BATCH)
        results = [json.loads(r[0])["call_id"] for r in fixture.workflow.db.execute(
            "SELECT detail FROM events WHERE kind='tool_result' ORDER BY sequence")]
        self.assertEqual(results, ["s1", "s2", "r1", "r2", "read"])
        read = json.loads(fixture.workflow.db.execute(
            "SELECT result FROM tool_calls WHERE call_id='read'").fetchone()[0])
        self.assertTrue(read["ok"])
        self.assertIn("Evidence from https://docs.example.org/a", read["result"]["content"])

    def test_failures_and_refusals_are_recorded_per_call_like_sequential(self):
        batch = [retrieve("ok", "https://docs.example.org/a", "sources/a.md"),
                 retrieve("missing", "https://docs.example.org/gone", "sources/gone.md"),
                 retrieve("badpath", "https://docs.example.org/c", "sources/c.pdf"),
                 retrieve("duplicate", "https://docs.example.org/d", "sources/a.md")]
        sequential = self.fixture(web=FakeWeb(missing={"https://docs.example.org/gone"}))
        overlapped = self.fixture(workers=4, web=FakeWeb(missing={"https://docs.example.org/gone"}))
        for fixture in (sequential, overlapped):
            self.turn(fixture, batch)
        self.assertEqual(sequential.snapshot(), overlapped.snapshot())
        statuses = [r[0] for r in overlapped.workflow.db.execute("SELECT status FROM tool_calls ORDER BY rowid")]
        self.assertEqual(statuses, ["succeeded", "failed", "failed", "failed"])
        # A refused path never reaches the network, in either mode.
        self.assertNotIn("https://docs.example.org/c", overlapped.web.urls)
        self.assertEqual(sorted(sequential.web.urls), sorted(overlapped.web.urls))

    # --- Budgets, crashes and threads -------------------------------------------------------------
    def test_budget_stop_completes_reserved_calls_then_stops(self):
        fixture = self.fixture(workers=4, max_calls=2)
        calls = [search("a", "one"), search("b", "two"), search("c", "three")]
        with self.assertRaises(ToolBudgetError):
            fixture.gateway.dispatch_retrievals(calls)
        rows = [tuple(r) for r in fixture.workflow.db.execute("SELECT call_id, status FROM tool_calls ORDER BY rowid")]
        self.assertEqual(rows, [("a", "succeeded"), ("b", "succeeded")])
        self.assertEqual(len(fixture.web.urls), 2)  # The unreserved call never fetched.

    def test_unexpected_fetch_crash_leaves_uncertain_reservations_and_is_never_resent(self):
        crash = "https://docs.example.org/crash"
        fixture = self.fixture(workers=4, web=FakeWeb(explode={crash}))
        calls = [retrieve("first", "https://docs.example.org/a", "sources/a.md"),
                 retrieve("crash", crash, "sources/crash.md"),
                 retrieve("last", "https://docs.example.org/b", "sources/b.md")]
        with self.assertRaises(RuntimeError):
            fixture.gateway.dispatch_retrievals(calls)
        rows = dict(fixture.workflow.db.execute("SELECT call_id, status FROM tool_calls").fetchall())
        self.assertEqual(rows, {"first": "succeeded", "crash": "reserved", "last": "reserved"})
        records = [r[0] for r in fixture.workflow.db.execute("SELECT status FROM retrieval_records ORDER BY rowid")]
        self.assertEqual(records, ["succeeded", "reserved", "reserved"])
        uncertain = {item["detail"].split(" call ")[1].split(" ")[0]
                     for item in WorkflowQueries(fixture.workflow).uncertain("user") if item["kind"] == "tool_reserved"}
        self.assertEqual(uncertain, {"crash", "last"})  # Surfaced for inspection, never replayed.
        self.assertEqual(len(fixture.web.urls), 3)  # Each fetch ran once; nothing is retried.

    def test_only_the_controller_thread_uses_the_database(self):
        fixture = self.fixture(workers=4, web=FakeWeb(barrier=threading.Barrier(4, timeout=5)))
        runner = fixture.runner([response(BATCH)])
        controller, seen, real = threading.get_ident(), set(), fixture.workflow.db

        class Watched:
            def __getattr__(self, name):
                seen.add(threading.get_ident())
                return getattr(real, name)
        fixture.workflow.db = Watched()
        try:
            runner.step()
        finally:
            fixture.workflow.db = real
        self.assertEqual(seen, {controller})
        self.assertEqual(fixture.web.peak, 4)

    # --- Official driver wiring -------------------------------------------------------------------
    def official_main(self, *flags):
        """Run the official driver up to scheduler creation with every outside effect replaced."""
        retrieval = Mock()
        services = SimpleNamespace(retrieval=retrieval, executor=None, close=lambda: None)

        @contextmanager
        def workflow(_):
            yield Mock()
        with (patch.object(official_live, "OfficialMidTestPlan"), patch.object(official_live, "_workflow", workflow),
              patch.object(official_live, "OfficialScenarioSession"), patch.object(official_live, "_posted_root"),
              patch.object(official_live, "runtime_config"), patch.object(official_live, "FileTools"),
              patch.object(official_live, "runtime_services", return_value=services),
              patch.object(official_live, "make_scheduler", side_effect=_Stop)):
            with self.assertRaises(_Stop):
                official_live.main(["--config", "plan.json", "--state-dir", "state", "--sequence", "1",
                                    "advance", *flags])
        return retrieval

    def test_official_driver_defaults_to_sequential_fetches(self):
        self.official_main().allow_concurrent_fetches.assert_called_once_with(1)

    def test_official_driver_passes_the_opt_in_and_rejects_larger_values(self):
        self.official_main("--parallel-web-fetches", "4").allow_concurrent_fetches.assert_called_once_with(4)
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            official_live.main(["--config", "p", "--state-dir", "s", "--sequence", "1", "advance",
                                "--parallel-web-fetches", "5"])


class _Stop(Exception):
    pass

if __name__ == "__main__":
    unittest.main()
