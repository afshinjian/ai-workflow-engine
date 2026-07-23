# Current Task

Mirror of `docs/TASK_QUEUE.md`'s `Current` set. Must contain exactly the same task ID(s) at the
same status as the task queue — `workflowctl check-task-state` fails otherwise.

## DASH-001 — Dashboard planning foundation and contracts

Status: Current

The sole active task, authorized by the Human Owner on 2026-07-23 and recovered/re-executed
correctly for this repository the same day after a mis-targeted first execution (authorization
log: `docs/agentos-dashboard/STAGE_REGISTRY.md` §4; adaptation decision:
`docs/agentos-dashboard/DECISIONS.md` DD-03). Branch: `governance/dash-001-documentation`.
Documentation-only; full contract: `docs/agentos-dashboard/stage-prompts/DASH-001.md`.

Acceptance criteria (per the stage contract):

1. All planning files under `docs/agentos-dashboard/` exist and are mutually consistent.
2. The DASH family is enrolled with exactly one `Current` task and agreeing mirrors
   (`workflowctl check-task-state` PASS).
3. No repository-root governance file is created or altered beyond the stage's allowed list.
4. The enrollment decision is recorded in `docs/DECISION_LOG.md`.
5. Handover checksum verification still PASSes without touching `handover/**`.
6. Zero forbidden-file changes (`src/`, `tests/`, `scripts/`, dependencies,
   `docs/implementation/orchestration/**` untouched).
7. Engine test collection unchanged.

Completion (flip to `Done`) requires Human Owner review of the stage report
(`docs/reports/agentos-dashboard/STAGE-01-completion.md`), an explicitly approved commit, and a
merge into `main` — commit and push remain human-gated per `docs/AGENT_PROTOCOL.md`.
