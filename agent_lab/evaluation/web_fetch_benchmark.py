"""Offline benchmark: sequential vs opt-in overlapped web fetches (synthetic; no network, no provider).

Each workload batch is one model reply holding consecutive search_web/retrieve_text calls. It
runs through the real runner, gateway, retrieval records and task files; only the HTTPS fetch is
replaced by a sleep of the given latency. With `--replay`, batch sizes and per-call latencies are
read from a run database's recorded tool timings (read-only), so the result is a replay estimate
of wall-clock time spent waiting for retrieval, never a measurement of live sites or model quality.

    python -m agent_lab.evaluation.web_fetch_benchmark --workers 4
    python -m agent_lab.evaluation.web_fetch_benchmark --workers 4 --replay COPY.sqlite3 --scale 0.05
"""

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit
from xml.sax.saxutils import escape

from ..core import Workflow
from ..deepseek import DeepSeekClient
from ..files import FileTools
from ..gateway import ToolGateway
from ..retrieval import WebRetrieval
from ..runner import Limits, TaskRunner

WEB = {"search_web", "retrieve_text"}
# Default synthetic workload: 20 replies of four calls at the median recorded latencies
# (search 1.55 s, retrieve 2.4 s; Securities runs of 2026-11-21).
SYNTHETIC = [[("search_web", 1.55), ("search_web", 1.55), ("retrieve_text", 2.4), ("retrieve_text", 2.4)]] * 20
BATCHES_PER_TASK = 20  # Each task may hold at most 100 retrieval records.


def recorded_batches(path):
    """Consecutive web calls per model reply with their recorded tool durations (read-only)."""
    db = sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True)
    try:
        batches, current, opened = [], None, {}
        for kind, detail, stamp in db.execute("SELECT kind, detail, timestamp FROM events ORDER BY sequence"):
            detail = json.loads(detail)
            if kind == "model_attempt_reserved":
                current = []
                batches.append(current)
            elif kind == "tool_reserved":
                opened[detail["call_id"]] = (stamp, detail["name"])
            elif kind == "tool_result" and detail["call_id"] in opened and current is not None:
                started, name = opened.pop(detail["call_id"])
                current.append((name, stamp - started))
        runs = []
        for batch in batches:
            run = []
            for name, seconds in batch + [(None, 0)]:
                if name in WEB:
                    run.append((name, seconds))
                elif run:
                    runs.append(run)
                    run = []
        return runs
    finally:
        db.close()


class SleepingWeb:
    def __init__(self, latencies, scale):
        self.latencies, self.scale = latencies, scale
        self.lock, self.inflight, self.peak, self.fetches = threading.Lock(), 0, 0, 0

    def fetch(self, url):
        with self.lock:
            self.inflight += 1
            self.fetches += 1
            self.peak = max(self.peak, self.inflight)
        try:
            time.sleep(self.latencies[url] * self.scale)
            if url.startswith("https://www.bing.com/search?"):
                query = parse_qs(urlsplit(url).query)["q"][0]
                link = "https://www.bing.com/search?" + urlencode({"q": query, "format": "rss"})
                body = (f"<rss><channel><link>{escape(link)}</link><item><title>{escape(query)}</title>"
                        f"<link>https://example.org/{abs(hash(query))}</link><description>synthetic</description>"
                        "</item></channel></rss>").encode()
                kind = "application/rss+xml"
            else:
                body, kind = f"<p>Synthetic page {url}</p>".encode(), "text/html"
            return {"url": url, "content_type": kind, "body": body, "sha256": hashlib.sha256(body).hexdigest(),
                    "redirects": []}
        finally:
            with self.lock:
                self.inflight -= 1


