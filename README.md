# ARIN 5202 / MAIE 5221 Final Project

Evolutionary Multi-Agent Collaboration System

## Status

2026-10-15: the feature branch implements durable workflow state, conversation membership checks, delegation records, human pause/resume, exact-action approval release, and task accounting. Controlled UTF-8 file tools now enforce task ownership and descriptor-based paths, provide explicit artifact snapshot handoff, and check actual text before completion. Deterministic CLI fixtures exercise this infrastructure. **There is no autonomous model-driven platform, process sandbox, experience-learning mechanism, or model-performance result yet.** The project repository is [Qingthefish/evolutionary-agent-lab](https://github.com/Qingthefish/evolutionary-agent-lab).

The instructor's announcement is the primary scope authority. Build a general multi-agent collaboration platform with autonomous delegation, human interaction, private sandboxes, per-agent memory and learning, required tools, and automatic completion/time evaluation. The proposed implementation emphasis is reliable execution with observable results and bounded recovery. A business vertical is not required to start the project.

## First 10 minutes / 新成员从这里开始

1. Clone this repository and open **the repository root** in Codex. This makes the project `AGENTS.md` available to the coding assistant. Accept the collaborator invitation before pushing changes.
2. Read [course requirements](docs/requirements.md), then [delivery scope](docs/direction.md). The announcement's mandatory requirements come before optional research ideas.
3. Ask Codex: `Read README.md, AGENTS.md, and docs/requirements.md. Summarize what exists, what is still planned, the mandatory course requirements, and one small next implementation step. Do not modify files yet.`
4. Before making changes, create a focused branch, agree on observable acceptance criteria, and follow [CONTRIBUTING.md](CONTRIBUTING.md).
5. Use Python 3.12 or newer and run the offline checks below. No API key, model download, package installation, or external service is needed. The demo is a scripted plumbing check, not an autonomous-agent demonstration.

Useful onboarding work includes checking requirements, running the fixture, reviewing the state/approval contract, and proposing small development tasks. Do not report planned capabilities as implemented.

```bash
git clone https://github.com/Qingthefish/evolutionary-agent-lab.git
cd evolutionary-agent-lab
```

## Run the offline foundation

From the repository root:

```bash
python3 -m unittest discover -s tests -v
python3 -m agent_lab demo
python3 -m agent_lab files-demo
```

The demo creates a fresh ignored `runs/offline-*` directory containing a SQLite database, a verified fixture `note.txt`, and `report.json`. It closes/reopens the database while awaiting clarification, resumes, requests and consumes one exact approval, writes the fixed note, checks its contents, and completes a parent/child task pair. Human responses and delegation in this fixture are scripted. No model, arbitrary shell command, Git mutation, or network request is executed.

Use `python3 -m agent_lab demo --state-dir runs/my-first-demo` to choose a **new** run directory. Existing paths are rejected to preserve evidence. Every report explicitly contains `mode: offline_fixture`, `model_calls: 0`, and `benchmark_valid: false`. Its success fractions describe trusted workflow state, not course benchmark performance.

`files-demo` creates a separate `runs/files-*` directory. It creates/reads/updates/deletes controlled text, hands a snapshot from a writer task to a reviewer task, and checks both copies against trusted expected contents before completion. Source and received SHA-256 receipts must agree. It also demonstrates that code execution is refused when no process sandbox is configured. Its report explicitly says `process_sandbox: false`; script-driven file operations are not a sandbox or a model benchmark. The file broker currently requires POSIX descriptor-relative operations and a private root directory; unsupported systems fail closed.

The offline checks have passed locally on Python 3.12 and 3.14. A [CI workflow template](docs/ci-workflow.yml) is provided for later installation as `.github/workflows/checks.yml`; it is **not enabled**, because the current Git push credential cannot add Actions workflows. No GitHub Actions result is claimed. Read [architecture and boundaries](docs/architecture.md) before connecting an executor or model.

## Initial delivery milestones

- [ ] Verify an allowed DeepSeek/HKGAI model connection and the local sandbox approach.
- [ ] Run one delegated task end to end with real tools and independently checked outputs.
- [ ] Cover every mandatory capability, including private/group chat, delegation, human pause/resume, isolation, Git, and independent experience memory.
- [ ] Run controlled completion/time comparisons and analyze failures and memory effects.
- [ ] Evaluate the official test set and prepare the architecture document, performance report, commit evidence, and presentation.

These unchecked milestones are planned work, not claimed results. The API key will be provided by the course later; quotas and official evaluation details remain to be confirmed.

## Read next

- [Course requirements](docs/requirements.md): mandatory capabilities and acceptance evidence.
- [Direction discussion](docs/direction.md): announcement-first scope, concrete task examples, and staged delivery.
- [Contribution guide](CONTRIBUTING.md): development and evidence practices.
- [AGENTS.md](AGENTS.md): instructions for coding assistants working in this project.
- [Architecture and boundaries](docs/architecture.md): the implemented state and approval contract, with missing integrations stated explicitly.

## Project boundaries

This folder is separate from lecture materials and Assignment 01. The submitted runtime must use DeepSeek or HKGAI, as required by the course. API credentials have not been configured. Provider integration and live-model validation are future work. The local workflow API expects a trusted caller; actor IDs alone are not authentication. Conversation membership checks do not establish execution-sandbox isolation.

Other coursework is reference material. Shared themes do not establish permission to reuse code, datasets, reports, or results across course submissions. Track any approved reuse and each course's new contribution explicitly.
