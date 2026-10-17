# Team roadmap and task register

Updated: 2026-10-18 (Asia/Hong_Kong). **Discuss in WeChat; record task claims, progress and acceptance here.** This is the single task register. No coding tasks have been assigned by this document. The instructor's [requirements](requirements.md) remain the scope authority.

**How to read progress:** Use the accepted baseline and milestone exit evidence, not a ratio of Done cards to all cards. I01–I03 record the review/integration of PRs #7–#9; substantial earlier work in #1–#6 is recorded separately in [Accepted baseline](#accepted-baseline). The card index covers that integration and the remaining delivery work, rather than every historical task. Cards differ in size and may be split as evidence reveals more work. Three Done cards therefore do **not** mean the project is only one ninth complete; no overall percentage is established.

## Start here

1. Read the finish line and milestones below, then pick an **Unclaimed** card whose prerequisites can be met. Prefixes A/B/C/D identify technical areas, not people or permanent assignments.
2. Say in the WeChat group: `I would like to claim <ID>; scope <files/result>; dependencies <...>`. Confirm that no active card overlaps the same files or interface.
3. Qingthefish coordinates claims and updates **this file on main** with owner/status and the starting revision before development begins. A claim only on a local/feature branch is not yet visible to everyone. Refresh main and check the card before starting Codex.
4. Work on a focused branch. Reference the card ID in the PR; report changes, checks, skipped checks, blockers and review fixes there and in WeChat. The coordinator updates this card's concise progress/review record. Developers do not independently edit the register in every feature PR.
5. Qingthefish coordinates final acceptance/merging, with Codex-assisted checks and teammate review where useful. Mark **Done** only after the agreed acceptance has evidence and the implementation is merged. An unknown owner remains `—`; do not infer ownership from an agent name or this conversation.

Roadmap updates can be small documentation commits/PRs. Keep one active editor for the register; keep the normal PR/code history for detailed evidence. A handoff preserves previous owners and contributions in the card record. For a newly discovered fix or oversized task, add/split a clearly scoped card and link its dependency rather than erasing a completed record.

**Status:** Unclaimed → Claimed → In progress → In review → Done. Use Blocked for a claimed task waiting on something concrete; state the blocker and next action. A pushed commit or an open PR is not Done. These labels are human coordination, not an automatic lock: the WeChat confirmation and main update prevent duplicate claims.

**Before closing a card**, fill its record with date, actual author, change summary, checks/results (including skips), reviewer/review corrections, remaining limits, PR and merged revision. Link raw evidence rather than copying full logs or private chat history. Never paste passwords/API keys, manufacture attribution, or present fixture success as a live-model score.

## Finish line and milestones

Deliver a runnable general multi-agent platform and an evaluation entry point: an allowed-model team autonomously decomposes/delegates tasks, interacts with humans, uses real search/files/code execution/Git, retains private agent memory/workspaces, checks outputs and reports completion/time. Submit the code/history, architecture, official results/report and presentation required by the announcement. This is engineering with empirical evaluation; it does not require an original research paper or guarantee success on unknown tasks.

| Gate | Exit evidence | Current position |
| --- | --- | --- |
| M0 — coordinate | Common baseline, visible claims and agreed boundaries | Register ready; future coding owners unclaimed |
| M1 — foundation integration | Existing platform plus #7/#8/#9 reviewed and integrated with honest evidence labels | Done; I01–I03 record that integration |
| M2 — first live slice | Issued model, live delegation, human interaction and independently checked output with model/time/usage evidence | Pending live access and integration cards |
| M3 — required coverage | Every R01–R13 capability has actual evidence or an explicit unresolved instructor dependency | Pending remaining tool, learning and interaction work |
| M4 — stabilize/evaluate | Reproducible setup, pinned configuration, development comparisons/failure analysis and official adapter | Pending prerequisites |
| M5 — official delivery | Issued test protocol/results and required submission materials | Await official set and actual deadlines |

These are gates, not claimed percentages. Independent cards can proceed in parallel; external model access need not block offline implementation. Draft the architecture/presentation during M3/M4. The announcement says presentation in week 13, report after week 13, and has conflicting “3 weeks” / “3/1 weeks” dataset wording: confirm exact dates and memory/intervention/repeat rules. Optional extensions and UI styling must not delay mandatory coverage.

