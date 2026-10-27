# Course requirements and acceptance evidence

Source: instructor announcement supplied by the user, “Final Project Specification: Evolutionary Multi-Agent Collaboration System”, posted 2026-10-14. This is a working interpretation, not an additional instructor rubric. Acceptance examples below are proposed checks.

| ID | Requirement | Proposed acceptance evidence |
| --- | --- | --- |
| R01 | Agent-to-human private messages and multi-agent + human group chat | Separate private and group conversations with explicit membership and message routing |
| R02 | Autonomous task decomposition, role negotiation, delegation, and agent-to-agent assignment | Live trace of a high-level task decomposed and a specialist assigning or transferring a subtask |
| R03 | Proactive human clarification and permission before critical actions | Missing-information and critical-action cases pause before side effects and resume after an applicable human response |
| R04 | Each agent owns memory and improves from successes/failures | Independent memory records and controlled future-task comparison with learning enabled/disabled |
| R05 | Each agent has a private sandbox and dedicated file system | Cross-agent access, traversal, and symlink escape checks; explicit artifact transfer |
| R06 | Internet search and data retrieval | Real search/retrieval trace with cited sources and bounded failure handling |
| R07 | File read, generation, update, deletion | Observable file changes inside the authorized workspace |
| R08 | Code writing, testing, execution | Generated or modified source, actual execution results, and independent validation |
| R09 | Git commit and push to GitHub | Actual commit and remote branch verification in a designated test repository |
| R10 | Documents use .md/.txt; no complex document-format work | Supported document inputs/outputs and stated format boundary |
| R11 | Minimal functional interface | Functional private/group interaction, task status, and clarification/approval controls |
| R12 | DeepSeek or HKGAI only; OpenAI/Anthropic API prohibited | Explicit provider configuration and live evaluation metadata |
| R13 | Automatic task completion rate and execution time | Goal/subtask outcomes checked against observable artifacts; end-to-end duration including failed runs |
| R14 | Standardized final dataset | Versioned evaluation against instructor-provided tasks under the issued protocol |
| R15 | GitHub codebase and ongoing collaborative history | Repository link and commit-history screenshots proving significant contributions by every member |
| R16 | Architecture document | Routing, memory/evolution, and sandbox design |
| R17 | Performance report and presentation | Completion/time metrics, failure analysis, memory evolution; presentation in week 13 |

## Dates and unresolved wording

- Preferred team size: 2–4. Announcement says members finalized by the end of next week; exact date is not specified.
- Final test set: one paragraph says exactly three weeks before final submission.
- Report paragraph instead refers to mid/final test sets released in the last “3/1 weeks”. Clarify the schedule.
- Final report is due after week 13; exact due date is not supplied.
- The original announcement said dedicated model keys would be distributed later. On 2026-10-26 the instructor's [API announcement](https://canvas.ust.hk/courses/73253/announcements/651390) directed students to the restricted [API Information page](https://canvas.ust.hk/courses/73253/pages/api-information), which now gives the HKGAI address, model and a credential. Do not copy its credential into project documentation. The inspected page does not state quota, pricing or reset policy.

## Questions affecting design

- Minimum accepted sandbox boundary and meaning of heterogeneous agents under one provider.
- Human participation during standardized evaluation, and whether waiting time counts toward execution time. Until clarified, record both total wall time and human-wait time separately without excluding either from reports silently.
- Whether memory persists between final test tasks and whether repeat runs are allowed.
- HKGAI address/model are supplied; actual credential validity, quota, tool-call compatibility and available search access still need confirmation and bounded validation.
- Development AI-tool policy and reuse/disclosure rules across courses.

## Implementation evidence audit (2026-10-21)

Checked against the original announcement text supplied by the owner, the current runtime/tool allowlists, task policies, tests, evaluation entry points and submission files. This is an evidence map, not an instructor-issued score or a second task register. Source files and passing fixtures do not prove live model ability; Roadmap cards retain owners, history and acceptance.

D02 console evidence refreshed on 2026-10-22; the instructor requirements and unresolved official rules are unchanged.

D03 approval/effect evidence refreshed on 2026-10-23: exact request receipts replace time-order inference; raw history and instructor requirements remain unchanged.

A01 evidence refreshed on 2026-10-26 following the instructor's API release. An owner-authorized HKGAI smoke used three real requests (create/read/final), retained the issued model, actual usage/time and passed independent file verification. This validates a connection/tool cycle; multi-agent behavior, human interaction, learning and official task performance retain their separate acceptance.

A03 preparation on 2026-10-26 decouples peer delegation/messages from optional external tools. Two separately authorized real attempts stopped before a completion was received (30-second timeout; transport failure at about 81 seconds with a 90-second setting). No model-chosen delegation or task-tool effect was observed. Provider processing/billing are unknown; latency, rate/concurrency limits and recommended tool-call settings need confirmation before another controlled trial. This does not establish a cause or change the instructor's requirements.

2026-10-27 follow-up: four read-only diagnostic cases returned valid responses; this does not retroactively identify the prior transport failure cause. A separate live workflow recorded model-chosen coordinator-to-writer/editor delegation, actual snapshot handoff and one owner-reviewed draft. It stopped at editor review after eleven of twelve allowed requests; the root goal, negotiation and further assignment coverage remain unaccepted. These are specific development observations, not an overall completion percentage or official score. Specialist-to-specialist delegation is an additional chosen coverage case, not a separate instructor-issued grading rule. Routine results may use predeclared independent automatic checks; the announcement does not require a manual approval button for every ordinary output.

