# AUTO-017 implementation remediation report

This is the unstaged remediation candidate for exactly `AUTO017-IMPL-R01` through
`AUTO017-IMPL-R06`. No discovery was reopened, no finding ID added, and no Stage lifecycle
or Git-history authority was exercised. The original report is preserved below as explicitly
historical/superseded evidence; its old hashes, blocked verdict, socket failures and stylesheet
hang do not describe the current controlling result.

## Current authority and baseline

Repository `/home/afshin-jian/ai-workflow-engine`; committed HEAD
`8d14e4394874078289653ea26483c54e968d6df2`. Pre-edit checks confirmed the expected HEAD,
empty index, clean `git diff --check`, and both frozen hashes. The starting tree already held
an unstaged implementation candidate and six authority/governance edits; these were retained.

| CLOSED/FROZEN artifact | Lines | Bytes | SHA-256 |
|---|---:|---:|---|
| `docs/workflow-automation/stage-prompts/AUTO-017.md` | 1717 | 138969 | `50760879b2f64c395c8c3c5ee83c3bdac1a8b8456588b144c068f01d1080b1e8` |
| `docs/workflow-automation/successor-planning/AWE-GOVERNED-AUTONOMOUS-STAGE-EXECUTION-MASTER-PLAN.md` | 1698 | 113150 | `8ab499c0240cc542e735eb5d1953dcd93994ebd87f1ef7413e9346805d613077` |

Accepted OWNER rulings: `D-AUTO017-01 = B`, `D-AUTO017-02 = B`, `D-AUTO017-03 = A`.
The last ruling resolves the former R02 contract conflict and authorizes the exact-name witness.

## Frozen finding remediation matrix

| Finding | Remediation | Regression evidence |
|---|---|---|
| AUTO017-IMPL-R01 | Missing pointer with binding, witness or published-run evidence refuses `STAGE_START_INPUT_CONFLICT` before lock/write; genuine pre-pointer authorization orphan remains recoverable. | Corrected pointer/missing hostile replay cell; `test_auto017_remediation_missing_pointer_after_consumption`; orphan recovery. |
| AUTO017-IMPL-R02 | Strict immutable consumption witness, exclusive B-0 before binding; cross-artifact verification and single-run crash recovery; loss never grants a second consumption. | `test_auto017_remediation_witness_first`, `witness_second_refused`, `hostile_witness`, `published_consumption_loss`, `witness_crash_recovery`, `raced_b0_never_replaces_winner`, `exact_name_witness_without_enumeration`, `b0_b1_revalidation_rejects_hostile_witness`, `witness_parent_links`, `stage_start_cannot_repair_consumed_binding`. Names abbreviated after the common prefix. |
| AUTO017-IMPL-R03 | Every parent is opened no-follow relative to the previous descriptor; creation, linking, collision reading, parent fsync and temporary cleanup use the anchored descriptor. | `test_auto017_remediation_parent_swap_cannot_escape`: authority/policy payloads, swaps before temporary creation and linking. |
| AUTO017-IMPL-R04 | Current frozen identities, OWNER rulings, controlling complete-suite evidence and G-1 Path B replace stale current claims; old runs remain historical. | This report and final identity/byte checks. |
| AUTO017-IMPL-R05 | Governed load requires `record.run_id == store.run_id` before policy/authority acceptance; mismatch is `POLICY_BINDING_MISMATCH`. | `test_auto017_remediation_substituted_run_directory`: all eight mutating commands, valid substituted state/policy, zero writes/locks/providers. |
| AUTO017-IMPL-R06 | Authorization clock sampled only after locked recheck finds both authorization and pointer absent; lock-holder diagnostics use an independent clock. Orphan bytes/timestamp are reused. | `test_auto017_stage_start_orphan_reuses_bytes_at_later_clock` now injects a clock that raises if called; ordinary idempotent replay retained. |

## R02 witness and recovery details

`policy.py` defines the closed strict `StageStartConsumptionWitness`. Its exact filename is
`stage-starts/<stage_start_id>.consumed.json`. It binds schema version, Stage Start key/ID,
Stage ID, contract SHA-256, authorization digest, policy digest, arbitrary grammar-valid consuming
run ID, exact binding digest and witness integrity digest. `authority_json_bytes` supplies canonical
bytes; `authority_digest` covers all fields except `witness_digest`. Nothing derives a run ID
from authorization data.

The bounded no-follow reader rejects malformed JSON, duplicate keys, invalid UTF-8, noncanonical
bytes, bad versions/fields/grammars, oversized files, symlinks and inconsistent or substituted pins.
The expected binding digest is reconstructed in memory from the validated authorization and
recorded run ID, even when the binding is absent. All lookups use exact names; no directory scan.

B-0 exclusively publishes the witness before B-1. Recovery skips witness publication, adopts its
recorded run, and completes only that pinned binding/policy/state while `state.json` is absent.
B-1/B-2 recovery preserves the immutable artifacts. Published state forbids restart, including
B-3 without `latest-run.json`. Binding/latest-pointer loss leaves the witness enforcing single use.
Missing required witnesses are never recreated, and conflicting B-0 publication never overwrites.
Mutating continuations require both binding and witness and matching loaded-run identity.

The witness is local consistency and single-use evidence, not authenticated attribution. Deleting
or consistently rewriting every consumption artifact is outside this guarantee; authenticated
consumption remains deferred as the frozen contract requires.

## Current G-1 adjudication

`D-AUTO017-02 = B`; controlling outcome: `AUTO_017_G1_PASS_PATH_B`.
The OWNER-provided completed-suite evidence in the remediation handoff is:

```text
3 failed, 9570 passed, 34 deselected, 2 warnings
```

