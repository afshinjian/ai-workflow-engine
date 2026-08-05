# Current Task

Mirror of docs/TASK_QUEUE.md's Current set. Must contain exactly the same task ID(s) at
the same status as the task queue — workflowctl check-task-state fails otherwise.

## No task is currently active

GOV-AUTO-10 — AUTO-016 Integrated Runner Contract Definition — was registered as the sole Current
task and closed `Current -> Done` on 2026-08-05, after the Human Owner selected **Integrated
Milestone Automation Runner** as the AUTO-016 capability. It is a documentation-only governance
task: it produced the finalized AUTO-016 stage contract
(`docs/workflow-automation/stage-prompts/AUTO-016.md`, now Revision 4) and its independent review
(`docs/reports/workflow-automation/AUTO-016-contract-review.md`, verdict "CONTRACT READY FOR HUMAN
OWNER AUTHORIZATION"). The Current set is therefore empty again.

On 2026-08-05 the Human Owner also ruled the three decisions the closure had left open —
DEC-016-002 (provider adapters owned by the milestone-runner package, under
`milestone_runner/providers/`), DEC-016-005 (external default plan root; repository-local plans only
at exact contract-allowlisted paths; no repository plan discovery), and DEC-016-006 (prototype
unchanged until live acceptance, deprecated afterwards, never automatically deleted). The rulings
are recorded in `docs/DECISION_LOG.md` and propagated into contract Revision 4. No new Current task
was created for them: recording a ruling in the governance documents is not a task transition.

Neither the contract nor the rulings authorize anything. AUTO-016 remains unregistered,
unauthorized, and unimplemented — it has no `STAGE_REGISTRY.md` §4 row, no task entry, no branch, and
no source. No contract decision remains open, but allowlist sign-off, acceptance-plan approval, a
fresh authorization preflight, and an explicit authorization statement are still required before
implementation may begin.

## Prior current-task history

AUTO-015 — Deterministic Next-Stage Proposal and Governed Prompt Generation was closed `Current ->
Done` on 2026-08-05 by explicit Human Owner approval, after implementation on branch
`feature/auto-015-successor-planning` (commit `05b819e`) was published via pull request #17 and
merged into `main` as `e325f95`. The Current set is therefore empty. Under
self-governance.yaml's `maximum_current_tasks: 1`, this is a legal state — the maximum is a
ceiling, not a quota.

Every remaining task is Planned and requires its own fresh written Human Owner authorization.
Closing AUTO-015 authorizes no successor. AUTO-016 remains unauthorized and untouched.
