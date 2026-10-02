# AUTO-018 implementation candidate report

**Status: `AUTO_018_IMPLEMENTATION_OWNER_ACCEPTED` — ready for bounded commit.** Independent
closure verification completed after remediation cycle 2 with verdict
`AUTO_018_IMPLEMENTATION_CLOSURE_PASS`; all frozen findings AUTO018-IMPL-R01 through
AUTO018-IMPL-R12 are `CLOSED`. The OWNER accepts exactly the implementation candidate that
received that verdict.

The closure verdict and OWNER acceptance are recorded from the authority supplied for this
bounded recording action. The current status is recorded under "OWNER implementation acceptance"
below. Earlier `OPEN`, `REMEDIATED_PENDING_CLOSURE` and G-9 "not started" entries are retained as
historical records of their respective remediation or verification sessions.

This cycle applies OWNER decisions **OD-AUTO018-03 = A** (the AUTO-018-only G-1 exception, which
replaces the identical-diagnostic requirement of the earlier OD-AUTO018-02 framing) and
**OD-AUTO018-04 = A** (the corpus pre-implementation timing deviation). The cycle performed no new
discovery and created no finding ID. The frozen contract, AUTO-017 contract, Master Plan, governance
documents and `agentos_dashboard` are byte-unchanged.

G-1 is satisfied only under OD-AUTO018-03: the fresh full configured run has exactly the two
authorized `BASELINE_PREEXISTING` dashboard failures and no other non-passing test. The exact
numbers are under "Remediation cycle 1 — gates" below. G-4 uses STAGE_REGISTRY §3 rule 16's
named `upstream_missing` tolerance. G-9's independent implementation closure and OWNER
implementation acceptance are now recorded below; stage close/freeze remains unauthorized.

Nothing is staged, committed, pushed or merged. AUTO-019 remains untouched and unauthorized.

## Identity and authority

| Item | Value |
|---|---|
| Stage | AUTO-018 / AWE-AUTO-ST-02 — Durable Lifecycle / Event Foundation |
| Repository | `/home/afshin-jian/ai-workflow-engine` |
| Branch | `feature/auto-018-durable-lifecycle-events` |
| Committed baseline HEAD | `147b122eaa5cfd3d4470a2b7fe1740faf76bee21` (index empty; candidate unstaged) |
| Planning baseline (contract §1) | `acd517ef4ea852f7f4dcab610f8c34e93a9c3ce4` |
| Frozen contract | `docs/workflow-automation/stage-prompts/AUTO-018.md` — 1008 lines, 76360 bytes, SHA-256 `75033788e08a6c3e6b9f7f79a48d1b33043018ed646857f059bf9916b3593751` (unchanged) |
| AUTO-017 contract | SHA-256 `50760879b2f64c395c8c3c5ee83c3bdac1a8b8456588b144c068f01d1080b1e8` (unchanged) |
| Master Plan | SHA-256 `8ab499c0240cc542e735eb5d1953dcd93994ebd87f1ef7413e9346805d613077` (unchanged) |
| stage_start_id | `b37134d87461f665a5d725964fb1ee192a047d4aad868830d53a565bbcc304ba` |
| stage_start_key | `69d34b4470efa01442e8972e88c900fd6307a31860a0761af91a6ddbae6da924` |
| effective_policy_digest | `afb747606f97409b9d04dcbd3f9b4ba47fe162251c7a53b8d1fc40842fb191a1` |
| authorization_digest | `43e573c10e0603d83e0a252157ea882327f68c3a03a4d379cc7b8fd42996bdf7` |
| OWNER authorization | `AUTO_018_IMPLEMENTATION_AUTHORIZED` |
| Implementer | Claude (Anthropic), implementing directly under the recorded development authority; `workflowctl milestone-runner start` was not run and the live-provider gate stays closed |

The Stage Start authorization, its binding and witness were neither recreated, replaced, consumed
nor mutated by this session.

## OWNER implementation acceptance (2026-10-02)

- **Independent closure verdict:** `AUTO_018_IMPLEMENTATION_CLOSURE_PASS`.
- **Closure sequence:** independent closure verification completed after remediation cycle 2.
- **OWNER acceptance marker:** `AUTO_018_IMPLEMENTATION_OWNER_ACCEPTED`.
- **Accepted scope:** exactly the implementation candidate that received
  `AUTO_018_IMPLEMENTATION_CLOSURE_PASS`, on branch
  `feature/auto-018-durable-lifecycle-events` at committed baseline
  `147b122eaa5cfd3d4470a2b7fe1740faf76bee21`, with the candidate unstaged and the index empty.
- **Readiness:** the implementation candidate is ready for bounded commit. This recording action
  does not stage or commit it.

The independent closure dispositions are:

| Frozen finding | Closure status |
|---|---|
| AUTO018-IMPL-R01 | CLOSED |
| AUTO018-IMPL-R02 | CLOSED |
| AUTO018-IMPL-R03 | CLOSED |
| AUTO018-IMPL-R04 | CLOSED |
| AUTO018-IMPL-R05 | CLOSED |
| AUTO018-IMPL-R06 | CLOSED |
| AUTO018-IMPL-R07 | CLOSED |
| AUTO018-IMPL-R08 | CLOSED |
| AUTO018-IMPL-R09 | CLOSED |
| AUTO018-IMPL-R10 | CLOSED |
| AUTO018-IMPL-R11 | CLOSED |
| AUTO018-IMPL-R12 | CLOSED |

All OWNER dispositions remain unchanged: **OD-AUTO018-01 = A**, **OD-AUTO018-02 = A**,
**OD-AUTO018-03 = A** and **OD-AUTO018-04 = A**. In particular, the existing AUTO-018-only G-1
exception under OD-AUTO018-03 and corpus timing deviation under OD-AUTO018-04 retain their
recorded scope and conditions.

This acceptance authorizes no AUTO-019 or successor-stage work, contract amendment, additional
implementation, push, merge, or stage close/freeze. AUTO-019 remains unauthorized. Only this
completion report is changed by the acceptance recording action; production code, tests, corpus,
governance/task/registry documents, contracts and Stage Start artifacts remain unchanged by it.
Nothing is staged, committed, pushed or merged.

## Changed paths (all within §11)

Production (§11 production allowlist):

- `src/ai_workflow_engine/milestone_runner/events.py` (new) — closed event vocabulary and payloads,
  integrity serialization, mutation declarations and incomplete-prefix evidence, pure fold,
  publication witness model, `EventStore` coordination. No filesystem primitive.
- `src/ai_workflow_engine/milestone_runner/operations.py` (new) — deterministic operation
  identity, closed phase-ladder artifacts, the derived `OperationRecord` view, `OperationJournal`
  coordination. No filesystem primitive, no workflow decision.
- `src/ai_workflow_engine/milestone_runner/models.py` — the eight §9 `StopReason` members; the
  explicit wire-v3 tip model and v3 document split/join. Legacy schemas, validators, transitions and
  digests unchanged.
- `src/ai_workflow_engine/milestone_runner/state.py` — descriptor-bound durable publication with
  typed `NOT_PUBLISHED`/`DURABLE`/`UNCERTAIN` outcomes; durability confirmation; the single bounded
  event enumeration; witness, verified load, projection repair, reference classification; the
  historical snapshot bridge. `_reconcile` and `resume` are AST-identical to the baseline.
- `src/ai_workflow_engine/milestone_runner/application.py` — the application lifecycle writer:
  every effect noted by the existing flow becomes typed events; any publication of two or more
  events is first durably declared; journal/startup evidence; ownership checks at publication and
  effect boundaries; incomplete/uncertain/error reporting. `_resume_from` is AST-identical to the
  baseline.
- `src/ai_workflow_engine/milestone_runner/providers/base.py` — the narrow observer seam
  (`before_spawn`, `at_spawn_entry`, `spawned`, `spawn_refused`), the ownership check at actual
  spawn entry, and child cleanup on receipt failure. Argv, sandbox, environment, timeout and retry
  classification unchanged (node-pinned to the baseline).
- `src/ai_workflow_engine/milestone_runner/lock.py` — R02 only: descriptor-bound ownership context,
  verification and invalidation, `LockOwnershipLost`, `bind_repository_root`. Flock domain and
  metadata/release helpers unchanged (node-pinned to the baseline).

Tests and data (§11 test allowlist):

- `tests/test_milestone_runner_events.py` (new), `tests/test_milestone_runner_operations.py` (new)
- `tests/test_milestone_runner_state.py`, `tests/test_milestone_runner_application.py`,
  `tests/test_milestone_runner_providers.py`, `tests/test_milestone_runner_lock.py` (R02 only),
  `tests/test_milestone_runner_security.py`, `tests/test_milestone_runner_acceptance.py`
- `tests/milestone_runner_state_v2_corpus.json` (new)

OWNER-authorized scope expansion (OD-AUTO018-01 = A): `tests/test_milestone_runner_plan.py`.
Only the assertion of `test_the_only_directory_listing_reads_the_external_plan_root` changed. It
is still an exact-list equality, now `[("plan.py", "_external_plan_paths"),
("state.py", "_bounded_event_names")]`, so any further listing still fails. 7 insertions,
1 deletion; no other line of that file was touched.

Documentation: this report only. No governance, registry, task, contract, Master Plan, CLI,
recovery, review, policy, config, results, verification, approval_git, plan, prompts or adapter
file was touched. `git diff --stat` for tracked files after remediation cycle 1: 12 files changed,
6527 insertions, 178 deletions (it was 5803/159 before the cycle; the untracked new files are not
included in that count). Remediation cycle 1 changed only paths already in this list: `lock.py`,
`state.py`, `events.py`, `operations.py`, `application.py`, the state, events, operations,
application and acceptance test files, and this report.

### Contract-required amendments to existing tests

Each is an exact consequence of a frozen requirement, made only in allowlisted files, and keeps
a meaningful assertion in place:

| Test | Change | Authority |
|---|---|---|
| state: stop-reason vocabulary | adds exactly the eight §9 codes | §9 |
| state: future/unknown version probes | version 3 is now defined, so the "future" probes use 4 / `"3"` / `3.0`; a new test proves v3 without its chain is `EVENT_CHAIN_BROKEN` | §10.1 |
| state: boundary signature | adds `target` and `refuse_redaction`; neither skips redaction (asserted) | §7.3/§7.4 |
| providers, application, security, acceptance: module counts | +`events.py`, +`operations.py` | §11 |
| security: enumeration sites | admits exactly `state.py::_bounded_event_names` | §7.3 |
| security: `state_version`/`last_event_id` exclusion | moved out of the AUTO-017 exclusion list and bounded to models/events/state/operations | §10.1 |
| security: whole-file pins of `lock.py`, `providers/base.py` | replaced by 53 node pins computed from `acd517e` plus a check that only the permitted nodes changed | §11 |
| application: one scripted fake that returned a completed row naming unpublished transcripts | now publishes its transcripts through the store | §8.3 |
| application: AUTO-017 crash point "after B-2" | retargeted from the state publication governed starts no longer perform to the genesis publication | §10.2 |
| application: a spy on `publish_exclusively` | forwards the new keyword | harness only |
| state: `TestAuto017CorpusProvenance::test_first_mutating_publication_writes_supervised_v2` (remediation cycle 1) | the corpus store now lives below its own lock's storage root; before, it published through a lock rooted at a *different* storage root with an equal identity, which is exactly what R01 must refuse. Still asserts supervised wire v2 with null policy pins | §7.4, R01 |
| state: two crash-before-rename stubs of `os.replace` (remediation cycle 1) | accept the descriptor-relative keywords the bound writers now pass; the injected crash is unchanged | harness only |

