# AUTO-018 — Durable Lifecycle / Event Foundation

> **CONTRACT REMEDIATION CANDIDATE — NOT AUTHORIZED.** Revision 2, 2026-09-30.
> Alias: AWE-AUTO-ST-02. Preparation under Stage Registry §3 rule 3a changes no
> lifecycle status. AUTO-018 remains `NOT_STARTED` / `Planned`; implementation,
> Stage Start, branch creation, staging, commit and push are not authorized.
> The single contract discovery review is complete. This revision remediates only
> AUTO018-CONTRACT-R01, R02, R03 and R04. Independent closure of that frozen set
> and separate written OWNER implementation authorization remain outstanding.

## 1. Identity, authority and preparation boundary

| Item | Required identity |
|---|---|
| Repository | `/home/afshin-jian/ai-workflow-engine` |
| Planning baseline | `main` at `acd517ef4ea852f7f4dcab610f8c34e93a9c3ce4` |
| Baseline conditions | Clean worktree, empty index, `origin/main == HEAD` |
| Execution predecessor | AUTO-017, COMPLETE / Done, CLOSED and FROZEN |
| AUTO-017 implementation commit | `1dab51d83dfe3f2975aa944dc4c0a3924cb6eed0` |
| AUTO-017 closeout commit | `acd517ef4ea852f7f4dcab610f8c34e93a9c3ce4` |
| Frozen predecessor contract | `docs/workflow-automation/stage-prompts/AUTO-017.md` |
| Predecessor SHA-256 | `50760879b2f64c395c8c3c5ee83c3bdac1a8b8456588b144c068f01d1080b1e8` |
| Frozen Master Plan | `docs/workflow-automation/successor-planning/AWE-GOVERNED-AUTONOMOUS-STAGE-EXECUTION-MASTER-PLAN.md` |
| Master Plan SHA-256 | `8ab499c0240cc542e735eb5d1953dcd93994ebd87f1ef7413e9346805d613077` |
| Development-stage authority | `STAGE_REGISTRY.md` §3, especially rules 1–3, 3a, 10; Standard Stage Protocol in `stage-prompts/README.md` |
| Proposed implementation branch | `feature/auto-018-durable-lifecycle-events`, only after separate authorization |
| Later completion report | `docs/reports/workflow-automation/AUTO-018-completion-report.md` |

The remediation session may modify only this file. Its required input identity is
686 lines, 50579 bytes, SHA-256
`39b6867cc58a12c95722b01a6864f817680c05cfd20e576eebd86f8b506d9238`.
Only this candidate may be untracked/modified at remediation entry; the index must
be empty and HEAD/origin/main must equal the planning baseline. No new discovery,
finding IDs, implementation, tests or authorization are part of this remediation.
It must not update governance
mirrors, including their historical statements that the contract is not yet
drafted. Their reconciliation belongs to a separately authorized governance act.
The frozen artifacts' historical candidate-status prose does not override the
current registry, task record and committed AUTO-017 closeout.

The Master Plan governs architecture; this candidate refines ST-02 only. MUST,
MUST NOT and refusal requirements below are normative upon authorization. An
unresolved contradiction with frozen authority must be reported, not silently
resolved by implementation. The SSP applies by reference, not by duplication.

## 2. Repository evidence and resulting constraints

All code references in this section are to the planning baseline above.

| Evidence | Consequence for AUTO-018 |
|---|---|
| Master Plan §2.3, §4 AUTO-018: per-event files, hash chain, authoritative events, rebuildable projection | No JSONL replacement and no database or external event broker |
| Master Plan §2.4: seven operation phases; ST-02 records, ST-03 consumes them | Persist truthful phase evidence without a recovery decision engine |
| `application.py::transition_to`, `revise_record`, `_publish` | Preserve the existing transition table and application authority; route publication through events |
| `state.py::RunStateStore.publish/load`, `publish_atomically`, `publish_exclusively` | Reuse the single redaction boundary, repository lock and no-clobber primitive; separate immutable records from replaceable projections |
| `_invoke_provider` publishes a completed invocation before `_review`, `_correct`, `_verify_closure` validate it | Record receipt, validation, acceptance and transition independently; do not claim E8/E9 recovery fixed here |
| `providers/base.py::ProviderInvoker._invoke_once`: `on_started` runs before `run_provider_process`; `Popen` acknowledgment is not exposed | A narrow post-spawn observer seam is required; calling `on_started` a dispatch receipt would be false evidence |
| `state.py::ProviderInvocationIntent`, `_reconcile`; `application.py::_resume_from` | Keep existing resume policy; phase-driven continuation belongs to AUTO-019 |
| AUTO-017 §20 DO-018-1/2; `_start_policy_run`, `StageStartStore` | Record policy publication and Stage Start binding as events; explicitly retain immutable primary authority artifacts |
| `models.py::canonical_json_bytes` excludes named wall-clock fields recursively | Do not use it as an integrity digest over event bytes; preserve all existing digest behavior |
| `policy.py::authority_json_bytes`, `authority_digest` | Reuse timestamp-inclusive canonical serialization for new integrity records |
| `recovery.py::reject_ledger_rewrite` and four recovery ledgers | Emit ledger append facts without changing recovery command decisions |
| Security tests admit one directory enumeration, in `plan.py` | Narrowly extend that structural test for the external event directory; retain the actual prohibition on worktree/plan discovery |
| `workflow/events.py`, `workflow/event_store.py` implement a different state machine; `agentos_workflow/orchestrator/state_store.py` owns different JSONL records | Architecture evidence only; no imports, reuse of their authority, or edits |
| `schema/registry.py` is the workflow-contract registry, not the runner state loader | Runner wire-version dispatch stays runner-local |
| Registry AUTO-017 COMPLETE, AUTO-018 NOT_STARTED; task AUTO-018 Planned; Current set empty | Contract preparation does not promote a task or start a run |

Tests are architecture evidence in this planning session, not implementation
verification. No existing production or test file is modified or executed as an
AUTO-018 implementation by preparing this document.

## 3. Objective and bounded scope

Make lifecycle changes reconstructable from durable, ordered, integrity-checked
evidence. `MilestoneRunnerApplication` remains the sole workflow transition
authority. EventStore persists and folds facts; OperationJournal records execution
evidence. Neither chooses the next workflow step.

ST-02 includes:

1. Strict, closed lifecycle event schemas, append-only EventStore and pure fold.
2. Deterministic operation identity and immutable request/attempt/result artifacts
   for the four existing provider roles.
3. Pre-spawn intent and truthful post-spawn receipt, followed by distinct result
   receipt, validation, persistence and applied-transition records.
4. Event-backed publication of every subsequent governed RunRecord mutation,
   including existing checkpoints, verification results, counters, approvals and
   recovery-ledger appends. Recording an approval grants no new approval authority.
5. Crash-safe event publication, projection repair, bounded hostile-record reads,
   event/phase write idempotency and evidence of incomplete publication.
6. Compatibility dispatch and an explicit, non-executing snapshot bridge for
   previously published policy-governed records (§10).

The §2.4 general Operation identity can represent a verification step structurally.
ST-02 records existing verification outcomes as lifecycle facts; it does not add
verification retry/recovery policy or a new verification scheduler. The dedicated
Git operation ladder is entirely AUTO-026. No Git dispatch intent or synthetic Git
receipt is introduced here.

## 4. Normative invariants

