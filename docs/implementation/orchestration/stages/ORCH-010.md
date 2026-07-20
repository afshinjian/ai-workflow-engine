# ORCH-010 — Candidate record and chain derivation

## Objective

Implement only the candidate record and chain derivation capability described by Architecture v3.

## Reason it must occur at this point

Prerequisites are 006,007. Its contracts must be independently accepted before any dependent stage.

## Prerequisites

Every listed stage (006,007) must be REVIEW_APPROVED, with committed review evidence. The repository/state preflight in session-protocol.md must pass.

## Exact allowed files or directories

src/ai_workflow_engine/candidates/models.py, chain.py, store.py, workflow adapters, tests/test_candidate_chain.py, ORCH records.

## Files expected to be created

candidate package/models/tests.

## Files expected to be modified

workflow read adapters.

## Public interfaces added or changed

read-only candidate show/verify; no order input.

## Schemas added or changed

CandidateRecord/ChainMember 1.0.0.

## Migrations required

Only migrations explicitly owned by this stage in migration-registry.yaml may change; otherwise none. Migration apply to the real repository requires a separate authorized migration session.

## Invariants introduced

Order only from accepted events; continuity and same epoch; no gaps/branches.

## Tests required

Focused unit, negative and fault/concurrency tests for every invariant, plus affected existing tests and the full regression suite. Tests use isolated temporary repositories/data roots and must not mutate real governance.

## Verification commands

Run independently and record exact argv, output digest and exit status: pytest -q tests/test_candidate_chain.py tests/test_workflow*.py; pytest -q.

## Acceptance criteria

All specified tests pass; all changed paths are allowed; schemas/interfaces match Architecture v3; evidence and handoff are complete; no unresolved blocker remains; an independent reviewer can reproduce the result.

## Non-goals

No Git reconstruction/application.

## Rollback strategy

Remove candidate package/read commands.

## Independent review checklist

Prove caller cannot influence membership/order. The reviewer must differ from implementation/remediation actors and rerun every verification command from the committed implementation HEAD.

## Risks

Ambiguous accepted round.

## Handoff state written for the next session

Add immutable evidence/<stage>/<implementation-id>.yaml and handoffs/<stage>/<implementation-id>.md with exact files, commands/results, decisions, risks, blockers, schema/migration changes and next legal action. Update implementation-state.yaml only through session-protocol transitions. Implementation stops at VERIFIED; review alone records REVIEW_APPROVED or REVIEW_REJECTED. Never start the next stage in the same session.