## OWNER decisions

### OD-AUTO018-01 — resolved: `OD-AUTO018-01: A`

- **Conflict.** §7.3 mandates `state.py`'s single bounded `events/` listing.
  `tests/test_milestone_runner_plan.py::TestNoPlanDiscoveryInWorktree::test_the_only_directory_listing_reads_the_external_plan_root`
  (outside the §11 test allowlist) asserted that plan.py's listing was the only one.
- **Ruling.** The OWNER authorized exactly one bounded scope expansion: update only that assertion
  to permit plan.py's external plan-root listing and `state.py::_bounded_event_names`, without
  weakening the test generally or permitting arbitrary enumeration. Applied as described under
  Changed paths.
- **Verification.**
  - `PATH="$E:$PATH" $E/python -m pytest -q tests/test_milestone_runner_plan.py::TestNoPlanDiscoveryInWorktree::test_the_only_directory_listing_reads_the_external_plan_root`:
    1 passed.
  - Whole `tests/test_milestone_runner_plan.py`: 156 passed.

### OD-AUTO018-02 — resolved: `OD-AUTO018-02: A`

- **Authority.** On 2026-10-01 the OWNER authorized `OD-AUTO018-02 = A`, an AUTO-018-only G-1
  exception for exactly the following two node IDs from the immediately preceding final full-suite
  run, each independently reproduced with the same failure behavior on clean copies of both
  `147b122eaa5cfd3d4470a2b7fe1740faf76bee21` and
  `acd517ef4ea852f7f4dcab610f8c34e93a9c3ce4`:
  1. `agentos_dashboard/tests/test_parsing_task_queue.py::test_real_remaining_tasks_historical_headings_do_not_degrade_confidence`
     — the parser reads the repository's real `docs/remaining_tasks.md` at LOW confidence
     ("6 table row(s) skipped: no recognizable Status cell");
  2. `agentos_dashboard/tests/test_services_consistency.py::test_real_repository_current_task_has_no_false_parser_finding`
     — the consistency checker reports the same degraded `docs/remaining_tasks.md` parse on the
     candidate and `147b122`; `acd517e` also has an earlier `docs/current_task.md` parser finding
     that stops this test before its remaining-tasks assertion. The common remaining-tasks
     finding is independently confirmed on all three trees (details under G-1).

- **Classification.** Both remain `BASELINE_PREEXISTING`. No other failure is covered, and this
  authority does not transfer to another stage.
- **Conditions.** These must be the only remaining non-passing configured full-suite tests;
  both must remain independently reproduced on the two clean baselines above; there must be no
  `CANDIDATE_CAUSED`, `INDETERMINATE` or unattributed failure; every other AUTO-018 §12 / §13
  candidate gate must pass. G-9 review and OWNER closeout remain subsequent, separately authorized
  activities; the OWNER explicitly prohibits beginning review in this session.
- **Boundary.** No test may be skipped, xfailed, weakened, deleted or modified under this ruling.
  No dashboard or governance-document fix, production scope expansion, or frozen-contract change
  is authorized. Only this completion report is updated. No staging, commit, push or merge.
- **Verification.** Final rerun and fresh baseline reproduction evidence are recorded under G-1
  below after execution, with the project conda environment first on `PATH`.

### OD-AUTO018-03 — resolved: `OD-AUTO018-03: A` (remediation cycle 1)

- **Scope.** For AUTO-018 only, the G-1 exception covers exactly these two node IDs and nothing
  else:
  1. `agentos_dashboard/tests/test_parsing_task_queue.py::test_real_remaining_tasks_historical_headings_do_not_degrade_confidence`
  2. `agentos_dashboard/tests/test_services_consistency.py::test_real_repository_current_task_has_no_false_parser_finding`
- **Condition.** Each must independently remain `BASELINE_PREEXISTING` on both clean baselines,
  `147b122eaa5cfd3d4470a2b7fe1740faf76bee21` and `acd517ef4ea852f7f4dcab610f8c34e93a9c3ce4`.
- **What changed.** OD-AUTO018-03 explicitly removes the earlier requirement that the diagnostic
  text or location be identical between the two baselines. The diagnostics do in fact differ for
  the second node ID (recorded below), and that is permitted.
- **Boundary.** No other failing test is covered. No dashboard, test or governance-document
  modification is made under this exception. No test is skipped, xfailed, weakened or
  reclassified. A `CANDIDATE_CAUSED`, `INDETERMINATE` or unattributed failure would block G-1.
- **Evidence.** Fresh reproduction and the fresh full run are under "Remediation cycle 1 — gates".

### OD-AUTO018-04 — resolved: `OD-AUTO018-04: A` (remediation cycle 1)

For AUTO-018 only, the OWNER accepted the missed pre-implementation timing requirement for
`tests/milestone_runner_state_v2_corpus.json`. Its isolated baseline provenance, import isolation,
deterministic derivation and byte identity must still hold, and do (see the v2 compatibility corpus
section). No pre-edit capture is claimed, and the corpus was not regenerated or altered to change
its history.

## Implementation summary

- **Event chain (§5).** Closed 16-type vocabulary, strict discriminated payloads. `event_id` and
  `payload_digest` use timestamp-inclusive integrity bytes (`authority_json_bytes` after a strict
  type check: no floats, non-string keys or surrogates). Each event chains to the previous event's
  full-file SHA-256, files are named `events/NNNNNNNN-TYPE.json`, `state_version == sequence`, and
  exhaustion refuses.
- **Fold (§6).** Pure and deterministic. It re-validates the closed transition table, pins, old
  values, append-only lists, the single-row provider completion rule, counters (each through its
  one route), ledger prefixes, operation dependencies and before/after body digests at every step.
- **Transition authority (INV-018-01).** Only `application.py` calls `EventStore.append_transition`.
  A private capability token blocks generic transition appends, and `_resume_from` is unchanged.
- **Declarations (§6.1, R01).** Any publication of two or more events, and every recovery command
  and result acceptance or rejection, is first published as a complete `APPLICATION_MUTATION_DECLARED`
  manifest. The manifest carries the original evidence, the exact constituent payloads, timestamps,
  sequences, intended transitions and the final body digest. Before anything is written, the
  declaration and every constituent are pre-folded on the verified state, so a manifest that could
  not complete legally is refused with no byte published. A proper prefix loads as
  `IncompleteApplicationMutation`; a later effecting command refuses with
  `APPLICATION_MUTATION_INCOMPLETE` and never completes, rolls back or reinterprets it.
- **Ownership (§7.4, R02).** Acquisition captures the canonical anchor, storage-root and lock-file
  identities, plus the repository root (the application always binds it), and retains no-follow
  descriptors. `verify_ownership` re-walks the paths and invalidates the hold on any mismatch.
  Every governed publication derives its descriptors from the retained root and re-verifies before
  mkdir, open, link/replace and barriers, and after visibility. The provider invoker re-verifies at
  spawn entry, and the application before verification, preflight and Git-gate effects.
- **Durability (§7.5, R03).**
  - Typed outcomes: a failure before canonical visibility is `StatePublicationFailure`
    (`NOT_PUBLISHED`); a failed barrier after link or replace is `PublicationUncertain`
    (`PUBLICATION_UNCERTAIN`); an identical existing artifact is reported durable only after its own
    barriers.
  - Every mutating command's locked open confirms the whole relied-upon set on the current
    descriptors (events, witness, projection and all referenced evidence), with exact file and
    ancestry fsyncs. The process-local cache lives only for the current hold and is keyed by inode
    and digest.
  - Confirmation rewrites nothing.
- **References (§8.3, R04).** A pending provider row's stdout/stderr are prospective declarations:
  grammar and containment are checked, and absence is valid. A completion carries digest-bound
  `TRANSCRIPT` references to the published prompt, stdout, stderr and any last message, and an
  empty output is a published empty file. Every asserted reference is verified on every load.
  Missing or altered evidence is `OPERATION_RECORD_INVALID` and is never downgraded.
- **Operations (§8).**
  - **Identity:** `sha256(run_id|provider|cycle|role|slot)`; the implementation slot is
    `<milestone>:<durable reopenings>`. `REQUEST_CREATED` comes before the first dispatch, and the
    request carries no clock reading, so a re-derived request is an exact duplicate.
  - **Attempt ladder:** `DISPATCH_INTENT` after the pending row and fingerprint and before spawn;
    `DISPATCH_RECEIVED` only from the post-`Popen` observer; `PRE_SPAWN_FAILED` only from a positive
    OS refusal, before the bounded retry. Then the raw result, the VALID/INVALID/EXECUTION_FAILED
    verdict, the declared acceptance or rejection with the causative transition, and finally
    `applied.json`.
  - **Receipt failure** after spawn kills the process group and never retries.
- **Storage (§7).**
  - Per-event exclusive links; an atomic, mandatory witness; atomic projections.
  - One bounded `os.listdir` of the explicitly addressed `events/` directory; no-follow bounded
    reads; duplicate keys, noncanonical bytes and unknown versions refuse.
  - Unlocked readers report retryable `LOCK_CONTENTION` while a writer holds the lock. Read-only
    loads never write; locked opens repair the projection and rebuild missing applied receipts
    without any execution.
- **Compatibility (§10).**
  - Supervised v1/v2 behaviour is unchanged.
  - New governed starts write `RUN_INITIALIZED` → `STAGE_START_BOUND` → `POLICY_PUBLISHED` →
    IDLE-to-PREFLIGHT.
  - Historical governed v2 state is read with no write. It is bridged lazily, at the first new
    state of a mutating command, into `RUN_BASELINED` (exact source digest) plus the bootstrap
    evidence. The bridge is idempotent because the snapshot's own timestamp is reused.
  - `policy.json` and the authorization, pointer, binding and witness stay primary and are never
    healed from events.

## §12 obligations — evidence map

All of the following pass (project env `~/miniconda3/envs/ai-workflow-engine`, CPython 3.11.15,
pydantic 2.13.4).

