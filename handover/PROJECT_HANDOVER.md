# Project Handover

Narrative context transfer between sessions. This file's integrity is checksum-verified by
`handover/PROJECT_CHECKSUM.md` via `workflowctl check-handover` — if the two disagree, trust
neither until you've reconciled why (a stale checksum after a legitimate edit is the most likely
cause; verify with `git diff` before assuming tampering).

## Where things stand (2026-07-18)

**All four milestones of `docs/milestones.md` are implemented.** Milestone 1 (v0.1.0, committed),
Milestone 2 (governed prompt generation), GOV-1 (self-governance, T-101), Milestone 3
(non-interactive agent execution, v0.2.0), and **Milestone 4 (controlled commit and push,
v0.3.0)** are all complete — every task independently reviewed; both milestone plans went through
plan review (M-4's took two rounds). Demonstrations: `docs/MILESTONE_3_VALIDATION.md`,
`docs/MILESTONE_4_VALIDATION.md`. The only remaining roadmap item is the 1.0.0 release (T-501).

The master roadmap to 1.0.0 (`docs/MASTER_ROADMAP.md`) was **human-approved on 2026-07-17**
(decisions in `docs/DECISION_LOG.md`). One approved local commit (preserving Milestone 2 + GOV-1
+ Stage 0) exists from 2026-07-17. **Everything since — Stage 0's T-104 and all of Milestones 3
and 4 — is uncommitted in the working tree, awaiting a fresh commit decision from the human.**
`main` is one commit ahead of `origin/main`; nothing has been pushed, per protocol.

## What Milestone 2 delivered

A `prompt` package (`src/ai_workflow_engine/prompt/`) that deterministically renders, validates,
and atomically stores a governed Markdown prompt for one of seven fixed workflow stages, plus
`workflowctl prompt <stage>` CLI commands. Every rendered prompt's identity is a SHA-256 hash of
a canonical JSON serialization of its complete context. Full spec: `docs/milestone-2-plan.md`;
defect history: `docs/DECISION_LOG.md`.

## What GOV-1 added

Nothing in `src/` — only the governance documents, `self-governance.yaml`, and this handover
pair, so `workflowctl` governs this repository itself. Reasoning: `docs/GOVERNANCE_AUDIT.md`.

## What Milestone 3 added (v0.2.0)

A `workflow` state machine (`workflowctl state`) and an `agents` execution layer
(`workflowctl agent run`): persisted hash-chained events with a fixed transition table; a
configurable agent surface with a strict report contract; a snapshot-sandbox runner with hard
timeouts and isolation; and independent claim verification with tamper-evident run artifacts.
Agent output is always verified against sandbox reality, never trusted. Full spec:
`docs/milestone-3-plan.md`; demonstration incl. lying-agent detection:
`docs/MILESTONE_3_VALIDATION.md`.

## What Milestone 4 added (v0.3.0)

A separate writable-Git surface and the approval-gated commit/push loop. `GitWriter`
(`git/writer.py`) exposes only typed methods with fixed argv shapes — force-push, branch
deletion, `reset`, `--amend`, `add -A`/glob, and `clean` are structurally unreachable — while the
read-only `GitClient.READ_ONLY_FORMS` is byte-unchanged. `workflowctl commit` / `push` /
`apply-patch` are each bound to a per-invocation control: commit/push to a human approval
artifact pinning branch/HEAD/paths, apply-patch to a verified Milestone 3 run artifact. No commit
or push happens without one, and every gate failure writes nothing. Full spec:
`docs/milestone-4-plan.md`; demonstration: `docs/MILESTONE_4_VALIDATION.md`.

## What's next

**The approved roadmap is 100% complete.** T-501 released version 1.0.0 (version-fact regex
widened so `check-governance` extracts a `1.x` version; summary in
`docs/FINAL_COMPLETION_REPORT.md`). No task-tracked work remains.

The only pending item is a **human decision on committing and pushing** the completed 1.0.0 work.
Everything since the one human-approved preservation commit (2026-07-17) — Stage 0's T-104 and
all of Milestones 3 and 4 through 1.0.0 — is uncommitted in the working tree; `main` is one
commit ahead of `origin/main` and nothing has been pushed. Committing and pushing each require
explicit human approval per `docs/AGENT_PROTOCOL.md`.

`apply-patch` (the one writable op not human-approval-gated) is flagged for the human in
`docs/milestone-4-plan.md`'s disposition; retained per the approved plan unless the human directs
otherwise.

Everything after the preservation commit is uncommitted and unpushed; the human approved only
that one snapshot commit, so T-104/T-301/T-302+ await a fresh commit decision.

Nothing is pushed without explicit human approval, every time.
