# ORCH-009 — Safe baseline cache

## Objective

Implement only the safe baseline cache capability described by Architecture v3.

## Reason it must occur at this point

Prerequisites are 008. Its contracts must be independently accepted before any dependent stage.

## Prerequisites

Every listed stage (008) must be REVIEW_APPROVED, with committed review evidence. The repository/state preflight in session-protocol.md must pass.

## Exact allowed files or directories

verification/cache.py, related verification/config, tests/test_baseline_cache.py, ORCH records.

## Files expected to be created

cache module/tests.

## Files expected to be modified

profile/config integration.

## Public interfaces added or changed

baseline run/show and bypass reasons.

## Schemas added or changed

BaselineCacheRecord 1.0.0.

## Migrations required

Only migrations explicitly owned by this stage in migration-registry.yaml may change; otherwise none. Migration apply to the real repository requires a separate authorized migration session.

## Invariants introduced

Unknown identity disables cache; cache never authorizes.

## Tests required

Focused unit, negative and fault/concurrency tests for every invariant, plus affected existing tests and the full regression suite. Tests use isolated temporary repositories/data roots and must not mutate real governance.

## Verification commands

Run independently and record exact argv, output digest and exit status: pytest -q tests/test_baseline_cache.py tests/test_verification*.py; pytest -q.

## Acceptance criteria

All specified tests pass; all changed paths are allowed; schemas/interfaces match Architecture v3; evidence and handoff are complete; no unresolved blocker remains; an independent reviewer can reproduce the result.

## Non-goals

No distributed cache/performance guarantee.

## Rollback strategy

Disable/remove cache without semantic change.

## Independent review checklist

Look for omitted key input. The reviewer must differ from implementation/remediation actors and rerun every verification command from the committed implementation HEAD.

## Risks

False hit.

## Handoff state written for the next session

Add immutable evidence/<stage>/<implementation-id>.yaml and handoffs/<stage>/<implementation-id>.md with exact files, commands/results, decisions, risks, blockers, schema/migration changes and next legal action. Update implementation-state.yaml only through session-protocol transitions. Implementation stops at VERIFIED; review alone records REVIEW_APPROVED or REVIEW_REJECTED. Never start the next stage in the same session.

