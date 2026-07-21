# Handoff: ORCH-002 implementation remediation — v2 coverage/error/consistency gaps (IMPLEMENTER)

## Summary

Acting in role IMPLEMENTER (actor `claude-code-implementer-orch-002-1`, the same
actor as the prior in-session ORCH-002 record, still distinct from every actor
recorded against ORCH-000 and ORCH-001), this session resumed ORCH-002 after a
human implementation review found the uncommitted diff incomplete. Nothing had
been committed between the original implementation and this remediation; `main`
and `origin/main` remain `0aa7d939b79ebf83146473a369e120f01d4b73e4` throughout,
matching `stages.ORCH-002.expected_base_head`.

**Findings addressed** (see `docs/implementation/orchestration/stages/ORCH-002.md`
and architecture-v3.md section 14):

- **Finding A — incomplete global v2 surface.** `--contract-version 2` enveloped
  only commands routed through the shared `_emit` helper plus `verify`, leaving
  `inspect`, every `prompt` subcommand, `state show/next/record` and `agent run`
  emitting legacy payloads even under contract v2.
- **Finding B — operational exception errors bypass v2.** `_protected`-caught
  operational/configuration/approval/gate exceptions bypassed JSON entirely
  (stderr + exit 2) regardless of `--contract-version`/`--output`, so a v2 JSON
  consumer received zero stdout on a config/approval failure.
- **Finding C — inconsistent envelopes accepted.** `ContractEnvelopeV2` accepted
  contradictory `ok`/`data`/`error` combinations (e.g. `ok=true` with `data=null`,
  or `ok=false` with `data` present) with no validation rejecting them.

**State lifecycle used**, per session-protocol.md section 2's legal transition
table: `VERIFIED -> BLOCKED` (history sequence 35, blocker
`IMPLEMENTATION_REVIEW_V2_COVERAGE_GAP` recorded) `-> IN_PROGRESS` (sequence 36,
blocker `resolution` recorded in the same edit — consistent with
`scripts/orchestration_feature_state.py`'s `BLOCKED -> IN_PROGRESS` gate, which
treats a blocker as resolved once its `resolution` field is non-null)
`-> IMPLEMENTED` (sequence 37) `-> VERIFIED` (sequence 38). The existing
implementation was preserved and extended, not replaced.

**Verdict: implementation stops at `VERIFIED` again.** All required verification
commands pass; no blocker remains open. This session does not approve its own
work.

## Changed paths

