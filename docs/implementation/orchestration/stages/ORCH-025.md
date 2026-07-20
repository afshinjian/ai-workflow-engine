# ORCH-025 — Write-capable orchestration and rollout

## Objective

Implement only the write-capable orchestration and rollout capability described by Architecture v3.

## Reason it must occur at this point

Prerequisites are 017,021,024. Its contracts must be independently accepted before any dependent stage.

## Prerequisites

Every listed stage (017,021,024) must be REVIEW_APPROVED, with committed review evidence. The repository/state preflight in session-protocol.md must pass.

## Exact allowed files or directories

src/ai_workflow_orchestrator/, config/entry points, tests/test_orchestrator_write_mode.py, operational docs, ORCH records.

## Files expected to be created

write executor/preflight/canary tests.

## Files expected to be modified

dry-run orchestrator.

## Public interfaces added or changed

orchestratorctl enable/run/resume/disable.

## Schemas added or changed

OrchestratorConfig/ActionReceiptCursor 1.0.0.

## Migrations required

Only migrations explicitly owned by this stage in migration-registry.yaml may change; otherwise none. Migration apply to the real repository requires a separate authorized migration session.

## Invariants introduced

Crypto approvald; exact decision/action/receipt; no direct Git; limits and safe resume.

## Tests required

Focused unit, negative and fault/concurrency tests for every invariant, plus affected existing tests and the full regression suite. Tests use isolated temporary repositories/data roots and must not mutate real governance.

## Verification commands

Run independently and record exact argv, output digest and exit status: pytest -q tests/test_orchestrator_write_mode.py tests/test_orchestrator_dry_run.py; pytest -q.

## Acceptance criteria

All specified tests pass; all changed paths are allowed; schemas/interfaces match Architecture v3; evidence and handoff are complete; no unresolved blocker remains; an independent reviewer can reproduce the result.

## Non-goals

No unattended approval/multi-host.

## Rollback strategy

Disable write mode before reverting.

## Independent review checklist

Red-team TOCTOU/allowlist/privileges/stop. The reviewer must differ from implementation/remediation actors and rerun every verification command from the committed implementation HEAD.

## Risks

Bad sequencing of valid primitives.

## Handoff state written for the next session

Add immutable evidence/<stage>/<implementation-id>.yaml and handoffs/<stage>/<implementation-id>.md with exact files, commands/results, decisions, risks, blockers, schema/migration changes and next legal action. Update implementation-state.yaml only through session-protocol transitions. Implementation stops at VERIFIED; review alone records REVIEW_APPROVED or REVIEW_REJECTED. Never start the next stage in the same session.

