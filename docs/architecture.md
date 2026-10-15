# Workflow foundation: architecture and boundaries

## Implemented boundary

The standard-library Python package `agent_lab` owns local SQLite-backed workflow state. Its public API is called by a trusted local application. There is no server, authenticated user session, model adapter, autonomous planner, arbitrary-code executor, or filesystem sandbox. Opening the database directly bypasses application checks; protect the database using normal operating-system access controls. Tests use temporary directories and the demo uses a fresh ignored run directory.

The next model integration must keep identity, transition authority, and completion validation outside model-controlled arguments. Never expose `register_actor`, `respond`, or arbitrary passing `checks` as tools a model can call to impersonate a user or certify its own result.

## Durable records

- Actors have an immutable human/agent kind. Registration is a trusted setup operation.
- Conversations have explicit membership. A private chat has exactly one human and one agent; group chats contain human and agent participants. Reads and writes check membership.
- Tasks belong to a conversation, have an assigned agent, and may reference a parent. An assigned agent can create child work for another participating agent while the parent is running. This is delegation infrastructure, not autonomous role negotiation.
- Human requests record a prompt, the addressed human, response, and optional canonical action/digest. SQLite transactions commit each state change together with its audit event.
- Audit events record task creation, delegation, start, human requests/responses, action release, completion, failure, and cascading cancellation.

## State and human-response rules

Tasks begin pending and can start only through their assigned agent. Running tasks may await clarification or approval. Only the addressed human can reply once; a valid clarification or approval resumes the same task. Denial cancels the task and all unfinished descendants. A failed parent also cancels unfinished descendants. Completed tasks cannot be restarted or rewritten.

Approval is bound to the canonical JSON representation of an exact action, including all supplied arguments. A changed branch, commit, or other argument invalidates the match. A request is usable only in its resumed task revision; a later human request makes older approvals stale. Action release is transactional and at most once, including across multiple database connections. A task cannot succeed while its current approved action remains unreleased.

**Release is not external execution.** A future executor must take the exact returned action and execute it with the applicable sandbox and resource checks. An approval does not grant authority the human does not already possess. Authenticated identity, tool-specific permission, expiry, and resource-scope enforcement must be added at that boundary. There is no permission-management service in this foundation.

At-most-once release does not guarantee exactly-once effects. A process may crash after consuming approval and before or after the external action. Do not replay the effect automatically: reconcile the external state and obtain a new applicable approval when needed. Similarly, cancellation cannot undo an already released/in-flight effect. Future tools need idempotency or explicit reconciliation.

## Completion and accounting

Only a running task's assignee can finish it. Success requires a nonempty map of named passing checks supplied by a trusted caller, and every direct child must have succeeded. Failure requires a reason. The scripted demo independently reads its fixed note back before passing its checks. A general artifact verifier is still required before model-backed evaluation; accepting model-provided booleans would not satisfy that requirement.

Goal and subtask status fractions are reported separately. Failed, cancelled, pending, and waiting assignments are not counted as successful or silently removed from the denominator. Elapsed time runs from assignment to terminal state, including time awaiting a human. Human waiting is also recorded separately, including an open wait, and survives restart. Wall-clock durations assume a reasonably stable system clock; this is not a distributed-clock protocol.

Offline reports explicitly identify themselves as fixtures, make zero model calls, and are not valid model-performance benchmarks. There is no model-call time, token usage, or learning result to report yet.

## Checks and remaining work

Behavior checks cover conversation access, delegation ownership, parent/child completion, restart/resume, wrong-user responses, exact-action approval, stale and duplicate release, concurrent release, denied/failed parent cancellation, and accounting. The fixture additionally checks that existing run directories are not overwritten.

Remaining integrations include allowed-provider tool calls, autonomous negotiation/allocation, search and retrieval, file CRUD, code execution, enforced sandboxes and artifact transfer, Git operations, per-agent experience memory, artifact verification, and a minimal interactive UI. The mandatory course requirements remain the acceptance target; this foundation implements only part of their supporting infrastructure.
