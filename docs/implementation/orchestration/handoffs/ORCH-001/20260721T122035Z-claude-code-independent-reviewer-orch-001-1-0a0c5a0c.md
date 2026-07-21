# Handoff: ORCH-001 review — Durable feature-state validator (REVIEWER, REJECTED)

## Summary

Acting in role REVIEWER (actor `claude-code-independent-reviewer-orch-001-1`,
distinct from `claude-code-implementer-1` and every ORCH-000 actor), this
session independently reviews ORCH-001's implementation at committed HEAD
`e9a43974b21d4d5c6ab12ea9c28d484a9afedf55` ("feat: implement ORCH-001
feature-state validator"), per `stages/ORCH-001.md`'s "Independent review
checklist" and `session-protocol.md` section 5.

**Verdict: REJECTED.**

Reruns of every stage-required verification command reproduced the
implementer's recorded results exactly (70/70 focused tests, 754/754 full
suite, validator `validate` PASS with a byte-identical stdout digest,
`workflowctl verify` PASS), and the changed-path scope is confirmed clean
(22 changed paths, all within ORCH-001's allowed paths; no governance, plan,
schema, or `src/` file touched; `ORCH-002` confirmed still `NOT_STARTED`).

However, an adversarial reproduction of the "Independent review checklist"
requirement ("Adversarial transition and filesystem review") found a
concrete, reproducible defect: `apply_transition` authorizes
`BLOCKED -> IN_PROGRESS` with **no check that the stage's blocker(s) are
resolved and no recheck that its prerequisites remain `REVIEW_APPROVED`**,
directly contradicting `session-protocol.md` section 2's row for this exact
edge: *"BLOCKED | IN_PROGRESS | appropriate role; blocker resolution is
evidenced and prerequisites still approved."* A minimal fixture (BLOCKED
stage, one unresolved blocker, `transition --to IN_PROGRESS` with no
`--resolve-blocker`) succeeds, and the tool's own `validate_state` reports
the result as fully valid — i.e. the validator both authorizes and then
blesses exactly the class of defect its own stage spec names as this
stage's central risk ("Validator defects could authorize later work" /
`R-ORCH-001-VALIDATOR-CORRECTNESS`). This is not hypothetical: it is
reproduced and saved as
`reviews/ORCH-001/logs/20260721T122035Z-claude-code-independent-reviewer-orch-001-1-0a0c5a0c-adversarial-blocked-resume-probe.py`.

A second, related finding: the 70-test suite's only
`BLOCKED -> IN_PROGRESS` test always supplies `resolve_blockers` and never
asserts the negative case, so this gap shipped with a fully green suite.

## Changed paths

- `docs/implementation/orchestration/reviews/ORCH-001/20260721T122035Z-claude-code-independent-reviewer-orch-001-1-0a0c5a0c.yaml` (new)
- `docs/implementation/orchestration/reviews/ORCH-001/logs/20260721T122035Z-claude-code-independent-reviewer-orch-001-1-0a0c5a0c-*` (new, 10 files)
- `docs/implementation/orchestration/handoffs/ORCH-001/20260721T122035Z-claude-code-independent-reviewer-orch-001-1-0a0c5a0c.md` (this file)
- `docs/implementation/orchestration/implementation-state.yaml` (modified: ORCH-001 stage entry, history, last_updated)

No other file changed. No production source (`src/`), no other stage file,
`session-protocol.md`, `decision-log.md`, `implementation-plan.md`, or
`implementation-state.schema.yaml` was touched.

## Verification

Rerun independently at HEAD `e9a43974b21d4d5c6ab12ea9c28d484a9afedf55`:

| Command | Result | Matches recorded? |
|---|---|---|
| `git status --porcelain -b` | clean | yes |
| `workflowctl verify --config self-governance.yaml --output json` | PASS | yes |
| `pytest -q tests/test_orchestration_feature_state.py` | 70 passed | yes |
| `python scripts/orchestration_feature_state.py validate --state ... --plan ...` | PASS, 0 errors | yes — byte-identical stdout digest |
| `pytest -q` (full) | 754 passed | yes |
| Adversarial `BLOCKED -> IN_PROGRESS` probe (new, this review) | **defect confirmed** | n/a — new finding |

Exact argv, exit codes and stdout digests are in
`reviews/ORCH-001/20260721T122035Z-claude-code-independent-reviewer-orch-001-1-0a0c5a0c.yaml`.
Every command record carries
`environment_fingerprint_digest: sha256:edd354c3e5367798c6d4c0163180e414ed7e1db97b735afff58dad0b739a61dc`
— independently recomputed this session and byte-identical to every prior
ORCH-000/ORCH-001 evidence record for this machine/tool identity.

## Decisions

1. Confirmed `LEGAL_TRANSITIONS` (scripts/orchestration_feature_state.py
   lines 148-162) and `check_transition_legal` against
   `session-protocol.md` section 2's table line-by-line: all 9 rows map
   1:1, including the two "Active role" / "appropriate role" rows read as
   "any role" (`roles=None`) — a defensible reading since neither row names
   specific roles.