| ID | Evidence (test classes) |
|---|---|
| T-EVENT-SCHEMA | events: `TestEventSchema` (field/type/version/enum boundaries, duplicate keys, noncanonical/invalid UTF-8, timestamp tamper, filename mismatch, independent digest vectors) |
| T-EVENT-CHAIN | events: `TestEventChain` (delete first/middle/last/all and the events dir, reorder, rename, edit, duplicate sequence under another type, unknown entry, subdirectory, foreign run/policy/contract/stage-start, broken link, witness mismatch/missing/regressed) |
| T-EVENT-IDEMPOTENT | events: `TestEventIdempotence`; operations: `test_a_repeated_identical_request_is_a_confirmed_duplicate` |
| T-EVENT-FOLD | events: `TestFold` |
| T-EVENT-PROJECTION | events: `TestProjection`; state: `test_a_hostile_projection_is_only_a_damaged_cache` |
| T-EVENT-ATOMIC | events: `TestAppendAtomicity` (write, file fsync, witness replace, event link, directory fsync, projection replace) |
| T-EVENT-TAIL | events: `TestEventTail`, `TestUnlockedReaders` |
| T-EVENT-LOCK | events: `TestAppendRequiresTheLock` |
| T-MUTATION-PREFIX (R01) | application: `TestAuto018MutationPrefix` — all four recovery commands at every boundary from before the declaration through the last constituent; declaration publication failure; projection lag; later invocation with a changed clock and repository; result acceptance |
| T-LOCK-IDENTITY (R02) | lock: `TestLockOwnershipIdentity`; application: `TestAuto018StaleHolder`, `TestAuto018ConfirmationOwnership`; providers: `test_spawn_entry_reverifies_continuing_lock_ownership` |
| T-PUBLICATION-UNCERTAIN (R03) | application: `TestAuto018PublicationUncertain` (policy.json authority artifact incl. identical-existing branch, request.json, projection, read-only reload); events: event directory fsync, later-hold confirmation with recorded fsync inodes; state: `TestAuto018WitnessDurability` |
| T-PROSPECTIVE-REFERENCE (R04) | application: `TestAuto018ProspectiveReferences`; events: `TestReferenceClassification` |
| T-OP-ID | operations: `TestOperationIdentity` |
| T-OP-ORDER | acceptance: `test_every_role_is_journaled_in_order_and_durably_before_spawn`; providers: `TestDispatchObserverSeam`; operations: `TestPhaseOrder` |
| T-OP-SPAWN | acceptance: `test_a_positive_os_refusal_retries_in_the_same_operation`; providers: refusal, nonzero/timeout and receipt-failure cleanup tests; operations: retry rules |
| T-OP-INVALID | acceptance: `test_failed_and_invalid_results_are_never_pre_spawn_or_accepted`; operations: `TestOnlyValidResultsAreAccepted` |
| T-OP-GAPS | acceptance: `test_a_stop_at_every_boundary_leaves_exactly_its_durable_prefix` (4 roles × 5 boundaries) |
| T-OP-APPLIED | operations: `TestAppliedReceipt`; acceptance: applied receipts checked for every causative transition |
| T-REDACTION | acceptance: `TestAuto018EndToEndRedaction`; state: `TestAuto018Redaction` |
| T-HOSTILE-IO | operations: `TestHostileOperationArtifacts`; state: `TestAuto018HostileLifecycleFiles`; events: chain/hostile tests |
| T-AUTHORITY | application: `TestAuto018AuthorityStaysPrimary` (policy/binding/witness × delete/tamper); existing AUTO-017 matrices re-run on event-backed runs |
| T-COMPAT | state: `TestAuto018V2CorpusProvenance`, `TestAuto018V2CorpusCompatibility`, existing v1 corpus tests; application: supervised-configuration mode mixing |
| T-BASELINE-BRIDGE | application: `TestAuto018BaselineBridge`; state: bridge per governed corpus document |
| T-LEDGERS | application: `TestAuto018Ledgers` |
| T-AUTHORITY-AST | security: `TestAuto018TransitionAuthorityAst` (alias, wrapper, `getattr`, dynamic-type and capability-keyword probes) plus the existing single-boundary tests |
| T-BOUNDARY-AST | security: `TestAuto018BoundaryAst` (`_resume_from`, `_reconcile`, `resume` pinned to baseline digests; no successor vocabulary; no legacy authority imports; enumeration confined) |
| T-TIER1 | acceptance: `TestAuto018EventBackedTier1` — ten scenarios plus recovery, resume/terminal/read-only/manual Git gate and contention, each compared fold-to-published after every projection publication |

### Remediation closure matrices (G-8)

- **R01.** For each recovery command, the original outcome is captured once and the artifact root
  is restored before each boundary. Before the declaration there is no constituent effect. At
  every proper prefix, the declaration, mutation ID, intended transitions, prior tip and final
  digest are identical to the original, and the applied-prefix index is exact. A later invocation
  with a changed clock and changed repository observations refuses, and the event bytes are
  unchanged. After the last constituent there is one ledger entry, one transition and
  exactly-once counters; a repeat is refused by the recovery coordinator.
- **R02.**
  - The same identity under a different root is refused, and the invalidation persists.
  - Replacing the lock file, the storage root, an ancestor (renamed or symlinked) or the target
    repository root each refuses. A simultaneous apparent holder on the replacement inode is
    exercised.
  - Replacement at the spawn boundary means zero provider processes; replacement before a
    publication publishes nothing; replacement after a link prevents acknowledgment and any later
    effect.
  - Replacement during confirmation refuses without success. Ordinary contention is unchanged,
    and the stale release leaves the replacement intact.
- **R03.**
  - Directory-fsync failure after link or replace is injected for an authority artifact
    (policy.json), operation evidence (request.json), an event, the witness and the projection.
    Every case is `PUBLICATION_UNCERTAIN` with zero dependent calls, including the
    identical-existing branch.
  - After the barrier recovers, a later holder confirms with the file and ancestor inodes recorded
    as fsynced, and bytes and mtimes are unchanged.
  - A failure before visibility is `NOT_PUBLISHED`. Read-only reload confers nothing, and an
    incomplete manifest stays incomplete.
- **R04.**
  - A pending row before spawn, with absent stdout/stderr, is valid. Deleting or corrupting each
    asserted artifact (prompt, stdout, stderr, raw result, validated verdict) refuses
    `OPERATION_RECORD_INVALID` on load and on an effecting command.
  - Empty outputs are published, digest-bound empty files.
  - A historical pending row bridges with no fabricated digest.
  - A manifest carrying both a durable completion reference and prospective pending paths keeps
    them distinct.

### Publication failure matrix and atomicity limits

| Failure point | Outcome |
|---|---|
| temp create/write/file fsync, or `link`/`replace` raising | `NOT_PUBLISHED` (`StatePublicationFailure`); canonical bytes unchanged |
| witness replaced, dir barrier fails | `PUBLICATION_UNCERTAIN`; the witness now names an unlinked event, so later loads stop with `EVENT_CHAIN_BROKEN` and no event is invented |
| event linked, dir barrier fails | `PUBLICATION_UNCERTAIN`; the event is visible; a later holder confirms it or refuses |
| event durable, projection replace fails | error with a committed event; the next locked open repairs the projection with zero execution |
| artifact durable, event never appended | orphan evidence, never deleted and never treated as acceptance |
| receipt write fails after spawn | child process group terminated; no retry |

There is no atomic transaction spanning an external process, several files and a transition. The
durable order exposes those gaps instead. Local POSIX durability only; no protection against
privileged coordinated rollback (§9).

### Deferred recovery limitations (AUTO-019)

ST-02 records evidence and refuses ambiguity. It does not recover. Resuming an event-backed run
whose operation has an unresolved dispatch, a received result without persistence, or an
incomplete declaration refuses with a typed storage error (`OPERATION_RECORD_CONFLICT` /
`APPLICATION_MUTATION_INCOMPLETE`). Re-review under the same identity after
`recover-failed-review`, and a re-closure after `revalidate-correction` once closure already ran,
are refused the same way. Choosing an action in those states is AUTO-019's job.

## v2 compatibility corpus

- Path: `tests/milestone_runner_state_v2_corpus.json`, 57153 bytes, SHA-256
  `8c8abcd787a43cd349e38524534eff433b527a2fa6225bbb96755f60d444d6fe`.
- Content: 18 baseline-published state wire v2 documents (9 supervised, 9 governed) across PREFLIGHT,
  PROVIDER_WAIT with a pending row, FOCUSED_VERIFYING, MILESTONE_COMPLETE, a reopened
  IMPLEMENTING, NEEDS_CORRECTION, HUMAN_INTERVENTION_REQUIRED with ledgers, READY_FOR_PUSH with a
  consumed approval, and ABORTED. Each document carries its exact byte count and SHA-256, and the
  real governed policy bytes are included.
- Provenance, embedded in the corpus:
  - Baseline `acd517ef4ea852f7f4dcab610f8c34e93a9c3ce4`, extracted with
    `git archive acd517e… src/ai_workflow_engine | tar -x -C <isolated dir>`.
  - Generator run as `python -I -B generator.py <isolated dir>/src`; generator SHA-256
    `cd6dc3cb9339b5842db645a563778dba6743ca81fc51b7d4095084c15b9e1a75`, source embedded.
  - The generator imports only the extracted baseline (it asserts this) and publishes through the
    baseline `RunStateStore.publish` under the baseline `RunLock`.
- Determinism: byte-identical output (SHA-256
  `be3a0c553369a3ba646dab722457cb2217abde03a88916f11d0f934b05880ac6`) twice under CPython
  3.11.15/pydantic 2.13.4 and once under CPython 3.13.5/pydantic 2.11.7.
- Re-derivation: the corpus test `test_the_embedded_generator_reproduces_the_corpus_from_the_isolated_baseline`
  re-runs the generator against a fresh `git archive` on every test run.
- Timing (AUTO018-IMPL-R11, disposed under **OD-AUTO018-04 = A**): §12 required the baseline v2
  corpus to be captured *before* implementation edits. That did not happen. The corpus was
  generated *after* implementation edits began, and this report does not claim pre-edit capture.
  The OWNER accepted only that timing deviation. The corpus is acceptable because its other
  properties are verified:
  - Isolated provenance: generated from a `git archive` extraction of baseline `acd517e` that the
    candidate cannot influence, with the generator importing only that extraction (asserted).
  - Import isolation: run as `python -I -B`, re-proven on every test run.
  - Deterministic reproduction and byte identity: the embedded generator reproduces it from a fresh
    extraction on every run. Its SHA-256 is still
    `8c8abcd787a43cd349e38524534eff433b527a2fa6225bbb96755f60d444d6fe` after this cycle.
  Remediation cycle 1 neither regenerated nor altered the corpus. Every other corpus requirement
  remains mandatory and is verified by `TestAuto018V2CorpusProvenance` and
  `TestAuto018V2CorpusCompatibility`.

## §13 gates (exact commands and results)

> The table and attribution below record the **pre-remediation** candidate run of 2026-10-01 and
> are retained as history. The fresh post-remediation gate results are under
> "Remediation cycle 1 — gates".

Environment: `E=~/miniconda3/envs/ai-workflow-engine/bin`. The base conda env lacks `hatchling`,
which made its wheel-build tests error; this was reproduced on the baseline clone too.

