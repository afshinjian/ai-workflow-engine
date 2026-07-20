# Handoff: ORCH-000 remediation (stage-contract amendment)

## Summary

This REMEDIATOR session (`claude-code-remediator`), distinct from both the
rejected implementer (`claude-code-bootstrap`) and the rejecting reviewer
(`claude-code-independent-reviewer`), remediated the `REVIEW_REJECTED`
findings F-1 and F-2 (blocking) and F-3 (non-blocking) recorded in
`reviews/ORCH-000/20260720T172520Z-claude-code-independent-reviewer-59f68d54.yaml`.

The remediation is a **stage-contract amendment**, not a re-implementation of
the design-package review itself: `stages/ORCH-000.md`'s "Exact allowed files
or directories" and "Files expected to be created" sections previously
omitted `evidence/ORCH-000/`, while the schema's VERIFIED-evidence
requirement and `implementation-plan.md`'s common stage contract (section 2,
item 6) both required implementation evidence — a genuine internal
inconsistency with no fully legal route to `VERIFIED` (F-2). The prior
implementation session's own resolution of that gap (writing to
`evidence/ORCH-000/` on self-authored rationale, `DEC-1`) was correctly
rejected as an unauthorized scope widening (F-1).

This session amended `stages/ORCH-000.md` directly to add `evidence/ORCH-000/`
to its allowed paths and to add an explicit "Lifecycle" section naming the
full `NOT_STARTED`→`IN_PROGRESS`→`IMPLEMENTED`→`VERIFIED`→`REVIEW_APPROVED`/
`REVIEW_REJECTED` transition path and its four distinct evidence categories
(implementation, verification, independent review, handoff). It corrected
"25 deliverables" to 28 (F-3). It recorded the full rationale in
`decision-log.md` (`D3-016`), including an explicit admissibility ruling for
the retained bootstrap evidence. `implementation-plan.md`, `architecture-v3.md`,
`architecture_version` and `plan_version` are **unchanged**.

`ORCH-000` ends this session at **`VERIFIED`** (never `REVIEW_APPROVED`) with
`review_status: PENDING`. No production code, no `ORCH-001` work, and no
review verdict was touched by this session.

## Changed paths

All within `docs/implementation/orchestration/`:

- `docs/implementation/orchestration/stages/ORCH-000.md` (modified — the plan
  amendment resolving F-1/F-2/F-3)
