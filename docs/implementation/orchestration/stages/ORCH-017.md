# ORCH-017 — Isolated approval service

## Objective

Implement only the isolated approval service capability described by Architecture v3.

## Reason it must occur at this point

Prerequisites are 016. Its contracts must be independently accepted before any dependent stage.

## Prerequisites

Every listed stage (016) must be REVIEW_APPROVED, with committed review evidence. The repository/state preflight in session-protocol.md must pass.

## Exact allowed files or directories

src/ai_workflow_approvald/, service config/packaging, approval/client.py, tests/test_approvald*.py, security docs, ORCH records.

## Files expected to be created

service/client/DB migration/tests.

## Files expected to be modified

entry points and approval CLI.

## Public interfaces added or changed

approvald socket consume/health/preflight.

## Schemas added or changed

ReplayLedger/Attestation/TrustStore 1.0.0.

## Migrations required

Only migrations explicitly owned by this stage in migration-registry.yaml may change; otherwise none. Migration apply to the real repository requires a separate authorized migration session.

## Invariants introduced

Distinct account; atomic consume; peer auth; rotation/revocation; DB failure closes.

## Tests required

Focused unit, negative and fault/concurrency tests for every invariant, plus affected existing tests and the full regression suite. Tests use isolated temporary repositories/data roots and must not mutate real governance.

## Verification commands

Run independently and record exact argv, output digest and exit status: pytest -q tests/test_approvald*.py tests/test_approval_v2.py; pytest -q.

## Acceptance criteria

All specified tests pass; all changed paths are allowed; schemas/interfaces match Architecture v3; evidence and handoff are complete; no unresolved blocker remains; an independent reviewer can reproduce the result.

## Non-goals

No remote service/HSM/trusted-local autonomy.

## Rollback strategy

Stop service; preserve audit DB; revert client.

## Independent review checklist

Independent threat/permission/SQL review. The reviewer must differ from implementation/remediation actors and rerun every verification command from the committed implementation HEAD.

## Risks

CI cannot prove deployment isolation.

## Handoff state written for the next session

Add immutable evidence/<stage>/<implementation-id>.yaml and handoffs/<stage>/<implementation-id>.md with exact files, commands/results, decisions, risks, blockers, schema/migration changes and next legal action. Update implementation-state.yaml only through session-protocol transitions. Implementation stops at VERIFIED; review alone records REVIEW_APPROVED or REVIEW_REJECTED. Never start the next stage in the same session.