| Current non-passing test | Accepted attribution |
|---|---|
| `tests/test_engine_provenance.py::test_worktree_root_is_none_outside_any_repository` | ENVIRONMENTAL |
| `agentos_dashboard/tests/test_parsing_task_queue.py::test_real_remaining_tasks_historical_headings_do_not_degrade_confidence` | BASELINE_PREEXISTING |
| `agentos_dashboard/tests/test_services_consistency.py::test_real_repository_current_task_has_no_false_parser_finding` | BASELINE_PREEXISTING |

These are the exact current three non-passing results. Attribution and Path B status are carried
forward from the completed independent review and explicit OWNER handoff, not newly adjudicated
by this implementer. The historical stylesheet hang was **not** a current non-passing result.
Earlier socket failures, interrupted counts and the historical blocked verdict are superseded.
This remediation does not claim a fresh full-suite execution or an exit-0 full-suite result.
The historical section retains the available prior commands/environment/proof; this handoff did
not supply a new raw-log path or named reviewer, and this report does not invent either.

## Remediation validation

Focused regressions used CPython 3.13.5, pytest 8.4.2 and Pydantic 2.11.7 under
`/home/afshin-jian/miniconda3/bin`. The required suite uses the existing project environment:
CPython 3.11.15 / Pydantic 2.13.4, which includes the declared `hatchling.build` backend.
No dependency, configuration or live-provider change. For the required suite set
`PATH=/home/afshin-jian/miniconda3/envs/ai-workflow-engine/bin:/home/afshin-jian/miniconda3/bin:/usr/bin:/bin`.
Commands:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:src pytest -q tests/test_milestone_runner_application.py tests/test_milestone_runner_state.py -k 'remediation or stage_start_orphan_reuses or stage_start_reuse_rejects_hostile_artifacts or binding_crash'
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:src pytest -q tests/test_milestone_runner_*.py tests/test_cli.py
ruff check .
mypy --strict
git diff --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:src workflowctl verify --config self-governance.yaml
```

| Check | Exact result |
|---|---|
| Focused R01/R02/R03/R05/R06 regression selection | `724 passed, 2929 deselected in 149.30s (0:02:29)`; exit 0 |
| Additional recovery/identity/parent-link subset | `83 passed, 3100 deselected in 44.91s`; exit 0; included in final focused selection |
| Required milestone-runner + CLI suite (current, Ubuntu-2 project environment) | `5575 passed, 1 skipped, 2 deselected`; no failure or error |
| Ruff (latest, project environment) | `All checks passed!`; exit 0 |
| Strict mypy (latest, project environment) | `Success: no issues found in 193 source files`; exit 0 |
| Black, whole repository (`black --check .`) | `368 files would be left unchanged`; exit 0 |
| Test collection (`python -m pytest tests --collect-only -q`) | `7352/7354 tests collected (2 deselected) in 2.93s`; exit 0; historical 6743 selected + 609 new cases |
| Whitespace (latest) | `git diff --check`: no output; exit 0 |
| Governance (latest `workflowctl verify`) | All five checks PASS; `Verdict: PASS`; exit 0 |

The one current skip in the required targeted suite is
`tests/test_milestone_runner_acceptance.py:2189`
(`TestPrototypeRunnerUnchanged::test_a_complete_run_leaves_the_prototype_untouched`), reason:
`the AUTO-015 prototype is not installed at /home/afshin-jian/.local/share/auto015-runner`.
It is the test's own pre-existing environmental guard (the prototype directory is absent on
Ubuntu-2); remediation added no skip. The earlier `5576 passed, 2 deselected in 902.90s` line
is superseded by this current result.

Governance details: Git invariants PASS; 1 Current / 61 Done / 9 Planned tasks; consistent mirrors;
36 stages across two registries; one working-tree handover record. Earlier raw remediation logs:
`/tmp/auto017-focused-final.log`, `/tmp/auto017-targeted-project.log` (superseded 5576-pass run),
`/tmp/auto017-governance.log`. The current targeted result was supplied in the remediation
handoff; no new raw-log path was supplied and none is invented.

**Historical/superseded environment evidence (not current):** the first full targeted attempt,
in the default Python 3.13 environment (not the project environment), completed with
`5572 passed, 2 deselected, 4 errors in 874.89s (0:14:34)` (exit 1). All four errors share the
wheel fixture's `BackendUnavailable: Cannot import 'hatchling.build'`, before the test bodies:

- `tests/test_milestone_runner_acceptance.py::TestWheelContainsMilestoneRunner::test_the_wheel_carries_every_module_of_section_8`
- `tests/test_milestone_runner_acceptance.py::TestWheelContainsMilestoneRunner::test_the_wheel_still_carries_the_three_top_level_packages`
- `tests/test_milestone_runner_acceptance.py::TestOutOfTreeImport::test_the_package_imports_from_a_fresh_environment_outside_the_repository`
- `tests/test_milestone_runner_acceptance.py::TestOutOfTreeImport::test_the_command_group_is_reachable_from_the_installed_console_script`

These `hatchling.build` errors were an artifact of the wrong interpreter and are superseded;
they are not current evidence. In the project environment the four packaging cases passed
(historical `4 passed in 10.34s`), and the current Ubuntu-2 project-environment targeted result
above (`5575 passed, 1 skipped, 2 deselected`) contains no error. Historical raw output:
`/tmp/auto017-targeted.log`, `/tmp/auto017-wheel-diagnostic.log` (`2 errors in 1.02s`),
`/tmp/auto017-wheel-project.log`. Nothing was installed. This superseded targeted-environment
result does not alter the controlling complete-suite G-1 inventory above.

Test-first evidence: the initial bounded regression run reproduced R01, R02, R03, R05 and R06
with `20 failed, 114 passed, 2930 deselected in 36.72s`. A further R02 replay test reproduced
missing-binding acceptance (`1 failed, 3182 deselected in 3.64s`) before the witness-run state
check was added. Intermediate new-test setup errors (the literal `latest-run` instead of
`latest-run.json`, and the pre-existing state-reader error class) were corrected; all affected
cases pass in the final focused result. No existing test was weakened or suppressed.
The report-only R04 change is verified by exact identity and evidence comparison.

## Remediation paths and exclusions

Exactly six files changed during this remediation:

- `src/ai_workflow_engine/milestone_runner/application.py`
- `src/ai_workflow_engine/milestone_runner/policy.py`
- `src/ai_workflow_engine/milestone_runner/state.py`
- `tests/test_milestone_runner_application.py`
- `tests/test_milestone_runner_state.py`
- `docs/reports/workflow-automation/AUTO-017-completion-report.md`

All six are in the existing implementation/test/report allowlist. No new path is required.
The pre-existing authorized providers-test inventory expansion is untouched by remediation.
Raw-byte comparison of all 907 tracked paths outside the authorized candidate paths and the six
pre-existing authority/governance edits found zero differences from HEAD. This includes every
explicit excluded implementation module, all provider modules, schema packages, dashboard,
workflow, scripts, examples, configuration and handover paths. The v1 `_registry_authorizes`
function, `RunStatus`, `TERMINAL_RUN_STATES`, `ALLOWED_RUN_TRANSITIONS` and application terminal
states are byte-identical to HEAD. The v1 corpus is unchanged from the remediation baseline.
The six pre-existing authority/governance edits are byte-identical to the starting tree; the
frozen contract and Master Plan match their current OWNER hashes above, rather than their
superseded HEAD blobs. No test is removed, skipped, weakened or xfailed by remediation.

## Final Git state and remediation status

All six frozen findings are remediated and the required targeted suite passes in the current
Ubuntu-2 project environment (`5575 passed, 1 skipped, 2 deselected`; the one skip is the
environmental AUTO-015 prototype guard at `tests/test_milestone_runner_acceptance.py:2189`).
G-1 remains `AUTO_017_G1_PASS_PATH_B` under `D-AUTO017-02 = B`. The candidate
remains unstaged; independent closure review and OWNER lifecycle approval remain separate acts.
No commit, push, tag, merge, reset, rebase, checkout or switch was performed. HEAD remains
`8d14e4394874078289653ea26483c54e968d6df2` and `git diff --cached --name-only` is empty.

Final `git status --short` (the same 24 paths present at remediation entry):

```text
 M docs/DECISION_LOG.md
 M docs/PROJECT_STATE.md
 M docs/TASK_QUEUE.md
 M docs/current_task.md
 M docs/workflow-automation/stage-prompts/AUTO-017.md
 M docs/workflow-automation/successor-planning/AWE-GOVERNED-AUTONOMOUS-STAGE-EXECUTION-MASTER-PLAN.md
 M src/ai_workflow_engine/cli.py
 M src/ai_workflow_engine/milestone_runner/application.py
 M src/ai_workflow_engine/milestone_runner/config.py
 M src/ai_workflow_engine/milestone_runner/models.py
 M src/ai_workflow_engine/milestone_runner/plan.py
 M src/ai_workflow_engine/milestone_runner/prompts.py
 M src/ai_workflow_engine/milestone_runner/state.py
 M tests/test_cli.py
 M tests/test_milestone_runner_acceptance.py
 M tests/test_milestone_runner_application.py
 M tests/test_milestone_runner_plan.py
 M tests/test_milestone_runner_providers.py
 M tests/test_milestone_runner_security.py
 M tests/test_milestone_runner_state.py
