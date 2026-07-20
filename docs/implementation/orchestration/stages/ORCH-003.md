# ORCH-003 — Legacy readers and migration framework

## Objective

Implement only the legacy readers and migration framework capability described by Architecture v3.

## Reason it must occur at this point

Prerequisites are 002. Its contracts must be independently accepted before any dependent stage.

## Prerequisites

Every listed stage (002) must be REVIEW_APPROVED, with committed review evidence. The repository/state preflight in session-protocol.md must pass.

## Exact allowed files or directories

src/ai_workflow_engine/migration/, schema adapters, cli.py, tests/test_migration*.py, ORCH migration/records.

## Files expected to be created

readers/framework/fixtures/tests.

## Files expected to be modified

CLI/schema registry/migration registry.

## Public interfaces added or changed

migrate inspect/plan/apply dry-run; apply disabled.

## Schemas added or changed

migration manifest/backup/recovery-plan 1.0.0.

## Migrations required

Only migrations explicitly owned by this stage in migration-registry.yaml may change; otherwise none. Migration apply to the real repository requires a separate authorized migration session.

## Invariants introduced

Legacy bytes/digests preserved; inspect/dry-run writes nothing; unknown quarantines.

## Tests required

Focused unit, negative and fault/concurrency tests for every invariant, plus affected existing tests and the full regression suite. Tests use isolated temporary repositories/data roots and must not mutate real governance.

## Verification commands

Run independently and record exact argv, output digest and exit status: pytest -q tests/test_migration*.py; pytest -q.

## Acceptance criteria

All specified tests pass; all changed paths are allowed; schemas/interfaces match Architecture v3; evidence and handoff are complete; no unresolved blocker remains; an independent reviewer can reproduce the result.

## Non-goals

No live migration or v2 writer.

## Rollback strategy

Remove additive framework/registration.

## Independent review checklist

External paths, backup integrity, no guessed legacy semantics. The reviewer must differ from implementation/remediation actors and rerun every verification command from the committed implementation HEAD.

## Risks

Unknown legacy variants.

## Handoff state written for the next session

Add immutable evidence/<stage>/<implementation-id>.yaml and handoffs/<stage>/<implementation-id>.md with exact files, commands/results, decisions, risks, blockers, schema/migration changes and next legal action. Update implementation-state.yaml only through session-protocol transitions. Implementation stops at VERIFIED; review alone records REVIEW_APPROVED or REVIEW_REJECTED. Never start the next stage in the same session.

