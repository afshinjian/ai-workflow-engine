# Handoff: ORCH-003 implementation remediation — integrity/path-safety findings F-1..F-7 (IMPLEMENTER)

## Summary

Acting in role IMPLEMENTER (actor `claude-code-implementer-orch-003-1`, the same actor as
the original ORCH-003 implementation, still distinct from every actor recorded against
ORCH-000, ORCH-001, and ORCH-002), this session resumed ORCH-003 after a human
implementation review found the uncommitted diff incomplete: seven blocking integrity and
path-safety defects, F-1 through F-7. Nothing had been committed between the original
implementation and this remediation; `main` and `origin/main` remain
`e9f63a81041ba528055948890d5623087b62dae8` throughout, matching
`stages.ORCH-003.expected_base_head`.

**Findings addressed** (full text in `implementation-state.yaml`'s
`stages.ORCH-003.blockers[0]`; see `stages/ORCH-003.md`, `architecture-v3.md` sections 14
and 18, and `agents/artifacts.py`/`prompt/store.py`/`workflow/event_store.py`'s own
verified-load logic):

- **F-1 — source-root symlink traversal.** `discover_legacy_artifacts` called
  `Path.resolve()` (which follows symlinks) before checking whether the given root was
  itself a symlink. Fixed: a new `_reject_symlink_root` check (`Path.is_symlink()`, an
  `lstat` of the exact given path) runs first, before any `resolve()`/`exists()`/scan.
- **F-2 — companion symlink traversal.** A symlinked `.patch`/`.md` companion was read via
  plain `Path.read_bytes()`, following the symlink. Fixed: every companion read now goes
  through a new no-follow safe reader (`_read_regular_nofollow`: `os.open` with
  `O_NOFOLLOW` where supported, then `os.fstat` of the *opened descriptor* to reconfirm
  `S_ISREG`), closing the discovery-to-open TOCTOU window. A symlinked companion now
  quarantines the complete pair (`COMPANION_SYMLINK_NOT_ALLOWED` on the primary,
  `SYMLINK_NOT_ALLOWED` on the companion itself) and its target is never read.
- **F-3 — duplicate YAML keys.** Approval YAML was parsed with `yaml.safe_load`, whose
  default `SafeLoader` silently applies last-key-wins on a duplicate mapping key. Fixed: a
  new `_NoDuplicateKeySafeLoader` (a `SafeLoader` subclass overriding the mapping
  constructor) rejects a duplicate key at every nesting level, with a new
  `DUPLICATE_YAML_KEY` quarantine reason.
- **F-4 — incomplete backup/recovery plans.** A validly-paired companion was folded into
  its primary's classification and never given its own manifest/backup entry. Fixed:
  `LegacyArtifactRecord` gained `entry_type` (`file`/`symlink`/`unreadable`); every
  physical file — including a valid companion (new `agent-run-patch`/`prompt-markdown`
  kinds) — now gets its own entry; `BackupPlan`/`RecoveryPlan` gained
  `complete`/`incomplete_paths`, and `RecoveryStep.action` is type-aware
  (`restore_file` only for `entry_type == "file"`; `refuse_unsupported_entry_type`
  otherwise), so a symlink's target-string digest can never be restored as a regular file.
