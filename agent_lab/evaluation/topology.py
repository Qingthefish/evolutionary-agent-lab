"""Matched single-agent/multi-agent topology conditions and fairness checks.

Both conditions reuse the existing live roles, MultiAgentScheduler, tool
gateway, shared task-tree budget and trusted acceptance policy. The agent
topology is the intended independent variable. Differences that the topology
itself makes unavoidable are recorded as confounds, never hidden. Everything
here is static inspection: no model call, network access or backend start.
"""

from dataclasses import asdict, dataclass
import json
import re

from ..core import WorkflowError
from ..deepseek import DeepSeekHTTP
from ..runner import Limits, _PROMPT as _RUNNER_PROMPT
from ..runtime import live_members, live_roles
from ..scheduler import Role
from .manifest import digest

PROTOCOL = "c07-matched-topology-v1"
TOPOLOGIES = ("single_agent", "multi_agent")
SINGLE_AGENT = "solo"
MULTI_ROOT = "coordinator"
STRUCTURAL_HANDOFF = "c07-structural-handoff-v1"
CHILD_RELEASE = (STRUCTURAL_HANDOFF, "trusted-review")
ORDER = "alternating-by-replicate-and-case-v1"

# Tools whose only purpose is moving work or snapshots between agent tasks.
# A single agent has no other task to address, so it never receives them.
COORDINATION_TOOLS = frozenset({"delegate_task", "delegate_with_inputs", "retry_failed_task",
                                "offer_artifact", "accept_artifact"})
CAPABILITY_CLASSES = {
    "filesystem_read": frozenset({"read_text"}),
    "filesystem_write": frozenset({"create_text", "update_text"}),
    "filesystem_delete": frozenset({"delete_text"}),
    "human": frozenset({"ask_human"}),
    "conversation": frozenset({"post_message", "read_messages"}),
    "web": frozenset({"search_web", "retrieve_text"}),
    "code_execution": frozenset({"run_python"}),
    "git_read": frozenset({"git_status", "git_diff", "git_log"}),
    "git_write": frozenset({"git_commit", "git_push"}),
    "memory": frozenset({"search_memory", "select_memory", "record_lesson"}),
    "coordination": COORDINATION_TOOLS,
}

SINGLE_INSTRUCTIONS = (
    "Complete the entire goal yourself. Plan the work, create and revise the deliverables with your tools, "
    "check them against every constraint, and repair them when trusted verification reports a failure. "
    "No other agents are available, so do not attempt delegation.")
DELETE_GUIDANCE = (" Delete only an exact version of your own task-local text through delete_text; read its current "
                   "SHA-256 first. This requests human approval and pauses; approval release belongs to the trusted "
                   "human controller, never to you.")

HUMAN_POLICIES = {
    "boundary-stops-run-v1": {
        "policy": "boundary-stops-run-v1",
        "initial_instructions": "case-goal-and-constraints-only",
        "clarification": "recorded; no response is supplied; unattended progress stops",
        "approval": "recorded; no decision is supplied; unattended progress stops",
        "responder": "none",
        "eligibility": "every agent with ask_human may request; requests count as interventions",
    },
}
MEMORY_POLICIES = {
    "disabled": {"mode": "disabled", "initial_state": "fresh-empty-per-run", "tools": "none"},
}

_AGENT_WORDS = re.compile(r"\b(coordinator|writer|editor|researcher|coder|integrator|solo|sub-?agents?|delegat\w*)\b",
                          re.IGNORECASE)
_RESOURCES = ("model_attempts", "reported_tokens", "tool_calls", "duration_seconds")


class FairnessError(WorkflowError):
    """A single/multi comparison that is not methodologically comparable."""

    def __init__(self, report):
        self.report = report
        lines = [f"[{e['dimension']}/{e['code']}] {e['message']}" for e in report["errors"]]
        super().__init__("Comparison rejected: " + " | ".join(lines))


