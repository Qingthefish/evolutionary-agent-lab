# ARIN 5202 / MAIE 5221 Final Project

Evolutionary Multi-Agent Collaboration System

A platform for turning human tasks into delegated, tool-based agent work with
private workspaces, recorded handoffs and independently checked delivery. The
allowed language model chooses actions; the application enforces permissions,
execution limits, human decisions and task state.

## Supported environment and clean setup

Use **Python 3.12 or newer and Git on Linux or macOS**. The controlled file broker requires POSIX directory descriptors, no-follow opens and private file permissions. Native Windows Python cannot enforce this boundary and is not supported. The core commands and tests use only the Python standard library; Textual is optional and Docker is needed only for actual isolated code execution.

On Windows, use a normal Linux distribution in WSL 2. For example, follow Microsoft's [WSL installation guide](https://learn.microsoft.com/en-us/windows/wsl/install) and run this from PowerShell, completing any requested restart and Linux user setup:

```powershell
wsl --install -d Ubuntu-24.04
```

Open that distribution's Linux shell for the commands below. Docker Desktop's internal `docker-desktop` distribution is not a development environment. Keep the checkout, virtual environment and runtime data in the Linux filesystem, such as `~/src`, rather than `/mnt/c` or another Windows-mounted directory; the broker requires private, current-user-owned directories. See Microsoft's [WSL filesystem guidance](https://learn.microsoft.com/en-us/windows/wsl/filesystems). Do not disable the broker's permission checks to accommodate a shared directory.

From the Linux or macOS shell, create a clean standard-library environment:

```bash
mkdir -p ~/src
cd ~/src
git clone https://github.com/Qingthefish/evolutionary-agent-lab.git
cd evolutionary-agent-lab
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python --version
```

Check that the selected Python is at least 3.12 before creating the environment. If the distribution reports a missing `venv` or `ensurepip` component, install its matching Python venv package (for example, `python3-venv` on Ubuntu 24.04), then repeat environment creation. No `pip install` is needed for the core checks. Run the commands below from the repository root with this environment active. This setup path does not by itself validate WSL, a Docker backend or a live model connection.

For a repeatable core setup check, use the same clean venv:

```bash
python scripts/check_setup.py --output runs/d04-clean-setup
```

The [setup reproduction script](scripts/check_setup.py) checks the six existing offline demos, console create/status/reopen behavior, evaluation cases, static plan inspection, refusal of unauthorized execution and the full engineering suite. It saves the source revision/diff identity, environment, command results and stdout/stderr logs in a new output directory; choose a new path for every attempt. It does not install dependencies or select live-model, web or Docker execution. Docker opt-in variables are removed for these child commands. Optional UI/container skips are counted separately, and `clean_core_environment` indicates whether the interpreter is in a venv without Textual. These results are setup evidence, not live capability or benchmark scores. Use `--repo` to check a separate source checkout with the same interpreter.

**Independent setup reproduction (2026-11-14):** a fresh Ubuntu 24.04 WSL 2 distribution, a non-root Linux user and Python 3.12.3 venv reproduced a console bug on original main `48709e5`: `status --task` was parsed as an ambiguous abbreviation of global `--task-*` flags, producing five errors and one failure in the 620-test suite. The console now requires exact top-level option names. After this fix and the unsupported-platform regression check, all 16 setup command checks passed; 621 tests were discovered, with 593 passing and 28 explicit skips (19 actual-container, nine optional UI). No third-party Python package or course credential was needed. This core-only record is preserved separately from the configured reproduction below.

**Configured setup reproduction (2026-11-14):** the same Ubuntu 24.04 WSL 2 environment, Python 3.12.3 and optional Textual 8.2.8 passed all **621 engineering checks**, including **19 actual-container and nine UI checks**, with zero skips, errors or failures. Docker Desktop's Linux engine was selected through an explicit local Unix socket and a digest-pinned official Python image. The documented sandbox fixture performed actual isolated execution, exited zero and confirmed container cleanup. These engineering checks made zero model calls. See the [Windows sandbox setup](docs/sandbox.md#windows-hosts).

**Allowed-provider setup smoke:** the issued HKGAI connection completed the existing tool-cycle case in **three actual requests and 5,104 reported tokens**, with `probe.txt` independently checked. The requested and returned model IDs have different suffixes (`e7` versus `e10`); equivalence is unconfirmed. A separate combined A05 probe then stopped after **two additional requests**: one accepted response reported 3,886 tokens and the next failed as `invalid_completion`, with its usage unknown. It produced no file or sandbox effect and was not retried; the failed A05 record remains unchanged.

