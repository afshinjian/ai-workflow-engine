# Current Task

Mirror of `docs/TASK_QUEUE.md`'s `Current` set. Must contain exactly the same task ID(s) at the
same status as the task queue — `workflowctl check-task-state` fails otherwise.

## No task is currently active

AUTO-004 — Claude Code CLI and Codex CLI providers was closed `Current → Done` on 2026-07-28 by
explicit Human Owner decision: implemented, validated, approved, and committed locally as
`84616d5`, then published and merged into `main` under the same decision. Registry state
`IN_PROGRESS → COMPLETE` (`docs/workflow-automation/STAGE_REGISTRY.md` §4, §5).

The `Current` set is therefore empty. Under `self-governance.yaml`'s `maximum_current_tasks: 1`
this is a legal state — the maximum is a ceiling, not a quota — and it is the state the Human
Owner's decision requires to be verified before AUTO-005's authorization is recorded.

Every remaining task (`docs/remaining_tasks.md`) is `Planned` and requires its own fresh written
Human Owner authorization naming it before it may become `Current`. Closing AUTO-004 authorizes
no successor (`docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 16).
