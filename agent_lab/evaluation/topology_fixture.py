"""Deterministic replay of scripted development simulations through the real runtime.

A fixture supplies model turns only. The real scheduler, tool gateway, file
broker, shared budgets and independent acceptance run unchanged, so tool errors,
verification failures and budget stops are genuine runtime behaviour. Dynamic
values (task IDs, file digests, artifact IDs) are resolved from the actual
request transcript, never hard-coded. Results are engineering validation only.
"""

import json
from pathlib import Path

from ..core import WorkflowError
from ..deepseek import DeepSeekClient, ProviderError
from ..protocol import strict_json
from ..runtime import LiveConfig
from .manifest import digest
from .plan import _object
from .topology import TOPOLOGIES
from .topology_plan import LiveTopologyDriver, TopologyExperiment, TopologyTrial
from .topology_report import FIXTURE_MODEL

SET_SCHEMA = "c07-replay-fixture-set"
FIXTURE_SCHEMA = "c07-replay-fixture"
PROVENANCE_KEYS = {"kind", "drafted_with", "normalization", "model_evidence"}
_MAX_BYTES = 262144
# Placeholder counts satisfy the provider protocol; they are not token measurements.
SYNTHETIC_USAGE = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}


def _read(path):
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(_MAX_BYTES + 1)
        if len(raw) > _MAX_BYTES:
            raise ValueError()
        return strict_json(raw.decode("utf-8"))
    except (OSError, ValueError, UnicodeError, RecursionError):
        raise WorkflowError(f"Cannot read bounded fixture JSON {Path(path).name}") from None


def _provenance(value, label):
    _object(value, PROVENANCE_KEYS, label + " provenance")
    if value["kind"] != "development_simulation" or value["model_evidence"] is not False:
        raise WorkflowError(label + ": fixtures must be labelled development_simulation with model_evidence false")
    for key in ("drafted_with", "normalization"):
        if not isinstance(value[key], str) or not value[key].strip():
            raise WorkflowError(label + f": provenance {key} must be stated")
    return value


def _turn(turn, label):
    if not isinstance(turn, dict) or len(turn) != 1 or next(iter(turn)) not in {"tool_calls", "final", "provider_error"}:
        raise WorkflowError(label + ": a turn is exactly one of tool_calls, final or provider_error")
    kind, value = next(iter(turn.items()))
    if kind == "tool_calls":
        if not isinstance(value, list) or not 1 <= len(value) <= 16:
            raise WorkflowError(label + ": tool_calls needs 1-16 calls")
        for call in value:
            _object(call, {"name", "arguments"}, label + " call")
            if not isinstance(call["name"], str) or not isinstance(call["arguments"], dict):
                raise WorkflowError(label + ": call needs a tool name and argument object")
    elif not isinstance(value, str) or not value.strip():
        raise WorkflowError(label + f": {kind} needs nonempty text")


def load_fixture(path):
    data = _read(path)
    _object(data, {"schema", "version", "fixture_id", "case_id", "topology", "description", "provenance", "scripts"}, "Fixture")
    label = f"Fixture {data.get('fixture_id')}"
    if data["schema"] != FIXTURE_SCHEMA or data["version"] != 1 or data["topology"] not in TOPOLOGIES:
        raise WorkflowError(label + ": unsupported schema, version or topology")
    _provenance(data["provenance"], label)
    if not isinstance(data["scripts"], dict) or not data["scripts"]:
        raise WorkflowError(label + ": scripts must map agents to turn lists")
    for agent, turns in data["scripts"].items():
        if not isinstance(turns, list) or not turns:
            raise WorkflowError(label + f": agent {agent} needs at least one turn")
        for number, turn in enumerate(turns):
            _turn(turn, f"{label} {agent} turn {number}")
    return data


def load_fixture_set(path):
    path = Path(path).resolve()
    data = _read(path)
    _object(data, {"schema", "version", "set_id", "description", "provenance", "entries"}, "Fixture set")
    if data["schema"] != SET_SCHEMA or data["version"] != 1:
        raise WorkflowError("Unsupported fixture set schema or version")
    _provenance(data["provenance"], "Fixture set")
    fixtures = {}
    if not isinstance(data["entries"], dict) or not data["entries"]:
        raise WorkflowError("Fixture set entries must map case IDs to topology fixtures")
    for case_id, arms in data["entries"].items():
        _object(arms, set(TOPOLOGIES), f"Fixture set entry {case_id}")
        for topology, name in arms.items():
            if not isinstance(name, str) or "/" in name or "\\" in name or not name.endswith(".json"):
                raise WorkflowError("Fixture references must be plain .json file names beside the set")
            fixture = load_fixture(path.parent / name)
            if (fixture["case_id"], fixture["topology"]) != (case_id, topology):
                raise WorkflowError(f"Fixture {name} is registered for the wrong case or topology")
            fixtures[(case_id, topology)] = fixture
    return data, fixtures


