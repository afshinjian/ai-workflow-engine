# AgentOS Workflow Automation — Model Provider Contracts

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Model Provider Contracts |
| **Purpose** | Contract for every Model Provider adapter: invocation shape, isolation guarantees, and the hard boundary that providers never authorize or bypass gates. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Documentation & Governance session (AUTO-001) · Human Owner (approval) |
| **Dependencies** | `ARCHITECTURE.md` §6, `AGENT_CONTRACTS.md` |
| **Related Documents** | `SECURITY_MODEL.md`, `CONFIGURATION_MODEL.md` |

## Table of Contents
1. Common Provider Rules · 2. ClaudeCLIProvider · 3. CodexCLIProvider · 4. MockProvider ·
5. Session Isolation · 6. Decision References · 7. Open Questions · 8. Future Revisions

## 1. Common Provider Rules

- A Provider wraps exactly one local CLI executable, invoked as a subprocess with a fixed,
  bounded timeout (`CONFIGURATION_MODEL.md`).
- A Provider **never authorizes a workflow**, never decides a machine-gate outcome by itself,
  and never invokes a Skill directly — it returns a structured report to the calling Agent,
  which the Orchestrator's machine gates independently verify.
- A Provider never receives secrets in its prompt; only the allowlisted environment variables
  configured for the target repository are passed to its process (`SECURITY_MODEL.md` §1).
- A Provider's stdout/stderr is captured, sanitized, and referenced (not inlined) in audit
  records (`AUDIT_MODEL.md`).
- All Providers implement the same abstract interface (`invoke(context) -> ProviderReport`), so
  `MockProvider` is a drop-in substitute for either CLI provider in tests.

## 2. ClaudeCLIProvider

**Wraps:** the local Claude Code CLI executable (configured path + timeout per target
repository, `CONFIGURATION_MODEL.md`).

**Role:** default implementation provider (invoked by `ImplementationAgent` for the initial
stage implementation) and default repair provider (invoked by `ImplementationAgent` during
`REPAIRING`, given the latest structured QA report).

**Input:** stage contract, target repository working tree on the stage branch, and — for
repair — the most recent QA report and prior diff.

**Output:** a completion report (files changed, validation the implementation itself ran,
recommended commit message) — evidence for the Orchestrator's own deterministic validation, not
a substitute for it.

## 3. CodexCLIProvider

**Wraps:** the local Codex CLI executable (configured path + timeout per target repository).

**Role:** default independent QA provider (invoked by `QAAgent`).

**Input:** the implementation diff, deterministic validation results, and the stage contract —
never Claude's session state or reasoning, only the resulting artifacts.

**Output:** a structured QA report with an explicit pass/fail verdict and findings, independent
of `ImplementationAgent`'s self-report (`AGENT_CONTRACTS.md` §4).

## 4. MockProvider

**Role:** deterministic, offline substitute for either CLI provider, used in the engine's own
test suite (`TEST_STRATEGY.md`) and in dry runs. Configurable to return canned pass/fail reports
so every Orchestrator state transition and machine gate can be tested without invoking a real
model CLI or a network call.

**Constraint:** `MockProvider` must never be selectable as the active provider for a real
authorized workflow against a real target repository; it is a test/dry-run-only configuration
(`CONFIGURATION_MODEL.md`, `MVP_SCOPE.md`).

## 5. Session Isolation

`ClaudeCLIProvider` and `CodexCLIProvider` invocations for the same workflow are isolated from
each other:

- Separate subprocess invocations, separate working-state directories where the provider needs
  scratch space, and no shared in-process session object.
- Neither provider's process receives the other provider's raw output; only the structured,
  already-validated artifacts (diff, deterministic validation results, prior QA report for
  repair) cross the boundary, assembled by the Orchestrator/Agents.
- Isolation is a correctness property (independent QA must not be contaminated by the
  implementation session's framing) as well as a security property (`SECURITY_MODEL.md` §3).

## 6. Decision References
DD-03.

## 7. Open Questions
None blocking AUTO-001; concrete CLI invocation shape (argv, stdin/stdout protocol) is AUTO-004
scope.

## 8. Future Revisions
Adding a new provider (e.g. a future third CLI) requires implementing the same abstract
interface and is additive; it does not change the default-provider assignment (Claude =
implementation/repair, Codex = QA) without a new Decision entry.
