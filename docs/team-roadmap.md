# Four-person delivery roadmap — proposal

Planning snapshot: 2026-10-17, Asia/Hong_Kong. This document proposes milestones, work packages, and ownership boundaries. It does not assign people, modify repository permissions, or change the instructor's requirements. Read [requirements](requirements.md), [direction](direction.md), and [architecture](architecture.md) first. README remains the source of implementation status; this roadmap owns the proposed work breakdown.

## 1. Starting point and document scope

The implementation status belongs in [README](../README.md); mandatory capabilities and acceptance evidence belong in [requirements](requirements.md); design choices belong in [direction](direction.md). This file contains only the proposed delivery stages, workstream boundaries and task cards, so four parallel Codex sessions can avoid duplicating work.

The original platform foundation came through PRs #1–#6. `HelloWorld2333666` contributed [#7](https://github.com/Qingthefish/evolutionary-agent-lab/pull/7) (terminal controls), [#8](https://github.com/Qingthefish/evolutionary-agent-lab/pull/8) (restricted Git), and [#9](https://github.com/Qingthefish/evolutionary-agent-lab/pull/9) (development evaluation). They were reviewed and merged as a dependency stack on 2026-10-17. I01–I03 below record the completed integration checks, not new coding assignments. Preserve each author's real contributions when handing modules over; new ownership does not transfer authorship of existing code.

The team has four members; A/B/C/D below remain proposed workstream slots until claimed. Task IDs are planning IDs, not automatically-created GitHub issues or assignments. Offline fixtures and passing engineering tests do not establish live-model performance. Actual GitHub runtime pushing, memory learning/comparisons and remaining live integrations retain the limitations stated in README.

## 2. The finish line

This is an engineering delivery with required empirical evaluation. It does not require inventing a new model/algorithm or publishing a research contribution. Its learning/evolution and performance requirements still require actual evidence. No fixed passing score or full unseen-task coverage can be inferred from the announcement.

The final artifact is a runnable general multi-agent platform plus an evaluation entry point and submission materials. A human can give a group a new goal. Allowed-model agents communicate, decompose work and negotiate/delegate to specialists, including specialist-to-specialist delegation; use real search, files, code execution and Git; ask the human when needed; and return checked Markdown/plain-text artifacts and run evidence. Private conversations, execution/files, and per-agent memory have enforced boundaries. Future tasks can reuse condition-scoped experience from actual outcomes. Evaluation automatically reports goal/subtask completion and assignment-to-output time, including failures.

A typical development demonstration is: retrieve documentation → implement a small script → run independent checks in the sandbox → return a Markdown summary and code → commit/push to an explicitly authorized test branch. This is an illustration, not a prediction of the instructor's test set or a fixed agent pipeline.

Final acceptance follows R01–R17 in the requirements document: real allowed-model execution and required tools, private/group interaction, isolation, per-agent learning, automatic completion/time evaluation, official test results, architecture/report/presentation and genuine continuing contributions. These are the finish line; a dashboard alone or a scripted success rate cannot substitute for them.

## 3. Milestones and exit gates

These are dependency gates, not percentage-complete estimates or invented deadlines. Parallel work inside a gate is encouraged; a missing API key should not block independent offline implementation/review.

| Gate | Resulting stage | Work to finish | Exit evidence |
| --- | --- | --- | --- |
| M0 — coordinate | Four owners and a common starting revision | Confirm invitation, choose A/B/C/D, agree interfaces and claim the first tasks | One owner and clear acceptance for each active task; nobody independently reimplements the same module |
| M1 — integrate existing work (complete) | A usable development platform | #7/#8/#9 reviewed and merged in dependency order; evaluate current status on main | Local UI/core/container checks, preserved contributions and honest evidence labels |
| M2 — first live slice | One real-model delegated task works end to end | Issued model smoke test, common runtime config, child acceptance/review, actual execution and human interaction | Full live trace and independently checked output; issued model identity, attempts/tokens/time and failures recorded |
| M3 — mandatory coverage | A complete candidate for the announcement | Search, verified GitHub push, per-agent learning loop, private/group interaction, isolation and failure paths | Every R01–R13 row has actual evidence or an explicit unresolved instructor dependency; no fixture evidence passed off as live capability |
| M4 — stabilize and evaluate | Reproducible release candidate | Freeze interfaces; clean-install test; development comparisons/failure analysis; prepare official-set adapter | Versioned config, reproducible checks, matched experiments where authorized, known limitations and setup guide |
| M5 — official delivery | Submission-ready project | Run issued set under its protocol; preserve results; complete report, architecture, presentation and contribution evidence | Official artifacts and required submission materials, checked against actual deadlines |

