# Handoff: ORCH-001 remediation — Durable feature-state validator (REMEDIATOR, F-1/F-2)

## Summary

Acting in role REMEDIATOR (actor `claude-code-remediator-orch-001-1`,
distinct from `claude-code-implementer-1` and
`claude-code-independent-reviewer-orch-001-1`), this session remediates the
two blocking findings from ORCH-001's first independent review
(`reviews/ORCH-001/20260721T122035Z-claude-code-independent-reviewer-orch-001-1-0a0c5a0c.yaml`),
per `prompts/remediate-rejected.md` and `session-protocol.md` section 6.

**F-1 (HIGH, blocking)**: `apply_transition` authorized `BLOCKED ->
IN_PROGRESS` with no check that the stage's blocker(s) were resolved and no
recheck that its prerequisites remained `REVIEW_APPROVED`, contradicting
`session-protocol.md` section 2's row for that exact edge.

**Fix**: added an explicit `from_status == "BLOCKED" and to_status ==
"IN_PROGRESS"` gate in `apply_transition`
(`scripts/orchestration_feature_state.py`) that raises `TransitionError
UNRESOLVED_BLOCKER` unless every one of the stage's existing blockers is
resolved (already, or via that same call's `resolve_blockers`), and raises
`TransitionError PREREQUISITE_NOT_APPROVED` unless every prerequisite still
recomputes as `REVIEW_APPROVED` — mirroring the pre-existing
`NOT_STARTED -> IN_PROGRESS` gate's structure. No other legal transition's
behavior changed; `LEGAL_TRANSITIONS`, `check_transition_legal`,
`validate_schema`, `validate_semantics`, and the CAS-guard/atomic-write path
are untouched.

**F-2 (MEDIUM, blocking)**: the 70-test suite's only `BLOCKED ->
IN_PROGRESS` coverage always supplied `resolve_blockers` and never asserted
the negative case.

**Fix**: added four new tests to `tests/test_orchestration_feature_state.py`:
`test_blocked_resume_rejected_with_unresolved_blocker`,
`test_blocked_resume_rejected_with_unapproved_prerequisite` (both negative),
`test_blocked_resume_succeeds_when_blockers_resolved_and_prerequisite_approved`,
`test_blocked_resume_succeeds_with_already_resolved_blocker_not_reresolved`
(both positive) — exactly the four cases named by the rejection's
`remediation_scope`.

## Changed paths

- `scripts/orchestration_feature_state.py` (modified: new `apply_transition` gate)
- `tests/test_orchestration_feature_state.py` (modified: 4 new tests, 70 → 74)
- `docs/implementation/orchestration/implementation-state.yaml` (modified: ORCH-001 stage entry, history sequences 24-26, `unresolved_risks` disposition, `last_updated`)
- `docs/implementation/orchestration/evidence/ORCH-001/20260721T124440Z-claude-code-remediator-orch-001-1-6e2bbce9.yaml` (new)
- `docs/implementation/orchestration/evidence/ORCH-001/logs/20260721T124440Z-claude-code-remediator-orch-001-1-6e2bbce9-*` (new, 17 files)
- `docs/implementation/orchestration/handoffs/ORCH-001/20260721T124440Z-claude-code-remediator-orch-001-1-6e2bbce9.md` (this file)

No production source (`src/`), no other governance document
(`session-protocol.md`, `decision-log.md`, `implementation-plan.md`,
`implementation-state.schema.yaml`), and no `stages/*.md` file changed —
confirmed by `git status --porcelain -b` after every edit.

## Verification

Run independently before and after this session's edits, at starting HEAD
`49e1727bf782e4c2fa769028f54f026df5edac9a` (this session leaves an
uncommitted diff; HEAD does not advance):

| Command | Before | After |
|---|---|---|
| `git status --porcelain -b` | clean | only declared paths modified/untracked |
| `workflowctl verify --config self-governance.yaml --output json` | PASS | PASS |
| `pytest -q` | 754 passed, 0 failed, 0 skipped | 758 passed, 0 failed, 0 skipped |
| `pytest -q tests/test_orchestration_feature_state.py` | 70 passed, 0 failed, 0 skipped | 74 passed, 0 failed, 0 skipped |
| `python scripts/orchestration_feature_state.py validate --state ... --plan ...` | PASS, 0 errors | PASS, 0 errors |
| `ruff check` (both changed files) | n/a | All checks passed |
| `black --check` (both changed files) | n/a | 2 files would be left unchanged |
| `mypy src` (sanity; unaffected) | n/a | Success: 44 files |
| Fresh F-1 demonstration probe (new, this session) | n/a | all 3 required scenarios PASS |

The "before" snapshot was captured after `git stash push -u` set aside this
session's own edits, to obtain a true pre-change baseline rather than one
that silently already included the fix under test (see DEC-4 in the
evidence YAML for the analogous state-file editing rationale; the
stash/pop itself mirrors the original implementer's DEC-2).

### Explicit demonstration of the three required scenarios

A fresh, standalone script
(`evidence/ORCH-001/logs/20260721T124440Z-claude-code-remediator-orch-001-1-6e2bbce9-f1-fix-demonstration-probe.py`,
independent of both the rejecting reviewer's adversarial probe and the new
unit tests) constructs a two-stage fixture and demonstrates:

1. **`BLOCKED -> IN_PROGRESS` fails with unresolved blockers**: a stage with
   an unresolved blocker and an approved prerequisite, transitioned with no
   `resolve_blockers` argument, raises
   `TransitionError: UNRESOLVED_BLOCKER: cannot resume BLOCKED ->
   IN_PROGRESS while blocker(s) ['B1'] remain unresolved`.
2. **`BLOCKED -> IN_PROGRESS` fails with an unapproved prerequisite**: the
   same stage with its prerequisite left `IN_PROGRESS` (not
   `REVIEW_APPROVED`), transitioned with `resolve_blockers={"B1": "fixed"}`,
   raises `TransitionError: PREREQUISITE_NOT_APPROVED: cannot resume
   BLOCKED -> IN_PROGRESS while prerequisite(s) ['ORCH-000'] are not
   REVIEW_APPROVED`.
3. **`BLOCKED -> IN_PROGRESS` succeeds only when both conditions hold**:
   the same stage with an approved prerequisite and
   `resolve_blockers={"B1": "fixed"}` succeeds, the blocker's `resolution`
   becomes `"fixed"`, and `validate_state` on the result reports
   `passed=True, errors=[]`.

Full output is in
`evidence/ORCH-001/logs/20260721T124440Z-claude-code-remediator-orch-001-1-6e2bbce9-f1-fix-demonstration-probe-output.txt`.

Exact argv, exit codes and stdout digests are in
`evidence/ORCH-001/20260721T124440Z-claude-code-remediator-orch-001-1-6e2bbce9.yaml`.
Every command record carries
`environment_fingerprint_digest: sha256:edd354c3e5367798c6d4c0163180e414ed7e1db97b735afff58dad0b739a61dc`
— byte-identical to every prior ORCH-000/ORCH-001 evidence and review record
for this same machine/tool identity.

## Decisions

See the evidence YAML's `decisions` (DEC-1..DEC-5) for full rationale:

1. **DEC-1** — the fix is a new conditional block in `apply_transition`
   itself (the sole write path), not a new `validate_semantics` rule,
   matching the rejection's `remediation_scope` and avoiding any risk of
   weakening `validate_state`.
2. **DEC-2** — a blocker resolved within the same call (via
   `resolve_blockers`) counts as resolved for this gate, preserving the
   existing, passing `test_blocked_with_blocker_succeeds_and_resolve_reopens`.
3. **DEC-3** — the prerequisite check reads each prerequisite's own status
   directly, rather than reusing `recompute_next_eligible` (a different
   question: global frontier vs. this stage's own prerequisite closure).
4. **DEC-4** — `implementation-state.yaml` was hand-edited to preserve its
   flow-style formatting, matching the original implementer's DEC-3
   rationale; independently re-validated with the tool's own `validate`
   afterward.
5. **DEC-5** — `unresolved_risks`' `R-ORCH-001-VALIDATOR-CORRECTNESS`
   disposition is updated to record the fix, but severity stays `HIGH` and
   the risk is not marked resolved: a REMEDIATOR cannot approve its own fix
   (`session-protocol.md` section 6); that requires a subsequent
   independent reviewer.

## Schema and migrations

No schema or migration changes. `implementation-state` semantics remain
`1.0.0`. `plan_version` (1.1.0) and `architecture_version` (3.0.0) are
unaffected. `migration-registry.yaml` unchanged (not in this stage's changed
paths).

## Risks

`R-ORCH-001-VALIDATOR-CORRECTNESS` (unchanged severity HIGH) — disposition
updated in `implementation-state.yaml` to record this fix. Not marked
resolved by this session; a subsequent independent reviewer, distinct from
`claude-code-implementer-1`, `claude-code-independent-reviewer-orch-001-1`
and this session's actor, must independently reproduce the fix and confirm
no remaining gap of the same kind before the risk can be marked resolved.
All four other pre-existing `unresolved_risks` entries
(`R-APPROVAL-ISOLATION`, `R-GOVERNANCE-TRANSACTION`,
`R-BOOTSTRAP-ROLE-OVERLAP`, `R-REMEDIATION-AMENDMENT-UNREVIEWED`) are
carried forward unchanged; none is affected by this remediation.

## Blockers

None introduced; `stages.ORCH-001.blockers` remains `[]`; no global blocker
added or resolved.

## Durable state

- `stages.ORCH-001.status`: `REVIEW_REJECTED` → `VERIFIED` (via
  `IN_PROGRESS`, `IMPLEMENTED`; history sequences 24-26).
- `stages.ORCH-001.review_status`: `REJECTED` → `PENDING`.
- `stages.ORCH-001.reviewer`: `claude-code-independent-reviewer-orch-001-1`
  → `null` (awaiting the next independent reviewer).
- `stages.ORCH-001.implementer`: `claude-code-implementer-1` →
  `claude-code-remediator-orch-001-1`.
- `stages.ORCH-001.verification_status`: unchanged, `PASSED`.
- `stages.ORCH-001.evidence`: one new entry appended (this session's
  implementation evidence); the rejected implementation's original evidence
  entry is preserved unchanged.
- `stages.ORCH-001.review_evidence`: unchanged (the rejection's review
  evidence entry is preserved; this session adds no new review evidence, as
  a REMEDIATOR does not record review verdicts).
- `stages.ORCH-001.implementation_commit`: `null` (left null per
  session-protocol.md section 3; the next reviewer sets it to the clean
  HEAD it actually reviews).
- `stages.ORCH-001.expected_base_head`: unchanged,
  `46ded3e51e8a90a8292d1c2721b565d62838caca` (the stage's original
  `NOT_STARTED -> IN_PROGRESS` start; not updated on a remediation restart,
  matching the precedent set across ORCH-000's multiple remediation
  rounds).
- `stages.ORCH-001.handoff`: this file's path.
- `implementation-state.yaml` `unresolved_risks`:
  `R-ORCH-001-VALIDATOR-CORRECTNESS` disposition updated (severity
  unchanged, `HIGH`).
- `implementation-state.yaml` `history`: three new sequences (24, 25, 26 —
  `STARTED_ORCH_001_REMEDIATION_F1_F2`,
  `IMPLEMENTED_ORCH_001_REMEDIATION_F1_F2`,
  `VERIFIED_ORCH_001_REMEDIATION_F1_F2`), role `REMEDIATOR`, actor
  `claude-code-remediator-orch-001-1`.
- `plan_version` / `architecture_version`: unchanged (`1.1.0` / `3.0.0`).
- `next_eligible_stage` / `candidate_next_stage` / `current_stage`:
  unchanged, `ORCH-001` (recomputation confirmed by the validator itself:
  ORCH-001 is `VERIFIED`, not `REVIEW_APPROVED`, so it remains the
  recomputed frontier; `ORCH-002`'s prerequisite, ORCH-001, is not yet
  `REVIEW_APPROVED`).
- **`ORCH-002` confirmed still `NOT_STARTED`** — unaffected by this session,
  direct read of the committed `implementation-state.yaml` after this
  session's edit.

## Next legal action

An independent REVIEWER, distinct from `claude-code-implementer-1`,
`claude-code-independent-reviewer-orch-001-1` and
`claude-code-remediator-orch-001-1`, reads this handoff and this session's
evidence, then:

1. Confirms this diff is committed and current HEAD matches it.
2. Reviews the fix: the new `apply_transition` gate against
   `session-protocol.md` section 2's `BLOCKED -> IN_PROGRESS` row, and the 4
   new tests against the rejection's `remediation_scope`.
3. Reruns required verification independently: `pytest -q
   tests/test_orchestration_feature_state.py`, `python
   scripts/orchestration_feature_state.py validate --state
   docs/implementation/orchestration/implementation-state.yaml --plan
   docs/implementation/orchestration/implementation-plan.md`, the full
   `pytest -q`, and `workflowctl verify`.
4. Independently reproduces (with its own fresh adversarial fixture, per
   `stages/ORCH-001.md`'s "Independent review checklist") that
   `BLOCKED -> IN_PROGRESS` now rejects an unresolved blocker and an
   unapproved prerequisite, and succeeds only when both are satisfied.
5. Records `REVIEW_APPROVED` or `REVIEW_REJECTED` in a new
   `reviews/ORCH-001/<review-id>.yaml`.
6. Does not implement ORCH-002 in the same session.

## Exact continuation prompt

```
Work in /home/afshin-jian/ai-workflow-engine. Do not rely on chat history.
Read README.md, self-governance.yaml, docs/AGENT_PROTOCOL.md,
docs/implementation/orchestration/session-protocol.md,
docs/implementation/orchestration/implementation-state.yaml,
docs/implementation/orchestration/stages/ORCH-001.md, this handoff and its
evidence record
(docs/implementation/orchestration/evidence/ORCH-001/20260721T124440Z-claude-code-remediator-orch-001-1-6e2bbce9.yaml),
plus the original rejection review evidence/handoff
(reviews/ORCH-001/20260721T122035Z-claude-code-independent-reviewer-orch-001-1-0a0c5a0c.yaml,
handoffs/ORCH-001/20260721T122035Z-claude-code-independent-reviewer-orch-001-1-0a0c5a0c.md).
Confirm this REMEDIATOR diff (history sequences 24-26) is committed and
current HEAD matches it. Act as an independent REVIEWER, distinct from
claude-code-implementer-1, claude-code-independent-reviewer-orch-001-1 and
claude-code-remediator-orch-001-1. Review the new apply_transition
BLOCKED -> IN_PROGRESS gate in scripts/orchestration_feature_state.py and
the 4 new tests in tests/test_orchestration_feature_state.py against
session-protocol.md section 2 and the rejection's remediation_scope,
rerun required verification (pytest -q
tests/test_orchestration_feature_state.py; python
scripts/orchestration_feature_state.py validate --state
docs/implementation/orchestration/implementation-state.yaml --plan
docs/implementation/orchestration/implementation-plan.md; full pytest -q;
workflowctl verify), independently reproduce the fix with a fresh
adversarial fixture, and record REVIEW_APPROVED or REVIEW_REJECTED in a new
reviews/ORCH-001/<review-id>.yaml. Do not implement ORCH-002 in the same
session.
```
