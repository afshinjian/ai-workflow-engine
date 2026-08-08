# Decision Log

Architectural decisions for `ai-workflow-engine`, newest first. Each entry records what was
decided, what alternatives were considered, and why — so a fresh session can understand *why*
the code looks the way it does, not just what it does. **This log is append-only, with exactly
one closed, non-repeatable exception**, on par with `docs/workflow-automation/STAGE_REGISTRY.md`
§5: an existing entry's text is never edited or deleted once written. The sole exception —
two specific, named, pre-protocol edits made on 2026-07-24 before this rule was stated in so many
words — is defined precisely, with its Human Owner basis, in the "append-only grandfathering
exception" entry below; no other edit, past or future, is covered by it. Every entry from that
one forward, including it, is append-only in fact. A wrong or incomplete entry is fixed only by
appending a new, dated entry that names what it corrects — a Governance Correction Record
(`docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 18) where the correction concerns an
AUTO-00x matter, or an equivalent plainly-labeled corrective entry otherwise.

## 2026-08-08 — Human Owner authorized DASH-005

**Decision:** The Human Owner typed the two exact `AUTHORIZE` confirmations for
`DASH-005`. The task moves `Planned → Current`; implementation remains separate.
The authorization was recorded from branch `main` at `1bfa860bf2583405e2e7e4caabef52ebff771f2e`.

**Boundaries:** This decision authorizes only the named task. It authorizes no successor,
push, merge, implementation approval, stash mutation, or automatic predecessor closure.

## 2026-08-02 — Human Owner approved and closed GOV-4

**Decision:** The Human Owner reviewed the implementation diff for `GOV-4` on branch
`fix/live-cli-test-isolation` and approved closure. Two pre-AUTO-013 live acceptance test-harness
defects are resolved, both test-only, in `agentos_workflow/tests/live/test_live_providers.py` and
`agentos_workflow/tests/test_provider_runtime.py`: (1) `_stage_ephemeral_claude_config_dir` makes
the configured Claude account directory a read-only authentication template, copying only
`.credentials.json` into a fresh per-invocation directory rather than forwarding the template
directly; (2) `run_live_claude_with_bounded_format_repair` bounds retry to exactly 3 attempts,
strictly limited to `FAILED`/`MALFORMED_OUTPUT`, each attempt isolated in its own ephemeral
config/session/repository directory. Evidence: two full `pytest -q -m live_cli -rs` runs at 32
passed/0 failed/0 skipped each; the authentication template byte- and mtime-identical before and
after every live run; zero `.claude-A` contamination; a new deterministic mocked test pinning
single-attempt malformed-output rejection unweakened; 3,470 tests green; `mypy` clean over 122
source files; `ruff`/`black`/pre-commit clean; `workflowctl verify` full PASS. No production code
was changed. Report: `docs/reports/GOV-4-completion-report.md`.

**Boundaries:** This decision approves and closes only `GOV-4`. It authorizes no successor
(including AUTO-013), does not push, merge, or open a PR, and does not begin AUTO-013.

## 2026-08-02 — Human Owner registered and authorized GOV-4

**Decision:** The Human Owner registered and authorized `GOV-4` — Isolate Claude live-test
configuration per attempt and add bounded test-only format retries — in one act, as an ordinary
(non-AUTO/GOV-AUTO-family) engine task record following the GOV-2/GOV-3 precedent rather than a
new AUTO or GOV-AUTO stage. The task moves directly to `Current`; implementation remains a
separate phase. This is a pre-AUTO-013 baseline-verification correction to the
`agentos_workflow` live acceptance test harness, discovered while verifying the AUTO-013 baseline:
(1) the live suite forwarded the configured Claude account's real, long-lived `CLAUDE_CONFIG_DIR`
to every invocation for an entire session, letting Claude Code's own client-side continuity state
accumulate and reproducing a real contract-violating failure; and (2), independently, real
Claude's compliance with the strict bare-JSON auto-mode contract is not deterministic on a single
attempt. The authorization was recorded from branch `main` at
`ce0f10775838bd9f20f3e02121600a9aa5dd68ed`.

**Boundaries:** This decision authorizes only the named task. It authorizes no successor
(including AUTO-013), no GOV-AUTO or AUTO stage, no production-code change, no parser weakening,
no push, merge, stash mutation, or automatic predecessor closure.

## 2026-08-01 — Human Owner authorized configurable approval gates (HUMAN_AUTHORIZATION_MODEL v2.0 §5a)

**Decision:** The Human Owner authorizes future workflow modes to define **configurable approval
gates**, governed exclusively by the `ApprovalService` subsystem delivered in AUTO-012.

**Why this needed its own decision.** `HUMAN_AUTHORIZATION_MODEL.md` v1.1 §1 stated that the
`CREATED → AUTHORIZED` transition is "the only human gate in this system" and that "no other point
in the workflow asks for or accepts human approval". Its §8 then classified adding *any* second
human-approval point as a MAJOR change requiring explicit Human Owner sign-off, "since it changes
the core safety property this program is built around". Building an approval subsystem without
first obtaining that sign-off would have contradicted the governing document while implementing the
thing it forbade. This entry, and §5a of that document (now v2.0), are the sign-off.

**Scope of the authorization:** the *subsystem* — typed policy, four-layer resolution, immutable
snapshot, durable append-only records, manual decisions, timeout decisions, checksum binding, and
invalidation. **Not** authorized: any specific Preparation, Reviewer, or Implementer workflow; the
placement of an approval gate at any particular point in any particular mode; and AUTO-013 or any
successor. A mode wanting a gate at a specific point needs its own separate authorization naming
that mode and that point.

**Constraints deliberately not relaxed,** each restated normatively in §5a: the founding
`CREATED → AUTHORIZED` gate and all of its bindings and invalidation conditions are unchanged, and
an approval is never a route to `AUTHORIZED`; an approval is evidence, not authority
(`AGENT_CONTRACTS.md` §1); an approval never substitutes for a deterministic machine gate, and no
admin-bypass path is created (`SECURITY_MODEL.md` §4); every approval is bound to the repository
state, diff, canonical agent result, and gate result it was granted against, and is invalidated if
any changes; an approval is single-use and cannot be replayed for another workflow or gate;
automatic approval is opt-in at the point of use and never acquired by inheritance; and no Model
Provider, Agent, or Skill may grant, decide, extend, or consume an approval.

**Alternatives considered and rejected.** *Implementing the subsystem and amending the document
afterwards* was rejected because it inverts the governance order the document itself sets, and the
whole value of a written single-gate property is that it is not amended silently by the code that
outgrows it. *Leaving §1 as written and treating approval gates as "not really human gates"* was
rejected as word-play: a policy that waits for a named human on a named channel and records who
decided is a human-approval point by any honest reading. *Authorizing specific gate placements now*
was rejected as premature — no mode exists yet, so any placement would be speculative, and the
directive explicitly forbids authorizing successor modes.

**A deliberate consequence:** `AUTO_APPROVE` exists and can, at a deadline, grant permission with
no human involved. It is confined by three things rather than by prose — it is refused unless the
specific gate or the run selected it, the resulting approval is still bound to the checksums
captured when it was requested, and the record states that the decision was automatic and which
timeout action produced it. An automatic approval is therefore never indistinguishable from a human
one in the audit trail.

## 2026-08-01 — Human Owner registered and authorized AUTO-012

**Decision:** The Human Owner registered and authorized AUTO-012 — Configurable Approval Policy,
Persistence, and Invalidation — in one written directive, as the single `Current` task on branch
`feature/auto-012-approval-policy`, created from clean, synchronized `main` at `e2b069c`. AUTO-012
had never been registered before, so registration and authorization are one act.

**Scope decided:** the reusable approval subsystem reached as
`WorkflowService → ApprovalService`, with policy resolution, request persistence, manual decisions,
timeout decisions, checksum binding, and invalidation. It implements no workflow mode and executes
no provider as part of an approval.

**Design decisions taken under it, and the alternatives rejected.**

*Events plus replay, not a mutable record.* An approval is an append-only sequence of
`ApprovalEvent`s and the current `ApprovalRequest` is derived by replaying them. Storing a single
mutable record and updating it in place was rejected: the requirement is that no decision is ever
overwritten and no historical record mutated, and with an editable row that is a promise, whereas
with append-only events it is a property of the file format — there is no code path that rewrites a
line because the only write is an append. This mirrors what `StateStore` already does for
transitions and what `WorkflowStatus` already does for state.

*No new workflow states.* The directive permitted adding `AWAITING_APPROVAL`,
`APPROVAL_TIMED_OUT`, and `HUMAN_INTERVENTION_REQUIRED` to the runtime state machine but preferred
none if the subsystem could be built without them. It can, so none were added. Adding them would
have required new edges in `ALLOWED_TRANSITIONS` that nothing in this stage could ever produce —
AUTO-012 implements no lifecycle — leaving unreachable states and untested edges in the safety-
critical core the same directive says not to refactor. Approval status lives on `ApprovalStatus`,
inside the subsystem that owns it, which also satisfies the rule that workflow states must not
duplicate policy logic. The stage that first *consumes* an approval is the one with the evidence to
choose the right states.

*Reuse `StateStore`, extend it by two methods.* `record_approval`/`read_approvals` were added to
`StateStore` rather than reimplementing persistence in the approval module or reaching into that
module's private helpers. Both alternatives were rejected: a second persistence framework is
explicitly prohibited and would drift from the original, and importing another module's private
functions is the same coupling without the type safety. The two methods are deliberately generic in
the record type, because the approval vocabulary is built *on* the store and naming it there would
invert the dependency into an import cycle.

*`required=False` refuses rather than auto-satisfies.* A gate whose policy says approval is not
required cannot have one requested. Returning a pre-approved record instead was rejected because it
would be automatic approval without the explicit opt-in the same stage is required to enforce.

**Stop condition:** implementation and validation only; no implementation/closeout commit, no push,
no PR, no merge, and no AUTO-013 work.

## 2026-08-01 — Human Owner approved and closed AUTO-011

**Decision:** The Human Owner approved AUTO-011 — Unified Provider and Agent Result Contract — for
finalization on branch `feature/auto-011-agent-result-contract` (base `fd0b34f`), required a final
fourteen-point scope, contract, and compatibility verification before any commit, and authorized
the implementation and closeout commit plus the push. **All fourteen checks passed.** No pull
request and no merge were authorized.

**What was verified:** the canonical field set with no speculative successor fields; the four-status
contract; every status invariant including `COMPLETED` rejecting both failure data and blocking
issues, and unknown statuses rejected; `status` and `final_verdict` still semantically distinct;
`recommended_next_state` advisory only and unable to mutate state, authorize a transition, invoke
an agent/provider/skill, or bypass deterministic validation; the adapter preserving every AUTO-010
result and failure classification; the single documented normalization; deterministic, strict,
duplicate-key-rejecting, round-trip-safe, timezone-aware, immutable, secret-redacted serialization;
artifacts as references with unsafe paths refused; no change to any provider, process-runner,
service, CLI, agent, skill, state-machine, configuration, Git, GitHub, or shell behaviour; AUTO-010
provider-runtime and live CLI tests unchanged and passing; every deferred finding still deferred;
AUTO-012 untouched; and no debug code, TODO, FIXME, skip, xfail, temporary workaround,
commented-out implementation, or unrelated refactor.

**One deviation recorded rather than hidden:** `AgentRunResult` carries a nineteenth field,
`session_id`, beyond the eighteen the contract enumerated. It is not speculative and not successor
behaviour — it is the invocation's audit identity, populated today from
`ProviderRunResult.session_id`, and it is what ties a result to the isolated session directory
holding its evidence. Artifact references give paths; only this gives identity. Disclosed in the
completion report's §5 and §1 and accepted.

**Decided not to collapse D-3.** AUTO-010 deferred the overlap between `ProviderReport.verdict` and
`ProviderReport.status` *to* AUTO-011, and AUTO-011 deliberately did not merge them. They answer
different questions: a `COMPLETED` run reporting `fail` is a QA provider finding real defects — a
successful execution with a failing verdict — and collapsing the axes would destroy that
distinction. What the stage removed is the ambiguity, by giving each axis one canonical type and one
documented meaning; what it did not do is delete a field from `ProviderReport`, which would have
modified AUTO-010. D-3 therefore remains recorded as deferred rather than being claimed resolved.

**Provenance note:** the approval was given in conversation and the closeout performed manually, not
through `scripts/workflow-approve.sh` — no scripted `APPROVE` confirmations were typed, and none
were supplied by the session.

**Three new defects deferred, none fixed:** D-8 (`ProviderRunResult` permits `COMPLETED` alongside
blocking issues), D-9 (an output-limit breach is not distinguishable by failure kind), and D-10 (the
canonical result's enum imports invite a future `agents -> results -> agents` cycle). Each is
recorded and classified in the completion report; none was implemented and no GOV stage was created
for any of them. Closing AUTO-011 authorizes no successor.

## 2026-08-01 — Human Owner registered and authorized AUTO-011

**Decision:** The Human Owner registered and authorized AUTO-011 — Unified Provider and Agent
Result Contract — in one written directive, as the single `Current` task on branch
`feature/auto-011-agent-result-contract`, created from clean, synchronized `main` at `fd0b34f`.
AUTO-011 had never been registered before, so registration and authorization are one act. The
directive first authorized publication of AUTO-010 (PR #10, merged `fd0b34f`), which is what made
AUTO-011's "predecessor merged and published" precondition true.

**Scope decided:** one canonical `AgentRunResult` for provider and agent execution, reached as
`WorkflowService -> Provider Runtime -> Canonical AgentRunResult`. It becomes the canonical result
contract for future Claude execution, Codex execution, internal agents, and the
Preparation/Reviewer/Implementer Modes — **without implementing any of them**. The stage
standardizes results and adds no workflow mode, lifecycle, or state transition.

**Alternatives considered and rejected.** *Declaring a fresh status enum, verdict, and failure type
for the canonical result* was rejected: AUTO-010 already ships `ProviderRunStatus` (the same four
terminal statuses), `ProviderVerdict`, `ProviderFailure`, and `ProviderKind`, and a parallel set
would create two answers to the same question and a mapping between them that could drift. The
canonical model therefore reuses those four and adds only what none of them expresses — execution
mode, agent identity, artifact references, and the advisory next state. *Changing
`ProviderRunResult` into the canonical model in place* was rejected because it would break
AUTO-010's boundary, which the directive requires to keep working unchanged; adapters are used
instead. *Deleting or migrating the legacy `AgentReport` under `src/ai_workflow_engine`* was
rejected as out of scope — no legacy result model is removed in this stage.

**Authority rule decided:** `recommended_next_state` is advisory only. It never mutates workflow
state, authorizes a transition, bypasses the Orchestrator, or substitutes for deterministic
validation. This preserves `AGENT_CONTRACTS.md` §1 and `ARCHITECTURE.md` §6 — an agent reports, the
Orchestrator decides — while still letting a result carry the producer's own read of what should
happen next, which an operator and a future Orchestrator both benefit from seeing. Tests must prove
no transition depends on the field.

**Prohibited:** Preparation/Reviewer/Implementer Mode; workflow authorization, approval, or
approval timeouts; task scheduling; workflow start, resume, or cancellation; Claude-Codex
coordination; Codex direct correction; Git commit/push automation; PR creation; CI polling; merge;
branch cleanup; Python governance closeout; daemon; Telegram; AUTO-012 or any successor. No
workflow state-machine change, no Git/GitHub skill registration change, no shell-script
modification, and no change to existing `workflowctl auto` behaviour or output.

**Stop condition:** implementation and validation only; no implementation/closeout commit, no push,
no PR, no merge, and no AUTO-012 work. Authorizing AUTO-011 authorizes no successor.

## 2026-07-31 — Human Owner approved and closed AUTO-010

**Decision:** The Human Owner approved AUTO-010 — Real Non-Interactive Provider Runtime — for
finalization on branch `feature/auto-010-provider-runtime` (base `5d1b6be`), required a final
fourteen-point scope, runtime, and safety verification before any commit, and authorized the
implementation/closeout commit and the push of that branch. All fourteen checks passed. **No PR and
no merge were authorized**, and AUTO-011 was explicitly not authorized.

**Provenance (recorded precisely rather than in the script's stock wording):** the approval was
given in conversation and the closeout was performed **manually**, not through
`scripts/workflow-approve.sh`. That script requires the Human Owner to type two exact `APPROVE`
confirmations interactively; no such confirmations were typed, and the session did not and must not
supply them on the Human Owner's behalf. The same manual path was used for GOV-AUTO-07's closure on
2026-07-31 for the same reason.

**What was decided, and why it looks the way it does.** Three choices are worth recording because a
later session would otherwise be tempted to undo them:

1. **The public request carries a `task`, never a `prompt`.** `CLIProvider.invoke` takes a fully
   formed prompt, which is right for the layer that runs a process and wrong for a public API: a
   caller who writes the whole prompt can omit the never-ask clauses, making the strongest of the
   three enforcement layers optional. The runtime therefore supplies the contract and the caller
   supplies only the task, so a provider prompt without the contract is unrepresentable.
2. **The unrestricted CLI modes are absent from the enums rather than rejected by a validator.**
   `bypassPermissions` and `danger-full-access` are not values the engine refuses and then
   discusses; they are values no configuration, request, or call site can name, because
   configuration is typed to `ClaudePermissionMode`/`CodexSandboxMode` and the adapters build argv
   from them. Those enums live in `agentos_workflow/config/policy.py` — a leaf module importing
   nothing from this engine — because the configuration schema and the adapters both need them and
   any home under `providers/` would make the schema import its own importer.
3. **Account selection is an allowlisted environment variable, never a shell alias.** The host's
   `codexA`/`claudeA` aliases expand to `CODEX_HOME=... codex`. An alias is a shell construct that a
   `shell=False`, fixed-argv spawn cannot see or expand, so configuring one as an executable fails
   at spawn — a fact now pinned by a test. What the alias actually does, setting one environment
   variable, is exactly what the existing provider environment allowlist already expresses.

**Blockers fixed (three, all inside the shared process runner, each minimal and each documented):**
`subprocess.run`'s timeout killed only the direct child and left the parent's controlling terminal
attached; output ceilings were unenforced during capture and stderr had none; and AUTO-004's Codex
parser took the last JSON object on stdout, which in a real run is always a `turn.*` envelope and
never the report — so that adapter could not have worked against the live CLI and was never
exercised against one until now.

**A correction recorded for its own sake.** The first validation pass concluded that the installed
Codex credential was expired. That was a misdiagnosis: the engine had allowlisted only `HOME`, so
Codex fell back to the default credential store. The account was never selected. The completion
report preserves the original failed attempt and its wrong conclusion verbatim, with the correction
appended (§22), because a report that quietly replaces a wrong diagnosis teaches nothing.

**Evidence:** 3,241 tests passing (3,151 + 90, none skipped, none xfail) plus 25 live acceptance
tests against the real installed CLIs with zero skips; `mypy --strict` clean over 120 source files;
`ruff`, `black`, and pre-commit clean; wheel carrying every new module; nine existing `workflowctl`
invocations byte-identical to the `5d1b6be` baseline. Registry state `IN_PROGRESS -> COMPLETE`;
task status `Current -> Done`. Report:
`docs/reports/workflow-automation/AUTO-010-completion-report.md`.

## 2026-07-30 — Human Owner approved and closed DASH-004

**Decision:** The Human Owner reviewed the implementation diff for `DASH-004` on
branch `feature/dash-004-dashboard-shell` at base `8dba9c57802073e14f63d1c859dd878096d03709`, typed the two exact `APPROVE` confirmations
required by `scripts/workflow-approve.sh`, and approved the Conventional Commit
message `feat(dashboard): add local dashboard shell with security baseline (DASH-004)`. The script then performed the deterministic governance closeout
(`DASH-004` moves `Current -> Done`) and staged the approved implementation
together with the generated closeout records in one local commit.

**Boundaries:** This decision approves and closes only `DASH-004`. It does not
push, merge, authorize a successor task, change branches, alter upstream, or mutate
stashes.

## 2026-07-31 — Human Owner approved and closed AUTO-009

**Decision:** The Human Owner approved AUTO-009 for finalization and required a final twelve-point
scope, API, and read-only integrity verification before any commit. All twelve passed, and the
Human Owner authorized the implementation and closeout commit and the push of
`feature/auto-009-workflow-service`. Registry state moves `IN_PROGRESS -> COMPLETE`; task status
moves `Current -> Done`.

**What was verified, and how.** The read-only claim was not accepted on inspection. Every mutation
channel the service could conceivably reach was replaced with a function that raises —
`RepositoryLock.acquire`, `__enter__`, and `release`; `subprocess.run` and `Popen`; `os.system`,
`os.fork`, and `os.posix_spawn`; `StateStore.record_transition` and `record_command_execution`; and
all six `skills.reporting` writers — and all six operation invocations completed without reaching
any of them. In the same run, a digest over every path, mode, mtime, and byte under the state
directory, the audit directory, *and the target repository* was identical before and after each
operation. AST assertions confirm the service module imports no lock or session symbol and calls no
write method. Compatibility was proven by byte-comparing fourteen existing command invocations
against a worktree at the `98acc195` baseline: thirteen identical; the fourteenth, `workflowctl
--help`, gains the intended `auto` group and nothing else.

**Two design calls the Human Owner accepted rather than deferred.** (A3) `auto audit` returns the
two record schemas `AUDIT_MODEL.md` sections 2-3 define and deliberately excludes the Skill-level
`audit.jsonl` event log, whose events are free-form dicts that would have weakened the typed-result
guarantee; the gap is recorded as deferred defect D4 and becomes real only once the Orchestrator
emits Skill events in a live run. (A4) `WorkflowNotFoundError` and `ReportNotFoundError` were added
rather than reusing `MissingPersistedStateError`, because that and its siblings are `ResumeError`
subclasses whose meaning is bound to resuming a workflow — reusing one would have made a read
report a resume attempt that never happened. Both new errors inherit only from
`WorkflowServiceError`, and their CLI mapping is identical to that of a pre-existing operational
error: exit 2 with `ERROR: ` on stderr and empty stdout under contract v1, exit 1 with a single
error envelope on stdout and empty stderr under v2.

**Alternatives considered:** committing the registration and the implementation as one commit. Two
were used instead, following the GOV-AUTO-06 and GOV-AUTO-07 precedent, so that the authorization
record exists as a commit that contains no implementation and cannot be read as having been written
after the fact.

**Boundaries:** This decision approves, closes, and publishes only AUTO-009, and publication means
pushing the stage branch — **no PR was opened and no merge was performed**. It authorizes no
successor: AUTO-010 and every later roadmap phase remain unauthorized. The six non-blocking defects
AUTO-009 recorded (D1-D6) remain deferred and explicitly unauthorized to fix; none was touched.

## 2026-07-31 — Human Owner registered and authorized AUTO-009

**Decision:** The Human Owner registered and authorized `AUTO-009 — WorkflowService boundary and
read-only workflowctl auto surface` as the single `Current` task, in one written directive that
named the stage, its target architecture, its required public boundary, its required CLI surface,
its strictly prohibited behaviours, its validation set, and its stop condition. AUTO-009 had never
been registered before, so the registration and the authorization are the same act, exactly as
AUTO-008's were.

**What the stage builds:** one application-service façade, `agentos_workflow.service
.WorkflowService`, with exactly four read-only operations — `status`, `list`, `audit`, `report` —
returning typed results over the *existing* AgentOS state, audit, report, and configuration
components; plus `agentos_workflow.cli_auto`, an additive Typer sub-application registered as
`workflowctl auto`. The dependency direction is fixed: `workflowctl auto -> WorkflowService ->
agentos_workflow read-only APIs`, and `src/ai_workflow_engine/cli.py` reaches AgentOS through
exactly one name (`agentos_workflow.cli_auto.auto_app`) rather than importing AgentOS internals
throughout the legacy CLI.

**Alternatives considered:** (a) exposing the AgentOS orchestrator directly to `workflowctl`,
rejected because it would make every future CLI change a change to the engine's internals and
would put a write-capable `WorkflowSession` one attribute access away from a read-only command;
(b) building the read-only surface as a second, parallel reader over the on-disk JSONL layout,
rejected because it would duplicate the descriptor-relative `O_NOFOLLOW` path-confinement
discipline that `state_store.py` and `skills/reporting.py` already own, and two copies of a
confinement rule are two rules that can drift apart.

**Rationale:** The engine has had a state machine, persistence, skills, providers, and agents since
AUTO-002..AUTO-006, but no public boundary at which any of it can be *observed*. Starting that
boundary with a read-only surface means the first thing the façade proves is that it cannot mutate
anything — no write lock, no state transition, no agent execution, no Git or GitHub mutation — so
the write-capable operations, when they are separately authorized, are added to a boundary whose
read path is already tested rather than to a blank file.

**Boundaries:** This decision authorizes only AUTO-009's implementation and validation. It
explicitly withholds the implementation/closeout commit, the push, the PR, the merge, and
AUTO-010 or any successor behaviour, and it forbids fixing unrelated defects: a newly discovered
defect is fixed in this stage only if it provably blocks AUTO-009 and no scope-preserving
workaround exists; every other one is recorded, classified, and deferred.

## 2026-07-31 — Human Owner approved and closed GOV-AUTO-07

**Decision:** The Human Owner required a final eight-point verification of the candidate
implementation — convention consistency, changed-site relevance, behaviour invariance, public-surface
compatibility, the cross-record checks, regression-test genuineness, untouched prohibited surfaces,
and residue — all of which passed, then approved GOV-AUTO-07 and authorized its implementation and
closeout commit and the push of `feature/gov-auto-07-drift-argument-convention`. Registry state has
no lifecycle entry for this task (see below); task status moves `Current → Done`.

**What the fix establishes.** `AuthorizationBindingDriftError` now documents, and every one of its
43 raise/helper call sites obeys, a single convention: `expected` is the authorization-bound value
where the comparison has one, otherwise the invariant the check requires; `actual` is the current
runtime, repository, live-observation, or caller/disk-supplied value judged against it. Where a
persisted `AuthorizationRecord` is one side of a comparison it is always `expected` — the human
authorization is the root of trust and is never reported as the thing that was "found".

**Scope decision worth recording — a third inversion beyond the two F-1 named.** F-1 identified two
mutually inverted paths (`_detect_authorization_binding_drift` and `_validate_live_resume_observation`).
Inspection found a third instance in `_validate_persisted_authorization_evidence`, whose four
cross-record checks reported the persisted `AuthorizationRecord` as `actual`. AUTO-008's audit had
classified these as conforming under its weaker "required/reference value" framing; they are
inverted under the stricter convention this stage was directed to establish. They were included,
because leaving them would have reproduced in a third place exactly the ambiguity F-1 exists to
remove and would have made the convention unstateable as a rule. This was flagged explicitly in the
report as a judgement call beyond the finding's literal wording, and remains independently
reversible — four one-line argument swaps with dedicated tests.

**Deliberately not changed.** The rendered message keeps AUTO-008's "expected …, found …" wording
rather than re-adopting "bound value / current value": with the convention uniform that labelling
would finally be correct on the bound-vs-current paths, but not at the sites where neither side is a
binding, where it would substitute a new falsehood for the old one. `AuthorizationScopeMismatchError`
was left untouched — a different exception for a different condition, whose message names its own
sides explicitly and is therefore already unambiguous.

**Evidence:** 3,005 tests passing (2,978 + 27 new, none skipped, deleted, or `xfail`ed); the new
suite fails 17 of its 27 tests against the stashed pre-fix engine, and the 10 that pass are exactly
the already-conforming sites — which independently confirms those were not disturbed. The only
pre-existing test that broke was AUTO-008's own message pin. `mypy --strict` clean over 115 source
files; `ruff`, `black`, and `pre-commit` clean. Every comparison is symmetric, so drift detection,
ordering, and the durable `-> FAILED` consequence are unchanged.

**Provenance note:** approval was given directly in session and the closeout was performed manually,
not through `scripts/workflow-approve.sh` — that script requires the Human Owner to type two exact
`APPROVE` confirmations interactively, which the implementation agent must not supply on the Human
Owner's behalf. The document set and commit structure match what the script produces.

**Boundaries:** This closure authorizes no successor. AUTO-009 and every later roadmap phase require
their own fresh written authorization. No PR was opened and no merge was performed.

## 2026-07-31 — Human Owner registered and authorized GOV-AUTO-07

**Decision:** The Human Owner registered and authorized `GOV-AUTO-07 — Normalize the
AuthorizationBindingDriftError expected/actual convention`, to resolve the F-1 finding AUTO-008
reported and deliberately left unfixed. The task becomes the single `Current` task; implementation
remains separate. Recorded from branch `feature/gov-auto-07-drift-argument-convention`, created
from clean `main` at `d8d10ec54c38571f6a4453a11d0e99c53d151743`.

**Why this stage exists (F-1).** `AuthorizationBindingDriftError(field, expected, actual)` is
raised from two authorization-drift call paths that pass those two arguments in opposite senses:
`_detect_authorization_binding_drift` passes the independently-supplied *current* value as
`expected` and the persisted `AuthorizationRecord` as `actual`;
`_validate_live_resume_observation` / `_live_drift` passes the persisted record as `expected` and
the *live observation* as `actual`. AUTO-008 discovered this while fixing the error's inverted
message and could only neutralize the wording — no fixed "bound value X / current value Y" text is
correct at both sites. The consequence is that `.expected` and `.actual` mean opposite things
depending on which safety path raised, on the primary authorization-invalidation path.

**Task identifier.** `GOV-AUTO-07` resolves under the governance parser
(`src/ai_workflow_engine/governance/parser.py`, `TASK_ID = re.compile(r"\b([A-Za-z]+-\d+)\b")`) to
`AUTO-07`, which is unused; it continues the GOV-AUTO-01..06 convention for narrowly-scoped
follow-up fixes outside the AUTO family. An `AUTO-008-F1`-style identifier is unusable for the same
reason recorded for GOV-AUTO-06: the parser would resolve it to the existing `Done` task
`AUTO-008`.

**Boundaries:** Authorizes only the F-1 fix — defining one canonical `expected`/`actual`
convention, normalizing the raise sites to it, and adding regression tests for every affected drift
path. The public attribute names `field`, `expected`, and `actual` are preserved. It authorizes no
new feature, no new public interface, no change to workflow transitions, Git/GitHub skill
registration, the public CLI, shell scripts, or any other exception type; and it does not authorize
the cleanup of the end-to-end dry run's redundant manual Skill bindings. It does not authorize
AUTO-009 or any successor.

## 2026-07-30 — Human Owner approved and closed GOV-AUTO-06

**Decision:** The Human Owner required a final seven-point scope and integrity verification, and on
its outcome approved GOV-AUTO-06 and authorized the closeout commit and push. Task status moves
`Current → Done`.

**Verification outcome.** All seven checks passed: changes strictly within GOV-AUTO-06;
`AGENT_SKILL_CONTRACTS` AST-identical to its prior value; all eight delivered Git/GitHub Skills
present in `default_skill_registry()` and identity-verified against `skills/git_github.py`;
`PROVISIONAL_SKILL_NAMES` empty but retained as a public symbol in `__all__`; no test-only manual
binding and no unrelated end-to-end cleanup; `orchestrator/` untouched, so F-1 and AUTO-009 are
unaffected; and no debug code, workaround, TODO, skipped test, or commented-out implementation.

**Two decisions inside the fix worth recording**, because each preserved behaviour that a narrower
reading would have silently changed:

1. `PROVISIONAL_SKILL_NAMES` was emptied rather than deleted. The stale part was its membership,
   not the concept — a contract may legitimately name a Skill before its implementing stage lands,
   and answering that with a typed `PRECONDITION` failure rather than a `CapabilityViolation` is
   the right distinction. Deleting the name would also have removed a public symbol from `__all__`.
2. `GitAgent._is_unbound` was widened to match both of the broker's no-binding answers. With the
   provisional set empty, the previous form — which required membership plus the literal string
   `AUTO-006` — would have silently reclassified every missing binding from `SKILL_UNAVAILABLE` to
   `SKILL_FAILED`, a behaviour change well beyond binding the Skills.

**Boundaries:** This closure authorizes no successor. F-1 (the `expected`/`actual` convention
divergence across the `AuthorizationBindingDriftError` raise sites), AUTO-009, and every later
roadmap phase remain unauthorized and require their own fresh written authorization. The
end-to-end dry run's hand-registration of the eight Skills was deliberately left in place: it is
outside this task's defect and is now provably redundant rather than load-bearing.

## 2026-07-30 — Human Owner registered and authorized GOV-AUTO-06

**Decision:** The Human Owner registered and authorized `GOV-AUTO-06 — Bind delivered Git/GitHub
skills into the default AgentOS skill registry`, to resolve the F-2 finding AUTO-008 reported and
deliberately left unfixed. The task becomes the single `Current` task; implementation remains
separate. Recorded from branch `feature/auto-008-f2-bind-github-skills`, created from clean `main`
at `2c8844c4e2c3f78271743b41e4f489155169e5d0`.

**Task identifier — deviation from the requested ID, and why.** The Human Owner proposed the ID
`AUTO-008-F2`. That identifier cannot be used: the governance parser
(`src/ai_workflow_engine/governance/parser.py`, `TASK_ID = re.compile(r"\b([A-Za-z]+-\d+)\b")`)
resolves `AUTO-008-F2` to `AUTO-008`, which is an existing `Done` task. A queue heading under that
ID would register a second, `Current` AUTO-008, breaking `check-task-state` (mirror disagreement)
and `check-registries` (registry says `COMPLETE`/`Done`, queue would say `Current`). `GOV-AUTO-06`
was chosen instead: it resolves to `AUTO-06`, which is unused, and it matches the established
convention for narrowly-scoped follow-up fixes outside the AUTO family (GOV-AUTO-01..05). The
Human Owner's recommended branch name, `feature/auto-008-f2-bind-github-skills`, is kept unchanged
— GOV tasks have no registered-branch constraint, so the branch name carries the requested
`auto-008-f2` label while the governed task ID stays parseable.

**Boundaries:** Authorizes only the F-2 fix — removing the stale provisional classification for the
eight genuinely-implemented Git/GitHub Skills and binding the existing implementations into the
production registry. It authorizes no new GitHub feature, no new public interface, no change to
agent capability contracts, `CapabilityBroker` enforcement, environment allowlist rules, or
workflow state-machine behaviour. It does not authorize F-1, AUTO-009, or any successor.

## 2026-07-30 — Human Owner approved and closed AUTO-008

**Decision:** The Human Owner reviewed the AUTO-008 implementation report, required an explicit
scope and cleanliness verification first, and on its outcome approved the implementation and
authorized governance closure plus the commit and push sequence. Registry state moves
`AUTHORIZED → COMPLETE`; task status moves `Current → Done`.

**What the closing verification changed.** The pre-approval verification the Human Owner required
found two defects in the candidate implementation, both self-inflicted and both corrected before
commit:

1. `live_cli`/`live_gh` pytest markers and a CI `-m "not live_cli and not live_gh"` filter had been
   added. No test carried either marker, so they were anticipatory infrastructure for AUTO-010 with
   no current consumer, and the `-m` filter was a behavioural change to CI beyond this stage's
   objective. Both were removed; the CI test command is byte-unchanged from baseline.
2. The new engine-version test contained a tautological assertion — given its own first assertion,
   the compound expression could never fail — plus an unnecessary conditional `pytest.skip`. It was
   rewritten to parse `observation/local.py`'s AST and assert the module imports no distribution
   metadata at all, which pins the decoupling structurally rather than comparing two values that
   may legitimately coincide later.

Recording this because the verification step earned its place: both defects would have shipped.

**Deliberately not fixed, and reported instead:** the eight AUTO-006 Git/GitHub Skills remain
unbound in `default_skill_registry()` (F-2 — REQUIRED before a first real run, since `GitAgent` and
`MergeAgent` cannot function with the default registry), and the `expected`/`actual` parameter
convention still diverges between the two `AuthorizationBindingDriftError` raise sites (F-1 —
RECOMMENDED). Both change behaviour beyond this stage's scope.

**Boundaries:** This closure authorizes no successor. AUTO-009 and every later roadmap phase
require their own fresh written authorization.

## 2026-07-30 — Human Owner registered and authorized AUTO-008

**Decision:** Following an architectural audit of this repository, the Human Owner registered and
authorized `AUTO-008 — Engine CI baseline` in one act. AUTO-008 did not previously exist in the
task queue or stage registry, so this decision records both its registration and its
authorization. The task becomes the single `Current` task; implementation remains separate. The
authorization was recorded from branch `feature/auto-008-engine-ci-baseline`, created from clean
`main` at `96a6bb4e7534008cf9516829df7db58fb79b1c50`.

**Why this stage exists:** the audit established that `agentos_workflow` — the AUTO-001..007
orchestrator, ~52k lines with 1,575 tests — has never run as a program and is verified by no
automated gate. It has no `cli.py`, no `.agentos/workflow.yaml`, is absent from the wheel
`packages` list, is not importable outside the repository root, is not type-checked, and its tests
were never collected by CI (1,803 of the repository's 2,963 tests, 61%, ran nowhere). Its single
end-to-end acceptance demonstration (`MVP_SCOPE.md` §4) fails on `main`. "AUTO-001..007 COMPLETE"
therefore did not mean "works". AUTO-008 closes that gap before any further capability is built on
the engine.

**Boundaries:** This decision authorizes only AUTO-008, scoped to making the existing engine
verifiable. It authorizes no new feature or public interface, no change to
`src/ai_workflow_engine/**` or `scripts/**`, no real Claude/Codex/GitHub invocation, and no
successor, push, merge, implementation approval, or stash mutation.

**Related publication:** in the same session, and separately authorized, the Human Owner directed
that DASH-004's implementation commit `96a6bb4` be published to `main` by fast-forward. DASH-004
was recorded `Done` while its code sat unmerged on its feature branch, so `main` did not match
governance; the fast-forward reconciled them.

## 2026-07-30 — Human Owner authorized DASH-004

**Decision:** The Human Owner typed the two exact `AUTHORIZE` confirmations for
`DASH-004`. The task moves `Planned → Current`; implementation remains separate.
The authorization was recorded from branch `main` at `e1817372e5b11500839bcae4b51666b19c804f57`.

**Boundaries:** This decision authorizes only the named task. It authorizes no successor,
push, merge, implementation approval, stash mutation, or automatic predecessor closure.

## 2026-07-30 — Human Owner approved and closed GOV-AUTO-05

**Decision:** The Human Owner reviewed the implementation diff for `GOV-AUTO-05` on
branch `main` at base `528449eda944e16a1f6889651402fb426f502336`, typed the two exact `APPROVE` confirmations
required by `scripts/workflow-approve.sh`, and approved the Conventional Commit
message `fix(workflow): avoid resolved blocker false positives (GOV-AUTO-05)`. The script then performed the deterministic governance closeout
(`GOV-AUTO-05` moves `Current -> Done`) and staged the approved implementation
together with the generated closeout records in one local commit.

**Boundaries:** This decision approves and closes only `GOV-AUTO-05`. It does not
push, merge, authorize a successor task, change branches, alter upstream, or mutate
stashes.

## 2026-07-30 — Human Owner exception-authorized GOV-AUTO-05

**Decision:** The Human Owner explicitly authorized implementation of GOV-AUTO-05 despite the
known false-positive defect in `scripts/workflow-authorize.sh`. This is a one-time governance
exception because the normal authorization gate could not authorize GOV-AUTO-05 without first
applying the parser fix GOV-AUTO-05 exists to implement. The authoritative task and mirrors
record the manual `Planned → Current` transition so the later approval gate can close the task
normally; no authorization-only commit was created.

**Implementation decision:** The task status is the first non-blank, whole canonical status-field
line after its exact task heading. Later quoted examples, Markdown emphasis, acceptance criteria,
fenced examples, or explanatory prose have no lifecycle meaning. Explicit canonical
`Status: Blocked` remains a refusal. For registry-governed tasks, only structured unresolved
blocker entries under `OPEN_QUESTIONS.md`'s `## Open` section are authoritative; resolved entries
and negated or historical wording do not refuse authorization.

**Approval-gate addendum:** Before approval, the Human Owner reproduced the identical broad-scan
defect in `scripts/workflow-approve.sh`. GOV-AUTO-05 therefore also applies the canonical-field
rule to approval-side Current-task discovery, mirror reading, guarded `Current → Done`
replacement, post-closeout status extraction, and next-Planned reporting. Canonical Blocked still
refuses atomically; status examples later in the task section do not. This is remediation of the
same authorized defect, not a new task or expanded approval capability.

**Boundaries:** The exception authorizes only GOV-AUTO-05's registered implementation, tests,
validation, bounded self-review, report, and permitted governance/handover updates. It does not
authorize another task, push, merge, branch creation or switching, rebase, reset, amend, force or
history rewriting, or stash operation. The completed work remains uncommitted for separate Human
Owner approval.

## 2026-07-30 — GOV-AUTO-05 registered as `Planned`

**Decision:** The Human Owner directed registration of
`GOV-AUTO-05 — Fix resolved-blocker false positives in authorization` so an already-prepared
patch can later pass through the normal authorization and approval workflow. The task is
registered as `Planned`, non-AUTO-family, with no structured AUTO/DASH stage-registry row.

**Contract:** A later authorized implementation may change `scripts/workflow-authorize.sh` and
its workflow-focused tests so explicit `Status: Blocked` and active unresolved open questions
still refuse, while only the `## Open` section is authoritative and resolved, negated, or
historical blocker wording does not refuse. Existing predecessor, registry, branch, dirty-tree,
and Human confirmation checks remain unchanged. The detailed scope, allowed paths, exclusions,
and acceptance criteria are authoritative in `docs/TASK_QUEUE.md`.

**Boundaries:** This decision registers only GOV-AUTO-05. It does not apply the prepared patch,
implement or authorize the task, make it `Current`, create or switch a branch, or authorize any
push, merge, rebase, reset, stash, or other repository operation beyond the single local
governance-registration commit.

## 2026-07-29 — OD-D9 resolved: the dashboard serving stack is FastAPI + Uvicorn + Jinja2, in an optional `dashboard` dependency group

**Decision:** The Human Owner resolved OD-D9 (`docs/agentos-dashboard/OPEN_QUESTIONS.md`), the
last open question in the Dashboard register. The AgentOS Dashboard's serving layer is
**FastAPI** (local HTTP application framework), **Uvicorn** (ASGI server), and **Jinja2**
(server-rendered HTML templates). These are declared in a **new optional dependency group named
`dashboard`** in `pyproject.toml` — `fastapi>=0.111,<1`, `jinja2>=3.1,<4`, `uvicorn>=0.30,<1`,
following this repository's existing lower-bound-plus-next-major convention. The default/core
`ai-workflow-engine` installation stays free of every dashboard-serving dependency:
`[project].dependencies` is unchanged, so `pip install ai-workflow-engine` still installs no web
framework. Stdlib `http.server` is explicitly **not** the primary implementation. DASH-004 and
later dashboard stages may use only the three distributions in this group unless separately
authorized. Full rationale: `docs/agentos-dashboard/DECISIONS.md` DD-09.

**Alternatives considered:** (a) Stdlib-only serving on `http.server` — the fallback OD-D9's own
recommendation named if the Human Owner declined any new dependency. Rejected: it would mean
hand-rolling routing, request parsing, header/CSRF middleware, and template escaping — the code
most likely to carry a security defect — to avoid three widely-audited distributions the optional
group already keeps out of the engine's install. (b) A standalone requirements file outside the
packaged project, the other placement OD-D9 offered. Rejected: it would put the dashboard's
dependency set outside the one file `workflowctl check-governance` already cross-checks and
outside normal `pip install -e '.[extra]'` handling. (c) Adding the stack to
`[project].dependencies`. Rejected outright: it would give the audited, deliberately lean CLI
engine a web-framework dependency it never serves anything with.

**Security boundary:** unchanged. The dashboard binds loopback-only by default
(`docs/agentos-dashboard/SECURITY_MODEL.md` SC-01..SC-05; `ARCHITECTURE.md` §5); this decision
selects an implementation, it does not widen exposure. Remote exposure, authentication, TLS, and
any production deployment posture remain out of scope and require their own decisions. The
framework choice affects how SC-03/SC-05 are implemented, not their intent.

**Effect on DASH-004:** DASH-004's contract
(`docs/agentos-dashboard/stage-prompts/DASH-004.md`) named "OD-D9 resolved by the Human Owner" as
a precondition and allowed "exactly the dependency-declaration change OD-D9's disposition names."
Both are settled here: the precondition is satisfied and the declaration is already performed, so
DASH-004 needs no `pyproject.toml` edit of its own and gains no license to add further
dependencies. **DASH-004 is no longer blocked by OD-D9 as of this governance commit.** It remains
`Planned` and **unauthorized**, still requiring its own fresh written Human Owner authorization
and its registered branch before any implementation may begin.

**Boundaries:** This is a governance, architecture, and dependency-declaration record only. No
dashboard server code was written, no runtime source or test was modified, no dependency was
installed, no task was authorized or moved to `Current`, and no branch, push, merge, rebase,
reset, or stash operation was performed. No task is `Current` after this commit.

**Note on dates:** the decision was made and this record written on 2026-07-29; the session
crossed local midnight before committing, so Git timestamps the commit 2026-07-30. Every
"2026-07-29" in this decision's records refers to the day of the decision and the work, not to
the commit timestamp. Nothing else is implied by the difference.

## 2026-07-29 — Human Owner approved and closed GOV-AUTO-04

**Decision:** The Human Owner reviewed the implementation diff for `GOV-AUTO-04` on
branch `main` at base `7e0954948ea00052f63070205854691b037c4c45`, typed the two exact `APPROVE` confirmations
required by `scripts/workflow-approve.sh`, and approved the Conventional Commit
message `fix(workflow): automate registered branches and canonical report discovery (GOV-AUTO-04)`. The script then performed the deterministic governance closeout
(`GOV-AUTO-04` moves `Current -> Done`) and staged the approved implementation
together with the generated closeout records in one local commit.

**Boundaries:** This decision approves and closes only `GOV-AUTO-04`. It does not
push, merge, authorize a successor task, change branches, alter upstream, or mutate
stashes.

## 2026-07-29 — GOV-AUTO-04 implemented and validated, awaiting Human Owner approval

**Decision:** Implemented `GOV-AUTO-04` on `main` in the working tree, within its authorized file
scope, resolving OD-D10 and OD-D11 (`docs/agentos-dashboard/OPEN_QUESTIONS.md`). Full rationale
for both resolutions: `docs/agentos-dashboard/DECISIONS.md` DD-08.

**What changed:** a new shared library, `scripts/lib/branch_prepare.sh`, giving
`scripts/workflow-authorize.sh` and `scripts/workflow-next.sh` one tested branch-preparation and
branch-verification routine. `workflow-authorize.sh` now creates or safely switches to a
registry-governed task's registered branch immediately after its own authorization commit
(GOV/plain tasks, with no registered branch, stay on the default branch exactly as before);
`workflow-next.sh` refuses to launch an agent when the Current task's registered branch does not
match the working branch, without ever mutating anything itself. `scripts/workflow-approve.sh`'s
completion-report discovery now also accepts the Dashboard program's canonical
`docs/reports/agentos-dashboard/STAGE-XX-completion.md` name for a DASH task, with the stage
number cross-checked against the registry's own Branch cell (never unchecked filename
construction from the task ID alone); a disagreeing or malformed registry silently disables the
canonical lookup, and conflicting duplicate reports are refused outright. Existing
`<TASK_ID>-completion-report.md` behavior for AUTO/GOV tasks is unchanged.

**Validation:** 40 new focused tests across three new/updated test files
(`tests/test_workflow_branch_prepare.py`, `tests/test_workflow_report_discovery.py`, and
additions to `tests/test_workflow_authorize_script.py` / `tests/test_workflow_runner_scripts.py`);
full repository suite 2726-green; ruff, black, and mypy (`src` and `agentos_workflow`) clean;
`git diff --check` clean; `workflowctl verify` PASS on all five checks. Report:
`docs/reports/GOV-AUTO-04-completion-report.md`.

**Boundaries:** Implementation stays inside GOV-AUTO-04's allowed-file list. No commit, push,
merge, branch change, or stash operation was performed by this session; the working tree is left
for Human Owner review via `scripts/workflow-approve.sh`.

## 2026-07-29 — Human Owner authorized GOV-AUTO-04

**Decision:** The Human Owner typed the two exact `AUTHORIZE` confirmations for
`GOV-AUTO-04`. The task moves `Planned → Current`; implementation remains separate.
The authorization was recorded from branch `main` at `65f64148e1c30d1defe80709ddcfd9093967fdb3`.

**Boundaries:** This decision authorizes only the named task. It authorizes no successor,
push, merge, implementation approval, stash mutation, or automatic predecessor closure.

## 2026-07-29 — GOV-AUTO-04 proposed and registered as `Planned`

**Decision:** The Human Owner directed registration of a new governance and
developer-experience task, `GOV-AUTO-04 — Automatic registered-branch preparation and canonical
completion-report naming`, to resolve OD-D10 and OD-D11
(`docs/agentos-dashboard/OPEN_QUESTIONS.md`) — the registered-branch-vs-no-branch-runner conflict
and the completion-report filename mismatch both DASH-002 and DASH-003 recorded. This is a
governance-registration-only decision: it adds the task to `docs/TASK_QUEUE.md` (and its prose
mirror `docs/remaining_tasks.md`) as `Planned`, non-AUTO-family (no stage-registry lifecycle
entry, per the GOV-AUTO-01/02/03 precedent). It does **not** authorize, implement, or begin any of
GOV-AUTO-04's work.

**Scope recorded:** (1) `workflow-authorize.sh`/`workflow-next.sh` gain one shared, tested
branch-preparation routine that safely creates or switches to a registry-governed task's
registered branch after the authorization commit, refusing on divergence, unexpected commits, a
dirty worktree, or ambiguous history; GOV/main-branch tasks remain on `main`. (2)
`workflow-approve.sh`'s report-discovery is extended to directly accept the Dashboard program's
canonical `docs/reports/agentos-dashboard/STAGE-XX-completion.md` name (stage number resolved
from registry data, not unchecked filename construction), rejecting path traversal and refusing on
conflicting duplicate reports, while existing `<TASK_ID>-completion-report.md` support for
AUTO/GOV tasks is preserved.

**Boundaries:** This decision registers only `GOV-AUTO-04` as `Planned`. It authorizes no
implementation, no commit beyond this governance-registration commit, no push, merge, branch
change, or stash mutation, and no successor task. `GOV-AUTO-04` requires its own fresh, explicit
Human Owner authorization (`scripts/workflow-authorize.sh GOV-AUTO-04 [claude|codex]`) before any
implementation session may begin.

## 2026-07-29 — Human Owner approved and closed DASH-003

**Decision:** The Human Owner reviewed the implementation diff for `DASH-003` on
branch `feature/dash-003-governance-parsing` at base `651e53e25da27e8494a7c5525cdc87cafdef9ce3`, typed the two exact `APPROVE` confirmations
required by `scripts/workflow-approve.sh`, and approved the Conventional Commit
message `feat(dashboard): add governance parsing and consistency engine (DASH-003)`. The script then performed the deterministic governance closeout
(`DASH-003` moves `Current -> Done`) and staged the approved implementation
together with the generated closeout records in one local commit.

**Boundaries:** This decision approves and closes only `DASH-003`. It does not
push, merge, authorize a successor task, change branches, alter upstream, or mutate
stashes.

## 2026-07-29 — Human Owner authorized DASH-003

**Decision:** The Human Owner typed the two exact `AUTHORIZE` confirmations for
`DASH-003`. The task moves `Planned → Current`; implementation remains separate.
The authorization was recorded from branch `main` at `f80919793cfb7776f094733484c837833995e23a`.

**Boundaries:** This decision authorizes only the named task. It authorizes no successor,
push, merge, implementation approval, stash mutation, or automatic predecessor closure.

## 2026-07-29 — Human Owner approved and closed DASH-002

**Decision:** The Human Owner reviewed the implementation diff for `DASH-002` on
branch `feature/dash-002-repo-adapter` at base `729f7461b5a2381251557db4e096346a503400de`, typed the two exact `APPROVE` confirmations
required by `scripts/workflow-approve.sh`, and approved the Conventional Commit
message `feat(dashboard): add read-only repository and git adapters (DASH-002)`. The script then performed the deterministic governance closeout
(`DASH-002` moves `Current -> Done`) and staged the approved implementation
together with the generated closeout records in one local commit.

**Boundaries:** This decision approves and closes only `DASH-002`. It does not
push, merge, authorize a successor task, change branches, alter upstream, or mutate
stashes.

## 2026-07-29 — Human Owner authorized DASH-002

**Decision:** The Human Owner typed the two exact `AUTHORIZE` confirmations for
`DASH-002`. The task moves `Planned → Current`; implementation remains separate.
The authorization was recorded from branch `main` at `5a111563a6bcec4c86d32e08efcfd3946f693eb6`.

**Boundaries:** This decision authorizes only the named task. It authorizes no successor,
push, merge, implementation approval, stash mutation, or automatic predecessor closure.

## 2026-07-29 — Human Owner approved and closed GOV-3

**Decision:** The Human Owner reviewed the implementation diff for `GOV-3` on
branch `main` at base `58ed4f6dde8b36fca349bbc91fe10278cf4cafd0`, typed the two exact `APPROVE` confirmations
required by `scripts/workflow-approve.sh`, and approved the Conventional Commit
message `feat(workflow): add attempt-aware report artifact naming to the Reporting Skills (GOV-3)`. The script then performed the deterministic governance closeout
(`GOV-3` moves `Current -> Done`) and staged the approved implementation
together with the generated closeout records in one local commit.

**Boundaries:** This decision approves and closes only `GOV-3`. It does not
push, merge, authorize a successor task, change branches, alter upstream, or mutate
stashes.

## 2026-07-29 — Human Owner authorized GOV-3

**Decision:** The Human Owner typed the two exact `AUTHORIZE` confirmations for
`GOV-3`. The task moves `Planned → Current`; implementation remains separate.
The authorization was recorded from branch `main` at `4bd1812ce3dd563528a8b8d2d2e6895995a88c6d`.

**Boundaries:** This decision authorizes only the named task. It authorizes no successor,
push, merge, implementation approval, stash mutation, or automatic predecessor closure.

## 2026-07-29 — Human Owner approved and closed GOV-2

**Decision:** The Human Owner reviewed the implementation diff for `GOV-2` on
branch `main` at base `919fef2b31e4aefba7d246b87dd1e8fbd5ee9849`, typed the two exact `APPROVE` confirmations
required by `scripts/workflow-approve.sh`, and approved the Conventional Commit
message `feat(governance): add check-registries stage-registry/lifecycle consistency check (GOV-2)`. The script then performed the deterministic governance closeout
(`GOV-2` moves `Current -> Done`) and staged the approved implementation
together with the generated closeout records in one local commit.

**Boundaries:** This decision approves and closes only `GOV-2`. It does not
push, merge, authorize a successor task, change branches, alter upstream, or mutate
stashes.

## 2026-07-29 — Human Owner authorized GOV-2

**Decision:** The Human Owner typed the two exact `AUTHORIZE` confirmations for
`GOV-2`. The task moves `Planned → Current`; implementation remains separate.
The authorization was recorded from branch `main` at `f39c673d1646a1a232deb3e53e2026c82e8d143d`.

**Boundaries:** This decision authorizes only the named task. It authorizes no successor,
push, merge, implementation approval, stash mutation, or automatic predecessor closure.

## 2026-07-29 — Human Owner approved and closed AUTO-007

**Decision:** The Human Owner reviewed the implementation diff for `AUTO-007` on
branch `fix/auto-007-e2e-dry-run-recovery` at base `fed6e9258d736c90b00343614824a66ba55eacb9`, typed the two exact `APPROVE` confirmations
required by `scripts/workflow-approve.sh`, and approved the Conventional Commit
message `feat(workflow): add end-to-end dry-run and recovery validation (AUTO-007)`. The script then performed the deterministic governance closeout
(`AUTO-007` moves `Current -> Done`) and staged the approved implementation
together with the generated closeout records in one local commit.

**Boundaries:** This decision approves and closes only `AUTO-007`. It does not
push, merge, authorize a successor task, change branches, alter upstream, or mutate
stashes.

## 2026-07-28 — Human Owner authorized AUTO-007

**Decision:** The Human Owner typed the two exact `AUTHORIZE` confirmations for
`AUTO-007`. The task moves `Planned → Current`; implementation remains separate.
The authorization was recorded from branch `main` at `b4abc0a5b2ba67d38b7c156ee7522aef9d8b52e9`.

**Boundaries:** This decision authorizes only the named task. It authorizes no successor,
push, merge, implementation approval, stash mutation, or automatic predecessor closure.

## 2026-07-28 — Human Owner approved and closed GOV-AUTO-03

**Decision:** The Human Owner reviewed the implementation diff for `GOV-AUTO-03` on
branch `main` at base `c8e59fb3ccb5429266122c2468bd83a3201c1223`, typed the two exact `APPROVE` confirmations
required by `scripts/workflow-approve.sh`, and approved the Conventional Commit
message `feat(workflow): add automatic task closeout to approval gate (GOV-AUTO-03)`. The script then performed the deterministic governance closeout
(`GOV-AUTO-03` moves `Current -> Done`) and staged the approved implementation
together with the generated closeout records in one local commit.

**Boundaries:** This decision approves and closes only `GOV-AUTO-03`. It does not
push, merge, authorize a successor task, change branches, alter upstream, or mutate
stashes.

## 2026-07-28 — GOV-AUTO-03 authorized and implemented, awaiting Human Owner approval

**Decision:** The Human Owner recorded: *"I authorize one new governance and developer-experience
task: GOV-AUTO-03 — Human-Approved Commit with Automatic Task Closeout."* This is a governance and
developer-experience task outside the AUTO family (no stage-registry lifecycle state, matching the
GOV-AUTO-01/02 precedent), extending the local Human-gated workflow so that
`scripts/workflow-approve.sh`, after Human Owner approval, performs both the approved
implementation commit and the governance closeout of that same task as one controlled local
commit — never a separate `docs(governance): close TASK_ID` commit. Publication and merge remain
separate Human Owner actions.

**Implementation summary.** `workflow-approve.sh` now branches on the same stable
`project.id: ai-workflow-engine` marker `workflow-authorize.sh` already uses (plus the full
governance file set being present): any other repository — including every pre-existing
disposable test sandbox — takes the unchanged GOV-AUTO-01 plain approval/commit gate; this
repository takes a new path that, after the same two exact `APPROVE` confirmations, identifies the
single `Current` task from the authoritative task queue, verifies the `current_task.md` and
`remaining_tasks.md` mirrors and (where applicable) the stage registry agree with it, verifies the
approved Conventional Commit message names that task, displays the full transition, then performs
a fail-closed deterministic closeout (task queue `Current → Done`, mirrors, project state,
decision log, changelog, stage registry `COMPLETE` where applicable, program changelog where
applicable, a completion-report addendum, handover, and a regenerated checksum) using
`awk`-guarded, precondition-checked replacements — never broad free-form text substitution — before
re-running `task-state`/`governance`/`handover` validation and creating exactly one local commit
containing the approved implementation and the generated closeout records together. A
pre-closeout backup of every governance file the closeout may touch is restored verbatim on any
failure, leaving the approved implementation diff and the index untouched; the script never
pushes, merges, changes branches, alters upstream, or mutates stashes, and never authorizes a
successor task.

**Validation.** 26 new focused tests in `tests/test_workflow_approve_closeout.py` (task discovery
and mirror/registry agreement, both approval gates, closeout content and single-commit behaviour,
closeout-failure atomicity, and Git safety); the pre-existing GOV-AUTO-01 suite
(`tests/test_workflow_runner_scripts.py`, 60 tests) and GOV-AUTO-02 suite
(`tests/test_workflow_authorize_script.py`, 28 tests) pass unmodified. Full repository suite
2,590-green (`tests` + `agentos_workflow/tests`); ruff, black, and mypy (`src` and
`agentos_workflow`) clean; `git diff --check` clean; `bash -n` and `shellcheck` clean on all three
scripts.

**Boundaries:** this decision authorizes only GOV-AUTO-03. It does not authorize, and this session
did not begin, AUTO-007 or any other task. Implementation is complete and validated but
**uncommitted**, awaiting a separate Human Owner approval decision before any commit is created.

## 2026-07-28 — AUTO-006 approved, closed to `Done`, and merged; no successor authorized

**Decision:** The Human Owner reviewed the AUTO-006 implementation and validation report
(`docs/reports/workflow-automation/AUTO-006-completion-report.md`) and recorded: *"I approve the
formal closure and publication of AUTO-006. The approved AUTO-006 implementation commit is
`d8d356d060076be4ad78afb4d20891004a946204`."* This directed, in order: record AUTO-006 as
implemented, validated, approved, and committed locally as `d8d356d`; move the task
`Current → Done` and the registry state `IN_PROGRESS → COMPLETE`; append a closure entry to the
Authorization Log (`STAGE_REGISTRY.md` §5) and this approval/closure entry to
`docs/DECISION_LOG.md`; reconcile every governance mirror and the handover checksum in exactly one
governance-only local commit, with no implementation changes bundled into it; then push the stage
branch, update local `main` from `origin/main`, merge into `main` by the repository's established
safe merge policy, and push `main` — retaining the stage branch and leaving both pre-existing
stashes untouched. The decision explicitly withholds authorization for AUTO-007 and for
GOV-AUTO-03: neither may begin as a consequence of this closure.

**Rationale — why the completion report is not rewritten:** the AUTO-006 completion report's
Confirmation section states that no commit, push, pull request, or merge had been performed —
true at the moment that report's text was finalized, immediately before this stage's own
implementation commit (`d8d356d`) was created. Rewriting that section to read as though the
commit already existed at that point would falsify what the delivering session actually recorded,
which `docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 8 forbids. The commit, the Human
Owner's approval, the closure, and the publication are instead recorded through a new,
append-only Addendum 1 section at the end of that report, a new `STAGE_REGISTRY.md` §5 row, and
this entry — exactly the record-integrity pattern already established for AUTO-004 (commit
`84616d5`, addendum in its own completion report) and AUTO-005 (commit `430cbb4`, same pattern).

**Rationale — two known limitations remain open, not fixed, by this closure:** the Human Owner's
approval explicitly accepted AUTO-006 as delivered, including its two self-reported limitations —
Orchestrator wiring of the Merge Safety Gate / Checks-Wait Gate not performed (outside this
stage's allowed files), and the `allowed_environment_variables` gap on five of the eight
`gh`-based Skill calls (OD-10, `DECISIONS.md` DD-38). Neither is fixed by this governance-only
closure commit, which touches no runtime code; both remain `Open` for a future stage's explicit
scope decision.

**What this decision does not do:** it authorizes no AUTO-007 work, no GOV-AUTO-03 work, and no
successor of any kind (`STAGE_REGISTRY.md` §3 rule 16) — every remaining task in
`docs/TASK_QUEUE.md` stays `Planned` and requires its own fresh, explicit Human Owner
authorization. Neither pre-existing stash was touched, and no branch other than the ones this
decision names was created, deleted, or renamed.

## 2026-07-28 — AUTO-006 implemented, awaiting Human Owner approval

**Decision:** Acting under the standing AUTO-006 authorization below, an engine implementation
session created branch `feature/auto-006-pr-merge-closeout` from clean `main` (initial-start
preflight, `STAGE_REGISTRY.md` §3 rule 4; registry `AUTHORIZED → IN_PROGRESS`) and implemented
the eight Git/GitHub Skills of `SKILL_CONTRACTS.md` §5 in the new file
`agentos_workflow/skills/git_github.py`: `create_commit`, `push_stage_branch`,
`create_pull_request`, `read_pull_request_state`, `verify_head_sha`, `read_required_checks`,
`enable_automatic_squash_merge`, `verify_merge_completion`. These bind the eight Skill names
`GitAgent`/`MergeAgent` (AUTO-005) already call against fakes with the exact same keyword shapes
— no Agent code changed. OD-1 (native GitHub auto-merge vs. engine-side polling) is resolved in
favor of native `gh pr merge --auto --squash` (`DECISIONS.md` DD-37); `create_commit`'s staging
design (`git add -A` rather than a caller-supplied path list, since `GitAgent` never passes one)
is recorded as DD-36.

**Discovered during self-review, not fixed in this stage:** five of the eight Skill calls
(`create_pull_request`, `read_pull_request_state`, `enable_automatic_squash_merge`,
`read_required_checks`, `verify_merge_completion`) are invoked by `GitAgent`/`MergeAgent`
without `allowed_environment_variables`, so in a real deployment `gh` has no path to a
`GH_TOKEN`/`GITHUB_TOKEN` or a readable `$HOME`. Fixing it requires editing
`agentos_workflow/agents/**`, outside AUTO-006's allowed files. Recorded as `DECISIONS.md` DD-38
and `OPEN_QUESTIONS.md` OD-10, both `Open`/unresolved, for a future Human Owner decision.

**Validation:** 33 new focused tests (`test_skills_git_github.py`); `agentos_workflow/tests`
1,498-green (was 1,465); `tests` collection unchanged at 1,066 (no `tests/`/`src/` file touched);
`tests` suite 1,066-green; ruff, black, and `mypy --no-incremental` clean on both
`agentos_workflow` and `src`; `git diff --check` clean; `workflowctl verify` PASSes on
`task-state`, `governance`, and `handover`, and FAILs `git` only on the pre-existing, documented
`upstream_missing` finding for a freshly created, not-yet-pushed stage branch (`STAGE_REGISTRY.md`
§3 rule 16's named tolerance).

**Boundaries:** No commit, push, merge, branch change, or stash mutation was performed. The
complete diff is left in the working tree for Human Owner review. Full report:
`docs/reports/workflow-automation/AUTO-006-completion-report.md`.

## 2026-07-28 — Human Owner authorized AUTO-006

**Decision:** The Human Owner typed the two exact `AUTHORIZE` confirmations for
`AUTO-006`. The task moves `Planned → Current`; implementation remains separate.
The authorization was recorded from branch `main` at `0a663a35ea502b7524344d69c595cfb1cc9984c0`.

**Boundaries:** This decision authorizes only the named task. It authorizes no successor,
push, merge, implementation approval, stash mutation, or automatic predecessor closure.

## 2026-07-28 — GOV-AUTO-02 closed to `Done`

**Decision:** The Human Owner closed GOV-AUTO-02 from `Current` to `Done` and directed the
governance and handoff records to state that it was implemented, validated, approved, and
committed as `d212e4d2dae2cd0a3510c54d7cd098fdfd5da548`. Exactly one governance-only local commit
is authorized for this closure.

**Resulting state:** No task is `Current`. GOV-AUTO-02 is `Done`; AUTO-006, AUTO-007, GOV-2,
GOV-3, and DASH-002..010 remain `Planned` and require their own fresh written Human Owner
authorization. This decision authorizes no successor and specifically does not authorize
AUTO-006.

**Boundaries:** No push, merge, successor implementation, branch/upstream change, or stash
mutation is authorized. The session must stop after the single local closure commit and report
its hash.

## 2026-07-28 — GOV-AUTO-02 local task authorization and launch gate

**Decision:** The Human Owner authorized GOV-AUTO-02 — Local Task Authorization and Launch Gate.
The task is the single `Current` task while its completed implementation remains uncommitted and
pending Human Owner approval. AUTO-006, GOV-3, DASH-002, and every other planned task remain
unauthorized.

**Design:** `scripts/workflow-authorize.sh <TASK_ID> [claude|codex]` accepts only an explicit task
ID; it never reads queue order to choose work. It requires the default-branch baseline, a clean
worktree/index, no existing `Current` task, a `Planned`/ready target, completed structured program
predecessors, resolved established owner-decision gates, and passing task-state/governance/
handover checks. The script displays the task, status, predecessor, canonical implementation
branch, current branch/HEAD, agent, and exact governance allowlist, then requires two exact
`AUTHORIZE` confirmations before changing anything.

**Phase separation:** authorization reconciles the queue, mirrors, project state, decision log,
changelogs, relevant stage registry, handoff, and checksum, validates again, and creates exactly
one local `docs(governance): authorize TASK-ID` commit containing only those records. An optional
agent is invoked through `workflow-next.sh` only after the commit is verified and the worktree is
clean. Implementation and its later `workflow-approve.sh` commit remain separate. The script has
no push, merge, branch/upstream mutation, stash mutation, automatic predecessor closure, or task
implementation path.

**Limitations:** AUTO/DASH predecessor and canonical-branch data are structured in their stage
registries. Ordinary queue-only GOV tasks declare no machine-readable predecessor, so the gate
reports none declared and relies on their explicit status/blocker prose plus the common baseline
and Human confirmations. Open-decision refusal recognizes the repository's established
“blocked on” and “must be resolved before TASK authorization” wording; a future structured
dependency schema could replace that conservative text check.

## 2026-07-28 — AUTO-005 approved, closed to `Done`, and merged; the QA report collision deferred to GOV-3

**Decision:** The Human Owner approved the AUTO-005 implementation, explicitly accepted all five
limitations the stage report documented, authorized exactly one local commit (created as
`430cbb4`), and then — in a second decision — approved AUTO-005's formal closure and publication:
task `Current → Done`, registry `IN_PROGRESS → COMPLETE`, push, merge into `main`, push `main`,
retain the stage branch, touch neither stash, and do not begin AUTO-006.

**Rationale — why the QA report collision was deferred rather than fixed.** AUTO-005 found a real
integration defect: `agentos_workflow/skills/reporting.py` writes one artifact per workflow
identifier per report kind and correctly refuses to overwrite differing content, but the bounded
repair loop (`FAILURE_RECOVERY.md` §1) produces up to four genuinely different QA reports per
workflow, so the second round failed on the *artifact* rather than on the code under review. The
stage could not fix it — `agentos_workflow/skills/**` is outside AUTO-005's allowed paths — so it
shipped a scoped per-attempt audit workaround, disclosed it in the report, and asked. The Human
Owner accepted the workaround for this stage and directed that the underlying defect be recorded as
explicit future work, not fixed in scope. It is now **GOV-3 — Attempt-aware report artifact naming
in the Reporting Skills** (`docs/TASK_QUEUE.md`, `Planned`, requiring its own fresh authorization),
carrying the defect description, why the workaround is not the fix, and a recommended shape.
Expanding AUTO-005's allowed paths to fix it in place was rejected: a stage that widens its own
scope to absorb a defect it discovers is exactly the drift the allowed-path list exists to prevent,
and the fix touches a module three other stages depend on.

**Rationale — why the completion report was not rewritten.** AUTO-005's report was deliberately
finished *before* its commit was created, recording the approval and the authorized commit without
naming a hash — the record-integrity problem AUTO-004 had hit, avoided by construction this time.
Closure then added a fact the report could not have known (the hash `430cbb4`) plus the merge
result, so those are recorded in a new append-only addendum, a new `STAGE_REGISTRY.md` §5 row, and
this entry, leaving the report's own text untouched (rule 8).

**What this decision does not do:** it authorizes no successor (rule 16). AUTO-006, AUTO-007,
GOV-2, and GOV-3 all remain `Planned` and explicitly unauthorized, and the Human Owner's directive
said so in terms ("Do not authorize AUTO-006"). Neither stash was touched, and both
`feature/auto-004-model-providers` and `feature/auto-005-agents` were retained, not deleted.

## 2026-07-28 — AUTO-004 approved, closed to `Done`, and merged; AUTO-005 authorized separately

**Decision:** An AUTO-005 session's authorization-precondition check found AUTO-004 still
`IN_PROGRESS`/`Current` with its work committed as `84616d5` on `feature/auto-004-model-providers`
but absent from `main`. Three preconditions were therefore unmet:
`docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 1 (predecessor `COMPLETE`) and rule 10
(no stage N+1 before N is `COMPLETE`); `maximum_current_tasks: 1` (AUTO-004 held the single
`Current` slot); and rule 14 (AUTO-005's branch must come from current `main`, which carried no
`agentos_workflow/providers/` for AUTO-005's Agents to be restricted to). Per rule 16 the session
stopped, made no change, and reported the conflict rather than resolving it on its own initiative.

The Human Owner, presented with it, gave one written decision resolving all of it: approve the
AUTO-004 implementation; close it `Current → Done` and `IN_PROGRESS → COMPLETE` recording commit
`84616d5`; publish it (push the stage branch, update `main` from `origin/main` without rewriting
history, merge by the established safe merge policy, push `main`, retain the branch, leave both
stashes untouched); and *then*, only after that integration and its closure checks passed,
authorize AUTO-005 as the single `Current` task.

**Rationale — why the completion report was not rewritten:** commit `84616d5` was created after
`docs/reports/workflow-automation/AUTO-004-completion-report.md` was written, so that report's
"No commit, push, pull request, merge … was performed" Confirmation was true when written. Rule 8
protects completion records from in-place editing, and the Human Owner's decision explicitly
required that the report "is not rewritten to pretend the commit existed when it was produced".
The later commit, approval, and merge are recorded instead by three append-only artifacts: a new
addendum section at the end of that report, a new `STAGE_REGISTRY.md` §5 row, and this entry.
Editing the report's Confirmation section in place — the tempting "just make it accurate now" fix —
was rejected because it would silently rewrite what the delivering session actually did and
observed, which is exactly the failure rule 8 and rule 18 exist to prevent.

**Rationale — why closure and authorization are two acts, not one:** this is the fourth occurrence
of the predecessor-still-`Current` pattern (after DASH-001→AUTO-001, AUTO-001→AUTO-002, and
GOV-AUTO-01→AUTO-004) and was handled identically: the session detects and reports, the Human
Owner decides both halves explicitly in one written directive. Rule 16 forbids a session selecting
or authorizing a successor on its own initiative in the same session as a closeout; it does not
forbid the Human Owner directing both when shown a genuine conflict. The `Current` set was
verifiably empty between the two acts, and AUTO-005's authorization is recorded as its own
`STAGE_REGISTRY.md` §5 row conditioned on the AUTO-004 integration having succeeded first.

**What this decision does not do:** it authorizes no AUTO-005 commit, push, or merge — AUTO-005
stops at a Human Owner approval report — and it authorizes no work on AUTO-006 or any later stage.
Neither stash was touched, and `feature/auto-004-model-providers` was retained, not deleted.

## 2026-07-28 — GOV-AUTO-01 closed to `Done`; AUTO-004 authorized as the single `Current` task

**Decision:** An AUTO-004 session's authorization-precondition check found GOV-AUTO-01 still
recorded `Current` in `docs/TASK_QUEUE.md`, `docs/current_task.md`, and `docs/remaining_tasks.md`
even though its commit `a302c95` had already been merged into `main` via `a3b5b0a`. Under
`self-governance.yaml`'s `maximum_current_tasks: 1`, that blocked
`docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 1's "no other `Current` task anywhere in the
queue" precondition, so AUTO-004 could not be recorded `Current`. Per rule 16 the session stopped,
made no change, and put the conflict to the Human Owner rather than resolving it on its own
initiative.

The Human Owner, presented with the conflict, gave one written decision resolving both: close
GOV-AUTO-01 `Current → Done` — recording that it was implemented, validated, approved, committed
as `a302c95`, and merged into `main` via `a3b5b0a` — and then authorize and begin AUTO-004 as the
single `Current` task, with commit, push, merge, and any work on AUTO-005 or another task
explicitly prohibited.

**Rationale:** This is the third occurrence of the predecessor-still-`Current` pattern rule 16
describes, after DASH-001→AUTO-001 (2026-07-23) and AUTO-001→AUTO-002 (2026-07-24), and it was
handled the same way: the session detects and reports, the Human Owner decides. Rule 16 forbids a
session selecting or authorizing a successor on its own initiative in the same session as a
closeout; it does not forbid the Human Owner directing both explicitly when shown a genuine
conflict. Recording the closure as an inference from the merge — "it is on `main`, therefore it
must be `Done`" — was rejected for exactly that reason: the merge is evidence of the Human Owner's
approval, not a substitute for the Human Owner's closure act, and a session that promotes itself
past a `Current` task on inferred approval is the failure mode `maximum_current_tasks: 1` and
rule 16 exist to prevent.

**What this decision does not do:** it authorizes no successor to AUTO-004 (rule 16), no push or
merge of the AUTO-004 work, and no reopening of GOV-AUTO-01. The stale
`handover/PROJECT_HANDOVER.md` — which still described GOV-AUTO-01 as uncommitted and reported
HEAD as `908be94` on the AUTO-003 branch — is refreshed under the same decision's explicit
instruction to update the handoff.

## 2026-07-27 — Human Owner accepts AUTO-002 for closure without another independent review

**Decision:** After reviewing the implementation report and validation results, the Human Owner
accepted the current AUTO-002 implementation as sufficient, explicitly directed that no further
independent review or search for findings occur, and authorized final integrity checks,
governance closure, and one local Conventional Commit. This is the controlling closure decision
for the pending-review language in the entry immediately below; the technical remediation record
remains intact.

AUTO-002 moves from registry `IN_PROGRESS` to `COMPLETE` and task status `Current` to `Done`.
AUTO-003 remains `NOT_STARTED`/`Planned`: predecessor completion satisfies only one precondition
and is not successor authorization. The approved action includes no push, merge, upstream change,
branch change, stash mutation, architectural redesign, or AUTO-003 implementation.

**Future work:** Existing POSIX portability boundaries, infrastructure-retry accounting when a
future stage first introduces such operations, remote/GitHub reconciliation, and other
out-of-scope improvements do not reopen or block AUTO-002. They remain assigned to the relevant
future AUTO stage or project backlog and require separate Human Owner authorization.

## 2026-07-27 — AUTO002-IR3-01..IR3-05: Human-Owner-authorized remediation pending fresh independent review

**Decision:** The Human Owner authorized implementation of every task from the third independent
review. The implementation is deliberately not self-approved: AUTO-002 remains `IN_PROGRESS` and
must receive a completely fresh independent review before any commit or merge approval.

The approved changes bind implementation reconciliation to the authorization record, exact current
branch tip, latest persisted attempt, independently-derived authorized-baseline diff, path policy,
and an exact structured completion report (DD-27); reject hardlinked mutable persistence targets
before writes (DD-28); confine authorization and attempt sidecars to the literal workflow directory
using descriptor-relative no-symlink operations (DD-29); reject duplicate JSON keys in those
sidecars and completion reports (DD-30); and reconcile the audit model's separate repository
identity/path fields with the implemented record schema (DD-31).

**Scope:** Only the five approved remediation tasks, their regression tests, and their governance
updates were performed. No dependency, packaged `src/` implementation, AUTO-003/AUTO-005 work,
commit, push, merge, branch, stash, upstream, GitHub, or other external-service action was
authorized or performed.

## 2026-07-27 — AUTO002-IR-01..IR-05: a second independent review reproduced five defects the prior pass reported as resolved; all five remediated, F11 reclassified

**Decision:** A second, independent review of AUTO-002 reproduced five concrete defects, two of
them in code the immediately preceding remediation pass (the entry directly below) had reported
as hardened. That prior pass's completion claims for **F04, F05, F08, and F09 are therefore
invalidated as overstated**: each fixed a real defect, but none closed the class of defect its
governance text claimed. This entry records the corrected position and the remediation. The
verdict of the review that found these is not erased and is not to be read as approval of this
work — this remediation is **pending fresh independent review**, and no independent approval has
been obtained for it.

**What the review reproduced, and the corrected status of the prior claims:**

- **IR-01 (lock, `agentos_workflow/orchestrator/lock.py`)** — `canonical_lock_path` resolves the
  repository *root* but appends `.agentos/workflow.lock` lexically, so a symlinked `<repo>/.agentos`
  was followed at open time and an external file was truncated and overwritten. **Corrects F04
  (`DECISIONS.md` DD-16):** resolving the root is not confinement. Fixed by a descriptor-relative
  `O_NOFOLLOW` walk (`DECISIONS.md` DD-21); 8 regression tests.
- **IR-02 (state/audit storage, `state_store.py`)** — validating `workflow_id` as a safe path
  *component* does not stop a symlinked `<root>/<workflow_id>` directory being followed; audit
  records were written outside the configured root, and unconfined reads could replay a planted
  external history. **Corrects F05 (DD-16) and the path-confinement half of F08 (DD-17).** Fixed by
  one shared confined-open primitive used by both histories and by reads and writes
  (`DECISIONS.md` DD-22); 10 regression tests.
- **IR-03 (changed-path authorization, `config/schema.py`, `orchestrator/engine.py`)** —
  noncanonical-but-non-traversing patterns (`docs/./secret/**`, `docs//secret/**`, backslash,
  Windows-drive and UNC forms) were accepted and passed raw into matching, so a
  `forbidden_changed_paths` rule stayed inert and a broader allowed rule won. **Corrects F09
  (DD-18):** rejecting absolute and `..` patterns was necessary but far from sufficient, and the
  inert-forbidden-pattern hazard DD-18 named was still live. Fixed by strict rejection of every
  noncanonical spelling plus canonicalisation of observed Git paths (`DECISIONS.md` DD-23); 48
  regression tests.
- **IR-04 (writer ordering, `state_store.py`)** — the reader enforced non-decreasing timestamps but
  the writer did not, so the supported writer could append a record that made the history
  permanently unreadable by the supported reader. **Corrects the ordering half of F08 (DD-17):**
  a read-side-only check was an incomplete invariant. Fixed by enforcing the reader's own rule at
  append time, under the append lock, before any byte is written (`DECISIONS.md` DD-24); 17
  regression tests.
- **IR-05 (duplicate JSON keys, `state_store.py`)** — standard JSON parsing accepted duplicate
  object keys with last-key-wins, so a record carrying two `to_state` or `timestamp` values
  validated cleanly and replayed as whichever value the parser kept. Fixed by
  `object_pairs_hook`-based rejection at every nesting level, before model validation
  (`DECISIONS.md` DD-25); 12 regression tests.

**F11:** the prior pass asserted "F11 was already resolved by a prior session and was not
reopened." That claim is superseded. An exhaustive local search (all governance records, reports,
addenda, stage prompts, tests, implementation, `git log -S` across all refs, and both stashes; no
network) finds the token `F11` only in the two prose assertions that it was resolved — never a
definition. F11 is reclassified **`INSUFFICIENT_DURABLE_EVIDENCE`**: *F11 historical definition and
regression mapping could not be reconstructed from durable repository evidence.* No definition was
invented and no code was changed to manufacture evidence (`DECISIONS.md` DD-26).

**F13 (governance consistency):** the prior F13 entry is not deleted, but its assertion that
governance was consistent with the code no longer held once IR-01..IR-05 were reproduced. This
entry, DD-21 through DD-26, and the corresponding report addendum are the corrected record.

**Validation:** `pytest tests agentos_workflow/tests` — 1967 passed, 0 failed, 0 errors, 0 skipped,
0 xfailed, 0 deselected, 0 warnings (baseline before this pass: 1872 passed; +95 regression tests).
Bare `pytest` — 978 passed; this is *not* full coverage of this work, because
`pyproject.toml`'s `testpaths = ["tests"]` excludes `agentos_workflow/tests` entirely. Ruff, Black,
`mypy src`, `mypy agentos_workflow`, and `git diff --check` all clean. `workflowctl verify` reports
the single pre-existing `upstream_missing` finding (this branch has no upstream and upstream
configuration was out of scope and untouched); all other checks pass.

**Alternatives considered:** for IR-03, normalizing patterns to canonical form instead of rejecting
them — declined, because a rewriting step risks reinterpreting glob tokens and because two
spellings mapping to one stored pattern makes configuration review harder; strict rejection gives
exactly one spelling per intent. For IR-01/IR-02, checking the resolved path before opening —
declined as a check-then-open race; the kernel refusing the open is the enforcement.

**Status:** AUTO-002 remains `IN_PROGRESS`, now **pending fresh independent review**. No commit,
push, merge, branch change, upstream change, or stash mutation occurred. AUTO-003 and AUTO-005
remain unauthorized and `NOT_STARTED`.

## 2026-07-27 — AUTO002-F04/F05/F06/F08/F09/F10/F12/F13: sequential remediation pass completed; governance reconciled

**Decision:** Following the F07 Human Owner decision recorded immediately below, remediation
continued sequentially through F08 (audit-record invariants), F09 (configuration-pattern
confinement), F10 (workflow-ID reuse bypass), and F12 (regression-test-adequacy audit), each
reproduced adversarially before being fixed, per the same discipline F04-F07 already established.
This entry is F13: the governance-reconciliation finding, synchronizing `DECISIONS.md`,
`CHANGELOG.md`, and the completion report for every finding in this pass.

**What was found and fixed, in order:**

- **F04/F05/F06** (canonical repository locking, JSONL append durability, durable retry/attempt
  accounting) were implemented and tested earlier in this same remediation session, ahead of F07;
  `DECISIONS.md` DD-16 records them at the level of detail directly verifiable against current
  code.
- **F07** (local reconciliation-evidence verification): recorded in the entry immediately below
  this one and in `DECISIONS.md` DD-15.
- **F08** (audit-record invariants, `state_store.py`): a naive (non-timezone-aware) timestamp, a
  command's `completion_time` preceding its own `start_time`, an `stdout_ref`/`stderr_ref`
  resolving outside the audit directory, a `StateTransitionRecord` whose own `workflow_id` field
  disagreed with the file it was read from, and a persisted sequence with out-of-order timestamps
  were all previously accepted with no validation. All four are now rejected
  (`DECISIONS.md` DD-17); 44 new regression tests.
- **F09** (configuration-pattern confinement, `config/schema.py`): `allowed_changed_paths`/
  `forbidden_changed_paths` accepted an absolute or parent-traversal glob pattern that could never
  match any real repository-relative changed path — for `forbidden_changed_paths` specifically, an
  inert pattern gives the false appearance of a protection that was never in effect. Now rejected
  (`DECISIONS.md` DD-18); 8 new regression tests.
- **F10** (workflow-ID reuse, `engine.py`): `ResumedWorkflow` — a plain, unguarded dataclass, unlike
  `WorkflowSession` — could be constructed directly and used to durably persist a fabricated
  `CREATED -> AUTHORIZED` transition (via `.transition_to(WorkflowState.AUTHORIZED, actor="human")`
  against a fresh, never-replayed machine) *before* `AuthorizationBypassError` was finally raised —
  the corrupting write happened first, every time. `ResumedWorkflow.transition_to` now rejects
  `AUTHORIZED` before any persistence is attempted (`DECISIONS.md` DD-19); 5 new regression tests.
  `authorize()` itself was independently re-verified and found already airtight against reuse.
- **F12** (regression-test-adequacy audit, no code change): a full-suite run plus a targeted sweep
  found no test anywhere in the AUTO-002 suite still asserting, as expected, behavior any of the
  above fixes made unsafe (`DECISIONS.md` DD-20).

**Validation, every finding:** full combined suite (`pytest tests agentos_workflow/tests`) green
throughout, ending at 1872 passed; `ruff check --no-cache agentos_workflow/`,
`black --check agentos_workflow/`, and `mypy --no-incremental agentos_workflow` all clean after
every fix; `git diff --check` clean. No dependency added; no network or GitHub access
implemented; no general Skill/Agent interface implemented; no mutable Git operation authorized;
no commit, push, merge, pull request, branch change, upstream change, or stash mutation occurred
at any point in this pass.

**Acknowledged, explicitly recorded limitations (not silently papered over):** `CommandExecutionRecord`
has no `workflow_id` field, so its identity cannot be cross-checked against its file the way
`StateTransitionRecord`'s now is (F08/DD-17); `ImplementationDiffEvidence` has no `attempt_number`
or `changed_paths` field, so per-attempt evidence binding and changed-path scope checking remain
open (F07/DD-15).

**Scope/status:** AUTO-002 remains `IN_PROGRESS`; AUTO-003 and AUTO-005 remain unauthorized and
`NOT_STARTED`. F11 was already resolved by a prior session and was not reopened. F13 (this entry)
completes the sequential remediation pass F04 through F13; remaining next steps belong to a fresh
independent review, not to this session.

## 2026-07-27 — Human Owner decision: AUTO002-F07 evidence verification scope

**Decision:** `ReconciliationEvidence` must never be accepted merely because a caller supplies a
success Boolean, internally self-consistent fields, or a nonblank reference string — lack of an
authorized verifier must never be interpreted as successful evidence. The Human Owner authorized a
narrow extension of DD-14's existing read-only local-observation boundary, evidence-verification-
only: `ImplementationDiffEvidence` (`IMPLEMENTING`) and `CommitEvidence` (`READY_TO_COMMIT`) are
locally verifiable and are now independently re-derived from real Git state (commit existence,
branch-ancestry reachability, or an independently recomputed tree SHA) before being trusted, using
a new fixed-argv, read-only `LocalEvidenceObserver` (`agentos_workflow/observation/evidence.py`)
built on the same pattern as DD-14's `LocalResumeObserver` — no arbitrary command surface, no
mutable Git operation, no network or GitHub call. `ImplementationDiffEvidence`'s completion-report
reference is confined to a bare filename the engine itself resolves to
`<audit_directory>/<workflow_id>/evidence/<state.value>/<artifact_name>`
(`resolve_evidence_artifact`), with path-component validation, audit-root confinement (defeating
both parent traversal and symlink escape), and an existing-regular-file check — a caller-supplied
path is never taken at face value. `RemoteRefEvidence` (`COMMITTED`) and `PullRequestEvidence`
(`PUSHED`) describe remote/GitHub facts AUTO-002 has no authorized network-reaching observer for;
both now unconditionally fail closed with a new `ReconciliationVerifierUnavailableError`, remaining
pending future authorized Skill/GitHub observation work. This decision explicitly does not
authorize network access, GitHub access, a general Skill or Agent interface, any mutable Git
operation, or starting AUTO-003 or AUTO-005.

**Rationale:** Without this decision, any caller (or a future buggy or compromised Skill) could
claim any reconciliation outcome for any commit, remote ref, or pull request and have it accepted
verbatim — the exact "evidence-free bypass path" class of defect this program's governance has
previously required be closed rather than left as a weaker parallel path. Confining the newly
authorized verification strictly to already-locally-observable facts, and failing closed rather
than guessing for everything else (remote/PR state), keeps the extension narrow and auditable
rather than opening a general execution or network capability.

**What changed:** `agentos_workflow/observation/evidence.py` added (`LocalEvidenceObserver`,
`LocalEvidenceObservationError`, `resolve_evidence_artifact`); `agentos_workflow/observation/
__init__.py` exports them; `agentos_workflow/orchestrator/engine.py` gained
`ReconciliationVerifierUnavailableError`, `LocalEvidenceVerificationFailedError`, and
`_verify_evidence_locally`, wired into the existing `evaluate_initial_execution_failure`
immediately after its existing internal-consistency check — no public signature changed.
`docs/workflow-automation/DECISIONS.md` gained DD-15 (version 1.4 → 1.5);
`docs/workflow-automation/CHANGELOG.md` gained a corresponding `[Unreleased]` entry (version 2.3 →
2.4); `docs/reports/workflow-automation/AUTO-002-completion-report.md` gained a corresponding
addendum. Two gaps are explicitly acknowledged as remaining, not silently assumed solved:
evidence-artifact binding does not yet reach the specific retry attempt (no `attempt_number` field
exists on any evidence type to bind against), and `ImplementationDiffEvidence` has no
`changed_paths` field, so changed-path scope is not independently checkable from evidence alone
today.

**Scope/status:** AUTO-002 remains `IN_PROGRESS`; AUTO-003 and AUTO-005 remain unauthorized and
`NOT_STARTED`. No commit, push, merge, branch change, upstream change, or stash mutation occurred.

## 2026-07-27 — Governance Correction Record: DD-14 ordering defect in `DECISIONS.md` corrected; `STAGE_REGISTRY.md` §6 decision index synchronized

**Decision:** A fresh session, resuming AUTO-002 under an explicit trust-boundary instruction not
to treat its handoff as authoritative proof, independently reconciled the F01/F02/F03 findings
before starting F04. That reconciliation found two governance-document defects, both introduced by
the immediately preceding (F03) session, neither previously disclosed in any handoff or report:

1. `docs/workflow-automation/DECISIONS.md`'s DD-14 entry (recorded in the entry immediately below
   this one) was physically appended between DD-01 and DD-02, rather than after DD-13, breaking
   this file's otherwise-strict ascending DD-01→DD-13 ordering with no supersession note explaining
   the placement.
2. `docs/workflow-automation/STAGE_REGISTRY.md` §6 ("Decision References") still read "DD-01
   through DD-13," not updated to reflect DD-14's addition.

The Human Owner reviewed this finding and authorized this Governance Correction Record
(`STAGE_REGISTRY.md` §3 rule 18), explicitly directing that DD-14 not be moved, deleted,
renumbered, or rewritten, and that no earlier decision entry's text be altered.

**Corrected facts:**

- DD-14 is valid and binding, exactly as originally recorded; its content is unchanged by this
  correction.
- The ordering defect does not invalidate DD-14 or any other decision.
- No decision identifier is being changed by this record; no historical decision text is being
  removed.
- The effective decision sequence, for all purposes going forward, is **DD-01 through DD-14**,
  regardless of DD-14's physical position in `DECISIONS.md`.
- This record supersedes only the implied physical ordering of `DECISIONS.md`; it does not
  supersede or re-litigate the content of any decision, including DD-14 itself.

**What changed:** `docs/workflow-automation/DECISIONS.md` gained an append-only "Governance
Correction Record (2026-07-27) — DD-14 physical placement" note after DD-13 (version 1.3 → 1.4),
cross-referencing this entry; DD-14's own text is untouched. `docs/workflow-automation/
STAGE_REGISTRY.md` §6 corrected to "DD-01 through DD-14," with a one-line note pointing back to
this record (version 6.1 → 6.2). `docs/workflow-automation/CHANGELOG.md` gained a corresponding
`[Unreleased]` entry (version 2.2 → 2.3). `docs/reports/workflow-automation/
AUTO-002-completion-report.md` gained a short addendum disclosing the defect and its correction,
per the same append-only, no-rewrite discipline every prior addendum to that report has followed.

**Who found it and when:** an independent fresh-session governance reconciliation audit, performed
2026-07-27, before any AUTO002-F04 work began, per the session's standing instruction not to trust
the prior session's handoff without direct verification.

**Scope/status:** AUTO-002 remains `IN_PROGRESS`; AUTO-003 remains unauthorized and `NOT_STARTED`.
No workflow state, transition, implementation file, or test file was touched by this correction. No
commit, push, merge, branch change, or stash mutation occurred. The pre-existing, expected
`upstream_missing` `workflowctl verify` finding is untouched and not addressed by this record.

## 2026-07-27 — Human Owner decisions: AUTO002-F03 local read-only observation boundary and state-specific resume policy

**Decision:** The Human Owner expanded AUTO-002 only enough to add a typed, local, read-only
resume observation boundary, then supplied the authoritative per-state branch, HEAD,
working-tree, control-artifact, ancestry, baseline-protection, and uncertain-operation policy.
Production resume constructs the observer internally and makes every authorization decision;
test adapters may return raw observations but never a verdict. Fixed allowlisted local Git
queries, confined contract reads, and canonical runtime-version observation are permitted.
Arbitrary commands, mutation, network/GitHub access, Providers, the general Skill interface,
and importing the root `GitClient` remain prohibited.

**Rationale:** `WorkflowSession.resume` could previously accept a
`CurrentAuthorizationBinding` copied directly from `authorization.json`, so repository,
contract, Git, and runtime facts were never independently observed. The prior phrases
"working tree state as expected" and "cleanliness where expected" also lacked a state/crash-
boundary definition. The new policy closes both gaps without adding a workflow state, changing
an edge, or starting AUTO-003.

**Scope/status:** Recorded normatively in `docs/workflow-automation/DECISIONS.md` DD-14,
`WORKFLOW_STATES.md` §6a, `MACHINE_GATES.md` §2a, `ARCHITECTURE.md`, and
`stage-prompts/AUTO-002.md`. AUTO-002 remains `IN_PROGRESS`; AUTO-003 remains unauthorized and
`NOT_STARTED`.

## 2026-07-26 — Human Owner policy decision recorded and applied: OD-4 (infrastructure retries, repair attempts, and initial-execution attempts are three separate durable counters)

**Decision:** The Human Owner supplied the explicit policy sign-off `OPEN_QUESTIONS.md` OD-4 was
waiting on before AUTO-002 could encode the infrastructure-retry/repair-attempt separation as
load-bearing behavior rather than documentation intent. Recorded here verbatim as the approval
basis, then summarized by what changed.

**OD-4 approval, verbatim:**

> I am the Human Owner of this repository.
>
> I approve the following governance decision for OD-4.
>
> Infrastructure retries are separate from the provider-driven repair-attempt counter.
>
> Infrastructure retries are permitted only when durable evidence proves that invocation did not
> begin and no external side effect could have occurred.
>
> Infrastructure retries do not increment the repair-attempt counter.
>
> If invocation may have started, infrastructure retry is prohibited. Mandatory reconciliation is
> required.
>
> Repair attempts, initial-execution attempts, and infrastructure retries are three separate
> durable event streams and counters.
>
> Record this as the official Human Owner disposition for OD-4.
>
> Update only the required governance documentation and completion report accordingly.
>
> Do not change implementation unless this governance decision requires a purely documentary
> synchronization.

**What changed:** `docs/workflow-automation/WORKFLOW_STATES.md` §5's parenthetical ("`OPEN_QUESTIONS.md`
OD-4 tracks confirming this separation before AUTO-002 implementation") is replaced with a
resolved-confirmation statement citing this entry — no wording about the *policy itself* changed,
since §5 already stated exactly the three-way separation this approval confirms (infrastructure
retry: Skill-internal, bounded, backoff, never touches the repair counter; repair attempts:
the `VALIDATING`/`QA_RUNNING` ⇄ `REPAIRING` cycle, §3/`FAILURE_RECOVERY.md`; initial-execution
attempts: §5a's provider/commit/push/PR policy, OD-9) — version 4.1 → **4.2**. Cross-posted as
`docs/workflow-automation/DECISIONS.md` DD-13. `OPEN_QUESTIONS.md` OD-4 moved from Open to
Resolved (version 1.3 → 1.4). `docs/workflow-automation/STAGE_REGISTRY.md` §6 corrected to include
DD-13 (and, on the same pass, DD-09 through DD-12, which a prior audit found missing — version 6.0
→ **6.1**).

**No AUTO-002 code change was required or made**, per this approval's own instruction to leave
implementation untouched absent a genuine documentary-synchronization need. AUTO-002's
`AttemptKind.INITIAL_EXECUTION`/`AttemptKind.REPAIR` (`agentos_workflow/orchestrator/engine.py`)
already implement two of this approval's three streams as independent, durable counters exactly
as approved. The third stream — infrastructure retry (e.g. a flaky GitHub API call) — has no
corresponding code anywhere in `agentos_workflow/` today, because AUTO-002 implements no Skill,
Provider, or Git/GitHub call of any kind (`AUTO-002.md`'s own out-of-scope list) — there is no
infrastructure call yet for such a retry to apply to. Building that third counter is therefore
correctly deferred to whichever future stage first introduces an actual infrastructure call
(a Git/GitHub Skill, most likely AUTO-003 or AUTO-006) — that stage's own implementation must
honor this approval's three-way separation from the moment it introduces the first retryable
infrastructure call, not retrofit it later. Checked `docs/TASK_QUEUE.md`, `docs/current_task.md`,
`docs/PROJECT_STATE.md` for any other live content referencing OD-4's `Open` status needing
sync — none found beyond the AUTO-002 completion report, corrected separately in its own addendum.

**Alternatives considered:** Adding a placeholder third `AttemptKind` member to AUTO-002's code now,
even with no infrastructure call to drive it — rejected as speculative implementation for a
capability this stage's own contract explicitly excludes, and as exactly the kind of
unrequested, unused abstraction this repository's engineering discipline avoids elsewhere.

**Rationale:** OD-4 was a policy-confirmation gate, not an open design question — `WORKFLOW_STATES.md`
§5 already fully specified the three-way separation this approval ratifies; what was missing was
solely the Human Owner's sign-off making it load-bearing, which this entry supplies.

## 2026-07-24 — Governance Correction Record: OD-9 retry-classification defect fixed, a missing Dashboard changelog entry appended, and the AUTO-002 branch procedure made fully durable

**Decision:** A further independent audit (Codex) found three defects in how the already-approved
OD-8/OD-9 policies (entry directly below) and this recovery's own prior work were represented —
resolved here without revisiting either policy's substance.

1. **The OD-9 retry classification in `SKILL_CONTRACTS.md`/`MODEL_PROVIDER_CONTRACTS.md` was
   weaker than the approved policy.** Confirmed real by re-reading the exact prior text: it
   listed "process/network timeout, connection reset, DNS failure" as unconditionally
   `retryable` "before any confirmed side effect" — treating error *type* as determinative, when
   the approved policy makes error *timing* determinative ("absence of confirmation is not proof
   that no side effect occurred"). A timeout can occur exactly as easily after a `git push`
   already reached the remote as before it sent anything. Corrected: `SKILL_CONTRACTS.md` §5 and
   `MODEL_PROVIDER_CONTRACTS.md` §2 now classify strictly by timing — "proven pre-side-effect"
   is narrowed to failures before the underlying `git`/`gh`/provider subprocess was ever
   invoked (precondition-check failure, spawn failure); every failure surfaced by an
   already-invoked subprocess, regardless of how the error is labeled, defaults to the
   possible/unknown-side-effect (mandatory reconciliation) bucket. `WORKFLOW_STATES.md` §5a
   item 1 tightened to state this explicitly and rule out error-type-based classification. No
   new state or transition — this is a correction to make the documentation actually implement
   OD-9 as approved, not a new decision. Versions: `SKILL_CONTRACTS.md` 1.1 → **1.2**,
   `MODEL_PROVIDER_CONTRACTS.md` 1.1 → **1.2**, `WORKFLOW_STATES.md` 4.0 → **4.1** (wording
   fidelity to the existing MAJOR approval, not a further MAJOR change).
2. **`docs/agentos-dashboard/STAGE_REGISTRY.md`'s 4.0 → 5.0 transition (incorporating the OD-8
   mirror) had no corresponding `docs/agentos-dashboard/CHANGELOG.md` entry.** Confirmed by
   direct comparison: the changelog's newest entry (`CL-20260724-05`) only accounted for the
   3.0 → 4.0 step. Appended `CL-20260724-06` (newest-first, above the existing entries, none of
   which were touched) recording the 4.0 → 5.0 transition, its OD-8 reason, and the existing
   approval basis. Audited every other version transition from this recovery for a matching
   changelog entry — none else was missing.
3. **Live documents still framed AUTO-002's branch route as an open Human Owner choice,
   including renaming the recovery branch before merge.** That framing predates the settled
   release procedure. Rewrote `docs/PROJECT_STATE.md` ("In progress" and "Blockers"),
   `docs/TASK_QUEUE.md`, `docs/current_task.md`, `docs/remaining_tasks.md`,
   `docs/workflow-automation/STAGE_REGISTRY.md` §7, and `handover/PROJECT_HANDOVER.md` to state
   the durable procedure as settled fact: this recovery branch is reviewed, committed, pushed,
   merged, and deleted through the ordinary recovery release process, never renamed into the
   AUTO-002 branch; only after that does an AUTO-002 session begin from clean `main` and create
   the canonical branch; this is not a new AUTO-002 authorization, and implementation does not
   begin during governance recovery. `stage-prompts/AUTO-002.md` needed no change — it already
   named only the canonical branch, never the temporary one. `STAGE_REGISTRY.md` §5's append-only
   Authorization Log rows (the historical discovery) were **not** touched.

Verified after all edits: `workflowctl verify` — `task-state`/`governance`/`handover` PASS, `git`
FAILs only on the same pre-existing `upstream_missing`. `ruff`/`black`/`mypy` all pass; `pytest`
978 passed, unchanged. Exactly one `Current` task (AUTO-002, `BLOCKED`, unchanged). No lifecycle
transition, authorization, or AUTO-002 implementation changed; no stash mutated; no branch
renamed.

**Alternatives considered:** (a) For item 1, keeping the error-type-based classification and
just widening its exception list — rejected: any finite list of "usually pre-effect" error types
would still be vulnerable to the exact counterexample that motivated the finding (a timeout is a
timeout whether it happens before or after the write); timing, not type, is the only classifier
consistent with "absence of confirmation is not proof." (b) For item 2, folding the missing entry
into the existing `CL-20260724-05` — rejected: that entry is already written and this changelog
is explicitly append-only ("Entries are appended, never edited"). (c) For item 3, leaving
`docs/DECISION_LOG.md`'s own historical entries describing the original discovery unedited —
correct and done: only *live* documents describing *current/future* state were rewritten; the
append-only historical record stands.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`. All three are fidelity/completeness
corrections to already-approved policy and already-recorded facts — no new governance decision
was made, and the Human Owner's OD-8/OD-9 approvals (entry below) are unchanged.

## 2026-07-24 — Human Owner policy decisions recorded and applied: OD-8 (`SUPERSEDED` task-status semantics) and OD-9 (initial-execution failure policy)

**Decision:** The Human Owner supplied explicit policy decisions for the two design questions
the twelfth pass (entry below) deliberately left open, and directed that both be fully and
consistently applied. Both are recorded here verbatim as their approval basis, then summarized
by what changed.

**OD-8 approval, verbatim:**

> I approve the following policy:
>
> - A lifecycle stage in SUPERSEDED maps to task status Done.
> - Done here means administratively closed and no longer active or planned.
> - SUPERSEDED must not be represented as successful completion.
> - Lifecycle outcome remains distinguishable:
>   - COMPLETE means successfully completed.
>   - SUPERSEDED means closed because a Human Owner replaced or abandoned it in favor of another
>     authorized stage.
> - Any successor stage must have its own independent task record and lifecycle authorization.
> - SUPERSEDED must not automatically authorize or start a successor.
> - Define the legal source transitions to SUPERSEDED explicitly.
> - Do not introduce a new fourth task status.

**OD-9 approval, verbatim:**

> I approve the following policy for initial execution failures involving: implementation
> providers; commit operations; push operations; PR creation; comparable external or
> side-effecting operations.
>
> 1. TRANSIENT FAILURE BEFORE ANY SIDE EFFECT — Permit a bounded retry while remaining in the
>    same runtime state. The retry limit and retryable-error classification must be explicit and
>    deterministic. Exhausting the retry limit transitions the workflow to FAILED.
> 2. FAILURE WITH POSSIBLE OR UNKNOWN SIDE EFFECT — Do not retry blindly. First perform an
>    idempotency/reconciliation check while remaining in the same state. Determine whether the
>    intended side effect already occurred.
> 3. RECONCILIATION SUCCESS — If the side effect occurred correctly, advance to the runtime state
>    that accurately represents repository or remote reality. Do not duplicate the commit, push,
>    or PR.
> 4. RECOVERABLE INCONSISTENCY — If the state is inconsistent but safely repairable under the
>    existing recovery model, use the existing REPAIRING path. Do not invent a second repair
>    lifecycle.
> 5. UNRECOVERABLE OR INDETERMINATE FAILURE — Transition to FAILED when: retry is exhausted;
>    reconciliation cannot establish a safe state; the side effect is inconsistent and not safely
>    repairable; required invariants cannot be restored.
> 6. SAFETY — Never report success solely because a command timed out. Never repeat a
>    side-effecting operation without reconciliation. The Orchestrator owns the transition
>    decision based on typed Agent/Skill results. Existing authorization and clean-tree
>    requirements remain unchanged.
>
> Treat the new failure-trigger semantics as the appropriate normative governance change under
> the applicable version policy. Record this message verbatim as the Human Owner approval basis.

**What changed, OD-8:** `docs/workflow-automation/STAGE_REGISTRY.md` §2 (state-mapping sentence
now includes `SUPERSEDED` ≈ `Done`, with the administratively-closed-vs-successful distinction
stated explicitly) and rule 9 (rewritten: legal source states — `AUTHORIZED`, `BLOCKED`,
`IN_PROGRESS`, `SELF_REVIEW`, `REVIEW`, `APPROVAL`; never `NOT_STARTED`/`PROPOSED`/`COMPLETE`;
the `Done` mapping; no automatic successor authorization; a successor's independent task record
and authorization requirement) — version 5.0 → **6.0**. Mirrored into
`docs/agentos-dashboard/STAGE_REGISTRY.md` §1/rule 9 — version 4.0 → **5.0**. No fourth task
status was introduced anywhere; `self-governance.yaml`/`workflowctl` still recognize exactly
`Current`/`Planned`/`Done`. Cross-posted as `DECISIONS.md` DD-08. `OPEN_QUESTIONS.md` OD-8 moved
from Open to Resolved (its own append-only-by-convention Format). Checked `docs/TASK_QUEUE.md`,
`docs/PROJECT_STATE.md`, `docs/current_task.md`, `docs/remaining_tasks.md` for any live
`SUPERSEDED`-related content needing sync — none found (no stage is currently `SUPERSEDED`), so
none required editing.

**What changed, OD-9:** `docs/workflow-automation/WORKFLOW_STATES.md` gained new §5a
(Initial-Execution Failure and Reconciliation), restating the six-point policy in this
document set's own terms, scoped exactly to `IMPLEMENTING`, `READY_TO_COMMIT`, `COMMITTED`,
`PUSHED` (the implementation-provider invocation and the `create_commit`/`push_stage_branch`/
`create_pull_request` Skills) — no state or transition added; only new *reasons* on the four
already-existing `→ FAILED` edges for those states (already added in the ninth-pass approval)
and expanded reasons on their four forward edges (already existing); §3's table and explanatory
paragraph updated to name this as a third `→ FAILED` reason alongside the existing two — version
3.2 → **4.0**. Cross-referenced (not substantively changed) in `MACHINE_GATES.md` §1 (a third,
non-gate failure path, → 1.2), `FAILURE_RECOVERY.md` (new §1a distinguishing this from the
existing code-repair policy, Purpose line updated, → 1.2), `AGENT_CONTRACTS.md`
(`ImplementationAgent`/`GitAgent`/Agent-to-State-Map notes that the Orchestrator, never the
Agent, decides the resulting transition, → 1.2), `TEST_STRATEGY.md` (new §4b naming the required
test coverage for all five numbered outcomes plus the safety property, → 1.2). Added the
explicit, deterministic retryable/non-retryable error classification and 3-attempt retry limit
OD-9 item 1 requires to `SKILL_CONTRACTS.md` (Git/GitHub Skills, → 1.1) and
`MODEL_PROVIDER_CONTRACTS.md` (provider invocation, → 1.1). Cross-posted as `DECISIONS.md` DD-09.
`OPEN_QUESTIONS.md` OD-9 moved from Open to Resolved. Checked `docs/TASK_QUEUE.md`,
`docs/PROJECT_STATE.md` for any live content needing sync — none found (no provider/commit/push/
PR failure is currently in progress; AUTO-002 has not started implementation), so none required
editing.

**Design judgment calls made while applying OD-9 (flagged explicitly, not silently decided):**
(a) "comparable external or side-effecting operations" in the approval's own preamble was read
narrowly — applied only to the four operations the approval's numbered policy and this
program's own document set actually name (provider invocation, `create_commit`,
`push_stage_branch`, `create_pull_request`) — not extended to `enable_automatic_squash_merge`,
`read_required_checks`, or the Closeout Skills, which already have their own complete gate
semantics in `MACHINE_GATES.md` §5–§7 that this decision does not touch. (b) Item 4's "use the
existing REPAIRING path" was read as applying only where `REPAIRING` is actually reachable today
(from `IMPLEMENTING`, via the existing `VALIDATING` route) — for `READY_TO_COMMIT`/`COMMITTED`/
`PUSHED`, where no code-fix path exists, an unresolved inconsistency was read as falling to item
5 (`FAILED`) rather than inventing a new edge into `REPAIRING` from those states. Both are
documented here so the Human Owner can correct either reading if it does not match intent.

**Alternatives considered:** for OD-8, mapping `SUPERSEDED` to `Current` instead of `Done` (it
*was* rejected by the user's own explicit "Done here means administratively closed" instruction,
recorded only for completeness) — the approval is unambiguous and was applied as given, not
re-derived. For OD-9, adding a literal `IMPLEMENTING → REPAIRING` edge for a cleaner-looking
direct path — rejected per the "do not invent a second repair lifecycle" instruction and this
recovery's standing preference for reusing existing edges over adding new ones wherever the
existing model already suffices.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`'s requirement that governance changes,
including policy decisions with their approval basis, be logged verbatim rather than summarized
or inferred. Both approvals were applied completely and consistently across every document named
in the Human Owner's own audit list, with the two judgment calls above disclosed rather than
silently resolved.

## 2026-07-24 — Governance recovery, twelfth pass: approved consistency fixes applied; two design questions deferred

**Decision:** The latest independent Codex review produced six findings. A subsequent
classification pass, performed without repository mutation, classified four as corrections that
do not require a new Human Owner policy decision and two as unresolved design decisions. The
operator then explicitly directed this recovery to apply only the four non-policy corrections,
record the other two as open questions without selecting a policy, rerun the complete validation
suite, and perform no release action or AUTO-002 implementation.

Applied corrections:

1. **Dashboard resume preflight:** `docs/agentos-dashboard/STAGE_REGISTRY.md` now restates AUTO
   rule 19's already-established initial-start/resume distinction as Dashboard rule 20, and the
   Dashboard SSP has matching initial-start and resume sections. This closes a real inconsistency
   with that registry's existing substantive-equivalence rule. It adds no state or transition:
   pass and fail during resume both leave registry state unchanged, and neither changes
   authorization or task status. Registry 3.0 → 4.0 under its control-rule revision policy; SSP
   1.2 → 1.3.
2. **Dashboard/AUTO rule crosswalk:** the explanatory equivalence range now includes Dashboard
   rule 20 ↔ AUTO rule 19. No governing behavior changed independently of item 1.
3. **Machine-gate count wording:** `WORKFLOW_STATES.md` now identifies six named gates correctly:
   the single Precondition gate spans two transition-source states, followed by five one-state
   gates. No state, transition, trigger, gate condition, or failure policy changed; version
   3.1 → 3.2 as a wording-only clarification.
4. **Git stash wording:** the handover now says the recovery branch is the sole local branch
   without an upstream, rather than the sole "unpushed ref," and separately records the two
   retained local stash snapshots. No stash was applied, dropped, or modified.

Deliberately unresolved, with no policy invented:

- `OPEN_QUESTIONS.md` OD-8 records the missing `SUPERSEDED` development-stage task-status
  mapping. The existing state, transitions, Human Owner directive requirement, and three-status
  task model remain unchanged.
- `OPEN_QUESTIONS.md` OD-9 records the undefined initial-execution failure policy for provider,
  commit, push, and PR operations. The runtime transition table, transition reasons,
  authorization model, repair counter, and release behavior remain unchanged.

**Alternatives considered:** implementing a `SUPERSEDED` mapping or assigning ordinary
initial-execution failures to an existing `→ FAILED` edge — rejected for this pass because each
would select new semantics among multiple valid policies and therefore requires a Human Owner
decision. Treating the Dashboard resume defect as the same kind of policy gap was also rejected:
the Dashboard registry already promises substantive equivalence with AUTO except for its named
Rollback rule, so mirroring AUTO's zero-transition resume preflight corrects an existing promise
rather than expanding it.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`. This pass is restricted to internal
consistency and factual synchronization. It does not start or re-authorize AUTO-002 and does not
authorize a commit, push, pull request, merge, branch rename, stash mutation, or branch deletion.

## 2026-07-24 — Governance recovery, eleventh pass: initial-start/resume preflight separated, GOV-2 mirrored into all remaining-work summaries, and the AUTO-002 branch blocker made durable

**Decision:** An eleventh independent audit (Codex) raised three further findings.

1. **The SSP's single preflight check ("status is `AUTHORIZED`") made resuming an already-
   `IN_PROGRESS` AUTO-00x stage impossible**, since a session picking up mid-implementation would
   find registry state `IN_PROGRESS`, not `AUTHORIZED`, and fail the literal check. Confirmed
   real by direct re-reading of `stage-prompts/README.md`'s prior text, which stated one
   undifferentiated check "before any change" with no resume carve-out. Resolved with **no new
   transitions**: added `STAGE_REGISTRY.md` §3 rule 19 (Resume Preflight), which states the legal
   resume-state set (`IN_PROGRESS`/`SELF_REVIEW`/`REVIEW`/`APPROVAL` — never `AUTHORIZED` again),
   requires re-verifying the same execution preconditions checked at initial start, and — for
   both the pass and fail outcome — causes **zero registry transition**: a passing resume simply
   continues (rule 5's existing "stage stays `IN_PROGRESS`" principle, now stated to also cover
   resume, not only review-retry); a failing resume stops the session and reports to the Human
   Owner without moving to `BLOCKED` (`BLOCKED` remains reserved for the pre-`IN_PROGRESS` case,
   rule 17) and without triggering re-authorization. This required no Human Owner approval:
   `STAGE_REGISTRY.md` §8's revision policy requires only a MAJOR version bump for control-rule
   changes, not the separate "Human Owner review" gate `WORKFLOW_STATES.md` §11 imposes for its
   own (different) machine — confirmed by re-reading both documents' revision-policy text
   side by side. The SSP (`stage-prompts/README.md`) was restructured into explicit
   "Initial-start preflight" and "Resume preflight" sections citing rules 4 and 19 respectively;
   `stage-prompts/AUTO-002.md` reworded to cite both. On the runtime-machine side
   (`WORKFLOW_STATES.md`), the existing model (built and Human-Owner-approved in the ninth/tenth
   passes) already fully satisfies the same initial-start/resume distinction — confirmed by
   re-reading `WORKFLOW_STATES.md` §6, `FAILURE_RECOVERY.md` §6, `TEST_STRATEGY.md` §4a, and
   `AGENT_CONTRACTS.md` directly; only a labeling paragraph was added to `WORKFLOW_STATES.md` §3
   (no new transition) making the initial-start/resume phase split explicit there too.
2. **`GOV-2` was a `Planned` task in `docs/TASK_QUEUE.md` and `docs/remaining_tasks.md` but
   absent from `docs/PROJECT_STATE.md`'s "Planned" section and `handover/PROJECT_HANDOVER.md`'s
   "What's next" summary.** Confirmed by direct re-reading of both files — neither mentioned it.
   Added to both, preserving the existing AUTO/DASH/governance-tooling distinction (GOV-2 is
   explicitly framed as the one non-AUTO/DASH-family Planned task in each), kept `Planned`, not
   described as implemented or authorized.
3. **Every live description of AUTO-002's branch blocker named the specific temporary
   governance-recovery branch** (`feature/auto-002-orchestrator-foundation`) as the subject of
   the mismatch — an assertion that becomes false the moment that branch is merged and deleted.
   Rewrote every live-state document (`docs/PROJECT_STATE.md`, `docs/TASK_QUEUE.md`,
   `docs/current_task.md`, `docs/remaining_tasks.md`, `handover/PROJECT_HANDOVER.md`,
   `docs/workflow-automation/STAGE_REGISTRY.md` §7) to state the blocker as a durable rule
   independent of any branch name: `BLOCKED` until this recovery merges; an AUTO-002 session must
   then begin from updated clean `main` and create/check out the canonical branch
   (`feature/auto-002-orchestrator-state-machine`, unchanged — not reauthorized, not renamed);
   that branch must pass the initial-start branch-binding/clean-tree checks before
   `AUTHORIZED → IN_PROGRESS`. `STAGE_REGISTRY.md` §5's append-only Authorization Log rows
   (which do name the temporary branch, as an accurate record of what was found on 2026-07-24)
   were **not** touched — they remain the correct historical record of the original discovery;
   only the *live, ongoing* assertions in the documents above were made durable.

Verified after all edits: `workflowctl verify` — `task-state`/`governance`/`handover` PASS, `git`
FAILs only on the same pre-existing `upstream_missing`. `pytest` 978 passed, unchanged;
`ruff`/`black`/`mypy` all pass. Exactly one `Current` task (AUTO-002, `BLOCKED`, unchanged). No
lifecycle transition changed; no AUTO-002 implementation performed; AUTO-002's canonical branch
binding, authorization, and this recovery's own working branch were none of them altered.

**Alternatives considered:** (a) For item 1, adding a literal `IN_PROGRESS → BLOCKED` transition
for resume failures (mirroring rule 17's `AUTHORIZED → BLOCKED` pattern) — rejected: it would
recreate the exact `BLOCKED`-must-return-to-`AUTHORIZED`-not-`IN_PROGRESS` deadlock pattern fixed
in the fourth pass, this time demoting a stage that may have substantial `IN_PROGRESS` work
already done; rule 5's "stage stays `IN_PROGRESS`" principle already covers this with zero new
transitions, so it was extended rather than a new one added. (b) For item 3, editing
`STAGE_REGISTRY.md` §5's authorization-log rows to remove the temporary branch's name — rejected:
those rows are the append-only historical record of what was actually found on 2026-07-24 on that
actual branch; removing the name would falsify history rather than make it durable — durability
belongs in the *live* documents describing *current* and *future* state, not in the log of what
already happened.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`. Item 1 closes a genuine SSP defect with no
new normative surface, consistent with this recovery's repeated preference for extending an
existing rule's stated scope over inventing a new transition. Items 2 and 3 are completeness/
durability corrections to already-established facts, not new governance decisions.

## 2026-07-24 — Governance recovery, tenth pass: Dashboard SSP formatter documentation resynchronized, and Dashboard changelog completeness closed

**Decision:** A tenth independent audit (Codex) raised two further findings, both scoped to
`docs/agentos-dashboard/`:

1. **`docs/agentos-dashboard/stage-prompts/README.md` still described the removed pre-commit
   pipeline.** Its pre-commit warning named `` `ruff --fix`, `ruff-format` `` as the auto-fixing
   hooks — stale since the seventh pass removed `ruff-format` from `.pre-commit-config.yaml`
   entirely (Black is the sole formatter; `ruff-check` is lint/import-sort only). Checked
   `docs/workflow-automation/stage-prompts/README.md` (the AUTO program's equivalent) for the
   same staleness — it does not name specific hooks, so it was not stale in this way and needed
   no change. Fixed the DASH SSP to name the actual current hooks in actual pre-commit order
   (`ruff-check --fix`, `black`, `mypy`, matching `.pre-commit-config.yaml` exactly) and added
   `` `ruff format --check .` `` to its recorded validation-command list, matching the AUTO
   program's SSP and this repository's actual validation practice. No repository policy changed
   — only the documentation was synchronized with the already-implemented toolchain (→ 1.2).
2. **`docs/agentos-dashboard/CHANGELOG.md` was missing entries for two already-approved
   revisions**: `STAGE_REGISTRY.md` 2.0 → 3.0 (the seventh-pass rule-17 gap fix and narrowed
   equivalence claim, entry directly below) and `stage-prompts/README.md` 1.0 → 1.1 (the
   fifth-pass `BLOCKED`/SSP-deadlock mirror, entry below), plus the 1.1 → 1.2 change this same
   entry's item 1 just made. Appended three new entries (`CL-20260724-02..04`) to
   `docs/agentos-dashboard/CHANGELOG.md`, each naming version, reason, the pre-existing approval
   basis (this log's own prior entries — no new authorization act), date, and affected files. The
   existing three entries were not touched, per that file's own explicit "Entries are appended,
   never edited" convention.

Verified after the edits: `workflowctl verify` — `task-state`/`governance`/`handover` PASS,
`git` FAILs only on the same pre-existing `upstream_missing`. `ruff format --check .` /
`black --check .` / `ruff check .` / `mypy src` all pass; `pytest` 978 passed, unchanged.

**Alternatives considered:** (a) Editing `docs/agentos-dashboard/CHANGELOG.md`'s existing
`CL-20260724-01` entry to also mention the SSP 1.0 → 1.1 change it happened alongside — rejected:
that entry is already written and this file is explicitly append-only; a new entry documents
what was missed instead. (b) Leaving the DASH SSP's stale hook names since removing
`ruff-format` was itself already fully documented in `docs/DECISION_LOG.md` — rejected: a stage
session executing the SSP verbatim would still be told to expect a hook that no longer exists;
the SSP itself, not just the decision record, needed to reflect current reality.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`. Both items are documentation-synchronization
fixes, not new governance decisions — no repository policy changed, only stale documentation
brought into agreement with already-implemented, already-approved reality.

## 2026-07-24 — Governance recovery, eighth pass: ruff-format/black disagreement fixed at the source file, and governance-validator overclaiming audited (none found)

**Decision:** An eighth independent audit (Codex) raised two further findings and reopened the
failure-transition-completeness question resolved in the entries above.

1. **`ruff format --check .` still failed on `tests/test_migration_plan_apply.py`** even after
   the prior pass removed `ruff-format` as a pre-commit gate — Codex correctly required it not
   be left failing regardless of gate status. Diagnosed as (B) a genuine ruff-format/black
   disagreement on wrapping a long `assert cond, "msg"` (ruff-format hugs the message in trailing
   parens; black wraps the condition instead) — not formatting debt (A) or unstable test logic
   (C). Fixed by extracting the message to a short-lived local variable so the line no longer
   needs wrapping by either tool; both formatters now produce byte-identical output. Verified:
   `ruff format --check .` → "88 files already formatted" (was 1 disagreeing); `black --check .`
   clean; `pytest tests/test_migration_plan_apply.py` → 15 passed, unchanged behavior.
2. **Audited every mention of `check-governance`/`check-task-state`/`workflowctl verify` across
   `docs/CONTEXT.md`, `docs/TASK_QUEUE.md`, and both programs' `STAGE_REGISTRY.md` rule 11/16**
   for overclaiming registry or lifecycle coverage. Found none: every mention already scopes the
   claim precisely to task-status mirror agreement and the `version` fact — never to
   `STAGE_REGISTRY.md` content. `GOV-2`'s existing entry (prior pass) already states the current
   limitation accurately. No documentation changes were needed for this finding; lightweight
   validation remains correctly deferred to `GOV-2`, unimplemented, for the same authorization
   reasons as before.

The failure-transition-completeness question these two findings' audit reopened is resolved in
the entry above (eight approved transitions, Human Owner approval quoted verbatim) — not
repeated here.

**Files changed:** `tests/test_migration_plan_apply.py` (message extracted to a local; no logic
change). No governance document required a change for item 2.

**Verified after the edit:** `ruff check .` / `ruff format --check .` / `black --check .` /
`mypy src` all pass; `pytest` 978 passed (was 978 before — this pass added no new tests, the
existing test's assertion behavior is unchanged); `workflowctl verify` — `task-state`/
`governance`/`handover` PASS, `git` FAILs only on the same pre-existing `upstream_missing`.

**Alternatives considered:** (a) For item 1, pinning `ruff-format` to an older version believed
compatible with the installed `black` instead of restructuring the test — rejected: no version
pair is guaranteed to stay compatible, whereas removing the line-wrapping decision entirely
(short enough line, no wrap needed) cannot regress by tool version drift. (b) For item 2, adding
speculative disclaimers to every governance document "just in case" — rejected: the audit found
no actual overclaiming, and adding unnecessary hedges to already-accurate text would itself be a
form of the imprecision this recovery has been correcting elsewhere.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`. Item 1 is a genuine repository/tooling
defect fixed at its source rather than patched around; item 2 is a verification that produced a
negative result (nothing to fix), recorded so the audit itself is traceable.

## 2026-07-24 — Human Owner approval recorded: `WORKFLOW_STATES.md` §11 MAJOR change (eight normative runtime transitions completing the failure-transition model)

**Decision:** The Human Owner explicitly reviewed and approved, in this Governance Recovery
session, the addition of eight normative runtime transitions to
`docs/workflow-automation/WORKFLOW_STATES.md` §3, closing the gap an independent audit (Codex)
identified: `TEST_STRATEGY.md` §4a requires interruption/authorization-drift testing "at each
state," but §3's table listed `→ FAILED` from only 7 of the 15 non-terminal, non-`CREATED`
states.

**The eight approved transitions:**

- `BRANCH_CREATED → FAILED`
- `IMPLEMENTING → FAILED`
- `REPAIRING → FAILED`
- `READY_TO_COMMIT → FAILED`
- `COMMITTED → FAILED`
- `PUSHED → FAILED`
- `AUTO_MERGE_ENABLED → FAILED`
- `MERGED → FAILED`

For `REPAIRING` specifically, the Human Owner approved the transition for **both** (a)
authorization-drift/interruption detection (the same reason as the other seven) and (b)
unrecoverable failure of the repair attempt itself (provider crash/timeout with no output to
re-validate) — a `REPAIRING`-specific third reason, distinct from (a) and from the
already-covered exhausted-3-attempts path (which fails out via `VALIDATING`/`QA_RUNNING`).

**Classification:** MAJOR, per `WORKFLOW_STATES.md` §11. This is a **separate** MAJOR change
from the three-transition approval recorded earlier today (which brought the document to
2.0) — per the Human Owner's explicit instruction not to reuse that version number, this change
brings `WORKFLOW_STATES.md` to **3.0**.

**Approval basis — quoted verbatim, in full:**

> HUMAN OWNER APPROVAL (this message is the required review/approval).
>
> I approve adding these 8 normative transitions to WORKFLOW_STATES.md, classified as a MAJOR
> change under §11:
> - BRANCH_CREATED → FAILED
> - IMPLEMENTING → FAILED
> - REPAIRING → FAILED
> - READY_TO_COMMIT → FAILED
> - COMMITTED → FAILED
> - PUSHED → FAILED
> - AUTO_MERGE_ENABLED → FAILED
> - MERGED → FAILED
>
> Rationale: authorization drift can surface when resuming from any non-terminal in-flight
> state; interruption recovery needs a legal terminal failure path; TEST_STRATEGY.md requires
> drift testing at each applicable state; the canonical table must not forbid behavior required
> elsewhere in normative governance.
>
> For REPAIRING specifically, approve the FAILED transition for both (a) authorization-drift/
> interruption detection, and (b) unrecoverable failure of the repair attempt itself.

No approval is inferred, assumed, or fabricated beyond what is quoted above.

**Purpose:** to make `WORKFLOW_STATES.md` §3 the complete, closed set of every legal `→ FAILED`
transition in this model, so no prose requirement elsewhere (`§6` interruption recovery,
`FAILURE_RECOVERY.md` §1/§6, `TEST_STRATEGY.md` §4a) implies a transition the canonical table
omits.

**Consistency updates made across the affected document set** (all citing this approval, none
independently re-deciding anything): `WORKFLOW_STATES.md` §3 (the eight rows, plus one
disambiguating paragraph distinguishing the two/three reason-classes populating `→ FAILED`) and
§6 item 3 (cross-reference confirming completeness); `MACHINE_GATES.md` §1 (new paragraph
clarifying its six gates are the forward-progress subset, not the exhaustive `→ FAILED` source,
→ 1.1); `FAILURE_RECOVERY.md` §1 (the `REPAIRING`-specific unrecoverable-attempt path, distinct
from the exhausted-attempts path, → 1.1); `TEST_STRATEGY.md` §4a (cross-reference confirming
"at each state" now has a legal transition to exercise at every state named, → 1.1);
`AGENT_CONTRACTS.md` §8 (a new Agent-to-State Map row attributing the drift-driven transitions to
the Orchestrator, not any named Agent, → 1.1).

**Scope of this approval:** as with the prior `WORKFLOW_STATES.md` approval, this concerns only
the classification and version number of this documentation change. **It does not authorize
AUTO-002 implementation or any commit, push, pull request, merge, or branch rename.** AUTO-002
remains `Current`/`BLOCKED`, unchanged.

**Alternatives considered:** (a) Treating `REPAIRING`'s unrecoverable-attempt case as already
implied by the drift-path approval and not calling it out separately — rejected per the Human
Owner's own explicit instruction to approve it as a distinct, named reason. (b) Reusing version
2.0 since both approvals happened "today" — rejected per the Human Owner's explicit instruction
that a further MAJOR change beyond the already-approved 2.0 change must not reuse that number.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`'s requirement that governance changes,
including MAJOR version classifications, be logged with their approval basis quoted verbatim,
not summarized or inferred.

## 2026-07-24 — Human Owner approval recorded: `WORKFLOW_STATES.md` §11 MAJOR change (three normative runtime transitions)

**Decision:** The Human Owner explicitly reviewed and approved, in this Governance Recovery
session, the addition of three normative runtime transitions to
`docs/workflow-automation/WORKFLOW_STATES.md` §3:

- `AUTHORIZED → FAILED`
- `PRECONDITIONS_CHECKED → FAILED`
- `PR_OPEN → FAILED`

**Classification:** MAJOR, per `WORKFLOW_STATES.md` §11 ("Any new state or transition is a MAJOR
change to this document and requires Human Owner review, since it changes the machine-gate
surface that stands in for human approval after authorization."). A prior governance-recovery
pass added these three transitions but classified the change as MINOR (version bump 1.1 → 1.2)
without a separate, explicit Human Owner review act for this specific document under this
specific policy — an independent audit (Codex) correctly identified this as unresolved. This
entry supplies that missing review and closes the gap; `WORKFLOW_STATES.md` is now version 2.0.

**Approval basis:** the Human Owner's direct, explicit instruction in this session: "I explicitly
approve the addition of these three normative runtime transitions: AUTHORIZED → FAILED,
PRECONDITIONS_CHECKED → FAILED, PR_OPEN → FAILED. Treat this message as the required Human Owner
review and approval under WORKFLOW_STATES.md §11. Classify the change as MAJOR. Bump
WORKFLOW_STATES.md to version 2.0." No approval is inferred, assumed, or fabricated — it is
quoted verbatim above.

**Purpose:** to reconcile `WORKFLOW_STATES.md` §3's canonical transition table with failure
behavior that `MACHINE_GATES.md` §2 (Precondition Gate) and §5/§8 (Merge Safety Gate) already
state as normative and mandatory — `MACHINE_GATES.md` documents these three gates failing to
`FAILED` from `AUTHORIZED`, `PRECONDITIONS_CHECKED`, and `PR_OPEN` respectively, and prior to this
change `WORKFLOW_STATES.md` §3 did not list any of the three, an inconsistency between two
equally normative documents (found and reasoned through in the prior "fifth pass" entry below).
This approval brings the transition table into agreement with behavior that was already
mandatory, rather than introducing new machine-gate behavior that did not exist before.

**Scope of this approval:** this approval concerns only the classification and version number of
this specific documentation change. **It does not authorize AUTO-002 implementation, any
commit, push, pull request, merge, or branch rename, or any other release action.** AUTO-002
remains `Current`/`BLOCKED` in `docs/TASK_QUEUE.md` and `docs/workflow-automation/
STAGE_REGISTRY.md` §4, unchanged by this entry.

Updated for consistency with the 2.0 version number: `docs/CHANGELOG.md`,
`docs/workflow-automation/CHANGELOG.md`, and `handover/PROJECT_HANDOVER.md` (+ regenerated
`handover/PROJECT_CHECKSUM.md`) — see the entries/edits following this one for the exact changes.

**Alternatives considered:** (a) Classifying as MINOR on the reasoning that
`MACHINE_GATES.md` already mandated this behavior, so nothing "new" was added to the system's
actual behavior — this was presented to the Human Owner as an available option; not chosen. (b)
Reverting the three transitions pending a separately authorized future task — also presented;
not chosen. (c) Silently leaving the MINOR classification uncorrected — never a real option,
since the mission underlying this recovery explicitly required stopping and asking rather than
fabricating or assuming approval for exactly this kind of self-versioning-policy question.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`'s requirement that governance changes,
including version classifications for documents with their own explicit revision policy, be
logged with their approval basis and rationale — verbatim, not summarized or inferred.

## 2026-07-24 — Governance recovery, seventh pass: Dashboard/AUTO equivalence claim corrected, stale AUTO-002 authorization wording fixed, formatter non-determinism eliminated, and governance-validator coverage gap tracked

**Decision:** A seventh independent audit (Codex) raised four further findings and one release
gate. Resolved as follows:

1. **The claim that Dashboard and AUTO registry rules are "identical in substance" was audited
   rule-by-rule against the actual current text of both files, not asserted.** Found: (a) a real
   gap — `docs/agentos-dashboard/STAGE_REGISTRY.md` rule 17 (Closeout) was missing the entire
   `git`-check exception-tolerance clause that `docs/workflow-automation/STAGE_REGISTRY.md` rule
   16 has (task-state/governance/handover PASS with no exception, `git` PASS unless pre-existing
   and unrelated to the merge) — fixed by adding the matching clause to DASH's rule 17; (b) DASH
   has one genuine, intentional program-specific rule with no AUTO counterpart — rule 14
   (Rollback, concerning `dashboard.db`, an artifact AUTO has no equivalent of). Every other rule
   (1–13, 15–19 in DASH ≈ 1–13, 14–18 in AUTO, accounting for the rule-14 offset) was checked and
   found substantively equivalent, differing only in verbosity (DASH states some rules — early-
   start prevention, evidence-before-completion — with more procedural detail; this is
   longstanding original-authorship wording, not new drift, and not a contradiction). `docs/
   agentos-dashboard/STAGE_REGISTRY.md` §1 was reworded from a blanket "identical in substance"
   claim to a precise list (which rules are shared, which is program-specific), so the claim is
   now exactly as strong as the evidence supports.
2. **`docs/workflow-automation/STAGE_REGISTRY.md` §7 stated "AUTO-002 authorization requires
   AUTO-001 `COMPLETE` plus a fresh Human Owner record"** — stale: both conditions were already
   satisfied and recorded on 2026-07-24 (§5). Reworded to state this as a completed fact (with the
   date and evidence location), distinguish it from AUTO-002's actual, still-open item (the
   execution-precondition branch mismatch, unrelated to authorization), and contrast it with
   AUTO-003, whose authorization precondition genuinely remains outstanding (AUTO-002 has not
   reached `COMPLETE`) — so the same sentence pattern is not applied where it would itself become
   stale.
3. **Formatter non-determinism, investigated as a release gate rather than dismissed.** Root
   cause confirmed, not assumed: `.pre-commit-config.yaml` ran **two different formatters**
   (`ruff-format` and `black`) over the same files, which have measurably diverged (a long
   parenthesized `assert x, "msg"` is wrapped differently by each), so which one "won" depended on
   hook order and left the other's preferred form as a perpetual pending diff — this was the
   actual non-determinism, not merely stale version pins. `docs/workflow-automation/
   stage-prompts/README.md`'s own required validation command list has only ever named
   `ruff check .` and `black --check .` — never `ruff format --check .` — confirming Black is this
   repository's actual canonical formatter and `ruff-format`'s presence in the pre-commit hook set
   was the misconfiguration. Fixed: removed the `ruff-format` hook entirely (ruff now runs
   `ruff-check --fix` only — linting and import-sorting, not formatting); separately, and because
   drift existed there too, re-pinned all three hooks to the exact revisions matching the locally
   installed tool versions confirmed by direct version query (`ruff-pre-commit` v0.12.3 → v0.15.21;
   `black-pre-commit-mirror` 25.1.0 → 25.12.0; `mirrors-mypy` v1.16.1 → v1.20.2 — all three tags
   confirmed to exist via `git ls-remote` before pinning). Verified idempotent: `pre-commit run
   --all-files` run twice in sequence from a clean pre-commit cache, both runs reporting all three
   hooks Passed with zero file modifications either time (previously, every run had mutated
   `tests/test_migration_readers.py`). `black --check .` passes repository-wide;
   `ruff format --check .` still disagrees with `black` on one file, which is now expected and
   non-blocking, since `ruff-format` is no longer a gate.
4. **Governance-validator coverage assessed, not implemented.** Read
   `src/ai_workflow_engine/governance/validators.py` directly: `check_governance`/
   `check_task_state` validate only task-status mirror agreement and byte-equality of configured
   regex "facts" (currently just `version`) — neither reads either program's `STAGE_REGISTRY.md`
   at all. Confirmed this cannot be safely retrofitted via `self-governance.yaml` configuration
   alone: the existing fact-checker only expresses byte-equality, and a registry-state-to-
   task-status check needs a semantic mapping (`BLOCKED` ≈ `Current`, etc.), which requires new
   code. Writing that code now would be implementation work outside a governance-recovery
   session's mandate, and — applying this recovery's own rules to itself — a new `workflowctl`
   validator is engine functionality requiring its own stage authorization and independent
   review, not something to add unauthorized during a documentation pass. Tracked instead as
   **GOV-2** (`docs/TASK_QUEUE.md`, `Planned`), with the exact gap, why config alone can't close
   it, and a recommended shape for when it is authorized, so the limitation is documented rather
   than left implied.

**Not resolved in this entry:** the WORKFLOW_STATES.md version-policy question (whether adding
the three failure transitions found in the prior pass was a MAJOR change requiring explicit
Human Owner review before the version number reflects it) is a genuine open decision, not
something this entry resolves — see the immediately following note to the Human Owner; no version
number or approval claim has been fabricated for it.

Verified after the edits above: `workflowctl verify` — `task-state`/`governance`/`handover` PASS;
`git` FAILs only on the same pre-existing `upstream_missing`. `pytest` 978 passed;
`pytest --collect-only` 978 collected (unchanged); `mypy`/`ruff check`/`black --check` all pass;
`git diff --check` clean; `git fsck --full` shows two pre-existing dangling commits dated
2026-07-21 (before this entire recovery), unrelated to this session's work. Exactly one `Current`
task (AUTO-002, `BLOCKED`, unchanged). No lifecycle transition changed; no AUTO-002
implementation performed; no commit, push, PR, merge, or branch rename.

**Alternatives considered:** (a) For the Dashboard/AUTO claim, leaving it as a blanket assertion
since most rules genuinely do match — rejected: one real gap existed, and an unverified blanket
claim is exactly the failure mode being corrected throughout this recovery. (b) For the formatter
fix, pinning `ruff-format` and `black` to some specific version pair believed compatible instead
of removing one — rejected: no version pair is guaranteed to stay compatible as either tool
evolves, whereas removing the redundant formatter is a structural fix that cannot regress by
version drift, and it matches what this repository's own documented validation commands already
required. (c) For GOV-2, writing the validator now since the gap is well-understood and the fix
sounds small — rejected: "small" is not the test; authorization and review discipline apply
regardless of estimated size, per this recovery's own repeatedly-stated principle that fixing
governance must not itself bypass governance.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`. Items 1–2 are further mis-citation/staleness
corrections in the pattern of earlier passes; item 3 is a genuine repository/tooling defect now
fixed at its root cause rather than patched; item 4 is a scoping decision, documented so the
absence of coverage is never mistaken for its presence.

## 2026-07-24 — Governance Correction Record: append-only grandfathering exception for two pre-protocol edits, closed and non-repeatable

**Decision:** A sixth independent audit (Codex) correctly found that declaring this log
append-only (fourth-pass entry, "this log's own append-only rule was violated twice...") while
leaving two disclosed-but-unremedied in-place edits sitting in the live document is an
unreconciled contradiction: an absolute "never edited" rule cannot coexist with acknowledged
historical edits that are neither undone nor formally excepted. Two ways to close this were
available: (A) restore the two edited entries to their exact original bytes and layer corrections
on top, or (B) define a precise, closed, non-repeatable grandfathering exception covering exactly
those two edits. **Chosen: (B).** (A) was rejected on reflection: it would require re-inserting
the original incorrect `HUMAN_AUTHORIZATION_MODEL.md` citation text back into the live log as
"restored," which is more likely to mislead a future reader who does not carefully trace the
correction layered after it than a plainly labeled, bounded exception is. `STAGE_REGISTRY.md` §5
kept the (A) treatment already applied to it in the fourth pass — that was a two-row table, cheap
and unambiguous to restore verbatim; the reasoning here is specific to this log's longer prose
entries, not a reversal of that choice.

**The exception, defined completely and precisely:**

- **Scope (exactly these two edits, no others):** (1) the second governance-recovery pass's
  removal of the `HUMAN_AUTHORIZATION_MODEL.md` §2/§4 citation from the "2026-07-24 — AUTO-001
  closed out to Done; AUTO-002 authorized but halted on a branch-binding mismatch" entry
  (replaced in place with an inline editorial-correction bracket, rather than left untouched with
  a separate appended correction); (2) that same pass's wholesale replacement of the first pass's
  "Governance recovery: corrected a mis-cited authority and a non-canonical registry state for
  the AUTO-002 block" entry with the "Governance recovery, completed: ..." entry that follows
  this one, rather than appending the latter alongside the former.
- **Cutoff:** both edits were made before the fourth-pass entry ("this log's own append-only rule
  was violated twice...", immediately below the "completed" entry) first stated this log's
  append-only rule in explicit words. No edit made after that entry is, or can be, covered — the
  fourth and fifth passes made zero in-place edits to any entry, confirmed by re-reading this
  file's full history when preparing this entry.
- **Non-repeatable:** this is a one-time exception for the two edits above, closed as of this
  entry. It sets no precedent and authorizes nothing else; any future incorrect entry is fixed
  exclusively by a new appended Governance Correction Record, with no exception route available.
- **Preserved disclosure:** the fourth-pass entry's full account of what was edited and why
  remains below, unedited, and is incorporated here by reference rather than restated.
- **Human Owner basis:** this session's operator has, across this Governance Recovery
  conversation, directly authored every instruction actually executed (the mission text framing
  each pass, including this one) — the same standing this repository's other authorization
  records treat as the Human Owner's explicit direction. This entry's specific basis is the
  operator's instruction in this turn to resolve Finding 2 "via either (A) ... or (B) ... a
  narrowly scoped, explicit, non-repeatable grandfathering exception ... with defined
  cutoff/entries, preserved disclosure, recorded Human Owner basis" — i.e., the operator named
  option (B) and its required components directly; choosing and fully specifying it here is
  acting on that explicit direction, not inferring authorization from silence.

Verified after this edit: no entry other than this one was modified; `docs/DECISION_LOG.md`'s
full entry count and every other entry's byte content is unchanged from before this edit.

**Alternatives considered:** covered above (choice of (B) over (A)). Also considered: leaving
the contradiction as a documented "known limitation" without resolving it — rejected, since the
mission is explicit that "no absolute 'never edited' rule can coexist with unexplained historical
edits," which requires resolving the contradiction, not further documenting it.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`. This entry converts an absolute,
unreconciled append-only claim into a rule with exactly one bounded, already-disclosed, closed
exception, which is both true to what actually happened and leaves no ambiguity for future
sessions about what may or may not be edited going forward (nothing, ever, again).

## 2026-07-24 — Governance recovery, fifth pass: Rule 16 revised (not the authorizations invalidated), every registry audited repository-wide, runtime failure-transitions synchronized, and Rule 1's artifact list completed

**Decision:** A fifth independent audit (Codex) raised four further findings, investigated and
resolved as follows, all in `docs/workflow-automation/STAGE_REGISTRY.md` (bumped 4.0, another
MAJOR change) unless noted:

1. **Rule 16 ("no successor selected in the same session") contradicted the Decision Log,
   which records both DASH-001→AUTO-001 and AUTO-001→AUTO-002 closing out a predecessor and
   authorizing a successor within one continuous session.** Codex was correct that this happened
   — verified against both 2026-07-23 and 2026-07-24 entries independently of this recovery's own
   framing. Investigated whether to revise the rule or retroactively invalidate both
   authorizations; chose **revision**, not invalidation, because in both cases the trigger was a
   precondition check finding a predecessor still `Current`, the session stopped and reported the
   conflict rather than proceeding silently, and the Human Owner then gave one written directive
   explicitly resolving *both* actions ("close out DASH-001 first, then proceed with AUTO-001";
   the AUTO-002 equivalent) — an explicit, distinct human decision for the successor, not an
   automatic consequence of the closeout. That is exactly the safety property rule 16 protects
   (no *automatic*/agent-initiated chaining); only the literal "same session" wording was
   violated, not the substance. Rule 16 now states this distinction explicitly. Invalidating two
   already-merged, Human-Owner-directed authorizations to satisfy a literal wording gap would have
   been disproportionate and itself a worse governance outcome (unwinding real, deliberate human
   decisions to fix an editorial ambiguity).
