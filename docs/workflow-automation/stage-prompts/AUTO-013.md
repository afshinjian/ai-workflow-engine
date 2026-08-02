# AUTO-013 — Foreground Implementer Mode (AUTHORIZED → PR_OPEN)

| Field | Value |
|---|---|
| **Stage** | AUTO-013 |
| **Title** | Foreground Implementer Mode (AUTHORIZED → PR_OPEN) |
| **Role** | Engine implementation session |
| **Branch** | `feature/auto-013-implementer-to-pr` |
| **Predecessor** | AUTO-012 (`COMPLETE`) |
| **Report** | `docs/reports/workflow-automation/AUTO-013-completion-report.md` |

## 1. Mission

Implement the first real foreground workflow: an authorized runtime task driven from `AUTHORIZED`
to exactly `PR_OPEN`, and no further. The target architecture is only:

```text
Authorized Task
        │
        ▼
Preconditions
        │
        ▼
Registered Branch Preparation
        │
        ▼
Claude Implementation
        │
        ▼
Canonical AgentRunResult
        │
        ▼
Deterministic Validation
        │
        ▼
Bounded Claude Repair
        │
        ▼
ApprovalService
        │
        ▼
Commit
        │
        ▼
Push
        │
        ▼
Create Pull Request
        │
        ▼
PR_OPEN
```

STOP.

AUTO-013 implements no waiting for CI, no merge, no merge confirmation, no baseline update, no
branch cleanup, no runtime closeout, no Codex review or correction, no Telegram, no daemon, no
scheduler, no Preparation Mode, no Reviewer Mode, and no AUTO-014 or AUTO-015 behaviour.

## 2. Guarded QA policy

Default `independent_qa_required = true`. AUTO-013 supports `independent_qa_required = false`
through the same guarded opt-in discipline AUTO-012 established for `TimeoutAction.AUTO_APPROVE`:
a `false` value is a configuration error unless it is selected explicitly at the gate or per-run
layer, never inherited from a broad built-in or project default. `qa_passed = true` is never
fabricated when QA has not run — a skipped QA round records that it was skipped, never a verdict.

## 3. Required implementation

`ImplementerModeDriver`; `ImplementationTask`; a `WorkflowService` implementation entry point;
guarded QA configuration; runtime task execution; Claude invocation; `AgentRunResult` integration;
deterministic validation; bounded repair; `ApprovalService` integration; commit; push; PR creation;
stop at `PR_OPEN`; resume support for every AUTO-013 state (`AUTHORIZED`, `PRECONDITIONS_CHECKED`,
`BRANCH_CREATED`, `IMPLEMENTING`, `VALIDATING`, `REPAIRING`, `READY_TO_COMMIT`, `COMMITTED`,
`PUSHED`, `PR_OPEN`).

Every existing subsystem is reused; none is duplicated.

## 4. Provider Runtime and Approval reuse

`ProviderRuntime`, the Claude provider, the Codex provider, `ProviderResult`, and `AgentRunResult`
(AUTO-010/AUTO-011) are reused exactly and not modified. `ApprovalService`, its policy resolution,
its timeout mechanism, and its persistence (AUTO-012) are reused exactly and not redesigned; this
stage only consumes approvals through the existing five-operation `WorkflowService` boundary.

## 5. Validation

Deterministic validation reuses `agents.run_deterministic_validation` unmodified. Repair may fix
only tests, lint, formatting, type checking, or a malformed completion report — never scope
violations, forbidden paths, secret findings, or security findings, which fail the workflow
directly rather than entering the repair cycle. Maximum repair attempts: 3. No fourth attempt.

## 6. Security

Preserved unmodified: no `shell=True`, fixed argv, provider isolation, approval integrity, checksum
validation, scope validation, forbidden-path validation, secret detection, deterministic
validation.

## 7. Boundaries

`WorkflowService`'s public surface is not extended with a sixth workflow verb — its own docstring
and `test_service.py`'s `APPROVED_OPERATIONS`/`FORBIDDEN_OPERATIONS` pins explicitly forbid adding
`implement` (or any other lifecycle verb) to that class. The "`WorkflowService` implementation
entry point" this stage requires is satisfied by `ImplementerModeDriver` composing
`WorkflowService.invoke_provider` and `WorkflowService`'s five approval operations as its provider-
and approval-facing entry points, alongside a directly held `WorkflowSession` for state, locking,
and durable attempt bookkeeping — the same composition pattern the AUTO-013 research already
identified as consistent with `WorkflowService`'s own stated boundary.

`WorkflowState`'s 19 members and 37 edges are not extended. If the guarded QA skip or any other
required behaviour can be implemented without a new state or edge, that is required, not merely
preferred.

## 8. Strictly prohibited

Waiting for CI; merge; merge confirmation; baseline update; branch cleanup; runtime closeout;
Codex review; Codex correction; Telegram; daemon; scheduler; Preparation Mode; Reviewer Mode;
AUTO-014; AUTO-015. Modifying `ProviderRuntime`, either CLI provider, `ProviderResult`,
`AgentRunResult`, or `ApprovalService`. Adding a sixth `WorkflowService` verb. Adding a new
`WorkflowState` member or transition edge. Fabricating a QA verdict when QA was skipped by policy.
Live acceptance testing against this repository — only disposable repositories.

## 9. Newly discovered defect policy

A newly discovered defect that does not directly block AUTO-013 is recorded, classified, added to
the completion report's Deferred Findings, and left unimplemented. No GOV stage is created. A
defect may be fixed only when it directly prevents completion, no scope-preserving workaround
exists, the fix is minimal, and it is documented explicitly as an AUTO-013 blocker.

## 10. Stop condition

After implementation and complete validation: no implementation/closeout commit, no push, no pull
request, no merge, no AUTO-014 work, and no AUTO-015 work. The stage stops at the Human Owner
approval gate with a complete completion report.
