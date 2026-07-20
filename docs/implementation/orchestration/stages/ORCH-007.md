# ORCH-007 — Integrity outcome and agent-run show

## Objective

Implement only the integrity outcome and agent-run show capability described by Architecture v3.

## Reason it must occur at this point

Prerequisites are 006. Its contracts must be independently accepted before any dependent stage.

## Prerequisites

Every listed stage (006) must be REVIEW_APPROVED, with committed review evidence. The repository/state preflight in session-protocol.md must pass.

## Exact allowed files or directories

agents/models.py, agents/artifacts.py, agents/verification.py, cli.py, tests/test_agent*.py, ORCH records.

## Files expected to be created

v2 adapters/fixtures.

## Files expected to be modified

listed agent files and CLI.

## Public interfaces added or changed

agent-run show contract v2.

## Schemas added or changed

AgentRunRecord/VerificationRecord 2.0.0.

## Migrations required

Only migrations explicitly owned by this stage in migration-registry.yaml may change; otherwise none. Migration apply to the real repository requires a separate authorized migration session.

## Invariants introduced

Integrity gates events; prose excluded; outcome cannot repair integrity.

## Tests required

Focused unit, negative and fault/concurrency tests for every invariant, plus affected existing tests and the full regression suite. Tests use isolated temporary repositories/data roots and must not mutate real governance.

## Verification commands

Run independently and record exact argv, output digest and exit status: pytest -q tests/test_agent*.py tests/test_cli_contract_v2.py; pytest -q.

## Acceptance criteria

All specified tests pass; all changed paths are allowed; schemas/interfaces match Architecture v3; evidence and handoff are complete; no unresolved blocker remains; an independent reviewer can reproduce the result.

## Non-goals

No delta/cache/sandbox.

## Rollback strategy

Revert v2 adapters/CLI.

## Independent review checklist

Trace fields to verified bytes. The reviewer must differ from implementation/remediation actors and rerun every verification command from the committed implementation HEAD.

## Risks

Unsafe legacy mapping.

## Handoff state written for the next session

Add immutable evidence/<stage>/<implementation-id>.yaml and handoffs/<stage>/<implementation-id>.md with exact files, commands/results, decisions, risks, blockers, schema/migration changes and next legal action. Update implementation-state.yaml only through session-protocol transitions. Implementation stops at VERIFIED; review alone records REVIEW_APPROVED or REVIEW_REJECTED. Never start the next stage in the same session.

