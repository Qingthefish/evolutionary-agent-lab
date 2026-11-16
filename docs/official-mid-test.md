# Instructor mid-test input adapter (C06)

Download the instructor's November 15, 2026 [Mid_Test.zip from Canvas](https://canvas.ust.hk/courses/73253/modules/items/1916529).
Keep the archive, generated manifest and prepared prompts in the ignored
`runs/` directory. The adapter records the SHA-256 of the archive and each
of the ten Markdown documents. Apple metadata is excluded from prompt parsing.

## Source contract

| Scenario | Original agent IDs | Ordered tasks |
| --- | --- | --- |
| Software development | `lead`, `dev`, `qa`, `release` | Meeting-room booking system; extend it with a usage dashboard |
| Newsroom | `chief_editor`, `reporter`, `fact_checker`, `editor` | HKUST campus AI news; investigate AI-writing detector reliability |
| Securities fund | `fund_manager`, `research`, `risk`, `marketing` | Simulated investment proposal; semiconductor outlook in HTML slides |

Create one group per scenario with its four original roles and the real human.
Post Task 1, then Task 2 to the **same group**, continuing its collaboration
context. Do not flatten these into six fresh independent development cases or
rename the roles to the platform's default coordinator/writer/editor team.
The agents choose decomposition, workflow, technical approach and tests, and
discuss completion criteria with the requester. No gold answers, quantitative
rubric or scripted human responses are supplied. Complete dialogue and actual
task outputs must be retained for later review.

Source prompts are benchmark inputs. Their text does not authorize this coding
assistant to perform those tasks, grant runtime tools, send model requests,
approve actions, or change the course's provider restriction. The source
README's suggestion of external model-assisted review is preserved as text;
this adapter makes no grading-model calls.

## Inspect and prepare

Run from the repository root with the supported Python environment. Put the
original `Mid_Test.zip` in `runs/official-mid-inputs/` after creating the directory:

```bash
mkdir -m 700 -p runs/official-mid-inputs
```

```bash
cp evaluation/official/mid-test/plan.json runs/official-mid-inputs/plan.json
python -m agent_lab.evaluation.official import \
  --archive runs/official-mid-inputs/Mid_Test.zip \
  --output runs/official-mid-inputs/manifest.json
python -m agent_lab.evaluation.official inspect --config runs/official-mid-inputs/plan.json
```

Inspection compares the ZIP with the locally generated manifest and prints the
plan fingerprint, scenario and task counts, continuation protocol and outstanding
choices. It runs offline. The fingerprint covers source bytes, parsed prompts,
adapter code and operator configuration.

Copy the inspected `plan_sha256` into the preparation command:

```bash
python -m agent_lab.evaluation.official prepare \
  --config runs/official-mid-inputs/plan.json \
  --plan-sha256 REVIEWED_SHA256 --output runs/official-mid-preparation
```

Use a new directory for each preparation. It saves:

- `official-plan.json`: original prompts/source hashes, operator configuration,
  adapter identity, inspection and fingerprint.
- `<scenario>/scenario.json`: the original roles/tasks and same-group continuation
  contract for the S01 driver.
- `run-progress.json`: all six expected tasks marked `not_run`, with empty
  dialogue/output/outcome/time/usage fields. Unknown observations are null;
  preparation supplies no success, zero execution time or completion score.

The [plan template](../evaluation/official/mid-test/plan.json) names HKGAI as an
operator choice and records the HTML format decision for scenario 3 Task 2.
Model, budget, tool policy and the other protocol choices are
null. Configure/review them before S01 execution. Proposed choices are not
instructor rules and do not enable execution. Credentials stay outside the
repository; only a variable name is configured.

The manifest destination's parent must exist. Existing files are refused. The importer
extracts no paths and executes no text. It rejects missing/unexpected documents,
duplicate/unsafe paths, symlinks, malformed role/task structures, invalid UTF-8,
unsupported/encrypted ZIP entries and excessive sizes. The manifest records each
meaningful member's original name, byte count and SHA-256, plus ignored metadata.
This is a versioned adapter for this issued package; changed README protocol
requires adapter review rather than silently inheriting its fixed interpretation.

