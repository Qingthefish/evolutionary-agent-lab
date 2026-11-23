# Instructor mid-test input adapter (C06)

**Current scope (November 22).** The original Software Task 1 replay reached
independent technical acceptance; its same-group Task 2 replay failed. Later
repair diagnostics are separate development evidence. Use the
[current results and limits](final-report.md#12-november-22-coordinator-catch-up)
for acceptance rather than treating the historical notes below as current state.

## Operating from the presentation Mac

The platform is a local Python application, started from Terminal; Codex is
the development assistant. Conversation state, files and the configured isolated
code runner live on that Mac. HKGAI performs model inference remotely, so the
live run needs a working network and the course credential. The credential is
not the model itself or a statement of account balance. Local request limits
bound an experiment; the teacher's quota and pricing remain unknown.

Before presentation day, freeze and rehearse one reviewed revision, environment,
configuration and cached execution image on the actual presenting machine.
Under the replacement instructor notice supplied November 23, the task link
arrives **three presentation slots before our turn** (before the session for
the first three teams). Preserve and inspect the supplied files, check their
runtime mapping, and **set up and run in that advance window**. Show the
results in the five-minute talk; the old live-start-at-talk-beginning rule is
superseded. Join the shared Zoom meeting and screen-share from this Mac.
The importer below supports the issued canonical mid-test ZIP; it does not
automatically accept an arbitrary link or an unverified final package.
See the [current requirements](requirements.md#current-presentation-and-submission-requirements).

The prepared command sequence is: initialize/post the task, perform the
zero-model-call preflight, then advance the run. Inspect status when it stops;
give the real answer or review decision when needed, continue within the same
allowance, and export the recorded results. Reopening state does not reset
requests or authorize replay of an uncertain attempt. Routine operation should
need the rehearsed Terminal commands and actual human decisions; live source
editing is not the planned presentation workflow. The owner prepares the slides
and speech separately. See the [live runbook](final-report.md#9-proposed-presentation-outline).

## Retained development observations

The reviewed S01 commands cover all three mid-test scenario policies. A real
software Task 1 trial stopped after two HKGAI requests on November 16. The first
completed group/task reads. The second failed completion parsing before any
tool effect. Its failed record is retained. The new diagnostic labels will
identify the failed structural check in a future reply. Complete outcomes had
not been verified at that date; the current report records later acceptance.

On November 19, two fresh software trials each stopped on the second reply
with `finish_reason=length` at the 1,024 output-token cap. Adding compact
action guidance did not complete the task. Four requests were reserved in
total, with both failed tasks retained. A local operator can select a larger
output ceiling with `--output-token-ceiling 2048|4096` after an explicit budget
authorization. The default ceiling is 1,024, and the configured plan value must
fit the selected ceiling. Existing task configurations cannot acquire the new
setting on resume.

A reply cut off at the ceiling is still discarded unread and runs no tool.
Without the optional finish protocol, consecutive cut-offs can recover through
smaller actions within the existing attempt, token and duration budgets; they
no longer terminate the task after two replies. The optional protocol still
forces completion after its configured cutoff streak (three by default).
The notice before the next request
names what filled the reply (the tool call and its argument size, reasoning or
text), and gives file-splitting advice only to roles that can write files. Only
sizes are recorded (the `output_limit_reached` event's `shape`), never text.
Each continuation is a new counted request, not execution of partial tool
arguments. Transport failures and unknown effects retain their separate stop
and reconciliation rules. These local limits are not instructor time limits.

The November 18 integration review checked the later interrupted-state recovery
command as well. It tightened file export against linked task directories,
added full runner transcripts to the local export and bound HTML permission in
the system prompt to the securities scenario's second root and its descendants.

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
`per_scenario_model_attempts` (2–160, up to 80 per task; the instructor package sets no call budget) and `max_output_tokens`
(1–1024 by default; up to 4096 with `--output-token-ceiling`). Inspect
this plan before initializing the run. The two roots' call caps add up to
the reviewed scenario budget. Shares above 24 requests scale the per-role and
tree tool-call caps in the same proportion. Agents may write a file longer than
one response in parts with `create_text` and then `append_text`. This path uses a 90-second socket timeout and
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

All three share coordination and file tools, the same limits and review by
the trusted human. In the software policy the lead retains coordination,
inspection and handoff tools and can execute the received integrated package
to verify it. File creation/updating stays with the specialist roles. The
original role prompts remain intact, and
agents still choose their tasks, criteria and delegation sequence. Pass `--docker-host` and
`--image` only for a policy with the Python sandbox; the newsroom commands
take neither and refuse them. `preflight` prints the policy and tool list
and makes no model request. Only `advance` sends provider requests or runs
tools. For the web policies, every command records retrieval with network
permitted, because the run's recorded tool configuration must not change
between commands; `preflight`, `review` and `reconcile` still dispatch no tool,
so they make no search or retrieval request.

The authorized budget is the request cap in the plan. Each root's
reported-token stop is a runaway guard currently set to 50,000 tokens per
request of its share: 4,000,000 for an 80-request root. This is not reserved
provider credit, a billing estimate or a teacher limit. Earlier retained plans
used different token guards and keep their original values. Output tokens have
a separate default ceiling of 1,024, with explicitly authorized selections up
to 4,096 as described above. `preflight` prints the actual thresholds. A root
that already started keeps its original configuration and refuses different
limits; old records can be inspected/exported without acquiring the new values.

For a **fresh run**, add `--show-execution-budget` consistently to `preflight`,
`advance`, `review` and `reconcile` to show each role the current remaining local
requests, tools, tokens and time. This adds no task recipe and changes no limit.
The selection is persisted; a restart that changes it is refused before another
model call. Existing runs remain on their recorded policy. These counts are not
the teacher's balance or a guarantee about charges.

An exit-zero sandbox run can still fail to export a declared output. The script
must actually write each requested output under its working directory. A missing
output now has the fixed `missing_output` diagnostic; raw Docker stderr is not
exposed, no artifact is fabricated and no rerun is automatic. Inspect the
retained execution and source before deciding on a corrected run.

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

### Completion protocol (proposed, opt-in; completion-protocol-v2)

`--show-execution-budget --finish-protocol` turns on a completion protocol for
every role. Task states do not change; each turn derives a phase from recorded
state and the shared budgets:

- **working** and **ready** (a subtask has offered files to its parent, or every
  subtask a parent delegated was accepted). Ready is advice in the completion
  contract only: every role tool stays available, because a parent may still
  have to write or integrate the final deliverable. Ready never means succeeded.
- **Finish window**: every open task's last `--finish-requests` (R, default 3)
  requests. While a task runs, each other open task in the tree (ancestors,
  siblings and their subtasks) holds what is left of its R requests, so nobody
  else can spend them;
  a subtask stops once only those holds remain. The window also starts when tool
  calls or the role's own request limit run low, and it is entered at once after
  three output-limit replies in a row or repeated identical outcomes (instead of
  stopping the task). The second cut-off in a row escalates the notice: one small
  call, the first part of a file. Once entered the window lasts at most R requests.
  (Live Securities Task 2, 2026-11-21: forcing after two cut-offs left the fund
  manager 19 requests it could not use to write its HTML deck in parts.)
- Inside the window the tool schema offers only the completion actions the
  gateway would accept: `submit_for_verification` (not when an unreplaced failed
  subtask makes review impossible) and `report_blocker`. With
  `tool_choice=required` every schema-valid reply is therefore a proposal for
  human review or an honest blocker. A batch that ends with one of them may still
  carry the role's other calls first (an `offer_artifact` / `accept_artifact`
  handoff, a last fix, a message); delegation and `ask_human` stay closed.
- `report_blocker` is the task's final failure evidence, so its summary must
  explain what is done, what is missing and why (at least 40 characters and six
  words; two CJK characters count as a word). Placeholder text such as
  "placeholder" or "TODO" is refused like any invalid argument and can be resent.
  In the 2026-11-21 live Securities run both forced window blockers said only
  "placeholder".
- An invalid completion (for example a summary over 2,000 characters) gets a
  specific error and can be corrected in the remaining window requests. A window
  used up without a valid completion ends the task as failed with "Finish window
  used without a valid submission or blocker report"; its files are kept.
- A proposal is reviewed by the human as before; its `completion_proposed` event
  records whether it was made in the window. A rejection with requests left
  beyond the window reopens every tool for a correction; a rejection inside the
  window leaves an honest resubmission or a blocker. No budget is enlarged.
- A new subtask needs `2R + --min-child-requests` (default 16) available
  requests: the caller's window, the subtask's window and its work.

What the window can and cannot guarantee under the existing hard limits (none is
enlarged):

- **Requests and tool calls**: guaranteed. Both are counted before use, so each
  other open task's unspent window (one tool call per window request) is held.
  A batch that would take held tool calls is refused with the number of free
  calls; it does not stop the task.
- **Duration**: not guaranteed. Time passes during requests and while the human
  reviews (the task duration includes human waiting by design). A deadline inside
  the window ends it early with the window label; a proposal still waiting for
  review when the deadline passes is failed by the next `advance`.
- **Reported tokens**: not guaranteed. Usage is known only after a reply; a reply
  that crosses the cap releases no tool, even a valid submission, and the cap can
  be reached before the window starts. In the 2026-11-21 live runs the largest
  tree used 1.41M of 2.4M tokens and every run ended on the request cap first.
- Provider failures inside the window count as window requests (the cap is
  strict); pauses for an operator or the requester spend no request. The window
  record is persisted, so it survives a restart, a review and a rejection.

The previous version (v1: `--parent-reserve`, `--submit-reserve`,
`--ready-fraction`, a two-tier Finish Mode and a final-batch rule) was replaced
after the 2026-11-21 live runs: Finish Mode removed a Newsroom chief editor's
file tools while it still had to write the final report, and in the final
requests it and a Software QA/lead spent every request on reads, packaging and
self-offers. Stored v1 policies are read with R = `parent_reserve`.

An operator `resend` after a provider failure consumes another request from the
same actual-request cap. Failed or response-less requests keep counting and
retain unknown usage. No local setting can refund a provider charge. Legacy
`provider_failures_refunded` records are preserved as history, but their credits
do not enlarge current limits or the remaining-budget view. There is no automatic
resend, even when a request allowance remains.

### Overlapping provider calls (proposed, opt-in)

`advance --parallel-model-calls 2` lets one controller step overlap the provider
requests of up to two independent ready tasks. The default (1) is unchanged.

- Each task turn has three stages: **prepare** (state checks, atomic request
  reservation and the persisted request snapshot, in one SQLite transaction),
  **call** (provider I/O only, on a worker thread with no database, file or tool
  access) and **apply** (response recording, tool validation and every tool
  effect, on the controller thread, in preparation order). Sequential `step()`
  runs the same three stages back to back.
- Only runnable tasks are prepared: a parent still waits for every open child,
  and a task that needs an artifact, a review or an answer is not runnable. A
  task has at most one reserved call. The shared request cap, finish-window
  holds and tool-call caps are checked against every earlier reservation.
- A pending review or requester answer pauses only its own task; independent
  ready tasks keep moving and the boundary is still reported in `needs`.
  Uncertain provider or tool states still stop the whole tree, and nothing is
  resent automatically, including after a crash with two calls in flight.
- Two calls can each push the reported-token total past its cap; a reply that
  crosses it releases no tool, as in sequential mode.
- `model_calls_overlapped` events record the overlapping tasks and the wait.

Where it helps: only when a parent delegates independent children in the same
batch. In the 2026-11-21 live records, provider calls were 28-54% of each task's
wall-clock time (review waits 4-12 minutes were the largest share). Replaying
recorded per-turn provider times, two workers would have saved 1.1-3.5 minutes
of provider time on the three Securities trees with research and risk delegated
together, and nothing on the Newsroom and Software trees, whose children ran in
a dependent chain. This is an estimate from stored timestamps, not a live
measurement; HKGAI's own concurrency limits are untested.

The offline benchmark (`python -m agent_lab.evaluation.parallel_benchmark`,
synthetic 0.15 s mock latency, five repeats) shows the same requests, tool
calls, tokens and final states in both modes, 1.49-1.59x faster wall time on
fan-out graphs (1.55-1.76x with a 1 s synthetic review delay), and 1.0x on a
dependent chain.

### Replacing a file with an accepted version (proposed)

`accept_artifact` takes an optional `replace_sha256`. Without it, an offered
version can only be accepted at a new path, and an existing path now gets a
clear refusal that names the options instead of the generic file error. With
it, the offered version replaces the existing file only if that file's current
SHA-256 matches (same check and atomic replace as `update_text`); the
`artifact_received` receipt records `replaced_sha256`, and the offer stays open
after any refusal.

Why: in both live Software tasks of 2026-11-22 the lead could not accept the
developer's fixed files over the existing paths and saw only "File request
rejected". It stored the fixes as `v2/` or `cli_dashboard_patch.py`, kept
shipping the old versions, and spent its remaining requests on workarounds; both
tasks ended failed although the fixed code existed and passed its tests. The
tool list changes, so a task started before this change cannot be resumed with
it (the runner configuration check refuses).

### Integration aids for any task (proposed)

The 2026-11-22 Software runs failed at the parent's integration step, not in
the children's work. These changes are task-agnostic:

- `list_files` (every role): the current files of your own task, with SHA-256
  and size, from the broker's write records. No directory walk.
- `accept_artifact` without `path` keeps the producer's path, so a received
  package keeps its layout. An explicit path still works.
- `delegate_task` says the child starts with no files; when the parent holds
  files, the result names how many and points to `delegate_with_inputs`.
- The software lead may run code (`run_python`) to check the integrated
  deliverable before submitting; it still cannot write source files.
- With the completion protocol, the first run of identical outcomes adds a
  notice asking the agent to change approach; only two more identical outcomes
  force the finish window (before: forced at the third).

Tool lists change, so tasks started before this change cannot be resumed with it.

### Review recovery and failed subtasks (proposed)

From the 2026-11-22 reruns across all three scenarios:

- A human rejection reopens a forced finish window and resets the repeat
  count, so the feedback can be acted on (`finish_mode_reopened`). If the
  budget is still low, the window is re-entered on the next request.
- An unreplaced failed subtask no longer blocks a proposal. The runner attaches
  it to the proposal (`unreplaced_failed_subtasks`, also shown in the review
  need); accepting that proposal with each explicit `--waive-failed-subtask`
  records `failed_subtask_waived` for exactly those reviewed subtasks. Without that, a parent
  still cannot succeed over a failed child.
- `retry_failed_task` without input files gets the same "child starts empty"
  note as `delegate_task`; running a script that does not exist names
  `list_files` and says only existing task files can run.
- The finish window also counts tokens: `available` is capped by the requests
  the shared token budget still affords at this task's latest request size
  (+15%), so a task reaches its window before tokens run out. Before, only
  request counts started it, and a Securities Task 2 tree spent its 4,000,000
  tokens with 11 requests left and every task still open.
- After a human rejection inside a finish window, file-fix tools (`create_text`,
  `update_text`, `append_text`, `offer_artifact`, `accept_artifact`,
  `run_python`) are offered too, still only before a completion call in the same
  batch. Normal windows offer completion actions only (re-reading tools stay
  hidden: live windows were spent re-reading when they were offered).
- `submit_for_verification` refuses a summary that is only placeholder words or
  contains "placeholder", "lorem ipsum" or "dummy" (live summaries: "x",
  "Placeholder").
- While a parent is open, each descendant leaves it an integration reserve of
  an eighth of the shared cap, at most `min_child` (10 of 80), beyond its finish
  window: a Securities Task 2 parent had been left 9 of 80 requests to build its
  deck after its subtasks finished.
- `advance` records a gap of more than 120 s since the tree's last event as
  `controller_idle` when nothing awaited a human, and deadlines exclude it. Human
  answer and review time still counts.

### Coordinator review corrections (November 22)

Receiving a snapshot and accepting a task are distinct. A failed direct child
may have offered useful output before failing. The parent can explicitly pass
`allow_failed_source: true` to `accept_artifact` to recover **only an already
offered** snapshot addressed to that parent. The receipt says `partial: true`
and `source_state: failed`; the child remains failed. Cancelled sources,
non-child sources, unoffered private files, wrong recipients, consumed offers
and stale replacement hashes stay refused. Independent validation remains
necessary; this is not a solution for a child that failed before offering files.

Accepting a parent proposal does **not** implicitly waive failed child work.
The reviewer must inspect the failure and explicitly repeat
`--waive-failed-subtask CHILD_ID` for every disclosed exception that the finished
deliverable actually covers. Missing, wrong, duplicate or stale waiver IDs
refuse acceptance without changing the review state. A new failure after the
proposal requires a new proposal. The child failures remain in the record and
budget failure rolls back the review/waiver transaction.

These are actual reviewer decisions, not choices to be auto-filled by a model.
An assistant's technical checks must not be labelled as a human decision.
The changed artifact schema requires fresh compatible tasks; do not upgrade an
ongoing teammate run underneath it or bypass the stored configuration guard.

Deadline accounting and evaluation timing also remain distinct. Provider pauses
and recorded controller-idle intervals can be excluded from **local deadline
enforcement**. Reported assignment-to-final wall time still includes those
intervals. Do not present deadline exclusion as faster real execution or an
instructor-approved timing adjustment.

### Stable prompt prefix (proposed, opt-in)

`advance --stable-prompt-prefix` sends the live execution budget (requests,
tool calls and seconds left, the completion contract and Finish Mode) as the
last message of each request instead of rewriting it into the first task
message. The default is unchanged.

- The model sees the same task context and the same budget view; only the
  budget's position moves. Only the current view is sent; earlier views are not
  kept in the conversation.
- The stored transcript stays append-only: each request repeats the previous
  one unchanged up to its old budget message. `runner_turns.request` still
  records exactly what was sent.
- The option is not part of the persisted run configuration. A resumed task
  switches layout cleanly in either direction (the first task message is then
  written without, or again with, the budget block).

Why: inference servers with prefix caching (for example vLLM's automatic prefix
caching) can skip recomputing a prompt prefix they have already processed. In
the 2026-11-21 live records the first task message changed on every request
(271 of 271 consecutive pairs), so only 11-25% of each prompt repeated the
previous one unchanged; with the budget moved out, 87-94% would have (replay
of the recorded requests). Provider latency in those records fits about 2.2 s
per request + 0.075 s per 1,000 prompt tokens + 3.8 s per 1,000 output tokens
(468 requests, R^2 0.85), so prompt processing was about a third of provider
time. Whether HKGAI caches prefixes is unknown, so the saving is unmeasured:
if it does not, this changes nothing but the message order. A short live check
(the same long prompt sent twice, then a run with the flag) is needed.
`python -m agent_lab.evaluation.prompt_prefix_benchmark` checks offline that
every request extends the previous one with the same requests, tool calls and
final states.

### Overlapping web fetches inside one reply (proposed, opt-in)

`advance --parallel-web-fetches N` (N = 2-4) lets up to N consecutive
`search_web`/`retrieve_text` calls in one model reply wait for their public
HTTPS responses at the same time. The default (1) is unchanged.

- Each call is validated and reserved in call order exactly as before (tool-call
  row, `tool_reserved` event, `reserved` retrieval record). Only the network
  fetch runs on a worker thread, with no database or file access. Parsing,
  artifact writes, retrieval records and tool results then settle in call order
  on the controller thread, so later calls in the same reply see the same files.
- Any other tool, or a non-web call between web calls, keeps strict serial
  execution. A tool-budget stop ends reservation; calls already reserved still
  complete first. An unexpected fetch crash leaves the unsettled calls
  `reserved` (reported as uncertain), and nothing is resent.
- Requests, tool calls, tokens and model-visible results are unchanged. Only
  event order differs: the group's `tool_reserved` events precede its results,
  and `retrieved_at` is taken when each response is processed, at most one fetch
  deadline (15 s) after it arrived. A `web_fetches_overlapped` event records
  the group and its wait. The option is not stored in the run configuration, so
  existing state directories resume unchanged.

Why: in the 2026-11-21 Securities and Newsroom records, research replies
usually held 2-4 web calls run one after another (48 of 49 and 63 of 70
retrieval replies in the two Securities runs), and web retrieval took 108-236 s
per research-heavy task tree. Replaying the recorded batch sizes and per-call
latencies through the real runner (`python -m
agent_lab.evaluation.web_fetch_benchmark --replay COPY.sqlite3`, synthetic
fetches) cuts that wait by 55-65%: 3.2-4.4 minutes per Securities run (two tasks) and
2.2 minutes for the Newsroom run, with identical tool records. This is a replay
estimate, not a live measurement; how the search endpoint and sites respond to
four concurrent requests is untested, so a short live check is needed before
relying on it.

### Recovering an interrupted command

If an `advance` or `review` process stops mid-request, for example from Ctrl-C,
a closed terminal or a crash, later `advance` calls report `calling`,
`processing`, `stopping` or `controller_reconciliation_or_busy` and make no
progress. Task 2 cannot be posted until Task 1 is terminal. First confirm that
no other `advance` or `review` process for this state is still running. Then
use `reconcile` with the same container options as `advance`:

```bash
python -m agent_lab.evaluation.official_live \
  --config runs/software-inputs/plan.json --state-dir runs/software-scenario --sequence 1 \
  reconcile --task TASK_ID --action abort --reason "Terminal closed during the request" \
  --confirm-stopped --docker-host "$DOCKER_SOCKET_URL" --image "$PINNED_PYTHON_IMAGE"
```

| Reported state | Action | Effect |
| --- | --- | --- |
| `calling` (no response stored) | `abort` | The task ends failed. The request is never re-sent, and its usage stays unknown. |
| `processing` (response stored, tools interrupted) | `recover-tools` | Already committed tool results are rebuilt. Unstarted calls are marked not executed, and the task can continue. |
| `processing` with a tool whose effect is unknown | `abort` | `recover-tools` refuses. Inspect the files first; the reserved tool stays recorded. |
| `stopping` | `abort` | Finishes the interrupted stop. |
| `controller_reconciliation_or_busy` only | `release-claim` | Clears the stale claim; the task is unchanged. |
| `provider_uncertain` (transport failure or HTTP 5xx) | `resend` or `abort` | Nothing is retried automatically. `resend` releases one new counted request with the same transcript; `abort` ends the task failed. Time paused for this decision does not count toward task or tree deadlines. |

Each action is recorded as an `official_reconciliation_recorded` event with the
operator's reason, and it sends no model request. An aborted Task 1 is a
failed attempt: record it and post Task 2 to the same group, as above.

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