| Gate | Command | Result |
|---|---|---|
| G-1 | `PATH="$E:$PATH" $E/python -m pytest -q` with the evidence-only XML/basetemp options recorded below (final run, after OD-AUTO018-02 = A) | **2 failed, 10581 passed, 34 deselected, 15 warnings, exit 1** — exactly the two authorized `BASELINE_PREEXISTING` failures; G-1 satisfied under OD-AUTO018-02 = A only |
| G-2 | all §12 tests (map above, expanded in `section12-node-map.json`) | pass; all 27 obligation mappings and all 403 added AUTO-018 tests pass in the final full run |
| G-3 | `$E/ruff check .` | pass |
| G-3 | `$E/black --check .` | pass (372 files) |
| G-3 | `$E/mypy --strict` (configured files) | pass (195 files) |
| G-3 | `PATH="$E:$PATH" $E/pre-commit run --all-files` | pass; no hook mutations. Pre-commit sees only tracked files; the whole-tree ruff/black/mypy runs cover the untracked new files |
| G-3 | `git diff --check` | pass |
| G-4 | `workflowctl check-task-state --config self-governance.yaml` | PASS |
| G-4 | `workflowctl check-governance --config self-governance.yaml` | PASS |
| G-4 | `workflowctl check-handover --source commit --commit HEAD --config self-governance.yaml` | PASS |
| G-4 | `workflowctl verify --config self-governance.yaml` | task-state, governance, registries, handover PASS; `git` only `upstream_missing`, which STAGE_REGISTRY §3 rule 16 tolerates (pre-existing, documented, unrelated to the diff; the same tolerance the SSP applies mid-stage) |
| G-5 | `$E/python -m pytest --collect-only -q`, `tests --collect-only -q`, and `--collect-only -q -m ''`, on both clean baselines and candidate | 10182 → 10583 selected; +403 AUTO-018 tests; −2 = the previously replaced whole-file pins of lock.py and providers/base.py; all 34 existing live-test deselections unchanged; full baseline run under identical settings recorded below |
| G-6 | changed-path audit vs §11; frozen hashes | all paths within §11; contract, AUTO-017 and Master Plan hashes unchanged; transition table, ceilings, policy resolution and Git authority unchanged (AST pins pass) |
| G-7 | Tier-1 event-backed runs | verified chains; every projection publication audited for fold equals published bytes; zero mismatches |
| G-8 | this report | recorded |
| G-9 | independent implementation review; OWNER acceptance and closeout | not started; outside this session |

### G-1 attribution (independently reproduced)

**Preceding final run, after OD-AUTO018-01:** 2 failed, 10581 passed (both listed under OD-AUTO018-02).

**OD-AUTO018-02 verification, 2026-10-01:** performed by Codex. Raw evidence is retained outside
the worktree at `/tmp/auto018-od02-final-5quqjhpv/`. The report is the only repository file
changed in this verification session; production and test contents are checked against a
SHA-256/mode snapshot taken before the report edit.

Fresh baseline copies were created with `git clone --quiet --no-hardlinks --no-checkout
/home/afshin-jian/ai-workflow-engine <copy>` followed by `git checkout --quiet --detach <sha>`.
Both copies had an empty `git status --porcelain=v1 --untracked-files=all` before and after the
two-node pytest run. Imports were verified to resolve to each copy's own `src/ai_workflow_engine`
and `agentos_dashboard`, using `PYTHONPATH=<copy>/src:<copy>`, with the project environment first
on `PATH`. Neither copy contains the candidate diff.

| Baseline | Focused result | Evidence under the directory above |
|---|---|---|
| `147b122eaa5cfd3d4470a2b7fe1740faf76bee21` | exactly the two authorized IDs fail; exit 1 | `147b122-baseline.json`, `147b122-dashboard.log`, `147b122-dashboard.xml` |
| `acd517ef4ea852f7f4dcab610f8c34e93a9c3ce4` | exactly the two authorized IDs fail; exit 1 | `acd517e-baseline.json`, `acd517e-dashboard.log`, `acd517e-dashboard.xml` |

Each command was `$E/python -m pytest -q <first exact node ID above> <second exact node ID above>
--junitxml=<evidence>/<sha-prefix>-dashboard.xml`, in the respective clean copy. No test was edited
or bypassed.

Failure-behavior precision: the parsing test fails at line 462 with LOW rather than HIGH
confidence and `6 table row(s) skipped: no recognizable Status cell` on both baselines. The
consistency test stops at line 368 on `147b122`, on the `parse_degraded` finding for
`docs/remaining_tasks.md`. On `acd517e` it stops at line 367 on a `parse_failed` finding for
`docs/current_task.md`; its checker also returns the identical remaining-tasks `parse_degraded`
finding. A separate read-only call to the unmodified `run_consistency_checks` on each tree proves
that common finding, with identical rule, message and source, in
`dashboard-common-behavior.json`. Thus the shared failure behavior is reproduced on both clean
baselines; the earlier report's statement that the two tracebacks were identical was too broad.
Both exact test IDs remain `BASELINE_PREEXISTING`.

The new final command is `PATH="$E:$PATH" $E/python -m pytest -q
--junitxml=/tmp/auto018-od02-final-5quqjhpv/full-suite.xml
--basetemp=/tmp/auto018-od02-final-5quqjhpv/pytest`, with output in `full-suite.log`.
The XML and disposable-root options only retain verification evidence; the configured collection
and marker selection are unchanged. **Final result: 2 failed, 10581 passed, 34 deselected,
15 warnings in 1795.49 seconds; exit 1.** Both failures are exactly the authorized IDs above;
their messages and assertion locations match the clean `147b122` reproduction, and the shared
failure behavior is also present on clean `acd517e` as detailed above.

`full-suite-summary.json` and `full-suite-node-results.json` account for every one of the 10583
selected node IDs. The full run contains 7753 passing `tests/` cases, 2085 passing
`agentos_workflow/tests/` cases, and 743 passing plus exactly two failing
`agentos_dashboard/tests/` cases. There are no errors, skips, xfails or additional non-passing
tests. All 403 added AUTO-018 tests pass. The expanded `section12-node-map.json` maps all 27
§12 obligations to 335 distinct named test nodes and records PASS for each; the broader
regression and counting-fake/fault-injection coverage described above also executes in this run.

| Failure classification | Count | Disposition |
|---|---|---|
| `BASELINE_PREEXISTING` | 2 | exactly the two verbatim IDs under OD-AUTO018-02; independently reproduced on both clean baselines; bounded exception applies |
| `CANDIDATE_CAUSED` | 0 | none |
| `INDETERMINATE` | 0 | none |
| Unattributed | 0 | none |

Accordingly, all five OWNER conditions for the AUTO-018-only G-1 exception are satisfied. The
tests remain failing and retain their classification; this report does not relabel pytest as
passing or extend the exception to any other node ID or stage.

Earlier runs, for completeness:

- Before OD-AUTO018-01, the same command failed 4 tests:
  - the plan test, now resolved;
  - the two tests above;
  - `tests/test_engine_provenance.py::test_worktree_root_is_none_outside_any_repository`, which
    observed `PosixPath('/tmp')` as a repository root. It failed in every earlier run and on both
    clean clones, then passed in the final run, so it is environment-sensitive and does not depend
    on the candidate.
- A full run of the clean `acd517e` clone under identical settings (project env first on `PATH`):
  10177 passed, 5 failed. Those 5 were the two OD-AUTO018-02 tests,
  `test_engine_provenance`, `TestOutOfTreeImport::...fresh_environment...` and
  `test_real_current_task_mirror_parses...`; the last two pass on the candidate.
- A first candidate run with the base env's `bin` first on `PATH` also failed 17 workflow-closeout
  and report-discovery tests. Those tests spawn `workflowctl` from `PATH`, which resolved to the
  base env entry point, and that could not import `agentos_workflow` there. All 17 pass with the
  project env first on `PATH` and on both clean clones.

### G-4 attribution

This is accepted under STAGE_REGISTRY §3 rule 16. Rule 16 tolerates a `git` finding when it is
the only one, is pre-existing and documented, and is unrelated to the stage's own diff, naming
`upstream_missing` as its example. It applies "the same tolerance the SSP already applies
mid-stage", and rule 15 keeps push human-gated. AUTO-006, AUTO-008 and AUTO-009 recorded their
candidates the same way. The finding clears at the OWNER's push. Evidence:
`git rev-parse @{upstream}` fails for `feature/auto-018-durable-lifecycle-events`: the branch has
never been pushed, and pushing is excluded for this session. The `git` check's only finding is
`upstream_missing`; the dirty worktree is listed in its evidence but raises no violation.
`milestone_runner/verification.py` already tolerates exactly this code for unpushed branches.
Note: `self-governance.yaml` pins `project.repository` to the absolute repository path, so a
separate clone cannot isolate this check; no such comparison is claimed.

### Fresh G-3 through G-7 evidence (2026-10-01)

All raw files below are in `/tmp/auto018-od02-final-5quqjhpv/`.

- G-3: `ruff.log`, `black.log`, `mypy.log`, `pre-commit.log` and corresponding `.exit` files
  record exit 0. Black checked 372 files; strict mypy checked 195 source files. The post-hook
  workspace snapshot comparison found only this report changed since session entry; no hook
  mutation occurred.
- G-4: `check-task-state.log`, `check-governance.log` and `check-handover.log` record exit 0.
  `verify.json` (from `workflowctl verify --config self-governance.yaml --output json`, exit 1)
  records exactly one finding, `git/upstream_missing`; all four other checks PASS. The existing
  rule-16 attribution above remains applicable and is separate from OD-AUTO018-02.
- G-5: `collection-comparison.json` and the nine `*-collection-*.log` files preserve exact IDs.
  Both baselines have identical selected collections (10182); candidate selection is 10583.
  The `tests/` collections are 7352 → 7753. Collecting with `-m ''` executes no live tests and
  confirms the same 34 IDs are excluded by the unchanged default marker filter on all three
  trees. The only two replaced baseline collection entries remain the already-recorded
  `TestAuto017TransitionsAndBudgetsUnchanged::test_excluded_runtime_modules_are_byte_identical`
  parameters `[lock.py]` and `[providers/base.py]`; their replacement node-level checks are in
  the existing §12 map. This session makes no test or collection change.
  The SSP's separate `$E/python -m pytest -q agentos_workflow/tests` check, with evidence-only
  `--junitxml=/tmp/auto018-od02-final-5quqjhpv/workflow-subsuite.xml` and
  `--basetemp=/tmp/auto018-od02-final-5quqjhpv/workflow-pytest`, also passes independently:
  **2085 passed, 32 deselected, exit 0** (`workflow-subsuite.log`). The complete configured run
  additionally executes all 7753 selected `tests/` regression cases and all focused §12 cases.
- G-6: the 18 changed/untracked candidate paths remain within §11 plus the already-authorized
  OD-AUTO018-01 plan-test assertion. The three frozen authority SHA-256 values match the Identity
  table above. The candidate itself is unchanged by this report-only verification.