class ReplayTransport:
    """Return the scripted turn for the calling agent; resolve references from the request."""

    def __init__(self, fixture):
        self.fixture = fixture
        self.assignments = {}
        self.requests = []

    def __call__(self, payload):
        request = json.loads(payload)
        self.requests.append(request)
        context = json.loads(request["messages"][1]["content"])
        agent, task = context["role"]["agent"], context["task_id"]
        if self.assignments.setdefault(agent, task) != task:
            raise ProviderError(f"Replay fixture scripts one assignment per agent; {agent} received another")
        turn = sum(m["role"] == "assistant" for m in request["messages"])
        script = self.fixture["scripts"].get(agent, [])
        if turn >= len(script):
            raise ProviderError(f"Replay fixture has no scripted turn {turn} for {agent}")
        kind, value = next(iter(script[turn].items()))
        if kind == "provider_error":
            raise ProviderError("Simulated provider failure: " + value)
        message = {"role": "assistant", "content": value if kind == "final" else None}
        if kind == "tool_calls":
            message["tool_calls"] = [{"id": f"c07-{agent}-{turn}-{i}", "type": "function", "function": {
                "name": call["name"], "arguments": json.dumps(_resolve(call["arguments"], request, context))}}
                for i, call in enumerate(value)]
        return json.dumps({"id": f"replay-{agent}-{turn}", "model": FIXTURE_MODEL, "usage": SYNTHETIC_USAGE,
                           "choices": [{"message": message,
                                        "finish_reason": "tool_calls" if kind == "tool_calls" else "stop"}]}).encode()


def _resolve(value, request, context):
    if isinstance(value, list):
        return [_resolve(item, request, context) for item in value]
    if not isinstance(value, dict):
        return value
    if "$ref" not in value:
        return {key: _resolve(item, request, context) for key, item in value.items()}
    ref = value["$ref"]
    if ref in {"task_id", "parent_task_id", "root_task_id"} and set(value) == {"$ref"}:
        if context.get(ref) is None:
            raise ProviderError(f"Replay reference {ref} is unavailable for this task")
        return context[ref]
    messages = [json.loads(m["content"]) for m in reversed(request["messages"])
                if m["role"] in {"tool", "user"} and isinstance(m.get("content"), str) and m["content"].startswith("{")]
    if ref == "file_sha256" and set(value) == {"$ref", "path"}:
        for item in messages:
            result = item.get("result") if item.get("ok") else None
            if isinstance(result, dict) and result.get("path") == value["path"] and "sha256" in result:
                return result["sha256"]
    elif ref == "child_artifact" and set(value) == {"$ref", "source_path"}:
        for item in messages:
            if item.get("kind") == "child_task_result":
                for offer in item["offered_artifacts"]:
                    if offer["source_path"] == value["source_path"] and not offer["consumed"]:
                        return offer["artifact_id"]
    else:
        raise ProviderError(f"Unsupported replay reference {value!r}")
    raise ProviderError(f"Replay reference {value!r} has no matching evidence in the transcript")


class FixtureTopologyDriver(LiveTopologyDriver):
    mode = "offline_fixture"

    def __init__(self, live, set_data, fixtures):
        super().__init__(live)
        self.fixtures = fixtures
        self.fixture_info = {"set_id": set_data["set_id"], "provenance": set_data["provenance"],
                             "set_sha256": digest(set_data),
                             "fixtures": {f"{c}/{t}": {"fixture_id": f["fixture_id"], "sha256": digest(f),
                                                       "provenance": f["provenance"]}
                                          for (c, t), f in sorted(fixtures.items())},
                             "usage": "synthetic placeholder counts, not tokens"}
        self.transports = []

    def clients(self, roles, slot):
        fixture = self.fixtures.get((slot["case_id"], slot["topology"]))
        if fixture is None:
            raise WorkflowError(f"No replay fixture for {slot['case_id']} / {slot['topology']}")
        transport = ReplayTransport(fixture)
        self.transports.append((slot["slot"], transport))
        return {agent: DeepSeekClient(self.live.model, transport, max_tokens=self.live.max_output_tokens) for agent in roles}


def run_fixture(config, fixture_set, output_root):
    """Replay a fixture set against a manifest. No key, network or engine is used."""
    experiment = TopologyExperiment(config)
    settings = experiment.runtime.settings
    if settings["enable_web"] or settings["docker_host"] or settings["repositories"]:
        raise WorkflowError("Replay fixtures require a text-only runtime plan without web, Docker or Git backends")
    set_data, fixtures = load_fixture_set(fixture_set)
    missing = {(c.id, t) for c in experiment.cases for t in TOPOLOGIES} - fixtures.keys()
    if missing:
        raise WorkflowError("Fixture set does not cover every planned case/topology: "
                            + ", ".join(f"{c}/{t}" for c, t in sorted(missing)))
    driver = FixtureTopologyDriver(LiveConfig(api_key="unused-offline-fixture-key", **settings), set_data, fixtures)
    return TopologyTrial(experiment, driver).run(output_root), driver


__all__ = ["FixtureTopologyDriver", "ReplayTransport", "SYNTHETIC_USAGE", "load_fixture", "load_fixture_set", "run_fixture"]
