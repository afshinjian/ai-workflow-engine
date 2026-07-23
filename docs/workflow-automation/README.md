# AgentOS Workflow Automation

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Program Overview |
| **Purpose** | Entry point for the governance and architecture documentation set that defines a local engine automating a target repository's stage lifecycle behind a single human authorization gate. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Documentation & Governance session (AUTO-001) · Human Owner (approval) |
| **Dependencies** | None (program entry point) |
| **Related Documents** | All documents listed in §3 below; `stage-prompts/`; `docs/reports/workflow-automation/` |

## 1. Purpose

AgentOS Workflow Automation ("the workflow engine" or "AUTO") is a local orchestration layer,
implemented inside `ai-workflow-engine`, that automates a **target repository's** stage
lifecycle after a human explicitly authorizes exactly one stage. Example: automating `DASH-002`
in a separate repository once a human runs `agentos workflow authorize DASH-002`.

This is distinct from — and does not replace — `ai-workflow-engine`'s own existing
self-governance discipline (`self-governance.yaml`, `docs/TASK_QUEUE.md`,
`workflowctl check-task-state`), which continues to govern work *on this repository itself*,
including the AUTO-00x stages that build this engine. AUTO automates *other* repositories'
stages; it is built *by* ordinary `ai-workflow-engine` tasks (AUTO-001..AUTO-007).

## 2. The one human gate

The entire system is designed around a single principle: **the only human gate is explicit
stage authorization.**

```
agentos workflow authorize DASH-002
```

After a valid authorization is recorded, no additional human approval occurs during that
workflow's execution. Every later step — precondition checks, branching, implementation, QA,
repair, commit, push, PR, merge, cleanup, closeout — is controlled entirely by machine gates.
Full model: `HUMAN_AUTHORIZATION_MODEL.md`.

## 3. Document map

| Document | Covers |
|---|---|
| `ARCHITECTURE.md` | Component model, layering, execution flow |
| `WORKFLOW_STATES.md` | Runtime workflow states, transitions, retry/resume/idempotency |
| `AGENT_CONTRACTS.md` | PMOAgent, ImplementationAgent, QAAgent, GitAgent, MergeAgent, CloseoutAgent |
| `SKILL_CONTRACTS.md` | All skill groups and their contracts |
| `MODEL_PROVIDER_CONTRACTS.md` | ClaudeCLIProvider, CodexCLIProvider, MockProvider |
| `HUMAN_AUTHORIZATION_MODEL.md` | The single human gate and authorization binding |
| `MACHINE_GATES.md` | Every automatic checkpoint after authorization |
| `SECURITY_MODEL.md` | Secrets, isolation, forbidden operations |
| `FAILURE_RECOVERY.md` | Repair policy, FAILED semantics, resume, restart |
| `AUDIT_MODEL.md` | Command records, append-only audit events |
| `CONFIGURATION_MODEL.md` | Per-target-repository configuration schema |
| `TARGET_REPOSITORY_MODEL.md` | Engine repository vs. target repository; baseline binding |
| `CLI_SPEC.md` | Command surface |
| `MVP_SCOPE.md` | What the MVP includes, defers, and prohibits |
| `STAGE_REGISTRY.md` | AUTO-001..AUTO-007 stage lifecycle and authorization log |
| `TEST_STRATEGY.md` | How the engine itself will be tested |
| `DECISIONS.md` | Program-level architectural decisions (DD-#) |
| `OPEN_QUESTIONS.md` | Owner-decision register (OD-#) |
| `CHANGELOG.md` | Program-level changelog |
| `STAGE_REPORT_TEMPLATE.md` | Mandatory skeleton for AUTO stage completion reports |
| `stage-prompts/` | Canonical prompts for AUTO-001..AUTO-007, plus the Standard Stage Protocol |

## 4. Required architectural model

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

Each layer only calls downward; no layer reaches upward or skips a layer. Full detail:
`ARCHITECTURE.md`.

## 5. Scope of this stage (AUTO-001)

AUTO-001 is documentation and architecture only. No runtime code, no dependency changes, no
commit, no push, no pull request, no merge, no branch deletion. Full contract:
`stage-prompts/AUTO-001.md`; completion report:
`docs/reports/workflow-automation/AUTO-001-completion-report.md`.