- G-7: `g7-tier1-chains.json` preserves each of the ten scenario node IDs, disposable run path,
  verified event count and tip, projection SHA-256, operation count and all artifact hashes.
  Read-only `RunStateStore.load_lifecycle()` with authority verification, followed by `fold` and
  `projection_bytes`, reverified all ten completed scenario runs from the final suite: 592 events,
  33 operations, 1710 artifact hashes, zero projection mismatches, no incomplete mutation.
  Artifact bytes and mtimes stayed unchanged during reload. Each scenario's test additionally
  checks fold/projection equality after every publication through `projection_audit`.
  The happy-path run has 74 events, tip
  `6768eb766addf50ea1e0e6ba8668f9cdea4e9f3e0f6f221f3e6a75c6496d214e`, projection SHA-256
  `39944f3c70d7b56253d3dffc733d73286b41053656206cf1785310e4a73f436a`, and four operations.

## Isolation evidence

- The OD-AUTO018-02 final verification compares `authority-before.json` with
  `authority-after.json`: all 486 entries under the real `~/.ai-workflow-engine` have identical
  paths, sizes, mtimes, inodes and file hashes. Stage Start authority remains untouched.
- `find ~/.ai-workflow-engine -printf '%P %s %T@ %i'` produced the same listing before and after
  each of the three full-suite runs: the real artifact root (which holds the AUTO-018 Stage Start) was never
  touched.
- An earlier session's test briefly undid its fixture's `HOME` redirection and attempted one read
  of the real root. Nothing was created there. All such tests now use scoped
  `monkeypatch.context()` and no test calls `monkeypatch.undo()`.

## Successor exclusions confirmed

The following are absent:

- AUTO-019: no phase-driven resume, `RecoveryReconciler`, stored-result adoption or revalidation,
  `ESCALATE_TO_OWNER`, PendingDecision or AMBIGUOUS_RECOVERY. The resume policy is AST-identical to
  the baseline.
- AUTO-020: no cycle behaviour.
- AUTO-021: no OWNER-decision API.
- AUTO-022: no provider catalog or model provenance, and no executable use of `roles`.
- AUTO-023: no Hermes or execution port.
- AUTO-024 / AUTO-025: no authentication or Telegram.
- AUTO-026: no Git operation ladder or new mutating argv.

The live-provider gate remains closed. Completion selects, solicits and starts no other stage.

## Remediation cycle 1 (2026-10-02)

**Inputs and boundary.**
- Frozen finding set: exactly AUTO018-IMPL-R01..R12. R01–R08 are High / blocking; R09–R12 are
  Medium / non-blocking.
- OWNER decisions: OD-AUTO018-03 = A and OD-AUTO018-04 = A.
- No discovery was performed and no finding ID was created.
- The reviewer's full write-up was not available on disk. The closure condition the remediation
  prompt states for each finding was treated as that finding's authoritative text.

**Entry checks.**
- Branch: `feature/auto-018-durable-lifecycle-events`.
- HEAD: `147b122eaa5cfd3d4470a2b7fe1740faf76bee21`.
- Index: empty.
- `git diff --check`: passed.
- Contract SHA-256: `75033788…3751`.
- Corpus SHA-256: `8c8abcd7…d6fe`.
- The dirty worktree was the expected candidate.

**Authorized paths.**
- Every path changed in this cycle is in §11: production `lock.py`, `state.py`, `events.py`,
  `operations.py` and `application.py`; the test files for state, events, operations, application
  and acceptance; and this report.
- No `agentos_dashboard`, governance, contract, Master Plan, `verification.py`, `approval_git.py`
  or provider-dispatch file was touched.

Every test named below passed in the focused runs and again in the fresh full run.

### AUTO018-IMPL-R01 — REMEDIATED_PENDING_CLOSURE

- **Remediation.** Every shared governed writer now verifies the hold's continuing ownership and
  publishes through descriptors derived from it. A held flag plus an equal identity string is no
  longer enough.
  - `RunStateStore._require_lock` adds `RunLock.verify_ownership` for the store's canonical storage
    root and its target repository root.
  - The following writers publish through a descriptor-bound `DurableTarget` (via the new
    `_held_target`): the legacy `state.json` publication, `plan.json`, `provider-intent.json`, the
    transcript-sequence counter (`next_transcript_sequence(..., target=)`) and every transcript.
    Ownership is therefore re-verified before the write and again after the replace.
  - `record_latest_run(..., lock=)` publishes the latest-run pointer the same way, and the
    application's call site passes the session lock.
  - Stage Start artifacts, `policy.json`, events, the witness, the projection and operation evidence
    were already descriptor-bound.
- **Supervised behaviour.** Writers whose directories exist by construction use
  `create_parents=False`, so a missing directory is still a refusal and is never recreated. The
  unlocked form of `record_latest_run` remains only for existing test fixtures (it is outside the
  allowlist in `tests/test_cli.py`). No application command calls it without a lock.
- **Files.** `state.py`, `application.py`, `tests/test_milestone_runner_state.py`.
- **Tests.** `tests/test_milestone_runner_state.py::TestAuto018R01SharedWritersBindTheHold`:
  - `test_the_owning_hold_publishes_normally[state|plan|intent|transcript_sequence|transcript|latest_run]`
  - `test_a_lock_at_another_root_with_the_same_identity_refuses[…6]`
  - `test_a_released_hold_refuses[…6]`
  - `test_a_replaced_lock_or_root_refuses_before_writing[lock_file|storage_root × …6]` (12)
  - `test_a_loss_detected_after_the_replace_prevents_success[state|plan|intent|transcript_sequence|latest_run]`
  - `test_the_transcript_writer_detects_a_loss_after_its_link`
  - `test_the_latest_run_pointer_is_written_through_the_hold`

  That is 37 passing nodes. Each refusal case asserts byte- and mtime-identical trees, in both the
  old and the replacement tree. Supervised regression is covered by the unchanged supervised suites.
- **Status:** REMEDIATED_PENDING_CLOSURE.

### AUTO018-IMPL-R02 — REMEDIATED_PENDING_CLOSURE

- **Remediation.**
  - New `RunLock.verify_descriptor_ancestry` re-walks every opened child directory, no-follow, from
    the retained root descriptor. It compares each child's `(st_dev, st_ino)` with the held
    descriptor and invalidates the hold (`LockOwnershipLost`) on any rename, replacement or missing
    component.
  - `DurableTarget.guard(descriptors)` applies this check after each child is opened, before
    `mkdir`, before opening the temporary file, before and after `link`/`replace`, after the
    ancestry barriers, and in identical-existing and `confirm_durable` confirmation.
  - Success can therefore never be acknowledged into a detached directory. This covers the run,
    `events/`, `operations/<id>/`, `attempts/NNNN/` and `stage-starts/` ancestry.
- **Files.** `lock.py` (R02 ownership validation only; the security node pins still pass with
  `RunLock` as the permitted node), `state.py`, `tests/test_milestone_runner_events.py`.
- **Tests.** `tests/test_milestone_runner_events.py::TestAuto018R02NamespaceSwap`:
  - `test_a_swap_before_the_link_publishes_nothing_canonically`
  - `test_a_swap_after_the_event_link_prevents_acknowledgment`
  - `test_a_swap_after_a_replace_prevents_acknowledgment[event-publication.json|state.json]`
  - `test_a_swap_of_the_operation_ancestry_after_the_link_prevents_acknowledgment`
  - `test_a_swap_of_the_authority_ancestry_after_the_link_prevents_acknowledgment`
  - `test_a_swap_during_confirmation_reports_no_success`

  That is 7 nodes. Each is deterministic, injected through `os.fsync`/`os.link`/`os.replace` wrappers
  rather than timing. Each asserts `LOCK_OWNERSHIP_LOST`, an un-advanced store and an invalidated
  hold.
- **Status:** REMEDIATED_PENDING_CLOSURE.

### AUTO018-IMPL-R03 — REMEDIATED_PENDING_CLOSURE

- **Remediation.** Continuing ownership is now re-verified immediately before *each* effectful
  command entry:
  - **Verification.** `_OwnedVerificationExecutor` (an application-local `VerificationExecutor`)
    re-verifies ownership in `run()`. Focused, configured, final and each individual
    governance/preflight check all enter through that method.
  - **Git.** The approval facade is an `ApprovalGit` subclass defined inside `_approve`, so
    `ApprovalGit` is still referenced only from `_approve`. It re-verifies ownership in `_run()`
    before every gated vector.
  - **Unchanged.** `verification.py`, `approval_git.py`, argv, gates, timeouts and the
    run-every-command policy are byte-unchanged.
- **Files.** `application.py`, `tests/test_milestone_runner_application.py`.
- **Tests.** `tests/test_milestone_runner_application.py::TestAuto018R03PerCommandOwnership`:
  - `test_the_preflight_governance_batch_stops_after_the_command_that_lost_it`
  - `test_the_focused_set_stops_after_the_command_that_lost_it`
  - `test_the_configured_final_set_stops_after_the_command_that_lost_it`
  - `test_the_git_vectors_stop_after_the_vector_that_lost_it` (`add` ran, `commit` never did,
    and HEAD is unchanged)
  - `test_a_valid_hold_runs_every_command_of_the_set` (control)

  That is 5 nodes. In each failing case command N+1 is never invoked.
- **Status:** REMEDIATED_PENDING_CLOSURE.

### AUTO018-IMPL-R04 — REMEDIATED_PENDING_CLOSURE

- **Remediation.**
  - Every descriptor-bound publication now fsyncs the parent and every ancestor up to the storage
    root, then re-verifies the binding (`_fsync_ancestry`), before it reports `DURABLE`. This covers
    exclusive links, atomic replaces, the identical-existing branch and `confirm_durable`.
  - A directory left visible by a failed parent fsync is therefore never treated as established.
    Caching a confirmation, acknowledging reuse, emitting a dependent event and dependent execution
    all occur only after these barriers succeed.
  - Confirmation rewrites nothing.
- **Files.** `state.py`, `tests/test_milestone_runner_events.py`.
- **Tests.** `tests/test_milestone_runner_events.py::TestAuto018R04AncestryDurability`:
  - `test_a_retry_under_the_same_hold_refsyncs_the_whole_ancestry`
  - `test_a_retry_under_a_later_hold_refsyncs_the_whole_ancestry`
  - `test_a_still_failing_ancestor_barrier_never_reports_durable` (both the created and the
    identical-existing branch give `PUBLICATION_UNCERTAIN`)
  - `test_a_dependent_event_is_not_emitted_while_the_ancestry_is_unconfirmed`

  That is 4 nodes. Fsynced inodes are recorded from the actual descriptors.
- **Status:** REMEDIATED_PENDING_CLOSURE.

### AUTO018-IMPL-R05 — REMEDIATED_PENDING_CLOSURE

