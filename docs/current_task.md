# Current Task

Mirror of `docs/TASK_QUEUE.md`'s `Current` set. Must contain exactly the same task ID(s) at the
same status as the task queue — `workflowctl check-task-state` fails otherwise.

## AUTO-001 — Architecture and governance contracts

Status: Current

The sole active task, authorized by the Human Owner on 2026-07-23 ("I authorize AUTO-001.").
Branch: `governance/auto-001-workflow-automation-planning`. Documentation-and-architecture-only;
full contract: `docs/workflow-automation/stage-prompts/AUTO-001.md`.

Acceptance criteria (per the stage contract):

1. All required documents under `docs/workflow-automation/` exist and are mutually consistent.
2. Every AUTO-001..AUTO-007 stage prompt exists under `docs/workflow-automation/stage-prompts/`.
3. State names, agent names, skill names, and CLI terminology are consistent across all
   documents.
4. The only human gate documented anywhere is explicit stage authorization
   (`CREATED → AUTHORIZED`); every later transition is machine-gated.
5. Automatic-merge safety rules are consistently documented (squash-only, PR-only, expected-SHA
   verification, no `gh pr merge --admin`, no direct baseline mutation).
6. `main` is documented only as `ai-workflow-engine`'s own baseline, never as a global default —
   the target-repository model requires each target to configure its own baseline branch.
7. Zero runtime implementation was added; zero forbidden-file changes (`src/`, `tests/`,
   `scripts/`, dependencies, `handover/**`, `docs/implementation/orchestration/**` untouched).
8. `git diff --check` passes; a changed-file inventory and validation summary are produced.

Completion (flip to `Done`) requires Human Owner review of the stage report
(`docs/reports/workflow-automation/AUTO-001-completion-report.md`), an explicitly approved
commit, and a merge into `main` — commit and push remain human-gated per
`docs/AGENT_PROTOCOL.md`. DASH-001 (prior `Current` task) was closed out to `Done` as an
AUTO-001 precondition — see `docs/TASK_QUEUE.md` and `docs/DECISION_LOG.md`
(2026-07-23 AUTO-001 entry).
