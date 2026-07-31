# AUTO-010 — Real Non-Interactive Provider Runtime

| Field | Value |
|---|---|
| **Stage** | AUTO-010 |
| **Title** | Real Non-Interactive Provider Runtime |
| **Role** | Engine implementation session |
| **Branch** | `feature/auto-010-provider-runtime` |
| **Predecessor** | AUTO-009 (`COMPLETE`) |
| **Report** | `docs/reports/workflow-automation/AUTO-010-completion-report.md` |

## 1. Mission

Implement and validate the real non-interactive Provider Runtime for Claude Code and Codex. The
target architecture for this stage is only:

```text
WorkflowService
        │
        ▼
Provider Runtime
        │
 ┌──────┴──────┐
 ▼             ▼
Claude CLI   Codex CLI
```

The stage must prove that both installed provider CLIs can run without an interactive terminal,
receive a complete prompt through stdin, never ask the user questions, execute under an explicit
permission or sandbox policy, return a structured machine-readable result, enforce timeouts and
output limits, isolate invocation artifacts, and return `BLOCKED` rather than waiting for
clarification.

This is **not** a workflow-mode implementation stage.

## 2. Fundamental auto-mode rule

Claude and Codex must always run in fully automatic, non-interactive mode. During provider
execution they must never ask a question, wait for keyboard input, display an approval prompt,
request permission interactively, pause for clarification, open an interactive session, require a
TTY, or wait indefinitely.

If information is incomplete, a provider must do exactly one of:

1. proceed using a safe, scope-preserving assumption and record it;
2. return a structured `BLOCKED` result with concrete evidence;
3. return a structured `FAILED` result for an execution failure.

A provider must never remain running while waiting for a human answer.

## 3. Strict scope

AUTO-010 may implement only:

1. explicit non-interactive Claude CLI execution;
2. explicit non-interactive Codex CLI execution;
3. closed permission and sandbox configuration;
4. provider invocation through a narrow `WorkflowService` boundary;
5. structured provider results;
6. real CLI acceptance tests;
7. timeout, output-limit, environment, and session-isolation validation.

No workflow lifecycle is implemented.

## 4. Required architecture

The existing AgentOS provider framework is reused, never duplicated. The dependency direction is:

```text
WorkflowService
    → public Provider Runtime boundary
        → ClaudeCLIProvider / CodexCLIProvider
            → shared provider process runner
```

`WorkflowService` must not contain provider-specific CLI flags or subprocess logic, and must not
bypass the provider abstraction with direct subprocess calls. No second provider framework is
created.

The public request selects a closed provider target (`CLAUDE`, `CODEX`) and exposes neither an
arbitrary executable path nor arbitrary CLI arguments.

## 5. Permission and sandbox policy

Claude's permission mode is drawn from a strict enum limited, for this stage, to `plan`,
`dontAsk`, and `acceptEdits`. `bypassPermissions` is not permitted.

Codex's sandbox mode is drawn from a strict enum limited to `read-only` and `workspace-write`.
`danger-full-access` is not permitted.

## 6. Never-ask enforcement

Three independent layers are implemented and tested; prompt wording alone is not sufficient.

* **Layer 1 — prompt contract.** Every provider prompt explicitly states that the provider must
  not ask questions, must not pause for clarification, must proceed on safe scope-preserving
  assumptions, and must return a structured `BLOCKED` result when safe continuation is impossible.
* **Layer 2 — mechanical non-interactivity.** No allocated TTY, exactly one prompt on stdin, stdin
  closed after the prompt, non-interactive CLI flags, no later user input, termination on timeout.
* **Layer 3 — structured terminal result.** Every execution ends in `COMPLETED`,
  `COMPLETED_WITH_ASSUMPTIONS`, `BLOCKED`, or `FAILED`, with `COMPLETED_WITH_ASSUMPTIONS`
  requiring a recorded assumption, `BLOCKED` requiring a concrete blocking issue, and `FAILED`
  requiring a typed failure category.

## 7. Result contract

The stage adds only the minimum typed provider-runtime result needed to prove real invocation, and
reuses `ProviderReport`, `ProviderFailure`, and `ProviderVerdict` where possible. The full
AUTO-011 unified agent-result redesign is **not** performed here.

## 8. Prohibited

Preparation/Reviewer/Implementer Mode; workflow authorization, approval, or approval timeouts;
Telegram; daemon; task scheduling; workflow start/resume/cancel; Codex direct correction workflow;
Claude–Codex orchestration; Git commit, push, PR, CI polling, merge, or branch cleanup; Python
governance closeout; shell-script retirement; the AUTO-011 unified agent result; the AUTO-012
approval policy; and any successor stage.

The workflow state machine is not modified absent a proven blocker. Git/GitHub skill registration
is not altered. Existing `workflowctl auto status|list|audit|report` behaviour and output are not
modified.

## 9. Newly discovered defects

A newly discovered defect is fixed only if it prevents real non-interactive Claude or Codex
execution, no safe scope-preserving workaround exists, the correction is minimal, and it is
documented as an AUTO-010 blocker. Every other defect is assigned an identifier, classified
(`REQUIRED`, `RECOMMENDED`, `OPTIONAL`, `FUTURE`), explained, and deferred.

## 10. Validation

`pytest -q`; `pytest -q -m live_cli`; `ruff check .`; `black --check .`; `mypy --strict`;
`pre-commit run --all-files`; `workflowctl verify --config self-governance.yaml`. Wheel packaging,
out-of-tree importability, and existing `workflowctl auto` compatibility are additionally verified.

Live acceptance tests run against disposable temporary repositories only. The target repository is
never used as a live write-test location. If live tests cannot run because credentials, quotas,
network, or provider availability are missing, the stage does not claim success, does not
substitute mocked tests, classifies itself as blocked or partially validated, reports exact
evidence, and stops before approval.

## 11. Stop condition

After implementation and all available validation the session stops at the Human Owner approval
gate: no implementation/closeout commit, no push, no PR, no merge, and no AUTO-011.
