# Current Task

Mirror of docs/TASK_QUEUE.md's Current set. Must contain exactly the same task ID(s) at
the same status as the task queue — workflowctl check-task-state fails otherwise.

## AUTO-016 — Integrated Milestone Automation Runner

Status: Current

Registered and authorized by the Human Owner on 2026-08-05: "I authorize AUTO-016 implementation
under the finalized AUTO-016 contract and its exact implementation allowlist." AUTO-016 had never
been registered before, so this entry records both its registration and its authorization.
Predecessor AUTO-015 is `COMPLETE`, merged as `e325f95`, and published via pull request #17.
Registry state `NOT_STARTED → AUTHORIZED` (`docs/workflow-automation/STAGE_REGISTRY.md` §4/§5).
Authorization is bounded to the finalized Revision 4 contract
(`docs/workflow-automation/stage-prompts/AUTO-016.md`, SHA-256
`56f6a8f5720f30543f5b0623f5cb52ffa2cc45cbe51be8c5f9b9f5f256b90a7e`) and its exact nineteen-file
implementation allowlist (§23), with the forbidden surface (§24) unchanged. Full scope:
`docs/TASK_QUEUE.md`.

**Registration and authorization only — no implementation performed, and progress is 0%.** The
Human Owner bounded this session to three acts: prepare and validate the authorization governance
edits, commit exactly those governance files to `main` as one documentation-only authorization
commit, then stop. Push is withheld. The registered branch `feature/auto-016-milestone-runner` was
**not created**: `STAGE_REGISTRY.md` §3 rule 14 requires the branch to be cut from a `main` baseline
that already carries this authorization record, so the branch waits on the Human Owner's own review
and push of this commit. Registry state therefore stops at `AUTHORIZED`; the
`AUTHORIZED → IN_PROGRESS` initial-start transition (rule 4) does not occur here.

Next, as directed: a separate initial-start session creates the branch from the synchronized
authorized baseline and records `AUTHORIZED → IN_PROGRESS`, stopping before implementation; a
separate implementation session then executes AUTO-016 using the milestone runner. Live acceptance
(contract §27) is authorized only during that later implementation/verification phase.

**Initial start (2026-08-06):** a later session verified the authorization record above had landed
on `main` and been published to `origin/main` (`4cbd714`), confirmed the standard initial-start
preflight (active stage exactly AUTO-016, registry status `AUTHORIZED`, predecessor AUTO-015
`COMPLETE`, clean and synchronized `main` == `origin/main` at
`4cbd714dd6a83de1b390feac39223e0b8f5d4cbf` with zero divergence and no staged or untracked files, no
other AUTO stage `AUTHORIZED` or `IN_PROGRESS`, no pre-existing AUTO-016 branch or `milestone_runner`
source symbol, the finalized Revision 4 contract present and unmodified at its recorded SHA-256,
DEC-016-001 through DEC-016-008 recorded, and `workflowctl check-task-state`/`check-governance`/
`check-handover`/`verify` all full PASS), and created branch `feature/auto-016-milestone-runner`
from `main` at `4cbd714dd6a83de1b390feac39223e0b8f5d4cbf`. Per rule 4 the registry state moved
`AUTHORIZED → IN_PROGRESS`; no new Human Owner authorization act occurred. That session performed
the initial-start transition only — **no implementation was performed**: implementation progress
remains 0%, no production, test, script, package, or dependency file changed, the local prototype
runner is untouched, no provider was invoked, and it held no commit, push, PR, or merge permission,
so none occurred. AUTO-016 remains bounded by the finalized contract and its exact implementation
allowlist. Full record: `docs/workflow-automation/STAGE_REGISTRY.md`, 2026-08-06 "AUTO-016
(initial-start preflight passed)".

## Prior current-task history

GOV-AUTO-10 — AUTO-016 Integrated Runner Contract Definition — was registered as the sole Current
task and closed `Current -> Done` on 2026-08-05, after the Human Owner selected **Integrated
Milestone Automation Runner** as the AUTO-016 capability. It is a documentation-only governance
task: it produced the finalized AUTO-016 stage contract
(`docs/workflow-automation/stage-prompts/AUTO-016.md`, now Revision 4) and its independent review
(`docs/reports/workflow-automation/AUTO-016-contract-review.md`, verdict "CONTRACT READY FOR HUMAN
OWNER AUTHORIZATION"). On the same date the Human Owner ruled the three decisions the closure had
left open — DEC-016-002 (provider adapters owned by the milestone-runner package, under
`milestone_runner/providers/`), DEC-016-005 (external default plan root; repository-local plans only
at exact contract-allowlisted paths; no repository plan discovery), and DEC-016-006 (prototype
unchanged until live acceptance, deprecated afterwards, never automatically deleted). The rulings
are recorded in `docs/DECISION_LOG.md` and propagated into contract Revision 4. No new Current task
was created for them: recording a ruling in the governance documents is not a task transition.
Neither the contract nor the rulings authorized anything; the separate explicit authorization
statement recorded above is what moved AUTO-016 out of that state.

AUTO-015 — Deterministic Next-Stage Proposal and Governed Prompt Generation was closed `Current ->
Done` on 2026-08-05 by explicit Human Owner approval, after implementation on branch
`feature/auto-015-successor-planning` (commit `05b819e`) was published via pull request #17 and
merged into `main` as `e325f95`. The Current set is therefore empty. Under
self-governance.yaml's `maximum_current_tasks: 1`, this is a legal state — the maximum is a
ceiling, not a quota.

Every remaining task is Planned and requires its own fresh written Human Owner authorization.
Closing AUTO-015 authorizes no successor. AUTO-016 remains unauthorized and untouched.
