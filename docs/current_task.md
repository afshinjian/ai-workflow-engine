# Current Task

Mirror of docs/TASK_QUEUE.md's Current set. Must contain exactly the same task ID(s) at
the same status as the task queue — workflowctl check-task-state fails otherwise.

## No task is currently active

AUTO-011 — Unified Provider and Agent Result Contract was closed `Current -> Done` on 2026-08-01 by
explicit Human Owner approval, after a required fourteen-point scope, contract, and compatibility
verification that passed in full. The approved implementation was committed together with this
closeout in one local commit, which was then pushed. **No PR was opened and no merge was
performed.**

The engine now has one canonical result contract for every execution it performs:

    WorkflowService -> Provider Runtime -> AgentRunResult

`agentos_workflow/results.py` delivers `AgentRunResult`, reached from AUTO-010's `ProviderRunResult`
through `agent_run_result_from_provider_run`. Compatibility is preserved by projection, not by
interface change: the Provider Runtime is byte-identical, all 240 of its tests pass, and all 25 live
CLI acceptance tests pass with zero skips.

The contract reuses rather than redeclares. `RunStatus` *is* `ProviderRunStatus` — an alias, not a
second enum — and `ProviderVerdict`, `ProviderFailureKind`, `RetryClassification`, `ProviderKind`,
`AgentKind`, and `WorkflowState` are all reused, so no mapping between two vocabularies can drift.
Only `ExecutionMode` and `ArtifactKind` are new, and a test asserts they are the only enums the
module declares.

Status and verdict stay deliberately distinct. AUTO-010's deferred D-3 is narrowed, not resolved by
collapsing: a `COMPLETED` run reporting `fail` is a QA provider finding real defects — a successful
execution with a failing verdict — and merging the two axes would destroy that.

`recommended_next_state` is advisory only. No module in `agentos_workflow` outside the contract
contains the string, no workflow transition depends on it, and the result exposes no callable that
executes, transitions, or approves anything.

The Current set is therefore empty. Under self-governance.yaml's maximum_current_tasks: 1
this is a legal state — the maximum is a ceiling, not a quota.

Every remaining task (docs/remaining_tasks.md) is Planned and requires its own fresh
written Human Owner authorization naming it before it may become Current. Closing AUTO-011
authorizes no successor: AUTO-012, the three non-blocking defects AUTO-011 deferred (D-8, D-9,
D-10), the four AUTO-010 deferred (D-3 through D-6), the six AUTO-009 deferred (D1-D6), and every
later roadmap phase all remain unauthorized.