def run_workload(batches, workers, scale, directory):
    workflow = Workflow(Path(directory) / "state.sqlite3", clock=lambda: 1000.0)
    files = FileTools(workflow, Path(directory) / "files")
    try:
        workflow.register_actor("requester", "human")
        workflow.register_actor("research", "agent")
        chat = workflow.create_chat("group", ["requester", "research"])
        latencies, wall, records = {}, 0.0, []
        web = SleepingWeb(latencies, scale)
        for offset in range(0, len(batches), BATCHES_PER_TASK):
            chunk = batches[offset:offset + BATCHES_PER_TASK]
            task = workflow.create_task(chat, "requester", "research", f"Benchmark sources {offset}")
            workflow.start_task(task, "research")
            retrieval = WebRetrieval(workflow, files)
            retrieval.allow_concurrent_fetches(workers)
            retrieval.http.fetch = web.fetch
            gateway = ToolGateway(workflow, files, task, "research", human="requester",
                                  allowed=["search_web", "retrieve_text"], retrieval=retrieval, max_calls=1000)
            replies = []
            for b, batch in enumerate(chunk):
                calls = []
                for c, (name, seconds) in enumerate(batch):
                    key = f"{offset + b}-{c}"
                    if name == "search_web":
                        query = f"benchmark query {key}"
                        latencies["https://www.bing.com/search?" + urlencode({"q": query, "format": "rss"})] = seconds
                        arguments = {"query": query, "limit": 1}
                    else:
                        url = f"https://example.org/page-{key}"
                        latencies[url] = seconds
                        arguments = {"url": url, "path": f"sources/{key}.md"}
                    calls.append({"id": f"call-{key}", "type": "function",
                                  "function": {"name": name, "arguments": json.dumps(arguments)}})
                replies.append({"id": "r", "model": "synthetic-benchmark",
                                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                                "choices": [{"finish_reason": "tool_calls",
                                             "message": {"role": "assistant", "content": None, "tool_calls": calls}}]})
            script = iter(replies)
            client = DeepSeekClient("synthetic-benchmark", lambda payload: json.dumps(next(script)).encode())
            runner = TaskRunner(gateway, client, mode="offline_fixture", constraints=["Benchmark"], verifier=None,
                                limits=Limits(model_attempts=len(chunk) + 1, reported_tokens=10 ** 6,
                                              duration_seconds=10 ** 6))
            for _ in chunk:
                started = time.perf_counter()
                runner.step()
                wall += time.perf_counter() - started
            records += [tuple(r) for r in workflow.db.execute(
                "SELECT call_id, name, status FROM tool_calls WHERE task=? ORDER BY rowid", (task,))]
        return {"wall_seconds": round(wall, 3), "fetches": web.fetches,
                "peak_concurrent_fetches": web.peak, "tool_calls": len(records),
                "succeeded": sum(1 for r in records if r[2] == "succeeded"), "records": records}
    finally:
        files.close()
        workflow.close()


def benchmark(batches, workers, scale):
    """Local bookkeeping is measured at zero latency and kept unscaled; only fetch waits are scaled back."""
    results = {}
    for mode, count in (("sequential", 1), ("overlapped", workers)):
        with tempfile.TemporaryDirectory() as directory:
            local = run_workload(batches, count, 0.0, directory)["wall_seconds"]
        with tempfile.TemporaryDirectory() as directory:
            result = run_workload(batches, count, scale, directory)
        result["local_seconds_at_zero_latency"] = local
        result["replayed_seconds"] = round(local + max(0.0, result["wall_seconds"] - local) / scale, 1)
        results[mode] = result
    sequential, overlapped = results["sequential"], results["overlapped"]
    same = sequential.pop("records") == overlapped.pop("records")
    recorded = sum(seconds for batch in batches for _, seconds in batch)
    return {"synthetic": True, "workers": workers, "scale": scale, "batches": len(batches),
            "calls": sum(map(len, batches)), "recorded_retrieval_seconds": round(recorded, 1),
            "sequential": sequential, "overlapped": overlapped, "identical_tool_records": same,
            "saved_replayed_seconds": round(sequential["replayed_seconds"] - overlapped["replayed_seconds"], 1)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workers", type=int, choices=(2, 3, 4), default=4)
    parser.add_argument("--scale", type=float, default=0.05, help="Sleep this fraction of each latency")
    parser.add_argument("--replay", action="append", default=[], help="Run database to read recorded timings from")
    args = parser.parse_args(argv)
    batches = [batch for path in args.replay for batch in recorded_batches(path)] if args.replay else SYNTHETIC
    print(json.dumps(benchmark(batches, args.workers, args.scale), indent=2))


if __name__ == "__main__":
    main()