| ID | Requirement |
|---|---|
| INV-018-01 | Only application-layer code in `milestone_runner/application.py` may request append of `STATE_TRANSITIONED`. Persistence validates and records it; folding reproduces it without executing it. |
| INV-018-02 | One repository RunLock serializes all event, operation, publication-witness and projection writes. Its continuing ownership must match the canonical repository/storage root, lock inode and publication descriptors (§7.4); matching repository identity alone is insufficient. No new lock domain; no unlocked repair. |
| INV-018-03 | One run has one gap-free sequence beginning at 1. Canonical filename, embedded sequence, run identity, policy pin and predecessor digest agree. |
| INV-018-04 | Published events and operation evidence are immutable. Exact duplicate append changes no content or identity, but must confirm durability under §7.5 before reporting success; conflicting reuse is a typed refusal before further effects. |
| INV-018-05 | `state.json` is a cache of verified events for event-backed runs. No state-only write may advance such a run. |
| INV-018-06 | Every event binds repository identity, stage ID, run ID, contract digest, policy digest and Stage Start ID. No event resolves policy or mints authorization. |
| INV-018-07 | A durable dispatch intent precedes entry to process creation. Receipt means observed process creation, not intention, provider completion, or successful validation. |
| INV-018-08 | Receipt, validation, acceptance and transition are separate durable facts. Invalid or failed results remain evidence and never masquerade as accepted successes. |
| INV-018-09 | Pure replay does no repository inspection, provider invocation, verification execution, Git action, policy resolution or recovery command. |
| INV-018-10 | All persisted bytes pass through `state.py::write_redacted_artifact`; integrity hashes cover the final redacted bytes/values. Redaction findings remain counted and visible. |
| INV-018-11 | Corrupt, conflicting or ambiguous storage never licenses workflow progress, event-chain truncation, evidence deletion, or a new run using a consumed authorization. |
| INV-018-12 | All existing states, edges, budgets, role vocabulary, review/result semantics and Git gates remain unchanged. New storage StopReasons do not add transition edges. |
| INV-018-13 | All v2-policy acceptance runs use explicitly admitted test doubles. Live/unclassified adapters remain refused by AUTO-017's gate. |
| INV-018-14 | Hermes and other orchestrators acquire no lifecycle authority or write interface. Completion never chooses, solicits or starts another Stage. |

R01 additionally requires §6.1's complete durable mutation declaration before any
constituent effect. R03 requires that visibility alone never grants durability or
permission for a dependent effect. R04 limits reference validation to the explicit
declaration/evidence distinction in §8.3; a prospective path is not an artifact.

Master Plan INV-01 and the event portion of INV-07 are delivered here. Its INV-06,
discovery cardinality across recovery (INV-02), and FA-3/FA-6 in their entirety are
not claimed complete until their designated later stages pass. A byte-identical
event retry is not an exactly-once external execution guarantee.

## 5. Event schema, identity and ordering

### 5.1 Wire representation

`LifecycleEvent` is a closed, strict model with these required fields:

| Field | Requirement |
|---|---|
| `schema_version` | Exact integer `1`, independently versioned from state/configuration |
| `repository_identity`, `stage_id`, `run_id` | Existing validated grammars; must agree with the addressed run and frozen authority |
| `contract_sha256`, `policy_digest`, `stage_start_id` | Existing 64-lowercase-hex pins; required, never null |
| `sequence` | Exact integer in `1..99_999_999`; bool, float and string rejected |
| `state_version` | Exact integer; equals sequence in event-backed runs |
| `event_type` | Member of the closed enum in §5.2 |
| `recorded_at` | Existing UTC timestamp grammar; covered by integrity hashing |
| `payload` | Discriminated closed model specific to event type; no arbitrary update dictionary |
| `payload_digest` | SHA-256 of timestamp-inclusive canonical payload bytes |
| `prev_event_digest` | Null only for sequence 1; otherwise previous event's full-file SHA-256 |
| `event_id` | SHA-256 of the canonical event fields above, omitting only `event_id` |
| `mutation_id`, `mutation_index` | Required keys, both null outside a grouped mutation; for a constituent, the declaration's 64-hex ID and exact 1-based manifest index (§6.1); included in event identity |

Canonical bytes use `authority_json_bytes` with no trailing newline. Full-file
SHA-256 is distinct from `event_id`; the next event chains to the full-file digest.
Canonical equality is checked on load, as well as each digest. Existing
`canonical_digest`, policy digests and approval bindings remain byte-unchanged.
All digest-bearing JSON is constructed from strict model dumps: no floats,
non-string keys, surrogate code points or serializer-dependent objects. Unlike
the older general digest helper, integrity serialization must not silently drop
any key or normalize a previously published value.

All ordering comes from sequence, never directory order or timestamps. Equal or
backward wall-clock observations do not reorder events. `state_version` increases
by exactly one for every event, including evidence-only events; therefore every
`STATE_TRANSITIONED` has previous version +1. It is not a remediation counter.

The filename is `events/<sequence:08d>-<event_type>.json`, using the enum's exact
uppercase wire spelling. Reject filename/type mismatch and two files for one
sequence. Sequence exhaustion refuses; it never wraps or overwrites.

### 5.2 Closed ST-02 event vocabulary

| Event | Payload and permitted effect |
|---|---|
| `RUN_INITIALIZED` | Full validated initial IDLE record, fixed run pins and format origin; first event for a new run |
| `RUN_BASELINED` | Full validated historical governed snapshot and source-byte digest/version; first event only for §10's compatibility bridge |
| `STAGE_START_BOUND` | Exact-name authorization, consumption-witness and binding references with their integrity digests; evidence only |
| `POLICY_PUBLISHED` | `policy.json` reference and its exact-byte digest; evidence only |
| `APPLICATION_MUTATION_DECLARED` | Complete immutable typed mutation manifest of §6.1, including original evidence and intended transition; no constituent body effect |
| `RUN_RECORD_UPDATED` | Typed replacement values for existing non-state fields, with before/after record-body digests and a typed durable-evidence-reference list for asserted provider completion (§8.3); no authority-pin/state/version updates |
| `RECOVERY_LEDGER_APPENDED` | Closed ledger-name enum, original entry, previous length and entry digest; precisely one append, no historical rewrite |
| `OPERATION_REQUEST_CREATED` | Operation ID, request reference/digest, logical-step tuple |
| `OPERATION_DISPATCH_INTENT` | Operation ID, attempt number, intent reference/digest |
| `OPERATION_DISPATCH_RECEIVED` | Operation ID, attempt number, receipt reference/digest |
| `OPERATION_PRE_SPAWN_FAILED` | Operation ID, attempt number, positive no-process-created verdict reference/digest |
| `OPERATION_RESULT_RECEIVED` | Operation ID, attempt number, redacted raw-result reference/digest and execution-outcome metadata |
| `OPERATION_RESULT_VALIDATED` | Operation ID, attempt number, typed verdict reference/digest |
| `OPERATION_RESULT_ACCEPTED` | Operation ID, accepted-result digest, existing typed findings/counter/checkpoint updates and before/after body digests |
| `OPERATION_RESULT_REJECTED` | Operation ID, invalid/failed verdict digest and existing failure accounting; no successful-result or round consumption |
| `STATE_TRANSITIONED` | Explicit from/to states, before/after body digests, existing stop reason and typed transition updates; optional causative operation ID |

`RUN_RECORD_UPDATED` is closed over baseline RunRecord fields only. It cannot append
the four recovery ledgers through a second route, and cannot apply an operation's
accepted findings/counters through a second route. Collection replacement must
enforce existing append-only rules and the existing single-row provider completion
rule. Before splitting a mixed mutation, durably declare its complete typed
manifest (§6.1). Then emit ordinary data changes, ledger appends, and transition
in manifest order. Do not lose intermediate transitions by comparing only the
final record passed to `_publish`.

Every payload that modifies the projection carries sufficient typed data to fold
without provider transcripts, worktree contents or fresh execution. Its digest-bound
durable evidence references must nevertheless verify (§8.3); prospective legacy
transcript path declarations do not assert existence. A valid hash over an illegal semantic update
does not make the event valid.

No decision, cycle scheduler, model-provenance, transport or Git-operation event
is reserved as an executable placeholder. New vocabulary requires a later contract
and explicit schema compatibility treatment.

## 6. Fold and transition authority

`fold(events)` is deterministic validation and reconstruction. The first event
establishes the body; subsequent events apply only their typed effects. It validates
the closed `ALLOWED_RUN_TRANSITIONS`, authority pins, old values, ledger prefixes,
operation dependencies and before/after digests at every step.

Projection-managed `state_version` and `last_event_id` are excluded from record-body
digests to avoid a circular event ID. All other body fields, including timestamps,
are included. After folding event N, version is N and last ID is event N's ID.
The same serializer produces folded bytes and `state.json`, making the acceptance
comparison byte-exact rather than merely JSON-equivalent.

`transition_to` remains the application's validator/constructor for transitions.
The application must retain each approved transition until its event is appended;
an in-memory mutation alone is not a durable transition. EventStore cannot select
a target state. Its transition append primitive accepts the typed application
record and verifies it; it has no retry, recovery, review or successor logic.

`RunStateStore.publish` for event-backed runs publishes only a verified folded
projection, never an arbitrary caller record. Existing recovery/approval helpers
may continue returning proposed records; only application code converts their
approved changes to lifecycle events. `RunStatus`, terminal-state rules and all
edges remain exactly the baseline set.