Modified again this round (on top of the prior round's diff, all inside
`stages/ORCH-002.md`'s allowed set):

- `src/ai_workflow_engine/cli.py` — Finding A: `inspect`, `_emit_prompt_success`,
  `_emit_state` (+ new `_contract_v2_for_status_payload` helper), `agent_run`
  (+ new `_contract_v2_for_agent_run_payload` helper) now honor
  `--contract-version`. Finding B: `_protected`/`_config` gained
  `output`/`command` parameters and emit the v2 error envelope for operational
  failures; every call site (`check-*`, `verify`, `commit`, `push`,
  `apply-patch`, `_run_prompt_command`, `state show/next/record`, `agent run`)
  now passes them through. New `_contract_v2_success`/`_contract_v2_error`
  helpers. The callback's existing invalid-`--contract-version` comment was
  expanded to state explicitly why that one case never uses the v2 envelope.
- `src/ai_workflow_engine/schema/contract.py` — Finding C:
  `ContractEnvelopeV2` gained a `model_validator(mode="after")` enforcing
  `ok=true <=> data is not None and error is None` and
  `ok=false <=> data is None and error is not None`, applied on every
  construction path (including `model_validate`/registry dispatch, not just the
  `success_envelope`/`error_envelope` builders, which already satisfied it).
- `tests/test_cli_contract_v2.py` — extended with the isolated-`$HOME` fixture
  and agent-stub helpers (duplicated locally per `tests/test_cli.py`'s own
  precedent, since `conftest.py` is outside this stage's allowed paths), plus
  28 new tests (see Verification below).
- `tests/test_schema_registry.py` — extended with Finding C's envelope
  consistency tests.
- `docs/implementation/orchestration/implementation-state.yaml` — state
  transitions (history sequences 35–38), the blocker record, and
  `last_updated`.

Not touched again this round (unchanged since the prior evidence record, which
already accounts for them): `src/ai_workflow_engine/exceptions.py`,
`src/ai_workflow_engine/schema/registry.py`,
`src/ai_workflow_engine/schema/__init__.py`,
`src/ai_workflow_engine/reporting/json_report.py`.

Added (new, immutable):

- `docs/implementation/orchestration/evidence/ORCH-002/20260721T160220Z-claude-code-implementer-orch-002-1-c6b9d62e.yaml`
- `docs/implementation/orchestration/evidence/ORCH-002/logs/20260721T160220Z-claude-code-implementer-orch-002-1-c6b9d62e-*`
  (15 log artifacts)
- `docs/implementation/orchestration/handoffs/ORCH-002/20260721T160220Z-claude-code-implementer-orch-002-1-c6b9d62e.md`
  (this file)

**The original evidence record
(`evidence/ORCH-002/20260721T152237Z-...-e916ac25.yaml`) and its handoff are
byte-for-byte unmodified** — this session adds a new record rather than
overwriting them, per session-protocol.md section 7.

Confirmed unchanged: every `stages/*.md` file, `session-protocol.md`,
`architecture-v3.md`, `implementation-plan.md`,
`implementation-state.schema.yaml`, `migration-registry.yaml`,
`scripts/orchestration_feature_state.py`,
`tests/test_orchestration_feature_state.py`, and every ORCH-000/ORCH-001 record.

## Verification

| Command | Result |
|---|---|
| `git rev-parse HEAD` / `git rev-parse origin/main` | both `0aa7d939b79ebf83146473a369e120f01d4b73e4`, unchanged throughout |
| `pytest -q tests/test_schema_registry.py tests/test_cli_contract_v2.py tests/test_cli.py` | **130 passed** (up from 102) |
| `pytest -q -rs` (full) | **824 passed, 0 skipped** (up from 795 passed / 1 skipped — the O-1 skip from ORCH-001's approval had already self-healed once ORCH-002 first reached VERIFIED in the prior round, and remains healed) |
| `ruff check` (every changed/added `.py` file) | clean |
| `black --check` (same files) | clean |
| `mypy src` | `Success: no issues found in 47 source files` (one dict-variance error was found and fixed by widening `_contract_v2_success`'s parameter to `Mapping[str, object]`) |
| `python scripts/orchestration_feature_state.py validate ...` (after this round's edit) | PASS, `state_digest sha256:54d27543a0eee5c75346b35b1ce2d1fc3beade948d8fb5a395f2e6f09cc42f33` |
| `python scripts/orchestration_feature_state.py status ...` | `current_stage`/`next_eligible_stage`/`candidate_next_stage` all `ORCH-002`; `ORCH-002.status VERIFIED`, `blockers` shows the one now-resolved blocker; `ORCH-003.status NOT_STARTED` |
| `workflowctl verify --config self-governance.yaml --output json` | PASS |
| `git diff --check` | clean |

**28 new tests**, spanning:

- Finding A: `test_inspect_v2_success`, `test_prompt_v2_success_with_no_store`,
  `test_state_show_and_next_v2_isolated`, `test_state_record_v2_domain_failure_envelope`,
  `test_agent_run_v2_isolated`, plus four dedicated `*_v1_is_byte_compatible` tests
  (inspect, prompt, state, agent-run) each proving the default and explicit
  `--contract-version 1` invocations are identical (byte-for-byte, or
  field-for-field modulo a legitimately-fresh timestamp for `agent-run`'s
  per-invocation verification).
- Finding B: `test_v2_configuration_failure_error_envelope`,
  `test_v1_configuration_failure_is_byte_compatible_stderr_only`,
  `test_v2_prompt_operational_failure_error_envelope`,
  `test_v2_agent_run_bad_agent_name_error_envelope`,
  `test_nonsense_contract_version_still_uses_stderr_not_v2_envelope` (documents
  and tests the deliberate exception: an unresolvable `--contract-version`
  itself can never select v2's envelope shape, since no contract has been
  chosen yet).
- Writable-gate refusal: `test_commit_v2_refusal_performs_no_write` — a
  well-formed-but-wrong-HEAD commit approval is refused via the v2 error
  envelope, and `git rev-parse HEAD` is asserted unchanged before/after.
- Stdout purity: `test_v2_output_is_a_single_json_document_under_force_color`
  (parametrized over `inspect`, `state next`, `check-handover`, `verify`) and
  `test_v2_error_output_is_a_single_json_document_under_force_color`, both under
  `FORCE_COLOR=3` via the real `python -m ai_workflow_engine` subprocess
  entrypoint, asserting `json.JSONDecoder.raw_decode` consumes the entire
  trimmed stdout and no ANSI escape appears.
- Finding C (`tests/test_schema_registry.py`): six positive/negative
  `ContractEnvelopeV2` construction cases, one via
  `CLI_CONTRACT_REGISTRY.dispatch` (proving the guard applies to
  `model_validate`, not just the builders), and one regression guard proving
  `success_envelope`/`error_envelope` already satisfied the invariant.

All state/prompt/agent tests reuse the isolated `$HOME` autouse fixture
(duplicated locally, matching `tests/test_cli.py`'s own precedent since
`conftest.py` is outside this stage's allowed paths) and the
`repository`/`config_factory` `tmp_path` fixtures from `conftest.py`; none
mutates the real repository or a real `$HOME`.

## Decisions

- **Route Finding A through the exact-same `_protected`/`_emit` choke points
  established in the original implementation**, adding small,
  command-shape-specific adapter helpers
  (`_contract_v2_for_status_payload`, `_contract_v2_for_agent_run_payload`)
  rather than one universal dict-to-envelope function — `state`'s
  `{status, command, finding}` shape and `agent run`'s
  `{status, verification: CheckResult, ...}` shape are genuinely different
  (the latter nests a full `CheckResult`), and forcing one generic adapter
  would have made the mapping less legible than two small, explicit ones.
- **Never touch the pre-existing v1 write statement in any command** — every
  v2 branch is inserted *before* the untouched v1 code, so v1's byte-for-byte
  output is guaranteed by construction, not merely by a subsequent test. This
  is why `src/ai_workflow_engine/reporting/json_report.py` needed no further
  change: the new v2 paths call `render_json`/`success_envelope`/`error_envelope`
  directly from `cli.py`, exactly like the original `_emit`/`verify` wiring did.
- **`_protected`/`_config` default to `output=HUMAN, command="command"`**
  rather than making the parameters required, so any future call site that
  forgets to pass them fails safe into the pre-existing stderr/exit-2 behavior
  instead of crashing — but every actual call site in `cli.py` now passes them
  explicitly (verified by grep and by the new tests reaching every one).
- **`type(exc).__name__` as the v2 error `code`, `retryable=False`** for every
  `_protected`-caught exception — deterministic and stable per exception type,
  and conservatively non-retryable since these are input/environment errors
  (bad config, bad approval file, bad parameter), not transient ones. This
  mirrors the existing `CHECK_{status}` convention already used for
  `CheckResult`-based failures.
- **The invalid-`--contract-version` case is the one place that never emits a
  v2 envelope**, even under `--output json`: until a contract version
  resolves, there is no envelope shape to use without begging the question.
  This was already true before this remediation; it is now explicitly
  commented in `cli.py`'s callback and covered by a dedicated test
  (`test_nonsense_contract_version_still_uses_stderr_not_v2_envelope`) instead
  of being an unstated, untested assumption.
- **Finding C's guard is a `model_validator(mode="after")` on
  `ContractEnvelopeV2` itself**, not a check duplicated at every call site —
  it therefore also protects `CLI_CONTRACT_REGISTRY.dispatch` (external/schema
  input), which a builder-only check could not reach.
- **Blocker introduced with `resolution: null`, then resolved in the same
  hand-edit that also advances `BLOCKED -> IN_PROGRESS`** — mirroring
  `scripts/orchestration_feature_state.py`'s own gate semantics (a blocker
  counts as resolved once its `resolution` field is non-null, whether it was
  already resolved or resolved by the same call), even though this session
  hand-edits the YAML rather than invoking the `transition` subcommand (same
  DEC-4/DEC-6 rationale as every prior ORCH-000/ORCH-001/ORCH-002 session:
  `write_state_atomic`'s `yaml.safe_dump` would reformat the whole flow-style
  document).
- **The blocker record is left in `stages.ORCH-002.blockers` with its
  resolution text, rather than cleared to `[]`**, to keep an auditable record
  of what was found and how it was fixed, consistent with how
  `unresolved_risks` dispositions are appended-to rather than deleted
  elsewhere in this document.

## Schema and migrations

**Schema changed**: `cli-contract` version `2.0.0` (`ContractEnvelopeV2`) gained
a validator (Finding C) — this narrows what the schema *accepts* (rejecting
previously-unvalidated contradictory payloads) without changing any field name,
type, or the wire shape of a valid envelope. No `contract_version` bump is
required: `2.0.0`'s wire shape is unchanged; only the Python-level validation
strictness improved, matching the schema's own stated intent
("stable ... envelope") more precisely. No new schema was registered.

**Migrations**: none, unchanged from the prior evidence record.
`migration-registry.yaml` is untouched; all three registered entries remain
owned by `ORCH-026`.

## Risks

No new risk introduced. The four pre-existing `unresolved_risks` entries
(`R-APPROVAL-ISOLATION`, `R-GOVERNANCE-TRANSACTION`, `R-BOOTSTRAP-ROLE-OVERLAP`,
`R-REMEDIATION-AMENDMENT-UNREVIEWED`) and the closed-on-substance
`R-ORCH-001-VALIDATOR-CORRECTNESS` are carried forward unchanged; none is
affected by this stage's scope.

The stage's own documented risk ("CLI consumers may break") remains mitigated
by construction and is now more thoroughly demonstrated: every existing
`--output json` command has an explicit v1-byte-compatibility test proving its
default behavior is unchanged, not just the four commands covered in the prior
round.

## Blockers

`stages.ORCH-002.blockers` now contains one entry
(`IMPLEMENTATION_REVIEW_V2_COVERAGE_GAP`), introduced and resolved within this
same session (history sequences 35–36), with `resolution` populated describing
the fix. Top-level `blockers` remains `[]`. No blocker is open.

## Durable state

- `stages.ORCH-002.status`: `VERIFIED` → **`BLOCKED`** → **`IN_PROGRESS`** →
  **`IMPLEMENTED`** → **`VERIFIED`** (history sequences 35–38).
- `stages.ORCH-002.blockers`: `[]` → one resolved
  `IMPLEMENTATION_REVIEW_V2_COVERAGE_GAP` entry.
- `stages.ORCH-002.evidence`: the original evidence YAML, plus **this session's
  new evidence YAML** appended.
- `stages.ORCH-002.handoff`: → **this handoff** (the prior handoff file remains
  on disk, unmodified, referenced by the prior evidence record).
- `stages.ORCH-002.implementer` / `review_status` / `reviewer` /
  `verification_status` / `implementation_commit` / `expected_base_head`:
  unchanged (`claude-code-implementer-orch-002-1` / `PENDING` / `null` /
  `PASSED` / `null` / `0aa7d939b79ebf83146473a369e120f01d4b73e4`).
- `current_stage` / `candidate_next_stage` / `next_eligible_stage`: unchanged at
  `ORCH-002` (VERIFIED is not REVIEW_APPROVED).
- `history`: four new entries, sequences 35–38.
- **`ORCH-003` status remains `NOT_STARTED`.**
- Nothing was committed and nothing was pushed.

## Next legal action

A human commits this implementation diff (production changes + extended tests
+ this evidence/handoff + `implementation-state.yaml`). The next session is
then an **independent ORCH-002 REVIEWER**, in a fresh session distinct from
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
docs/implementation/orchestration/stages/ORCH-002.md, both ORCH-002 evidence
records and both handoffs
(evidence/ORCH-002/20260721T152237Z-claude-code-implementer-orch-002-1-e916ac25.yaml,
evidence/ORCH-002/20260721T160220Z-claude-code-implementer-orch-002-1-c6b9d62e.yaml,
handoffs/ORCH-002/20260721T152237Z-claude-code-implementer-orch-002-1-e916ac25.md,
handoffs/ORCH-002/20260721T160220Z-claude-code-implementer-orch-002-1-c6b9d62e.md),
and the full changed source: src/ai_workflow_engine/schema/,
src/ai_workflow_engine/cli.py, src/ai_workflow_engine/exceptions.py,
src/ai_workflow_engine/reporting/json_report.py, tests/test_schema_registry.py,
tests/test_cli_contract_v2.py.

Confirm this IMPLEMENTER diff (history sequences 35-38) is committed, HEAD
matches origin/main with a clean tree, ORCH-002 is VERIFIED with review_status
PENDING and its blocker resolved, and ORCH-003 is still NOT_STARTED. Act as an
independent ORCH-002 REVIEWER, in a session distinct from
claude-code-implementer-orch-002-1. Re-run every stage-required verification
command from the committed implementation HEAD, review the full diff (both
rounds) against stages/ORCH-002.md's allowed paths and architecture-v3.md
section 14, independently verify that Findings A, B and C from the prior human
review are genuinely fixed (not merely asserted), set implementation_commit to
the exact reviewed HEAD, and record REVIEW_APPROVED or REVIEW_REJECTED with
exact findings and evidence. Do not commit, do not push, and do not implement
ORCH-003.
```
