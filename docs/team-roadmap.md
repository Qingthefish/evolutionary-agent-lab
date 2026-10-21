# Team roadmap and task register

Updated: 2026-10-21 (Asia/Hong_Kong). **Discuss in WeChat; record task claims, progress and acceptance here.** This is the single task register. No coding tasks have been assigned by this document. The instructor's [requirements](requirements.md) remain the scope authority.

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
| M2 — first live slice | Issued model, live delegation, human interaction and independently checked output with model/time/usage evidence | Pending live access and integration cards |
| M3 — required coverage | Every R01–R13 capability has actual evidence or an explicit unresolved instructor dependency | Public retrieval, combined tools and memory-reset engineering checked; live Delete wiring, model behavior, runtime GitHub and learning evidence pending |
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
| [#11](https://github.com/Qingthefish/evolutionary-agent-lab/pull/11), [#12](https://github.com/Qingthefish/evolutionary-agent-lab/pull/12) | Single-register task cards, progress interpretation and contributor onboarding | Qingthefish, Codex-assisted |
| [#13](https://github.com/Qingthefish/evolutionary-agent-lab/pull/13) | Independent descendant/human-evidence acceptance (C01) | Qingthefish, Codex-assisted |
| [#14](https://github.com/Qingthefish/evolutionary-agent-lab/pull/14) | Common runtime configuration and persisted task policy (A02) | Qingthefish, Codex-assisted |
| [#15](https://github.com/Qingthefish/evolutionary-agent-lab/pull/15) | Separate goal/subtask metrics and matched-condition reporting (C04) | Qingthefish, Codex-assisted |
| [#16](https://github.com/Qingthefish/evolutionary-agent-lab/pull/16) | Independent child criteria, concrete repair feedback and checked handoff (A04 offline slice) | Qingthefish, Codex-assisted |
| [#17](https://github.com/Qingthefish/evolutionary-agent-lab/pull/17) | Combined retrieval, private experience, isolated execution and local-remote Git engineering | Qingthefish, Codex-assisted |
| [#18](https://github.com/Qingthefish/evolutionary-agent-lab/pull/18) | Bounded failed-child replacement, structural artifact criteria and inspectable run plans | Qingthefish, Codex-assisted |
| [#19](https://github.com/Qingthefish/evolutionary-agent-lab/pull/19) | Frozen candidate-memory reset/boundary protocol, ON/OFF trial preparation and announcement/handoff audit | Qingthefish, Codex-assisted |

The reviewed combined runtime passed 214 checks on 2026-10-17, including real Docker/UI checks; #18 later passed 308 and #19 passed 334 with no skips. These engineering checks use scripted/mocked model responses: no live-model or official-test-set performance is established. #8 does not close real GitHub runtime pushing; #9 does not close live memory learning/comparison. Later accepted partial slices retain their live dependencies in the cards below.

## Re-entry and next claims

Completed cards stay as reusable implementation/history records. Read their acceptance, linked PRs and actual limitations; do not rebuild completed modules just to start contributing. Earlier accepted slices inside a Blocked card also remain valid work. A new finding receives a follow-up card, not deletion or renumbering of the old record. The original 27 IDs remain; B05/C07 are additive findings/preparation, so card counts still do not measure percentage complete.

For a returning/new member: pull current main; read README, [announcement/evidence audit](requirements.md#implementation-evidence-audit-2026-10-21), this register and the relevant architecture section; ask Codex for a **read-only** summary of requirements, existing capabilities/evidence, missing acceptance and likely files. Check that summary yourself. Then discuss one bounded claim in WeChat and have the coordinator record it on main before coding. Private chat history is not transferred by Git.

| Candidate starting point | Concrete next result | Starting boundary |
| --- | --- | --- |
| [B05](#b05) | Claimed workflow example: approval-bound deletion | Read its claim/results before proposing further work; coordinate shared runtime edits |
| [C07](#c07) | Version a fair single/multi-agent development comparison | Evaluation configuration/baseline and tests; reuse the scheduler/scorer, coordinate shared interfaces |
| [D02](#d02) | Reproduce private/group interaction and approval/restart scenarios; fix observed usability gaps | Minimal interface and focused integration checks; offline slice can start before key, final live gate remains |
| [D04](#d04) | Independently install/run from the guide and fix actual setup problems | Clean environment, README and only necessary setup/CLI fixes; existing preparation is retained |

These are available/proposed claim scopes, not assignments. Review card status at the time of claiming. B03 needs a separately scoped runtime GitHub credential; A01/A03 and final live gates need issued model access and a defined budget. Official work waits for the instructor's dataset/protocol. UI styling or speculative redesign is not a replacement for required coverage. See the requirements audit for the distinction between engineering checks and unvalidated model performance.

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

- **Stage / status:** M2 / Blocked
- **Owner:** Qingthefish (Codex-assisted)
- **Dependencies / configuration:** A02 and C01; the final live check needs A01.
- **Scope:** Task acceptance policy and runner/scheduler integration; coordinate evaluation interfaces.
- **Acceptance:** Supported children have independent checks, unsupported proposals request explicit trusted review, and a parent resumes only with valid evidence. Failed checks return concrete feedback within budget.
- **Base revision / branch / PR / evidence:** Scope baseline 91ef064; main claim ae710d1; branch feat/A04-child-acceptance. Offline implementation 1eb10c9; synchronized branch 111e58b; [PR #16](https://github.com/Qingthefish/evolutionary-agent-lab/pull/16), merged 2026-10-21 in fee6843. Merged tree matches the checked feature tree. Python 3.14.7: 251 discovered, 229 passed, 22 skipped (13 Docker, 9 optional UI); seven new synthetic integration checks passed. Raw evidence: ignored runs/review-20261021-a04/. No live calls or Actions result.
- **Reviewer:** Qingthefish, Codex-assisted same-session self-review under standing authorization; no independent peer review claimed.
- **Progress / review changes / outcome:** 2026-10-21: owner-authorized continuation; no overlapping remote claim/open PR observed. Implement trusted exact-text child acceptance and bounded feedback/restart checks without changing model-provider or tool boundaries. Unknown proposals still require independent review. Offline integration now checks wrong-text feedback/repair, restart, verified child-to-parent handoff, budget exhaustion, missing/ambiguous child selectors, immutable policy and shared UI/evaluator wiring. Version-1 policies keep their existing IDs; version 2 stores trusted child criteria. Unsupported absence/failure criteria retain review and post-run checks. Review hardened malformed persisted policy handling. Offline slice accepted via PR #16; final live acceptance remains blocked on A01 and issued access. 2026-10-21 follow-up: A06 extends trusted acceptance with structural/absence criteria and bounded failed-attempt replacement; the final live gate remains. Next action: after approved model/key/budget arrive, run real child rejection/repair/handoff and retain model/time/usage evidence; fix observed integration failures before closing A04. This card is not Done, and other independent cards can proceed.

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

- **Stage / status:** M3 / In progress
- **Owner:** Qingthefish (owner-requested workflow example, Codex-assisted)
- **Dependencies / configuration:** A02 and existing exact-action delete/release path; engineering work does not require a model key.
- **Scope:** Deliberate live-role/configuration wiring and focused tests; coordinate runtime.py/gateway.py edits. Reuse the existing deletion implementation.
- **Acceptance:** An explicitly configured live agent can request deletion only for its own exact file version, pause before effects, then delete only after the addressed human approves and releases that action. Denial, changed hash, stale/wrong-task grant and restart remain safe. Preserve existing persisted runtime configurations rather than silently changing old roles. Document the supported flag/policy choice and add no host-file deletion fallback. Final model-driven smoke joins A05/D02 after A01.
- **Base revision / branch / PR / evidence:** Starting main 1acb56c; claim published on main in a4fbc10 before feature coding; branch feat/B05-controlled-delete; implementation ef5667f. Python 3.14.7 + Textual 8.2.8: 347 discovered, 332 passed, 15 actual-container checks explicitly skipped (engine not started), zero errors/failures; includes nine UI checks and 13 B05 checks. Clean committed-source Python 3.12.14 snapshot: all 13 B05 checks and seven suite/CLI/legacy checks passed. A task actually created using a4fbc10 resumes with unchanged configuration; enabling deletion on it is rejected without poisoning the stored record. 138 local Markdown links/anchors and two README JSON examples checked. Raw evidence: ignored runs/review-20261021-b05/. PR/acceptance recorded after review.
- **Reviewer:** Qingthefish coordinates; Codex-assisted review, no independent teammate approval claimed.
- **Progress / review changes / outcome:** 2026-10-21 announcement audit found the missing role capability; earlier file/gateway work is retained. The owner requested this workflow example; no overlapping remote claim/open PR was observed. A WeChat announcement was drafted for the owner to send; no group message or teammate confirmation is claimed. Implemented opt-in enable_delete / --enable-delete using the existing gateway and separate human release. Real files exercise pending approval, restart before/after approval, exactly-once release, independently checked absence, denial, changed file versions, wrong-task/human grants, stale revisions and released-but-unverified effects. Default roles stay unchanged; persisted runs reject capability changes. Runtime views/manifests expose the capability; version-1 plan JSON deliberately remains unchanged/disabled. Review corrected two test setup/status-name assumptions without changing production authorization rules. All provider responses were mocked; no model calls, live performance or Actions success claimed. Engineering implementation is ready for PR review; final real-model smoke remains A05/D02 after A01.

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

- **Stage / status:** M3 / Blocked
- **Owner:** Qingthefish (Codex-assisted)
- **Dependencies / configuration:** A02 and existing per-agent memory APIs; final live use needs A01.
- **Scope:** memory.py and scoped runtime hooks; do not duplicate orchestration.
- **Acceptance:** Actual successes/failures produce condition/provenance-linked candidate experience that a later live task can retrieve and consider. Usage/outcomes are recorded; logging a lesson alone is not learning evidence.
- **Base revision / branch / PR / evidence:** Batch implementation c95747c; shared runtime/combined fixture evidence in [A05](#a05).
- **Reviewer:** Qingthefish, Codex-assisted same-session self-review under standing merge authorization; no independent peer approval claimed.
- **Progress / review changes / outcome:** 2026-10-21: runtime memory is opt-in. Models may stage bounded conditional hypotheses; actual terminal outcomes idempotently capture observations/candidates and assess selected-use outcomes. A later scripted task retrieved/selected scoped experience and retained actual success/failure provenance. Lessons remain candidates, not authorization or proven repairs. At that acceptance, live batch comparison refused memory labels pending a versioned cross-task/reset protocol. Real-model reuse/learning acceptance needs A01; offline slice accepted via [PR #17](https://github.com/Qingthefish/evolutionary-agent-lab/pull/17) in 8888060. 2026-10-21 follow-up: the frozen-experience development protocol now versions training/reset conditions; C03 records boundary checks and C05 records experiment preparation. Next: validate real later-task retrieval/consideration/outcome evidence with issued access; card not Done.

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

- **Stage / status:** M4 / Blocked
- **Owner:** Qingthefish (accepted preparation may be handed off through WeChat)
- **Dependencies / configuration:** M3, C03/C04, [C07](#c07) for single/multi controls, issued allowed-model access and an authorized live budget.
- **Scope:** Versioned development run configurations, raw evidence and Markdown analysis; no held-out-data reuse.
- **Acceptance:** Run memory ON/OFF and single/multi-agent comparisons under matched conditions. Preserve failures, time and supplementary call/token cost; report actual gains/regressions. These comparison layouts are our evidence method, not an extra instructor rubric.
- **Base revision / branch / PR / evidence:** Shared branch/evidence in C03; engineering preparation accepted via PR #19 in cb05507. evaluation/memory-plan.json references explicit cases/limits; no live model call.
- **Reviewer:** Qingthefish coordinates; Codex-assisted same-session self-review, no independent teammate approval claimed.
- **Progress / review changes / outcome:** 2026-10-21: implemented a frozen-training ON/OFF development entry, read-only preflight, explicit fingerprint/budget authorization, counterbalanced order, planned-slot checkpoints and validated comparison. Shared training cost/failures are separate; probe failures/unrun slots stay in denominators. Probe prompts/non-memory tools/limits match; probe tools cannot read training chat/files or reuse old approvals, and probes cannot teach later probes. Source observations remain in the private snapshot for provenance. Scripted fixture and mocked HTTP prove plumbing only; their answers are not learned. Normal batch memory-on labels remain refused; use the versioned experience entry. Blocker: actual live trials/analysis need issued access and budget; single/multi setup remains C07. Do not mark this card Done from synthetic results.

### C07

**Prepare a matched single/multi-agent baseline**

- **Stage / status:** M4 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** C04 and current C05 protocol contracts; no key is needed for engineering preparation.
- **Scope:** Evaluation baseline/configuration and focused checks; reuse existing scheduler, acceptance and result summaries. Coordinate shared runtime/role edits. This splits the remaining preparation from C05 without erasing its memory-protocol work.
- **Acceptance:** Same allowed model, task/oracle content, comparable aggregate tools/budgets and declared initial memory/intervention conditions. Reject multi-only required-decomposition cases for an invalid single-agent control. Record topology as the intended difference, actual usage/failures and condition fingerprints. Offline output is engineering evidence only; actual comparison remains C05 after access/budget.
- **Base revision / branch / PR / evidence:** —
- **Reviewer:** —
- **Progress / review changes / outcome:** Added from the 2026-10-21 audit. Supporting experiment agreed with the owner, not an additional instructor requirement. No person assigned.

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

- **Stage / status:** M3 / Unclaimed
- **Owner:** —
- **Dependencies / configuration:** Accepted D01 engineering slice and the relevant runtime/tool contracts allow offline reproduction now; final live behavior needs A01/D01 live acceptance.
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

- **Stage / status:** M3 / Blocked
- **Owner:** Qingthefish (Codex-assisted)
- **Dependencies / configuration:** A03, A04, B02, B03 and D02.
- **Scope:** A focused integration fixture/live run across existing retrieval, file, sandbox, Git and human-control APIs.
- **Acceptance:** A bounded live development task performs actual retrieval, code execution, checked handoff and authorized GitHub push. Failures/partial outcomes remain visible and all actual effects have evidence.
- **Base revision / branch / PR / evidence:** Scope baseline 2d373dc; owner-requested batch branch feat/integrated-runtime-tools. Credential commit 8c4eb63, runtime/fixture commit c95747c, existing-doc update 694ce9a. Python 3.14.7 + Textual 8.2.8: 277 passed, zero skips/errors/failures, including 15 actual-container and nine UI checks. Public HTTPS smoke and combined web fixture retained in ignored runs/integrated-20261021-network/ and runs/integrated-20261021-combined-2/; final full evidence in runs/review-20261021-integrated/accepted-tests.log and accepted-validation.json. Three clean-snapshot CLI entry checks and 92 local Markdown links/anchors passed. [PR #17](https://github.com/Qingthefish/evolutionary-agent-lab/pull/17), merged 2026-10-21 in 8888060; synchronized feature a3d6afc. Merged tree matches the checked feature tree.
- **Reviewer:** Qingthefish, Codex-assisted same-session self-review under standing merge authorization; no independent peer approval claimed.
- **Progress / review changes / outcome:** 2026-10-21: continuous owner-authorized integration covered retrieval/cited handoff, input-aware specialist delegation, scoped coordination messages, optional Docker/Git/memory services and a minimal console. A combined scripted-model fixture performed public retrieval, actual isolated Python execution, independent checks, exact scripted approval for a disposable local-remote push, restart and later scoped candidate selection. A negative actual-container case rejects wrong output before any push. Review fixed input-delivery ordering/duplicates, partial-offer reporting, malformed credential settings and verifier transaction nesting in the fixture. No real model calls, autonomous-collaboration score, causal learning gain, runtime GitHub push or Actions result is claimed. Final A05 live acceptance remains dependent on A01/A03/B03. Offline slice accepted via PR #17; no new Markdown tracker. Next: provision issued model/budget and the designated GitHub runtime remote/credential, run the bounded live combined workflow and retain failures and actual effects before closing A05.

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
