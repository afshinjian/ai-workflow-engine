# Agent Protocol

Rules for any AI agent — Claude Code, Codex, OpenCode, or otherwise — working in this
repository, and for human reviewers overseeing them. This document is prose: it states what
`docs/milestones.md`'s milestone boundaries already imply, and records the review discipline
this project has actually used, so a fresh session doesn't have to reconstruct it from
conversation history.

## Where this stands today

Only **Claude Code** currently operates in this repository. Milestone 3
(`docs/milestones.md`) — "non-interactive agent execution: Codex read-only review and scoped
OpenCode writes" — is planned but **not implemented**. The role split below for Codex and
OpenCode is the *intended* division once Milestone 3 exists; do not assume any live Codex or
OpenCode integration exists in this codebase today. Until then, independence between roles is
achieved by running separate, independent agent sessions (fresh context, no memory of prior
sessions' work) rather than by separate tooling.

## Roles

**Claude Code** — architecture, planning, implementation, governance maintenance, complex
reasoning, and (via separate fresh sessions) independent review of its own or others' work.

**Codex** (planned, Milestone 3) — read-only review: independent verification of implementation
claims against actual repository state, never trusted output taken at face value.

**OpenCode** (planned, Milestone 3) — scoped writes only: implementation/refactoring/tests within
an explicitly bounded allowed-path list, never architecture or governance decisions.

**Human** — final approval on anything destructive or hard to reverse: `git push`, `git commit`
(until Milestone 4's approval-gated commit exists), deleting files, and changing governance
rules (this document, `WORKFLOW_RULES`-equivalent content, or the config schema).

## What no agent may do, regardless of role

- Push code (`git push`) without explicit human approval, every time — a prior approval does not
  carry forward to a later push.
- Delete or force-rewrite Git history (`reset --hard`, force-push, history rewriting) without
  explicit human approval.
- Silently change governance rules — this document, `docs/DECISION_LOG.md`,
  `docs/WORKFLOW_RULES`-equivalent content in `docs/milestones.md`/`docs/architecture.md`, or the
  `EngineConfig` schema — without recording the change and its rationale in
  `docs/DECISION_LOG.md`.
- Trust an agent's own summary of its work as evidence that the work is correct. Verify against
  the actual repository state (run the tests, read the diff, reproduce the claimed bug/fix)
  before accepting a claim.

## Review discipline (in active use since Milestone 2)

1. A task moves through: plan review → implementation → implementation review → remediation
   (repeat implementation review → remediation until approved) → governance closeout →
   governance review → push. Stage prompts follow the exact templates in
   `docs/milestone-2-plan.md`'s "Normative built-in templates" section (now generatable via
   `workflowctl prompt <stage>` once a target is governed by this tool — see
   `self-governance.yaml`).
2. **Every review round after the first uses a reviewer with no memory of prior rounds.** A
   reviewer who already knows "these N things were fixed" is anchored on that frame and
   structurally prone to missing anything new introduced by the fix itself. This caught a real
   regression during Milestone 2 (see `docs/DECISION_LOG.md`, 2026-07-16 entry).
3. A review's job is to reproduce claims, not restate them: run the tests, read the actual
   diff, and independently verify file-scope matches whatever the task's plan authorized before
   returning a verdict.
4. `APPROVED`/`REJECTED` verdicts are exactly one token, per the plan's normative template — no
   partial or hedged verdicts.

## Fresh-session recovery

See `docs/CONTEXT.md` for the exact read order a new session should follow to recover full
context from repository files alone, without relying on prior conversation history.
