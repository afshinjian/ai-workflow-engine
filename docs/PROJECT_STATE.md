# Project State

Overall condition of `ai-workflow-engine`. This document is a governance mirror
(`governance.project_state` in `self-governance.yaml`) and a `governance.facts` source for the
`version` fact — it is cross-checked against `pyproject.toml` by `workflowctl check-governance`,
so keep the version line's wording exact if you edit it.

Current Version: 1.0.0

## Summary

`ai-workflow-engine` is a local orchestration foundation for governed AI-assisted software
development: deterministic read-only inspection, governed prompt generation, non-interactive
agent execution with independent claim verification and a persisted workflow state machine, and
approval-gated controlled commit and push. All four milestones are implemented. See
`docs/milestones.md` for the four-milestone roadmap, `docs/MASTER_ROADMAP.md` for the task-level
plan to 1.0, and `docs/architecture.md` for the pipeline shapes.

## Completed

- AUTO-006 (closed 2026-07-28): the eight Git/GitHub Skills of `SKILL_CONTRACTS.md` §5 in
  `agentos_workflow/skills/git_github.py` — `create_commit`, `push_stage_branch`,
  `create_pull_request`, `read_pull_request_state`, `verify_head_sha`, `read_required_checks`,
  `enable_automatic_squash_merge`, `verify_merge_completion` — binding the eight Skill names
  `GitAgent`/`MergeAgent` (AUTO-005) already called against fakes; no Agent code changed. OD-1
  resolved in favor of native GitHub auto-merge (`gh pr merge --auto --squash`). Implemented,
  validated, approved by the Human Owner, committed as
  `d8d356d060076be4ad78afb4d20891004a946204`, and merged into `main` under the same decision.
  Report: `docs/reports/workflow-automation/AUTO-006-completion-report.md`.
- GOV-AUTO-02 (closed 2026-07-28): the local Human task authorization and launch gate in
  `scripts/workflow-authorize.sh`, with exact task naming, fail-closed readiness and baseline
  checks, two Human confirmations, governance-only authorization commits, and optional launch
  through the existing runner only after authorization is committed and verified. Implemented,
  validated, approved by the Human Owner, and committed as
  `d212e4d2dae2cd0a3510c54d7cd098fdfd5da548`. Report:
  `docs/reports/GOV-AUTO-02-completion-report.md`.
- AUTO-005 (closed 2026-07-28): the six AgentOS Workflow Automation Agents in
  `agentos_workflow/agents/` — `PMOAgent`, `ImplementationAgent`, `QAAgent`, `GitAgent`,
  `MergeAgent`, `CloseoutAgent` — each bounded by a capability broker to the Skills and Provider
  roles its own contract lists, none deciding its own workflow-state transition, plus the
  Orchestrator-owned `VALIDATING` sequence and the bounded repair loop. Implemented, validated,
  approved by the Human Owner, committed as `430cbb4`, and merged into `main` under the same
  decision. Report: `docs/reports/workflow-automation/AUTO-005-completion-report.md`.
- AUTO-004 (closed 2026-07-28): the AgentOS Workflow Automation Model Provider layer in
  `agentos_workflow/providers/` — the common `Provider` interface, `ClaudeCLIProvider` and
  `CodexCLIProvider` as subprocess adapters over each target repository's own configured
  executable and timeout, and `MockProvider` as an offline substitute structurally excluded from
  any real authorized workflow. Implemented, validated, approved by the Human Owner, committed as
  `84616d5`, and merged into `main` under the same decision. Report:
  `docs/reports/workflow-automation/AUTO-004-completion-report.md`.
- AUTO-003 (closed 2026-07-27): the deterministic Repository, Contract, Validation, and Reporting
  Skill families in `agentos_workflow/skills/`, committed as `908be94` and merged into `main` via
  `a3b5b0a`.
- AUTO-002 (closed 2026-07-27): orchestrator, 19-state workflow machine, authorization capture,
  append-only persistence, per-repository locking, retry accounting, local resume/evidence
  observation, security-boundary hardening, and regression coverage under `agentos_workflow/`.
  The Human Owner accepted the implementation for closure without another independent review
  after the approved remediation and configured gates passed.
- AUTO-001 (closed 2026-07-24): AgentOS Workflow Automation architecture and governance
  contracts — the complete documentation set under `docs/workflow-automation/`, merged into
  `main` via PR #3 (`191f600`). Formally flipped to `Done` per Human Owner review (see
  `docs/DECISION_LOG.md`, 2026-07-24 entry).