## S01 handoff and unresolved rules

C06 prepares inputs and configuration. S01 now opens a persistent group with
the four original role IDs, posts each exact task prompt as both a message and
a root task, and keeps the same group across process restarts. Task 2 can be
posted after Task 1 reaches a terminal state. A repeated post returns the
existing root for the same assignee. An operator can provide a reviewed Task 1
artifact to pending Task 2 by specifying its source task, path and SHA-256.
The status report distinguishes that transfer from a later read of the same
bytes by the second root.

To rehearse setup with the original local inputs, use a fresh ignored state
directory and the fingerprint from C06 inspection:

```bash
python -m agent_lab.evaluation.official_session \
  --config runs/official-mid-inputs/plan.json --state-dir runs/software-scenario \
  init --scenario software-engineering --human requester --plan-sha256 REVIEWED_SHA256
python -m agent_lab.evaluation.official_session \
  --config runs/official-mid-inputs/plan.json --state-dir runs/software-scenario \
  post --sequence 1 --assignee lead
python -m agent_lab.evaluation.official_session \
  --config runs/official-mid-inputs/plan.json --state-dir runs/software-scenario status
```

These commands leave Task 1 pending. Task 2 uses `post --sequence 2 --assignee ROLE`
under the same state directory after Task 1 finishes. Use
`carry --source-task TASK_ID --source-path PATH --sha256 SHA256 --target-path PATH`
before starting Task 2 if it needs an earlier artifact. Keep the status output
local because it contains conversation text. Use `--help` for options.

### HKGAI software rehearsal

For the software scenario, copy the operator plan into a fresh local input
directory alongside its archive and manifest. Set the issued HKGAI model,
`tool_policy` to `software-files-coordination-python-v1`, and set the authorized
`per_scenario_model_attempts` (2–48) and `max_output_tokens` (1–1024). Inspect
this plan before initializing the run. The two roots' call caps add up to
the reviewed scenario budget. This path uses a 90-second socket timeout and
requires the [existing isolated Python backend](sandbox.md).

After posting Task 1, load the key through the plan's environment variable and
run the local preflight. Replace the socket and digest with the verified ones:

```bash
python -m agent_lab.evaluation.official_live \
  --config runs/software-inputs/plan.json --state-dir runs/software-scenario --sequence 1 \
  preflight --docker-host "$DOCKER_SOCKET_URL" --image "$PINNED_PYTHON_IMAGE"
```

Replace `preflight` with `advance` to run one provider turn in the same state.
Use `--turns` for up to eight turns per command. The runtime stops at pending
clarifications or independent proposals for review. The operator can use
`answer --request ID --text TEXT` for an actual clarification answer or
`review --task ID --decision accept|reject --feedback TEXT` with the same
backend options after inspecting a proposal. Record specific checked evidence
in the feedback. Post Task 2 to the same group after Task 1 reaches a terminal
state and carry forward reviewed inputs before advancing the second root.

### Tool policies for the three scenarios

Each scenario has its own reviewed tool policy. Set `tool_policy` in that
scenario's plan to the matching identifier; a different value is refused.

| Scenario | `tool_policy` | Web search and retrieval | Python sandbox |
| --- | --- | --- | --- |
| `software-engineering` | `software-files-coordination-python-v1` | no | yes |
| `newsroom` | `newsroom-files-coordination-web-v1` | yes | no |
| `securities-fund` | `securities-files-coordination-web-python-v1` | yes | yes |

All three share the coordination and file tools, the same limits and review by
the trusted human. The software policy is unchanged. Pass `--docker-host` and
`--image` only for a policy with the Python sandbox; the newsroom commands
take neither and refuse them. `preflight` prints the policy and tool list,
makes no model request and keeps network access off. Only `advance` enables the
provider and, for the web policies, public search and retrieval.

