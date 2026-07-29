# AgentOS Dashboard — Changelog

| Field | Value |
|---|---|
| **Title** | AgentOS Dashboard — Changelog |
| **Purpose** | Append-only log of every approved change to the dashboard documentation set; the audit spine of `MASTER_PLAN.md` §8. |
| **Status** | Draft |
| **Version** | 1.2 |
| **Owner** | Completing agent per stage · verified at review |
| **Dependencies** | None |
| **Related Documents** | `MASTER_PLAN.md` §7–§8 |

## Conventions

Entry ID `CL-YYYYMMDD-##`, newest first. Each entry: documents touched, versions
before/after, authorizing task, approver. Entries are appended, never edited.

## Entries

### CL-20260729-02 — DASH-003 implemented: governance and Markdown parsing

- **Documents:** `DECISIONS.md` (new DD-06, DD-07), `STAGE_REGISTRY.md` §4 (new append-only
  preflight row; the §3 state cell is unchanged at `AUTHORIZED`), and the new report
  `docs/reports/agentos-dashboard/STAGE-03-completion.md`.
- **Versions:** `DECISIONS.md` 1.1 → **1.2**; `STAGE_REGISTRY.md` 5.0 → 5.0 (append-only log
  growth, which §8 does not version).
- **Code delivered (outside this documentation set):** `agentos_dashboard/parsing/**` (tolerant,
  confidence-scored parsers for `docs/PROJECT_STATE.md`, the task queue and its two mirrors,
  `docs/DECISION_LOG.md`, `implementation-state.yaml`, and the handover checksum manifest),
  `agentos_dashboard/services/consistency.py` (the consistency engine v1), and
  `agentos_dashboard/tests/**` (157 tests including a malformed-document fixture corpus under
  `tests/fixtures/malformed/`) — exactly the stage contract's Allowed list. Stdlib + PyYAML
  (already pinned) only; no new dependency.
- **Reason for change:** DASH-003's implementation, recurring the exact OD-D10 branch-vs-runner
  conflict DASH-002 already recorded (no new Open Question needed; OD-D10's "Blocked" line
  already names "every later DASH stage run through the same local runner").
- **Authorizing task:** DASH-003, authorized by the Human Owner 2026-07-29 through
  `scripts/workflow-authorize.sh` (`STAGE_REGISTRY.md` §4).
- **Approver:** pending — the implementation is uncommitted and awaits Human Owner approval.
- **Date:** 2026-07-29.

### CL-20260729-01 — DASH-002 implemented: repository adapters and read-only snapshot

- **Documents:** `DECISIONS.md` (new DD-04, DD-05), `OPEN_QUESTIONS.md` (new OD-D10, OD-D11),
  `STAGE_REGISTRY.md` §4 (new append-only preflight row; the §3 state cell is unchanged at
  `AUTHORIZED`), and the new report
  `docs/reports/agentos-dashboard/STAGE-02-completion.md`.
- **Versions:** `DECISIONS.md` 1.0 → **1.1**; `OPEN_QUESTIONS.md` 1.0 → **1.1**;
  `STAGE_REGISTRY.md` 5.0 → 5.0 (append-only log growth, which §8 does not version).
- **Code delivered (outside this documentation set):** `agentos_dashboard/{__init__.py,
  core/__init__.py, core/paths.py, core/files.py, core/gitread.py, core/snapshot.py}` and
  `agentos_dashboard/tests/**` — exactly the stage contract's Allowed list. Stdlib only.
- **Reason for change:** DASH-002's implementation, and the two governance conflicts it hit,
  which are recorded rather than resolved by the session that found them.
- **Authorizing task:** DASH-002, authorized by the Human Owner 2026-07-29 through
  `scripts/workflow-authorize.sh` (`STAGE_REGISTRY.md` §4).
- **Approver:** pending — the implementation is uncommitted and awaits Human Owner approval.
- **Date:** 2026-07-29.

### CL-20260724-06 — `SUPERSEDED` task-status policy (OD-8) mirrored from the AUTO program

- **Documents:** `STAGE_REGISTRY.md` §1 (state-mapping sentence) and rule 9 (Superseding).
- **Versions:** `STAGE_REGISTRY.md` 4.0 → **5.0**.
- **Reason for change:** Human Owner policy decision OD-8 (`OPEN_QUESTIONS.md`, resolved
  2026-07-24): `SUPERSEDED` maps to task status `Done` — administratively closed, never
  successful completion, distinct from `COMPLETE` in `docs/TASK_QUEUE.md` prose every time; legal
  source states `AUTHORIZED`/`BLOCKED`/`IN_PROGRESS`/`SELF_REVIEW`/`REVIEW`/`APPROVAL`; never a
  fourth task status; never an automatic successor authorization. Mirrored here from
  `docs/workflow-automation/STAGE_REGISTRY.md` rule 9, so the two programs' registries do not
  drift on this shared policy, per this registry's own existing substantive-equivalence promise
  (§1).
