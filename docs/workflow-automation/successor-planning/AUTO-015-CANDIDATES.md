# AUTO-015 Successor Candidates

## Governance status

This is a decision-support document for GOV-AUTO-08. It does not register, authorize, or
implement AUTO-015. AUTO-014 is `COMPLETE`; AUTO-015 remains undefined, unregistered, and
unauthorized until the Human Owner completes the decision form and records a separate
authorization.

The comparison uses the current contracts in `MVP_SCOPE.md`, `ARCHITECTURE.md`,
`WORKFLOW_STATES.md`, `MACHINE_GATES.md`, `AGENT_CONTRACTS.md`, `SECURITY_MODEL.md`,
`CONFIGURATION_MODEL.md`, and `HUMAN_AUTHORIZATION_MODEL.md`. “Expected source/test surface” is
a planning estimate, not permission to edit those files.

## Decision rule

Exactly one option may be selected later. A selection is not an implementation authorization.
The selected capability still requires a new AUTO-015 contract, exact file allowlist, fresh
preflight, and explicit Human Owner authorization. “No AUTO-015 at this time” is a valid outcome.

## Comparison summary

| Option | Main value | MVP relation | Relative size | Primary gating concern |
|---|---|---|---|---|
| Preparation Mode | prepare/verify a stage workspace | Mostly inside existing architecture; new mode contract | M | branch and write-boundary safety |
| Reviewer Mode | independent review of an existing result | Adjacent to MVP; extends QA semantics | M | authority and review evidence binding |
| Codex Correction Mode | bounded correction after review | Outside current delivered flow; uses existing repair concepts | M/L | Codex write authority and repair scope |
| Automatic Next-Stage Computation and Prompt Generation | derive and render the next contract | Outside current runtime MVP | M | must not silently authorize or select |
| Runtime Daemon/Scheduler | unattended/resident execution | Explicitly deferred/outside MVP | L/XL | unattended authorization and lifecycle safety |
| Operator Interface | Telegram or comparable remote control | Outside MVP | L | remote authentication and command authority |
| Multi-task Orchestration | coordinate several workflows | Explicitly deferred/outside MVP | XL | locks, isolation, fairness, failure coupling |
| Security Hardening | reduce residual threat exposure | Cross-cutting; may be inside or outside MVP by finding | S/M | must define a bounded security defect |
| Provider Expansion | add another model/provider adapter | Adjacent to provider contracts; scope-dependent | M | provider isolation and permission parity |
| Deferred-Defect Remediation | fix a named existing defect | Inside existing architecture if narrowly bounded | S/M | exact defect and regression boundary |
| No AUTO-015 at this time | preserve a safe stopping point | No runtime change | S | owner intentionally defers successor |
| Other (written definition) | owner-defined capability | Unknown until defined | Unknown | definition completeness |

## Candidate 1 — Preparation Mode

- **Problem solved:** establish a controlled, inspectable workspace for a named task before implementation, including baseline, branch, configuration, and preconditions.
- **Intended user:** Human Owner or local operator preparing one authorized target-repository workflow.
- **User-visible result:** a persisted preparation report and a ready/blocked decision; no implementation result.
- **Relationship to AUTO-013/AUTO-014:** precedes AUTO-013’s foreground implementation and would feed AUTO-014 only indirectly; neither predecessor currently defines this as a mode.
- **MVP:** largely inside the local, one-workflow architecture, but a distinct mode is not delivered.
- **Required architecture changes:** a preparation operation/driver, durable preparation evidence, CLI/service entry point, and explicit composition with repository lock, state store, PMO, and branch skills.
- **Workflow states affected:** ideally `AUTHORIZED`, `PRECONDITIONS_CHECKED`, `BRANCH_CREATED`, or a separate mode record; no new state may be assumed.
- **Provider permissions:** none by default; provider invocation must be explicitly excluded unless separately authorized.
- **Write authority:** repository writes limited to the named stage branch and only after gates; baseline writes forbidden.
- **Approval model:** Human Owner authorization remains the only start gate; preparation completion must not imply implementation approval.
- **Security implications:** branch/baseline binding, path confinement, lock ownership, clean-tree checks, and stale-preparation invalidation.
- **Configuration changes:** preparation policy, branch naming, allowed paths, and possibly whether branch creation is automatic.
- **Expected source surface:** new mode/driver and service/CLI wiring; repository/branch and state-store integration; no provider changes expected.
- **Expected test surface:** state/resume, clean-tree and branch binding, no-provider/no-implementation, idempotency, scope, and security tests.
- **Live acceptance requirements:** disposable target repository; prove preparation cannot commit, push, open a PR, or invoke a provider.
- **Dependencies:** current PMO/repository skills, lock/state store, exact authorization binding, and a decision on branch ownership.
- **Explicit exclusions:** implementation, review, correction, prompt selection, daemon, Telegram, multi-task orchestration, commit/push/PR/merge unless separately specified.
- **Relative size:** medium.
- **Principal risks:** preparation becomes implicit authorization; stale branch/evidence is reused; users assume “ready” means “approved.”
- **Deferred defects that block/influence it:** OD-10, OD-11, OD-12 affect reliable real execution; OD-7 affects reauthorization after baseline drift.
- **Reasons to select:** clear separation of concerns and a useful safety boundary before agent writes.
- **Reasons to reject/defer:** may duplicate existing precondition/branch logic and provide little user value without a following mode.