- **Remediation.**
  - New pure `events.check_operation_artifact(state, reference, artifact)` cross-checks each
    referenced operation artifact against the fold's facts:
    - request ↔ step, role, milestone, adapter and request digest;
    - intent ↔ request digest, adapter and the attempt's intent digest;
    - receipt and pre-spawn verdict ↔ the attempt's intent;
    - validated result ↔ role, raw-result digest, the event's verdict and the operation's
      milestone.
  - `_verify_reference` now returns the strictly parsed artifact. Both the streaming verified load
    and append validation (`EventStore.publish_envelope` through `verify_references`) run the
    cross-check.
  - `_validate_declaration` additionally requires a result declaration's verdict reference to be
    the last attempt's exact artifact path and digest. That digest must equal the persistence
    payload's, and an acceptance needs a `VALID` verdict. This check runs before publication and on
    load.
  - A consistently rehashed but contradictory chain refuses `OPERATION_RECORD_INVALID`.
- **Files.** `events.py`, `state.py`, `tests/test_milestone_runner_operations.py`.
- **Tests.** `tests/test_milestone_runner_operations.py::TestAuto018R05ArtifactFactCrossCheck`:
  - `test_a_rehashed_contradictory_chain_fails_closed_on_verified_load`, with variants
    `validated-invalid-on-valid-event`, `validated-other-raw-result`, `validated-other-milestone`,
    `request-other-adapter`, `intent-other-request`, `intent-other-adapter` and
    `receipt-other-intent`. Each variant rewrites the artifact, repoints every digest, re-chains
    every later event and the witness.
  - `test_the_untampered_rehash_still_loads` (control)
  - `test_an_invalid_artifact_is_never_appended_under_a_valid_event_fact`
  - `test_an_acceptance_declared_on_a_foreign_verdict_reference_refuses[missing|other-digest|other-artifact]`

  That is 12 nodes.
- **Status:** REMEDIATED_PENDING_CLOSURE.

### AUTO018-IMPL-R06 — REMEDIATED_PENDING_CLOSURE

- **Remediation.** New `_validate_budget_effects`, run from `_validate_declaration` for every
  recovery declaration, so it applies both before declaration publication (the store pre-folds the
  declaration) and on every verified load. It enforces:
  - declared budget keys must be the five counters;
  - each counter is assigned by at most one constituent;
  - a non-zero delta must be applied;
  - an unbudgeted counter must not be assigned;
  - the net change across the complete manifest must equal the declared delta exactly.

  Repeated, omitted and altered deltas, and incompatible before/final values, refuse. The recovery
  coordinator (`recovery.py`) and AUTO-019 policy are untouched.
- **Files.** `events.py`, `tests/test_milestone_runner_events.py`.
- **Tests.** `tests/test_milestone_runner_events.py::TestAuto018R06AggregateBudgets`:
  - `test_the_declared_delta_applied_once_completes_exactly_once`
  - `test_a_wrong_aggregate_is_refused_before_the_declaration_is_published[repeated|omitted|altered|unbudgeted-counter]`
    (no event byte is published)
  - `test_a_published_repeated_delta_is_refused_on_verified_load`

  That is 6 nodes. The four recovery commands' exactly-once budget, ledger and transition behaviour
  is re-proven by the unchanged `TestAuto018Ledgers`, `TestAuto018MutationPrefix` and the recovery
  suites, all passing.
- **Status:** REMEDIATED_PENDING_CLOSURE.

### AUTO018-IMPL-R07 — REMEDIATED_PENDING_CLOSURE

- **Remediation.** New `EventStore.confirm_established()`. Before any exact-duplicate
  acknowledgment, including a duplicate operation request, it:
  - re-checks that the on-disk names and witness bytes are exactly the verified ones;
  - validates the witness against the tip with its actual predecessor;
  - durability-confirms the witness, every event of the established prefix and every artifact they
    reference.

  Any failure refuses the duplicate. The process-local confirmation cache is keyed on
  `(dev, ino, size, mtime_ns, ctime_ns)`, so an in-place rewrite is never acknowledged from the
  cache. A valid duplicate still preserves bytes, mtimes and counters.
- **Files.** `events.py`, `state.py`, `tests/test_milestone_runner_events.py`.
- **Tests.** `tests/test_milestone_runner_events.py::TestAuto018R07DuplicateDependencies`:
  - `test_a_missing_witness_refuses_the_duplicate`
  - `test_a_corrupt_witness_refuses_the_duplicate`
  - `test_a_regressed_witness_refuses_the_duplicate`
  - `test_a_corrupted_predecessor_refuses_the_duplicate`
  - `test_an_unavailable_predecessor_refuses_the_duplicate`
  - `test_a_missing_referenced_dependency_refuses_the_duplicate`
  - `test_a_valid_duplicate_preserves_bytes_mtimes_and_counters`

  That is 7 nodes. The existing `TestEventIdempotence` also passes.
- **Status:** REMEDIATED_PENDING_CLOSURE.

### AUTO018-IMPL-R08 — REMEDIATED_PENDING_CLOSURE

- **Remediation.** Through OD-AUTO018-03 = A only. No dashboard test or governance document was
  edited.
- **Report.** This report now states:
  - both exact node IDs;
  - that each is independently `BASELINE_PREEXISTING` on both clean baselines;
  - that diagnostics may, and do, differ between baselines;
  - that OD-AUTO018-03 explicitly removes the earlier identical-diagnostic requirement;
  - that no other failing test is covered.
- **Evidence.** Fresh reproduction and the fresh full run are recorded below. No other non-passing
  test exists.
- **Files.** This report only.
- **Status:** REMEDIATED_PENDING_CLOSURE.

### AUTO018-IMPL-R09 — REMEDIATED_PENDING_CLOSURE

- **Remediation.**
  - `operations.redact_typed_result` redacts only the typed result's free-text fields (`title`,
    `summary`, `reason`, `resolution`, `blockers`, `command`). It then revalidates the result
    through its own closed model, so the typed structure is preserved, before the
    `ValidatedResult` is built and content-addressed. Verdict diagnostics are redacted the same way.
  - Identity-bearing fields (milestone and finding ids, statuses, severities, verdicts, changed
    paths) are never rewritten. A secret there is still refused by the mandatory final structural
    pass, and a redaction that would make the typed model invalid refuses
    `OPERATION_RECORD_INVALID`.
  - Counts propagate through `record_validation(on_redaction=…)` into
    `_Lifecycle.defer_redactions`. They become counted, visible `redaction-NNNN-…` deferred findings
    on the next committed record.
- **Files.** `operations.py`, `application.py`, `tests/test_milestone_runner_operations.py`,
  `tests/test_milestone_runner_acceptance.py`.
- **Tests.**
  - `tests/test_milestone_runner_operations.py::TestAuto018R09TypedResultRedaction`:
    - `test_every_role_accepts_a_result_with_secret_shaped_free_text[IMPLEMENTATION|REVIEW|CORRECTION|CLOSURE]`
    - `test_identity_fields_are_never_rewritten_and_a_secret_there_still_fails_closed`
  - `tests/test_milestone_runner_acceptance.py::TestAuto018R09TypedResultSecretsEndToEnd::test_all_four_roles_accept_redacted_free_text`.
    A real governed run with secret-shaped prose in all four roles reaches
    `READY_FOR_COMMIT_APPROVAL`. Every role's `VALID` artifact carries a redaction marker, at least
    four validated-result redactions are counted on the record, and no persisted byte under the
    artifact root contains the secret.

  That is 6 nodes.
- **Status:** REMEDIATED_PENDING_CLOSURE.

### AUTO018-IMPL-R10 — REMEDIATED_PENDING_CLOSURE

- **Remediation.**
  - `PublicationWitness` validates its predecessor: it is null exactly for sequence 1, and
    otherwise a 64-lowercase-hex digest.
  - The fold keeps the tip event's own `prev_event_digest`. `check_witness` requires the witness's
    predecessor to equal it.
  - Genesis semantics are unchanged.
  - The same validation applies in the duplicate path (R07).
- **Files.** `events.py`, `tests/test_milestone_runner_events.py`.
- **Tests.** `tests/test_milestone_runner_events.py::TestAuto018R10WitnessPredecessor`:
  - `test_a_bad_predecessor_on_an_established_chain_refuses[null-for-non-genesis|malformed|uppercase|wrong-digest]`
  - `test_a_contradictory_predecessor_refuses`
  - `test_a_missing_predecessor_field_refuses`
  - `test_the_genesis_witness_names_no_predecessor`

  That is 7 nodes.
- **Status:** REMEDIATED_PENDING_CLOSURE.

### AUTO018-IMPL-R11 — REMEDIATED_PENDING_CLOSURE

- **Remediation.** Through OD-AUTO018-04 = A only (see the v2 compatibility corpus section).
  - The report states that generation occurred after implementation edits began.
  - Provenance is isolated from the archived baseline `acd517e`.
  - Deterministic reproduction and byte identity are verified.
  - The OWNER accepted only the timing requirement; every other corpus requirement remains
    mandatory.
  - No pre-edit capture is claimed. The corpus is byte-unchanged (SHA-256 `8c8abcd7…d6fe`).
- **Evidence.** `TestAuto018V2CorpusProvenance` (including the regeneration from a fresh
  `git archive`) and `TestAuto018V2CorpusCompatibility` pass in the fresh full run.
- **Files.** This report only.
- **Status:** REMEDIATED_PENDING_CLOSURE.

### AUTO018-IMPL-R12 — REMEDIATED_PENDING_CLOSURE

- **Remediation.** The verified load now streams the chain (`RunStateStore._stream_verified`).
  - **Per event, in sequence order:** the size is checked on the descriptor before any read; the
    bytes are read, parsed and hash-verified; the event is folded and its pins checked; its
    referenced artifacts are verified and cross-checked (R05); then the body is dropped. The first
    invalid event stops the load before any later file is opened.
  - **Retained.** Only bounded per-event `ChainEntry` metadata (sequence, type, ids, digest and
    references) and the fold state. `LifecycleView.chain` and `EventStore.entries` hold no event
    bodies.
  - **Diagnostics.** `LifecycleView.events` and `EventStore.events` remain diagnostic accessors that
    re-read the bodies, digest-checked against the verified chain. No load, fold, append or
    confirmation path uses them.
  - **Unchanged.** Fold, projection, replay and read-only behaviour are unchanged: all earlier
    events, state, application and acceptance tests, including the T-TIER1 fold-to-bytes audits,
    pass unmodified.
- **Files.** `state.py`, `events.py`, `operations.py` (applied receipts accept a `ChainEntry`),
  `application.py` (one genesis timestamp read now uses `view.chain`),
  `tests/test_milestone_runner_events.py`.
- **Tests.** `tests/test_milestone_runner_events.py::TestAuto018R12StreamingChain`:
  - `test_each_event_is_parsed_then_folded_before_the_next_is_read` (exact
    read → parse → fold interleaving)
  - `test_an_invalid_prefix_stops_before_any_later_event_is_read`
  - `test_the_verified_view_retains_no_event_bodies` (the `gc` count of live `LifecycleEvent`
    objects is unchanged across a load)
  - `test_an_oversize_event_is_refused_before_it_is_read` (the oversize inode is never `os.read`)

  That is 4 nodes.