Read-only load returns the verified folded record without writing. A mutating
application command repairs a missing/stale projection under RunLock before any
further execution. A lock-aware load may perform that repair directly. Thus load
always obtains authoritative state, while status/verify do not gain unlocked
filesystem writes. No lock upgrade while holding another incompatible lock.
An unlocked reader must not mistake a concurrent append's intermediate files for
a stable corruption verdict: check for a changing publication witness and writer
contention, and report a retryable read/LOCK_CONTENTION refusal if a consistent
view cannot be obtained. No write or workflow action follows that refusal. A
mutating command establishes its final integrity verdict under the held lock.

### 6.1 Complete logical-mutation evidence (AUTO018-CONTRACT-R01)

An existing application command may propose one logical mutation containing
several effects: record changes, a recovery-ledger append and a transition. Before
the first constituent becomes authoritative, application code must append and
durably confirm `APPLICATION_MUTATION_DECLARED`. This is evidence of an already
computed application decision, not a new transition authority or a recovery plan.
It applies to every such existing multi-event mutation, including the four
recovery commands and result acceptance plus its already-decided transition.
Do not group observations across provider execution or predict a future result.

The declaration's closed payload has schema version 1 and contains:

- `mutation_id`: SHA-256 of the full canonical declaration payload excluding only
  this field; no clock-derived allocation or separate mutable counter.
- Full run/authority pins; the prior event ID, sequence/version and record-body
  digest; the initiating existing command/action kind and its original timestamp.
- Original validated, redacted typed command evidence: the complete recovery
  entry/outcome where applicable, including reason, classification/OWNER ruling
  if present, observed repository context, original ledger length and budget
  deltas. For accepted results, include the original validated-result reference
  and typed accepted updates. No fresh observations may replace that evidence.
- The complete ordered constituent manifest: each exact event type, payload,
  recorded timestamp, intended sequence/version and before/after body digests.
  The declaration occupies the next sequence and constituent 1 follows it.
  Future event IDs/hash links are calculated as those events are emitted, avoiding
  circular hashes; their semantic content is already fixed by this manifest.
- The intended transition's original from/to states, stop reason and typed
  updates, plus the final record-body digest. If the existing logical mutation
  contains multiple transitions, retain each in its exact manifest position.

All digest-bound evidence needed by the manifest must be validated and durability
confirmed before the declaration. Its content-addressed identity includes the
starting tip, so a different mutation at a later tip cannot silently reuse it.
The declaration advances only event-tip/version metadata. It applies none of its
listed counter, ledger, finding or workflow-state effects.

Every constituent carries the declaration ID and manifest index. Fold validates
that declaration first, exact payload equality and order, expected original body,
and every before/after digest. It refuses missing declarations, changed payloads,
skipped/repeated indices, interleaved mutations and an unrelated next event while
a manifest is incomplete. A declaration cannot itself apply a transition; only
application code appends the matching `STATE_TRANSITIONED` constituent.

A proper constituent prefix may be folded as recorded, but load must expose a
typed `IncompleteApplicationMutation` alongside that prefix: declaration identity,
complete original manifest/evidence, intended transition and applied-prefix length.
It must never return that prefix as an ordinary executable completed mutation.
Completeness is derived from all declared constituents matching the chain, not a
mutable completion flag. Thus every durable prefix has either no constituent
effect, or an explicitly identifiable incomplete mutation with the original data
needed to interpret all its effects. Projection reconstruction preserves this
distinction even if a constituent already changed the apparent workflow state.
The bound manifest must fit the existing event-size ceiling; reject oversize
before the declaration or any constituent effect, never persist a partial manifest.

Within the original uninterrupted command, application code may finish emitting
the predeclared constituents in order. Once that command fails or loses its lock,
a later invocation may inspect the declaration/prefix and confirm storage
durability, but ST-02 refuses execution with `APPLICATION_MUTATION_INCOMPLETE`.
It must not complete, roll back, reinterpret, or choose a recovery action for the
mutation. Those decisions belong to AUTO-019. A complete duplicate manifest and
its complete constituents are a no-op after §7.5 durability confirmation.

## 7. Publication, atomicity and durability

### 7.1 Storage boundaries

All paths remain below the existing external repository/run root, never inside
the target worktree. New run-local paths are:

```text
events/NNNNNNNN-TYPE.json
event-publication.json
operations/<operation-id>/request.json
operations/<operation-id>/attempts/NNNN/dispatch-intent.json
operations/<operation-id>/attempts/NNNN/dispatch-receipt.json
operations/<operation-id>/attempts/NNNN/pre-spawn-failed.json
operations/<operation-id>/attempts/NNNN/result.raw
operations/<operation-id>/attempts/NNNN/result.validated.json
operations/<operation-id>/applied.json
```

Attempt directories refine the Master Plan's illustrative flat operation layout:
bounded pre-spawn retries must not replace an earlier attempt's intent. No
`dispatch.json` ambiguous between intent and receipt is used.

`event-publication.json` is a bounded, closed integrity witness for the latest
publication intent: schema version 1, full run pins, sequence, event ID, full event
digest, predecessor digest. It is not an alternate source of workflow data. It
exists to detect loss of the tail, including when `state.json` lagged the event.
A hash chain alone cannot detect deletion of its entire last suffix.
The witness is mandatory once genesis publication begins. Missing, malformed or
regressed witness with existing events is corruption, not a reason to recreate it.
For an established stable chain it must identify exactly its final event. Only the
first append into a proven new/legacy-unconverted run may begin without a witness.

### 7.2 Ordered append protocol

Under the already-held repository RunLock, with §7.4 ownership checks at every
publication/effect boundary and §7.5 durability confirmation:

1. Verify authority artifacts, prior chain, prior publication witness and caller's
   expected tip. Validate and redact payloads; compute final canonical bytes.
2. Publish digest-bound immutable evidence artifacts first, exclusively, and fsync
   their parent directories. No durable-evidence reference may assert bytes not
   yet durable; prospective legacy path declarations follow §8.3. A constituent
   additionally requires its complete, durable §6.1 declaration first.
3. Atomically publish and fsync `event-publication.json` naming the intended next
   event. Refuse a witness inconsistent with the current verified tip.
4. Exclusively publish the event file through the redaction boundary and fsync its
   directory. Never use replacement over an existing event file.
5. Fold the verified event and publish `state.json` atomically; fsync its directory.
6. Only after the event is durably published may its caller treat that fact as
   committed; only after projection publication succeeds may normal execution
   proceed to the next step. A post-event projection failure is an error with a
   committed event, not permission to retry an external effect.

An exact duplicate event is recognized before allocating another sequence or
changing the witness. Recheck the original canonical file and referenced evidence;
confirm all required durability barriers under §7.5, then return its existing
identity without changing timestamps, sequence or counters. Identical visible
bytes alone do not make this a successful duplicate.
The same event ID with different bytes, or the same sequence with another digest,
refuses. A caller retries the original envelope, not one with a new clock reading.

Use `publish_exclusively`'s no-clobber discipline for immutable files and
`publish_atomically` for replaceable cache/witness files. Both stay behind
`write_redacted_artifact`. All successful writes must include file and directory
fsync, including newly created parent directories up to the existing durable root.
Do not swallow durability errors on new paths. Durability is local filesystem
durability under the repository's existing POSIX assumptions, not remote replication.

There is no atomic transaction spanning an external process, several files and a
workflow transition. The durable ordering exposes those gaps rather than hiding
them. A crash after witness publication but before its event leaves an incomplete
publication and must stop on load; ST-02 does not invent or auto-append the missing
event. A crash after the event but before the projection permits projection repair
from the verified chain after §7.5 durability confirmation, with zero execution.
A crash after an artifact but before
its event leaves orphan evidence; it is not proof of acceptance and is not deleted.

### 7.3 Read and security discipline

Reads must reject symlinks in any path component, parent-swap escapes, non-regular
files, invalid UTF-8, duplicate JSON keys at any depth, unknown fields/versions,
noncanonical bytes, invalid types, digest mismatches and cross-run references.
Use descriptor-relative no-follow bounded reads, including the final file.

One bounded, non-recursive enumeration of the explicitly addressed external
`events/` directory is permitted in `state.py`'s event storage helper. Sort and
validate names, then read by exact name. No scan of worktree, repository root,
Stage Start directory, other runs, operations or successor contracts is allowed.
Operation paths are derived from validated IDs in the chain. This is a narrow
amendment to AUTO-017's enumeration test, not to AUTO-016 invariant 19's prohibition
on plan discovery inside the repository.

