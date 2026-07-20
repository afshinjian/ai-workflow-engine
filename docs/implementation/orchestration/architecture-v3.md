# Autonomous Workflow Orchestration — Architecture v3

Status: proposed; gated by independent review of `ORCH-000`  
Feature: `ORCH`  
Architecture version: `3.0.0`

## 1. Executive summary

V3 retains the useful hybrid boundary: the engine owns normative primitives and
evidence; a separate orchestrator consumes only a versioned `workflowctl` JSON
contract and applies deterministic routing policy. The orchestrator cannot
manufacture history, order patches, mutate governance directly, approve an
operation, or run agents from a dirty target.

Every task execution is a first-class attempt bound to one committed base HEAD,
governance revision and immutable approved execution specification. Candidate
patches form an engine-derived chain inside that epoch. A prerequisite commit
supersedes the parent attempt; the parent starts a new attempt and plan review
at the new HEAD. V3 intentionally does not rebase old candidates.

Governance changes are external candidates until a locked, validated,
approval-bound apply-and-commit transaction publishes them. Cryptographically
enforced autonomous operation requires Ed25519 approvals verified and replay
protected outside the orchestrator's OS authority.

## 2. V2 findings disposition

| V2 issue/assumption | Disposition and v3 result |
|---|---|
| Reviews could not see candidates | Accepted: deterministic synthetic chain baselines. |
| CLI lacked agent outcomes | Accepted: contract v2 `agent-run show`. |
| Integrity and domain outcome were conflated | Accepted: independent values and gates. |
| Routing covered mainly verdicts | Accepted: complete stage/publication/terminal table. |
| A graph store could own dependencies | Rejected: task records remain authoritative. |
| Prerequisites could be automatic despite promotion approval | Corrected: proposal is automatic; signed promotion activates it. |
| Stage alone could attribute failure | Rejected: normalized baseline/candidate delta is primary. |
| Approval could remain abstract/policy based | Rejected: concrete signature and capability protocol. |
| Existing transition table could remain untouched | Rejected: attempt identity and closeout outcomes require v2 events/transitions. |
| Candidate chains could survive prerequisite HEAD changes | Rejected: supersede and restart; no implicit rebase. |
| Task commands could edit queue directly | Rejected: external mutation plus atomic commit. |
| O_EXCL/hard links could publish mutable documents | Rejected: journaled multi-document transaction. |

## 3. Component and authority model

| Component | Classification | Authority/responsibility |
|---|---|---|
| Governed Git documents | Normative, authoritative | Declared task status, dependencies, current task and mirrors. |
| Attempt/workflow event store | Normative, authoritative evidence | Append-only execution and stage history. |
| Committed execution spec | Normative, authoritative | Approved immutable task execution constraints. |
| Candidate/mutation/application records | Normative evidence | Content-addressed bytes and receipts. |
| Approval service/replay ledger | Normative trust authority | Verify and consume capabilities. |
| `workflowctl` | Normative write surface | Validate, derive, record, publish and recover. |
| Decision policy | Normative routing | Map verified fact digests to one permitted action. |
| Separate orchestrator | Derived controller | Invoke contract-v2 operations; no imports/direct stores/Git. |
| Baseline cache | Derived, cached | Optimization only when complete identity is proven. |
| Agent prose/summaries | Advisory | Explanation only; never transition input. |
| This package | Normative for feature delivery only | Cross-session implementation progress, not runtime task authority. |

`TASK_QUEUE.md` declares tasks and dependencies. Attempt records prove execution.
`task show` may combine them, but disagreement produces `INCONSISTENT` and stops.

All new identities are SHA-256 of RFC 8785 canonical JSON UTF-8 bytes. Every
record has `schema_name` and `schema_version`. Audit timestamps are excluded from
identity unless explicitly listed. Repository identity is the digest of the
verified canonical remote URL and default branch. Autonomous mode is unavailable
when repository identity cannot be proven. Governance revision is the digest of
the ordered authoritative-path/digest manifest at a committed HEAD.

## 4. Task attempts and base-HEAD epochs

`AttemptRecord` v1 contains:

