# ARIN 5202 / MAIE 5221 Final Project

Evolutionary Multi-Agent Collaboration System

## Status

2026-10-17: the current foundation implements durable workflow state, conversation membership checks, delegation records, human pause/resume, exact-action approval release, and task accounting. Controlled UTF-8 file tools enforce task ownership and descriptor-based paths, transfer artifact snapshots, and check actual text before completion. Per-agent candidate memory captures observed outcomes with provenance, scoped lexical retrieval, selected-use outcomes, exact duplicate merging, and retirement. A DeepSeek HTTP/protocol adapter and allowlisted tool gateway now connect structured requests to these tools, with persisted call reservations and a per-task tool-call cap. A durable single-task runner now repeats model/tool turns, preflights batches, pauses for humans, retains user constraints across restart, routes final proposals to independent verification, and stops on persisted attempt, reported-token, duration, or repeated-outcome limits. Deterministic CLI fixtures exercise this infrastructure. A durable cooperative multi-agent scheduler now routes delegated tasks to configured roles, retains goal constraints, waits for independently checked child results, and returns explicit artifact offers to parents. Persisted task-tree limits bound total tasks, depth, model attempts, reported tokens, tool calls, and assignment-to-completion time. **Live-provider validation, demonstrated autonomous negotiation/replanning, learning improvement, and model-performance results remain pending.** An opt-in Docker Python backend now performs actual isolated execution with pinned input/image versions, resource limits, explicit text export, and confirmed cleanup; it has separate real-container integration checks, including scheduler-driven delegation, actual execution, artifact handoff, and rejection of a matching file after failed execution. An optional Textual terminal control center (`python -m agent_lab.tui`) now exposes conversations, task trees, execution evidence, artifacts, memory, and approvals over these APIs, with labelled offline scenarios. The project repository is [Qingthefish/evolutionary-agent-lab](https://github.com/Qingthefish/evolutionary-agent-lab).

The instructor's announcement is the primary scope authority. Build a general multi-agent collaboration platform with autonomous delegation, human interaction, private sandboxes, per-agent memory and learning, required tools, and automatic completion/time evaluation. The proposed implementation emphasis is reliable execution with observable results and bounded recovery. A business vertical is not required to start the project.

2026-10-18: UI and live evaluation now use one shared runtime setup for roles, tools, task/tree limits and acceptance. Original task constraints and root text expectations are persisted and restored across restart; conflicting policies/configurations are rejected. This is validated through offline configuration contracts, not live-model performance.

2026-10-21: trusted exact-text child criteria now use that shared runtime policy. Offline checks exercise failed child verification, concrete repair feedback, restart, checked handoff and parent completion within existing budgets. Unknown/ambiguous child proposals still pause for trusted review. A04 remains in progress until its final live check; this is no evidence of autonomous-model performance.

2026-10-21: optional runtime services now connect public HTTPS search/retrieval, private candidate experience, isolated Python and trusted Git repositories to the shared scheduler. Specialists can delegate with input snapshots and read scoped coordination messages. A combined engineering fixture has exercised public retrieval, actual Docker execution, verified local-remote push, restart and later scoped memory selection. All model decisions in that fixture are scripted; live-model validation, actual GitHub runtime pushing and learning gains remain unestablished.

2026-10-21: opt-in failed-child replacement now retains failed history, original assignment/criteria and shared budgets. Denials, unreleased approvals and unknown effects cannot be bypassed with a retry. Independent data-only artifact criteria cover existence/absence, size, required text, JSON equality and SHA-256. Versioned development plans inspect cases/budgets without a key and require the reviewed fingerprint plus explicit authorization before model calls. These changes do not establish general replanning, arbitrary code/report correctness, live learning or official performance.

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
| Task execution, delegation and shared limits | [runner.py](agent_lab/runner.py), [scheduler.py](agent_lab/scheduler.py), [budget.py](agent_lab/budget.py) |
| Controlled files, public text retrieval and private candidate memory | [files.py](agent_lab/files.py), [retrieval.py](agent_lab/retrieval.py), [memory.py](agent_lab/memory.py) |
| Python sandbox and restricted Git operations | [sandbox.py](agent_lab/sandbox.py), [git_tools.py](agent_lab/git_tools.py) |
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

The provider code uses the official DeepSeek endpoint directly, requires an explicit model ID, and disables network use by default. No alternate provider, local model, or synthetic fallback is selected automatically. Live use still needs the issued credential/model details, an authorized experiment budget, and validation of the controller against the issued endpoint/model. The runner caps per-task attempts and observed token usage; its token threshold is checked after a response and is not a strict billing cap. HKGAI integration awaits its official interface details. See [provider and gateway boundaries](docs/architecture.md#provider-protocol-and-tool-gateway).

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

Live mode must be requested explicitly (`--live --model <id> --api-key-env <VAR>`) and uses only the DeepSeek adapter; there is no fallback provider. It has not been exercised against the real endpoint. Both the TUI and evaluation `run` command share these flags, plus repeatable `--constraint`, `--max-output-tokens`, `--task-attempts` and `--tree-attempts`. Live flags are rejected without `--live`. The launcher reads only the named key variable; programmatic `LiveConfig` defaults to network disabled. Obtain the issued model/key and authorize a run budget before live execution. See [shared runtime setup](docs/architecture.md#shared-runtime-setup) and [control-center boundaries](docs/architecture.md#terminal-control-center).

## Run development evaluations

```bash
python3 -m agent_lab.evaluation list
python3 -m agent_lab.evaluation run
```

The harness loads development cases from `evaluation/dev/*.json`, runs each in a fresh state directory, computes independent acceptance checks (final task state, exact artifact text, absent files, verified remote branch, time limit) from persisted records and actual files, classifies failures, and writes `results.json` plus a Markdown `report.md` under the ignored `runs/evaluations/`. Offline cases execute fixed scripts and are reported as `offline_fixture` with `benchmark_valid: false`; negative-control cases check that the evaluator reports mismatches. The live case is reported as *not configured* (never as a success) until a DeepSeek/HKGAI runtime is configured. The same evaluator backs the control center's Evaluation tab (`F9`). These are development cases, not the instructor's held-out set; Memory ON/OFF comparison is an interface that refuses offline, unmatched, or unexercised-memory runs. Memory-enabled batch evaluation is rejected before provider calls pending its cross-task/reset protocol; interactive runtime memory is available with explicit configuration.

Cases can also require uniquely identified descendant tasks, their states and actual artifacts, plus exact counts of persisted clarification/approval outcomes within the goal's task tree. Negative controls exercise wrong child results and missing/wrong human evidence even when the root output matches. Invalid/unknown criteria are rejected before execution; driver crashes do not count as detected controls. Full expected criteria and matched task/request evidence are retained in `results.json`. See the [case contract](docs/architecture.md#evaluation-harness-foundation) and [development definitions](evaluation/dev/).

For `live_scheduler` cases, optional `constraints` are combined with the CLI's original constraints and persisted in the shared task policy. Scripted fixtures reject custom constraints because they do not interpret arbitrary requests. Trusted root and supported child exact-text/structural/absence expectations use the same verifier factory in the UI API and evaluator. Child criteria select an exact assignee/title and must be independently supplied before execution. A success selector follows the active replacement attempt; every original failure remains in metrics/history. Expected failures and unsupported criteria retain review. Unknown, ambiguous or unsupported child proposals require trusted review. A root with configured child rules cannot pass by producing its own file while skipping required children. Optional runtime backends now require explicit flags and matching session-owned services. Without those settings, their tools stay disabled. Live batch evaluation can use configured web/Python/Git tools, but memory-enabled batch evaluation still refuses to run until its cross-task/reset protocol is versioned. Actual live model/tool behavior and learning gains remain unvalidated.

Reports distinguish **contract acceptance** (including correct rejection behavior) from verified **goal completion** and **subtask completion**. They show expected/executed/blocked/unconfigured cases, missing evidence, task states, assignment-to-final-status time, unfinished elapsed time and cumulative per-task human waits. Failed/cancelled times remain visible; waits are not subtracted. The legacy JSON `completion_rate` remains the acceptance fraction for compatibility; use `goal_completion_rate` and `subtask_completion_rate` for task outcomes. Offline fractions remain fixture results.

Each run saves a fingerprinted manifest of full task/acceptance content, requested model, role prompts/tools/budgets, code/templates, intervention protocol and initial-memory reset conditions, plus observed model IDs and actual task/request evidence. Memory comparisons reject legacy/missing/corrupt or unmatched evidence, even if case IDs agree. The current protocol uses a fresh empty memory store per case; actual memory-on execution and controlled learning trials remain C02/C05 work. Fingerprints detect condition changes and do not authenticate results. See [evaluation evidence and comparison](docs/architecture.md#evaluation-evidence-and-comparison).

## Run a real task without the optional interface

The standard-library console uses the same task service as the TUI. No model call occurs when creating a task; an unconfigured task remains pending.

```bash
python3 -m agent_lab.console new --goal 'Prepare a cited Markdown explanation'
python3 -m agent_lab.console status
python3 -m agent_lab.console status --task TASK_ID
```

After the issued model/key and run budget are available, supply the same live flags when creating or advancing a live task. Set the named model-key variable outside the repository; never paste its value into a command argument or committed file.

```bash
python3 -m agent_lab.console --live --model ISSUED_MODEL --api-key-env AGENT_LAB_MODEL_KEY --enable-web --enable-memory new --goal 'Prepare a cited Markdown explanation'
python3 -m agent_lab.console --live --model ISSUED_MODEL --api-key-env AGENT_LAB_MODEL_KEY --enable-web --enable-memory advance TASK_ID
```

Use `answer REQUEST_ID 'clarification'`, `decide REQUEST_ID approve|deny`, `release REQUEST_ID`, and `review TASK_ID accept|reject --feedback 'concrete evidence'`. Answering/approving only records the human response; releasing executes an exact approved action. Without supported independent criteria a final proposal waits for review. A trusted `new --policy policy.json` may supply `constraints`, exact-text `artifacts`, data-only `criteria` and `child_rules`; the model cannot edit them. This is a trusted local interface, not a multi-user authentication service.

Optional live capabilities share the console, TUI and evaluator configuration:

- `--child-retries N`: permit up to N explicit failed-child replacements across the entire root (default 0, maximum 8). Each replacement preserves the assignment and acceptance, receives failure feedback, and consumes the original shared budgets. Fresh parent-owned inputs can be explicitly offered in the retry request after hash checks; old private files and approvals are not inherited. Opt-in roles can revise their own files through the same version-checked tool. This is bounded retry, not a general dependency planner.
- `--enable-web`: bounded public HTTPS search and cited `.md`/`.txt` retrieval. Search availability/relevance depends on the public endpoint; empty/challenge/failure results are retained. JavaScript, login pages and proprietary documents are unsupported.
- `--enable-memory --memory-namespace NAME`: private candidate retrieval/selection, staged model hypotheses and terminal outcome capture. A later task must share the same agent, conversation and namespace to retrieve a lesson. A selected lesson does not authorize an action or prove improvement.
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

The plan fixes task/tree limits, selected cases and tools; the fingerprint covers case/policy/role/code content. Execution refuses stale fingerprints, missing access, fixture/held-out substitution, unknown fields and unsupported memory-on labels. Limits bound reserved attempts and reported usage, **not exact billing**. HKGAI remains blocked until its issued interface is implemented; there is no provider fallback. Human pauses stay real. A fresh empty database is used per case, and blocked/failed outcomes remain in the evaluation report. The inspected plan is saved with each actual run.

These two cases test initial wiring only. Their automatic checks establish declared file properties. They do not validate arbitrary program behavior, report accuracy, learning improvement, real GitHub pushes, all required tools or the instructor's unseen dataset. Optional Docker/Git/web settings still require working backends and actual validation. Formal memory comparisons and the official adapter/reset protocol remain separate work.

Example trusted structural policy (these expectations must be authored independently of the candidate):

```json
{"criteria":[{"path":"report.md","kind":"contains","expected":"## Sources","min_bytes":100},{"path":"scratch.txt","kind":"absent"}],"child_rules":[{"assignee":"writer","title":"Write structured result","criteria":[{"path":"data.json","kind":"json_equals","expected":"{\"count\":3}"}]}]}
```

Supported kinds are `exists`, `absent`, `contains`, `json_equals` and `sha256`, with bounded `min_bytes`/`max_bytes`. JSON criteria are for internal structured data, not complex document formats. Unsupported/unknown task acceptance still needs trusted review; candidate-produced “tests passed” text is never enough to satisfy missing criteria.

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

This folder is separate from lecture materials and Assignment 01. The submitted runtime must use DeepSeek or HKGAI, as required by the course. API credentials have not been configured. Provider protocol and scheduling infrastructure are implemented; live-model validation and demonstrated autonomous negotiation/replanning remain future work. The local workflow API expects a trusted caller; actor IDs alone are not authentication. Conversation membership checks do not establish execution-sandbox isolation.

Other coursework is reference material. Shared themes do not establish permission to reuse code, datasets, reports, or results across course submissions. Track any approved reuse and each course's new contribution explicitly.
