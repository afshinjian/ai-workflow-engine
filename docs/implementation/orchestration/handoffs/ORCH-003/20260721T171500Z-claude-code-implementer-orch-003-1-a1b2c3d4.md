# Handoff: ORCH-003 implementation — legacy readers and migration framework (IMPLEMENTER)

## Summary

Acting in role IMPLEMENTER (actor `claude-code-implementer-orch-003-1`, distinct from
every actor recorded against ORCH-000, ORCH-001, and ORCH-002), this session implemented
the additive legacy-reader and dry-run migration framework described by
`architecture-v3.md` sections 14 and 18, as scoped by `stages/ORCH-003.md`.

Preflight confirmed `main == origin/main == HEAD e9f63a81041ba528055948890d5623087b62dae8`
("docs: approve ORCH-002"), a clean tree/index, no in-progress Git operation or feature
lock, ORCH-002 `REVIEW_APPROVED` with committed evidence, ORCH-003 the unique
`NOT_STARTED` `next_eligible_stage`, and ORCH-004 `NOT_STARTED`. That HEAD is recorded as
`stages.ORCH-003.expected_base_head`.

**State lifecycle used**, per `session-protocol.md` section 2: `NOT_STARTED -> IN_PROGRESS`
(history sequence 40) `-> IMPLEMENTED` (sequence 41) `-> VERIFIED` (sequence 42).

**Verdict: implementation stops at `VERIFIED`.** All required verification commands pass;
no blocker was raised. This session does not approve its own work.

## Changed paths

