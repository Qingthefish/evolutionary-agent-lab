"""Public experiment conditions for reproducibility; never serialize credentials.

Fingerprints detect accidental condition changes, not forged experimental data.
Memory-on batch comparison is still unavailable; interactive runtime experience
is separate. C02 must version cross-task/reset conditions before comparable trials.
"""

from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import re

from ..gateway import _SPECS
from ..runner import _PROMPT, model_context_conditions
from ..runtime import LIVE_AGENTS, live_members, live_roles, live_roles_for_policy, policy_delegation_inputs, provider_endpoint
from ..delegation import input_records
from .cases import input_records as case_input_records, INPUT_PROTOCOL


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
                                    separators=(",", ":")).encode()).hexdigest()


def build_manifest(cases, live, memory):
    definitions = []
    for case in sorted(cases, key=lambda c: c.id):
        definition = asdict(case)
        definition.pop("source")  # File location is not task content.
        definitions.append(definition)
    package = Path(__file__).resolve().parents[1]
    sources = {str(p.relative_to(package)): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(package.rglob("*.py"))}
    runtime = {"provider": None, "model": None, "roles": None, "tree_limits": None}
    if live is not None:
        # Deliberate whitelist: asdict(live) would include its private API key.
        runtime = {"provider": live.provider, "model": live.model, "endpoint": provider_endpoint(live.provider),
                   "max_output_tokens": live.max_output_tokens, "socket_timeout": live.socket_timeout,
                   "roles": {a: asdict(r) for a, r in live_roles(live_members(live), live).items()},
                   "tree_limits": asdict(live.tree_limits), "constraints": list(live.constraints),
                   "child_retries": live.child_retries,
                   "capabilities": {"web": live.enable_web, "memory": live.enable_memory,
                                    "memory_namespace": live.memory_namespace if live.enable_memory else None,
                                    "python_image": live.python_image,
                                    "docker_endpoint_sha256": digest(live.docker_host) if live.docker_host else None,
                                    "repositories_sha256": digest([asdict(r) for r in live.repositories]) if live.repositories else None}}
        if live.enable_delete:
            runtime["capabilities"]["delete"] = "task-local-exact-version-human-release-v1"
        if live.enable_collaboration:
            runtime["capabilities"]["collaboration"] = "scoped-specialist-delegation-messages-v1"
        from .harness import _case_policy
        if any(c.expected.declared_subtasks_only for c in cases):
            runtime['case_roles'] = {c.id: {a:asdict(r) for a,r in live_roles_for_policy(
                live_members(live),live,_case_policy(c,live)).items()} for c in cases}
            runtime['case_budget_context'] = {c.id: 'local-reservations-v1' if c.expected.declared_subtasks_only else None
                                             for c in cases}
            runtime['case_model_context'] = {c.id: model_context_conditions(c.expected.declared_subtasks_only)
                                             for c in cases}
        prerequisites = {c.id: input_records(policy_delegation_inputs(_case_policy(c, live)) or ()) for c in cases}
        if any(prerequisites.values()):
            runtime['case_delegation_inputs'] = prerequisites
        if any(c.inputs for c in cases):
            runtime['case_inputs'] = case_input_records(cases)
            runtime['input_protocol'] = INPUT_PROTOCOL
    manifest = {"schema_version": 1, "cases": definitions, "runtime": runtime,
                "code_sha256": digest(sources), "prompt_sha256": digest(_PROMPT),
                "tools_sha256": digest(_SPECS),
                "interventions": {"live": "external-human-pause-no-scripted-responses-v1",
                                  "offline": "case-defined-scripted-responses-v1", "include_wait_in_elapsed": True},
                "initial_memory": {"reset": "fresh-per-case", "seed": "empty",
                                   "scope": "agent+conversation+evaluation-namespace"},
                "condition": {"memory": memory}}
    # Normalize tuples to the JSON representation used by saved reports.
    return json.loads(json.dumps(manifest, allow_nan=False))


