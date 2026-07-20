# ORCH-024 — Prerequisite lifecycle and attempt supersession

## Objective

Implement only the prerequisite lifecycle and attempt supersession capability described by Architecture v3.

## Reason it must occur at this point

Prerequisites are 020,022,023. Its contracts must be independently accepted before any dependent stage.

## Prerequisites

Every listed stage (020,022,023) must be REVIEW_APPROVED, with committed review evidence. The repository/state preflight in session-protocol.md must pass.

## Exact allowed files or directories

task/dependency orchestration services, mutation builders, decision facts, dry-run adapter, tests/test_prerequisite_lifecycle.py, ORCH records.

## Files expected to be created

prerequisite service/E2E fixtures.

## Files expected to be modified

only new ORCH modules.

## Public interfaces added or changed

proposal/block/unblock/new-attempt compositions.

## Schemas added or changed

PrerequisiteFingerprint/ResumeDecision 1.0.0.

## Migrations required

Only migrations explicitly owned by this stage in migration-registry.yaml may change; otherwise none. Migration apply to the real repository requires a separate authorized migration session.

## Invariants introduced

Tier B; atomic child+parent; limits/dedupe; all success; old attempt superseded; restart plan.

## Tests required

Focused unit, negative and fault/concurrency tests for every invariant, plus affected existing tests and the full regression suite. Tests use isolated temporary repositories/data roots and must not mutate real governance.

## Verification commands

Run independently and record exact argv, output digest and exit status: pytest -q tests/test_prerequisite_lifecycle.py tests/test_governance_transaction.py tests/test_decision_policy.py; pytest -q.

## Acceptance criteria

All specified tests pass; all changed paths are allowed; schemas/interfaces match Architecture v3; evidence and handoff are complete; no unresolved blocker remains; an independent reviewer can reproduce the result.

## Non-goals

No candidate rebase/automatic approval.

## Rollback strategy

Revert composition only.

## Independent review checklist

Dependency direction and every HEAD/attempt boundary. The reviewer must differ from implementation/remediation actors and rerun every verification command from the committed implementation HEAD.

## Risks

Graph growth/livelock.

## Handoff state written for the next session

Add immutable evidence/<stage>/<implementation-id>.yaml and handoffs/<stage>/<implementation-id>.md with exact files, commands/results, decisions, risks, blockers, schema/migration changes and next legal action. Update implementation-state.yaml only through session-protocol transitions. Implementation stops at VERIFIED; review alone records REVIEW_APPROVED or REVIEW_REJECTED. Never start the next stage in the same session.