- DASH-001 (closed 2026-07-23): AgentOS Dashboard planning foundation and contracts — the
  complete documentation set under `docs/agentos-dashboard/`, merged into `main` via PR #1
  (`5f82996`). Formally flipped to `Done` as an AUTO-001 precondition (see
  `docs/DECISION_LOG.md`, 2026-07-23 AUTO-001 entry).
- Milestone 1 (v0.1.0, released 2026-07-16): deterministic read-only Git inspection, governance
  and task-state mirror checks, source-aware handover checksum verification, protected paths,
  structured CLI/JSON results.
- Milestone 2 (approved; committed locally 2026-07-17): governed prompt generation — deterministic,
  canonically-hashed rendering/validation/atomic storage for all seven workflow stages, plus the
  `workflowctl prompt <stage>` CLI surface. Passed three independent fresh implementation
  reviews; two real defects found and fixed along the way (see `docs/DECISION_LOG.md`).
- GOV-1 (closed 2026-07-17): the self-governance layer — this document and its siblings —
  validated end-to-end in `docs/VALIDATION_REPORT.md` and formally closed via task T-101.
- Milestone 3 (v0.2.0, 2026-07-18): non-interactive agent execution — a persisted, hash-chained
  workflow state machine (`workflowctl state`), the `agents` config section + strict report
  contract, a snapshot-sandbox runner with hard timeouts and isolation, and independent claim
  verification with tamper-evident run artifacts (`workflowctl agent run`). Each task (T-301..
  T-306) passed independent review; the normative plan is `docs/milestone-3-plan.md` and the
  demonstration is `docs/MILESTONE_3_VALIDATION.md`.
- Milestone 4 (released in v1.0.0, 2026-07-18): controlled commit and push — a separate typed
  writable-Git surface (`GitWriter`, read-only `GitClient` untouched), per-invocation human
  approval artifacts, and the `workflowctl commit` / `push` / `apply-patch` gates. Each task
  (T-401..T-404) passed independent review (the plan review took two rounds); normative plan
  `docs/milestone-4-plan.md`, demonstration `docs/MILESTONE_4_VALIDATION.md`. This completes all
  four milestones of `docs/milestones.md`.
- Version 1.0.0 (T-501, 2026-07-18): the approved roadmap is 100% complete. The `version`-fact
  regex was widened so `check-governance` extracts a `1.x` version; full summary in
  `docs/FINAL_COMPLETION_REPORT.md`.

## In progress

No task is in progress. AUTO-006 was implemented, validated, approved, committed as
`d8d356d060076be4ad78afb4d20891004a946204`, closed to `Done`, and merged into `main` on
2026-07-28; GOV-AUTO-02 and every earlier task were closed on their own dates. Every remaining
task requires its own fresh written Human Owner authorization naming it before work begins.
Closing AUTO-006 authorizes no successor; AUTO-007, GOV-2, and GOV-3 remain explicitly
unauthorized.

## Planned

AUTO-007 (`docs/TASK_QUEUE.md`; program plan `docs/workflow-automation/README.md`)
and Dashboard stages DASH-002..DASH-010 (program plan
`docs/agentos-dashboard/MASTER_PLAN.md`), each requiring its own fresh Human Owner
authorization; DASH-004 onward additionally gated on the OD-D9 dependency decision. Separately,
two ordinary (non-AUTO/DASH-family) governance/tooling tasks. **GOV-3**
(`docs/TASK_QUEUE.md`) was recorded on 2026-07-28 by Human Owner decision as explicit future work:
the Reporting Skills write one artifact per workflow identifier per kind, but a bounded repair loop
produces several genuinely different QA and stage reports per workflow; AUTO-005 works around it
with a per-attempt audit scope, and the fix is an attempt-aware artifact name. **GOV-2**
(`docs/TASK_QUEUE.md`):
extending `workflowctl check-governance` to machine-verify stage-registry/lifecycle consistency,
assessed but deliberately not implemented during the 2026-07-24 governance recovery (real
validator code needing its own authorization, out of scope for a documentation-only recovery
session) — requires its own fresh authorization like any other Planned task. Candidate future
engine work (explicitly out of the delivered 1.0.0 scope) remains listed in
`docs/FINAL_COMPLETION_REPORT.md` under "Future improvements".

## Blockers

There is no active task blocker. Every planned successor still requires separate Human Owner
authorization.

`main` and `origin/main` are identical and carry the AUTO-006 merge; `feature/auto-004-model-
providers`, `feature/auto-005-agents`, and `feature/auto-006-pr-merge-closeout` were all pushed to
`origin` and retained, not deleted. Stage branches created later and not yet pushed produce the
pre-existing `upstream_missing` finding from `workflowctl check-git` — the tolerance
`docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 16 and the SSP both name.