M2 closes the first live integration risk; M3 closes feature coverage. These can overlap, but neither can be replaced by a polished dashboard. The official set is described as arriving three weeks before final submission; the report paragraph also says “3/1 weeks.” Verify that wording and exact dates. The announcement specifies presentation in week 13 and report submission after week 13; this roadmap does not move either deadline.

Draft the architecture, failure analysis and presentation during M3/M4. Do not postpone preparation until official results exist, or delay the week-13 presentation because an assumed dataset schedule differs. M5 finalizes each deliverable at its actual required date.

## 4. Four workstreams

These are human workstreams, not the identities of runtime agents. All four people can use Codex. Ownership means one accountable implementer per task/module, with a different reviewer; it does not restrict everyone from reading the code.

| Slot | Main responsibility | Primary code ownership after handoff | Interface responsibility |
| --- | --- | --- | --- |
| A — runtime/integration | Allowed model, planning/delegation, execution lifecycle, common configuration | `core.py`, `deepseek.py`, `protocol.py`, `gateway.py`, `runner.py`, `scheduler.py`, `budget.py`, `files.py`, `sandbox.py`, top-level CLI | Own shared state/schema and wiring; consume B/C capabilities; expose the same runtime to D and evaluation |
| B — external tools | Search/retrieval and restricted Git through verified remote effects | `git_tools.py`; proposed retrieval module and their tests | Define bounded inputs/results and exact-action push approval; request A to wire tools into shared gateway |
| C — experience/evaluation | Per-agent learning loop, independent acceptance, batch results and controlled comparisons | `memory.py`, `evaluation/`, development cases, corresponding tests | Own memory scope/outcome and result schemas; consume runtime events instead of duplicating orchestration |
| D — interaction/observability | Minimal private/group interaction, human pause/release, status/evidence and setup | `tui/`, `queries.py`, `inspection.py`, optional UI requirements, corresponding tests | Use shared runtime/evaluator APIs; UI must not implement another scheduler, permission service or scoring formula |

Suggested initial fit: Qingthefish can retain A and integration because that baseline is already here; the #7–#9 author can retain B's Git work if the team chooses. C and D can adopt the existing evaluation/TUI seeds through explicit handoff. This is a proposal, not an assignment based on background. PRs #7–#9 were authored by `HelloWorld2333666`; later ownership transfer must preserve that contribution and history. Their author does not automatically own every future task in all three areas.

A starts with more existing modules, not a requirement to redo them. B/C/D each have substantial source-code work beyond writing documentation or running commands. Everyone contributes throughout implementation and integration; collecting names on the final report is not a substitute for the instructor's significant ongoing code-contribution requirement.

Shared files (`gateway.py`, `scheduler.py`, `core.py`, top-level CLI, README and consolidated architecture notes) need one active editor at a time. For example, B implements/tests a backend and provides its schema; A performs the focused gateway integration. Do not have both Codex sessions independently change the same registration code. PR #8 already includes gateway/scheduler changes: review and reuse that work instead of rewriting it under this proposed ownership table.

## 5. Small work packages

Each row should become one reviewable task/PR or be split further if its acceptance cannot be stated clearly. These IDs are not existing GitHub issue numbers. Claim an owner before starting; do not allocate all rows to one person merely because that person's Codex can run.

