# Examine memory ON/OFF effects

This read-only analysis supports [R04, R13 and R17](requirements.md). It uses the
existing frozen-experience protocol and comparator, then reports each matched
case/replicate. It does not run a model or change retrieval, prompts, task limits,
training content, seeds or original results. It does not close C05 or establish a
learning gain.

## Run the offline example

From the repository root, use Python 3.12 or newer:

```bash
python -m agent_lab.evaluation experience demo --output runs/memory-effect-demo
python -m agent_lab.evaluation.experience_effect --run runs/memory-effect-demo/RUN_ID
python -m agent_lab.evaluation.experience_effect --run runs/memory-effect-demo/RUN_ID --format markdown
```

Replace `RUN_ID` with the directory ID printed by the first command. Analysis is
also available as `analyze_experience(report)` for an in-memory saved report.
The reader accepts a regular UTF-8 `experiment.json` of at most 16 MiB, rejects
ambiguous/non-finite JSON and symlinks/FIFOs, and prints to stdout. Redirect output
to a separate file to preserve the original experiment.

The example uses scripts that know the answers. Four ON/OFF probe pairs are
counterbalanced across two replicates. Both arms succeed; each ON probe makes
two additional scripted attempts for search and selection. The report remains
`engineering_only` with no established learning improvement. These counts are
fixture reservations, not actual provider requests or model performance.

## Read the result

| Field | Interpretation |
| --- | --- |
| `outcomes` | Planned pairs split into ON-only success, OFF-only success, both succeeded and neither succeeded. Failed goals stay in the denominator. |
| `pairs` | Each case is matched by replicate and ID, independent of which arm ran first. |
| `on_minus_off.reserved_model_attempts` | Positive means ON reserved more requests. This is not monetary cost. |
| `on_minus_off.successful_goal_final_seconds` | ON minus OFF assignment-to-final duration, only when both independently verified goals succeeded. Otherwise unavailable. Failed and unfinished timings remain in the arm/aggregate records. |
| `on_minus_off.reported_tokens` | ON minus OFF provider-reported tokens; unavailable if either arm has unknown usage. Known partial totals and unknown-attempt counts remain visible. |
| `retrieved_candidate_records` | Returned candidate rows persisted by memory search. One search may return several; this is not a search-call count. |
| `selected_lesson_task_pairs` / `assessed_lesson_task_pairs` | Recorded selection and later outcome assessment. Neither proves that a lesson caused the result. |
| `comparison.training` | Training success/failure, time and usage stay separate from probe results. |

Diagnostics distinguish no retrieved candidates, retrieval without selection,
unassessed selections, selected experience followed by root failure, success
without a selection, additional ON attempts and slower successful ON probes.
These observations locate follow-up work; they do not automatically condemn or
promote a particular lesson.

The existing comparator now also rejects changed or omitted supplied inputs,
missing usage counters, duplicated selected-use records and a selected use whose
owner/assignee disagrees with the actual task. Missing or incompatible evidence
returns `not_comparable` (CLI exit 2) without an effect table. Valid scripted or
descriptive live evidence exits 0, even when ON loses. Previously saved headline
summaries are recomputed, not trusted.

Trial execution also stops before another arm or replicate when the current slot
has unknown provider usage, a driver failure or a human/unfinished boundary. The
`stop` record identifies the slot and a fixed reason; remaining slots stay
`not_run`. A known terminal task failure with complete usage is retained and can
still be followed by the planned comparison. This prevents an ON transport error
or clarification from silently triggering OFF or a later replicate.

Setup, frozen-seed snapshot or accounting failures outside a slot's normal
result path also stop the entire trial. Their `stop` record names the
replicate with `reason=replicate_driver_failure`; original completed/partial
rows and the `replicate_errors` record are retained. No later replicate is
started to work around that failure.

## Prepare a real trial

The checked-in JSONL repair plan is an existing three-root development experiment:

```bash
python -m agent_lab.evaluation experience plan --config evaluation/required-actions-experience-plan.json
```

It plans one common training root and one probe root per arm, each with at most
16 shared model attempts: **48 requests total**, at most **1024 output tokens per
request** and a **90-second socket timeout**. Training and probes use fresh task
files; probes share the same frozen training memory and cannot teach each other.
Current inputs, code and policy are included in the inspected fingerprint.

Actual execution needs a reviewed ignored local runtime copy with the allowed
HKGAI model/key environment variable and an already verified digest-pinned,
no-network [Python sandbox](sandbox.md). It also needs an explicit current trial
budget. Static inspection does not provision these or authorize calls. Use the
current plan fingerprint when executing under that authorization. Preserve every
failed, interrupted and unrun task. Stop on authentication, transport or unknown
effects; do not automatically spend the remainder on a replacement round. Actual
human clarification/review remains a human boundary.

After an authorized run, use the same analysis command on its retained directory.
Interpret multiple matched development cases and any allowed repeats together;
one favorable pair is not general improvement. Official inputs, memory/reset and
repeat rules remain separate from development experiments.

### Retained development attempt, 2026-11-16

The existing JSONL plan was attempted on source commit
`679c145c01404bc249ee0f4f38f8aa7c99ad9a1c` under a fresh authorized allowance of
48 requests across three roots. A dedicated Linux Docker VM and the actual
digest-pinned Python sandbox had passed validation first: all 670 discovered
tests passed with Docker and the optional Textual dependency configured, with
zero skips. These are engineering checks, not model task results.

Run `20261116-191157-19d03a` reserved and started **one actual HKGAI request** in
training. Its retained `provider_request_failed` event reports `kind=timeout`,
`phase=opening`, about 91.45 seconds, no HTTP status/response byte count, and
`request_may_have_been_processed=true`. The requested model was
`t2_hkgai-v3_fp8_1m_e7`; no returned model identity or token usage was observed.
The known-token counter is zero with **one unknown-usage attempt**, not evidence
of zero cost or zero provider processing.

Training ended failed; both planned probe slots remain `not_run`. The trial
stopped at slot 0 with `unknown_provider_usage`, without retrying or spending the
remaining allowance on replacement tasks. Analysis is `not_comparable`; there
is no ON/OFF effect estimate, learning gain, or C05 acceptance claim. Original
SQLite, experiment/configuration JSON and the request ledger are retained in the
ignored local run directory. This is an interface-stage failure; it supplies no
evidence about the memory algorithm's effectiveness. No response was available
to diagnose the remote cause. Any later model attempt needs reconciliation and
authorization rather than automatic reissue.

## Limits

This checks recorded consistency and describes associations. It does not
authenticate the SQLite database, artifacts, lesson application or provider
responses. Output excludes raw tasks, inputs, lessons, transcripts and exception
messages. `model_calls: 0` describes this reader only. `benchmark_valid`,
`authenticity_verified` and `learning_improvement_established` stay `false`.