?? docs/reports/workflow-automation/AUTO-017-completion-report.md
?? src/ai_workflow_engine/milestone_runner/policy.py
?? tests/milestone_runner_state_v1_corpus.json
?? tests/test_milestone_runner_policy.py
```


---

The following original report is retained solely as historical/superseded evidence. Its present
tense, older identities, counts and verdict apply only to that earlier execution.

## Historical/superseded — original implementation report

This report records an unstaged implementation candidate, not Stage completion, OWNER approval,
or Git-history authority. AUTO-017 and its successor lifecycle states have not been promoted.

## Historical/superseded — Authority and baseline

- OWNER authorization: `AUTO_017_IMPLEMENTATION_AUTHORIZED`.
- Bounded test expansion: `AUTO_017_SCOPE_EXPANSION_01_AUTHORIZED`.
- Repository: `/home/afshin-jian/ai-workflow-engine`, branch `main`.
- Implementation HEAD: `8d14e4394874078289653ea26483c54e968d6df2`.
- The original pre-edit baseline was clean with an empty index. Continuation verified the same
  HEAD and empty index and retained the authorized unstaged partial candidate.
- Contract: `docs/workflow-automation/stage-prompts/AUTO-017.md`, 1552 lines, 120530 bytes,
  SHA-256 `80358d0f368a74e845c034072a813c85c5b90c20e5717c668235e2bc4e2b969d`.
- Master Plan: `docs/workflow-automation/successor-planning/AWE-GOVERNED-AUTONOMOUS-STAGE-EXECUTION-MASTER-PLAN.md`,
  1675 lines, 111414 bytes,
  SHA-256 `8ca4d72d9f2487f9a39f52c8dca653d74c1257b993878200f4305c97eb4ed3f7`.
- Both frozen documents were reverified and remain unchanged.

## Historical/superseded — Implementation

| Contract | Implementation |
|---|---|
| §§7–9: vocabulary, strict schemas, resolution | Pure `policy.py`; closed frozen schemas; exact integer versions; whole-role overrides; contract ceilings; immutable normalized registry context; deterministic canonical digests; fixed severity/extension/retry values; identifier syntax without provider catalog lookup. |
| §§7.9, 8, 15: state compatibility | State schema 2 publication; read-only v1 upgrade; rejection of poisoned v1 policy fields; paired state pins; policy byte-digest and schema verification at every governed load. |
| §7.10: Stage grammar | Shared Stage/milestone grammar, generalized prompt context, preserved legacy v1 plan filtering, exact configured v2 Stage prefix. |
| §§10.6–10.8: immutable persistence | Single redaction write boundary; exclusive hard-link publication; bounded descriptor-relative no-follow readers; duplicate-key rejection at every depth; canonical persisted documents; filename, self-digest and cross-artifact pins. |
| §11.2: Stage Start | One additive CLI command; explicit Stage ID and typed confirmation; Stage Start construction only in the application method; logical identity independent of timestamp; full timestamp integrity; read-only identical replay; orphan record reuse without enumeration. |
| §§10.2, 11.3: binding | Read-only Phase A; fixed D-AUTO017-01=B refusal; registry/context and contract-pin checks; exclusive single-use binding; adoption after B1/B2 interruption; policy publication before initial state; durable initial PREFLIGHT stop that ordinary resume can clear after correction. |
| §§10.3, 11.4: continuation | Frozen policy/configuration comparison before changed registry authority can be consulted; hostile authority refusal before lock/write/invocation; binding validation before registry agreement; no-follow CLI run lookup; lost published binding never recreated. |
| §10.5: admission | Immutable explicit exact-object/exact-type test manifest; all bound adapters checked; unknown, replacement, inherited, relabelled production and live bindings refused; registry/pin rechecked at actual invocation and retry boundaries. |
| §§10.4, 19: runtime boundaries | Frozen max_blockers supplies the existing review policy. Runtime review/correction/closure budgets remain 1/1/1. Role selections, remediation cycles, retry exhaustion and extensions have no added runtime effect. No later-stage implementation. |

The v1 `_registry_authorizes` function body, transition table, RunStatus, terminal states and
existing budget ceilings retain their baseline source bytes. The legacy supervised path and
Git/recovery modules retain their contracted behavior. A baseline build cannot read state schema
2; downgrade is unsupported.

## Historical/superseded — Candidate paths

Production:

- `src/ai_workflow_engine/milestone_runner/policy.py` (new)
- `src/ai_workflow_engine/milestone_runner/models.py`
- `src/ai_workflow_engine/milestone_runner/config.py`
- `src/ai_workflow_engine/milestone_runner/state.py`
- `src/ai_workflow_engine/milestone_runner/application.py`
- `src/ai_workflow_engine/milestone_runner/plan.py`
- `src/ai_workflow_engine/milestone_runner/prompts.py`
- `src/ai_workflow_engine/cli.py`

Tests/data:

- `tests/test_milestone_runner_policy.py` (new)
- `tests/milestone_runner_state_v1_corpus.json` (new)
- `tests/test_milestone_runner_state.py`
- `tests/test_milestone_runner_application.py`
- `tests/test_milestone_runner_plan.py`
- `tests/test_milestone_runner_security.py`
- `tests/test_milestone_runner_acceptance.py`
- `tests/test_milestone_runner_providers.py`
- `tests/test_cli.py`

Documentation:

- `docs/reports/workflow-automation/AUTO-017-completion-report.md` (new, contract D1)

The providers test expansion changes only its inventory/safety-count assertions and explanatory
count docstring: non-spawning modules 15→16 and addition of `policy.py`. Spawn capabilities,
restrictions and provider-safety assertions remain intact. No other path expansion was used.

## Historical/superseded — Required test traceability

Names below refer to the authorized test files, with prefixes shortened for readability.

| Contract test IDs | Named coverage |
|---|---|
| T-CFG-V2-OK, T-CFG-V1-UNCHANGED, T-CFG-VERSION | policy: `test_v2_configuration_dispatch`, `test_v1_configuration_accept_refuse_matrix`, `test_configuration_version_is_exact_before_validation` |
| T-CFG-V2-REVIEW-POLICY, T-CFG-V2-REGISTRY-KEY | policy: `test_v2_review_policy_is_forbidden_whatever_content`, `test_v2_stage_requires_explicit_authority_keys`, `test_registry_configuration_normalizes_and_protects_paths`, `test_registry_paths_refuse_hostile_input` |
| T-MRC-1, T-MRC-2, T-MRC-3, T-MRC-REJECT, T-BLOCKERS | policy: `test_integer_fields_accept_each_permitted_value`, `test_integer_fields_reject_non_exact_values`, `test_null_means_unset_only_for_input_scalars` |
| T-ORE, T-EXT, T-SEVERITY, T-ACCEPTED | policy: `test_retry_exhaustion_is_closed`, `test_resolution_fixed_fields_and_unknown_identifiers`, `test_fixed_and_future_fields_are_unrepresentable_inputs`, `test_policy_fixed_values_reject_mutation`; application authority matrix |
| T-RES-DEFAULTS, T-RES-OVERRIDE, T-RES-PARTIAL | policy: `test_defaults_and_whole_role_overrides_follow_precedence` |
| T-RES-CEILING, T-RES-BUILTIN | policy: `test_explicit_override_refuses_ceiling_while_defaults_are_capped`, `test_builtins_are_used_without_default_file_and_missing_roles_refuse` |
| T-RES-DET | policy: `test_resolution_is_exhaustively_deterministic` (all 576 combinations) |
| T-DIGEST-VECTORS, T-CANONICAL-UNCHANGED | policy: `test_fixed_policy_digest_vectors`, `test_canonical_v1_bytes_and_literal_digest_remain_unchanged` |
| T-ROLE-KEYS, T-ROLE-ALIAS | policy: `test_role_keys_use_only_persisted_provider_vocabulary`, `test_role_keys_accept_any_subset_and_reject_duplicate_json_keys`, `test_role_alias_is_exact_immutable_bijection` |
| T-ROLE-IDENTITY, T-ROLE-UNKNOWN | policy: `test_role_identity_is_retained_through_authorization_and_policy_json`, `test_policy_module_is_pure_and_no_catalog_symbol_exists` |
| T-ROLE-GRAMMAR, T-ROLE-REVIEWER-RO | policy: `test_role_identity_grammar_and_timeout_are_strict`, `test_role_timeout_is_required_and_identity_boundaries_are_accepted`, `test_reviewer_capability_is_read_only` |
| T-AUTH-SELF, T-REGISTRY-CONTEXT-DIGEST | policy: `test_authorization_every_persisted_field_is_integrity_bound`, `test_authorization_binding_mismatch_refuses_even_with_fresh_self_digests`, `test_authorization_logical_id_is_stable_but_full_digest_binds_clock`, `test_authorization_requires_valid_utc_calendar_timestamp`, `test_registry_context_changes_policy_and_logical_authority_identity` |
| T-STAGE-ID, T-PROMPT-STAGE-ID | policy: generalized Stage/milestone grammar tests, `test_prompt_context_uses_same_generalized_stage_grammar`; plan: `TestVersionedMilestoneGrammar` |
| T-OPEN | policy: `test_open_owner_decisions_remain_structurally_unencoded`; security: `TestAuto017DeferredFeaturesStayAbsent` |
| T-V1-CORPUS, T-V1-CORPUS-PROVENANCE, T-V1-POISONED | state: `TestAuto017Migration`, `TestAuto017CorpusProvenance` (all 19 migration cases plus baseline reproduction) |
| T-STATE-VERSION, T-PAIRING | state: `test_exact_state_version_dispatch`, `test_auto017_run_record_requires_both_policy_pins` |
| T-POLICY-TAMPER, T-EXCLUSIVE | state: `TestAuto017PolicyFreeze`, `TestAuto017ExclusivePublication` |
| T-NO-REPLACE, T-WRITE-AST | state: `TestAuto017ExclusiveWriteStructure`; existing write/removal structural assertions |
| T-REVISE-GUARD | application: `test_auto017_revise_and_transition_updates_cannot_replace_policy_pins`, `test_auto017_transition_preserves_both_policy_pins` |
| T-START-POINTER-HOSTILE, T-START-AUTH-HOSTILE, T-START-BINDING-HOSTILE | application: `test_auto017_hostile_persisted_authority_matrix`, `test_auto017_stage_start_reuse_rejects_hostile_artifacts`, `test_auto017_valid_same_stage_different_policy_refuses_run_pin`, ancestor/link spies and valid mutable-entry controls; state: `TestAuto017HostileAuthority` |
| T-START-NO-RECORD, T-START-REGISTRY-NOT-AUTH, T-START-REGISTRY-PROMPT, T-START-NO-REGISTRY | application: `test_auto017_authority_matrix_registry_states`, `test_auto017_registry_parser_fail_closed`, `TestAuto017Binding.test_missing_authority_matrix` |
| T-REGISTRY-PARSER | application: `test_auto017_registry_parser_pinned_real_registry` |
| T-START-BINDS, T-START-SINGLE-USE | application: `test_stage_start_and_start_end_to_end`, `test_auto017_stage_start_is_single_use`, `test_auto017_binding_crash_adopts_run_id`, `test_auto017_missing_published_binding_never_rebinds` |
| T-FREEZE-DEFAULTS, T-FREEZE-CONFIG | application: `test_changed_defaults_do_not_reinterpret`, `test_auto017_changed_ceilings_refuse_continuations` |
| T-FREEZE-REGISTRY-PATH-NULL, T-FREEZE-REGISTRY-NULL-PATH, T-FREEZE-REGISTRY-PATH-PATH | application: `test_auto017_registry_declaration_is_frozen` (start and every mutating continuation) |
| T-NO-RESOLVE, T-MODE-MIX, T-V1-NO-AUTONOMY | security: `TestAuto017NoReresolution`; application: `test_auto017_configuration_record_mode_mismatch`, `test_auto017_v1_lifecycle_has_no_policy_artifacts` |
| T-LIVE-REFUSED, T-INJECTED-SPAWNER-REFUSED | application: `test_auto017_adapter_admission_fails_closed`, `test_auto017_manifest_is_copied_and_provider_boundary_rechecks`, unknown-adapter and actual-invocation/retry guards |
| T-STAGE-START-CLOCK-IDEMPOTENT | application: `test_stage_start_clock_idempotent`, `test_auto017_stage_start_orphan_reuses_bytes_at_later_clock`, hostile timestamp cases |
| T-BUDGETS-UNCHANGED, T-TRANSITIONS-UNCHANGED | acceptance: `TestAuto017BudgetsUnchanged`; security: `TestAuto017TransitionsAndBudgetsUnchanged` |
| T-INV10-AST, T-NO-ENUMERATION, T-NO-SUCCESSOR | security: `TestAuto017AuthorizationConstructionAuthority`, `TestAuto017NoEnumeration`, `TestAuto017NoSuccessorSelection` |
| T-CLI-STAGE-START, T-CLI-UNCHANGED | CLI: AUTO-017 confirmation/receipt/refusal tests, `test_auto017_existing_cli_handlers_and_options_byte_unchanged`, `test_auto017_existing_cli_help_matches_baseline` |
| T-TIER1-POLICY | acceptance: `TestAuto017Tier1Policy` |

## Historical/superseded — Fixed digest evidence

Policy digest vectors, in test index order:

```text
0  3b0286a4defb7183644183dcf1aabcfd15a449186050851199819a928dcb437b
1  7193bd03e06429fca66146d7e923cbca94deac2f9184e315fa6e27e1e7e9ae07
2  77d817cbacb32d3329d0f4c879dc631d8b574739d2d9f209523332a6e26bf099
```

The v1 corpus was generated before production edits exclusively from Git blobs at
`489885d51e0d84e60c3506fd1ae2b365440b2401` with the exact contract §15.2 generator.
The body of that fenced generator was executed unchanged. Generation used its original first line:

```bash
PYTHONDONTWRITEBYTECODE=1 python -I -B - <<'PY'
```

Comparison uses the same body and only the contract-prescribed argument on its first line:

```bash
PYTHONDONTWRITEBYTECODE=1 python -I -B - tests/milestone_runner_state_v1_corpus.json <<'PY'
```

Reference interpreter: CPython 3.13.5, Pydantic 2.11.7. The provenance test locates this exact
reference runtime independently of the project test interpreter and does not substitute current
production models. G-15 output:

```text
PASS: 21155 bytes; SHA-256 c1a1c044526528e04251f5c9fcadbbe246e0fbb5874e2e11420172abbd17b41c
```

## Historical/superseded — OPEN OWNER decisions

OD-GSE-04, OD-GSE-05, OD-GSE-08, OD-GSE-09, OD-GSE-10 and OD-GSE-11 remain OPEN and unencoded.
The accepted decisions and D-AUTO017-01=B are implemented only within this contract's scope.


## Historical/superseded — Master Plan acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| 1: deterministic resolution | PASS | All 576 combinations and three literal digest vectors. |
| 2: remediation-cycle range and exact types | PASS | 1, 2, 3 accepted; 0, 4, strings, floats and booleans refused. |
| 3: immutable published policy | PASS | Byte tampering, invalid schemas, missing files and symlinked authority fail with the required typed reason. |
| 4: v1 migration | PASS | Exact baseline generator comparison and all 19 corpus records load read-only and publish schema 2. |
| 5: missing native authority | PASS | Registry-authorized + absent native authority uses STAGE_START_AUTHORIZATION_CONFLICT; otherwise STAGE_START_NOT_AUTHORIZED. |
| 5a: registry disagreement / absent registry | PASS | Strict v2 parser, contract binding and every mutating entry guard; native-only authorization accepted when no governed registry is configured. |
| 5b: severity and blocker policy | PASS | Fixed CRITICAL/HIGH and MEDIUM/LOW sets; exact integer blockers 1..3; v2 legacy review_policy rejected. |
| 6: authorization construction authority | PASS | AST construction-site proof and positive counterexample detection. |
| Restart/idempotency | PASS | Identical replay and orphan reuse preserve bytes and timestamp; conflicts never overwrite. |
| Tier-1 policy artifact | PASS | End-to-end disposable repository reaches READY_FOR_COMMIT_APPROVAL with exact state/policy/authorization/binding agreement. |
| Complete AUTO-017 acceptance | BLOCKED | The full-suite G-1 gate is not green in this sandbox. Independent review and OWNER lifecycle closure remain separate acts. |

Tier-1 observed policy SHA-256: `a545db437edeef656a7629d208955ddabd1c8199f4b4e716c934bf7ec6216b65`.
The run record contains the same digest and workflow state `READY_FOR_COMMIT_APPROVAL`.
The disposable artifact was `/tmp/pytest-of-afshin-jian/pytest-106/test_confirmed_policy_governs_0/home/.ai-workflow-engine/milestone-runs/demo-repo--2059e82cffa9/auto016-20260929T120000Z-ad239f43/policy.json`.

Process/environment evidence combines the unchanged provider-spawn capability assertions,
explicit test-double admission and invocation-boundary spies, Tier-1 process logs with zero
provider processes, and a bounded PATH containing no real `claude` or `codex` executable.
The non-live run never opts into the `live_cli` marker. The live-marker gate's real-provider
cases are skipped for unavailable CLI binaries; mocked harness cases retain their own labels.
No `strace` result is claimed: the sandbox refused the diagnostic PTRACE operation.


## Historical/superseded — Independent exclusion comparison

The comparison read each working-tree file and the exact `git show HEAD:<path>` blob and
required raw-byte equality, independently of Git diff output. All 12 required files match.

| Path | SHA-256 of both copies |
|---|---|
| `src/ai_workflow_engine/milestone_runner/approval_git.py` | `6a5f61c6939bffd67d6fe03cd66edafc0fb015058635d43013f221f0cc6ecd59` |
| `src/ai_workflow_engine/milestone_runner/lock.py` | `cef2c3dfb924c1647a19b4acd876b45a0393ddbbdb02770aeededdd9f18a112b` |
| `src/ai_workflow_engine/milestone_runner/providers/__init__.py` | `27edb2358ebb1d6842eb3da7f0c2c6ab37d209a2642f5ec66342522d3f4795a0` |
| `src/ai_workflow_engine/milestone_runner/providers/base.py` | `4ebe4f39f48fdc8cfd6ddff79573243a48ae980135047c55c0ce751e046638e6` |
| `src/ai_workflow_engine/milestone_runner/providers/claude_cli.py` | `ff226ecb592c518077eda54db3ab9b31b32249a6eb89fc8bf7e0a5f87b40395d` |
| `src/ai_workflow_engine/milestone_runner/providers/codex_cli.py` | `bd64791106af480e0947db57e04f869f310d7e5c9dec6722f84af5a5dfa8abd8` |
| `src/ai_workflow_engine/milestone_runner/recovery.py` | `5afb170155ddc36074630c6e1a3c4702f88e431d042c9a6363437926a53712a0` |
| `src/ai_workflow_engine/milestone_runner/review.py` | `21805cdbc40e9a8e0adafd5af1c6091c0c78195f918df86451d70c65667e4cb7` |
| `src/ai_workflow_engine/schema/__init__.py` | `b9c1271dc3711f49b7143230b84fc864e91efcd7cf08af55eb6f3f3cda1d0a9d` |
| `src/ai_workflow_engine/schema/contract.py` | `11ddee44eb74f5adc93ed1e58fadd0063bf756917414d702c03f55fead63f4d5` |
| `src/ai_workflow_engine/schema/migration.py` | `2e571c0d43bf773a23b296c4e606805c949fd93b39f153f11ee67a7022674be1` |
| `src/ai_workflow_engine/schema/registry.py` | `1f0046e784bf37c7621417ba3db2bb4740b186a0dcf71c6714cf843001b174b7` |

The working-tree audit uses both `git diff --name-only` and
`git ls-files --others --exclude-standard`; the unstaged and new candidate files are included.
Unauthorized changed paths: **none**. The commit-range checks alone are empty because HEAD was
not moved, so they are not used as a substitute for this working-tree/byte audit.


## Historical/superseded — Validation environment and exact commands

The project environment provides CPython 3.11.15, Pydantic 2.13.4 and the declared wheel-build
backend. The independently reproduced v1 corpus uses the contract's separate reference
interpreter, CPython 3.13.5 / Pydantic 2.11.7. No dependency or repository configuration was edited.

For the default and targeted test runs:

```bash
export PATH=/home/afshin-jian/miniconda3/envs/ai-workflow-engine/bin:/home/afshin-jian/miniconda3/bin:/usr/bin:/bin
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:src pytest -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:src pytest -q tests/test_milestone_runner_*.py tests/test_cli.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:src python -m pytest tests --collect-only -q
```

For the live-marker gate, PATH was restricted to
`/home/afshin-jian/miniconda3/envs/ai-workflow-engine/bin:/usr/bin:/bin`:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:src pytest -q -m live_cli -rs
```