## Candidate 2 — Reviewer Mode

- **Problem solved:** independently inspect an implementation or workflow result and produce a bounded, evidence-based verdict.
- **Intended user:** Human Owner seeking independent review before accepting a stage result.
- **User-visible result:** immutable review report with findings, verdict, evidence hashes, and explicit approval recommendation.
- **Relationship to AUTO-013/AUTO-014:** reviews AUTO-013’s PR-producing result and AUTO-014’s closeout evidence without performing either implementation or merge.
- **MVP:** adjacent to the existing QAAgent/Codex provider path; a separately resumable mode is not in the delivered MVP.
- **Required architecture changes:** review driver, review artifact schema, evidence binding, report discovery, and a clear distinction between QA and owner approval.
- **Workflow states affected:** `QA_RUNNING`, `READY_TO_COMMIT`, `PR_OPEN`, or a separate review record; no unapproved transition may be added.
- **Provider permissions:** Codex read-only review by default; no repository mutation, Git mutation, provider chaining, or approval grant.
- **Write authority:** review artifacts only in the governed report location; target source and baseline remain read-only.
- **Approval model:** review verdict is evidence, never authorization; Human Owner separately accepts or rejects.
- **Security implications:** diff/evidence authenticity, prompt isolation, secret redaction, report confinement, and reviewer non-bypassability.
- **Configuration changes:** reviewer provider, timeout, report path, independent-review requirement, and finding severity policy.
- **Expected source surface:** review driver/report models, read-only service entry point, provider invocation policy, and CLI if required.
- **Expected test surface:** tampered evidence, stale diff, provider isolation, forbidden writes, verdict parsing, resume, and report immutability.
- **Live acceptance requirements:** disposable repository with a known defect and a clean case; prove the reviewer sees the real diff and cannot change it.
- **Dependencies:** AUTO-011 result contract, AUTO-012 approval subsystem, AUTO-013 artifacts, and clear QA-versus-review semantics.
- **Explicit exclusions:** correction, commit, push, PR creation, merge, automatic acceptance, daemon, Telegram, and task selection.
- **Relative size:** medium.
- **Principal risks:** duplicate QA, review result treated as approval, or Codex being granted hidden write capability.
- **Deferred defects that block/influence it:** OD-10/11/12 affect runtime evidence; D-14–D-16 may affect AUTO-013 review interpretation.
- **Reasons to select:** strengthens independent assurance at a natural post-AUTO-014 boundary.
- **Reasons to reject/defer:** value may be incremental if existing QA evidence is sufficient; terminology and gate placement require owner policy.

## Candidate 3 — Codex Correction Mode

