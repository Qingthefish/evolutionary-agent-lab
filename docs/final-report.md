# Evolutionary Multi-Agent Collaboration System — Draft Report

MAIE5221 / ARIN5202. **Development draft, updated 2026-11-11 (Asia/Hong_Kong).** This is not a final submission or an official benchmark report. Official tasks, scoring/intervention rules, final member contribution evidence and submission dates have not been incorporated into this draft. The instructor announcement remains the authority in [requirements](requirements.md).

## 1. Objective and verified scope

Build a general multi-agent platform that delegates work, uses tools in private workspaces, interacts with humans, retains per-agent experience and automatically records task completion and execution time. Our implementation emphasizes checked execution and bounded recovery. An original research paper, a specific business vertical and an elaborate frontend are not prerequisites.

The latest engineering source at `f66271b` passed **552 checks**, with zero skips, errors or failures, including **19 actual-container integration checks and nine UI checks**. These are software checks, not 552 instructor tasks. The earlier opt-in required-action trial at `a52c34a` observed 43 tool-call replies without free-text narration/truncation and two independently audited complete JSONL probe roots. This bounded result does not establish general reliability or an official score. The [architecture](architecture.md) documents the actual contracts and limits; the [Roadmap](team-roadmap.md) remains the sole task/owner register.

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
| ON | 1/1 | 13 | 20.369 | 70,790 | Two retrievals, one explicit candidate selection, later outcome succeeded |
| OFF | 1/1 | 13 | 20.795 | 66,618 | No retrieval or selection |

Common training cost was 15 attempts and 78,230 reported tokens; its coder succeeded but its parent failed. The ON candidate was source-bound observed experience, not proof of a newly learned algorithm. Both arms used 13 attempts; ON used more tokens. One pair and a small time difference establish exercised experience use, **not a general learning advantage**. Different cases/code/budgets across later rounds cannot establish a causal improvement either.

The current JSONL pair uses identical case content, initial frozen memory, allowed model, non-memory tools, prompt/view policy and budgets; both request provider-required tools. Training is separate and not silently amortized:

| Condition | Root completion | Attempts | Assignment-to-final seconds | Provider-reported tokens | Experience use |
| --- | ---: | ---: | ---: | ---: | --- |
| JSONL ON | 1/1 | 14 | 52.244 | 78,666 | One retrieval/selection of a coordinator observation sourced from the failed training parent; later task succeeded |
| JSONL OFF | 1/1 | 13 | 48.281 | 67,567 | No retrieval/selection |

Common training used 16 attempts and 106,586 reported tokens. Its coder executed the original failing starter, repaired it, produced independently correct output and was accepted, but the parent exhausted the shared local cap after receiving that output. The full work round used 43/48 requests and three/three roots; five unused requests do not authorize a fourth root. ON was slower, used more requests and tokens, and did not establish a benefit. The selected candidate is a source-bound failure observation, not proof of an invented successful repair recipe. Each task family has one matched pair; the different code/request policy and stochastic runs prevent causal comparison to earlier truncated trials. All raw databases/reports are unchanged under independent read-only audits.

A separate human/web development round is **closed at an expired human-approval boundary**; it is excluded from the nine code/experience aggregate rows above. It used **18 actual HKGAI HTTP requests / 101,203 reported tokens**, 19 framework reservations (one known local refusal without HTTP), and three roots. The private writer resumed in a new process after the owner's actual **English** choice, wrote the current note, posted a private message and completed all independently checked criteria. The same one external human choice addressed the group clarification; it is two answered requests, not two independent decisions. Read-only audits match saved replies, workflow events, human membership and later writes. Private assignment-to-final time includes **2,912.756 seconds of recorded human waiting** and is not provider latency.

The group actually retrieved the official Python JSON page (24,388 bytes with matching receipt/hash), read it, posted messages and wrote an English draft, but stopped for exact-version scratch deletion approval. No such decision/release occurred; the original four-hour assignment deadline has now elapsed and the database remains unchanged in `waiting_approval`. Its full contract is unfulfilled: `scratch.txt` remains and the exact `Search status: unavailable` line is missing. Independent semantic review also found an incorrect fixed error column for all-whitespace input and an inaccurate suggestion that a normal final newline alone adds a blank streaming iteration. The draft is preserved rather than rewritten by the auditor. The separate source root failed after four empty/irrelevant Bing RSS reads and a local cap refusal. Direct retrieval from a supplied official URL does not establish relevant search. The read-only public plan's recorded 4→6 adjustment preserved counters and did not increase model allowance. Frozen earlier pending and final DB/ledger snapshots are bound in the [public evidence](../evaluation/evidence/development-summary.json). No new model call was made during this closeout; critical-action live coverage, relevant search, runtime Git provisioning and official evaluation remain open.