@dataclass(frozen=True)
class Condition:
    topology: str
    root: str
    roles: dict
    record: dict

    @property
    def members(self):
        return tuple(self.roles)


def tool_classes(tools):
    """Map each tool to one capability class; unknown tools fail closed."""
    result = {}
    for tool in tools:
        owners = [name for name, members in CAPABILITY_CLASSES.items() if tool in members]
        if len(owners) != 1:
            raise WorkflowError(f"Tool {tool!r} has no unique capability class; update the C07 classification first")
        result[tool] = owners[0]
    return result


def case_eligibility(case):
    """Reasons a case cannot serve as a matched single/multi control (empty if eligible)."""
    reasons = []
    expected = case.expected
    if case.driver != "live_scheduler":
        reasons.append(f"driver {case.driver} replays a fixed script and ignores topology")
    if case.split != "development":
        reasons.append("only development cases are allowed; held-out data is never used here")
    if case.control is not None:
        reasons.append("negative evaluator controls are not topology comparisons")
    if case.human_responses or case.approval:
        reasons.append("scripted human responses conflict with the boundary-stops human policy")
    if expected.final_state != "succeeded":
        reasons.append("matched comparisons use positive goal cases")
    for subtask in expected.subtasks:
        reasons.append(f"prescribes a delegated subtask for assignee {subtask.assignee!r}; "
                       "a single agent cannot satisfy a required decomposition")
    if expected.min_tasks > 1:
        reasons.append(f"requires at least {expected.min_tasks} tasks, which forces decomposition")
    for human in expected.human_requests:
        if human.assignee is not None:
            reasons.append(f"expects a human request from assignee {human.assignee!r}, which is topology-specific")
    text = " ".join((case.goal, *case.constraints))
    found = sorted({m.group(0).lower() for m in _AGENT_WORDS.finditer(text)})
    if found:
        reasons.append("goal or constraints name topology-specific agents or delegation (" + ", ".join(found)
                       + "); rephrase the task topology-neutrally")
    return reasons


def case_record(case, policy):
    content = {k: v for k, v in asdict(case).items() if k != "source"}
    acceptance = policy.record()
    return {"id": case.id, "content_sha256": digest(json.loads(json.dumps(content))),
            "acceptance_id": policy.acceptance_id, "acceptance_sha256": digest(acceptance),
            "ineligible": case_eligibility(case)}


def single_agent_role(team, task_limits):
    """Union of the team's task capabilities, minus inter-agent coordination tools."""
    tools = tuple(sorted({t for role in team.values() for t in role.tools if t not in COORDINATION_TOOLS}))
    instructions = SINGLE_INSTRUCTIONS + (DELETE_GUIDANCE if "delete_text" in tools else "")
    limits = Limits(model_attempts=task_limits["model_attempts"], reported_tokens=task_limits["reported_tokens"],
                    duration_seconds=task_limits["duration_seconds"],
                    repeated_outcomes=task_limits["repeated_outcomes"])
    return Role(instructions, tools, (), limits, task_limits["tool_calls"])


def effective_ceilings(topology, roles, root, tree):
    """Largest usage the configured limits can ever release for one goal.

    The shared tree budget bounds every condition. A single agent is additionally
    bounded by its one task's limits. A team is bounded by its root task plus at
    most (tasks - 1) delegated tasks, each under its own role limits.
    """
    def per_task(role, key):
        return role.tool_calls if key == "tool_calls" else getattr(role.limits, key)

    result = {}
    if topology == "single_agent":
        role = roles[root]
        for key in _RESOURCES:
            result[key] = min(per_task(role, key), getattr(tree, key))
        result["tasks"] = 1
        return result
    delegable = {d for role in roles.values() for d in role.delegates}
    for key in _RESOURCES:
        if key == "duration_seconds":
            # The root's own deadline ends the goal regardless of child deadlines.
            result[key] = min(tree.duration_seconds, roles[root].limits.duration_seconds)
            continue
        children = max((per_task(roles[a], key) for a in delegable), default=0) * (tree.tasks - 1)
        result[key] = min(getattr(tree, key), per_task(roles[root], key) + children)
    result["tasks"] = tree.tasks
    return result


