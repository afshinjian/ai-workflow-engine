# ORCH-026 — Migration and backward compatibility

## Objective

Implement only the migration and backward compatibility capability described by Architecture v3.

## Reason it must occur at this point

Prerequisites are 003,020,025. Its contracts must be independently accepted before any dependent stage.

## Prerequisites

Every listed stage (003,020,025) must be REVIEW_APPROVED, with committed review evidence. The repository/state preflight in session-protocol.md must pass.

## Exact allowed files or directories

src/ai_workflow_engine/migration/, adapters/cli, fixtures/docs, tests/test_orchestration_migrations.py, ORCH migration/records.

## Files expected to be created

migration implementations/goldens.

## Files expected to be modified

migration framework/registry/schema dispatch.

## Public interfaces added or changed

enable migrate apply with digest/approval/backup.

## Schemas added or changed

MigrationPlan/Receipt 1.0.0; mixed marker.

## Migrations required

Only migrations explicitly owned by this stage in migration-registry.yaml may change; otherwise none. Migration apply to the real repository requires a separate authorized migration session.

## Invariants introduced

Dry-run exact; backup/no delete; new attempt; legacy approval powerless; cutoff/mixed guard.

## Tests required

Focused unit, negative and fault/concurrency tests for every invariant, plus affected existing tests and the full regression suite. Tests use isolated temporary repositories/data roots and must not mutate real governance.

## Verification commands

Run independently and record exact argv, output digest and exit status: pytest -q tests/test_orchestration_migrations.py tests/test_migration*.py; pytest -q.

## Acceptance criteria

All specified tests pass; all changed paths are allowed; schemas/interfaces match Architecture v3; evidence and handoff are complete; no unresolved blocker remains; an independent reviewer can reproduce the result.

## Non-goals

No real-repo migration in implementation.

## Rollback strategy

Rollback before cutoff; forward repair after.

## Independent review checklist

Byte-level data-loss and unknown variants. The reviewer must differ from implementation/remediation actors and rerun every verification command from the committed implementation HEAD.

## Risks

Unseen legacy data.

## Handoff state written for the next session

Add immutable evidence/<stage>/<implementation-id>.yaml and handoffs/<stage>/<implementation-id>.md with exact files, commands/results, decisions, risks, blockers, schema/migration changes and next legal action. Update implementation-state.yaml only through session-protocol transitions. Implementation stops at VERIFIED; review alone records REVIEW_APPROVED or REVIEW_REJECTED. Never start the next stage in the same session.

