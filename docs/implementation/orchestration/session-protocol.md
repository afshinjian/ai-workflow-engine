# Orchestration Feature Session Protocol

This protocol applies to every fresh Claude or Codex session working on feature
`ORCH`. Conversation history is neither required nor authoritative.

## 1. Mandatory preflight for every role

1. Change to `/home/afshin-jian/ai-workflow-engine`; refuse a different resolved
   repository root.
2. Read, in full: `README.md`, `self-governance.yaml`, every path named under its
   `governance` and `handover` keys, `docs/AGENT_PROTOCOL.md`, and the applicable
   governance/validation report, then this package's
   `README.md`, `architecture-v3.md`, `implementation-plan.md`,
   `implementation-state.schema.yaml`, `implementation-state.yaml`, and the
   selected stage specification.
3. Validate YAML syntax, state schema and semantic rules. Until ORCH-001 provides
   the validator, perform the checks explicitly and record them.
4. Inspect branch, HEAD, upstream, worktree/index, in-progress Git operations,
   feature lock and recent commits. Acquire the feature-operation lock before
   any write. The operational lock is engine-external and repository-identity
   scoped; durable `IN_PROGRESS` state is the second concurrency signal.
5. Require a clean tree. The only bootstrap exception is an owner explicitly
   handling `DESIGN_PACKAGE_PENDING_HUMAN_COMMIT`; no implementation or review
   happens in that state.
6. Verify current HEAD contains the state/evidence being relied upon. For an
   implementation start, record current HEAD as the selected stage's
   `expected_base_head`. For review, current HEAD is the implementation commit
   and becomes `implementation_commit` in review evidence.
7. Re-run the preceding stage's required verification and compare evidence. Any
   disagreement blocks; a recorded pass is not trusted without reproducibility.
8. Compute eligibility from status and prerequisites. It must equal the single
   `next_eligible_stage`; never select a later stage because it appears easy.
9. Confirm exact allowed paths and non-goals from `stages/<id>.md`.

## 2. Legal feature-stage transitions

| From | To | Authorized role and conditions |
|---|---|---|
| NOT_STARTED | IN_PROGRESS | IMPLEMENTER; uniquely eligible, clean known HEAD, lock acquired. |
| IN_PROGRESS | IMPLEMENTED | IMPLEMENTER; scoped change complete and evidence written. |
| IMPLEMENTED | VERIFIED | IMPLEMENTER; all required commands pass and evidence agrees. |
| IN_PROGRESS/IMPLEMENTED/VERIFIED | BLOCKED | Active role; structured blocker and handoff recorded. |
| VERIFIED | REVIEW_APPROVED | independent REVIEWER only; reviewer differs from implementer, committed implementation reviewed, reruns pass. |
| VERIFIED | REVIEW_REJECTED | independent REVIEWER only; findings and exact remediation scope recorded. |
| REVIEW_REJECTED | IN_PROGRESS | REMEDIATOR; rejection evidence read, same stage scope or narrower. |
| BLOCKED | IN_PROGRESS | appropriate role; blocker resolution is evidenced and prerequisites still approved. |
| NOT_STARTED/IN_PROGRESS/BLOCKED/REVIEW_REJECTED | SUPERSEDED | HUMAN_OWNER/architect via reviewed plan amendment. |

`REVIEW_APPROVED` is immutable except a reviewed plan amendment may mark it
`SUPERSEDED`; downstream approvals then cease to satisfy prerequisites. A stage
cannot transition directly from `IMPLEMENTED` to review disposition. A reviewer
cannot approve a stage it implemented or remediated. A remediation session
cannot alter the rejection finding or approve its fix.

`review_status` changes to `PENDING` when review starts, then `APPROVED` or
`REJECTED` alongside the stage status. `verification_status: PASSED` is required
for `VERIFIED` and approval. `implementation_commit` may be null in the
implementer's uncommitted handoff; the reviewer sets it to the clean HEAD it
actually reviewed before approval.

## 3. Commit boundaries

The feature process respects current governance: an agent does not infer commit
authority from a continuation prompt.

