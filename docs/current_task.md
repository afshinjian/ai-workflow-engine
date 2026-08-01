# Current Task

Mirror of docs/TASK_QUEUE.md's Current set. Must contain exactly the same task ID(s) at
the same status as the task queue — workflowctl check-task-state fails otherwise.

## No task is currently active

AUTO-012 — Configurable Approval Policy, Persistence, and Invalidation was closed `Current -> Done`
on 2026-08-01 by explicit Human Owner approval. The approved implementation was committed together
with this closeout in one local commit, which was then published.

The engine now has a reusable approval subsystem for future workflow gates:

    WorkflowService -> ApprovalService -> policy resolution, request persistence,
                                          manual decisions, timeout decisions,
                                          checksum binding, invalidation

A strict typed policy resolves across built-in defaults, project configuration, per-gate
configuration, and per-run override into an immutable snapshot that later configuration changes
cannot retroactively alter. Approvals are append-only events in a per-workflow `approvals.jsonl`
written through the existing `StateStore` discipline, with the current request derived by replay,
so no decision is ever overwritten. Deadlines are absolute timezone-aware UTC instants on disk
evaluated lazily — no thread, timer, sleep, or scheduler exists in the module — so a deadline
survives a process or machine restart. Every approval binds four checksums, recomputed immediately
before consumption; any change invalidates it, records which checksum changed, and blocks reuse.

`AUTO_APPROVE` is refused when inherited from a broad default and accepted only from the specific
gate or a per-run override, so automatic approval is never acquired by inheritance.

A separate governance act accompanied the stage: `HUMAN_AUTHORIZATION_MODEL.md` moved to v2.0 with
a new §5a recording the Human Owner's decision that future workflow modes may use configurable
approval gates governed by `ApprovalService`. That decision authorizes the **subsystem only** —
never a specific Preparation, Reviewer, or Implementer workflow, never a gate placement, and never
a successor stage — and relaxes none of the existing safety properties.

**No workflow mode, lifecycle, or state was implemented.** `WorkflowState` remains 19 members with
37 transition edges.

The Current set is therefore empty. Under self-governance.yaml's maximum_current_tasks: 1
this is a legal state — the maximum is a ceiling, not a quota.

Every remaining task (docs/remaining_tasks.md) is Planned and requires its own fresh
written Human Owner authorization naming it before it may become Current. Closing AUTO-012
authorizes no successor: AUTO-013, the three non-blocking defects AUTO-012 deferred (D-11, D-12,
D-13), the three AUTO-011 deferred (D-8 through D-10), the four AUTO-010 deferred (D-3 through
D-6), the six AUTO-009 deferred (D1-D6), and every later roadmap phase all remain unauthorized.
