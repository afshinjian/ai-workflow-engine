# Handoff: ORCH-000 governance amendment (ARCHITECT/HUMAN_OWNER)

## Summary

Acting in role ARCHITECT/HUMAN_OWNER (actor `claude-code-architect-1`,
distinct from `claude-code-bootstrap`, `claude-code-independent-reviewer`,
`claude-code-remediator`, and `claude-code-independent-reviewer-2`), this
session resolves findings F-4, F-5, F-6 (HIGH, blocking) and F-7 (LOW,
non-blocking) from the second independent rejection of ORCH-000
(`reviews/ORCH-000/20260720T194000Z-claude-code-independent-reviewer-2-b7e21ac4.yaml`).

It does **not** implement production code, does **not** approve or advance
ORCH-000's review disposition, and does **not** commit or push. ORCH-000
remains `REVIEW_REJECTED`; ORCH-001 remains `NOT_STARTED` and ineligible.

The amendment:

1. Adds a standing ARCHITECT/HUMAN_OWNER governance-amendment-authorization
   procedure to `session-protocol.md` (resolves F-4's structural gap for
   future findings, not only this one).
2. Adds `decision-log.md` entry D3-017, which durably records this
   authorization (in `implementation-state.yaml` history, sequence 11),
   ratifies D3-016's stage-contract text unchanged, and increments
   `plan_version` 1.0.0 → 1.1.0 per `decision-log.md`'s own header
   requirement (resolves F-5).
3. Adds a one-line pointer to `stages/ORCH-000.md` clarifying that
   stage-contract/decision-log amendments are authorized only through the
   session-protocol.md procedure, never through the stage's own
   allowed-paths list — which is **not** widened (resolves F-6).
4. Delegates F-7's mechanical fix (re-capturing and committing the first
   rejection review's missing `.log`-referenced artifacts) to the next
   REMEDIATOR session, since it requires no contract amendment.

## Changed paths

- `docs/implementation/orchestration/session-protocol.md`
- `docs/implementation/orchestration/decision-log.md`
- `docs/implementation/orchestration/implementation-plan.md` (version header line only)
- `docs/implementation/orchestration/implementation-state.schema.yaml` (`plan_version` const only)
- `docs/implementation/orchestration/implementation-state.yaml`
- `docs/implementation/orchestration/stages/ORCH-000.md` (allowed-paths note + Risks-section note only)
- `docs/implementation/orchestration/evidence/ORCH-000/20260720T201500Z-claude-code-architect-1-f7bef021.yaml` (new)
- `docs/implementation/orchestration/evidence/ORCH-000/logs/20260720T201500Z-claude-code-architect-1-f7bef021-*.{txt,json}` (new, 8 files)
- `docs/implementation/orchestration/handoffs/ORCH-000/20260720T201500Z-claude-code-architect-1-f7bef021.md` (this file)

No production source and no other stage file changed.

## Verification

Run independently before and after the edits, at starting/ending HEAD
`7443ce060faa30e5baaa4e2f4bc2673198366927` (this session leaves an
uncommitted diff; HEAD does not advance):

| Command | Before | After |
|---|---|---|
| `git status --porcelain -b` | clean | only declared paths modified/untracked |
| `workflowctl verify --config self-governance.yaml --output json` | PASS | PASS |
| `pytest -q` | 684 passed, 0 failed, 0 skipped | 684 passed, 0 failed, 0 skipped |
| freshly written state/schema/DAG validator | STRUCTURAL PASS (plan_version 1.0.0) | STRUCTURAL PASS (plan_version 1.1.0, matches schema const) |

Exact argv, exit codes and stdout digests are recorded in
`evidence/ORCH-000/20260720T201500Z-claude-code-architect-1-f7bef021.yaml`.

## Decisions

See `evidence/ORCH-000/20260720T201500Z-claude-code-architect-1-f7bef021.yaml`
`decisions` (DEC-A1..DEC-A5) and `decision-log.md` D3-017 for full rationale:
ratify D3-016's text unchanged; do not widen ORCH-000's allowed-paths list;
increment `plan_version` not `architecture_version`; delegate F-7's
mechanical fix; record a blocker rather than a status change.

## Schema and migrations

