# Current Task

Mirror of `docs/TASK_QUEUE.md`'s `Current` set. Must contain exactly the same task ID(s) at the
same status as the task queue — `workflowctl check-task-state` fails otherwise.

## AUTO-002 — Orchestrator, state machine, locking, and persistence

Status: Current

The sole active task, authorized by the Human Owner on 2026-07-24 ("I authorize AUTO-002.").
Engine implementation session; full contract:
`docs/workflow-automation/stage-prompts/AUTO-002.md`. Canonical branch per
`docs/workflow-automation/STAGE_REGISTRY.md` §4: `feature/auto-002-orchestrator-state-machine`.

**Blocked on a durable execution precondition, discovered 2026-07-24**: AUTO-002 stays `BLOCKED`
until this governance recovery is merged into `main`. The recovery release procedure is settled:
this session's working branch is reviewed, committed, pushed, merged, and deleted through the
ordinary recovery release process — it is not renamed into the AUTO-002 implementation branch.
After that merge and cleanup, an AUTO-002 session begins from updated, clean `main` and creates
or checks out the canonical branch above, which must independently pass the SSP's initial-start
branch-binding and clean-tree checks (`docs/workflow-automation/stage-prompts/README.md`;
`STAGE_REGISTRY.md` §3 rules 1/14/4) before the registry transitions to `IN_PROGRESS`. This is
not a fact tied to this session's own (temporary, non-canonical) working branch — it holds
regardless of that branch's name, and regardless of whether that branch still exists. Per
`STAGE_REGISTRY.md` §3 rule 17, a failed execution precondition never invalidates the Human
Owner's "I authorize AUTO-002." authorization, which stands unaffected — it moves the stage to
registry state `BLOCKED` (§2; still `Current` here) until resolved. This is not a new AUTO-002
authorization, and no AUTO-002 runtime implementation begins during governance recovery — see
`docs/DECISION_LOG.md`, 2026-07-24 entries (the original discovery, unchanged, plus this
recovery's durability correction).

AUTO-001 (prior `Current` task) was merged into `main` via PR #3 (`191f600`) and formally closed
out to `Done` 2026-07-24 as part of the same governance session — see `docs/TASK_QUEUE.md` and
`docs/DECISION_LOG.md` (2026-07-24 entry).