Validate and improve the platform with independent development cases before the official set arrives. Release of that set begins the official evaluation phase, not the first round of testing. The required capabilities and submission components are known; the exact test tasks, issued model/quota and unresolved evaluation details are not. Meeting a roadmap gate requires actual evidence and does not guarantee a benchmark score or grade.

## Documents and directory boundaries

| Material | Purpose |
| --- | --- |
| [README](../README.md) | What exists and how to run it; link here for task status |
| [requirements](requirements.md) | Instructor requirements and unresolved official details |
| [direction](direction.md) | Design choices and their rationale |
| [architecture](architecture.md), [sandbox](sandbox.md) | Implemented contracts, limitations and setup |
| This Roadmap | Task owner/status, dependencies, acceptance and concise development/review records |
| [CONTRIBUTING](../CONTRIBUTING.md), [AGENTS](../AGENTS.md) | Human/Codex working instructions |

Keep source in `agent_lab/`, checks in `tests/`, development cases in `evaluation/dev/`, and generated evidence in ignored `runs/`. Do not create another progress log or copy the session transcript into the repository. Preserve existing run evidence and unrelated coursework.

## Accepted baseline

These merged contributions are starting material to reuse, not new tasks to reproduce. Authorship and changes remain traceable through each PR/commit; later maintenance does not transfer the original author's contribution.

