# T-405 Task Contract — Governed First Publication of an Absent Remote Branch

Status: DONE — DEFERRED/CLOSED WITHOUT IMPLEMENTATION BY HUMAN OWNER DECISION, RATIFIED
2026-09-02; THIS CONTRACT AND ALL REVIEW FINDINGS ARE RETAINED AS HISTORICAL TRUST-BOUNDARY
EVIDENCE

Review-evidence status: `UNVERIFIABLE — no preserved independent-review artifact was located.`
The technical analysis in this contract stands on its own merits and is retained in full; but every
claim below that a *fresh independent plan review* occurred, returned a verdict, or closed a
finding is the authoring session's own account, not verified fact. See section 17.

Human Owner ruling date: 2026-08-19

**Supersession notice:** Section 16 records the final Human Owner disposition and supersedes every
earlier implementation/readiness direction in this historical contract. Section 17 records the
2026-09-02 Human Owner ratification, the contract's verified evidence status, and the supersession
of section 16's cross-repository operator sequence. T-405 must not be implemented or submitted for
another plan review.

## 1. Ownership and relationship to completed work

T-405 is a new ordinary Milestone 4 remediation task linked to T-403. T-403 remains `Done`; its
record, implementation history, and approved existing-upstream behavior must not be reopened or
rewritten. T-405 corrects only the missing governed bootstrap path for first publication of an
approved local branch whose intended tracking target is configured but whose exact remote branch
does not yet exist.

The repository has no task-ID allocator. `docs/MASTER_ROADMAP.md` defines the
`T-<milestone><nn>` namespace, controlled push belongs to Milestone 4, and T-401 through T-404 are
the existing contiguous Milestone 4 tasks. T-405 is therefore the next unused canonical ID in the
owning task family.

## 2. Human Owner policy ruling

The binding concurrency rule is:

> The approved remote branch may be created only if the exact destination ref still does not exist
> at update time.

For this bounded operation only, the Human Owner permits Git's zero-expected-OID creation
compare-and-swap mechanism equivalent to:

```text
--force-with-lease=<exact-approved-remote-ref>:
```

This is authority for one narrowly typed **create-only** primitive. It is not authority for a
generic force or lease surface. The engine must construct the empty-expectation lease and the
single explicit refspec internally. Its source is the immutable commit OID taken only from the
already validated `approval.head`; its destination is the exact `refs/heads/*` merge target taken
only from independently validated structured tracking data; and its transport operand is the one
immutable effective push endpoint derived from the configured remote before inspection. The same
endpoint value must be used directly for pre-write inspection, mutation, and post-write
inspection. No caller may provide a source ref, an independent commit OID, a remote symbolic name,
a push-URL list, a lease expression, refspec, unvalidated destination ref, force flag, arbitrary
expected OID, config override, or deletion spelling.

The ruling does not authorize general force push, force-with-lease against an existing ref,
arbitrary leases, caller-supplied lease expressions, arbitrary refspecs, branch overwrite, branch
deletion, non-fast-forward update, automatic remote creation, or unattended approval. If the
destination ref appears at any SHA between authoritative inspection and publication, the operation
must report failure, must not modify that ref, and must require re-evaluation from authoritative
remote state. A process exit of zero or an "up to date" response is not proof that this operation
created the ref. One symbolic remote must never expand this primitive to multiple endpoints, and
ambient Git configuration must never add a tag, submodule push, other ref, or other repository to
the operation.

After the one remote create CAS has been authoritatively verified, T-405 additionally authorizes
one fixed-shape **local tracking materialization** operation. It may fetch only the approved exact
remote head from the same frozen endpoint into the one validated local
`refs/remotes/<approved-remote>/<approved-branch>` ref required by the existing configured tracking
relationship. This is local Git metadata/ref authority only: it grants no second remote write, no
generic fetch/synchronization API, no tag or submodule fetch, no configured-refspec expansion, no
worktree/index mutation, and no mutation of another local ref.

## 3. Objective

Extend `workflowctl push` with an explicit approval-bound first-publication path while preserving
the T-403 existing-upstream path exactly. The new path alone must use authoritative effective-
repository pre/post verification. It may create exactly one absent `refs/heads/*`
destination at the single effective push endpoint derived from the approved configured remote,
publish exactly the approved local branch at the approved HEAD, establish and verify the approved
tracking relationship through the one narrow local materialization operation, independently verify
the authoritative remote and local tracking SHAs at the approved HEAD, and only then return a
successful push result eligible for a separate workflow `push` completion record. T-405 adds no
post-push query, endpoint resolution, or tracking materialization to the legacy T-403 path.

## 4. Entry conditions and approval contract

The `PushApproval` model gains exactly one additive, field-locally strict authority field. An
implementation equivalent to the repository's installed Pydantic version is:

```python
from pydantic import StrictBool

create_remote_ref: StrictBool = False
```

`Field(strict=True)` or another equally strict field-local declaration is acceptable if it is
compatible with the installed Pydantic version. Changing unrelated approval fields or globally
changing `StrictModel` is not acceptable. Omission and literal boolean `false` preserve T-403
behavior and existing approval artifacts that omit the field remain valid. Only literal boolean
`true` selects the first-publication path. The YAML values `"true"`, `"false"`, `1`, and `0` must
all be rejected as invalid approvals rather than coerced. The approval must continue to bind the
normalized task ID, exact local branch, exact live HEAD, exact approved upstream target, and human
approver. No remote URL digest redesign is part of T-405.

Before any remote write, the gate must prove all of the following:

1. the approval artifact is structurally valid and its digest is captured using the existing
   approval-integrity path;
2. live branch equals the approved local branch;
3. the approved local branch and live HEAD both resolve to the approved commit OID;
4. the worktree and index are clean and there are no untracked files;
5. the local branch has structured tracking configuration, read independently of whether
   `@{upstream}` resolves;
6. the configured remote name and configured merge ref identify exactly the approved remote and
   `refs/heads/*` destination;
7. the configured remote's complete fetch-URL and push-URL value sets are read without silently
   selecting a first value, and exactly one effective push endpoint is derived by the rules below;
8. the endpoint has an accepted direct form and the effective Git configuration contains no
   `url.*.insteadOf` or `url.*.pushInsteadOf` rule; any such rule is a fail-closed refusal rather
   than an invitation to reproduce Git's rewrite algorithm;
9. the configured remote has exactly one fetch mapping and it is byte-for-byte the canonical
   `+refs/heads/*:refs/remotes/<validated-remote-name>/*` mapping. Applying that mapping to the
   approved exact `refs/heads/<branch-tail>` yields the exact validated
   `refs/remotes/<validated-remote-name>/<branch-tail>` represented by the approved upstream and
   sole permitted local metadata destination;
10. any non-empty effective `fetch.bundleURI` is rejected before the remote CAS because installed
    Git can contact that second repository before an ordinary fetch; and
11. the derived effective endpoint is frozen as a validated value that will not be re-resolved from
   the symbolic remote during inspection or mutation; and
12. an authoritative exact-ref query to that exact effective endpoint proves the approved
   destination is absent, with absence distinguished from transport/authentication/protocol
   failure and from
   malformed, duplicate, ambiguous, or unexpected output.

The implementation must not parse the display form `origin/branch` by splitting user-controlled
text and must not treat failure to resolve `@{upstream}` as proof of remote absence.

Effective endpoint derivation is deterministic and fail-closed:

- exactly one explicit `remote.<name>.pushurl` value makes that value the effective push endpoint;
- no `pushurl` plus exactly one `remote.<name>.url` value makes that ordinary URL the effective
  push endpoint;