```yaml
schema_name: attempt-record
schema_version: 1.0.0
project_id: string
repository_id: sha256
task_id: string
attempt_id: string
sequence: integer
base_head: git_oid
governance_revision: sha256
execution_spec_path: repo_relative_path
execution_spec_digest: sha256
candidate_chain: [agent_run_id]
candidate_digest: sha256|null
status: ACTIVE|BLOCKED|SUPERSEDED|SUCCEEDED|FAILED|CANCELLED
prerequisite_ids: [task_id]
created_at: rfc3339
superseded_by: attempt_id|null
terminal_reason: {code: string, detail: string}|null
```

`attempt_id` hashes project, task, locked sequence, base HEAD, governance
revision and spec digest; `created_at` is audit-only. Histories are keyed by
`(project, task, attempt)`.

After a prerequisite commit, the parent's active attempt becomes `SUPERSEDED`
with `PREREQUISITE_CHANGED_HEAD`; its candidate remains immutable audit evidence
but is ineligible. When all prerequisites succeed, an approved governance
mutation unblocks the parent and creates a new attempt at clean current HEAD.
That attempt restarts at plan review. Rebase is a future, separately approved
feature that would still create a new attempt and require complete re-review.

## 5. Immutable execution specification

Promotion commits an `ExecutionSpec` v1 and records its digest on the task:

```yaml
schema_name: execution-spec
schema_version: 1.0.0
project_id: string
repository_id: sha256
task_id: string
risk: LOW|MEDIUM|HIGH|CRITICAL
recipe: {id: string, version: semver}
allowed_paths: [normalized/repository/relative/path-or-prefix]
agents:
  plan-review: {primary: agent-id, fallback: []}
  implementation: {primary: agent-id, fallback: []}
  implementation-review: {primary: agent-id, fallback: []}
  remediation: {primary: agent-id, fallback: []}
  governance-closeout: {primary: agent-id, fallback: []}
  governance-review: {primary: agent-id, fallback: []}
verification_profile: {id: string, schema_version: semver, digest: sha256}
round_limits:
  plan_review: integer
  implementation_review: integer
  remediation: integer
  governance_review: integer
timeouts:
  agent_seconds: integer
  verification_seconds: integer
  orchestration_seconds: integer
prerequisite_policy: {maximum_depth: integer, maximum_fan_out: integer}
base_head: git_oid
governance_revision: sha256
protected_policy_digest: sha256
```

Every field is required. `task propose` may materialize policy defaults before
digest/approval; execution has no implicit defaults. Paths are NFC-normalized
POSIX relative paths. Empty/absolute/`..` paths, symlink escape, case collision
and protected-path overlap are rejected. A trailing `/` alone denotes prefix
semantics; otherwise a path is exact.

Fallback is forbidden unless its signed ordered list exists. The first healthy
listed agent is selected and health evidence is recorded. Any post-promotion
field change needs a new spec, renewed approval and new attempt. Spec, attempt,
governance revision and candidate identity enter PromptContext v2 and prompt ID.

## 6. Candidate chain and exact sandbox baseline

The engine derives order solely from accepted attempt workflow events. Each
member must bind the same task/attempt/spec/base, have integrity `PASS`, valid
patch/manifest digests, an allowed contributing stage and
`parent_candidate_digest` equal to the preceding chain digest (null first).
Paths are checked per member and in aggregate. Gaps, branches, duplicates,
superseded attempts and caller-supplied ordering are rejected.

For implementation review, remediation and governance stages the engine:

1. creates an isolated clone/worktree detached at `base_head`;
2. verifies then applies each derived patch using `git apply --check --binary`
   followed by `git apply --binary`;
3. runs `git add -A` and `git write-tree`;
4. creates a sandbox-only `git commit-tree` with parent `base_head`, fixed
   identity `AI Workflow Engine <engine@invalid>`, timestamp
   `2000-01-01T00:00:00Z`, and candidate-digest message;
5. checks out that synthetic commit detached and verifies it clean;
6. records synthetic commit/tree as `chain_baseline`.