Enforce existing 8 MiB state and 64 MiB artifact ceilings. Each event, witness,
request and validated-result JSON is at most 16 MiB, additionally bounded by typed
field/list limits; raw results retain the existing 64 MiB ceiling. Validate file
sizes before allocation, stream chain verification, and reject sequence overflow.
Only owned namespaced temporary files may be ignored; unknown canonical entries,
subdirectories or duplicate sequence names in `events/` fail closed. No temp-file
cleanup sweep, truncation, compaction, retention or garbage collection is added.

Redact free text before validation/digest construction, then pass final serialization
through the mandatory write boundary again. If that final pass changes structural
identity, pins or canonical bytes, refuse publication. Never persist an unredacted
copy for hashing or debugging. Record redaction counts without recursive redaction
events or changing an already frozen request. Do not change existing digest vectors.

### 7.4 Continuing lock and storage ownership (AUTO018-CONTRACT-R02)

`is_held` and equal repository-identity strings are necessary, not sufficient.
For governed publication/effect paths, acquisition must retain a descriptor-bound
ownership context for the canonical target-repository root, repository-scoped
storage root and lock file. Capture each canonical path and descriptor's
`(st_dev, st_ino)` identity, retaining no-follow directory descriptors for the
addressed storage ancestry. The lock descriptor must still hold the actual flock;
metadata, PID liveness and a lock file's mere existence are not substitutes.

The store's canonical root must equal the root addressed by that hold. A lock at
another storage root with the same repository identity cannot authorize the store.
The current no-follow path walk must resolve to the captured repository root,
storage ancestry and lock inode. Missing/replaced components, renamed-away roots,
unexpected file types, shared/aliased lock inodes rejected by baseline validation,
or a lost/closed hold invalidate this context. Never silently rebind the old hold
to a replacement path, recreate the lock, steal another hold or change lock domains.

Publication must derive its parent/file descriptors from that retained, verified
storage context; compare them with the current canonical path identities before
creating directories, opening write targets, linking/replacing a canonical file,
and performing durability confirmation. This applies to events, mutation
declarations, operations, the publication witness, projection and governed
authority-artifact writes. Do not check one root and publish via an independently
reopened pathname. Keep all state/evidence bytes behind the existing redaction
boundary; the existing descriptor-local diagnostic lock metadata remains its
established exception and gains no lifecycle authority.

Revalidate the same ownership context after publication and immediately before
entry to an external effect (provider spawn or an existing verification/Git
executor call reached through the application). No Git authority or execution
policy changes: this is only a prerequisite on an already permitted call. The
provider invoker must repeat the check at actual spawn entry, not merely when
the application first constructs a request. Lock checks in stale callbacks fail
as well; a process already created before loss follows existing cleanup semantics.

Detected replacement raises typed `LockOwnershipLost` / `LOCK_OWNERSHIP_LOST` and
invalidates the context for the rest of that invocation. The stale holder must
not publish, confirm publication, append a stop to suspect storage, or proceed to
another effect. It may release its original descriptor without unlinking either
lock path. A race detected after a publication syscall prevents acknowledgment
and dependent effects; any already-visible bytes remain uncertain evidence under
§7.5. This does not claim to undo an effect begun before replacement, nor to make
POSIX path checks atomic with arbitrary privileged namespace changes.

The exact additions to the later allowlist are `milestone_runner/lock.py` for
this ownership context/validation and `tests/test_milestone_runner_lock.py` for
its deterministic tests. No lock backend replacement, lease, expiry, PID-based
recovery or AUTO-019 reconciliation is introduced. Baseline supervised behavior
and immutable authority bytes remain unchanged; the strengthened checks bind
governed lifecycle paths and their shared publication primitives.

### 7.5 Uncertain publication and confirmation (AUTO018-CONTRACT-R03)

Publication has typed outcomes `NOT_PUBLISHED`, `DURABLE` and `UNCERTAIN`.
`NOT_PUBLISHED` requires proof that no canonical publication occurred. If link or
replace made canonical bytes visible and a required directory fsync then fails,
or canonical publication may have occurred but cannot be confirmed, raise typed
`PublicationUncertain` / `PUBLICATION_UNCERTAIN`, not a no-effect write failure.
Carry the artifact address, expected identity/digest and failed barrier when known;
do not require another durable write to report a failed durable write.

`DURABLE` is returned only after required file and directory barriers succeed on
the correct §7.4 descriptors. `CREATED` or `IDENTICAL_EXISTS` may describe content
placement, but neither alone is a durability verdict. This rule covers exclusive
artifacts and events, replaceable witness/projection files, and existing immutable
policy/binding/witness artifacts when relied on by a governed lifecycle command.

Before a retry or later invocation permits any dependent effect, it must confirm
the full relied-upon evidence dependency set under the correct current lock:

1. Reopen through the verified descriptor context and strictly validate canonical
   bytes, identity, digest and event/manifest relationships. Missing or conflicting
   bytes retain their existing typed refusal; confirmation cannot repair them.
2. Successfully fsync the exact regular-file descriptors and all necessary parent
   directories, including ancestry whose creation/publication durability was not
   established. Recheck canonical path/inode bindings before reporting success.
3. Confirm all dependencies, including publication witness, referenced immutable
   evidence and applicable chain prefix, before the next event or external effect
   can rely on them. If any barrier fails or ownership is stale, remain refused;
   do not report a durable duplicate or proceed because the bytes compare equal.

A later invocation cannot know from visible bytes whether an earlier caller's
directory fsync succeeded. Therefore every reused dependency is unconfirmed until
these barriers succeed in the current valid ownership context; a process-local
confirmation cache may be reused only within that unchanged hold and exact inode/
digest dependency set. No persisted boolean or error-marker absence exempts this
check. Read-only load may inspect and fold integrity-valid visible evidence, but
cannot supply execution-ready durability confirmation; an effecting caller must
perform the locked confirmation above, or refuse. Restart cannot discard uncertainty
merely by discarding the earlier exception object.

Confirmation performs barriers on existing bytes; it must not republish or rewrite
identity-bearing content, timestamps, event IDs, sequences, counters or ledger
entries. Successful duplicate confirmation leaves content and modification times
unchanged. It selects no recovery action, does not supply missing events, does not
complete an incomplete §6.1 mutation and never retries an external process. Missing
events after a witness still fail under §7.2; intact but unconfirmed files are the
distinct case governed here. If storage remains unavailable, the result remains
typed fail-closed. Preserve all visible evidence without claiming it durable.

## 8. Operation identity and phase ladder

### 8.1 Identity

The Master Plan derivation is fixed as SHA-256 of UTF-8
`run_id|step_kind|cycle_no|role|slot`. Components contain no `|`; numeric components
use unpadded decimal. Preserve role wire values IMPLEMENTATION, REVIEW, CORRECTION,
CLOSURE. Program role names remain aliases, not new wire values.

For current provider steps, `step_kind = provider`; cycle number is 0 for
implementation/discovery and 1 for the existing single correction/closure pair.
`slot` is `<milestone-id>:<reopening-count>` for implementation, `discovery` for
review, `correction` for correction and `closure` for closure. Reopening count is
derived from existing durable reopening entries for that milestone, never the
clock, transcript sequence or number of times resume was called. No new cycle
behavior or retry entitlement follows from this tuple. Future stages extend its
closed step-kind vocabulary through their own contracts.
Attempt numbers begin at 1, are gap-free within an operation and retain the
existing `MAX_SPAWN_RETRY_ATTEMPTS = 3` bound. Directory names are `0001` through
`0003`; names themselves grant no retry permission.

`OperationRecord` is a typed view derived from events and immutable artifacts,
not another mutable authoritative JSON file. It binds the tuple, full run pins,
request digest, actual baseline adapter identity, existing provider role, milestone
if any, pre-fingerprint, attempts and highest evidenced phase. Frozen `roles`
selections remain audit-only and do not select adapters/models in this stage.

Request and result content addresses are full SHA-256 values over their final
redacted bytes. Fixed artifact paths plus those digests provide addressing; a
second global blob store is not required. Requests contain the existing prompt and
execution constraints or digest-bound references to their durable transcript bytes.
No Hermes envelope, provider catalog or model-provenance schema is introduced.

### 8.2 Ordered facts

