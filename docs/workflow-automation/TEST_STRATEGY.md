# AgentOS Workflow Automation — Test Strategy

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Test Strategy |
| **Purpose** | How the engine itself will be tested across AUTO-002..AUTO-007, without ever invoking real Claude/Codex CLIs or real GitHub state in the default test run. |
| **Status** | Draft |
| **Version** | 1.2 |
| **Owner** | Documentation & Governance session (AUTO-001) · Human Owner (approval) |
| **Dependencies** | `MODEL_PROVIDER_CONTRACTS.md` §4, `WORKFLOW_STATES.md` |
| **Related Documents** | `MVP_SCOPE.md` §4, `SECURITY_MODEL.md` |

## Table of Contents
1. Test Levels · 2. MockProvider-Driven State-Machine Tests · 3. Skill Contract Tests ·
4. Security Tests · 4a. Interruption/Resume Tests · 4b. Initial-Execution Retry/Reconciliation
Tests · 5. End-to-End Dry Run (AUTO-007) · 6. Engine Non-Regression · 7. Decision References ·
8. Open Questions · 9. Future Revisions

## 1. Test Levels

- **Unit** — one Skill or one Agent method at a time, subprocess calls mocked.
- **Contract** — QA/stage/failure/closeout report schemas validated against
  `validate_completion_report` / `validate_qa_report`.
- **Integration** — full state machine driven end-to-end against a disposable local Git
  repository fixture, using `MockProvider` for both implementation and QA.
- **End-to-end dry run** — AUTO-007, against a real (throwaway) target repository, still
  defaulting to `MockProvider` unless explicitly configured otherwise.

## 2. MockProvider-Driven State-Machine Tests

Every transition in `WORKFLOW_STATES.md` §3 has at least one test driving it via
`MockProvider` configured to return a canned pass or fail report, so the full
`CREATED → DONE` and `CREATED → FAILED` (via exhausted repair attempts) paths are exercised
without any real model CLI or network call. This is the primary regression suite and runs on
every change.

## 3. Skill Contract Tests

Each Skill (`SKILL_CONTRACTS.md`) is tested against a temporary real Git repository fixture
(init/commit/branch/merge/dirty/detached-HEAD cases), mirroring this repository's own
`GitClient`/`GitWriter` test discipline. GitHub-facing Skills (§5 of `SKILL_CONTRACTS.md`) are
tested against a mocked `gh` invocation layer; no test suite run depends on network access or a
real GitHub repository.

## 4. Security Tests

Dedicated tests for every rule in `SECURITY_MODEL.md`: attempted baseline commit/push is
rejected; attempted force-push/history-rewrite is structurally unreachable (not just refused);
attempted `gh pr merge --admin` path does not exist in the Skill layer; secret-shaped strings in
mocked command output are redacted before reaching an audit record or report; an
environment-variable not in the allowlist is never forwarded to a Provider/Skill subprocess.

## 4a. Interruption/Resume Tests

Simulated process interruption at each state (kill and restart the Orchestrator mid-workflow),
verifying: state persisted correctly before the interruption; resume re-verifies preconditions
per `WORKFLOW_STATES.md` §6; a drifted authorization-bound value (e.g. baseline SHA changed)
is detected and moves the workflow to `FAILED` rather than silently continuing; no Skill
side effect is duplicated on resume (idempotency, `WORKFLOW_STATES.md` §7). "At each state"
means every non-terminal state except `CREATED`; `WORKFLOW_STATES.md` §3's transition table
lists an explicit `→ FAILED` row for every one of them, so this requirement has a legal
transition to exercise at every state named here — none is an untestable, table-unsupported
case.

## 4b. Initial-Execution Retry/Reconciliation Tests

For each of `IMPLEMENTING`, `READY_TO_COMMIT`, `COMMITTED`, `PUSHED` (`WORKFLOW_STATES.md` §5a):
a `MockProvider`/mocked-Skill test for each of the five numbered outcomes — transient failure
retried and then succeeding within the limit; transient failure exhausting the limit reaching
`FAILED`; a possible-side-effect failure where reconciliation confirms success (advances with no
duplicated side effect — assert the Skill's idempotent no-op path, `WORKFLOW_STATES.md` §7, is
what was exercised, not a second real invocation); a possible-side-effect failure where
reconciliation finds a recoverable inconsistency (`IMPLEMENTING` only: asserts the flow reaches
`REPAIRING` via the existing `VALIDATING` route, never a direct edge); and an unrecoverable/
indeterminate failure reaching `FAILED` with a complete failure report
(`FAILURE_RECOVERY.md` §3). A dedicated test asserts a timeout alone, with no reconciliation
performed, never produces a state read as success (§5a item 6).

## 5. End-to-End Dry Run (AUTO-007)

A full run against a disposable target repository, `MockProvider` for both roles, exercising:
at least one automatic repair cycle (`FAILURE_RECOVERY.md`), one interruption/resume cycle, the
full commit → push → PR → auto-merge-enable → checks-wait → merge → closeout path, and a
DASH-family stage contract as the real-world stage-contract shape being automated
(`docs/agentos-dashboard/stage-prompts/`), demonstrating the engine can read an existing,
independently-authored stage contract without modification to that contract's format.

## 6. Engine Non-Regression

Every AUTO-00x stage's test run additionally confirms `ai-workflow-engine`'s own existing test
collection (`pytest tests --collect-only -q`) is unchanged, mirroring the DASH program's own
non-regression discipline — the AUTO package is fully additive to this repository.

## 7. Decision References
DD-03, DD-09.

## 8. Open Questions
None blocking AUTO-001; concrete fixtures and CI wiring are AUTO-002+ scope.

## 9. Future Revisions
Any test level that would require real Claude/Codex credentials or real GitHub write access in
the default (non-opt-in) test run is out of scope permanently for this strategy.
