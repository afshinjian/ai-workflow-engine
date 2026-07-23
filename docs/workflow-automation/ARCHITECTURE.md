# AgentOS Workflow Automation — Architecture

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Architecture |
| **Purpose** | Normative component model, layering, execution flow, and package layout. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Documentation & Governance session (AUTO-001) · Human Owner (approval) |
| **Dependencies** | `README.md` §4 |
| **Related Documents** | `AGENT_CONTRACTS.md`, `SKILL_CONTRACTS.md`, `MODEL_PROVIDER_CONTRACTS.md`, `WORKFLOW_STATES.md` |

## Table of Contents
1. Layering · 2. Component Responsibilities · 3. Execution Flow · 4. Package Layout ·
5. Concurrency and Locking · 6. Isolation Boundaries · 7. Non-Goals · 8. Decision References ·
9. Open Questions · 10. Future Revisions

## 1. Layering

```
Human
  ↓
CLI
  ↓
Orchestrator / Workflow Engine
  ↓
Persistent State Store + Repository Lock
  ↓
Agents
  ↓
Skills and Model Providers
  ↓
Target Repository, Git, GitHub CLI, Claude CLI, Codex CLI
```

Each layer depends only on the layer(s) below it. The CLI never calls Agents or Skills
directly — it only talks to the Orchestrator. Agents never call the Target Repository, Git,
GitHub CLI, or a model CLI directly — they only invoke named Skills or Model Providers. This
keeps every side-effecting operation reachable through exactly one narrow, typed surface.

## 2. Component Responsibilities

- **CLI** — parses operator commands (`CLI_SPEC.md`), captures the one human gate
  (authorization), and starts/resumes/inspects/cancels workflows. Contains no business logic.
- **Orchestrator / Workflow Engine** — owns the state machine (`WORKFLOW_STATES.md`), decides
  which Agent runs next, enforces machine gates (`MACHINE_GATES.md`), and is the only component
  that validates and consumes an authorization record.
- **Persistent State Store** — durable, local, per-workflow record of the current state, the
  authorization binding, transition history, and command-execution audit trail
  (`AUDIT_MODEL.md`). Survives process restarts.
- **Repository Lock** — a per-target-repository lock preventing a second workflow from starting
  against the same target while one is active (MVP: exactly one active workflow per target
  repository).
- **Agents** — coordinate a bounded set of Skills and Model Providers to accomplish one phase of
  the lifecycle (`AGENT_CONTRACTS.md`). Agents hold no direct subprocess or filesystem access.
- **Skills** — deterministic, narrowly-scoped, typed operations against the target repository,
  Git, or GitHub CLI (`SKILL_CONTRACTS.md`). Skills are the only components that shell out to
  `git`/`gh`.
- **Model Providers** — adapters over the local Claude Code CLI and Codex CLI
  (`MODEL_PROVIDER_CONTRACTS.md`). Providers return structured reports; they never authorize
  anything and never call Skills directly.

## 3. Execution Flow (informal)

1. Human runs `agentos workflow authorize <STAGE_ID>` for a target repository.
2. CLI hands the request to the Orchestrator, which validates and binds the authorization
   (`HUMAN_AUTHORIZATION_MODEL.md`), acquires the repository lock, and persists state `CREATED`
   then `AUTHORIZED`.
3. Orchestrator drives `PMOAgent` through precondition verification and stage-branch creation.
4. Orchestrator drives `ImplementationAgent`, which invokes `ClaudeCLIProvider` to implement the
   stage contract on the stage branch.
5. Orchestrator runs deterministic validation Skills (tests, lint, formatting, scope, security,
   secret detection) directly (not through an Agent — these are Orchestrator-owned machine
   gates) and then drives `QAAgent`, which invokes `CodexCLIProvider` for independent QA.
6. On any validation or QA failure, Orchestrator drives `ImplementationAgent` through a bounded
   repair loop (`FAILURE_RECOVERY.md`), re-running step 5 after each attempt.
7. On full pass, Orchestrator drives `GitAgent` (commit, push, open PR), then `MergeAgent`
   (verify head SHA, enable automatic squash merge, wait for required checks, verify merge),
   then `CloseoutAgent` (cleanup, baseline update, final verification, closeout report).
8. Orchestrator releases the repository lock and reaches a terminal state (`DONE` or `FAILED`).

## 4. Package Layout (planned for AUTO-002+)

```
agentos_workflow/
  __init__.py
  cli.py                 # CLI_SPEC.md surface
  orchestrator/
    engine.py             # state machine driver, WORKFLOW_STATES.md
    state_store.py         # persistence, AUDIT_MODEL.md
    lock.py                 # repository lock
  agents/
    pmo.py, implementation.py, qa.py, git.py, merge.py, closeout.py
  skills/
    repository.py, contract.py, validation.py, git_github.py, reporting.py
  providers/
    base.py, claude_cli.py, codex_cli.py, mock.py
  config/
    schema.py, loader.py   # CONFIGURATION_MODEL.md
  tests/
```

Naming follows the CLI namespace: `agentos workflow ...` ↔ package `agentos_workflow/`. This
package is new and separate from `src/ai_workflow_engine/` and from `agentos_dashboard/`; none
of the three import from another's internals across the writable-surface boundary. Exact module
boundaries are finalized in AUTO-002.

## 5. Concurrency and Locking

Exactly one active workflow per target repository (MVP constraint). The Repository Lock is
acquired before any state transition past `AUTHORIZED` and released only when a workflow
reaches `DONE`, `FAILED`, or `CANCELLED`. A second `authorize` call against a locked target
repository is refused by the Orchestrator before any target-repository mutation occurs.

## 6. Isolation Boundaries

`ClaudeCLIProvider` and `CodexCLIProvider` sessions are isolated from each other (separate
process invocations, separate provider-scoped working state, no shared session memory or
context). Codex's QA verdict is always independently derived from the actual diff and
deterministic validation results — never trusted from Claude's self-report. This mirrors this
repository's own Milestone 3 principle: agent output is evidence to verify, not an authority.

## 7. Non-Goals (this stage)

No runtime code is written in AUTO-001. No dependency is added. This document defines shape and
contracts only; AUTO-002 begins implementation.

## 8. Decision References
DD-01, DD-03, DD-06.

## 9. Open Questions
None blocking AUTO-001. OD-3, OD-5 affect AUTO-002 implementation choices.

## 10. Future Revisions
Package layout may be refined during AUTO-002 without invalidating this document's layering
model, which is binding for all later stages.