`implementation-state.schema.yaml`'s `plan_version` const changes from
`1.0.0` to `1.1.0`, in lockstep with `implementation-state.yaml`'s
`plan_version` and `schema_versions.plan` fields, and
`implementation-plan.md`'s version header. `architecture_version` (3.0.0)
and `implementation-state` schema_version (1.0.0) are unchanged. No
migrations required or affected.

## Risks

`R-REMEDIATION-AMENDMENT-UNREVIEWED` is resolved by this session (see
`implementation-state.yaml` `unresolved_risks` for the updated
disposition). `R-BOOTSTRAP-ROLE-OVERLAP`, `R-APPROVAL-ISOLATION`, and
`R-GOVERNANCE-TRANSACTION` are carried forward unchanged; none is affected
by this amendment.

## Blockers

Added `GOVERNANCE_AMENDMENT_PENDING_REMEDIATION` to
`stages.ORCH-000.blockers` (`implementation-state.yaml`): unresolved until
a REMEDIATOR session completes the delegated F-7 fix and returns ORCH-000
to `VERIFIED`.

## Durable state

- `stages.ORCH-000.status`: unchanged, `REVIEW_REJECTED`.
- `stages.ORCH-000.review_status`: unchanged, `REJECTED`.
- `implementation-state.yaml` `history`: new sequence 11
  (`AUTHORIZED_GOVERNANCE_AMENDMENT_ORCH_000`, role `HUMAN_OWNER`, actor
  `claude-code-architect-1`, `from`/`to` both `REVIEW_REJECTED` — no stage
  transition occurred).
- `plan_version`: `1.0.0` → `1.1.0`. `architecture_version`: unchanged, `3.0.0`.
- `next_eligible_stage` / `candidate_next_stage`: unchanged, `ORCH-000`.
- `ORCH-001`: unchanged, `NOT_STARTED`, ineligible (prerequisite `ORCH-000`
  not `REVIEW_APPROVED`).

## Next legal action

A REMEDIATOR session, distinct from all five actors recorded against
ORCH-000 (`claude-code-bootstrap`, `claude-code-independent-reviewer`,
`claude-code-remediator`, `claude-code-independent-reviewer-2`,
`claude-code-architect-1`), reads this handoff, `decision-log.md` D3-017,
and this session's evidence, then:

1. Confirms this diff is committed and current HEAD matches it.
2. Within `evidence/ORCH-000/` and `reviews/ORCH-000/` only: re-runs the
   commands referenced by
   `reviews/ORCH-000/20260720T172520Z-claude-code-independent-reviewer-59f68d54.yaml`
   whose `stdout_artifact` paths use a `.log` extension and were never
   committed; captures output under `.txt`/`.json`; commits them — without
   altering that review's recorded verdict or findings text (resolves F-7).
3. Writes new implementation evidence and a handoff; returns ORCH-000
   through `IN_PROGRESS`/`IMPLEMENTED` to `VERIFIED`.
4. Stops for the next independent review. Does not touch
   `session-protocol.md`, `decision-log.md`, `implementation-plan.md`,
   `implementation-state.schema.yaml`, or `stages/ORCH-000.md` — those are
   settled by this amendment. Does not start ORCH-001.

## Exact continuation prompt

```
Work in /home/afshin-jian/ai-workflow-engine. Do not rely on chat history.
Read README.md, self-governance.yaml, docs/AGENT_PROTOCOL.md, this
package's session-protocol.md, decision-log.md (especially D3-017),
implementation-state.yaml, stages/ORCH-000.md, this handoff and its
evidence record. Confirm the ARCHITECT/HUMAN_OWNER amendment diff (history
sequence 11, evidence
20260720T201500Z-claude-code-architect-1-f7bef021.yaml) is committed and
current HEAD matches it. Act as REMEDIATOR: within evidence/ORCH-000/ and
reviews/ORCH-000/ only, recapture and commit the F-7 evidence-log
artifacts referenced by
reviews/ORCH-000/20260720T172520Z-claude-code-independent-reviewer-59f68d54.yaml
under .txt/.json extensions, without altering that review's verdict or
findings text. Write new implementation evidence and a handoff. Return
ORCH-000 through IN_PROGRESS/IMPLEMENTED to VERIFIED. Do not touch
session-protocol.md, decision-log.md, implementation-plan.md,
implementation-state.schema.yaml, or stages/ORCH-000.md. Do not approve,
commit, push, or start ORCH-001.
```
