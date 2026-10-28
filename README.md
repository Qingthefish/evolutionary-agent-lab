# ARIN 5202 / MAIE 5221 Final Project

Evolutionary Multi-Agent Collaboration System

## Status

**Current position — 2026-10-29:** one declared-contract HKGAI workflow completed and passed an independent audit of numeric outputs, real snapshot handoffs, the checker's read and the final report. Another numerically correct run failed its handoff audit; original reports are preserved rather than counted as two fully compliant runs. The `received_from` criterion enforces identity-bound delivery/read evidence during trusted acceptance; dependent child delegation now also requires verified source inputs before scheduling. Final regression: 447 checks passed, including actual isolated execution and terminal UI checks. Open-ended collaboration, full required live-tool coverage, measured learning and official evaluation remain separate gates. Trial caps are local limits; course quota remains unknown. See the [Roadmap](docs/team-roadmap.md) for acceptance and retained evidence.

2026-10-17: the current foundation implements durable workflow state, conversation membership checks, delegation records, human pause/resume, exact-action approval release, and task accounting. Controlled UTF-8 file tools enforce task ownership and descriptor-based paths, transfer artifact snapshots, and check actual text before completion. Per-agent candidate memory captures observed outcomes with provenance, scoped lexical retrieval, selected-use outcomes, exact duplicate merging, and retirement. A DeepSeek HTTP/protocol adapter and allowlisted tool gateway now connect structured requests to these tools, with persisted call reservations and a per-task tool-call cap. A durable single-task runner now repeats model/tool turns, preflights batches, pauses for humans, retains user constraints across restart, routes final proposals to independent verification, and stops on persisted attempt, reported-token, duration, or repeated-outcome limits. Deterministic CLI fixtures exercise this infrastructure. A durable cooperative multi-agent scheduler now routes delegated tasks to configured roles, retains goal constraints, waits for independently checked child results, and returns explicit artifact offers to parents. Persisted task-tree limits bound total tasks, depth, model attempts, reported tokens, tool calls, and assignment-to-completion time. **Live-provider validation, demonstrated autonomous negotiation/replanning, learning improvement, and model-performance results remain pending.** An opt-in Docker Python backend now performs actual isolated execution with pinned input/image versions, resource limits, explicit text export, and confirmed cleanup; it has separate real-container integration checks, including scheduler-driven delegation, actual execution, artifact handoff, and rejection of a matching file after failed execution. An optional Textual terminal control center (`python -m agent_lab.tui`) now exposes conversations, task trees, execution evidence, artifacts, memory, and approvals over these APIs, with labelled offline scenarios. The project repository is [Qingthefish/evolutionary-agent-lab](https://github.com/Qingthefish/evolutionary-agent-lab).

The instructor's announcement is the primary scope authority. Build a general multi-agent collaboration platform with autonomous delegation, human interaction, private sandboxes, per-agent memory and learning, required tools, and automatic completion/time evaluation. The proposed implementation emphasis is reliable execution with observable results and bounded recovery. A business vertical is not required to start the project.

2026-10-18: UI and live evaluation now use one shared runtime setup for roles, tools, task/tree limits and acceptance. Original task constraints and root text expectations are persisted and restored across restart; conflicting policies/configurations are rejected. This is validated through offline configuration contracts, not live-model performance.

2026-10-21: trusted exact-text child criteria now use that shared runtime policy. Offline checks exercise failed child verification, concrete repair feedback, restart, checked handoff and parent completion within existing budgets. Unknown/ambiguous child proposals still pause for trusted review. A04 remains in progress until its final live check; this is no evidence of autonomous-model performance.

2026-10-21: optional runtime services now connect public HTTPS search/retrieval, private candidate experience, isolated Python and trusted Git repositories to the shared scheduler. Specialists can delegate with input snapshots and read scoped coordination messages. A combined engineering fixture has exercised public retrieval, actual Docker execution, verified local-remote push, restart and later scoped memory selection. All model decisions in that fixture are scripted; live-model validation, actual GitHub runtime pushing and learning gains remain unestablished.

2026-10-21: opt-in failed-child replacement now retains failed history, original assignment/criteria and shared budgets. Denials, unreleased approvals and unknown effects cannot be bypassed with a retry. Independent data-only artifact criteria cover existence/absence, size, required text, JSON equality and SHA-256. Versioned development plans inspect cases/budgets without a key and require the reviewed fingerprint plus explicit authorization before model calls. These changes do not establish general replanning, arbitrary code/report correctness, live learning or official performance.

2026-10-21: a separate frozen-experience development protocol now records common training, copies the identical candidate memory into fresh ON/OFF probe workflows, hides training chat and copies no training files and grants no inherited approval authority. Probe prompts/tools/budgets match except for memory search/selection; probes cannot teach later probes. Training failures/costs and all planned probes stay visible. Scripted and mocked-transport checks establish plumbing only; live learning gains and single/multi-agent comparison remain unvalidated. The [announcement audit](docs/requirements.md#implementation-evidence-audit-2026-10-21) and [Roadmap re-entry guide](docs/team-roadmap.md#re-entry-and-next-claims) distinguish these gates and retain completed work.

2026-10-21: opt-in `--enable-delete` now exposes the existing exact-version deletion request to configured live roles. Human approval and separate release remain mandatory. Checks cover actual file effects, refusal paths, restart and unchanged disabled configurations using mocked provider responses; the real-model smoke test remains pending.

2026-10-26: the instructor released HKGAI connection information. Explicit `--provider hkgai` selects the issued service for shared console/TUI, scheduler and experience/evaluation setup. An owner-authorized real connection check used three requests: `create_text`, `read_text`, then a final proposal. Independent file checks passed with the issued model identity and actual usage/time retained. The plan capped four attempts and 512 output tokens per request; no fourth request or automatic retry was used. This establishes one provider/tool cycle, not live multi-agent collaboration, learning gains or official-test performance. Quota confirmation and subsequent run budgets remain separate. No credential is included in the repository.

## First 10 minutes / 新成员从这里开始

1. Clone this repository and open **the repository root** in Codex. This makes the project `AGENTS.md` available to the coding assistant. Accept the collaborator invitation before pushing changes.
2. Read [course requirements](docs/requirements.md), [delivery scope](docs/direction.md), and the [Roadmap task cards](docs/team-roadmap.md). The announcement takes priority; A/B/C/D are technical areas, not assigned people.
3. Use the read-only starter prompt below. Check Codex's summary against the files before selecting work.
4. Before feature development, claim one Roadmap card in WeChat and have the coordinator record it on main. Then create a focused branch and follow [CONTRIBUTING.md](CONTRIBUTING.md).
5. Use Python 3.12 or newer and run the offline checks below. No API key, model download, package installation, or external service is needed. The demo is a scripted plumbing check, not an autonomous-agent demonstration.

Useful onboarding work includes checking requirements, running the fixture, reviewing the state/approval contract, and proposing small development tasks. Do not report planned capabilities as implemented.

```text
Read AGENTS.md, README.md, docs/requirements.md, docs/direction.md,
docs/team-roadmap.md and CONTRIBUTING.md. List the instruction sources you
loaded and any conflicting guidance. Summarize the mandatory course requirements,
the accepted baseline, missing live capabilities, and the relevant source modules.
Inspect the Roadmap's dependencies and recorded claims before suggesting a small
available task; do not assign it to anyone. State uncertainties explicitly.
Do not modify files or call external services yet. Feature coding starts only
after the agreed claim is recorded on main and I name that card.
```

Git transfers versioned files, not another member's Codex or WeChat conversation. Keep shared decisions in the existing project documents. Codex [discovers project instructions through AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md); start a fresh session at the repository root after updating those instructions. Instructions guide the assistant, while scoped claims, review and appropriate checks verify the work. Do not assume a correct summary or compliance without checking it.

```bash
git clone https://github.com/Qingthefish/evolutionary-agent-lab.git
cd evolutionary-agent-lab
```

## Source map

Use these entry points to inspect the current implementation; a module's presence does not establish live-model or official-test performance. The [architecture](docs/architecture.md) describes contracts and limits; the [Roadmap](docs/team-roadmap.md) records acceptance and remaining work.

| Area | Entry points |
| --- | --- |
| Durable tasks, conversations and evidence views | [core.py](agent_lab/core.py), [queries.py](agent_lab/queries.py), [inspection.py](agent_lab/inspection.py) |
| Model protocol and allowed tool dispatch | [protocol.py](agent_lab/protocol.py), [deepseek.py](agent_lab/deepseek.py), [gateway.py](agent_lab/gateway.py) |
| Shared live configuration, task policies and CLI flags | [runtime.py](agent_lab/runtime.py) |
| Task execution, delegation and shared limits | [runner.py](agent_lab/runner.py), [scheduler.py](agent_lab/scheduler.py), [delegation.py](agent_lab/delegation.py), [budget.py](agent_lab/budget.py) |
| Controlled files, public text retrieval and private candidate memory | [files.py](agent_lab/files.py), [provenance.py](agent_lab/provenance.py), [retrieval.py](agent_lab/retrieval.py), [memory.py](agent_lab/memory.py) |
| Python sandbox and restricted Git operations | [sandbox.py](agent_lab/sandbox.py), [git_tools.py](agent_lab/git_tools.py) |
| Frozen experience trials and reset/provenance boundaries | [experience.py](agent_lab/evaluation/experience.py), [memory_protocol.py](agent_lab/evaluation/memory_protocol.py) |
| Terminal interface and development evaluator | [tui/](agent_lab/tui/), [evaluation/](agent_lab/evaluation/) |
| Checks and development cases | [tests/](tests/), [evaluation/dev/](evaluation/dev/) |

Generated transcripts, databases and reports belong in ignored `runs/`; preserve the original evidence and keep secrets out of commits.

## Run the offline foundation

From the repository root:

```bash
python3 -m unittest discover -s tests -v
python3 -m agent_lab demo
python3 -m agent_lab files-demo
python3 -m agent_lab memory-demo
python3 -m agent_lab protocol-demo
python3 -m agent_lab runner-demo
python3 -m agent_lab scheduler-demo
```

The demo creates a fresh ignored `runs/offline-*` directory containing a SQLite database, a verified fixture `note.txt`, and `report.json`. It closes/reopens the database while awaiting clarification, resumes, requests and consumes one exact approval, writes the fixed note, checks its contents, and completes a parent/child task pair. Human responses and delegation in this fixture are scripted. No model, arbitrary shell command, Git mutation, or network request is executed.

Use `python3 -m agent_lab demo --state-dir runs/my-first-demo` to choose a **new** run directory. Existing paths are rejected to preserve evidence. These six offline fixture reports explicitly contain `mode: offline_fixture`, `model_calls: 0`, and `benchmark_valid: false`. Their success fractions describe trusted workflow state, not course benchmark performance.

`files-demo` creates a separate `runs/files-*` directory. It creates/reads/updates/deletes controlled text, hands a snapshot from a writer task to a reviewer task, and checks both copies against trusted expected contents before completion. Source and received SHA-256 receipts must agree. It also demonstrates that code execution is refused when no process sandbox is configured. Its report explicitly says `process_sandbox: false`; script-driven file operations are not a sandbox or a model benchmark. The file broker currently requires POSIX descriptor-relative operations and a private root directory; unsupported systems fail closed.

`memory-demo` creates a separate `runs/memory-*` directory. An actual text check rejects the first scripted output. A candidate suggestion is attached to that failure, retrieved and selected by a later task owned by the same agent, and assessed after the later task passes its text check. The duplicate suggestion retains both source outcomes. The second output is explicitly written by fixture code, not learned by a model; the report states `learning_improvement_established: false`. This checks memory plumbing, not whether memory improves the course metrics.

`protocol-demo` creates a separate `runs/protocol-*` directory. Two explicitly synthetic provider responses pass through the DeepSeek response parser: a structured request creates a real controlled file, its tool result is returned in the next protocol request, and a final assistant message leaves the task running until a trusted text check succeeds. This fixture makes zero network/model calls, needs no key, and saves its transcript with `benchmark_valid: false`. It does not measure DeepSeek capability or autonomous collaboration.

`runner-demo` exercises a synthetic three-response loop: clarification pauses execution, the database is closed/reopened, a scripted human answer resumes the same task with its original constraints and budget, a real file is created, and an independent text verifier decides completion. The runner stores its transcript, requests, response metadata, known/unknown usage, and state in the ignored database. Attempts and reported token counts in this fixture are synthetic; `model_calls` and `api_network_calls` remain zero. This is one assigned task, not autonomous multi-agent scheduling.

`scheduler-demo` exercises a **fixed synthetic** coordinator → writer → editor delegation chain. It pauses at a child clarification, reopens the database, passes explicit file snapshots back through both parents, and independently checks each actual note before task completion. Distinct role instructions/tools and the original goal/constraints are supplied on every task. The saved report contains shared budgets, before/after restart states, and task accounting, with zero model/API calls and `autonomous_model_collaboration_established: false`. This proves scheduling and handoff plumbing, not autonomous planning or model capability. The scheduler has no fixed role sequence: these particular delegations come from the fixture's scripted responses. See [scheduler operation and limits](docs/architecture.md#cooperative-multi-agent-scheduler).

The provider code uses an explicitly selected DeepSeek or course-issued HKGAI endpoint, requires an explicit model ID, and disables network use by default. No alternate provider, local model, or synthetic fallback is selected automatically. Live use needs the corresponding credential, an authorized experiment budget, and validation against the selected endpoint/model. The runner caps per-task attempts and observed token usage; its token threshold is checked after a response and is not a strict billing cap. See [provider and gateway boundaries](docs/architecture.md#provider-protocol-and-tool-gateway).

Provider failures now retain a sanitized category and phase in a durable `provider_request_failed` event: timeout, DNS, TLS, connection or HTTP-protocol failure, response size or completion parsing. Raw exception reasons, URLs, headers and bodies are excluded. Actual localhost checks reproduce a malformed status line that previously escaped and left a task calling; it now records a terminal failure without retry. An error's request-processing flag remains conservative and never proves zero billing or permission to replay. Historical generic errors are preserved without inventing their missing cause.

2026-10-27: four separately authorized read-only provider probes returned valid completions, including the earlier full collaboration payload; no tools were executed by those probes, and the old failures' cause is still unknown. A separately authorized twelve-request workflow used eleven requests: the model selected writer/editor tasks, created an actual draft, resumed after one real human acceptance, and transferred checked snapshots to the editor and back. It is retained as partial at the editor-review boundary; the root goal did not complete. No specialist-to-specialist delegation or agent negotiation is claimed from this trace. Trial call limits are locally agreed test allowances, not the teacher's account balance or evidence of unlimited quota.

The offline checks have passed locally on Python 3.12 and 3.14. A [CI workflow template](docs/ci-workflow.yml) is provided for later installation as `.github/workflows/checks.yml`; it is **not enabled**, because the current Git push credential cannot add Actions workflows. No GitHub Actions result is claimed. Read [architecture and boundaries](docs/architecture.md) before connecting an executor or model.

## Run the terminal control center

An optional [Textual](https://textual.textualize.io/) dashboard exposes conversations, the live task tree and execution inspector, artifacts, candidate memory, approvals, and execution logs on top of the existing workflow, gateway, scheduler, and file broker. Textual is the only extra dependency; the core package and its tests remain standard-library only.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-tui.txt
.venv/bin/python -m agent_lab.tui
```

The default session directory `runs/tui-session` is reused across restarts, so conversations, tasks, approvals, and history persist. Offline mode is the default and is labelled in the header. It can create conversations, post messages, and create real tasks, but **a task created without a configured model stays pending**: no arbitrary request is completed offline. Dashboard scenarios (`chat`, `delegation`, `approval`, `memory`, `git`) drive the real workflow, gateway, file broker, approval release, and verifiers with scripted provider responses; their results are `offline_fixture` evidence with zero model calls. Approving an action only records the decision; a separate *Release & execute* step consumes it through `ToolGateway.release_approved` and shows the verified effect. Press `?` for shortcuts.

The Git tab (`Ctrl+G`) shows a disposable, scenario-created local repository and any repositories listed with `--git-config repos.json`. The `git` scenario has a scripted integrator commit a task note through the restricted Git tools and request a push; the push happens only after you approve the exact commit/branch/remote binding and release it, and the remote branch is then verified. No GitHub remote or credential is used. See [restricted Git tools](docs/architecture.md#restricted-git-tools).

Live mode must be requested explicitly (`--live --provider hkgai --model <id> --api-key-env <VAR>` for HKGAI; the compatible default remains `deepseek`); there is no fallback provider. Real-provider acceptance is recorded separately in A01. Both the TUI and evaluation `run` command share these flags, plus repeatable `--constraint`, `--max-output-tokens`, `--task-attempts` and `--tree-attempts`. Live flags are rejected without `--live`. The launcher reads only the named key variable; programmatic `LiveConfig` defaults to network disabled. Obtain the issued model/key and authorize a run budget before live execution. See [shared runtime setup](docs/architecture.md#shared-runtime-setup) and [control-center boundaries](docs/architecture.md#terminal-control-center).

## Run development evaluations

```bash
python3 -m agent_lab.evaluation list
python3 -m agent_lab.evaluation run
```

The harness loads development cases from `evaluation/dev/*.json`, runs each in a fresh state directory, computes independent acceptance checks (final task state, exact artifact text, absent files, verified remote branch, time limit) from persisted records and actual files, classifies failures, and writes `results.json` plus a Markdown `report.md` under the ignored `runs/evaluations/`. Offline cases execute fixed scripts and are reported as `offline_fixture` with `benchmark_valid: false`; negative-control cases check that the evaluator reports mismatches. The live case is reported as *not configured* (never as a success) until a DeepSeek/HKGAI runtime is configured. The same evaluator backs the control center's Evaluation tab (`F9`). These are development cases, not the instructor's held-out set; Memory ON/OFF comparison is an interface that refuses offline, unmatched, or unexercised-memory runs. The ordinary batch entry rejects memory-enabled labels before provider calls; use the separate frozen-experience protocol below for controlled memory trials. Interactive runtime memory remains explicitly configured.

Cases can also require uniquely identified descendant tasks, their states and actual artifacts, plus exact counts of persisted clarification/approval outcomes within the goal's task tree. Negative controls exercise wrong child results and missing/wrong human evidence even when the root output matches. Invalid/unknown criteria are rejected before execution; driver crashes do not count as detected controls. Full expected criteria and matched task/request evidence are retained in `results.json`. See the [case contract](docs/architecture.md#evaluation-harness-foundation) and [development definitions](evaluation/dev/).

For `live_scheduler` cases, optional `constraints` are combined with the CLI's original constraints and persisted in the shared task policy. Scripted fixtures reject custom constraints because they do not interpret arbitrary requests. Trusted root and supported child exact-text/structural/absence expectations use the same verifier factory in the UI API and evaluator. Child criteria select an exact assignee/title and must be independently supplied before execution. A success selector follows the active replacement attempt; every original failure remains in metrics/history. Expected failures and unsupported criteria retain review. Unknown, ambiguous or unsupported child proposals require trusted review. A root with configured child rules cannot pass by producing its own file while skipping required children. Optional runtime backends now require explicit flags and matching session-owned services. Without those settings, their tools stay disabled. Live batch evaluation can use configured web/Python/Git tools. The separate frozen-experience entry versions training/reset conditions; the ordinary batch entry still refuses memory-on labels. Actual live model/tool behavior and learning gains remain unvalidated.

Reports distinguish **contract acceptance** (including correct rejection behavior) from verified **goal completion** and **subtask completion**. They show expected/executed/blocked/unconfigured cases, missing evidence, task states, assignment-to-final-status time, unfinished elapsed time and cumulative per-task human waits. Failed/cancelled times remain visible; waits are not subtracted. The legacy JSON `completion_rate` remains the acceptance fraction for compatibility; use `goal_completion_rate` and `subtask_completion_rate` for task outcomes. Offline fractions remain fixture results.

Each run saves a fingerprinted manifest of full task/acceptance content, requested model, role prompts/tools/budgets, code/templates, intervention protocol and initial-memory reset conditions, plus observed model IDs and actual task/request evidence. Memory comparisons reject legacy/missing/corrupt or unmatched evidence, even if case IDs agree. The ordinary batch protocol uses a fresh empty memory store per case. Frozen-experience development trials use the separate protocol below; actual live learning evidence remains C02/C05 work. Fingerprints detect condition changes and do not authenticate results. See [evaluation evidence and comparison](docs/architecture.md#evaluation-evidence-and-comparison).

## Run a real task without the optional interface

The standard-library console uses the same task service as the TUI. No model call occurs when creating a task; an unconfigured task remains pending.

```bash
python3 -m agent_lab.console new --goal 'Prepare a cited Markdown explanation'
python3 -m agent_lab.console status
python3 -m agent_lab.console status --task TASK_ID
```

For a private conversation or a task addressed to a particular agent:

```bash
python3 -m agent_lab.console chat new --kind private --participant writer
python3 -m agent_lab.console chat list
python3 -m agent_lab.console new --chat CHAT_ID --assignee writer --goal 'Prepare a Markdown note'
python3 -m agent_lab.console message CHAT_ID 'Please clarify missing information before proceeding'
python3 -m agent_lab.console chat feed CHAT_ID
python3 -m agent_lab.console requests --pending
python3 -m agent_lab.console requests --request REQUEST_ID
```

Use `chat new --kind group` with repeated `--participant` values for a group; participants must already be registered actors, and the current human is added automatically. A private conversation contains exactly one human and one agent. `new --assignee` must name an agent member; omitting it retains the coordinator default. Conversations/messages do not execute tasks or answer requests. `requests --pending` lists unanswered requests addressed to the current human; approved requests awaiting release remain visible through `requests` or `requests --request ID`. Read views reuse conversation membership checks. `--human` selects a trusted local operator identity, not a login/authentication mechanism.

After the issued model/key and run budget are available, supply the same live flags when creating/advancing a live task or releasing/reviewing its actions. Set the named model-key variable outside the repository; never paste its value into a command argument or committed file.

```bash
python3 -m agent_lab.console --live --model ISSUED_MODEL --api-key-env AGENT_LAB_MODEL_KEY --enable-web --enable-memory new --goal 'Prepare a cited Markdown explanation'
python3 -m agent_lab.console --live --model ISSUED_MODEL --api-key-env AGENT_LAB_MODEL_KEY --enable-web --enable-memory advance TASK_ID
```

Use `answer REQUEST_ID 'clarification'`, `decide REQUEST_ID approve|deny`, `release REQUEST_ID`, and `review TASK_ID accept|reject --feedback 'concrete evidence'`. Answering/approving only records the human response; releasing executes an exact approved action. Without supported independent criteria a final proposal waits for review. A trusted `new --policy policy.json` may supply `constraints`, exact-text `artifacts`, data-only `criteria` and `child_rules`; the model cannot edit them. This is a trusted local interface, not a multi-user authentication service.

Request outcomes require a receipt bound to that exact approval, file version or Git operation. `released` alone is not verified success. An old unbound event or a later operation cannot confirm the request; it stays `unrecorded` while original task history is preserved. Inspect the evidence before any further action; views never retry operations or rewrite old records. Displayed task/request content is redacted separately from persisted evidence.

Optional live capabilities share the console, TUI and evaluator configuration:

- `--child-retries N`: permit up to N explicit failed-child replacements across the entire root (default 0, maximum 8). Each replacement preserves the assignment and acceptance, receives failure feedback, and consumes the original shared budgets. Fresh parent-owned inputs can be explicitly offered in the retry request after hash checks; old private files and approvals are not inherited. Opt-in roles can revise their own files through the same version-checked tool. This is bounded retry, not a general dependency planner.
- `--enable-web`: bounded public HTTPS search and cited `.md`/`.txt` retrieval. Search availability/relevance depends on the public endpoint; empty/challenge/failure results are retained. JavaScript, login pages and proprietary documents are unsupported.
- `--enable-memory --memory-namespace NAME`: private candidate retrieval/selection, staged model hypotheses and terminal outcome capture. A later task must share the same agent, conversation and namespace to retrieve a lesson. A selected lesson does not authorize an action or prove improvement.
- `--enable-collaboration`: allow present specialists to delegate to eligible peers and read scoped coordination messages without enabling web, memory, Docker or Git. Task ownership, file handoff, human review and shared limits remain in force. The default retains existing roles; changing this option cannot reinterpret an existing task.
- `--enable-delete`: allow an agent to request deletion of its own task-local text by exact SHA-256. The request pauses before deletion. Use the existing human `decide REQUEST_ID approve` and separate `release REQUEST_ID` controls, then advance the task; approving alone changes no file. Keep the same flag when reopening that task. Default is disabled, and changing the flag cannot reinterpret an existing run. This shared option works in the console, TUI and evaluation `run`; version-1 development/experience plan JSON keeps deletion disabled and rejects an added `delete` field.
- `--docker-host unix:///EXPLICIT_SOCKET --python-image python@sha256:PINNED_DIGEST`: use the existing Docker backend. No VM startup, image pull or host execution fallback occurs in the application.
- `--git-config repos.json`: explicitly allowlisted repositories/branches/paths. An optional `credential_env` names a separately provisioned, repository-scoped GitHub credential. Credentials are never discovered from the developer's Git setup; the project has not performed an actual GitHub runtime push.

A trusted repository configuration contains references and permissions, never the token value:

```json
{"repositories":[{"name":"output","path":"/ABSOLUTE/PATH/TO/TRUSTED/REPO","writable_branches":["agent-output"],"writable_paths":["docs/"],"remotes":{"origin":"https://github.com/OWNER/REPOSITORY.git"},"allow_network":true,"credential_env":"AGENT_LAB_GITHUB_TOKEN"}]}
```

Provision a token limited to that test repository outside the project files. The application disables redirects and ambient Git credentials, binds approval to the exact commit/remote/branch and independently reads the remote SHA after a push. A local fixture push is not GitHub evidence.

See [shared runtime setup](docs/architecture.md#shared-runtime-setup) and [Git boundaries](docs/architecture.md#restricted-git-tools). New capabilities are opt-in; changing an existing task's roles/tools/policy does not silently reinterpret its persisted configuration.

## Inspect a development run before model access arrives

```bash
python3 -m agent_lab.evaluation plan --config evaluation/development-plan.json
```

This reads two independently specified **live connection checks**: a delegated note/handoff and structured-file acceptance. It makes no model/network/engine request, creates no run state and needs no key. The checked-in plan intentionally leaves `model` null. Configure the teacher-issued provider/model and the named credential variable when issued, inspect again, then explicitly authorize the reported conditions:

```bash
python3 -m agent_lab.evaluation execute --config evaluation/development-plan.json --allow-model-calls --plan-sha256 REVIEWED_SHA256
```

The plan fixes task/tree limits, selected cases and tools; the fingerprint covers case/policy/role/code content. Execution refuses stale fingerprints, missing access, fixture/held-out substitution, unknown fields and unsupported memory-on labels. Limits bound reserved attempts and reported usage, **not exact billing**. The selected provider is retained rather than silently replaced. Human pauses stay real. A fresh empty database is used per case, and blocked/failed outcomes remain in the evaluation report. The inspected plan is saved with each actual run.

For the issued HKGAI service, [hkgai-smoke-plan.json](evaluation/hkgai-smoke-plan.json) fixes model `t2_hkgai-v3_fp8_1m_e7`, credential variable `COURSE_HKGAI_API_KEY`, one [connection case](evaluation/smoke/hkgai-tool-cycle.json), at most four reserved model attempts and 512 output tokens per request. Inspect with `python3 -m agent_lab.evaluation plan --config evaluation/hkgai-smoke-plan.json`; only after authorizing that small budget, execute with the same plan path, `--allow-model-calls` and its current fingerprint. This does not authorize memory/topology comparisons or further runs. A successful connection is not a multi-agent capability or official-test result. Never put the course key in a command argument, source file or report; set only the named local environment variable. HTTP failures/unknown effects are not retried automatically.

The version-2 [collaboration plan](evaluation/collaboration-plan.json) independently enables that capability for a self-contained [order-summary task](evaluation/collaboration/a03-handover.json), with at most 24 shared requests, 1024 output tokens per request and an explicit 90-second socket-operation timeout. Inspect it with `python3 -m agent_lab.evaluation plan --config evaluation/collaboration-plan.json`. The model chooses roles and task titles; no exact child criteria are preassigned, so a child's final proposal pauses for actual trusted review. The batch evaluator records a pause as blocked rather than scripting acceptance; the existing console/TUI workflow can retain interactive review state. Minimum task count and formatting checks do not establish autonomous negotiation or full report accuracy. A03 records actual observations separately; this plan is not a single/multi comparison or the official test set. Version-1 plans keep their existing fields and 30-second default; adding collaboration/timeout fields to version 1 is rejected. The shared live CLI also accepts `--socket-timeout` (at most 120 seconds). A socket timeout is not a task deadline, proof of non-billing or permission to retry; uncertain attempts stay recorded and no automatic POST retry occurs.

2026-10-26 A03 observation: the first authorized request hit the 30-second transport limit. After separate owner approval, a new task with a 90-second setting failed at the transport boundary after about 81 seconds. Neither returned a completion or dispatched a task tool; processing/billing are unknown. Both original attempts and configurations are retained. No automatic retry or further request followed. The collaboration capability has engineering evidence; actual autonomous decomposition/negotiation remains unvalidated and A03 stays open.

The separate [checked collaboration plan](evaluation/checked-collaboration-plan.json) uses [declared writer/editor work contracts](evaluation/collaboration/a04-checked-handover.json). Its opt-in declared-only policy returns early feedback for an unknown role/title pair, then independently checks structured numeric artifacts and final report properties. It makes no human acceptance automatic and leaves the open-ended A03 case unchanged. This is a bounded development workflow, not evidence of general planning, all required tools or official performance. A [different-input case](evaluation/collaboration/a04-changed-input.json) exercises the same declared work contracts with different order values. Both checked cases now require the checker to receive and read the writer's actual snapshot; the live audit retains the old numeric-only classifications separately from full workflow compliance.

These two cases test initial wiring only. Their automatic checks establish declared file properties. They do not validate arbitrary program behavior, report accuracy, learning improvement, real GitHub pushes, all required tools or the instructor's unseen dataset. Optional Docker/Git/web settings still require working backends and actual validation. Live memory comparisons, a single/multi-agent comparison and the official adapter/reset rules remain separate acceptance work.

Example trusted structural policy (these expectations must be authored independently of the candidate):

```json
{"criteria":[{"path":"report.md","kind":"contains","expected":"## Sources","min_bytes":100},{"path":"scratch.txt","kind":"absent"}],"child_rules":[{"assignee":"writer","title":"Write structured result","criteria":[{"path":"data.json","kind":"json_equals","expected":"{\"count\":3}"}]}]}
```

Supported kinds are `exists`, `absent`, `contains`, `json_equals`, `sha256` and `received_from`, with bounded `min_bytes`/`max_bytes`. JSON criteria are for internal structured data, not complex document formats. `received_from` takes an exact source assignee/title/path plus explicit `allow_relay` and `require_read` booleans; it checks identity-bound consumed receipts and ordered reads of the same file version. Identical recreated content alone does not prove delivery. Unsupported/unknown task acceptance still needs trusted review; candidate-produced “tests passed” text is never enough to satisfy missing criteria.

## Inspect or exercise the memory comparison protocol

```bash
python3 -m agent_lab.evaluation experience plan --config evaluation/memory-plan.json
python3 -m agent_lab.evaluation experience demo --config evaluation/memory-plan.json
python3 -m agent_lab.evaluation experience compare --run runs/experience-development/RUN_ID
```

Inspection needs no key, network or engine. `demo` deliberately supplies scripted responses that already know the fixture outputs; both probe arms produce the same fixed answers. Its report is `offline_fixture`, `model_calls: 0`, `benchmark_valid: false`, and comparison status `engineering_only`. A scripted training failure and success exercise provenance retention; they demonstrate no learning gain.

After approved model access and a run budget are available, configure the referenced runtime plan, inspect again and explicitly execute the current fingerprint:

```bash
python3 -m agent_lab.evaluation experience execute --config evaluation/memory-plan.json --allow-model-calls --plan-sha256 REVIEWED_SHA256
```

Each replicate starts fresh training. A checked, frozen SQLite seed retains original outcome provenance; each probe receives a new database/filesystem with the same private candidate content, without old files or approval authority. Training messages are hidden behind a persisted message boundary; new probe messages still work. Probe memory is frozen, retrieval/selection is optional, and selected-use outcomes are recorded without claiming causality. New probes reset all previous probe effects. ON/OFF order alternates; roles, instructions and budgets match except for `search_memory`/`select_memory` availability.

Training costs are reported separately. Failed, paused, interrupted and unrun planned cases remain in the report/denominator. Human boundaries stop that trial without a scripted answer; incomplete/unknown training effects prevent dependent probes. This first protocol does not resume interrupted trials automatically. Preserve their state and start an explicitly authorized new run after inspecting the failure. Mutable Git repositories are rejected until a repository-reset protocol exists. Normal interactive runtime memory/Git/HITL remain available separately.

Reports and seeds stay in ignored `runs/`. `compare` rechecks conditions, candidate identity, reset boundaries, role/tool/budget matching, observed model IDs and result evidence; edited headline summaries are ignored. Fingerprints detect changes, not forged results. No official scoring/reset rule is assumed, and no single/multi-agent baseline is supplied by this memory protocol.

## Run the combined actual-tool fixture

With an existing local Docker socket and cached pinned image:

```bash
python3 -m agent_lab integrated-demo --docker-host "unix://${HOME}/.colima/agent-lab/docker.sock" --image 'python@sha256:REPLACE_WITH_INSPECTED_DIGEST' --with-web
```

The fixed synthetic agents retrieve official Python text (only with `--with-web`), hand off input snapshots, run Python in the real container, independently check the output, commit/push to a disposable **local bare remote**, restart at exact-action approval and select scoped experience in a later task. Without `--with-web`, the source is explicitly a fixture. The approval is scripted for this disposable remote. `report.json` records zero model calls, `benchmark_valid: false`, no established autonomous collaboration/learning gain and no GitHub push. A negative actual-container test rejects a wrong output before any push. All evidence stays in ignored `runs/`; existing evidence is preserved.

## Run actual Python sandbox checks

The default offline commands above do not need Docker and skip actual-container tests. An explicitly configured Docker engine and an already-pulled, digest-pinned official Python image enable `sandbox-demo` and the real isolation checks. See [sandbox setup and validation](docs/sandbox.md) for the dedicated Colima environment, exact commands, limits, recovery, and shutdown.

The actual execution fixture reports `mode: sandbox_integration_fixture`, zero model/API network calls, and `benchmark_valid: false`. It runs fixed source/tests inside a real container, exports actual text through the broker, confirms removal, and independently verifies the artifact before completion. It is not an autonomous-agent or model-performance result. The backend serializes sandbox executions per workflow and supports Python text/source snapshots only; full course coverage and the instructor's accepted minimum isolation boundary still need confirmation.

## Delivery progress and collaboration

Use the [Roadmap](docs/team-roadmap.md) as the single task register: remaining work, dependencies, owner, status, acceptance and concise development/review outcomes. Discuss and claim work in WeChat; Qingthefish coordinates the main-branch register and final merges. Detailed code changes and checks stay in the linked PRs. Refresh main before starting a claimed task; do not maintain a second checklist or infer a percentage complete from fixture scores or card counts. The accepted baseline includes work completed before these cards were introduced.

This README describes capabilities and operation; requirements, design and architecture documents keep their separate purposes. Live-model access and official evaluation details remain the dependencies stated above and in the Roadmap.

## Read next

- [Course requirements](docs/requirements.md): mandatory capabilities and acceptance evidence.
- [Direction discussion](docs/direction.md): announcement-first scope, concrete task examples, and staged delivery.
- [Contribution guide](CONTRIBUTING.md): development and evidence practices.
- [Team roadmap](docs/team-roadmap.md): the shared task register; choose a card, coordinate in WeChat, and record the owner before coding.
- [AGENTS.md](AGENTS.md): instructions for coding assistants working in this project.
- [Architecture and boundaries](docs/architecture.md): the implemented state and approval contract, with missing integrations stated explicitly.

## Project boundaries

This folder is separate from lecture materials and assignments. The submitted runtime must use DeepSeek or HKGAI, as required by the course. Credentials are local only; their presence does not authorize unlimited calls. Provider protocol and scheduling infrastructure are implemented; live-model validation and demonstrated autonomous negotiation/replanning require the evidence recorded in the Roadmap. The local workflow API expects a trusted caller; actor IDs alone are not authentication. Conversation membership checks do not establish execution-sandbox isolation.

Other coursework is reference material. Shared themes do not establish permission to reuse code, datasets, reports, or results across course submissions. Track any approved reuse and each course's new contribution explicitly.
