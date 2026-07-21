# Handoff: ORCH-002 implementation — Schema registry and CLI v2 envelope (IMPLEMENTER)

## Summary

Acting in role IMPLEMENTER (actor `claude-code-implementer-orch-002-1`, distinct
from every actor recorded against ORCH-000 and ORCH-001), this session
implemented ORCH-002 ("Schema registry and CLI v2 envelope") at clean committed
HEAD `0aa7d939b79ebf83146473a369e120f01d4b73e4` ("docs: approve ORCH-001"); `main`
and `origin/main` are identical. This HEAD is recorded as
`stages.ORCH-002.expected_base_head`. Preflight confirmed: branch `main`; clean
tree/index; no merge/rebase/cherry-pick/bisect or orchestration lock active;
`package_status: PUBLISHED`; ORCH-001 `REVIEW_APPROVED` with committed review
evidence (`implementation_commit cfcdac346cd8ba03a17068f95d2253195798f621`);
ORCH-002 the unique `next_eligible_stage`, `NOT_STARTED`; ORCH-003 `NOT_STARTED`.

Implemented a schema registry (`src/ai_workflow_engine/schema/registry.py`'s
`SchemaRegistry`: a closed `(name, version) -> Pydantic model` dispatch that
fails closed — `UnknownSchemaNameError` for an unregistered name,
`UnsupportedSchemaVersionError` for an unregistered version of a known name,
never a silent default) and the CLI contract v2 envelope
(`src/ai_workflow_engine/schema/contract.py`'s `cli-contract` schema: version
`1.0.0` = `CliContractV1`, the pre-existing open/unenveloped shape, kept
available unchanged; version `2.0.0` = `ContractEnvelopeV2`, the
architecture-v3.md section 14 `{contract_version, command, ok, data, error,
warnings}` envelope, with `ContractErrorV2 {code, message, retryable, details}`
for stable structured errors). Wired a new global `--contract-version` CLI
option (default `"1"`; also accepts `"2"`, `"1.0.0"`, `"2.0.0"`) into the
existing shared `_emit` helper (`check-git`, `check-task-state`,
`check-governance`, `check-handover`, `commit`, `push`, `apply-patch`) and the
`verify` command, via a new `reporting/json_report.py` function
`render_contract_json`. The version is resolved once in the app callback,
before any command body runs, so an unknown/unsupported version fails closed —
`ERROR: ...` to stderr, exit code 2, **zero** stdout bytes — rather than ever
emitting a malformed or partial JSON document. No domain orchestration command
was added, per this stage's explicit non-goal.

**Verdict: implementation stops at `VERIFIED`.** All required verification
commands pass; no blocker. This session does not approve its own work.

## Changed paths