def _role_record(role):
    return {"instructions_sha256": digest(role.instructions), "tools": sorted(role.tools),
            "delegates": sorted(role.delegates), "limits": asdict(role.limits), "tool_calls": role.tool_calls}


def build_condition(topology, live, *, cases, policies, single_limits, child_release, memory, human):
    """Derive one condition from the shared LiveConfig; nothing model-controlled."""
    if topology not in TOPOLOGIES:
        raise WorkflowError("Unknown topology")
    team = live_roles(live_members(live), live)
    if topology == "single_agent":
        roles, root = {SINGLE_AGENT: single_agent_role(team, single_limits)}, SINGLE_AGENT
    else:
        roles, root = team, MULTI_ROOT
    tools = sorted({t for r in roles.values() for t in r.tools})
    classes = tool_classes(tools)
    task_tools = sorted(t for t in tools if classes[t] != "coordination")
    record = {
        "protocol": PROTOCOL, "topology": topology, "root_agent": root,
        "model": {"provider": live.provider, "model": live.model, "max_output_tokens": live.max_output_tokens,
                  "thinking": "disabled", "endpoint": DeepSeekHTTP.endpoint, "socket_timeout": live.socket_timeout},
        "roles": {agent: _role_record(role) for agent, role in roles.items()},
        "capabilities": {"tools": task_tools, "classes": sorted({classes[t] for t in task_tools}),
                         "coordination_tools": sorted(t for t in tools if classes[t] == "coordination"),
                         "backends": {"web": live.enable_web, "python_image": live.python_image,
                                      "docker_endpoint_sha256": digest(live.docker_host) if live.docker_host else None,
                                      "repositories_sha256": digest([asdict(r) for r in live.repositories]) if live.repositories else None,
                                      "delete": live.enable_delete}},
        "budget": {"aggregate": asdict(live.tree_limits),
                   "effective": effective_ceilings(topology, roles, root, live.tree_limits),
                   "repeated_outcomes": sorted({r.limits.repeated_outcomes for r in roles.values()})},
        "tasks": [case_record(case, policies[case.id]) for case in cases],
        "constraints": list(live.constraints),
        "memory": dict(memory), "human": dict(human),
        "child_release": child_release if topology == "multi_agent" else "not_applicable",
        "child_retries": live.child_retries if topology == "multi_agent" else 0,
    }
    return Condition(topology, root, roles, json.loads(json.dumps(record)))


def _error(errors, dimension, code, message, single=None, multi=None):
    errors.append({"dimension": dimension, "code": code, "message": message, "single_agent": single, "multi_agent": multi})


def validate_pair(single, multi):
    """Compare two condition records; return a report with blocking errors and confounds.

    Records may come from a freshly built plan or from a saved run, so every
    dimension is checked explicitly rather than trusting how they were built.
    """
    errors, confounds = [], []
    try:
        _validate(single, multi, errors, confounds)
    except (KeyError, TypeError, AttributeError, ValueError, WorkflowError) as error:
        _error(errors, "structure", "malformed_record", f"Condition record is incomplete or malformed: {error}")
    return {"protocol": PROTOCOL, "status": "invalid" if errors else "valid", "errors": errors,
            "confounds": confounds,
            "checked": ["structure", "topology", "model", "tasks", "budget", "tools", "memory", "human", "constraints"]}


def require_valid(report):
    if report["status"] != "valid":
        raise FairnessError(report)
    return report


