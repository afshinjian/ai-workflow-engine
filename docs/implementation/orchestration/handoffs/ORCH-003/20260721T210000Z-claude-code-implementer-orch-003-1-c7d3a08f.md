# Handoff: ORCH-003 implementation remediation — unsupported-entry and TOCTOU findings F-8/F-9 (IMPLEMENTER)

## Summary

Acting in role IMPLEMENTER (actor `claude-code-implementer-orch-003-1`, the same actor as
both prior ORCH-003 rounds, still distinct from every actor recorded against ORCH-000,
ORCH-001, and ORCH-002), this session resumed ORCH-003 after a further human
implementation review found two more blocking findings, F-8 and F-9. Nothing had been
committed between any of the three rounds; `main` and `origin/main` remain
`e9f63a81041ba528055948890d5623087b62dae8` throughout, matching
`stages.ORCH-003.expected_base_head`.

**Findings addressed** (full text in `implementation-state.yaml`'s
`stages.ORCH-003.blockers[1]`):

- **F-8 (HIGH) — unsupported filesystem entries silently omitted.** `_iter_entries_safe`
  only classified entries that were a regular file, a directory, or a symlink; a FIFO,
  Unix socket, or device node placed anywhere under the source root (e.g.
  `state/p/t/00000001.json`) produced no manifest artifact at all, and
  `build_backup_plan` incorrectly reported `complete=True` with no `incomplete_paths`
  even though a real physical entry was never captured. Fixed: `_iter_entries_safe` now
  yields a `(path, abs_path, kind)` triple, `kind` one of `"file"`/`"symlink"`/
  `"unsupported"`, instead of a symlink-only boolean; anything that is none of
  file/directory/symlink is classified via a new `_classify_unsupported` helper that
  determines the entry's type **solely from a no-follow `lstat`**
  (`os.DirEntry.stat(follow_symlinks=False)` / `os.lstat`) and **never opens it** — a
  FIFO can therefore never block the scan waiting for a writer, and a socket/device node
  is never connected to or read. A new `EntryType` value `"unsupported"` and
  `QuarantineReason` `"UNSUPPORTED_ENTRY_TYPE"` were added.
  `build_backup_plan`/`build_recovery_plan` now exclude `"unsupported"` entries from
  `entries` the same way they already excluded `"unreadable"` ones (added to
  `incomplete_paths`, `complete=False`); `BackupPlanEntry`'s own validator structurally
  forbids ever representing one, so it can never receive a `restore_file` recovery step.
- **F-9 (HIGH) — same-name content mutation undetected.** Mutation detection (F-7) only
  compared the directory's *filename set* after reading; a same-path, same-filename
  content change occurring during inspection was not caught — a record could still be
  classified `KNOWN` carrying a digest that no longer matched the file's actual on-disk
  bytes. Fixed: a new `_verify_unchanged(path, expected_bytes)` helper re-reads a path one
  final time via the exact same safe no-follow reader used for every other read in this
  module, and every family that can return `KNOWN` now calls it on each of its members
  immediately before returning — approvals (single file), agent-run and prompt pairs
  (both members), and workflow-event history groups (every member, added **alongside**,
  not instead of, the pre-existing F-7 directory-listing re-check). Any mismatch —
  content changed, the path vanished, or it raced into becoming a symlink (never
  followed) — quarantines the affected member(s) `SOURCE_MUTATED_DURING_SCAN` instead of
  returning a possibly-stale `KNOWN` result. The digest/model used for a successful
  `KNOWN` classification is always the **first** read's bytes (the verification read is
  comparison-only), so stable inputs are provably unaffected — every one of this stage's
  126 pre-existing tests still passes verbatim.

**F-1 through F-7 were preserved, not weakened or re-litigated**: all 126 tests from the
prior remediation round still pass unmodified, and only three production files changed
this round — `models.py`, `legacy_readers.py`, and `plan.py`. `apply.py`, `errors.py`,
`inspect.py`, `schema/migration.py`, and `cli.py` are byte-identical to the prior round.

**State lifecycle used**, per `session-protocol.md` section 2: `VERIFIED -> BLOCKED`
(history sequence 47, blocker `IMPLEMENTATION_REVIEW_UNSUPPORTED_ENTRY_AND_TOCTOU_GAP`
recorded) `-> IN_PROGRESS` (sequence 48, resolution recorded in the same edit) `->
IMPLEMENTED` (sequence 49) `-> VERIFIED` (sequence 50).

**Verdict: implementation stops at `VERIFIED` again.** All required verification commands
pass; no blocker remains open. This session does not approve its own work.

## Changed paths

