# AgentOS Workflow Automation — Human Authorization Model

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Human Authorization Model |
| **Purpose** | Defines the single human gate, the authorization binding, and every condition that invalidates it. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Documentation & Governance session (AUTO-001) · Human Owner (approval) |
| **Dependencies** | `WORKFLOW_STATES.md` §2-3 |
| **Related Documents** | `MACHINE_GATES.md`, `TARGET_REPOSITORY_MODEL.md`, `CLI_SPEC.md`, `FAILURE_RECOVERY.md` |

## Table of Contents
1. The Single Human Gate · 2. Authorization Binding · 3. Capture and Validation ·
4. Invalidation Conditions · 5. What Is Not a Human Gate · 6. Decision References ·
7. Open Questions · 8. Future Revisions

## 1. The Single Human Gate

The only human gate in this system is the `CREATED → AUTHORIZED` transition
(`WORKFLOW_STATES.md` §3), triggered by an explicit stage authorization command:

```
agentos workflow authorize <STAGE_ID>
```

After a valid authorization is captured and bound, every later transition is automatic and
controlled by machine gates (`MACHINE_GATES.md`). No other point in the workflow asks for or
accepts human approval. Models (`ClaudeCLIProvider`, `CodexCLIProvider`) never authorize
workflows and never bypass machine gates (`MODEL_PROVIDER_CONTRACTS.md` §1).

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

## 6. Decision References
DD-04.

## 7. Open Questions
OD-7 (safe re-authorization policy for baseline drift — deliberately undefined for now).

## 8. Future Revisions
Adding a bound field is additive (MINOR); removing or weakening a bound field, or adding any
second human-approval point, is a MAJOR change requiring explicit Human Owner sign-off, since it
changes the core safety property this program is built around.
