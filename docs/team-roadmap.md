# Team roadmap and task register

Updated: 2026-10-29 (Asia/Hong_Kong). **Discuss in WeChat; record task claims, progress and acceptance here.** This is the single task register. The instructor's [requirements](requirements.md) remain the scope authority; agreed claims are recorded below.

**How to read progress:** Use the accepted baseline and milestone exit evidence, not a ratio of Done cards to all cards. I01–I03 record the review/integration of PRs #7–#9; substantial earlier work in #1–#6 is recorded separately in [Accepted baseline](#accepted-baseline). The card index covers that integration and the remaining delivery work, rather than every historical task. Cards differ in size and may be split as evidence reveals more work. Those integration records alone do **not** measure the whole project; no overall percentage is established.

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
| M0 — coordinate | Common baseline, visible claims and agreed boundaries | Register ready; individual claims recorded below |
| M1 — foundation integration | Existing platform plus #7/#8/#9 reviewed and integrated with honest evidence labels | Done; I01–I03 record that integration |
| M2 — first live slice | Issued model, live delegation, human interaction and independently checked output with model/time/usage evidence | One bounded declared-contract live root now passes independent numeric and handoff/read audit; prior actual draft acceptance is retained. Open-ended negotiation and remaining live human interactions still need coverage |
| M3 — required coverage | Every R01–R13 capability has actual evidence or an explicit unresolved instructor dependency | Bounded real code/handoff and private experience-use probes audited; broader live search/GitHub/human behavior and demonstrated learning benefit remain pending |
| M4 — stabilize/evaluate | Reproducible setup, pinned configuration, development comparisons/failure analysis and official adapter | Pending prerequisites |
| M5 — official delivery | Issued test protocol/results and required submission materials | Await official set and actual deadlines |

These are gates, not claimed percentages. Independent cards can proceed in parallel; external model access need not block offline implementation. Draft the architecture/presentation during M3/M4. The announcement says presentation in week 13, report after week 13, and has conflicting “3 weeks” / “3/1 weeks” dataset wording: confirm exact dates and memory/intervention/repeat rules. Optional extensions and UI styling must not delay mandatory coverage.