- `docs/implementation/orchestration/decision-log.md` (modified — `D3-016`
  entry and detail recording the amendment's rationale)
- `docs/implementation/orchestration/implementation-state.yaml` (modified —
  `stages.ORCH-000` moved `REVIEW_REJECTED` → `VERIFIED`; history sequences
  7–9 appended; `R-REMEDIATION-AMENDMENT-UNREVIEWED` risk added;
  `last_updated` refreshed)
- `docs/implementation/orchestration/evidence/ORCH-000/20260720T181000Z-claude-code-remediator-e27efbe4.yaml`
  (created — this session's `ImplementationEvidence`, now legally located
  under the just-amended allowed-paths list)
- `docs/implementation/orchestration/evidence/ORCH-000/logs/*.txt`,
  `docs/implementation/orchestration/evidence/ORCH-000/logs/20260720T181000Z-claude-code-remediator-e27efbe4-workflowctl-verify.json`
  (created — 6 content-addressed command-log artifacts; `.txt`/`.json`, not
  `.log`, per the amended stage contract's gitignore note, see Risks; the
  `workflowctl-verify` output is implementation-ID-prefixed because the
  unprefixed name is already used by the retained bootstrap evidence — an
  earlier draft of this session briefly overwrote that file with an
  unprefixed rerun and it was restored via `git checkout` before this diff
  was finalized)
- `docs/implementation/orchestration/handoffs/ORCH-000/20260720T181000Z-claude-code-remediator-e27efbe4.md`
  (this file, created)

No file outside `docs/implementation/orchestration/` was created, modified,
or deleted. No production source code was touched. No `ORCH-001` file was
created or touched. `docs/implementation/orchestration/reviews/ORCH-000/` was
not touched — no review verdict was rendered or altered by this session.

## Verification

All commands run from `/home/afshin-jian/ai-workflow-engine` at the session's
starting clean HEAD `17111c781072260a51d08ba077fed8fba8b8dcd6` (the review-rejection
commit); exact argv, stdout digests, and purpose are recorded in the evidence
YAML's `commands` list and raw logs under `evidence/ORCH-000/logs/`.

| Check | Command | Result |
|---|---|---|
| Starting HEAD identity | `git rev-parse HEAD` | `17111c781072260a51d08ba077fed8fba8b8dcd6` |
| Dirty-state preflight | `git status --porcelain -b` | only this session's 3 modified governance files (`stages/ORCH-000.md`, `decision-log.md`, `implementation-state.yaml`); no untracked/staged files before evidence was written |
| Repository governance | `workflowctl verify --config self-governance.yaml --output json` | `status: PASS` (git/task-state/governance/handover all PASS) |
| Full regression | `pytest -q` | `684 passed`, exit 0 — matches both the bootstrap implementer's and the rejecting reviewer's recorded count exactly |
| Independent schema/DAG/link/semantic validator (freshly written for this session) | `PASS`: 28 stages, delivery_order length 28, 28 plan rows, 28 stage files, acyclic, valid topology, 9 contiguous history entries, `next_eligible_stage` recomputes to `ORCH-000`, `ORCH-000.status=VERIFIED`, `review_status=PENDING`, `evidence_count=2`, `review_evidence_count=1` |

No merge/rebase/cherry-pick/bisect was active. No orchestration feature lock
was found. No `ORCH-001` work exists in the repository.

## Decisions

1. **Amend `stages/ORCH-000.md` (not `implementation-plan.md` or
   `architecture-v3.md`).** The defect was local to the per-stage file's
   allowed-paths/expected-outputs sections; `implementation-plan.md`'s common
   stage contract already correctly required implementation evidence, so only
   the stage file needed to change. `architecture_version`/`plan_version`
   remain the schema-pinned constants `3.0.0`/`1.0.0`, unchanged.
2. **This amendment is authorized as a reviewed plan amendment under direct
   task instruction, not self-authorized rationale.** `stages/ORCH-000.md`
   and `decision-log.md` are governance/package-level documents, outside any
   single stage's own "exact allowed files" sandbox — exactly the kind of
   change `implementation-plan.md` section 1 gates behind "a reviewed plan
   amendment" rather than a normal implementer's unilateral in-scope write.
   Unlike the rejected `DEC-1` (an implementer inventing its own
   authorization mid-session), this amendment was made under explicit,
   separate instruction to remediate exactly this governance gap, is fully
   documented with rationale in `decision-log.md` `D3-016` before any new
   evidence was written, and does not confer approval on itself — see
   Decision 4.
3. **Existing bootstrap evidence
   (`evidence/ORCH-000/20260720T164147Z-claude-code-bootstrap-d24e29f6.yaml`
   and its logs) is retained and ratified as admissible, not superseded or
   deleted.** F-1/F-2 are scope/specification defects in *where* that
   evidence was permitted to live, not defects in its substance: the design
   package it verifies (`a676e0b`) is unchanged, and the rejecting reviewer
   already independently reran the same commands from a separate session,
   getting matching or byte-identical results
   (`verification_status: PASSED` survived the rejection). It is listed
   first in `stages.ORCH-000.evidence`, with this session's new evidence
   appended alongside it, not replacing it. Full rationale in `decision-log.md`
   `D3-016`.
4. **`ORCH-000` returns only to `VERIFIED`, never `REVIEW_APPROVED`.** This
   session rendered no review verdict and did not touch
   `reviews/ORCH-000/`. `review_status` was set to `PENDING` (matching the
   convention the bootstrap session used at `VERIFIED`, `DEC-6` in its own
   evidence), not `APPROVED`. A new `R-REMEDIATION-AMENDMENT-UNREVIEWED`
   risk was recorded specifically to flag that the amendment itself, not
   just the evidence, awaits independent review.
5. **`implementation_commit` set to `null`, not carried forward from the
   prior `a676e0b`.** This session's diff (the stage-contract amendment,
   decision-log entry, state update and new evidence/handoff) is a new,
   currently uncommitted implementation, unlike the bootstrap session's
   "already-committed, no new diff" special case (its own `DEC-2`). The
   general rule applies instead (`session-protocol.md` section 2):
   `implementation_commit` stays `null` until a human commits this diff; the
   next reviewer sets it to the clean HEAD it actually reviews.