- multiple `pushurl` values are `MULTIPLE_PUSH_ENDPOINTS` / no-write FAIL;
- no `pushurl` plus multiple ordinary URL values are `MULTIPLE_FALLBACK_URLS` / no-write FAIL;
- no usable value is `NO_EFFECTIVE_ENDPOINT` / no-write FAIL; and
- unreadable, syntactically invalid, or otherwise untrustworthy remote configuration is
  `REMOTE_CONFIGURATION_ERROR` and no write may occur. Repeated URL values still count as multiple
  configured values and must never be silently de-duplicated into a single endpoint.

This internal endpoint resolution does not add a URL or URL digest to `PushApproval`. Human
approval remains bound through the existing upstream/tracking contract. It only prevents Git's
symbolic remote expansion from changing which repository is inspected or written.

`ValidatedPushEndpoint` accepts only implementation-verifiable direct forms: absolute filesystem
paths and `file://`, `ssh://`, `git://`, `http://`, or `https://` URLs with no NUL, control
character, newline, or option spelling. Relative paths, scp-like shorthand, strings that can name a
configured remote, custom remote-helper forms such as `<helper>::<address>`, `ext::`, and every
unrecognized scheme are `ENDPOINT_FORM_REJECTED` / no-write FAIL. Supporting another transport
form requires separate Human Owner authority.

For T-405 first publication, any configured `url.*.insteadOf` or `url.*.pushInsteadOf` entry in the
effective system, global, local, worktree, command, or environment configuration is rejected before
remote inspection, whether or not the engine believes it matches. This deliberately avoids
implementing or racing Git's rewrite-selection algorithm. The fixed inspection, publication, and
materialization subprocess envelope also sets `GIT_CONFIG_SYSTEM=/dev/null`,
`GIT_CONFIG_GLOBAL=/dev/null`, and `GIT_CONFIG_NOSYSTEM=1`; rejects and removes inherited
command/environment config injection mechanisms including `GIT_CONFIG_PARAMETERS` and every
`GIT_CONFIG_COUNT` / `GIT_CONFIG_KEY_*` / `GIT_CONFIG_VALUE_*` tuple; and supplies only the
contract's fixed internal `-c` entries. Repository/worktree rewrite absence and the frozen
configuration snapshot are revalidated immediately inside each typed operation. Detection or
configuration drift is `URL_REWRITE_CONFIGURATION_PRESENT` / no-write FAIL before the first CAS.
After the CAS, it is indeterminate/ERROR and forbids further transport operations, including
tracking materialization. No code may claim an effective repository identity while a rewrite
mechanism remains eligible to alter it.

The same sanitized environment and rewrite-free capability are mandatory for both `ls-remote`
queries, the create writer, and tracking materialization. The direct endpoint operand must not be
canonicalized into, substituted with, or re-derived from the symbolic remote. Therefore
`pushInsteadOf` cannot make inspection A / publication B / verification A, and `insteadOf` cannot
redirect only a subset of the sequence. A failure to establish this envelope is
`REMOTE_CONFIGURATION_ERROR` / ERROR before mutation, not permission to proceed.

## 5. Required state model

The implementation must make at least these states explicit in typed results or equally precise
internal classifications:

- `EXISTING_UPSTREAM`: structured tracking matches, `@{upstream}` resolves, and the existing T-403
  path remains applicable.
- `SINGLE_EFFECTIVE_ENDPOINT`: exactly one push destination was derived: the sole explicit
  `pushurl`, or otherwise the sole ordinary `url`. Its immutable value is the only transport
  operand permitted for inspection and first publication.
- `NO_EFFECTIVE_ENDPOINT`: neither a usable push URL nor a usable fallback ordinary URL exists.
  This is a no-write FAIL.
- `MULTIPLE_PUSH_ENDPOINTS`: more than one explicit push URL exists. This is a no-write FAIL; the
  engine must not select one or invoke Git push.
- `MULTIPLE_FALLBACK_URLS`: no push URL exists and more than one ordinary URL would make Git push
  address multiple repositories. This is a no-write FAIL.
- `REMOTE_CONFIGURATION_ERROR`: the endpoint-bearing configuration cannot be read or is malformed,
  syntactically invalid, execution-ambiguous, or otherwise cannot yield authoritative structured
  evidence. This is `Status.ERROR` and no push may occur. Repeated URL values instead retain their
  cardinality and enter the appropriate multiple-endpoint state.
- `ENDPOINT_FORM_REJECTED`: the derived value is not one of section 4's accepted direct endpoint
  forms. This is a no-write policy/configuration FAIL.
- `URL_REWRITE_CONFIGURATION_PRESENT`: at least one `url.*.insteadOf` or
  `url.*.pushInsteadOf` value exists in the effective configuration, or the rewrite-free
  configuration snapshot cannot be revalidated. Before the create CAS this is a no-write FAIL;
  after a remotely verified creation it is `PUBLICATION_INDETERMINATE` / `Status.ERROR`, with no
  second remote write and no tracking fetch through an untrusted transport configuration.
- `TRACKING_CONFIGURATION_ERROR`: the configured fetch mapping is absent, duplicate, ambiguous,
  malformed, or does not map the approved exact remote head to the sole expected
  `refs/remotes/<remote>/<branch>` destination. This is a no-write FAIL/ERROR according to whether
  the evidence is a definite policy mismatch or unreadable configuration.
- `REMOTE_REF_ABSENT`: structured tracking matches and the authoritative remote query returns a
  valid empty result from the single effective endpoint, proving the exact approved destination
  does not exist there.
- `NO_TRACKING_CONFIGURATION`: one or both required local tracking fields are absent.
- `APPROVAL_TARGET_MISMATCH`: configured remote or merge ref differs from the approval target.
- `REMOTE_REF_EXISTS_MATCHING`: an authoritative pre-write query finds the exact destination at
  the approved HEAD. This is not a T-405 creation and is a no-write FAIL/re-evaluation.
- `REMOTE_REF_EXISTS_CONFLICTING`: an authoritative pre-write query finds the exact destination at
  another OID. This is a no-write conflict FAIL.
- `REMOTE_QUERY_ERROR`: command execution, transport, authentication, or protocol failure means
  existence cannot be determined. This is `Status.ERROR`, never FAIL and never absence.
- `REMOTE_QUERY_MALFORMED`: duplicate, ambiguous, unexpected, or syntactically invalid output
  prevents an authoritative observation. This is `Status.ERROR`, and no push may occur.
- `DIVERGED_OR_BEHIND`: the existing upstream resolves but the current T-403 behind/divergence
  protections refuse publication.
- `POLICY_REFUSAL`: a strict approval, branch/HEAD, cleanliness, tracking, endpoint-form,
  endpoint-cardinality, or pre-CAS configuration policy gate definitely failed. This is
  `Status.FAIL` with no remote mutation.
- `REMOTE_CONFLICT`: authoritative pre-write evidence shows the destination exists at another
  OID. It retains the more precise `REMOTE_REF_EXISTS_CONFLICTING` reason and is never eligible for
  update.
- `READY_FOR_FIRST_PUBLICATION`: every local, approval, tracking, and authoritative-absence gate
  passed immediately before the write attempt.
- `CREATE_CAS_REJECTED`: the writer ran, but the empty-expectation lease deterministically rejected
  creation or machine-readable output proves this process did not create the ref. An authoritative
  re-query must retain `CONCURRENT_SAME_SHA_CREATION` versus
  `CONCURRENT_CONFLICTING_CREATION` evidence. Both are definite no-success `Status.FAIL` results;
  neither may be credited to T-405 or modified/retried automatically.
- `PUBLICATION_FAILED_NO_CREATE`: the writer failed but authoritative reconciliation proves the
  destination is still absent and no creation occurred. This is a definite failure, distinct from
  an invoked writer whose effect cannot be reconciled.
