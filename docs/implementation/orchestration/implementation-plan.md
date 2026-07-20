# Autonomous Orchestration v3 — Staged Implementation Plan

Plan version: `1.1.0` (see decision-log.md D3-017)  
Architecture: `architecture-v3.md`  
Authoritative progress: `implementation-state.yaml`

## 1. Delivery rule

Stages execute in dependency order, one focused implementation session followed
by an independent review session. A stage is a prerequisite only when its state
is `REVIEW_APPROVED`, not merely implemented or tested. No session may widen the
stage's allowed paths. Any required out-of-scope change blocks the stage and
requires a reviewed plan amendment.

`ORCH-000` is a design review gate. Production work starts no earlier than
`ORCH-001`. Every stage has a full specification in `stages/`.

## 2. Common stage contract

Every implementation session must:

1. follow `session-protocol.md` and validate `implementation-state.yaml`;
2. require clean HEAD equal to the selected stage's `expected_base_head`;
3. verify all prerequisite review/evidence records and required migrations;
4. change only paths allowed by the stage specification;
5. run the exact stage commands and the existing regression suite required by
   its risk level;
6. write immutable evidence at
   `evidence/<stage-id>/<implementation-id>.yaml` and a handoff at
   `handoffs/<stage-id>/<implementation-id>.md`;
7. advance only to `IMPLEMENTED` or `VERIFIED`; never `REVIEW_APPROVED`.

The independent reviewer checks the diff, commands and evidence, reruns required
verification, writes `reviews/<stage-id>/<review-id>.yaml`, and alone advances
`VERIFIED` to `REVIEW_APPROVED` or `REVIEW_REJECTED`.

Evidence YAML must contain stage/implementation/session identity, starting and
ending HEAD, dirty-state preflight, files changed, command argv, exit code,
stdout/stderr artifact digests, tests passed/failed/skipped, decisions, schemas
and migrations changed, risks/blockers, and next proposed action. Evidence may
refer to large content-addressed logs rather than embed them.

Rollback means revert the uncommitted stage diff or create a normal revert of a
stage commit after review. Never rewrite prior stage history. A rollback or
remediation gets new evidence and state history.

## 3. Ordered stage graph

| ID | Title | Prerequisites | Principal output |
|---|---|---|---|
| ORCH-000 | Independent v3 design review | none | Reviewed architecture/plan gate. |
| ORCH-001 | Durable feature-state validator | 000 | Machine-enforced cross-session state transitions. |
| ORCH-002 | Schema registry and CLI v2 envelope | 001 | Version dispatch and stable JSON/errors. |
| ORCH-003 | Legacy readers and migration framework | 002 | Read-only legacy audit and dry-run migration core. |
| ORCH-004 | Execution specification | 003 | Immutable spec/path/agent policy model. |
| ORCH-005 | Attempt records and store | 004 | Base-epoch attempt identity and lifecycle. |
| ORCH-006 | Workflow event/state v2 | 005 | Attempt-scoped history and revised transitions. |
| ORCH-007 | Integrity/outcome and agent-run show | 006 | Structured inspectable run results. |
| ORCH-008 | Verification profiles and finding delta | 007 | Stable findings and deterministic attribution. |
| ORCH-009 | Safe baseline cache | 008 | Complete-key optional evidence cache. |
| ORCH-010 | Candidate record and chain derivation | 006,007 | History-derived candidate continuity. |
| ORCH-011 | Synthetic chain sandbox | 010 | Deterministic chain baseline construction. |
| ORCH-012 | Contribution capture and verification | 011,008 | Contribution-only patch ownership/evidence. |
| ORCH-013 | Prompt/run identity v2 integration | 004,005,012 | Spec/attempt/candidate-bound prompts and runs. |
| ORCH-014 | Aggregate candidate reconstruction | 012 | Base-to-final candidate record/patch. |
| ORCH-015 | Idempotent candidate application | 014,017 | Locked apply journal and recovery. |
| ORCH-016 | Approval v2 and Ed25519 verification | 002 | Canonical single-use approval data/crypto library. |
| ORCH-017 | Isolated approval service | 016 | Protected trust/replay capability boundary. |
| ORCH-018 | Task v2 and dependency validation | 003,004,005 | Authoritative graph rules. |
| ORCH-019 | Governance mutation construction | 018,016 | Isolated complete-document candidate/validation. |
| ORCH-020 | Governance transaction/recovery | 019,017 | Locked atomic apply-and-commit publication. |
| ORCH-021 | Candidate commit, push and receipts | 015,017,020 | Approval-bound terminal publication primitives. |
| ORCH-022 | Decision policy engine | 008,013,018,021 | Complete deterministic action evaluator. |
| ORCH-023 | Orchestrator dry-run process | 022 | Separate resumable read-only controller. |
| ORCH-024 | Prerequisite and attempt supersession | 020,022,023 | Governed prerequisite loop/new epoch. |
| ORCH-025 | Write-capable orchestration and rollout | 017,021,024 | Gated live controller with round/timeout controls. |
| ORCH-026 | Migration/backward-compat integration | 003,020,025 | Real repository migration and mixed-version guards. |
| ORCH-027 | End-to-end safety and release closeout | 000–026 | Fault-injected acceptance and release decision. |