No target ref receives the synthetic object and it cannot be fetched/pushed;
sandbox deletion removes it. The next contribution is produced after `git add
-A` as `git diff --cached --binary --full-index --no-renames
<synthetic-commit>`. Paths use `--name-status -z --no-renames`; a rename is
deliberately delete+add. Untracked files, deletions, executable bits and binaries
are included. Symlinks are ownership-checked without following them; submodule
and special-file changes are rejected initially. Thus remediation remains a
separate patch owned by its run, relative to all prior accepted work.

Patch continuity is verified both by parent digest and by reconstructing the
recorded result tree after every member.

## 7. Aggregate candidate application

`workflowctl candidate apply --task ID --attempt ID --output json` accepts no
run list. Under the repository lock it:

1. derives and verifies all accepted chain members;
2. reconstructs from base in isolation;
3. computes one base-to-final binary/full-index/no-renames patch and final tree;
4. writes `CandidateRecord` v1 with base, attempt, ordered members, chain,
   aggregate patch and tree digests, and normalized applied paths;
5. rechecks aggregate allowed/protected paths and dry-runs on the target;
6. requires exact clean base HEAD, governance/spec digests and no open journal;
7. fsyncs an `ApplicationRecord` as `PREPARED`, applies exactly once, verifies
   exact target fingerprint and advances it atomically to `APPLIED`.

The record is external. The target is intentionally dirty only until the
separately approved candidate commit; agents and governance mutations are
forbidden in this publication window.

Idempotency key is repository/attempt/candidate digest. A retry returns the same
receipt if `APPLIED` and target fingerprint is exact, returns `COMMITTED` for the
recorded current/reachable commit, and otherwise refuses stale, partial or
different state. It never reapplies. Abort requires an approval and exact
journal/preimage restoration; ambiguity quarantines the repository.

## 8. Clean-tree-safe governance mutation

Pending mutations are immutable external directories:

`governance-mutations/<project-id>/<mutation-id>/`

They contain canonical mutation JSON, complete proposed document bytes,
validation/review evidence and approvals. The ID hashes expected HEAD and
governance revision, operation, all input/output document digests, exact task,
spec and dependency fields, and policy version. A pending mutation has no task
authority.

`task propose|promote|block|complete` constructs a mutation in an isolated
worktree at expected HEAD, renders the complete governed set, round-trip parses
it, runs governance and cross-document validators and records evidence.
Proposal is consequence-free and may be automatic. Promotion, unblock,
completion intent and configured consequential changes require an approval
bound to the exact mutation digest.

The governed set is resolved from configuration and always includes
`docs/TASK_QUEUE.md`, `docs/current_task.md`, every configured governance mirror
(currently `docs/PROJECT_STATE.md`, `docs/remaining_tasks.md` and
`docs/CONTEXT.md` when affected), and configured generated manifests including
`handover/PROJECT_CHECKSUM.md`. The mutation records why each configured path is
changed or proves its output digest is unchanged; callers cannot omit a member.

`governance-mutation commit` is the sole publisher. It requires exact clean
HEAD/index/input/governance digests, valid unconsumed approval, no other
publication/recovery, validates again, performs section 9's transaction, stages
only declared paths, creates a commit with mutation/approval trailers, verifies
clean committed result, consumes approval and records a receipt. Agents resume
only at that committed HEAD. Any stale binding requires regeneration.

## 9. Transactional governance publication

All engine writers take an exclusive advisory lock on an engine-owned file keyed
by canonical repository identity. Metadata records PID, process-start identity,
operation and transaction. Concurrent writers are rejected. A dead lock may be
broken only after process and journal inspection.

Before touching Git, the engine fsyncs an external recovery journal containing
transaction ID, expected HEAD/index, paths, input/output digests, exact preimage
bytes/modes, temp paths and phase. It then:

1. writes same-directory temporary files, fsyncs them, and validates the whole
   temporary set and cross-document invariants;
2. marks/fsyncs `PREPARED`;
3. publishes each file with same-filesystem `os.replace`, fsyncing directories
   and a journal replacement bitmap;
4. validates the published set, stages exact paths and verifies staged tree;
5. commits, verifies commit tree/trailers/governance and a clean worktree;
6. records receipt and `COMMITTED`, then `FINALIZED`.

POSIX has no atomic multi-file-plus-Git primitive. V3 explicitly uses atomic
per-file replacement, a recovery journal and the Git commit as the durable
visibility boundary. No engine operation proceeds with an unfinalized journal.

