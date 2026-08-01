# AgentOS Workflow Automation — Human Authorization Model

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Human Authorization Model |
| **Purpose** | Defines the founding human gate, the authorization binding, every condition that invalidates it, and the conditions under which a later workflow mode may add a configurable approval gate. |
| **Status** | Draft |
| **Version** | 2.0 |
| **Owner** | Documentation & Governance session (AUTO-001) · Human Owner (approval) |
| **Dependencies** | `WORKFLOW_STATES.md` §2-3 |
| **Related Documents** | `MACHINE_GATES.md`, `TARGET_REPOSITORY_MODEL.md`, `CLI_SPEC.md`, `FAILURE_RECOVERY.md` |

## Table of Contents
1. The Founding Human Gate · 2. Authorization Binding · 3. Capture and Validation ·
4. Invalidation Conditions · 5. What Is Not a Human Gate ·
5a. Configurable Approval Gates (Human Owner decision, 2026-08-01) · 6. Decision References ·
7. Open Questions · 8. Future Revisions

## 1. The Founding Human Gate

**Amended 2026-08-01 (v2.0).** Through v1.1 this section read "the *only* human gate in this
system". That is no longer accurate and is superseded by §5a: the `CREATED → AUTHORIZED` gate
remains the *founding* gate — the one without which no workflow may begin, and the one every
binding in §2 attaches to — but a later workflow mode may now additionally define configurable
approval gates governed by `ApprovalService`. §5a states exactly what that permits and, more
importantly, what it does not.

The founding human gate is the `CREATED → AUTHORIZED` transition
(`WORKFLOW_STATES.md` §3), triggered by an explicit stage authorization command:

```
agentos workflow authorize <STAGE_ID>
```

After a valid authorization is captured and bound, every later transition is automatic and
controlled by machine gates (`MACHINE_GATES.md`), **except** where a mode explicitly defines an
approval gate under §5a. Models (`ClaudeCLIProvider`, `CodexCLIProvider`) never authorize
workflows and never bypass machine gates (`MODEL_PROVIDER_CONTRACTS.md` §1); that is unchanged and
§5a does not weaken it.

**Scope.** This entire document — every binding field in §2 and every invalidation condition in
§4 — governs only the runtime machine above: one execution of the *finished* engine against an
authorized *target repository's* stage. It is never authority for this repository's own AUTO-00x
development-stage lifecycle (building the engine itself), which `STAGE_REGISTRY.md` and the
Standard Stage Protocol govern exclusively; see that document's §1.

## 2. Authorization Binding

Every authorization is bound to all of the following, captured at authorization time:

1. Repository identity (of the target repository).
2. Target repository path.
3. Stage identifier.
4. Stage contract path.
5. Stage contract hash (`calculate_contract_hash`).
6. Configured baseline branch (`TARGET_REPOSITORY_MODEL.md`).
7. Baseline commit SHA at authorization time.
8. Planned stage branch name.
9. Authorization timestamp.
10. Authorizing human identity, when available.
11. Workflow engine version.

If **any** bound value changes before implementation starts, the authorization becomes invalid
and the workflow moves to `FAILED` — it must be re-authorized from `CREATED`, never silently
re-bound (§4).

## 3. Capture and Validation

- Only the Orchestrator captures and validates an authorization record; the CLI is a thin
  front-end that forwards the operator's command and reads back the result
  (`ARCHITECTURE.md` §2).
- Validation is performed **only by the Orchestrator** — no Agent, Skill, or Model Provider
  participates in deciding whether an authorization is valid.
- Capturing an authorization is itself an audited event (`AUDIT_MODEL.md`).

## 4. Invalidation Conditions

An authorization is invalid, and the workflow must not proceed (or must move to `FAILED` if
already in progress), when any of the following hold:

- Repository identity cannot be verified.
- The stage contract changes (its hash no longer matches the bound value) after authorization.
- The authorized baseline commit SHA no longer matches the live baseline branch — **unless** an
  explicit safe-reauthorization policy is defined later (`OPEN_QUESTIONS.md` OD-7); until then,
  this is always a hard stop.
- The configured baseline branch for the target repository has changed since authorization.
- The planned stage branch already exists with unexpected history (not created by this
  workflow from the expected base).
- The workflow engine version bound at authorization no longer matches the running engine
  version, when that mismatch is judged relevant (exact policy: AUTO-002).