1. An implementation/remediation session leaves one scoped diff containing
   implementation, evidence, handoff and state through `VERIFIED`, then stops.
2. A human reviews and commits that exact diff.
3. An independent review session begins from that clean commit, writes review
   evidence and state disposition, then stops.
4. A human commits the review evidence/state.
5. The next implementation session begins at the resulting clean HEAD and
   records it as its expected base.

This two-commit pattern avoids circularly placing a commit's own OID inside its
contents. Review evidence binds the known implementation commit. The following
stage binds the known review commit as its base.

## 4. Implementation session

- Transition only the eligible stage to `IN_PROGRESS` and set actor/base.
- Implement only allowed paths; do not opportunistically fix unrelated issues.
- Add/update migration registry entries before schema changes are considered
  verified.
- Run focused then full specified checks.
- Write structured evidence and human-readable handoff.
- On success advance through `IMPLEMENTED` to `VERIFIED`; set review pending.
- On failure restore safe partial work or record `BLOCKED`; never claim a pass.
- Stop for human commit and independent review. Do not start the next stage.

## 5. Review session

- Require the stage `VERIFIED`, a clean implementation commit and different
  reviewer identity.
- Review only; do not silently repair. Check scope, public contracts, migrations,
  invariants, security implications, tests and rollback.
- Re-run required verification in a fresh environment where specified.
- Record `REVIEW_APPROVED` or `REVIEW_REJECTED` with exact findings and evidence.
- If approved, compute the next unique eligible stage but do not implement it.
- Stop for human commit of the review record/state.

## 6. Remediation, migration and release roles

A remediation session reads the rejection report, changes only the original or
narrower allowed scope, produces a new implementation ID/evidence and returns to
`VERIFIED`. It cannot erase prior evidence.

A migration session additionally requires migration registry state, dry-run
output, verified backup, clean repository and explicit approval named by its
stage. It performs only the selected migration and records rollback eligibility.

A release/closeout session is review-only until ORCH-027 explicitly authorizes a
canary. It checks every stage, migration, risk, threat-model and recovery drill;
it cannot waive a failed acceptance criterion.

### Governance-amendment authorization (ARCHITECT/HUMAN_OWNER)

A REMEDIATOR (or any IMPLEMENTER/REVIEWER) may never widen a stage's own
allowed paths, rewrite a stage specification, or edit `decision-log.md` under
its own authority, even when a rejection finding requires exactly that.
Encountering such a finding is a fail-closed stop (section 8): record
`BLOCKED` and hand off; do not amend the contract in the same session.

Only a session acting in role `ARCHITECT` or `HUMAN_OWNER` may author a
governance amendment that corrects a stage specification, the staged
implementation plan, `session-protocol.md` itself, or `architecture-v3.md`.
That session must:

1. Be an actor distinct from every IMPLEMENTER/REMEDIATOR/REVIEWER already
   recorded against the stage/finding being corrected — the same
   independence rule section 5 applies to review applies here to authorship.
2. Record one `implementation-state.yaml` `history` entry with
   `role: ARCHITECT` or `role: HUMAN_OWNER`, an action naming the amendment,
   and evidence pointing at a new architecture-amendment evidence record
   (below), in the same diff as the document edits it authorizes — never
   asserted after the fact without a durable record.
3. State, in that evidence record and in the `decision-log.md` entry, the
   exact closed list of paths the amendment may touch. No other path may
   change in the same diff.
4. Add exactly one new `decision-log.md` entry describing the amendment and,
   per that document's own header, increment `architecture_version` (a
   change to `architecture-v3.md`'s normative content) or `plan_version` (a
   change to `implementation-plan.md`, `session-protocol.md`, a
   `stages/*.md` file, or `decision-log.md` itself) — whichever document the
   amendment actually edits. `implementation-state.yaml` and
   `implementation-state.schema.yaml` must carry the same incremented value
   in the same diff; a version bump that leaves the schema's `const` stale
   is invalid.
