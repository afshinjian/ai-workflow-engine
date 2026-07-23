# AgentOS Workflow Automation — Decisions

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Decisions |
| **Purpose** | Append-only record of program-level decisions (DD-##). Subordinate to `docs/DECISION_LOG.md`; cross-posted there when repository governance requires. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Documentation & Governance session (append) · Human Owner (approval) |
| **Dependencies** | `README.md` |
| **Related Documents** | `docs/DECISION_LOG.md` |

## Format

Each entry: status, context, decision, consequences, reconsideration trigger. Entries are
appended, never rewritten; supersessions are explicit.

## DD-01 — Separate top-level package `agentos_workflow/`

- **Status:** Accepted.
- **Context:** The engine could live inside `src/ai_workflow_engine/` (this repository's
  audited engine package) or as a separate top-level package, mirroring the choice already made
  for `agentos_dashboard/` (DASH DD-01).
- **Decision:** A separate top-level package `agentos_workflow/`, so the audited engine
  package's strict lint/type/test gates and self-governance scope are never touched by AUTO
  work, and so AUTO-00x stages are ordinary `docs/TASK_QUEUE.md` tasks under the existing
  `check-task-state` discipline (same reasoning as DASH DD-01).
- **Consequences:** Zero risk to `src/ai_workflow_engine/`; AUTO tests live outside the engine
  suite's `testpaths`.
- **Reconsideration trigger:** none identified.

## DD-02 — Per-target-repository configuration at `.agentos/workflow.yaml`

- **Status:** Accepted (naming open — `OPEN_QUESTIONS.md` OD-5).
- **Context:** `self-governance.yaml` is this repository's own self-governance config, in a
  schema built for `ai-workflow-engine`'s own read-only inspection tooling; it is not a fit for
  per-target workflow-automation configuration, which needs CLI executables, timeouts, merge
  policy, and audit/state directories.
- **Decision:** A distinct configuration schema (`CONFIGURATION_MODEL.md`) at a
  target-repository-local conventional path, discovered per invocation, never assuming a
  target's shape matches this repository's own.
- **Consequences:** No coupling between AUTO's configuration and this repository's own
  governance schema; each can evolve independently.
- **Reconsideration trigger:** if a future stage needs to automate `ai-workflow-engine` itself
  as a target, this decision is revisited explicitly rather than silently reused.

## DD-03 — Claude = default implementation/repair provider; Codex = default QA provider; sessions isolated

- **Status:** Accepted.
- **Context:** The requesting Human Owner specified Claude as default implementation/repair and
  Codex as default independent QA. This repository's own Milestone 3 already established the
  principle "agent output is evidence to verify, not an authority," verified against sandbox
  reality rather than trusted.
- **Decision:** `ClaudeCLIProvider` implements and repairs; `CodexCLIProvider` independently
  verifies, with session isolation between the two (`MODEL_PROVIDER_CONTRACTS.md` §5) so QA
  never inherits the implementation session's framing.
- **Consequences:** QA has real independence; a compromised or overconfident implementation
  session cannot self-certify its own work.
- **Reconsideration trigger:** adding a third provider role requires a new decision, not a
  silent extension of this one.

## DD-04 — One workflow per target repository; local execution only; no multi-approver system (MVP)

- **Status:** Accepted.
- **Context:** MVP constraints requested explicitly: local execution, single active workflow
  per target, no distributed agents/cloud orchestration/multi-user approval.
- **Decision:** A per-target-repository lock enforces single-active-workflow; state and audit
  are local-filesystem only; authorization is single-authorizer.
- **Consequences:** Simplicity and a small, auditable trust boundary for the MVP; concurrency
  and multi-approver support are explicitly deferred (`MVP_SCOPE.md` §3), not silently
  unsupported by omission.
- **Reconsideration trigger:** any future multi-target-concurrency requirement is a new
  program decision, not an incremental change to this one.

## DD-05 — Squash-only merge, PR-only path, no admin bypass, structurally enforced

- **Status:** Accepted.
- **Context:** This repository's own Milestone 4 established the principle that dangerous Git
  operations (force-push, history rewrite, branch deletion outside policy) should be
  structurally unreachable through the writable surface, not merely policy-documented.
- **Decision:** The Git/GitHub Skill layer (`SKILL_CONTRACTS.md` §5) has no argv path that can
  reach `gh pr merge --admin`, a force-push, or a baseline commit/push — these are absent from
  the Skill surface entirely, mirroring `GitWriter`'s typed-method design.
- **Consequences:** Skill-layer code review can verify these prohibitions by inspection of the
  available methods, not by trusting every call site to remember policy.
- **Reconsideration trigger:** none identified; this is treated as permanent (`SECURITY_MODEL.md`
  §10 / `MVP_SCOPE.md` §2).

## DD-06 — Runtime workflow states named distinctly from the AUTO-00x stage lifecycle

- **Status:** Accepted.
- **Context:** Both state machines use everyday words like `AUTHORIZED`; without an explicit
  disambiguation, cross-document "state name consistency" review could wrongly read them as
  contradictory.
- **Decision:** `WORKFLOW_STATES.md` §1 and `STAGE_REGISTRY.md` §1 each carry an explicit
  cross-reference stating the two machines are distinct and naming any word shared between them
  as coincidental English overlap, not aliasing.
- **Consequences:** Reviewers and future sessions have one place each to resolve any apparent
  naming conflict.
- **Reconsideration trigger:** none identified.

## DD-07 — DASH-001 closed out as an AUTO-001 precondition

Cross-posted from `docs/DECISION_LOG.md` (2026-07-23 AUTO-001 entry) for program-local
visibility: DASH-001 was flipped from `Current` to `Done` in `docs/TASK_QUEUE.md` and its
mirrors before AUTO-001 work began, to satisfy this repository's `maximum_current_tasks: 1`
invariant. Full rationale: `docs/DECISION_LOG.md`.