2. Confirmed `validate_semantics` against
   `implementation-state.schema.yaml`'s trailing comment block line-by-line:
   every literal rule is implemented except "expected HEAD must advance
   explicitly after a human commit/review" and "state changes and their
   evidence must be committed together", both of which require Git
   introspection outside a single state-file snapshot and are reasonably
   left to the surrounding process rather than this tool — not treated as a
   blocking gap.
3. The `BLOCKED -> IN_PROGRESS` gap (F-1) is treated as blocking because it
   is precisely the category of defect this stage exists to prevent
   (`R-ORCH-001-VALIDATOR-CORRECTNESS`), it is concretely reproduced (not
   speculative), and it directly contradicts a named row of the contract
   this validator's docstring claims to enforce.

## Schema and migrations

No schema or migration changes proposed or required. `migration-registry.yaml`
confirmed unchanged (empty diff, 46ded3e..e9a4397).

## Risks

`R-ORCH-001-VALIDATOR-CORRECTNESS` (already recorded, MEDIUM) is **not**
resolved by this review — it is realized: F-1 is exactly the failure mode
that risk names. This review does not modify `unresolved_risks`; the
REMEDIATOR fixing F-1/F-2 should update that entry's disposition once fixed
and independently re-reviewed.

## Blockers

None introduced at the global level. `stages.ORCH-001.blockers` remains
`[]`; the rejection itself is recorded via `review_status: REJECTED` /
`status: REVIEW_REJECTED`, per the legal `VERIFIED -> REVIEW_REJECTED`
transition (session-protocol.md section 2), not via a stage blocker record.

## Durable state

- `stages.ORCH-001.status`: `VERIFIED` → `REVIEW_REJECTED`.
- `stages.ORCH-001.review_status`: `PENDING` → `REJECTED`.
- `stages.ORCH-001.reviewer`: `null` → `claude-code-independent-reviewer-orch-001-1`.
- `stages.ORCH-001.review_evidence`: `[]` → one new entry (this review's evidence).
- `stages.ORCH-001.implementation_commit`: left `null` (not required at
  `REVIEW_REJECTED`; the reviewed commit is recorded in this review's
  evidence `reviewed.implementation_commit` field instead).
- `stages.ORCH-001.verification_status`: unchanged, `PASSED` (the
  implementer's recorded verification results were reproduced and are not
  in dispute; the rejection is about a code defect the passing tests did
  not catch, not about verification having failed).
- `implementation-state.yaml` `history`: one new sequence (23,
  `REVIEW_REJECTED_ORCH_001`), role `REVIEWER`, actor
  `claude-code-independent-reviewer-orch-001-1`.
- `next_eligible_stage` / `candidate_next_stage` / `current_stage`:
  unchanged, `ORCH-001` (recomputation confirmed: ORCH-001 is not
  `REVIEW_APPROVED`, so it remains the frontier).

## Next legal action

A REMEDIATOR, distinct from `claude-code-implementer-1` and from this
reviewer (`claude-code-independent-reviewer-orch-001-1`), reads this
handoff and this review's evidence, then:

1. Reads the rejection findings (F-1, F-2) in full.
2. Within ORCH-001's existing allowed paths (no plan/schema amendment
   needed — see `remediation_scope` in the review evidence), fixes
   `apply_transition`'s `BLOCKED -> IN_PROGRESS` edge to require every
   stage blocker resolved and to recheck prerequisite `REVIEW_APPROVED`
   closure, and adds negative/fault tests pinning both checks.
3. Reruns the full required verification (focused suite, full pytest,
   validator `validate` against the real committed state,
   `workflowctl verify`).
4. Returns the stage to `VERIFIED` with new implementation evidence/handoff
   (a new implementation ID; the rejected evidence is never overwritten).
5. Does not re-litigate this verdict, does not touch
   `session-protocol.md`/`decision-log.md`/`implementation-plan.md`/
   `implementation-state.schema.yaml`/any `stages/*.md` file, and does not
   start ORCH-002.

## Exact continuation prompt

```
Work in /home/afshin-jian/ai-workflow-engine. Do not rely on chat history.
Read README.md, self-governance.yaml, docs/AGENT_PROTOCOL.md,
docs/implementation/orchestration/session-protocol.md,
docs/implementation/orchestration/decision-log.md,
docs/implementation/orchestration/implementation-plan.md,
docs/implementation/orchestration/implementation-state.yaml,
docs/implementation/orchestration/stages/ORCH-001.md, this handoff and its
review evidence
(docs/implementation/orchestration/reviews/ORCH-001/20260721T122035Z-claude-code-independent-reviewer-orch-001-1-0a0c5a0c.yaml),
plus the rejected implementation's own evidence/handoff
(evidence/ORCH-001/20260721T115508Z-claude-code-implementer-1-02891aae.yaml,
handoffs/ORCH-001/20260721T115508Z-claude-code-implementer-1-02891aae.md).
Confirm this REVIEWER diff (history sequence 23) is committed and current
HEAD matches it. Act as a REMEDIATOR, distinct from claude-code-implementer-1
and from claude-code-independent-reviewer-orch-001-1. Fix findings F-1 and
F-2 in scripts/orchestration_feature_state.py and
tests/test_orchestration_feature_state.py only (no plan/schema/session-
protocol amendment is authorized or needed), rerun all required
verification, and return ORCH-001 to VERIFIED with new implementation
evidence/handoff. Do not implement ORCH-002 in the same session.
```