- `REMOTE_PUBLICATION_VERIFIED_TRACKING_PENDING`: Git reported an actual new-ref creation and the
  authoritative post-write query against the frozen endpoint equals the approved HEAD, but the
  sole authorized local tracking materialization and its postconditions have not yet completed.
  This is not PASS and is never eligible for a workflow event.
- `TRACKING_MATERIALIZATION_ERROR`: the remote creation was verified, but the fixed single-ref
  tracking fetch failed, produced unexpected evidence, changed an unapproved local ref, or did not
  leave the expected tracking ref at the approved HEAD. This becomes
  `PUBLICATION_INDETERMINATE` / `Status.ERROR`; the engine must not issue another remote write.
- `PUBLISHED_VERIFIED`: Git reported an actual new-ref creation, the authoritative remote SHA and
  sole approved local remote-tracking ref both equal the approved HEAD, `@{upstream}` resolves to
  the exact approved symbolic upstream and SHA, and the worktree/index remain unchanged. Only this
  terminal state is PASS.
- `PUBLICATION_INDETERMINATE`: the writer was invoked but its effect cannot be authoritatively
  reconciled, or any post-write remote-SHA/tracking materialization/tracking verification is
  unavailable or mismatched. This is `Status.ERROR`, never PASS, permits no automatic retry or
  second remote write, and no successful workflow event may be recorded.

`FIRST_PUBLICATION_REJECTED` may remain an external/result umbrella for policy refusal or CAS
rejection only if its typed reason preserves all distinctions above; it may not collapse
pre-existing state, same-SHA/different-SHA races, definite no-create failure, or indeterminacy.

Endpoint configuration state and remote-ref existence state are orthogonal and must not be
collapsed. No local tracking configuration, no effective endpoint, ambiguous/multiple endpoints,
and an absent remote branch are different states. A remote query error or malformed response is
never absence. A pre-existing same-SHA ref and a pre-existing different-SHA ref have distinct
evidence/classifications, although neither is eligible for creation. A ref that appears after the
absence observation also has distinct race evidence: same SHA means this process did not create
it; different SHA is a conflict. Neither race may be reported as T-405 success.

## 6. Required read and write architecture

The plan review must verify the smallest typed extension consistent with the existing architecture:

- add a typed tracking read that returns the local branch's configured remote name and exact merge
  ref without requiring a resolvable `@{upstream}`; missing fields, duplicate values, a non-head
  merge ref, or any ambiguous/malformed configuration must fail closed;
- add a typed remote-endpoint read that returns the complete `remote.<name>.pushurl` and
  `remote.<name>.url` value sets, preserving cardinality and distinguishing absent values from
  unreadable/malformed configuration; it must derive exactly one `ValidatedPushEndpoint` under
  section 4's precedence rules and must never silently select the first of multiple values. The
  validated execution operand must also be proven not to be reinterpretable by Git as another
  configured symbolic remote; ambiguous plain-name endpoint spellings must be rejected or converted
  through a fixed, tested direct-transport form before any query or write;
- add a typed rewrite-configuration read that enumerates all effective `url.*.insteadOf` and
  `url.*.pushInsteadOf` values across the configuration scopes Git would otherwise consult. It
  must reject any value and produce a frozen rewrite-free configuration snapshot/capability that
  the exact-query, create writer, and tracking materializer revalidate rather than attempting URL
  rewrite matching;
- add a typed tracking-destination read that accepts exactly one `remote.<name>.fetch` value,
  requires the exact canonical
  `+refs/heads/*:refs/remotes/<validated-remote-name>/*` spelling, and proves that the approved
  `refs/heads/<branch>` maps to exactly
  `refs/remotes/<validated-remote-name>/<branch>`, and returns that single destination as a
  `ValidatedRemoteTrackingRef`. Configured fetch refspecs are validation evidence only; they are
  never executed by the T-405 materializer;
- read effective `fetch.bundleURI` configuration before the CAS and refuse any non-empty value;
  the materializer must additionally supply a fixed empty command-local value so it cannot contact
  a bundle repository even if a lower-priority value exists;
- add a typed exact-remote-head read that accepts only that `ValidatedPushEndpoint` and the
  validated exact `refs/heads/*` merge target, uses safe option termination, and runs an exact
  query equivalent to `git ls-remote --refs --heads -- <endpoint> <exact-ref>` inside the fixed
  rewrite-free configuration envelope; passing the remote symbolic name to this operation is
  forbidden;
- require the exact-remote-head parser to accept only either empty stdout (authoritative absence)
  or one `<40-or-64-lowercase-hex-OID>\t<exact-requested-ref>\n` record; duplicate, mismatched,
  ambiguous, extra, or malformed records are `REMOTE_QUERY_MALFORMED`, while any nonzero command,
  transport, authentication, or protocol result is `REMOTE_QUERY_ERROR`;
- allow only the minimum new read-only Git forms required for those typed methods; no generic Git
  argv executor becomes public;
- retain `GitWriter.push()` unchanged for `EXISTING_UPSTREAM`;
- add one separately named, fixed-shape first-publication writer method and one separately named,
  fixed-shape single-ref local tracking materializer; and
- expose no generic `force`, `force_with_lease`, `lease`, `expected_oid`, `refspec`, `source_ref`,
  `destination_ref`, `extra_args`, or arbitrary-argv parameter through a public writer API.

`ValidatedRemoteName`, `ValidatedHeadsRef`, and `ValidatedRemoteTrackingRef` must be constructed
from structured Git configuration only after exact approval comparison and Git ref-format
validation. They reject empty values, control characters, option spellings, glob/refspec syntax,
colons, deletion forms, and any value that cannot form the exact expected heads or remote-tracking
namespace. String concatenation from an unvalidated display-form upstream is forbidden.

The new writer method must be a narrow semantic operation over validated operand types. Its shape
must be equivalent to:

```python
def push_new_branch(
    *,
    endpoint: ValidatedPushEndpoint,
    approved_head: CommitOid,
    remote_ref: ValidatedHeadsRef,
) -> FirstPublicationWriteResult: ...
```

Exact type and method names may differ. `ValidatedPushEndpoint` must be constructed only by the
gate from the structured configured remote after approval-target comparison and exact-cardinality
validation. `ValidatedHeadsRef` must likewise come only from the matched structured tracking read.
`CommitOid` must be constructed only from the already validated `approval.head`, after the gate
has proved that the live approved branch and live `HEAD` resolve to that OID. The writer must not
accept a caller-selected OID independent of that validated approval flow. It must not accept a
remote symbolic name or URL list and must never re-read or re-resolve remote configuration. These
semantic operands do not authorize caller-provided option text, command-local config, a source
ref, a refspec, a lease, an expected OID, or any extra argument.

The fixed-shape writer must internally construct an argv equivalent in meaning to:

```text
git \
  -c push.followTags=false \
  -c push.recurseSubmodules=no \
  -c push.pushOption= \
  push --porcelain --no-verify \
  --force-with-lease=<validated-exact-refs/heads-destination>: \
  -- <validated-effective-push-endpoint> \
  <validated-approved-head-OID>:<validated-exact-refs/heads-destination>
```

The exact order and spelling must be validated against the repository's installed Git and current
subprocess convention before implementation. All three `-c` entries are fixed internal literals
before the `push` subcommand; callers cannot add, remove, or replace them. The fixed empty
`push.pushOption` value clears inherited multi-valued push options for this invocation, and
`--no-verify` prevents repository-local or `core.hooksPath` pre-push hooks from executing.
Invocation-local overrides are required so repository or global configuration is not mutated.
Equivalent fixed command-level flags are acceptable only if tests prove the same no-expansion and
no-push-option semantics against the installed Git.

