# AUTO-015 Human Owner Decision Record

## Binding status

This record captures capability selection only. It does not authorize AUTO-015 implementation,
create an AUTO-015 branch, register an AUTO-015 stage, or authorize commit, push, PR, or merge.
Any implementation requires a separately reviewed stage contract and explicit authorization.

## 1. Selection — exactly one

- [ ] Preparation Mode
- [ ] Reviewer Mode
- [ ] Codex Correction Mode
- [x] Automatic Next-Stage Computation and Prompt Generation
- [ ] Runtime Daemon/Scheduler
- [ ] Operator Interface
- [ ] Multi-task Orchestration
- [ ] Security Hardening
- [ ] Provider Expansion
- [ ] Deferred-Defect Remediation
- [ ] No AUTO-015 at this time
- [ ] Other — mandatory written definition below

## 2. Selected capability definition

| Field | Human Owner decision |
|---|---|
| Selected capability | Automatic Next-Stage Computation and Prompt Generation |
| Stage title | AUTO-015 — Deterministic Next-Stage Proposal and Governed Prompt Generation |
| Mission | Inspect authoritative governance state and completed-stage evidence, compute bounded eligible successor proposals, and render a governed prompt draft without selecting, registering, authorizing, or executing a successor automatically. |
| Primary user | Human Owner operating the local `ai-workflow-engine` workflow. |
| User-visible outcome | Deterministic proposal artifact containing authoritative project state, eligible candidates, blocked/ineligible candidates with reasons, an evidence-supported recommendation when policy permits, a governed prompt draft, and explicit non-authorization warnings. |
| Entry conditions | AUTO-014 `COMPLETE`; clean synchronized baseline; no conflicting Current task; governance verification passes; authoritative task, registry, handover, and completion evidence readable; no unauthorized successor implementation. |
| Exit conditions | Proposal persisted; eligibility and rejection reasons recorded; prompt structurally validated; no task, registry, workflow, authorization, Git, or runtime state changed; execution stops for Human Owner review. |
| Runtime flow | Read authoritative state → reconcile task/registry/handover/completion evidence → enumerate candidates → apply deterministic eligibility/blocking rules → produce recommendation or “no eligible successor” → render prompt draft → validate structure → persist artifact → stop at owner gate. |
| Architecture | `WorkflowService` → read-only successor-planning operation → deterministic successor planner → authoritative governance/state readers → candidate eligibility policy → existing governed prompt renderer/validator → proposal artifact store. |
| Exact scope | Read-only repository/governance inspection; deterministic eligibility; blocked-candidate reasoning; prompt draft generation; proposal serialization/persistence; any future CLI/service access only if separately authorized; deterministic/security validation. |
| Explicit exclusions | No authoritative candidate selection; AUTO stage registration; authorization creation; task/workflow mutation; provider invocation; Claude/Codex execution; branch creation; target source modification; commit/push/PR/merge/closeout; daemon/scheduler; Telegram; multi-task orchestration. |
| Allowed source files | None authorized by this decision. A separate AUTO-015 contract must name the exact implementation/test paths. |
| Allowed documentation/governance files | None authorized for runtime mutation. Proposal/prompt artifact location must be specified by the separate contract; authoritative governance documents remain read-only. |
| State ownership | No existing `WorkflowState` is owned or changed. Use a separate planning/proposal artifact unless a later reviewed contract proves otherwise. |
| Provider permissions | None by default; deterministic implementation must not require an AI provider. Optional provider assistance requires separate authorization and cannot decide or mutate. |
| Write authority | Only the separately contracted proposal/prompt artifact location; no authoritative governance or target-repository source writes. |
| Approval gates | Human Owner reviews the proposal and separately decides whether to register and authorize a successor stage. |
| Commit permission | None for AUTO-015 runtime behavior. |
| Push permission | None. |
| PR permission | None. |
| Merge permission | None. |
| Deterministic verification | Identical authoritative inputs produce identical canonical output; eligibility rules are explicit; stale/contradictory/incomplete evidence fails closed; prompt structure and hashes validate; no mutation occurs; proposal is always labeled non-authoritative and unauthorized. |
| Live acceptance requirements | Disposable repositories/fixtures covering one eligible candidate, competing candidates, no eligible candidate, stale/contradictory mirrors, missing completion evidence, and malicious or prompt-injection-like content; prove no mutation, deterministic output, safe refusal, and non-authoritative prompt labeling. |
| Security invariants | Repository-relative confinement; no secrets in proposals/prompts; authoritative-source precedence; untrusted text treated as data; prompt-injection resistance; no implicit authority; fail-closed behavior; canonical input/output hash binding. |
| Defect policy | Record and classify newly discovered defects. Fix only a defect proven to directly block a separately authorized AUTO-015 contract, with the smallest documented scope. Do not bundle deferred defects. |
| Stop condition | Stop after producing and validating the proposal and prompt draft. Await explicit Human Owner action; never register, authorize, implement, or run a successor automatically. |

## 3. Required confirmations

- Predecessor AUTO-014 is `COMPLETE`: **Yes**
- This selection is exactly one option: **Yes**
- AUTO-015 remains unregistered: **Yes**
- AUTO-015 implementation authorization: **Not authorized**
- No implementation begins before a separate explicit authorization: **Yes**
- Existing workflow states/transitions are preserved: **Yes**
- No provider receives authority by inheritance: **Yes**
- No commit, push, PR, or merge is authorized: **Yes**
- Defects remain governed by the stated defect policy: **Yes**

## 4. Decision record

| Field | Human Owner decision |
|---|---|
| Decision date | 2026-08-04 |
| Human Owner identity | Human Owner |
| Decision statement | I select **Automatic Next-Stage Computation and Prompt Generation** as the proposed basis for AUTO-015. |
| Authorization statement | **Not authorized.** |
| Decision rationale | This capability directly supports governed continuation after AUTO-014 while preserving the mandatory Human Owner gate. |
| Alternatives rejected/deferred | Preparation Mode, Reviewer Mode, Codex Correction Mode, daemon/scheduler, operator interface, multi-task orchestration, security hardening, provider expansion, and deferred-defect remediation remain separate future work. |
| Required follow-up | A separate AUTO-015 contract-definition step must review the proposal, name exact files and acceptance criteria, and obtain explicit authorization before implementation. |

## 5. Governance disposition

- [x] Choice is exactly one and the required fields are complete.
- [x] Scope is recorded without authorizing implementation.
- [x] AUTO-015 registration is withheld because authorization is absent.
- [x] No AUTO-015 contract or implementation branch is created in this step.
- [x] GOV-AUTO-08 may close; the selected capability remains a proposal until separately authorized.

AUTO-015 is conceptually selected but remains unregistered, unauthorized, and unimplemented.