Recovery reacquires the lock and compares exact journal, HEAD, index and files.
Before commit it restores all preimages and the originally clean index and marks
`ROLLED_BACK`. After an exact matching commit it finalizes. Mismatched commits,
overlapping user edits or unprovable restoration require human resolution and
remain quarantined. Hook rejection rolls back only when exact restoration is
provable. Unsupported filesystem/fsync semantics disable autonomous writing.

## 10. Authoritative dependency model

Dependency fields live in authoritative task records:

```text
Status: Blocked
Blocked by: [T-401, T-402]
Active attempt: null
Execution spec: <repo-relative path>
Execution spec digest: <sha256>
Terminal reason: null
```

The parent is blocked by its prerequisites. The canonical sorted list may have
zero or multiple unique existing IDs. Self, missing, duplicate and cyclic edges
are rejected. Graph depth and fan-out must satisfy repository policy and the
signed spec.

Discovery creates one atomic mutation adding proposed prerequisite(s) and
blocking the parent. Applying a signed promotion may make one prerequisite
`Current`, preserving `maximum_current_tasks`. Repeated discovery is deduplicated
by `{parent, recipe, normalized finding IDs, scope}`. An existing non-terminal
match is reused; a failed/cancelled match needs a new explicit proposal.

A prerequisite is satisfied only when the authoritative task is `Done` and a
successful terminal attempt plus push receipt agree. All prerequisites must be
satisfied before an unblock/new-attempt mutation. Failed/cancelled children keep
the parent blocked and require human cancellation, replacement or dependency
change; they never unblock it.

## 11. Integrity, outcome and attribution

Integrity and domain outcome are independent:

```yaml
integrity: PASS|FAIL|UNVERIFIABLE
outcome: PASS|FAIL|BLOCKED|NO_CHANGE|ENVIRONMENT_ERROR|AMBIGUOUS
```

Integrity other than `PASS` prevents recording/routing. Honest failing tests are
integrity `PASS`, outcome `FAIL`.

Baseline and candidate finding sets use stable profile/check/finding IDs,
severity, normalized location/message digest and evidence pointer. Delta classes
are: both empty `PASS`; identical failures `PRE_EXISTING`; candidate-only new
failures `INTRODUCED`; removed baseline plus distinct candidate failures
`DIFFERENT`; unreliable mapping `AMBIGUOUS`; command/fingerprint failure
`ENVIRONMENT_ERROR`. Exact Tier-B findings are mandatory for automatic
prerequisite creation. Coarse Tier-A pass/fail evidence routes `AMBIGUOUS` for
human classification.

## 12. Safe baseline cache

The cache identity hashes project/repository, HEAD, governance revision,
verification-profile schema/digest/exact argv arrays, relevant configuration,
OS/release/architecture/filesystem flags, runtime, dependency-lock digests,
environment package fingerprint, tool executable identities/versions and all
declared affecting environment variables/locale/timezone.

Entries contain full key material and result/evidence integrity digests, all
recomputed on read. Unknown fingerprints, mutable remote dependencies,
undeclared inputs, non-hermetic commands, unsupported tools or profile opt-out
disable persistent caching and run fresh. Any key change invalidates. TTL can
shorten but not extend validity. Cache is derived evidence, never authority.

## 13. Approval signature and trust protocol

Cryptographic mode uses detached Ed25519 over RFC 8785 canonical JSON
`signed_payload`. `signature` and verifier attestation are excluded.

```yaml
schema_name: approval-envelope
schema_version: 2.0.0
signed_payload:
  approval_id: sha256-of-payload-with-approval_id-omitted
  approval_kind: TASK_PROMOTION|GOVERNANCE_MUTATION|CANDIDATE_COMMIT|PUSH|ABORT
  project_id: string
  repository_id: sha256
  task_id: string
  attempt_id: string|null
  authorized_operation: exact-operation
  authorized_fields: {operation-specific exact object}
  governance_mutation_digest: sha256|null
  candidate_digest: sha256|null
  expected_head: git_oid
  expected_governance_revision: sha256
  key_id: string
  nonce: base64url-128-random-bits
  issued_at: rfc3339
  expires_at: rfc3339
signature: {algorithm: Ed25519, value: base64url}
```

