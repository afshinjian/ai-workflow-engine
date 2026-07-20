# ORCH-000 — Independent v3 design review

## Objective

Independently accept or reject the complete v3 design package.

## Reason it must occur at this point

Prerequisites are none. Its contracts must be independently accepted before any dependent stage.

## Prerequisites

Every listed stage (none) must be REVIEW_APPROVED, with committed review evidence. The repository/state preflight in session-protocol.md must pass.

## Exact allowed files or directories

docs/implementation/orchestration/reviews/ORCH-000/, handoffs/ORCH-000/, implementation-state.yaml.

## Files expected to be created

review YAML; optional rejection handoff.

## Files expected to be modified

implementation-state.yaml.

## Public interfaces added or changed

No production interface.

## Schemas added or changed

implementation-state 1.0.0.

## Migrations required

Only migrations explicitly owned by this stage in migration-registry.yaml may change; otherwise none. Migration apply to the real repository requires a separate authorized migration session.

## Invariants introduced

No self-review; all 25 deliverables and every blocker trace to a mechanism/stage.

## Tests required

Focused unit, negative and fault/concurrency tests for every invariant, plus affected existing tests and the full regression suite. Tests use isolated temporary repositories/data roots and must not mutate real governance.

## Verification commands

Run independently and record exact argv, output digest and exit status: state/schema/DAG/link checks and pytest -q.

## Acceptance criteria

All specified tests pass; all changed paths are allowed; schemas/interfaces match Architecture v3; evidence and handoff are complete; no unresolved blocker remains; an independent reviewer can reproduce the result.

## Non-goals

No source, migration, task promotion or runtime change.

## Rollback strategy

Revert review/state; design revisions increment version and repeat 000.

## Independent review checklist

Architecture authority, recovery, signature/commit circularity, stage completeness. The reviewer must differ from implementation/remediation actors and rerun every verification command from the committed implementation HEAD.

## Risks

A hidden lifecycle gap requires rejection.

## Handoff state written for the next session

Add immutable evidence/<stage>/<implementation-id>.yaml and handoffs/<stage>/<implementation-id>.md with exact files, commands/results, decisions, risks, blockers, schema/migration changes and next legal action. Update implementation-state.yaml only through session-protocol transitions. Implementation stops at VERIFIED; review alone records REVIEW_APPROVED or REVIEW_REJECTED. Never start the next stage in the same session.