`shutil.which("claude")` and `shutil.which("codex")` both returned `None` under the test PATH.

| Run | Exact result |
|---|---|
| Corrected complete milestone-runner + CLI selection | `4967 passed, 2 deselected in 888.15s (0:14:48)`; exit 0 |
| Security suite after correction | `127 passed in 23.85s`; exit 0 |
| Live-marker gate | `14 passed, 20 skipped, 9573 deselected in 3.10s`; exit 0 |
| `tests/` collection | `6743/6745 tests collected (2 deselected) in 2.47s`; exit 0 |
| Entire configured-suite collection | `9573/9607 tests collected (34 deselected) in 3.10s`; exit 0 |
| Entire configured-suite execution | Observed 9532 passing and 6 failing cases; 35 cases unfinished (including the hanging case). The run stalled at the unchanged dashboard static-file test and was interrupted (exit 130). These are observed progress counts, not a completed pytest summary. |

The original targeted run found one newly added purity-test mismatch: its allowed-import list
omitted the deterministic `datetime.strptime` parser already used for timestamp validation.
The test now permits only that parser and explicitly rejects aliased clock reads (`now`,
`utcnow`, `today`); a positive/negative regression was added. The complete corrected targeted
selection above includes that correction and all later supplemental cases. No existing test was
weakened, removed or skipped to obtain its pass.