def _validate(s, m, errors, confounds):
    if s["protocol"] != PROTOCOL or m["protocol"] != PROTOCOL:
        _error(errors, "structure", "protocol", "Both records must use protocol " + PROTOCOL, s["protocol"], m["protocol"])
    if s["topology"] != "single_agent" or m["topology"] != "multi_agent":
        _error(errors, "structure", "topology_order", "Pass the single-agent record first and the multi-agent record second",
               s["topology"], m["topology"])
        return
    # Topology shape: the only intended difference.
    srole = s["roles"]
    if len(srole) != 1 or s["root_agent"] not in srole:
        _error(errors, "topology", "single_not_single", "The single-agent condition must configure exactly one agent as its root",
               sorted(srole), None)
    else:
        only = srole[s["root_agent"]]
        if only["delegates"] or set(only["tools"]) & COORDINATION_TOOLS:
            _error(errors, "topology", "single_can_delegate",
                   "The single-agent control must not delegate or hand off; remove coordination tools/delegates",
                   sorted(set(only["tools"]) & COORDINATION_TOOLS), None)
    mroles = m["roles"]
    if len(mroles) < 2 or m["root_agent"] not in mroles or not mroles[m["root_agent"]]["delegates"]:
        _error(errors, "topology", "multi_not_team", "The multi-agent condition needs a root that can delegate to at least one other agent",
               None, sorted(mroles))
    # Model equivalence, including generation settings. No fallback can pass.
    for key in sorted(set(s["model"]) | set(m["model"])):
        if s["model"].get(key) != m["model"].get(key):
            _error(errors, "model", f"model_{key}_differs",
                   f"Model setting {key!r} differs; both topologies must use the identical provider, model and generation settings",
                   s["model"].get(key), m["model"].get(key))
    # Task, input and oracle equivalence.
    sid, mid = [t["id"] for t in s["tasks"]], [t["id"] for t in m["tasks"]]
    if sid != mid:
        _error(errors, "tasks", "case_sets_differ", "Both conditions must run the identical ordered case list; unmatched cases are never compared",
               sid, mid)
    mt = {t["id"]: t for t in m["tasks"]}
    for task in s["tasks"]:
        other = mt.get(task["id"])
        if other is None:
            continue
        if task["content_sha256"] != other["content_sha256"]:
            _error(errors, "tasks", "case_content_differs", f"Case {task['id']} goal, inputs, constraints or expectations differ",
                   task["content_sha256"], other["content_sha256"])
        if (task["acceptance_id"], task["acceptance_sha256"]) != (other["acceptance_id"], other["acceptance_sha256"]):
            _error(errors, "tasks", "acceptance_differs", f"Case {task['id']} uses different independent acceptance criteria",
                   task["acceptance_id"], other["acceptance_id"])
        for reason in sorted(set(task["ineligible"]) | set(other["ineligible"])):
            _error(errors, "tasks", "ineligible_case", f"Case {task['id']} is not a valid single/multi control: {reason}")
    # Budgets at the aggregate level, never per team member.
    if s["budget"]["aggregate"] != m["budget"]["aggregate"]:
        _error(errors, "budget", "aggregate_differs", "The shared task-tree budget must be identical", s["budget"]["aggregate"], m["budget"]["aggregate"])
    for key in _RESOURCES:
        a, b = s["budget"]["effective"][key], m["budget"]["effective"][key]
        if a != b:
            _error(errors, "budget", f"effective_{key}_differs",
                   f"Effective aggregate {key} ceiling differs ({a} single vs {b} multi); adjust the single-agent task limit "
                   f"or the team's per-task/tree limits so both conditions can use the same total", a, b)
    outcomes = set(s["budget"]["repeated_outcomes"]) | set(m["budget"]["repeated_outcomes"])
    if len(outcomes) != 1:
        _error(errors, "budget", "repeated_outcomes_differs", "Every task in both conditions must use the same repeated-outcome stop rule",
               s["budget"]["repeated_outcomes"], m["budget"]["repeated_outcomes"])
    # Capabilities at the condition level; coordination tools are topology-specific.
    for record in (s, m):
        tool_classes([*record["capabilities"]["tools"], *record["capabilities"]["coordination_tools"]])
        listed = {t for r in record["roles"].values() for t in r["tools"]}
        if listed != set(record["capabilities"]["tools"]) | set(record["capabilities"]["coordination_tools"]):
            _error(errors, "tools", "capability_summary_mismatch", f"{record['topology']} capability summary does not match its roles")
    stools, mtools = set(s["capabilities"]["tools"]), set(m["capabilities"]["tools"])
    if stools != mtools:
        classes = tool_classes(sorted(stools ^ mtools))
        detail = "; ".join(f"{t} ({classes[t]}) only in {'single_agent' if t in stools else 'multi_agent'}"
                           for t in sorted(stools ^ mtools))
        _error(errors, "tools", "task_tools_differ",
               "Task capabilities must be identical at the condition level: " + detail, sorted(stools - mtools), sorted(mtools - stools))
    if s["capabilities"]["backends"] != m["capabilities"]["backends"]:
        _error(errors, "tools", "backends_differ", "Web, execution, Git and deletion backends must be configured identically",
               s["capabilities"]["backends"], m["capabilities"]["backends"])
    if s["capabilities"]["coordination_tools"]:
        _error(errors, "tools", "single_coordination_tools", "The single agent must not receive coordination tools",
               s["capabilities"]["coordination_tools"], None)
    # Memory: explicit and identical initial conditions.
    if s["memory"] != m["memory"]:
        _error(errors, "memory", "memory_differs", "Initial memory conditions must be identical and explicit", s["memory"], m["memory"])
    for record in (s, m):
        if record["memory"].get("mode") not in MEMORY_POLICIES:
            _error(errors, "memory", "memory_unsupported",
                   "Only memory-disabled comparisons are implemented; memory-on trials belong to the frozen-memory protocol (C05)",
                   record["memory"].get("mode") if record is s else None, record["memory"].get("mode") if record is m else None)
        elif record["memory"] != MEMORY_POLICIES[record["memory"]["mode"]]:
            _error(errors, "memory", "memory_policy_altered", f"{record['topology']} memory block differs from the declared policy")
        if record["memory"].get("mode") == "disabled" and "memory" in set(tool_classes(record["capabilities"]["tools"]).values()):
            _error(errors, "memory", "memory_tools_present", f"{record['topology']} exposes memory tools although memory is disabled")
    # Human intervention: the scripted vs live difference is always explicit.
    if s["human"].get("responder") != m["human"].get("responder"):
        _error(errors, "human", "responder_type_differs",
               "Methodological difference: human responses are supplied differently (e.g. scripted vs live human); "
               "such runs are never compared", s["human"].get("responder"), m["human"].get("responder"))
    if s["human"] != m["human"]:
        _error(errors, "human", "human_policy_differs", "Initial instructions, clarification/approval policy and intervention eligibility must match",
               s["human"], m["human"])
    if s["constraints"] != m["constraints"]:
        _error(errors, "constraints", "constraints_differ", "Global task constraints must be identical", s["constraints"], m["constraints"])
    if errors:
        return
    _record_confounds(s, m, confounds)