| Phase | Required evidence and meaning |
|---|---|
| `REQUEST_CREATED` | Immutable `request.json` and `OPERATION_REQUEST_CREATED`; records what AWE requested before dispatch |
| `DISPATCH_INTENT` | Attempt intent and event, durable before spawn; binds attempt, request/argv digest, actual adapter and fingerprint |
| `DISPATCH_RECEIPT` | Post-creation observer records PID and observed UTC start time for a local process, or explicitly typed scripted-fake acknowledgment in tests; event `OPERATION_DISPATCH_RECEIVED` |
| `RESULT_RECEIVED` | Redacted raw result, its digest and outcome/transcript references, then receipt event; no acceptance implication |
| `RESULT_VALIDATED` | Immutable typed result plus VALID/INVALID/EXECUTION_FAILED verdict and bounded diagnostics, then validation event |
| `RESULT_PERSISTED` | `OPERATION_RESULT_ACCEPTED` commits the existing accepted result/counter effects; rejected verdicts use `OPERATION_RESULT_REJECTED`, not a success event |
| `TRANSITION_APPLIED` | Application appends the causative `STATE_TRANSITIONED`; only afterward writes `applied.json` referencing that event ID/version/digest |

Returning from PROVIDER_WAIT to the invoking state is a transport excursion, not
the result's `TRANSITION_APPLIED`. Only the later transition caused by accepting or
rejecting that result completes the operation. Persist result effects before that
transition; never put both facts in a single opaque completion write.

For a rejected result, retain receipt and terminal validation verdict, append the
rejection accounting and take the existing stop route. Malformed discovery remains
the baseline provider-failure route in ST-02; overflow policy and new OWNER stops
are not implemented. No successful round is fabricated for an invalid result.

`PRE_SPAWN_FAILED` is a separate terminal attempt outcome, permitted only when the
OS positively refused process creation. It must be durable before the existing
bounded retry. It has no receipt or provider result. Retry keeps the operation ID,
increments attempt number and preserves earlier artifacts. Timeout, cancellation,
nonzero exit, receipt-publication failure and unknown outcome are not pre-spawn
failure. A receipt-write failure after spawn stops further progress, cleans up the
child using existing process-group handling, and never triggers a spawn retry.

Observers carry evidence to application-owned journal callbacks; providers never
append transition events. Existing `on_started` remains pre-spawn. A new observer
fires immediately after successful process creation, before waiting for completion.
Scripted fakes must exercise this same ordering contract without invented OS PIDs.
One attempt cannot hold both a receipt and PRE_SPAWN_FAILED. Only the attempt
reaching a provider result can supply the operation's terminal validation/result;
earlier pre-spawn attempts remain evidence. A different result under that same
identity is a storage conflict, not a replacement or a newly accepted result.

Publication failure may leave a valid prefix. Every normally returned early-stop
path records its verdict if storage is usable; an abrupt death or unavailable
storage can leave only the last durable phase. Do not manufacture a verdict after
the fact. Missing `applied.json` with a valid causative transition is an incomplete
receipt, not authority to apply the transition twice; that receipt can be rebuilt
from the verified event without executing a transition.

### 8.3 Prospective paths versus durable evidence (AUTO018-CONTRACT-R04)

These are distinct types of reference, not two validation modes chosen by a caller:

1. **Prospective legacy transcript path declaration.** The pending baseline
   `ProviderRunRecord` (`completed_at is None`) preallocates `stdout_path` and
   `stderr_path` before spawn. Those fields describe where output will be written;
   they assert neither existence, a digest, nor successful publication. Validate
   their grammar, run containment and no-follow access if present, but absence is
   valid in a pre-spawn/in-flight prefix. A path's presence alone is not proof of
   execution, completion or durable evidence. The unchanged legacy row schema does
   not acquire a magic digest or a success assertion on account of its filename.
2. **Digest-bound durable evidence reference.** A typed lifecycle payload, mutation
   manifest, request or result names an artifact as published evidence, with its
   exact relative path, artifact kind and full SHA-256 of final redacted bytes.
   The artifact must exist, be safely readable and match that digest before the
   asserting event/manifest is durably accepted and on every subsequent verified
   read/fold. Before dependent execution its durability must also pass §7.5.

For new event-backed invocations, the prompt is evidence when REQUEST_CREATED
binds its durable bytes; stdout/stderr remain prospective in the pending provider
row through dispatch. When invocation completion is published, the completion
event must carry digest-bound references to the actually published prompt,
stdout/stderr and any collected last-message artifact. This supplements the
unchanged row shape; `completed_at` must not be published as a new completion
fact before those artifacts are verified and durability-confirmed. Empty output
is represented by a durably published empty artifact with its actual digest, not
by an absent file. RESULT_RECEIVED independently asserts its `result.raw` bytes;
RESULT_VALIDATED asserts its verdict artifact. All must then exist and verify.

An event/manifest may carry a pending row with prospective fields and separate
durable evidence references. Its schema must make that distinction explicit; a
generic recursive search for path-shaped strings must not treat pending output
names as published evidence. Once a digest-bound reference is asserted, deleting
or corrupting the file fails with `OPERATION_RECORD_INVALID` (or the appropriate
authority/chain refusal), never downgrades it to prospective, and never triggers
provider redispatch. An applied receipt's expressly permitted reconstruction in
§8.2 remains limited to its already-durable causative transition.

The §10 historical snapshot bridge preserves legacy path declarations and their
original completion metadata as historical state; it does not fabricate historic
transcript digests or certify missing files as published evidence. A historical
path relied on as evidence by a current command must be safely read, validated and
digest-bound when that command asserts it. This preserves the historical snapshot
exception without weakening any new assertion's mandatory existence/integrity
check. Pure load of a pending legacy row cannot require future stdout/stderr.

## 9. Replay and failure semantics — ST-02 only

| Condition | Mandatory result |
|---|---|
| Identical event/artifact publication repeated | Same bytes/identity; successful no-op only after §7.5 confirms durability; no counter/ledger duplication |
| Complete declaration with only a proper constituent prefix | Expose `IncompleteApplicationMutation` with original typed evidence/intended transition; a later effecting invocation refuses `APPLICATION_MUTATION_INCOMPLETE`, without a recovery decision |
| Held lock no longer matches addressed canonical roots/lock inode/descriptors | `LOCK_OWNERSHIP_LOST`; invalidate holder, no publication or further effect (§7.4) |
| Canonical bytes visible but required durability barrier fails or is unconfirmed | `PUBLICATION_UNCERTAIN`; locked confirmation or continued refusal, never success from byte equality alone (§7.5) |
| Reused identity or sequence with different content | `EVENT_CONFLICT` or `OPERATION_RECORD_CONFLICT`; stop before dispatch or subsequent transition |
| Missing, reordered, edited, duplicate-sequence or foreign event; broken hash link; witness naming a missing tail | `EVENT_CHAIN_BROKEN`; effective HUMAN_INTERVENTION_REQUIRED, no execution |
| Valid chain and missing/stale/damaged projection | Return fold; repair only under RunLock; no provider or state-transition append |
| Projection claims a later tip than the verified chain | `EVENT_CHAIN_BROKEN`, never silently roll state backward |
| Missing/malformed required operation artifact, pin conflict, impossible phase order | `OPERATION_RECORD_INVALID`; no best-effort continuation |
| Valid durable prefix with an unresolved dispatch/result boundary | Retain evidence; ST-02 does not choose revalidation, adoption, redispatch or escalation policy |
| Missing/modified primary policy or authorization/binding/witness | Existing AUTO-017 typed refusal; events cannot heal or replace authority |
| Unknown state/event/operation wire version | `STATE_SCHEMA_UNKNOWN` or `LIFECYCLE_SCHEMA_UNKNOWN`, never guess a version |
| File/fsync/projection publication failure | No further effect; distinguish proven NOT_PUBLISHED, confirmed DURABLE event with failed later step, and PUBLICATION_UNCERTAIN; visibility alone never proves commitment |

New `StopReason` members are limited to `EVENT_CHAIN_BROKEN`, `EVENT_CONFLICT`,
`OPERATION_RECORD_INVALID`, `OPERATION_RECORD_CONFLICT`, `LIFECYCLE_SCHEMA_UNKNOWN`,
`APPLICATION_MUTATION_INCOMPLETE`, `LOCK_OWNERSHIP_LOST`, `PUBLICATION_UNCERTAIN`.
They are storage refusals, not new OWNER decision kinds.

On a broken chain, do not append a stop event to that chain or overwrite its
projection with a guessed state. Application reporting must expose the effective
safety stop `HUMAN_INTERVENTION_REQUIRED` and typed error independently of an
untrusted RunRecord. Preserve the recorded state as evidence; this diagnostic
does not add an outbound edge to a terminal state. When the chain is valid and a
normal failure transition is legal, application code may record the existing stop
transition in the usual way.