2. **Registry audit found DASH's own stage registry was stale and had drifted from AUTO's**
   (`docs/agentos-dashboard/STAGE_REGISTRY.md`): its §3 table still showed DASH-001 `IN_PROGRESS`,
   though it has been `Done`/merged (PR #1, `5f82996`) since 2026-07-23 — this registry was never
   updated at that closeout, a real, previously-undiscovered staleness bug, confirmed against
   `docs/TASK_QUEUE.md`/`docs/PROJECT_STATE.md` (both correctly say `Done`). Fixed: state
   corrected to `COMPLETE`; the same BLOCKED-mapping, clean-tree, rule-8, and same-session
   clarifications made to AUTO's registry were mirrored into DASH's (new rules 18–19, referencing
   AUTO's fuller versions to avoid two independently-editable copies of shared mechanisms
   drifting). `docs/agentos-dashboard/CHANGELOG.md` was also found stale (both entries still say
   "pending Human Owner acceptance at DASH-001 completion" though it completed 2026-07-23); a new
   entry was appended (its own convention: "Entries are appended, never edited") rather than
   editing the stale ones. `docs/implementation/orchestration/migration-registry.yaml` was
   checked and found out of scope: frozen historical evidence from the pre-GOV-1 ORCH-00x program,
   explicitly forbidden to modify by the SSP, not a live registry expected to track current
   `docs/TASK_QUEUE.md` state.
3. **Runtime lifecycle documents disagreed on failure transitions.** Cross-checked
   `MACHINE_GATES.md` against `WORKFLOW_STATES.md` §3's Allowed Transitions table directly (not by
   assertion) and found three real gaps: `MACHINE_GATES.md` §2 documents the Precondition Gate
   failing from `AUTHORIZED` or `PRECONDITIONS_CHECKED` to `FAILED`, and §5/§8 document the Merge
   Safety Gate failing from `PR_OPEN` to `FAILED` — none of these three transitions appeared in
   `WORKFLOW_STATES.md` §3 at all (not merely mis-worded; absent). Added all three
   (`AUTHORIZED → FAILED`, `PRECONDITIONS_CHECKED → FAILED`, `PR_OPEN → FAILED`) to
   `WORKFLOW_STATES.md` §3 (→ 1.2), each citing the `MACHINE_GATES.md` section that requires it.
   Every other gate's failure transition (`VALIDATING`, `QA_RUNNING`, `WAITING_FOR_CHECKS`,
   `CLOSING`) was already present and cross-checked as consistent.