The empty expected OID is mandatory and literal. The source operand is the immutable approved
commit OID, never the mutable local branch ref. The destination must be the exact validated
approved `refs/heads/*` ref, and the internally generated refspec must never contain deletion or
leading-force syntax. The endpoint operand is the immutable validated effective endpoint, never
the symbolic remote. Changing `remote.<name>.url` or `remote.<name>.pushurl` after validation
cannot redirect the writer: the invocation still addresses the frozen endpoint or fails before
publication. The execution form must not perform a second named-remote lookup; otherwise a URL/path
value equal to another remote name, or a newly introduced alias after validation, could redirect
the operation and must be rejected as `REMOTE_CONFIGURATION_ERROR`. The local branch remains
independently approval-gated, but moving it after validation cannot change the object the writer
offers to the remote. Structured tracking configuration is already a precondition, so this
primitive does not add a generic config writer. Because publication directly to a URL/path does
not update a named remote-tracking ref, `@{upstream}` is not tested until the narrow materializer
below has made that one prevalidated tracking ref current.

The fixed direct endpoint plus explicit OID-to-ref refspec makes `remote.<name>.push`,
`push.default`, `remote.pushDefault`, `branch.<name>.pushRemote`, and `push.autoSetupRemote`
irrelevant to target selection and refspec expansion; implementation tests must verify that claim
against the installed Git. Named-remote-only settings such as `remote.<name>.mirror` and
`remote.<name>.receivepack` are likewise irrelevant only after the execution operand is proved
incapable of named-remote reinterpretation. `push.followTags` remains capable of adding tag refs
and `push.recurseSubmodules` remains capable of initiating pushes to other repositories, so the
fixed invocation must override both as shown. `push.pushOption` can transmit ambient caller/server
instructions and is cleared; client pre-push hooks can initiate arbitrary effects and are bypassed.
Installed Git 2.43's `push.gpgSign`, `push.negotiate`, `push.useBitmaps`, and
`push.useForceIfIncludes` affect certification, negotiation/performance, or an additional safety
condition, but do not select another refspec or push repository; they therefore need no generic
hardening in this contract. The implementation/reviewer must reverify those conclusions against
the installed Git used for implementation and document whether any other setting can add a ref or
repository write to this explicit-endpoint/explicit-refspec invocation. Only settings that
actually retain such influence require a fixed override or a pre-write fail-closed gate; this is
bounded proof, not generic Git hardening.

`--porcelain` must be strictly checked so success is recognized only when Git reports one actual
new-ref creation for the exact destination (the `*` new-ref status), with no unexpected update.
An exit-zero no-op (the `=` up-to-date status), including a concurrent same-SHA appearance, is
`FIRST_PUBLICATION_REJECTED`, not T-405 success. A deterministic empty-lease rejection is likewise
`FIRST_PUBLICATION_REJECTED`. A subprocess outcome whose remote effect cannot be authoritatively
reconciled is `PUBLICATION_INDETERMINATE`.

Porcelain checking is defense in depth, not the mechanism preventing extra writes. Endpoint
cardinality, direct endpoint addressing, the explicit single refspec, and fixed ambient-expansion
overrides must make any additional endpoint/ref/submodule operation unreachable before Git runs.

After, and only after, a post-write exact query proves that the remote branch at the frozen
endpoint equals `approval.head`, the gate may invoke this second narrow semantic operation:

```python
def materialize_approved_tracking(
    *,
    endpoint: ValidatedPushEndpoint,
    remote_ref: ValidatedHeadsRef,
    tracking_ref: ValidatedRemoteTrackingRef,
) -> TrackingMaterializationResult: ...
```

The method must internally construct a single fixed fetch equivalent in meaning to:

```text
git \
  -c fetch.writeCommitGraph=false \
  -c fetch.bundleURI= \
  fetch \
  --atomic \
  --no-tags \
  --no-recurse-submodules \
  --no-write-fetch-head \
  --no-prune \
  --no-prune-tags \
  --no-auto-maintenance \
  --no-write-commit-graph \
  --refmap= \
  -- <validated-effective-push-endpoint> \
  +<validated-exact-remote-head>:<validated-exact-local-remote-tracking-ref>
```

The implementation must verify the exact installed-Git spelling and ordering. The source and
destination are separate validated types; neither accepts a glob, deletion spelling, option, or
caller-composed refspec. The fixed leading `+` is generated internally and authorizes replacement
of only this one local remote-tracking cache ref with the already verified authoritative remote
head; it is not caller-provided and grants no remote force/update authority. The empty `--refmap=`
disables configured refmap expansion, and the explicit one-to-one mapping is generated internally.
The empty `fetch.bundleURI` override prevents a configured incremental bundle download from any
second repository and is defense in depth after the required pre-CAS configuration refusal. The
other fixed flags prevent tag,
submodule, `FETCH_HEAD`, prune, maintenance, and commit-graph side effects. The operation uses the
same frozen endpoint and rewrite-free subprocess envelope as inspection/publication and never the
symbolic remote for transport. It may create or update only the approved local remote-tracking
ref; it may not change config, another local ref, `HEAD`, the index, or the worktree. No generic
fetch API, arbitrary refspec, endpoint, config, or option input is exposed.

The gate snapshots local refs plus worktree/index state immediately before materialization and
compares them afterward. Only the expected tracking ref may differ, and it must resolve to
`approval.head`; every unrelated-ref or worktree/index difference is
`TRACKING_MATERIALIZATION_ERROR`. A materialization subprocess failure or mismatch occurs after a
verified remote creation, so it is `PUBLICATION_INDETERMINATE` / `Status.ERROR`: no workflow event,
no automatic materialization retry, and no second remote write.

The zero-expected-OID lease is the update-time compare-and-swap. If another actor creates the
destination after the absence check, the writer must not overwrite or advance it. Any Git response
other than proven creation is non-success for this path.

## 7. Gate sequence and postconditions

The first-publication path must execute in this order:

1. load and validate the approval, requiring literal strict `create_remote_ref is True`;
2. capture the approval digest and verify the exact local branch;
3. resolve both that local branch and live `HEAD` and require each to equal `approval.head`;
4. require a clean worktree/index with no untracked files;
5. read structured tracking configuration and match the approved remote and destination ref;
6. validate exactly one canonical configured fetch mapping and derive the sole permitted local
   `ValidatedRemoteTrackingRef` represented by the approved symbolic upstream;
7. read all configured fetch and push URL values for that symbolic remote and derive exactly one
   effective push endpoint under section 4, refusing missing, multiple, malformed, or ambiguous
   endpoint configurations before mutation;
8. validate the endpoint's accepted direct form; reject every effective Git URL rewrite entry and
   every non-empty effective `fetch.bundleURI`; freeze the endpoint plus rewrite-free/no-bundle
   configuration snapshot/capability so every later operation receives the exact same transport
   value and fixed configuration envelope;
9. authoritatively query the exact destination at that endpoint and prove it absent;
10. revalidate approval integrity, exact branch, live HEAD, clean worktree/index, endpoint/tracking
    configuration snapshots, and rewrite absence immediately before mutation;
11. derive the immutable source exclusively from validated `approval.head` and invoke the
    fixed-shape create-only writer exactly once with hardcoded hook, push-option, tag, and submodule
    protections;
12. require machine-readable proof that this invocation created the exact new ref;
13. query the authoritative remote ref again through the same rewrite-free envelope at the same
    frozen endpoint and require its SHA to equal `approval.head`, entering
    `REMOTE_PUBLICATION_VERIFIED_TRACKING_PENDING` rather than PASS;
14. snapshot all local refs and the worktree/index; invoke the fixed single-ref tracking
    materializer against the same frozen endpoint, source exact remote head, and sole validated
    local remote-tracking destination;
15. require only that local tracking ref to have changed, require it to resolve to
    `approval.head`, and require the worktree/index to remain byte/state unchanged;