G-10 node-ID comparison: baseline 3192 selected cases + 3551 new cases = 6743 selected cases;
zero baseline node IDs removed. The two existing live cases remain deselected by repository
configuration in both baseline and final collection.

## Historical/superseded — Machine-verifiable gates

Static commands were run with the project environment first on PATH:

```bash
ruff check .
black --check .
mypy
mypy --strict
pre-commit run --all-files
git diff --check
git diff --name-only main...HEAD
git diff main...HEAD -- src/ai_workflow_engine/milestone_runner/review.py src/ai_workflow_engine/milestone_runner/approval_git.py src/ai_workflow_engine/milestone_runner/recovery.py src/ai_workflow_engine/milestone_runner/lock.py src/ai_workflow_engine/milestone_runner/providers/
```

Black used `BLACK_NUM_WORKERS=1 BLACK_CACHE_DIR=/tmp/auto017-black-cache`; pre-commit additionally
used `PRE_COMMIT_HOME=/tmp/auto017-pre-commit PYTHONDONTWRITEBYTECODE=1`. The temporary pre-commit
cache reused existing installed hook environments. Black's complete-tree check covers the new
untracked Python files, which pre-commit does not select. Its final run followed the individual
file checks used to avoid the sandbox's worker-wakeup problem. No hook changed an unauthorized file.