- **F-5 — digest seals not enforced.** The three models format-checked their digest
  fields (hex64) but never recomputed/verified them; `apply_migration` only compared
  caller-supplied digest strings. Fixed: `MigrationManifest`/`BackupPlan`/`RecoveryPlan`
  each gained a `model_validator(mode="after")` that recomputes its own digest from its
  current field values and rejects construction on mismatch — on every construction path,
  including `model_validate`/schema-registry dispatch. Every builder now computes the real
  digest from a plain dict *before* constructing the model exactly once (no
  placeholder-digest intermediate, per the finding's explicit instruction).
  `apply_migration` now forces a full `model_validate` round trip on all three arguments,
  so a `model_construct`-bypassed object is still caught, not merely a digest-string
  mismatch. All models are additionally `frozen=True`.
- **F-6 — incomplete legacy integrity validation.** Artifacts were classified `KNOWN` on
  schema validity alone. Fixed: agent-run records now check canonical bytes + terminal
  newline, no duplicate JSON keys, `run_id == compute_run_id(record)`, path/identity match
  (`run_id`/`project_id`/`stage`/`task_dir_name(task_id)`), `patch_sha256`, and
  `stdout_sha256`/`stderr_sha256` against decoded base64 — mirroring `load_run` exactly.
  Prompt metadata now recomputes the full deterministic rendering via `render_prompt` and
  checks recomputed metadata/`prompt_id`/Markdown bytes match — mirroring `load` exactly.
  Workflow-event directories are now validated as **one history group**: contiguous
  `00000001.json..` filenames, per-member canonical bytes, parent-digest chain (via
  `workflow.transitions.expected_stage`), and path identity; a single corrupt member now
  quarantines **every** member of that history, never just the offending one.
- **F-7 — concurrent mutation/TOCTOU, and apply-before-refusal.** `migrate apply` called
  `inspect_source` (reading the whole source tree) *before* checking `--dry-run`. Fixed:
  the CLI now checks `--dry-run` as the first statement in the command body, before
  `inspect_source` is ever called. Also fixed a workflow-history-specific TOCTOU: the
  directory listing is re-taken after every member is read and compared to the pre-read
  snapshot; a mismatch quarantines the whole group as `SOURCE_MUTATED_DURING_SCAN` rather
  than trusting a result assembled across two filesystem states.

  **A second, independently discovered gap of the same class as F-7/ORCH-002 Finding B**:
  proving the apply refusal with a permission-denied `--source` revealed that Click's
  `Path` parameter type checks `readable=True` (and would check `exists`) at
  argument-parsing time by default, *before* any command body runs — bypassing the JSON
  contract entirely (a raw `click` `UsageError`, stderr-only, exit 2) for a
  permission-denied path, regardless of `--contract-version`. Fixed by passing
  `exists=False, readable=False` on `SourceOption` in `cli.py`, deferring all
  existence/type/readability handling to `discover_legacy_artifacts`/`apply_migration`,
  which always emit through the stable v1/v2 contract.

**State lifecycle used**, per `session-protocol.md` section 2: `VERIFIED -> BLOCKED`
(history sequence 43, blocker `IMPLEMENTATION_REVIEW_INTEGRITY_PATH_SAFETY_GAP` recorded)
`-> IN_PROGRESS` (sequence 44, blocker `resolution` recorded in the same edit) `->
IMPLEMENTED` (sequence 45) `-> VERIFIED` (sequence 46). The existing implementation was
extended and corrected, not replaced.

**Verdict: implementation stops at `VERIFIED` again.** All required verification commands
pass; no blocker remains open. This session does not approve its own work.

## Changed paths

Modified again this round (all inside `stages/ORCH-003.md`'s allowed set):

- `src/ai_workflow_engine/migration/models.py` — `entry_type`, `EntryType`; nine new
  `QuarantineReason` values; `LegacyArtifactRecord`/`BackupPlanEntry`/`BackupPlan`/
  `RecoveryStep`/`RecoveryPlan`/`ApplyResult` all `frozen=True`; digest-seal
  `model_validator`s on `MigrationManifest`/`BackupPlan`/`RecoveryPlan`;
  `BackupPlan`/`RecoveryPlan` gained `incomplete_paths`/`complete`; `ApplyResult` gained
  `backup_complete`; `build_manifest` no longer uses a placeholder-digest + `model_copy`.
- `src/ai_workflow_engine/migration/legacy_readers.py` — near-total rewrite: `_reject_symlink_root`,
  `_open_regular_nofollow`/`_read_regular_nofollow`/`_read_or_none` (F-2/F-7 safe I/O),
  `_NoDuplicateKeySafeLoader` (F-3), per-family full integrity validators
  (`_validate_workflow_event_bytes`, `_validate_agent_run_bytes`,
  `_validate_prompt_metadata_bytes`) and history-group/pair classification functions
  (`_classify_workflow_history_group`, `_classify_agent_run_pair`,
  `_classify_prompt_pair`) replacing the old per-file/folding logic.
- `src/ai_workflow_engine/migration/plan.py` — `build_backup_plan`/`build_recovery_plan`
  rewritten for `entry_type`-aware, complete-coverage, digest-sealed construction.
- `src/ai_workflow_engine/migration/apply.py` — `apply_migration` now forces a full
  `model_validate` re-verification of all three arguments before trusting them.
- `src/ai_workflow_engine/cli.py` — `migrate apply` now checks `--dry-run` before calling
  `inspect_source`; `SourceOption` now passes `exists=False, readable=False`.
- `tests/test_migration_models.py`, `tests/test_migration_readers.py`,
  `tests/test_migration_plan_apply.py`, `tests/test_migration_cli.py` — extended/rewritten
  with regression tests for every finding (see Verification below).
- `docs/implementation/orchestration/implementation-state.yaml` — state transitions
  (history sequences 43–46), the blocker record, and `last_updated`.

Not modified: `src/ai_workflow_engine/migration/errors.py`,
`src/ai_workflow_engine/migration/inspect.py`,
`src/ai_workflow_engine/schema/migration.py` (unchanged from the original round).

Added (new, immutable):

- `docs/implementation/orchestration/evidence/ORCH-003/20260721T190000Z-claude-code-implementer-orch-003-1-b5f2e91a.yaml`
- `docs/implementation/orchestration/evidence/ORCH-003/logs/20260721T190000Z-claude-code-implementer-orch-003-1-b5f2e91a-*`
  (22 log/script artifacts)
- `docs/implementation/orchestration/handoffs/ORCH-003/20260721T190000Z-claude-code-implementer-orch-003-1-b5f2e91a.md`
  (this file)

**The original evidence record
(`evidence/ORCH-003/20260721T171500Z-...-a1b2c3d4.yaml`) and its handoff are byte-for-byte
unmodified** — this session adds a new record rather than overwriting them, per
`session-protocol.md` section 7. `migration-registry.yaml` remains untouched: all three
entries still `owner_stage: ORCH-026`, `status: PLANNED`.

## Verification

| Command | Result |
|---|---|
| `git rev-parse HEAD` / `origin/main` | both `e9f63a81041ba528055948890d5623087b62dae8`, unchanged throughout |
| `pytest -q tests/test_migration*.py` | **126 passed** (up from 79) |
| `pytest -q -rs` (full) | **950 passed, 0 skipped** (up from 902 passed / 1 skipped) |
| `ruff check` (every changed/added file) | clean |
| `black --check` (same files) | clean |
| `mypy src` | `Success: no issues found in 55 source files` |
| `python scripts/orchestration_feature_state.py validate ...` (after this edit) | PASS, `state_digest sha256:b7299d9ec3cdc9212be4a443ebf96ab185e8536c9f23c526b7a97f241801f563` |
| `python scripts/orchestration_feature_state.py status ...` | `current_stage`/`next_eligible_stage`/`candidate_next_stage` all `ORCH-003`; `ORCH-003.status VERIFIED`, `blockers_open: []`; `ORCH-004.status NOT_STARTED` |
| `workflowctl verify --config self-governance.yaml --output json` | PASS |
| `git diff --check` | clean |

**47 new/rewritten tests** across the four files cover every finding, including:
adversarial reproductions of a symlinked source root (`os.scandir` guarded to raise if
invoked), a symlinked `.patch`/`.md` companion (secret target content asserted absent from
every quarantine detail), duplicate top-level and nested YAML keys, exact backup-coverage
comparison against an independently-enumerated physical file listing, tampered
manifest/backup/recovery digests (including a `model_construct`-bypassed object caught
only by `apply_migration`'s re-verification), full agent-run/prompt/workflow-event
integrity chains (address mismatch, content-hash mismatch, canonical-form mismatch), a
corrupted history member quarantining its independently-valid-looking siblings, a
monkeypatched mid-scan directory mutation (`SOURCE_MUTATED_DURING_SCAN`), and `migrate
apply` refusing with a missing/unreadable/instrumented source and an unsupported `--to`.

An independent, disposable-fixture adversarial demonstration script — not part of the
pytest suite — was written and run
(`evidence/ORCH-003/logs/20260721T190000Z-...-b5f2e91a-adversarial-remediation-demo.py`,
`...-adversarial-remediation-demo-output.txt`,
`ORCH003_REMEDIATION_DEMO: ALL_CHECKS_PASS`), independently reproducing all seven
findings' fixes outside the test suite.

## Decisions

See `implementation-state.yaml`'s `stages.ORCH-003.blockers[0].resolution` for the
complete per-finding technical resolution text (reproduced in condensed form in this
handoff's Summary above). Key cross-cutting decisions:

- **A companion is never "folded" into its primary's record; every physical file gets its
  own manifest entry.** This is the direct fix for F-4 and also makes F-2's "quarantine
  the complete pair" property observable in the manifest itself (two records, not one).
- **`entry_type` is a first-class field**, not inferred implicitly, so backup/recovery
  logic can be exhaustive and type-safe by construction (`RecoveryStep`'s own validator
  rejects `restore_file` for a non-`"file"` entry type) rather than by convention.
- **Digest seals are validators, not builder-time assertions.** Placing the recompute-and-
  verify check in `model_validator(mode="after")` means it protects every future
  construction path automatically (including ones this stage didn't anticipate), not just
  `build_manifest`/`build_backup_plan`/`build_recovery_plan`.
- **`apply_migration`'s re-verification uses `model_validate`, not a hand-rolled digest
  recompute**, so it automatically benefits from every validator already defined on the
  three models (including future ones), and exercises the exact same code path a
  schema-registry dispatch would.
- **The workflow-history TOCTOU check re-lists rather than re-hashing everything**: a
  changed *name set* is sufficient evidence of a possibly-inconsistent scan; re-hashing
  already-read bytes would not detect a benign concurrent write that happened to produce
  identical content, but a changed *directory listing* is the actual signal of a
  potentially different filesystem epoch.

## Schema and migrations

**Schema changed**: `migration-manifest`, `migration-backup-plan`, `migration-recovery-plan`
remain version `1.0.0` (Pydantic-level field additions — `entry_type`,
`incomplete_paths`, `complete`, `backup_complete` — and new validators; no field was
removed or reinterpreted, and no prior valid payload becomes invalid by field removal, but
every prior payload now additionally requires the new required fields and must satisfy the
digest-seal validator, so this is a breaking shape change in practice). Since ORCH-003 has
not yet been reviewed/approved, no consumer outside this stage's own tests/CLI exists yet,
so no migration or compatibility shim is required; this is captured as a normal revision
of an as-yet-unapproved contract.

**Migrations**: none; `migration-registry.yaml` is untouched. All three registered entries
remain owned by `ORCH-026`.

## Risks

No new risk introduced. The stage's own documented risk ("Unknown legacy variants") is
now more thoroughly mitigated: unknown/corrupt/mixed-version/inconsistent input is
quarantined with one of 23 stable, specific reasons (up from 14), and a corrupt history
member no longer lets its siblings escape quarantine. The four pre-existing
`unresolved_risks` entries and the closed-on-substance `R-ORCH-001-VALIDATOR-CORRECTNESS`
are carried forward unchanged; none is affected by this stage's scope.

## Blockers

`stages.ORCH-003.blockers` now contains one entry
(`IMPLEMENTATION_REVIEW_INTEGRITY_PATH_SAFETY_GAP`), introduced and resolved within this
same session (history sequences 43–44), with `resolution` populated describing every
fix. Top-level `blockers` remains `[]`. No blocker is open.

## Durable state

- `stages.ORCH-003.status`: `VERIFIED` → **`BLOCKED`** → **`IN_PROGRESS`** →
  **`IMPLEMENTED`** → **`VERIFIED`** (history sequences 43–46).
- `stages.ORCH-003.blockers`: one resolved `IMPLEMENTATION_REVIEW_INTEGRITY_PATH_SAFETY_GAP` entry.
- `stages.ORCH-003.evidence`: the original evidence YAML, plus **this session's new
  evidence YAML** appended.
- `stages.ORCH-003.handoff`: → **this handoff** (the prior handoff remains on disk,
  unmodified, referenced by the prior evidence record).
- `stages.ORCH-003.implementer` / `review_status` / `reviewer` / `verification_status` /
  `implementation_commit` / `expected_base_head`: unchanged
  (`claude-code-implementer-orch-003-1` / `PENDING` / `null` / `PASSED` / `null` /
  `e9f63a81041ba528055948890d5623087b62dae8`).
- `current_stage` / `candidate_next_stage` / `next_eligible_stage`: unchanged at
  `ORCH-003` (`VERIFIED` is not `REVIEW_APPROVED`).
- `history`: four new entries, sequences 43–46.
- **`ORCH-004` status remains `NOT_STARTED`.**
- `migration-registry.yaml`: unchanged; all three entries remain owned by `ORCH-026`.
- Nothing was committed and nothing was pushed.

## Next legal action

A human commits this implementation diff (production changes + extended tests + this
evidence/handoff + `implementation-state.yaml`). The next session is then an
**independent ORCH-003 REVIEWER**, in a fresh session distinct from
`claude-code-implementer-orch-003-1` and every actor recorded against
ORCH-000/ORCH-001/ORCH-002, beginning from the resulting clean HEAD, setting
`stages.ORCH-003.implementation_commit` to that HEAD, re-running every stage-required
verification command, independently reproducing the F-1 through F-7 fixes (not merely
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
docs/implementation/orchestration/stages/ORCH-003.md, both ORCH-003 evidence records and
both handoffs
(evidence/ORCH-003/20260721T171500Z-claude-code-implementer-orch-003-1-a1b2c3d4.yaml,
evidence/ORCH-003/20260721T190000Z-claude-code-implementer-orch-003-1-b5f2e91a.yaml,
handoffs/ORCH-003/20260721T171500Z-claude-code-implementer-orch-003-1-a1b2c3d4.md,
handoffs/ORCH-003/20260721T190000Z-claude-code-implementer-orch-003-1-b5f2e91a.md), and
the full changed source: src/ai_workflow_engine/migration/,
src/ai_workflow_engine/schema/migration.py, src/ai_workflow_engine/cli.py,
tests/test_migration_models.py, tests/test_migration_readers.py,
tests/test_migration_plan_apply.py, tests/test_migration_cli.py.

Confirm this IMPLEMENTER diff (history sequences 43-46) is committed, HEAD matches
origin/main with a clean tree, ORCH-003 is VERIFIED with review_status PENDING and its
blocker resolved, migration-registry.yaml is unchanged (all entries still owned by
ORCH-026), and ORCH-004 is still NOT_STARTED. Act as an independent ORCH-003 REVIEWER, in
a session distinct from claude-code-implementer-orch-003-1. Re-run every stage-required
verification command from the committed implementation HEAD, review the full diff (both
rounds) against stages/ORCH-003.md's allowed paths and architecture-v3.md sections 14 and
18, independently verify that findings F-1 through F-7 from the prior human review are
genuinely fixed (not merely asserted) -- including reproducing the adversarial symlink,
duplicate-key, tamper, and TOCTOU scenarios yourself -- set implementation_commit to the
exact reviewed HEAD, and record REVIEW_APPROVED or REVIEW_REJECTED with exact findings
and evidence. Do not commit, do not push, and do not implement ORCH-004.
```