**Direct live Docker setup check:** after an explicit continuation, a distinct private coder task completed in **four actual HKGAI requests and 12,711 reported tokens**. The model wrote a 123-byte `main.py`, executed that exact source snapshot in the configured Docker sandbox, imported the exact `d04-live-docker-ok:5` result with its final newline, read it and submitted to the existing independent verifier. Exit code zero, source/output hashes, cleanup and final task success were checked. A separate direct Docker CLI probe also verified non-root execution, no external network, resource limits and removal of its container. This small fixed-value setup demo does not replace the failed multi-agent A05 task or establish general code correctness.

The cumulative record is **nine actual requests, 21,701 known reported tokens plus unknown usage for the earlier rejected response**, within the original 20-request ceiling. Original failures and database hashes were preserved. [Whitelisted setup evidence](evaluation/evidence/d04-setup-reproduction.json) records the separate outcomes. D04's independent setup, allowed-provider and actual Docker reproduction was accepted through PR #52. [D04 review](docs/team-roadmap.md#d04)

## Status

**Additional no-search practice (November 24 night).** On the tested runtime,
the actual classroom command menu completed a fresh author-created interval
analysis task and its same-group usage-summary follow-up in **75 HKGAI requests**.
Independent root checks passed **11/11** and **17/17**; exit/reopen preserved the
25-call review checkpoint, eight checked files were carried, and both partial
and completed exports retained their real states with zero additional calls.
Assignment to final export took **874.79 seconds including operator review/idle**;
this small assisted pair is not a classroom speed prediction or a new six-task
score. No runtime code changed. [Evidence and limits](docs/final-report.md#18-additional-no-search-command-menu-practice)

**Classroom rehearsal (November 24).** The actual classroom ZIP command menu
imported an explicitly labelled practice package with the original software
roles and two new ordered tasks. Both roots completed assistant technical
acceptance in **27 HKGAI requests / 328,752 reported tokens**. Independent root
checks passed **8/8** and **12/12**; the same group carried five checked files.
Assignment to final export took **779.37 seconds**, including review/idle.
This simple practice pair is not the final test or a classroom speed estimate.
A pending-review-list display defect found during rehearsal is corrected
without changing acceptance or making model calls; **67 focused and all 953
full engineering checks passed**, including actual containers and Textual,
with zero skips. Safari opened the earlier
securities HTML and navigated pages 1–3; the entire deck was not visually checked.
Native Terminal control was explicitly unavailable, so this was a command-menu
rehearsal rather than a completed human desktop/Zoom presentation.
[Rehearsal evidence and limits](docs/final-report.md#17-classroom-menu-and-safari-rehearsal)
· [Step-by-step Wednesday SOP](docs/presentation-sop.md)

The owner subsequently operated a separate fresh practice pair through the
actual Terminal menu: both tasks completed with four genuine owner review
decisions, **64 HKGAI requests**, assistant inspection and independent 8/8 and
12/12 checks. Exported code matches the checked version. This is distinct from
the earlier 27-request rehearsal and from the unreleased classroom task.
A refreshed [five-minute speaking script](docs/presentation-script.txt) and
[Chinese slide cues and result alternatives](docs/presentation-speaking-notes.txt)
support the owner's manually prepared PPT. The November 25 update has 486
spoken words and includes the assisted 6/6 and fresh first-proposal 4/6 under
their distinct review conditions, plus a separate no-search workflow practice.
Spoken timing, Zoom sharing and the actual classroom result remain unverified;
the tested runtime is unchanged.

**Classroom reliability integration (November 24).** Teammate proposals
[#90](https://github.com/Qingthefish/evolutionary-agent-lab/pull/90) and
[#92](https://github.com/Qingthefish/evolutionary-agent-lab/pull/92) add opt-in
streamed replies, quality-profile exact-passage editing and explicit operator
resend controls on both classroom paths. Independent review additionally
rejects mixed/incomplete/malformed streams, bounds actual encoded bytes and
single-line reads, and refuses overlapping edit matches. All **952 engineering
checks passed**, with actual configured containers and Textual, zero skips and
zero model calls. These are general workflow changes, not answers to the six
mid-test tasks. The original role-package adapter remains specific to its
issued ZIP contract; ordinary TXT/MD tasks use the separate generic team.

A new author-created laboratory CSV-QC task used that actual ordinary intake,
with fresh files, no old-six answers or memory, and no web tools. It completed
through specialist delegation, isolated execution, exact handoff and technical
review in **43 HKGAI requests / 766,126 reported tokens**. The first proposal
passed **9/12** independent datasets, losing raw rejected-field whitespace;
after explicit feedback the repaired child and final coordinator delivery each
passed the same **12/12**. Actual task wall time was **2,653.22 seconds** including
review/idle, versus **211.29 seconds** summed turn duration including tools.
This single assisted development smoke is not an unseen-classroom success rate
or proof that the known-six result generalizes.
[Generalization audit, new-task result and limits](docs/final-report.md#16-classroom-integration-and-new-task-audit)
· [Sanitized evidence](evaluation/evidence/classroom-integration-20261124.json)

**Known-six first-proposal diagnostic (November 24–25).** A fresh single run
accepted **four roots and stopped two**, using **600 HKGAI requests /
31,122,236 reported tokens**. Software and newsroom pairs passed independent
checks without external technical repair. Both securities roots stopped at
their first risk-child proposal: incorrect currency stress, then misinterpreted
valuation arithmetic and a misstated policy constraint. No request allowance
was exhausted. This local diagnostic stops a whole root on a material child
error before possible later repair; it is stricter than ordinary final-only
review and is not an instructor score. Two ordinary preferences were answered
under owner delegation, and Codex performed technical reviews; this is not
zero-human autonomy. The earlier assisted 6/6 remains separate and unchanged.
[Results, failure evidence and limits](docs/final-report.md#19-known-six-first-proposal-diagnostic)
· [Sanitized evidence](evaluation/evidence/known-six-first-proposal-20261125.json)

**Fresh known-six development (November 23–24).** All six original mid-test
tasks reached **coordinator-assisted technical acceptance**, using **633 actual
HKGAI requests**, 59,534,942 known reported tokens and four retained attempts
with unknown usage. The three groups started fresh with their original four
roles; each Task 2 continued its accepted Task 1 in the same group. Larger
quality allowances, concrete repairs and explicit review assistance all changed
the conditions, so this is not an isolated measurement of raising limits,
unattended 6/6, a teacher grade or held-out accuracy. The final dashboard passed
51 generated regressions and 28 independent arithmetic/export/static-wiring
checks; its JavaScript syntax and critical formulas were inspected. The dashboard's
browser visuals and controls remain untested; the separate securities-deck
Safari check above covers pages 1–3 only. The original four-assisted,
two-failed 375-call trial below stays unchanged.
[Complete results, timing and retained mistakes](docs/final-report.md#15-fresh-known-six-assisted-development)
· [Sanitized evidence](evaluation/evidence/known-six-assisted-20261124.json)

**Six-task Mac evaluation (2026-11-23).** All six canonical mid-test tasks have
now ended: **four coordinator-assisted acceptances and two failures**, using
**375 actual HKGAI requests**. These are development outcomes, with retained
reviews and exceptions, rather than unattended completion or teacher scores.
Software Task 2 failed; Securities Task 2 failed without an HTML deck after
search-heavy child failures, truncated repair replies and exhausted child
replacements. The frozen runtime, original states and outputs are sealed
privately. A local recovery correction keeps the parent and independent
siblings available after replacement quota exhaustion while retaining failure,
approval and unknown-effect checks. Its full engineering regression passed
**866 of 896 checks**, with **30 explicit container/UI skips** and zero model
calls. A separate 80-request known-task repeat then produced an 11-slide HTML
candidate, but content review rejected it and the repair remained incomplete.
A further seven-request artifact repair stopped on two consecutive 4,096-token
cutoffs, with no corrected HTML saved. Its next 18-call derivative produced
revised files and paused, unaccepted, at cumulative **480 requests**; the
original six-task result remains unchanged. Ordinary execution now
allows smaller counted actions after consecutive cutoffs within the existing
budgets; the optional finish protocol remains separate. The 18-call derivative
exercised this recovery without accepting its incomplete goal. That correction's
offline regression passed **869/899 checks**, with **30 explicit container/UI skips**.
[Results and failure analysis](docs/final-report.md#13-six-task-mac-evaluation-23-november)
· [Sanitized evidence](evaluation/evidence/mid-test-six-20261123.json)

**Quality execution audit (2026-11-23).** Re-read the original instructor
specification and replacement presentation notice. Historical 80/480-call,
4,096-output and 90-second settings are local experiment choices, not course
scoring rules. Fresh quality-mode plans select larger operating allowances;
budget exhaustion preserves work for an audited same-goal extension, and
stagnation pauses for a revised approach. The software lead may write its own
integration files; private workspaces, critical-action approval, source/effect
checks and independent acceptance stay enforced. Old bindings remain available
for reproduction. The full release regression passed **880/910 checks**, with
**30 explicit container/UI skips**.

An explicitly inspected transport resend also permits a later audited numeric
extension while retaining the old error row and unknown usage. A new unresolved
failure, an unprocessed response or an uncertain tool effect still blocks extension.

Two real HKGAI regressions used **93 new requests**: an **81-call known-artifact
HTML repair**, technically accepted after independent rejection/correction and
an actual bad/good checker control; and the existing **12-call code/execution/
handoff contract**, completed through its predeclared automatic criteria.
Returned replies were not truncated at the selected 8,192-token ceiling; one
connection-closed request retains unknown usage and its counted inspected
resend. These are separate development outcomes, not an improved six-task score.
[Quality-mode commands](docs/official-mid-test.md#quality-mode-for-fresh-development)
· [Results and limits](docs/final-report.md#14-quality-execution-audit-and-regressions)
· [Sanitized evidence](evaluation/evidence/quality-execution-20261123.json)

**Integrated baseline before this evaluation.** Reviewed contributor changes #75/#76/#77
and coordinator corrections are integrated through [PR #79](https://github.com/Qingthefish/evolutionary-agent-lab/pull/79).
The runtime requires exact explicit failed-child waiver IDs and permits labelled
recovery only of a failed direct child's already-offered snapshot. Follow-up
`61a9f86` corrects late repair authorization and the gateway's boolean option
validation. Baseline engineering checks: **893 discovered, 884 passed, nine
optional UI skips**, with **21 actual-container checks executed**.
Optional performance switches remain off; actual HKGAI speed benefits remain
unmeasured. [Review and limits](docs/final-report.md#12-november-22-coordinator-catch-up)

**Original Software Task 1 replay: complete technical acceptance.** Frozen
runtime `d8dec1a` completed the instructor's booking-system task in **63 actual
HKGAI requests / 28.47 minutes**, including review and repair. An independent
check exposed a first-initialization race that erased a confirmed booking.
The developer Agent repaired it; all ten independent behavioral checks then
passed. The lead received/read that exact revision, reran the 12 generated
tests and delivered source and usage instructions. This is a coordinator-
assisted replay with two active roles, not a teacher score, an unattended run
or ten-minute completion. In the same group, the bounded Task 2 replay ended
**failed** after 78 requests: 14/16 independent checks passed, and the cross-hour
statistic repair was not fully checked or handed back. Its tool/repair defects
were then corrected offline; no repaired-runtime Task 2 success is claimed. [Evidence and limits](docs/final-report.md#original-software-task-1-reproduction)

**Repair validation.** A separate real-model regression on `bddf523` completed
failed-snapshot recovery, an explicitly linked replacement, isolated repair
and exact result receipt/read in **16 requests / 233.234 seconds**. Its failed
seed was a labelled zero-model fixture. A larger known-package repair remains
paused after a DNS-stage failure; it is not accepted. Its actual implementation
now passes all **16 independent dashboard checks**. After the coding assistant
corrected mistaken expectations in one model-edited test, a separate artifact
also passed all **38 original unit tests**, without modifying the model's
implementation or the independent checker. This repairs an artifact, not the
original same-group Task 2 outcome. [Scope and retained failures](docs/final-report.md#scoped-recovery-and-artifact-validation)

**Other evidence.** A fresh known-development HKGAI root completed delegated
input, isolated execution, checked handoff/read and report delivery in **18
requests / 86.693 seconds**. Earlier bounded real private clarification,
approval/release and peer handoff are accepted separately. Two complete memory
ON/OFF pairs retain their **no demonstrated learning benefit** conclusion.
Original failed, expired and incomplete runs remain preserved. Requested e7
and returned e10 model labels differ; equivalence is unconfirmed. The
[report](docs/final-report.md) and [public evidence](evaluation/evidence/development-summary.json)
retain the source identities, actual outcomes and limitations.

**Contributor scenario reports.** The contributor reports complete Newsroom
and Securities pairs and earlier Software successes. Their `full13/full14/full16`
raw records are not attached to the PR or available locally, so these remain
contributor-reported outcomes. Do not combine best results across different
rounds into a six-of-six claim. The local Software replay is recorded separately.
New [PR #81](https://github.com/Qingthefish/evolutionary-agent-lab/pull/81)
reports a further Software Task 1 success and Task 2 delivery failure on
`bddf523`; its raw full17 state is likewise unavailable locally and its review
is pending. This follow-up preserves that separate contributor branch.

**Updated presentation and submission.** The instructor's replacement notice,
supplied on November 23, specifies **5 minutes plus 30 seconds for transition**,
**one presenter**, and normally no Q&A. Receive the task link **three
presentation slots before our turn**, set up and run then, and show the results
during the talk. Use the same Zoom meeting and screen-share from our own
computer. Skip background introductions: Method 2 minutes, Mid-test results
1 minute, In-class test results 1 minute, Reflection 1 minute. Tasks will not
require web search; DeepSeek or HKGAI is permitted. **Final submission is
December 19, 2026**; the cutoff time is not stated. This replaces the previous
ten-minute/live-start arrangement. November 25 remains the week-13 planning
target; the exact group slot is unconfirmed. A separate five-slide presentation
draft and [speaking notes](docs/presentation-speaking-notes.txt) are prepared;
the classroom-result page and manual timed rehearsal remain open.
[Requirements](docs/requirements.md#current-presentation-and-submission-requirements) · [Runbook](docs/final-report.md#9-proposed-presentation-outline)

The connected Outlook notification independently confirms the replacement
[notice](https://canvas.ust.hk/courses/73253/announcements/659120). It supplies
no answer key or detailed marking rubric. Prioritize a complete Mac operator
rehearsal and a timed five-minute presentation alongside usable, substantially
correct outputs; the [classroom review scope](docs/presentation-sop.md#周三的准备优先级)
does not require repeating every development boundary check during the talk.

The later [attendance notice](https://canvas.ust.hk/courses/73253/announcements/659506),
received November 23 at 23:22 Hong Kong time, requires **all students to attend
in the classroom**. The same Zoom/screen-sharing arrangements remain in place.
The [input-to-output walkthrough](docs/presentation-sop.md#从收到题到看到结果按你实际操作的顺序)
explains the current TXT/ZIP inputs, clickable Terminal interface and exported results.

**Remaining gates.** Complete repaired-runtime Software Task 2 and Securities
Task 2 deliveries under a separately recorded development plan,
check the actual final-link mapping, freeze and rehearse
on the presentation machine, retain final task results and finish submission.
Original four-role CLI setup/preflight/read-only export has been rehearsed with
zero calls, which does not verify an unknown final input. R09's actual Agent-
runtime GitHub push still needs its designated test branch, scoped credential
and genuine action-bound approval; coordinator pushes/local-remote fixtures do
not establish it. The owner relays permission for reasonable HKGAI coursework
use; operating checkpoints are local controls, not teacher limits or measured
account balance. The [Terminal operating guide](docs/official-mid-test.md#operating-from-the-presentation-mac)
distinguishes the local platform from remote model inference. Use the [Roadmap](docs/team-roadmap.md) as the sole task,
owner and progress register, with the instructor [requirements](docs/requirements.md)
as the primary project authority. Historical observations live in the report
and retained evidence rather than competing current-status paragraphs.

## First 10 minutes / 新成员从这里开始

1. Clone this repository and open **the repository root** in Codex. This makes the project `AGENTS.md` available to the coding assistant. Accept the collaborator invitation before pushing changes.
2. Read [course requirements](docs/requirements.md), [delivery scope](docs/direction.md), and the [Roadmap task cards](docs/team-roadmap.md). The announcement takes priority; A/B/C/D are technical areas, not assigned people.
3. Use the read-only starter prompt below. Check Codex's summary against the files before selecting work.
4. Before feature development, claim one Roadmap card in WeChat and have the coordinator record it on main. Then create a focused branch and follow [CONTRIBUTING.md](CONTRIBUTING.md).
5. Use the supported environment above and run the offline checks below. Once Python and its venv support are installed, no API key, model download, third-party Python package or external service is needed for the core checks. The demo is a scripted plumbing check, not an autonomous-agent demonstration.

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

## Source map

Use these entry points to inspect the current implementation; a module's presence does not establish live-model or official-test performance. The [architecture](docs/architecture.md) describes contracts and limits; the [Roadmap](docs/team-roadmap.md) records acceptance and remaining work.

| Area | Entry points |
| --- | --- |
| Durable tasks, conversations and evidence views | [core.py](agent_lab/core.py), [queries.py](agent_lab/queries.py), [inspection.py](agent_lab/inspection.py) |
| Model protocol and allowed tool dispatch | [protocol.py](agent_lab/protocol.py), [deepseek.py](agent_lab/deepseek.py), [gateway.py](agent_lab/gateway.py), [model_context.py](agent_lab/model_context.py) |
| Shared live configuration, task policies and CLI flags | [runtime.py](agent_lab/runtime.py) |
| Task execution, delegation and shared limits | [runner.py](agent_lab/runner.py), [scheduler.py](agent_lab/scheduler.py), [delegation.py](agent_lab/delegation.py), [budget.py](agent_lab/budget.py) |
| Controlled files, public text retrieval and private candidate memory | [files.py](agent_lab/files.py), [provenance.py](agent_lab/provenance.py), [retrieval.py](agent_lab/retrieval.py), [memory.py](agent_lab/memory.py) |
| Python sandbox, execution evidence and restricted Git operations | [sandbox.py](agent_lab/sandbox.py), [execution_proof.py](agent_lab/execution_proof.py), [git_tools.py](agent_lab/git_tools.py) |
| Frozen experience trials and reset/provenance boundaries | [experience.py](agent_lab/evaluation/experience.py), [memory_protocol.py](agent_lab/evaluation/memory_protocol.py) |
| Matched single/multi-agent conditions, fairness checks and replay | [topology.py](agent_lab/evaluation/topology.py), [topology_plan.py](agent_lab/evaluation/topology_plan.py), [topology_report.py](agent_lab/evaluation/topology_report.py), [topology_fixture.py](agent_lab/evaluation/topology_fixture.py) |
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

The [GitHub Actions workflow](.github/workflows/checks.yml) runs on pull requests and pushes to `main`; manual dispatch becomes available after installation on the default branch. Python 3.12 and 3.14 core jobs each use a fresh standard-library-only venv and run all 16 setup checks, including the full engineering suite. A separate Python 3.12 job installs the optional Textual requirements and runs headless UI interactions, failing if any UI check is skipped. Job summaries expose actual counts and explicit core skip reasons; summary/log artifacts are retained for 14 days, including on failure. The [documented workflow copy](docs/ci-workflow.yml) matches the installed file.

**Observed Actions run (2026-11-14):** [the first remote run](https://github.com/Qingthefish/evolutionary-agent-lab/actions/runs/43592710950), for I04 head `4cfab17`, passed all three jobs. Python 3.12.16 and 3.14.10 each passed all 16 setup commands and 593 of 621 discovered tests, with 28 explicit skips (19 actual-container and nine optional UI). The separate Textual job passed all nine UI checks without skips. Downloaded summary/log artifacts confirmed these counts. CI deliberately leaves actual Docker checks unconfigured and makes zero live model calls; these are engineering checks, not an official evaluation. I04 merged after the D04 setup fix and passed its first push-triggered run on main. [I04 PR #53](https://github.com/Qingthefish/evolutionary-agent-lab/pull/53) · [Main Actions run](https://github.com/Qingthefish/evolutionary-agent-lab/actions/runs/43595176368)

## Run the terminal control center

For the presenting Mac, use the [Chinese classroom SOP](docs/presentation-sop.md)
and [Mac launcher](打开平台.command). The prepared local entry point imports a
verbatim text goal and bounded text attachments before opening the existing
live interface, or validates a supported instructor role ZIP before opening
its sequential operator. Import/open/export do not call a model; unknown role
packages are refused rather than assigned the default team. Local settings,
credentials, environments and run data remain ignored. The final classroom
package and a complete timed operator rehearsal are not yet verified.

An optional [Textual](https://textual.textualize.io/) dashboard exposes conversations, the live task tree and execution inspector, artifacts, candidate memory, approvals, and execution logs on top of the existing workflow, gateway, scheduler, and file broker. Textual is the only extra dependency; the core package and its tests remain standard-library only. Use a separate ignored environment to preserve the clean core venv:

```bash
python3 -m venv venv/tui
source venv/tui/bin/activate
python -m pip install -r requirements-tui.txt
python -m agent_lab.tui
```

The default session directory `runs/tui-session` is reused across restarts, so conversations, tasks, approvals, and history persist. Offline mode is the default and is labelled in the header. It can create conversations, post messages, and create real tasks, but **a task created without a configured model stays pending**: no arbitrary request is completed offline. Dashboard scenarios (`chat`, `delegation`, `approval`, `memory`, `git`) drive the real workflow, gateway, file broker, approval release, and verifiers with scripted provider responses; their results are `offline_fixture` evidence with zero model calls. Approving an action only records the decision; a separate *Release & execute* step consumes it through `ToolGateway.release_approved` and shows the verified effect. Press `?` for shortcuts.

The Git tab (`Ctrl+G`) shows a disposable, scenario-created local repository and any repositories listed with `--git-config repos.json`. The `git` scenario has a scripted integrator commit a task note through the restricted Git tools and request a push; the push happens only after you approve the exact commit/branch/remote binding and release it, and the remote branch is then verified. No GitHub remote or credential is used. See [restricted Git tools](docs/architecture.md#restricted-git-tools).

Live mode must be requested explicitly (`--live --provider hkgai --model <id> --api-key-env <VAR>` for HKGAI; the compatible default remains `deepseek`); there is no fallback provider. Real-provider acceptance is recorded separately in A01. Both the TUI and evaluation `run` command share these flags, plus repeatable `--constraint`, `--max-output-tokens`, `--task-attempts` and `--tree-attempts`. Live flags are rejected without `--live`. The launcher reads only the named key variable; programmatic `LiveConfig` defaults to network disabled. Obtain the issued model/key and authorize a run budget before live execution. See [shared runtime setup](docs/architecture.md#shared-runtime-setup) and [control-center boundaries](docs/architecture.md#terminal-control-center).

## Run development evaluations

The C06 input adapter reads the instructor's **2026 mid-test** from a local
copy of the Canvas archive. It prepares three four-agent scenarios, each with
two ordered tasks in the same group. Follow the local setup steps in the
[mid-test guide](docs/official-mid-test.md), then inspect the prepared inputs:

```bash
python -m agent_lab.evaluation.official inspect --config runs/official-mid-inputs/plan.json
```

The inspection records six unrun tasks, the input hashes and the choices
remaining for S01. The [session rehearsal](docs/official-mid-test.md#s01-handoff-and-unresolved-rules)
keeps each pair in one saved group and tracks a selected artifact's transfer
and read across tasks. Development commands below start each case from fresh state.

```bash
python3 -m agent_lab.evaluation list
python3 -m agent_lab.evaluation run
```

For file-based development tasks, inspect `python3 -m agent_lab.evaluation plan --config evaluation/provided-input-plan.json`. Its declared `inputs` are raw case data supplied by trusted setup to a pending root, not model-generated answers or human approvals. The plan exposes original input hashes and missing configuration without a key/network call. The JSONL experience plan uses the same input protocol with frozen ON/OFF arms; original prompt-transcription case definitions remain retained separately. Only explicitly configured/authorized live execution can establish model results.

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

The [sandbox code case](evaluation/code/a05-sandbox-order-summary.json) prepares a separate coordinator/coder workflow: create source/data, execute the exact snapshots in the configured Python sandbox, independently check numeric output, then accept/read the real result for the report. The sandbox_output criterion declares entrypoint, arguments and input paths; it requires the current versions, the latest matching successful job, confirmed cleanup and a run-bound import receipt. It does not prove arbitrary program correctness, and an independent content oracle is still required. Inspect the case without a key using `python3 -m agent_lab.evaluation list --cases evaluation/code`. Execution needs an explicitly configured pinned sandbox and a separately bounded live-tool scope; this preparation and actual-container scripted checks are not a new live HKGAI run.

The [code/experience plan](evaluation/experience-code/plan.json) declares one training task and the same different-input probe with memory ON/OFF. Its checked-in runtime deliberately leaves the local socket/image unset; inspect it with `python3 -m agent_lab.evaluation experience plan --config evaluation/experience-code/plan.json`, then supply a reviewed ignored local runtime configuration before any authorized live execution. Training/probe stages retain the shared declared-role/input guards and per-case effective role metadata. The first real attempt's three failures remain in the register; current schema clarifications and repair tools do not rewrite those results. A separately authorized fresh run subsequently completed both probes with the same frozen experience seed: ON selected one coder-owned candidate and its later outcome was checked; OFF had no retrieval or selection. Independent read-only audits preserve all DB hashes and verify the actual artifacts and handoffs. Training cost/failure remains separate. Both probes used 13 requests, while ON reported 70790 tokens and OFF 66618; the timing difference is not a reliable learning-effect estimate.

Declared-contract runners now refresh a versioned execution_budget object in the original trusted task context before every model request. Counts show local/shared remaining attempts after reserving the current request, remaining tool/task slots and observed token/time thresholds. They do not change caps, grant approval, represent provider account balance or bypass verification. Plans/manifests record local-reservations-v1. Older declared runner sessions without that version refuse incompatible resume; ordinary legacy contexts are unchanged. The training parent's recorded failure remains unchanged, and this hint's live effect still needs validation.

`run_python` accepts optional `replace_outputs` (path → current SHA-256) for existing outputs only when the role also has `update_text`. Preflight reads no new receipt, verifies owned versions before execution, and export rechecks them before updating. Omission preserves create-only exports. Failed execution leaves old outputs unchanged; an intervening edit blocks import/recovery. This does not grant deletion, host file access or approval authority.

These two cases test initial wiring only. Their automatic checks establish declared file properties. They do not validate arbitrary program behavior, report accuracy, learning improvement, real GitHub pushes, all required tools or the instructor's unseen dataset. Optional Docker/Git/web settings still require working backends and actual validation. Live memory comparisons, a single/multi-agent comparison and the official adapter/reset rules remain separate acceptance work.

Example trusted structural policy (these expectations must be authored independently of the candidate):

```json
{"criteria":[{"path":"report.md","kind":"contains","expected":"## Sources","min_bytes":100},{"path":"scratch.txt","kind":"absent"}],"child_rules":[{"assignee":"writer","title":"Write structured result","criteria":[{"path":"data.json","kind":"json_equals","expected":"{\"count\":3}"}]}]}
```

Supported kinds are `exists`, `absent`, `contains`, `json_equals`, `sha256`, `received_from`, `sandbox_output`, `human_answer` and `searched_source`, with bounded `min_bytes`/`max_bytes`. JSON criteria are for internal structured data, not complex document formats. `received_from` takes an exact source assignee/title/path plus explicit `allow_relay` and `require_read` booleans; it checks identity-bound consumed receipts and ordered reads of the same file version. Identical recreated content alone does not prove delivery. Unsupported/unknown task acceptance still needs trusted review; candidate-produced “tests passed” text is never enough to satisfy missing criteria.

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

For a per-case ON/OFF result table and memory-use diagnostics, run `python -m agent_lab.evaluation.experience_effect --run runs/experience-development/RUN_ID --format markdown`. The read-only [memory effect analysis](docs/memory-effect-analysis.md) preserves training costs, failures and unknown usage; positive time/request/token deltas mean ON used more. Scripted fixtures remain engineering evidence, and the tool makes no causal learning claim.

## Inspect or exercise the single/multi-agent baseline (C07 preparation)

```bash
python3 -m agent_lab.evaluation topology plan
python3 -m agent_lab.evaluation topology plan --config evaluation/topology/negative-control-plan.json   # must be rejected
python3 -m agent_lab.evaluation topology demo --fixtures evaluation/topology/fixtures/adverse-set.json
python3 -m agent_lab.evaluation topology compare --run runs/topology-development/RUN_ID
```

[evaluation/topology-plan.json](evaluation/topology-plan.json) wraps a normal development runtime plan and adds two topologies. The single agent `solo` receives the team's task tools without delegation or hand-off tools. The team is the existing `live_roles` set under the same `MultiAgentScheduler`. Loading the manifest checks model, cases, acceptance, aggregate budgets, tool capabilities, memory and human policy, and fails closed with structured reasons. Cases that prescribe a decomposition are rejected as single-agent controls. Topology-specific differences such as role prompts and coordination tools are recorded as confounds.

Delegated children have no independent content oracle, so the default `c07-structural-handoff-v1` policy releases a child only after it has offered a snapshot to its parent. Only the root is judged by the case criteria, and each recorded task states its acceptance basis. Reports also show how many team runs actually delegated. With `trusted-review`, unattended team runs stop for human review instead.

`demo` replays scripted model turns through the real scheduler, gateway, budgets and acceptance. The fixtures are development simulations drafted with an AI assistant outside the runtime and normalized by hand. Each fixture records its provenance. Their reports are `engineering_validation` with zero model calls and synthetic usage placeholders. They are not model results. Live pilot execution needs an issued model, the named key variable, `--allow-model-calls` and the inspected `--plan-sha256`, and stays within the manifest's `pilot_budget`. A live result is `pilot_compared` only when every pair is complete and every run has an observed model identity and known usage. Otherwise it is `pilot_incomplete`, with the gaps listed. [evaluation/topology/smoke-plan.json](evaluation/topology/smoke-plan.json) is a separate first live check with one case, one run per topology and at most 16 model attempts. Its result is `smoke_only` and is never a comparison. Each run uses a fresh state directory, and alternating order is recorded. Unrun, interrupted and failed runs stay in denominators, unknown usage is never shown as zero and monetary cost is reported as unavailable.

To diagnose coordination costs in a retained C07 or frozen-experience run, use the read-only audit. It reconciles reserved requests, known tokens and tool calls against the database and distinguishes a waiting parent from a failed one.

```bash
python3 -m agent_lab.evaluation.coordination_audit --run runs/topology-development/RUN_ID --summary
```

Five historical batches yielded three training roots where the coder succeeded and the root exhausted its shared request budget. The last root actions in those three examples were a progress message, an artifact acceptance and a memory record. See the [audit evidence](evaluation/evidence/development-summary.json).

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
