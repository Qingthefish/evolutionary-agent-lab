# Workflow foundation: architecture and boundaries

## Implemented boundary

The standard-library Python package `agent_lab` owns local SQLite-backed workflow state and a controlled text-file broker. Its public API is called by a trusted local application. There is no server, authenticated user session, model adapter, autonomous planner, arbitrary-code executor, or process sandbox. Opening the database or raw workspace paths directly bypasses application checks; protect them using normal operating-system access controls. Tests use temporary directories and demos use fresh ignored run directories.

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

Only a running task's assignee can finish it. Success requires a nonempty map of named passing checks supplied by a trusted caller or computed by a trusted verifier inside the task-state transaction, and every direct child must have succeeded. Failure requires a reason. The scripted workflow demo reads its fixed note back before passing its checks. `FileTools.complete_from_text` hashes actual file bytes against trusted expected UTF-8 text within the transaction. Missing or mismatched artifacts cannot complete the task. Expected text and verifier callables must never come from model-controlled arguments. This exact-text verifier is not a general verifier for arbitrary tasks or code-test results; accepting model-provided passing booleans would not satisfy that requirement.

Goal and subtask status fractions are reported separately. Failed, cancelled, pending, and waiting assignments are not counted as successful or silently removed from the denominator. Elapsed time runs from assignment to terminal state, including time awaiting a human. Human waiting is also recorded separately, including an open wait, and survives restart. Wall-clock durations assume a reasonably stable system clock; this is not a distributed-clock protocol.

Offline reports explicitly identify themselves as fixtures, make zero model calls, and are not valid model-performance benchmarks. There is no model-call time, token usage, or learning result to report yet.

## Checks and remaining work

### Controlled file API

`FileTools` binds one private, current-user-owned file root to the workflow database by its filesystem identity. Each task has a separate directory and only its assigned agent may operate on it while running. This is stronger than filename conventions within the broker API, but it does not restrict a process that bypasses the broker. Untrusted code must not run on the host or receive broker descriptors.

File paths must be relative POSIX paths without empty, dot, dot-dot, backslash, or NUL components. Directory traversal uses anchored descriptors and no-follow opens. Reads/updates/deletes require regular single-link files, reject symbolic/hard links and special files, validate UTF-8, and enforce a configurable byte limit. Creates never overwrite; updates/deletes require the expected prior SHA-256. Updates replace through a temporary file in the same directory. Broker operations produce task audit events and content receipts. The default file limit is one MiB. Unsupported OS descriptor operations fail closed; Windows is not currently supported by this broker.

Explicit handoff copies the offered text into a stored snapshot and records a manifest binding its source, recipient task, digest, and byte count. Only the designated assigned recipient can import it once, into a fresh path in its own task directory. Source and recipient must share a conversation; a failed/cancelled source cannot supply its snapshot. Recipient import verifies snapshot integrity. Future source edits do not change an existing offer. This is application-level transfer, not direct cross-workspace access or autonomous negotiation.

SQLite serializes cooperating broker operations and task transitions. Filesystem effects and SQLite commits are not a single atomic transaction: a crash can leave an unrecorded file or orphan snapshot. Inspect content and reconcile before retrying; do not assume the audit log proves the absence of a disk effect. Same-user hostile host processes and OS-level file access are outside this broker's boundary. No storage/retention quota for the number of files or snapshots is implemented yet.

`execute_code` always refuses execution until a real process sandbox is implemented. No host subprocess fallback, network operation, model call, or Git operation is hidden behind it. File ownership checks are not evidence of satisfying the full sandbox requirement.

Behavior checks cover conversation access, delegation ownership, parent/child completion, restart/resume, wrong-user responses, exact-action approval, stale and duplicate release, concurrent release, denied/failed parent cancellation, and accounting. The fixture additionally checks that existing run directories are not overwritten.

Additional checks cover controlled file CRUD, ownership and path escape attempts, symlink/hard-link/special-file rejection, stale digests, corrupted/duplicate/concurrent handoff, restart, mismatched completion artifacts, and refusal of unconfigured execution.

Remaining integrations include model-facing tool registration, allowed-provider calls, autonomous negotiation/allocation, search and retrieval, code execution, enforced process sandboxes, Git operations, per-agent experience memory, task-specific verification beyond exact text, and a minimal interactive UI. The mandatory course requirements remain the acceptance target; this foundation implements only part of their supporting infrastructure.
