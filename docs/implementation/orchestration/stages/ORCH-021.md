# ORCH-021 — Candidate commit push and receipts

## Objective

Implement only the candidate commit push and receipts capability described by Architecture v3.

## Reason it must occur at this point

Prerequisites are 015,017,020. Its contracts must be independently accepted before any dependent stage.

## Prerequisites

Every listed stage (015,017,020) must be REVIEW_APPROVED, with committed review evidence. The repository/state preflight in session-protocol.md must pass.

## Exact allowed files or directories

src/ai_workflow_engine/commit/, git/, candidate/workflow/task completion integration, cli.py, tests/test_terminal_publication.py, ORCH records.

## Files expected to be created

receipt/terminal service/tests.

## Files expected to be modified

existing gates/writer/CLI/integration.

## Public interfaces added or changed

candidate commit; push; push state; task complete.

## Schemas added or changed

CommitReceipt/PushReceipt/TaskCompletionRecord 1.0.0.

## Migrations required

Only migrations explicitly owned by this stage in migration-registry.yaml may change; otherwise none. Migration apply to the real repository requires a separate authorized migration session.

## Invariants introduced

Exact applied fingerprint; approval binds commit/push; remote OID; Done plus receipts for terminal.

## Tests required

Focused unit, negative and fault/concurrency tests for every invariant, plus affected existing tests and the full regression suite. Tests use isolated temporary repositories/data roots and must not mutate real governance.

## Verification commands

Run independently and record exact argv, output digest and exit status: pytest -q tests/test_terminal_publication.py tests/test_commit_gates.py tests/test_push_gates.py; pytest -q.

## Acceptance criteria

All specified tests pass; all changed paths are allowed; schemas/interfaces match Architecture v3; evidence and handoff are complete; no unresolved blocker remains; an independent reviewer can reproduce the result.

## Non-goals

No autonomous routing or approval removal.

## Rollback strategy

Use receipts in disposable repos; revert integration.

## Independent review checklist

Terminal trace and dependency remains blocked on failure. The reviewer must differ from implementation/remediation actors and rerun every verification command from the committed implementation HEAD.

## Risks

Network ambiguity.

## Handoff state written for the next session

Add immutable evidence/<stage>/<implementation-id>.yaml and handoffs/<stage>/<implementation-id>.md with exact files, commands/results, decisions, risks, blockers, schema/migration changes and next legal action. Update implementation-state.yaml only through session-protocol transitions. Implementation stops at VERIFIED; review alone records REVIEW_APPROVED or REVIEW_REJECTED. Never start the next stage in the same session.