| Gate | Result | Exact output / evidence |
|---|---|---|
| G-1 | BLOCKED | Full-suite failures and hang described below; no exit-0 result is claimed. |
| G-2 | PASS | `14 passed, 20 skipped, 9573 deselected in 3.10s` |
| G-3 | PASS | `All checks passed!` |
| G-4 | PASS | `All done!` / `368 files would be left unchanged.` |
| G-5 | PASS | Bare `mypy` and `mypy --strict`: `Success: no issues found in 193 source files` |
| G-6 | PASS | `ruff check...Passed`, `black...Passed`, `mypy...Passed` |
| G-7 | PASS | `git diff --check`: empty output, exit 0 |
| G-8 | PASS | Commit-range diff empty; working-tree plus untracked audit contains only the 18 listed authorized paths, including D1 and the OWNER-expanded provider test. |
| G-9 | PASS | All four governance commands below pass. |
| G-10 | PASS | 3192 + 3551 = 6743 selected cases; zero removed. |
| G-11 | PASS | Commit-range exclusion diff empty, supplemented by direct raw-byte comparisons with HEAD for all 12 required excluded files. |
| G-12 | PASS | Master Plan and contract identities match their required line counts, bytes and SHA-256. |
| G-13 | PASS | Three fixed vectors, exact corpus identity and Tier-1 policy digest recorded above. |
| G-14 | PASS | Explicit admission/refusal and process spies pass; no live provider executable on the bounded test PATH; no live provider invoked. |
| G-15 | PASS | Exact pinned-baseline comparison: `PASS: 21155 bytes; SHA-256 c1a1c044526528e04251f5c9fcadbbe246e0fbb5874e2e11420172abbd17b41c`; migration and provenance tests pass. |

