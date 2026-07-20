# ORCH-004 — Immutable execution specification

## Objective

Implement only the immutable execution specification capability described by Architecture v3.

## Reason it must occur at this point

Prerequisites are 003. Its contracts must be independently accepted before any dependent stage.

## Prerequisites

Every listed stage (003) must be REVIEW_APPROVED, with committed review evidence. The repository/state preflight in session-protocol.md must pass.

## Exact allowed files or directories

src/ai_workflow_engine/execution/, config.py, tests/test_execution_spec.py, ORCH records.

## Files expected to be created

spec models/validator/router/tests.

## Files expected to be modified

config explicit policy/defaults.

## Public interfaces added or changed

validate/digest/route library.

## Schemas added or changed

ExecutionSpec 1.0.0; gated config 2.0.

## Migrations required

Only migrations explicitly owned by this stage in migration-registry.yaml may change; otherwise none. Migration apply to the real repository requires a separate authorized migration session.

## Invariants introduced

Defaults materialized before digest; paths confined; fallback signed and ordered.

## Tests required

Focused unit, negative and fault/concurrency tests for every invariant, plus affected existing tests and the full regression suite. Tests use isolated temporary repositories/data roots and must not mutate real governance.

## Verification commands

Run independently and record exact argv, output digest and exit status: pytest -q tests/test_execution_spec.py tests/test_config.py; pytest -q.

## Acceptance criteria

All specified tests pass; all changed paths are allowed; schemas/interfaces match Architecture v3; evidence and handoff are complete; no unresolved blocker remains; an independent reviewer can reproduce the result.

## Non-goals

No promotion or agent execution.

## Rollback strategy

Remove additive execution package/config.

## Independent review checklist

Cross-platform path and canonical identity audit. The reviewer must differ from implementation/remediation actors and rerun every verification command from the committed implementation HEAD.

## Risks

Filesystem variance.

## Handoff state written for the next session

Add immutable evidence/<stage>/<implementation-id>.yaml and handoffs/<stage>/<implementation-id>.md with exact files, commands/results, decisions, risks, blockers, schema/migration changes and next legal action. Update implementation-state.yaml only through session-protocol transitions. Implementation stops at VERIFIED; review alone records REVIEW_APPROVED or REVIEW_REJECTED. Never start the next stage in the same session.

