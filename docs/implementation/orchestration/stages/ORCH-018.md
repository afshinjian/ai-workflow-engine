# ORCH-018 — Task v2 and dependency validation

## Objective

Implement only the task v2 and dependency validation capability described by Architecture v3.

## Reason it must occur at this point

Prerequisites are 003,004,005. Its contracts must be independently accepted before any dependent stage.

## Prerequisites

Every listed stage (003,004,005) must be REVIEW_APPROVED, with committed review evidence. The repository/state preflight in session-protocol.md must pass.

## Exact allowed files or directories

src/ai_workflow_engine/governance/, tests/test_task_v2.py, fixtures, ORCH migration/records.

## Files expected to be created

task model/renderer/dependency tests.

## Files expected to be modified

governance parser/models/validators.

## Public interfaces added or changed

read-only v2 parse/render/task show.

## Schemas added or changed

TaskRecord 2.0.0.

## Migrations required

Only migrations explicitly owned by this stage in migration-registry.yaml may change; otherwise none. Migration apply to the real repository requires a separate authorized migration session.

## Invariants introduced

Parent direction; unique existing children; no cycles/self; limits; mirrors/spec consistent.

## Tests required

Focused unit, negative and fault/concurrency tests for every invariant, plus affected existing tests and the full regression suite. Tests use isolated temporary repositories/data roots and must not mutate real governance.

## Verification commands

Run independently and record exact argv, output digest and exit status: pytest -q tests/test_task_v2.py tests/test_governance.py; pytest -q.

## Acceptance criteria

All specified tests pass; all changed paths are allowed; schemas/interfaces match Architecture v3; evidence and handoff are complete; no unresolved blocker remains; an independent reviewer can reproduce the result.

## Non-goals

No real TASK_QUEUE write.

## Rollback strategy

Revert parser extensions.

## Independent review checklist

Lossless Markdown and single authority. The reviewer must differ from implementation/remediation actors and rerun every verification command from the committed implementation HEAD.

## Risks

Legacy prose ambiguity.

## Handoff state written for the next session

Add immutable evidence/<stage>/<implementation-id>.yaml and handoffs/<stage>/<implementation-id>.md with exact files, commands/results, decisions, risks, blockers, schema/migration changes and next legal action. Update implementation-state.yaml only through session-protocol transitions. Implementation stops at VERIFIED; review alone records REVIEW_APPROVED or REVIEW_REJECTED. Never start the next stage in the same session.