Governance commands (with the same project interpreter and read-only runtime environment):

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:src workflowctl check-task-state --config self-governance.yaml
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:src workflowctl check-governance --config self-governance.yaml
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:src workflowctl check-handover --source commit --commit HEAD --config self-governance.yaml
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:src workflowctl verify --config self-governance.yaml
```

Exact individual outputs:

```text
PASS task-state: Detected 1 Current, 61 Done, and 9 Planned tasks
PASS governance: Governance mirrors are consistent
PASS handover: Verified 1 manifest record(s) from commit
```

`verify` reports all five checks PASS: Git invariants; 1 Current / 61 Done / 9 Planned tasks;
consistent governance mirrors; 36 stages across two registries; one working-tree handover record.
Its final line is `Verdict: PASS`.

## Historical/superseded — Bounded blockers outside the AUTO-017 diff

The following existing tests fail independently of the candidate:

1. `tests/test_engine_provenance.py::test_worktree_root_is_none_outside_any_repository`:
   the sandbox exposes a read-only `/tmp/.git`, so the unchanged directory detector returns
   `/tmp` instead of `None`. Isolated result: `1 failed in 0.49s`.
2. `tests/test_migration_readers.py::test_unix_socket_is_quarantined_without_connection_or_read`:
   the sandbox refuses AF_UNIX `bind` with `PermissionError: [Errno 1] Operation not permitted`.
   Isolated result: `1 failed in 0.13s`.
3. `agentos_dashboard/tests/test_dunder_main.py::test_lock_already_held_is_refused_with_a_clean_error`
   and `test_port_already_in_use_is_refused_with_a_clean_error_and_releases_the_lock`:
   AF_INET socket construction is refused with the same permission error.
4. `agentos_dashboard/tests/test_parsing_task_queue.py::test_real_remaining_tasks_historical_headings_do_not_degrade_confidence`
   and `agentos_dashboard/tests/test_services_consistency.py::test_real_repository_current_task_has_no_false_parser_finding`:
   the unchanged dashboard parser reports LOW confidence for the HEAD version of
   `docs/remaining_tasks.md`: `6 table row(s) skipped: no recognizable Status cell`.

The four dashboard failures were reproduced together: `4 failed in 0.39s`. Direct parsing of
`git show HEAD:docs/remaining_tasks.md` reproduces the same six-row finding. These are baseline
dashboard/document issues, while the governed `workflowctl verify` gate remains PASS.

The full run also hangs at
`agentos_dashboard/tests/test_web_overview.py::test_static_stylesheet_is_served_from_this_app`.
This isolated diagnostic reproduces it without any AUTO-017 call:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:src timeout --signal=INT --kill-after=5s 30s pytest -q agentos_dashboard/tests/test_web_overview.py::test_static_stylesheet_is_served_from_this_app -o faulthandler_timeout=10
```