| PR | Accepted contribution | Recorded contributor |
| --- | --- | --- |
| [#1](https://github.com/Qingthefish/evolutionary-agent-lab/pull/1) | Workflow, controlled files and candidate memory | Qingthefish, Codex-assisted |
| [#2](https://github.com/Qingthefish/evolutionary-agent-lab/pull/2) | DeepSeek protocol and tool gateway | Qingthefish, Codex-assisted |
| [#3](https://github.com/Qingthefish/evolutionary-agent-lab/pull/3) | Bounded single-task runner | Qingthefish, Codex-assisted |
| [#4](https://github.com/Qingthefish/evolutionary-agent-lab/pull/4) | Actual Python sandbox backend | Qingthefish, Codex-assisted |
| [#5](https://github.com/Qingthefish/evolutionary-agent-lab/pull/5) | Durable multi-agent scheduler/shared budgets | Qingthefish, Codex-assisted |
| [#6](https://github.com/Qingthefish/evolutionary-agent-lab/pull/6) | Actual delegated sandbox integration checks | Qingthefish, Codex-assisted |
| [#7](https://github.com/Qingthefish/evolutionary-agent-lab/pull/7) | Terminal controls and evidence views | HelloWorld2333666 |
| [#8](https://github.com/Qingthefish/evolutionary-agent-lab/pull/8) | Restricted Git/local remote validation | HelloWorld2333666 |
| [#9](https://github.com/Qingthefish/evolutionary-agent-lab/pull/9) | Development evaluation; review corrections recorded in I03 | HelloWorld2333666; corrections by Qingthefish, Codex-assisted |
| [#10](https://github.com/Qingthefish/evolutionary-agent-lab/pull/10) | Initial collaboration roadmap | Qingthefish, Codex-assisted |

The reviewed combined runtime passed 214 checks on 2026-10-17, including real Docker/UI checks. Its model responses were scripted: no live-model or official-test-set performance is established. #8 does not close real GitHub runtime pushing; #9 does not close live memory learning/comparison. Those remain explicit cards below.

## Card index

One accountable owner per claimed card; multiple people may review or help. Shared source files (`core.py`, `gateway.py`, `scheduler.py`, top-level CLI, shared runtime configuration, consolidated README/architecture) need one active editor at a time. Before claiming overlapping work, agree who makes the shared edit and record that boundary. Reuse the current backend; UI and evaluation should consume common runtime policies rather than implement another scheduler/scorer.

| ID | Deliverable |
| --- | --- |
| [I01](#i01) | Terminal control center |
| [I02](#i02) | Restricted Git foundation |
| [I03](#i03) | Development evaluation foundation |
| [I04](#i04) | Enable actual CI |
| [A01](#a01) | Validate the issued model connection |
| [A02](#a02) | Unify runtime configuration |
| [A03](#a03) | Demonstrate live autonomous delegation |
| [A04](#a04) | Verify delegated work and resume parents |
| [B01](#b01) | Add real internet search |
| [B02](#b02) | Retrieve and hand off cited text |
| [B03](#b03) | Connect a real GitHub push |
| [B04](#b04) | Validate remote failures and uncertainty |
| [C01](#c01) | Define independent development cases |
| [C02](#c02) | Close the experience-use loop |
| [C03](#c03) | Verify memory boundaries and reset rules |
| [C04](#c04) | Make evaluation results comparable |
| [C05](#c05) | Run controlled development comparisons |
| [D01](#d01) | Submit real tasks through the interface |
| [D02](#d02) | Exercise human interaction end to end |
| [D03](#d03) | Expose trustworthy execution evidence |
| [A05](#a05) | Run the combined tool workflow |
| [A06](#a06) | Check isolation and bounded recovery |
| [D04](#d04) | Verify clean-environment setup |
| [C06](#c06) | Prepare the official dataset adapter |
| [A07](#a07) | Freeze and verify a release candidate |
| [S01](#s01) | Run the official evaluation |
| [S02](#s02) | Finish submission materials |

## Task cards

`—` means not yet claimed/recorded. A card's fields below are the only owner/status record; the index above is navigation. Existing acceptance criteria are proposed implementation checks, not additional instructor requirements.

### I01

**Terminal control center**

- **Stage / status:** M1 / Done
- **Owner:** HelloWorld2333666
- **Dependencies / configuration:** Baseline #1–#6
- **Scope:** TUI, queries, inspection and UI/controller tests.
- **Acceptance:** Private/group routing, clarification, approval/release, restart and membership checks.
- **Base revision / branch / PR / evidence:** Base 545c2df; PR #7; 172 checks passed, 13 Docker checks skipped in its separate review.
- **Reviewer:** Qingthefish (Codex-assisted)
- **Progress / review changes / outcome:** Merged 2026-10-17 in 0ed9251. No live model result claimed.

### I02

**Restricted Git foundation**

- **Stage / status:** M1 / Done
- **Owner:** HelloWorld2333666
- **Dependencies / configuration:** I01
- **Scope:** git_tools.py, gateway/scheduler wiring and Git UI/tests.
- **Acceptance:** Allowlisted repository/branch/path operations, approval-bound local push, uncertainty handling and independent remote SHA checks.
- **Base revision / branch / PR / evidence:** Base 12e04ed; PR #8; 191 checks passed, 13 Docker checks skipped in its separate review.
- **Reviewer:** Qingthefish (Codex-assisted)
- **Progress / review changes / outcome:** Merged 2026-10-17 in 534920c. Only a local bare remote was verified; B03 remains open.

### I03

**Development evaluation foundation**

- **Stage / status:** M1 / Done
- **Owner:** HelloWorld2333666; review corrections by Qingthefish (Codex-assisted)
- **Dependencies / configuration:** I02
- **Scope:** evaluation/, development cases, evaluation UI and tests.
- **Acceptance:** Independent outcomes and time accounting; explicit offline/not-configured labels; inspection errors cannot prove absence; unexercised memory cannot count as a live comparison.
- **Base revision / branch / PR / evidence:** Base 6297786; PR #9; corrected combined stack passed all 214 checks, including 13 real Docker checks and optional Textual UI checks. Correction commit: 7cb53a4.
- **Reviewer:** Qingthefish (Codex-assisted)
- **Progress / review changes / outcome:** Merged 2026-10-17 in 3692159. Review corrected ambiguous absence checks and unimplemented memory-on labels; no model/API calls.

### I04

**Enable actual CI**

- **Stage / status:** M4 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** Owner can install a workflow with the necessary GitHub permission; development work does not wait for this.
- **Scope:** docs/ci-workflow.yml and a focused .github/workflows/ change; no runtime feature changes.
- **Acceptance:** Actual core/UI jobs expose their results and explicit skips; no CI success is claimed before a run exists.
- **Base revision / branch / PR / evidence:** —
- **Reviewer:** —
- **Progress / review changes / outcome:** —

### A01

**Validate the issued model connection**

- **Stage / status:** M2 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** Issued DeepSeek/HKGAI endpoint/model/key/quota and an authorized experiment budget.
- **Scope:** Existing provider/protocol adapter and its live smoke-check entry point.
- **Acceptance:** One real structured tool request/result cycle is recorded with model identity, attempts, usage, time and sanitized failure evidence; no fallback provider or credential in commits.
- **Base revision / branch / PR / evidence:** —
- **Reviewer:** —
- **Progress / review changes / outcome:** —

### A02

**Unify runtime configuration**

- **Stage / status:** M2 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** M1; agree callable/config shapes with anyone claiming related UI/evaluation work.
- **Scope:** A shared runtime configuration entry plus focused CLI/TUI/evaluation wiring; preserve current state and permission checks.
- **Acceptance:** UI and evaluation use the same role/tool/limit/acceptance policy and original constraints. Unsupported backends are explicitly disabled. Offline contract checks can proceed before A01.
- **Base revision / branch / PR / evidence:** —
- **Reviewer:** —
- **Progress / review changes / outcome:** —

### A03

**Demonstrate live autonomous delegation**

- **Stage / status:** M2 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** A01 and A02.
- **Scope:** Role instructions/capability configuration and delegation integration checks; retain scheduler budgets.
- **Acceptance:** A live high-level goal produces model-chosen decomposition, role negotiation and specialist-to-specialist delegation, with constraints and outcomes recorded. Fixed scripted role choices do not meet acceptance.
- **Base revision / branch / PR / evidence:** —
- **Reviewer:** —
- **Progress / review changes / outcome:** —

### A04

**Verify delegated work and resume parents**

- **Stage / status:** M2 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** A02 and C01; the final live check needs A01.
- **Scope:** Task acceptance policy and runner/scheduler integration; coordinate evaluation interfaces.
- **Acceptance:** Supported children have independent checks, unsupported proposals request explicit trusted review, and a parent resumes only with valid evidence. Failed checks return concrete feedback within budget.
- **Base revision / branch / PR / evidence:** —
- **Reviewer:** —
- **Progress / review changes / outcome:** —

### B01

**Add real internet search**

- **Stage / status:** M3 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** A02 tool contract; approved search access/configuration if needed.
- **Scope:** A retrieval backend and its tests; any gateway registration is a coordinated edit.
- **Acceptance:** A real query returns bounded results with source URLs and retrieval evidence. Unsupported/local targets, oversized responses, timeouts and failed requests are handled explicitly.
- **Base revision / branch / PR / evidence:** —
- **Reviewer:** —
- **Progress / review changes / outcome:** —

### B02

**Retrieve and hand off cited text**

- **Stage / status:** M3 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** B01.
- **Scope:** Retrieval result processing, bounded text artifacts and related tests.
- **Acceptance:** A specialist hands another task useful cited text through the existing artifact path. Source content remains reference data and cannot grant tool permissions or discard user constraints.
- **Base revision / branch / PR / evidence:** —
- **Reviewer:** —
- **Progress / review changes / outcome:** —

### B03

**Connect a real GitHub push**

- **Stage / status:** M3 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** I02; explicitly authorized test repository/branch and narrow runtime credential scope.
- **Scope:** Git credential provisioning and remote verification in git_tools.py; preserve existing approval/allowlist boundaries.
- **Acceptance:** The runtime commits and pushes to the authorized GitHub branch after applicable approval; an independent remote lookup confirms the expected commit SHA. Local bare-remote success alone is insufficient.
- **Base revision / branch / PR / evidence:** —
- **Reviewer:** —
- **Progress / review changes / outcome:** —

### B04

**Validate remote failures and uncertainty**

- **Stage / status:** M3 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** B03 and coordinated gateway wiring.
- **Scope:** Git/retrieval failure-path tests and only the fixes those checks justify.
- **Acceptance:** Changed bindings, denial, non-fast-forward, failed network and interrupted push do not receive false success. Uncertain effects are reconciled without blindly repeating a push.
- **Base revision / branch / PR / evidence:** —
- **Reviewer:** —
- **Progress / review changes / outcome:** —

### C01

**Define independent development cases**

- **Stage / status:** M2 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** I03.
- **Scope:** evaluation/cases.py, evaluation/dev/ and case/acceptance tests; coordinate shared harness edits.
- **Acceptance:** Small positive and negative cases have expectations written independently of candidate implementations. Cases cover goal/subtask outcomes and human intervention; acceptance criteria are available to A04 before live experiments.
- **Base revision / branch / PR / evidence:** —
- **Reviewer:** —
- **Progress / review changes / outcome:** —

### C02

**Close the experience-use loop**

- **Stage / status:** M3 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** A02 and existing per-agent memory APIs; final live use needs A01.
- **Scope:** memory.py and scoped runtime hooks; do not duplicate orchestration.
- **Acceptance:** Actual successes/failures produce condition/provenance-linked candidate experience that a later live task can retrieve and consider. Usage/outcomes are recorded; logging a lesson alone is not learning evidence.
- **Base revision / branch / PR / evidence:** —
- **Reviewer:** —
- **Progress / review changes / outcome:** —

### C03

**Verify memory boundaries and reset rules**

- **Stage / status:** M3 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** C02.
- **Scope:** Memory tests and narrowly justified fixes.
- **Acceptance:** Agents/conversations/namespaces remain separate; contradictory evidence and selected-use outcomes stay visible; fresh/reset memory works. An old lesson cannot authorize a new action.
- **Base revision / branch / PR / evidence:** —
- **Reviewer:** —
- **Progress / review changes / outcome:** —

### C04

**Make evaluation results comparable**

- **Stage / status:** M3 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** C01 and A02; agree memory metadata with C02.
- **Scope:** evaluation/harness.py, result manifests and reporting/tests.
- **Acceptance:** Report separate root/subtask completion and assignment-to-final time, failures and human waits; show expected/executed/blocked/not-configured counts. Record dataset content, model, prompts, tools, budgets, interventions and initial memory so incompatible runs are rejected.
- **Base revision / branch / PR / evidence:** —
- **Reviewer:** —
- **Progress / review changes / outcome:** —

### C05

**Run controlled development comparisons**

- **Stage / status:** M4 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** M3, C03, C04 and an authorized live-model budget.
- **Scope:** Versioned development run configurations, raw evidence and Markdown analysis; no held-out-data reuse.
- **Acceptance:** Run memory ON/OFF and single/multi-agent comparisons under matched conditions. Preserve failures, time and supplementary call/token cost; report actual gains/regressions. These comparison layouts are our evidence method, not an extra instructor rubric.
- **Base revision / branch / PR / evidence:** —
- **Reviewer:** —
- **Progress / review changes / outcome:** —

### D01

**Submit real tasks through the interface**

- **Stage / status:** M2 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** I01 and A02; final live check needs A01.
- **Scope:** tui/ controller/view integration using the common runtime API.
- **Acceptance:** A human submits a real goal and sees actual progress/blockers. An offline unconfigured task remains pending; the UI creates neither a second scheduler nor fake completion.
- **Base revision / branch / PR / evidence:** —
- **Reviewer:** —
- **Progress / review changes / outcome:** —

### D02

**Exercise human interaction end to end**

- **Stage / status:** M3 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** D01 and the relevant runtime/tool contracts.
- **Scope:** Minimal conversation, clarification and approval controls plus tests.
- **Acceptance:** Private/group messages, clarification and restart, approval versus release versus verified effect, denial and unresolved effects are usable and correctly distinguished.
- **Base revision / branch / PR / evidence:** —
- **Reviewer:** —
- **Progress / review changes / outcome:** —

### D03

**Expose trustworthy execution evidence**

- **Stage / status:** M3 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** D01 and C04 result contract.
- **Scope:** tui/, queries.py and inspection.py; coordinate any shared schema changes.
- **Acceptance:** Show actual task/tool/artifact/evaluation evidence, respect private boundaries and redact credentials. Display the evaluator's results without adding another scoring formula or expanding UI styling scope.
- **Base revision / branch / PR / evidence:** —
- **Reviewer:** —
- **Progress / review changes / outcome:** —

### A05

**Run the combined tool workflow**

- **Stage / status:** M3 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** A03, A04, B02, B03 and D02.
- **Scope:** A focused integration fixture/live run across existing retrieval, file, sandbox, Git and human-control APIs.
- **Acceptance:** A bounded live development task performs actual retrieval, code execution, checked handoff and authorized GitHub push. Failures/partial outcomes remain visible and all actual effects have evidence.
- **Base revision / branch / PR / evidence:** —
- **Reviewer:** —
- **Progress / review changes / outcome:** —

### A06

**Check isolation and bounded recovery**

- **Stage / status:** M3 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** A candidate covering the M3 capabilities.
- **Scope:** Task/role/tool isolation and recovery checks; create separate small repair cards for larger findings.
- **Acceptance:** Cross-agent access, path escapes, unsafe execution, exhausted budgets and unknown effects are rejected or reported correctly. Fixes follow observed failures rather than an unrelated redesign.
- **Base revision / branch / PR / evidence:** —
- **Reviewer:** —
- **Progress / review changes / outcome:** —

### D04

**Verify clean-environment setup**

- **Stage / status:** M4 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** M3.
- **Scope:** Installation/run instructions and one minimal reproducible demo; coordinate shared README edits.
- **Acceptance:** Another member can install and run from the guide, use the actual supported capabilities and identify missing configuration. Core use works without optional Textual dependencies; setup does not expose credentials.
- **Base revision / branch / PR / evidence:** —
- **Reviewer:** —
- **Progress / review changes / outcome:** —

### C06

**Prepare the official dataset adapter**

- **Stage / status:** M4 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** Stable evaluation contracts; final mapping awaits the instructor's dataset/protocol.
- **Scope:** Dataset adapter, manifests and official-run configuration; keep development and official inputs separate.
- **Acceptance:** When issued, every official task and intervention/memory/repeat rule maps to recorded evaluation inputs/outputs. Do not substitute our development cases or silently remove failures/unrun tasks.
- **Base revision / branch / PR / evidence:** —
- **Reviewer:** —
- **Progress / review changes / outcome:** —

### A07

**Freeze and verify a release candidate**

- **Stage / status:** M4 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** M3, D04 and versioned evaluation configuration.
- **Scope:** Release/config manifest and necessary integration/regression checks.
- **Acceptance:** Pin the revision/config, list known limitations and triage required fixes. No unsupported feature or unrun check is reported as completed.
- **Base revision / branch / PR / evidence:** —
- **Reviewer:** —
- **Progress / review changes / outcome:** —

### S01

**Run the official evaluation**

- **Stage / status:** M5 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** C06, A07, the official dataset and authorized runtime access.
- **Scope:** Official raw run records, complete result counts and metrics.
- **Acceptance:** Evaluate under the issued protocol, preserve full denominators/timing/failures and required memory history. Development results are not presented as official scores.
- **Base revision / branch / PR / evidence:** —
- **Reviewer:** —
- **Progress / review changes / outcome:** —

### S02

**Finish submission materials**

- **Stage / status:** M5 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** Draft during M3/M4; finalize results when available and meet actual course dates.
- **Scope:** Final architecture, performance/failure/memory analysis, presentation outline and authentic contribution evidence.
- **Acceptance:** Cover routing, memory/evolution and isolation; include official results and genuine ongoing commit-history evidence. Prepare the week-13 presentation and later report under the actual schedule; document outputs remain .md/.txt.
- **Base revision / branch / PR / evidence:** —
- **Reviewer:** —
- **Progress / review changes / outcome:** —

## Starting a Codex session

```text
Read AGENTS.md, README.md, docs/requirements.md and card <ID> in docs/team-roadmap.md.
Confirm the WeChat claim is recorded on main with my name and agreed scope.
Implement only this card on a dedicated branch; inspect current code and reuse it.
Coordinate shared-file/interface changes with other active card owners before editing.
Report actual changes, checks/skips, blockers and review fixes in the PR using the card ID.
The coordinator maintains the Roadmap record; do not start another progress document.
```

Notify the group when blocked, changing scope or handing off. Ask the coordinator to record the change before someone else takes over. Finish by linking actual review/acceptance evidence to the same card. Do not claim that a later task is complete merely because an earlier plumbing check passed.
