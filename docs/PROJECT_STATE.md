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

The entire approved 1.0.0 roadmap (`docs/MASTER_ROADMAP.md`) is complete. The active task is
DASH-001 (dashboard planning foundation), the first stage of the post-1.0 **AgentOS Dashboard
program** authorized by the Human Owner on 2026-07-23: a documentation-only stage on branch
`governance/dash-001-documentation` establishing the planning set under
`docs/agentos-dashboard/`. It was recovered and re-executed correctly for this repository on
2026-07-23 after a mis-targeted first execution (see `docs/agentos-dashboard/DECISIONS.md`
DD-03). Details: `docs/current_task.md`.

## Planned

Dashboard stages DASH-002..DASH-010 (`docs/TASK_QUEUE.md`; program plan
`docs/agentos-dashboard/MASTER_PLAN.md`), each requiring its own fresh Human Owner
authorization; DASH-004 onward additionally gated on the OD-D9 dependency decision. Candidate
future engine work (explicitly out of the delivered 1.0.0 scope) remains listed in
`docs/FINAL_COMPLETION_REPORT.md` under "Future improvements".

## Blockers

None currently. One human-approved local commit (preserving Milestone 2, GOV-1, and Stage 0)
exists from 2026-07-17. Everything since — Stage 0's T-104 and all of Milestones 3 and 4, up to
and including the 1.0.0 release — is uncommitted in the working tree, awaiting a fresh commit
decision from the human; `main` is one commit ahead of `origin/main` and nothing has been pushed.
Committing and pushing each require explicit human approval per `docs/AGENT_PROTOCOL.md` — the
very gates Milestone 4 now provides.
