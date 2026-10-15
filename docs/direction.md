# Direction and delivery scope

Status: implementation recommendation, not an instructor-issued rubric or an approved architecture.

## Primary authority

The instructor's final-project announcement defines the objective and mandatory boundaries. Personal experience and other courses are optional context. They must not replace required capabilities, change the model-provider restriction, or add unnecessary scope. Human team allocation is deferred.

Build a general multi-agent collaboration platform. Do not require selection of an industry vertical before starting. The unknown standardized test set makes general search, files, code, execution, and Git capabilities important.

## Recommended emphasis

Reliable execution with observable completion and bounded recovery. First cover every announcement requirement; then measure whether collaboration and experience memory improve results. Context compression, typed proof cards, and domain simulators are optional extensions, not core implementation commitments.

## Concrete development examples

1. Search official documentation, implement and test a small text-processing tool in isolated workspaces, write Markdown usage instructions, and commit/push to a designated test branch after any applicable approval.
2. Inspect an existing small repository, diagnose a failing test, repair the implementation, verify the result, and produce a change report.
3. Execute an ambiguous task, ask a concrete clarification, persist the response, and resume; separately exercise a critical operation requiring approval before execution.

These are development and demonstration tasks, not predictions of the instructor's test set. A platform-change assistant was an earlier candidate demonstration only; it is not the project objective.

## Proposed minimal design

- A coordinator and a small set of specialists with distinct tools, prompts, and private memory. Capabilities may be predefined, but task allocation, role negotiation, specialist delegation, and reassignment must occur at runtime rather than as a fixed script.
- A minimal text interface supporting private/group conversations, status, and human replies, plus a batch evaluation entry point.
- Enforced per-agent execution sandboxes and private file systems; explicit transfer of shared artifacts. A directory naming convention alone is insufficient.
- Durable task state, bounded retries, and verification of tool outputs. A model saying done is insufficient evidence of completion.
- Small persistent per-agent experience records: conditions, failure, attempted fix, verification, and provenance. Retrieve validated lessons for new tasks; do not reuse an old action authorization.
- DeepSeek or HKGAI adapter and a test double clearly restricted to offline engineering checks.

Implementation details remain provisional. More agents, a vector database, model training, complex negotiation protocols, and elaborate UI are not required by the announcement.

## Delivery gates

1. One real-model task runs end to end with delegated work, real tools, verified outputs, and measured time. This vertical slice alone is not full course compliance.
2. Cover every requirement in requirements.md, including private/group interaction, specialist-to-specialist assignment, clarification/approval, isolation, file CRUD, search, code execution, Git, and per-agent learning. Exercise failures and denied actions as well as successful paths.
3. Freeze a development protocol and run controlled comparisons: single versus multiple agents with comparable tools and budgets, then experience memory off versus on for future tasks. Report completion and elapsed time, including failures. Additional comparisons need a specific hypothesis.
4. Apply the official test protocol when released; produce architecture documentation, performance/failure/memory analysis, commit evidence, and presentation.

## Feasibility and dependencies

This is a substantial but bounded engineering project. Main uncertainties are provider tool-call behavior and quotas, local sandbox runtime, long-task reliability, and the unseen test distribution. Validate these early. Current files are documentation only; no runtime, sandbox, or model integration has been validated.

Live-model validation requires an allowed provider credential. Offline fixtures can advance implementation but cannot establish completion rate or learning effectiveness. Sandbox implementation depends on available runtime support and the instructor's minimum boundary. No grade or universal task success is guaranteed by this plan.

## Other coursework

ARIN 5203 evidence-audit work and the ARIN 5305 AttnCompress reading may inform optional improvements. Do not copy code, data, reports, or results across submissions without checking applicable rules and recording approved reuse. Other-course local-model results are not evidence for this runtime.

## Open administrative decisions

- Repository: `Qingthefish/evolutionary-agent-lab`; public visibility was explicitly confirmed by the owner on 2026-10-15.
- Exact deadlines and the announcement's conflicting three weeks versus 3/1 weeks test-release wording.
- Evaluation rules for human waiting, repeated runs, and memory persistence.
- Allowed provider endpoint/model/quota and required sandbox boundary.
