# ORCH-002 — Schema registry and CLI v2 envelope

## Objective

Implement only the schema registry and cli v2 envelope capability described by Architecture v3.

## Reason it must occur at this point

Prerequisites are 001. Its contracts must be independently accepted before any dependent stage.

## Prerequisites

Every listed stage (001) must be REVIEW_APPROVED, with committed review evidence. The repository/state preflight in session-protocol.md must pass.

## Exact allowed files or directories

src/ai_workflow_engine/schema/, reporting/, cli.py, exceptions.py, tests/test_schema_registry.py, tests/test_cli_contract_v2.py, ORCH records.

## Files expected to be created

schema/contract modules and tests.

## Files expected to be modified

CLI/reporting/exceptions.

## Public interfaces added or changed

global contract-version; stable v2 envelope/errors.

## Schemas added or changed

CLI contract 2.0.0.

## Migrations required

Only migrations explicitly owned by this stage in migration-registry.yaml may change; otherwise none. Migration apply to the real repository requires a separate authorized migration session.

## Invariants introduced

Exactly one JSON stdout; stable errors; unknown schema fails; explicit v1 remains.

## Tests required

Focused unit, negative and fault/concurrency tests for every invariant, plus affected existing tests and the full regression suite. Tests use isolated temporary repositories/data roots and must not mutate real governance.

## Verification commands

Run independently and record exact argv, output digest and exit status: pytest -q tests/test_schema_registry.py tests/test_cli_contract_v2.py tests/test_cli.py; pytest -q.

## Acceptance criteria

All specified tests pass; all changed paths are allowed; schemas/interfaces match Architecture v3; evidence and handoff are complete; no unresolved blocker remains; an independent reviewer can reproduce the result.

## Non-goals

No domain orchestration commands.

## Rollback strategy

Remove additions and localized CLI changes.

## Independent review checklist

Golden compatibility and stdout purity. The reviewer must differ from implementation/remediation actors and rerun every verification command from the committed implementation HEAD.

## Risks

CLI consumers may break.

## Handoff state written for the next session

Add immutable evidence/<stage>/<implementation-id>.yaml and handoffs/<stage>/<implementation-id>.md with exact files, commands/results, decisions, risks, blockers, schema/migration changes and next legal action. Update implementation-state.yaml only through session-protocol transitions. Implementation stops at VERIFIED; review alone records REVIEW_APPROVED or REVIEW_REJECTED. Never start the next stage in the same session.

