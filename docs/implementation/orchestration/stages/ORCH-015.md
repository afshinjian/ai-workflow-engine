# ORCH-015 — Idempotent candidate application

## Objective

Implement only the idempotent candidate application capability described by Architecture v3.

## Reason it must occur at this point

Prerequisites are 014 and 017. Candidate identity and the isolated approval capability must be independently accepted before target application.

## Prerequisites

Every listed stage (014 and 017) must be REVIEW_APPROVED, with committed review evidence. The repository/state preflight in session-protocol.md must pass.

## Exact allowed files or directories

candidates/application.py, writer lock/recovery, cli.py, tests/test_candidate_application.py, ORCH records.

## Files expected to be created

application/journal/receipt/tests.

## Files expected to be modified

candidate CLI/minimal lock.

## Public interfaces added or changed

candidate apply/abort with dry-run.

## Schemas added or changed

ApplicationRecord/ApplyJournal 1.0.0.

## Migrations required

Only migrations explicitly owned by this stage in migration-registry.yaml may change; otherwise none. Migration apply to the real repository requires a separate authorized migration session.

## Invariants introduced

Exact clean base/lock/dry-run/fingerprint; retry never reapplies; ambiguity quarantines.

## Tests required

Focused unit, negative and fault/concurrency tests for every invariant, plus affected existing tests and the full regression suite. Tests use isolated temporary repositories/data roots and must not mutate real governance.

## Verification commands

Run independently and record exact argv, output digest and exit status: pytest -q tests/test_candidate_application.py; pytest -q.

## Acceptance criteria

All specified tests pass; all changed paths are allowed; schemas/interfaces match Architecture v3; evidence and handoff are complete; no unresolved blocker remains; an independent reviewer can reproduce the result.

## Non-goals

No commit/push/governance publication.

## Rollback strategy

Use tested abort only in disposable repos; revert code.

## Independent review checklist

Destructive targets, fsync, locks, retry matrix. The reviewer must differ from implementation/remediation actors and rerun every verification command from the committed implementation HEAD.

## Risks

Filesystem behavior.

## Handoff state written for the next session

Add immutable evidence/<stage>/<implementation-id>.yaml and handoffs/<stage>/<implementation-id>.md with exact files, commands/results, decisions, risks, blockers, schema/migration changes and next legal action. Update implementation-state.yaml only through session-protocol transitions. Implementation stops at VERIFIED; review alone records REVIEW_APPROVED or REVIEW_REJECTED. Never start the next stage in the same session.
