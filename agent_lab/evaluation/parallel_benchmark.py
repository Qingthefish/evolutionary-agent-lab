"""Offline benchmark: sequential vs opt-in overlapping provider calls (synthetic, no provider is contacted).

The same scripted task graphs, mock latencies and requirements run through the real
scheduler, gateway, files and official `advance` driver in both modes. Mock model
latency is a fixed sleep per call; reviews are synthetic acceptances after a fixed
delay. Results describe the scheduler only, never HKGAI speed or model quality.

    python -m agent_lab.evaluation.parallel_benchmark --repeats 5 --latency 0.15
"""

import argparse
import itertools
import json
from pathlib import Path
import statistics
import tempfile
import threading
import time

from .. import budget
from ..budget import FinishPolicy
from ..core import Workflow
from ..deepseek import DeepSeekClient
from ..files import FileTools
from ..runner import Limits
from ..scheduler import MultiAgentScheduler, Role
from .official_live import advance, review_proposal

_IDS = itertools.count()
ROOT_TOOLS = ("delegate_task", "accept_artifact", "read_text", "report_blocker", "submit_for_verification")
CHILD_TOOLS = ("create_text", "offer_artifact", "report_blocker", "submit_for_verification")


def _reply(*calls):
    tool_calls = [{"id": f"b{next(_IDS)}", "type": "function",
                   "function": {"name": name, "arguments": json.dumps(args)}} for name, args in calls]
    return json.dumps({"id": "r", "model": "synthetic-benchmark",
                       "usage": {"prompt_tokens": 9, "completion_tokens": 1, "total_tokens": 10},
                       "choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
                                                                               "tool_calls": tool_calls}}]}).encode()


def _messages(payload):
    for message in json.loads(payload)["messages"]:
        if message["role"] == "user":
            try:
                body = json.loads(message["content"])
            except ValueError:
                continue
            if isinstance(body, dict):
                yield body


def _receipt(payload):
    for message in reversed(json.loads(payload)["messages"]):
        if message["role"] == "tool":
            result = json.loads(message["content"])
            if result.get("ok") and {"path", "sha256"} <= set(result.get("result") or {}):
                return result["result"]
    return None


def worker(steps):
    """`steps` file writes, then offer and submit: steps + 1 provider calls."""
    state = {"n": 0}

    def decide(payload):
        state["n"] += 1
        if state["n"] <= steps:
            return _reply(("create_text", {"path": f"part{state['n']}.md", "content": f"part {state['n']}"}))
        mine = _receipt(payload)
        parent = json.loads(json.loads(payload)["messages"][1]["content"])["parent_task_id"]
        return _reply(("offer_artifact", {"path": mine["path"], "target_task": parent, "expected_sha256": mine["sha256"]}),
                      ("submit_for_verification", {"summary": "Delivered the parts"}))
    return decide


def root(children, dependent):
    state = {"delegated": 0, "accepted": set()}

    def decide(payload):
        offers = [(m["task_id"], o) for m in _messages(payload) if m.get("kind") == "child_task_result"
                  for o in m["offered_artifacts"] if o["artifact_id"] not in state["accepted"]]
        if offers:
            state["accepted"].update(o["artifact_id"] for _, o in offers)
            return _reply(*[("accept_artifact", {"artifact_id": o["artifact_id"], "path": f"in/{t[:6]}.md"})
                            for t, o in offers])
        if not dependent and not state["delegated"]:
            state["delegated"] = len(children)
            return _reply(*[("delegate_task", {"assignee": c, "title": f"Part {c}"}) for c in children])
        if dependent and state["delegated"] < len(children):
            state["delegated"] += 1
            return _reply(("delegate_task", {"assignee": children[state["delegated"] - 1], "title": "Next part"}))
        return _reply(("submit_for_verification", {"summary": "Integrated the parts"}))
    return decide


class Probe:
    def __init__(self, latency):
        self.latency, self.lock, self.inflight, self.peak, self.calls = latency, threading.Lock(), 0, 0, 0

    def wrap(self, decide):
        def transport(payload):
            with self.lock:
                self.inflight += 1
                self.calls += 1
                self.peak = max(self.peak, self.inflight)
            try:
                time.sleep(self.latency)
                return decide(payload)
            finally:
                with self.lock:
                    self.inflight -= 1
        return transport


GRAPHS = {
    "fan-out of 2 independent children": {"children": ("a", "b"), "steps": (5, 5), "dependent": False},
    "fan-out of 3 children (2 workers)": {"children": ("a", "b", "c"), "steps": (5, 3, 3), "dependent": False},
    "dependent chain of 2 children": {"children": ("a", "b"), "steps": (5, 5), "dependent": True},
}


