# Remaining Work

Mirror of `docs/TASK_QUEUE.md`'s not-yet-`Done` entries (`Current` and `Planned`). Statuses here
must agree with the task queue — `workflowctl check-task-state` fails otherwise. Full task
detail (dependencies, deliverables, acceptance criteria): `docs/MASTER_ROADMAP.md`.

## M-3 — Non-interactive agent execution

Status: Planned

Codex read-only review and scoped OpenCode writes, strict report schemas, isolation, timeouts,
independent claim verification, and the workflow-state capabilities deferred from Milestone 2.
Tasks T-301..T-306. Depends on Stage 0 completing first.

## M-4 — Controlled commit and push

Status: Planned

Approval-bound staging allowlists, commit verification, protected-path enforcement,
remote/upstream checks, and explicit push gates. Tasks T-401..T-404. Depends on M-3.
