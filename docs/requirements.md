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
- Dedicated model API keys will be distributed per team later in the semester.

## Questions affecting design

- Minimum accepted sandbox boundary and meaning of heterogeneous agents under one provider.
- Human participation during standardized evaluation, and whether waiting time counts toward execution time. Until clarified, record both total wall time and human-wait time separately without excluding either from reports silently.
- Whether memory persists between final test tasks and whether repeat runs are allowed.
- Model identity, quota, tool-call support, endpoint, and available search access.
- Development AI-tool policy and reuse/disclosure rules across courses.

## Implementation evidence audit (2026-10-21)

Checked against the original announcement text supplied by the owner, the current runtime/tool allowlists, task policies, tests, evaluation entry points and submission files. This is an evidence map, not an instructor-issued score or a second task register. Source files and passing fixtures do not prove live model ability; Roadmap cards retain owners, history and acceptance.

| Requirement | Evidence currently available | Remaining acceptance / Roadmap |
| --- | --- | --- |
| R01 — private/group human communication | Conversation membership, private/group creation, scoped messages and minimal interface checks | Verify actual live interactions and usability; [D02](team-roadmap.md#d02) |
| R02 — autonomous decomposition/negotiation/delegation | Model-facing delegation/input handoff, role eligibility, shared budgets and specialist routing; scripts exercise the paths | High-level live goal with model-chosen plan and specialist-to-specialist delegation; [A01](team-roadmap.md#a01), [A03](team-roadmap.md#a03), [A04](team-roadmap.md#a04) |
| R03 — proactive clarification/critical approval | Durable waits, exact-action grants, separate release, denial/uncertainty handling and restart checks | Actual live proactive decisions and interface interaction; [D02](team-roadmap.md#d02), [B03](team-roadmap.md#b03) |
| R04 — private memory and improvement from history | Actual outcome provenance, private candidate retrieval/selection, contradictions/retirement; frozen-training comparison/reset engineering | Real later-task use and measured effects, including regressions; [C02](team-roadmap.md#c02), [C05](team-roadmap.md#c05). Logging or script success is insufficient |
| R05 — private sandbox/filesystem | Task/actor-bound no-follow file broker; digest-pinned restricted Docker execution and real boundary checks | Live combined behavior and confirmation of instructor's minimum isolation interpretation; [A05](team-roadmap.md#a05), [A06](team-roadmap.md#a06) |
| R06 — internet search/retrieval | Actual public query/retrieval smoke evidence and bounded cited handoff; no document-format expansion | Live model use, relevance/availability and failure handling in general tasks; [A05](team-roadmap.md#a05), [B04](team-roadmap.md#b04) |
| R07 — Read/Generate/Update/Delete | File broker/gateway implement all four. B05 adds opt-in `--enable-delete` / `LiveConfig.enable_delete` to formal roles using the same exact-action approval/release path; mocked-provider checks exercise actual deletion, denial, stale versions/requests, task ownership and restart | Final real-model CRUD smoke under the explicitly enabled configuration; [B05](team-roadmap.md#b05), [A05](team-roadmap.md#a05), [D02](team-roadmap.md#d02). Version-1 run-plan JSON still keeps deletion disabled |
| R08 — code writing/testing/execution | Actual Docker code execution, bounded exports and independent positive/negative integration checks | Live code tasks and task-specific independent oracles; file-property checks alone do not prove arbitrary code correctness; [A04](team-roadmap.md#a04), [A05](team-roadmap.md#a05), [C06](team-roadmap.md#c06) |
| R09 — commit/push to GitHub | Approved local-remote push, scoped credential injection and remote-SHA checks | Runtime push to a designated GitHub test branch with a narrow credential, then actual remote verification; developer pushes are different evidence; [B03](team-roadmap.md#b03), [B04](team-roadmap.md#b04) |
| R10 — MD/TXT documents | Plain-text document tooling and Markdown reports; JSON/SQLite are internal configuration/state | Maintain this boundary in future tools and official mapping; no PDF/DOCX/PPT parser project |
| R11 — minimal functional UI | Standard-library console and optional Textual controls over common backend | Teammate clean setup and live task/human round trip; [D01](team-roadmap.md#d01), [D02](team-roadmap.md#d02), [D04](team-roadmap.md#d04) |
| R12 — allowed model backbone | Explicit DeepSeek HTTP adapter; no alternate provider fallback | Configure issued provider/model/key/quota and verify one real tool cycle; HKGAI adapter depends on its issued specification; [A01](team-roadmap.md#a01) |
| R13 — automatic completion/time | Separate goal/subtask outcomes, failures/missing evidence, assignment-to-final-status/observed time and waits | Align official final-output timing, intervention and scoring semantics when issued; [C06](team-roadmap.md#c06). No course performance established |
| R14 — standardized test set | General development case loader and retained manifests | Actual official format/protocol adapter and full prescribed run; [C06](team-roadmap.md#c06), [S01](team-roadmap.md#s01) |
| R15 — continuous collaborative history/screenshots | Public repository and preserved actual commits/PRs; audit observed two contributor accounts | Every member's significant ongoing code contribution and final commit-history screenshots; collaborator access alone is insufficient; [S02](team-roadmap.md#s02) |
| R16 — architecture document | [architecture.md](architecture.md) explains routing, memory, isolation, permissions and evaluation | Reconcile the final release configuration and live changes; [A07](team-roadmap.md#a07), [S02](team-roadmap.md#s02) |
| R17 — test report/presentation | Development Markdown reports and failure/provenance records | Official mid/final results, failure/memory discussion and week-13 presentation/final report; [S01](team-roadmap.md#s01), [S02](team-roadmap.md#s02) |

The new memory protocol supports development ON/OFF preparation. A single/multi-agent comparison remains [C07](team-roadmap.md#c07), an agreed supporting experiment rather than an additional announcement requirement. CI is useful engineering support, not a stated instructor requirement. Exact official dates, scoring, memory persistence/repeats and human waiting rules remain the unresolved questions above.