- **Problem solved:** apply a bounded correction after an independent review identifies an actionable defect.
- **Intended user:** Human Owner who wants a controlled repair loop with Codex as the correction provider.
- **User-visible result:** corrected diff plus a new deterministic validation and review record, or a safe stop.
- **Relationship to AUTO-013/AUTO-014:** extends AUTO-013’s Claude repair concept and follows review of AUTO-013/AUTO-014 evidence; it is not present in either predecessor.
- **MVP:** outside the delivered MVP’s fixed provider/mode flow unless narrowly defined as a future bounded repair capability.
- **Required architecture changes:** correction driver, patch/scope binding, correction-attempt ledger, revalidation/review cycle, and provider-role policy.
- **Workflow states affected:** likely `REPAIRING` and `VALIDATING`; any new transition requires an explicit contract and state decision.
- **Provider permissions:** Codex may receive only the exact correction role and bounded paths; Claude and Codex sessions remain isolated.
- **Write authority:** only the authorized stage branch and only files in the correction allowlist; no baseline or remote mutation.
- **Approval model:** Human Owner authorizes the correction mode; every correction is bounded and final acceptance remains separate.
- **Security implications:** prompt injection, arbitrary patch expansion, provider confused-deputy risk, secret exposure, and replayed review findings.
- **Configuration changes:** correction budget, allowed paths, finding-to-patch mapping, provider sandbox, and failure policy.
- **Expected source surface:** correction driver/agent, patch validation, service/provider plumbing, reports, and possibly state handling.
- **Expected test surface:** scope escape, malformed patch, repeated correction, poisoned finding, attempts, resume, and provider isolation.
- **Live acceptance requirements:** disposable repository with a deliberately failing test; prove bounded correction and no unauthorized file/remote changes.
- **Dependencies:** Reviewer Mode or equivalent evidence, deterministic validation, result contract, approval persistence, and a decision on Codex write permissions.
- **Explicit exclusions:** unrestricted Codex coding, autonomous acceptance, commit/push/PR/merge, daemon, remote operator, and multi-task behavior.
- **Relative size:** medium to large.
- **Principal risks:** expands write authority and can turn review evidence into autonomous code modification.
- **Deferred defects that block/influence it:** OD-10/11/12; any D-14–D-16 affecting repair boundaries; OD-7 for stale authorization.
- **Reasons to select:** closes a potentially useful review-to-repair loop with bounded automation.
- **Reasons to reject/defer:** highest safety complexity among single-workflow candidates and may be unnecessary before review policy is proven.

## Candidate 4 — Automatic Next-Stage Computation and Prompt Generation

- **Problem solved:** derive a candidate next capability from current evidence and render a prompt for owner review.
- **Intended user:** Human Owner planning the roadmap after a completed stage.
- **User-visible result:** deterministic candidate proposal and prompt draft, explicitly awaiting owner selection/authorization.
- **Relationship to AUTO-013/AUTO-014:** consumes their completion records and must preserve the rule that closeout never selects a successor.
- **MVP:** outside the current runtime MVP; prompt rendering is read-only and automatic next-stage computation is explicitly future-looking.
- **Required architecture changes:** proposal model, candidate policy, evidence inputs, deterministic ranking, prompt renderer integration, and a hard authorization boundary.
- **Workflow states affected:** none in the runtime workflow; may add planning records only, never `AUTHORIZED` or `Current` automatically.
- **Provider permissions:** none required; if models are consulted, they may propose only and cannot authorize or mutate.
- **Write authority:** proposal/prompt artifact only, with no target-repository or task-state mutation.
- **Approval model:** Human Owner must choose exactly one candidate and separately authorize AUTO-015; generated text is non-authoritative.
- **Security implications:** prompt injection from reports, poisoned evidence, deterministic reproducibility, and accidental auto-promotion.
- **Configuration changes:** candidate catalog, ranking policy, source documents, output path, and owner-review requirements.
- **Expected source surface:** proposal/prompt planner, canonical serialization, read-only CLI/service surface, and documentation schemas.
- **Expected test surface:** deterministic same-input output, stale/tampered evidence, no-current-task mutation, no authorization, and prompt contract validation.
- **Live acceptance requirements:** complete AUTO-014 evidence plus conflicting candidate signals; prove output remains a proposal and exactly no task/stage state changes.
- **Dependencies:** candidate catalog from GOV-AUTO-08, report/state readers, prompt renderer, and explicit owner decision form.
- **Explicit exclusions:** selecting a candidate, registering AUTO-015, authorization, implementation, daemon, Telegram, and orchestration.
- **Relative size:** medium.
- **Principal risks:** apparent neutrality hides policy choices; generated prompt is mistaken for authorization; report content is attacker-controlled.
- **Deferred defects that block/influence it:** OD-7, OD-10–OD-12, and all unresolved predecessor findings that change evidence trust.
- **Reasons to select:** directly improves governance continuity while preserving the human gate.
- **Reasons to reject/defer:** may be premature; a static owner decision package can achieve the immediate planning need without runtime change.