def comparison_conditions(run):
    """Validate saved conditions and remove only the declared memory switch."""
    manifest = run.get("manifest")
    required = {"schema_version", "cases", "runtime", "code_sha256", "prompt_sha256", "tools_sha256",
                "interventions", "initial_memory", "condition"}
    if (not isinstance(manifest, dict) or set(manifest) != required
            or type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1):
        raise ValueError("missing or unsupported experiment manifest")
    if run.get("manifest_sha256") != digest(manifest):
        raise ValueError("experiment manifest fingerprint does not match")
    if manifest["condition"] != {"memory": run.get("memory")}:
        raise ValueError("manifest memory condition differs from the run label")
    for key in ("code_sha256", "prompt_sha256", "tools_sha256"):
        if not isinstance(manifest[key], str) or not re.fullmatch(r"[0-9a-f]{64}", manifest[key]):
            raise ValueError("missing code/prompt/tool fingerprint")
    if manifest["initial_memory"] != {"reset": "fresh-per-case", "seed": "empty", "scope": "agent+conversation+evaluation-namespace"}:
        raise ValueError("unsupported initial-memory protocol")
    interventions = manifest["interventions"]
    if (not isinstance(interventions, dict) or set(interventions) != {"live", "offline", "include_wait_in_elapsed"}
            or not interventions["live"] or not interventions["offline"] or interventions["include_wait_in_elapsed"] is not True):
        raise ValueError("missing intervention/timing protocol")
    runtime = manifest["runtime"]
    if (not isinstance(runtime, dict) or runtime.get("provider") not in {"deepseek", "hkgai"}
            or not isinstance(runtime.get("model"), str) or not runtime["model"]
            or not isinstance(runtime.get("roles"), dict) or not runtime["roles"]
            or not isinstance(runtime.get("tree_limits"), dict) or not runtime["tree_limits"]):
        raise ValueError("missing live-model/tool/budget conditions")
    results = run.get("results")
    if not isinstance(results, list) or not results:
        raise ValueError("comparison requires nonempty results")
    ids = [r["case"]["id"] for r in results]
    definitions = manifest["cases"]
    if not isinstance(definitions, list):
        raise ValueError("missing case definitions")
    expected_ids = [c["id"] for c in definitions]
    if (len(set(ids)) != len(ids) or len(set(expected_ids)) != len(expected_ids)
            or set(ids) != set(expected_ids)):
        raise ValueError("results do not match the manifest's complete unique case set")
    definitions_by_id = {c["id"]: c for c in definitions}
    for result in results:
        defined = definitions_by_id[result["case"]["id"]]
        for key in ("id", "title", "goal", "driver", "split", "control", "expected", "constraints"):
            if digest(result["case"][key]) != digest(defined[key]):
                raise ValueError("result case content differs from its experiment manifest")
        if result.get("control") != defined["control"]:
            raise ValueError("result control label differs from the declared case")
        if result.get("status") != "executed" or result.get("mode") != "live":
            raise ValueError("every selected live case must be executed; blocked/failed outcomes stay in the results")
        initial = result.get("initial_memory")
        if initial != {"lessons": 0, "lesson_sources": 0, "lesson_uses": 0, "lesson_retrievals": 0}:
            raise ValueError("initial memory is missing or does not satisfy the fresh-state contract")
        workflow = result.get("workflow")
        if workflow is None and result.get("classification") == "driver_error":
            continue  # Keep a real setup/provider failure, with explicitly missing evidence.
        if not isinstance(workflow, dict) or not isinstance(workflow.get("observed_models"), list):
            raise ValueError("missing/malformed observed model evidence")
        if any(not isinstance(m, str) or not m for m in workflow["observed_models"]):
            raise ValueError("invalid observed model identity")
        outcomes = workflow.get("task_outcomes")
        if not isinstance(outcomes, list) or not outcomes:
            raise ValueError("missing task outcome evidence")
        for task in outcomes:
            if type(task["verified_success"]) is not bool:
                raise ValueError("verified task success must be boolean")
            for key in ("elapsed_seconds", "human_wait_seconds", "final_duration_seconds"):
                value = task[key]
                if key == "final_duration_seconds" and value is None:
                    continue
                if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                    raise ValueError("task timing must be nonnegative and finite")
    normalized = json.loads(json.dumps(manifest, allow_nan=False))
    normalized.pop("condition")
    # Memory tool availability is the intended intervention, not an unrelated
    # change of tools. All other tools, instructions and limits must match.
    for role in normalized["runtime"]["roles"].values():
        role["tools"] = [t for t in role["tools"] if t not in {"search_memory", "select_memory"}]
    return normalized
