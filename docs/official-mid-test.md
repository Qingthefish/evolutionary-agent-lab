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
operator choice. Model, budget, tool policy and unresolved protocol choices are
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

C06 prepares inputs/configuration; it supplies no live driver, automatic grading
or official score. The development `Evaluator` resets state per case and
`DevelopmentPlan` rejects held-out inputs; these defaults are unchanged. S01 must
consume the scenario contract with the existing workflow/scheduler/tool APIs,
retain Task 1 context for Task 2 and real human decisions, and collect dialogue,
outputs, observed models, total time, human waits and usage. Failed, blocked and
unrun tasks must stay in the approved metrics' denominator.

The following need review rather than invented defaults:

- **Output format:** scenario 3 Task 2 asks for HTML slides, while the earlier
  announcement limits documents to MD/TXT. The exact prompt and a format-conflict
  blocker are retained; no rewritten task or widened runtime file policy is supplied.
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
