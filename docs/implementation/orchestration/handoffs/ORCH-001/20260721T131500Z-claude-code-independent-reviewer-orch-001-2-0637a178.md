# Handoff: ORCH-001 review — Durable feature-state validator (REVIEWER, REJECTED — F-3)

## Summary

Acting in role REVIEWER (actor `claude-code-independent-reviewer-orch-001-2`,
distinct from `claude-code-implementer-1`,
`claude-code-independent-reviewer-orch-001-1`, and
`claude-code-remediator-orch-001-1`), this session independently reviews
ORCH-001's remediated implementation at committed HEAD
`f89be9b3178794515a25d7f0d504946114b6b821` ("fix: remediate ORCH-001 blocked
resume validation"), per `stages/ORCH-001.md`'s "Independent review
checklist" and `session-protocol.md` section 5.

**Verdict: REJECTED (new finding F-3; F-1/F-2 confirmed fixed).**

This is the second independent review of ORCH-001. The first review
(`claude-code-independent-reviewer-orch-001-1`) rejected the original
implementation on F-1 (HIGH) and F-2 (MEDIUM). A REMEDIATOR
(`claude-code-remediator-orch-001-1`) fixed both. This session confirms that
fix is sound, then finds a separate, new blocking defect while checking the
fix's downstream consequences.

**F-1/F-2 — confirmed fixed, not re-litigated.** Reruns of every
stage-required verification command reproduced the remediator's recorded
results exactly (74/74 focused tests, 758/758 full suite, validator
`validate` PASS with a byte-identical `state_digest`, `workflowctl verify`
PASS), the changed-path scope is clean (25 changed paths, all within
ORCH-001's allowed paths), and line-by-line diff inspection confirms the fix
is a single additive hunk (28 lines, 0 deletions) that correctly implements
`session-protocol.md` section 2's `BLOCKED -> IN_PROGRESS` row without
touching `LEGAL_TRANSITIONS`, `check_transition_legal`, `validate_semantics`,
or the CAS-guard/atomic-write path. A fresh, methodologically distinct
adversarial fixture (drives the CLI `transition`/`validate` subcommands
end-to-end via `subprocess`, rather than calling `apply_transition`
in-process like both prior probes) independently reproduces all three
required scenarios.

**F-3 (HIGH, new, blocking).** While independently verifying the consequence
of the `ORCH-001 -> REVIEW_APPROVED` transition this stage's own review
process exists to reach — recomputing `next_eligible_stage`, exactly as
`apply_transition` and the CLI `transition` subcommand both do — this review
found that
`tests/test_orchestration_feature_state.py::TestRealRepositoryState::test_committed_state_next_eligible_stage_is_orch_001`
hard-codes the live governance document's `next_eligible_stage` as the
literal string `"ORCH-001"`, a transient fact rather than a durable
invariant. Driving the real `transition` CLI subcommand (not a hand-edit)
against a throwaway copy of the real committed state file confirms
`recompute_next_eligible` deterministically returns `"ORCH-002"` once
ORCH-001 is `REVIEW_APPROVED` — correctly, since `ORCH-002`'s sole
prerequisite is then satisfied — which this pinned test asserts must never
happen. Because `ORCH-002`'s own allowed paths (`stages/ORCH-002.md`) exclude
`tests/test_orchestration_feature_state.py`, and `REVIEW_APPROVED` is
immutable except by a reviewed plan amendment (`session-protocol.md` section
2), **no future session would have authority to fix this test once ORCH-001
becomes `REVIEW_APPROVED`.** Only a REMEDIATOR acting now, before approval,
has both the authority (ORCH-001's own allowed paths) and the opportunity.
Left unfixed, every subsequent session's required full `pytest -q` run
across the rest of the ORCH delivery pipeline (`ORCH-002` through `ORCH-027`)
would show one permanently, spuriously failing test — including
`ORCH-002`'s own stage-required verification command.

ORCH-001 is therefore returned to `REVIEW_REJECTED` on F-3 alone. F-1 and F-2
are not re-litigated and remain confirmed fixed.

## Changed paths

- `docs/implementation/orchestration/reviews/ORCH-001/20260721T131500Z-claude-code-independent-reviewer-orch-001-2-0637a178.yaml` (new)
- `docs/implementation/orchestration/reviews/ORCH-001/logs/20260721T131500Z-claude-code-independent-reviewer-orch-001-2-0637a178-*` (new, 12 files: environment fingerprint, git rev-parse/status/diff-stat/diff-script-patch, out-of-scope-check, pytest focused/full, validate, workflowctl verify, adversarial CLI probe script + output, F-3 pinned-test-failure capture)
- `docs/implementation/orchestration/handoffs/ORCH-001/20260721T131500Z-claude-code-independent-reviewer-orch-001-2-0637a178.md` (this file)
- `docs/implementation/orchestration/implementation-state.yaml` (modified: ORCH-001 stage entry, `unresolved_risks`, history, `last_updated`; `next_eligible_stage`/`candidate_next_stage`/`current_stage` unchanged, `ORCH-001`)

No other file changed. No production source (`src/`), no other stage file,
`session-protocol.md`, `decision-log.md`, `implementation-plan.md`, or
`implementation-state.schema.yaml` was touched. This review did not modify
`scripts/orchestration_feature_state.py` or
`tests/test_orchestration_feature_state.py` — per `session-protocol.md`
section 5, review sessions review, they do not silently repair; the F-3 fix
is a REMEDIATOR's job.

## Verification

Rerun independently at HEAD `f89be9b3178794515a25d7f0d504946114b6b821`
(against the unmodified committed state, before any edit by this review):

| Command | Result | Matches recorded? |
|---|---|---|
| `git status --porcelain -b` | clean | yes |
| `git diff 49e1727 f89be9b --stat` | 25 files changed, 1623(+)/59(-) | matches `git show --stat -1 HEAD` |
| `workflowctl verify --config self-governance.yaml --output json` | PASS | yes |
| `pytest -q tests/test_orchestration_feature_state.py` | 74 passed | yes |
| `python scripts/orchestration_feature_state.py validate --state ... --plan ...` | PASS, 0 errors | yes — byte-identical `state_digest` |
| `pytest -q` (full) | 758 passed | yes |
| Fresh CLI-level adversarial probe (F-1/F-2 only) | all 3 scenarios confirmed | n/a — independent reproduction |
| CLI-driven `transition ... --to REVIEW_APPROVED` against a throwaway copy | `next_eligible_stage` → `ORCH-002` | n/a — new diagnostic, confirms F-3 is deterministic |
| `pytest -q tests/test_orchestration_feature_state.py::TestRealRepositoryState -v` (at the point this session's own in-progress edit had ORCH-001 REVIEW_APPROVED) | 1 failed, 1 passed — `test_committed_state_next_eligible_stage_is_orch_001` fails | n/a — demonstrates F-3 |

Exact argv, exit codes and stdout digests are in
`reviews/ORCH-001/20260721T131500Z-claude-code-independent-reviewer-orch-001-2-0637a178.yaml`.
Every command record carries
`environment_fingerprint_digest: sha256:edd354c3e5367798c6d4c0163180e414ed7e1db97b735afff58dad0b739a61dc`
— independently recomputed this session and byte-identical to every prior
ORCH-000/ORCH-001 evidence and review record for this machine/tool identity.

## Decisions

1. Treated the F-1/F-2 fix as sound (see above); no remaining gap of that
   kind was found, so it is not re-litigated.
2. Chose to check the downstream consequence of ORCH-001's own required
   end-state (`REVIEW_APPROVED`, recomputing `next_eligible_stage`) as part
   of "adversarial transition and filesystem review"
   (`stages/ORCH-001.md`'s Independent review checklist) rather than
   stopping once F-1/F-2 verification passed — this is what surfaced F-3.
3. Verified F-3 is a real, tool-level, deterministic consequence (not an
   artifact of any particular editing method) by driving the actual CLI
   `transition` subcommand against a throwaway copy of the real committed
   state file, independently of any hand-edit.
4. Judged F-3 blocking rather than advisory because of its structural
   consequence: once ORCH-001 is `REVIEW_APPROVED`, no session in the
   delivery pipeline downstream of it (starting with `ORCH-002`'s own
   allowed paths) has the authority to fix the pinned test, and
   `REVIEW_APPROVED` itself is immutable outside a governance-amendment
   action. Fixing it after the fact would require exactly the kind of
   session-protocol.md section 6 "Governance-amendment authorization" that
   an ordinary REMEDIATOR/IMPLEMENTER may not invoke on its own authority —
   whereas fixing it now, before approval, is squarely within an ordinary
   REMEDIATOR's existing ORCH-001 scope (the offending file,
   `tests/test_orchestration_feature_state.py`, is already one of
   ORCH-001's exact allowed paths).
5. Did not attempt to fix F-3 myself: `session-protocol.md` section 5
   requires reviewers to "Review only; do not silently repair," and I have
   no independent way to verify a self-authored fix without becoming a
   self-review.
6. Reverted my own in-progress hand-edit of `implementation-state.yaml`
   (which had briefly, locally, recorded ORCH-001 as `REVIEW_APPROVED`
   while I was diagnosing F-3's real consequence) back to the committed
   baseline via `git checkout --`, then reapplied a fresh edit recording
   the actual verdict of this review (`REVIEW_REJECTED`) — the working tree
   this session leaves behind never carries the (incorrect, since this
   review does not actually approve) `REVIEW_APPROVED` state.

## Schema and migrations

No schema or migration changes. `implementation-state` semantics remain
`1.0.0`. `migration-registry.yaml` confirmed unchanged (empty diff,
49e1727..f89be9b).

## Risks

`R-ORCH-001-VALIDATOR-CORRECTNESS` (HIGH, previously unresolved pending
independent review) — disposition updated: the F-1/F-2 `apply_transition`
fix itself is confirmed sound by this independent review. The risk is **not**
marked resolved, because a new, separate blocking finding (F-3) means the
stage as a whole is not yet approved. Severity remains HIGH pending the F-3
remediation and a further independent review, distinct from
`claude-code-implementer-1`, `claude-code-independent-reviewer-orch-001-1`,
`claude-code-remediator-orch-001-1` and this session's actor
(`claude-code-independent-reviewer-orch-001-2`). All four other
pre-existing `unresolved_risks` entries (`R-APPROVAL-ISOLATION`,
`R-GOVERNANCE-TRANSACTION`, `R-BOOTSTRAP-ROLE-OVERLAP`,
`R-REMEDIATION-AMENDMENT-UNREVIEWED`) are carried forward unchanged; none is
affected by this review.

## Blockers

None introduced at the global or stage level. `stages.ORCH-001.blockers`
remains `[]`; the rejection itself is recorded via `review_status: REJECTED`
/ `status: REVIEW_REJECTED`, per the legal `VERIFIED -> REVIEW_REJECTED`
transition (`session-protocol.md` section 2), not via a stage blocker
record.

## Durable state

- `stages.ORCH-001.status`: `VERIFIED` → `REVIEW_REJECTED`.
- `stages.ORCH-001.review_status`: `PENDING` → `REJECTED`.
- `stages.ORCH-001.reviewer`: `null` → `claude-code-independent-reviewer-orch-001-2`.
- `stages.ORCH-001.implementation_commit`: left `null` (not required at
  `REVIEW_REJECTED`; the reviewed commit is recorded in this review's
  evidence `reviewed.implementation_commit` field instead — same pattern as
  the first rejection).
- `stages.ORCH-001.review_evidence`: one new entry appended (this review's
  evidence); the first review's evidence entry is preserved unchanged.
- `stages.ORCH-001.verification_status`: unchanged, `PASSED` (F-1/F-2's
  verification results themselves reproduced cleanly; the rejection is
  about a newly found test-suite defect the passing tests do not, by
  construction, catch against today's state).
- `implementation-state.yaml` `unresolved_risks`:
  `R-ORCH-001-VALIDATOR-CORRECTNESS` disposition updated to record both the
  confirmed F-1/F-2 fix and the new F-3 finding; severity left HIGH.
- `implementation-state.yaml` `history`: one new sequence (27,
  `REVIEW_REJECTED_ORCH_001_F3`), role `REVIEWER`, actor
  `claude-code-independent-reviewer-orch-001-2`.
- `next_eligible_stage` / `candidate_next_stage` / `current_stage`:
  unchanged, `ORCH-001` (recomputed: ORCH-001 is not `REVIEW_APPROVED`, so
  it remains the frontier; confirmed by direct validator `status`
  recomputation after this edit).
- **`ORCH-002` confirmed still `NOT_STARTED`** throughout — unaffected by
  this session, direct read of the committed `implementation-state.yaml`
  after this session's edit.

## Next legal action

A REMEDIATOR, distinct from `claude-code-implementer-1`,
`claude-code-independent-reviewer-orch-001-1`,
`claude-code-remediator-orch-001-1` and this reviewer
(`claude-code-independent-reviewer-orch-001-2`), reads this handoff and this
review's evidence, then:

1. Reads finding F-3 in full (does not re-litigate F-1/F-2, which are
   confirmed fixed).
2. Within ORCH-001's existing allowed paths (only
   `tests/test_orchestration_feature_state.py` needs to change; see
   `remediation_scope` in the review evidence for acceptable approaches),
   fixes `test_committed_state_next_eligible_stage_is_orch_001` so it no
   longer hard-codes a specific stage name as a permanent assertion against
   the live governance document.
3. Verifies the fix survives a subsequent, correct
   `ORCH-001 -> REVIEW_APPROVED` transition (e.g. by testing against a
   temporary copy transitioned via the real CLI, as this review did), not
   just against today's `REVIEW_REJECTED` state.
4. Reruns the full required verification (focused suite, full pytest,
   validator `validate` against the real committed state, `workflowctl
   verify`).
5. Returns the stage to `VERIFIED` with new implementation evidence/handoff
   (a new implementation ID; no prior evidence is overwritten).
6. Does not touch `scripts/orchestration_feature_state.py`,
   `session-protocol.md`, `decision-log.md`, `implementation-plan.md`,
   `implementation-state.schema.yaml`, any `stages/*.md` file, and does not
   start ORCH-002.

## Exact continuation prompt

```
Work in /home/afshin-jian/ai-workflow-engine. Do not rely on chat history.
Read README.md, self-governance.yaml, docs/AGENT_PROTOCOL.md,
docs/implementation/orchestration/session-protocol.md,
docs/implementation/orchestration/implementation-state.yaml,
docs/implementation/orchestration/stages/ORCH-001.md, this handoff and its
review evidence
(docs/implementation/orchestration/reviews/ORCH-001/20260721T131500Z-claude-code-independent-reviewer-orch-001-2-0637a178.yaml),
plus the prior implementation/remediation evidence and handoffs referenced
therein. Confirm this REVIEWER diff (history sequence 27) is committed and
current HEAD matches it. Act as a REMEDIATOR, distinct from
claude-code-implementer-1, claude-code-independent-reviewer-orch-001-1,
claude-code-remediator-orch-001-1, and claude-code-independent-reviewer-orch-001-2.
Fix finding F-3 in tests/test_orchestration_feature_state.py only (do not
touch scripts/orchestration_feature_state.py or re-litigate F-1/F-2; no
plan/schema/session-protocol amendment is authorized or needed), verify the
fix survives a subsequent correct ORCH-001 -> REVIEW_APPROVED transition,
rerun all required verification, and return ORCH-001 to VERIFIED with new
implementation evidence/handoff. Do not implement ORCH-002 in the same
session.
```