A fresh bounded group approval task on **4 November** completed in **7 HKGAI requests / 26,527 reported tokens**, one root. Its actual deletion request named the current scratch version. The owner's genuine decision was saved and matched to the addressed operator; recording approval alone had no file effect. A separate trusted release consumed that request once and recorded deletion of the exact version. Independent read-only checks verify the scratch is absent, retained input matches its provided hash, note creation follows deletion, and the actual group completion message follows the note. Start/resume used distinct processes with no model call during the human pause. Assignment-to-final time was **85.349 seconds**, including **68.286 seconds** of recorded human waiting. One subsequent read of the absent scratch produced a retained tool failure; it is not hidden or called a provider failure. The new case succeeds; the old expired group/search failures remain unchanged. This completes the bounded private-clarification/group-approval interface evidence, while denial/uncertainty retain their earlier engineering checks. Runtime/tests are unchanged from `4bd246a`; ten existing console-interaction regressions pass again. The [separate public record](../evaluation/evidence/development-summary.json) does not enter the nine code/experience comparison rows or establish general autonomy, task success, grades or learning gains.

A separate **11 November** [peer-review case](../evaluation/peer-review/cases.json) completed one root and two subtasks in **14 HKGAI requests / 55,769 reported tokens**, with **13.337 seconds** from assignment to final status and no human intervention. The coordinator delegated to the writer; the writer used an actual input-bearing delegation to assign the editor. A read-only audit checked the exact corrected room/time and all three ordered offer, receipt and read sequences (writer → editor → writer → coordinator). Roles and titles were declared in advance. The client requested the course ID `t2_hkgai-v3_fp8_1m_e7`; all 14 replies reported `t2_hkgai-v3_fp8_1m_e10_meeting`. The responses do not establish that the two labels identify an equivalent backend. This observation is separate from the matched comparisons and official results. See the [public audit summary](../evaluation/evidence/development-summary.json).

The optional Python Module Index adapter passed three direct runtime tool checks on **11 November**. Each query found a module page in the official index. The runtime fetched that page, saved its cited text and read it from the assigned task. Independent checks confirmed the official URL, a required content marker and the order of the search, retrieval and file read. The source criterion rejected all three cases before the file read. The checks used six actual public HTTPS requests across `json`, `pathlib` and `csv`. General web relevance remains open. [Development evidence](../evaluation/evidence/development-summary.json)

A separate **11 November HKGAI search run** completed both planned roots in **eight model requests and four public HTTPS GETs**, with no human intervention. For each module, the model chose the scoped search query, retrieved the result, read `source.md` and proposed completion. Read-only review matched each raw model tool call to the runtime dispatch, the index and page hashes, the exact saved excerpt, and the recorded read before acceptance. The saved excerpts were truncated at the configured text limit and retained the case-specific markers. Assignment-to-final times were **4.941 seconds for json** and **3.742 seconds for pathlib**. The client requested the course ID `t2_hkgai-v3_fp8_1m_e7`, and the eight replies reported `t2_hkgai-v3_fp8_1m_e10`. The backend mapping remains unconfirmed. The provider reported 39,060 total tokens. [Live search audit](../evaluation/evidence/development-summary.json)

The **11 November Git acceptance rehearsal** reproduced a false negative in the evaluator. A successful scoped runtime push to a local bare remote was missed because the verifier looked for the offline fixture backend. The updated evaluator checked the consumed approval and independently read the matching branch SHA on the original remote. The fixture also checked the pending and granted states before release, a changed remote, unavailable or missing refs, and a missing consumption record. The approval was scripted for the local fixture. The GitHub runtime trial still requires a designated target and credential. [Git acceptance evidence](../evaluation/evidence/development-summary.json)

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
- More varied matched experience trials and the pending single/multi baseline; report regressions or null effects as well as gains.
- The actual official dataset/protocol adapter, prescribed runs, scoring/timing/memory/intervention semantics, and performance/failure analysis.
- Another member's clean setup, each member's genuine significant contribution, final commit-history screenshots and the required presentation/report delivery.

Detailed ownership, acceptance and dependencies remain in the Roadmap; this draft does not create another task register. No score, completion percentage or final grade is inferred from check counts.

## 8. Contributions and AI assistance

Repository history preserves actual authors and reviews. The accepted contributions include Qingthefish's Codex-assisted backend/integration work and HelloWorld2333666's terminal/Git/evaluation foundations (PRs #7–#9). Further claims must be checked against actual code and review history; repository access alone does not establish contribution. AI assistance was used for implementation, checks, documentation and review. Automated/Codex-assisted self-review is not independent teammate approval. Final per-member statements and required screenshots remain to be verified.

## 9. Proposed presentation outline

The announcement requires a week-13 presentation; confirm its exact date/format. This outline and its length are our proposal:

1. Instructor objective and the engineering problem: observable completion under bounded execution.
2. Task lifecycle: original inputs, model-selected delegation, isolated code execution, handoff and independent verification.
3. Human boundaries and private experience: actual grants/outcomes rather than prompt-only restrictions.
4. Real development results, including failed parents, unrun probes and the two bounded memory pairs and actual private/group human decisions.
5. Demonstration and limitations: label recorded traces and scripted fixtures clearly; never present them as a new live model run.
6. Official test results and remaining failure analysis, to be filled only after the prescribed evaluation.

## 10. Official-results fields — not yet filled

| Field | Status |
| --- | --- |
| Official dataset version/hash and exact task count | Not present in this draft |
| Instructor timing, human intervention, memory reset/repeat and scoring rules | Await verified protocol |
| Final revision/configuration and authorized evaluation budget | To freeze for the official run |
| Official completion rate, execution time and failure/memory analysis | No official results claimed |
| Presentation/report deadlines and delivery evidence | Confirm actual dates and requirements |