6. **`stages.ORCH-000.expected_base_head` updated to this session's starting
   HEAD `17111c781072260a51d08ba077fed8fba8b8dcd6`** (the review-rejection
   commit), per `session-protocol.md` section 1.6 ("For an implementation
   start, record current HEAD as the selected stage's `expected_base_head`").
7. **Command-log artifacts use `.txt`/`.json`, not `.log`.** The repository
   root `.gitignore` excludes `*.log`; the 8 pre-existing logs under
   `evidence/ORCH-000/logs/` from the bootstrap/review sessions are already
   tracked (force-added at some point prior to this session) and were left
   untouched, but this session's own new command-log artifacts use
   non-ignored extensions so they can be added and committed normally,
   without depending on undocumented `git add -f` behavior. This is
   documented as an explicit note in the amended `stages/ORCH-000.md`
   allowed-paths section, scoped only to this stage's evidence directories —
   the root `.gitignore` itself was not modified, keeping this remediation's
   changes entirely within `docs/implementation/orchestration/`.
8. **`repository.expected_base_head` (top-level) left unchanged at
   `a676e0b`.** It was already one commit stale (behind `46898ec` and
   `17111c7`) before this session started; that staleness pre-dates this
   remediation, is not part of F-1/F-2/F-3, and fixing it is out of the
   scope this task authorized. Left unresolved and unremarked in state;
   noted here for transparency only.

## Schema and migrations

No schema change. No migration-registry change (`ORCH-000` owns no migration
entries). `implementation-state.schema.yaml` was used unmodified as the
validation target; `architecture_version` and `plan_version` are unchanged.

## Risks

- **F-1, F-2 (HIGH, blocking)** — remediated by the `stages/ORCH-000.md`
  amendment (`decision-log.md` `D3-016`). Not independently re-reviewed yet.
- **F-3 (LOW, non-blocking)** — "25 deliverables" corrected to 28.
- **R-REMEDIATION-AMENDMENT-UNREVIEWED (MEDIUM, new)** — the amendment
  authored by this session has not yet been independently reviewed; the next
  reviewer must assess both the amendment and this session's evidence.
- **R-BOOTSTRAP-ROLE-OVERLAP (MEDIUM, carried forward, unaffected)** —
  unchanged; still a flag for the next reviewer.
- **R-APPROVAL-ISOLATION (CRITICAL, carried forward, unaffected)** —
  unchanged; disposition remains `ORCH-016`/`ORCH-017`/`ORCH-027`.
- **R-GOVERNANCE-TRANSACTION (CRITICAL, carried forward, unaffected)** —
  unchanged; disposition remains `ORCH-020`/`ORCH-027`.

## Blockers

None. The top-level `blockers` list remains `[]`.

## Durable state

`docs/implementation/orchestration/implementation-state.yaml` updated:

- `stages.ORCH-000.status`: `REVIEW_REJECTED` → `VERIFIED`
- `stages.ORCH-000.expected_base_head`: `a676e0b...` → `17111c781072260a51d08ba077fed8fba8b8dcd6`
- `stages.ORCH-000.implementation_commit`: `a676e0b...` → `null`
- `stages.ORCH-000.implementer`: `claude-code-bootstrap` → `claude-code-remediator`
- `stages.ORCH-000.review_status`: `REJECTED` → `PENDING`
- `stages.ORCH-000.reviewer`: unchanged, `claude-code-independent-reviewer` (historical record of the last review action; the next reviewer must still differ from this actor)
- `stages.ORCH-000.verification_status`: unchanged, `PASSED`
- `stages.ORCH-000.evidence`: `[bootstrap-evidence]` → `[bootstrap-evidence, this-session-evidence]` (retained, not replaced)
- `stages.ORCH-000.review_evidence`: unchanged, `[rejection-review-evidence]` (retained, not erased)
- `stages.ORCH-000.handoff`: `handoffs/ORCH-000/20260720T164147Z-...` → `handoffs/ORCH-000/20260720T181000Z-claude-code-remediator-e27efbe4.md` (this file)
- `unresolved_risks`: `R-REMEDIATION-AMENDMENT-UNREVIEWED` appended
- `history`: 3 new entries appended (sequence 7–9): `REVIEW_REJECTED → IN_PROGRESS`, `IN_PROGRESS → IMPLEMENTED`, `IMPLEMENTED → VERIFIED`, all role `REMEDIATOR`, actor `claude-code-remediator`
- `last_updated`: refreshed to this session, role `REMEDIATOR`
- `current_stage` / `next_eligible_stage` / `candidate_next_stage`: unchanged, `ORCH-000` (recomputed independently; matches recorded — no `ORCH-001`+ stage is eligible)

## Next legal action

An **independent `ORCH-000` review**, run by a session/actor different from
**all three** prior actors on this candidate: `claude-code-bootstrap`
(original implementer), `claude-code-independent-reviewer` (rejecting
reviewer), and `claude-code-remediator` (this session). That reviewer must:
require the clean committed remediation diff, re-run every verification
command listed above from scratch, assess whether the `stages/ORCH-000.md`
amendment itself correctly and minimally resolves F-1/F-2/F-3 (not just
whether this session's evidence reproduces), inspect the full
architecture/plan package per `stages/ORCH-000.md`'s "Independent review
checklist," and then alone record `REVIEW_APPROVED` or `REVIEW_REJECTED` at
`reviews/ORCH-000/<review-id>.yaml`. No `ORCH-001`+ stage is
implementation-eligible until that review records `REVIEW_APPROVED`. This
remediation session may not, and did not, render or alter any review
verdict.

## Exact continuation prompt

Use `docs/implementation/orchestration/prompts/review-current.md` verbatim,
in a fresh session with no memory of this remediation session or either
prior ORCH-000 session, working in `/home/afshin-jian/ai-workflow-engine`.
The reviewer must independently confirm reviewer-identity independence from
`claude-code-bootstrap`, `claude-code-independent-reviewer`, and
`claude-code-remediator` before proceeding.