4. **Rule 1's "clean tree" definition (added in the fourth pass) was itself incomplete** — it
   said "`docs/TASK_QUEUE.md` and its mirrors, `docs/DECISION_LOG.md`, and `docs/CHANGELOG.md`"
   without naming this registry's own §4/§5 (which the same transition also modifies — the
   AUTO-001→AUTO-002 entry itself says so: "`STAGE_REGISTRY.md` §4/§5 was updated only with the
   required status reference") or the program-level changelog (which the historical transition
   *should* have updated but didn't — a gap this recovery's third pass already fixed
   retroactively). Rewrote rule 1 with a complete, itemized list of every artifact, and an
   explicit list of what is *not* included (`handover/**`, the predecessor's own completion
   report) and why.

Verified after all edits: `workflowctl verify` — `task-state`/`governance`/`handover` PASS,
`git` FAILs only on the same pre-existing `upstream_missing`. Exactly one `Current` task
(AUTO-002, `BLOCKED`, unchanged). No lifecycle transition changed; no AUTO-002 implementation
performed; no commit, push, PR, or merge.

**Alternatives considered:** (a) For rule 16, invalidating and re-issuing both historical
authorizations — rejected per the reasoning above: the evidence shows deliberate, explicit human
decisions, not silent chaining; invalidating them would discard real approvals to fix wording.
(b) For the DASH registry, leaving it un-mirrored since Finding 2 named it as a target but the
active work is on the AUTO program — rejected: the mission explicitly required auditing every
registry, and the staleness (DASH-001 `IN_PROGRESS`) was a genuine, independent defect, not
housekeeping that could wait. (c) For the runtime transitions, assuming `MACHINE_GATES.md`'s
prose was merely informal and `WORKFLOW_STATES.md`'s table was the sole source of truth needing
no change — rejected: `MACHINE_GATES.md` §8's own Gate Summary Table is exactly as normative as
`WORKFLOW_STATES.md` §3, and an omission in either is a real inconsistency, not a stylistic
choice.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`. Finding 1 in particular required judging
whether a genuine violation should be fixed by changing the rule or by undoing history; the
evidence-based conclusion is that this repository's actual practice (stop, report the conflict,
obtain one explicit directive covering both actions) already satisfied the safety property the
rule exists to protect, so the rule — not the two historical decisions — was corrected.

## 2026-07-24 — Governance recovery, fourth pass: "clean tree" redefined, the BLOCKED/SSP deadlock resolved, and rule 8 rewritten to distinguish frozen records from living documents

**Decision:** A further independent audit (Codex) found three more substantive governance defects
— not citation errors this time, but genuine rule-design flaws — all repaired in
`docs/workflow-automation/STAGE_REGISTRY.md` (bumped 2.1 → 3.0, a MAJOR control-rule change per
its own §8):

1. **Rule 1's "clean tree" was literally impossible to satisfy.** Verified against repository
   evidence: recording "predecessor `COMPLETE`, successor `Current`" in `docs/TASK_QUEUE.md` and
   its mirrors is itself the edit that authorizes a stage — the tree cannot be byte-clean at the
   exact instant of authorization, because that edit is sitting uncommitted at that instant by
   construction. Confirmed independently via `git status` at every point in this recovery: the
   dirty set has only ever contained the sanctioned governance-mirror closeout files (never
   `src/`, `tests/`, or unrelated documents). Codex was correct that the literal wording was
   impossible; incorrect (unevidenced) would be any claim that this invalidates either the
   AUTO-001 or AUTO-002 authorization, since no foreign drift was ever present. Fixed by
   redefining "clean tree" in rule 1: no uncommitted change *other than* the sanctioned
   closeout/enrollment edit itself, which is the trigger, not a violation.
2. **The registry's own `BLOCKED → IN_PROGRESS` transition (added in an earlier pass, rule 17)
   deadlocked against the SSP**, which gates implementation on registry status literally reading
   `AUTHORIZED` — a stage leaving `BLOCKED` straight for `IN_PROGRESS` would never pass that
   textual check. This was introduced by this recovery's own second pass and is a genuine defect,
   not a pre-existing one. Resolved by choosing `BLOCKED → AUTHORIZED → IN_PROGRESS`: unblocking
   always returns a stage to `AUTHORIZED` first (no re-authorization act), so the SSP's existing
   "status is `AUTHORIZED`" check keeps working unmodified. `STAGE_REGISTRY.md` §2/§3 rule 17 and
   the SSP (`stage-prompts/README.md`, → 1.2) now state this identically.
3. **Rule 8 ("never amend a completed stage in place") contradicted this recovery's own actions**,
   which repeatedly edited `docs/workflow-automation/` documents that AUTO-001 (`COMPLETE`)
   delivered. Resolved by distinguishing, in rule 8 itself, two different things it was
   conflating: **completion records** (Registry §4 state/branch facts, §5 rows, stage reports,
   `docs/DECISION_LOG.md` entries) — frozen, corrected only via a Governance Correction Record
   (new rule 18), never in place; versus **versioned reference/control documents** a stage
   happened to deliver (this registry, `HUMAN_AUTHORIZATION_MODEL.md`, `WORKFLOW_STATES.md`, the
   SSP, `stage-prompts/*.md`, `OPEN_QUESTIONS.md`) — each already carries its own `Version` field
   (and, where present, a `Future Revisions` clause) precisely because they are living documents;
   amending their content in place, with a version bump and a logged rationale, is normal
   maintenance and was never a rule-8 violation. Substantive re-litigation of a completed stage's
   actual decisions remains out of bounds for in-place editing either way.

New rule 18 (Governance Correction Record) formalizes the correction mechanism these three fixes
and Finding 4 (next entry) all rely on. Verified after all edits: `workflowctl verify --config
self-governance.yaml` — `task-state`/`governance`/`handover` PASS, `git` still FAILs only on the
same pre-existing `upstream_missing` condition. Exactly one `Current` task (AUTO-002, state
`BLOCKED`, unchanged). No lifecycle transition changed; no AUTO-002 implementation performed.

**Alternatives considered:** (a) For "clean tree," declaring the AUTO-001/AUTO-002 authorizations
retroactively invalid and requiring fresh ones — rejected: the evidence shows no foreign drift was
ever present, only the sanctioned closeout edit; invalidating a correctly-conducted authorization
because a rule's *wording* was ambiguous would penalize correct behavior for an editorial gap. (b)
For the `BLOCKED` deadlock, changing the SSP to also accept status `BLOCKED` directly (skipping
back through `AUTHORIZED`) — rejected: it would require the SSP to carry special-cased logic for
resuming from `BLOCKED`, whereas routing back through `AUTHORIZED` first keeps the SSP's existing
single invariant true unmodified. (c) For rule 8, requiring every documentation clarity fix to go
through a brand-new authorized linked task — rejected as disproportionate for citation/clarity
fixes on living reference documents, and inconsistent with those documents' own explicit
versioning/revision-policy fields, which already anticipate this maintenance mode.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`. These three findings are rule-design flaws,
two of them (BLOCKED deadlock, rule-8 conflict) introduced by this recovery's own earlier passes —
acknowledged as such rather than attributed solely to the original governance.

## 2026-07-24 — Governance Correction Record: this log's own append-only rule was violated twice by the two prior recovery passes, before it was made explicit

**Decision:** An independent audit (Codex) found that this log — despite `docs/AGENT_PROTOCOL.md`
treating it as *the* audit trail for governance changes — had never explicitly stated it was
append-only, and, in that gap, two prior governance-recovery passes today edited existing entries
in place rather than appending: (1) the second pass rewrote parts of the "AUTO-001 closed out to
Done; AUTO-002 authorized but halted on a branch-binding mismatch" entry (removing its
`HUMAN_AUTHORIZATION_MODEL.md` citation) instead of leaving it untouched and appending a
correction; (2) the second pass also replaced the first pass's "Governance recovery: corrected a
mis-cited authority..." entry wholesale with a new "Governance recovery, completed: ..." entry,
rather than leaving the first pass's entry in place and appending. Both are real, confirmed
violations of the append-only principle this log now states explicitly — not a citation error
like the earlier findings, a process error in how this recovery itself was conducted.

This entry does **not** attempt to mechanically reconstruct and replay the exact prior byte
history: the entries that replaced the originals are themselves now real, dated facts about what
happened in this recovery, and unwinding them would mean deleting or rewriting *those*, compounding
the violation rather than fixing it. Full byte-exact reconstruction was performed only where it
was cheap and mechanical and the append-only promise had been explicit from the start — see
`docs/workflow-automation/STAGE_REGISTRY.md` §5, where both original AUTO-002 authorization-log
rows have been restored verbatim and a proper new correction row appended instead. For this log,
the corrective action is: declare append-only status explicitly (done, above), disclose the two
violations precisely (above), and commit that every entry from this one forward — including this
one — is append-only in fact, not just in name. No entry below this one has been altered by this
correction.

**Alternatives considered:** (a) Silently continuing to treat this log as we always effectively
had (no explicit rule, informal append-only-by-convention) — rejected: this is exactly the
ambiguity Codex flagged, and `docs/AGENT_PROTOCOL.md` requires governance rules to be explicit,
not assumed. (b) Attempting a full archaeological restoration of every edited entry, then
re-appending corrections on top — rejected as explained above: for prose entries (unlike
`STAGE_REGISTRY.md` §5's two-row table) this produces a nested, harder-to-read mess without adding
real audit value beyond a clear disclosure, and it would require discarding real facts about what
this recovery actually did in its second pass. (c) Doing nothing since no rule technically
existed to violate at the time — rejected: `docs/AGENT_PROTOCOL.md`'s spirit (governance changes
must be traceable) was violated regardless of whether this file had said "append-only" in so many
words; disclosure and going forward compliance is the correct remedy, per this recovery's
standing instruction to fix governance rather than defend prior decisions.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`'s requirement that governance changes be
logged with their rationale, and because Finding 4 of this recovery's audit specifically named
this log's append-only ambiguity as unresolved. This entry closes that ambiguity going forward and
is honest about the two violations rather than concealing them.

## 2026-07-24 — Governance recovery, third pass: OD-3/OD-4 disambiguated, rule 16 clarified, BLOCKED lifecycle completed, stale mirrors and handover corrected

**Decision:** A further audit backlog (framed as independent-review findings) identified six more
governance gaps beyond the two prior passes, all repaired without changing any lifecycle state or
starting AUTO-002 work:

1. **OD-3/OD-4 blocking ambiguity.** `OPEN_QUESTIONS.md` used "blocks AUTO-002" loosely for two
   different relationships: a hard `STAGE_REGISTRY.md` §3 rule 1 authorization gate, versus a
   question the implementer must resolve before `COMPLETE` (rule 12). Since AUTO-002 was in fact
   authorized while OD-3 and OD-4 were (and remain) `Open`, and `stage-prompts/AUTO-002.md`
   explicitly assigns OD-3 to AUTO-002's own implementation, neither was ever a rule-1 gate. Added
   an explicit definition of the two relationships to `OPEN_QUESTIONS.md`'s Format section and
   reworded both entries' Dispositions accordingly. No new blocking behavior invented — this
   documents what the entries' own history already showed.
2. **Rule 16 (closeout) silence on `workflowctl verify` tolerance.** The rule required
   post-merge `verify` to run but did not say whether a `git`-check finding (e.g.
   `upstream_missing`) could ever be tolerated at closeout, unlike the SSP's mid-stage runs which
   already say to identify pre-existing failures as such. Clarified: `task-state`/`governance`/
   `handover` must PASS with no exception at closeout; `git` must PASS unless its only finding is
   pre-existing and unrelated to the stage's own merge — never for a finding the merge itself
   caused. This does not currently gate anything (AUTO-002 is nowhere near closeout).
3. **`BLOCKED` lifecycle incomplete.** §2/§3 established `BLOCKED` as a state and rule 17
   established how it is entered, but never stated its legal exits. Added: `BLOCKED` is reached
   only from `AUTHORIZED`, and exits only to `IN_PROGRESS` (precondition resolved, resuming rule
   4's "Starting" step, no re-authorization) or `SUPERSEDED` (Human Owner directive, rule 9) —
   never to `NOT_STARTED`/`PROPOSED`. §2's state-model prose, rule 17, and the SSP now all state
   this the same way.
4. **`docs/remaining_tasks.md`** still carried the retired "authorization-binding branch
   mismatch" phrase this recovery's first pass had already corrected everywhere else. Reworded to
   "execution-precondition branch mismatch... registry state `BLOCKED`."
5. **`docs/PROJECT_STATE.md`** contradicted itself: its "In progress" section said AUTO-002 is
   `BLOCKED`, but its "Blockers" section said "None currently" and then described stale Git
   history — "`main` is one commit ahead of `origin/main` and nothing has been pushed," which as
   of the DASH-001/AUTO-001 PR merges is false (`main`/`origin/main` are identical at `191f600`,
   0 ahead/0 behind; verified via `git rev-list --left-right --count origin/main...main`).
   Rewrote "Blockers" to state the real current blocker (AUTO-002 `BLOCKED`) and the real Git
   state (main/origin/main in sync; the only unpushed ref is the session's own working branch).
6. **`handover/PROJECT_HANDOVER.md`** was dated 2026-07-18 and described a since-superseded world
   (no task-tracked work remaining, an uncommitted 1.0.0 working tree, `main` one commit ahead of
   `origin/main`) — checksum-valid against `handover/PROJECT_CHECKSUM.md` but factually stale, per
   that file's own warning that a checksum match only proves byte-identity, not continued truth.
   Rewrote it in full to describe the current state (DASH-001/AUTO-001 `Done` and pushed, AUTO-002
   `Current`/`BLOCKED`, this recovery's corrections, and the real Git history), then regenerated
   `handover/PROJECT_CHECKSUM.md`'s size/digest/date for the new content (`workflowctl
   check-handover` re-verified PASS).

Also synchronized `docs/workflow-automation/CHANGELOG.md`, which still read as though AUTO-001
were in progress and AUTO-002 did not exist; added `Changed` entries mirroring AUTO-001's closeout,
AUTO-002's authorization/`BLOCKED` state, and this pass's document revisions, without deleting the
original (still-true) `Added` entry.

Verified after all edits: `workflowctl verify --config self-governance.yaml` — `task-state`,
`governance`, `handover` all PASS; `git` still FAILs only on the same pre-existing
`upstream_missing` condition (this session's own unpushed working branch), now correctly
described rather than contradicted in `PROJECT_STATE.md`. Exactly one `Current` task (AUTO-002).
No lifecycle transition changed; no AUTO-002 implementation performed; no commit, push, PR, or
merge.

**Alternatives considered:** (a) Leaving OD-3/OD-4's wording as-is since no rule ever literally
said "authorization gate" — rejected: the ambiguity is exactly what a reviewer flagged, and rule
1's "blocking OD-# resolved" language invites the misreading that any "blocks AUTO-002" line is
such a gate. (b) Deleting the stale `docs/workflow-automation/CHANGELOG.md` `Added` entry instead
of adding beside it — rejected: it is a true historical fact (those files were added on
2026-07-23); only its incompleteness, not its content, was the defect. (c) Treating the handover
checksum's PASS as sufficient evidence the file was fine — rejected per the file's own stated
purpose: checksum validity proves byte-identity to a prior snapshot, never continued factual
accuracy.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`'s requirement that governance changes be
logged with their rationale. This entry documents the third and (at time of writing) final
governance-recovery pass; the first two are recorded in the entries directly below.

## 2026-07-24 — Governance recovery, completed: corrected the mis-cited authority, the non-canonical registry state, and made the authorization/execution-precondition boundary explicit

**Decision:** An independent governance audit of the AUTO-001 post-merge state (the closeout
recorded in the entry directly below) found, and this two-pass recovery repaired, three related
defects — none of which changed any lifecycle state or started AUTO-002 work:

1. **Mis-cited authority.** The entry below, and its mirrors in `docs/current_task.md`,
   `docs/TASK_QUEUE.md`, `docs/PROJECT_STATE.md`, `docs/CHANGELOG.md`, and
   `docs/workflow-automation/STAGE_REGISTRY.md` §5, grounded the AUTO-002 branch mismatch in
   `docs/workflow-automation/HUMAN_AUTHORIZATION_MODEL.md` §2 field 8 / §4, treating it as an
   "authorization-binding invalidation." That document's own Dependencies field and
   `docs/workflow-automation/WORKFLOW_STATES.md` §1 state that it governs the **runtime workflow
   engine's** future authorization of workflows against **target repositories** — a system that
   does not exist as code yet (AUTO-001 was documentation-only) — not this repository's own
   AUTO-00x development-stage lifecycle, which is governed instead by `docs/workflow-automation/
   STAGE_REGISTRY.md` §3 and the Standard Stage Protocol (`docs/workflow-automation/
   stage-prompts/README.md`). Under the correct authority (the SSP's named-branch precondition
   and `STAGE_REGISTRY.md` §3 rule 14), the branch mismatch is an ordinary execution-precondition
   failure, not an event that calls the Human Owner's "I authorize AUTO-002." authorization
   itself into question. The practical outcome is unchanged — no AUTO-002 implementation may
   begin on the current branch, and resolution is still a Human Owner decision — only the stated
   reason was wrong. Every mirror, including the `STAGE_REGISTRY.md` §5 log row itself, has been
   corrected in place so no document retains the incorrect claim; the log row's own text now
   discloses that it was corrected and why, rather than leaving a second, contradicting row
   beside it.
2. **Non-canonical registry state.** `STAGE_REGISTRY.md` §4 recorded AUTO-002's state as
   `AUTHORIZED (blocked — branch-binding mismatch, see §5)` — a composite string that is not one
   of the canonical states in §2 (`NOT_STARTED`/`PROPOSED`/`AUTHORIZED`/`IN_PROGRESS`/
   `SELF_REVIEW`/`REVIEW`/`APPROVAL`/`COMPLETE`/`BLOCKED`/`SUPERSEDED`). Corrected to the
   canonical `BLOCKED`.
3. **Implicit rather than explicit governance boundary.** The scope boundary above was
   previously derivable only by cross-reading three documents' Dependencies/Naming-Note fields.
   Made explicit instead: `STAGE_REGISTRY.md` §1 now states in prose that it and the SSP are the
   exclusive authority for the AUTO-00x lifecycle, that `WORKFLOW_STATES.md`/
   `HUMAN_AUTHORIZATION_MODEL.md` govern only the runtime engine, and that authorization
   preconditions and execution preconditions are separate concepts; a new §3 rule 17 states
   plainly that a failed execution precondition moves a stage to `BLOCKED` (never invalidates
   authorization, never by itself requires re-authorization); §2's `Current`/`Planned`/`Done`
   mapping now names `BLOCKED` explicitly (≈ `Current`) instead of leaving it unmapped.
   `HUMAN_AUTHORIZATION_MODEL.md` §1 and `WORKFLOW_STATES.md` §1 each gained one added sentence
   stating the same boundary from their side; the SSP gained one sentence stating the
   `BLOCKED`/no-invalidation consequence at the point it checks the branch precondition;
   `stage-prompts/AUTO-002.md` now separates its "Preconditions" line into an authorization half
   and an execution half instead of one undifferentiated list.

Verified after the edits: `workflowctl check-task-state --config self-governance.yaml` and
`workflowctl check-governance --config self-governance.yaml` both PASS; exactly one `Current`
task (AUTO-002); AUTO-001 remains `Done`/`COMPLETE` everywhere. No lifecycle transition was
changed by this recovery: AUTO-001 is still `Done`/`COMPLETE`, AUTO-002 is still `Current` in
`docs/TASK_QUEUE.md` (registry state `BLOCKED`), and AUTO-002 implementation still has not
started. `workflowctl check-git` continues to `FAIL` on a pre-existing, unrelated condition — the
branch has no upstream configured (`require_upstream: true`). No commit, push, PR, merge, branch
rename, or AUTO-002 runtime change was performed.

**Alternatives considered:** (a) Leaving the mis-citation in place since the practical outcome
(stop and wait for a Human Owner decision) happened to be correct anyway — rejected: a governance
document that cites the wrong authority for a safety-relevant claim misleads the next session
that reads it literally, and `docs/AGENT_PROTOCOL.md` requires governance changes to be logged
with rationale. (b) Preserving `STAGE_REGISTRY.md` §5's original row byte-for-byte and only
appending a separate correcting row (the first pass's approach, out of deference to §8's
"append-only" framing for that log) — superseded in this second pass on the operator's explicit
instruction to leave no conflicting historical guidance anywhere in the live governance surface;
the row's own text still discloses that a correction was made and why, which preserves audit
value without leaving two rows that assert opposite things. (c) Introducing a new state token
(e.g. `AUTHORIZED_BLOCKED`) instead of reusing `BLOCKED` — rejected: only canonical registry
state values are used. (d) Treating the scope boundary as adequately covered by the pre-existing
Dependencies fields and leaving it implicit — rejected on the operator's explicit instruction
that the governance should state it outright rather than require cross-reading three documents.

**Rationale:** Recorded per `docs/AGENT_PROTOCOL.md`'s requirement that governance changes be
logged with their rationale. This entry documents a documentation-correctness repair and a
clarity amendment identified by independent audit, distinct from the substantive AUTO-001/
AUTO-002 governance decision it corrects (recorded directly below, with its own erroneous
citations corrected in place for the same reason).

## 2026-07-24 — AUTO-001 closed out to Done; AUTO-002 authorized but halted on a branch-binding mismatch

**Decision:** Before beginning AUTO-002, the Human Owner authorized the required governance
closeout: AUTO-001 (merged into `main` via PR #3, commit `191f600`) was flipped from `Current`
to `Done` in `docs/TASK_QUEUE.md`, `docs/current_task.md`, `docs/remaining_tasks.md`, and
`docs/PROJECT_STATE.md` (prose only), and AUTO-002 was enrolled as the sole `Current` task,
authorized in the same session ("I authorize AUTO-002."). `workflowctl check-task-state
--config self-governance.yaml` and `workflowctl check-governance --config self-governance.yaml`
were re-run after the edit and both PASS.

With governance state consistent, AUTO-002's own preconditions (`docs/workflow-automation/
STAGE_REGISTRY.md` §3 rule 1; Standard Stage Protocol,
`docs/workflow-automation/stage-prompts/README.md`) were re-checked. Every authorization
precondition passed; one execution precondition did not: the session's actual working branch is
`feature/auto-002-orchestrator-foundation`, but the canonical stage contract
(`docs/workflow-automation/stage-prompts/AUTO-002.md`) and the stage registry
(`docs/workflow-automation/STAGE_REGISTRY.md` §4) both bind AUTO-002 to
`feature/auto-002-orchestrator-state-machine`. The Standard Stage Protocol requires verifying
"you are on the stage's named branch created from a clean baseline" before any implementation
begins (`docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 14). *[Editorial correction, same
day, during final governance cleanup: this paragraph originally also cited "Planned stage branch
name" as authorization-binding field 8 of `docs/workflow-automation/HUMAN_AUTHORIZATION_MODEL.md`
§2 and its §4 as "an explicit invalidation condition" for this mismatch. That citation was
incorrect — `HUMAN_AUTHORIZATION_MODEL.md` governs only the runtime engine's future authorization
of workflows against target repositories (`WORKFLOW_STATES.md` §1), never this repository's own
AUTO-00x stages — and has been removed rather than left as conflicting historical guidance; see
the entry above.]*

Per the SSP and the Human Owner's own explicit instruction ("If any precondition still fails
after the authorized closeout: stop, make no AUTO-002 runtime implementation changes, report the
exact failed precondition"), AUTO-002 implementation was **not started**. AUTO-002 remains the
sole `Current` task (registry state `BLOCKED` per `docs/workflow-automation/STAGE_REGISTRY.md`
§2/§3 rule 17 — authorization intact, execution precondition unmet) pending a Human Owner
decision: rename the working branch to the canonical `feature/auto-002-orchestrator-state-machine`,
or formally amend the canonical branch binding (a new entry in `docs/workflow-automation/
OPEN_QUESTIONS.md` plus a `docs/workflow-automation/STAGE_REGISTRY.md` update) to bind
`feature/auto-002-orchestrator-foundation` instead. `docs/workflow-automation/STAGE_REGISTRY.md`
§4/§5 was updated only with the required status reference (AUTO-001 row → `COMPLETE`; AUTO-002
row → `BLOCKED`; authorization log appended) — no architecture content in that document set was
altered.

**Alternatives considered:** (a) Renaming the local branch to the canonical name and proceeding
— rejected: unilaterally resolving a detected branch-precondition mismatch without a Human Owner
decision bypasses the Human Owner's own stated instruction to stop and report, even though the
fix is mechanically trivial. (b) Editing the canonical contract and registry to match the actual
branch — rejected for the same reason: the canonical branch value is a stage-contract fact, not
documentation drift to be silently corrected. (c) Proceeding with AUTO-002 implementation on the
actual branch, treating the contract's branch field as non-binding — rejected: the stage
contract and the SSP both make this a hard execution precondition, not an advisory note.

**Rationale:** Recorded here because `docs/AGENT_PROTOCOL.md` requires governance changes to be
logged with their rationale, and because this decision documents both an authorized governance
transition and a precondition-check outcome that a future session (or the Human Owner) needs to
understand without replaying this session. No commit, push, PR, merge, or branch deletion was
performed.

## 2026-07-23 — DASH-001 closed out; AgentOS Workflow Automation program (AUTO) enrolled with AUTO-001 current

**Decision:** Before starting AUTO-001, the AUTO-001 stage prompt's own precondition check
("no conflicting task is active") found that DASH-001 was still recorded `Status: Current` in
`docs/TASK_QUEUE.md` and its mirrors, even though its PR (#1, `5f82996`) had already merged into
`main` — the formal flip-to-`Done` closeout step had not yet run. `self-governance.yaml` sets
`workflow.maximum_current_tasks: 1`, enforced by `workflowctl check-task-state`, so starting a
second `Current` task would have broken that invariant. Presented with the conflict, the Human
Owner chose "close out DASH-001 first, then proceed with AUTO-001." DASH-001 was flipped to
`Done` in `docs/TASK_QUEUE.md`, `docs/current_task.md`, `docs/remaining_tasks.md`, and
`docs/PROJECT_STATE.md` (prose only; the `Current Version:` fact line untouched), and the new
**AgentOS Workflow Automation program** (AUTO-001..AUTO-007, entry point
`docs/workflow-automation/README.md`) was enrolled in the same edit: AUTO-001 as the sole
`Current` task and AUTO-002..AUTO-007 as `Planned`, mirroring exactly how the DASH program was
enrolled at DASH-001. `workflowctl check-task-state --config self-governance.yaml` re-run after
the edit to confirm exactly 1 `Current` task.

**Alternatives considered:** (a) Leaving DASH-001 marked `Current` and treating AUTO-001 as
exempt from `docs/TASK_QUEUE.md` tracking, since AUTO-001's own file scope
(`docs/workflow-automation/`) never overlaps DASH-001's — rejected: this repository's
`maximum_current_tasks: 1` rule is a whole-repository invariant, not a per-program one (DASH-001's
own stage prompt encoded the same precondition: "no other `Current` task anywhere in
`docs/TASK_QUEUE.md`"), and a program-private state file (the option taken for the read-only
`docs/implementation/orchestration/` ORCH package) was rejected for DASH-001 on the grounds that
"DASH stages are ordinary tasks and belong under the existing `check-task-state` discipline" —
the same reasoning applies to AUTO. (b) Stopping entirely and asking the Human Owner to close out
DASH-001 in a separate session first — rejected as the Human Owner's explicit choice, given they
authorized the closeout in the same turn as being asked. (c) Leaving AUTO-002..AUTO-007
unenrolled (only adding AUTO-001) since the AUTO-001 authorization text did not explicitly
request `TASK_QUEUE.md` changes — rejected for internal consistency: the DASH precedent enrolls a
program's full known roadmap as `Planned` at its first authorized stage, and AUTO-001's own
required deliverables already define all seven stages' scope in
`docs/workflow-automation/stage-prompts/`.

**Rationale:** Recorded here because `docs/AGENT_PROTOCOL.md` requires governance changes to be
logged with their rationale, and because promotion of AUTO-001 to `Current` needs the recorded
owner approval (`self-governance.yaml` `require_designer_approval_for_promotion`). The Human
Owner's 2026-07-23 authorization ("I authorize AUTO-001.") plus the explicit "close out DASH-001
first" choice made when presented with the conflict are that approval for both actions. This
entry, and the `docs/TASK_QUEUE.md`/mirror edits it describes, are governance/task-state changes
required by repository governance to satisfy AUTO-001's own preconditions — not part of
AUTO-001's documentation deliverable set, which remains scoped to `docs/workflow-automation/`.
No commit, push, PR, merge, or branch deletion was performed for either the closeout or the
AUTO-001 work.

## 2026-07-23 — AgentOS Dashboard program enrolled; DASH-001 recovered from a mis-targeted execution

**Decision:** Adopt the ten-stage AgentOS Dashboard program (DASH-001..DASH-010) as post-1.0
work, enrolled in `docs/TASK_QUEUE.md` with DASH-001 as the sole `Current` task, and complete
DASH-001 by **recovery**: the first execution was mistakenly performed in a different
repository (`amozesh_konkur`), and its documentation output — copied here as untracked
candidate material — was rewritten in place so every assumption matches this repository's
actual governance (authority chain per `docs/AGENT_PROTOCOL.md` + `self-governance.yaml`;
Current/Planned/Done task lifecycle with `workflowctl` mirror checks; branches from `main`;
handover pair verified by `workflowctl check-handover`; upstream check instead of a baseline
tag; this single decision log; the orchestration package treated as read-only observed state).
The program is documentation-first, and the dashboard itself will be a separate top-level
package (`agentos_dashboard/`) with read-only repository access — it never gains commit, push,
or governance-mutation authority.

**Alternatives considered:** (a) Discarding the copied material and re-planning from scratch —
rejected as wasteful: the product/security/test design is repository-agnostic and sound; only
its governance bindings were wrong. (b) Keeping the copied files verbatim and reconciling later
— rejected: they cited nonexistent files (`CONSTITUTION.md`, `governance/`, root `AGENTS.md`,
`scripts/create_handover.py`), a nonexistent base branch (`recovery/project-baseline`), a
nonexistent baseline tag, foreign decision IDs (CTO-xxx/D-xxx/ISS-xxx), and a false "zero new
dependencies (FastAPI)" claim, so leaving them in place would have created a second, false
authority. (c) Enrolling the DASH stages outside `docs/TASK_QUEUE.md` in a program-private
state file, like the ORCH package — rejected: unlike ORCH (a reviewed design package with its
own session protocol), DASH stages are ordinary tasks and belong under the existing
`check-task-state` discipline.

**Rationale:** Recorded here because `docs/AGENT_PROTOCOL.md` requires governance changes to be
logged with their rationale, and because promotion of DASH-001 to `Current` needs the recorded
owner approval (`self-governance.yaml` `require_designer_approval_for_promotion`). The Human
Owner's 2026-07-23 recovery directive ("I authorize recovery and correct execution of DASH-001
in the ai-workflow-engine repository") is that approval. The known dependency gap (this
repository pins no web framework) is deliberately not decided here; it is held open as OD-D9 in
`docs/agentos-dashboard/OPEN_QUESTIONS.md` and blocks DASH-004, not DASH-001..003. Full
correction inventory: `docs/agentos-dashboard/DECISIONS.md` DD-03 and
`docs/reports/agentos-dashboard/DASH-001-recovery-report.md`.

## 2026-07-18 — `state` CLI emits a deterministic bespoke payload, not a timestamped CheckResult (T-302)

**Decision:** `workflowctl state show|next|record` success output is a purpose-built canonical-JSON
object (`{status, command, ...}`) written Rich-free to stdout, rather than a `CheckResult` routed
through `render_json`. Failures carry `{status: "FAIL", command, finding: {code, message}}` and
exit 1; success exits 0; usage/unexpected errors exit 2 via `_protected`.

**Alternatives considered:** Emitting a `CheckResult(check_name="state", ...)` exactly as
`docs/milestone-3-plan.md` loosely worded it ("CheckResult-style PASS"). Rejected because
`CheckResult` carries a wall-clock `timestamp`, which would make identical state queries produce
different bytes — at odds with this project's determinism principle and with the timestamp-free
canonical outputs used everywhere else in the workflow layer. `show`/`next` are also queries, not
pass/fail checks, so the `CheckResult` shape fits them poorly.

**Rationale:** The Milestone 2 prompt CLI set the precedent of a bespoke success payload
(`PromptSuccess`) with `CheckResult` reserved for validation *failures*; the state CLI follows the
same pattern. Recorded here because it is a conscious, reviewer-flagged (T-302 review, finding N1)
deviation from the plan's literal wording, kept for a determinism reason rather than an oversight.
`docs/current_task.md`'s T-302 acceptance criteria describe the CLI contract without `check_name`,
consistent with this decision.

## 2026-07-18 — Milestone 4 writer is typed-methods-only; push gate reads live, not recorded (T-401)

**Decision:** In the `docs/milestone-4-plan.md` contracts, (a) the writable-Git surface
`GitWriter` exposes only typed methods (`stage_paths`, `unstage_paths`, `commit`, `push`,
`apply_check`, `apply_patch`), each emitting one fixed argv template — there is no method that
runs a caller-supplied argv, so dangerous forms (force push, remote-branch deletion, `reset`,
`commit --amend`/`-a`, `add -A`) are structurally unreachable rather than blocked by a denylist;
and (b) the push gate reads live Git state and decides on `behind == 0` computed by the exact
Milestone 2 `rev-list --left-right --count @{upstream}...HEAD` command, without carrying
recorded ahead/behind counts in the `PushApproval`.

**Alternatives considered (all from round-1 plan-review findings):** an allowlist that runs
arbitrary argv and scans it for denylisted tokens (rejected — B2/B3: it both false-rejects
operand data like a commit message containing "reset" and misses real dangers like
`push --delete`); carrying recorded ahead/behind in the approval to mirror M-2's cross-check
(rejected — B5: M-2 needed that only because its prompt was a snapshot that could drift from
execution; the M-4 gate reads live state, so the live computation is itself authoritative).

**Rationale:** An independent round-1 plan review REJECTED the first draft with five blocking
findings; the typed-writer redesign resolves three of them (B1 self-contradictory unstage,
B2 operand-scanning, B3 non-airtight allowlist) at once and is a stronger safety posture for the
project's first writable-Git milestone. The live-read push gate (B5) and the read-only `GitClient`
extension using already-allowlisted forms (B4) are the other two. Recorded here because these are
genuine safety-architecture choices, not typo fixes. Full history in `docs/milestone-4-plan.md`'s
status and disposition sections.

## 2026-07-18 — `AgentRunRecord` stores the agent's stdout bytes, not a re-parsed `AgentReport` (T-305)

**Decision:** The stored `AgentRunRecord` does not carry a structured `AgentReport` field. The
agent's report is preserved byte-exactly as `stdout_b64` under a committed `stdout_sha256`, and
its material claims (verdict, changed-path judgement) live in the `verification` snapshot's
`evidence`. The `docs/milestone-3-plan.md` "Run artifacts" wording listed "the full AgentReport"
as a member.

**Alternatives considered:** Adding a parsed `AgentReport` field alongside the raw stdout
(rejected — it duplicates data already recoverable from `stdout_b64`, and a separately-stored
parse could drift from the bytes that were actually digested, weakening tamper-evidence);
storing only the report and discarding raw stdout (rejected — then non-report stdout noise and
the exact bytes an operator saw would be lost, and a malformed-report run would have nothing to
store).

**Rationale:** Storing the exact bytes under a digest is strictly more tamper-evident than a
re-parsed copy, and it also covers the failure cases where there is no valid report at all
(`agent_report_invalid`, timeout). Downstream Milestone 4 consumes the verified verdict and
patch, both already present. Recorded per the T-305 review's non-blocking finding N3 so a future
session sees this as a conscious choice, not an omission.

## 2026-07-18 — Machine-readable CLI output must bypass Rich entirely (T-104)

**Decision:** All of `workflowctl`'s machine-readable stdout — every `--output json` payload and
the `version` string — is written as plain bytes via a `_write_stdout` helper, never through
Rich's `Console`.

**Alternatives considered:** Configuring the Rich `Console` with `no_color=True` /
`force_terminal=False` (rejected — `FORCE_COLOR` overrides those, and Rich still owns
soft-wrapping and other transforms); leaving it and documenting "unset FORCE_COLOR" (rejected —
a governance tool whose JSON is meant for CI consumption must not emit invalid JSON under a
common env var).

**Rationale:** Discovered during T-301's round-2 plan review: with `FORCE_COLOR` set, Rich
injected ANSI codes into `verify --output json`, producing unparseable JSON and violating the
stable 1.0 schema contract in `docs/architecture.md`. This is the same Rich-corruption class the
2026-07-17 `_protected` decision fixed for stderr; T-104 extends the same bytes-not-Rich
principle to the stdout machine paths that were missed. Human output and the Rich summary tables
are unchanged. Also hardens the `conda run ... pytest` verification path Milestone 3 re-executes.

## 2026-07-17 — Milestone 3 plan: two boundary decisions surfaced by round-1 plan review

**Decision:** In the `docs/milestone-3-plan.md` contracts, (a) Milestone 3 makes **no** change
to the target repository at all — a scoped-write agent's output is captured as a verified patch
artifact and applying it to the working tree is deferred to Milestone 4 (the earlier `agent
apply` verb was cut); and (b) `agent run` requires a **clean** target working tree at the
recorded HEAD before running, so the committed-HEAD sandbox faithfully reproduces the prompt's
working-tree-derived evidence.

**Alternatives considered:** Keeping `agent apply` in M-3 (rejected — it sat adjacent to
Milestone 4's controlled-change scope and added a third, un-allowlisted writable-Git surface on
the real repository); building the sandbox from the dirty working tree instead of committed HEAD
(rejected — it would make run inputs non-deterministic and diverge from the governance principle
that committed state is the source of truth).

**Rationale:** An independent round-1 plan review (fresh session, no memory of the drafting)
returned REJECTED with three blocking findings (missing `renderer.py` in the file list;
unspecified/non-deterministic verification-command re-execution; a task-ID slug collision hole)
and two substantive ones (sandbox-vs-dirty-tree tension; an unverifiable lossy-stderr digest).
All were remediated in a round-2 revision; the two items above were genuine scope/architecture
choices worth recording, not mere typo fixes. This is the same independent-review discipline
that caught a real regression in Milestone 2 (see the 2026-07-16 entry).

## 2026-07-17 — Master roadmap to 1.0 approved; local-commit and CI decisions

**Decision:** The human approved `docs/MASTER_ROADMAP.md` as written: Stage 0 (GOV-1 closeout,
documentation sync, plus a lightweight CI task the human opted into), then Milestone 3, then
Milestone 4, then the 1.0.0 release. The human additionally approved creating **one local git
commit** before Milestone 3 begins, to preserve the validated M-2 + GOV-1 working tree —
explicitly no push and no remote branch. Versioning follows Semantic Versioning; intermediate
versions are recommended by the engine's maintainer session at each milestone closeout
(suggested 0.2.0 after M-3, 0.3.0 after M-4).

**Alternatives considered:** Leaving the working tree uncommitted until 1.0 (rejected — largest
recoverability risk in the gap analysis); skipping CI (rejected by the human — a minimal
workflow improves reliability at negligible complexity).

**Rationale:** Recorded here because commit approval and roadmap approval are exactly the class
of human decisions `docs/AGENT_PROTOCOL.md` says must not be inferred from prior context by a
future session.

## 2026-07-17 — Self-governance: extend the existing engine rather than build a parallel system

**Decision:** Point this project's own tooling at its own repository (new governance documents
+ `self-governance.yaml` config), rather than building a second, differently-shaped governance
system under `docs/governance/` with new file names, a new task-lifecycle model, and new CLI
verbs.

**Alternatives considered:** A from-scratch system with an 8-file `docs/governance/` tree, a
7-state task lifecycle (`BACKLOG → PLANNED → APPROVED → IMPLEMENTING → VALIDATING → COMPLETED →
HANDED_OVER`) with timestamped/evidenced transitions, and new `governance status/validate/
handover/closeout` CLI commands running alongside the existing `check-*`/`verify`/`prompt`
surface.

**Rationale:** The existing `EngineConfig` schema, `governance`/`handover` validators, and
`prompt` module already cover nearly everything a from-scratch system would provide, under
different names, and had already been through two full milestone review cycles. Building a
parallel system would create two incompatible vocabularies describing the same repository
(`Current/Done/Planned` vs. a 7-state machine; `check-governance` vs. `governance validate`).
The genuinely new task-lifecycle/multi-agent-execution/push-gate capabilities the alternative
implied were already scoped as Milestones 3 and 4 in `docs/milestones.md` — pulling them forward
under new names would fork the roadmap rather than extend it. Full reasoning:
[`docs/GOVERNANCE_AUDIT.md`](GOVERNANCE_AUDIT.md).

## 2026-07-17 — `_protected` CLI error output bypasses Rich's `Console` entirely

**Decision:** `_protected()` in `src/ai_workflow_engine/cli.py` writes `ERROR: <message>\n`
directly to `sys.stderr` rather than through Rich's `Console.print`.

**Alternatives considered:** `Console.print(..., markup=False)` (insufficient — Rich's automatic
repr-highlighter still bolds bracketed substrings with ANSI codes even with markup parsing off);
`Console.print(..., markup=False, highlight=False)` (insufficient — Rich still soft-wraps text
to the console's line width, splicing a spurious newline into any message near or past ~80
columns, even when not attached to a TTY).

**Rationale:** Milestone 2's plan requires `_protected`'s stderr output to be the exact bytes
`ERROR: <message>` in every mode. Two independent fresh implementation-reviews each found one of
the above defects in turn; bypassing Rich's console formatting layer entirely was the only fix
that satisfied the byte-exact contract for arbitrary message content (brackets, tabs, length).
This also silently fixed the same latent defect for every pre-existing Milestone 1 command that
shares `_protected`.

## 2026-07-16 — Three-round independent fresh-review discipline for Milestone 2

**Decision:** After every remediation pass, dispatch a new reviewer with *no memory of the prior
session's fixes* rather than self-certifying that a fix resolved a prior review's findings.

**Rationale:** A reviewer that already knows "these four things were fixed" is anchored on that
frame and is structurally prone to missing anything new. Milestone 2 went through three such
rounds; round 2 caught a real regression-adjacent bug (the wrapping defect above) that round 1's
own fix had introduced by not going far enough. Self-certification would have missed it.

## Milestone 2 plan — Prompt generation is read-only and stateless

**Decision:** `ai_workflow_engine.prompt` renders, validates, and optionally stores a prompt for
an operator-specified stage. It does not persist workflow state, record verdicts, enforce stage
transitions, or compute the next stage automatically.

**Alternatives considered:** Coupling prompt rendering to a live workflow state machine tracking
which stage a task is "in."

**Rationale:** No state machine had been designed yet at the time Milestone 2 was scoped.
Building one implicitly, as a side effect of prompt generation, would have made Milestone 2's
correctness depend on an undesigned, untested state model. Deferred explicitly to Milestone 3;
see `docs/milestone-2-plan.md`.

## Milestone 2 plan — Prompt identity is a pinned, canonical, byte-exact hash

**Decision:** Every rendered prompt's identity (`prompt_id`) is the first 16 hex characters of
the SHA-256 of a canonical JSON serialization of its complete context (config, git status, task
snapshot, check evidence, template content/version/digest — everything). Canonical JSON uses
NFC-normalized, sorted-key, no-float, signed-64-bit-int-only serialization with a golden test
vector. All seven built-in templates are pinned to fixed byte counts and SHA-256 digests.

**Rationale:** Free-form or non-deterministic prompt generation would make two renders of "the
same" prompt potentially differ, breaking the atomic no-clobber storage protocol's core
assumption (two writers at the same address must be writing the same bytes) and making stored
prompts unverifiable without the exact code version that produced them. Byte-exact canonical
identity makes verification independent of the installed template registry.

## Milestone 1 — Governance/task-state parsing is conservative, with one authoritative source

**Decision:** Task states come only from explicit Markdown headings (`## TASK-ID` + a `Status:`
field) or table rows containing a task-ID-shaped token and a status word — no fuzzy inference.
Exactly one configured document (`governance.task_queue`) is authoritative; every other
configured document is a mirror that must agree with it, checked by `check_task_state` and
`check_governance`.

**Rationale:** A governance tool whose job is to catch documentation drift must not itself
introduce ambiguity about what a document says. Treating one document as authoritative and
everything else as a verified mirror turns "these two docs quietly disagree" into a detectable
`FAIL` instead of a silent inconsistency an agent (or a human) could act on incorrectly.

## 2026-08-04 — GOV-AUTO-08 — AUTO-015 successor decision remains with the Human Owner

**Decision:** Register GOV-AUTO-08 as the sole `Current` task for documentation-only comparison
and contract definition of possible successors after AUTO-014. Do not select, register, authorize,
or implement AUTO-015.

**Rationale:** AUTO-014 is `COMPLETE`, but its closeout does not select a successor. The repository
evidence does not establish one coherent AUTO-015 implementation stage. The Human Owner must
choose exactly one candidate, or explicitly choose “No AUTO-015 at this time,” using the governed
decision template. Any later implementation requires a fresh stage contract, preflight, and
explicit authorization.

**Boundary:** GOV-AUTO-08 changes governance documents only. No production source, tests, scripts,
providers, workflow states, CLI commands, or runtime behavior are changed or authorized. No
commit, push, PR, or merge occurs. GOV-AUTO-08 remains Current until the Human Owner decision gate
is completed. AUTO-015 remains undefined, unregistered, unauthorized, and untouched.

## 2026-08-04 — GOV-AUTO-08 closure — Human Owner selected the AUTO-015 capability

**Decision:** The Human Owner selected **Automatic Next-Stage Computation and Prompt Generation**
as the proposed basis for **AUTO-015 — Deterministic Next-Stage Proposal and Governed Prompt
Generation**. The authorization statement is **Not authorized**.

**Rationale:** This capability directly supports governed continuation after AUTO-014 while
preserving the mandatory Human Owner gate. Preparation Mode, Reviewer Mode, Codex Correction Mode,
daemon/scheduler, operator interface, multi-task orchestration, security hardening, provider
expansion, and deferred-defect remediation remain separate future work.

**Closure and boundary:** GOV-AUTO-08 moves `Current → Done` and its registry continuity state
moves `IN_PROGRESS → COMPLETE`. Capability selection does not register or authorize AUTO-015,
create a contract or branch, or permit implementation, commit, push, PR, or merge. The Current task
set is empty. AUTO-015 remains unregistered, unauthorized, and unimplemented pending a separate
contract-definition and explicit authorization step.

## 2026-08-04 — Human Owner accepted DEC-001 through DEC-011 for the proposed AUTO-015 contract

**Decision:** The Human Owner accepted eleven contract-semantics decisions, DEC-001 through
DEC-011, for the proposed (not authorized) `docs/workflow-automation/stage-prompts/AUTO-015.md`
stage contract, Revision 3, following that contract's remediation against an independent audit and
this repository's own final independent contract review
(`docs/reports/workflow-automation/AUTO-015-contract-review.md`). The eleven decisions are:

- **DEC-001 — Architecture:** Option A, Core Engine Planning Service under
  `src/ai_workflow_engine/successor_planning/`; no AgentOS `WorkflowService` adapter.
- **DEC-002 — Artifact root:** external repository-scoped root
  `~/.ai-workflow-engine/successor-proposals/<repository-id>/`, never part of Git.
- **DEC-003 — Candidate source:** static authoritative catalog only; no arbitrary-prose or
  bounded-derived candidates in the AUTO-015 MVP.
- **DEC-004 — One eligible candidate:** always issue an advisory recommendation; never selection,
  registration, authorization, implementation permission, or owner approval.
- **DEC-005 — Multiple eligible candidates:** list all eligible candidates and recommend none; the
  Human Owner alone selects one.
- **DEC-006 — Entry surface:** a new read-only `workflowctl successor-planning` command backed by
  the Core Engine Planning Service.
- **DEC-007 — Publication:** the lock-free, immutable, content-addressed, atomic, no-clobber
  protocol in AUTO-015.md §§17-18.
- **DEC-008 — Rendering:** AUTO-015.md §14's safe structured rendering; repository-derived content
  remains untrusted data and never becomes directive text.
- **DEC-009 — Identity and baseline:** AUTO-015.md §7's repository identity, Git baseline, evidence
  snapshot, drift detection, and fail-closed protocol.
- **DEC-010 — Repository ID:**
  `<normalized-repository-name>--<first-12-hex-characters-of-SHA256(canonical-primary-remote-identity)>`,
  excluding credentials/query/fragments, normalizing SSH/HTTPS equivalence and host casing and an
  optional `.git` suffix, retaining owner and repository name, and excluding local filesystem paths.
- **DEC-011 — CLI:**
  `workflowctl successor-planning propose --config <CONFIG_PATH> --predecessor <STAGE_ID>`, with
  optional `--output console|json` (default `console`) and `--dry-run`; no mutation, authorization,
  registration, provider, Git, task, workflow, commit, push, PR, or merge option exists.

**Rationale:** The final independent contract review found that DEC-001 through DEC-011 were
recorded only inside the contract document and its own review report, with no corroborating entry
in this append-only decision record — the same authoritative source AUTO-015's own evidence model
(§8 item 4) treats as governing for decision rationale and Human Owner directives. This entry closes
that gap so the acceptance of these eleven decisions is independently verifiable the same way every
other Human Owner decision in this repository is, rather than resting solely on the proposed
contract's own self-description.

**Boundary:** This entry finalizes AUTO-015 **contract semantics only**. It does not register a
`STAGE_REGISTRY.md` row, does not create a branch, does not grant implementation permission, and
does not constitute the separate, explicit "I authorize AUTO-015" act `STAGE_REGISTRY.md` §3 rule 3
requires. AUTO-015 remains unregistered, unauthorized, and unimplemented. No production source,
test, script, configuration schema, commit, push, PR, or merge is authorized or occurred as part of
this entry. A fresh authorization preflight and a separate, explicit Human Owner authorization
statement remain mandatory before any implementation may begin.

## 2026-08-04 — Human Owner registered and authorized AUTO-015

**Decision:** The Human Owner authorized AUTO-015 — Deterministic Next-Stage Proposal and Governed
Prompt Generation — for registration, in one written directive: "Authorization received. AUTO-015
implementation is authorized only within the finalized contract and its stated boundaries." AUTO-015
had never been registered before, so this entry records both its registration and its
authorization, exactly as AUTO-009 through AUTO-014's registrations did.

**Scope of the authorization**, stated exactly by the directive and verified against the finalized
Revision 4 contract (`docs/workflow-automation/stage-prompts/AUTO-015.md`) and its independent
final review (`docs/reports/workflow-automation/AUTO-015-contract-review.md` §12, verdict
"CONTRACT READY FOR AUTHORIZATION PREFLIGHT"): the exact architecture (DEC-001 — Option A, the
Core Engine Planning Service under `src/ai_workflow_engine/successor_planning/`, exposing
`workflowctl successor-planning propose --config <CONFIG_PATH> --predecessor <STAGE_ID>` with no
`agentos_workflow.WorkflowService` adapter); DEC-001 through DEC-011 in full, each already
independently recorded in this log's immediately preceding 2026-08-04 entry; the exact
implementation allowlist (contract §23) and the exact forbidden surface (§24); the static
authoritative candidate catalog only
(`docs/workflow-automation/successor-planning/AUTO-015-AUTHORITATIVE-CATALOG.yaml`, DEC-003); the
security invariants (§22); the deterministic outcome and failure model (§12/§13); the verification
plan (§25); the live-acceptance plan (§27); the defect policy (§28); and the implementation stop
condition (§30). No work outside the finalized contract is authorized.

**Preconditions verified before this registration** (`STAGE_REGISTRY.md` §3 rule 1): predecessor
AUTO-014 `COMPLETE`, merged, and published; AUTO-001 through AUTO-014 and GOV-4 all
`COMPLETE`/`Done`; GOV-AUTO-08 `Done`; registry and `docs/TASK_QUEUE.md` in agreement; no other
`Current` task anywhere in the queue (the `Current` set was empty); clean, synchronized `main` ==
`origin/main` at `fcb93730bf211ee020027dcb67733a5e8b00e8ea`; no AUTO-015 branch, `STAGE_REGISTRY.md`
row, source symbol, or task entry existed before this session; `workflowctl verify --config
self-governance.yaml` full PASS (`git`, `task-state`, `governance`, `registries`, `handover` all
PASS); no blocking `OPEN_QUESTIONS.md` `## Open` entry (OD-6, OD-7, OD-10, OD-11, OD-12 each
explicitly "blocks nothing's authorization"). Registry state moves `NOT_STARTED → AUTHORIZED`
(`docs/workflow-automation/STAGE_REGISTRY.md` §4/§5); task status moves to `Current`
(`docs/TASK_QUEUE.md`).

**Registration only — initial start did not occur.** `STAGE_REGISTRY.md` §3 rule 14 requires the
stage's one branch to be created from a `main` baseline that already carries the authorization
record being registered here, and rule 4's `AUTHORIZED → IN_PROGRESS` "Starting" transition
presupposes that branch exists. This session holds no commit authorization, so the governance
edits recording this registration (this entry, `docs/TASK_QUEUE.md`, `docs/current_task.md`,
`docs/remaining_tasks.md`, `docs/PROJECT_STATE.md`, and `docs/workflow-automation/STAGE_REGISTRY.md`
§4/§5) are left **uncommitted** in the working tree, the registered branch
`feature/auto-015-successor-planning` was **not created**, and registry state stops at
`AUTHORIZED`. A separate Human Owner-directed documentation commit and publication of this
registration is required before the branch may be created and initial start (rule 4) may proceed.

**Boundaries:** This decision authorizes only AUTO-015's registration and its future
implementation and validation work as scoped by the finalized contract. It does not authorize a
commit, a push, a PR, a merge, branch creation, any target-repository mutation, any runtime
workflow-state mutation, any Claude/Codex/model-provider invocation, or any successor stage.
Authorizing AUTO-015 authorizes no successor.

## 2026-08-05 — Human Owner approved and closed AUTO-015

**Decision:** The Human Owner reviewed the AUTO-015 implementation and approved its governance
closure. AUTO-015 — Deterministic Next-Stage Proposal and Governed Prompt Generation — was
implemented on branch `feature/auto-015-successor-planning`, committed as `05b819e`, and published
via pull request **#17**, merged as **`e325f95`** (parents `c9cda88` + `05b819e`). The completion
report (`docs/reports/workflow-automation/AUTO-015-completion-report.md`) records repository-native
verification evidence — a git before/after comparison showing the working tree and all fourteen
authoritative governance documents byte- and mtime-identical across a publishing run and a dry run,
process/environment evidence that no `claude` or `codex` subprocess was ever spawned, a
package-wide AST structural sweep, and a live invocation against this repository — plus a
correction round in which an independent review raised three High findings (AUTO015-REV-001,
secret-bearing catalog fields reaching the persisted artifact; AUTO015-REV-002, the §4 item 6
unauthorized-successor preflight never performed; AUTO015-REV-003), each reproduced first and then
closed with the smallest change satisfying the contract.

**Evidence — Human Owner–confirmed external runner record.** The following is confirmed directly
by the Human Owner from the local AUTO-015 runner session; it was produced and observed outside
this repository and is **not** claimed to exist as a repository-stored artifact or transcript:
runner run ID `auto015-20260804T060616Z-dedd54c6`; one full Codex review, completed exactly once,
initial verdict `BLOCKED` on findings AUTO015-REV-001, AUTO015-REV-002, and AUTO015-REV-003; one
correction round, completed; one closure verification, completed exactly once and limited to those
same three finding IDs, with all three found `CLOSED`; final runner state
`READY_FOR_COMMIT_APPROVAL`; full verification 11/11 PASS. The repository-native artifacts backing
this closure are the completion report, the implementation diff on `05b819e`, the CI results on
PR #17, PR #17 itself, and merge commit `e325f95` — no other repository artifact path is claimed
for the Codex review or the closure verification.

None of the six deferred, non-blocking items (D-14 through D-16, inherited unimplemented from
AUTO-013's scope; OD-6, OD-7, OD-10, OD-11, OD-12) is a Critical or High blocker — each is
dispositioned "not a blocker" in the completion report for AUTO-015's read-only, non-runtime scope,
and none was fixed by this closure. Registry state moves `IN_PROGRESS → COMPLETE`
(`docs/workflow-automation/STAGE_REGISTRY.md` §4/§5); task status moves `Current → Done`
(`docs/TASK_QUEUE.md`, `docs/current_task.md`, `docs/remaining_tasks.md`). The Current task set is
now empty.

**Boundaries:** This decision approves and closes only AUTO-015's governance record. It does not
register, authorize, or implement AUTO-016 or any later roadmap phase — AUTO-016 remains
unregistered, unauthorized, and `Planned`, and requires its own separate, fresh, written Human
Owner authorization. It does not authorize any further commit, push, PR, or merge beyond PR #17
and merge commit `e325f95`, both of which had already occurred before this closure entry was
written.

## 2026-08-05 — GOV-AUTO-10 registered — AUTO-016 capability selected, implementation withheld

**Decision:** The Human Owner selected **AUTO-016 — Integrated Milestone Automation Runner** as the
AUTO-015 successor capability and registered GOV-AUTO-10 — AUTO-016 Integrated Runner Contract
Definition — as the sole `Current`, documentation-only governance task, bounded to producing a
finalized, implementation-ready stage contract and one bounded independent review of it.

**Rationale:** The local AUTO-015 runner drove an entire authorized stage to a reviewed,
ready-to-commit state under real conditions (run `auto015-20260804T060616Z-dedd54c6`), including one
provider failure, one result-format reconciliation, one milestone reopening, one review recovery,
and one post-correction revalidation. That is proven behavior currently living in unsupported,
untested, single-file operator tooling outside the repository. Converting it into a packaged,
tested, `mypy --strict`-clean capability of the engine is the natural successor, and the selection
records the capability only.

**Boundary:** This registration authorizes no AUTO-016 implementation. It permits no creation of
`src/ai_workflow_engine/milestone_runner/`, no CLI command, no test, no provider adapter, no run
state, and no configuration schema. It permits no modification of production source, tests,
scripts, package files, dependencies, workflow runtime, providers, or the local prototype runner. It
creates no `STAGE_REGISTRY.md` §4 row and no AUTO-016 task entry, and authorizes no branch, commit,
push, PR, or merge.

## 2026-08-05 — GOV-AUTO-10 closure — AUTO-016 contract finalized and independently reviewed

**Decision:** GOV-AUTO-10 is closed `Current -> Done`. The finalized contract
(`docs/workflow-automation/stage-prompts/AUTO-016.md`, Revision 2) and its independent review
(`docs/reports/workflow-automation/AUTO-016-contract-review.md`, verdict "CONTRACT READY FOR HUMAN
OWNER AUTHORIZATION") are complete. The following contract decisions are recorded as pre-resolved by
direct repository evidence, requiring Human Owner confirmation at authorization rather than a fresh
choice:

- **DEC-016-001 — Architecture.** A Core Engine Milestone Runner under
  `src/ai_workflow_engine/milestone_runner/`, with no `agentos_workflow.WorkflowService`
  integration. Four independent lines of evidence prove that route is not mandatory:
  `ARCHITECTURE.md` §4's package-boundary rule; the single existing `src -> agentos_workflow` edge
  (`cli.py:1268`, importing only `auto_app`); `WorkflowService`'s requirement of a
  target-repository `WorkflowConfig` that this repository does not have; and AUTO-015's accepted
  precedent of declining the same route.
- **DEC-016-003 — Process lock.** A runner-owned `fcntl.flock` lock, because no `flock` lock exists
  anywhere under `src/ai_workflow_engine/` and the only one in the tree
  (`agentos_workflow/orchestrator/lock.py`) is unimportable across the package boundary. Its
  documented disciplines are adopted without importing it.
- **DEC-016-004 — Run-state location.** An external, repository-scoped artifact root outside the
  worktree, reusing AUTO-015's repository-containment rejection, so a runner guarding a diff cannot
  pollute it.
- **DEC-016-007 — Command surface.** The twelve required commands plus one disclosed, retained
  read-only `verify` command carried over from the prototype.
- **DEC-016-008 — Redaction utility.** Intra-package reuse of
  `successor_planning.redaction.redact_text` rather than a duplicated runner-local redactor. No
  package boundary is crossed and no existing module is modified; duplicating a security primitive
  would let the two copies drift.

**Independent review:** One bounded Codex review, read-only, capped at three Critical/High
blockers, returned two: AUTO016-REV-001 (Critical — the contract both permitted a human-gated
commit/push and asserted that no mutating Git argv was reachable anywhere, and its gates omitted
`HUMAN_AUTHORIZATION_MODEL.md` §5a's binding, invalidation, and single-use properties) and
AUTO016-REV-002 (High — transcripts were to be persisted without the redaction that
`SECURITY_MODEL.md` §1 and `AUDIT_MODEL.md` §2 require *before* a referenced file is written, §2
forbidding a raw credential "even in a referenced file"). Both were independently re-verified
against the governing documents, found real, and remediated in one bounded correction round. One
bounded closure verification confirmed AUTO016-REV-002 `CLOSED` and returned AUTO016-REV-001
`STILL_OPEN` on one residual unqualified line in §25; that line was corrected and verified by direct
inspection, the review budget being spent — a weaker standard, recorded as such in the review
report §4a rather than presented as independently confirmed.

**Remaining prerequisites:** Three genuinely open Human Owner decisions block authorization —
**DEC-016-002** (provider-adapter ownership: runner-owned adapters, recommended, versus importing
`agentos_workflow/providers/**`), **DEC-016-005** (milestone plan location: operator-supplied
root-confined directory, recommended, versus a fixed location inside `docs/`), and **DEC-016-006**
(prototype disposition after acceptance: retain deprecated and frozen, recommended, versus remove).
Formal allowlist and acceptance-plan sign-off, a fresh dated authorization preflight, and the
explicit authorization statement `STAGE_REGISTRY.md` §3 rule 3 requires also remain.

**Boundary:** This closure does not register, authorize, or implement AUTO-016 or any later roadmap
phase. AUTO-016 remains unregistered, unauthorized, and `Planned`, with no `STAGE_REGISTRY.md` §4
row, no task entry, no branch, and no source symbol, and requires its own separate, fresh, written
Human Owner authorization. No commit, push, PR, or merge was performed or authorized. The local
prototype runner at `~/.local/share/auto015-runner/` was read in full and left unmodified. The
Current task set is empty.

## 2026-08-05 — Human Owner rulings on AUTO-016 open contract decisions (DEC-016-002, -005, -006)

**Decision:** The Human Owner ruled the three decisions the GOV-AUTO-10 closure recorded as
genuinely open. All three are binding on any future AUTO-016 implementation and are propagated into
the contract, which advances to Revision 3 and retains the status `PROPOSED — NOT AUTHORIZED`.

- **DEC-016-002 — Provider adapter ownership. RULED.** Provider adapters belong under
  `src/ai_workflow_engine/milestone_runner/providers/` and are owned by the AUTO-016
  milestone-runner package. The `agentos_workflow` provider runtime must not be reused directly.
  Adapters must use validated configuration, stdin prompt delivery, bounded timeout, captured
  stdout/stderr, durable transcripts, strict result parsing, and no credential storage. This
  confirms the contract's recommended direction and tightens its shape: Revision 2 proposed a single
  `providers.py` module, whereas the ruling requires a dedicated four-file subpackage, raising the
  package's allowed surface from sixteen to nineteen files. The alternative — importing
  `agentos_workflow/providers/**` — is closed and may not be reopened at implementation time.
- **DEC-016-005 — Milestone plan location. RULED.** The default milestone-plan root is external to
  the target repository: `~/.ai-workflow-engine/milestone-runs/<repository-id>/plans/`, a sibling of
  the run directories under the same repository-scoped artifact root. Repository-local milestone
  plans are permitted only when the governing stage contract explicitly lists their exact paths in
  its implementation allowlist — not a directory, glob, or prefix. Arbitrary repository-local plan
  discovery is forbidden: no search, walk, glob, or default scan of the worktree may exist anywhere
  in the package. This is narrower and more specific than the contract's recommendation, which named
  no default and no repository-local rule, and it is recorded as a security invariant rather than a
  preference: worktree plan discovery would let a file inside the repository the runner is guarding
  influence what the runner is permitted to change.
- **DEC-016-006 — Prototype runner disposition. RULED.** The prototype at
  `~/.local/share/auto015-runner/` remains unchanged as historical and reference tooling until
  AUTO-016 live acceptance succeeds. After successful live acceptance it is marked deprecated; it is
  never automatically deleted; its historical state and transcripts are never migrated or rewritten;
  and deletion requires a separate explicit Human Owner decision. This confirms the contract's
  recommendation and adds a sequencing condition and an explicit deletion barrier that Revision 2
  did not carry. AUTO-016's implementation touches the prototype at no point; the post-acceptance
  deprecation note is a separate operator act outside the stage allowlist.

**Propagation:** Contract Revision 3 records the rulings in a new §1b and carries them into §6, §8
(nineteen files including the `providers/` subpackage), §11, §14, §17, §21, §22 (two new invariants,
19 and 20), §23, §24, §26, §27, §28, §30, and §32. The contract review report advances to Revision 3
with a new §8a documenting the propagation check.

**Review standard:** The bounded independent review budget the Human Owner set — one Codex review,
one correction round, one closure verification — was spent during the GOV-AUTO-10 closure and was
not reopened for these rulings. The propagation was verified by direct inspection only. That is a
weaker standard than the independent review applied to Revisions 1 and 2, and it is recorded as such
in the review report §8a rather than presented as independent confirmation.

**Remaining prerequisites:** No contract decision remains open. Authorization still requires formal
allowlist sign-off against the revised nineteen-file surface, acceptance of the verification, test,
and live-acceptance plans including the assertions the rulings added, a fresh dated authorization
preflight, and the explicit authorization statement `STAGE_REGISTRY.md` §3 rule 3 requires.

**Boundary:** These are design rulings, not an authorization. Ruling on how a capability would be
built is a different act from authorizing that it be built
(`HUMAN_AUTHORIZATION_MODEL.md` §5a). AUTO-016 remains unregistered, unauthorized, and
unimplemented, with no `STAGE_REGISTRY.md` §4 row, no task entry, no branch, and no source symbol.
No production source, test, script, package file, dependency, workflow runtime, provider, or the
local prototype runner was created, modified, or deleted. No commit, push, PR, or merge was
performed or authorized. The Current task set is empty.

## 2026-08-05 — AUTO-016 contract correction AUTO016-REV-003 — Git-authority restatement

**Decision:** A bounded verification identified two residual absolute Git-authority statements in
the AUTO-016 contract that contradicted its own §20 gated commit and push capability. Both are
corrected, documentation-only, in contract Revision 4.

- **Contract §1, implementation class.** "Performs no commit, push, PR, merge, or governance
  mutation" — an unqualified claim, incompatible with §20's Human Owner–gated capability. Replaced
  with the precise semantics: AUTO-016 performs no **automatic** commit, push, pull-request
  creation, merge, branch deletion, reset, restore, rebase, stash, or governance mutation; commit
  and push execute only when explicitly enabled by configuration, separately approved by the Human
  Owner, bound to repository identity, branch, baseline SHA, the exact staged diff or commit
  payload and the exact operation, single-use, and invalidated by branch drift, HEAD drift,
  changed-path drift, verification failure, expiry, or prior use; pull-request creation, merge,
  branch deletion, reset, restore, rebase, stash, and governance mutation remain forbidden outright
  unless a future separate contract explicitly authorizes them.
- **Contract §4, entry condition 4.** "Because the runner never commits, this value is invariant
  for a whole run" — rescoped to invariance up to the §20 commit gate, an approved commit being the
  only event that may advance `HEAD`, recorded with the approval that authorized it.
- **Contract §20, approval binding.** The bound-state bullet gains repository identity and the
  exact authorized operation (commit or push, never both, never a substitute); the invalidation
  bullet names all six triggers explicitly.

**Why this was missed.** The Revision 2 remediation of AUTO016-REV-001 swept for mutating-Git
*argv* language and re-scoped every instance it found. It did not sweep capability *summaries*, so
two prose restatements survived. The contract review report §4a now records that its own earlier
sweep claim — "the only remaining unqualified commit/push statement carries an explicit 'by default'
qualifier" — was wrong, and leaves the claim visible rather than rewriting it.

**Boundary:** Git authority is **narrowed and made explicit, never broadened**. No design change,
no Human Owner decision change, no ruling change, no new capability, and no authorization. AUTO-016
remains unregistered, unauthorized, and unimplemented, status `PROPOSED — NOT AUTHORIZED`. Only
four documentation files were touched. No production source, test, script, package file,
dependency, workflow runtime, provider, or the local prototype runner was modified. No commit,
push, PR, or merge was performed or authorized. The Current task set is empty.

## 2026-08-05 — AUTO-016 registered and authorized (registration only; no implementation)

**Decision:** The Human Owner registered and authorized AUTO-016 — Integrated Milestone Automation
Runner — in one written directive: "I authorize AUTO-016 implementation under the finalized AUTO-016
contract and its exact implementation allowlist." AUTO-016 had never been registered before, so this
single act records both its registration and its authorization. Registry state moves
`NOT_STARTED → AUTHORIZED` (`docs/workflow-automation/STAGE_REGISTRY.md` §4/§5); task status moves to
`Current`. This satisfies the four authorization prerequisites contract §30 left outstanding and the
six acceptance criteria of §32.

**Authorization boundary.** Authorization is limited to exactly the finalized **Revision 4** contract
(`docs/workflow-automation/stage-prompts/AUTO-016.md`, SHA-256
`56f6a8f5720f30543f5b0623f5cb52ffa2cc45cbe51be8c5f9b9f5f256b90a7e`) and its independent review
(`docs/reports/workflow-automation/AUTO-016-contract-review.md`, Revision 3, SHA-256
`00c44cac08891f166be1bc50412a18069c305e31259a984a469f3b7ff699a58d`, verdict "CONTRACT READY FOR HUMAN
OWNER AUTHORIZATION"). The directive names the implementation allowlist explicitly, so §23's exact
nineteen-file package surface (fifteen modules plus the four-file `providers/` subpackage), the
additive `cli.py` surface, and the twelve new test modules are the authorized surface, with §24's
forbidden surface unchanged. Also bounded in: DEC-016-001 (Core Engine architecture, no
`agentos_workflow.WorkflowService` integration), the ruled DEC-016-002/-005/-006, the
evidence-resolved DEC-016-003/-004/-007/-008, the twenty security invariants (§22), the run state
machine (§10), the durable state model (§11), the plan format and location rules (§14), the scope
guard (§15), the verification executor (§16), the provider boundary (§17), the
sanitization-before-persistence boundary (§17a), the result grammar (§18), the review and budget
policy (§19), the human gates and two-surface Git authority (§20), the configuration model (§21), the
verification plan (§25), the test matrix (§26), the two-tier live-acceptance plan (§27), the
migration plan (§28), the defect policy (§29), and the implementation stop condition (§31). Nothing
outside the finalized contract is authorized.

**Preflight (contract §30 prerequisite 3; `STAGE_REGISTRY.md` §3 rule 1), verified before any file was
modified:** predecessor AUTO-015 `COMPLETE`, merged as `e325f95` and published via PR #17; AUTO-001
through AUTO-015, GOV-4, GOV-AUTO-08, and GOV-AUTO-10 all `COMPLETE`/`Done`; no other `Current` task
anywhere in the queue (the `Current` set was empty, so `maximum_current_tasks: 1` is satisfied by this
promotion); registry and `docs/TASK_QUEUE.md` in agreement; branch `main`, working tree clean, `main`
== `origin/main` at `3b1cc232b3ae8a32f19f154a98ec89b1f464b946`; `workflowctl verify --config
self-governance.yaml` full PASS across all five checks (`git`, `task-state` at `0 Current, 51 Done, 6
Planned`, `governance`, `registries` at 25 stages across 2 registries, `handover`), with
`check-task-state`, `check-governance`, and `check-handover --source working-tree` each independently
PASS; no blocking OD-# (OD-6, OD-7, OD-10, OD-11, OD-12 each explicitly "blocks nothing's
authorization"); and no pre-existing AUTO-016 branch, Registry row, source symbol, or task entry.

**Scope of this session — registration only.** The Human Owner bounded this session to exactly three
permitted acts: prepare and validate the authorization governance edits; commit exactly those
governance files to `main` as one documentation-only authorization commit; then stop with AUTO-016
`AUTHORIZED` and implementation progress 0%. Push is explicitly withheld for Human Owner review. The
registered branch `feature/auto-016-milestone-runner` was **not created**, and the
`AUTHORIZED → IN_PROGRESS` initial-start transition (rule 4) does **not** occur here: rule 14 requires
the branch to be cut from a `main` baseline that already carries this authorization record, which
depends on the Human Owner's own review and push of this commit. Under rule 17 the recorded
authorization is not weakened by this — implementation simply has not begun.

**Directed sequencing.** After the Human Owner reviews and pushes this authorization commit to
`origin/main`, a separate **initial-start session** creates `feature/auto-016-milestone-runner` from
that synchronized authorized baseline, records `AUTHORIZED → IN_PROGRESS`, and stops before
implementation. A separate **implementation session** then executes AUTO-016 using the milestone
runner. Live acceptance (§27), including its Tier 2 real Claude/Codex invocations under the
`live_cli` marker, is authorized only as the finalized contract defines it and only during that later
implementation/verification phase — never during this authorization session.

**Boundary:** Six documentation and governance files were modified, exactly the sanctioned
governance-transition edit set of rule 1: `docs/TASK_QUEUE.md`, `docs/current_task.md`,
`docs/remaining_tasks.md`, `docs/PROJECT_STATE.md` (prose only; the `Current Version:` fact line
untouched), this file, and `docs/workflow-automation/STAGE_REGISTRY.md` (§4 row and one §5
Authorization Log row) — the same six-file shape as the AUTO-015 authorization commit `c9cda88`. No
production source, test, script, package file, dependency, workflow runtime, provider, CI
configuration, or the local prototype runner at `~/.local/share/auto015-runner/` was created,
modified, or deleted; no `src/ai_workflow_engine/milestone_runner/` package, CLI command, test, run
state, or configuration file exists. No branch, push, PR, or merge occurred. The authorization
directive and the preflight above are dated 2026-08-05; the commit carrying this record was made on
2026-08-06, which changes no recorded fact and is noted so the commit timestamp is not mistaken for a
second authorization act.

## 2026-08-08 — Human Owner approved and closed AUTO-016

**Decision:** The Human Owner reviewed the AUTO-016 implementation and approved its governance
closure. AUTO-016 — Integrated Milestone Automation Runner — was implemented on branch
`feature/auto-016-milestone-runner` (`4fa9212` initial start, `34ae307` implementation, `f41d3f3`
CI fix) and published via pull request **#19**, merged into `main` as **`b4534c7`** on 2026-08-08.
PR #19's CI is green. The stage delivers exactly the nineteen-file
`src/ai_workflow_engine/milestone_runner/` package DEC-016-001 and contract §23.1 fix, plus one
additive `workflowctl milestone-runner` Typer sub-app; with shipped defaults it commits nothing,
pushes nothing, opens no pull request and merges nothing.

**Repository-native evidence.** The completion report
(`docs/reports/workflow-automation/AUTO-016-completion-report.md`) records the §25 verification
command set, the twenty §22 security invariants each held by a named negative test, the ten
prototype-defect regressions, a real wheel build and a fresh-venv out-of-tree import, the §27 Tier 1
disposable-repository acceptance matrix, the four-way proof that no automatic Git mutation occurs,
the DEC-016-006 prototype non-interference fixtures, and the DEC-016-005 plan-location assertions.
It also records, and does not paper over, the two §25 commands not executed in that evidence set
(`pre-commit run --all-files` and `pytest -q -m live_cli -rs`) — both of which were subsequently
executed and passed in the external runner's final verification set recorded below. The other
repository-native artifacts backing this closure are the implementation diff on PR #19, PR #19's CI
results, PR #19 itself, and merge commit `b4534c7`.

**Milestones.** 9/9 complete: AUTO-016-M01 through AUTO-016-M09.

**Review, correction, and closure history.** One bounded independent Codex review was conducted
against the delivered code and returned `AUTO016_REVIEW_BLOCKED` with three High blockers, all in
`application.py`: **AUTO016-IMPL-001** (a crash during a provider invocation could let resume repeat
an already-effectful invocation without reconciliation), **AUTO016-IMPL-002** (the push gate was
unreachable after the runner's own approved commit, because the push preflight still demanded the
original baseline SHA), and **AUTO016-IMPL-003** (Git approval and consumption were persisted only
after the external Git mutation, leaving an unrecorded and reusable crash window). Each was
reproduced first and then corrected in one bounded correction round. The single closure
verification returned **AUTO016-IMPL-002 `CLOSED`** and **AUTO016-IMPL-003 `CLOSED`**, and
**AUTO016-IMPL-001 `STILL_OPEN`** — the corrected reconciliation still compared changed-path names
rather than content. A separate GOV-AUTO-11 correction round, raised by the run against itself
earlier, closed GOV-AUTO-11-F1 through F4, each held closed by a named test.

**Final blocker remediation.** The Human Owner authorized one narrowly bounded production
remediation to close AUTO016-IMPL-001, scoped to `state.py`, `application.py` and their three test
modules only. It replaced changed-path-name reconciliation with a durable pre-invocation SHA-256
content fingerprint. A strictly read-only, out-of-band Codex verification — explicitly not a new
review round, and bounded to four questions — returned `AUTO016-IMPL-001 CLOSED`. It was recorded
with `budget_effect: none`: no further review, correction, or closure round was authorized or
performed. **All three of AUTO016-IMPL-001, -002 and -003 are closed.**

**Evidence — Human Owner–confirmed external runner record.** The following is confirmed directly by
the Human Owner from the local AUTO-016 runner at `~/.local/share/auto016-runner/`, with durable run
state under `~/.ai-workflow-engine/milestone-runs/`; it was produced and observed **outside this
repository** and is **not** claimed to exist as a repository-stored artifact or transcript: runner
run ID `auto016-20260805T213855Z-7fea75fc`; baseline `4fa9212`, contract SHA-256
`56f6a8f5720f30543f5b0623f5cb52ffa2cc45cbe51be8c5f9b9f5f256b90a7e`; nine completed milestones;
`review_attempts` 1 and `successful_review_rounds` 1; `correction_round` 1; `closure_round` 1; the
final verification set 11/11 exit 0 (`pytest -q`, `pytest -q -m live_cli -rs`, `ruff check .`,
`black --check .`, `mypy --strict`, `pre-commit run --all-files`, `git diff --check`,
`workflowctl check-task-state`, `check-governance`, `check-registries`, `check-handover`); the
out-of-band verdict file
`~/.local/share/auto016-runner/state/auto016-impl-001-out-of-band-verdict.txt`, SHA-256
`80a473b8811974a651c91bc385647707d5046c0acca401d888531f9346294989`, containing exactly
`AUTO016-IMPL-001 CLOSED`; a durable `blocking_findings` list that is **empty**; and final runner
state **`READY_FOR_COMMIT_APPROVAL`**. No repository artifact path is claimed for the Codex review,
the closure verification, or the out-of-band verification.

**Deferred finding retained as non-blocking.** `AUTO-016-M08-BLOCKER-001` remains recorded in the
external runner's durable state as a deferred finding, classified `cross_milestone` by Human Owner
ruling on 2026-08-07 and carrying `budget_effect: none`. It records a pre-existing conflict between
AUTO-016-M04's `TestProviderSpawnOnlyFromProvidersSubpackage` allowed set and both contract §20's
required `approval_git.py` execution vectors and AUTO-016-M05's independent `verification.py`
`subprocess.run` — neither file inside AUTO-016-M08's `allowed_files`, and the test not in M08's
focused verification, so M08 could not have turned it green. It is **not** a blocking finding, it
blocks nothing, and it was subsequently resolved on its merits as GOV-AUTO-11-F4. The pre-existing
deferred, non-blocking items OD-6, OD-7, OD-10, OD-11, OD-12 and D-14 through D-16 are each
dispositioned "not applicable" or "not a blocker" in the completion report for AUTO-016's scope, and
none was fixed by this closure. The suspected load-sensitive flake in AUTO-015's
`test_successor_planning_publishes_once_and_is_idempotent` is likewise recorded, deferred, and not
claimed as a defect.

**No remaining blocking findings.** Registry state moves `IN_PROGRESS → COMPLETE`
(`docs/workflow-automation/STAGE_REGISTRY.md` §4/§5); task status moves `Current → Done`
(`docs/TASK_QUEUE.md`, `docs/current_task.md`, `docs/remaining_tasks.md`). The Current task set is
now empty.

**Boundaries:** This decision approves and closes only AUTO-016's governance record. It does not
register, authorize, or implement AUTO-017 or any later roadmap phase — every successor remains
unregistered, unauthorized, and `Planned`, and requires its own separate, fresh, written Human Owner
authorization. It does not authorize any further commit, push, PR, or merge beyond PR #19 and merge
commit `b4534c7`, both of which had already occurred before this closure entry was written. It does
not deprecate or delete the local prototype runner at `~/.local/share/auto015-runner/`: DEC-016-006
makes post-acceptance deprecation a separate operator act and deletion a separate explicit Human
Owner decision, and neither is taken here. Six governance files were modified, exactly the sanctioned
closeout mirror set and the same shape as the AUTO-015 closure commit `ef1d565`:
`docs/TASK_QUEUE.md`, `docs/current_task.md`, `docs/remaining_tasks.md`, `docs/PROJECT_STATE.md`
(prose only; the `Current Version:` fact line untouched), this file, and
`docs/workflow-automation/STAGE_REGISTRY.md` (§4 row and one appended §5 Authorization Log row; no
historical row rewritten). No production source, test, script, package file, dependency, workflow
runtime, provider, CI configuration, or external runner file was created, modified, or deleted.
