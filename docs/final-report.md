# Evolutionary Multi-Agent Collaboration System — Draft Report

MAIE5221 / ARIN5202. **Development draft, updated 2026-11-14 (Asia/Hong_Kong).** This is not a final submission or an official benchmark report. Official tasks, scoring/intervention rules, final member contribution evidence and submission dates have not been incorporated into this draft. The instructor announcement remains the authority in [requirements](requirements.md).

## 1. Objective and verified scope

Build a general multi-agent platform that delegates work, uses tools in private workspaces, interacts with humans, retains per-agent experience and automatically records task completion and execution time. Our implementation emphasizes checked execution and bounded recovery. An original research paper, a specific business vertical and an elaborate frontend are not prerequisites.

Minho’s configured WSL reproduction at `950c894` passed **621 engineering checks**, including **19 actual-container integration checks and nine UI checks**, with zero skips. The coordinator independently ran the 16 clean setup steps and recorded 593 core passes with 28 Docker/UI skips. The core and Textual jobs passed on main. [D04 evidence](../evaluation/evidence/d04-setup-reproduction.json) · [Main Actions run](https://github.com/Qingthefish/evolutionary-agent-lab/actions/runs/43595395085) The earlier opt-in required-action trial at `a52c34a` observed 43 tool-call replies without free-text narration/truncation and two independently audited complete JSONL probe roots. This bounded result does not establish general reliability or an official score. The [architecture](architecture.md) documents the actual contracts and limits; the [Roadmap](team-roadmap.md) remains the sole task/owner register.

Two earlier real HKGAI code/report probes and two current JSONL probes completed their full independently audited contracts. The earlier JSONL failures and the latest exhausted training parent remain preserved. Thus the project has runnable, checked development slices; broad live coverage and official performance remain unresolved.

## 2. System design

The minimal terminal interface and batch evaluator use a common backend. SQLite records conversations, task trees, messages, model/tool reservations, human requests, artifact receipts and outcomes. Trusted configuration sets role capabilities, acceptance criteria and budgets; model requests choose actions within those boundaries.

- **Input and context:** the creating human can provide bounded new UTF-8 files to a pending root task. Descriptor-based writes preserve exact bytes, ownership and human attribution. Agents receive original receipt metadata and read their own current files. Data contents grant no permission. Child tasks receive only explicitly offered snapshots; private files and full transcripts are not automatically shared. Declared tasks use the versioned concise model view: full own-role/global constraints, bounded peer descriptions without private experience tools, and execution replies retaining outcomes/errors/receipts. Full original sandbox records remain independent evidence; configurations/manifests bind the effective prompt/view policy.
- **Delegation:** the scheduler runs eligible tasks, waits for children and returns checked child outcomes and explicit offers. Current complete live probes use declared role/title contracts. These constrain automatic acceptance and do not establish open-ended planning or negotiation.
- **Execution and acceptance:** the gateway validates schemas, task identity, allowlists and budgets before effects. Python runs only in a configured, digest-pinned container with no external network or host mounts, restricted identities/resources, bounded exports and confirmed cleanup. File output must match current source/input hashes and the recorded execution/import, in addition to independent content checks.
- **Completion proposals:** a final answer or opt-in `submit_for_verification` proposes completion. The latter must be last in a batch and can follow final file/offer actions without another model turn. The existing trusted verifier still decides success. Missing criteria retain independent review; unfinished children, unreleased actions, expiry and budget refusal remain barriers. Interrupted proposals are not automatically re-issued by recovery. The optional required-action setting sends `tool_choice=required` and rejects ignored/unsupported responses without retry or auto fallback. It leaves model action selection and every independent criterion unchanged; default auto-choice behavior is preserved.
- **Human interaction:** private/group membership, clarification pauses and exact-action approval/release are durable. A grant is not evidence that an action ran. Model tools cannot answer humans, approve actions or supply acceptance criteria.
- **Experience:** each agent owns conditional candidate observations/lessons with source outcomes. Retrieval and explicit selection are logged; later outcomes assess use. Contradictory and failed observations remain visible. This is retrieval of experience, not model-weight training or a guarantee that old advice is correct.

The HTTP runtime explicitly selects DeepSeek or the issued HKGAI service, with no OpenAI/Anthropic or synthetic fallback. Documents remain Markdown/plain text; JSON and SQLite serve configuration/state. See [sandbox setup](sandbox.md) for the actual isolation assumptions, including the trusted engine/kernel boundary.

## 3. Reproduction and evidence

The core requires Python 3.12 or newer and the standard library; Textual is optional. From a clean repository root:

```bash
python3 -m agent_lab demo
python3 -m agent_lab scheduler-demo
python3 -m agent_lab.evaluation run
python3 -m agent_lab.evaluation plan --config evaluation/provided-input-plan.json
python3 -m agent_lab.evaluation experience plan --config evaluation/required-actions-experience-plan.json
```

The demos/evaluation fixtures are scripted and labelled accordingly. Plan inspection makes zero model/engine calls and reports missing credentials/executor configuration. An unconfigured live case is not a success. Actual model runs require the inspected conditions, issued credential, explicitly authorized budget and configured backends. Do not commit credentials or reuse an expired/failed task automatically.

A clean Python 3.12.12 setup passed 16 command checks without Textual or course credentials: six demos, console/evaluation commands, blocked live execution and the core suite. Of 552 discovered core checks, 524 passed and 28 Docker/UI checks were explicitly skipped. Logs distinguish actual skips from passes; automated reproduction is not another member's independent reproduction.

The public [development evidence summary](../evaluation/evidence/development-summary.json) contains whitelisted outcomes, timing, usage, source/configuration identities and hashes of retained raw records. It omits raw prompts, credentials and host paths. Original requests/responses, SQLite files and read-only audits remain in ignored local evidence directories. Hashes bind records for later comparison; they do not authenticate data or replace an audit. Before final delivery, prepare the required accessible evidence package and genuine history screenshots without exposing secrets.

For the combined provided-input/repair/handoff check, configure the actual Docker environment described in the sandbox guide, then run:

```bash
python3 -m unittest discover -s tests -p test_sandbox_integration.py -k provided_input -v
```

This check uses real isolated executions with scripted provider decisions. It rejects an incorrect executed result, repairs/reruns it, checks exact input custody and completes child/parent submissions in nine scripted decisions. Without the explicit Docker variables it is skipped, not passed. It establishes engineering behavior, not HKGAI autonomy.

The batch evaluator saves the reviewed development plan before entering the first case. Its `run-progress.json` records selected cases, the manifest, completed outcomes, the active case and the cases still to start. A process interruption leaves the last published checkpoint available for inspection. If an active case may have produced an effect, inspect its retained state before considering another run. The completed batch publishes its regular `report.md` and `results.json`.

## 4. Evaluation method

**Goal completion** requires a succeeded root with independent acceptance and the required child/evidence contracts. Matching files or a successful child alone do not complete the goal. **Subtask completion** is reported separately. Failed and unrun cases remain visible; failures are not removed from denominators.

**Execution time** currently means assignment-to-final-state time, including human waiting, with observed trial time separately available. Final instructor timing and intervention rules must be mapped before official evaluation. Failure durations are retained; a mean over finalized tasks is not a mean over successful tasks alone.

Model attempts, reported token counts and unknown usage supplement the two required metrics. Local request caps are not the teacher account balance. Provider-reported tokens on a reply rejected by the parser are retained in the observer ledger; the framework's conservative unknown-usage record remains unchanged. Neither measure determines money spent, remaining quota or reset policy.

The memory comparison freezes one training history, supplies identical candidate content to fresh ON/OFF probes, hides training chat/files and inherits no approval. Case content, model, non-memory tools, prompts and budgets match; only retrieval/selection tools differ. Probe experience cannot teach later probes. The planned single/multi comparison remains a separate teammate contribution under review.

## 5. Observed development results

These selected recent code/experience records are development evidence, **not official results or all-time account usage**. They include unsuccessful preparation and missing probes. Do not add the local caps: some historical authorizations overlap, and each final-slot row continues its preceding allowance.

| Record | Reserved attempts | Observed outcome |
| --- | ---: | --- |
| Initial code/experience trial | 35 | Training and both probes failed; no complete root |
| DNS-stopped follow-up | 1 | No model completion; dependent probes unrun; usage unknown |
| Repaired code trial after DNS recovery | 41 | ON and OFF roots completed; training coder succeeded but training parent failed at its limit |
| First JSONL trial | 16 | Supplied script genuinely failed and was repaired; coder/root incomplete; ON reply truncated; OFF unrun |
| Extended JSONL training/ON portion | 29 | Training coder independently succeeded; parent exhausted the shared budget; ON reply truncated; OFF unrun |
| Same allowance's final distinct provided-file task | 7 new, 36 cumulative | Exact 215-byte human-source → coordinator → coder receipt/read verified; generated code ran but failed an incorrect assertion; repair reply truncated; root failed |
| Overnight compact-context training/ON portion | 25 | Supplied starter failed and was repaired; coder independently completed, parent exhausted; ON generated correct output but then narrated line counts until truncation; OFF unrun |
| Overnight allowance's final distinct capability task | 8 new, 33 cumulative | Exact source receipt/read and correct current-code isolated output verified; subsequent narration truncated; no offer/submission or completed root |
| Required-action common training and matched JSONL probes | 43 (16 training, 14 ON, 13 OFF) | Training coder repaired the supplied bug and completed, parent exhausted; both probes independently completed; all 43 replies were tool calls without narration/truncation |

The older final-slot task carried its original allowance from 29 to 36 requests, leaving 12 unused. The overnight final-slot task carried its different user-requested allowance from 25 to 33, leaving 15 unused. Each used its third and final root slot after a read-only audit of a complete length-limited reply, terminal tasks and no pending human/unknown tool effects. Neither replayed an old request, increased its allowance or completed the missing OFF condition. Unused requests do not permit a fourth root or reveal provider balance.

The overnight training coder was accepted at the time of its independent check. Subsequent read-only checks retain historical exact source receipt/read but current `received_from` rules reject failed source roots; the failed parents are not reclassified as successes. All three overnight code outputs match their numeric expectations through cleaned real containers. This partial capability is distinct from completed tasks. The 1024-output-token ceiling is the local development allowance setting, not an inferred instructor grading rule. No larger-limit result is available.

An isolated v1 projection of a saved request reduced repeated peer-description text from 4,596 to 1,494 characters (whole payload 17,054 to 14,367 characters with the new system guidance). This is a character-count/view check under changed role conditions, not a provider-token, cost or causal quality comparison.

The earlier complete code/report memory pair is:

| Condition | Root completion | Attempts | Assignment-to-final seconds | Provider-reported tokens | Experience use |
| --- | ---: | ---: | ---: | ---: | --- |
| ON | 1/1 | 13 | 20.369 | 70,790 | Two candidate records retrieved, one explicit selection, later outcome succeeded |
| OFF | 1/1 | 13 | 20.795 | 66,618 | No retrieval or selection |

Common training cost was 15 attempts and 78,230 reported tokens; its coder succeeded but its parent failed. The ON candidate was source-bound observed experience, not proof of a newly learned algorithm. Both arms used 13 attempts; ON used more tokens. One pair and a small time difference establish exercised experience use, **not a general learning advantage**. Different cases/code/budgets across later rounds cannot establish a causal improvement either.

The current JSONL pair uses identical case content, initial frozen memory, allowed model, non-memory tools, prompt/view policy and budgets; both request provider-required tools. Training is separate and not silently amortized:

| Condition | Root completion | Attempts | Assignment-to-final seconds | Provider-reported tokens | Experience use |
| --- | ---: | ---: | ---: | ---: | --- |
| JSONL ON | 1/1 | 14 | 52.244 | 78,666 | One candidate record retrieved/selected from the failed training parent; later task succeeded |
| JSONL OFF | 1/1 | 13 | 48.281 | 67,567 | No retrieval/selection |

Common training used 16 attempts and 106,586 reported tokens. Its coder executed the original failing starter, repaired it, produced independently correct output and was accepted, but the parent exhausted the shared local cap after receiving that output. The full work round used 43/48 requests and three/three roots; five unused requests do not authorize a fourth root. ON was slower, used more requests and tokens, and did not establish a benefit. The selected candidate is a source-bound failure observation, not proof of an invented successful repair recipe. Each task family has one matched pair; the different code/request policy and stochastic runs prevent causal comparison to earlier truncated trials. All raw databases/reports are unchanged under independent read-only audits.

A separate human/web development round is **closed at an expired human-approval boundary**; it is excluded from the nine code/experience aggregate rows above. It used **18 actual HKGAI HTTP requests / 101,203 reported tokens**, 19 framework reservations (one known local refusal without HTTP), and three roots. The private writer resumed in a new process after the owner's actual **English** choice, wrote the current note, posted a private message and completed all independently checked criteria. The same one external human choice addressed the group clarification; it is two answered requests, not two independent decisions. Read-only audits match saved replies, workflow events, human membership and later writes. Private assignment-to-final time includes **2,912.756 seconds of recorded human waiting** and is not provider latency.

The group actually retrieved the official Python JSON page (24,388 bytes with matching receipt/hash), read it, posted messages and wrote an English draft, but stopped for exact-version scratch deletion approval. No such decision/release occurred; the original four-hour assignment deadline has now elapsed and the database remains unchanged in `waiting_approval`. Its full contract is unfulfilled: `scratch.txt` remains and the exact `Search status: unavailable` line is missing. Independent semantic review also found an incorrect fixed error column for all-whitespace input and an inaccurate suggestion that a normal final newline alone adds a blank streaming iteration. The draft is preserved rather than rewritten by the auditor. The separate source root failed after four empty/irrelevant Bing RSS reads and a local cap refusal. Direct retrieval from a supplied official URL does not establish relevant search. The read-only public plan's recorded 4→6 adjustment preserved counters and did not increase model allowance. Frozen earlier pending and final DB/ledger snapshots are bound in the [public evidence](../evaluation/evidence/development-summary.json). No new model call was made during this closeout; critical-action live coverage, relevant search, runtime Git provisioning and official evaluation remain open.

A fresh bounded group approval task on **4 November** completed in **7 HKGAI requests / 26,527 reported tokens**, one root. Its actual deletion request named the current scratch version. The owner's genuine decision was saved and matched to the addressed operator; recording approval alone had no file effect. A separate trusted release consumed that request once and recorded deletion of the exact version. Independent read-only checks verify the scratch is absent, retained input matches its provided hash, note creation follows deletion, and the actual group completion message follows the note. Start/resume used distinct processes with no model call during the human pause. Assignment-to-final time was **85.349 seconds**, including **68.286 seconds** of recorded human waiting. One subsequent read of the absent scratch produced a retained tool failure; it is not hidden or called a provider failure. The new case succeeds; the old expired group/search failures remain unchanged. This completes the bounded private-clarification/group-approval interface evidence, while denial/uncertainty retain their earlier engineering checks. Runtime/tests are unchanged from `4bd246a`; ten existing console-interaction regressions pass again. The [separate public record](../evaluation/evidence/development-summary.json) does not enter the nine code/experience comparison rows or establish general autonomy, task success, grades or learning gains.

A separate **11 November** [peer-review case](../evaluation/peer-review/cases.json) completed one root and two subtasks in **14 HKGAI requests / 55,769 reported tokens**, with **13.337 seconds** from assignment to final status and no human intervention. The coordinator delegated to the writer; the writer used an actual input-bearing delegation to assign the editor. A read-only audit checked the exact corrected room/time and all three ordered offer, receipt and read sequences (writer → editor → writer → coordinator). Roles and titles were declared in advance. The client requested the course ID `t2_hkgai-v3_fp8_1m_e7`; all 14 replies reported `t2_hkgai-v3_fp8_1m_e10_meeting`. The responses do not establish that the two labels identify an equivalent backend. This observation is separate from the matched comparisons and official results. See the [public audit summary](../evaluation/evidence/development-summary.json).

The optional Python Module Index adapter passed three direct runtime tool checks on **11 November**. Each query found a module page in the official index. The runtime fetched that page, saved its cited text and read it from the assigned task. Independent checks confirmed the official URL, a required content marker and the order of the search, retrieval and file read. The source criterion rejected all three cases before the file read. The checks used six actual public HTTPS requests across `json`, `pathlib` and `csv`. General web relevance remains open. [Development evidence](../evaluation/evidence/development-summary.json)

A separate **11 November HKGAI search run** completed both planned roots in **eight model requests and four public HTTPS GETs**, with no human intervention. For each module, the model chose the scoped search query, retrieved the result, read `source.md` and proposed completion. Read-only review matched each raw model tool call to the runtime dispatch, the index and page hashes, the exact saved excerpt, and the recorded read before acceptance. The saved excerpts were truncated at the configured text limit and retained the case-specific markers. Assignment-to-final times were **4.941 seconds for json** and **3.742 seconds for pathlib**. The client requested the course ID `t2_hkgai-v3_fp8_1m_e7`, and the eight replies reported `t2_hkgai-v3_fp8_1m_e10`. The backend mapping remains unconfirmed. The provider reported 39,060 total tokens. [Live search audit](../evaluation/evidence/development-summary.json)

The **11 November Git acceptance rehearsal** reproduced a false negative in the evaluator. A successful scoped runtime push to a local bare remote was missed because the verifier looked for the offline fixture backend. The updated evaluator checked the consumed approval and independently read the matching branch SHA on the original remote. The fixture also checked the pending and granted states before release, a changed remote, unavailable or missing refs, and a missing consumption record. The approval was scripted for the local fixture. The GitHub runtime trial still requires a designated target and credential. [Git acceptance evidence](../evaluation/evidence/development-summary.json)

On **11 November**, C07’s read-only audit reconciled 13 recorded slots across five retained HKGAI development batches. Two other slots lacked root records. In three training runs the coder succeeded, while the root failed after using the shared attempt cap. The parent and child used **7 + 8**, **3 + 13**, and **7 + 9** requests respectively. The final parent action was a progress message, an artifact acceptance, and a memory record respectively. None of those last turns submitted the root for verification. The audit used no new provider requests and the original database hashes matched after reading. C07’s paired single/multi replay uses scripted turns and supplies engineering evidence. [C07 evidence](../evaluation/evidence/development-summary.json)

### Retained evidence reanalysis

On November 20, coordinator review applied the contributed read-only readers
from PRs #67 and #58 to seven selected retained memory experiments and two
ordinary batch reports. Original experiment hashes match the already published
record, and all source JSON remained byte-identical after reading. The readers
check recorded consistency; this reanalysis does not authenticate database
events, rerun generated programs or create a new live experiment.

Two complete pairs remain comparable under their recorded conditions:

| Pair | ON/OFF verified probes | ON minus OFF requests | ON minus OFF successful seconds | ON minus OFF reported tokens |
| --- | --- | ---: | ---: | ---: |
| Code/report | 1/1 and 1/1 | 0 | -0.426 | +4,172 |
| Required-action JSONL | 1/1 and 1/1 | +1 | +3.963 | +11,099 |

Both training parents remain failed, with costs kept separate. A third selected
report retains failed ON/OFF goals and no selected experience; the other four
selected reports remain not comparable. None is discarded or counted as a new
successful run. One pair per family and differing protocols do not establish a
general learning gain, causal speed benefit or official score. Candidate-record
retrieval counts do not mean search-call counts.

Both ordinary batches passed internal consistency checks. Editing a copy's
completion summary was rejected; the originals were untouched. Review also
reproduced and corrected a memory-trial error outside the normal slot handler:
failed seed snapshots or usage accounting could previously continue into a
later replicate. Such failures now stop the trial, retaining error evidence and
unstarted slots. The reviewed runtime passed 768 engineering checks, including
21 actual-container checks, with nine optional UI skips. This review made zero
model calls; all engineering fault injections were scripted. Public hashes and
scope are in the [existing evidence summary](../evaluation/evidence/development-summary.json).

## 6. Failure analysis and corrections

| Observed issue | Evidence and correction | Verified limit |
| --- | --- | --- |
| Wrong schema/representation and stale exports | Preserve the failed code trial; clarify exact schemas and require exact-version output replacement after a new run | Repaired earlier probes completed; arbitrary program correctness remains unproven |
| Correct numbers without required handoff/read | Bind acceptance to actual source/recipient receipts and subsequent reads | Matching text/messages do not substitute for delivery |
| Coder/parent call exhaustion and unnecessary chatter | Expose current local/shared reservations; remove the redundant ten-call sublimit while keeping the aggregate cap; add explicit verification proposals | Batched submission/rejection/recovery and low-budget notices are engineering-tested; latest probes fully completed, but the training parent still exhausted its local 16-call limit |
| Prompt-to-file whitespace transcription | Add creating-human pending-root inputs and input-aware delegation | Real last-slot audit verifies exact custody/read; its overall task still failed |
| Incorrect hard-coded assertion on real input | The generated script expected two blank lines where current data has three; execution failed and exported no result | Earlier correct outputs still ended in manual recounting/truncation; the current required-action probes completed both full declared contracts |
| Output-length truncation | Reject incomplete replies, preserve usage/raw records and release no tools from that reply; prefer concise action-only turns | Earlier compact-context versions still truncated after correct execution. The new opt-in provider-required mode observed 43 conforming tool replies and two complete probes; this one round does not prove the failure eliminated generally |
| Git reconciliation observed the current configured remote instead of the original target; malformed ref bytes escaped the uncertainty boundary | Disposable-repository reproductions retained; match original remote URL and reapply local-path checks, validate a single matching ref, retain unknown effects on malformed observations | Six new regressions; 22 Git and 549 full checks pass. Actual GitHub runtime push remains unvalidated |
| Transport uncertainty | Preserve the DNS failure and stop without automatic reissue; distinguish it from a later complete length-limited reply with known no-tool effects | Quota/pricing/remaining balance remain unknown; no unlimited quota assumption |

Case-provided files are authored test inputs, not model-authored outputs, simulated human answers or granted approvals. Final outputs and execution still require the original independent checks. Saved failed records were not edited into successes.

## 7. Required evidence still missing

Current engineering checks do not close these live or submission requirements:

- Broad autonomous decomposition/negotiation and useful replanning outside declared role/title examples.
- Combined real search/retrieval, file CRUD and runtime GitHub commit/push under a designated branch, narrow credentials and real approvals. Developer publishing is different evidence.
- Broader human interaction/recovery scenarios if demanded by the official protocol. The bounded real private clarification and group approval/release paths now pass; live denial/uncertainty are not newly claimed.
- More varied matched memory trials and a live single/multi comparison using the merged C07 harness. Report null effects and regressions alongside gains.
- Prescribed mid-test and final runs, final dataset mapping, scoring and timing rules, memory and intervention handling, and performance and failure analysis. The [mid-test adapter](official-mid-test.md) prepares three scenarios with six tasks.
- Assemble all members’ commit-history screenshots and complete the presentation and final report.

Detailed ownership, acceptance and dependencies remain in the Roadmap; this draft does not create another task register. No score, completion percentage or final grade is inferred from check counts.

## 8. Contributions and AI assistance

Repository history preserves actual authors and reviews. The accepted contributions include Qingthefish's Codex-assisted backend/integration work and HelloWorld2333666's terminal, Git and evaluation foundations (PRs #7–#9), plus the C07 comparison and coordination audit (PRs #48–#50). Minho Joh (aminoacid11) reproduced setup on clean WSL, fixed CLI parsing, tested HKGAI and Docker, and added the GitHub Actions workflow. [D04 PR #52](https://github.com/Qingthefish/evolutionary-agent-lab/pull/52) · [I04 PR #53](https://github.com/Qingthefish/evolutionary-agent-lab/pull/53) Further claims must be checked against actual code and review history; repository access alone does not establish contribution. AI assistance was used for implementation, checks, documentation and review. Automated/Codex-assisted self-review is not independent teammate approval. Final per-member statements remain to be verified.

Jingran (jingran-jupiter) contributed the C06 instructor mid-test adapter, including input parsing, same-group preparation and automated checks. The coordinator adapted it to use a local course archive while keeping his authorship. [C06 source PR #54](https://github.com/Qingthefish/evolutionary-agent-lab/pull/54) · [Review evidence](team-roadmap.md#c06)

Jingran also contributed the [ordinary batch audit, PR #58](https://github.com/Qingthefish/evolutionary-agent-lab/pull/58)
and [memory evidence/effect reader, PR #67](https://github.com/Qingthefish/evolutionary-agent-lab/pull/67).
Coordinator review retained his commits and added the outer snapshot/accounting
stop correction. These are evaluation-engineering contributions, not evidence
of a learning gain or an official task pass.

On November 20, actual public GitHub main-branch commit-history pages were
captured through the author filter. The unedited screenshots below retain
titles, authors, dates and commit IDs. Their [manifest](contributions/manifest.json)
records source URLs, capture times, hashes and the baseline `5e7073b`, before
PR #69 integration. They show recorded history, not hours worked or guaranteed
individual grades; the coordinator capture shows the first history page.

| Member/account | Actual history screenshot |
| --- | --- |
| Qingthefish | [Coordinator history](contributions/04-qingthefish-main-history.jpg) |
| HelloWorld2333666 | [Software/evaluation history](contributions/02-helloworld-main-history.jpg) |
| Minho / aminoacid11 | [Setup/CI history](contributions/01-minho-main-history.jpg) |
| Jingran / jingran-jupiter | [Mid-test adapter history](contributions/03-jingran-main-history.jpg) |

## 9. Proposed presentation outline

The instructor announcement specifies a week-13 presentation and a report
**after** week 13; the report deadline is not automatically the presentation
date. Wednesday, **25 November 2026**, is week 13 if the shown 2 September
lecture is week 1. Treat November 25 as the preparation target, not a confirmed
group slot. The mailbox search found no separate presentation timetable or
stated duration. The following nine-minute structure is our proposal and can
be shortened when the actual format is confirmed.

### What the system is

A multi-agent execution platform takes a human task, lets permitted agents
choose and delegate work, gives each agent its own tools/files/experience, and
records actual handoffs, execution, human decisions and checked outcomes.
The allowed course model supplies language reasoning; trusted application code
owns state, access, limits and acceptance. The booking application is one test
output produced through that platform, not its definition. Experience means
retrieving scoped candidate observations, not retraining model weights or
assuming every prior fix is useful.

Opening script:

> We built a multi-agent execution platform that connects human requests to
> delegated tool work and verifiable delivery. The language model chooses
> actions; the platform enforces workspace boundaries, records evidence and
> decides completion through independent checks or actual human review.
> We evaluate both execution reliability and the observed effect of experience
> reuse, including failures and cases where memory does not help.

### Proposed slides and evidence

| Slide / time | Main point | Show or explain |
| --- | --- | --- |
| 1 / 0:45 | What problem the platform solves | A multi-step task needs delegation, executable work and checked delivery. State the instructor objective and the system definition above. |
| 2 / 1:15 | Architecture and responsibility | Human request → model-selected assignments → private tools/workspaces → snapshot handoff → independent checks → candidate experience. Explain what the model chooses and what code enforces. |
| 3 / 2:00 | One complete recorded workflow | Historical HKGAI JSONL probe: coordinator delegates original input, coder writes/runs source, offers output, coordinator receives/reads it and delivers the report. Both tasks succeeded under their declared contract. Label it a past real run, not a fresh live request. |
| 4 / 1:00 | Isolation and human control | Explain private files, actual restricted code execution, clarification, and approval versus action release. Reference the separately retained real private clarification and group-deletion evidence; they are not part of the JSONL run. |
| 5 / 1:15 | Experience and evaluation | Show the matched JSONL ON/OFF results and separate training cost. Both probes completed; ON took 14 versus 13 requests and 52.244 versus 48.281 seconds. One selected candidate is not proof of benefit. |
| 6 / 1:00 | Instructor mid-test status | Show the three scenario pairs and the exact verified state. Booking source has independent behavior evidence, but complete mid-test parent delivery is not established locally; other unrun/partial tasks stay visible. Do not convert engineering checks into a six-task score. |
| 7 / 1:00 | Failures and corrections | Separate our truncation, shared-budget, handoff and completion problems from the later HTTP 502 boundary. Explain parent reserves, bounded repair, exact-version checks and stopping on uncertain effects. Fixed-code live benefit remains unverified where service failure prevented execution. |
| 8 / 0:45 | Deliverables and remaining gates | Repository, architecture, truthful results/failure analysis, genuine contribution history and recorded demonstration. Remaining gates: allowed-model scenario runs, runtime GitHub evidence, final release/configuration and actual course submission requirements. |

A recorded walkthrough may be presented if the service remains unavailable,
with that limitation stated before showing it. It is preparation material,
not instructor approval to replace required live evaluation. Avoid making the
outage the whole presentation: the engineering design, real bounded outcomes,
null memory result and remaining delivery gaps are all part of the story.

### Demonstration runbook

The local ignored package `runs/presentation-20261120/` contains a hash-checked
viewer, exact prior outputs and a scoped 14-turn trace from the original
October 30 HKGAI ON probe. Its source experiment and database match the retained
published/audited hashes. The original six coordinator criteria and five coder
criteria were rechecked read-only and pass. The viewer makes zero model calls
and executes no generated code; original records remain unchanged.

From the project root:

```bash
python3 runs/presentation-20261120/view.py --section overview
python3 runs/presentation-20261120/view.py --section trace
python3 runs/presentation-20261120/view.py --section results
python3 runs/presentation-20261120/view.py --section memory
```

The source trace is a bounded declared-role/file-contract development case,
not proof of general autonomous planning or a passed instructor mid-test.
Training's failed parent remains failed. Keep the separate booking-artifact
reproduction below as an optional view of the partial software output; do not
combine the two examples into one supposedly completed official workflow.

If asked why a child can succeed while its root fails, explain that root
completion also requires delivery, receipt/read, report and final acceptance
within the shared budget. A working child artifact proves only its checked
subtask. If asked whether memory improves results, state that the mechanism
was exercised but the retained pairs do not establish general improvement.

### Recorded-artifact fallback

If live service is unavailable during presentation, label the demonstration as
reproduction of a previously generated artifact. On 19 November, the exact
developer booking snapshot from runtime `b028936` was copied from its retained
export without editing. The configured digest-pinned, no-network Python
container reproduced all 26 independent behavior checks and the ten original
generated unit tests, with successful cleanup. The independent checks cover
booking conflicts, adjacency, separate rooms/dates, cancellation/rebooking,
cross-process persistence and exactly one winner for concurrent same-slot
requests. The generated tests are supplementary, not an independent oracle.

The local demonstration package includes provenance, a hash-verifying launcher,
actual command/output transcript, result records and a short presentation
script. A changed-source negative control was refused before execution. No new
model request was made, and generated source was never run on the host. The
source package remains local rather than becoming a hard-coded platform
solution. Public hashes and scope are in the [evidence summary](../evaluation/evidence/development-summary.json).
This fallback proves artifact reproducibility only: it does not complete the
parent handoff, accept Software Task 1, exercise Task 2, establish a learning
gain or supply a teacher score.

## 10. Official-results fields — not yet filled

| Field | Status |
| --- | --- |
| Official dataset version/hash and exact task count | Mid-test: three scenarios and six ordered tasks, with source hashes recorded by C06. Final test dataset pending. |
| Instructor timing, human intervention, memory reset/repeat and scoring rules | Await verified protocol |
| Final revision/configuration and authorized evaluation budget | To freeze for the official run |
| Official completion rate, execution time and failure/memory analysis | No official results claimed |
| Presentation/report deadlines and delivery evidence | Confirm actual dates and requirements |

## 11. Mid-test execution record, 19 November

The mid-test has three four-agent scenarios and six ordered tasks. The retained
16 November software attempt failed after two requests. On 19 November two new
software Task 1 attempts also stopped after two requests each. Both new failures
record `finish_reason=length` at the 1,024 output-token limit, before any tool
from the rejected replies was released. Compact action guidance in the second
new attempt did not complete the task. The two new trials have 6,345 known
provider-reported tokens in total, plus unknown usage for the two rejected
completions. These counts cover the two new trials only.

| Scenario | Task 1 | Task 2 |
| --- | --- | --- |
| Software development | Three truncated Nov 19 attempts retained; fourth partial has an independently checked booking implementation, without completed parent delivery | Unrun |
| Newsroom | Unrun | Unrun |
| Securities fund | Unrun | Unrun |

Each new failure has a local read-only export containing the original prompt
and roles, full recorded runner dialogue, task state, tool calls, diagnostics
and configuration. The source databases remain preserved. Source versions and
the cumulative request allowance are recorded in the local round ledger.
The current six-task completion rate and final course score remain unreported.
Further runs need to verify the configured output ceiling, retain the same
group within each pair and undergo actual outcome review.

The authorized 4,096-output-token trial also stopped on its second reply with
`finish_reason=length`. A distinct fourth root limited the lead to coordination
and left implementation/execution with the original specialists. In 20 requests
it observed real lead-to-developer and developer-to-QA assignment, source
handoffs and actual execution. The developer's first script and QA's first
script exited zero but omitted declared export files; QA subsequently wrote and
exported its transcript. These failed exports remain in the record.

A separate reviewer-written script tested the exact current developer source
in the fixed no-network container. All 26 checks passed, including cross-process
persistence, five overlap shapes, cancellation/history/rebooking and two
concurrent bookers with exactly one winner. These are core behavior checks,
not an instructor rubric or proof of full delivery. The parent and its children
are still running, with no accepted completion proposal. The controller paused
at 20/22 requests and 242,924/247,500 reported tokens rather than reset limits
or force another request. This whole Nov 19 round has 26 requests across four
allocated roots, 252,542 known reported tokens and unknown usage on three
rejected replies. The three truncated roots remain failed; the partial root
does not count as a completed official task. [Selected evidence](../evaluation/evidence/development-summary.json)

Follow-up engineering adds optional current-budget guidance without fixed
delegation recipes, and sanitized missing-output export diagnostics. These
corrections need their own future live validation; no learning benefit, final
score or provider account balance is inferred from this rehearsal.

The original announcement specifies presentation in week 13 and the final
report after week 13. The 18 November Canvas check found the 15 November
mid-test release as the latest project notice and listed only `Mid_Test.zip`
under General Information. Exact final-test and submission dates still need
confirmation. [Course announcements](https://canvas.ust.hk/courses/73253/announcements)

The later local software round observed a fresh Task 1 failure after three
requests: the developer's first reply reached its 4,096 completion-token cap,
with 3,779 reported reasoning tokens and incomplete tool arguments. No tool
from that reply was dispatched. A separate read-only protocol diagnostic used
one further request on the issued model/host and executed no tool. A
`thinking.type=disabled` request still reported 37 reasoning tokens; this does
not establish a supported thinking control. Both raw replies and the cumulative
four-request ledger remain local. This observation explains one truncation;
it does not explain every earlier failure or establish a completed task.

PR #64 proposes an opt-in completion protocol and provider-pause handling.
Coordinator review corrected request credits that could exceed the actual-call
cap and a rejected-resume side effect. Original failed/uncertain attempts and
legacy credit rows are retained, with no credit applied to current hard limits.
The corrected source passed 724 engineering checks (including 21 real-container
checks), with nine UI skips. Contributor-only live run records were not part of
this review, and no scenario pass is claimed from the engineering checks.

The reviewed package merged through [PR #65](https://github.com/Qingthefish/evolutionary-agent-lab/pull/65)
as `0b1a63b`, after all three required remote jobs passed. A new development
root ran that fixed source with the opt-in finish protocol and no mid-run source
change. Its first request returned HTTP 502 after 1.10 seconds, before any tool
was executed. It remains at `provider_uncertain`; no automatic resend or
request credit was applied. This round's cumulative count is five actual
requests: the earlier failed root's three, one read-only protocol diagnostic,
and this uncertain request. Parsed valid replies report 9,001 tokens, the saved
rejected length reply reports 8,142, and the diagnostic reports 455: 17,598
known reported tokens, plus unknown usage for the 502. These figures are neither
account balance nor money. The new root and Task 2 are not completed. The
contributor's other live databases remain outside this local audit.

Later that evening, one explicitly released, counted resend on the same
unexpired root again returned HTTP 502. A separate minimal plain-chat request
with no tools also returned 502. The latest cumulative snapshot is **seven
actual requests**, including two diagnostics, and usage is unknown for three
attempts; the known 17,598 tokens are unchanged. The five-request snapshot
above and its original database hash are preserved. Neither request executed
a model tool, and no automatic retry or request credit followed. These
observations suggest the failure is not specific to the large tool payload;
they do not diagnose the service/account route or establish a provider-wide
outage. The current course API page still lists the same endpoint/model. The
root's original deadline is 20 November 00:38:23 Hong Kong time; quota recovery
does not extend it or authorize replay. The [recorded-artifact fallback](#recorded-artifact-fallback)
is available independently of that paused live run.

On November 20 at 10:14 Hong Kong time, one new owner-requested minimal
plain-chat observation also returned HTTP 502. The cumulative round is eight
requests, with four unknown-usage attempts; no tool was dispatched and no old
task was resumed. An earlier local environment lookup failed before transport
construction. Its record is retained separately; fixing environment export
released the same unissued reservation once. Known usage is unchanged. The
failure still does not establish its remote cause or a provider-wide outage.