# Recorded differences are either deliberate architecture or a cost the team
# topology cannot avoid. Accidental configuration asymmetries are never recorded
# here: _validate reports them as blocking errors instead.
CONFOUND_KINDS = ("intentional_architecture", "necessary_coordination_cost")


def _record_confounds(s, m, confounds):
    root = m["roles"][m["root_agent"]]
    solo = s["roles"][s["root_agent"]]

    def add(code, kind, description, single, multi):
        confounds.append({"code": code, "kind": kind, "description": description, "single_agent": single, "multi_agent": multi})

    architecture, coordination = CONFOUND_KINDS
    add("role_prompts", architecture, "Role instructions differ by topology; prompt digests are recorded, not equalized.",
        {s["root_agent"]: solo["instructions_sha256"]}, {a: r["instructions_sha256"] for a, r in m["roles"].items()})
    add("shared_runner_prompt", architecture, "Both conditions receive the identical runner system prompt, whose wording describes a "
        "multi-agent platform and delegation; it is not changed for either topology.",
        digest(_RUNNER_PROMPT), digest(_RUNNER_PROMPT))
    add("coordination_tools", coordination, "Only the team has delegation and snapshot hand-off tools; their calls and the model "
        "attempts spent on them come out of the same aggregate budget.", [], m["capabilities"]["coordination_tools"])
    add("task_tree", architecture, "The single agent works in exactly one task and transcript; each team member keeps a separate "
        "transcript.", {"tasks": 1}, {"max_tasks": m["budget"]["effective"]["tasks"], "depth": m["budget"]["aggregate"]["depth"]})
    add("file_ownership", architecture, "Files are task-local in both conditions. The single agent owns every file it creates; team "
        "members cannot read each other's files and exchange data only through explicitly offered snapshots.",
        "one task owns all files", "per-task files, snapshot hand-off")
    add("per_task_limits", architecture, "Equal aggregate ceilings; the team additionally divides them under per-task caps.",
        {a: {"limits": r["limits"], "tool_calls": r["tool_calls"]} for a, r in s["roles"].items()},
        {a: {"limits": r["limits"], "tool_calls": r["tool_calls"]} for a, r in m["roles"].items()})
    add("root_identity", architecture, "The root agent identity differs by construction.", s["root_agent"], m["root_agent"])
    add("child_release", coordination, "Delegated child proposals are released by this policy; the single agent has no intermediate "
        "releases. A structural hand-off check proves a snapshot was offered, not that its content is correct, and a child that "
        "has not offered one receives trusted feedback naming the missing hand-off.", None, m["child_release"])
    missing = sorted(set(solo["tools"]) - set(root["tools"]))
    if missing:
        add("root_repair_capability", architecture, "The team root lacks task tools that exist elsewhere in the team, so it cannot "
            "itself repair a root file after accepting it. This favours the single agent on post-hand-off repairs. It comes from "
            "the runtime role definitions and is recorded, not equalized.", sorted(solo["tools"]), {"root_lacks": missing})
    if m["child_retries"]:
        add("child_retries", architecture, "Bounded failed-child replacement is available only to the team (within the same "
            "aggregate budget).", 0, m["child_retries"])