- **Authorizing task:** none required — a consistency mirror of an explicit Human Owner policy
  decision already fully recorded elsewhere, not a new governance decision made here.
- **Approval basis already recorded elsewhere:** `docs/DECISION_LOG.md`, 2026-07-24 entry "Human
  Owner policy decisions recorded and applied: OD-8 ... and OD-9 ...", quoting the Human Owner's
  OD-8 approval verbatim.
- **Date:** 2026-07-24.

### CL-20260724-05 — Resume preflight synchronized with the shared AUTO lifecycle

- **Documents:** `STAGE_REGISTRY.md` §1/§2 and `stage-prompts/README.md`.
- **Versions:** `STAGE_REGISTRY.md` 3.0 → **4.0**;
  `stage-prompts/README.md` 1.2 → **1.3**.
- **Reason for change:** the registry already promises that AUTO and DASH share the same
  lifecycle/control rules except for Dashboard's explicitly named Rollback rule, but AUTO's
  zero-transition Resume Preflight had not been mirrored after it was added. Added Dashboard
  rule 20 and split the SSP into initial-start/resume sections. A passing or failing resume
  leaves registry state unchanged; no state, transition, authorization rule, or task-status
  semantic was added. Updated the explanatory rule-number crosswalk accordingly.
- **Authorizing task:** none required — internal synchronization with an existing normative
  equivalence promise, not a new governance policy.
- **Approval basis already recorded elsewhere:** `docs/DECISION_LOG.md`, 2026-07-24 "twelfth
  pass" entry and the operator's explicit instruction to apply Classification Findings 1–2.
- **Date:** 2026-07-24.

### CL-20260724-04 — Stage-prompts SSP formatter documentation resynchronized

- **Documents:** `stage-prompts/README.md` (pre-commit hook description and validation-command
  list).
- **Versions:** `stage-prompts/README.md` 1.1 → **1.2**.
- **Reason for change:** the SSP's pre-commit warning still named `` `ruff --fix`, `ruff-format` ``
  as the auto-fixing hooks, stale since `ruff-format` was removed from `.pre-commit-config.yaml`
  entirely (`docs/DECISION_LOG.md`, 2026-07-24 "seventh pass" entry) — Black is the sole
  formatter, `ruff-check` is lint/import-sort only. Reworded to name the actual current hooks in
  actual order (`ruff-check --fix`, `black`, `mypy`) and added `` `ruff format --check .` `` to
  the recorded validation-command list. Repository policy is unchanged; only documentation was
  synchronized with the already-implemented toolchain.
- **Authorizing task:** none required — a factual documentation-synchronization fix found on
  independent governance audit, not a new governance decision.
- **Approval basis already recorded elsewhere:** `docs/DECISION_LOG.md`, 2026-07-24 "tenth pass"
  entry (this change) and "seventh pass" entry (the underlying `ruff-format` removal this
  documentation now correctly reflects).
- **Date:** 2026-07-24.

### CL-20260724-03 — Stage registry: closeout rule gap fixed, rule-equivalence claim narrowed

- **Documents:** `STAGE_REGISTRY.md` §2 rule 17 (Closeout) and §1 (rule-equivalence claim).
- **Versions:** `STAGE_REGISTRY.md` 2.0 → **3.0**.
- **Reason for change:** rule-by-rule audit against `docs/workflow-automation/STAGE_REGISTRY.md`
  found this registry's rule 17 was missing the entire `git`-check closeout-tolerance clause the
  AUTO program's equivalent rule states — fixed by adding the matching clause. The §1 claim that
  every control rule is "identical in substance" to AUTO's was overstated; narrowed to a precise
  list of which rules are shared and which (rule 14, Rollback) is intentionally
  program-specific.
- **Authorizing task:** none required — a factual rule-consistency fix found on independent
  governance audit, not a new governance decision.
- **Approval basis already recorded elsewhere:** `docs/DECISION_LOG.md`, 2026-07-24 "seventh
  pass" entry ("Dashboard/AUTO equivalence claim corrected...").
- **Date:** 2026-07-24.

### CL-20260724-02 — Stage registry and SSP: `BLOCKED` lifecycle and execution-precondition rules mirrored from the AUTO program

- **Documents:** `STAGE_REGISTRY.md` §1 (`BLOCKED` mapping), §2 (rules 1, 8, 17–19, new),
  `stage-prompts/README.md` (SSP resume-from-`BLOCKED` clarification).
- **Versions:** `STAGE_REGISTRY.md` 1.0 → 2.0 (recorded in `CL-20260724-01` below);
  `stage-prompts/README.md` 1.0 → **1.1** (not previously recorded in this changelog — this
  entry closes that gap).
- **Reason for change:** mirrored, into the DASH program's registry and SSP, the same
  authorization-vs-execution-precondition rules, the `BLOCKED` state's legal transitions
  (`BLOCKED → AUTHORIZED → IN_PROGRESS` or `BLOCKED → SUPERSEDED`), the completed-stage-amendment
  distinction (rule 8), and the Governance Correction Record mechanism (rule 19, adopted by
  reference), all established for the AUTO program in the same work session, so the two
  programs' registries do not drift on shared mechanisms.
