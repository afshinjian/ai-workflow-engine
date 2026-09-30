# Current Task

Mirror of docs/TASK_QUEUE.md's Current set. Must contain exactly the same task ID(s) at
the same status as the task queue — `workflowctl check-task-state` fails otherwise.

## AUTO-017 — Schema v2 + Stage Execution Policy

Status: Current

The OWNER accepted the current unstaged, uncommitted implementation candidate on 2026-09-30
(`AUTO_017_IMPLEMENTATION_OWNER_ACCEPTED`). The one independent implementation discovery review's
frozen findings AUTO017-IMPL-R01..R06 are all CLOSED (`AUTO_017_IMPLEMENTATION_CLOSURE_PASS`), and
G-1 is `AUTO_017_G1_PASS_PATH_B` under `D-AUTO017-02 = B`. Commit authority remains separate and
ungranted: no `git add`, commit, push, tag or merge is authorized. AUTO-017 is not complete until
the accepted candidate is committed and committed-state verification passes. AUTO-018 remains
unauthorized. Full record: `docs/DECISION_LOG.md`, 2026-09-30.

Earlier (2026-09-29), the OWNER accepted and froze the reviewed AUTO017-IMPL-R02 contract amendment
under `D-AUTO017-03 = A` (`AUTO_017_R02_CONTRACT_AMENDMENT_OWNER_ACCEPTED`; independent
`AUTO_017_R02_CONTRACT_AMENDMENT_REVIEW_PASS`, no amendment findings). The authoritative CLOSED / FROZEN
contract and Master Plan identities are recorded in `docs/TASK_QUEUE.md` and `docs/DECISION_LOG.md`.

The OWNER recorded `AUTO_017_IMPLEMENTATION_AUTHORIZED` on 2026-09-29. Registry state is `AUTHORIZED`;
AUTO-017 is the sole Current task under `self-governance.yaml`'s `maximum_current_tasks: 1`.

The current authoritative CLOSED / FROZEN contract and Master Plan identities are recorded in
`docs/TASK_QUEUE.md`'s AUTO-017 entry and `docs/DECISION_LOG.md`'s AUTO017-IMPL-R02 amendment acceptance entry.
Implementation remains limited to the contract's exact production/test path set (§§5–6).

At the earlier authorization-recording step, the named branch was registered but not created and
initial-start preflight had not run. That governance step changed no production code or tests. It
granted no Git mutation authority, including staging, commit, push, tag, merge and
reset/rebase/checkout/switch. AUTO-018 … AUTO-026 remain `Planned` and unauthorized;
scope expansion is not authorized.