- **Status:** REMEDIATED_PENDING_CLOSURE.

### Remediation cycle 1 — gates

Environment: `E=~/miniconda3/envs/ai-workflow-engine/bin`, first on `PATH`. Raw evidence is in
`/tmp/claude-1000/-home-afshin-jian-ai-workflow-engine/df29af2a-28c3-43f0-a446-0b9488d57a25/scratchpad/g1/`.

| Gate | Command | Result |
|---|---|---|
| G-1 | `PATH="$E:$PATH" $E/python -m pytest -q --junitxml=<g1>/full-suite.xml --basetemp=<g1>/pytest` (configured selection unchanged; options retain evidence only) | **2 failed, 10676 passed, 34 deselected, 23 warnings in 1980.04 s; exit 1.** The two failures are exactly the OD-AUTO018-03 node IDs, so G-1 is satisfied under OD-AUTO018-03 = A only. JUnit accounting: 10676 passed, 2 failures, 0 errors, 0 skips, 0 xfails. |
| G-2 | every §12 obligation plus the 95 remediation nodes | pass: every §12 obligation node and all 95 remediation-cycle nodes pass in the fresh full run |
| G-3 | `$E/ruff check .` | pass |
| G-3 | `$E/black --check .` | pass (372 files unchanged) |
| G-3 | `$E/mypy --strict` | pass (195 source files) |
| G-3 | `PATH="$E:$PATH" $E/pre-commit run --all-files` | pass (ruff, black, mypy); `git status --short` identical before and after, so no hook mutation |
| G-3 | `git diff --check` | pass |
| G-4 | `workflowctl check-task-state --config self-governance.yaml` | exit 0 |
| G-4 | `workflowctl check-governance --config self-governance.yaml` | exit 0 |
| G-4 | `workflowctl check-handover --source commit --commit HEAD --config self-governance.yaml` | exit 0 |
| G-4 | `workflowctl verify --config self-governance.yaml --output json` | exit 1. `task-state`, `governance`, `registries` and `handover` PASS. `git` FAIL with exactly one finding, `upstream_missing`: the branch has never been pushed. This is the sole verify issue and is reported, not concealed, under the existing STAGE_REGISTRY §3 rule 16 tolerance (see G-4 attribution). |
| G-5 | `$E/python -m pytest --collect-only -q` | 10678 selected / 34 deselected (10712 collected). Against the pre-cycle candidate collection (10583): 95 added, 0 removed or renamed; all 95 are this cycle's `TestAuto018R*` nodes. The 34 live-test deselections are unchanged. |
| G-6 | changed-path audit and frozen hashes | all paths within §11 plus the OD-AUTO018-01 plan-test line. AUTO-018 contract `75033788…3751`, AUTO-017 `50760879…b1e8` and Master Plan `8ab499c0…3077` are unchanged; corpus `8c8abcd7…d6fe` is unchanged. Transition table, ceilings, policy resolution and Git authority are unchanged (security AST pins pass). |
| G-7 | T-TIER1 event-backed runs | `TestAuto018EventBackedTier1` passes in the fresh run, with fold-to-published byte equality after every projection publication |
| G-8 | this report | updated with all twelve remediation closure entries |
| G-9 | independent closure verification; OWNER closeout | not started; outside this session |

#### OD-AUTO018-03 fresh baseline evidence (2026-10-02)

- **Copies.** Fresh clean copies of each baseline were made with `git clone --quiet --no-hardlinks
  --no-checkout <repo> <copy>` followed by `git checkout --quiet --detach <sha>`.
- **Clean before and after.** `git status --porcelain=v1 --untracked-files=all` was empty in each
  copy before and after the run.
- **Imports.** Each copy imported its own `src/ai_workflow_engine` and `agentos_dashboard`
  (`PYTHONPATH=<copy>/src:<copy>`; module paths verified).
- **Command.** Run in each copy: `$E/python -m pytest -q -p no:cacheprovider <node 1> <node 2>
  --junitxml=<g1>/<sha7>-dashboard.xml`.

| Baseline | Result | Diagnostic |
|---|---|---|
| `147b122…` | exactly both node IDs fail, exit 1 | node 1: `test_parsing_task_queue.py:462`, `docs/remaining_tasks.md` at LOW confidence ("6 table row(s) skipped: no recognizable Status cell"). Node 2: `test_services_consistency.py:368`, `parse_degraded` for `docs/remaining_tasks.md` |
| `acd517e…` | exactly both node IDs fail, exit 1 | node 1: same location and LOW-confidence assertion. Node 2: `test_services_consistency.py:367`, `parse_failed` for `docs/current_task.md` (a different diagnostic, permitted by OD-AUTO018-03) |

Each node ID fails independently on each clean baseline, so both remain `BASELINE_PREEXISTING`.
On the candidate's fresh full run, the two failures have the same locations and messages as the
clean `147b122` reproduction (`test_parsing_task_queue.py:462`; `test_services_consistency.py:368`,
`parse_degraded` for `docs/remaining_tasks.md`).

| Failure classification | Count | Disposition |
|---|---|---|
| `BASELINE_PREEXISTING` | 2 | exactly the two OD-AUTO018-03 node IDs |
| `CANDIDATE_CAUSED` | 0 | none |
| `INDETERMINATE` | 0 | none |
| Unattributed | 0 | none |

No other test is non-passing. Neither test was edited, skipped, xfailed or reclassified as passing,
and pytest's exit status remains 1.

#### Isolation

`find ~/.ai-workflow-engine -printf '%P %s %T@ %i'` produced an identical listing (486 entries)
before and after the fresh full run. The real artifact root holding the AUTO-018 Stage Start
authority was not touched, and `workflowctl milestone-runner start` was not run.

## Remediation cycle 2 (2026-10-02)

**Inputs and boundary.**
- Cycle-1 closure verdicts: R01, R03, R04, R05, R06, R08, R09, R10, R11 and R12 are `CLOSED`.
  R02 and R07 are `OPEN`.
- This cycle remediated only R02 and R07. No discovery was performed, no finding ID was created,
  and no `CLOSED` finding was reworked.
- Effective policy digest `afb74760…91a1`. The CORRECTION role is `claude` / `claude-opus-5`,
  `WORKSPACE_WRITE`.

**Entry checks.**
- Branch: `feature/auto-018-durable-lifecycle-events`.
- HEAD: `147b122eaa5cfd3d4470a2b7fe1740faf76bee21`.
- Index: empty.
- `git diff --check`: passed.
- Contract SHA-256: `75033788…3751`.
- Corpus SHA-256: `8c8abcd7…d6fe`.
- The dirty worktree was the expected cycle-1 candidate.

**Paths changed in this cycle.** All are already in §11 and in the candidate:
- `src/ai_workflow_engine/milestone_runner/state.py`
- `src/ai_workflow_engine/milestone_runner/lock.py`
- `tests/test_milestone_runner_operations.py`
- this report

No path was added. `events.py`, `operations.py`, `application.py`, `models.py`, the frozen
contract, AUTO-017, the Master Plan, governance documents, `agentos_dashboard` and the corpus are
byte-unchanged in this cycle.

**Root cause (shared by R02 and R07).** `RunLifecycleStorage._confirm` answered a cache hit by
calling `os.stat(<path>, follow_symlinks=False)` on the full pathname, then
`RunLock.verify_ownership`.
- `follow_symlinks=False` applies only to the last path component. A symlink at a parent's
  canonical name was therefore followed to the detached directory, and the leaf's cached
  `(dev, ino, size, mtime_ns, ctime_ns)` still matched.
- `verify_ownership` checks only the anchor, root, lock and repository roots.
- The cycle-1 probe (rename `stage-starts`, symlink the canonical name to the detached directory,
  retry an exact duplicate) was therefore acknowledged.

### AUTO018-IMPL-R02 — REMEDIATED_PENDING_CLOSURE