The verifier recomputes ID; validates every binding, maximum lifetime/skew, key
purpose/status and signature; then atomically consumes
`(key_id, nonce, approval_id)`. Replay, unknown/revoked/inactive/wrong-purpose
key, encoding/signature/time/digest/HEAD/repository/operation mismatch or
unavailable ledger are distinct fail-closed errors.

The versioned trust store records public key, purpose, activation/retirement and
revocation. Rotation may overlap keys; new signing uses the new key. Revocation
blocks unconsumed approvals. Historical consumed approvals retain trust-store
digest and verification attestation.

`authorized_fields` is closed by approval kind:

| Approval kind | Exact authorized fields |
|---|---|
| TASK_PROMOTION | `mutation_id`, proposed task status, execution-spec path/digest, prerequisite IDs, resulting current-task ID, commit-message digest |
| GOVERNANCE_MUTATION | `mutation_id`, mutation operation, ordered output path/digest list, resulting governance revision, commit-message digest |
| CANDIDATE_COMMIT | `application_id`, candidate/final-tree digest, ordered applied paths, exact commit-message digest, author identity, target branch |
| PUSH | commit OID, canonical remote URL digest, exact refspec, expected pre-push remote OID, `force: false` |
| ABORT | `application_id`, candidate digest, expected dirty fingerprint, exact clean restoration fingerprint |

Extra or missing fields reject the envelope. Approval is consumed immediately
before its authorized side effect. Failure before a proved side effect requires
a new approval; a lost response after success is recovered from the matching
journal/receipt and never consumes a second approval.

Genuine non-forgeability requires the orchestrator/agents cannot read private
keys, alter trust keys or edit replay state. `approvald` therefore runs as a
different privileged OS account, owns protected trust configuration and a
transactional SQLite-WAL replay/audit DB, and exposes an authenticated Unix
socket. Human signing uses a separate account/token. Same-user storage provides
key authentication but no meaningful orchestrator capability boundary.

`TRUSTED_LOCAL` reads legacy approvals for manual compatibility only and cannot
enable autonomous promotion, governance publication, commit, push or abort.
`CRYPTO_ENFORCED`, isolated healthy `approvald`, and verified repository identity
are mandatory for `orchestratorctl enable --write`.

## 14. Schema, migration and CLI versioning

| Contract/artifact | New version |
|---|---|
| PromptContext/PromptMetadata | 2.0.0 |
| AgentRunRecord, VerificationRecord | 2.0.0 |
| WorkflowEvent/WorkflowState | 2.0.0 |
| TaskRecord, ApprovalEnvelope | 2.0.0 |
| ExecutionSpec, AttemptRecord | 1.0.0 |
| Candidate/ApplicationRecord | 1.0.0 |
| GovernanceMutation/Journal | 1.0.0 |
| BaselineCacheRecord | 1.0.0 |
| CLI JSON contract | 2.0.0 |

Contract v2 has `{contract_version, command, ok, data, error, warnings}`; errors
have stable code/message/retryable/details. The orchestrator pins a supported
major. Existing commands may explicitly request v1 during deprecation; new
orchestration writers are v2 only. Writers emit only newest schema; there is no
mixed-schema write mode.

Legacy terminal artifacts remain byte-preserved, readable and auditable. Legacy
approvals never authorize v2. An active legacy workflow cannot accept v2 events;
migration creates a signed new attempt at current HEAD linked by `migrated_from`
and excludes old candidates. Unknown/corrupt artifacts are quarantined.

`workflowctl migrate inspect|plan|apply --to VERSION --output json` supports
`--dry-run`. Apply requires clean state/lock/preflight, content-addressed
external backup and recovery journal. Migration is additive and never deletes
legacy evidence. Rollback is allowed only before a new-schema write; afterwards
recovery is forward-only. Mixed-version writers disable autonomy.

## 15. Complete workflow and terminal lifecycle

The per-attempt transition table changes as follows:

| Stage | Verified outcome | Next action |
|---|---|---|
| none | active attempt | plan-review |
| plan-review | APPROVED | implementation |
| plan-review | rejected plan defect | new plan-review round within limit |
| any pre-publication | exact pre-existing blocker | prerequisite flow; supersede after commit |
| implementation | completed valid contribution | implementation-review |
| implementation | failed/blocked | attribute then remediation/prerequisite/retry/block |
| implementation-review | APPROVED | governance-closeout |
| implementation-review | introduced/different task defect | remediation |
| remediation | completed contribution | implementation-review |
| governance-closeout | READY | governance-review |
| governance-closeout | NOT_READY, in-scope | remediation |
| governance-review | APPROVED | apply final candidate |
| governance-review | REJECTED | remediation |
| publication | candidate + commit approval | commit exact candidate |
| publication | commit + push approval | push exact commit |
| push | verified push receipt | record `push --completed` |
| push completed | all task projections/evidence agree | complete task; evaluate dependents |

Governance closeout has no verdict. It is `READY` only when a deterministic
profile proves required governance/project/handover/manifest candidate documents,
cross-document invariants, mandatory evidence, no blockers and intended terminal
task/dependency projection. Otherwise it is `NOT_READY`; blockers prevent its
completion event. Governance review evaluates the entire reconstructed final
candidate, evidence, scope, protected paths and terminal projection and binds
approval to its exact digest.

Successful terminal sequence is strictly:

1. governance-review approval for final candidate;
2. aggregate application to exact clean base HEAD;
3. verified application receipt;
4. human `CANDIDATE_COMMIT` approval bound to candidate/HEAD/attempt/message;
5. exact commit and clean commit receipt;
6. human `PUSH` approval bound to commit/remote/refspec;
7. push and remote-OID-verified `PushReceipt`;
8. `state record --stage push --completed` citing receipt;
9. `task complete` verifies committed `Done` projection, successful attempt and
   commit/push/evidence consistency, then marks external attempt `SUCCEEDED`;
10. propose eligible dependent unblocks/new attempts.

The reviewed candidate contains the terminal governance/dependency projection.
After commit and before verified push/completion the derived state is
`PUBLISHING`; all new work is refused. `task complete` never writes the repo and
refuses wrong/dirty HEAD, non-Done projection, blockers, absent/mismatched
receipts or unpushed commit. Failed/cancelled attempts use signed governance
projections and terminal reasons and never unblock parents. `BLOCKED` is not
terminal.

## 16. Engine and orchestrator contracts

Required contract-v2 operations include:

- `task show|propose|promote|block|complete`
- `attempt show|start|supersede`
- `agent-run show --run-id ID`
- `candidate show|verify|apply|abort --attempt ID`
- `governance-mutation show|verify|commit|recover`
- `approval verify --approval ID --consume-for OP`
- `baseline run|show --profile ID`
- `decision evaluate --attempt ID`
- `state record --attempt ID --stage STAGE --outcome OUTCOME`
- `migrate inspect|plan|apply`

All support JSON; mutations support dry-run. `agent-run show` returns findings,
blockers, summary, integrity/outcome, verification/baseline evidence, prompt,
spec, attempt, chain baseline, contribution and candidate identities. Prose is
not parsed. No API accepts patch order, caller-selected next stage, unverified
outcome JSON or free-form approver. Unknown fields in mutating/signed input fail.

`orchestratorctl` is a separate process/package. It imports no engine internals,
opens no stores and calls no Git. It pins CLI/policy versions, keeps only a
derived cursor reconstructible from engine facts, invokes one action, and waits
for its receipt. Agents lack target Git credentials and approval keys.

## 17. Complete deterministic decision table

Decision outputs are `RUN_STAGE`, `RETRY_STAGE`, `PROPOSE_PREREQUISITE`,
`REQUEST_APPROVAL`, `APPLY_CANDIDATE`, `COMMIT_CANDIDATE`, `PUSH`,
`COMPLETE_TASK`, `WAIT`, or `BLOCK`, with policy/fact digests, reason and exact
command. The engine rechecks it; a decision is not a capability.