New (all inside `stages/ORCH-003.md`'s allowed `src/ai_workflow_engine/migration/` path):

- `src/ai_workflow_engine/migration/__init__.py`
- `src/ai_workflow_engine/migration/errors.py` — `MigrationError` and three typed
  subclasses (mirrors `ArtifactError`/`PromptStorageError`/`ApprovalError`'s local
  `ValueError`-subclass pattern, not `WorkflowEngineError`).
- `src/ai_workflow_engine/migration/models.py` — `LegacyArtifactRecord`,
  `MigrationManifest`, `BackupPlanEntry`/`BackupPlan`, `RecoveryStep`/`RecoveryPlan`,
  `ApplyResult` (schema `1.0.0` each where architecture-required), plus
  `content_digest`/`build_manifest`.
- `src/ai_workflow_engine/migration/legacy_readers.py` — symlink-safe, never-guessing
  discovery/classification of legacy artifacts under a source root.
- `src/ai_workflow_engine/migration/inspect.py` — `inspect_source`,
  `resolve_migration_target`, `default_migration_source`.
- `src/ai_workflow_engine/migration/plan.py` — `build_backup_plan`, `build_recovery_plan`.
- `src/ai_workflow_engine/migration/apply.py` — `apply_migration` (real apply refused).

New (schema adapter, inside the allowed `src/ai_workflow_engine/schema/` path):

- `src/ai_workflow_engine/schema/migration.py` — registers `migration-manifest`,
  `migration-backup-plan`, `migration-recovery-plan` at `1.0.0` in a new
  `MIGRATION_SCHEMA_REGISTRY`.

Modified (inside the allowed `cli.py` path):

- `src/ai_workflow_engine/cli.py` — added imports and a new `migrate` Typer sub-app
  (`migrate inspect|plan|apply`). No existing command's code path was touched.

New (inside the allowed `tests/test_migration*.py` path):

- `tests/test_migration_models.py` (23 tests) — model invariants, digest determinism,
  schema-registry round trip.
- `tests/test_migration_readers.py` (30 tests) — known-artifact classification (built
  with the real, existing writers under an isolated `$HOME`), every quarantine reason,
  byte/digest preservation, determinism, concurrency, symlink/path safety, fault
  injection.
- `tests/test_migration_plan_apply.py` (9 tests) — write-safety snapshots, refusal,
  plan/backup/recovery determinism and content-addressing.
- `tests/test_migration_cli.py` (18 tests) — v1/v2 CLI contract, single-JSON-document
  purity under `FORCE_COLOR`, apply refusal, empty input, real-governance-file
  invariance.

Modified (state):

- `docs/implementation/orchestration/implementation-state.yaml` — `ORCH-003` stage
  record, history sequences 40–42, `last_updated`.

Added (new, immutable evidence):

- `docs/implementation/orchestration/evidence/ORCH-003/20260721T171500Z-claude-code-implementer-orch-003-1-a1b2c3d4.yaml`
- `docs/implementation/orchestration/evidence/ORCH-003/logs/20260721T171500Z-claude-code-implementer-orch-003-1-a1b2c3d4-*`
  (18 log/script artifacts)
- `docs/implementation/orchestration/handoffs/ORCH-003/20260721T171500Z-claude-code-implementer-orch-003-1-a1b2c3d4.md`
  (this file)

**Not touched**: `migration-registry.yaml` (read, not modified — all three existing
entries remain owned by `ORCH-026`, `status: PLANNED`); every `stages/*.md` file;
`session-protocol.md`; `architecture-v3.md`; `implementation-plan.md`;
`implementation-state.schema.yaml`; `scripts/orchestration_feature_state.py`;
`tests/test_orchestration_feature_state.py`; `tests/test_cli_contract_v2.py`; every
ORCH-000/ORCH-001/ORCH-002 record; `src/ai_workflow_engine/models.py`; `config.py`;
`exceptions.py`.

## Verification

| Command | Result |
|---|---|
| `git rev-parse HEAD` / `origin/main` | both `e9f63a81041ba528055948890d5623087b62dae8`, unchanged throughout |
| `pytest -q tests/test_migration*.py` | **79 passed** |
| `pytest -q -rs` (full, after the state edit) | **903 passed, 0 skipped** (up from 824 passed / 0 skipped before ORCH-003; an intermediate mid-session run taken *before* the `implementation-state.yaml` edit showed 902 passed / 1 skipped — the pre-existing ORCH-001 O-1 skip is dynamic and was still armed while ORCH-003 was `NOT_STARTED`; it disarmed itself the moment ORCH-003 reached `VERIFIED`, exactly as documented at that skip's own definition) |
| `ruff check` (every changed/added `.py` file) | clean |
| `black --check` (same files) | clean |
| `mypy src` | `Success: no issues found in 55 source files` (one union-typed-variable assignment error found and fixed in the approval-kind dispatch) |
| `python scripts/orchestration_feature_state.py validate ...` (after this edit) | PASS, `state_digest sha256:32d2568f93896a9576812292d2ce47a5eeb09fb4c161eb4e152bd628c5a0cd25` |
| `python scripts/orchestration_feature_state.py status ...` (after this edit) | `current_stage`/`next_eligible_stage`/`candidate_next_stage` all `ORCH-003`; `ORCH-003.status VERIFIED`, `review_status PENDING`; `ORCH-004.status NOT_STARTED` |
| `workflowctl verify --config self-governance.yaml --output json` | PASS |
| `git diff --check` | clean |
| `git diff --name-only` (after this edit) | exactly `docs/implementation/orchestration/implementation-state.yaml`, `src/ai_workflow_engine/cli.py` — every other change is a new file inside this stage's allowed paths |

An independent, disposable-fixture demonstration script — not part of the pytest suite —
was written and run against a fresh temporary root
(`evidence/ORCH-003/logs/...-disposable-fixture-demo.py`,
`...-disposable-fixture-demo-output.txt`, `ORCH003_DEMO: ALL_CHECKS_PASS`),
independently reproducing:

- identical legacy bytes/digest before and after `inspect`;
- an identical directory-tree hash before/after `plan`;
- an identical directory-tree hash (including the containing temp directory — no backup
  object or any other file was created anywhere) before/after `apply --dry-run`;
- `apply` without `dry_run=True` raising `ApplyNotAuthorizedError` before any mutation;
- a corrupt sibling artifact quarantined `NOT_VALID_JSON` (unknown/corrupt input
  quarantine classification);
- a read-only reconfirmation that `stages.ORCH-004.status` is `NOT_STARTED`, with the
  real state file's bytes unchanged by that read.

## Decisions

- **A legacy-artifact source root mirrors the union of this engine's existing on-disk
  artifact stores** (`state/`, `agent-runs/`, `prompts/` — exactly
  `prompt/store.py`/`agents/artifacts.py`/`workflow/event_store.py`'s own
  `_artifact_root()` layout under `~/.ai-workflow-engine/workflow-runs`), plus a new
  `approvals/` convention for archived `git/approval.py` YAML files. `--source` defaults
  to that real root and is overridable, so production usage needs no new configuration
  surface, while tests point it at disposable fixtures.
- **Classification never guesses.** A file's family is determined solely by its fixed
  position in the documented directory convention, then strict validation against the
  exact existing v1 Pydantic model for that family — never by content sniffing or
  trying multiple families until one parses. An unlabelled/foreign approval `kind` is
  quarantined `UNKNOWN_APPROVAL_KIND` rather than guessed from shape.
- **14 stable, specific quarantine reasons** rather than one generic "invalid" bucket,
  so a caller (or a later orchestration stage's decision policy) can distinguish, e.g.,
  a symlink-safety refusal from a genuinely corrupt artifact from a schema-version
  mismatch (the "mixed-version" case).
- **A `.patch`/`.md` companion file is folded into its primary `.json` record's
  classification, not listed as its own manifest entry** — a missing or
  digest-mismatched companion downgrades the *primary* to `QUARANTINED`
  (`MISSING_COMPANION_MEMBER`/`COMPANION_DIGEST_MISMATCH`); an orphaned companion with no
  primary gets its own `ORPHAN_COMPANION_FILE` entry. This mirrors exactly what the real
  `agents/artifacts.py`/`prompt/store.py` loaders already verify at load time.
- **Symlinks are never followed, anywhere in the tree** — a symlinked file or directory
  is classified from its own identity (the target path string is hashed, never the
  target's content), and a symlinked directory is not descended into. This is the sole
  external-path-safety mechanism; since every non-symlink path is reached only by
  recursively walking real subdirectories of the resolved source root, path-traversal
  cannot occur except via a symlink, which is always refused before any read.
- **`manifest_digest`/`plan_digest` are self-referential content hashes** (SHA-256 of the
  canonical JSON of the record with the digest field itself excluded — the same
  technique as `agents/artifacts.py`'s `run_id`), so no field is time-dependent and two
  inspections of unchanged input are byte-for-byte identical, independently
  recomputable, and safe to compare across sessions/reviewers.
- **`ApplyResult.dry_run` is typed `Literal[True]`** — there is no way to construct an
  `ApplyResult` with `dry_run=False`; combined with `apply_migration` raising
  `ApplyNotAuthorizedError` as the very first thing it does whenever `dry_run` is not
  `True` (before touching its other arguments at all), "real apply is disabled" is a
  structural guarantee, not merely a tested behavior.
- **The backup plan includes quarantined artifacts too, not only `KNOWN` ones** — a
  backup preserves legacy evidence as found; it does not judge it. This matches
  architecture-v3.md section 18: "Migration is additive and never deletes legacy
  evidence."
- **CLI `migrate` commands reuse the exact ORCH-002 contract machinery unchanged**
  (`_protected`, `_contract_v2_success`/`_contract_v2_error`, `canonical_json` for v1) —
  no new error-handling code path was needed, so v1/v2 behavior, stdout purity, and the
  refuse-before-any-write property for `apply` without `--dry-run` all fall out of
  already-reviewed infrastructure rather than new bespoke logic.
- **A self-correction, recorded rather than silently fixed**: an early draft of two test
  files called the real, `$HOME`-coupled `workflow.event_store.append` against an
  explicit non-`$HOME` `--source`/`tmp_path` directory, not realizing that function's
  `repository` parameter is only a containment check, not a target root — so the first
  full-suite run actually wrote one artifact under this machine's real
  `~/.ai-workflow-engine/workflow-runs/state/p/`. This was caught immediately via `find
  ... -newer pyproject.toml`, confirmed by file birth-time and by the fact that
  project/task IDs `p`/`t` appear only in these fixtures (a `test-project` directory
  found alongside it was confirmed older, pre-existing, and left untouched), the exact
  polluted subtree was removed, and both fixtures were rewritten to write canonical
  bytes directly into the explicit disposable root instead. No real governance file was
  ever at risk; the affected path was purely a legacy-artifact-store convenience
  directory, not tracked by Git.

## Schema and migrations

**Schemas added**: `migration-manifest`, `migration-backup-plan`, `migration-recovery-plan`,
each version `1.0.0`, registered in a new `MIGRATION_SCHEMA_REGISTRY`
(`src/ai_workflow_engine/schema/migration.py`), proven to round-trip through
`SchemaRegistry.dispatch` (external/`model_validate` input), not merely direct Python
construction — the same rationale `cli-contract`'s Finding C used.

**Migrations**: `migration-registry.yaml` was read but not modified. All three existing
entries (`ORCH-MIG-001`, `ORCH-MIG-002`, `ORCH-MIG-003`) remain `owner_stage: ORCH-026`,
`status: PLANNED`, byte-for-byte unchanged — this stage introduced no entry it owns and
made no unauthorized change to an ORCH-026-owned entry.

## Risks

No new risk introduced. The stage's own documented risk ("Unknown legacy variants") is
mitigated by construction: every unrecognized shape is quarantined with a specific,
stable reason rather than guessed or silently accepted, and the four pre-existing
`unresolved_risks` entries (`R-APPROVAL-ISOLATION`, `R-GOVERNANCE-TRANSACTION`,
`R-BOOTSTRAP-ROLE-OVERLAP`, `R-REMEDIATION-AMENDMENT-UNREVIEWED`, plus the
closed-on-substance `R-ORCH-001-VALIDATOR-CORRECTNESS`) are carried forward unchanged;
none is affected by this stage's scope. `unresolved_risks` itself was not edited by this
session (no entry required a disposition change).

## Blockers

None. `stages.ORCH-003.blockers` is `[]`; top-level `blockers` remains `[]`.

## Durable state

- `stages.ORCH-003.status`: `NOT_STARTED` → **`IN_PROGRESS`** → **`IMPLEMENTED`** →
  **`VERIFIED`** (history sequences 40–42).
- `stages.ORCH-003.expected_base_head`: `e9f63a81041ba528055948890d5623087b62dae8`
  (equals `stages.ORCH-002.implementation_commit`, the committed ORCH-002 approval HEAD).
- `stages.ORCH-003.implementer`: `claude-code-implementer-orch-003-1`.
- `stages.ORCH-003.review_status`: `PENDING`; `reviewer`: `null`.
- `stages.ORCH-003.verification_status`: `PASSED`.
- `stages.ORCH-003.implementation_commit`: `null` (set by the reviewer once this diff is
  committed).
- `stages.ORCH-003.evidence`: this session's new evidence YAML.
- `stages.ORCH-003.handoff`: this handoff.
- `current_stage` / `candidate_next_stage` / `next_eligible_stage`: unchanged at
  `ORCH-003` (`VERIFIED` is not `REVIEW_APPROVED`).
- `history`: three new entries, sequences 40–42.
- **`ORCH-004` remains untouched**: `status NOT_STARTED`, `implementer null`,
  `review_status NOT_REQUESTED`, `verification_status NOT_RUN`.
- `migration-registry.yaml`: unchanged; all three entries remain owned by `ORCH-026`.
- Nothing was committed and nothing was pushed.

## Next legal action

A human commits this implementation diff (production changes + tests + this
evidence/handoff + `implementation-state.yaml`). The next session is then an
**independent ORCH-003 REVIEWER**, in a fresh session distinct from
`claude-code-implementer-orch-003-1` and every actor recorded against
ORCH-000/ORCH-001/ORCH-002, beginning from the resulting clean HEAD, setting
`stages.ORCH-003.implementation_commit` to that HEAD, re-running every stage-required
verification command (`pytest -q tests/test_migration*.py`, `pytest -q`, `ruff check`,
`black --check`, `mypy src`, the orchestration state validator, `workflowctl verify`,
`git diff --check`), independently re-verifying the byte-preservation, quarantine,
determinism, and write-safety claims above (not merely trusting this evidence), and
recording `REVIEW_APPROVED` or `REVIEW_REJECTED` in a new `reviews/ORCH-003/<review-id>.yaml`.
Per `session-protocol.md` section 4, this implementer session does not start ORCH-004.

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
docs/implementation/orchestration/stages/ORCH-003.md, the ORCH-003 evidence record and
handoff (evidence/ORCH-003/20260721T171500Z-claude-code-implementer-orch-003-1-a1b2c3d4.yaml,
handoffs/ORCH-003/20260721T171500Z-claude-code-implementer-orch-003-1-a1b2c3d4.md), and
the full changed source: src/ai_workflow_engine/migration/,
src/ai_workflow_engine/schema/migration.py, src/ai_workflow_engine/cli.py,
tests/test_migration_models.py, tests/test_migration_readers.py,
tests/test_migration_plan_apply.py, tests/test_migration_cli.py.

Confirm this IMPLEMENTER diff (history sequences 40-42) is committed, HEAD matches
origin/main with a clean tree, ORCH-003 is VERIFIED with review_status PENDING and no
open blocker, migration-registry.yaml is unchanged (all entries still owned by
ORCH-026), and ORCH-004 is still NOT_STARTED. Act as an independent ORCH-003 REVIEWER,
in a session distinct from claude-code-implementer-orch-003-1. Re-run every
stage-required verification command from the committed implementation HEAD, review the
full diff against stages/ORCH-003.md's allowed paths and architecture-v3.md sections 14
and 18, independently reproduce the byte-preservation, quarantine-classification,
determinism, and write-safety claims in the evidence and handoff (not merely trust
them), set implementation_commit to the exact reviewed HEAD, and record REVIEW_APPROVED
or REVIEW_REJECTED with exact findings and evidence. Do not commit, do not push, and do
not implement ORCH-004.
```
