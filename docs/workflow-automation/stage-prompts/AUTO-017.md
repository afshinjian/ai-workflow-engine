# AUTO-017 — Schema v2 and Stage Execution Policy (alias AWE-AUTO-ST-01)

> **PROPOSAL — NOT AUTHORIZED**
> This is a proposed stage contract, prepared under `STAGE_REGISTRY.md` §3 rule 3a (contract
> preparation precedes authorization, and is not authorization). It authorizes nothing, creates no
> branch, changes no code, and promotes no lifecycle state. AUTO-017 remains `NOT_STARTED` in
> `STAGE_REGISTRY.md` §4 and `Planned` in `docs/TASK_QUEUE.md`.
>
> **Revision 2 — FROZEN-FINDING REMEDIATION CANDIDATE.** The one independent discovery review is
> complete. This revision addresses only AUTO017-R01 through AUTO017-R06 and records the accepted
> OWNER ruling `D-AUTO017-01 = B`. It is not a new discovery review or implementation authorization.
> Implementation still requires closure of the frozen blocking findings and a separate written
> OWNER authorization under `STAGE_REGISTRY.md` §3 rules 1–3, recorded in §5 and the task record.

## 1. Contract Metadata

| Field | Value |
|---|---|
| **Stage** | AUTO-017 (alias AWE-AUTO-ST-01; the alias is a traceability label only) |
| **Title** | Schema v2 and Stage Execution Policy |
| **Status** | `PROPOSED — NOT AUTHORIZED` (Revision 2, remediation of the completed review's six frozen findings) |
| **Execution predecessor** | AUTO-016 (`COMPLETE`; merged as `b4534c7`, PR #19), per OD-GSE-12 |
| **Execution successor** | AUTO-018. Completing AUTO-017 authorizes nothing (§7 item 4 of the Master Plan). |
| **Governing architecture** | `docs/workflow-automation/successor-planning/AWE-GOVERNED-AUTONOMOUS-STAGE-EXECUTION-MASTER-PLAN.md` (CLOSED/FROZEN; identity in §2) |
| **Contract baseline** | `main` @ `489885d51e0d84e60c3506fd1ae2b365440b2401`, clean, empty index |
| **Implementation class** | Engine implementation. Typed schema, pure resolution, durable policy binding, one new local CLI verb. **No new runtime behavior**: no new run state, no new transition edge, no budget change, no provider-binding change, no Git change. |
| **Proposed branch** | `feature/auto-017-schema-v2-stage-policy` (created only after authorization; not created by this contract) |
| **Proposed report** | `docs/reports/workflow-automation/AUTO-017-completion-report.md` (created only on actual implementation) |
| **Implementation authorization** | **None.** |

### 1.1 Normative language

"Must", "must not", "refuse" and "exactly" are binding. Every refusal names a typed code from §14. A
behavior this contract does not grant is forbidden. Where this contract and the frozen Master Plan
appear to differ, the Master Plan governs. The implementer stops and reports the conflict
(§14.4); the implementer never resolves it alone.

---

## 2. Frozen Architecture Inputs

| Input | Identity | Role |
|---|---|---|
| Master Plan (Revision 2, OWNER-accepted, CLOSED/FROZEN, with bounded D-AUTO017-01 amendment) | 1675 lines, 111414 bytes, SHA-256 `8ca4d72d9f2487f9a39f52c8dca653d74c1257b993878200f4305c97eb4ed3f7` | Sole governing architecture. AUTO-017 is at lines 446–548; §6.1 records the ruling. |
| AUTO-016 contract (Revision 4) | SHA-256 `56f6a8f5720f30543f5b0623f5cb52ffa2cc45cbe51be8c5f9b9f5f256b90a7e` | The contract this stage amends (§18.3). |
| `STAGE_REGISTRY.md` (v7.0) at the contract baseline | SHA-256 `b2874e760d513eac2eb898876074fdd320d259dd3875bfad7b528a5788044462` | Rules 1–3, 3a and 10. §4 row format (§11.4). |
| SSP (`stage-prompts/README.md`, v1.4) at the contract baseline | SHA-256 `5d5a6acf786fe5929b31befae9f60256f9d0bc71abccb3b6f23927cd998ad398` | Standard Stage Protocol, applied by reference. It is not duplicated here. |

The implementer must re-verify the Master Plan identity before starting. If it differs, the
implementer stops before making any change.

**Bounded authority amendment (AUTO017-R01).** The pre-amendment Master Plan was 1664 lines,
110623 bytes, SHA-256 `6bb2509f1b30b2518755d63549dfa87fa5a10289e547bcd6fe824f40ecf195ad`.
Only AUTO-017 acceptance 5 and the ruling record in Master Plan §6.1 are amended. The OWNER's
`D-AUTO017-01 = B` makes registry authorization without a matching AWE-native Stage Start record
`STAGE_START_AUTHORIZATION_CONFLICT`. The amended identity above supersedes the former pin.
The Master Plan §6.1 entry is the minimum governance record; no separate lifecycle mirror changes.

### 2.1 Accepted OWNER decisions (CLOSED; binding; not reopened)

| ID | Ruling as it binds AUTO-017 |
|---|---|
| OD-GSE-01 | `blocking_severities = {CRITICAL, HIGH}` and `defer_severities = {MEDIUM, LOW}` are fixed in the policy and cannot be overridden (§7.6, §12 V-12). |
| OD-GSE-02 | `max_blockers ∈ 1..3`, default **3**, frozen in the policy. The *overflow behavior* belongs to AUTO-020 and is **not** implemented here. |
| OD-GSE-03 | `max_owner_extensions = 2`, a fixed constant recorded in the policy for auditability. It is not an OWNER-tunable knob, and extension *behavior* is not implemented here. |
| OD-GSE-06 | A matching AWE-native `StageStartAuthorization` is required and authoritative. A governed registry's authorization is an additional precondition. Any disagreement refuses with `STAGE_START_AUTHORIZATION_CONFLICT` (§11). |
| OD-GSE-07 | The Registry ID is `AUTO-017`, and `AWE-AUTO-ST-01` is a preserved alias. |
| OD-GSE-12 | The execution predecessor is AUTO-016 and the successor is AUTO-018. The numbering is preserved. |
| D-AUTO017-01 = B | Accepted and CLOSED (OWNER, 2026-09-29). Registry authorizes Stage + no matching AWE-native Stage Start authorization → `STAGE_START_AUTHORIZATION_CONFLICT`. This resolves OI-017-2 and AUTO017-R01; it is not reopened. |

### 2.2 OPEN OWNER decisions (not decided; not encoded)

AUTO-017 must not encode, default, name or leave a placeholder for any choice belonging to these
decisions (§13 INV-017-12; §16 T-OPEN).

| ID | Subject | Blocks | What AUTO-017 must NOT contain |
|---|---|---|---|
| OD-GSE-04 | Automatic commit vs. the human commit gate | AUTO-026 | No auto-commit or auto-push field or flag in any policy, defaults, overrides or authorization schema. `git.execute_commit`/`execute_push` keep their exact AUTO-016 meaning. |
| OD-GSE-05 | Telegram principal, attestation, custody, expiry | AUTO-024/025 | No attestation, nonce, expiry, principal-registry, Telegram or Hermes field. The only principal value is `LOCAL_CLI` (§7.9). |
| OD-GSE-08 | Reviewer independence; model mismatch | AUTO-022 | No independence rule: no check that roles differ in provider or model, and no `reported_model` field. |
| OD-GSE-09 | Post-remediation verification failure | AUTO-020 | No `POST_REMEDIATION_VERIFICATION_FAILED`, no `RETRY_CYCLE`, no cycle-completion field. |
| OD-GSE-10 | Worktree disposition on ABORT/AMEND | AUTO-021 | No worktree-disposition, carry-forward or patch-export field or behavior. |
| OD-GSE-11 | Closure scope in cycles 2..N | AUTO-020 | No closure-scope field. |

---

## 3. Objective

Introduce the versioned model through which the OWNER's start-time choices become one immutable,
digest-pinned `EffectiveStageExecutionPolicy` bound to exactly one run, so that a Stage that has
started can never be reinterpreted from changed project defaults, changed overrides or a changed
runner configuration.

Concretely, AUTO-017 delivers:

1. runner configuration schema **v2**, alongside an unchanged v1;
2. run-state schema **v2** (`STATE_SCHEMA_VERSION = 2`), with a read-only v1 → v2 upgrade on load;
3. `ProjectExecutionDefaults`, `StageExecutionOverrides`, `ContractExecutionCeilings`,
   `RoleSelection` and `EffectiveStageExecutionPolicy` as typed, closed, strict schemas;
4. a deterministic, pure `resolve_policy`;
5. a local, unauthenticated, typed-confirmation `StageStartAuthorization`, created only by the new
   `workflowctl milestone-runner stage-start` verb;
6. binding at `start`: `policy.json` published immutably, and `RunRecord.policy_digest` and
   `RunRecord.stage_start_id` recorded;
7. verification of the binding at every load, which makes a tampered or substituted policy fatal;
8. a Stage ID grammar generalized to a project-scoped grammar;
9. the fail-closed refusal of live providers for v2 runs until the Master Plan §3 live-provider
   isolation gate opens (AUTO-023).

The policy is **recorded and frozen, not executed**, except for `max_blockers`, which already has
AUTO-016 semantics and is sourced from the frozen policy for v2 runs (§10.4).
`max_remediation_cycles`, `on_retry_exhausted`, `max_owner_extensions` and `roles` have **no
behavioral effect** in AUTO-017 (§19).

---

## 4. Preconditions

Before authorization (all must hold, as evidenced at the authorization act):

- P-1. Execution predecessor AUTO-016 is `COMPLETE` in `STAGE_REGISTRY.md` §4.
- P-2. OD-GSE-01, -02, -03, -06, -07 and -12 are accepted (`docs/DECISION_LOG.md`, 2026-09-28).
  No OPEN decision blocks AUTO-017 (Master Plan §6.2).
- P-3. The `Current` set in `docs/TASK_QUEUE.md` is empty.
- P-4. This contract has received exactly one bounded independent contract review, and every
  blocking finding from it is closed in a later revision of this file.
- P-5. The Master Plan identity equals §2.
- P-6. `workflowctl verify --config self-governance.yaml` PASS on a clean, synchronized `main`.

Before the first implementation change (initial-start preflight, SSP):

- P-7. Registry `AUTHORIZED`, on branch `feature/auto-017-schema-v2-stage-policy` cut from the
  synchronized `main` that carries the authorization record. Clean tree.
- P-8. **Baseline evidence captured first** (§15.2): the v1 state corpus is generated from the
  unmodified baseline code *before* any production file is edited.

---

## 5. Authorized Production Paths (exact; nothing else)

| # | Path | Kind | Why it is required |
|---|---|---|---|
| A1 | `src/ai_workflow_engine/milestone_runner/policy.py` | **new** | Pure policy vocabulary, the schemas of §7, `resolve_policy`, the stage-start key and ID derivations. The Master Plan names this file. |
| A2 | `src/ai_workflow_engine/milestone_runner/models.py` | modify | `STATE_SCHEMA_VERSION = 2`, the Stage ID and milestone ID grammars (§7.10), the new `StopReason` members (§14.1), `RunRecord.policy_digest` and `RunRecord.stage_start_id`, and `canonical_json_bytes`. |
| A3 | `src/ai_workflow_engine/milestone_runner/config.py` | modify | Configuration schema v2 (§7.11), version dispatch in `load_runner_config`. v1 stays unchanged. |
| A4 | `src/ai_workflow_engine/milestone_runner/state.py` | modify | v1 → v2 read upgrade, v2 publication, the exclusive (no-replace) publication primitive, `policy.json`, `stage-starts/`, and a bounded read of `project-defaults.json`. |
| A5 | `src/ai_workflow_engine/milestone_runner/application.py` | modify | The **start path** (authorization, registry agreement, explicit adapter admission, binding), `stage_start` ingestion, the source of `ReviewPolicy` for v2 sessions, and authority/admission guards at existing mutating-command and provider-call boundaries. **No change** to drive-loop decisions, transitions or recovery-command semantics. |
| A6 | `src/ai_workflow_engine/milestone_runner/plan.py` | modify | `PLAN_FILE_NAME_RE` follows the generalized milestone grammar. A v1 configuration keeps the legacy grammar exactly, and a v2 configuration requires the milestone prefix to equal the stage ID (§7.10). Without this, a v2 Stage ID such as `ST-07` could have no milestone. |
| A7 | `src/ai_workflow_engine/milestone_runner/prompts.py` | modify | `PromptContext.stage_id` uses the shared Stage ID grammar. Without this, a v2 run fails at its first prompt render. **Grammar import only.** |
| A8 | `src/ai_workflow_engine/cli.py` | modify, **additive only** | Exactly one new command, `milestone-runner stage-start` (§11.2). No existing command is moved, renamed, re-optioned or changed. |

A6 and A7 are beyond the Master Plan's *expected* file list. That list is "for planning only; the
authoritative allowlist is fixed by each contract" (Master Plan §4). Both are required solely by the
Stage ID generalization, which the Master Plan assigns to AUTO-017, and neither gains any other
change.

### 5.1 Documentation path (on implementation only)

| # | Path | Kind |
|---|---|---|
| D1 | `docs/reports/workflow-automation/AUTO-017-completion-report.md` | new, at completion |

The governance mirror updates that the authorization, start and closure acts themselves require
(`STAGE_REGISTRY.md` §4/§5, `docs/TASK_QUEUE.md`, `docs/current_task.md`,
`docs/remaining_tasks.md`, `docs/PROJECT_STATE.md`, `docs/CHANGELOG.md`,
`docs/workflow-automation/CHANGELOG.md`) are governed by rule 1's sanctioned set. They are not part
of the implementation allowlist.

---

## 6. Authorized Test Paths (exact; nothing else)

| # | Path | Kind | Coverage |
|---|---|---|---|
| T1 | `tests/test_milestone_runner_policy.py` | **new** | Every §7 schema, `resolve_policy`, the digest vectors, the Stage ID grammar, the PromptContext grammar, the OPEN-decision negative tests, and v2 configuration validation. |
| T2 | `tests/milestone_runner_state_v1_corpus.json` | **new (data)** | The frozen v1 `state.json` corpus generated from the baseline code (§15.2). It is not collected by pytest. |
| T3 | `tests/test_milestone_runner_state.py` | modify | Schema v2, the v1 upgrade, unknown-version refusal, `policy.json` tamper detection, exclusive publication, the stage-start store, and the updated write-primitive AST allowlist. |
| T4 | `tests/test_milestone_runner_application.py` | modify | The start refusals, registry agreement, binding, resume binding verification, the live-provider refusal, v1/v2 mode mismatch, and "changed defaults do not reinterpret". |
| T5 | `tests/test_milestone_runner_plan.py` | modify | The milestone grammar: v1 unchanged, and the v2 generalized grammar and prefix rule. |
| T6 | `tests/test_milestone_runner_security.py` | modify | The INV-10 AST test, the no-directory-enumeration rule, the removal-call allowlist, and the absence of repository-path literals. |
| T7 | `tests/test_milestone_runner_acceptance.py` | modify | The Tier-1 disposable-repository acceptance run that produces `policy.json` end to end (completion marker). |
| T8 | `tests/test_cli.py` | modify, additive | The `stage-start` verb: typed confirmation, refusal codes, idempotency, and exit codes. |

**Expected to need no change** (verified by inspection at the contract baseline, where every state
fixture uses the `STATE_SCHEMA_VERSION` constant and every literal `schema_version: 1` is a v1
*configuration* or *plan* document): `tests/test_milestone_runner_recovery.py`,
`tests/test_milestone_runner_results.py`, `tests/test_milestone_runner_providers.py`,
`tests/test_milestone_runner_review.py`, `tests/test_milestone_runner_scope.py`,
`tests/test_milestone_runner_lock.py`. If one of these fails because of AUTO-017, the implementer
stops and reports it under §14.4. Editing the file is not the remedy.

---

## 7. Schema v2 Model Definitions and Ownership

All models inherit `MilestoneRunnerModel` (`extra="forbid"`, `strict=True`). "Strict" therefore
refuses `"2"`, `2.0` and `true` wherever an integer is required, and refuses any unknown key, at
every depth. Closed enums are resolved from JSON or YAML strings by a `mode="before"` lookup (the
`config._as_enum` discipline). An unknown member is a validation error.

### 7.1 Ownership

| Symbol | Module | Owner stage | Consumers (later; not implemented here) |
|---|---|---|---|
| `POLICY_SCHEMA_VERSION = 2` | `policy.py` | AUTO-017 | all |
| `CapabilityMode`, `OnRetryExhausted`, `ProgramRole`, `StartPrincipal` | `policy.py` | AUTO-017 | AUTO-020/021/022/024 |
| `RoleSelection` | `policy.py` | AUTO-017 (structure and validation only) | AUTO-022 (binding) |
| `ProjectExecutionDefaults`, `StageExecutionOverrides`, `ContractExecutionCeilings` | `policy.py` | AUTO-017 | — |
| `RegistryAuthorityContext`, `StageContractBinding`, `EffectiveStageExecutionPolicy`, `resolve_policy` | `policy.py` | AUTO-017 | AUTO-018..026 (read-only) |
| `StageStartAuthorization`, `StageStartPointer`, `StageStartBinding`, `stage_start_key`, `authority_json_bytes`, `authority_digest` | `policy.py` | AUTO-017 (local form) | AUTO-021 (START_STAGE ingestion), AUTO-024 (authentication) |
| `STAGE_ID_RE`, `LEGACY_STAGE_ID_RE`, `MILESTONE_ID_RE`, `LEGACY_MILESTONE_ID_RE` | `models.py` | AUTO-017 | all |
| `RunRecord.policy_digest`, `RunRecord.stage_start_id` | `models.py` | AUTO-017 | AUTO-018 onward |
| Configuration v2 (`RunnerConfig` with `schema_version: 2`) | `config.py` | AUTO-017 | all |
| `publish_exclusively`, the policy and stage-start store | `state.py` | AUTO-017 | AUTO-018 (events) |

`policy.py` imports only from `models.py`, the standard library and pydantic. It opens no file,
spawns no process and imports no provider (like `models.py`). It must not import `config.py`,
which imports it.

### 7.2 Enumerations (closed)

```text
CapabilityMode(StrEnum):    READ_ONLY = "READ_ONLY" | WORKSPACE_WRITE = "WORKSPACE_WRITE"
OnRetryExhausted(StrEnum):  ASK_OWNER_AND_FREEZE = "ask_owner_and_freeze"          # exactly one member
ProgramRole(StrEnum):       IMPLEMENTER | DISCOVERY_REVIEWER | REMEDIATOR | CLOSURE_VERIFIER
StartPrincipal(StrEnum):    LOCAL_CLI = "LOCAL_CLI"                                # exactly one member
```

- There is no "full access" or "bypass" capability member, so none is representable (AUTO-016
  invariant 17, carried forward).
- `OnRetryExhausted` has exactly one member. Later stages may add members only by contract
  (Master Plan, AUTO-017 scope).
- **Role vocabulary.** The persisted wire vocabulary is the existing `ProviderRole`
  (`IMPLEMENTATION`, `REVIEW`, `CORRECTION`, `CLOSURE`), as Master Plan §0 requires. `ProgramRole`
  is a documented alias and is never persisted. `PROGRAM_ROLE_TO_PROVIDER_ROLE` is a
  `Mapping[ProgramRole, ProviderRole]` bijection:
  `IMPLEMENTER→IMPLEMENTATION`, `DISCOVERY_REVIEWER→REVIEW`, `REMEDIATOR→CORRECTION`,
  `CLOSURE_VERIFIER→CLOSURE`. Every persisted `roles` mapping is keyed by `ProviderRole` values, and
  a program-name key such as `"IMPLEMENTER"` in an input document is refused.
- `READ_ONLY_PROVIDER_ROLES = frozenset({REVIEW, CLOSURE})`.

### 7.3 Constants

| Constant | Value | Source |
|---|---|---|
| `POLICY_SCHEMA_VERSION` | `2` | this contract |
| `MIN_REMEDIATION_CYCLES`, `MAX_REMEDIATION_CYCLES` | `1`, `3` | Master Plan AUTO-017 scope |
| `BUILTIN_MAX_REMEDIATION_CYCLES` | `1` | "a capability-granting field defaults to least capability" (Master Plan AUTO-017 invariants) |
| `MIN_BLOCKERS`, `MAX_BLOCKERS` | `1`, `3` | OD-GSE-02 |
| `BUILTIN_MAX_BLOCKERS` | `3` | OD-GSE-02 ("default of 3") |
| `BUILTIN_ON_RETRY_EXHAUSTED` | `ASK_OWNER_AND_FREEZE` | the only member |
| `MAX_OWNER_EXTENSIONS` | `2` | OD-GSE-03 |
| `POLICY_BLOCKING_SEVERITIES` | `(CRITICAL, HIGH)` (this order) | OD-GSE-01 |
| `POLICY_DEFER_SEVERITIES` | `(MEDIUM, LOW)` (this order) | OD-GSE-01 |
| `MAX_ROLE_TIMEOUT_SECONDS` | `43200` | equals `config.MAX_TIMEOUT_SECONDS`; a test asserts the equality |
| `MAX_POLICY_INPUT_BYTES` | `65536` | the bound on `project-defaults.json` and the overrides file |
| `MAX_STAGE_START_BYTES` | `65536` | authorization artifact read bound; reject before publication if the complete record exceeds it |
| `MAX_STAGE_START_REFERENCE_BYTES` | `4096` | key/pointer and binding artifact read bound |

The tuple order is the enum declaration order, so every serialization is deterministic.

### 7.4 `RoleSelection` (structure and validation only)

| Field | Type | Rule |
|---|---|---|
| `provider_id` | `str` | required. Grammar `[a-z][a-z0-9]*(?:-[a-z0-9]+)*`, 1..64 characters. |
| `model_id` | `str` | required. Grammar `[A-Za-z0-9][A-Za-z0-9._:@/+-]*`, 1..128 characters. No whitespace, no control or bidirectional code point, and no `..` substring. |
| `capability_mode` | `CapabilityMode` | default `READ_ONLY` (least capability) |
| `timeout_seconds` | `int` | **required, no default** (as AUTO-016 §17 requires for provider timeouts). `1..MAX_ROLE_TIMEOUT_SECONDS`. |

**Catalog boundary.** AUTO-017 validates provider and model identity by **grammar only**. There is
no provider catalog, no dispatch adapter registry and no model list. The explicit test-adapter
admission gate in §10.5 grants no dispatch meaning to these IDs. A well-formed but unknown
`provider_id` or `model_id` is accepted, recorded verbatim and frozen, and it is **never
dispatched**, because role selections do not bind any adapter in AUTO-017 (§19). Refusing unknown
IDs "at resolution" belongs to the AUTO-022 catalog (Master Plan AUTO-022 scope). Building a
catalog here would pull AUTO-022 forward. See §20 DO-022-1.

### 7.5 Input documents

**`ProjectExecutionDefaults`**: the file
`~/.ai-workflow-engine/milestone-runs/<repository-id>/project-defaults.json`. It is optional,
maintained by the OWNER, and **never written by AWE**.

| Field | Type | Rule |
|---|---|---|
| `schema_version` | `int` | exactly `2` |
| `max_remediation_cycles` | `int \| None` | `None`, or `1..3` |
| `max_blockers` | `int \| None` | `None`, or `1..3` |
| `on_retry_exhausted` | `OnRetryExhausted \| None` | `None`, or the single member |
| `roles` | `dict[ProviderRole, RoleSelection]` | default `{}`. **Any subset** of the four roles. |

**`StageExecutionOverrides`**: supplied at `stage-start` through `--overrides <path>`. It has
exactly the same fields and rules as `ProjectExecutionDefaults`. When `--overrides` is omitted, the
overrides are `StageExecutionOverrides(schema_version=2)`, with every field `None` and `roles`
empty.

**Not representable in either input** (`extra="forbid"` refuses the key itself):
`blocking_severities`, `defer_severities`, `max_owner_extensions`, `max_full_reviews`,
`max_discovery_reviews`, `max_correction_rounds`, `max_closure_reviews`, and any Git, commit, push,
Telegram, Hermes, attestation, expiry or independence key.

**`ContractExecutionCeilings`**: carried in the v2 configuration's `stage.execution_ceilings`
(§7.11). It is written next to the contract pin, so it is bound to the pinned contract digest.

| Field | Type | Rule |
|---|---|---|
| `max_remediation_cycles` | `int` | required, `1..3` |
| `max_blockers` | `int` | required, `1..3` |

**`StageContractBinding`** (in memory; built from the validated v2 configuration):
`repository_identity`, `stage_id`, `contract_path`, `contract_sha256`, `ceilings`, `registry_context`.

**`RegistryAuthorityContext`** (closed, strict, immutable; AUTO017-R02): exactly two required keys,
`kind` and `path`. Its only valid forms are
`{"kind":"NO_GOVERNED_REGISTRY","path":null}` and
`{"kind":"GOVERNED_REGISTRY","path":"<normalized repository-relative path>"}`.
`kind` is a closed enum. A path is validated with `normalize_repository_path`; absolute, traversal,
empty, control-character and malformed paths are refused. The normalized result is frozen, and
persisted paths must already equal that normalized form. There is no missing-key/default form.
The v2 configuration's explicit `registry_path: null` maps to `NO_GOVERNED_REGISTRY`; a declared
path maps to `GOVERNED_REGISTRY`. No filesystem observation may infer or change this declaration.
The declaration/path, not the mutable registry status text, is frozen into the policy digest.

### 7.6 `EffectiveStageExecutionPolicy` (resolved, frozen, the content of `policy.json`)

| Field | Type | Rule |
|---|---|---|
| `schema_version` | `int` | exactly `2` |
| `repository_identity` | `str` | the DEC-010 identity grammar (as `config._REPOSITORY_IDENTITY_RE`) |
| `stage_id` | `str` | `STAGE_ID_RE` |
| `contract_path` | `str` | normalized repository-relative (`normalize_repository_path`) |
| `contract_sha256` | `str` | 64 lowercase hexadecimal characters |
| `contract_ceilings` | `ContractExecutionCeilings` | copied from the binding |
| `registry_context` | `RegistryAuthorityContext` | required; copied from the binding, including explicit no-governed-registry; included in the policy digest |
| `max_remediation_cycles` | `int` | `1..3` and `≤ contract_ceilings.max_remediation_cycles` |
| `on_retry_exhausted` | `OnRetryExhausted` | the single member |
| `max_blockers` | `int` | `1..3` and `≤ contract_ceilings.max_blockers` |
| `blocking_severities` | `list[FindingSeverity]` | **exactly** `[CRITICAL, HIGH]` |
| `defer_severities` | `list[FindingSeverity]` | **exactly** `[MEDIUM, LOW]` |
| `max_owner_extensions` | `int` | **exactly** `2` |
| `roles` | `dict[ProviderRole, RoleSelection]` | **exactly** the four `ProviderRole` keys. `REVIEW` and `CLOSURE` must have `capability_mode = READ_ONLY` (§12 V-9). |
| `project_defaults_digest` | `str \| None` | SHA-256 of the exact `project-defaults.json` bytes read at `stage-start`, or `None` when the file was absent |
| `stage_overrides_digest` | `str` | `canonical_digest` of the validated `StageExecutionOverrides` |

The model carries no timestamp, so its canonical form is total. `DIGEST_EXCLUDED_FIELDS` never
drops a field from it.

`digest` is `canonical_digest(policy.model_dump(mode="json"))`. `canonical_bytes` is
`canonical_json_bytes(...)` of the same payload, the exact byte serialization `canonical_digest`
hashes (§7.12). The invariant is `sha256(policy.canonical_bytes()) == policy.digest`.

Deliberately absent (§2.2, §19): `max_discovery_reviews`, cycle counters, `authorized_remediation_cycles`,
`extensions_applied`, any Git or auto-commit field, any independence rule, `reported_model`,
`adapter_id`, and any Hermes or Telegram field. Adding any of them later is a schema change, which
Master Plan AUTO-017 "Must NOT be implemented early" intends.

### 7.7 `StageStartAuthorization` (local, unauthenticated form; immutable)

| Field | Type | Rule |
|---|---|---|
| `schema_version` | `int` | exactly `2` |
| `stage_start_id` | `str` | 64 lowercase hexadecimal characters; the logical-input digest defined in §7.8. |
| `authorization_digest` | `str` | 64 lowercase hexadecimal characters; full-record integrity digest defined in §7.8, including `created_at`. |
| `stage_start_key` | `str` | `stage_start_key(repository_identity, stage_id, contract_sha256)` (§7.8) |
| `principal` | `StartPrincipal` | `LOCAL_CLI` |
| `repository_identity`, `stage_id`, `contract_path`, `contract_sha256` | `str` | these must equal the embedded policy's fields |
| `contract_ceilings` | `ContractExecutionCeilings` | this must equal the embedded policy's `contract_ceilings` |
| `registry_context` | `RegistryAuthorityContext` | required; must equal the embedded policy's frozen declaration/path |
| `stage_overrides` | `StageExecutionOverrides` | the full validated overrides, so the record is self-contained evidence |
| `effective_policy` | `EffectiveStageExecutionPolicy` | the resolved policy the OWNER confirmed |
| `effective_policy_digest` | `str` | this must equal `effective_policy.digest` |
| `created_at` | `str` | valid UTC `YYYY-MM-DDTHH:MM:SSZ`, sampled only for a never-published logical input. Included in `authorization_digest`; an existing record's timestamp and bytes are reused, never refreshed (§11.2). |

A model validator enforces every equality in this table. A record that violates one cannot be
constructed or loaded.

### 7.8 Derived identifiers

- `stage_start_key(repository_identity, stage_id, contract_sha256)` is
  `canonical_digest({"repository_identity": …, "stage_id": …, "contract_sha256": …})`.
- `authority_json_bytes(payload)` in `policy.py` serializes validated JSON values with
  `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`
  encoded as strict UTF-8, with no trailing newline. It omits **no** key at any depth.
  `authority_digest(payload) = sha256(authority_json_bytes(payload)).hexdigest()`.
  These new helpers never use `DIGEST_EXCLUDED_FIELDS`; the v1 digest function is unchanged.
- The logical authorization payload is the entire §7.7 record with **only** top-level
  `stage_start_id`, `authorization_digest` and `created_at` removed. `stage_start_id` is its
  `authority_digest`. This freezes all logical input, including the normalized registry context.
- `authorization_digest` is `authority_digest` of the entire record with **only** top-level
  `authorization_digest` removed. It binds every other persisted field, including `stage_start_id`
  and `created_at`. The key pointer and binding pin this digest (§10.7). Load recomputes both
  digests, compares the pins, and requires canonical stored bytes; timestamp tampering refuses.
- These functions are pure. Neither reads the clock or filesystem. The application reads an
  existing record by deterministic logical ID before sampling a clock (§11.2), so byte equality
  and logical idempotency are consistent. No global timestamp-exclusion rule is changed.

### 7.9 `RunRecord` additions (`models.py`)

| Field | Type | Rule |
|---|---|---|
| `policy_digest` | `str \| None = None` | 64 lowercase hexadecimal characters, or `None` |
| `stage_start_id` | `str \| None = None` | 64 lowercase hexadecimal characters, or `None` |

- **Pairing.** Either both are `None` (a *supervised*, AUTO-016-mode run) or both are set (a
  *policy-governed* run). A record with exactly one set is invalid.
- `RunRecord.is_policy_governed` is a property: `policy_digest is not None`.
- `schema_version` is exactly `2` on every constructed record. (§8 covers v1 documents on load.)

### 7.10 Stage ID and milestone ID grammars (`models.py`)

```text
LEGACY_STAGE_ID_RE     = AUTO-[0-9]{3}
STAGE_ID_RE            = [A-Z][A-Z0-9]{0,15}(?:-[A-Z0-9]{1,16}){0,4}       total length ≤ 64
LEGACY_MILESTONE_ID_RE = AUTO-[0-9]{3}-M[0-9]{2}
MILESTONE_ID_RE        = <STAGE_ID_RE>-M[0-9]{2}                           total length ≤ 68
```

- **Additional rule.** A Stage ID whose **last** hyphen-separated segment matches `M[0-9]{2}` is
  refused. Without this rule `X-M01` would be both a Stage ID and a milestone of Stage `X`.
- Positive examples: `AUTO-017`, `ST-07`, `AWE-AUTO-ST-01`, `PROJ1-STAGE-2`.
- Negative examples: `auto-017`, `ST_07`, `-ST`, `ST-`, `ST--07`, `ST-M01`, a 65-character ID,
  `AUTO-017 `, `ÄUTO-1`, and `ST/07`.
- **Project scoping.** A Stage ID is unique only within one `repository_identity`. Every persisted
  AUTO-017 record binds the pair `(repository_identity, stage_id)`, and nothing compares Stage IDs
  across repositories.
- **Use by version.** A v1 configuration keeps `stage.stage_id ∈ LEGACY_STAGE_ID_RE`, exactly as
  today. A v2 configuration uses `STAGE_ID_RE`. `MilestoneSpec`, `ProviderRunRecord`,
  `RecoveryLedgerEntry`, `MilestoneCheckpoint`, `RunRecord`, `PromptContext` and
  `PLAN_FILE_NAME_RE` use the generalized grammars.
- **Plan loading.** Under a v1 configuration, the plan loader additionally requires every milestone
  ID to match `LEGACY_MILESTONE_ID_RE`, so the v1 accept/refuse set is **identical** to the
  baseline. Under a v2 configuration, the plan loader requires every milestone ID to equal
  `<config.stage.stage_id>-M[0-9]{2}`. A mismatch is `INVALID_CONFIGURATION`.

### 7.11 Configuration schema v2 (`config.py`)

v1 (`schema_version: 1`) is **unchanged**: the same model, the same validators, and the same
accept/refuse set. The v2 document is:

```yaml
schema_version: 2
repository: { root, identity, expected_branch, baseline_sha, conda_environment }  # as v1
stage:
  stage_id: ST-07                     # STAGE_ID_RE (generalized)
  contract_path: <repo-relative>      # as v1
  contract_sha256: <64 hex>           # as v1
  plan_directory: <optional>          # as v1
  registry_path: <repo-relative> | null   # REQUIRED key; explicit null = no governed registry
  execution_ceilings:                 # REQUIRED
    max_remediation_cycles: 1..3
    max_blockers: 1..3
allowlist: { allowed_paths, forbidden_paths, required_coverage }   # as v1
providers: { claude, codex, allowed_environment_variables }       # as v1 (see §10.5)
verification: { focused, final }                                   # as v1
git: { execute_commit: false, execute_push: false }                 # as v1
# review_policy: FORBIDDEN in v2 (refused if present, whatever its content)
```

- `registry_path` is **required as a key**. Omitting the key refuses the document. An explicit
  `null` declares that the repository has no governed stage registry. The presence of a registry
  file is never *inferred*: deleting the registry file never downgrades a repository to
  "record alone". A declared path that is absent or unreadable is a registry disagreement (§11.4).
- The normalized declaration becomes `registry_context` in the binding, effective policy and
  authorization. `path → null`, `null → path`, and `path A → path B` are authority changes, even
  when both registries contain identical rows. `start` and every mutating continuation compare
  current configuration to the frozen context before any write (§10.3, §11.3).
- `registry_path` and `contract_path` must not appear in `allowlist.allowed_paths`. A run must never
  be able to edit the document that authorizes it.
- `review_policy` is forbidden in v2. The review parameters of a v2 run come from the frozen policy
  and the fixed AUTO-016 ceilings (§10.4), so the configuration cannot become a second source that
  would reinterpret a started run. This is also how Master Plan acceptance 5b ("a config that
  promotes MEDIUM or LOW to blocking … is refused for a policy-governed run") holds structurally.
- The implementer may factor v1 and v2 as one model with version-conditional validators, or as two
  models under a discriminated return type. Either way, `load_runner_config` returns a value from
  which `config.schema_version` identifies the mode, and the v1 accept/refuse set is proven
  unchanged (§17 G-8).

### 7.12 `canonical_json_bytes` (`models.py`)

`canonical_json_bytes(payload) -> bytes` returns the exact UTF-8 serialization that
`canonical_digest` hashes today. `canonical_digest` is refactored to
`sha256(canonical_json_bytes(payload))`, **with byte-identical output for every existing input**.
The existing digest tests must pass unmodified.

---

## 8. Version-1 Compatibility Semantics

### 8.1 Configuration

| `schema_version` in the configuration file | Result |
|---|---|
| `1` (exact `int`) | The v1 model. **Supervised mode**: AUTO-016 behavior unchanged in every respect. |
| `2` (exact `int`) | The v2 model. **Policy-governed mode.** |
| anything else, including `0`, `3`, `"2"`, `2.0`, `true`, `null` or a missing key | `INVALID_CONFIGURATION`, checked **before** model validation by exact type and value (`type(v) is int and v in {1, 2}`) |

### 8.2 Run state (`state.json`)

| `schema_version` in `state.json` | Result |
|---|---|
| `2` (exact `int`) | Validated as `RunRecord` v2. |
| `1` (exact `int`) | **Read-only upgrade** (§15). The document must contain neither `policy_digest` nor `stage_start_id` (if it does, `StateCorrupted`). It is validated with `schema_version` set to `2` and both new fields `None`. **The file is not rewritten on load.** |
| anything else, including `0`, `3`, `"1"`, `1.0`, `true`, `null` or a missing key | `StateSchemaUnknown` (`STATE_SCHEMA_UNKNOWN`), checked before model validation by exact type and value. This closes the baseline's `==` comparison, which accepts `true` and `1.0` as `1`. |

### 8.3 v1 cannot silently gain v2 autonomy

- A v1 configuration cannot express any §7.5–§7.7 field: `extra="forbid"` refuses
  `execution_ceilings`, `registry_path`, and any policy key.
- An upgraded v1 record is **supervised** (`policy_digest is None`). No code path sets
  `policy_digest` or `stage_start_id` on an existing record (INV-017-3). Binding happens only in the
  v2 `start` path, on a record that has never been published before.
- The mode is fixed by the pair (configuration mode, record mode). **Mixing is refused**:

| Configuration | Record | Result |
|---|---|---|
| v1 | supervised | AUTO-016 behavior, unchanged |
| v1 | policy-governed | `POLICY_BINDING_MISMATCH`; nothing is written |
| v2 | supervised (including an upgraded v1 record) | `POLICY_BINDING_MISMATCH`; nothing is written |
| v2 | policy-governed | §10.3 binding verification, then continue |

- The `stage-start` verb refuses a v1 configuration (`INVALID_CONFIGURATION`: "stage-start requires
  a schema-v2 configuration").

### 8.4 Other versioned documents

- The milestone plan stays at `PLAN_SCHEMA_VERSION = 1`, and its schema is unchanged apart from the
  milestone ID grammar (§7.10).
- The `plan.json` snapshot keeps writing `STATE_SCHEMA_VERSION` as its version field, as at the
  baseline, so it now writes `2`. No other change is made to it.
- `policy.json`, `project-defaults.json`, the overrides file and `stage-starts/*.json` accept
  exactly `schema_version: 2`:
  - `policy.json`: any other value is `POLICY_DIGEST_MISMATCH`, because its bytes then cannot equal
    the pinned digest.
  - Inputs: any other value is `INVALID_CONFIGURATION`.
  - Stage-start records: any other value makes the record invalid. The authoritative refusal is
    selected by §11.3's matrix (`STAGE_START_AUTHORIZATION_CONFLICT` when the registry authorizes,
    otherwise `STAGE_START_NOT_AUTHORIZED`); binding-artifact failures use §10.8.

---

## 9. Resolution Algorithm (`resolve_policy`)

```text
resolve_policy(defaults: ProjectExecutionDefaults | None,
               overrides: StageExecutionOverrides,
               contract: StageContractBinding,
               *, project_defaults_digest: str | None) -> EffectiveStageExecutionPolicy
```

The function is pure and deterministic. It reads no clock, no filesystem and no environment.
Inputs arrive already validated. The rules are applied in this exact order:

1. **Scalars** (`max_remediation_cycles`, `max_blockers`, `on_retry_exhausted`). For each field
   `f`, with ceiling `C_f` from the contract (no ceiling for `on_retry_exhausted`):
   - If `overrides.f` is not `None`: when `overrides.f > C_f`, **refuse** (`INVALID_CONFIGURATION`,
     naming `f`, the value and the ceiling); otherwise the value is `overrides.f`.
   - Otherwise, if `defaults` is present and `defaults.f` is not `None`: the value is
     `min(defaults.f, C_f)`.
   - Otherwise the value is `min(BUILTIN_f, C_f)`.

   This is the Master Plan precedence exactly: contract ceiling, then Stage override, then project
   default, then built-in default. An explicit OWNER override that exceeds the contract is an
   error, never silently lowered. A default or built-in value is capped at the ceiling. Capping
   only ever *reduces* the value; it never raises one.
2. **Roles.** For each of the four `ProviderRole` members, in declaration order:
   - If `overrides.roles` has the role: take that `RoleSelection` **whole**.
   - Otherwise, if `defaults.roles` has the role: take that `RoleSelection` **whole**.
   - Otherwise **refuse** (`INVALID_CONFIGURATION`: "no selection for role R"). There is no
     built-in provider or model default, because inventing one would be an unrecorded choice.

   **Partial overrides.** At the top level, any subset of fields may be overridden. For `roles`, any
   subset of *roles* may be overridden, and "an override at Stage start changes only that role"
   (Master Plan AUTO-022 acceptance 1). Inside one role, overrides are **not** merged field by
   field: a `RoleSelection` replaces the whole selection. A field-level merge could combine one
   provider's ID with another provider's model ID.
3. **Fixed fields.** `blocking_severities = [CRITICAL, HIGH]`, `defer_severities = [MEDIUM, LOW]`,
   `max_owner_extensions = 2`, `schema_version = 2`.
4. **Binding fields.** The binding fields are copied from `contract`. `project_defaults_digest` is
   passed through. `stage_overrides_digest = canonical_digest(overrides.model_dump(mode="json"))`.
5. **Construction.** The `EffectiveStageExecutionPolicy` is constructed. Its validators, including
   reviewer `READ_ONLY` (§12 V-9), are final. A validation failure is `INVALID_CONFIGURATION`.

**Determinism** (Master Plan acceptance 1): the same inputs produce the same policy and the same
`digest`. There is no property-testing dependency in the repository and `pyproject.toml` is
forbidden, so determinism is proven by **exhaustive enumeration** (§16 T-RES-DET).

---

## 10. Effective Policy Freeze Semantics

### 10.1 When resolution happens

Resolution happens **exactly once**, inside `stage-start` (§11.2). `start` and `resume` **never
read `project-defaults.json`**, never read an overrides file, and never call `resolve_policy`. They
read the policy the authorization embeds, or the policy the run published. This is how "changed
defaults cannot reinterpret an already-started Stage" holds by construction. It holds between
`stage-start` and `start` as well as after `start`.

### 10.2 Publication at `start` (order is normative)

Phase A runs in full (§11.3). Then, under the run lock:

1. **B-1.** `stage-starts/<stage_start_id>.binding.json`, the closed binding document in §10.7,
   is published **exclusively** (§10.6), pinning the authorization and policy digests and `run_id`:
   - If it already exists, validates fully under §10.8, and names a run `R` that has **no published `state.json`**: a previous `start`
     crashed before B-3, and no run ever executed. `start` **adopts `R` as its run ID** and continues
     at B-2. It does not mint a new random ID, which would burn the authorization.
   - If it names a run that has a published `state.json`: `STAGE_START_ALREADY_BOUND`.
2. **B-2.** `<run-id>/policy.json` = `effective_policy.canonical_bytes()` is published
   **exclusively**:
   - If it already exists with identical bytes: continue.
   - If it exists with different bytes: `POLICY_DIGEST_MISMATCH`.
3. **B-3.** `state.json` (v2) is published, with `policy_digest = effective_policy_digest` and
   `stage_start_id` set, through the existing `publish` path.
4. **B-4.** From here on the existing AUTO-016 start flow is unchanged: the `latest-run` pointer, the
   plan snapshot, the remaining entry conditions, and the drive loop.

### 10.3 Verification at every load of a policy-governed record

`RunStateStore.load()`, and therefore `status`, `resume`, `abort`, the recovery commands and the
approval commands, must, for a record with `policy_digest` set:

1. read `policy.json` bounded and no-follow. An absent, unreadable or oversized file is
   `POLICY_DIGEST_MISMATCH`;
2. require `sha256(bytes) == record.policy_digest`. **Any** byte mutation fails here, including one
   that is whitespace only;
3. require the bytes to parse and validate as `EffectiveStageExecutionPolicy`. Otherwise
   `POLICY_DIGEST_MISMATCH`.

In addition, `resume`, `abort`, the recovery commands and the approval commands (every mutating
command) must, before acting:

4. load the exact key pointer and `stage-starts/<record.stage_start_id>.json` through §10.8.
   Validate both digests, the filename/key/record IDs and the pointer's authorization digest.
   Missing or invalid authority selects the single refusal from §11.3's authority matrix,
   including `STAGE_START_AUTHORIZATION_CONFLICT` when the governed registry authorizes;
5. require `authorization.effective_policy_digest == record.policy_digest` and byte equality of
   its embedded policy to `policy.json`. Otherwise `POLICY_DIGEST_MISMATCH`;
6. require the validated binding (§10.8) to name this `run_id`, Stage Start key/ID, authorization
   digest and policy digest. Missing, malformed or mismatched binding is
   `STAGE_START_ALREADY_BOUND`;
7. require the policy's `repository_identity`, `stage_id`, `contract_path`, `contract_sha256` and
   `contract_ceilings`, plus `registry_context`, to equal the current v2 configuration's normalized
   binding. Otherwise `POLICY_BINDING_MISMATCH`;
8. evaluate registry agreement using the **frozen** context (§11.4). A configuration change never
   switches the registry consulted or removes the requirement. Repeat these authority checks at
   each existing mutating continuation/entry-condition boundary, before any write or invocation.

The declaration comparison in step 7 is performed before any current-configuration registry is
consulted for execution authority; when a valid frozen policy exists, use its context to classify
missing authorization in step 4. A registry-context mismatch itself has the deterministic result
`POLICY_BINDING_MISMATCH`, including all three path/null mutations. No re-resolution or rebinding.

A failure raises a typed `StateError` subclass (or `RunRefused`) carrying the stop reason, and
**writes nothing**, as `StateCorrupted` and `StateSchemaUnknown` do today. A record whose binding
cannot be trusted is never the record a stop is published into.

### 10.4 What the frozen policy controls in AUTO-017

For a policy-governed session, `ReviewPolicy` is constructed from the frozen policy, never from
configuration:
`ReviewPolicy(max_full_reviews=1, max_correction_rounds=1, max_closure_reviews=1,
max_blockers=policy.max_blockers, blocking_severities=CRITICAL+HIGH,
defer_severities=MEDIUM+LOW)`. The three budgets are the unchanged AUTO-016 ceilings, and
`max_blockers` keeps its exact AUTO-016 meaning (§19). `review.py` is not modified.

### 10.5 Live-provider refusal (Master Plan §3, live-provider isolation gate)

"Before the gate opens, v2 runs accept only test-double adapters." In AUTO-017:

- `live_provider_execution_enabled() -> bool` is a pure function in `application.py` that returns
  `False`. Its docstring states that FA-5a is unevidenced and that AUTO-023 replaces it.
- **Explicit, fail-closed admission (AUTO017-R04).** `application.py` owns a closed in-memory
  `AdapterAdmissionKind` (`TEST_DOUBLE`, `LIVE`) and an immutable test-admission manifest supplied
  explicitly by the trusted test harness through a keyword-only application constructor argument,
  default empty. Each admission binds an exact adapter object identity, its exact concrete type
  object and `TEST_DOUBLE`. The harness must enumerate its audited inert scripted fakes explicitly;
  it must not auto-admit all injected objects. There is no class-name/module-name heuristic,
  inherited admission, adapter-supplied marker, config flag, environment switch or persisted
  admission. The manifest is copied/frozen; adapters and admission entries cannot change after the
  binding is checked. Known production adapters are `LIVE` and cannot be relabelled by a test entry.
- For a policy-governed run, `start`, `resume`, `doctor` and every existing provider-call boundary
  check **all** bound adapters before invoking any adapter method, probe, executable check or
  provider process. Only an exact object/type match to an explicit `TEST_DOUBLE` admission passes.
  An absent/mismatched admission, unknown type, subclass, replacement object, `LIVE` admission or
  production `from_config` binding is `LIVE_PROVIDER_NOT_ENABLED`. Known Claude/Codex classes
  remain live, but refusing those classes alone is insufficient. Refusal causes zero adapter
  invocations, zero provider/process invocations and zero run/artifact writes or progression.
- The admission check uses inert identity/type data only; it never calls an adapter to ask whether
  it is safe. Tests cannot bless an adapter by assigning it a `TEST_DOUBLE` attribute. Production
  constructors never supply a test manifest, and production/live adapters remain disabled until
  AUTO-023 evidences FA-5a and amends this gate. `roles`/provider/model IDs do not affect admission.
- This is evaluated in Phase A (§11.3), so a refused `start` consumes nothing. It is a local test
  admission boundary, not the AUTO-022 provider catalog or runtime role dispatch.
- As a consequence, a v2 `start` or `resume` through the CLI always refuses in AUTO-017. That is
  intended. v2 acceptance runs inject explicitly admitted scripted fakes through the application
  API. v1 Tier-1 tests require no new admission and retain their baseline behavior.
- v1 (supervised) runs are **unaffected**: the check is not evaluated for them.
- `providers/**` is not modified, and no adapter gains a marker.

### 10.6 Exclusive publication primitive (`state.py`)

`publish_exclusively(path, payload) -> ExclusiveOutcome{CREATED | IDENTICAL_EXISTS}` publishes
without ever replacing:

1. namespaced temp file in the same directory, then write, then fsync;
2. `os.link(temp, path)`:
   - on success, fsync the parent directory, and the outcome is `CREATED`;
   - on `FileExistsError`, read the existing file bounded and no-follow. Byte-equal is
     `IDENTICAL_EXISTS`. Otherwise raise `ExclusivePublicationConflict` (the caller maps it to its
     typed code);
3. the temp file is **always** unlinked, through the same local name `temporary` that the existing
   removal allowlist names (`PERMITTED_REMOVALS["state.py"] == {("unlink", "temporary")}` stays
   unchanged).

- It is reachable only through the single write boundary, extended as
  `write_redacted_artifact(..., exclusive=True)`, so redaction still precedes every byte.
- Redaction of a policy byte would change the digest. The next load then refuses the policy
  (fail-closed), and the §7.4 grammars make that practically unreachable.
- `publish_atomically` remains the only *replacing* primitive and is never used for `policy.json`,
  `stage-starts/*.json` or `*.binding.json`.

### 10.7 Durable layout added (exact names; read by exact name; never enumerated)

```text
~/.ai-workflow-engine/milestone-runs/<repository-id>/
    project-defaults.json                        OWNER-maintained; AWE reads, never writes
    stage-starts/<stage_start_id>.json           StageStartAuthorization (exclusive, immutable)
    stage-starts/key-<stage_start_key>.json      StageStartPointer (exclusive; fields below)
    stage-starts/<stage_start_id>.binding.json   StageStartBinding (exclusive; fields below)
    <run-id>/policy.json                         EffectiveStageExecutionPolicy canonical bytes (exclusive)
    <run-id>/state.json                          schema_version 2
```

- **The key pointer is a refinement of Master Plan §2.3.** The package never enumerates a
  directory (AUTO-016 invariant 19, applied package-wide; `application.latest_run_id`). `start`
  therefore finds the authorization by exact name: it computes `stage_start_key` from the
  configuration and reads `key-<key>.json`. The binding file makes the authorization **single-use**
  without a scan.
- Every directory component is checked no-follow and outside the repository, as today.
- A `<stage_start_id>`, a `<stage_start_key>` or a run ID that does not match its grammar is never
  used as a path.

Closed strict documents (all fields required, no extras; `schema_version` is exact integer `2`):

- `StageStartPointer`: `schema_version`, `stage_start_key`, `stage_start_id`,
  `authorization_digest`. The key must match its filename/computed key, and the ID and digest must
  match the loaded authorization. All three digest-shaped fields are 64 lowercase hex characters.
- `StageStartBinding`: `schema_version`, `stage_start_key`, `stage_start_id`,
  `authorization_digest`, `policy_digest`, `run_id`, `binding_digest`. The key/ID and both pinned
  digests must match the authorization; `policy_digest` must also match the run's policy. `run_id`
  obeys the existing store's run-ID grammar. `binding_digest` is `authority_digest` of all its
  fields except `binding_digest`, and must validate before adoption or continuation. Digest-shaped
  fields are 64 lowercase hex. On continuation, `run_id` must equal the loaded run's ID.

### 10.8 Hostile-input boundary for persisted Stage Start artifacts (AUTO017-R05)

Every read of a pointer, authorization or binding (including idempotent `stage-start`, Phase A,
B-1 adoption and every mutating continuation) must use the same bounded, no-follow reader in
`state.py`. Check every directory component and final artifact without following symlinks; require
a regular file, read at most its §7.3 limit plus one byte, and refuse oversize. Require strict
UTF-8, duplicate-key-free JSON at **every depth**, object root, exact schema/version, all required
fields, no extras, valid field/ID/path grammar and canonical bytes. Validate digests, filenames and
cross-artifact identity before using any loaded value as a path or trusting any authorization.
No permissive parser, directory scan, repair or normalization of hostile persisted content.

| Artifact | Required cross-checks | Typed refusal on failure |
|---|---|---|
| Key/pointer | Exact expected key and filename; linked ID/digest matches the authorization; authorization matches repository/Stage/contract/policy context | Authority matrix §11.3 (`STAGE_START_AUTHORIZATION_CONFLICT` when registry authorizes; otherwise `STAGE_START_NOT_AUTHORIZED`) |
| Authorization | Logical ID and full integrity digest, timestamp, pointer pin, embedded policy digest, repository/Stage/contract/registry context, and loaded run's Stage Start ID/policy where available | Authority matrix for invalid/untrusted authority; `POLICY_DIGEST_MISMATCH` for a valid authorization against a different pinned run policy; `POLICY_BINDING_MISMATCH` for valid frozen context against changed configuration |
| Binding | Self-digest, exact filename/ID/key, authorization/policy digests, run-ID grammar and expected run ID where already published | `STAGE_START_ALREADY_BOUND` |

On `stage-start` reuse, a malformed, missing referenced, substituted or mismatched artifact is
`STAGE_START_INPUT_CONFLICT` and is never replaced. Absence permits only the explicitly defined
initial publications in §11.2 and B-1: a missing reference required by an existing pointer/run
is corruption, not permission to recreate it. Initial absence of an unbound binding is normal;
its absence from a published run refuses. The record-without-pointer crash window is the one
explicit orphan reuse in §11.2, not a repair of an existing pointer's missing target.

Every hostile-artifact refusal is raised **before any write**, including a stop publication,
receipt rewrite, run lock metadata update or transcript. There is no Stage progression and no
provider invocation. Existing redaction remains mandatory; raw hostile content must not appear
in errors. §16.2 requires independent negative matrices for all three artifact types. Integrity
hashes are local consistency/tamper checks; authenticated attribution remains AUTO-024 scope.

---

## 11. Stage Start Policy Binding Requirements

### 11.1 Principle (OD-GSE-06; Master Plan §2.1 rule 3; INV-10 local form)

- A policy-governed run exists only if the OWNER explicitly ran `stage-start` naming the Stage ID.
  Nothing in AWE constructs a `StageStartAuthorization` on its own initiative, proposes a Stage, or
  derives a successor.
- The AWE-native record is **required and authoritative**. A governed registry is an **additional
  precondition**.

### 11.2 `workflowctl milestone-runner stage-start` (the one new CLI verb)

```text
workflowctl milestone-runner stage-start --config <path> --stage-id <STAGE_ID> [--overrides <path>]
```

The CLI handler parses and renders only. `MilestoneRunnerApplication.stage_start(stage_id=…,
overrides_path=…, confirmation=None)` does everything, and its body is the **only** place that
constructs a `StageStartAuthorization` (INV-017-8). Steps, in order:

1. The configuration must be v2. Otherwise `INVALID_CONFIGURATION`.
2. `--stage-id` must be exactly `config.stage.stage_id`. Otherwise `INVALID_CONFIGURATION`. The
   Stage ID is always named explicitly by the OWNER and never inferred.
3. Verify the contract pin (`inspector.verify_contract_pin`). A mismatch is `STAGE_ID_NOT_AUTHORIZED`,
   as for AUTO-016 entry condition 1.
4. Read `project-defaults.json`, if present: bounded (`MAX_POLICY_INPUT_BYTES`), no-follow, UTF-8,
   duplicate-key-free JSON. Record `sha256(bytes)` as `project_defaults_digest`. Any read or
   validation failure is `INVALID_CONFIGURATION`, never "treat as absent".
5. Read `--overrides`, if given, under the same bounds. The path must resolve **outside the
   repository root** (DEC-016-005's rationale: a file inside the guarded worktree must not steer
   policy). Otherwise `INVALID_CONFIGURATION`.
6. `resolve_policy(...)` (§9).
7. **Typed confirmation at the point of use.** Render the full effective policy, its digest and the
   Stage ID to stderr, then require the exact line `START_STAGE <STAGE_ID>`. A closed stdin or any
   other text is `STAGE_START_NOT_CONFIRMED`, and nothing is written. The confirmation reader is
   injectable for tests, as `prompt_for_confirmation` is today.
8. Derive the logical payload, key and `stage_start_id` without reading the clock (§7.8). Perform
   §10.8's read-only checks of existing exact-name artifacts **before** acquiring a write-capable
   lock. A key naming different logical input is `STAGE_START_INPUT_CONFLICT`, with no writes.
   A pointer whose target is missing or invalid also refuses; do not recreate the target.
9. For a new publication, acquire the repository run lock (holder ID from `new_run_id`, diagnostic
   metadata only, no run directory; `lock.py` unchanged) and recheck the exact artifacts. For a
   fully published identical rerun, return the validated existing receipt without acquiring this
   lock or writing. Validation is repeated before returning; concurrent drift refuses.
10. If the exact logical-ID authorization already exists, validate it and compare its complete
    logical payload to the requested input. Reuse its **exact bytes**, `created_at` and
    `authorization_digest`; do not construct a new timestamped candidate or rewrite it. This also
    covers a crash after record publication but before the key exists: the stable logical-ID path
    locates that orphan without enumeration. Otherwise, only when the pointer and record are both
    absent, sample UTC once, form the complete `LOCAL_CLI` payload and its full integrity digest,
    then construct the validated `StageStartAuthorization` and publish its canonical bytes
    (`authority_json_bytes` of the complete record) exclusively. If exclusive publication
    observes a race winner, validate and reuse that record's bytes for equal logical input; never
    equate newly timestamped bytes with old bytes or overwrite a conflict. All nonidentical or
    malformed existing input is `STAGE_START_INPUT_CONFLICT`.
11. Publish the §10.7 key pointer exclusively, pinning the **reused or newly persisted** record's
    key, ID and `authorization_digest`. Existing byte-identical pointer: success without rewrite.
    A different pointer refuses `STAGE_START_INPUT_CONFLICT`; it is never overwritten. The lock
    serializes cooperating publishers; no orphan is enumerated or deleted.
12. Release any held lock. Print a deterministic receipt containing `stage_start_id`,
    `stage_start_key`, `effective_policy_digest`, `authorization_digest` and the stored `created_at`
    in fixed order. Identical reruns at later clocks return exactly the same receipt. Exit `0`.

Every persisted authorization field is integrity-bound; a timestamp mutation with the old digest
fails validation, and recomputing the digest while leaving the published pointer/binding intact
fails their pins. Validation after redaction must confirm canonical bytes and digests **before**
publication; redaction must never create a silently altered authorization. This publication
algorithm adds no event log, new run transition, general recovery behavior or later-stage runtime.

Exit codes follow AUTO-016 §9: `0` success, `1` typed refusal (`WorkflowEngineError`), `2`
operational error.

**Consequence, stated honestly.** Once a key pointer exists, a *different* policy for the same
`(repository, stage, contract digest)` requires a new contract revision, which gives a new
`contract_sha256` and a new key. AUTO-017 has no revocation or replacement act, because that would
be a decision response, which is AUTO-021 scope. See §20 DO-021-2.

### 11.3 `start` for a v2 configuration: Phase A (no durable write)

Evaluated in this order, **before** any write, run directory, binding file or state. Authority
observations are collected read-only before a refusal is selected, so absence cannot prematurely
win over `D-AUTO017-01 = B`. Exactly one typed `RunRefused` is authoritative:

| # | Check | Refusal |
|---|---|---|
| A-1 | Collect bounded/no-follow pointer and authorization evidence (§10.8), including filename/key/ID/integrity checks. For valid authority, compare frozen context to configuration before reading its registry; use only the frozen path. If no valid record exists, collect the current declared registry's Stage status only to classify the refusal. Invalid authority is never used to form a path. | Select at A-2; do not return a competing absence code here |
| A-2 | Require matching repository, Stage, contract path/digest, ceilings and frozen registry context. Apply the authority matrix below; valid authority with changed registry context or ceilings is a configuration-binding mismatch. | Matrix below; context/ceiling drift is `POLICY_BINDING_MISMATCH` |
| A-3 | The contract pin verifies against the worktree. | `STAGE_ID_NOT_AUTHORIZED` |
| A-4 | Registry agreement (§11.4). | `STAGE_START_AUTHORIZATION_CONFLICT` |
| A-5 | Binding is initially absent, or validates in full (§10.8) and names a run with no published `state.json`, which is then adopted (§10.2 B-1). Never adopt a malformed binding. | `STAGE_START_ALREADY_BOUND` |
| A-6 | Live-provider refusal (§10.5). | `LIVE_PROVIDER_NOT_ENABLED` |

| Frozen/declarative registry authority | Matching valid AWE-native record | Result (A-2/A-4) |
|---|---|---|
| Governed registry authorizes Stage (`AUTHORIZED` or `IN_PROGRESS`) | absent, invalid or nonmatching | `STAGE_START_AUTHORIZATION_CONFLICT` — D-AUTO017-01 = B |
| Governed registry denies, is absent, unreadable or invalid | absent, invalid or nonmatching | `STAGE_START_NOT_AUTHORIZED` |
| Explicit `NO_GOVERNED_REGISTRY` | absent, invalid or nonmatching | `STAGE_START_NOT_AUTHORIZED` |
| Governed registry authorizes Stage and its contract agrees | present | proceed to remaining Phase-A checks |
| Governed registry denies/is invalid, or its contract disagrees | present | `STAGE_START_AUTHORIZATION_CONFLICT` |
| Explicit `NO_GOVERNED_REGISTRY` | present | proceed to remaining Phase-A checks |

- A valid frozen authorization whose normalized registry context or ceilings differ from current
  configuration is `POLICY_BINDING_MISMATCH` before registry execution authority is consulted.
  It cannot be reclassified as "no governed registry". Other mismatching authority uses the matrix.
- **Amended Master Plan acceptance 5 / OWNER ruling.** Registry authorization without a matching
  native record has exactly one stop reason: `STAGE_START_AUTHORIZATION_CONFLICT`. A report must
  not assign `STAGE_START_NOT_AUTHORIZED` to that scenario or emit two competing refusal codes.
- After Phase A, §10.2 Phase B runs. The remaining AUTO-016 entry conditions (identity, branch,
  HEAD, cleanliness, plan coverage, governance, configuration, lock) are evaluated and published
  **exactly as today**. A failure there is a durable stop on a *bound* run, and it is cleared by
  `resume` once fixed.

### 11.4 Registry agreement (v2 only; frozen `registry_context`)

- After verifying configuration equality, read the registry declared in the frozen authorization
  (at start) or policy (on continuation). Configuration never substitutes a different declaration.
  With no valid native record at start, the current explicit declaration is used only to classify
  the refusal under §11.3, never to grant execution.
- If the frozen context is `NO_GOVERNED_REGISTRY` with `path: null`, the check passes, and the
  record alone governs (OD-GSE-06: "A repository without a governed registry relies on the record
  alone").
- Otherwise, the registry text is read bounded (`MAX_REGISTRY_BYTES`) and no-follow, and parsed by a
  **pure** function, `registry_stage_entry(text, stage_id)`:
  - The registry is a Markdown table whose header row is exactly
    `| Stage | Title | Role | State | Branch | Prompt |`, followed by its delimiter row.
  - The function selects the rows of **that table only** whose **first cell, trimmed, equals
    `stage_id` exactly**.
  - **Zero or more than one** such row, an absent or unreadable file, or no such table all mean
    disagreement.
  - The `State` cell, trimmed, must be exactly `AUTHORIZED` or `IN_PROGRESS`.
  - The `Prompt` cell, with backticks and whitespace trimmed, resolved relative to the registry
    file's directory and normalized, must equal `config.stage.contract_path`. The contract digest
    is compared through that path: the file it names is the one A-3 pinned, so a record whose
    contract digest differs from the registry-named contract fails.
- With a valid matching native record, any registry failure is `STAGE_START_AUTHORIZATION_CONFLICT`.
  Without one, §11.3's matrix applies, including the OWNER-ruling case.
- The check is also re-evaluated for v2 runs wherever AUTO-016 re-evaluates entry condition 1 (every
  milestone boundary and every provider invocation), and there it is published as a durable stop,
  as today.
  Frozen-context or persisted authority corruption is refused before writes under §10.3/§10.8;
  that is distinct from a valid authority context whose current registry status no longer permits
  execution. Neither situation permits progression or provider invocation.

**Why a new parser.** The baseline `_registry_authorizes` matches `stage_id` as a substring of
**any** line, and the status word anywhere in that line. At the contract baseline it reports
`AUTO-017` as `IN_PROGRESS`, because a §5 log row mentions AUTO-017 next to
`IN_PROGRESS → COMPLETE`. It reports `AUTO-016`, which is `COMPLETE`, as authorized in the same
way. A generalized grammar would add prefix collisions such as `ST-1` inside `ST-10`. OD-GSE-06's
disagreement rule is meaningless on such a parser. **The v1 path keeps `_registry_authorizes`
byte-unchanged** (§8.3; see §19.2 and the OWNER item in §21).

---

## 12. Validation Rules

| ID | Rule | Code |
|---|---|---|
| V-1 | Configuration `schema_version` is exactly the `int` `1` or `2`. | `INVALID_CONFIGURATION` |
| V-2 | A v2 configuration has the required `stage.registry_path` key and the required `stage.execution_ceilings`, and no `review_policy`. | `INVALID_CONFIGURATION` |
| V-3 | `max_remediation_cycles` is an exact `int` in `{1, 2, 3}` wherever it appears. `0`, `4`, `-1`, `"2"`, `2.0`, `true` and `null` are refused. (`null` is refused where the field is required; in the inputs, `null` means "not set".) | `INVALID_CONFIGURATION` |
| V-4 | `max_blockers` is an exact `int` in `{1, 2, 3}`. | `INVALID_CONFIGURATION` |
| V-5 | `on_retry_exhausted` is exactly the string `ask_owner_and_freeze`. `ASK_OWNER_AND_FREEZE`, `abort`, `retry`, `""` and a non-string are refused. | `INVALID_CONFIGURATION` |
| V-6 | Overrides never exceed the contract ceilings (§9 rule 1). | `INVALID_CONFIGURATION` |
| V-7 | `roles` keys are `ProviderRole` values only. A program-name key, an unknown key or a duplicate key is refused. | `INVALID_CONFIGURATION` |
| V-8 | The `RoleSelection` grammars and bounds of §7.4 hold. `timeout_seconds` is required. | `INVALID_CONFIGURATION` |
| V-9 | In the effective policy, `REVIEW` and `CLOSURE` are `READ_ONLY`. This carries forward AUTO-016's fixed read-only reviewer (Master Plan E5; INV-12) at the policy layer. It is a validator, not the AUTO-022 type-level guarantee. | `INVALID_CONFIGURATION` |
| V-10 | After resolution, all four roles are present. | `INVALID_CONFIGURATION` |
| V-11 | `blocking_severities`, `defer_severities` and `max_owner_extensions` in the policy equal their fixed values exactly. In the inputs, they are unrepresentable keys. | `INVALID_CONFIGURATION` / `POLICY_DIGEST_MISMATCH` (on load) |
| V-12 | A v2 configuration with `review_policy` present is refused, **whatever it contains**, including a MEDIUM or LOW promotion (Master Plan acceptance 5b). | `INVALID_CONFIGURATION` |
| V-13 | Stage ID and milestone ID grammars (§7.10), each by configuration mode. | `INVALID_CONFIGURATION` |
| V-14 | The Stage Start self-consistency, integrity and hostile-read rules of §7.7–§7.8 and §10.8. | §11.3 authority matrix / §10.8 artifact-specific refusal |
| V-15 | `RunRecord` pairing (§7.9). | `StateCorrupted` |
| V-16 | Inputs are bounded (`MAX_POLICY_INPUT_BYTES`), UTF-8, JSON, duplicate-key-free, with an object root. | `INVALID_CONFIGURATION` |
| V-17 | The overrides path lies outside the repository root, and no path component is a symlink. | `INVALID_CONFIGURATION` |
| V-18 | `registry_path` and `contract_path` do not appear in `allowlist.allowed_paths`. | `INVALID_CONFIGURATION` |
| V-19 | The normalized registry declaration/path equals the frozen `registry_context` at start and every mutating continuation. | `POLICY_BINDING_MISMATCH` |

---

## 13. Invariants

Each invariant has at least one named negative test (§16).

| ID | Invariant |
|---|---|
| INV-017-1 (INV-07, local form) | `EffectiveStageExecutionPolicy` is immutable for the life of the run. `policy.json` is published once, exclusively, and verified by byte digest at every load. |
| INV-017-2 | Resolution happens only in `stage-start`. `start`, `resume` and every other command never call `resolve_policy` and never read `project-defaults.json` (AST test). |
| INV-017-3 | `policy_digest` and `stage_start_id` are set only in the v2 `start` path on a never-published record. `revise_record` refuses both names, as it refuses `workflow_state`, and `transition_to` preserves both. |
| INV-017-4 | A v1 configuration never produces a policy-governed run, and a supervised record never becomes policy-governed. |
| INV-017-5 | Configuration and record modes never mix (§8.3 table). |
| INV-017-6 | A `StageStartAuthorization` binds at most one run (binding file, exclusive). |
| INV-017-7 | `stage-start` never overwrites. A differing logical input for an existing key is refused; an identical rerun reuses the existing timestamp, bytes, integrity digest and receipt. |
| INV-017-8 (INV-10, local form) | Only `MilestoneRunnerApplication.stage_start` constructs `StageStartAuthorization(...)`, by call, `model_construct` or `model_copy`. Only the `state.py` loader parses one from bytes (AST test; Master Plan acceptance 6). |
| INV-017-9 | Nothing in AWE selects, derives, proposes or names a Stage ID other than the one the OWNER typed in `--stage-id` and confirmed. The output never names another Stage. |
| INV-017-10 | A v2 run reaches only explicitly admitted test-double instances while `live_provider_execution_enabled()` is `False`. Unknown/unclassified and live adapters refuse before invocation. |
| INV-017-11 | `ALLOWED_RUN_TRANSITIONS`, `RunStatus`, `TERMINAL_RUN_STATES` and the `MAX_*_CEILING` constants are byte-identical to the baseline. |
| INV-017-12 | No OPEN-decision field, member or placeholder exists (§2.2). |
| INV-017-13 | The package adds no directory enumeration (the baseline `plan.py` plan-root listing is the only one), and all new persistence passes through the single redaction write boundary. |
| INV-017-14 | AUTO-016 invariants 1–20 continue to hold (INV-12). v1 supervised behavior is unchanged. |
| INV-017-15 | Registry authority context is immutable and integrity-bound: path→null, null→path and path A→path B cannot reinterpret a Stage Start or active run. |

---

## 14. Failure and Refusal Behavior

### 14.1 `StopReason` additions (closed; exactly these eight)

`STAGE_START_NOT_AUTHORIZED`, `STAGE_START_AUTHORIZATION_CONFLICT`, `POLICY_DIGEST_MISMATCH`
(these three are named by the Master Plan), and five codes this contract coins:
`STAGE_START_INPUT_CONFLICT`, `STAGE_START_ALREADY_BOUND`, `STAGE_START_NOT_CONFIRMED`,
`POLICY_BINDING_MISMATCH`, `LIVE_PROVIDER_NOT_ENABLED`. The docstring is updated to state that
AUTO-017 §14.1 names them. `INVALID_CONFIGURATION`, `STATE_SCHEMA_UNKNOWN` and
`STAGE_ID_NOT_AUTHORIZED` are reused unchanged.

### 14.2 Where each refusal happens and what is written

| Code | Raised by | Durable effect |
|---|---|---|
| `INVALID_CONFIGURATION` | config load, input validation, `resolve_policy`, `stage-start` step 1/2/4/5 | none |
| `STAGE_START_NOT_CONFIRMED` | `stage-start` step 7 | none |
| `STAGE_START_INPUT_CONFLICT` | `stage-start` steps 8–11, including hostile or nonmatching existing artifacts | no overwrite; preflight-detected failures write nothing; only a crash/race after a successful new record publication may leave that unreferenced record |
| `STAGE_START_NOT_AUTHORIZED` | §11.3 matrix: no matching native authority and registry does not authorize, or explicit no-governed-registry; §10.3(4) uses the same matrix | none; never the registry-authorizes/no-record case |
| `STAGE_ID_NOT_AUTHORIZED` | `stage-start` step 3; `start` A-3 | none (at a later boundary: a published stop, as today) |
| `STAGE_START_AUTHORIZATION_CONFLICT` | §11.3 A-2/A-4 matrix, including registry authorizes + no matching native record (D-AUTO017-01 = B); §10.3(4/8) | none at start or on untrusted-artifact refusal; only valid authority with later registry-status disagreement publishes the existing durable stop |
| `STAGE_START_ALREADY_BOUND` | `start` A-5 / B-1; §10.3(6) | none |
| `LIVE_PROVIDER_NOT_ENABLED` | §10.5 explicit adapter admission at `start`, `resume`, `doctor` and invocation boundaries | none; zero adapter/provider/process invocations |
| `POLICY_DIGEST_MISMATCH` | `load()` §10.3(1–3); B-2; §10.3(5) | none |
| `POLICY_BINDING_MISMATCH` | mode mix (§8.3); `start` A-2; §10.3(7), including registry-context drift | none |
| `STATE_SCHEMA_UNKNOWN` | `load()` | none |

A refusal never deletes, repairs, rewrites or relocates any file. It never falls back to a default,
never downgrades to supervised mode, and never proceeds on partial evidence.

### 14.3 Crash windows (AUTO-017 scope only)

The phase ladder and general crash recovery are AUTO-018/019. AUTO-017 guarantees only the
following:

| Crash after | Next command | Outcome |
|---|---|---|
| `stage-start` step 10 (record written, no key) | `stage-start` with identical input at a later clock | exact logical-ID path reuses validated record bytes/timestamp/digest; key created; same ID and receipt |
| `stage-start` step 10 | `stage-start` with different input | a new record and key are created; the orphan is harmless |
| `start` B-1 (binding, no policy) | `start` again | the bound run ID is adopted (A-5); B-2 creates the policy |
| `start` B-3 (run published) | `start` for another run bound to the same authorization | `STAGE_START_ALREADY_BOUND` |
| `start` B-2 (policy, no state) | `start` again with the same `run_id` | B-2 `IDENTICAL_EXISTS`; B-3 publishes |

The baseline `start` refuses once a `latest-run` pointer names a published run. That behavior is
**unchanged**.

### 14.4 Implementer stop conditions

The implementer stops and reports to the OWNER, without improvising, if any of these occurs:
- a required change falls outside §5 or §6;
- a test outside §6 fails because of AUTO-017;
- a Master Plan statement conflicts with this contract;
- any §2.2 OPEN decision would have to be assumed;
- `canonical_digest` output changes for an existing input.

---

## 15. Migration Behavior

### 15.1 Rules

- **No migration writes.** Nothing rewrites, renames, moves or deletes an existing `state.json`,
  plan, transcript, ledger, lock, `latest-run` pointer or prototype artifact
  (`~/.local/share/auto015-runner/`, `~/.local/share/auto016-runner/`: DEC-016-006 unchanged).
- **Read-only upgrade.** A v1 `state.json` is upgraded in memory on each load (§8.2). A read-only
  command (`status`) leaves it byte-identical and mtime-identical.
- **Publication is always v2.** The first publication by a mutating command on a supervised v1 run
  writes `schema_version: 2`, with both new fields `null`. The run stays supervised forever.
- **Configurations are not migrated.** Existing v1 configurations keep working unchanged. A v2
  configuration is a new, OWNER-authored document.
- **Downgrade is not supported.** A v2 `state.json` is `STATE_SCHEMA_UNKNOWN` to a baseline build. The
  completion report must state this.

### 15.2 v1 fixture corpus (P-8; `tests/milestone_runner_state_v1_corpus.json`)

**Fixed provenance (AUTO017-R06).** Generate before production edits, exclusively from Git blobs at
`489885d51e0d84e60c3506fd1ae2b365440b2401`, even if the working tree has since changed. Exact sources:

- `src/ai_workflow_engine/models.py` (baseline `StrictModel` dependency);
- `src/ai_workflow_engine/milestone_runner/models.py` (baseline enums, validators and serializer);
- `tests/test_milestone_runner_state.py`: only `provider_run`, `passing_verification`, `run_record`,
  `approval`, and the `record` assignment in
  `TestRunRecord.test_a_full_record_round_trips_through_json_unchanged`.

The following command is the complete normative generator. Execute at the repository root with
CPython **3.13.5** and pydantic **2.11.7** (the reference environment); it requires only local Git
objects. It executes only the two pure baseline model modules and the listed fixture AST nodes,
never current production code, pytest collection, a provider or network service. Python `-I -B`
excludes the worktree/PYTHONPATH and suppresses bytecode writes; empty package paths prevent a
fallback import from the current repository. No branch switch, checkout or installation is needed.

The command writes canonical corpus bytes to stdout. The future implementer captures those exact
bytes as T2; this contract-remediation session does not create or modify test files. For validation,
execute the **same** command with first line changed only to
`PYTHONDONTWRITEBYTECODE=1 python -I -B - tests/milestone_runner_state_v1_corpus.json <<'PY'`.
That mode compares the checked-in file byte-for-byte to the isolated baseline reproduction and
fails on any difference. G-15 and T-V1-CORPUS-PROVENANCE must use this exact recipe, not a current
`RunRecord` import or a hand-authored `generated_from` claim.

<!-- AUTO017-V1-CORPUS-GENERATOR-BEGIN -->
```bash
PYTHONDONTWRITEBYTECODE=1 python -I -B - <<'PY'
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types
import pydantic

assert sys.version_info[:3] == (3, 13, 5)
assert pydantic.__version__ == "2.11.7"
baseline = "489885d51e0d84e60c3506fd1ae2b365440b2401"

def source(path):
    return subprocess.check_output(
        ["git", "show", f"{baseline}:{path}"], text=True, encoding="utf-8"
    )

for name in ("ai_workflow_engine", "ai_workflow_engine.milestone_runner"):
    package = types.ModuleType(name)
    package.__path__ = []
    sys.modules[name] = package

def load_model(name, path):
    module = types.ModuleType(name)
    module.__file__ = f"{baseline}:{path}"
    sys.modules[name] = module
    exec(compile(source(path), module.__file__, "exec"), module.__dict__)
    return module

load_model("ai_workflow_engine.models", "src/ai_workflow_engine/models.py")
m = load_model("ai_workflow_engine.milestone_runner.models",
               "src/ai_workflow_engine/milestone_runner/models.py")
assert m.STATE_SCHEMA_VERSION == 1
fixture_path = "tests/test_milestone_runner_state.py"
tree = ast.parse(source(fixture_path))
names = {"provider_run", "passing_verification", "run_record", "approval"}
nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
assert {n.name for n in nodes} == names
env = dict(vars(m))
exec(compile(ast.Module(body=nodes, type_ignores=[]), fixture_path, "exec"), env)
case = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "TestRunRecord")
method = next(n for n in case.body if isinstance(n, ast.FunctionDef)
              and n.name == "test_a_full_record_round_trips_through_json_unchanged")
assignment = method.body[0]
assert isinstance(assignment, ast.Assign) and assignment.targets[0].id == "record"
exec(compile(ast.Module(body=[assignment], type_ignores=[]), fixture_path, "exec"), env)

documents = []
assert len(m.RunStatus) == 18
for status in m.RunStatus:
    reason = (m.StopReason.OUT_OF_MILESTONE_SCOPE
              if status is m.RunStatus.HUMAN_INTERVENTION_REQUIRED else None)
    documents.append(env["run_record"](workflow_state=status, stop_reason=reason)
                     .model_dump(mode="json"))

payload = env["record"].model_dump()
payload["completed_milestones"] = ["AUTO-016-M01"]
payload["milestone_checkpoints"] = [m.MilestoneCheckpoint(
    milestone_id="AUTO-016-M01", recorded_at="2026-08-06T12:00:00Z",
    path_digests={"src/ai_workflow_engine/milestone_runner/models.py": "a" * 64})]
for ledger, command, pre, post in (
    ("reconciliations", "RECONCILE_MILESTONE", "HUMAN_INTERVENTION_REQUIRED", "FOCUSED_VERIFYING"),
    ("reopenings", "REOPEN_MILESTONE", "MILESTONE_FAILED", "IMPLEMENTING"),
    ("review_recoveries", "RECOVER_FAILED_REVIEW", "HUMAN_INTERVENTION_REQUIRED", "REVIEWING"),
    ("revalidations", "REVALIDATE_CORRECTION", "HUMAN_INTERVENTION_REQUIRED", "CLOSURE_VERIFYING"),
):
    payload[ledger] = [m.RecoveryLedgerEntry(
        command=m.RecoveryCommand[command], reason="deterministic v1 corpus",
        recorded_at="2026-08-05T22:00:00Z", pre_state=m.RunStatus[pre], post_state=m.RunStatus[post],
        branch=payload["expected_branch"], head_sha=payload["baseline_sha"],
        milestone_id="AUTO-016-M01", budgets_touched={"review_attempts": 1})]
rich = m.RunRecord(**payload).model_dump(mode="json")
assert all(value for value in rich.values() if isinstance(value, list))
documents.append(rich)
for document in documents:
    assert m.RunRecord.model_validate_json(json.dumps(document)).model_dump(mode="json") == document
corpus = {"generated_from": baseline, "documents": documents}
data = (json.dumps(corpus, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
assert len(data) == 21155
assert hashlib.sha256(data).hexdigest() == "c1a1c044526528e04251f5c9fcadbbe246e0fbb5874e2e11420172abbd17b41c"
if len(sys.argv) == 2:
    assert Path(sys.argv[1]).read_bytes() == data, "v1 corpus differs from pinned baseline"
    print(f"PASS: {len(data)} bytes; SHA-256 {hashlib.sha256(data).hexdigest()}")
else:
    assert len(sys.argv) == 1
    sys.stdout.buffer.write(data)
PY
```
<!-- AUTO017-V1-CORPUS-GENERATOR-END -->

**Normalization and order.** Exactly 19 documents: baseline `RunStatus` declaration order for 18
minimal fixtures, followed by the rich fixture (every list and all four ledgers nonempty, with
current milestone/checkpoint). Keep all serialized fields, including fixed timestamps, durations,
nulls and empty lists. No live clock, random ID, filesystem-root substitution, field omission or
timestamp stripping. JSON keys sorted, list order retained, compact separators, strict UTF-8,
no BOM, one final LF. The only corpus root keys are `generated_from` and `documents`.

**Expected identity:** **21155 bytes**, SHA-256
`c1a1c044526528e04251f5c9fcadbbe246e0fbb5874e2e11420172abbd17b41c`, reproduced from the pinned
baseline during this contract remediation without writing a corpus file. The generator asserts
both values. The implementation report must repeat that identity and record the exact generation/
comparison commands and G-15 output. Never regenerate from post-change code.

---

## 16. Required Tests

Test names are indicative, but each ID must map to at least one named test. Every test runs in the
default suite with no live provider, network, Hermes or Telegram.

### 16.1 Schema and resolution (T1)

| ID | Test |
|---|---|
| T-CFG-V2-OK | A complete v2 configuration loads; `schema_version == 2`; mode is policy-governed. |
| T-CFG-V1-UNCHANGED | The v1 accept/refuse matrix is identical to the baseline: every existing v1 configuration test passes unmodified, and a table of v1 documents is accepted or refused exactly as before. |
| T-CFG-VERSION | `0`, `3`, `"2"`, `2.0`, `true`, `null` and a missing configuration `schema_version` all give `INVALID_CONFIGURATION`. |
| T-CFG-V2-REVIEW-POLICY | A v2 configuration with any `review_policy`, including a MEDIUM promotion, is refused (5b). |
| T-CFG-V2-REGISTRY-KEY | A missing `registry_path` key is refused; explicit `null` maps to the exact `NO_GOVERNED_REGISTRY` form. A valid path maps to normalized `GOVERNED_REGISTRY`; invalid kind/path pairings and hostile paths refuse. `registry_path` or `contract_path` in `allowed_paths` is refused. |
| T-MRC-1 / T-MRC-2 / T-MRC-3 | `max_remediation_cycles` of 1, 2 and 3 are each accepted in defaults, overrides, ceilings and the policy, and survive resolution unchanged when within the ceiling. |
| T-MRC-REJECT | `0`, `4`, `-1`, `"2"`, `2.0`, `true`, `[]` and `{}` are refused everywhere the field appears (Master Plan acceptance 2). |
| T-BLOCKERS | `max_blockers` 1..3 is accepted; `0`, `4` and non-ints are refused; the default resolves to 3 when the ceiling is 3; it is capped by a ceiling of 2 when not overridden. |
| T-ORE | Only `ask_owner_and_freeze` is accepted. `ASK_OWNER_AND_FREEZE`, `abort`, `""` and `1` are refused. `OnRetryExhausted` has exactly one member. |
| T-EXT | `max_owner_extensions == 2` in every resolved policy. The key is refused in defaults and overrides. A policy document with `1` or `3` fails validation. |
| T-SEVERITY | The policy's severities are exactly `[CRITICAL, HIGH]` and `[MEDIUM, LOW]`. Severity keys in the inputs are refused. |
| T-RES-DEFAULTS | Values come from project defaults when there is no override. |
| T-RES-OVERRIDE | A Stage override beats a default for every scalar and every role. |
| T-RES-PARTIAL | An override of a subset of scalars and a subset of roles changes exactly those fields and roles. Inside one role, the selection is replaced whole, never merged by field. |
| T-RES-CEILING | An override above the ceiling is refused (never lowered). A default above the ceiling is capped. The built-in value is capped. |
| T-RES-BUILTIN | With no defaults file and empty overrides, the scalars resolve to the built-ins (1, 3, ask_owner_and_freeze), and the missing roles are refused. |
| T-RES-DET (Master Plan acceptance 1) | An **exhaustive enumeration** over max_remediation_cycles ∈ {absent, 1, 2, 3} in defaults × the same in overrides × ceilings {1, 2, 3} × max_blockers ∈ {absent, 1, 2, 3} × role source ∈ {defaults, overrides, mixed}. For each case, two independent calls give equal policies and equal digests, and invalid cases refuse identically. |
| T-DIGEST-VECTORS | At least three fixed policies with their **literal expected digests** written in the test (the digest vectors, recorded in the completion report). `sha256(canonical_bytes) == digest`. |
| T-CANONICAL-UNCHANGED | `canonical_digest` gives byte-identical output for the existing vectors. |
| T-ROLE-KEYS | Keys: `ProviderRole` keys are accepted; `IMPLEMENTER` and other program names are refused; unknown and duplicate keys are refused. |
| T-ROLE-ALIAS | `PROGRAM_ROLE_TO_PROVIDER_ROLE` is a bijection onto `ProviderRole`, with exactly the §7.2 pairs. |
| T-ROLE-IDENTITY | Provider and model identity are retained verbatim through resolution, the authorization, `policy.json` and load. |
| T-ROLE-GRAMMAR | Malformed `provider_id` and `model_id` values are refused (uppercase provider, whitespace, `..`, control or bidirectional character, too long, empty). A missing `timeout_seconds` or one out of range is refused. |
| T-ROLE-UNKNOWN | A well-formed but unknown `provider_id`/`model_id` is accepted and recorded. Nothing resolves it against a catalog. No `catalog` symbol exists in the package, and no adapter is selected from it (§7.4). |
| T-ROLE-REVIEWER-RO | `REVIEW` or `CLOSURE` with `WORKSPACE_WRITE` is refused; `IMPLEMENTATION` and `CORRECTION` may be `WORKSPACE_WRITE`; `READ_ONLY` is the default. |
| T-AUTH-SELF | Wrong logical ID, key, full `authorization_digest`, embedded policy digest or any mismatched binding field refuses. Equal logical input gives the same ID; different `created_at` changes the full integrity digest, never bypassing it through `DIGEST_EXCLUDED_FIELDS`. Any persisted-field mutation without updating its integrity pin refuses. |
| T-REGISTRY-CONTEXT-DIGEST | Hold all other inputs fixed: path A, null and path B produce distinct frozen contexts, policy digests and logical Stage Start IDs. Both authorization and policy require the context; missing fields or null/path contradictions refuse. |
| T-STAGE-ID | The §7.10 positive and negative lists, including the `-M01` last-segment refusal. |
| T-PROMPT-STAGE-ID | `PromptContext` accepts `ST-07` and `AWE-AUTO-ST-01`, and refuses the negatives. |
| T-OPEN | **OPEN decisions stay unencoded.** A structural test walks every field name and enum member of every §7 model and every `StopReason` member, and asserts the absence of: `auto_commit`, `auto_push`, `commit`, `push`, `attest`, `nonce`, `expiry`, `expires`, `telegram`, `hermes`, `independen`, `reported_model`, `fallback`, `retry_cycle`, `POST_REMEDIATION`, `worktree`, `carry_forward`, `patch`, `closure_scope`, `OWNER_DECISION_REQUIRED`, `SUPERSEDED`, `EXTEND`. It also asserts that `StartPrincipal` and `OnRetryExhausted` each have exactly one member. |
| T-ACCEPTED | The accepted decisions are represented: OD-GSE-01 (fixed severities), OD-GSE-02 (range and default 3), OD-GSE-03 (constant 2), OD-GSE-06 and D-AUTO017-01 = B (the single-code refusal matrix, §16.3), and OD-GSE-07/12 (the contract metadata; no code). |

### 16.2 State and persistence (T2, T3)

| ID | Test |
|---|---|
| T-V1-CORPUS (Master Plan acceptance 4) | Every document in `tests/milestone_runner_state_v1_corpus.json` loads through `RunStateStore.load()` as a supervised v2 record. `status` leaves the file byte- and mtime-identical. The next mutating publication writes `schema_version: 2` with both fields `null`. |
| T-V1-CORPUS-PROVENANCE | Run §15.2's isolated pinned-baseline generator and compare its stdout byte-for-byte with T2; assert 19 documents, 21155 bytes and the literal expected SHA-256. The baseline models validate all records before any v2 loading. Reproduction must be identical even after current v2 code changes. A changed corpus byte, false provenance label or current-code-generated replacement fails; neither generator nor expected identity may be updated to ratify it. |
| T-V1-POISONED | A v1 document carrying `policy_digest` or `stage_start_id` is `StateCorrupted`. |
| T-STATE-VERSION | `0`, `3`, `"1"`, `1.0`, `true`, `null` and a missing state `schema_version` all give `STATE_SCHEMA_UNKNOWN`. |
| T-PAIRING | Exactly one of `policy_digest`/`stage_start_id` set is refused. |
| T-POLICY-TAMPER (Master Plan acceptance 3) | After publication, each of these makes `load()` fail with `POLICY_DIGEST_MISMATCH`: flip one byte, append a newline, reformat with indentation, reorder keys, delete the file, replace it with a symlink, or substitute another valid policy. |
| T-EXCLUSIVE | `publish_exclusively` creates; identical bytes give `IDENTICAL_EXISTS`; different bytes raise and leave the original intact; no temp file remains in any outcome; the redaction boundary is applied. |
| T-NO-REPLACE | `policy.json`, `stage-starts/*.json` and `*.binding.json` are never written through `publish_atomically` (AST test). |
| T-WRITE-AST | The updated write-primitive AST tests: `os.link` appears only inside `publish_exclusively`, and `PERMITTED_REMOVALS` is unchanged. |
| T-REVISE-GUARD | `revise_record` refuses `policy_digest` and `stage_start_id`; `transition_to` preserves both. |
| T-START-POINTER-HOSTILE | Execute every applicable cell of the pointer column in the hostile-artifact matrix below, through `start` and all mutating continuation entry points. |
| T-START-AUTH-HOSTILE | Execute every authorization-column cell below, including timestamp tampering and substituted valid authorization, through `start` and all mutating continuations. |
| T-START-BINDING-HOSTILE | Execute every binding-column cell below, through `start` adoption and all mutating continuations. |

**Required hostile-artifact matrix (AUTO017-R05).** Each cell is an independent negative test with
otherwise valid authority. Exercise `resume`, `abort`, recovery commands and approval commands
at a state where they would otherwise mutate, as well as Phase A. Use explicitly admitted fakes
so provider admission cannot mask the artifact refusal. Missing binding is tested on a published
run; an initially unbound start is the positive control. Pointer/authorization failures are
parametrized with registry authorizes → `STAGE_START_AUTHORIZATION_CONFLICT` and explicit
no-governed-registry → `STAGE_START_NOT_AUTHORIZED`. Valid-authority policy or configuration
mismatches use the more specific digest/binding codes in §10.8. Binding failures always use
`STAGE_START_ALREADY_BOUND`. Also test `stage-start` reuse with malformed existing artifacts:
`STAGE_START_INPUT_CONFLICT`, no rewrite. Initial publication exceptions are only those in §10.8.

| Mutation | Key/pointer artifact | Authorization artifact | Binding artifact |
|---|---|---|---|
| Missing artifact | Remove the required pointer while retaining the published run | Remove the referenced authorization; no reconstruction | Remove from a published run; no rebind |
| Symlink | Final pointer and each parent component separately | Final record and each parent component separately | Final binding and each parent component separately |
| Oversize | `MAX_STAGE_START_REFERENCE_BYTES + 1` bytes | `MAX_STAGE_START_BYTES + 1` bytes | `MAX_STAGE_START_REFERENCE_BYTES + 1` bytes |
| Duplicate JSON keys | Duplicate key or ID, equal and conflicting values | Top-level timestamp/ID and nested policy/registry-context duplicates | Duplicate run ID or digest, equal and conflicting values |
| Invalid schema | Missing required field, unknown field, non-object root; schema 1, 3, string, float, bool or null | Same, plus malformed nested policy/context and invalid UTF-8 | Same closed-schema/version/root/UTF-8 negatives |
| Invalid ID/grammar | Non-hex, uppercase, truncated key/ID/digest; ID never used as path | Invalid logical ID/key/digest, Stage ID and timestamp grammar | Invalid key/ID/digests and run ID; never used as a path |
| Substituted content | Valid pointer from another Stage/key/policy; digest pin altered | Another valid authorization at the expected filename; mutate timestamp with unchanged digest, then with recomputed digest but unchanged pointer/binding | Another valid binding at the expected filename; changed self-digest, or valid self-digest with mismatched authorization/policy pins |
| Mismatched run ID | Pointer has no run-ID field: adding one is forbidden; following a substituted pointer cannot bypass the loaded run's Stage Start ID/policy checks | Authorization has no run-ID field: adding one is forbidden; a different run's authorization must fail the loaded run's ID/policy pins | Well-formed wrong run ID (including recomputed binding self-digest) against the loaded published run refuses |
| Mismatched Stage ID | Wrong computed key or a pointer leading to another Stage's valid authorization | Well-formed wrong Stage ID against embedded policy and configured/loaded Stage | Wrong Stage's key/ID/authorization linkage; no independent Stage field may be injected |
| Mismatched policy/config digest | Pointer with wrong authorization digest; substitute a valid same-Stage authorization whose policy differs from the run pin | Wrong embedded policy digest, valid different policy against `record.policy_digest`, or config contract digest/ceilings/registry context drift | Wrong policy or authorization digest, even with valid binding self-digest |
| Malformed/hostile path | Traversal/absolute/drive/backslash/NUL/separator-bearing key/ID; reject before path construction | Hostile `contract_path` or governed registry path, including traversal, absolute, control, backslash and noncanonical forms | Traversal/absolute/drive/backslash/NUL/separator-bearing run ID or Stage Start ID; reject before path construction |

Every negative case asserts the exact typed code and **zero writes**, unchanged existing bytes/
mtimes and file set, no run/Stage progression, and zero adapter/provider/process calls. Install
write-boundary and invocation spies before the command; snapshots alone are insufficient. Verify
no new binding, policy, state, pointer, receipt or transcript; no stop is published into untrusted
state. Symlink targets are never read or written, and hostile payloads remain redacted in errors.

### 16.3 Start, binding and freeze (T4)

| ID | Test |
|---|---|
| T-START-NO-RECORD (amended acceptance 5; AUTO017-R01) | Registry `AUTHORIZED` and `IN_PROGRESS`, each with missing pointer, missing target or invalid/nonmatching native record: exactly `STAGE_START_AUTHORIZATION_CONFLICT`, with no competing absence code. Denying registry or explicit no registry with no record: `STAGE_START_NOT_AUTHORIZED`. Every row of §11.3 is exercised; zero writes/progression/provider calls. |
| T-START-REGISTRY-NOT-AUTH (acceptance 5a) | A valid record while the registry shows `NOT_STARTED`, `COMPLETE`, `BLOCKED`, no row, two rows, or no §4 table: `STAGE_START_AUTHORIZATION_CONFLICT`. |
| T-START-REGISTRY-PROMPT | A registry `Prompt` cell naming a different contract, whose digest differs: `STAGE_START_AUTHORIZATION_CONFLICT`. |
| T-START-NO-REGISTRY | `registry_path: null` with a valid record: start proceeds. With a declared path and the file deleted: `STAGE_START_AUTHORIZATION_CONFLICT` (no inference). |
| T-REGISTRY-PARSER | `registry_stage_entry` against the **real** `STAGE_REGISTRY.md` text at the contract baseline: `AUTO-016 → COMPLETE`, `AUTO-017 → NOT_STARTED`, `AUTO-009 → COMPLETE`. A log row naming a stage never counts. `ST-1` never matches `ST-10`. |
| T-START-BINDS | A successful Phase A/B: `policy.json` bytes equal `authorization.effective_policy.canonical_bytes()`; `state.json` carries `schema_version 2`, `policy_digest` and `stage_start_id`; the binding file names the run. |
| T-START-SINGLE-USE | Once the bound run has published `state.json`, a second run (a different injected `run_id`) against the same authorization is refused `STAGE_START_ALREADY_BOUND`, and the first run is untouched. A crash injected after B-1 followed by `start` adopts the bound run ID. |
| T-FREEZE-DEFAULTS (brief: "changed defaults do not reinterpret") | Change `project-defaults.json` (1) between `stage-start` and `start`, and (2) between `start` and `resume`. In both cases `policy.json`, `policy_digest` and the `ReviewPolicy.max_blockers` in effect equal the confirmed policy. |
| T-FREEZE-CONFIG | Changing `execution_ceilings` in the configuration after `start` makes `resume` fail with `POLICY_BINDING_MISMATCH`. The frozen policy is never recomputed. |
| T-FREEZE-REGISTRY-PATH-NULL | Freeze governed path A, then set config `registry_path: null`: `POLICY_BINDING_MISMATCH` both between `stage-start`/`start` and before every mutating continuation on a published run. Zero writes, no progression/provider calls; authority bytes unchanged. |
| T-FREEZE-REGISTRY-NULL-PATH | Freeze explicit no-governed-registry, then set config to path A: the same start/continuation refusal and no-side-effect assertions. |
| T-FREEZE-REGISTRY-PATH-PATH | Freeze path A, then set config to path B, including B with byte-identical authorized rows: the same refusal/assertions. An unchanged normalized declaration is the positive control. No lookup of B for execution authority. |
| T-NO-RESOLVE (INV-017-2) | AST: `resolve_policy` and the defaults reader are called only from `stage_start`. |
| T-MODE-MIX | All four rows of the §8.3 table. |
| T-V1-NO-AUTONOMY | A v1 configuration with any policy key is refused. A v1 run's lifecycle, from start through `READY_FOR_COMMIT_APPROVAL` with fakes, produces no `policy.json`, no binding and no `stage-starts/` entry. |
| T-LIVE-REFUSED | v2 `start`, `resume`, `doctor` and provider-call boundaries reject production bindings, live admissions, known Claude/Codex adapters, unknown/unclassified objects, an admitted fake's unadmitted subclass/replacement, and a forged marker: `LIVE_PROVIDER_NOT_ENABLED`, zero adapter methods/process calls or writes/progression. Explicitly admitted inert fakes pass. v1 behavior remains unchanged. |
| T-INJECTED-SPAWNER-REFUSED (AUTO017-R04) | Inject an adapter unrelated to Claude/Codex whose invocation body would call `subprocess.Popen`. Give it no admission (also test a misleading fake class name/`TEST_DOUBLE` attribute and a mixed binding with three admitted fakes). Patch the process primitive with a failing counter and spy all adapter methods. At v2 `start`, `resume` and `doctor`, assert `LIVE_PROVIDER_NOT_ENABLED`, invocation count 0, process count 0, zero writes/progression. No actual process is launched. |
| T-STAGE-START-CLOCK-IDEMPOTENT (AUTO017-R03) | Publish Stage Start at clock A; snapshot authorization, pointer and receipt. Advance fake clock to B and rerun identical logical input. Assert byte-identical stored files, unchanged mtimes, same ID/digest/receipt and no overwrite. Mutate stored timestamp: load/start/continuation refuse before writes/progression/provider calls. Recompute its self-digest but leave pointer/binding pins: still refuse. Repeat later-clock orphan reuse after step-10 crash to prove deterministic recovery by logical ID. |
| T-BUDGETS-UNCHANGED | For a v2 run with `max_remediation_cycles = 3`, behavior is exactly one correction round and one closure verification, as the AUTO-016 ceilings (INV-017-11). |
| T-TRANSITIONS-UNCHANGED | `ALLOWED_RUN_TRANSITIONS`, `RunStatus` and the ceilings equal a literal snapshot of the baseline. |

### 16.4 Security and CLI (T6, T8)

| ID | Test |
|---|---|
| T-INV10-AST (acceptance 6) | Only `MilestoneRunnerApplication.stage_start` constructs `StageStartAuthorization`, and only the `state.py` loader parses one. A planted offender module is detected. |
| T-NO-ENUMERATION | The only directory enumeration in the package remains the baseline `os.listdir` in `plan.py` (the plan root). No new `os.listdir`, `os.scandir`, `Path.iterdir`, `glob` or `rglob` anywhere; in particular none touches `stage-starts/`. |
| T-NO-SUCCESSOR | No non-docstring string literal in the package fully matches `[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-[0-9]{2,3}` (there are none at the baseline, verified). `stage-start` output names only the confirmed Stage. |
| T-CLI-STAGE-START | Typed confirmation `START_STAGE <id>` is required. A wrong line or closed stdin exits 1 with `STAGE_START_NOT_CONFIRMED` and writes nothing. An identical re-run exits 0 with the same ID. A differing re-run exits 1 with `STAGE_START_INPUT_CONFLICT` and leaves the files byte-identical. A v1 configuration exits 1. An overrides file inside the repository exits 1. An unreadable configuration exits 2. |
| T-CLI-UNCHANGED | Every existing `milestone-runner` command's options and help text are unchanged (snapshot of the baseline `--help` output). |

### 16.5 Acceptance (T7; completion marker)

| ID | Test |
|---|---|
| T-TIER1-POLICY | In a disposable Git repository with a v2 configuration and explicitly admitted scripted fake adapters, run `stage-start` (injected confirmation), then `start`, to `READY_FOR_COMMIT_APPROVAL`. `policy.json` exists; its SHA-256 equals `state.policy_digest` and `authorization.effective_policy_digest`; frozen registry context and full authorization digest validate through pointer/binding. Nothing is committed or pushed; the worktree contains no AWE artifact. |

---

## 17. Machine-Verifiable Acceptance Gates

The implementation is COMPLETE only if every gate passes and is recorded with its exact output in the
completion report.

| Gate | Command / check | Pass condition |
|---|---|---|
| G-1 | `pytest -q` | exit 0; every §16 ID maps to at least one passing test |
| G-2 | `pytest -q -m live_cli -rs` | exit 0 (skips allowed, as today) |
| G-3 | `ruff check .` | exit 0 |
| G-4 | `black --check .` | exit 0 (whole tree; pre-commit skips untracked files) |
| G-5 | `mypy --strict` | exit 0 |
| G-6 | `pre-commit run --all-files` | exit 0; any hook mutation outside §5/§6 is restored and recorded |
| G-7 | `git diff --check` | exit 0 |
| G-8 | Changed-path audit: `git diff --name-only main...HEAD` | ⊆ §5 ∪ §5.1 ∪ §6 ∪ the rule-1 governance mirrors |
| G-9 | `workflowctl check-task-state`, `check-governance`, `check-handover --source commit --commit HEAD`, `verify --config self-governance.yaml` | all PASS |
| G-10 | `python -m pytest tests --collect-only -q` | the count equals baseline + new tests, with none removed |
| G-11 | `git diff main...HEAD -- src/ai_workflow_engine/milestone_runner/review.py src/ai_workflow_engine/milestone_runner/approval_git.py src/ai_workflow_engine/milestone_runner/recovery.py src/ai_workflow_engine/milestone_runner/lock.py src/ai_workflow_engine/milestone_runner/providers/` | empty |
| G-12 | Master Plan identity re-verified (§2) | equal |
| G-13 | Digest vectors and v1 corpus SHA-256 recorded in the report | present |
| G-14 | Process proof: no `claude` or `codex` subprocess spawned by any non-live test | as AUTO-016 §25 |
| G-15 | §15.2 exact pinned-baseline generator in comparison mode; T-V1-CORPUS-PROVENANCE | byte-for-byte equality to checked-in T2; 21155 bytes; SHA-256 `c1a1c044526528e04251f5c9fcadbbe246e0fbb5874e2e11420172abbd17b41c`; baseline validation and all 19 v2 migration cases pass |

---

## 18. Traceability to the Frozen Master Plan

### 18.1 Scope items

| Master Plan item (AUTO-017 section unless noted) | Contract |
|---|---|
| Objective | §3 |
| Prerequisites | §4 |
| `ProjectExecutionDefaults` | §7.5 |
| `StageExecutionOverrides` | §7.5, §11.2 |
| `EffectiveStageExecutionPolicy` fields | §7.6 |
| `max_remediation_cycles ∈ {1,2,3}` | §7.3, §7.6, V-3 |
| `on_retry_exhausted` single-member enum | §7.2, V-5 |
| `max_blockers ∈ 1..3`, default 3 (OD-GSE-02) | §7.3, V-4, §10.4 |
| fixed severities (OD-GSE-01) | §7.6, V-11, V-12 |
| `max_owner_extensions = 2` (OD-GSE-03) | §7.3, §7.6 |
| roles → `RoleSelection` (structure only) | §7.4, §7.6, §19 |
| `StageStartAuthorization`, local, typed confirmation | §7.7, §11.2 |
| Stage-start source of truth (OD-GSE-06) | §11.1, §11.3, §11.4 |
| Stage ID grammar generalization | §7.10, A6, A7 |
| `RunRecord` v2 + v1→v2 read-only upgrade | §7.9, §8.2, §15 |
| `resolve_policy`, deterministic and pure | §9 |
| Exclusions (no cycles, events, decisions, Hermes, binding, Git) | §19 |
| Files expected (`policy.py`, `models.py`, `config.py`, `application.py` start path, `state.py`, `cli.py` one verb, tests) | §5, §6 |
| State/schema additions (`STATE_SCHEMA_VERSION = 2`, `policy.json`, `stage-starts/*.json`, `policy_digest`, `stage_start_id`) | §7.9, §10.7 |
| Invariants INV-07 and INV-10 (local form), precedence, least capability | INV-017-1, INV-017-8, §9, §7.3 |
| Acceptance 1 | T-RES-DET, T-DIGEST-VECTORS |
| Acceptance 2 | T-MRC-REJECT, T-MRC-1/2/3 |
| Acceptance 3 | T-POLICY-TAMPER |
| Acceptance 4 | T-V1-CORPUS, T-V1-CORPUS-PROVENANCE, G-15 |
| Acceptance 5 / 5a / 5b | T-START-NO-RECORD / T-START-REGISTRY-* / T-CFG-V2-REVIEW-POLICY |
| Acceptance 6 | T-INV10-AST |
| Restart/idempotency | §7.8, §11.2 steps 8–12, §14.3, T-CLI-STAGE-START, T-STAGE-START-CLOCK-IDEMPOTENT |
| Evidence required | G-13, the completion report |
| Completion marker | T-TIER1-POLICY |
| Must NOT be implemented early | §19, INV-017-11, INV-017-12, T-OPEN |
| §2.1 rules 3–5 | INV-017-9, §19 |
| §3 live-provider isolation gate, clause 1 | §10.5, T-LIVE-REFUSED, T-INJECTED-SPAWNER-REFUSED |
| §4 common requirements (adapters, verification set, tests, scope, completion marker) | §10.5, §17, §6 |
| §7 item 2 (AUTO-016 sections amended) | §18.3 |
| E1, E2, E3, E5, E10, E11, E14, E15, E16 | INV-017-11; §10.4; V-12; §10.5; §7.10; §11; §11.2 step 8; §10.6; §19 |

### 18.2 Refinements this contract makes (none contradicts the Master Plan)

| Refinement | Reason |
|---|---|
| The `stage-starts/key-<key>.json` pointer and `<id>.binding.json` | The no-enumeration invariant; single use; "never overwrites" |
| Phase A performs no durable write | A refused start must not consume the authorization or create a policy-less v2 run (INV-07) |
| Single-code authority matrix under D-AUTO017-01 = B | Bounded OWNER amendment to Master Plan acceptance 5 removes the conflicting absence code |
| Frozen `registry_context` in policy/authorization | The authorization requirement cannot be changed by later configuration |
| Logical ID plus full timestamp-inclusive authorization digest | Stable exact-name reuse and complete persisted-field integrity without changing v1 digests |
| Explicit test-adapter admissions | Unknown injected adapters fail closed; no AUTO-022 provider catalog |
| Closed pointer/binding schemas and hostile-read matrices | All persisted Stage Start authority crosses the same fail-closed boundary |
| Isolated pinned-baseline corpus reproduction | Compatibility is proven against baseline v1 bytes, independently of current code |
| The exact-cell registry parser for v2 | The baseline parser false-positives (§11.4) |
| `review_policy` forbidden in v2 | One source of review parameters; 5b holds structurally |
| `ContractExecutionCeilings` in the v2 configuration | Gives "contract ceiling" a machine-readable, pin-adjacent source |
| Five coined stop codes | Each refusal needs a distinct typed code |
| A6/A7 added beyond the expected file list | Required by the Stage ID generalization |

### 18.3 AUTO-016 contract sections amended (Master Plan §7 item 2)

| AUTO-016 § | Amendment (v2 / policy-governed runs only unless stated) |
|---|---|
| §4 | Entry condition 1 is extended by Phase A (§11.3). v1 is unchanged. |
| §9 | One new command, `stage-start`. The existing thirteen commands are unchanged. |
| §11 | `STATE_SCHEMA_VERSION = 2`, the v1 read upgrade, `policy.json` and `stage-starts/`, and exclusive publication. It applies to all runs, and v1 behavior is otherwise unchanged. |
| §13 | Resume additionally verifies the binding (§10.3). Resume *decision* logic is unchanged. |
| §14 | Milestone ID grammar generalized; v1 plans are unchanged (§7.10). |
| §17 | Only explicitly admitted test doubles may run in v2; live and unclassified adapters are refused (§10.5). v1 is unchanged. |
| §19 | For v2, `ReviewPolicy` is sourced from the frozen policy (§10.4). Budgets and ceilings are unchanged. |
| §21 | Configuration schema v2 (§7.11). v1 is unchanged. |
| §10, §20, §22 | **Not amended.** No state, no edge, no Git authority change. Invariants 1–20 are retained. |

---

## 19. Explicit Exclusions and Prohibited Paths

### 19.1 Behavior excluded (and its owner)

| Excluded | Owner stage |
|---|---|
| Durable lifecycle/event log, `events/`, `operations/`, phase ladder, `state_version`, `last_event_id` | AUTO-018 |
| Restart/crash recovery changes, `RecoveryReconciler`, new `ResumeAction` members, `OWNER_DECISION_REQUIRED`, `PendingDecision`, `AMBIGUOUS_RECOVERY` | AUTO-019 |
| Any multi-cycle remediation; any budget or ceiling raise; `CLOSURE_VERIFYING → NEEDS_CORRECTION`; `FINDING_SET_FROZEN`; discovery-overflow routing; any *use* of `max_remediation_cycles` | AUTO-020 |
| The OWNER Decision API; `DecisionRequest`/`Response`; `EXTEND_REMEDIATION`/`KEEP_FROZEN`/`ABORT_STAGE`/`AMEND_STAGE_CONTRACT`; `SUPERSEDED`; any *use* of `max_owner_extensions` or `on_retry_exhausted`; generalized `START_STAGE` ingestion; revocation or replacement of a stage-start | AUTO-021 |
| Runtime provider/model dispatch; the provider catalog; `ProviderBinding` generalization; any *use* of `roles`; `ModelProvenance`; type-level reviewer read-only; unknown-ID refusal; the independence rule | AUTO-022 |
| Hermes adapter, `RunEnvelope`, `ExecutionPort`, FA-5a confinement, and opening the live-provider gate | AUTO-023 |
| Authenticated OWNER decisions, attestation, nonces, expiry, principal registry | AUTO-024 |
| Telegram transport | AUTO-025 |
| Controlled Git automation, and any change to `approval_git.py` or the commit/push gates | AUTO-026 |

**Behavioral effect of the frozen fields in AUTO-017.** `max_blockers` has effect (§10.4). The
following are **recorded, validated and frozen with no effect**: `max_remediation_cycles`,
`on_retry_exhausted`, `max_owner_extensions`, `roles`, `contract_ceilings`, and the two input
digests. Retry exhaustion still ends at AUTO-016's existing `HUMAN_INTERVENTION_REQUIRED` stop.

### 19.2 Prohibited paths (must remain byte-unchanged)

- Everything not listed in §5, §5.1 or §6. In particular:
  - `src/ai_workflow_engine/milestone_runner/{review,approval_git,recovery,lock,results,scope,verification,git_inspect}.py`
  - `src/ai_workflow_engine/milestone_runner/providers/**`
  - `src/ai_workflow_engine/milestone_runner/__init__.py`
- `src/ai_workflow_engine/{config,models,result,exceptions,provenance}.py` and every other
  `src/ai_workflow_engine/*/` subpackage, including `schema/**`, `workflow/**`, `git/**`,
  `governance/**`, `prompt/**` and `successor_planning/**`. `src/ai_workflow_engine/schema/` is
  the workflow-contract schema package, unrelated to runner schema v2, and is **not** touched.
- `agentos_workflow/**`, `agentos_dashboard/**`, `scripts/**`, `examples/**`, `.github/**`,
  `pyproject.toml`, `.pre-commit-config.yaml`, `self-governance.yaml`, `handover/**`.
- `docs/**` other than D1 and the rule-1 governance mirrors of the authorization and closure acts.
  The Master Plan, this contract after authorization, the AUTO-016 contract and every other
  stage prompt are read-only.
- The baseline `_registry_authorizes` function body, and the v1 behavior of `run_preflight`.
- The prototype runners (`~/.local/share/auto015-runner/`, `~/.local/share/auto016-runner/`).
- No import of `agentos_workflow` from `milestone_runner/` (the existing AST test).

### 19.3 Operational prohibitions

No live provider, Hermes, Telegram or network in any test. No commit, push, tag, merge, reset,
rebase, stash or branch switch by any AWE code path added here. No new dependency.

---

## 20. Deferred Obligations (AUTO-018 … AUTO-026)

| ID | Stage | Obligation created or left by AUTO-017 |
|---|---|---|
| DO-018-1 | AUTO-018 | Emit the stage-start binding and the policy publication as events, carrying `policy_digest` and `stage_start_id`. Bind `policy_digest` into every event (INV-07). |
| DO-018-2 | AUTO-018 | Decide whether `policy.json` and the binding file are projections rebuilt from events or remain primary artifacts. AUTO-017's exclusive publication is the baseline. |
| DO-019-1 | AUTO-019 | Resume re-validation includes `policy_digest` (Master Plan AUTO-019 scope). Reuse §10.3 and never re-resolve. Extend §14.3's crash windows into the general matrix. |
| DO-020-1 | AUTO-020 | Consume `max_remediation_cycles` as the automatic budget. Raise the correction and closure ceilings to 3 only there. Keep `max_blockers` overflow routing per OD-GSE-02. |
| DO-021-1 | AUTO-021 | Consume `on_retry_exhausted` and `max_owner_extensions` (≤ 2). |
| DO-021-2 | AUTO-021 | Generalize `START_STAGE` ingestion from AUTO-017's `stage-start`. Define any revocation or replacement of an unbound stage-start (§11.2 consequence). Preserve INV-017-8 and the single-use binding. |
| DO-022-1 | AUTO-022 | Introduce the provider catalog. Validate every frozen `RoleSelection` of an already-started run against it on resume, **refusing, never re-resolving**. Make reviewer read-only type-level. Apply the OD-GSE-08 ruling. Add `ModelProvenance`. |
| DO-022-2 | AUTO-022 | Replace the non-binding status of `roles` with binding. Until then, dispatch ignores `roles`. |
| DO-023-1 | AUTO-023 | Replace `live_provider_execution_enabled()` with the evidenced FA-5a predicate plus per-run self-test. Extend the explicit fail-closed admission gate to admit only confined live adapters; retain refusal of unknown/unclassified adapters. |
| DO-024-1 | AUTO-024 | Authenticate `START_STAGE`. `StartPrincipal` gains members only by that contract. |
| DO-025-1 | AUTO-025 | None created. `stage-start` is local only. |
| DO-026-1 | AUTO-026 | Bind `policy_digest` into approvals and Git intents (INV-07 "every approval"). In AUTO-017, approvals are protected indirectly: every approval command loads the record, and the load verifies the policy (§10.3). |
| DO-ALL-1 | all | Keep v1 supervised behavior unchanged unless a contract explicitly amends it. |

---

## 21. OWNER Items Surfaced by Contract Preparation

These author-reported items retain their accepted disposition. OI-017-2 is resolved by the closed
OWNER ruling; OI-017-1 and OI-017-3 remain deferred as stated. No additional decision is requested.

| Item | Reported item | Accepted disposition |
|---|---|---|
| OI-017-1 | **Pre-existing defect in the v1 registry check.** At the baseline, `_registry_authorizes` returns *authorized* for `AUTO-017` (`NOT_STARTED`) and `AUTO-016` (`COMPLETE`), because it matches §5 log prose. This is the previously reported baseline observation, not new discovery. | Deferred. AUTO-017 uses the strict exact-cell parser for **v2 only** and leaves v1 byte-unchanged. Fixing v1 is outside this remediation and this stage. |
| OI-017-2 | **Acceptance 5 vs. OD-GSE-06 wording.** The frozen review identified two codes for registry authorization without a matching native record (AUTO017-R01). | **RESOLVED — D-AUTO017-01 = B.** Exactly `STAGE_START_AUTHORIZATION_CONFLICT`; Master Plan acceptance 5 and §6.1 record the bounded amendment. §11.3, §14.2 and §16.3 apply it consistently. |
| OI-017-3 | **Provider catalog in the preparation brief vs. the Master Plan.** The brief lists "provider/runtime catalog structures". The Master Plan assigns the catalog to AUTO-022. | The catalog is deferred (§7.4, DO-022-1). AUTO-017 validates identity by grammar only. |

---

## 22. Completion Marker

AUTO-017 is COMPLETE only when all of the following hold:

1. Every §17 gate is PASS and recorded in `docs/reports/workflow-automation/AUTO-017-completion-report.md`.
   The report also records the digest vectors, the v1 corpus identity and exact isolated baseline
   generation/comparison commands (G-15), the
   Tier-1 `policy.json` digest, the changed-path audit, and a per-acceptance-criterion PASS/FAIL.
2. T-TIER1-POLICY demonstrates `policy.json` produced end to end in a disposable repository by a
   Tier-1 run with test-double adapters.
3. One bounded independent implementation review has run, and every blocking finding is closed.
4. The OWNER records `IN_PROGRESS → COMPLETE` in `STAGE_REGISTRY.md` §4/§5 and `Current → Done` in
   `docs/TASK_QUEUE.md`.

Completion authorizes nothing. AUTO-018 still requires its own contract, one bounded review, and a
separate written OWNER authorization.

---

## 23. Authorization Boundary

This document is a contract **candidate**. It authorizes no branch, no implementation prompt, no
production change and no lifecycle promotion. AUTO-017 remains `NOT_STARTED` / `Planned` and
unauthorized until the OWNER writes "I authorize AUTO-017" (or an equivalent explicit directive)
bound to a reviewed revision of this file by its SHA-256.

### 23.1 Frozen remediation scope and handoff

Revision 2 remediates exactly AUTO017-R01, AUTO017-R02, AUTO017-R03, AUTO017-R04, AUTO017-R05 and
AUTO017-R06 from the one completed independent discovery review. No new discovery or finding IDs.
R01 is traced to §2/§2.1, §11.3, §14.2 and T-START-NO-RECORD; R02 to §7.5–§7.7, §10.3 and the
three T-FREEZE-REGISTRY tests; R03 to §7.8, §11.2 and T-STAGE-START-CLOCK-IDEMPOTENT; R04 to §10.5
and T-INJECTED-SPAWNER-REFUSED; R05 to §10.8 and the three hostile-artifact matrices in §16.2;
R06 to §15.2, T-V1-CORPUS-PROVENANCE and G-15. These are contract/test specifications, not executed
AUTO-017 production behavior or implementation test results. Independent closure and OWNER
implementation authorization remain separate acts. The six OPEN decisions in §2.2 stay OPEN.

`AUTO_017_CONTRACT_REMEDIATION_CANDIDATE_READY`
