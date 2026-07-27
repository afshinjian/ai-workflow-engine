# Current Task

Mirror of `docs/TASK_QUEUE.md`'s `Current` set. Must contain exactly the same task ID(s) at the
same status as the task queue — `workflowctl check-task-state` fails otherwise.

## GOV-AUTO-01 — Local Human-Gated Task Runner

Status: Current

Authorized by the Human Owner on 2026-07-27 as a governance and developer-experience task. It is
not an AUTO-family stage and therefore has no `STAGE_REGISTRY.md` entry and no stage contract; its
authorization is this task record plus the Human Owner's written instruction.

Scope — create or modify only: `scripts/workflow-next.sh`, `scripts/workflow-approve.sh`,
`scripts/prompts/implement-next-task.md`, `docs/automation-workflow.md`, directly relevant script
tests, and the minimum governance/task-queue/current-task/changelog/completion-report/handoff
files needed to record the task. No dependencies added; Bash and standard tools only.

Objective: automate the mechanical parts of the repository's standard task cycle — preflight,
prompt delivery, change review, and the commit itself — **without replacing the Human Owner
approval gate**. Push, merge, branch changes, upstream changes, and stash mutation are never
performed by either script.

Implemented and validated 2026-07-27; **not committed**. Awaiting Human Owner approval.
AUTO-004 is not authorized and must not be started.