The normative `delivery_order` is stored in `implementation-state.yaml`.
It places ORCH-016 and ORCH-017 before ORCH-015 so approval capability exists
before application/abort. Where a stage lists multiple prerequisites, all must
be `REVIEW_APPROVED`. Parallel implementation is not authorized by this plan;
the next stage is the first non-approved entry in delivery order whose
prerequisites are approved, and the state file exposes only that one.

## 4. Verification tiers

- Tier S (schema/docs): schema validation, focused unit tests, full existing
  suite before review approval.
- Tier C (core state): focused unit/property tests, CLI golden tests, full suite.
- Tier G (Git mutation): Tier C plus disposable-repository integration,
  idempotency and crash/fault-injection tests.
- Tier T (trust): Tier C plus signature vectors, replay/concurrency, Unix
  permission/isolation tests and a documented threat-model review.
- Tier E (end-to-end): all suites in supported runtimes, clean-tree and recovery
  drills, manual approval ceremony and opt-in canary.

Unless a stage explicitly adds more, the full regression command is
`pytest -q`. Commands must be stored as argv in evidence. Tests must use isolated
temporary repositories/data roots and never mutate the real governance files.

## 5. Cross-stage interface freeze points

After review approval of these stages, changing the named interface requires a
plan amendment and migration entry:

- ORCH-002: CLI v2 envelope/error/schema-dispatch contract.
- ORCH-004: execution-spec v1.
- ORCH-005: attempt-record v1.
- ORCH-006: workflow-event v2 transition vocabulary.
- ORCH-008: verification finding/delta vocabulary.
- ORCH-010: candidate chain identity.
- ORCH-016: approval-envelope v2 signed payload.
- ORCH-018: task/dependency v2 projection.
- ORCH-020: governance mutation/journal/receipt v1.
- ORCH-021: application/commit/push receipt and terminal preconditions.

## 6. Migration ordering

ORCH-003 builds only safe inspection/planning/backup machinery. ORCH-026 wires
the final schemas after all have stabilized. No production governance document
is migrated in an earlier stage. Migration IDs are registered in
`migration-registry.yaml`; every migration is dry-run first, backed up, reviewed
and applied only in a dedicated migration session.

## 7. Rollout

1. Unit/integration implementation with orchestration disabled.
2. `decision evaluate` shadow output compared with human decisions.
3. Read-only `orchestratorctl` dry runs and crash/resume exercises.
4. Trusted-local manual compatibility remains available but never enables
   autonomous writes.
5. Deploy isolated `approvald`; pass capability preflight.
6. Crypto-enforced single-repository canary with automatic agents but human
   promotion/commit/push signatures.
7. Fault-injected terminal and prerequisite exercises.
8. Independent ORCH-027 release review decides whether write mode may be enabled.

There is no rollout step that removes human commit/push approval.

## 8. Implementation-ready acceptance

The feature may be called implementation-complete only when every stage through
ORCH-027 is `REVIEW_APPROVED`, all migrations are applied or explicitly not
required, state/evidence validate, repository and governance are clean/valid,
supported-runtime suites pass, recovery drills pass, approval isolation is
proven, and the final reviewer records a release decision. Detail alone is not
completion.

Final reviewer checklist:

- [ ] Every operation is exposed through a specified contract and revalidates
  its preconditions in the engine.
- [ ] Agent work begins only from clean committed HEAD; the only intentional
  dirty period has an exact application journal and blocks agents.
- [ ] Governance documents and execution evidence each have one stated authority.
- [ ] Every workflow, attempt, dependency, publication and feature-stage
  transition has tested preconditions and fail-closed errors.
- [ ] Candidate chain ordering, continuity, aggregate reconstruction,
  exactly-once apply and stale/partial refusal are tested.
- [ ] Prerequisite completion supersedes the parent epoch and restarts plan
  review; old candidates cannot apply.
- [ ] Transaction crash recovery is fault-tested before, during and after commit.
- [ ] Integrity/outcome and every attribution class are independently tested.
- [ ] Crypto-enforced approval isolation, replay, rotation and revocation are
  demonstrated on the deployment host.
- [ ] Legacy reads, dry-run migration, backups, rollback cutoff and mixed-version
  quarantine are demonstrated.
- [ ] Terminal commit/push/receipt/task-complete/dependent-resume order is proven.
- [ ] A fresh session using only repository state can select, execute, evidence
  and hand off exactly one stage without chat memory.
- [ ] No implementation/remediation actor approved its own work.
- [ ] No critical/high risk or unresolved blocker remains and write mode defaults
  disabled until the release decision is committed.