| ID | Slot | Deliverable / acceptance | Depends on |
| --- | --- | --- | --- |
| I01 | D; review A | **Integrated in #7.** Review checklist: private/group flow, human controls, safe read-only inspection and optional UI tests; preserve functionality without UI expansion | M0 |
| I02 | B; review A | **Integrated in #8.** Review checklist: repository/branch/path binding, approval/release, uncertainty and local push checks; retain “GitHub not validated” status | I01 integration |
| I03 | C; review A | **Integrated in #9.** Review checklist: outcome classes, counts, timing, live/not-configured distinction and report evidence | I02 integration |
| I04 | A + D review | Enable a small real CI workflow using the existing template when the owner can install it; expose actual core/UI results and explicit skips | Owner credential with required workflow scope; independent of feature coding |
| A01 | A | Validate the issued allowed model's real structured request/tool-result cycle with explicit call/time/token limits; sanitize credentials | Issued access and authorized budget |
| A02 | A | Publish one shared runtime/config interface for UI and evaluation: provider, roles, tools, memory mode, limits and acceptance policy | M1; coordinate B/C/D |
| A03 | A | Demonstrate live high-level decomposition/role negotiation and specialist-to-specialist delegation; produce a complete trace rather than fixed scripted role choices | A01/A02 |
| A04 | A + C review | Define child acceptance: independently verify supported tasks and yield explicit trusted review for others; resume parent only with valid evidence | A02; C01 |
| B01 | B | Add real search with source URL/retrieval evidence, bounded response/time and safe network scope; reject unsupported/local targets and handle failures | A02 tool contract; approved search access if needed |
| B02 | B | Read/retrieve useful text from search results and hand off cited, bounded material; retrieved instructions cannot grant permissions | B01 |
| B03 | B | Provision a narrow runtime Git credential path and designated test repo/branch; demonstrate real GitHub commit/push plus remote SHA verification | I02; explicit target/credential authorization |
| B04 | B | Exercise changed binding, denied approval, non-fast-forward, failed network and uncertain external effects; do not retry an unknown push blindly | B03; A wiring |
| C01 | C | Define development positive/negative cases and independent acceptance; report separate root/subtask completion and assignment-to-final time, failures and human waits; show expected/executed/blocked/not-configured counts rather than hiding unrun official cases | I03 |
| C02 | C + A wiring | Generate candidate experience from actual outcomes, preserve conditions/provenance, and provide scoped retrieval/use to a later live task | A02; existing memory APIs |
| C03 | C | Validate distinct agents/conversations/namespaces, contradictory evidence, selected-use outcomes and fresh/reset memory behavior | C02 |
| C04 | C | Version result manifests and comparison guards: dataset/case contents, model, prompts, tools, budgets, intervention rules and initial memory must be compatible | C01/A02 |
| C05 | C | Run authorized development memory ON/OFF and single/multi-agent comparisons; preserve failures and report actual gains/regressions/costs | M3; C03/C04; authorized model budget |
| D01 | D | Submit a real human task through the common runtime; display state and blockers without treating an offline task as completed | I01/A02 |
| D02 | D | Exercise private/group messages, clarification/restart, approval vs release vs verified effect, denial and unresolved effects | D01; A/B interfaces |
| D03 | D | Show task tree, actual tool/evaluation results and artifact receipts; protect private boundaries and redact credentials; remove duplicate scoring/orchestration | D01; C result contract |
| A05 | A | Integrate real retrieval, code execution, checked handoff and Git in a bounded development task; verify failures/partial outcomes remain visible | A03/A04/B02/B03/D02 |
| A06 | A | Review task/role/tool isolation and bounded recovery; improve failed-step repair where development evidence warrants it | M3 candidate |
| D04 | D; all verify | Clean-environment installation/run instructions and a minimal repeatable demo; main must run without optional UI dependencies | M3 |
| C06 | C | Prepare dataset adapter/result manifests before release; map official tasks/rules when supplied, without substituting development cases | M4; issued protocol |
| A07 | A; all review | Freeze release/config, triage only necessary fixes, and run required integration/regression checks on the final revision | M4 |
| S01 | All; C coordinates results | Run official evaluation, preserve full task denominators, timing, raw outcomes and failures under the issued rules | C06/A07; issued set |
| S02 | All; A/D coordinate delivery | Final routing/memory/sandbox architecture, results/failure/memory analysis, week-13 presentation, authentic commit evidence and repository submission | Official outputs and actual instructor schedule |