## Candidate 5 — Runtime Daemon/Scheduler

- **Problem solved:** run or resume workflows without a foreground operator invocation.
- **Intended user:** operations owner managing recurring or unattended automation.
- **User-visible result:** scheduled execution, durable status, alerts, and safe recovery across process restarts.
- **Relationship to AUTO-013/AUTO-014:** would invoke/resume their foreground and closeout capabilities; neither predecessor authorizes unattended operation.
- **MVP:** explicitly outside/deferred from the local foreground MVP.
- **Required architecture changes:** daemon lifecycle, scheduler, leases, restart/recovery, observability, signal handling, and unattended authorization policy.
- **Workflow states affected:** all resumable states plus daemon/job states; likely requires a separate orchestration state model.
- **Provider permissions:** inherited permissions must never be broadened by unattended execution; provider credentials require explicit policy.
- **Write authority:** same target branch restrictions, with additional unattended side-effect controls and shutdown reconciliation.
- **Approval model:** must define pre-authorized recurring scope versus per-run Human Owner approval; no safe default is assumed.
- **Security implications:** credential persistence, process identity, replay, privilege escalation, stale locks, and unattended destructive operations.
- **Configuration changes:** schedules, leases, retry limits, notification, retention, and authorization expiration.
- **Expected source surface:** daemon/scheduler, service lifecycle, persistence, locks, CLI controls, config, and telemetry.
- **Expected test surface:** crash/restart, duplicate execution, clock behavior, lock recovery, auth expiry, signal handling, and side-effect reconciliation.
- **Live acceptance requirements:** disposable repository, induced process termination, bounded schedule, and proof of no duplicate commit/merge.
- **Dependencies:** stable foreground modes, safe reauthorization policy, robust remote reconciliation, and operational threat model.
- **Explicit exclusions:** Telegram, multi-task orchestration, arbitrary unattended scope, and provider expansion unless separately selected.
- **Relative size:** large to extra-large.
- **Principal risks:** converts a human-gated system into unattended automation before its safety model is complete.
- **Deferred defects that block/influence it:** OD-7 and OD-10–OD-12 are material; all live-provider and remote reconciliation defects matter.
- **Reasons to select:** operational value if recurring automation is the primary business need.
- **Reasons to reject/defer:** broadest authority expansion and explicit current non-goal.

## Candidate 6 — Operator Interface

- **Problem solved:** let an operator inspect, approve, start, pause, or stop workflows through a remote interface such as Telegram.
- **Intended user:** Human Owner/operator away from the local CLI.
- **User-visible result:** authenticated remote status and explicit command responses with audit trails.
- **Relationship to AUTO-013/AUTO-014:** would control or observe them; neither predecessor defines a remote interface.
- **MVP:** outside current MVP; Telegram is explicitly excluded by AUTO-013/AUTO-014 boundaries.
- **Required architecture changes:** adapter, command protocol, authentication/authorization, rate limits, idempotency, notifications, and audit correlation.
- **Workflow states affected:** command access to existing states; no remote interface may invent transitions.
- **Provider permissions:** interface has no direct provider access; it delegates through the orchestrator and cannot widen permissions.
- **Write authority:** remote commands may request only explicitly authorized operations; source and baseline writes remain engine-gated.
- **Approval model:** define secure Human Owner identity and step-up confirmation for consequential operations.
- **Security implications:** token theft, spoofing, replay, chat leakage, message injection, and cross-repository command confusion.
- **Configuration changes:** bot credentials, allowed identities/chats, command policy, confirmations, and notification redaction.
- **Expected source surface:** adapter, command router, auth policy, audit integration, config, and tests; no direct engine bypass.
- **Expected test surface:** forged/replayed commands, unauthorized users, duplicate delivery, redaction, concurrency, and failure delivery.
- **Live acceptance requirements:** isolated bot/test account and disposable repository; prove unauthorized chat cannot act and secrets never appear.
- **Dependencies:** stable CLI/service API, owner identity model, audit model, and operational secret handling.
- **Explicit exclusions:** daemon/scheduler, multi-task orchestration, direct provider calls, and automatic authorization.
- **Relative size:** large.
- **Principal risks:** remote control creates a new privileged perimeter and may be mistaken for authentication merely because a chat exists.
- **Deferred defects that block/influence it:** all security findings; OD-7 and OD-10–OD-12 affect safe command execution.
- **Reasons to select:** improves operator accessibility if remote operation is a validated requirement.
- **Reasons to reject/defer:** high security burden with no immediate need established by AUTO-014.