16. require `@{upstream}` to resolve to the exact approved symbolic upstream and require its SHA to
    equal `approval.head`; and
17. return `PUBLISHED_VERIFIED` / PASS only after every preceding postcondition succeeds.

The required invariant is byte-for-byte operand identity:

```text
pre-write inspected endpoint == writer endpoint == post-write verified endpoint
                         == tracking-materialization source endpoint
```

If symbolic remote configuration changes after step 7, it must not be consulted by the writer or
post-write query or materializer. Before step 11, any endpoint, tracking, or rewrite-configuration
drift is a no-write refusal. After step 11, drift or rewrite evidence is
`PUBLICATION_INDETERMINATE` / ERROR: the gate must not use a changed symbolic value, run tracking
transport through an untrusted rewrite configuration, retry the CAS, or perform another remote
write. A mere raw endpoint-string match is insufficient; accepted direct endpoint forms plus the
fixed rewrite-free environment must prove all four operations dispatch to the same actual
repository.

If the push subprocess exits zero but the post-write query is unavailable, its output is
malformed, the authoritative SHA differs, tracking materialization fails, the local tracking SHA
differs, or upstream resolution/name/SHA is not exact, the result is
`PUBLICATION_INDETERMINATE` / `Status.ERROR`. Post-write observation can refuse success but can
never retroactively claim no remote mutation or authorize an object other than the immutable
approved OID. No failure after the CAS permits an automatic second remote write.

No workflow `push` completion record may be written before step 17. T-405 does not redesign the
event store or combine `workflowctl push` with `workflowctl state record`; it requires that failed
or indeterminate publication never be represented as a completed push, and that a separate state
record be permitted only after the independently verified PASS evidence exists.

## 8. Existing-upstream compatibility

When `create_remote_ref` is omitted or false, current T-403 behavior remains unchanged: exact
branch, HEAD, and resolvable upstream equality; clean tree; strict behind/ahead computation;
behind zero; at least one local commit ahead; `diff --check`; and the existing non-force
`GitWriter.push()` call and existing result semantics. All existing T-403 tests remain present and
passing. T-405 must not add an authoritative post-push remote query, endpoint-set derivation,
direct endpoint publication, multiple-pushurl handling, URL-rewrite policy, tracking
materialization, or any new postcondition to that legacy path. No new T-405 endpoint or tracking
function may be invoked by it, and the existing `GitWriter.push()` argv remains exactly unchanged.

The boundary is explicit:

```text
T-403 existing-upstream path:
  existing gates -> existing GitWriter.push() -> existing result semantics, unchanged

T-405 absent-approved-ref bootstrap path:
  strict endpoint/CAS/remote verification/local tracking materialization semantics in sections 4-7
```

Hardening legacy remote verification, hooks, endpoint identity, or tracking behavior is a separate
task and policy decision. T-405's endpoint derivation, direct endpoint addressing, fixed ambient
protections, post-write query, and materializer are bootstrap-only.

Wrong branch, HEAD, remote, destination ref, tracking configuration, dirty state, or
behind/diverged history retains the existing legacy outcome. On the new bootstrap path, remote
query execution/malformed-output failures are ERROR, and a subprocess failure or post-CAS
mismatch/unavailable observation is `PUBLICATION_INDETERMINATE`; none may enable a successful
workflow record.

## 9. Expected implementation surface

Production changes are bounded to the push approval, typed Git inspection/writer, push gate, and
their existing CLI result wiring:

- `src/ai_workflow_engine/git/approval.py`
- `src/ai_workflow_engine/git/models.py`
- `src/ai_workflow_engine/git/client.py`
- `src/ai_workflow_engine/git/writer.py`
- `src/ai_workflow_engine/commit/gates.py`
- `src/ai_workflow_engine/cli.py` only if additive output/help wiring is required

Test changes are bounded to the existing approval/Git/push/CLI modules:

- `tests/test_approval.py`
- `tests/test_git_client_reads.py`
- `tests/test_git_writer.py`
- `tests/test_push_gates.py`
- `tests/test_cli.py` only where the CLI boundary must be demonstrated

Product documentation may update `README.md`, `docs/architecture.md`, `docs/configuration.md`,
`docs/milestone-4-plan.md` through an explicit T-405 amendment (without rewriting T-403 history),
`docs/DECISION_LOG.md`, and `docs/CHANGELOG.md`. Normal task closeout mirrors and handover files may
change only at their corresponding governance stages. The independent plan review must reject any
broader production or test surface unless a concrete requirement above cannot otherwise be met and
the Human Owner separately authorizes the expansion.

## 10. Deterministic regression matrix

All remote-writing tests use temporary local repositories and local bare remotes; no GitHub or
other external network is required.

1. existing valid upstream -> existing T-403 PASS unchanged;
2. exact tracking, remote absent, and literal `create_remote_ref: true` -> verified first-
   publication PASS;
3. field omitted while the remote ref is absent -> first publication refused;
4. literal `create_remote_ref: false` while the remote ref is absent -> refused;
5. `create_remote_ref: "true"` -> approval rejected;
6. `create_remote_ref: "false"` -> approval rejected;
7. `create_remote_ref: 1` -> approval rejected;
8. `create_remote_ref: 0` -> approval rejected;
9. no tracking configuration -> FAIL before remote mutation;
10. approval target differs from configured remote or merge ref -> FAIL before mutation;
11. remote query command/transport/authentication/protocol failure -> `REMOTE_QUERY_ERROR` /
    `Status.ERROR`, never absent;
12. malformed, duplicate, ambiguous, mismatched, or unexpected remote output ->
    `REMOTE_QUERY_MALFORMED` / `Status.ERROR`, no push;
13. the exact remote ref already exists at the approved SHA before eligibility ->
    `REMOTE_REF_EXISTS_MATCHING`, no creation attempt;
14. the exact remote ref already exists at another SHA -> `REMOTE_REF_EXISTS_CONFLICTING`, no
    creation attempt;
15. another actor creates the destination at the approved SHA after authoritative absence but
    before the write -> zero-OID CAS/no-op proof yields `FIRST_PUBLICATION_REJECTED`, no claimed
    creation and no modification by T-405;
16. another actor creates the destination at a different SHA in the same window -> zero-OID CAS
    rejects, `FIRST_PUBLICATION_REJECTED`, and the competing ref remains untouched;
17. the local branch initially equals `approval.head`, then a deterministic hook/interposition
    moves it after gate validation -> writer argv still uses only the immutable approved OID (or
    the operation fails before publication), and the moved commit can never be published;
18. live local branch/HEAD differs from `approval.head` initially -> FAIL before mutation;
19. staged, modified, or untracked worktree state -> FAIL before mutation;
20. writer subprocess failure -> no success and no workflow event; if its remote effect cannot be
    reconciled, classify `PUBLICATION_INDETERMINATE` rather than claiming definite publication;
21. push exits zero, then the authoritative post-write query is unavailable ->
    `PUBLICATION_INDETERMINATE` / `Status.ERROR`, no workflow event;
22. push exits zero, then the authoritative remote SHA differs from `approval.head` ->
    `PUBLICATION_INDETERMINATE` / `Status.ERROR`, no workflow event;
23. push exits zero and the remote SHA matches, but materialized tracking or `@{upstream}` is
    missing, differs from the approved target, or resolves to another SHA ->
    `PUBLICATION_INDETERMINATE` / `Status.ERROR`, no workflow event and no second remote write;
24. verified first publication -> writer proves exact new-ref creation, exact authoritative remote
    SHA and the one materialized tracking ref equal `approval.head`, `@{upstream}` resolves to the
    exact approved target/SHA, and worktree/index are unchanged;
25. the new writer's complete argv is asserted, including the literal empty-expectation lease,
    safe option termination, immutable effective endpoint, approved OID source, exact heads
    destination, fixed ambient-expansion overrides, empty push-option override, and hook bypass;
