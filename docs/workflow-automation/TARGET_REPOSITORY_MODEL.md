# AgentOS Workflow Automation — Target Repository Model

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Target Repository Model |
| **Purpose** | Distinguishes the workflow engine's own repository from the repositories it automates, and binds baseline-branch configuration per target. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Documentation & Governance session (AUTO-001) · Human Owner (approval) |
| **Dependencies** | `CONFIGURATION_MODEL.md` |
| **Related Documents** | `HUMAN_AUTHORIZATION_MODEL.md` §2, `SECURITY_MODEL.md` §6 |

## Table of Contents
1. Two Repository Roles · 2. Engine Repository · 3. Target Repositories · 4. Baseline Branch
Binding · 5. Multiple Targets · 6. Decision References · 7. Open Questions · 8. Future
Revisions

## 1. Two Repository Roles

This program deliberately separates two roles that must never be conflated:

- The **workflow engine repository** (`ai-workflow-engine`) — where AUTO's own code and
  documentation live, built by ordinary AUTO-00x tasks under this repository's own
  `docs/TASK_QUEUE.md` self-governance.
- **Target repositories** — the (potentially many, though MVP allows one active at a time)
  separate repositories whose stages the engine automates once authorized.

The engine never assumes a target repository resembles `ai-workflow-engine` structurally,
governance-wise, or in its choice of baseline branch.

## 2. Engine Repository

- Name: `ai-workflow-engine`.
- Baseline branch: `main`.
- Governed by `self-governance.yaml`, `docs/TASK_QUEUE.md`, and `workflowctl` — entirely
  separate machinery from the workflow engine this program builds.
- `main` here is a fact about this one repository, never a default value baked into the
  workflow engine's logic (`CONFIGURATION_MODEL.md` §1).

## 3. Target Repositories

Each target repository defines its own configuration (`CONFIGURATION_MODEL.md` §3), including
its own:

- Baseline branch — may be `main`, `recovery/project-baseline`, or any other explicitly
  configured protected branch.
- Remote name, stage contract directory, test/lint/format/security commands, required GitHub
  checks, and every other per-target field.

The engine reads this configuration at precondition-check time for every workflow; it never
falls back to `main` (or any other value) when a target's `baseline_branch` is unset — an unset
baseline branch is a configuration error, refused before any target-repository mutation.

## 4. Baseline Branch Binding

The baseline branch is bound into every authorization (`HUMAN_AUTHORIZATION_MODEL.md` §2,
field 6) and re-verified at multiple points:

- At precondition-check time (`verify_baseline_ancestry`).
- Before merge (the pull request's base must be the bound baseline branch).
- At closeout (`checkout_baseline`, `fast_forward_pull` both operate against the bound baseline
  branch, never an assumed one).

If the configured baseline branch for a target repository changes between authorization and
execution, the authorization is invalidated (`HUMAN_AUTHORIZATION_MODEL.md` §4).

## 5. Multiple Targets

The MVP allows automating multiple distinct target repositories, each with its own
configuration, state directory, and audit directory — but only **one active workflow per
target repository** at a time (`ARCHITECTURE.md` §5, `MVP_SCOPE.md`). There is no cross-target
shared state; a lock or failure in one target repository never affects another.

## 6. Decision References
DD-02.

## 7. Open Questions
None blocking AUTO-001.

## 8. Future Revisions
Any change that would introduce a global default baseline branch, or that would let the engine
infer a baseline branch without explicit target configuration, is prohibited by this document
and would require rewriting it, not extending it.
