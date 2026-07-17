# Context — Fresh-Session Recovery

Read this first if you are a new AI session (or a human) picking up work on
`ai-workflow-engine` with no memory of prior conversations. Never assume prior chat history is
available — everything you need is in these files.

## Read order

1. `docs/AGENT_PROTOCOL.md` — what you're allowed to do, what requires human approval, and the
   review discipline this project uses.
2. `docs/PROJECT_STATE.md` — overall condition, what's done, what's in progress, what's planned,
   any blockers.
3. `docs/current_task.md` — the exactly-one active task right now, with its acceptance
   criteria.
4. `docs/TASK_QUEUE.md` — everything else, in priority order, with dependencies noted inline.
5. `handover/PROJECT_HANDOVER.md` — narrative detail on what changed most recently and why,
   checksum-verified against tampering by `handover/PROJECT_CHECKSUM.md`.
6. Check repository status: `git status`, `git log --oneline -10`, run the test suite. Trust
   what you observe over what any document claims — documents can drift; `git` and a passing
   test suite cannot lie about the working tree's actual state.
7. Continue from there. If a document and the actual repository state disagree, that
   disagreement is itself the most urgent thing to report — don't silently pick one.

## Why this project looks the way it does

- It is a **tool**, not (until this task) a project that used its own tool on itself.
  `examples/amozesh_konkur.yaml` governs a *separate* repository; `self-governance.yaml` (added
  by this task) is the first config pointing the tool at its own source.
- It follows a strict, incremental milestone roadmap (`docs/milestones.md`) precisely because
  its subject matter is "don't trust an agent's self-report" — the project holds itself to that
  same standard. Every milestone so far has gone through independent fresh review before being
  called done; see `docs/AGENT_PROTOCOL.md` for exactly how.
- Nothing destructive (`git push`, deleting files, changing governance rules) happens without
  explicit human approval, every time, regardless of what was approved before.

## If you're about to touch the governance documents themselves

`docs/PROJECT_STATE.md`, `docs/TASK_QUEUE.md`, `docs/current_task.md`, and
`docs/remaining_tasks.md` are cross-checked for consistency by `workflowctl check-task-state`
and `workflowctl check-governance` — a task ID's status must agree everywhere it's mentioned.
Run `workflowctl verify --config self-governance.yaml` after editing any of them.