## 5. What Is Not a Human Gate

- **Cancellation** (`WORKFLOW_STATES.md` §3) only withdraws permission to continue; it never
  grants permission to proceed, so it is not a second authorization point.
- **Automatic repair** (`FAILURE_RECOVERY.md`) is machine-gated, bounded, and re-runs the same
  deterministic validation and independent QA every time — it never asks for or requires human
  approval.
- **Enabling automatic merge** is a machine gate, not a human approval — it fires only after
  every required deterministic and QA gate has passed (`MACHINE_GATES.md` §5).

## 5a. Configurable Approval Gates (Human Owner decision, 2026-08-01)

**Decision.** The Human Owner authorizes future workflow modes to define **configurable approval
gates**, governed exclusively by the `ApprovalService` subsystem delivered in AUTO-012. This is the
MAJOR change §8 requires explicit sign-off for, and this section is that sign-off.

**What is authorized.** The *subsystem* — a typed approval policy, its four-layer resolution, an
immutable resolved snapshot, durable append-only approval records, manual decisions, deadline-driven
timeout decisions, checksum binding, and invalidation. Nothing else.

**What is not authorized.** No specific Preparation, Reviewer, or Implementer workflow, and no
successor stage. A mode that wishes to place an approval gate at a particular point in its own
lifecycle requires its own separate authorization naming that mode and that point; this decision
grants the mechanism, never a placement.

**Constraints this decision does not relax.** All of the following remain exactly as they were, and
an approval gate that violated any of them would be outside this authorization:

1. The founding `CREATED → AUTHORIZED` gate (§1) is unchanged, and every binding in §2 and every
   invalidation condition in §4 still applies to it in full. An approval gate is additional to it,
   never a substitute for it, and never a way to reach `AUTHORIZED`.
2. An approval is **evidence, not authority** (`AGENT_CONTRACTS.md` §1, `ARCHITECTURE.md` §6). It
   never causes a transition by itself; the Orchestrator decides, exactly as before.
3. An approval **never** substitutes for a deterministic machine gate (`MACHINE_GATES.md`). A gate
   that fails still fails with an approval in hand. There is no admin bypass and no override path
   (`SECURITY_MODEL.md` §4), and this decision creates none.
4. Every approval is **bound to the state it was granted against** — repository state, diff,
   canonical agent result, and deterministic gate result — and is invalidated if any of those
   change before it is consumed. This mirrors §4's rule for the founding authorization: permission
   attaches to a specific state of the world, never to a workflow in the abstract.
5. An approval is **single-use**. Once consumed it cannot be consumed again, and it cannot be
   replayed for a different workflow or a different gate.
6. **Automatic approval is opt-in at the point of use.** A timeout action of `AUTO_APPROVE` is
   valid only when selected by the specific gate or by an explicit per-run override; it is refused
   when inherited from a built-in or project-wide default. Permission is never acquired by
   inheritance.
7. No Model Provider, Agent, or Skill may grant, decide, extend, or consume an approval.

**Auditability.** Every approval event is durably persisted, append-only, in per-workflow
confinement, with no record ever rewritten — the same discipline and the same code path as the
transition history (`AUDIT_MODEL.md` §8: audit completeness is a safety property). An automatic
decision records that it was automatic and which timeout action produced it, so an approval granted
without a human is never indistinguishable from one granted with a human.

**Basis.** AUTO-012 stage authorization, 2026-08-01; `docs/DECISION_LOG.md`, entry of the same date.

## 6. Decision References
DD-04. The §5a configurable-approval-gate decision (2026-08-01) is recorded in
`docs/DECISION_LOG.md` and in `docs/workflow-automation/STAGE_REGISTRY.md` §5.

## 7. Open Questions
OD-7 (safe re-authorization policy for baseline drift — deliberately undefined for now).

## 8. Future Revisions
Adding a bound field is additive (MINOR); removing or weakening a bound field, or adding any
second human-approval point, is a MAJOR change requiring explicit Human Owner sign-off, since it
changes the core safety property this program is built around.

v2.0 is exactly such a MAJOR change: §5a admits configurable approval gates, which is a second
human-approval point. It was made with the explicit Human Owner sign-off this section requires, and
it authorizes the mechanism only. **Placing** an approval gate at any particular point in any
particular mode remains a further MAJOR change needing its own sign-off, as does weakening any of
§5a's seven constraints.
