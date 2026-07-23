# AgentOS Workflow Automation — MVP Scope

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — MVP Scope |
| **Purpose** | Binding boundary of the first release: included, deferred, and prohibited. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Documentation & Governance session (AUTO-001) · Human Owner (approval) |
| **Dependencies** | `ARCHITECTURE.md`, `STAGE_REGISTRY.md` |
| **Related Documents** | `SECURITY_MODEL.md`, `CONFIGURATION_MODEL.md` |

## Table of Contents
1. Included · 2. Prohibited · 3. Deferred · 4. MVP Acceptance Definition ·
5. Decision References · 6. Open Questions · 7. Future Revisions

## 1. Included

- Local execution only.
- One active workflow at a time, per target repository.
- GitHub-hosted target repositories only.
- GitHub CLI (`gh`) integration for PR/merge/check operations.
- Local Claude Code CLI integration (`ClaudeCLIProvider`).
- Local Codex CLI integration (`CodexCLIProvider`).
- Automatic squash merge, gated per `MACHINE_GATES.md` §5.
- The full state machine, all six Agents, all skill groups, and the audit/configuration models
  defined in this document set.

## 2. Prohibited (permanently, not just for MVP)

- GitHub admin bypass, under any condition (`SECURITY_MODEL.md` §4).
- Direct baseline mutation (commit or push) (`SECURITY_MODEL.md` §2).
- Autonomous scope expansion — working outside the active stage contract, or performing
  future-stage work (`SKILL_CONTRACTS.md` §3, `MACHINE_GATES.md` §3).

## 3. Deferred (explicitly out of MVP scope)

- No web dashboard.
- No distributed agents.
- No cloud orchestration.
- No multi-user approval system (the single human gate is single-authorizer by design for the
  MVP; multi-approver workflows are future scope, not silently supported).
- Running more than one workflow concurrently against the same target repository.
- `MockProvider` as a production (non-test, non-dry-run) provider selection
  (`MODEL_PROVIDER_CONTRACTS.md` §4).
- A defined safe-reauthorization policy for baseline-commit drift (`OPEN_QUESTIONS.md` OD-7) —
  until defined, drift is always a hard stop.

## 4. MVP Acceptance Definition

AUTO-001..AUTO-007 all `COMPLETE` per `STAGE_REGISTRY.md`; AUTO-007's end-to-end dry run
(`MockProvider`-driven and, separately, a real target-repository run) demonstrates the full
state machine from `CREATED` to `DONE` including at least one automatic repair cycle and one
interruption/resume cycle; every safety rule in `SECURITY_MODEL.md` verified by a dedicated
test; Human Owner records final MVP acceptance.

## 5. Decision References
DD-04.

## 6. Open Questions
OD-7.

## 7. Future Revisions
Moving an item from §3 (Deferred) into scope requires a new Decision entry and, if it changes
any safety property in §2, explicit Human Owner review before any implementation begins.
