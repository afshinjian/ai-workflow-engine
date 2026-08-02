# Current Task

Mirror of docs/TASK_QUEUE.md's Current set. Must contain exactly the same task ID(s) at
the same status as the task queue — workflowctl check-task-state fails otherwise.

## No task is currently active

GOV-4 — Isolate Claude live-test configuration per attempt and add bounded test-only format
retries was closed `Current -> Done` on 2026-08-02. It was registered and authorized in one act,
as an ordinary (non-AUTO/GOV-AUTO-family) engine task record, and resolves two independent
pre-AUTO-013 live acceptance test-harness defects: session-scoped forwarding of the configured
Claude account's real `CLAUDE_CONFIG_DIR` (letting Claude Code's own continuity state accumulate
across invocations), and real Claude's non-deterministic first-attempt compliance with the strict
bare-JSON auto-mode contract. Scope was test-only; no production code, parser, provider argv,
permission mode, or workflow state changed. Report: `docs/reports/GOV-4-completion-report.md`.

The Current set is therefore empty. Under self-governance.yaml's maximum_current_tasks: 1
this is a legal state — the maximum is a ceiling, not a quota.

Every remaining task (docs/remaining_tasks.md) is Planned and requires its own fresh
written Human Owner authorization naming it before it may become Current. Closing GOV-4
authorizes no successor: AUTO-013, the three non-blocking defects AUTO-012 deferred (D-11, D-12,
D-13), the three AUTO-011 deferred (D-8 through D-10), the four AUTO-010 deferred (D-3 through
D-6), the six AUTO-009 deferred (D1-D6), and every later roadmap phase all remain unauthorized.