def planned_slots(replicates, case_ids):
    """Counterbalanced order: each pair's first arm alternates by replicate and case index."""
    rows = []
    for rep in range(replicates):
        for index, case_id in enumerate(case_ids):
            arms = TOPOLOGIES if (rep + index) % 2 == 0 else tuple(reversed(TOPOLOGIES))
            for position, topology in enumerate(arms):
                rows.append({"slot": len(rows), "replicate": rep, "case_id": case_id, "topology": topology,
                             "pair_position": position})
    return rows


def single_limits_from(data):
    keys = {"model_attempts", "reported_tokens", "duration_seconds", "repeated_outcomes", "tool_calls"}
    if not isinstance(data, dict) or set(data) != keys:
        raise WorkflowError("single_agent.task_limits needs exactly " + ", ".join(sorted(keys)))
    Limits(**{k: data[k] for k in keys - {"tool_calls"}})
    if type(data["tool_calls"]) is not int or not 1 <= data["tool_calls"] <= 1000:
        raise WorkflowError("single_agent.task_limits.tool_calls must be an integer from 1 to 1000")
    return dict(data)


__all__ = ["CAPABILITY_CLASSES", "CONFOUND_KINDS", "COORDINATION_TOOLS", "Condition", "FairnessError", "HUMAN_POLICIES", "MEMORY_POLICIES",
           "ORDER", "PROTOCOL", "SINGLE_AGENT", "STRUCTURAL_HANDOFF", "TOPOLOGIES", "build_condition", "case_eligibility",
           "effective_ceilings", "planned_slots", "require_valid", "single_agent_role", "tool_classes", "validate_pair"]