Validate and improve the platform with independent development cases before the official set arrives. Release of that set begins the official evaluation phase, not the first round of testing. The required capabilities and submission components are known, and the HKGAI address/model/key have now been issued. The exact test tasks, quota and unresolved evaluation details are not known. Meeting a roadmap gate requires actual evidence and does not guarantee a benchmark score or grade.

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
| [#11](https://github.com/Qingthefish/evolutionary-agent-lab/pull/11), [#12](https://github.com/Qingthefish/evolutionary-agent-lab/pull/12) | Single-register task cards, progress interpretation and contributor onboarding | Qingthefish, Codex-assisted |
| [#13](https://github.com/Qingthefish/evolutionary-agent-lab/pull/13) | Independent descendant/human-evidence acceptance (C01) | Qingthefish, Codex-assisted |
| [#14](https://github.com/Qingthefish/evolutionary-agent-lab/pull/14) | Common runtime configuration and persisted task policy (A02) | Qingthefish, Codex-assisted |
| [#15](https://github.com/Qingthefish/evolutionary-agent-lab/pull/15) | Separate goal/subtask metrics and matched-condition reporting (C04) | Qingthefish, Codex-assisted |
| [#16](https://github.com/Qingthefish/evolutionary-agent-lab/pull/16) | Independent child criteria, concrete repair feedback and checked handoff (A04 offline slice) | Qingthefish, Codex-assisted |
| [#17](https://github.com/Qingthefish/evolutionary-agent-lab/pull/17) | Combined retrieval, private experience, isolated execution and local-remote Git engineering | Qingthefish, Codex-assisted |
| [#18](https://github.com/Qingthefish/evolutionary-agent-lab/pull/18) | Bounded failed-child replacement, structural artifact criteria and inspectable run plans | Qingthefish, Codex-assisted |
| [#19](https://github.com/Qingthefish/evolutionary-agent-lab/pull/19) | Frozen candidate-memory reset/boundary protocol, ON/OFF trial preparation and announcement/handoff audit | Qingthefish, Codex-assisted |
| [#20](https://github.com/Qingthefish/evolutionary-agent-lab/pull/20) | B05 explicit runtime deletion capability and approval/restart/legacy-boundary checks | Qingthefish, Codex-assisted |
| [#21](https://github.com/Qingthefish/evolutionary-agent-lab/pull/21) | D02 private-chat/assignee/request console routes and complete scripted human round trips; final live acceptance retained | Qingthefish, Codex-assisted |
| [#22](https://github.com/Qingthefish/evolutionary-agent-lab/pull/22) | D03 exact approval/effect evidence binding, conservative legacy display and read-only/private/redaction checks | Qingthefish, Codex-assisted |
| [#23](https://github.com/Qingthefish/evolutionary-agent-lab/pull/23) | A01 issued HKGAI integration and actual three-request create/read/final cycle with independently checked output | Qingthefish, Codex-assisted |
| [#24](https://github.com/Qingthefish/evolutionary-agent-lab/pull/24) | A03 independent specialist collaboration capability and explicit socket limits; original failed live attempts retained, final A03 gate open | Qingthefish, Codex-assisted |
| [#25](https://github.com/Qingthefish/evolutionary-agent-lab/pull/25) | A03 bounded provider failure evidence and malformed/incomplete HTTP handling; partial real collaboration recorded without closing the live gate | Qingthefish, Codex-assisted |
| [#26](https://github.com/Qingthefish/evolutionary-agent-lab/pull/26) | D02 terminal proposal views and durable actual-human review evidence; final live interaction coverage stays open | Qingthefish, Codex-assisted |
| [#27](https://github.com/Qingthefish/evolutionary-agent-lab/pull/27) | A04 declared-contract delegation, scoped task directory and effective role evidence; 420 full checks passed, incomplete live roots retained | Qingthefish, Codex-assisted |
| [#28](https://github.com/Qingthefish/evolutionary-agent-lab/pull/28) | A04 one independently audited complete live workflow, received-source/read criteria and preserved partial-run evidence; 431 full checks passed | Qingthefish, Codex-assisted |
| [#29](https://github.com/Qingthefish/evolutionary-agent-lab/pull/29) | A04 verified source-input prerequisites before dependent delegation/replacement; 447 full checks passed, no new live-model requests | Qingthefish, Codex-assisted |
| [#30](https://github.com/Qingthefish/evolutionary-agent-lab/pull/30) | A05 shared sandbox execution/import acceptance, actual-container workflow checks and prepared code case; 466 full checks passed | Qingthefish, Codex-assisted |
| [#31](https://github.com/Qingthefish/evolutionary-agent-lab/pull/31) | Real code/experience negative trial, matched experience policies and verified exact-version export repair; 479 full checks passed | Qingthefish, Codex-assisted |

The reviewed combined runtime passed 214 checks on 2026-10-17, including real Docker/UI checks; #18 later passed 308 and #19 passed 334 with no skips. These engineering checks use scripted/mocked model responses: no live-model or official-test-set performance is established. #8 does not close real GitHub runtime pushing; #9 does not close live memory learning/comparison. Later accepted partial slices retain their live dependencies in the cards below.

## Re-entry and next claims

Completed cards stay as reusable implementation/history records. Read their acceptance, linked PRs and actual limitations; do not rebuild completed modules just to start contributing. Earlier accepted slices inside a Blocked card also remain valid work. A new finding receives a follow-up card, not deletion or renumbering of the old record. The original 27 IDs remain; B05/C07 are additive findings/preparation, so card counts still do not measure percentage complete.

For a returning/new member: pull current main; read README, [announcement/evidence audit](requirements.md#implementation-evidence-audit-2026-10-21), this register and the relevant architecture section; ask Codex for a **read-only** summary of requirements, existing capabilities/evidence, missing acceptance and likely files. Check that summary yourself. Then discuss one bounded claim in WeChat and have the coordinator record it on main before coding. Private chat history is not transferred by Git.

| Candidate starting point | Concrete next result | Starting boundary |
| --- | --- | --- |
| [B05](#b05) | Completed workflow example: approval-bound deletion | Read its claim, review and accepted results; choose an available card for new work |
| [A03](#a03) | Accepted capability slice; partial actual collaboration evidence | Preserve the paused writer/editor trial; do not treat a draft or successful connectivity probe as completed collaboration |
| [C07](#c07) | Claimed: HelloWorld2333666's single/multi-agent baseline | Published feature branch awaits PR/full acceptance; do not duplicate evaluation work |
| [D02](#d02) | Accepted console slice; final live human interaction remains | Reuse the merged routes/checks and issued HKGAI setup; define a budget and retain real human responses |
| [D04](#d04) | Independently install/run from the guide and fix actual setup problems | Clean environment, README and only necessary setup/CLI fixes; existing preparation is retained |

These are available/proposed claim scopes, not assignments. Review card status at the time of claiming. A01 validates the issued HKGAI connection; its authorized initial budget used three of at most four requests and has stopped, without authorizing a new trial. A03 and the remaining live gates need their own agreed scope/budget using that setup. B03 also needs a separately scoped runtime GitHub credential. Official work waits for the instructor's dataset/protocol. UI styling or speculative redesign is not a replacement for required coverage. See the requirements audit for the distinction between engineering checks and unvalidated model performance. Older dated blocker records describe their acceptance at that time; the issued model is now available locally, while later live evidence remains outstanding.

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
| [B05](#b05) | Expose controlled deletion in live roles |
| [C01](#c01) | Define independent development cases |
| [C02](#c02) | Close the experience-use loop |
| [C03](#c03) | Verify memory boundaries and reset rules |
| [C04](#c04) | Make evaluation results comparable |
| [C05](#c05) | Run controlled development comparisons |
| [C07](#c07) | Prepare a matched single/multi-agent baseline |
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

- **Stage / status:** M2 / Done (bounded provider connection/tool-cycle scope)
- **Owner:** Qingthefish (owner-authorized continuation, Codex-assisted)
- **Dependencies / configuration:** Issued HKGAI endpoint/model/key and the owner's explicit maximum-four-request/512-output-token-per-request initial budget. Provider quota/pricing remain unreported; larger trials require a separate budget.
- **Scope:** Existing provider/protocol adapter and its live smoke-check entry point.
- **Acceptance:** One real structured tool request/result cycle is recorded with model identity, attempts, usage, time and sanitized failure evidence; no fallback provider or credential in commits.
- **Base revision / branch / PR / evidence:** Baseline f57ca99; main claim 5efaf00 before feature coding; branch feat/A01-hkgai-provider; implementation 5be635b, actual-result documentation bd0a560; [PR #23](https://github.com/Qingthefish/evolutionary-agent-lab/pull/23), merged 2026-10-26 in 82a3f8c. Merged tree matches reviewed feature a322866; subsequent acceptance edits are documentation only. Python 3.14.7 + Textual: 380 discovered, 365 passed, 15 actual-container checks skipped (engine not started), zero errors/failures; includes nine UI and 11 HKGAI mocked contracts. Clean committed Python 3.12.14: 30 provider/runtime/plan checks passed. Temporary C07 (854a3b8) plus current source: 80 focused offline checks passed; not full C07 acceptance or merge. 140 local Markdown links/anchors checked before closeout. Real HKGAI smoke: three requests; observed t2_hkgai-v3_fp8_1m_e7; 4598 prompt + 214 completion = 4812 reported tokens; run wall time 1.8485 seconds; actual probe.txt exact bytes and final state independently verified. Original logs, request/response records, plan, DB and run results: ignored runs/review-20261026-a01/, live run 20261026-085037-8cda28. No Actions or official performance result.
- **Reviewer:** Qingthefish coordinates; Codex-assisted self-review, no independent teammate approval claimed.
- **Progress / review changes / outcome:** 2026-10-26: owner requested the course API email check and project continuation. The instructor's API announcement and restricted API Information page supply the HKGAI address/model/key; the inspected page does not state quota. Added the fixed issued-host HTTP adapter and standard chat/tool protocol without DeepSeek-specific thinking fields; preserved no redirects/retries/fallback and strict response validation. Shared console/TUI, scheduler, evaluation and experience selection retain the requested provider, endpoint and compatible legacy DeepSeek shape; provider/protocol changes or mixed live providers are rejected. Review fixed the old plan's unconditional DeepSeek selection and the UI's hard-coded provider indicator. After the owner explicitly authorized local key storage and at most four requests/512 output tokens per request, a single bounded smoke completed with actual create_text, read_text and final proposal. The independent predeclared expected file bytes and final task state passed. A durable request ledger reserved all three calls before POST; no automatic retry, fourth request, scripted response, fallback or extra backend was used. The credential is only in an owner-readable mode-0600 Git-ignored local file; tracked-source secret scan passed. Public credential-free metadata reads returned 404 for /docs and /openapi.json, 401 for /v1/models. C07's branch remains untouched and its separate live-provider re-entry finding is recorded below. A01's bounded connection acceptance has evidence; subsequent autonomous delegation, human interaction, tools and learning remain in their existing cards, with no general performance/grade claim.

### A02

**Unify runtime configuration**

- **Stage / status:** M2 / Done
- **Owner:** Qingthefish (Codex-assisted)
- **Dependencies / configuration:** M1; agree callable/config shapes with anyone claiming related UI/evaluation work.
- **Scope:** A shared runtime configuration entry plus focused CLI/TUI/evaluation wiring; preserve current state and permission checks.
- **Acceptance:** UI and evaluation use the same role/tool/limit/acceptance policy and original constraints. Unsupported backends are explicitly disabled. Offline contract checks can proceed before A01.
- **Base revision / branch / PR / evidence:** Scope baseline d76d585; main claim 127f511; branch feat/A02-shared-runtime. Implementation c5086f8, synchronized branch bc84cf9; [PR #14](https://github.com/Qingthefish/evolutionary-agent-lab/pull/14); merged 2026-10-18 in dfeb305. Python 3.14.7: 212 passed, 22 skipped (13 Docker, 9 optional UI); 12 shared-runtime contracts passed. Offline batch: four ordinary cases completed, five controls detected, one live case not configured. Raw evidence: ignored runs/review-20261018-a02/.
- **Reviewer:** Codex-assisted self-review under Qingthefish's standing merge authorization; no independent reviewer or formal peer approval claimed.
- **Progress / review changes / outcome:** 2026-10-18: shared roles/tools/task-tree limits, acceptance factory and CLI flags wired into UI/evaluation. Original constraints/root expectations persist across restart; changed contracts/budgets reject resume. Review added direct-call constraint preservation, combined-limit preflight and known legacy-task compatibility. Both CLI entry points and 79 local links checked; no new Markdown file. Search/execution/Git/memory remain disabled in this live setup; no model/API calls or Actions result. Review recorded in 496ac1d. Accepted and merged via PR #14 in dfeb305; merged tree matches the checked feature tree. A02 complete; live validation and tool/learning integrations remain separate cards.

### A03

**Demonstrate live autonomous delegation**

- **Stage / status:** M2 / In progress (engineering slice accepted; partial actual delegation/handoff evidence, root not complete)
- **Owner:** Qingthefish (owner-authorized continuation, Codex-assisted)
- **Dependencies / configuration:** A01 and A02.
- **Scope:** Opt-in shared collaboration capability independent of web/memory/execution/Git; versioned development plan, bounded socket configuration and focused checks. Retain scheduler budgets, exact child criteria and real human-review boundaries; no C07 edits or automatic approval of model-chosen tasks.
- **Acceptance:** A live high-level goal produces model-chosen decomposition, role negotiation and specialist-to-specialist delegation, with constraints and outcomes recorded. Fixed scripted role choices do not meet acceptance.
- **Base revision / branch / PR / evidence:** Baseline e502074; main claim adca6bf before coding; branch feat/A03-collaboration-capability; capability d7c0646, reviewed timeout configuration 233544a, actual-result documentation ed25992; [PR #24](https://github.com/Qingthefish/evolutionary-agent-lab/pull/24), merged 2026-10-26 in 6dee55d. Merged tree matches reviewed feature 28550b1; closeout changes are documentation only. Final Python 3.14.7 + Textual: 390 discovered, 375 passed, 15 actual-container checks skipped (engine not started), zero errors/failures; includes nine UI and 10 collaboration contracts. Clean committed Python 3.12.14: 40 checks passed. Temporary C07 (854a3b8) compatibility: 90 focused offline checks passed, not full C07 acceptance/merge. 143 local Markdown links/anchors checked. Two real requests attempted across separately authorized tasks: no completion received, no task tool dispatched, provider processing/billing unknown. Original evidence in ignored runs/review-20261026-a03/, including initial and retry-90s/ ledgers/requests/databases, original 30-second plan and final post-timeout-validation/. Engineering preparation is accepted; the live acceptance is not complete.
- **Reviewer:** Qingthefish coordinates; Codex-assisted self-review, no independent peer approval claimed.
- **2026-10-27 follow-up claim:** Qingthefish, owner-authorized Codex-assisted continuation from 2eee84f, branch fix/A03-provider-diagnostics. Scope: sanitized provider failure classification, durable runner failure evidence and real loopback HTTP fault checks. The prior generic transport errors do not identify a cause, and some HTTPException paths can escape the provider boundary. Preserve all prior attempts, no C07/assignment edits or automatic retry. A new small read-only provider diagnostic, if needed, requires a separately defined budget; no new live request authorized yet. Final A03 live acceptance remains unresolved.
- **2026-10-28 follow-up review:** [PR #25](https://github.com/Qingthefish/evolutionary-agent-lab/pull/25) merged in 8b91204; merged tree matches reviewed ae0c6d0. Implementation 379f41e catches malformed/incomplete HTTP responses, records sanitized failure kind/phase/size/duration and stops without automatic retry. A real loopback reproduction previously left the runner calling/task running after BadStatusLine; the fixed version stops and retains the failure. Python 3.14.7 + Textual: 399 discovered, 384 passed, 15 actual-container checks skipped (engine stopped), zero failures/errors. Clean committed Python 3.12.14: 49 focused checks passed; temporary unchanged C07 854a3b8 compatibility: 99 focused checks passed, not C07 acceptance/merge. 143 local Markdown links/anchors checked. Original observations and validation remain in ignored runs/review-20261027-provider/.
- **2026-10-27 actual provider observations:** Separately authorized read-only diagnostics used exactly four requests; all returned valid completions with the issued HKGAI model, but proposed tools were not dispatched. A separately approved 12-request local order-summary trial used 11 requests: the model assigned writer and editor tasks, wrote a draft and transferred matching snapshots. The owner actually accepted only the writer draft; its quantities/amounts were independently recomputed. The editor returned a snapshot for review, but the parent did not finish. No specialist-to-specialist assignment or negotiation was observed; that peer case is our chosen coverage, not a separate instructor grading rule. Human-review state was retained and all new model calls stopped after the owner requested clarification. The unspent request allowance is not an account balance; course quota/pricing/reset remain unknown. Preserve both the earlier failed attempts and these partial results. Do not resume this expired trial, script another human acceptance, or claim official performance.
- **Progress / review changes / outcome:** 2026-10-26: owner requested a finish-line audit and continuation after A01; no overlapping new remote work observed. Added an independent opt-in collaboration flag for scoped peer delegation/messages without external backends or legacy configuration changes. Version-2 plans explicitly record collaboration and provider socket limits; version 1 preserves existing fields/defaults. Scripted checks verify coordinator-to-writer-to-editor delegation, scoped messages, no implicit external tools, no self/unavailable delegates, shared attempt exhaustion across restart and actual review before unknown child completion. Review corrected a test's scheduler-state versus task-state assertion. The owner authorized at most 24 requests/1024 output tokens each, stopping at review and without automatic retry. The first request stopped after 30 seconds without a completion. After separate explicit approval, a fresh task used a 90-second setting and failed at transport after about 81 seconds. Both failed task records remain; only two requests were attempted, with no model-chosen decomposition or tool effect observed. The longer timeout is explicit configuration, not a proven latency fix. A03 is not Done. Next: confirm service availability, expected tool-call latency/limits and processing/billing conditions, then authorize a controlled new run. Human-review replies, negotiation and final output must be actual evidence; preserve failures and unknown usage. Other independent cards can proceed, and C07's branch remains untouched.

### A04

**Verify delegated work and resume parents**

- **Stage / status:** M2 / In progress (accepted engineering; complete live child repair/root gate still open)
- **Owner:** Qingthefish (Codex-assisted)
- **Dependencies / configuration:** A02 and C01; the final live check needs A01.
- **Scope:** Task acceptance policy and runner/scheduler integration; coordinate evaluation interfaces.
- **2026-10-29 input-preparation follow-up claim:** Qingthefish, owner-authorized Codex-assisted continuation after PR #28, branch fix/A04-required-delegation-inputs. Prevent the observed late-input deadlock for predeclared received-source requirements: reject unprepared delegation before creating the checker and point the model to verified input-aware delegation. Preserve unknown-child review, legacy policies/configurations, budgets, exact content/provenance checks and all raw trials. This is a focused prerequisite guard, not a new agent messaging architecture or a general replanning claim. Validate read-only preflight, source ownership/receipts, refusal paths and existing combined runtime; no new model allowance is created.
- **2026-10-29 complete-root follow-up claim:** Qingthefish, owner-authorized Codex-assisted continuation from 00105c9, branch feat/A04-completed-root-evidence. Prioritize a complete real allowed-model task with independently checked writer/editor/root outputs and actual artifact handoffs, then a different-input development probe if the same explicitly authorized work-round allowance permits. Preserve previous trials, fresh-state boundaries, exact criteria, real human pauses and scoped tools. No C07 branch edits, acceptance weakening or claims of general planning/official performance. Define and inspect the new cumulative allowance before any model call; final submission still needs the remaining announcement coverage and official protocol.
- **2026-10-28 follow-up claim:** Qingthefish, owner-authorized Codex-assisted continuation from 2554d30, branch feat/A04-checked-live-workflow. Prepare a separate declared-criteria collaboration case and bounded HKGAI plan, verify the exact existing child/root contracts offline, then seek a clearly defined live-run allowance. Aim for a complete independently checked root with actual artifact handoffs; do not change the open-ended A03 case, weaken acceptance, fabricate human replies, or duplicate C07. Preserve all old trials and report limits of predeclared role/title contracts. Review and fix actual runtime findings within this scope; no model call is authorized merely by preparing a plan.
- **Acceptance:** Supported children have independent checks, unsupported proposals request explicit trusted review, and a parent resumes only with valid evidence. Failed checks return concrete feedback within budget.
- **Base revision / branch / PR / evidence:** Scope baseline 91ef064; main claim ae710d1; branch feat/A04-child-acceptance. Offline implementation 1eb10c9; synchronized branch 111e58b; [PR #16](https://github.com/Qingthefish/evolutionary-agent-lab/pull/16), merged 2026-10-21 in fee6843. Merged tree matches the checked feature tree. Python 3.14.7: 251 discovered, 229 passed, 22 skipped (13 Docker, 9 optional UI); seven new synthetic integration checks passed. Raw evidence: ignored runs/review-20261021-a04/. No live calls or Actions result.
- **Reviewer:** Qingthefish, Codex-assisted same-session self-review under standing authorization; no independent peer review claimed.
- **Progress / review changes / outcome:** 2026-10-21: owner-authorized continuation; no overlapping remote claim/open PR observed. Implement trusted exact-text child acceptance and bounded feedback/restart checks without changing model-provider or tool boundaries. Unknown proposals still require independent review. Offline integration now checks wrong-text feedback/repair, restart, verified child-to-parent handoff, budget exhaustion, missing/ambiguous child selectors, immutable policy and shared UI/evaluator wiring. Version-1 policies keep their existing IDs; version 2 stores trusted child criteria. Unsupported absence/failure criteria retain review and post-run checks. Review hardened malformed persisted policy handling. Offline slice accepted via PR #16; final live acceptance remains blocked on A01 and issued access. 2026-10-21 follow-up: A06 extends trusted acceptance with structural/absence criteria and bounded failed-attempt replacement; the final live gate remains. Next action: after approved model/key/budget arrive, run real child rejection/repair/handoff and retain model/time/usage evidence; fix observed integration failures before closing A04. This card is not Done, and other independent cards can proceed.

- **2026-10-29 follow-up review:** [PR #27](https://github.com/Qingthefish/evolutionary-agent-lab/pull/27) merged in 7d2aa27; merged tree matches reviewed ecb64bb. Source 151a8f0 adds opt-in version-4 declared-child validation before any delegation/batch effect, scoped read-only task discovery, explicit final-proposal guidance and accurate effective per-case role metadata shared by launchers/plans/reports. Unknown role/title pairs receive allowed-contract feedback; actual file/root/child checks are unchanged. Versions 1–3 and ordinary comparison-role schemas stay unchanged; incompatible recorded configurations are refused rather than silently resumed. Final Python 3.14.7 + Textual full suite: 420 passed, zero skips/errors/failures, including all 15 actual-container and nine UI checks. The dedicated environment was started for these checks and stopped afterward. Clean committed Python 3.12.14: 57 focused checks passed. Incoming C07 854a3b8 has one unclassified-new-tool check error; 84 focused checks pass only with the proposed one-entry classification bridge in a temporary copy, not with an unchanged C07 branch. No teammate branch edit or C07 acceptance/merge. The owner requested fewer interruptions: routine corrections/fresh local tasks may share an explicitly authorized cumulative allowance; scope expansion, new allowance and critical approvals remain separate.
- **2026-10-28 actual trial outcomes:** First allowance used 18/24 HKGAI requests and paused because an expanded editor title had no declared criterion. The second 24-request allowance was shared cumulatively across 7 requests (repeated message polling stopped the writer), 5 requests (real clarification asking for an internal editor task ID), and 12 requests (writer independently verified, editor/root stopped at the shared call limit). All used t2_hkgai-v3_fp8_1m_e7; no transport failure, scripted human answer or whole-root success was observed. Original ledgers, conditions, payloads, responses, databases and independently recomputed numeric artifacts remain in ignored runs/review-20261028-checked-workflow/. The read-only audit preserves database hashes. Exact contract labels constrain this example and cannot establish open-ended decomposition/negotiation. Final opt-in scoping preserves the last trial's effective role/policy conditions, with code changes explicitly retained. No further model allowance remains; course quota/pricing/reset are unknown. A04/A03 stay open, and official performance is not established.

- **2026-10-29 complete-root evidence:** The explicitly approved 48-request work round used 43 requests across two fresh HKGAI tasks (22 original-input, 21 different-input), with the issued model, no human answers and memory disabled. Both original numeric/file reports classified their roots and required writer/editor tasks succeeded. A separate read-only audit found that the first checker never received the draft; its correct recomputation and report cannot prove that requirement. The changed-input task has writer→coordinator→checker delivery of the same snapshot, an actual checker read, checked result delivery, correct source rows/totals/report and a completed root. Thus one audited probe meets the complete bounded workflow scope; neither two full successes, general planning/negotiation, learning gains nor official performance is claimed. Original reports, requests/responses, conditions and database hashes are preserved in ignored runs/review-20261029-complete-root/.
- **2026-10-29 source-verification follow-up:** [PR #28](https://github.com/Qingthefish/evolutionary-agent-lab/pull/28) merged in c5aebd5; merged tree matches reviewed d1733ab. Source 20fde82 adds received_from criteria, identity-bound new receive events and exact-ID legacy gateway receipt verification. It checks one source selector in the same goal, consumed matching-version transfers, allowed causal relays and the required target read; copied bytes, chat assertions, unrelated/ambiguous/failed sources and malformed/conflicting receipts fail closed. Eleven regressions cover positive/negative paths and completion refusal. The new criterion retrospectively passes the changed-input trace and rejects the first trace without rewriting either. Both public checked examples now declare this criterion; their stricter runtime policy was not rerun using more paid calls. Final Python 3.14.7 + Textual full suite: 431 passed, zero skips/errors/failures (15 actual-container and nine UI checks); dedicated environment stopped afterward. Clean committed Python 3.12.14: 68 focused checks passed. Untouched C07 still has the known one-entry tool-classification gap; 95 focused checks pass with only the proposed bridge in a temporary copy, not in the unmodified teammate branch. No C07 merge or Actions result. User granted standing same-scope 48-request work-round authorization, retained in AGENTS.md; this is not unlimited quota or permission to invent a new round. The unused five requests are retained, and no new model calls were needed for the final audit. This complete-root/provenance slice is accepted; A04's broader live failure/repair and A03's open-ended collaboration gates stay open.

- **2026-10-29 input-preparation review (accepted):** [PR #29](https://github.com/Qingthefish/evolutionary-agent-lab/pull/29) merged in 5a88ea7; merged tree matches reviewed 2060956. Tested source afe3469, branch fix/A04-required-delegation-inputs. Trusted received_from child requirements now preflight current owned input hashes and unique active source provenance before delegation or failed-child replacement; only the original source or an explicitly permitted, consumed-snapshot relay qualifies. Strict schemas direct dependent contracts to delegate_with_inputs. Preflight has no file-read receipt, child, offer, approval or tool-call effect; execution rechecks before child creation. The child's actual receive/read/content checks remain required. Plan inspection, runtime settings and manifests preserve the same prerequisites; legacy no-source policies retain prior schemas/settings and incompatible recorded runs are refused. Review added changed-file, ownership/symlink, copied/unconsumed/wrong-source, relay, retry, restart/configuration and synthetic correction checks. Final Python 3.14.7 + Textual: 447 passed, zero skips/errors/failures (all 15 actual-container and nine UI checks); project-only environment stopped afterward. Clean committed Python 3.12.14: 84 focused passed. Temporary incoming C07 plus the proposed one-entry classification bridge: 111 focused passed; unmodified C07 retains its one known classification error, and its branch is untouched. Read-only re-audit still passes only the changed-input live trace; original DB hashes/reports and 43/48 cumulative request count are unchanged. Raw checks/audits: ignored runs/review-20261029-input-preparation/. No additional model requests, new allowance, Actions run, general replanning proof or official score. Same-session Codex-assisted review under owner authorization; no independent teammate approval claimed. This prerequisite slice is accepted; A04's broader live failure/repair and A03's open-ended collaboration gates stay open.

### B01

**Add real internet search**

- **Stage / status:** M3 / Done
- **Owner:** Qingthefish (Codex-assisted)
- **Dependencies / configuration:** A02 tool contract; approved search access/configuration if needed.
- **Scope:** A retrieval backend and its tests; any gateway registration is a coordinated edit.
- **Acceptance:** A real query returns bounded results with source URLs and retrieval evidence. Unsupported/local targets, oversized responses, timeouts and failed requests are handled explicitly.
- **Base revision / branch / PR / evidence:** Scope baseline 2d373dc; batch branch feat/integrated-runtime-tools; implementation c95747c. Actual public search/retrieval and nine retrieval boundary tests; shared evidence/review in [A05](#a05).
- **Reviewer:** Qingthefish, Codex-assisted same-session self-review under standing merge authorization; no independent peer approval claimed.
- **Progress / review changes / outcome:** 2026-10-21: owner-requested batch implementation, without per-card approval stops. Added explicit public HTTPS search/retrieval, checked/pinned DNS, redirect/size/type/deadline controls, query identity/site filtering, cited text artifacts and failure records. Actual Python documentation retrieved; public search availability/relevance remains a provider limitation. Accepted and merged via [PR #17](https://github.com/Qingthefish/evolutionary-agent-lab/pull/17) on 2026-10-21 in 8888060.

### B02

**Retrieve and hand off cited text**

- **Stage / status:** M3 / Done
- **Owner:** Qingthefish (Codex-assisted)
- **Dependencies / configuration:** B01.
- **Scope:** Retrieval result processing, bounded text artifacts and related tests.
- **Acceptance:** A specialist hands another task useful cited text through the existing artifact path. Source content remains reference data and cannot grant tool permissions or discard user constraints.
- **Base revision / branch / PR / evidence:** Batch implementation c95747c; shared fixture/test evidence in [A05](#a05).
- **Reviewer:** Qingthefish, Codex-assisted same-session self-review under standing merge authorization; no independent peer approval claimed.
- **Progress / review changes / outcome:** 2026-10-21: a researcher retrieved cited text and explicitly handed it through task-owned artifacts to downstream work. Input delegation preflights hashes and offers snapshots before waiting; child metadata exposes only offered paths, not private transcripts/files. Partial offers retain child identity and clear uncertainty. Review removed duplicate child-result/input notifications. Accepted and merged via [PR #17](https://github.com/Qingthefish/evolutionary-agent-lab/pull/17) on 2026-10-21 in 8888060.

### B03

**Connect a real GitHub push**

- **Stage / status:** M3 / Blocked
- **Owner:** Qingthefish (Codex-assisted)
- **Dependencies / configuration:** I02; explicitly authorized test repository/branch and narrow runtime credential scope.
- **Scope:** Git credential provisioning and remote verification in git_tools.py; preserve existing approval/allowlist boundaries.
- **Acceptance:** The runtime commits and pushes to the authorized GitHub branch after applicable approval; an independent remote lookup confirms the expected commit SHA. Local bare-remote success alone is insufficient.
- **Base revision / branch / PR / evidence:** Credential implementation 8c4eb63; batch branch feat/integrated-runtime-tools. Three credential tests and actual anonymous HTTPS main-SHA lookup; full evidence in [A05](#a05).
- **Reviewer:** Qingthefish, Codex-assisted same-session self-review under standing merge authorization; no independent peer approval claimed.
- **Progress / review changes / outcome:** 2026-10-21: explicit named-variable, repository-URL-scoped GitHub credential injection is implemented; no ambient developer credential is forwarded. Added strict configuration/permission parsing, disabled HTTP redirects and scrubbed credential diagnostics. Existing exact-approval/remote-SHA checks remain. Only a disposable local remote was pushed; actual GitHub runtime push acceptance still requires a designated test repository/branch and narrow credential. Offline slice accepted via [PR #17](https://github.com/Qingthefish/evolutionary-agent-lab/pull/17) in 8888060. Next: provision the designated test remote/branch and narrow credential, execute an approved runtime push and verify its remote SHA before closing B03.

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

### B05

**Expose controlled deletion in live roles**

- **Stage / status:** M3 / Done
- **Owner:** Qingthefish (owner-requested workflow example, Codex-assisted)
- **Dependencies / configuration:** A02 and existing exact-action delete/release path; engineering work does not require a model key.
- **Scope:** Deliberate live-role/configuration wiring and focused tests; coordinate runtime.py/gateway.py edits. Reuse the existing deletion implementation.
- **Acceptance:** An explicitly configured live agent can request deletion only for its own exact file version, pause before effects, then delete only after the addressed human approves and releases that action. Denial, changed hash, stale/wrong-task grant and restart remain safe. Preserve existing persisted runtime configurations rather than silently changing old roles. Document the supported flag/policy choice and add no host-file deletion fallback. Final model-driven smoke joins A05/D02 after A01.
- **Base revision / branch / PR / evidence:** Starting main 1acb56c; claim published on main in a4fbc10 before feature coding; progress f4a241e and review 62bd8fc; branch feat/B05-controlled-delete; implementation ef5667f and strengthened review check a23085d; [PR #20](https://github.com/Qingthefish/evolutionary-agent-lab/pull/20), merged 2026-10-21 in b7b0507. Merged tree matches checked feature a23085d. Python 3.14.7 + Textual 8.2.8: 347 discovered, 332 passed, 15 actual-container checks explicitly skipped (engine not started), zero errors/failures; includes nine UI checks and 13 B05 checks. Clean committed-source Python 3.12.14 snapshot: all 13 B05 checks and seven suite/CLI/legacy checks passed; the strengthened final 13 checks also passed in a fresh snapshot. A task actually created using a4fbc10 resumes with unchanged configuration; enabling deletion on it is rejected without poisoning the stored record. 138 local Markdown links/anchors and two README JSON examples checked. Raw evidence: ignored runs/review-20261021-b05/.
- **Reviewer:** Qingthefish coordinates; Codex-assisted review, no independent teammate approval claimed.
- **Progress / review changes / outcome:** 2026-10-21 announcement audit found the missing role capability; earlier file/gateway work is retained. The owner requested this workflow example; no overlapping remote claim/open PR was observed. A WeChat announcement was drafted for the owner to send; no group message or teammate confirmation is claimed. Implemented opt-in enable_delete / --enable-delete using the existing gateway and separate human release. Real files exercise pending approval, restart before/after approval, exactly-once release, independently checked absence, denial, changed file versions, wrong-task/human grants, stale revisions and released-but-unverified effects. Default roles stay unchanged; persisted runs reject capability changes. Runtime views/manifests expose the capability; version-1 plan JSON deliberately remains unchanged/disabled. Review corrected two test setup/status-name assumptions and strengthened the wrong-human case to use an actual member of the same group, reaching the addressed-responder gate; production authorization rules were reused unchanged. Accepted via PR #20 for this card's engineering wiring/boundary scope. All provider responses were mocked; no model calls, live performance or Actions success claimed. Final real-model CRUD smoke remains A05/D02 after A01.

### C01

**Define independent development cases**

- **Stage / status:** M2 / Done
- **Owner:** Qingthefish (Codex-assisted)
- **Dependencies / configuration:** I03.
- **Scope:** evaluation/cases.py, evaluation/dev/, focused harness acceptance checks and related tests; no scheduler, UI or live-provider changes.
- **Acceptance:** Small positive and negative cases have expectations written independently of candidate implementations. Cases cover goal/subtask outcomes and human intervention; acceptance criteria are available to A04 before live experiments.
- **Base revision / branch / PR / evidence:** Scope baseline debc027; claim on main 055d895; branch feat/C01-independent-acceptance from 055d895. Criteria b54a704, implementation 950c4da, synchronized branch 92ee146; [PR #13](https://github.com/Qingthefish/evolutionary-agent-lab/pull/13). Python 3.14.7: 200 passed, 22 skipped (13 Docker, 9 optional UI); five negative controls detected, one live case not configured. Raw evidence: ignored runs/review-20261018-c01/.
- **Reviewer:** Codex-assisted self-review under Qingthefish's standing merge authorization; no independent reviewer or formal peer approval claimed.
- **Progress / review changes / outcome:** 2026-10-18: Claimed on main before feature work; progress 960866f; review recorded in ae8dd5f. Defined criteria first, then enforced descendant state/artifacts and scoped clarification/approval counts. Rejected ignored/malformed criteria; corrected negative-control statistics so driver failures do not count as detected mismatches. Existing README/architecture updated, 77 local links checked; no new Markdown tracker, live model calls or Actions result. Accepted and merged via PR #13 on 2026-10-18 in cbcbae3. Merged tree matches the reviewed feature tree; C01 is complete, while live capability and official evaluation remain separate cards.

### C02

**Close the experience-use loop**

- **Stage / status:** M3 / In review (bounded actual-use evidence; general benefit remains C05)
- **Owner:** Qingthefish (Codex-assisted)
- **Dependencies / configuration:** A02 and existing per-agent memory APIs; final live use needs A01.
- **Scope:** memory.py and scoped runtime hooks; do not duplicate orchestration.
- **Acceptance:** Actual successes/failures produce condition/provenance-linked candidate experience that a later live task can retrieve and consider. Usage/outcomes are recorded; logging a lesson alone is not learning evidence.
- **Base revision / branch / PR / evidence:** Batch implementation c95747c; shared runtime/combined fixture evidence in [A05](#a05).
- **Reviewer:** Qingthefish, Codex-assisted same-session self-review under standing merge authorization; no independent peer approval claimed.
- **Progress / review changes / outcome:** 2026-10-21: runtime memory is opt-in. Models may stage bounded conditional hypotheses; actual terminal outcomes idempotently capture observations/candidates and assess selected-use outcomes. A later scripted task retrieved/selected scoped experience and retained actual success/failure provenance. Lessons remain candidates, not authorization or proven repairs. At that acceptance, live batch comparison refused memory labels pending a versioned cross-task/reset protocol. Real-model reuse/learning acceptance needs A01; offline slice accepted via [PR #17](https://github.com/Qingthefish/evolutionary-agent-lab/pull/17) in 8888060. 2026-10-21 follow-up: the frozen-experience development protocol now versions training/reset conditions; C03 records boundary checks and C05 records experiment preparation. Next: validate real later-task retrieval/consideration/outcome evidence with issued access; card not Done.

- **2026-10-29 bounded live acceptance:** In the repaired HKGAI trial, coder selected a private candidate whose source coder task had independently passed current input hash, actual sandbox-output and numeric checks. The later coder task succeeded, selection was assessed against its actual outcome, and the completed parent received/read the result. Read-only audits verify ownership, source checks, exact candidate identity, frozen seed/reset boundaries and DB hashes. The candidate is an observed success, not a universally valid recipe or causal learning proof. C02's agreed actual-use mechanism now has evidence; statistical/useful general improvement remains C05 and instructor R04 is not declared wholly closed. See [A05](#a05) for original failures, limits, full validation and pending evidence-PR acceptance.

### C03

**Verify memory boundaries and reset rules**

- **Stage / status:** M3 / Done
- **Owner:** Qingthefish (owner-authorized continuation, Codex-assisted)
- **Dependencies / configuration:** Existing C02 candidate-memory runtime; actual learning effectiveness remains C02/C05.
- **Scope:** Memory tests and narrowly justified reset/provenance fixes; preserve existing actor/conversation/namespace boundaries.
- **Acceptance:** Agents/conversations/namespaces remain separate; contradictory evidence and selected-use outcomes stay visible; fresh/reset memory works. An old lesson cannot authorize a new action.
- **Base revision / branch / PR / evidence:** Baseline b3e9689; branch feat/frozen-memory-protocol; implementation 2d8ff6d; [PR #19](https://github.com/Qingthefish/evolutionary-agent-lab/pull/19), merged 2026-10-21 in cb05507. Merged tree matches reviewed feature 399a379. Python 3.14.7 + Textual 8.2.8: 334 passed, zero skips/errors/failures, including 15 actual-container and nine UI checks. Clean committed-source snapshot on Python 3.12.14: 310 passed, 24 explicit Docker/UI skips; six CLI/suite checks passed. 136 local Markdown links/anchors and seven evaluation JSON files checked. Raw full/fixture/inspection/clean-snapshot evidence in ignored runs/review-20261021-memory/.
- **Reviewer:** Qingthefish coordinates; Codex-assisted same-session self-review, no independent teammate approval claimed.
- **Progress / review changes / outcome:** 2026-10-21: frozen, integrity-checked training provenance forks into fresh per-probe databases/files. Original source binding is unchanged; old files/transcripts/messages and approvals are not available to probe tools. A persisted current-message boundary allows new coordination messages. Contradictory source outcomes, retirement and failed selected-use outcomes remain visible; each later probe resets to the seed. Review fixed explicit SQLite connection closure, checked source evidence against actual terminal tasks, and kept unknown usage/unreleased actions from seeding probes. Accepted via PR #19 for boundary/reset engineering only. Synthetic/mocked-transport checks establish no live learning gain; C02/C05 remain open for that evidence, and official reset rules remain C06.

### C04

**Make evaluation results comparable**

- **Stage / status:** M3 / Done
- **Owner:** Qingthefish (Codex-assisted)
- **Dependencies / configuration:** C01 and A02; agree memory metadata with C02.
- **Scope:** evaluation/harness.py, result manifests and reporting/tests.
- **Acceptance:** Report separate root/subtask completion and assignment-to-final time, failures and human waits; show expected/executed/blocked/not-configured counts. Record dataset content, model, prompts, tools, budgets, interventions and initial memory so incompatible runs are rejected.
- **Base revision / branch / PR / evidence:** Scope baseline 3680542; main claim 1d29337; branch feat/C04-evaluation-evidence; implementation f6b8691. Python 3.14.7: 222 passed, 22 skipped (13 Docker, 9 optional UI), 244 discovered. Ten reporting tests include synthetic comparison-schema/arithmetic checks; 84 local Markdown links/anchors resolved. No live experiment. Offline batch: four contracts accepted, three verified goals, two verified subtasks, five negative controls detected, one live case not configured. Raw evidence: ignored runs/review-20261020-c04/acceptance-tests.log, acceptance-validation.json and acceptance-evaluation/20261021-000550-77f12d/. Synchronized branch 45269ad; [PR #15](https://github.com/Qingthefish/evolutionary-agent-lab/pull/15), merged 2026-10-21 in e144d57. Merged tree matches the checked feature tree.
- **Reviewer:** Qingthefish, Codex-assisted same-session self-review under standing merge authorization; no independent peer review claimed.
- **Progress / review changes / outcome:** 2026-10-20: claim published on main before coding. 2026-10-21: separate contract acceptance from verified goal/subtask completion; record final/unfinished timing, waits, failures and public comparison conditions. Review retained setup failures, validated result content/initial-memory/model evidence, rejected malformed/missing/mismatched conditions and explicit empty selections, and corrected live scripted-input labels. Existing README/architecture and UI labels updated; no new Markdown tracker. Accepted via PR #15; C04 reporting contract complete. Fresh-memory protocol only: actual memory-on use/trials and the official scoring/reset adapter remain C02/C05/C06. No live model calls or Actions result.

### C05

**Run controlled development comparisons**

- **Stage / status:** M4 / In progress (one matched real memory pair audited; broader comparisons remain)
- **Owner:** Qingthefish (accepted preparation may be handed off through WeChat)
- **Dependencies / configuration:** M3, C03/C04, [C07](#c07) for single/multi controls, issued allowed-model access and an authorized live budget.
- **Scope:** Versioned development run configurations, raw evidence and Markdown analysis; no held-out-data reuse.
- **Acceptance:** Run memory ON/OFF and single/multi-agent comparisons under matched conditions. Preserve failures, time and supplementary call/token cost; report actual gains/regressions. These comparison layouts are our evidence method, not an extra instructor rubric.
- **Base revision / branch / PR / evidence:** Shared branch/evidence in C03; engineering preparation accepted via PR #19 in cb05507. evaluation/memory-plan.json references explicit cases/limits; no live model call.
- **Reviewer:** Qingthefish coordinates; Codex-assisted same-session self-review, no independent teammate approval claimed.
- **Progress / review changes / outcome:** 2026-10-21: implemented a frozen-training ON/OFF development entry, read-only preflight, explicit fingerprint/budget authorization, counterbalanced order, planned-slot checkpoints and validated comparison. Shared training cost/failures are separate; probe failures/unrun slots stay in denominators. Probe prompts/non-memory tools/limits match; probe tools cannot read training chat/files or reuse old approvals, and probes cannot teach later probes. Source observations remain in the private snapshot for provenance. Scripted fixture and mocked HTTP prove plumbing only; their answers are not learned. Normal batch memory-on labels remain refused; use the versioned experience entry. Blocker: actual live trials/analysis need issued access and budget; single/multi setup remains C07. Do not mark this card Done from synthetic results.

- **2026-10-29 actual combined trial:** Owner-requested code/experience work has now exercised the frozen protocol with real HKGAI and a pinned sandbox. One failed training task and paired failed probes retain all costs and source outcomes. ON retrieved candidates but recorded zero selections; no useful adoption or improvement is established. Shared-role/input metadata and repair-feedback changes are covered in [A05](#a05); keep this card open pending a new bounded live validation, not a synthetic success.

- **2026-10-29 matched live pair:** The repaired ON/OFF probes use identical case content, the same allowed model, common frozen source experience, fresh files and matched prompts/non-memory tools/budgets. Both completed 1/1; ON/OFF used 13/13 requests, 20.369/20.795 seconds, 70790/66618 reported tokens. ON retrieved two candidates and selected one coder observation with an assessed successful later outcome; OFF retrieved/selected none. The training coder succeeded but its parent failed at the shared limit (15 requests/78230 tokens), retained as separate training cost/failure. No general learning improvement is established by this pair. Earlier failed/unselected and DNS trials remain; additional cases/replicates, single/multi comparison (C07), and official reset/repeat rules are outstanding. Raw evidence and read-only scope audit are linked in [A05](#a05).

### C07

**Prepare a matched single/multi-agent baseline**

- **Stage / status:** M4 / In review
- **Owner:** HelloWorld2333666
- **Dependencies / configuration:** C04 and current C05 protocol contracts; no key is needed for engineering preparation.
- **Scope:** Evaluation baseline/configuration and focused checks; reuse existing scheduler, acceptance and result summaries. Coordinate shared runtime/role edits. This splits the remaining preparation from C05 without erasing its memory-protocol work.
- **Acceptance:** Same allowed model, task/oracle content, comparable aggregate tools/budgets and declared initial memory/intervention conditions. Reject multi-only required-decomposition cases for an invalid single-agent control. Record topology as the intended difference, actual usage/failures and condition fingerprints. Offline output is engineering evidence only; actual comparison remains C05 after access/budget.
- **Base revision / branch / PR / evidence:** Baseline ff0f1bd; remote branch feat/C07-single-multi-baseline; implementation cc84203, branch record 854a3b8. The contributor reports 394 discovered / 370 passed / 24 skips on Python 3.12.15; that full-suite report has not yet been independently accepted. Coordinator preliminary checks at 854a3b8: 47 focused topology tests passed in an isolated source copy; 47 C07 plus 10 D02 checks also passed together in a temporary combined copy. Raw logs: ignored runs/review-20261022-c07-preliminary/ and runs/review-20261022-d02/clean-and-compatibility.json. These are bounded engineering/compatibility checks, not full-code approval. No PR observed at this check.
- **Reviewer:** Contributor's branch describes an earlier engineering handoff review; coordinator acceptance remains pending. Do not infer a completed repository review.
- **Provider re-entry note (2026-10-26):** A01 now prepares the issued HKGAI service. This branch's topology_plan.py live client and topology.py endpoint/thinking metadata still hard-code DeepSeek. Before any HKGAI topology trial, rebase those entry points onto the shared provider selection and check actual endpoint/protocol metadata. The 80-check temporary compatibility run is offline only; it does not validate that live path or transfer ownership.
- **Progress / review changes / outcome:** 2026-10-22: the owner supplied a WeChat claim screenshot; the matching remote branch records HelloWorld2333666 as owner and contains versioned single/multi plans, fairness validation, reporting and nominal/adverse scripted fixtures. Claim synchronized to main to avoid duplicate work. Preserve the contributor's commits; no merge, live comparison or independent full-code acceptance is implied. C05 still owns actual allowed-model trials after access/budget. D02 is reserved separately for console/human-flow work, without editing C07 evaluation modules or configurations.

- **2026-10-29 integration finding:** The new optional list_tasks tool needs an explicit C07 capability classification before this incoming branch can pass its all-gateway-tools taxonomy check. Untouched C07: 47 topology checks ran, 46 passed and one errored on that unknown tool. A temporary proposal adds list_tasks to COORDINATION_TOOLS; with that bridge 84 focused checks pass. Review the intended single-agent exclusion before applying during C07 integration. The original branch/commits remain unchanged; this is not full C07 acceptance or a live comparison.

### D01

**Submit real tasks through the interface**

- **Stage / status:** M2 / Blocked
- **Owner:** Qingthefish (Codex-assisted)
- **Dependencies / configuration:** I01 and A02; final live check needs A01.
- **Scope:** tui/ controller/view integration using the common runtime API.
- **Acceptance:** A human submits a real goal and sees actual progress/blockers. An offline unconfigured task remains pending; the UI creates neither a second scheduler nor fake completion.
- **Base revision / branch / PR / evidence:** Batch implementation c95747c; two console contracts, existing UI checks and clean source-snapshot CLI checks; shared evidence in [A05](#a05).
- **Reviewer:** Qingthefish, Codex-assisted same-session self-review under standing merge authorization; no independent peer approval claimed.
- **Progress / review changes / outcome:** 2026-10-21: added a standard-library console over the existing control-center service: real goal creation/status/advance, human answer/decision/release, messages and trusted review. Console/TUI/evaluator share explicitly configured runtime backends; runtime indicators reflect actual settings. Creating a task never calls the model implicitly; unconfigured tasks remain pending. Final live-goal acceptance still requires A01; offline slice accepted via [PR #17](https://github.com/Qingthefish/evolutionary-agent-lab/pull/17) in 8888060. Next: submit a bounded real goal through the shared interface with issued access, retain model/time/usage evidence and address observed failures before closing D01.

### D02

**Exercise human interaction end to end**

- **Stage / status:** M3 / In progress (engineering slice accepted; partial real draft review, complete live interaction gate open)
- **Owner:** Qingthefish (owner-authorized continuation, Codex-assisted)
- **Dependencies / configuration:** Accepted D01 engineering slice and the relevant runtime/tool contracts allow offline reproduction now; final live behavior needs A01/D01 live acceptance.
- **Scope:** Minimal console conversation/request controls and interaction checks; agent_lab/console.py and a dedicated test file. Reuse ControlCenter/workflow/scheduler. Leave C07 evaluation modules, shared runtime policies and its feature branch unchanged. Coordinator documentation edits stay in the existing documents.
- **Acceptance:** Private/group messages, clarification and restart, approval versus release versus verified effect, denial and unresolved effects are usable and correctly distinguished.
- **Base revision / branch / PR / evidence:** Baseline ff0f1bd; claim published on main in ee038dd before coding; branch feat/D02-console-human-flow; implementation 37b40f0; review record d5cefb8; [PR #21](https://github.com/Qingthefish/evolutionary-agent-lab/pull/21), merged 2026-10-22 in c5b9785. Merged tree matches reviewed feature bb95194. Python 3.14.7 + Textual: 357 discovered, 342 passed, 15 actual-container tests explicitly skipped (engine not started), zero errors/failures; includes nine UI tests and 10 new CLI interaction tests. Clean committed snapshot on Python 3.12.14 passed all 10 new tests, including separate interpreter persistence, plus CLI help. C07's unchanged modules/fixtures and D02 coexist in a temporary snapshot: 57 focused tests passed. 138 local Markdown links/anchors checked. Raw evidence: ignored runs/review-20261022-d02/.
- **Reviewer:** Qingthefish coordinates, Codex-assisted self-review; no independent teammate approval claimed.
- **2026-10-28 follow-up claim:** Qingthefish, owner-authorized Codex-assisted continuation, from 0f0fd38, branch fix/D02-review-state after the A03 diagnostics merge; main claim published in 2c1534e before coding. Scope: completed human-reviewed tasks must not still appear awaiting review in runner/query views; retain actual human review provenance and reject repeat/terminal review without a model call. Reuse existing checks and authorization, preserve original trial records, add focused regressions. No new HKGAI requests, C07 changes, auto-acceptance, or final D02 live completion is authorized or implied.
- **Progress / review changes / outcome:** 2026-10-22: owner requested a separate round after C07's claim. Added console chat new/list/feed, explicit task assignee and request list/detail/pending views, reusing ControlCenter. Existing commands/default coordinator remain compatible. Scripted-provider CLI invocations verify private agent messages, human clarification, restart, exact grant versus release versus observed file deletion, denial, wrong responder, changed-file/unverified effects, and explicit human review. Messages grant no approval or task execution. Review reproduced and fixed an invalid default assignee leaving an empty group; validation now precedes conversation creation. Corrected a test helper to use the existing read_file inspector; no authorization rules changed. C07 evaluation code/configuration, shared runtime policy and the teammate branch remain untouched. Engineering slice accepted via PR #21; all provider responses were scripted, with zero actual model calls and no Actions/model-performance claim. Blocker: issued model access and an authorized live budget under A01/D01. Next: perform the same human/agent interaction against the actual allowed model, retain observed behavior/failures and address findings before closing D02.

- **2026-10-28 follow-up review:** [PR #26](https://github.com/Qingthefish/evolutionary-agent-lab/pull/26) merged in db4cd7f; merged tree matches reviewed 281e3ca. Source 4a5910d derives terminal review status from trusted task state without changing historical caches; completed/failed/cancelled tasks cannot be reopened by review. Human acceptance records the actual actor/decision/feedback/proposal attempt atomically with success; rejection records its event and repair feedback together. Budget/incomplete-child refusals roll back a proposed acceptance event. Eight new regressions cover these paths, restart, nonmembers/agent reviewers and invalid input. Python 3.14.7 + Textual full suite: 407 discovered, 392 passed, 15 actual-container checks skipped (engine stopped), zero failures/errors; includes nine UI checks. Clean committed Python 3.12.14: 74 focused checks passed. Temporary unchanged C07 854a3b8 compatibility: 77 focused checks passed, not full C07 approval/merge. 143 local Markdown links/anchors checked. A read-only before/after check against the actual writer/editor database resolves the accepted writer display while retaining the editor pause and incomplete parent; hashes confirm original JSON/database evidence unchanged. No new model calls, past review events, automatic acceptance, Actions result or official score. Evidence: ignored runs/review-20261028-review-state/. A01 access is now verified and one real draft review is preserved, but private/group clarification and critical-action live coverage still remain; D02 is not Done.

### D03

**Expose trustworthy execution evidence**

- **Stage / status:** M3 / Done (engineering evidence-view scope; live platform acceptance remains in its existing cards)
- **Owner:** Qingthefish (owner-authorized continuation, Codex-assisted)
- **Dependencies / configuration:** D01 and C04 result contract.
- **Scope:** Read-only request/effect evidence in queries.py plus narrowly justified gateway/file receipt binding and focused tests. No table/schema rewrite or C07 evaluation/runtime-policy change. Existing interface views consume the same query result.
- **Acceptance:** Show actual task/tool/artifact/evaluation evidence, respect private boundaries and redact credentials. Display the evaluator's results without adding another scoring formula or expanding UI styling scope.
- **Base revision / branch / PR / evidence:** Baseline b0978db; claim published on main in 87a270a before feature coding; branch feat/D03-bound-action-evidence; implementation 5b6c84d; review record 66514ea; [PR #22](https://github.com/Qingthefish/evolutionary-agent-lab/pull/22), merged 2026-10-23 in a8698d6. Merged tree matches reviewed feature 4698284; changes since the tested source revision are register records only. Python 3.14.7 + Textual: 369 discovered, 354 passed, 15 actual-container checks explicitly skipped (engine not started), zero errors/failures; includes nine UI and 12 D03 checks. Clean committed Python 3.12.14 snapshot: 12 D03 and 10 D02 checks passed. Temporary C07 (854a3b8) + current code: 69 focused checks passed; no C07 merge/full acceptance implied. 138 local Markdown links/anchors checked. Original before/after reproduction and logs retained in ignored runs/review-20261023-d03/.
- **Reviewer:** Qingthefish coordinates; Codex-assisted self-review, no independent teammate approval claimed.
- **Progress / review changes / outcome:** 2026-10-23: reproduced false attribution after a failed deletion and later successful deletion in the same task. Added optional trusted file receipt binding, checked against the consumed exact task/action/digest/revision once; model tool schemas cannot set it. Queries confirm one bound file receipt or Git's existing operation/request/target/result evidence, never time order. Conflicting/missing/altered data stays unconfirmed, including historical unbound file events; raw history and prior task outcomes are retained. Same-path new-version, different-file/task, restart, single-use, Git uncertainty/reconciliation and read-only/private/redaction checks passed. Free-form displayed task/request content is redacted without changing stored evidence or scoring. Review kept the old file return shape and low-level trusted calls compatible and documented conservative legacy display behavior. Engineering scope accepted via PR #22; no model/API calls, actual GitHub runtime push, Actions or official-performance claim. C07 source/configuration/branch and shared runtime policy remain unchanged. Future live-run evidence uses these views under A01/D01 and the existing evaluation cards; this closure does not accept live model capability.

### A05

**Run the combined tool workflow**

- **Stage / status:** M3 / Blocked
- **Owner:** Qingthefish (Codex-assisted)
- **Dependencies / configuration:** A03, A04, B02, B03 and D02.
- **Scope:** A focused integration fixture/live run across existing retrieval, file, sandbox, Git and human-control APIs.
- **2026-10-29 execution-acceptance claim:** Qingthefish, owner-authorized Codex-assisted continuation from da0d2b1, branch feat/A05-sandbox-output-acceptance. Connect actual sandbox execution/export evidence to the shared trusted artifact criteria and prepare one bounded code-workflow case. Require current input/code versions, declared entrypoint/arguments, a successful isolated process, confirmed cleanup and a run-bound imported output; preserve independent content checks, failed/legacy records, budgets and human boundaries. Validate adversarial evidence and actual container integration without new model requests. No C07 edits, runtime GitHub credential expansion, open-ended autonomy or learning-performance claim; the broader A05 live gate stays open.
- **Acceptance:** A bounded live development task performs actual retrieval, code execution, checked handoff and authorized GitHub push. Failures/partial outcomes remain visible and all actual effects have evidence.
- **Base revision / branch / PR / evidence:** Scope baseline 2d373dc; owner-requested batch branch feat/integrated-runtime-tools. Credential commit 8c4eb63, runtime/fixture commit c95747c, existing-doc update 694ce9a. Python 3.14.7 + Textual 8.2.8: 277 passed, zero skips/errors/failures, including 15 actual-container and nine UI checks. Public HTTPS smoke and combined web fixture retained in ignored runs/integrated-20261021-network/ and runs/integrated-20261021-combined-2/; final full evidence in runs/review-20261021-integrated/accepted-tests.log and accepted-validation.json. Three clean-snapshot CLI entry checks and 92 local Markdown links/anchors passed. [PR #17](https://github.com/Qingthefish/evolutionary-agent-lab/pull/17), merged 2026-10-21 in 8888060; synchronized feature a3d6afc. Merged tree matches the checked feature tree.
- **Reviewer:** Qingthefish, Codex-assisted same-session self-review under standing merge authorization; no independent peer approval claimed.
- **Progress / review changes / outcome:** 2026-10-21: continuous owner-authorized integration covered retrieval/cited handoff, input-aware specialist delegation, scoped coordination messages, optional Docker/Git/memory services and a minimal console. A combined scripted-model fixture performed public retrieval, actual isolated Python execution, independent checks, exact scripted approval for a disposable local-remote push, restart and later scoped candidate selection. A negative actual-container case rejects wrong output before any push. Review fixed input-delivery ordering/duplicates, partial-offer reporting, malformed credential settings and verifier transaction nesting in the fixture. No real model calls, autonomous-collaboration score, causal learning gain, runtime GitHub push or Actions result is claimed. Final A05 live acceptance remains dependent on A01/A03/B03. Offline slice accepted via PR #17; no new Markdown tracker. Next: provision issued model/budget and the designated GitHub runtime remote/credential, run the bounded live combined workflow and retain failures and actual effects before closing A05.

- **2026-10-29 execution-acceptance review (accepted):** [PR #30](https://github.com/Qingthefish/evolutionary-agent-lab/pull/30) merged in d0f6d64; merged tree matches reviewed 1717594. Tested source a9c76e7, branch feat/A05-sandbox-output-acceptance. Shared sandbox_output criteria require the current code/data hashes, exact job selector, the latest matching successful uninterrupted isolated run, confirmed cleanup, a verified export checkpoint and a run-bound imported-output receipt. Independent content criteria remain separate. New records preserve job metadata and idempotent import/reconciliation events; old unbound evidence and unrelated/failed/modified results cannot certify this new criterion. Setup/plan inspection refuse a missing executor. Added one independently checked coordinator/coder case, prepared for a later bounded live run; it is not claimed as executed by HKGAI. Eighteen synthetic-engine evidence checks and the existing actual-container delegation fixture now use the shared policy; a new real-container check rejects changed code after success. Review corrected a misplaced test assertion and enforced an integer receipt size; the initial failed full-check log remains. Final Python 3.14.7 + Textual: 466 passed, zero skips/errors/failures, including all 16 actual-container and nine UI checks; dedicated environment stopped afterward. Clean committed Python 3.12.14: 114 focused passed. Temporary C07 plus only the proposed list_tasks classification bridge: 141 focused passed; unchanged C07 retains its known classification error and its branch remains untouched. Raw evidence: ignored runs/review-20261029-execution-proof/. No new provider calls, allowance reset, actual runtime GitHub push, general coding/planning/learning claim or official result. Same-session Codex-assisted self-review under owner authorization; no independent teammate approval claimed. This execution-acceptance slice is accepted; the broader A05 live-tool/GitHub gate remains open.

- **2026-10-29 combined capability/experience claim:** Qingthefish, owner-authorized Codex-assisted continuation from 9111e8e, branch feat/A05-C05-live-code-experience. The owner explicitly requested a substantial combined real-capability and memory-use round. Prepare one real sandbox/code/handoff training task and identical frozen-seed memory ON/OFF probes on different order inputs; use the issued HKGAI model, actual isolated execution and independent acceptance. First synchronize declared policy roles/input guards/metadata in the experience driver, then validate offline. Define a fresh cumulative allowance of at most 48 requests across the three planned fresh root tasks (16 per task), 1024 output tokens/request, 90-second socket timeout, with no automatic retry, fake human reply or acceptance weakening. This is a genuinely new user-requested work round; the previous 43/48 ledger stays closed and unchanged. New scope includes the existing no-network pinned Python sandbox and per-agent experience tools as explicitly requested here; no runtime GitHub credential provisioning or push. Stop the round at transport/auth/quota/unknown effects or actual human review and keep planned/unrun slots visible. Preserve C07 and original evidence; no new progress Markdown. Record actual gains, null effects or regressions without claiming general learning or official scores.

- **2026-10-29 combined capability/experience review (accepted engineering and retained trial evidence):** [PR #31](https://github.com/Qingthefish/evolutionary-agent-lab/pull/31) merged in 0f95a04; merged tree matches reviewed 60f0f79. Real experiment source 186b68b used 35/48 HKGAI requests across all three allowed fresh roots (training 12, ON 12, OFF 11), with the issued model, 214752 reported tokens, no provider failures or human replies, and six successful isolated/cleaned Python runs. All three full contracts failed. Training totals were numerically right but total_amount used 63.0; both probes had correct aggregate totals but CSV strings instead of required line objects. Repeated exports after code repair failed create-only import. Original prompts/criteria, reports, payloads, outcomes, DB hashes and frozen seed remain unchanged in ignored runs/review-20261029-code-experience/. ON retrieved three candidates, selected zero; OFF retrieved/selected zero. Both completion rates are 0/1, so no learning benefit or general coding performance is claimed. The raw candidate set includes fallible statements and failed-source evidence; candidates remain hypotheses.
- **2026-10-29 repairs and checks:** Source c783eea synchronizes experience-stage role/input guards and inspected per-case roles, adds optional exact-version replace_outputs with a separate update_text capability check and read-only preflight, safe import/recovery and current-version execution proof, and retains bounded real verification feedback in new observations without changing old outcome/source records. Probe guidance requires explicit selection only for actually adopted advice. Case clarification 34dab3b spells out integer representation and object-line schema; original criteria were not relaxed or rerun. Final Python 3.14.7 + Textual: 479 passed, zero skips/errors/failures, including 17 actual-container and nine UI checks; dedicated environment stopped. Clean committed Python 3.12.14: 178 focused passed. Temporary incoming C07 with its proposed one-entry list_tasks bridge: 205 focused passed; unmodified C07 keeps its known taxonomy error and its branch remains unchanged. Source/case refinements retain read-only audit and raw failures; no Actions result or new live allowance. All three planned root slots are used; the remaining 13 requests are retained, not permission to create another root. A05/C02/C05 remain open for repaired real-task completion/adoption and broader required coverage. Same-session Codex-assisted self-review under owner authorization; no independent teammate approval claimed. This repair/evidence slice is accepted; additional live validation remains pending an explicit new allowance.

- **2026-10-29 approved repaired live follow-up:** After the reviewed repairs merged, the owner explicitly approved an additional at-most-48-request/three-fresh-root round (1024 output tokens, 90-second socket, same local sandbox/frozen-experience scope). Combined maximum with the retained first round is 83 requests. Use the prepared ignored runs/review-20261029-code-experience-followup/ plan and cumulative ledger; no old trial replay, new provider, web/runtime Git or simulated human reply. This is an explicit additional allowance, not a reset of the spent first round. Run training and matched ON/OFF probes; retain failures and inspect actual selection/use, execution/import and root delivery before accepting evidence.

- **2026-10-29 follow-up transport boundary:** The explicitly approved repaired run reserved one request, which failed at DNS/opening in about 0.016 seconds before a completion or task tool effect. It stopped without retry; both dependent probes remain not run, the failed root/request and unknown usage remain, and the dedicated environment was stopped. A later read-only check resolved the issued hostname and reference hosts; no proxy/system setting was changed and no further model call was made. This does not establish the transient cause, zero billing or permission to replay. A fresh three-task/45-request restart is prepared pending explicit post-failure confirmation, entirely inside the already approved combined 83-request ceiling (35 + 1 + at most 45 = 81). Preserve ignored runs/review-20261029-code-experience-followup/ and runs/review-20261029-code-experience-dns-restart/; do not resume the failed root.

- **2026-10-29 explicit post-DNS restart approval:** The owner approved three fresh tasks and at most 45 requests after read-only DNS resolution recovered. Preserve the one DNS-failed request and do not resume its task. Use the prepared ignored runs/review-20261029-code-experience-dns-restart/ plan, 15 shared attempts per task, 1024 output tokens, 90-second socket and no automatic retries; perform one read-only DNS preflight after engine startup before creating tasks/POSTing. The combined ceiling is 35 + 1 + 45 = 81 requests, within the separately approved 83-request total. Same pinned local code/memory scope, no provider substitution, web/runtime Git expansion or fabricated human decisions. This explicit restart also authorizes the three replacement root slots, without erasing the failed root.

- **2026-10-29 repaired live result (independently audited; integration record pending):** Source ff1ac5f used 41/45 issued-HKGAI requests across three fresh roots (training 15, ON 13, OFF 13), 215638 reported tokens, no transport failure/human reply and three successful isolated/cleaned Python jobs. Both ON/OFF roots completed; an independent read-only audit rechecks every root/coder criterion, actual source/input versions and run-bound export, root receipt/read, preserved report rows, numeric/schema values, equal probe definitions/effective non-memory roles and unchanged frozen memory. The coder selected one private source-bound observation from its successful training subtask; its probe use was assessed succeeded. OFF retrieval/selection stayed zero. Training coder passed, its report/root artifacts also pass the file checks, but its parent exhausted the shared 15-attempt budget before completion; preserve that failed root rather than promoting it from artifacts. ON/OFF each completed 1/1 in 20.369/20.795 seconds with 13 requests each; ON reported 70790 tokens and OFF 66618. This one pair is not evidence of general learning gains. Raw requests/responses, configs, seeds, reports, audits and unchanged DB hashes are retained in ignored runs/review-20261029-code-experience-dns-restart/. The combined reserved count is 35 + 1 DNS failure + 41 = 77, within the explicit 81/83 ceilings; four current requests remain unused and all three current task slots are spent. No new code or repeated full suite was needed for this evidence-only update; prior c783eea regression remains 479 passed (17 actual-container, nine UI), with later case-contract checks retained. The dedicated execution environment was stopped. Bounded code/report and explicit experience-use evidence is accepted subject to this evidence PR; A05's broader retrieval/GitHub/human tool gate and A03's general planning gate remain open. Same-session Codex-assisted audit, no independent teammate approval or official score.

### A06

**Check isolation and bounded recovery**

- **Stage / status:** M3 / In progress
- **Owner:** Qingthefish (owner-requested continuous batch, 2026-10-21)
- **Dependencies / configuration:** Existing M3 capabilities; final live checks await A01 and relevant tools.
- **Scope:** Task/role/tool isolation and recovery checks; create separate small repair cards for larger findings.
- **Acceptance:** Cross-agent access, path escapes, unsafe execution, exhausted budgets and unknown effects are rejected or reported correctly. Fixes follow observed failures rather than an unrelated redesign.
- **Base revision / branch / PR / evidence:** Baseline 304ea4d; branch feat/bounded-recovery-and-acceptance. Implementation 43dc18c; input handoff 1919a29; compatibility 808705c. Python 3.14.7 + Textual 8.2.8: 308 passed, zero skips/errors/failures, including 15 actual-container and nine UI checks. Raw evidence: ignored runs/review-20261021-recovery/full-tests.log and validation.json. [PR #18](https://github.com/Qingthefish/evolutionary-agent-lab/pull/18), merged 2026-10-21 in 1b25892. Merged tree matches checked feature 983a855.
- **Reviewer:** Qingthefish coordinates; Codex-assisted same-session self-review, no independent teammate approval claimed.
- **Progress / review changes / outcome:** 2026-10-21: owner requested another substantial batch without per-card stops; remote showed no overlapping open PR/new teammate branch. Added opt-in shared-limit child replacement preserving failed rows, identical assignments/criteria, budgets and fresh file/approval boundaries. Denied/unreleased/unknown effects prevent replacement. Extended independent root/child acceptance with bounded data-only properties and retained failure metrics. Review corrected legacy-resume configuration poisoning, preserved a parent's human wait, blocked unknown provider usage, retained explicit version-checked retry inputs before scheduling, enabled owned-file repair, and kept failed attempts visible in evaluator denominators. General DAG replanning/reassignment and live behavior remain unvalidated; no model calls or official performance claim. Engineering slice accepted via PR #18; final live boundary/recovery checks remain before closing this card.

### D04

**Verify clean-environment setup**

- **Stage / status:** M4 / Unclaimed
- **Owner:** — (available for agreed teammate claim; prior Qingthefish preparation retained below)
- **Dependencies / configuration:** M3; final real-model/tool setup awaits issued access and relevant backends.
- **Scope:** Installation/run instructions and one minimal reproducible demo; coordinate shared README edits.
- **Acceptance:** Another member can install and run from the guide, use the actual supported capabilities and identify missing configuration. Core use works without optional Textual dependencies; setup does not expose credentials.
- **Base revision / branch / PR / evidence:** Baseline 304ea4d; shared branch/evidence in A06. Versioned evaluation/development-plan.json and two development connection cases; README updated in place. Clean source-snapshot Python 3.12 CLI and offline-suite checks are retained in ignored runs/review-20261021-recovery/clean-snapshot-checks.json (24 explicit skips for unavailable Docker/UI). No teammate reproduction is implied.
- **Reviewer:** Qingthefish coordinates; Codex-assisted same-session self-review, no independent teammate reproduction claimed.
- **Progress / review changes / outcome:** 2026-10-21: static inspection needs no model/key/network/engine and lists actual missing model configuration. Explicit execution requires the inspected content fingerprint and permission, uses declared budgets and real human pauses, and snapshots conditions with results. Inspection rejects hidden fields, unsupported memory/official labels and missing cases; HKGAI has no fallback. Initial cases cover connection/handoff and structured artifacts only. This is preparation for live setup, not a release freeze, full requirement benchmark, learning comparison or official adapter. Engineering preparation accepted via PR #18; another member's clean setup and actual configured live/tool reproduction remain before closing D04.

- **Next claim scope:** Independently reproduce setup/CLI and supported tool configuration from current main; report actual failures and necessary fixes. No need to rewrite the existing implementation. Final live reproduction awaits access.

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
