# Project Handover

Narrative context transfer between sessions. This file's integrity is checksum-verified by
`handover/PROJECT_CHECKSUM.md` via `workflowctl check-handover` — if the two disagree, trust
neither until you've reconciled why (a stale checksum after a legitimate edit is the most likely
cause; verify with `git diff` before assuming tampering).

## Where things stand (2026-07-17)

Milestone 1 (v0.1.0) is released and committed. Milestone 2 (governed prompt generation) is
implemented, tested (448 tests passing at last check), approved by three independent fresh
implementation reviews, and **uncommitted**. GOV-1 (the self-governance layer) is complete,
validated in `docs/VALIDATION_REPORT.md`, and formally closed via task T-101.

The master roadmap to version 1.0.0 (`docs/MASTER_ROADMAP.md`) was **human-approved on
2026-07-17**, together with two explicit human decisions recorded in `docs/DECISION_LOG.md`:
one local git commit is approved to preserve the validated working tree before Milestone 3
begins (no push, no remote branch), and a lightweight CI task (T-103) joins Stage 0.

## What Milestone 2 delivered

A `prompt` package (`src/ai_workflow_engine/prompt/`) that deterministically renders, validates,
and atomically stores a governed Markdown prompt for one of seven fixed workflow stages, plus
`workflowctl prompt <stage>` CLI commands. Every rendered prompt's identity is a SHA-256 hash of
a canonical JSON serialization of its complete context. Full spec: `docs/milestone-2-plan.md`;
defect history: `docs/DECISION_LOG.md`.

## What GOV-1 added

Nothing in `src/` — only the governance documents, `self-governance.yaml`, and this handover
pair, so `workflowctl` governs this repository itself. Reasoning: `docs/GOVERNANCE_AUDIT.md`.

## What's next, in order

Stage 0 (T-101 GOV-1 closeout, T-102 documentation sync, T-103 lightweight CI) closed
2026-07-17.

1. The human-approved local commit preserving the working tree (no push, no remote branch).
2. `M-3` (T-301..T-306): normative plan first, then the persisted workflow state machine, agent
   config/report schemas, non-interactive runner, independent claim verification, closeout.
3. `M-4` (T-401..T-404), then the 1.0.0 release (T-501).

Nothing is pushed without explicit human approval, every time.
