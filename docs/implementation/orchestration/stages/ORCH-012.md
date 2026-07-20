# ORCH-012 — Contribution capture and verification

## Objective

Implement only the contribution capture and verification capability described by Architecture v3.

## Reason it must occur at this point

Prerequisites are 011,008. Its contracts must be independently accepted before any dependent stage.

## Prerequisites

Every listed stage (011,008) must be REVIEW_APPROVED, with committed review evidence. The repository/state preflight in session-protocol.md must pass.

## Exact allowed files or directories

agents/runner.py, artifacts.py, verification.py, candidate modules, tests/test_agent_contribution.py, ORCH records.

## Files expected to be created

ContributionRecord/tests.

## Files expected to be modified

runner/artifact/verification integration.

## Public interfaces added or changed

run chain-baseline/contribution fields.

## Schemas added or changed

ContributionRecord 1.0.0; AgentRunRecord additions.

## Migrations required

Only migrations explicitly owned by this stage in migration-registry.yaml may change; otherwise none. Migration apply to the real repository requires a separate authorized migration session.

## Invariants introduced

Contribution relative to synthetic baseline; all file kinds captured; paths confined.

## Tests required

Focused unit, negative and fault/concurrency tests for every invariant, plus affected existing tests and the full regression suite. Tests use isolated temporary repositories/data roots and must not mutate real governance.

## Verification commands

Run independently and record exact argv, output digest and exit status: pytest -q tests/test_agent_contribution.py tests/test_agent_runner.py tests/test_agent_artifacts.py; pytest -q.

## Acceptance criteria

All specified tests pass; all changed paths are allowed; schemas/interfaces match Architecture v3; evidence and handoff are complete; no unresolved blocker remains; an independent reviewer can reproduce the result.

## Non-goals

No prompt/target apply.

## Rollback strategy

Revert runner integration.

## Independent review checklist

Index, rename, untracked, symlink and failure cleanup. The reviewer must differ from implementation/remediation actors and rerun every verification command from the committed implementation HEAD.

## Risks

Engine files captured.

## Handoff state written for the next session

Add immutable evidence/<stage>/<implementation-id>.yaml and handoffs/<stage>/<implementation-id>.md with exact files, commands/results, decisions, risks, blockers, schema/migration changes and next legal action. Update implementation-state.yaml only through session-protocol transitions. Implementation stops at VERIFIED; review alone records REVIEW_APPROVED or REVIEW_REJECTED. Never start the next stage in the same session.