Prepare **one plan copy per scenario run** in its own ignored `runs/...` input
directory, beside the archive and manifest, with the model, `tool_policy`,
budget and operator decisions set. Changing any plan value changes
`plan_sha256`, and a state directory only opens with the plan it was
initialized from. Do not edit the plan used by an existing state directory,
including the retained 2026-11-16 software run.

### Order, failure and continuity

- When Task 1 reaches any terminal state (succeeded, failed or cancelled),
  record its outcome, then post Task 2 to the same group. A failed Task 1
  never silently omits Task 2.
- The two roots have separate call allocations, so a failed Task 1 does not
  spend Task 2's share.
- `carry` works from a closed Task 1 tree, including a failed one, and only
  with the exact reviewed SHA-256 of the file.
- Whether a whole scenario may be repeated is the `repeat_policy` operator
  decision. Every attempt is preserved and reported, including failed ones.
- Known limitation: an agent's `read_messages` call returns at most the 20
  most recent group messages, each cut to 2,048 characters. Older Task 1
  dialogue is not reachable that way during Task 2. The full conversation is
  still retained in the state directory and the evidence export.

### Evidence export

After a scenario, or at any point during it, export its record for review into
a new directory outside the state directory:

```bash
python -m agent_lab.evaluation.official_export \
  --config runs/software-inputs/plan.json --state-dir runs/software-scenario \
  --output runs/software-export
```

The exporter opens the database read-only, works on a temporary copy and never
writes inside the state directory. It refuses an existing output directory. The
export holds the plan fingerprint, original roles and prompts, both task
statuses (including `not_posted`), the group conversation as JSON and Markdown,
human questions, answers and review decisions, the task tree with stop reasons
and timing, per-turn usage (unknown stays unknown), tool, retrieval and sandbox
records, provider failure diagnostics, the task files with SHA-256, the recorded
configuration and code identity. `manifest.json` lists every file with its
hash. `evidence_class` marks a scripted offline run as synthetic so it cannot
be mistaken for live evidence. Keep exports local: they contain conversation
text.

Official scoring still requires dialogue, outputs, observed models, total time,
human waits and usage. Failed, blocked and unrun tasks must stay in the approved
metrics' denominator.

The following need review rather than invented defaults:

- **Output format:** documents are Markdown or plain text by convention. Scenario 3
  Task 2 is the one exception: its prompt explicitly asks for HTML slides that open
  and present slide by slide in a browser, so the team delivers HTML task files for
  that task only. The plan template records this decision, the exact prompt is
  unchanged, and no tool, file permission or acceptance check was widened. The
  agents choose the presentation design. A plan whose `html_format_conflict` is
  null still reports the format blocker on that task. Single-file delivery,
  offline operation and a second-browser check are optional reviewer
  observations, not acceptance criteria.
- **Acceptance/scoring:** criteria are negotiated; no scoring rubric is supplied.
  File existence or an agent's claim of success is insufficient. Trusted review
  and its evidence must be recorded.
- **Memory/repeats:** same-group collaboration context within a scenario is
  required. Additional memory resets, cross-scenario reuse and repeats are unspecified.
- **Timing/access:** waiting-time treatment, quotas, call budgets, tool grants and
  the final due date are not fixed by this package. Preserve both total time and
  human wait for the later approved calculation.

Protocol gaps do not remove tasks from the manifest. This package is the mid-test,
not an invented final held-out dataset.

### Software scenario rehearsal

- Verify that both roots have the same conversation ID and same four assigned
  roles. Preserve the actual human questions and decisions, and record the
  outcome of Task 1 before posting Task 2.
- For Task 1, apply independently checked booking, cancellation and availability
  cases to the team's actual deliverable. Save the version of the booking records
  used by Task 2.
- For Task 2, compare the dashboard's counts and times to independently
  calculated results for a selected date range from those records. Confirm that
  changing the date range changes the results as expected.
- Retain both task outcomes, artifacts, dialogue, total elapsed time and human
  waiting time. Record any failed or blocked checks against the delivered work.

These proposed checks guide the rehearsal. The requester and the team still
agree the actual completion criteria in the conversation.