Some existing seeds still need explicit completion: #8 proves local bare-remote pushing rather than GitHub; #9's live driver does not yet wire all tool backends and leaves child proposals to trusted review; its comparison helper is not a complete matched/repeated experiment protocol. Use these as integration tasks, not reasons to discard the PRs. Single/multi-agent and memory ON/OFF are our proposed evidence methods; the announcement requires completion/time reporting and memory evolution, not these exact experiment layouts.

Automatic replacement of terminally failed child tasks, a full dependency DAG, semantic memory merging, additional languages, and more elaborate UI are evidence-driven extensions. They must not delay mandatory coverage merely because they sound more research-oriented.

## 6. Contracts that prevent duplicate Codex work

Agree these before parallel edits: A owns runtime entry/config, task/request lifecycle, event and tool registration; B owns retrieval/Git backend request/result contracts; C owns memory and evaluation-result contracts; D owns display/controller adaptation. Record schema/version changes in the relevant task, notify downstream owners, and integrate them through one editor. A contract can initially be a documented callable/result shape; it does not require a new abstraction framework.

The current evaluator imports live role setup from the TUI controller. A/C/D should converge on a shared runtime configuration entry rather than creating different role/tool policies for CLI, TUI and evaluation. Evaluation should consume the backend and the UI should display evaluation results; neither should silently define a second execution or scoring path.

Recommended task card:

```text
ID and one owner:
Starting main revision / dependency PR:
Requirement and observable result:
Files owned by this task:
Files/interfaces that must not change independently:
Acceptance checks (including a failure/negative case where relevant):
Required external configuration / authorized budget:
Done when: implementation + relevant checks + evidence + reviewer + merged main.
```

Recommended Codex task preamble:

```text
Read AGENTS.md, README.md, docs/requirements.md, docs/team-roadmap.md and task <ID>.
Implement only this task's accepted scope on a dedicated branch.
Inspect current main and dependencies first; reuse existing modules.
Do not reimplement another workstream, change shared interfaces, or expand UI scope.
If shared wiring is required, describe the needed contract and coordinate its owner.
Report actual checks, skipped checks, external dependencies and remaining limitations.
```

Use one active branch/task per owner, short focused PRs, and a different reviewer. A push creates remote work; a PR proposes integration; only a verified merge changes main. For this existing stack, use its dependency order; for new independent tasks, start from updated main. Do not force-push a teammate's branch, silently rebase another person's work, or use a shared author identity. Passing tests do not automatically authorize external effects or prove the instructor's metrics.

Once agreed, mirror the active task rows into GitHub Issues/milestones with one assignee each. This roadmap does not itself create issues, assignments or permission changes; GitHub is authoritative for PR state. Before a session begins, its owner should claim the task in the common register; before switching workstreams, finish or explicitly hand off the current task. Keep documents concise and evidence-focused; README and architecture edits should follow the modules they describe, not become four conflicting status reports.

## 7. Decisions and dependencies still outside the code

- Choose who occupies A/B/C/D and confirm `jingran-jupiter` accepts the invitation. Public names need not map to personal background.
- Confirm the issued provider/model/key/quota and spending limits before live experiments. A ChatGPT/Codex development subscription is not the runtime model credential.
- Confirm exact submission/test-release dates, the minimum accepted per-agent sandbox boundary, and human intervention/memory-reset/repeated-run rules for official evaluation.
- Select an explicitly authorized GitHub test target and runtime credential scope; authorization to maintain this development repository is not a credential-provisioning mechanism for autonomous runtime tools.
- Agree the proposed minimal interface scope and shared contracts. The next work should reuse the integrated modules and cover missing required capabilities, rather than produce another dashboard or Git backend.