Modified (production, all inside `stages/ORCH-002.md`'s allowed set):

- `src/ai_workflow_engine/cli.py` — global `--contract-version` option resolved
  in the app callback (fail-closed on invalid input, same stderr/exit-2 shape as
  `_protected`); `_emit` and `verify` now call `render_contract_json` instead of
  `render_json` directly.
- `src/ai_workflow_engine/exceptions.py` — added `SchemaDispatchError` (base),
  `UnknownSchemaNameError`, `UnsupportedSchemaVersionError`.
- `src/ai_workflow_engine/reporting/json_report.py` — added
  `render_contract_json`; `render_json` unchanged.

Added (new, all inside the same allowed set):

- `src/ai_workflow_engine/schema/__init__.py`
- `src/ai_workflow_engine/schema/registry.py` — `SchemaRegistry`.
- `src/ai_workflow_engine/schema/contract.py` — `cli-contract` schema
  (`CliContractV1`, `ContractErrorV2`, `ContractEnvelopeV2`,
  `resolve_contract_version`, `success_envelope`, `error_envelope`).
- `tests/test_schema_registry.py` — 17 focused unit tests.
- `tests/test_cli_contract_v2.py` — 18 CLI-level tests.

ORCH records (this session, immutable, new):

- `docs/implementation/orchestration/evidence/ORCH-002/20260721T152237Z-claude-code-implementer-orch-002-1-e916ac25.yaml`
- `docs/implementation/orchestration/evidence/ORCH-002/logs/20260721T152237Z-claude-code-implementer-orch-002-1-e916ac25-*`
  (18 log artifacts)
- `docs/implementation/orchestration/handoffs/ORCH-002/20260721T152237Z-claude-code-implementer-orch-002-1-e916ac25.md`
  (this file)
- `docs/implementation/orchestration/implementation-state.yaml` (state
  transitions, history sequences 32–34, `last_updated`)

Confirmed empty diff / unchanged for: every `stages/*.md` file,
`session-protocol.md`, `architecture-v3.md`, `implementation-plan.md`,
`implementation-state.schema.yaml`, `migration-registry.yaml`,
`scripts/orchestration_feature_state.py`, `tests/test_orchestration_feature_state.py`,
and every other `src/`/`tests/` path not listed above (`git status --porcelain`
before this state edit showed exactly the paths listed here — see
`git-status-porcelain-untracked.txt`).

## Verification

Re-run from the committed base HEAD, before any state edit:

| Command | Result |
|---|---|
| `git rev-parse HEAD` / `git rev-parse origin/main` | both `0aa7d939b79ebf83146473a369e120f01d4b73e4` |
| `git status --porcelain -b` | clean at start |
| `python scripts/orchestration_feature_state.py validate ...` (before) | PASS, `state_digest sha256:53ee6a56...4acc` — byte-identical to the state ORCH-001's approving review left, confirming no drift |
| `pytest -q tests/test_schema_registry.py tests/test_cli_contract_v2.py tests/test_cli.py` | **102 passed** (up from 66 pre-existing in `test_cli.py` alone) |
| `pytest -q -rs` (full, before state edit) | **795 passed, 1 skipped** — the skip is the pre-existing, self-disabling O-1 observation ("frontier ORCH-002 is not yet implemented to VERIFIED grade"), reproduced exactly as predicted at ORCH-001's approval |
| `ruff check` (every changed/added `.py` file) | clean |
| `black --check` (same files) | clean |
| `mypy src` | `Success: no issues found in 47 source files` |
| `workflowctl verify --config self-governance.yaml --output json` | PASS |
| `git diff --check` | clean (empty output) |

Re-run **after** this session's own `implementation-state.yaml` edit:

| Command | Result |
|---|---|
| `python scripts/orchestration_feature_state.py validate ...` (after) | PASS, `state_digest sha256:14cd5d86...a642` |
| `python scripts/orchestration_feature_state.py status ...` | `current_stage`/`next_eligible_stage`/`candidate_next_stage` all `ORCH-002`; `ORCH-002.eligible_now: true`; `ORCH-003.status: NOT_STARTED` |
| `pytest -q -rs` (full, after) | **796 passed, 0 skipped** — O-1 self-healed exactly as its acceptance note predicted, now that ORCH-002 carries a VERIFIED-grade implementation with non-empty evidence |
| `workflowctl verify --config self-governance.yaml --output json` | PASS |
| `git status --porcelain` | exactly the changed/added paths listed above |

Every command's argv, exit code, stdout digest and environment-fingerprint
digest are recorded in
`evidence/ORCH-002/20260721T152237Z-claude-code-implementer-orch-002-1-e916ac25.yaml`.

**Explicit invariant checks:**

- *Exactly one JSON document on stdout*: verified for `--contract-version 2`
  under `FORCE_COLOR=3` via the real `python -m ai_workflow_engine` subprocess
  entrypoint (`test_v2_output_is_exactly_one_json_document_and_uncolored`) —
  `json.JSONDecoder.raw_decode` consumes the entire trimmed stdout, and no ANSI
  escape appears.
- *Known v1 contracts remain available*: default behavior unchanged
  (`test_v1_is_the_default_and_matches_the_pre_contract_shape`); explicit
  `--contract-version 1` is byte-identical to the default modulo the wall-clock
  timestamp (`test_explicit_v1_alias_matches_the_default`).
- *Known v2 contracts dispatch correctly*: envelope shape verified for a
  passing check, a failing check, `verify` pass and `verify` fail
  (`test_v2_envelope_shape_for_a_passing_check`,
  `test_v2_envelope_shape_for_a_failing_check`,
  `test_v2_envelope_for_verify_command`,
  `test_v2_envelope_for_verify_command_failure`).
- *Unknown schema names fail closed*: `test_unknown_schema_name_fails_closed`
  (registry unit test).
- *Unsupported schema versions fail closed*: `test_unsupported_schema_version_fails_closed`
  (registry unit test) plus three CLI-level negative tests
  (`test_unknown_contract_version_fails_closed_with_no_stdout`,
  `test_unregistered_but_well_formed_version_fails_closed`,
  `test_nonsense_contract_version_fails_closed`) — each asserts exit code `2`
  and **zero** stdout bytes.
- *Stable error codes/envelopes are deterministic*: `ContractErrorV2`/
  `ContractEnvelopeV2` are `extra="forbid"` Pydantic models
  (`test_cli_contract_v2_rejects_unknown_fields`); the same underlying `FAIL`
  check always yields the same `error.code` (`test_v2_envelope_shape_for_a_failing_check`).
- *ORCH-003 was not started*: confirmed before (`NOT_STARTED`) and after
  (`NOT_STARTED`) — see the `status` rerun above.
- *Only authorized paths changed*: see Changed paths above; cross-checked
  against `git status --porcelain` output captured in this evidence's logs.

## Decisions

- **`_emit`/`verify` route through `command=result.check_name` (or `"verify"`)
  rather than a new per-call-site parameter**, so no existing call site needed
  to change — only the shared helper body did. This kept the diff to exactly
  the three modified production files plus the new `schema/` package.
- **The legacy v1 shape is registered as `CliContractV1` with `extra="allow"`**
  rather than modeling every existing command's distinct payload shape under one
  v1 schema: v1 was never a single envelope, so the registry entry states
  exactly that fact (open, unenveloped, command-specific) instead of fabricating
  a fictitious common shape.
- **Contract-version validation happens once, in the app callback, using the
  exact `_protected`-style stderr/exit-2 shape** already established elsewhere
  in `cli.py`, rather than inventing a new error-reporting convention — and
  rather than letting an unresolved version reach `_emit`/`verify` and risk a
  partial or malformed JSON document.
- **No domain orchestration command was added** (`task`, `attempt`, etc.) —
  those are out of scope per this stage's explicit non-goal; only the schema
  registry and the CLI v2 envelope primitives were implemented, wired into the
  existing check/verify commands as the concrete demonstration.
- **`implementation_commit` left `null`**, per session-protocol.md section 2:
  the independent reviewer sets it to the exact clean HEAD it reviews.
- **State edited by hand**, following the precedent of every prior ORCH session
  (the `transition` CLI subcommand's `yaml.safe_dump` would reformat the whole
  flow-style document — an out-of-scope stylistic change). Re-validated with the
  tool's own `validate` after editing (state_digest above).

## Schema and migrations

**Schemas added**: `cli-contract` (schema registry entry), versions `1.0.0`
(`CliContractV1`) and `2.0.0` (`ContractEnvelopeV2`/`ContractErrorV2`), per
architecture-v3.md section 14 ("CLI JSON contract | 2.0.0"). This is now a
cross-stage interface freeze point per implementation-plan.md section 5
("ORCH-002: CLI v2 envelope/error/schema-dispatch contract") — changing it after
review approval requires a plan amendment and migration entry.

**Migrations**: none. `migration-registry.yaml` is unchanged; all three
registered entries (`ORCH-MIG-001..003`) remain owned by `ORCH-026`; none is
assigned to `ORCH-002`, so none was applied, consistent with
`implementation-plan.md` section 6 ("No production governance document is
migrated in an earlier stage").

## Risks

No new risk introduced. The four pre-existing `unresolved_risks` entries
(`R-APPROVAL-ISOLATION`, `R-GOVERNANCE-TRANSACTION`, `R-BOOTSTRAP-ROLE-OVERLAP`,
`R-REMEDIATION-AMENDMENT-UNREVIEWED`) and the closed-on-substance
`R-ORCH-001-VALIDATOR-CORRECTNESS` are carried forward unchanged; none is
affected by this stage's scope (`src/ai_workflow_engine/schema/`, `reporting/`,
`cli.py`, `exceptions.py`).

The stage's own documented risk ("CLI consumers may break") is mitigated by
construction: the default contract version is unchanged (`"1"`), every existing
`tests/test_cli.py` test (66) passes unmodified, and
`test_explicit_v1_alias_matches_the_default` directly proves the explicit-v1
path is byte-identical to the pre-existing default (modulo the per-request
timestamp field).

One transient, already-anticipated observation: `pytest -q` moved from
"795 passed, 1 skipped" (before this session's state edit) to "796 passed, 0
skipped" (after) — the O-1 skip recorded at ORCH-001's approval
(`test_frontier_invariant_survives_a_real_cli_approval_of_the_frontier`)
self-healed the moment ORCH-002 carried a VERIFIED-grade implementation with
non-empty evidence, exactly as that observation's acceptance note predicted.
This is not a regression.

## Blockers

None. `stages.ORCH-002.blockers` is `[]`; top-level `blockers` remains `[]`.

## Durable state

- `stages.ORCH-002.status`: `NOT_STARTED` → **`VERIFIED`** (via `IN_PROGRESS`,
  `IMPLEMENTED`).
- `stages.ORCH-002.expected_base_head`: `null` → **`0aa7d939b79ebf83146473a369e120f01d4b73e4`**.
- `stages.ORCH-002.implementer`: `null` → **`claude-code-implementer-orch-002-1`**.
- `stages.ORCH-002.review_status`: `NOT_REQUESTED` → **`PENDING`**.
- `stages.ORCH-002.reviewer`: `null` (unchanged).
- `stages.ORCH-002.verification_status`: `NOT_RUN` → **`PASSED`**.
- `stages.ORCH-002.evidence`: `[]` → **this session's evidence YAML**.
- `stages.ORCH-002.handoff`: `null` → **this handoff**.
- `stages.ORCH-002.implementation_commit`: `null` (unchanged — set by the
  reviewer on approval).
- `current_stage` / `candidate_next_stage` / `next_eligible_stage`: unchanged at
  `ORCH-002` (VERIFIED is not REVIEW_APPROVED; the frontier does not advance).
- `history`: three new entries, sequences 32–34
  (`STARTED_ORCH_002`/`IMPLEMENTED_ORCH_002`/`VERIFIED_ORCH_002`), role
  IMPLEMENTER.
- **`ORCH-003` status remains `NOT_STARTED`.**
- Nothing was committed and nothing was pushed.

## Next legal action

A human commits this implementation diff (production changes + new tests +
this evidence/handoff + `implementation-state.yaml`). The next session is then
an **independent ORCH-002 REVIEWER**, in a fresh session distinct from
`claude-code-implementer-orch-002-1`, beginning from the resulting clean HEAD,
setting `stages.ORCH-002.implementation_commit` to that HEAD, re-running every
stage-required verification command, and recording `REVIEW_APPROVED` or
`REVIEW_REJECTED`. Per session-protocol.md section 4, this implementer session
does not start ORCH-003.

## Exact continuation prompt

```
Work in /home/afshin-jian/ai-workflow-engine. Do not rely on chat history.
Read README.md, self-governance.yaml, docs/AGENT_PROTOCOL.md,
docs/implementation/orchestration/session-protocol.md,
docs/implementation/orchestration/architecture-v3.md,
docs/implementation/orchestration/implementation-plan.md,
docs/implementation/orchestration/implementation-state.schema.yaml,
docs/implementation/orchestration/implementation-state.yaml,
docs/implementation/orchestration/stages/ORCH-002.md, this implementation's
evidence and handoff
(evidence/ORCH-002/20260721T152237Z-claude-code-implementer-orch-002-1-e916ac25.yaml,
handoffs/ORCH-002/20260721T152237Z-claude-code-implementer-orch-002-1-e916ac25.md),
and the changed source: src/ai_workflow_engine/schema/, src/ai_workflow_engine/cli.py,
src/ai_workflow_engine/exceptions.py, src/ai_workflow_engine/reporting/json_report.py,
tests/test_schema_registry.py, tests/test_cli_contract_v2.py.

Confirm this IMPLEMENTER diff (history sequences 32-34) is committed, HEAD
matches origin/main with a clean tree, ORCH-002 is VERIFIED with review_status
PENDING, and ORCH-003 is still NOT_STARTED. Act as an independent ORCH-002
REVIEWER, in a session distinct from claude-code-implementer-orch-002-1.
Re-run every stage-required verification command from the committed
implementation HEAD, review the diff against stages/ORCH-002.md's allowed paths
and Architecture v3 section 14, set implementation_commit to the exact reviewed
HEAD, and record REVIEW_APPROVED or REVIEW_REJECTED with exact findings and
evidence. Note that pytest -q now reports 796 passed, 0 skipped (the O-1
observation from ORCH-001's approval self-healed once ORCH-002 reached VERIFIED
grade) -- this is expected, not a regression. Do not commit, do not push, and do
not implement ORCH-003.
```
