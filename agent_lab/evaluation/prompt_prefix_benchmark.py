"""Offline check: how much of each request repeats the previous one unchanged (synthetic; no provider).

The scripted task graphs of `parallel_benchmark` run through the real scheduler, runner, gateway
and files with and without `stable_prompt_prefix`. Every request body is recorded and compared
with the previous request of the same task: the unchanged leading share is what a provider with
prefix caching could reuse. Whether HKGAI caches prefixes, and how much time that saves, is not
measured here.

    python -m agent_lab.evaluation.prompt_prefix_benchmark
"""

import argparse
import json
from pathlib import Path
import statistics
import tempfile

from .. import budget
from ..budget import FinishPolicy
from ..core import Workflow
from ..deepseek import DeepSeekClient
from ..files import FileTools
from ..runner import Limits
from ..scheduler import MultiAgentScheduler, Role
from .official_live import advance, review_proposal
from .parallel_benchmark import CHILD_TOOLS, GRAPHS, ROOT_TOOLS, root, worker


def _text(payload):
    """The prompt as rendered for comparison: tool definitions, then messages in order."""
    body = json.loads(payload)
    return json.dumps(body.get("tools") or [], sort_keys=True) + json.dumps(body["messages"], ensure_ascii=False)


def _task(payload):
    return json.loads(json.loads(payload)["messages"][1]["content"])["task_id"]


def run_graph(graph, stable, directory):
    workflow = Workflow(Path(directory) / "state.sqlite3", clock=lambda: 1000.0)
    files = FileTools(workflow, Path(directory) / "files")
    try:
        children = graph["children"]
        workflow.register_actor("requester", "human")
        for actor in ("lead", *children):
            workflow.register_actor(actor, "agent")
        chat = workflow.create_chat("group", ["requester", "lead", *children])
        root_task = workflow.create_task(chat, "requester", "lead", "Benchmark goal")
        sent = []
        decides = {"lead": root(children, graph["dependent"])}
        decides.update({c: worker(s) for c, s in zip(children, graph["steps"])})

        def record(decide):
            def transport(payload):
                sent.append(payload)
                return decide(payload)
            return transport
        roles = {"lead": Role("lead", ROOT_TOOLS, children, Limits(model_attempts=80))}
        roles.update({c: Role(c, CHILD_TOOLS, (), Limits(model_attempts=80)) for c in children})
        scheduler = MultiAgentScheduler(
            workflow, files, root_task, human="requester", roles=roles, mode="offline_fixture", constraints=[],
            clients={a: DeepSeekClient("synthetic-benchmark", record(d)) for a, d in decides.items()},
            acceptance_id="benchmark", verifier_factory=lambda task: None,
            limits=budget.TreeLimits(model_attempts=80, tool_calls=512, reported_tokens=10 ** 6, duration_seconds=3600),
            show_execution_budget=True, finish_policy=FinishPolicy(), child_retries=2, stable_prompt_prefix=stable)
        for _ in range(500):
            result = advance(scheduler, 1)
            for need in result.get("needs") or []:
                if need.get("kind") in {"awaiting_verification", "independent_verification"}:
                    review_proposal(scheduler, need["task"], "accept", "Synthetic benchmark review")
            if workflow.task(root_task, "requester")["state"] in {"succeeded", "failed", "cancelled"}:
                break
        status = budget.status(workflow, root_task)
        states = dict(workflow.db.execute("SELECT assignee, state FROM tasks ORDER BY rowid").fetchall())
    finally:
        files.close()
        workflow.close()
    previous, shares, total, kept = {}, [], 0, []
    for payload in sent:
        text, task, messages = _text(payload), _task(payload), json.loads(payload)["messages"]
        total += len(text)
        if task in previous:
            before, before_messages = previous[task]
            same = next((i for i, (a, b) in enumerate(zip(before, text)) if a != b), min(len(before), len(text)))
            shares.append(same / len(text))
            # Every message before the previous request's last one is sent again unchanged.
            kept.append(messages[:len(before_messages) - 1] == before_messages[:-1])
        previous[task] = text, messages
    return {"requests": len(sent), "characters_sent": total, "attempts": status["attempts"],
            "tool_calls": status["tool_calls"], "states": states,
            "unchanged_prefix_share_median": round(statistics.median(shares), 3),
            "unchanged_prefix_share_mean": round(statistics.fmean(shares), 3),
            "unchanged_prefix_share_min": round(min(shares), 3),
            "requests_extending_the_previous_one": f"{sum(kept)}/{len(kept)}"}


def benchmark():
    report = {"synthetic": True, "graphs": {}}
    for name, graph in GRAPHS.items():
        entry = {}
        for stable in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                entry["stable_prompt_prefix" if stable else "default"] = run_graph(graph, stable, directory)
        before, after = entry["default"], entry["stable_prompt_prefix"]
        entry["same_requests_tool_calls_and_states"] = all(before[k] == after[k] for k in ("requests", "tool_calls", "states"))
        report["graphs"][name] = entry
    return report


def main(argv=None):
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args(argv)
    print(json.dumps(benchmark(), indent=2))


if __name__ == "__main__":
    main()
