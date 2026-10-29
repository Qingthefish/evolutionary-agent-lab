"""Versioned model views for declared development tasks; never acceptance evidence.

Original sandbox records and own-role instructions remain intact. Legacy tasks
retain their existing views. Private experience tools are not peer capabilities.
"""

CONTEXT_POLICY = "declared-concise-actions-v2"
ACTION_GUIDANCE = """
On action turns use tool_calls and null content. Spend the output budget on the
actual tool arguments, not narrated plans or repeated evidence. Keep source writes
small enough for one response. When the deliverable and handoff are ready, place
submit_for_verification last in the batch; only independent checks decide success.
Do not poll for a parent's response before submitting your completed child work.
For quantitative results rely on actual sandbox output and independent checks,
not repeated manual counting of escaped file strings. Investigate contradictions
with source/execution evidence. File writes, offers and recorded lessons alone do
not submit completion: include the verification proposal after the final actions.
"""


def peer_description(role):
    """Describe a specialist without copying its full private operating context."""
    purpose = role.instructions.split(". ", 1)[0].strip()[:240]
    tools = sorted(set(role.tools) - {"search_memory", "select_memory", "record_lesson"})
    return (f"Purpose: {purpose}. Tool names: {', '.join(tools)}. "
            "Capabilities remain subject to task ownership, scope and human approval.")


def execution_view(result):
    """Keep all outcome/repair/import evidence, omit repeated runtime identity only.

    This is a fresh shallow projection: the executor's full record is not mutated.
    In particular stdout/stderr, hashes, errors and partial receipts are untouched.
    """
    omitted = [key for key in ("configuration", "engine", "identity") if key in result]
    return {key: value for key, value in result.items() if key not in omitted} | {
        "evidence_record": {"kind": "sandbox_runs", "run_id": result["run_id"],
                            "omitted_runtime_fields": omitted}}