def critical_calls(graph, parallel):
    """Provider calls on the critical path: root turns plus the children's calls on `parallel` workers."""
    child = [s + 1 for s in graph["steps"]]
    roots = (2 * len(child) + 1) if graph["dependent"] else 3  # delegate(s), accept(s), submit.
    if graph["dependent"] or parallel == 1:
        return roots + sum(child)
    lanes = [0] * parallel
    for calls in sorted(child, reverse=True):
        lanes[lanes.index(min(lanes))] += calls
    return roots + max(lanes)


def run_once(graph, parallel, latency, review_delay, directory):
    workflow = Workflow(Path(directory) / f"s{next(_IDS)}.sqlite3")
    files = FileTools(workflow, Path(directory) / f"f{next(_IDS)}")
    try:
        children = graph["children"]
        workflow.register_actor("requester", "human")
        for actor in ("lead", *children):
            workflow.register_actor(actor, "agent")
        chat = workflow.create_chat("group", ["requester", "lead", *children])
        root_task = workflow.create_task(chat, "requester", "lead", "Benchmark goal")
        probe = Probe(latency)
        decides = {"lead": root(children, graph["dependent"])}
        decides.update({c: worker(s) for c, s in zip(children, graph["steps"])})
        roles = {"lead": Role("lead", ROOT_TOOLS, children, Limits(model_attempts=80))}
        roles.update({c: Role(c, CHILD_TOOLS, (), Limits(model_attempts=80)) for c in children})
        options = dict(human="requester", roles=roles, mode="offline_fixture", constraints=[],
                       clients={a: DeepSeekClient("synthetic-benchmark", probe.wrap(d)) for a, d in decides.items()},
                       acceptance_id="benchmark", verifier_factory=lambda task: None,
                       limits=budget.TreeLimits(model_attempts=80, tool_calls=512, reported_tokens=10 ** 6,
                                                duration_seconds=3600),
                       show_execution_budget=True, finish_policy=FinishPolicy(), child_retries=2)
        try:
            scheduler = MultiAgentScheduler(workflow, files, root_task, parallel_model_calls=parallel, **options)
        except TypeError:  # An implementation without the option (the original scheduler) is sequential.
            if parallel != 1:
                raise
            scheduler = MultiAgentScheduler(workflow, files, root_task, **options)
        due = {}
        started = time.perf_counter()
        for _ in range(500):
            result = advance(scheduler, 1)
            now = time.perf_counter()
            waiting = [n["task"] for n in result.get("needs") or []
                       if n.get("kind") in {"awaiting_verification", "independent_verification"}]
            for task in waiting:
                due.setdefault(task, now + review_delay)
            ready = [task for task in waiting if due[task] <= now]
            for task in ready:
                review_proposal(scheduler, task, "accept", "Synthetic benchmark review")
                due.pop(task)
            if workflow.task(root_task, "requester")["state"] in {"succeeded", "failed", "cancelled"}:
                break
            if result["state"] != "running" and not ready:
                if not due:
                    break
                time.sleep(max(0.0, min(due.values()) - time.perf_counter()))
        wall = time.perf_counter() - started
        status = budget.status(workflow, root_task)
        return {"wall_seconds": wall, "peak_concurrent_calls": probe.peak, "provider_calls": probe.calls,
                "reserved_requests": status["attempts"], "tool_calls": status["tool_calls"], "tokens": status["tokens"],
                "states": dict(workflow.db.execute("SELECT assignee, state FROM tasks ORDER BY rowid").fetchall())}
    finally:
        files.close()
        workflow.close()


def benchmark(repeats, latency, review_delay):
    report = {"synthetic": True, "latency_seconds_per_call": latency, "review_delay_seconds": review_delay,
              "repeats": repeats, "graphs": {}}
    with tempfile.TemporaryDirectory() as directory:
        for name, graph in GRAPHS.items():
            entry = {}
            for parallel in (1, 2):
                runs = [run_once(graph, parallel, latency, review_delay, directory) for _ in range(repeats)]
                walls = [r["wall_seconds"] for r in runs]
                path = critical_calls(graph, parallel) * latency
                entry[f"parallel_{parallel}"] = {
                    "wall_seconds_median": round(statistics.median(walls), 3),
                    "wall_seconds_min_max": [round(min(walls), 3), round(max(walls), 3)],
                    "critical_path_provider_seconds": round(path, 3),
                    "scheduler_overhead_seconds_median": round(statistics.median(walls) - path, 3),
                    **{key: sorted({json.dumps(r[key], sort_keys=True) for r in runs}) for key in (
                        "peak_concurrent_calls", "provider_calls", "reserved_requests", "tool_calls", "tokens",
                        "states")}}
            one, two = entry["parallel_1"]["wall_seconds_median"], entry["parallel_2"]["wall_seconds_median"]
            entry["speedup"] = round(one / two, 2) if two else None
            report["graphs"][name] = entry
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--latency", type=float, default=0.15)
    parser.add_argument("--review-delay", type=float, default=0.0)
    args = parser.parse_args(argv)
    print(json.dumps(benchmark(args.repeats, args.latency, args.review_delay), indent=2))


if __name__ == "__main__":
    main()