| Requirement | Evidence currently available | Remaining acceptance / Roadmap |
| --- | --- | --- |
| R01 — private/group human communication | Conversation membership, private/group creation, scoped messages, console chat/feed/agent assignment and minimal interface checks; scripted agent-to-human private messages verified | Verify actual live interactions and usability; [D02](team-roadmap.md#d02) |
| R02 — autonomous decomposition/negotiation/delegation | Model-facing delegation/input handoff, role eligibility, shared budgets and specialist routing; independent collaboration capability enables peer delegation/messages without optional backends; scripted boundary checks | High-level live goal with model-chosen plan and specialist-to-specialist delegation; initial real A03 attempts stopped at the transport boundary; [A01](team-roadmap.md#a01), [A03](team-roadmap.md#a03), [A04](team-roadmap.md#a04) |
| R03 — proactive clarification/critical approval | Durable waits, exact-action grants, separate release, denial/uncertainty handling and restart checks; console request views and scripted clarification-to-verification round trip | Actual live proactive decisions and interface interaction; [D02](team-roadmap.md#d02), [B03](team-roadmap.md#b03) |
| R04 — private memory and improvement from history | Actual outcome provenance, private candidate retrieval/selection, contradictions/retirement; frozen-training comparison/reset engineering | Real later-task use and measured effects, including regressions; [C02](team-roadmap.md#c02), [C05](team-roadmap.md#c05). Logging or script success is insufficient |
| R05 — private sandbox/filesystem | Task/actor-bound no-follow file broker; digest-pinned restricted Docker execution and real boundary checks | Live combined behavior and confirmation of instructor's minimum isolation interpretation; [A05](team-roadmap.md#a05), [A06](team-roadmap.md#a06) |
| R06 — internet search/retrieval | Actual public query/retrieval smoke evidence and bounded cited handoff; no document-format expansion | Live model use, relevance/availability and failure handling in general tasks; [A05](team-roadmap.md#a05), [B04](team-roadmap.md#b04) |
| R07 — Read/Generate/Update/Delete | File broker/gateway implement all four. B05 adds opt-in `--enable-delete` / `LiveConfig.enable_delete` to formal roles using the same exact-action approval/release path; mocked-provider checks exercise actual deletion, denial, stale versions/requests, task ownership and restart | Final real-model CRUD smoke under the explicitly enabled configuration; [B05](team-roadmap.md#b05), [A05](team-roadmap.md#a05), [D02](team-roadmap.md#d02). Version-1 run-plan JSON still keeps deletion disabled |
| R08 — code writing/testing/execution | Actual Docker code execution, bounded exports and independent positive/negative integration checks | Live code tasks and task-specific independent oracles; file-property checks alone do not prove arbitrary code correctness; [A04](team-roadmap.md#a04), [A05](team-roadmap.md#a05), [C06](team-roadmap.md#c06) |
| R09 — commit/push to GitHub | Approved local-remote push, scoped credential injection and remote-SHA checks | Runtime push to a designated GitHub test branch with a narrow credential, then actual remote verification; developer pushes are different evidence; [B03](team-roadmap.md#b03), [B04](team-roadmap.md#b04) |
| R10 — MD/TXT documents | Plain-text document tooling and Markdown reports; JSON/SQLite are internal configuration/state | Maintain this boundary in future tools and official mapping; no PDF/DOCX/PPT parser project |
| R11 — minimal functional UI | Standard-library console and optional Textual controls over common backend | Teammate clean setup and live task/human round trip; [D01](team-roadmap.md#d01), [D02](team-roadmap.md#d02), [D04](team-roadmap.md#d04) |
| R12 — allowed model backbone | Explicit DeepSeek and issued HKGAI HTTP adapters; fixed separate hosts and shared setup with no provider fallback. Real HKGAI create/read/final cycle passed independent file checks with observed model/usage/time | Confirm quota and authorize subsequent live trials; connection acceptance in [A01](team-roadmap.md#a01) does not establish the other required model behaviors |
| R13 — automatic completion/time | Separate goal/subtask outcomes, failures/missing evidence, assignment-to-final-status/observed time and waits | Align official final-output timing, intervention and scoring semantics when issued; [C06](team-roadmap.md#c06). No course performance established |
| R14 — standardized test set | General development case loader and retained manifests | Actual official format/protocol adapter and full prescribed run; [C06](team-roadmap.md#c06), [S01](team-roadmap.md#s01) |
| R15 — continuous collaborative history/screenshots | Public repository and preserved actual commits/PRs; audit observed two contributor accounts | Every member's significant ongoing code contribution and final commit-history screenshots; collaborator access alone is insufficient; [S02](team-roadmap.md#s02) |
| R16 — architecture document | [architecture.md](architecture.md) explains routing, memory, isolation, permissions and evaluation | Reconcile the final release configuration and live changes; [A07](team-roadmap.md#a07), [S02](team-roadmap.md#s02) |
| R17 — test report/presentation | Development Markdown reports and failure/provenance records | Official mid/final results, failure/memory discussion and week-13 presentation/final report; [S01](team-roadmap.md#s01), [S02](team-roadmap.md#s02) |

The new memory protocol supports development ON/OFF preparation. A single/multi-agent comparison remains [C07](team-roadmap.md#c07), an agreed supporting experiment rather than an additional announcement requirement. CI is useful engineering support, not a stated instructor requirement. Exact official dates, scoring, memory persistence/repeats and human waiting rules remain the unresolved questions above.
