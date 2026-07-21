# Handoff: ORCH-001 remediation — Durable feature-state validator (REMEDIATOR, F-3)

## Summary

Acting in role REMEDIATOR (actor `claude-code-remediator-orch-001-2`, distinct
from `claude-code-implementer-1`, `claude-code-independent-reviewer-orch-001-1`,
`claude-code-remediator-orch-001-1`, and
`claude-code-independent-reviewer-orch-001-2`), this session remediates **finding
F-3 only** from the second independent ORCH-001 review
(`reviews/ORCH-001/20260721T131500Z-claude-code-independent-reviewer-orch-001-2-0637a178.yaml`),
at committed HEAD `b9813b6cb6d791181db27811df9173be8667f967` ("docs: reject
ORCH-001 for pinned frontier test", history sequence 27).

**F-3 (HIGH, blocking).** `TestRealRepositoryState.test_committed_state_next_eligible_stage_is_orch_001`
hard-coded `ofs.recompute_next_eligible(state) == "ORCH-001"` against the live
committed governance document — a transient fact, not a durable invariant. The
moment ORCH-001 legitimately reaches `REVIEW_APPROVED`, the real frontier
correctly advances to `ORCH-002` and that pinned assertion fails; because
`ORCH-002`'s allowed paths exclude `tests/test_orchestration_feature_state.py`
and `REVIEW_APPROVED` is immutable, no downstream session could repair it. Only a
REMEDIATOR acting now, before approval, has both the authority and the
opportunity.

**Fix (remediation_scope approach (b)).** Removed the pinned test and replaced it
with a shared helper `_assert_frontier_is_durable_invariant` plus three
stage-name-free tests. The helper asserts the exact durable properties the review
recommended: (1) the recomputed frontier equals the document's own declared
`next_eligible_stage`; (2) it is `null` or a member of `delivery_order`; (3) when
non-null, the frontier is itself not `REVIEW_APPROVED` and every one of its
prerequisites is `REVIEW_APPROVED`. The frontier is discovered dynamically
(never named), and the approval scenario is driven through the **real CLI
`transition` subcommand** against an isolated throwaway copy of the real
committed state file. The one concrete `ORCH-001 -> ORCH-002` anchor is guarded
behind `if frontier == "ORCH-001"`, so it documents the exact scenario F-3 named
while self-disabling once the frontier legitimately advances. **F-1/F-2 were not
re-litigated or touched;** `scripts/orchestration_feature_state.py` is unchanged.

ORCH-001 is returned to `VERIFIED` (via `IN_PROGRESS` and `IMPLEMENTED`, history
sequences 28–30) with `review_status: PENDING`, `reviewer: null`,
`implementation_commit: null`, awaiting a further independent review.

## Changed paths

- `tests/test_orchestration_feature_state.py` (modified: replaced one pinned
  `TestRealRepositoryState` test with a durable-invariant helper and three new
  tests)
- `docs/implementation/orchestration/implementation-state.yaml` (modified:
  ORCH-001 stage entry, `unresolved_risks` R-ORCH-001-VALIDATOR-CORRECTNESS
  disposition, history sequences 28–30, `last_updated`;
  `next_eligible_stage`/`candidate_next_stage`/`current_stage` unchanged,
  `ORCH-001`)
- `docs/implementation/orchestration/evidence/ORCH-001/20260721T141500Z-claude-code-remediator-orch-001-2-943a0e4c.yaml` (new)
- `docs/implementation/orchestration/evidence/ORCH-001/logs/20260721T141500Z-claude-code-remediator-orch-001-2-943a0e4c-*` (new: environment fingerprint; git rev-parse/status before+after; pytest focused/full before+after; validate before+after; workflowctl verify before+after; ruff/black; git diff --check; the standalone F-3 durability probe script + its output)
- `docs/implementation/orchestration/handoffs/ORCH-001/20260721T141500Z-claude-code-remediator-orch-001-2-943a0e4c.md` (this file)

No other file changed. `scripts/orchestration_feature_state.py`,
`session-protocol.md`, `decision-log.md`, `implementation-plan.md`,
`implementation-state.schema.yaml`, every `stages/*.md` file, ORCH-000 records,
ORCH-002 state, and `src/` are untouched (empty diffs; independently confirmed
in the git-status-after artifact).

## Verification

Rerun at clean HEAD `b9813b6cb6d791181db27811df9173be8667f967`:

| Command | Before | After |
|---|---|---|
| `git status --porcelain -b` | clean | only declared changed_paths |
| `pytest -q tests/test_orchestration_feature_state.py` | 74 passed | 76 passed |
| `pytest -q` (full) | 758 passed | 760 passed |
| `python scripts/orchestration_feature_state.py validate --state … --plan …` | PASS | PASS (`state_digest` sha256:d3cc44ba…13c0) |
| `workflowctl verify --config self-governance.yaml --output json` | PASS | PASS |
| `ruff check …` / `black --check …` | — | pass / 2 files unchanged |
| `git diff --check` | — | clean (no whitespace errors) |
| F-3 durability probe (real CLI approval on throwaway copy) | — | `F3_DURABILITY_PROBE: PASS` |

Focused suite is +2 net: the single pinned test was removed and three durable
tests added (`test_committed_state_frontier_is_a_durable_invariant`,
`test_committed_state_frontier_invariant_holds_at_every_pre_approval_status`,
`test_frontier_invariant_survives_a_real_cli_approval_of_the_frontier`). Exact
argv, exit codes and stdout digests are in the evidence YAML; every command
carries `environment_fingerprint_digest: sha256:edd354c3…a61dc`, byte-identical
to every prior ORCH-000/ORCH-001 record.

The durability probe
(`evidence/ORCH-001/logs/…-f3-durability-probe.py`) drives the real CLI
`transition` subcommand to `ORCH-001 -> REVIEW_APPROVED` against a throwaway copy
of the real committed state file and confirms: the post-approval state validates;
the durable frontier invariant holds; `recompute_next_eligible` becomes
`ORCH-002`; the removed pinned assertion (`== "ORCH-001"`) would fail
(`assert 'ORCH-002' == 'ORCH-001'`); and the real committed document is untouched
(frontier still `ORCH-001`).

## Decisions

See the evidence YAML's `decisions` (DEC-1 … DEC-5): replace via approach (b)
with a durable invariant helper (DEC-1); discover the frontier dynamically and
guard the one concrete anchor to avoid reintroducing the F-3 defect class
(DEC-2); drive the approval scenario through the real CLI against an isolated
copy (DEC-3); hand-edit the flow-style state document rather than reformatting it
via the transition subcommand, re-validated with the tool's own `validate`
(DEC-4); update the risk disposition but leave severity HIGH pending independent
review (DEC-5).

## Schema and migrations

No schema or migration changes. `implementation-state` semantics remain `1.0.0`.
`migration-registry.yaml` unchanged.

## Risks

`R-ORCH-001-VALIDATOR-CORRECTNESS` (HIGH) — disposition updated to record the F-3
remediation. **Not** marked resolved: a REMEDIATOR may not approve its own fix
(session-protocol.md section 6), so it awaits a further independent review by an
actor distinct from `claude-code-implementer-1`,
`claude-code-independent-reviewer-orch-001-1`,
`claude-code-remediator-orch-001-1`,
`claude-code-independent-reviewer-orch-001-2` and this session's actor. The four
other pre-existing `unresolved_risks` entries are carried forward unchanged.

## Blockers

None introduced. `stages.ORCH-001.blockers` remains `[]`.

## Durable state

- `stages.ORCH-001.status`: `REVIEW_REJECTED` → `VERIFIED` (via `IN_PROGRESS`,
  `IMPLEMENTED`).
- `stages.ORCH-001.review_status`: `REJECTED` → `PENDING`.
- `stages.ORCH-001.reviewer`: `claude-code-independent-reviewer-orch-001-2` → `null`.
- `stages.ORCH-001.implementer`: → `claude-code-remediator-orch-001-2`.
- `stages.ORCH-001.implementation_commit`: `null` (unchanged; set by the reviewer at approval).
- `stages.ORCH-001.verification_status`: `PASSED` (unchanged).
- `stages.ORCH-001.evidence`: one new entry appended; prior two preserved.
- `stages.ORCH-001.handoff`: → this handoff.
- `history`: three new entries (sequences 28–30): `STARTED_ORCH_001_REMEDIATION_F3`,
  `IMPLEMENTED_ORCH_001_REMEDIATION_F3`, `VERIFIED_ORCH_001_REMEDIATION_F3`, all
  role `REMEDIATOR`.
- `unresolved_risks` R-ORCH-001-VALIDATOR-CORRECTNESS disposition: F-3
  remediation recorded; severity left HIGH.
- `next_eligible_stage` / `candidate_next_stage` / `current_stage`: unchanged,
  `ORCH-001` (ORCH-001 is `VERIFIED`, not `REVIEW_APPROVED`, so it remains the
  frontier; confirmed by the validator `status`/`validate` runs).
- **`ORCH-002` remains `NOT_STARTED`** throughout — unaffected by this session.

## Next legal action

A REMEDIATOR did the F-3 fix; the next legal action is an **independent
REVIEWER**, distinct from `claude-code-implementer-1`,
`claude-code-independent-reviewer-orch-001-1`,
`claude-code-remediator-orch-001-1`,
`claude-code-independent-reviewer-orch-001-2`, and
`claude-code-remediator-orch-001-2`, in a fresh session, after a human commits
this diff. The reviewer re-runs the stage-required verification, independently
reproduces that the durable frontier invariant survives a correct
`ORCH-001 -> REVIEW_APPROVED` transition (and that the removed pin would fail
after it), confirms F-1/F-2 remain fixed and are not re-litigated, and records
`REVIEW_APPROVED` or `REVIEW_REJECTED`. Do not start ORCH-002 in the same
session.

## Exact continuation prompt

```
Work in /home/afshin-jian/ai-workflow-engine. Do not rely on chat history.
Read README.md, self-governance.yaml, docs/AGENT_PROTOCOL.md,
docs/implementation/orchestration/session-protocol.md,
docs/implementation/orchestration/implementation-state.yaml,
docs/implementation/orchestration/stages/ORCH-001.md, this handoff and its
evidence
(docs/implementation/orchestration/evidence/ORCH-001/20260721T141500Z-claude-code-remediator-orch-001-2-943a0e4c.yaml),
the F-3 rejection review it remediates
(reviews/ORCH-001/20260721T131500Z-claude-code-independent-reviewer-orch-001-2-0637a178.yaml),
and the prior ORCH-001 implementation/remediation evidence and handoffs.
Confirm this REMEDIATOR diff (history sequences 28-30) is committed and current
HEAD matches it. Act as an independent REVIEWER, distinct from
claude-code-implementer-1, claude-code-independent-reviewer-orch-001-1,
claude-code-remediator-orch-001-1, claude-code-independent-reviewer-orch-001-2
and claude-code-remediator-orch-001-2. Re-run pytest -q
tests/test_orchestration_feature_state.py, full pytest -q, the validator
validate against the real committed state, and workflowctl verify;
independently reproduce that the durable frontier invariant survives a correct
ORCH-001 -> REVIEW_APPROVED transition against a throwaway copy (and that the
removed pinned assertion would fail after it); confirm F-1/F-2 remain fixed and
are not re-litigated; then record REVIEW_APPROVED or REVIEW_REJECTED in a new
reviews/ORCH-001/<review-id>.yaml. Do not implement ORCH-002 in the same
session.
```