At ten seconds, faulthandler shows the main thread waiting in the asyncio selector and the AnyIO
worker waiting on its queue. The bounded diagnostic required SIGKILL after the interrupt grace
period (exit 137). A separate repository-independent `asyncio.to_thread` probe also timed out
(exit 124), showing that the thread-wakeup problem is reproducible without project imports.

The affected tests, dashboard parser/services/client, provenance implementation and governance
input documents were independently compared with `git show HEAD:<path>` and are byte-identical.
No additional AUTO-017 implementation path has been identified as necessary. These failures
must be resolved in the baseline/environment before G-1 can become PASS. They were not skipped,
patched, or suppressed by the candidate. Sandbox escalation was not attempted.

## Historical/superseded — Git state and verdict

Final `git status --short`:

```text
 M src/ai_workflow_engine/cli.py
 M src/ai_workflow_engine/milestone_runner/application.py
 M src/ai_workflow_engine/milestone_runner/config.py
 M src/ai_workflow_engine/milestone_runner/models.py
 M src/ai_workflow_engine/milestone_runner/plan.py
 M src/ai_workflow_engine/milestone_runner/prompts.py
 M src/ai_workflow_engine/milestone_runner/state.py
 M tests/test_cli.py
 M tests/test_milestone_runner_acceptance.py
 M tests/test_milestone_runner_application.py
 M tests/test_milestone_runner_plan.py
 M tests/test_milestone_runner_providers.py
 M tests/test_milestone_runner_security.py
 M tests/test_milestone_runner_state.py
?? docs/reports/workflow-automation/AUTO-017-completion-report.md
?? src/ai_workflow_engine/milestone_runner/policy.py
?? tests/milestone_runner_state_v1_corpus.json
?? tests/test_milestone_runner_policy.py
```

`git diff --cached --name-only` returns no output. Branch is `main` and `git rev-parse HEAD` is
`8d14e4394874078289653ea26483c54e968d6df2`. No files were staged and no commit or other Git-history
operation was performed.

`AUTO_017_IMPLEMENTATION_BLOCKED`

The authorized implementation and targeted validation are present, but the contract's complete
acceptance gate is not green. This report does not assert Stage completion, independent-review
closure, OWNER lifecycle approval, or readiness under the requested all-gates-passing verdict.


## Historical/superseded — Exact isolated corpus commands

These blocks use `/home/afshin-jian/miniconda3/bin/python` as `python`
(CPython 3.13.5 / Pydantic 2.11.7), independently of the project test environment above.
Set `PATH=/home/afshin-jian/miniconda3/bin:/usr/bin:/bin` before executing them.

Generation (performed before production edits; stdout captured as T2):

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

Comparison (rerun against the checked-in corpus):

```bash
PYTHONDONTWRITEBYTECODE=1 python -I -B - tests/milestone_runner_state_v1_corpus.json <<'PY'
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
