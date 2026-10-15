# ARIN 5202 / MAIE 5221 Final Project

Evolutionary Multi-Agent Collaboration System

## Status

2026-10-15: repository bootstrap and requirements preparation. There is no runnable system, measured result, or finalized team yet. The project repository is [Qingthefish/evolutionary-agent-lab](https://github.com/Qingthefish/evolutionary-agent-lab).

The instructor's announcement is the primary scope authority. Build a general multi-agent collaboration platform with autonomous delegation, human interaction, private sandboxes, per-agent memory and learning, required tools, and automatic completion/time evaluation. The proposed implementation emphasis is reliable execution with observable results and bounded recovery. A business vertical is not required to start the project.

## First 10 minutes / 新成员从这里开始

1. Clone this repository and open **the repository root** in Codex. This makes the project `AGENTS.md` available to the coding assistant. Accept the collaborator invitation before pushing changes.
2. Read [course requirements](docs/requirements.md), then [delivery scope](docs/direction.md). The announcement's mandatory requirements come before optional research ideas.
3. Ask Codex: `Read README.md, AGENTS.md, and docs/requirements.md. Summarize what exists, what is still planned, the mandatory course requirements, and one small next implementation step. Do not modify files yet.`
4. Before making changes, create a focused branch, agree on observable acceptance criteria, and follow [CONTRIBUTING.md](CONTRIBUTING.md).
5. No API key, model download, dependency installation, or experiment run is needed to review these initial documents. There is no application startup or test command yet; commands will be documented once implemented and verified.

For now, useful onboarding work is checking requirements, reviewing acceptance examples, and proposing small development tasks. Do not report any planned capability as implemented.

```bash
git clone https://github.com/Qingthefish/evolutionary-agent-lab.git
cd evolutionary-agent-lab
```

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

## Project boundaries

This folder is separate from lecture materials and Assignment 01. The submitted runtime must use DeepSeek or HKGAI, as required by the course. API credentials have not been configured. Provider integration and live-model validation are future work.

Other coursework is reference material. Shared themes do not establish permission to reuse code, datasets, reports, or results across course submissions. Track any approved reuse and each course's new contribution explicitly.