26. writer API introspection proves there is no generic force, lease, expected-OID, refspec,
    source-ref, destination-ref, remote-name, URL-list, config-override, extra-args, or raw-argv
    escape hatch;
27. the full pre-existing T-403 push-gate and CLI suite remains behaviorally green, its writer argv
    remains byte-for-byte unchanged, and it invokes none of the bootstrap endpoint/query/tracking
    functions; and
28. workflow event/history bytes remain identical across every FAIL, ERROR, rejected, and
    indeterminate case; only independently verified PASS evidence may precede a separate record;
29. one ordinary remote URL and no push URL -> that URL is the sole endpoint used for exact
    pre-write inspection, mutation, and exact post-write verification;
30. one explicit push URL different from the fetch URL -> the push URL is the sole effective
    endpoint for inspection/mutation/verification, and the fetch repository is not treated as
    authoritative publication state;
31. multiple push URLs -> `MULTIPLE_PUSH_ENDPOINTS`, FAIL before mutation, and every candidate bare
    remote remains unchanged;
32. no push URL and multiple ordinary URLs -> `MULTIPLE_FALLBACK_URLS`, FAIL before mutation, with
    no silent first-value selection and all repositories unchanged;
33. no usable URL or push URL -> `NO_EFFECTIVE_ENDPOINT`, FAIL before mutation;
34. unreadable, malformed, syntactically invalid, or execution-ambiguous endpoint configuration
    (including an endpoint spelling Git could reinterpret as another symbolic remote) ->
    `REMOTE_CONFIGURATION_ERROR` / ERROR or equally fail-closed configuration result, no mutation;
35. the fetch repository reports the ref absent while a distinct sole push endpoint already has
    it -> eligibility is classified from the push endpoint and the existing ref is not updated;
36. fetch and sole push endpoints contain different SHAs -> only the push endpoint controls the
    matching/conflicting first-publication classification;
37. after endpoint validation, deterministic interposition changes the symbolic remote config
    from bare remote A to bare remote B -> the writer still receives immutable A or fails before
    invocation, and B remains untouched;
38. captured calls prove the post-write query receives the exact same endpoint value as the
    pre-write query and writer;
39. repository config sets `push.followTags=true` and an eligible local annotated tag exists ->
    only the approved branch is created and no tag appears remotely;
40. repository/submodule config enables recursive push in a fixture capable of exposing it -> the
    first-publication invocation performs no submodule push or other-repository operation;
41. adversarial `remote.<name>.push` contains additional refspecs -> the direct endpoint and exact
    command-line refspec ignore it structurally and no extra ref is written;
42. adversarial `push.default`, `remote.pushDefault`, `branch.<name>.pushRemote`, and
    `push.autoSetupRemote` cannot redirect or expand the fixed direct-endpoint/explicit-refspec
    invocation; tests exercise settings that affect installed Git and document why the others are
    irrelevant;
43. the complete writer argv proves all hardcoded ambient protections are present in the verified
    order/spelling supported by installed Git; and
44. writer API inspection proves callers cannot override/remove the endpoint binding or ambient
    protections and cannot supply a symbolic remote, URL list, or command-local configuration;
45. with both the remote branch and local remote-tracking ref initially absent, publication and
    authoritative remote verification complete before the single tracking materializer runs;
46. the materializer fetches exactly the approved remote head from the frozen endpoint into the
    exact validated `refs/remotes/<remote>/<branch>` ref and leaves it at `approval.head`;
47. before/after local-ref snapshots prove that only that one remote-tracking ref changes and all
    unrelated local branches, tags, and remote-tracking refs remain byte-for-byte unchanged;
48. worktree/index snapshots prove the materializer does not modify tracked files, untracked-file
    state, staged state, `HEAD`, or branch configuration;
49. after materialization, `@{upstream}` resolves to the exact approved symbolic upstream and both
    the tracking ref and resolved upstream object equal `approval.head`;
50. deterministic tracking-materialization subprocess failure after verified remote creation ->
    `TRACKING_MATERIALIZATION_ERROR` and `PUBLICATION_INDETERMINATE` / ERROR, no event, no retry,
    and no second remote write;
51. materialization returns success but the tracking SHA mismatches -> indeterminate/ERROR, with
    remote creation reported as potentially/actually already performed rather than rolled back;
52. materialization changes an unrelated local ref or worktree/index evidence -> indeterminate /
    ERROR and no workflow event;
53. captured argv proves `--refmap=`, empty `fetch.bundleURI`, and all fixed no-tags/no-submodule/
    no-FETCH_HEAD/no-prune/no-maintenance/no-write-commit-graph protections plus one exact
    generated mapping; a configured bundle URI fixture proves no second repository is contacted;
54. materializer API inspection proves no generic fetch, refspec, endpoint, config, option,
    symbolic-remote, or destination escape hatch;
55. fetch repository A is inspected while `url.<B>.pushInsteadOf=A` is configured -> T-405 refuses
    before remote mutation and both A and B remain unchanged;
56. an applicable `url.<B>.insteadOf=A` rule -> fail-closed refusal before any remote operation,
    with both repositories unchanged;
57. multiple or overlapping rewrite rules, including rules in different effective configuration
    scopes, are rejected without choosing or reproducing Git's longest-match behavior;
58. inherited `GIT_CONFIG_PARAMETERS` and `GIT_CONFIG_COUNT` rewrite injection are rejected and
    removed from the fixed subprocess envelope before any remote operation;
59. an accepted absolute temporary bare-repository path and accepted `file://` endpoint each prove
    actual inspect/write/verify/materialize repository identity under the rewrite-free envelope;
60. a relative path, scp-like spelling, configured-remote-looking plain name, unknown scheme,
    `<helper>::<address>`, or `ext::` endpoint is `ENDPOINT_FORM_REJECTED` with no mutation;
61. after endpoint/rewrite validation, symbolic remote A is changed to B -> all bootstrap
    operations remain bound to frozen A or refuse; B and every unrelated repository remain
    untouched;
62. a repository `.git/hooks/pre-push` executable that would write another ref/repository is not
    executed, proven by absent marker/effect and exact `--no-verify` argv;
63. adversarial `core.hooksPath` pointing outside `.git/hooks` likewise cannot execute its
    pre-push hook;
64. ambient multi-valued `push.pushOption` configuration is cleared by the fixed empty
    invocation-local value, and a receive-hook fixture proves no unexpected push option is
    delivered;
65. writer API and exact-argv tests prove callers cannot remove `--no-verify`, remove/override the
    empty push-option entry, or supply a push option/hook/config argument;
66. tag-following, recursive-submodule, push-option, and hook adversarial fixtures each prove that
    only the one approved branch is remotely created and every unrelated bare remote/ref remains
    unchanged;
67. the complete pre-existing T-403 suite runs unchanged;
68. spies prove the legacy path invokes no T-405 endpoint derivation, rewrite inspection,
    authoritative remote query, or tracking materialization function;
69. the legacy `GitWriter.push()` exact argv and existing success/failure result semantics remain
    unchanged; and
70. route-selection tests prove only literal strict `create_remote_ref: true` can enter the new
    bootstrap path, while omission/false remains entirely on the legacy path.

The two remote-race tests must deterministically interpose a second local clone or direct
local-bare-remote publication between the engine's absence observation and writer invocation. The
local-source race must deterministically move the local branch after validation but before writer
execution and assert the exact OID-based argv. The endpoint-race test must deterministically change
only the symbolic remote configuration after `ValidatedPushEndpoint` construction and prove that
late re-resolution cannot redirect the writer. Rewrite, hook, push-option, and materialization
tests must use captured argv/config plus repository/ref snapshots, not timing assumptions. Timing
sleeps and external services are prohibited.
All remote-writing tests use only temporary local repositories and local bare remotes. Every test
with multiple repositories must assert all unrelated bare-remotes' refs and relevant bytes remain
unchanged.

