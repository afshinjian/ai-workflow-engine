# ORCH-023 — Separate orchestrator dry run

## Objective

Implement only the separate orchestrator dry run capability described by Architecture v3.

## Reason it must occur at this point

Prerequisites are 022. Its contracts must be independently accepted before any dependent stage.

## Prerequisites

Every listed stage (022) must be REVIEW_APPROVED, with committed review evidence. The repository/state preflight in session-protocol.md must pass.

## Exact allowed files or directories

src/ai_workflow_orchestrator/, packaging, tests/test_orchestrator_dry_run.py, ORCH records.

## Files expected to be created

client/cursor/loop/CLI/tests.

## Files expected to be modified

entry points.

## Public interfaces added or changed

orchestratorctl inspect/step --dry-run.

## Schemas added or changed

OrchestratorCursor 1.0.0 derived only.

## Migrations required

Only migrations explicitly owned by this stage in migration-registry.yaml may change; otherwise none. Migration apply to the real repository requires a separate authorized migration session.

## Invariants introduced

No engine import/store/Git; pinned contract; cursor derived; bounded subprocess.

## Tests required

Focused unit, negative and fault/concurrency tests for every invariant, plus affected existing tests and the full regression suite. Tests use isolated temporary repositories/data roots and must not mutate real governance.

## Verification commands

Run independently and record exact argv, output digest and exit status: pytest -q tests/test_orchestrator_dry_run.py; pytest -q.

## Acceptance criteria

All specified tests pass; all changed paths are allowed; schemas/interfaces match Architecture v3; evidence and handoff are complete; no unresolved blocker remains; an independent reviewer can reproduce the result.

## Non-goals

No mutation or agent launch.

## Rollback strategy

Remove orchestrator package/entry.

## Independent review checklist

Import boundary and injection. The reviewer must differ from implementation/remediation actors and rerun every verification command from the committed implementation HEAD.

## Risks

Accidental internal dependency.

## Handoff state written for the next session

Add immutable evidence/<stage>/<implementation-id>.yaml and handoffs/<stage>/<implementation-id>.md with exact files, commands/results, decisions, risks, blockers, schema/migration changes and next legal action. Update implementation-state.yaml only through session-protocol transitions. Implementation stops at VERIFIED; review alone records REVIEW_APPROVED or REVIEW_REJECTED. Never start the next stage in the same session.