## Candidate 7 — Multi-task Orchestration

- **Problem solved:** coordinate multiple tasks/workflows across repositories or stages.
- **Intended user:** program owner managing a portfolio of independent work.
- **User-visible result:** queued/concurrent task execution, dependencies, aggregate status, and failure handling.
- **Relationship to AUTO-013/AUTO-014:** composes their single-workflow capabilities; both are explicitly one-workflow/one-target oriented.
- **MVP:** explicitly deferred/outside MVP.
- **Required architecture changes:** scheduler/queue, dependency graph, per-task locks, fairness, resource limits, aggregation, and cross-task audit.
- **Workflow states affected:** task-level orchestration states around existing runtime states; no implicit mutation of the existing state machine.
- **Provider permissions:** per-task capability isolation and quotas; never share provider sessions or authorization bindings.
- **Write authority:** per-task branch/repository confinement; cross-task writes forbidden unless specifically designed.
- **Approval model:** define whether each task needs a separate Human Owner gate; a portfolio approval cannot silently authorize all tasks.
- **Security implications:** confused deputy, cross-task data leakage, lock starvation, priority abuse, and blast radius multiplication.
- **Configuration changes:** queues, dependencies, concurrency caps, quotas, retention, and cancellation policy.
- **Expected source surface:** orchestration layer, persistence, locks, scheduler, CLI/interface, aggregation reports, and config.
- **Expected test surface:** dependency cycles, fairness, isolation, duplicate work, crash recovery, cancellation, and cross-task authorization.
- **Live acceptance requirements:** at least two disposable repositories/tasks with induced failure and proof of isolated artifacts/credentials.
- **Dependencies:** daemon/scheduler decisions, stable single-task semantics, and a broader operational model.
- **Explicit exclusions:** remote interface, provider expansion, unrestricted parallelism, and automatic successor selection.
- **Relative size:** extra-large.
- **Principal risks:** largest complexity and blast-radius increase; conflicts directly with MVP’s one-active-workflow constraint.
- **Deferred defects that block/influence it:** OD-7, OD-10–OD-12 and every provider/remote reconciliation defect.
- **Reasons to select:** only if portfolio-level throughput is the dominant unmet requirement.
- **Reasons to reject/defer:** no evidence that single-task behavior is ready for multiplication; explicit deferred scope.

## Candidate 8 — Security Hardening

- **Problem solved:** remediate a specifically identified security weakness without adding a new workflow mode.
- **Intended user:** Human Owner prioritizing risk reduction and invariant preservation.
- **User-visible result:** a named threat is reduced, with before/after evidence and no broadened authority.
- **Relationship to AUTO-013/AUTO-014:** hardens their shared foundations or a documented residual finding; it does not extend their runtime behavior.
- **MVP:** potentially inside existing architecture when the finding is narrow; moving deferred scope requires a bounded decision.
- **Required architecture changes:** only those necessary for the named finding; threat model, invariant, and regression evidence must precede edits.
- **Workflow states affected:** ideally none; existing states/transitions remain unchanged unless the finding directly requires a separately authorized change.
- **Provider permissions:** unchanged or narrowed; no provider expansion is implied.
- **Write authority:** unchanged or narrowed; baseline/remote protections remain intact.
- **Approval model:** Human Owner authorizes the exact security finding and accepts residual risk; no generalized “security” mandate.
- **Security implications:** primary purpose; must define threat, asset, attacker capability, control, and residual risk.
- **Configuration changes:** only if configuration is the vulnerability and defaults remain fail-closed.
- **Expected source surface:** smallest affected production and test/documentation surfaces, identified only after a finding is selected.
- **Expected test surface:** regression, adversarial, scope, secret, provider isolation, and invariant tests targeted to the finding.
- **Live acceptance requirements:** safe disposable test against the relevant boundary, with no real credentials or destructive remote action.
- **Dependencies:** selected defect/threat, current security model, and a precise acceptance oracle.
- **Explicit exclusions:** feature work, mode creation, provider expansion, daemon, interface, and unrelated cleanup.
- **Relative size:** small to medium, depending on finding.
- **Principal risks:** vague “hardening” scope becomes unauthorized redesign; a fix can create a new bypass.
- **Deferred defects that block/influence it:** OD-7, OD-10–OD-12 and D-14–D-16 are possible inputs, but no defect is selected here.
- **Reasons to select:** preserves safety and may deliver high value with small surface.
- **Reasons to reject/defer:** cannot be authorized honestly until one concrete threat/defect is named.

