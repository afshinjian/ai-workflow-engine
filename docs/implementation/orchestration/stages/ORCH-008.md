# ORCH-008 — Verification profiles and finding delta

## Objective

Implement only the verification profiles and finding delta capability described by Architecture v3.

## Reason it must occur at this point

Prerequisites are 007. Its contracts must be independently accepted before any dependent stage.

## Prerequisites

Every listed stage (007) must be REVIEW_APPROVED, with committed review evidence. The repository/state preflight in session-protocol.md must pass.

## Exact allowed files or directories

src/ai_workflow_engine/verification/, agent verification adapter, tests/test_verification*.py, ORCH records.

## Files expected to be created

profile/finding/evidence/delta modules/tests.

## Files expected to be modified

agent verification adapter.

## Public interfaces added or changed

profile runner and v2 evidence shapes.

## Schemas added or changed

VerificationProfile/FindingSet/AttributionRecord 1.0.0.

## Migrations required

Only migrations explicitly owned by this stage in migration-registry.yaml may change; otherwise none. Migration apply to the real repository requires a separate authorized migration session.

## Invariants introduced

Stable finding IDs; Tier B for automatic prerequisite; ambiguity remains blocked.

## Tests required

Focused unit, negative and fault/concurrency tests for every invariant, plus affected existing tests and the full regression suite. Tests use isolated temporary repositories/data roots and must not mutate real governance.

## Verification commands

Run independently and record exact argv, output digest and exit status: pytest -q tests/test_verification*.py tests/test_agent_verification.py; pytest -q.

## Acceptance criteria

All specified tests pass; all changed paths are allowed; schemas/interfaces match Architecture v3; evidence and handoff are complete; no unresolved blocker remains; an independent reviewer can reproduce the result.

## Non-goals

No cache/prerequisite creation.

## Rollback strategy

Remove verification package/adapter.

## Independent review checklist

False attribution and parser version binding. The reviewer must differ from implementation/remediation actors and rerun every verification command from the committed implementation HEAD.

## Risks

Tool output drift.

## Handoff state written for the next session

Add immutable evidence/<stage>/<implementation-id>.yaml and handoffs/<stage>/<implementation-id>.md with exact files, commands/results, decisions, risks, blockers, schema/migration changes and next legal action. Update implementation-state.yaml only through session-protocol transitions. Implementation stops at VERIFIED; review alone records REVIEW_APPROVED or REVIEW_REJECTED. Never start the next stage in the same session.

