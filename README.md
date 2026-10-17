# ARIN 5202 / MAIE 5221 Final Project

Evolutionary Multi-Agent Collaboration System

## Status

2026-10-17: the current foundation implements durable workflow state, conversation membership checks, delegation records, human pause/resume, exact-action approval release, and task accounting. Controlled UTF-8 file tools enforce task ownership and descriptor-based paths, transfer artifact snapshots, and check actual text before completion. Per-agent candidate memory captures observed outcomes with provenance, scoped lexical retrieval, selected-use outcomes, exact duplicate merging, and retirement. A DeepSeek HTTP/protocol adapter and allowlisted tool gateway now connect structured requests to these tools, with persisted call reservations and a per-task tool-call cap. A durable single-task runner now repeats model/tool turns, preflights batches, pauses for humans, retains user constraints across restart, routes final proposals to independent verification, and stops on persisted attempt, reported-token, duration, or repeated-outcome limits. Deterministic CLI fixtures exercise this infrastructure. A durable cooperative multi-agent scheduler now routes delegated tasks to configured roles, retains goal constraints, waits for independently checked child results, and returns explicit artifact offers to parents. Persisted task-tree limits bound total tasks, depth, model attempts, reported tokens, tool calls, and assignment-to-completion time. **Live-provider validation, demonstrated autonomous negotiation/replanning, learning improvement, and model-performance results remain pending.** An opt-in Docker Python backend now performs actual isolated execution with pinned input/image versions, resource limits, explicit text export, and confirmed cleanup; it has separate real-container integration checks, including scheduler-driven delegation, actual execution, artifact handoff, and rejection of a matching file after failed execution. An optional Textual terminal control center (`python -m agent_lab.tui`) now exposes conversations, task trees, execution evidence, artifacts, memory, and approvals over these APIs, with labelled offline scenarios. The project repository is [Qingthefish/evolutionary-agent-lab](https://github.com/Qingthefish/evolutionary-agent-lab).

The instructor's announcement is the primary scope authority. Build a general multi-agent collaboration platform with autonomous delegation, human interaction, private sandboxes, per-agent memory and learning, required tools, and automatic completion/time evaluation. The proposed implementation emphasis is reliable execution with observable results and bounded recovery. A business vertical is not required to start the project.

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
| Task execution, delegation and shared limits | [runner.py](agent_lab/runner.py), [scheduler.py](agent_lab/scheduler.py), [budget.py](agent_lab/budget.py) |
| Controlled files and private candidate memory | [files.py](agent_lab/files.py), [memory.py](agent_lab/memory.py) |
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

Live mode must be requested explicitly (`--live --model <id> --api-key-env <VAR>`) and uses only the DeepSeek adapter; there is no fallback provider. It has not been exercised against the real endpoint. See [control-center boundaries](docs/architecture.md#terminal-control-center).

## Run development evaluations

```bash
python3 -m agent_lab.evaluation list
python3 -m agent_lab.evaluation run
```

The harness loads development cases from `evaluation/dev/*.json`, runs each in a fresh state directory, computes independent acceptance checks (final task state, exact artifact text, absent files, verified remote branch, time limit) from persisted records and actual files, classifies failures, and writes `results.json` plus a Markdown `report.md` under the ignored `runs/evaluations/`. Offline cases execute fixed scripts and are reported as `offline_fixture` with `benchmark_valid: false`; a negative-control case checks that the evaluator reports a mismatch. The live case is reported as *not configured* (never as a success) until a DeepSeek/HKGAI runtime is configured. The same evaluator backs the control center's Evaluation tab (`F9`). These are development cases, not the instructor's held-out set; Memory ON/OFF comparison is an interface that refuses offline, unmatched, or unexercised-memory runs. Live memory-on execution is not implemented and is rejected before provider calls.

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