## Candidate 9 — Provider Expansion

- **Problem solved:** support an additional model/provider while retaining the existing typed, isolated contract.
- **Intended user:** operator whose approved provider availability or capability differs from Claude/Codex.
- **User-visible result:** a provider can perform only its authorized role with equivalent evidence and failure semantics.
- **Relationship to AUTO-013/AUTO-014:** must plug into their provider/runtime boundaries without changing their modes or merge flow.
- **MVP:** adjacent to the provider contract; specific providers may be outside current MVP policy.
- **Required architecture changes:** adapter, capability declaration, process sandbox, result mapping, configuration, and registry wiring.
- **Workflow states affected:** none intended; provider invocation occurs within existing state ownership.
- **Provider permissions:** explicit allowlisted capabilities, permission/sandbox mode, environment, timeout, and no inherited authority.
- **Write authority:** provider remains indirect; only authorized agents/skills may write within the active branch scope.
- **Approval model:** provider selection must not alter approval gates; Human Owner approval remains independent.
- **Security implications:** binary trust, credential handling, prompt/data egress, non-interactive enforcement, and result authenticity.
- **Configuration changes:** provider name, executable, argv policy, environment allowlist, timeout, capability mapping, and failure policy.
- **Expected source surface:** provider adapter/runtime, config schema, registry, docs, and focused tests.
- **Expected test surface:** argv/sandbox, malformed output, timeouts, isolation, permission denial, result contract, and live disposable provider tests.
- **Live acceptance requirements:** real installed provider in a disposable environment, no real target mutation, and evidence of isolation.
- **Dependencies:** stable AUTO-010/011 contracts and resolution of provider environment defects such as OD-10.
- **Explicit exclusions:** new workflow mode, automatic provider selection, daemon, Telegram, and multi-task behavior.
- **Relative size:** medium.
- **Principal risks:** capability drift, secret leakage, inconsistent failure semantics, and provider-specific bypasses.
- **Deferred defects that block/influence it:** OD-10 materially blocks real GitHub/provider use; OD-11/12 affect workflow evidence reliability.
- **Reasons to select:** practical capability expansion while reusing established boundaries.
- **Reasons to reject/defer:** provider need is not established and every adapter enlarges the trust surface.

## Candidate 10 — Focused Deferred-Defect Remediation

- **Problem solved:** correct one named, reproducible defect already recorded as deferred, with no unrelated feature work.
- **Intended user:** Human Owner or operators affected by that defect.
- **User-visible result:** defect no longer reproduces, regression evidence passes, and residual limitations are documented.
- **Relationship to AUTO-013/AUTO-014:** may remediate a finding from either completion report or the shared engine; it must not reopen or rewrite their closed records.
- **MVP:** inside existing architecture when the defect is narrowly bounded; scope is determined by the selected defect, not by this candidate label.
- **Required architecture changes:** only the minimum affected code/contracts/tests/docs; no new mode or state by default.
- **Workflow states affected:** none unless the defect itself is a state-machine defect and the owner explicitly authorizes that change.
- **Provider permissions:** unchanged; any provider involvement follows existing contracts.
- **Write authority:** existing authority only, narrowed to the defect’s allowlist.
- **Approval model:** owner selects one defect, defines acceptance, and separately approves implementation/closeout.
- **Security implications:** fixing a defect must not weaken gates; security classification and negative tests are mandatory where relevant.
- **Configuration changes:** only if the defect is configuration-related; defaults and compatibility must be explicit.
- **Expected source surface:** unknown until one defect is selected; expected to be small/targeted.
- **Expected test surface:** reproducer, regression, neighboring contract tests, and direct governance/scope checks.
- **Live acceptance requirements:** only if the defect concerns a live boundary; use disposable repositories and no production credentials.
- **Dependencies:** exact defect record, reproduction, owner-defined scope, and acceptance oracle.
- **Explicit exclusions:** broad cleanup, architecture redesign, feature expansion, and automatic selection of which defect to fix.
- **Relative size:** small to medium.
- **Principal risks:** “focused” becomes a bundle of defects; a workaround masks rather than fixes the cause.
- **Deferred defects that block/influence it:** the selected D-/OD- item is the blocker/input; no item is selected by this document.
- **Reasons to select:** highest evidence-to-scope ratio when a concrete defect has operational impact.
- **Reasons to reject/defer:** impossible to define responsibly without owner choosing the exact defect first.