Modified again this round (all inside `stages/ORCH-003.md`'s allowed set):

- `src/ai_workflow_engine/migration/models.py` — `EntryType` gained `"unsupported"`;
  `QuarantineReason` gained `"UNSUPPORTED_ENTRY_TYPE"`; `LegacyArtifactRecord`'s
  consistency validator and `BackupPlanEntry`'s readable-entry-type validator both extended.
- `src/ai_workflow_engine/migration/legacy_readers.py` — `_iter_entries_safe`'s yield
  shape changed to a `kind` string (`"file"`/`"symlink"`/`"unsupported"`); new
  `_describe_unsupported_entry`/`_classify_unsupported` (F-8); new `_verify_unchanged`
  (F-9), called at the end of `_classify_approval_entry`, `_classify_agent_run_pair`,
  `_classify_prompt_pair`, and appended to `_classify_workflow_history_group`'s existing
  post-read consistency phase; `discover_legacy_artifacts`'s main loop updated for the
  new `kind` values.
- `src/ai_workflow_engine/migration/plan.py` — `build_backup_plan` now also excludes
  `entry_type == "unsupported"` (alongside the pre-existing `"unreadable"` exclusion).
- `tests/test_migration_models.py` — (no changes this round; existing tests already
  cover the extended validators via the pre-existing `EntryType`/`QuarantineReason`
  parametrization patterns; new invariants are exercised through the reader/plan tests
  below, which is where the new behavior is actually produced).
- `tests/test_migration_readers.py` — 13 new tests: F-8 (FIFO never opened/blocks, a
  real AF_UNIX socket where the platform supports it, manifest/backup representation,
  existing regular-file/symlink behavior unchanged alongside an unsupported entry) and
  F-9 (workflow-event/agent-run primary+companion/prompt primary+companion/approval
  content-mutation fault injection, a regular-file-replaced-by-symlink race, and a
  stable-input determinism/digest-accuracy check).
- `tests/test_migration_plan_apply.py` — 1 new test: backup/recovery completeness
  reporting for an unsupported entry.
- `tests/test_migration_cli.py` — (no changes this round; F-8/F-9 are reader-level
  findings with no CLI-contract-shape implications beyond the already-tested
  `entry_type`/`complete` fields already exercised in the prior round's CLI tests).
- `docs/implementation/orchestration/implementation-state.yaml` — state transitions
  (history sequences 47–50), the new blocker record, and `last_updated`.

Not modified: `src/ai_workflow_engine/migration/__init__.py`,
`src/ai_workflow_engine/migration/errors.py`, `src/ai_workflow_engine/migration/apply.py`,
`src/ai_workflow_engine/migration/inspect.py`, `src/ai_workflow_engine/schema/migration.py`,
`src/ai_workflow_engine/cli.py` (byte-identical to the prior round; still shows in `git
diff --name-only` because it was modified relative to `HEAD`, not relative to the prior
round).

Added (new, immutable):

- `docs/implementation/orchestration/evidence/ORCH-003/20260721T210000Z-claude-code-implementer-orch-003-1-c7d3a08f.yaml`
- `docs/implementation/orchestration/evidence/ORCH-003/logs/20260721T210000Z-claude-code-implementer-orch-003-1-c7d3a08f-*`
  (16 log/script artifacts)
- `docs/implementation/orchestration/handoffs/ORCH-003/20260721T210000Z-claude-code-implementer-orch-003-1-c7d3a08f.md`
  (this file)

**Both prior evidence records
(`evidence/ORCH-003/20260721T171500Z-...-a1b2c3d4.yaml`,
`evidence/ORCH-003/20260721T190000Z-...-b5f2e91a.yaml`) and both prior handoffs are
byte-for-byte unmodified** — this session adds a third record rather than overwriting
them, per `session-protocol.md` section 7. `migration-registry.yaml` remains untouched:
all three entries still `owner_stage: ORCH-026`, `status: PLANNED`.

## Verification

| Command | Result |
|---|---|
| `git rev-parse HEAD` / `origin/main` | both `e9f63a81041ba528055948890d5623087b62dae8`, unchanged throughout |
| `pytest -q tests/test_migration*.py` | **139 passed** (up from 126) |
| `pytest -q -rs` (full, before and after the state edit) | **963 passed, 0 skipped** (up from 950), identical both times |
| `ruff check` (the exact required file set) | clean |
| `black --check` (same set) | clean |
| `mypy src` | `Success: no issues found in 55 source files` |
| `python scripts/orchestration_feature_state.py validate ...` (after this edit) | PASS, `state_digest sha256:ecf82903b95884e46d16f3ae866d40537bdb8fb17f4215c9e60e845c4ce4ea21` |
| `python scripts/orchestration_feature_state.py status ...` | `current_stage`/`next_eligible_stage`/`candidate_next_stage` all `ORCH-003`; `ORCH-003.status VERIFIED`, `blockers_open: []`; `ORCH-004.status NOT_STARTED` |
| `workflowctl verify --config self-governance.yaml --output json` | PASS |
| `git diff --check` | clean |
| `git status --short` | 2 modified (`implementation-state.yaml`, `cli.py`), 6 untracked top-level entries |

**14 new tests** across two files:

- F-8: a real FIFO (`os.mkfifo`) and, where the platform supports it, a real `AF_UNIX`
  socket, each run on a **daemon thread with a timeout** so a regression that ever opens
  either fails the assertion instead of hanging the whole test run; manifest/backup
  representation and `incomplete_paths`/`complete=False` reporting; recovery never
  emitting `restore_file` for it; existing regular-file/symlink classification
  demonstrated unchanged alongside an unsupported sibling.
- F-9: a deterministic, non-threaded fault-injection helper
  (`_inject_mutation_after_first_read`) that monkeypatches the shared `_read_or_none`
  primitive to mutate the real file on disk immediately after its first successful read
  for a specific path returns — covering a workflow-event primary (its unrelated,
  independently-valid sibling in the same history is also quarantined, since the whole
  history shares one fate), an agent-run primary, an agent-run companion, a prompt
  primary, a prompt companion, an approval file, and a regular file replaced by a
  symlink mid-inspection (target content asserted absent from the resulting
  `quarantine_detail`); plus a stable-input test proving unchanged determinism and exact
  digest accuracy.

An independent, disposable-fixture adversarial demonstration script — not part of the
pytest suite — was written and run
(`evidence/ORCH-003/logs/20260721T210000Z-...-c7d3a08f-adversarial-f8-f9-demo.py`,
`...-adversarial-f8-f9-demo-output.txt`, `ORCH003_F8_F9_DEMO: ALL_CHECKS_PASS`),
independently reproducing both findings' fixes outside the test suite.

## Decisions

- **F-8's type detection uses only a no-follow `lstat`, never an `open()`.** This is the
  only way to determine an entry's type without any risk of blocking (FIFO) or hanging a
  connection attempt (socket) — the finding's own required property.
- **`"unsupported"` is treated identically to `"unreadable"` everywhere completeness is
  computed** (excluded from `BackupPlan.entries`, added to `incomplete_paths`,
  `complete=False`), rather than inventing a parallel completeness concept — both
  represent "no genuine bytes were ever obtained for this entry," just for different
  reasons (never attempted vs. attempted and failed).
- **F-9's verification is placed at the very end of each family's happy path**, right
  before the `KNOWN` records are constructed, rather than immediately after each
  individual read. This covers the *entire* validation window for that member (parsing,
  schema validation, cross-checks, deterministic re-rendering for prompts) with a single
  final check, rather than requiring a narrower check after every intermediate step.
- **The digest used for a `KNOWN` record is always the first read's bytes, never the
  verification read's.** The verification read exists purely to *compare*, not to
  *replace* the bytes already used to build the record — this is what makes the fix
  provably non-disruptive to the stable case (same digest as before, on every one of the
  126 pre-existing tests).
- **The workflow-history group gets a *second*, separate post-scan phase for F-9**
  (content re-verification), added after the pre-existing F-7 phase (directory-listing
  re-check), rather than merging the two into one loop — they detect genuinely different
  things (a changed *name set* vs. changed *bytes at an unchanged name*) and keeping them
  as two distinct, sequential, independently-testable checks is clearer than one combined
  one.
- **The F-9 fault-injection test helper mutates the real file directly** (via a
  monkeypatched shared primitive triggered by call count) **rather than using threads**,
  making every test fully deterministic and eliminating any possibility of test flakiness
  from timing.

## Schema and migrations

**Schema changed**: `migration-manifest` gains the `"unsupported"` `EntryType` value and
`"UNSUPPORTED_ENTRY_TYPE"` `QuarantineReason` (both are Python `Literal` extensions on
already-open-ended-by-design fields, not new required fields); `migration-backup-plan`/
`migration-recovery-plan` gain no new fields this round (the existing
`incomplete_paths`/`complete` fields from the prior round already accommodate the new
entry type without a shape change). All three remain version `1.0.0`. Since ORCH-003 has
not yet been reviewed/approved, no external consumer exists yet, so no migration or
compatibility shim is required.

**Migrations**: none; `migration-registry.yaml` is untouched. All three registered
entries remain owned by `ORCH-026`.

## Risks

No new risk introduced. The stage's own documented risk ("Unknown legacy variants") is
now even more thoroughly mitigated: every physical filesystem entry reachable from the
source root is now represented in the manifest or causes an explicit quarantine, and a
same-path content mutation during inspection can no longer produce a stale `KNOWN`
result. The four pre-existing `unresolved_risks` entries and the closed-on-substance
`R-ORCH-001-VALIDATOR-CORRECTNESS` are carried forward unchanged; none is affected by
this stage's scope.

## Blockers

`stages.ORCH-003.blockers` now contains two entries:
`IMPLEMENTATION_REVIEW_INTEGRITY_PATH_SAFETY_GAP` (F-1..F-7, resolved in the prior
round) and `IMPLEMENTATION_REVIEW_UNSUPPORTED_ENTRY_AND_TOCTOU_GAP` (F-8/F-9, introduced
and resolved within this same session, history sequences 47–48), both with `resolution`
populated. Top-level `blockers` remains `[]`. No blocker is open.

## Durable state

- `stages.ORCH-003.status`: `VERIFIED` → **`BLOCKED`** → **`IN_PROGRESS`** →
  **`IMPLEMENTED`** → **`VERIFIED`** (history sequences 47–50).
- `stages.ORCH-003.blockers`: two entries, both resolved.
- `stages.ORCH-003.evidence`: both prior evidence YAMLs, plus **this session's new
  evidence YAML** appended (3 total).
- `stages.ORCH-003.handoff`: → **this handoff** (both prior handoffs remain on disk,
  unmodified, referenced by their own evidence records).
- `stages.ORCH-003.implementer` / `review_status` / `reviewer` / `verification_status` /
  `implementation_commit` / `expected_base_head`: unchanged
  (`claude-code-implementer-orch-003-1` / `PENDING` / `null` / `PASSED` / `null` /
  `e9f63a81041ba528055948890d5623087b62dae8`).
- `current_stage` / `candidate_next_stage` / `next_eligible_stage`: unchanged at
  `ORCH-003` (`VERIFIED` is not `REVIEW_APPROVED`).
- `history`: four new entries, sequences 47–50.
- **`ORCH-004` status remains `NOT_STARTED`.**
- `migration-registry.yaml`: unchanged; all three entries remain owned by `ORCH-026`.
- Nothing was committed and nothing was pushed.

## Next legal action

A human commits this implementation diff (all three rounds' production changes + tests +
all evidence/handoffs + `implementation-state.yaml`). The next session is then an
**independent ORCH-003 REVIEWER**, in a fresh session distinct from
`claude-code-implementer-orch-003-1` and every actor recorded against
ORCH-000/ORCH-001/ORCH-002, beginning from the resulting clean HEAD, setting
`stages.ORCH-003.implementation_commit` to that HEAD, re-running every stage-required
verification command, independently reproducing the F-1 through F-9 fixes (not merely
trusting this evidence), confirming only `stages/ORCH-003.md`'s allowed paths changed and
`migration-registry.yaml` is untouched, and recording `REVIEW_APPROVED` or
`REVIEW_REJECTED` in a new `reviews/ORCH-003/<review-id>.yaml`. Per `session-protocol.md`
section 4, this implementer session does not start ORCH-004.

## Exact continuation prompt

```
Work in /home/afshin-jian/ai-workflow-engine. Do not rely on chat history.
Read README.md, self-governance.yaml, docs/AGENT_PROTOCOL.md,
docs/implementation/orchestration/session-protocol.md,
docs/implementation/orchestration/architecture-v3.md,
docs/implementation/orchestration/implementation-plan.md,
docs/implementation/orchestration/implementation-state.schema.yaml,
docs/implementation/orchestration/implementation-state.yaml,
docs/implementation/orchestration/migration-registry.yaml,
docs/implementation/orchestration/stages/ORCH-003.md, all three ORCH-003 evidence
records and all three handoffs, and the full changed source:
src/ai_workflow_engine/migration/, src/ai_workflow_engine/schema/migration.py,
src/ai_workflow_engine/cli.py, tests/test_migration_models.py,
tests/test_migration_readers.py, tests/test_migration_plan_apply.py,
tests/test_migration_cli.py.

Confirm this IMPLEMENTER diff (history sequences 47-50) is committed, HEAD matches
origin/main with a clean tree, ORCH-003 is VERIFIED with review_status PENDING and both
blockers resolved, migration-registry.yaml is unchanged (all entries still owned by
ORCH-026), and ORCH-004 is still NOT_STARTED. Act as an independent ORCH-003 REVIEWER, in
a session distinct from claude-code-implementer-orch-003-1. Re-run every stage-required
verification command from the committed implementation HEAD, review the full diff (all
three rounds) against stages/ORCH-003.md's allowed paths and architecture-v3.md sections
14 and 18, independently verify that findings F-1 through F-9 are genuinely fixed (not
merely asserted) -- including reproducing the adversarial symlink, duplicate-key, tamper,
TOCTOU, unsupported-entry-type, and same-filename-mutation scenarios yourself -- set
implementation_commit to the exact reviewed HEAD, and record REVIEW_APPROVED or
REVIEW_REJECTED with exact findings and evidence. Do not commit, do not push, and do not
implement ORCH-004.
```