| Verified facts | Action |
|---|---|
| Integrity/schema/evidence not valid | BLOCK `UNTRUSTED_EVIDENCE` |
| Environment error, stable fingerprint and retry remains | RETRY same stage |
| Persistent/changed environment | BLOCK `ENVIRONMENT` |
| Ambiguous or coarse attribution | BLOCK for human classification |
| Plan approved | RUN implementation |
| Plan defect and rounds remain | RETRY plan-review |
| Exact pre-existing blocker | PROPOSE_PREREQUISITE |
| Implementation valid contribution | RUN implementation-review |
| Introduced/different task-owned defect | RUN remediation within limit |
| Implementation review approved | RUN governance-closeout |
| Remediation contribution complete | RUN implementation-review |
| Any round limit exhausted | BLOCK `ROUND_LIMIT` |
| Closeout READY | RUN governance-review |
| Closeout NOT_READY but in-scope | RUN remediation |
| Governance review rejected | RUN remediation |
| Governance review approved | APPLY_CANDIDATE |
| Applied candidate lacks commit approval | REQUEST_APPROVAL `CANDIDATE_COMMIT` |
| Valid consumed commit approval | COMMIT_CANDIDATE |
| Commit lacks push approval | REQUEST_APPROVAL `PUSH` |
| Valid consumed push approval | PUSH |
| Push receipt | record push complete, then COMPLETE_TASK |
| Successful prerequisite and all siblings successful | propose parent unblock/new attempt |
| Failed/cancelled prerequisite | BLOCK parent |
| Exact idempotent receipt/already completed | WAIT/return receipt |

Limits come only from the signed spec. Multiple/no matching actions or policy
version mismatch is `BLOCK`, never guessed priority.

## 18. Backward compatibility and fail-closed behavior

V3 is not write-compatible with active v1 histories, approvals or prompt/run
schemas. Manual v1 behavior can exist during a bounded compatibility release;
autonomy requires v2 attempts. Existing task Markdown gains fields through a
validated migration mutation; missing fields are not silently defaulted later.
Old clients receive v1 shapes only for old operations. Contract-major mismatch,
unsupported schemas, partial migration or mixed writers quarantines autonomy.

All writers require exact HEAD, governance revision, schema/policy, lock and
known clean/publication state. Missing/malformed state, dirty tree outside an
exact application receipt, stale/missing evidence, absent approval, inconsistent
mirrors, recovery journal, concurrency, partial application, unknown environment
or ambiguous attribution stops and records a blocker. Success is never inferred
from prose, exit code, file existence, cache, commit alone or push exit alone.

## 19. Risk register

| Risk | Severity | Control/gate |
|---|---|---|
| Crash during document/Git publication | Critical | Journal, preimages, quarantine and crash-injection tests. |
| Orchestrator compromises approvals | Critical | Separate account/service/key; autonomy refuses weak isolation. |
| Markdown round trip loses data | High | Strict parser/canonical renderer/golden full-set tests. |
| Git-version patch variance | High | Record Git identity and verify final tree. |
| Misattributed failure | High | Stable finding IDs; coarse evidence cannot automate. |
| Prerequisite explosion/deadlock | High | Depth/fan-out/round limits, dedupe, human promotion. |
| External evidence loss/tampering | High | Hash chains, integrity scans and backups; WORM future option. |
| Mixed legacy writers | High | Contract pinning, migration marker, quarantine. |
| Feature implementation self-approval | High | Role-separated durable state/review evidence. |
| Unsupported filesystem semantics | High | Capability preflight disables writers. |

## 20. Implementation-readiness invariants

This architecture is ready for independent plan review, not production work.
`ORCH-000` must approve it before the staged plan is eligible. Initial non-goals
are candidate rebase, distributed orchestration, non-Git repositories, arbitrary
shell verification, submodule mutation and autonomous ambiguous classification.

Final invariants:

1. Agents start only from a clean committed target.
2. Attempts/candidates never cross base-HEAD epochs.
3. Chain order comes only from verified history.
4. Integrity PASS precedes outcome routing.
5. Task/dependency declarations have one authority.
6. Governance publication ends verified or quarantined.
7. Consequential approvals bind exact identities/digests and are single-use.
8. Autonomous writes require a genuine capability boundary.
9. Implementation and independent approval roles differ.
10. Missing, stale, inconsistent or ambiguous evidence always stops.