## 11. Acceptance criteria

T-405 implementation is acceptable only when:

- `create_remote_ref` is field-locally strict, explicit, defaults false, is included in approval
  identity, and rejects `"true"`, `"false"`, `1`, and `0`;
- tracking configuration is read structurally without requiring `@{upstream}` resolution;
- the approved remote and exact `refs/heads/*` destination are unambiguously bound;
- the complete push-URL and fallback ordinary-URL sets retain their cardinality and yield exactly
  one immutable validated effective endpoint, with missing/multiple/malformed cases failing before
  mutation and duplicate configured values never being silently de-duplicated;
- accepted endpoint forms are implementation-verifiable direct filesystem paths or the enumerated
  standard URL schemes; relative/scp-like/helper/custom/ambiguous forms fail before mutation;
- all effective Git URL rewrite entries and inherited config injection are rejected, every
  transport command uses the fixed sanitized rewrite-free environment, and pre-write inspection,
  writer invocation, post-write inspection, and tracking materialization address the same actual
  repository through the same frozen endpoint without re-resolving the symbolic remote;
- absence, matching existence, conflicting existence, query error, and malformed query evidence
  are observably distinct, with both query-failure classes reported as ERROR;
- the only new remote write primitive is fixed-shape and can express only exact absent-ref creation
  using the empty-expectation CAS authorized above;
- the first-publication source operand is the immutable validated `approval.head` OID, never a
  mutable local ref, and a post-validation local branch move cannot change what may be published;
- a concurrently appearing ref is never modified, including when it is an ancestor or the same
  SHA as the approved HEAD;
- no generic force, lease, or refspec API exists;
- the first-publication writer uses the direct validated endpoint plus one explicit refspec,
  `--no-verify`, an empty inherited-push-option override, and fixed invocation-local protection
  against tag following and submodule recursion, with no caller authority to alter those
  protections;
- installed Git's other relevant push settings are assessed and either proven irrelevant to the
  fixed direct-endpoint/explicit-refspec operation or neutralized/fail-closed before mutation;
- definite first-publication rejection and post-write indeterminacy are distinct;
- the only new local Git metadata write is the fixed one-to-one materialization of the approved
  remote head into its validated local remote-tracking ref, with configured refmaps and all
  unrelated fetch side effects disabled, including explicit refusal plus invocation-local
  clearance of `fetch.bundleURI` so no second repository is contacted;
- post-push authoritative remote SHA, local tracking SHA, and resolved upstream name/SHA all equal
  the approval, with unavailable or mismatched postconditions producing
  `PUBLICATION_INDETERMINATE` / ERROR and no second remote write;
- no successful gate result or workflow push completion record occurs before independent
  publication verification;
- every test in section 10 passes with local bare remotes;
- every pre-existing T-403 test remains present and passes, with exact legacy writer argv/result
  semantics and no bootstrap endpoint/query/materialization calls; and
- the focused and full repository validation suites are green.

## 12. Validation requirements

Focused validation must cover the five test modules in section 9 plus deterministic local-bare
remote ref-race, endpoint-cardinality, endpoint-drift, fetch/push-divergence, and ambient-
configuration containment tests, URL-rewrite refusal, hook bypass, push-option clearance, exact
tracking materialization/failure, and legacy path isolation. Full authoritative validation is:

```text
pytest -q
ruff check .
black --check .
mypy
pre-commit run --all-files
git diff --check
workflowctl verify --config self-governance.yaml
```

No live provider/model command or external GitHub access is part of validation.

## 13. Explicit exclusions

T-405 excludes ORCH-021, remote URL digest redesign, generic Git synchronization, automatic remote
or GitHub repository creation, merge or pull-request automation, force/lease support outside the
single zero-expected-OID creation CAS, arbitrary ref publication, branch deletion, documentation-
orchestrator code or governance changes, provider/model execution, unrelated governance
improvements, retry of unrelated workflow stages, and publication without explicit Human approval.

Resolving the current configured URL sets into one internal effective endpoint is not an approval
schema or remote-identity redesign. T-405 adds no approved URL/digest field and no reusable generic
remote-resolution or push-hardening facility.

## 14. Required review and workflow

The immediate next stage is a fresh independent `plan-review` against this contract and the live
T-403 implementation. The reviewer must have no participation in drafting this contract, must
verify the zero-OID race semantics (including the same-SHA no-op case), single-effective-endpoint
binding, rewrite-free actual-repository identity, symbolic-config TOCTOU protection, hook and
push-option containment, exact local tracking materialization, and the strict T-403 preservation
boundary, and must return the repository's exact `APPROVED` or `REJECTED` verdict. Implementation
must not begin on a rejected or unreviewed contract. A rejection is remediated in the plan/contract
and submitted to another fresh independent review before implementation.

After an approved plan review, the existing lifecycle continues through implementation,
implementation review/remediation, governance closeout/review, and separately Human-approved
commit and push. Registering T-405 authorizes no production change during this governance-only
registration step and authorizes no successor task.

## 15. Plan-remediation disposition

`UNVERIFIABLE — no preserved independent-review artifact was located.` This section's account of
three review rounds, their verdicts, and their finding closures could not be corroborated by any
review file, prompt, agent run, or workflow event (section 17). It is retained because the
engineering findings it enumerates are substantive and traceable in the contract text itself — not
because the reviews that allegedly produced them have been verified. Read every "review returned",
"confirmed closed", and "finding" below as reported, not as established.

Three fresh independent plan reviews were reported to have returned
`REJECTED / PLAN_REMEDIATION_REQUIRED`. No workflow event was recorded for any rejected review, so
T-405 remained `Current` with `plan-review` next.
The earlier remediations remain binding and keep their four original findings closed:

- `T405-PR-001`: replaces the coercive plain boolean with field-local strict boolean authority and
  requires rejection of string/integer lookalikes;
- `T405-PR-002`: replaces the mutable local-ref push source with the immutable validated
  `approval.head` OID and adds the deterministic local-ref movement test plus exact argv proof;
- `T405-PR-003`: makes command/transport/authentication/protocol query failures and malformed,
  duplicate, ambiguous, or unexpected query output distinct `Status.ERROR` outcomes; and
- `T405-PR-004`: separates matching existence, conflicting existence, definite creation
  rejection, and post-write indeterminacy, with dedicated post-write query/SHA/tracking tests.

The endpoint/push-containment remediation established the core corrections for the next two
findings, and this final trust-boundary remediation closes the consequences that prevented them
from being considered fully closed:

- `T405-PR-005`: separates symbolic remote identity, fetch URLs, push URLs, and one immutable typed
  effective endpoint; rejects missing/multiple/malformed endpoint configuration before mutation;
  uses the same direct endpoint value for pre-write inspection, zero-OID publication, and
  post-write verification; and adds deterministic fetch/push divergence, endpoint-cardinality, and
  symbolic-config movement tests.
- `T405-PR-006`: requires fixed invocation-local `push.followTags=false` and
  `push.recurseSubmodules=no` semantics, direct endpoint addressing, and one explicit OID-to-ref
  refspec; now also requires `--no-verify`, empty `push.pushOption`, rewrite-free configuration,
  installed-Git assessment of other push settings, and deterministic tag, submodule, extra-refspec,
  redirect/default, hook, push-option, exact-argv, and API-closure tests. Porcelain remains
  post-write evidence, not the protection against expanded writes.

This remediation closes the four latest blocking findings:

- `T405-PR-007`: after verified direct-endpoint publication, authorizes one fixed, single-ref
  fetch from the same frozen endpoint into the prevalidated approved remote-tracking ref; disables
  refmap/tag/submodule/FETCH_HEAD/prune/maintenance/commit-graph expansion; verifies the sole local
  ref change, SHA, upstream name/SHA, and unchanged worktree/index; and makes every failure
  indeterminate with no second remote write.
- `T405-PR-008`: enumerates accepted direct endpoint forms; rejects custom helpers, ambiguous
  forms, and every effective `insteadOf`/`pushInsteadOf` entry; sanitizes Git configuration
  injection; and requires inspection, CAS, post-query, and materialization to use the same frozen
  endpoint under the same rewrite-free envelope.
- `T405-PR-009`: fixes `--no-verify` so neither repository hooks nor `core.hooksPath` can run a
  client pre-push hook, fixes an empty invocation-local `push.pushOption` to clear ambient options,
  forbids caller override, and adds deterministic hooks/options/no-leakage tests.
- `T405-PR-010`: removes the earlier common post-push verification requirement and explicitly
  preserves the complete T-403 existing-upstream path, exact `GitWriter.push()` argv, and result
  semantics without invoking any T-405 endpoint, query, rewrite, or materialization operation.

The Human Owner's create-only policy, task scope, authorization, and exclusions are unchanged.
This remediation authorizes only another fresh independent plan review, not implementation.

## 16. Final Human Owner disposition — deferred/closed without implementation

On 2026-08-19, after the reported plan reviews
(`UNVERIFIABLE — no preserved independent-review artifact was located.`) indicated that a fully
governed first-publication primitive requires materially broader Git transport, URL rewriting,
hook, ambient configuration, environment, tracking, and local-metadata isolation than the intended
bounded remediation, the Human Owner directed that T-405 must not be implemented. This is an intentional
policy/scope decision, not abandonment because of an implementation defect: no T-405 production
or test implementation was started.

The binding replacement policy is:

```text
FIRST PUBLICATION
Human Owner manual bootstrap
→ establishes remote branch and upstream

SUBSEQUENT PUBLICATION
existing T-403 workflowctl push
→ requires resolvable approved upstream
```

First publication of a branch whose remote upstream ref does not yet exist is an explicit Human
Owner bootstrap performed outside `workflowctl push`. Once the manual operation establishes the
remote branch and a resolvable upstream, ordinary subsequent publication returns to the unchanged
T-403 path. This decision grants no unattended push, force, force-with-lease, arbitrary first-
publication automation, deletion, merge automation, T-403 change, `GitWriter` change, or T-405
implementation authority.

`SUPERSEDED — historical operator sequence; no longer actionable.` As written on 2026-08-19,
this section recorded a prospective operator sequence for the separate `documentation-orchestrator`
repository — the manual bootstrap `git push -u origin feature/docflow-005-provider-doctor`,
performed only after rechecking that repository's branch, exact HEAD, clean worktree, remote and
upstream target, then verifying remote branch SHA `dced1783788c64ec0c97576ea5709b7e2dc27600` and
upstream resolution, completing the DOCFLOW-005 push lifecycle, reconciling that repository's stale
governance and handover narratives, and only then considering DOCFLOW-006. It was recorded to
explain the practical consequence of T-405's policy and was never executed from this repository.

That sequence completed in `documentation-orchestrator` itself between 2026-08-19 and 2026-08-22:
the bootstrap was performed and verified at the SHA above (its committed `DL-009`), the DOCFLOW-005
push lifecycle was recorded, DOCFLOW-006 was authorized, implemented and closed `Done`, the
completed baseline was reconciled, and DOCFLOW-007 became that repository's sole `Current` task. The
wording above is retained only as the historical record of what T-405 decided. It is not an
instruction to any future operator, and this contract issues no present-tense direction to
`documentation-orchestrator` and rewrites none of its history.

The repository's canonical task statuses are `Planned`, `Current`, and `Done`; there is no fourth
`Deferred` status. Consistent with the established `SUPERSEDED ≈ Done` administrative rule, T-405
moves `Current -> Done` as deferred/closed without successful implementation. Its zero-event
workflow history remains unchanged because the event state machine has no cancellation event and
no plan-review approval, implementation, review, commit, or push outcome occurred. This closeout
removes T-405 from the Current set, creates no replacement task, authorizes no successor, and
preserves T405-PR-001 through T405-PR-010 plus the complete regression/design record above as the
rationale for not pursuing implementation.

## 17. Human Owner ratification and evidence status — 2026-09-02

On 2026-09-02 the Human Owner ratified T-405 — its registration, its strict create-only policy
ruling, and its deferred closure `Current -> Done` without implementation — as a real governance
decision made on 2026-08-19. T-405 remains `Done`, the `Current` set remains empty, and no
replacement task, successor, or implementation authority is created. This contract remains
historical trust-boundary evidence and must not be implemented or resubmitted for plan review.

The ratification records this contract's evidence status truthfully rather than repairing it. A
read-only survey of committed history, the working tree, `~/.ai-workflow-engine/`, and the
`documentation-orchestrator` repository established:

| Item | Status |
|---|---|
| `scripts/workflow-authorize.sh` (GOV-AUTO-02) authorization-gate artifact for T-405 | `NOT_FOUND` — the gate was not used |
| Committed `authorize T-405` transition | `NOT_FOUND` — no commit in this repository mentions T-405 |
| `INTENTIONAL_POLICY` governed first-push bootstrap audit (cited in §1/§2 lineage) | `NOT_FOUND` |
| Plan-review round 1 artifact (T405-PR-001..004) | `NOT_FOUND / UNVERIFIABLE` |
| Plan-review round 2 artifact (T405-PR-005..006) | `NOT_FOUND / UNVERIFIABLE` |
| Plan-review round 3 artifact (T405-PR-007..010) | `NOT_FOUND / UNVERIFIABLE` |
| DOCFLOW-005 manual-bootstrap corroboration of the policy substance | `FOUND` |

Consequently, sections 15 and 16's narrative of three fresh independent `REJECTED /
PLAN_REMEDIATION_REQUIRED` reviews is retained as the authoring session's own account, not as
verified fact: no review file, prompt, agent run, or workflow event exists for any round. This
contract's zero workflow events prove nothing either way, because the engine's event store contains
no `ai-workflow-engine` project directory at all. Nothing in this section or anywhere in this
reconciliation fabricates a workflow event, a plan-review verdict, a prompt ID, or a run ID, and
nothing claims the missing artifacts existed or that the repository's normal authorization gate was
historically satisfied.

The substance of the decision *is* independently corroborated. This contract and its companion
governance files were written on 2026-08-19 between 21:50 and 21:54 and state that the bootstrap was
not executed here. At 22:57 the same day, DOCFLOW-005 event 8 recorded the Human Owner's manual
bootstrap "under recorded first-publication policy" at exactly the HEAD
`dced1783788c64ec0c97576ea5709b7e2dc27600` named in §16, and `documentation-orchestrator`'s
committed `DL-009` and `docs/CONTEXT.md` record the same act. The Human Owner enacted T-405's
replacement policy in a separate governed repository an hour after it was decided here. The DOCFLOW-005 evidence corroborates the substance of the
deferral/manual-bootstrap policy only. It does not prove, supply, or substitute for T-405's missing
authorization event, the missing `INTENTIONAL_POLICY` artifact, or any of the three missing
plan-review artifacts, which remain `NOT_FOUND` / `UNVERIFIABLE`.

This contract remains tracked in the repository because `docs/TASK_QUEUE.md`,
`docs/PROJECT_STATE.md`, `docs/DECISION_LOG.md`, and `handover/PROJECT_HANDOVER.md` each still refer
to it by path as T-405's contract; relocating it would leave those references dangling. Rationale:
`docs/DECISION_LOG.md`, 2026-09-02 entry.
