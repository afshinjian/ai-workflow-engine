# AgentOS Workflow Automation — Failure Recovery

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Failure Recovery |
| **Purpose** | Automatic repair policy, `FAILED` semantics, interruption resume, and restart requirements. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Documentation & Governance session (AUTO-001) · Human Owner (approval) |
| **Dependencies** | `WORKFLOW_STATES.md`, `MACHINE_GATES.md` |
| **Related Documents** | `AGENT_CONTRACTS.md` §3-4, `AUDIT_MODEL.md` |

## Table of Contents
1. Automatic Repair Policy · 2. Repair Attempt Contents · 3. FAILED Semantics ·
4. Safety of a Failed Workflow · 5. Restart Requires New Authorization · 6. Resume vs. Restart ·
7. Decision References · 8. Open Questions · 9. Future Revisions

## 1. Automatic Repair Policy

- Maximum repair attempts: **3**, per workflow.
- Each repair attempt is driven by `ImplementationAgent` invoking `ClaudeCLIProvider` with the
  **latest** structured QA report (or deterministic-validation failure report) as input — never
  a stale report from an earlier attempt.
- After every repair attempt, **all** deterministic validations (`MACHINE_GATES.md` §3) and
  independent Codex QA (`MACHINE_GATES.md` §4) run again in full — a repair is never assumed
  correct and never partially re-validated.
- After 3 failed repair attempts, the workflow is marked `FAILED`. There is no 4th attempt, and
  no automatic escalation to a different provider or strategy.

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
DD-04.

## 8. Open Questions
OD-4 (whether transient infrastructure retries are cleanly separated from the repair-attempt
counter in the eventual implementation).

## 9. Future Revisions
Changing the repair-attempt limit (3) or the "re-run everything after every attempt" rule is a
MAJOR change requiring explicit Human Owner review, since it changes how much autonomous
correction the engine is allowed before requiring a human to look again.
