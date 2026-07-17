# Project State

Overall condition of `ai-workflow-engine`. This document is a governance mirror
(`governance.project_state` in `self-governance.yaml`) and a `governance.facts` source for the
`version` fact — it is cross-checked against `pyproject.toml` by `workflowctl check-governance`,
so keep the version line's wording exact if you edit it.

Current Version: 0.1.0

## Summary

`ai-workflow-engine` is a local orchestration foundation for governed AI-assisted software
development: deterministic, read-only inspection first, then governed prompt generation, with
agent execution and controlled commit/push explicitly deferred until each prior layer is proven.
See `docs/milestones.md` for the full four-milestone roadmap and `docs/architecture.md` for the
inspection pipeline shape.

## Completed

- Milestone 1 (v0.1.0, released 2026-07-16): deterministic read-only Git inspection, governance
  and task-state mirror checks, source-aware handover checksum verification, protected paths,
  structured CLI/JSON results.
- Milestone 2 (approved, not yet committed): governed prompt generation — deterministic,
  canonically-hashed rendering/validation/atomic storage for all seven workflow stages, plus the
  `workflowctl prompt <stage>` CLI surface. Passed three independent fresh implementation
  reviews; two real defects found and fixed along the way (see `docs/DECISION_LOG.md`).
- GOV-1 (closed 2026-07-17): the self-governance layer — this document and its siblings —
  validated end-to-end in `docs/VALIDATION_REPORT.md` and formally closed via task T-101.

## In progress

Stage 0 of the approved master roadmap (`docs/MASTER_ROADMAP.md`, human-approved 2026-07-17):
documentation synchronization (T-102) and lightweight CI (T-103) are next; see
`docs/current_task.md` for the exact Current set at any moment.

## Planned

- Non-interactive agent execution (Codex read-only review, scoped OpenCode writes) — M-3.
- Controlled, approval-gated commit and push — M-4.
- Version 1.0.0 release (T-501).

Full detail: `docs/remaining_tasks.md`, `docs/MASTER_ROADMAP.md`, and `docs/milestones.md`.

## Blockers

None currently. The human approved (2026-07-17) creating one local git commit to preserve the
validated working tree before Milestone 3 begins — no push, no remote branch. Pushing still
requires separate explicit approval per `docs/AGENT_PROTOCOL.md`.