5. State explicitly which prior remediation/implementation content the
   amendment ratifies unchanged, which it supersedes, and which must still
   be reapplied by a subsequent session. Ratified content is not restated;
   the amendment says so by reference and leaves it untouched.
6. Write architecture-amendment evidence
   (`evidence/<stage-id>/<amendment-id>.yaml`, a category distinct from
   implementation evidence, described in the stage's own lifecycle section)
   and a handoff (`handoffs/<stage-id>/<amendment-id>.md`) naming the exact
   next legal action and the exact actor-independence constraint for the
   next session.
7. Never itself advance a stage's `status` or `review_status` toward
   `VERIFIED` or any review disposition, and never approve, commit or push.
   An ARCHITECT/HUMAN_OWNER amendment re-opens or clarifies the contract;
   only a REMEDIATOR (section 6) and an independent REVIEWER (section 5) may
   move the stage itself.

This authorization is itself subject to the same fail-closed discipline as
any other write: missing independence, an undeclared path, a missing version
increment, or a missing history entry makes the amendment invalid and blocks
the next session from relying on it.

## 7. Evidence and handoff

Implementation evidence path:
`evidence/<stage-id>/<implementation-id>.yaml`.

Review evidence path: `reviews/<stage-id>/<review-id>.yaml`.

Handoff path: `handoffs/<stage-id>/<implementation-id>.md`.

IDs are collision-resistant (`YYYYMMDDTHHMMSSZ-<actor>-<8hex>`). YAML records
carry schema/version, repo/HEAD, role, commands as argv, exit results and content
digests. Never overwrite an evidence record; add a new one and append state
history. Handoff states what changed, paths, tests/results, decisions, risks,
blockers, schema/migrations, exact next legal action and exact continuation
prompt.

`ImplementationEvidence` 1.0.0 requires exactly: schema name/version, feature
and stage IDs, implementation ID, session/actor/role, started/finished times,
starting/ending HEAD, preflight tree/index/lock results, ordered changed paths,
ordered command records (`argv`, cwd, environment-fingerprint digest, exit code,
stdout/stderr artifact digests), test summary, decisions, unresolved risks,
blockers, schema changes, migration changes, resulting worktree digest and
handoff path. Unknown fields fail validation.

`ReviewEvidence` 1.0.0 requires exactly: schema name/version, feature/stage and
review IDs, reviewer identity/role, reviewed implementation IDs and commit,
independence declaration, scope-diff digest, ordered rerun command records,
checklist results, findings (`id`, severity, blocking, path/location, summary),
verdict, resulting state transition and review time. Verdict is only `APPROVED`
or `REJECTED`; unknown fields fail.

`HandoffRecord` 1.0.0 is Markdown with required headings: Summary, Changed
paths, Verification, Decisions, Schema and migrations, Risks, Blockers, Durable
state, Next legal action, and Exact continuation prompt. The evidence YAML binds
the handoff byte digest.

## 8. Exact fail-closed stops

Stop, make no production changes, and record `BLOCKED` when possible if:

- state/schema/stage spec is missing, malformed, unsupported or inconsistent;
- the design package is uncommitted or the tree/index is unexpectedly dirty;
- HEAD/branch/repository identity differs from the recorded/selected base;
- Git merge/rebase/cherry-pick/bisect or another feature session is active;
- previous evidence/review approval is absent, stale, self-approved or fails rerun;
- stage prerequisites or a required migration are incomplete;
- selected/requested stage is completed, non-eligible or ambiguous;
- required files, approval, tool/runtime or environment identity are absent;
- command results disagree with evidence;
- changed paths exceed the stage scope;
- a concurrent state edit, duplicate history sequence or stale state is found;
- recovery/publication artifacts indicate incomplete work.

Never infer success from absence of an error. If state cannot safely be updated
because the tree/state is unknown, emit a read-only blocker report to the user
instead of modifying it.

## 9. Status-only sessions

Status inspection acquires no write lock and changes nothing. It validates and
reports package status, HEAD/tree, current/candidate/next stage, prerequisite
closure, evidence/review/migration health and blockers. It must clearly label
derived conclusions and cannot repair state.