- **Authorizing task:** none required — a consistency mirror of already-established rules, not a
  new governance decision.
- **Approval basis already recorded elsewhere:** `docs/DECISION_LOG.md`, 2026-07-24 "fifth pass"
  entry ("every registry audited repository-wide").
- **Date:** 2026-07-24.

### CL-20260724-01 — DASH-001 completion recorded; stage registry synchronized

- **Documents:** `STAGE_REGISTRY.md` §3 (DASH-001 row: `IN_PROGRESS` → `COMPLETE`, its actual
  state since 2026-07-23), this changelog (this entry).
- **Versions:** `STAGE_REGISTRY.md` 1.0 → 2.0 (also carries the same-day Finding 1–4 governance
  corrections mirrored from `docs/workflow-automation/STAGE_REGISTRY.md`).
- **Authorizing task:** none required — this is a factual synchronization of records with an
  already-approved, already-merged completion (PR #1, `5f82996`), found stale on independent
  governance audit; not a new governance decision. The two entries below still correctly read
  "pending Human Owner acceptance at DASH-001 completion" as of when they were written
  (2026-07-23, before that acceptance had been recorded here) and are left untouched per this
  file's own append-only convention; DASH-001's actual completion and closeout is recorded in
  `docs/DECISION_LOG.md` (2026-07-23 entry) and `docs/TASK_QUEUE.md`.
- **Approver:** Human Owner (via the 2026-07-23 closeout decision recorded in
  `docs/DECISION_LOG.md`, not a new approval act).

### CL-20260723-02 — DASH-001 recovery adaptation to `ai-workflow-engine`

- **Documents:** entire set (MASTER_PLAN, ARCHITECTURE, PRODUCT_SPEC, SECURITY_MODEL,
  SOURCE_OF_TRUTH, DATA_MODEL, API_SPEC, UI_SPEC, MVP_SCOPE, STAGE_REGISTRY,
  stage-prompts/README + DASH-001..010, STAGE_REPORT_TEMPLATE, TEST_STRATEGY, DECISIONS,
  OPEN_QUESTIONS, CHANGELOG) rewritten in place to remove every assumption inherited from the
  mis-targeted `amozesh_konkur` execution and bind the set to `ai-workflow-engine`'s actual
  governance (see `DECISIONS.md` DD-03 for the full correction list).
- **Versions:** 1.0 (Draft) → 1.0 (Draft); the set had never been approved or committed, so
  this is a pre-approval draft correction, not a MAJOR revision.
- **Authorizing task:** DASH-001 recovery, authorized by the Human Owner 2026-07-23
  ("I authorize recovery and correct execution of DASH-001 in the ai-workflow-engine
  repository").
- **Approver:** pending Human Owner acceptance at DASH-001 completion.

### CL-20260723-01 — Initial draft documentation set

- **Documents:** MASTER_PLAN, ARCHITECTURE, PRODUCT_SPEC, SECURITY_MODEL, SOURCE_OF_TRUTH,
  DATA_MODEL, API_SPEC, UI_SPEC, MVP_SCOPE, STAGE_REGISTRY, stage-prompts/README +
  DASH-001..010, STAGE_REPORT_TEMPLATE, TEST_STRATEGY, DECISIONS, OPEN_QUESTIONS, CHANGELOG —
  all created at version 1.0, status Draft. (This creation was performed in the wrong
  repository and its bytes were carried here only as candidate material; see CL-20260723-02.)
- **Versions:** — → 1.0 (all).
- **Authorizing task:** DASH-001, authorized by the Human Owner 2026-07-23
  ("I authorize DASH-001"); OD-D1 resolved.
- **Approver:** pending Human Owner acceptance at DASH-001 completion.

## Decision References
DD-01, DD-02, DD-03.

## Open Questions
None.

## Future Revisions
Append-only.

## 2026-07-29 — DASH-002 authorized

The Human Owner authorized DASH-002 through the two-confirmation local gate. The stage is
`AUTHORIZED`; implementation, approval, push, and merge remain separate.

## 2026-07-29 — DASH-002 closed

The Human Owner approved and closed DASH-002 through the automatic task-closeout gate
(`scripts/workflow-approve.sh`, GOV-AUTO-03). Registry state `COMPLETE`; task status `Done`.

## 2026-07-29 — DASH-003 authorized

The Human Owner authorized DASH-003 through the two-confirmation local gate. The stage is
`AUTHORIZED`; implementation, approval, push, and merge remain separate.

## 2026-07-29 — DASH-003 closed

The Human Owner approved and closed DASH-003 through the automatic task-closeout gate
(`scripts/workflow-approve.sh`, GOV-AUTO-03). Registry state `COMPLETE`; task status `Done`.
