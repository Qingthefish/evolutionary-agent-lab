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