Read/fold must detect complete event-directory loss for a version-3 record or a
publication witness. No fallback to state-only mode. Coordinated deletion or
rollback of every independent artifact by a privileged attacker is outside the
local hash-chain guarantee; this stage adds neither trusted external anchoring
nor cryptographic authentication. The live-provider isolation gate stays closed.

ST-02's storage validators reject rewriting/regressing an already evidenced
operation; they do not choose what to do instead. `_reconcile` and `_resume_from`
must not branch on phase, dispatch fingerprint, stored result or receipt to select
a new recovery action. No `APPLY_STORED_RESULT`, `REVALIDATE_STORED_RESULT`,
`ESCALATE_TO_OWNER`, PendingDecision or RecoveryReconciler is added. Existing
resume policy remains, subject to the new storage integrity boundary; this is not
a claim that partial event-backed runs have safe automatic recovery yet.

## 10. AUTO-017 compatibility and authority artifacts

### 10.1 Schema boundary

Adding fields to a closed wire schema must be explicit (Master Plan AUTO-017,
"Must NOT be implemented early"). Event-backed state uses runner state wire
version **3**, with mandatory `state_version` and `last_event_id`. This is a
state-document revision only: configuration, policy, defaults, overrides and
Stage Start remain version **2**, milestone plan version remains **1**. The Master
Plan's v2-policy-governed program is not renamed or enabled by this wire revision.

Version dispatch must preserve strict historical validators. Exact integer 1 and
2 documents retain their established meaning; no event fields may be smuggled
into either. Unknown versions and bool/string/float versions refuse before model
coercion. Version 3 requires both policy pins and event-tip fields, and may never
be interpreted as a supervised run.

Supervised v1 behavior remains unchanged, including the read-only v1-to-v2 upgrade
and publication as state wire v2. Do not use a global constant change to silently
upgrade plans, fixtures, policy schemas or every supervised publication to v3.
Use explicit runner-local wire models/version dispatch as needed in `models.py`
and `state.py`; the unrelated `schema/` registry remains untouched.

New policy-governed starts are event-backed from RUN_INITIALIZED onward. Existing
policy-governed v2 state remains readable with no write or invented history.
Before its first explicitly requested mutating command publishes any new state,
under RunLock and after all existing authority checks, import the validated v2
snapshot as `RUN_BASELINED`. Record its original byte digest and source version;
then emit binding/policy evidence and publish the v3 projection. This bridge is
idempotent by the addressed run and first-event identity, not by current time.
If events or a publication witness already exist, validate them; never baseline
again from `state.json`.

The bridge records only the known historical snapshot, with transcript references
classified under §8.3. It does not synthesize
past requests, dispatch receipts, validation phases or elapsed execution history,
and it does not change the outcome of a resume/recovery command. Historical
provider rows remain historical rows; newly initiated operations use the journal.
A crash during the bridge follows §7's publication rules. A missing or corrupt
historical snapshot is a refusal, never a fabricated genesis. Tests and reports
must distinguish migrated history from fully event-recorded new runs.

### 10.2 Primary authority stays primary

Resolve DO-018-2 by retaining `policy.json`, authorization, key pointer, binding
and consumption witness as AUTO-017 immutable primary artifacts. Event projection
repair cannot reconstruct, replace, re-resolve or legitimize any of them. This
preserves OD-GSE-06 and D-AUTO017-03 rather than creating two competing authorities.

Keep the existing start order: authority validation, exclusive consumption witness,
binding, immutable policy publication. Before execution, record RUN_INITIALIZED,
STAGE_START_BOUND and POLICY_PUBLISHED and their projection; then emit the ordinary
IDLE-to-PREFLIGHT transition. Events attest publication, not create authorization.
The run is considered present when a publication witness or genesis event exists,
even if its state projection is absent; `exists()`/start must not create a second
run or consume authorization again in that gap.

AUTO-017's pre-genesis orphan-start semantics remain exact-name and single-use.
After genesis publication begins, event integrity rules govern projection loss.
Missing authority is never repaired by this distinction. Unchanged frozen
`registry_context`, contract/policy pins, arbitrary grammar-valid run IDs, and
consumption-witness checks continue at the same mutation boundaries.

No policy re-resolution on load/resume, no changed role dispatch, no consumption of
`max_remediation_cycles`, `on_retry_exhausted`, `max_owner_extensions` or `roles`.
Existing one-round review/correction/closure ceilings and severity behavior remain.
Existing accepted D-AUTO017-01 and D-AUTO017-03 rulings are not reopened.

## 11. Exact later implementation surfaces

This is a proposed allowlist for later authorization, not present write permission.

| Production path | Sole permitted change |
|---|---|
| `src/ai_workflow_engine/milestone_runner/events.py` (new) | Closed events/payloads, complete mutation declarations/incomplete-prefix evidence, integrity serialization, EventStore coordination and pure fold; no filesystem-write primitives |
| `src/ai_workflow_engine/milestone_runner/operations.py` (new) | Closed operation/phase records, deterministic identities and journal coordination; no workflow decisions or filesystem-write primitives |
| `src/ai_workflow_engine/milestone_runner/models.py` | Explicit state v3 model/version handling and eight storage StopReasons; retain legacy schemas/validators and unchanged transitions/digests |
| `src/ai_workflow_engine/milestone_runner/state.py` | Descriptor-bound durable I/O, uncertainty/confirmation, bounded event enumeration, publication witness, verified load/projection publication and reference classification, historical snapshot bridge; no `_reconcile` policy changes |
| `src/ai_workflow_engine/milestone_runner/application.py` | Declare complete existing logical mutations before constituent emission; journal/startup evidence, lock validation at publication/effect boundaries, incomplete/uncertain/error reporting; no `_resume_from` policy changes |
| `src/ai_workflow_engine/milestone_runner/providers/base.py` | Narrow pre/post-spawn observer propagation, continuing ownership check at spawn entry and cleanup on observer failure; unchanged argv, sandbox, environment, timeout and retry classifications |
| `src/ai_workflow_engine/milestone_runner/lock.py` | R02 only: descriptor-bound canonical root/lock identity capture, validation and invalidation of stale ownership; retain repository flock domain and existing metadata/release semantics |

The provider-base addition is justified by the missing receipt observation in §2;
the Master Plan §4 expected surface is explicitly planning-only. No adapter file
or ProviderBinding generalization is needed or allowed.

Exact test allowlist for later implementation:

- New `tests/test_milestone_runner_events.py`.
- New `tests/test_milestone_runner_operations.py`.
- Modify `tests/test_milestone_runner_state.py`.
- Modify `tests/test_milestone_runner_application.py`.
- Modify `tests/test_milestone_runner_providers.py`.
- Modify `tests/test_milestone_runner_lock.py` (R02 ownership tests only).
- Modify `tests/test_milestone_runner_security.py`.
- Modify `tests/test_milestone_runner_acceptance.py`.
- New `tests/milestone_runner_state_v2_corpus.json`, with baseline provenance and
  snapshot byte hashes embedded in the corpus, not generated from candidate code.

Later implementation may create only the completion report named in §1 as its
documentation output. Governance transitions have their own separately authorized
edit set. Frozen contracts, Master Plan, v1 corpus and historical evidence remain
byte-unchanged. This candidate's later review remediation is a separate bounded act.

All other production/test paths are excluded, especially `recovery.py`,
`review.py`, `policy.py`, `config.py`, `results.py`, `verification.py`,
`approval_git.py`, `plan.py`, `prompts.py`, adapter implementations,
`cli.py`, other `src/` subpackages, `agentos_workflow/**`, `agentos_dashboard/**`,
dependencies, scripts, examples and CI/configuration files. No new CLI command.

Existing AST snapshots may be updated only for the exact instrumentation above.
The R02 lock-file allowance is limited to §7.4 and does not permit unrelated lock
refactoring. Keep the existing diagnostic lock-write exception when testing the
single state/evidence write boundary; do not grant new writers to other modules.
Keep negative detectors and explicit baseline equality for transition tables,
ceilings, policy resolution, result parsing, retry policy and Git authority. Do not
replace meaningful assertions with broad exclusions to make the suite pass.

## 12. Verification obligations

Every test below is required during later implementation. Test IDs are contract
obligations, not claims that these tests already exist or have passed.