- **Remediation (`state.py`, `RunLifecycleStorage`).**
  - **Hold-scoped namespace bindings.** `_directories` maps every governed directory prefix below
    the storage root (`<run>`, `<run>/events`, `<run>/operations/<id>`,
    `<run>/operations/<id>/attempts/NNNN`, `stage-starts`, …) to the `(st_dev, st_ino)` at which
    this hold first reached it. It is reached through a no-follow walk from the hold's retained
    root descriptor.
  - **`_walk` / `_bind` / `_bind_directory`.**
    - Each component is opened `O_RDONLY | O_DIRECTORY | O_NOFOLLOW` relative to the previous
      descriptor, starting at `storage_root_descriptor`.
    - Each must equal its recorded identity; the first sighting records it.
    - The leaf is `fstatat`-ed by name with `follow_symlinks=False`. The walk ends with
      `DurableTarget.guard(descriptors)`, which is `verify_ownership` plus
      `verify_descriptor_ancestry`.
    - **Refusals.**
      - A bound directory that is now a symlink, missing, or another inode makes the hold
        invalidate itself through the new `RunLock.invalidate` (a thin public wrapper over
        `_lose`) and raises `LockOwnershipLost` (`LOCK_OWNERSHIP_LOST`).
      - A never-bound directory that is absent is `EvidenceUnavailable`.
      - `.`, `..` and empty components refuse.
    - A symlink is never followed, so a detached directory reachable through a new symlink at the
      original name is a namespace loss.
  - **`prime`.** When a hold opens an event-backed run, `prime` binds the run directory, `events/`
    and the parent directory of every referenced artifact (Stage Start authority, policy, operation
    and attempt evidence). A swap after the verified load is therefore refused, not adopted, even
    before the first confirmation.
  - **Reads.** `check_tip` and `read_chain` validate `<run>/events` before and after the read.
    `verify_references` validates each reference's parent directory before and after the read.
  - **Writes.** `_write` validates the already-bound prefix of the target's directories before
    `write_redacted_artifact`. A bound directory replaced by an empty directory now refuses
    before anything is written into it. Directories not yet bound are still created as before
    (R04's ancestry fsync is unchanged).
  - **Every confirmation path.** `_confirm` now always calls `_bind` first, whether or not a cache
    entry exists (see R07). `confirm_durable`, `_confirm_identical_existing` and the publication
    guards keep their cycle-1 descriptor-ancestry checks unchanged.
- **Tests.** `tests/test_milestone_runner_operations.py::TestAuto018Cycle2NamespaceBoundConfirmation`:
  - **Dependencies.** `DEPENDENCIES` is `authority` (`stage-starts`), `run-witness` (the run
    directory), `events-predecessor` (`events/`), `operation-request` (`operations/<id>`) and
    `attempt-artifact` (`operations/<id>/attempts/0001`).
  - **Mutations.** `MUTATIONS` is:
    - `symlink-to-detached` — rename the parent, symlink the canonical name to the detached
      original;
    - `other-directory-copy` — rename the parent, put a different directory with byte- and
      mtime-identical files at the canonical name;
    - `other-directory-empty`.
  - **Nodes.**
    - `test_a_change_before_confirmation_refuses_the_open[dependency × mutation]` (15). The
      mutation is injected after the verified load and `prime`, immediately before `confirm_all`.
      The open refuses with `LOCK_OWNERSHIP_LOST`, the hold is invalidated, and no file is repaired,
      rebuilt or added (bytes and mtimes unchanged).
    - `test_a_later_hold_refuses_a_change_after_it_bound_the_namespace[dependency × mutation]`
      (15). A fresh hold with an empty cache refuses a later exact duplicate.
    - `test_a_redirected_ancestor_refuses_a_fresh_hold_before_confirmation[dependency]` (5). A
      symlinked canonical name is refused even before anything was bound, and the tree is
      unchanged.
    - Item 4 (mutation while cached data exists) is covered by the R07 cached nodes below.
    - `test_a_later_hold_with_unchanged_ancestry_opens_and_acknowledges` (control).
  - Every refusal asserts `LockOwnershipLost` / `LOCK_OWNERSHIP_LOST` (except the pre-binding
    symlink case, which refuses with a typed lifecycle or state error), an un-advanced sequence, a
    byte-, mtime-, inode- and link-count-identical `namespace_snapshot` of the whole artifact root
    (symlinks not followed), and an invalidated hold.
- **R02 closure-evidence mapping.**
  1. Rename + symlink to the detached original: every `symlink-to-detached` node, and the probe
     node below.
  2. Rename + a different directory: the `other-directory-copy` and `other-directory-empty` nodes.
  3. Mutation before confirmation: `test_a_change_before_confirmation_refuses_the_open`.
  4. Mutation while cached data exists: the R07 cached nodes.
  5. Authority / Stage Start: the `authority` parameter.
  6. Run, events, operation and attempt: the remaining four parameters.
- **Status:** REMEDIATED_PENDING_CLOSURE.

### AUTO018-IMPL-R07 — REMEDIATED_PENDING_CLOSURE

- **Remediation (`state.py`).**
  - A cache entry is now `_NamespaceBinding = (directory identities, leaf cache identity)`.
    `_remember` records it from the same no-follow walk.
  - `_confirm` first proves the current canonical namespace with `_bind`. It reuses a cached
    confirmation only if the entry equals the freshly walked binding exactly: every directory the
    entry depends on, and the file. Otherwise it runs the full `confirm_durable` (strict digest,
    fsync of the file and the whole ancestry, inode recheck) and re-records.
  - A changed parent binding never reaches the cache comparison: `_bind` refuses it as a
    namespace loss.
  - `EventStore.confirm_established` (unchanged) therefore confirms the complete dependency set
    under the current canonical namespace before any exact-duplicate acknowledgment: the witness,
    every predecessor event, every referenced immutable artifact (Stage Start authority, policy,
    operation and attempt evidence), and `check_tip`'s chain and witness bytes.
  - Validation was not disabled, and the cache was not broadly invalidated. A valid duplicate still
    rewrites nothing.
- **Tests.** `tests/test_milestone_runner_operations.py::TestAuto018Cycle2NamespaceBoundConfirmation`:
  - `test_the_cycle_1_closure_probe_now_fails_closed`. The exact cycle-1 probe: a valid duplicate
    populates the cache, `stage-starts` is renamed and its name replaced by a symlink to the
    detached directory, and the duplicate is retried. It refuses `LOCK_OWNERSHIP_LOST`.
  - `test_unchanged_ancestry_acknowledges_duplicates_without_mutation`. Every event is retried
    twice (the second pass is cache-answered), plus a duplicate operation request. All are
    acknowledged, and bytes, mtimes, inodes, link counts, the record, the sequence and the hold are
    unchanged.
  - `test_a_cached_duplicate_event_refuses_a_changed_ancestry[dependency × mutation]` (15). A prior
    successful duplicate confirmation populates the cache, then the ancestry is mutated.
  - `test_a_cached_duplicate_request_refuses_a_changed_ancestry[dependency × mutation]` (15). The
    same, through the duplicate operation-request path (`record_operation_request`).
- **R07 closure-evidence mapping.**
  1. Valid duplicate with unchanged ancestry: the unchanged-ancestry node.
  2. Authority parent replaced by a symlink: `authority-symlink-to-detached`, and the probe node.
  3. Authority parent replaced by another directory: `authority-other-directory-{copy,empty}`.
  4. Predecessor ancestry: `events-predecessor-*`.
  5. Witness ancestry: `run-witness-*`.
  6. Referenced-artifact ancestry: `authority-*`, `operation-request-*` and `attempt-artifact-*`.
  7. After a prior successful confirmation populated the cache: every `cached_duplicate` node.
     The empty-cache variant is the later-hold nodes.
- The cycle-1 `TestAuto018R07DuplicateDependencies` (7) and `TestEventIdempotence` still pass.
- **Status:** REMEDIATED_PENDING_CLOSURE.

### Remediation cycle 2 — focused and regression evidence

Environment: `E=~/miniconda3/envs/ai-workflow-engine/bin`, first on `PATH`.

| Run | Nodes | Result |
|---|---|---|
| R02/R07 closure: `TestAuto018Cycle2NamespaceBoundConfirmation` | 68 | 68 passed |
| Same, with cycle-1 `TestAuto018R02NamespaceSwap`, `TestAuto018R07DuplicateDependencies` and `TestEventIdempotence` | 86 | 86 passed |
| `CLOSED`-finding regression: R01 `TestAuto018R01SharedWritersBindTheHold`, R03 `TestAuto018R03PerCommandOwnership`, R04 `TestAuto018R04AncestryDurability`, R05 `TestAuto018R05ArtifactFactCrossCheck`, R06 `TestAuto018R06AggregateBudgets`, R09 `TestAuto018R09TypedResultRedaction` + `TestAuto018R09TypedResultSecretsEndToEnd`, R10 `TestAuto018R10WitnessPredecessor`, R11 `TestAuto018V2CorpusProvenance` + `TestAuto018V2CorpusCompatibility`, R12 `TestAuto018R12StreamingChain` | 130 | 130 passed |
| All 16 `tests/test_milestone_runner_*.py` files | 5979 | 5979 passed, 2 deselected |

- **R08.** OD-AUTO018-03 G-1 handling is re-evidenced by the fresh full run below: exactly the two
  authorized node IDs fail.
- **R11.** The corpus is byte-unchanged (`8c8abcd7…d6fe`), and its provenance and compatibility
  classes pass.
- **R01, R03, R04, R05, R06, R09, R10, R12.** Their production paths were not edited this cycle,
  except where R02's binding is added in front of `RunLifecycleStorage` writes and reads. Those
  writes still go through the single `write_redacted_artifact` boundary (the security AST pin
  passes) and keep R04's ancestry barriers.

### Remediation cycle 2 — gates

Raw evidence: `/tmp/claude-1000/-home-afshin-jian-ai-workflow-engine/e2fd5920-222d-45c9-acc4-9fb354e4235a/scratchpad/g1/`.

| Gate | Command | Result |
|---|---|---|
| G-1 | `PATH="$E:$PATH" $E/python -m pytest -q --junitxml=<g1>/full-suite.xml --basetemp=<g1>/pytest` (configured selection unchanged) | **2 failed, 10744 passed, 34 deselected, 23 warnings in 2327.09 s; exit 1.** The two failures are exactly the OD-AUTO018-03 node IDs, `agentos_dashboard/tests/test_parsing_task_queue.py::test_real_remaining_tasks_historical_headings_do_not_degrade_confidence` (`:462`) and `agentos_dashboard/tests/test_services_consistency.py::test_real_repository_current_task_has_no_false_parser_finding` (`:368`, `parse_degraded` for `docs/remaining_tasks.md`). Their locations and messages are the same as in cycle 1. JUnit accounting: 10746 tests, 2 failures, 0 errors, 0 skips. G-1 is satisfied under OD-AUTO018-03 = A only. No other non-passing test. |
| G-2 | every §12 obligation plus all remediation nodes | pass in the fresh full run (95 cycle-1 nodes + 68 cycle-2 nodes) |
| G-3 | `$E/ruff check .` | pass |
| G-3 | `$E/black --check .` | pass (372 files unchanged) |
| G-3 | `$E/mypy --strict` | pass (195 source files) |
| G-3 | `PATH="$E:$PATH" $E/pre-commit run --all-files` | pass (ruff, black, mypy); `git status --short` identical before and after |
| G-3 | `git diff --check` | pass |
| G-4 | `workflowctl check-task-state --config self-governance.yaml` | exit 0 |
| G-4 | `workflowctl check-governance --config self-governance.yaml` | exit 0 |
| G-4 | `workflowctl check-handover --source commit --commit HEAD --config self-governance.yaml` | exit 0 |
| G-4 | `workflowctl verify --config self-governance.yaml --output json` | exit 1. `task-state`, `governance`, `registries` and `handover` PASS. `git` FAIL with exactly one finding, `upstream_missing` (never pushed), under the existing STAGE_REGISTRY §3 rule 16 tolerance, unchanged from cycle 1 |
| G-5 | `$E/python -m pytest --collect-only -q` | 10746 selected / 34 deselected (10780 collected). Against cycle 1 (10678): +68, all `TestAuto018Cycle2NamespaceBoundConfirmation`; 0 removed or renamed; the 34 live-test deselections are unchanged |
| G-6 | changed-path audit and frozen hashes | cycle-2 paths are within §11. Contract `75033788…3751`, AUTO-017 `50760879…b1e8`, Master Plan `8ab499c0…3077` and corpus `8c8abcd7…d6fe` are unchanged |
| G-7 | T-TIER1 event-backed runs | `TestAuto018EventBackedTier1` passes in the fresh run |
| G-8 | this report | updated with the cycle-2 R02 and R07 entries |
| G-9 | independent closure verification; OWNER closeout | not started; outside this session |

**Isolation.** `find ~/.ai-workflow-engine -printf '%P %s %T@ %i'` produced an identical listing
(486 entries) before and after the fresh full run. The Stage Start artifacts were not touched, and
`workflowctl milestone-runner start` was not run.

## Git state

Nothing staged, committed, pushed or merged. Index empty. HEAD remains
`147b122eaa5cfd3d4470a2b7fe1740faf76bee21`. The candidate is the unstaged modification of the 12
tracked files plus the six new files listed above (including this report). Neither remediation
cycle added a path.

Final verification after remediation cycle 2:
- `git diff --check` passes.
- `git diff --cached --name-only` is empty.
- No dashboard, governance, frozen contract or other authority file was modified.
- AUTO-019 was not touched and remains unauthorized.

**Historical remediation-cycle-2 verdict (before independent closure):** AUTO-018 remediation
cycle #2 has remediated AUTO018-IMPL-R02 and AUTO018-IMPL-R07,
both `REMEDIATED_PENDING_CLOSURE` and awaiting independent closure verification. The ten findings
the cycle-1 verifier closed keep their regression evidence. G-1 is satisfied only under
OD-AUTO018-03 = A, and all other candidate gates are satisfied.
