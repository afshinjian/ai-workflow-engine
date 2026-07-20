# ORCH-000 — Independent v3 design review

## Objective

Independently accept or reject the complete v3 design package.

## Reason it must occur at this point

Prerequisites are none. Its contracts must be independently accepted before any dependent stage.

## Prerequisites

Every listed stage (none) must be REVIEW_APPROVED, with committed review evidence. The repository/state preflight in session-protocol.md must pass.

## Lifecycle

Unlike every other stage, ORCH-000 reviews an already-committed design
package rather than implementing new production code, but it still follows
the full common-stage-contract lifecycle and is not exempt from the schema's
implementation-evidence requirement:

`NOT_STARTED` → `IN_PROGRESS` → `IMPLEMENTED` → `VERIFIED` → `REVIEW_APPROVED`
or `REVIEW_REJECTED`.

An implementer (or, after a rejection, a REMEDIATOR per session-protocol.md
section 6) advances `NOT_STARTED`/`REVIEW_REJECTED` through `IN_PROGRESS` and
`IMPLEMENTED` to `VERIFIED` by independently reproducing the verification
commands below against the committed design package and writing
implementation evidence. Only an independent reviewer, in a later session,
advances `VERIFIED` to `REVIEW_APPROVED` or `REVIEW_REJECTED` by writing
review evidence. These are four distinct evidence/artifact categories, each
with its own path and required content:

- **Implementation evidence** — proves the design package was inspected and
  the verification commands below were run once, independently, before
  `VERIFIED`. Lives under `evidence/ORCH-000/<implementation-id>.yaml`
  (`ImplementationEvidence` 1.0.0, per session-protocol.md section 7), plus
  any referenced command-log artifacts under
  `evidence/ORCH-000/logs/<name>.<ext>` (see the note on log-file extensions
  below).
- **Verification evidence** — the exact command argv, exit codes and
  stdout/stderr digests for the verification commands, referenced from
  implementation evidence (or review evidence) rather than duplicated; may be
  embedded inline or stored as the same `evidence/ORCH-000/logs/` artifacts.
- **Independent review evidence** — proves a distinct reviewer session
  reproduced the verification and rendered a verdict. Lives under
  `reviews/ORCH-000/<review-id>.yaml` (`ReviewEvidence` 1.0.0).
- **Handoff artifacts** — the human-readable record of what a session did,
  for both implementation/remediation and review sessions. Live under
  `handoffs/ORCH-000/<session-id>.md` (`HandoffRecord` 1.0.0).

## Exact allowed files or directories

docs/implementation/orchestration/evidence/ORCH-000/, docs/implementation/orchestration/reviews/ORCH-000/, docs/implementation/orchestration/handoffs/ORCH-000/, implementation-state.yaml.

Command-log artifacts under `evidence/ORCH-000/logs/` and `reviews/ORCH-000/logs/`
must not use a `.log` extension, since the repository's root `.gitignore`
excludes `*.log` and this stage's evidence must be versioned, not force-added.
Use `.txt` (plain stdout capture) or a structured extension such as `.json`
instead.

## Files expected to be created

Implementation evidence YAML and its referenced command-log artifacts under
`evidence/ORCH-000/`; an implementation (or remediation) handoff under
`handoffs/ORCH-000/`; review YAML under `reviews/ORCH-000/`; an optional
rejection handoff under `handoffs/ORCH-000/`.

## Files expected to be modified

implementation-state.yaml.

## Public interfaces added or changed

No production interface.

## Schemas added or changed

implementation-state 1.0.0.

## Migrations required

Only migrations explicitly owned by this stage in migration-registry.yaml may change; otherwise none. Migration apply to the real repository requires a separate authorized migration session.

## Invariants introduced

No self-review; all 28 deliverables and every blocker trace to a mechanism/stage.

## Tests required

Focused unit, negative and fault/concurrency tests for every invariant, plus affected existing tests and the full regression suite. Tests use isolated temporary repositories/data roots and must not mutate real governance.

## Verification commands

Run independently and record exact argv, output digest and exit status: state/schema/DAG/link checks and pytest -q.

## Acceptance criteria

All specified tests pass; all changed paths are allowed; schemas/interfaces match Architecture v3; evidence and handoff are complete; no unresolved blocker remains; an independent reviewer can reproduce the result.

## Non-goals

No source, migration, task promotion or runtime change.

## Rollback strategy

Revert review/state; design revisions increment version and repeat 000.

## Independent review checklist

Architecture authority, recovery, signature/commit circularity, stage completeness. The reviewer must differ from implementation/remediation actors and rerun every verification command from the committed implementation HEAD.

## Risks

A hidden lifecycle gap requires rejection. (Resolved by a reviewed
remediation on 2026-07-20: this stage's own allowed-paths and lifecycle
sections previously omitted an implementation-evidence phase, which
contradicted the schema's VERIFIED-evidence requirement and
implementation-plan.md's common stage contract; see decision-log.md and
`reviews/ORCH-000/` for the rejection that identified the gap and the
remediation that closed it. This amendment itself remains subject to
independent re-review before ORCH-000 may reach REVIEW_APPROVED.)

## Handoff state written for the next session

Add immutable evidence/<stage>/<implementation-id>.yaml and handoffs/<stage>/<implementation-id>.md with exact files, commands/results, decisions, risks, blockers, schema/migration changes and next legal action. Update implementation-state.yaml only through session-protocol transitions. Implementation stops at VERIFIED; review alone records REVIEW_APPROVED or REVIEW_REJECTED. Never start the next stage in the same session.