| ID | Required evidence |
|---|---|
| T-EVENT-SCHEMA | Every field/type/version/enum boundary, duplicate keys, noncanonical serialization, timestamp tampering and full digest vectors |
| T-EVENT-CHAIN | Delete first/middle/last/all events; reorder/rename/edit; duplicate sequence under another type; foreign run/policy/contract; broken predecessor; witness mismatch; all refuse |
| T-EVENT-IDEMPOTENT | Duplicate exact event and artifacts produce no bytes/mtime/counter changes; conflicting ID/sequence/digest refuses |
| T-EVENT-FOLD | Every event prefix folds deterministically; illegal transitions/ledger rewrites/counter double-application and generic update bypasses refuse |
| T-EVENT-PROJECTION | Missing/stale/corrupt cache repairs from valid chain under lock; ahead-of-chain cache refuses; read-only load writes nothing; repair spawns nothing |
| T-EVENT-ATOMIC | Inject failure before/after write, file fsync, witness replace, event exclusive link, directory fsync and projection replace; assert canonical bytes, committed tip, refusal and absence of subsequent effects |
| T-EVENT-TAIL | Delete the last event while projection is deliberately stale; publication witness detects loss; no fallback to a plausible shorter prefix |
| T-EVENT-LOCK | No writes/repair without correct held repository lock; two appenders cannot allocate the same sequence; stale expected-tip append refuses |
| T-MUTATION-PREFIX | R01: for each of reconcile-milestone, reopen-milestone, recover-failed-review and revalidate-correction, inject deterministic faults before declaration, after declaration and between every constituent through the final event; reload each durable prefix and prove the §6.1 outcome below |
| T-LOCK-IDENTITY | R02: same repository identity/different lock root; lock-file replacement after acquisition; target-repository root replacement; repository-scoped storage-root/ancestor replacement; ordinary two-writer contention; test both publication and effect boundaries as detailed below |
| T-PUBLICATION-UNCERTAIN | R03: successful link or replace followed by directory-fsync failure, then retry/reload in a later invocation; byte equality must not return durable success or permit a dependent effect until the correct barriers succeed |
| T-PROSPECTIVE-REFERENCE | R04: pending provider pre-spawn prefix with absent stdout/stderr loads/folds as valid declarations; missing/corrupt evidence after a durable assertion refuses, with no downgrade or redispatch |
| T-OP-ID | Fixed vectors for each role/milestone/reopening slot; repeated identity derivation stable; separate milestones distinct; retry attempt does not change operation ID |
| T-OP-ORDER | Counting fake for all four roles observes request and intent durably before spawn entry, then true receipt, raw result, verdict, acceptance and causative transition |
| T-OP-SPAWN | Positive OS pre-spawn failure creates verdict before bounded retry in same operation; timeout/nonzero/receipt-write failure never becomes PRE_SPAWN_FAILED |
| T-OP-INVALID | Missing/unparseable/out-of-scope result preserves raw evidence and terminal verdict; unchanged failure route/budgets; no accepted-success event |
| T-OP-GAPS | Stop/fault at each boundary for every role and inspect durable prefix; receipt absent never means no spawn; no automatic recovery is exercised or claimed |
| T-OP-APPLIED | Transition durable before applied receipt; missing receipt may be rebuilt without transition/counter duplication; contradictory receipt refuses |
| T-REDACTION | Secrets in prompt/stdout/stderr/result/diagnostic never reach any persisted artifact; digest verifies final redacted bytes; redaction finding counts visible; structural redaction refuses |
| T-HOSTILE-IO | Each new artifact type: symlink final/parent, parent swap, FIFO/device/directory, oversize, traversal, duplicate keys, invalid UTF-8/schema/digest; no escape or hang |
| T-AUTHORITY | Policy/binding/witness tamper or deletion cannot be healed from events; exact-byte AUTO-017 digests, single-use and registry disagreement behavior retained |
| T-COMPAT | Frozen v1 corpus, baseline-generated supervised/governed v2 corpus and new v3 round trips; no read-side migration writes; version confusion and mode mixing refuse |
| T-BASELINE-BRIDGE | One historical snapshot event, exact original digest, no synthetic past phases, idempotent interrupted publication handling, no second genesis after projection loss |
| T-LEDGERS | Each existing recovery command emits its ledger entry and application transition once; prior entries immutable; behavior and budgets unchanged |
| T-AUTHORITY-AST | Only application appends transition type, including alias/wrapper/dynamic-type bypass probes; only state module has state/evidence write primitives, with the unchanged diagnostic lock-metadata exception (§7.4) |
| T-BOUNDARY-AST | No phase-driven resume/recovery, future decisions/cycles/providers/Git vocabulary; no agentos_workflow or legacy workflow authority imports; event enumeration confined as §7.3 |
| T-TIER1 | Event-backed equivalents of every recorded AUTO-016 Tier-1 scenario plus AUTO-017 policy run; compare folded and published bytes after every committed step |

The four remediation tests above must meet these exact closure obligations:

- **R01:** Capture the original application outcome once for each of the four
  recovery commands, including evidence, counter changes, ledger entry and
  intended transition. Test every adjacent constituent boundary of its complete
  manifest, even a command with no budget delta. Before any constituent, no
  authoritative constituent effect may exist. Every proper applied prefix must
  expose the same complete typed declaration, intended transition, prior tip and
  applied-prefix index through load/fold. Compare all original evidence values and
  digests, not merely presence of a mutation ID. Include declaration publication
  failure, projection lag and a later invocation with changed clock/repository
  observations: none may invent/recompute the missing original evidence, report
  the prefix as complete or automatically apply missing constituents. After the
  last constituent, prove one complete mutation and exactly-once counters/ledger
  entry/transition. Include a result-acceptance multi-event mutation to prove the
  declaration rule is shared rather than recovery-command-specific. These are
  persistence tests, not AUTO-019 recovery-outcome tests.
- **R02:** Use deterministic barriers/hooks after acquisition and before each
  publication/effect boundary. A correctly held lock under root A must not
  authorize a store under root B even when repository-identity strings match.
  Replace the lock file, target-repository root, repository-scoped storage root
  and an addressed storage ancestor in separate cases. Where applicable acquire
  a fresh lock on the replacement inode to reproduce simultaneous apparent
  holders. The stale holder must fail with LOCK_OWNERSHIP_LOST before new
  canonical publication or effect entry: assert no new files/events, no writes
  to either old or replacement tree after detection, and zero provider/verification/
  Git executor calls. Test descriptor/path mismatch during confirmation and
  post-publication replacement: no successful acknowledgment or dependent effect.
  A valid second writer at the unchanged canonical root must receive ordinary
  LOCK_CONTENTION, then acquire normally after release. Release of a stale hold
  must not unlink or damage the replacement lock. No timing-only race assertions.
- **R03:** Cover an exclusive authority artifact, operation evidence, a mutation
  declaration/event, publication witness and projection. Inject directory fsync
  failure after each relevant successful link/replace; retain the visible bytes,
  discard in-memory outcomes, and retry/reload with a later valid lock holder.
  A still-failing barrier must yield PUBLICATION_UNCERTAIN and zero dependent
  effect calls, including the identical-existing branch. Then permit barriers to
  succeed and prove durability confirmation without changing artifact bytes,
  identity/timestamps, event count/ID, counters, ledger entries or mtimes. Show
  that the actual file and required directory descriptors were fsynced; a cached
  return value or equality assertion is insufficient. Missing/conflicting files
  and the R02 wrong-root/stale-lock variants still refuse; read-only reload cannot
  confer execution-ready confirmation. Confirmation of an incomplete R01 manifest
  must not apply its missing constituents. Failure before visibility separately
  proves NOT_PUBLISHED; failure after visibility must never claim that outcome.
- **R04:** Publish a pending provider row after durable prompt/request and before
  spawn, with no stdout/stderr files. Verify the row and event prefix remain valid
  with grammar/containment checks and no fabricated completion. Then publish the
  actual transcript/result bytes and their digest-bound completion/receipt
  assertions. Delete or corrupt each asserted artifact in separate variants;
  verified load/fold and effecting continuation must refuse. Include empty output
  files, an invalid digest, a historical pending-row snapshot and a mutation
  manifest carrying both prospective fields and a durable reference. Once asserted,
  evidence cannot be reclassified as prospective to make any variant pass.