## Candidate 11 — No AUTO-015 at this time

- **Problem solved:** avoids inventing a successor and preserves the completed AUTO-014 boundary while the owner gathers evidence.
- **Intended user:** Human Owner who wants a deliberate pause.
- **User-visible result:** explicit governance record that AUTO-015 has no successor and no runtime work is authorized.
- **Relationship to AUTO-013/AUTO-014:** treats both as complete and terminal for now; no chaining is inferred.
- **MVP:** fully consistent with the current MVP and stage rules.
- **Required architecture changes:** none.
- **Workflow states affected:** none.
- **Provider permissions:** none.
- **Write authority:** documentation-only decision record; no target-repository authority.
- **Approval model:** explicit owner selection of this option; a later successor requires a new decision.
- **Security implications:** minimizes new attack surface and preserves existing invariants.
- **Configuration changes:** none.
- **Expected source surface:** governance records and decision template only.
- **Expected test surface:** governance consistency and proof of no AUTO-015 registration/implementation.
- **Live acceptance requirements:** none beyond safe governance verification; no runtime acceptance is applicable.
- **Dependencies:** completion evidence for AUTO-014 and a future trigger for reconsideration.
- **Explicit exclusions:** every implementation/runtime capability listed in this document.
- **Relative size:** small.
- **Principal risks:** delayed value or loss of momentum; these are visible and reversible through a later decision.
- **Deferred defects that block/influence it:** none blocks the decision; all remain deferred and untouched.
- **Reasons to select:** honors the no-automatic-successor rule and avoids unauthorized scope.
- **Reasons to reject/defer:** does not deliver a new capability if an urgent owner priority exists.

## Candidate 12 — Other, with mandatory written definition

- **Problem solved:** an owner-identified capability not represented by the catalog above.
- **Intended user:** specified by the Human Owner in the completed decision form.
- **User-visible result:** specified, testable outcome; a label alone is insufficient.
- **Relationship to AUTO-013/AUTO-014:** must explicitly state what it consumes, changes, and leaves untouched.
- **MVP:** must be classified as inside, adjacent to, or outside MVP with rationale.
- **Required architecture changes:** must be enumerated before authorization.
- **Workflow states affected:** must name exact existing states/edges or justify a new state decision.
- **Provider permissions:** must name each provider and capability; “as needed” is invalid.
- **Write authority:** must name exact files/repositories/branches and forbidden writes.
- **Approval model:** must define Human Owner gates and prove no implicit authorization.
- **Security implications:** must name threats, invariants, and residual risk.
- **Configuration changes:** must enumerate schema/default/compatibility impact.
- **Expected source surface:** exact paths and rationale required.
- **Expected test surface:** exact tests and negative cases required.
- **Live acceptance requirements:** concrete environment, evidence, and stop criteria required.
- **Dependencies:** named prerequisites required.
- **Explicit exclusions:** mandatory and testable.
- **Relative size:** owner must estimate and justify.
- **Principal risks:** owner must identify and rank.
- **Deferred defects that block/influence it:** owner must identify relevant items without silently fixing them.
- **Reasons to select:** written mission-based rationale required.
- **Reasons to reject/defer:** written alternatives and deferral rationale required.

## Current conclusion

No candidate is selected. The options are deliberately not ranked into an automatic successor.
The Human Owner must complete `AUTO-015-DECISION-TEMPLATE.md`, selecting exactly one option or
providing the mandatory definition for “Other.” Until then, AUTO-015 remains undefined,
unregistered, unauthorized, and unimplemented.
