# Current Task

Mirror of docs/TASK_QUEUE.md's Current set. Must contain exactly the same task ID(s) at
the same status as the task queue — `workflowctl check-task-state` fails otherwise.

## AUTO-017 — Schema v2 + Stage Execution Policy

Status: Current

The OWNER recorded `AUTO_017_IMPLEMENTATION_AUTHORIZED` on 2026-09-29. Registry state is `AUTHORIZED`;
implementation has NOT begun, and no implementation candidate exists. AUTO-017 is the sole Current task
under `self-governance.yaml`'s `maximum_current_tasks: 1`.

Authorization binds exactly the CLOSED / FROZEN contract and Master Plan identities recorded in
`docs/TASK_QUEUE.md`'s AUTO-017 entry and `docs/DECISION_LOG.md`'s 2026-09-29 implementation-authorization
entry. Implementation is limited to the contract's exact production/test path set (§§5–6).

This is an authorization-recording step only. The named branch is registered, not created; initial-start
preflight has not run. No production code or tests changed. Git mutation authority remains ungranted,
including staging, commit, push, tag, merge and reset/rebase/checkout/switch. The frozen artifacts remain
unchanged. AUTO-018 … AUTO-026 remain `Planned` and unauthorized; scope expansion is not authorized.
