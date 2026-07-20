# Handoff: ORCH-000 independent review (REJECTED)

## Summary

Independent review of `ORCH-000` (`VERIFIED` -> review), reviewer
`claude-code-independent-reviewer`, distinct from the implementer/HUMAN_OWNER
actor `claude-code-bootstrap` recorded for this candidate. All process
preconditions for review held (clean committed HEAD `46898ec`, stage
`VERIFIED`, complete `ImplementationEvidence`, vacuously-satisfied
prerequisites, independent reviewer identity), and every required
verification command reproduced the implementer's recorded results, several
byte-identically. The verdict is **`REVIEW_REJECTED`**, not because
verification failed, but because the reviewed diff itself violates
`ORCH-000`'s own stage scope and exposes a real specification gap that
`stages/ORCH-000.md`'s own Risks section names as grounds for rejection.

## Changed paths

- `docs/implementation/orchestration/reviews/ORCH-000/20260720T172520Z-claude-code-independent-reviewer-59f68d54.yaml` (created)
- `docs/implementation/orchestration/reviews/ORCH-000/logs/*` (created — 8 content-addressed rerun logs)
- `docs/implementation/orchestration/handoffs/ORCH-000/20260720T172520Z-claude-code-independent-reviewer-59f68d54.md` (this file, created)
- `docs/implementation/orchestration/implementation-state.yaml` (modified)

All paths are within `ORCH-000.md`'s own "Exact allowed files or
directories" (`reviews/ORCH-000/`, `handoffs/ORCH-000/`,
`implementation-state.yaml`). No file under `evidence/ORCH-000/` was created,
modified or deleted by this review — that directory's pre-existing contents
(from the reviewed implementation session) are exactly what finding F-1
flags as out of scope; this review does not repair them.

## Verification

All commands rerun from `/home/afshin-jian/ai-workflow-engine` at clean HEAD
`46898ec943e94d63f15a1ba33e2b0c05e82d6223`; full argv, stdout digests and
purposes are in the review evidence YAML's `commands` list.

| Check | Result |
|---|---|
| `git rev-parse HEAD` | `46898ec...` (current committed implementation-bookkeeping commit; differs from `stages.ORCH-000.implementation_commit` = `a676e0b`, which is correctly the *design-package* commit per DEC-2 — see review evidence `reviewed.note`) |
| `git status --porcelain -b` | clean |
| `git show --stat a676e0b` | byte-identical stdout digest to the implementer's recorded run — reproducible |
| `workflowctl verify --config self-governance.yaml --output json` | `PASS` |
| `pytest -q` | `684 passed`, exit 0 — matches recorded count exactly |
| Independent schema/DAG/link validator (freshly written, not reused) | `PASS`: 28 stages, delivery_order length 28, 28 plan rows, 28 stage files, no cycles, valid topology, `next_eligible_stage` recomputes to `ORCH-000` matching the recorded value |
| Changed-path scope vs. `ORCH-000.md`'s allowed-paths list | **FAIL** — 9 of 11 files changed by the reviewed commit (`46898ec`) are under `evidence/ORCH-000/`, which is not in `ORCH-000.md`'s "Exact allowed files or directories" |

No merge/rebase/cherry-pick/bisect was active. No orchestration feature lock
was found. No prior `ORCH-000` review existed before this one.

## Decisions

None — this is a review-only session; no repair was made to the reviewed
diff, `stages/ORCH-000.md`, or any other file outside the allowed review
paths.

## Schema and migrations

No schema change. No migration-registry change (`ORCH-000` owns no migration
entries).

## Risks

- **F-1** (HIGH, blocking) — the reviewed implementation session widened its
  own allowed-path scope to `evidence/ORCH-000/`, self-authorized via its own
  `DEC-1` rather than stopping for a reviewed plan amendment, contradicting
  `implementation-plan.md` section 1's explicit "no session may widen the
  stage's allowed paths" rule and `session-protocol.md` section 8's exact
  fail-closed stop for out-of-scope changed paths.
- **F-2** (HIGH, blocking) — `stages/ORCH-000.md` itself is internally
  ambiguous about whether/where ORCH-000 has an implementation-evidence
  phase, conflicting with the schema's universal VERIFIED-evidence
  requirement and the common stage contract. This is the exact "hidden
  lifecycle gap" the stage spec's own Risks section says requires rejection.
- **F-3** (LOW, non-blocking) — `stages/ORCH-000.md` says "25 deliverables";
  the committed package has 28 stages. Should be corrected alongside F-2's
  remediation.
- **R-APPROVAL-ISOLATION** (CRITICAL, carried forward, unaffected by this
  review) — unchanged; disposition remains ORCH-016/ORCH-017/ORCH-027.
- **R-GOVERNANCE-TRANSACTION** (CRITICAL, carried forward, unaffected) —
  unchanged; disposition remains ORCH-020/ORCH-027.
- **R-BOOTSTRAP-ROLE-OVERLAP** (MEDIUM, carried forward) — noted but not
  independently blocking; superseded in practical effect by F-1/F-2, which
  identify the more precise, actionable defect in the same session's output.

## Blockers

None added to the top-level (global) blocker list — `next_eligible_stage`
correctly remains `ORCH-000` rather than `null`, since a REMEDIATOR must
still act on this exact stage next. The rejection findings (F-1, F-2, F-3)
are the actionable record; see `remediation_scope` in the review evidence
YAML for exact required next steps.

## Durable state

`docs/implementation/orchestration/implementation-state.yaml` updated:

- `stages.ORCH-000.status`: `VERIFIED` -> `REVIEW_REJECTED`
- `stages.ORCH-000.review_status`: `PENDING` -> `REJECTED`
- `stages.ORCH-000.reviewer`: `null` -> `claude-code-independent-reviewer`
- `stages.ORCH-000.review_evidence`: `[]` -> `[reviews/ORCH-000/20260720T172520Z-claude-code-independent-reviewer-59f68d54.yaml]`
- `stages.ORCH-000.verification_status`: unchanged, `PASSED` (rerun commands
  did pass; the rejection is a scope/specification defect, not a command
  failure)
- `current_stage` / `next_eligible_stage` / `candidate_next_stage`: unchanged,
  `ORCH-000` (computed independently; matches recorded)
- `history`: one new entry appended (sequence 6): `REVIEWER`,
  `VERIFIED -> REVIEW_REJECTED`
- `last_updated`: refreshed to this session, role `REVIEWER`

## Next legal action

A **REMEDIATOR** session, distinct from both `claude-code-bootstrap` and this
reviewer (`claude-code-independent-reviewer`), must read this rejection
report and `docs/implementation/orchestration/prompts/remediate-rejected.md`,
then pursue the `remediation_scope` recorded in the review evidence YAML:
obtain an architect-reviewed plan amendment resolving F-1/F-2 (and correcting
F-3), then produce new implementation evidence/handoff for `ORCH-000` under
the amended, unambiguous scope. It may not alter this rejection finding or
approve its own fix. No `ORCH-001`+ stage is implementation-eligible until a
subsequent independent review records `ORCH-000` as `REVIEW_APPROVED`.

## Exact continuation prompt

Use `docs/implementation/orchestration/prompts/remediate-rejected.md`
verbatim, in a fresh session with no memory of this review session, working
in `/home/afshin-jian/ai-workflow-engine`.
