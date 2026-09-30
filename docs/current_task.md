# Current Task

Mirror of docs/TASK_QUEUE.md's Current set. Must contain exactly the same task ID(s) at
the same status as the task queue — `workflowctl check-task-state` fails otherwise.

## AUTO-018 — Durable Lifecycle / Event Foundation

Status: Current

The OWNER recorded `AUTO_018_IMPLEMENTATION_AUTHORIZED` on 2026-09-30. Registry state is
`AUTHORIZED`; implementation has NOT begun, and no implementation candidate exists. AUTO-018 is the
sole Current task under `self-governance.yaml`'s `maximum_current_tasks: 1`.

Authorization binds exactly the CLOSED / FROZEN contract
`docs/workflow-automation/stage-prompts/AUTO-018.md` — 1008 lines, 76360 bytes, SHA-256
`75033788e08a6c3e6b9f7f79a48d1b33043018ed646857f059bf9916b3593751` — and the frozen Master Plan
`docs/workflow-automation/successor-planning/AWE-GOVERNED-AUTONOMOUS-STAGE-EXECUTION-MASTER-PLAN.md`
(1698 lines, 113150 bytes, SHA-256
`8ab499c0240cc542e735eb5d1953dcd93994ebd87f1ef7413e9346805d613077`). Implementation is limited to
the exact production/test path set and scope in contract §11 and the one completion report §1 names.

Registered implementation branch: `feature/auto-018-durable-lifecycle-events`. It is registered
only, not created.

This is an authorization-recording and Stage-Start-input preparation step only. The external
schema-v2 runner configuration and StageExecutionOverrides are prepared outside the repository and
validated, and the resolved `EffectiveStageExecutionPolicy` digest is
`afb747606f97409b9d04dcbd3f9b4ba47fe162251c7a53b8d1fc40842fb191a1`. No native
`StageStartAuthorization` was created, `workflowctl milestone-runner stage-start` was not run, and
initial-start preflight has not run. No production code or tests changed. Git mutation authority
remains ungranted, including staging, commit, push, tag, merge and reset/rebase/checkout/switch. The
frozen artifacts remain byte-unchanged. AUTO-019 … AUTO-026 remain `Planned` and unauthorized;
contract amendment and scope expansion are not authorized.