Tier-1 coverage includes successful multi-milestone run, disjoint scopes,
correction/closure, open blocker stop, malformed/provider/verification failures,
scope violations, explicit recovery commands, no-op successful resume, terminal
refusals, lock contention, read-only commands, and unchanged manual Git gates.
Keep the original supervised scenarios as regression coverage. Interrupted
execution is tested for durable evidence only in ST-02; AUTO-019 owns new recovery
outcome/provider-call-count expectations and E8/E9 reproductions followed by fixes.

Before implementation edits, capture baseline v2 corpus and test collection in an
isolated checkout of `acd517ef4ea852f7f4dcab610f8c34e93a9c3ce4`, recording generator
commands, environment, fixture names, schema versions and exact-byte hashes. Do
not regenerate the frozen v1 corpus. A candidate-generated legacy fixture alone
does not prove backward compatibility.

## 13. Acceptance gates and completion evidence

All gates are required after separate implementation authorization:

1. G-1: Complete configured `pytest -q`, exit 0. D-AUTO017-02's exceptional G-1
   path was explicitly AUTO-017-only and is not inherited. A failing/hung gate
   blocks; do not weaken, skip or reclassify it as a pass without new authority.
2. G-2: All §12 tests pass with a per-test-ID evidence map, counting fakes and raw
   fault-injection results. No live provider, Hermes, Telegram or network.
3. G-3: `ruff check .`, `black --check .`, `mypy --strict`,
   `pre-commit run --all-files` and `git diff --check` pass. Whole-tree checks must
   cover new files; record any hook mutation and restore out-of-scope edits.
4. G-4: `workflowctl check-task-state --config self-governance.yaml`,
   `workflowctl check-governance --config self-governance.yaml`,
   `workflowctl check-handover --source commit --commit HEAD --config self-governance.yaml`,
   and `workflowctl verify --config self-governance.yaml` pass.
5. G-5: Baseline/candidate collection comparison preserves existing tests and
   dispositions; compatibility corpora and digest vectors pass. Run the SSP's
   collection/subsuite checks as well; current configured collection covers all
   three packages, not the SSP's historical `testpaths=["tests"]` description.
6. G-6: Exact changed-path audit matches §11; frozen authority hashes unchanged;
   transition table, ceilings, policy behavior and Git authority unchanged.
7. G-7: Disposable, test-double Tier-1 governed run produces a verified event chain
   whose fold equals `state.json` byte-identically. Preserve chain verification
   output, event count/tip, projection digest, operation artifacts and their hashes.
8. G-8: Report records publication failure matrix, atomicity limits, compatibility
   bridge evidence, no-effect replay proof and deferred recovery limitations,
   including all four remediation closure matrices in §12.
9. G-9: One bounded independent implementation review completed and every blocking
   finding closed; separate OWNER completion acceptance and registry/task closeout.

No gate authorizes implementation in this planning session. No completion report,
branch, stage authorization or runtime StageStartAuthorization is created here.

## 14. Successor boundaries and OWNER decisions

| Stage | Explicitly excluded behavior |
|---|---|
| AUTO-019 | Phase-driven resume, RecoveryReconciler, E8/E9 recovery fixes, duplicate-delivery recovery policy, new ResumeActions, OWNER_DECISION_REQUIRED, minimal PendingDecision/AMBIGUOUS_RECOVERY, automatic adoption/revalidation/application of stored results |
| AUTO-021 | OWNER Decision API, decision request/response rendering and application, extensions, KEEP_FROZEN/ABORT/AMEND semantics, SUPERSEDED, revocation/replacement of Stage Start, worktree disposition |
| AUTO-020 | Multiple remediation cycles, budget raises, cycle completion/scheduling, frozen-finding-set behavior, overflow routing, closure-scope or post-remediation-failure policy |
| AUTO-022 | Provider catalog, model dispatch/bindings, reviewer independence, model provenance, executable use of frozen roles |
| AUTO-023 | Hermes/ExecutionPort/RunEnvelope, remote idempotency/querying, adapter integration, live-provider confinement and opening the live gate |
| AUTO-024 | Authentication, attestation, principal registry, nonce consumption, expiry/revocation policy |
| AUTO-025 | Telegram notification or decision transport |
| AUTO-026 | Git operation ladder, staging/commit/push automation, Git recovery, approval-policy changes or new mutating Git argv |

The OPEN decisions OD-GSE-04, -05, -08, -09, -10 and -11 retain their named later
stage blockers. No fields, defaults, option sets or behavior decide them here.

**No new unresolved OWNER policy decision is required by this candidate.**
Primary-authority retention, the state wire revision, snapshot compatibility
bridge, integrity witness, bounded event enumeration and receipt observer are
explicit ST-02 design refinements; they do not grant new execution policy. R01–R04
add only the frozen review's mutation-evidence, continuing-lock-ownership,
durability-confirmation and reference-classification requirements. No new OWNER
choice arose. Independent closure of the frozen finding set and later OWNER
authorization are still required; this revision requests no new discovery review.

If implementation cannot satisfy a frozen constraint within this scope, stop the
affected portion and report `OWNER_DECISION_REQUIRED` with a new decision ID,
exact question, all valid options and their consequences, recommendation/rationale
and exact OWNER response syntax. Do not encode a later-stage policy to bypass it.

## 15. Traceability and planning-session completion

| Frozen requirement | Candidate coverage |
|---|---|
| Master Plan §2.1 sole authority; §2.7 INV-01 | §§4–6, T-AUTHORITY-AST |
| §2.3 events/projection; ST-02 acceptances 1–3 | §§5–7, §9, T-EVENT-CHAIN/FOLD/IDEMPOTENT/PROJECTION/TAIL |
| §2.4 phase ladder; ST-02 acceptance 4 | §8, T-OP-ORDER/SPAWN/INVALID/GAPS/APPLIED |
| ST-02 acceptance 5 | §6, T-AUTHORITY-AST |
| ST-02 atomic publication/redaction evidence | §7, T-EVENT-ATOMIC, T-REDACTION, G-7/G-8 |
| ST-02 existing-ledger events and deterministic operation ID | §§5.2/8.1, T-LEDGERS, T-OP-ID |
| AUTO-017 DO-018-1/2 | §§5.2/10.2, T-AUTHORITY |
| AUTO-017 DO-ALL-1; Master Plan schema evolution rule | §10.1, T-COMPAT, T-BASELINE-BRIDGE |
| Master Plan §3 isolation gate, §4 common checks | §§4/12/13 |
| ST-02 excludes phase-driven resume; successor boundaries | §§9/14, T-BOUNDARY-AST |

Candidate preparation finishes by running the requested diff/index/status/HEAD,
line-count, byte-count and SHA-256 checks, and reporting this file's exact identity.
That planning evidence is distinct from future implementation acceptance.

### 15.1 Frozen contract remediation traceability

| Frozen finding | Bounded remediation | Required closure evidence |
|---|---|---|
| AUTO018-CONTRACT-R01 — High / blocking | §§5–6.1: complete durable mutation declaration before constituent effects; exact manifest binding and explicit incomplete-prefix view; §9 refuses later execution without choosing recovery | T-MUTATION-PREFIX for all four existing recovery commands at every constituent boundary, plus shared acceptance-path coverage |
| AUTO018-CONTRACT-R02 — High / blocking | §§4/7.4: continuing descriptor/root/lock-inode ownership; stale holder invalidation at publication/effect boundaries; §11 narrowly admits lock.py and its test file | T-LOCK-IDENTITY with different roots, lock/root replacement and normal two-writer contention |
| AUTO018-CONTRACT-R03 — High / blocking | §§7.2/7.5/9: typed uncertain publication, locked durability confirmation for retries/reloads, no content/identity rewrite or execution on visibility alone | T-PUBLICATION-UNCERTAIN after successful link/replace and failed directory fsync, across later invocations |
| AUTO018-CONTRACT-R04 — Medium / non-blocking | §§5.2/7.2/8.3/10: prospective legacy path declarations distinguished from digest-bound published evidence; precise assertion/validation boundaries | T-PROSPECTIVE-REFERENCE with valid absent pre-spawn outputs and refused missing/corrupt asserted evidence |

This table is an author-reported remediation map, not independent closure. The
finding set is exactly AUTO018-CONTRACT-R01 through AUTO018-CONTRACT-R04; no new
finding IDs or discovery results are introduced. No implementation tests were
written or run by this document-only remediation. Frozen AUTO-017 and the Master
Plan remain byte-unchanged; all successor-stage exclusions remain in force.

AUTO-018 remains `NOT_STARTED` / `Planned` / implementation unauthorized.
Nothing in this document authorizes staging, commit, push or any successor stage.
