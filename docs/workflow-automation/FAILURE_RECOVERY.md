# AgentOS Workflow Automation — Failure Recovery

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Failure Recovery |
| **Purpose** | Automatic repair policy, `FAILED` semantics, interruption resume, restart requirements, and initial-execution failure/reconciliation policy. |
| **Status** | Draft |
| **Version** | 1.2 |
| **Owner** | Documentation & Governance session (AUTO-001) · Human Owner (approval) |
| **Dependencies** | `WORKFLOW_STATES.md`, `MACHINE_GATES.md` |
| **Related Documents** | `AGENT_CONTRACTS.md` §3-4, `AUDIT_MODEL.md` |

## Table of Contents
1. Automatic Repair Policy · 1a. Initial-Execution Failure and Reconciliation ·
2. Repair Attempt Contents · 3. FAILED Semantics · 4. Safety of a Failed Workflow ·
5. Restart Requires New Authorization · 6. Resume vs. Restart · 7. Decision References ·
8. Open Questions · 9. Future Revisions

## 1. Automatic Repair Policy

- Maximum repair attempts: **3**, per workflow.
- Each repair attempt is driven by `ImplementationAgent` invoking `ClaudeCLIProvider` with the
  **latest** structured QA report (or deterministic-validation failure report) as input — never
  a stale report from an earlier attempt.
- After every repair attempt, **all** deterministic validations (`MACHINE_GATES.md` §3) and
  independent Codex QA (`MACHINE_GATES.md` §4) run again in full — a repair is never assumed
  correct and never partially re-validated.
- After 3 failed repair attempts, the workflow is marked `FAILED`. There is no 4th attempt, and
  no automatic escalation to a different provider or strategy. This exhausted-attempts path
  transitions out via `VALIDATING`/`QA_RUNNING` (whichever gate the Nth attempt failed at),
  already in `WORKFLOW_STATES.md` §3's table.
- Separately, if a repair attempt itself is unrecoverable — the provider invocation crashes or
  times out with no usable output to re-validate — the workflow transitions directly
  `REPAIRING → FAILED` (`WORKFLOW_STATES.md` §3) rather than looping back to `VALIDATING` with
  nothing to validate. This is distinct from the exhausted-attempts path above and from
  `REPAIRING`'s other `→ FAILED` reason (interruption/resume authorization drift,
  `WORKFLOW_STATES.md` §6 item 3) — all three are enumerated, not conflated, in the canonical
  table.

## 1a. Initial-Execution Failure and Reconciliation

Distinct from this section's repair-attempt policy (which is about `ImplementationAgent`
producing a *code* fix after `VALIDATING`/`QA_RUNNING` rejects a diff): the policy for a
side-effecting operation's own first-time execution failing — the implementation-provider
invocation, `create_commit`, `push_stage_branch`, `create_pull_request` — is normative in
`WORKFLOW_STATES.md` §5a (Human Owner policy decision OD-9, `OPEN_QUESTIONS.md`, resolved
2026-07-24; `DECISIONS.md` DD-09). Summary: bounded same-state retry before any side effect;
idempotency/reconciliation check, never a blind retry, once a side effect may have occurred;
reconciliation success advances normally; a recoverable inconsistency uses this section's
existing `REPAIRING` path (never a second repair lifecycle, and only reachable from
`IMPLEMENTING`, never directly from `READY_TO_COMMIT`/`COMMITTED`/`PUSHED`); everything else
reaches `FAILED`. Full text: `WORKFLOW_STATES.md` §5a.

## 2. Repair Attempt Contents

A repair attempt receives: the original stage contract, the current diff on the stage branch,
and the most recent QA report or deterministic-validation failure detail (whichever gate
failed). It does not receive prior repair attempts' full history beyond what is needed to avoid
repeating an already-rejected fix — exact context-window policy is AUTO-005 implementation
detail.

## 3. FAILED Semantics

`FAILED` is terminal (`WORKFLOW_STATES.md` §8). Reaching it means the workflow could not
complete the stage automatically within policy. It always carries a failure report
(`generate_failure_report`) identifying which gate failed, on which attempt, with what
evidence.

## 4. Safety of a Failed Workflow

A `FAILED` workflow must not, from the point of failure onward: create a commit, push, open a
pull request, merge, or perform destructive cleanup (branch deletion, baseline mutation) —
**unless** that specific action had already safely completed *before* the failure occurred. For
example: if `WAITING_FOR_CHECKS` fails because a required check fails, the PR remains open and
unmerged, but the earlier `PUSHED`/`PR_OPEN` steps that already completed are not undone (undoing
a non-destructive, already-safe step is not required and is not itself a repair action).
Conversely, if a precondition-gate failure occurs before `BRANCH_CREATED`, nothing has touched
the target repository beyond read-only inspection.

## 5. Restart Requires New Authorization

Restarting a `FAILED` (or `CANCELLED`) workflow always begins a brand-new workflow at `CREATED`
and requires a fresh `agentos workflow authorize <STAGE_ID>` call, producing a fresh
authorization binding (`HUMAN_AUTHORIZATION_MODEL.md` §2) — even if the target repository state
looks unchanged. There is no "retry failed workflow" command that skips authorization.

## 6. Resume vs. Restart

- **Resume** (`WORKFLOW_STATES.md` §6) is for a still-authorized, still-valid, in-flight
  workflow interrupted by a process crash or restart — it continues the same workflow instance
  from its persisted state, after re-verifying that nothing bound at authorization has drifted.
- **Restart** is for a workflow that has reached `FAILED`/`CANCELLED` (or whose resume-time
  drift check invalidated it) — it is always a new workflow with new authorization.
- The Orchestrator only ever offers resume for the single workflow permitted by the repository
  lock; there is no ambiguity about which workflow "resume" refers to (MVP constraint).

## 7. Decision References
DD-04, DD-09.

## 8. Open Questions
OD-4 (whether transient infrastructure retries are cleanly separated from the repair-attempt
counter in the eventual implementation). OD-9 resolved 2026-07-24 — §1a, `OPEN_QUESTIONS.md`.

## 9. Future Revisions
Changing the repair-attempt limit (3) or the "re-run everything after every attempt" rule is a
MAJOR change requiring explicit Human Owner review, since it changes how much autonomous
correction the engine is allowed before requiring a human to look again.
