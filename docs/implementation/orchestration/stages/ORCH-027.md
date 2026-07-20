# ORCH-027 — End-to-end safety and release closeout

## Objective

Prove the integrated feature and decide whether it may be released.

## Reason it must occur at this point

Prerequisites are all ORCH-000 through ORCH-026. Every component and security boundary must be independently accepted before release closeout.

## Prerequisites

Every stage ORCH-000 through ORCH-026 must be REVIEW_APPROVED, with committed review evidence. The repository/state preflight in session-protocol.md must pass.

## Exact allowed files or directories

tests/e2e/orchestration/, harness/fixtures, operational docs, release review/evidence/state.

## Files expected to be created

E2E/fault suites/threat model/runbook/report.

## Files expected to be modified

test configuration/docs only; defects reopen owner stage.

## Public interfaces added or changed

release preflight/report only.

## Schemas added or changed

no new schema.

## Migrations required

Only migrations explicitly owned by this stage in migration-registry.yaml may change; otherwise none. Migration apply to the real repository requires a separate authorized migration session.

## Invariants introduced

Every architecture invariant/fail stop; human gates and independent release review.

## Tests required

Focused unit, negative and fault/concurrency tests for every invariant, plus affected existing tests and the full regression suite. Tests use isolated temporary repositories/data roots and must not mutate real governance.

## Verification commands

Run independently and record exact argv, output digest and exit status: pytest -q; governance validators; packaged CLI smoke; isolated canary.

## Acceptance criteria

All specified tests pass; all changed paths are allowed; schemas/interfaces match Architecture v3; evidence and handoff are complete; no unresolved blocker remains; an independent reviewer can reproduce the result.

## Non-goals

No production push or gate removal.

## Rollback strategy

Keep write mode disabled; reopen defective owner stage.

## Independent review checklist

Threat model, recovery, fresh-session reproducibility. The reviewer must differ from implementation/remediation actors and rerun every verification command from the committed implementation HEAD.

## Risks

Test host differs from production.

## Handoff state written for the next session

Add immutable evidence/<stage>/<implementation-id>.yaml and handoffs/<stage>/<implementation-id>.md with exact files, commands/results, decisions, risks, blockers, schema/migration changes and next legal action. Update implementation-state.yaml only through session-protocol transitions. Implementation stops at VERIFIED; review alone records REVIEW_APPROVED or REVIEW_REJECTED. Never start the next stage in the same session.
