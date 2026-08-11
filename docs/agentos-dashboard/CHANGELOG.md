# AgentOS Dashboard — Changelog

| Field | Value |
|---|---|
| **Title** | AgentOS Dashboard — Changelog |
| **Purpose** | Append-only log of every approved change to the dashboard documentation set; the audit spine of `MASTER_PLAN.md` §8. |
| **Status** | Draft |
| **Version** | 2.3 |
| **Owner** | Completing agent per stage · verified at review |
| **Dependencies** | None |
| **Related Documents** | `MASTER_PLAN.md` §7–§8 |

## Conventions

Entry ID `CL-YYYYMMDD-##`, newest first. Each entry: documents touched, versions
before/after, authorizing task, approver. Entries are appended, never edited.

## Entries

### CL-20260811-02 — DASH-010 final independent review corrections

- **Documents:** `OPERATIONS.md` (accurate lock smoke check, explicit-refresh staleness behavior,
  SQLite troubleshooting, and a checksum procedure that excludes the manifest's self-row);
  `MVP_SCOPE.md` §5 (recommendation remains explicitly pending Human Owner acceptance);
  `STAGE_REGISTRY.md` §4, `docs/TASK_QUEUE.md`, and
  `docs/reports/agentos-dashboard/STAGE-10-completion.md` (reviewed evidence superseding the
  implementation-session counts and sampled DR-121/DR-122 claims).
- **Versions:** this file 2.2 → **2.3**. `OPERATIONS.md` remains 1.0 because the corrections make
  its first unapproved draft accurate rather than changing an approved operating contract.
- **Code corrected (inside DASH-010's allowed `agentos_dashboard/**` surface):** `--check` now
  acquires/releases the real execution lock and reports lock, filesystem, malformed/incompatible
  SQLite, repository, and configuration failures without tracebacks; snapshot caching now retains
  stale state until explicit refresh so DR-121 is observable; Overview, Board, Stages,
  Orchestration, Handover, and Consistency now deliver the missing DR-122 provenance/raw fallback;
  Overview now integrates required summary, handover, validation-gate, and audit-event state; and
  E2E/golden/regression coverage now tests semantic content across all delivered pages without
  coupling to the transient identity of the live `Current` task.
- **Reason for change:** the Human Owner requested exactly one final bounded independent
  reviewer/corrector pass before DASH-010 approval and MVP closure.
- **Authorizing task:** DASH-010; every correction is inside its explicit final integration,
  E2E/golden, DR-121/DR-122, operations, and local-readiness scope.
- **Approver:** pending — review is complete, the tree is uncommitted, and no Human Owner
  acceptance is claimed.

### CL-20260811-01 — DASH-010 implemented: integration testing, documentation, and release readiness

- **Documents:** new `OPERATIONS.md` (start/stop, `AWED_*` configuration, the manual handover
  manifest-refresh procedure per OD-D6, `dashboard.db` backup/disposal, troubleshooting, and the
  restated `SECURITY_MODEL.md` §5 prohibited-operations list); `MVP_SCOPE.md` §5 (Closure Record
  populated — a recommendation to the Human Owner, not a self-declared acceptance);
  `STAGE_REGISTRY.md` §3 (state cell `AUTHORIZED` → `IN_PROGRESS`) and §4 (two new append-only
  rows: initial-start preflight and implementation-complete); `docs/TASK_QUEUE.md`; and the new
  report `docs/reports/agentos-dashboard/STAGE-10-completion.md`.
- **Versions:** `OPERATIONS.md` new at **1.0**; `MVP_SCOPE.md` 1.0 → 1.0 (its §5 placeholder
  populated, not a scope change — §8 reserves version bumps for scope changes only);
  `STAGE_REGISTRY.md` 5.2 → 5.2 (append-only log growth and a state-cell update, neither of which
  §8 versions); this file 2.1 → **2.2**.
- **Code delivered (outside this documentation set):** `agentos_dashboard/services/settings_view.py`,
  `web/templates/settings.html`, and the `/settings` route (PG-12 Settings/About — read-only,
  reusing existing settings/lock data, per PLAN-001/`DECISIONS.md` DD-16's explicit bound: no new
  adapter, no new API endpoint, zero mutation affordance); an enhanced `python -m agentos_dashboard
  --check` that now builds the repository snapshot and opens one local-database connection;
  `agentos_dashboard/tests/e2e/` (TC-16 full page-set walks against a constructed fixture
  repository and, read-only, against this real repository; TC-10 byte-exact golden-file snapshots
  of the Board and Handover pages; the DR-121/DR-122 final cross-page verification suite) — the
  stage contract's Allowed list, no new dependency.
- **Reason for change:** DASH-010's implementation — the program's final stage.
- **Authorizing task:** DASH-010, authorized by the Human Owner 2026-08-11 through
  `scripts/workflow-authorize.sh` (`STAGE_REGISTRY.md` §4).
- **Approver:** pending — the implementation is uncommitted and awaits Human Owner approval.
- **Date:** 2026-08-11.

### CL-20260810-05 — DASH-009 mandatory independent security review corrections

- **Documents:** `SECURITY_MODEL.md` §7 (final reviewed SC-01..SC-36 evidence), `DECISIONS.md`
  (DD-18/DD-19), `OPEN_QUESTIONS.md` (OD-D13 scope clarified), `STAGE_REGISTRY.md` §4,
  `docs/TASK_QUEUE.md`, and `docs/reports/agentos-dashboard/STAGE-09-completion.md`.
- **Versions:** `SECURITY_MODEL.md` 1.1 → **1.2**; `DECISIONS.md` 1.9 → **2.0**;
  `OPEN_QUESTIONS.md` 1.5 → **1.6**; this file 2.0 → **2.1**; registry remains version 5.2
  because its append-only log grew without a control-rule/state-model change.
- **Corrections:** the bounded fresh-session reviewer found and corrected four substantive gaps:
  incomplete recognizable-secret redaction across persistence/audit/display/error boundaries;
  no whole-request body cap before framework parsing; a stale-PID lockfile read/unlink race that
  could permit two writers; and audit pagination that bounded output only after loading all DB
  rows. Every correction has adversarial regression coverage.
- **Evidence:** final Dashboard result 707 passed/1 known baseline governance-fixture failure;
  clean archived authorization HEAD 623 passed/the identical failure; engine 2991 passed/2
  deselected; workflow 2085 passed/32 deselected. Full commands and remaining quality/governance
  results are recorded in the completion report.
- **Scope:** only `agentos_dashboard/**` and DASH-009 evidence/governance documents changed. No
  dependency, repository mutation capability, DASH-010 code, or Git operation was added.
- **Reason for change:** the mandatory one-pass independent security review required by the
  DASH-009 stage contract before Human Owner approval.
- **Authorizing task:** DASH-009, already authorized and still `IN_PROGRESS`.
- **Approver:** pending — review completed; working tree remains uncommitted for Human Owner.
- **Date:** 2026-08-10.

### CL-20260810-04 — DASH-009 implemented: security hardening and failure handling

- **Documents:** `SECURITY_MODEL.md` §7 (Reconciliation Log populated for every SC-01..SC-36
  row), `DECISIONS.md` (new `DD-17`), `OPEN_QUESTIONS.md` (new `OD-D13`, resolved/deferred),
  `STAGE_REGISTRY.md` §3 (state cell `AUTHORIZED` → `IN_PROGRESS`) and §4 (two new append-only
  log rows), and the new report `docs/reports/agentos-dashboard/STAGE-09-completion.md`.
- **Versions:** `SECURITY_MODEL.md` 1.0 → **1.1**; `DECISIONS.md` 1.8 → **1.9**;
  `OPEN_QUESTIONS.md` 1.4 → **1.5**; this file 1.9 → **2.0**; `STAGE_REGISTRY.md` 5.1 → **5.2**.
- **Implementation:** the adversarial security test corpus and failure-handling hardening the
  stage contract requires. Three real defects were found and fixed: (1) SC-09 (secret-shaped-
  substring redaction) did not exist anywhere in the codebase — new `agentos_dashboard/core/
  redact.py`, wired into `services/notes.py`/`services/runs.py` (redact before the idempotency
  hash is computed, so a pasted credential never reaches `dashboard.db`) and `services/
  governance.py`/`services/handover.py` (redact the display-only copy of repository text,
  deliberately not the shared `core.files.read_text` primitive other services rely on for
  byte-exact comparison — `DD-17`); (2) `core.files.read_head_tail` (SC-35) existed but was
  called from nowhere outside its own unit test — now wired into `services/governance.py::
  render_document`, surfacing a redacted tail excerpt whenever a document is truncated; (3)
  Starlette's `ServerErrorMiddleware` always wraps outside `SecurityMiddleware`, so an unhandled
  exception's response never received CSP/no-sniff/no-store headers or the CSRF cookie —
  `apply_security_headers`/`ensure_csrf_cookie` are now module-level functions in `api/
  security.py`, applied both by the middleware and by `main.py`'s `Exception` handler, which now
  also renders a themed `web/templates/error.html` page for browser-facing routes instead of a
  raw JSON envelope. A related test-infrastructure gap was fixed in `agentos_dashboard/tests/
  _asgi_client.py` so the dependency-free ASGI test client tolerates Starlette's documented
  send-then-re-raise behavior on an unhandled exception, matching a real ASGI server. Also added:
  a genuine cross-process lockfile-contention test (SC-24) and two parser empty-document
  degradation tests (SC-34).
- **Scope:** all changes remain inside `agentos_dashboard/**` and the stage's named documentation
  paths. No file under `src/`, `tests/`, `scripts/`, `agentos_workflow/**`, `pyproject.toml`, or
  `docs/implementation/orchestration/**` was touched.
- **Reason for change:** DASH-009's mandatory security-hardening and failure-handling pass, with
  a mandatory independent security review still required before Human Owner approval.
- **Authorizing task:** DASH-009, authorized 2026-08-10.
- **Approver:** pending — implementation is uncommitted, awaiting the mandatory independent
  security review and then Human Owner approval.
- **Date:** 2026-08-10.

### CL-20260810-03 — DASH-008 final machine-review corrections

- **Documents:** this append-only entry and
  `docs/reports/agentos-dashboard/STAGE-08-completion.md`.
- **Versions:** this file 1.8 → **1.9**; the completion report remains unversioned and was
  corrected in place before approval.
- **Corrections:** fail-closed exact schema validation and SQL immutability triggers; conflict-
  safe, restart-safe, DB-unique idempotency; an explicit DB/JSONL reconciliation model with
  rollback and divergence tests; bounded stable evidence hashing and symlink refusal; strict API
  validation and typed conflicts; local-only approval semantics and transient-Git handling; and
  correct bounded audit/note filtering; and a whole-HTTP-path EP-18 proof that makes no Git/
  subprocess call. Focused regressions were added for each correction.
- **Scope:** all corrections remain inside DASH-008's authorized storage, service, API, page,
  test, and closeout-document surfaces. `services/evidence.py` and `api/evidence.py` are recorded
  as the necessary implied subdivision of expressly authorized EP-17, with no new entity,
  persistence source, adapter, or capability. No DASH-009 implementation was added.
- **Reason for change:** one bounded independent final review before Human Owner approval.
- **Authorizing task:** DASH-008, already authorized and still `IN_PROGRESS`.
- **Approver:** pending — the corrected implementation remains uncommitted and awaits Human
  Owner approval.
- **Date:** 2026-08-10.

### CL-20260810-02 — DASH-008 implemented: run records, evidence, and audit timeline

- **Documents:** `STAGE_REGISTRY.md` §3 (state cell `AUTHORIZED` → `IN_PROGRESS`) and §4 (new
  append-only preflight row), and the new report
  `docs/reports/agentos-dashboard/STAGE-08-completion.md`.
- **Versions:** `STAGE_REGISTRY.md` 5.1 → 5.1 (append-only log growth and a state-cell update,
  neither of which §8 versions); this file 1.7 → **1.8**.
- **Code delivered (outside this documentation set):** `agentos_dashboard/storage/{__init__.py,
  db.py}` (stdlib `sqlite3` `dashboard.db`, `PRAGMA user_version = 1`, foreign keys on, the eight
  `DATA_MODEL.md` §3 tables, and the JSONL audit-log mirror path); `agentos_dashboard/services/
  {runs.py, approvals.py, findings.py, notes.py, audit.py, evidence.py, orchestration.py}` (EN-11
  `StageRun`/EN-16 `ValidationRun` with live report-path verification, EN-14 `Approval` drafts with
  automatic Git-reconciliation-divergence findings, EN-15 `Finding` and EN-29 `UserNote` drafts,
  the append-only EN-26 `AuditEvent` log and its merged local+repository timeline, the EP-17
  verified-vs-claimed evidence aggregate, and the read-only EP-18 ORCH feature-state view);
  `agentos_dashboard/api/{runs.py, drafts.py, audit.py, evidence.py, orchestration.py}` (EP-15,
  EP-16, EP-17, EP-18, EP-22, EP-23, wired into `api/routes.py`); `agentos_dashboard/web/templates/
  {runs.html, run_detail.html, evidence.html, audit.html}` (PG-05/PG-06/PG-10) plus a nav update to
  `base.html`/`app.js`; and `agentos_dashboard/tests/**` (79 new tests, including the append-only
  source-scan proof, the `dashboard.db`-deletion-safety proof, and EP-18's zero-write/zero-Git/
  zero-subprocess negative proofs). `.gitignore` gained the narrowest rule covering the new
  `data/agentos_dashboard/` runtime directory (allowed modification per the stage contract). No
  new dependency; stdlib `sqlite3` only, as `DATA_MODEL.md` §3 requires.
- **Scope note:** `services/evidence.py` and `api/evidence.py` are not literally named in the
  stage contract's Allowed-files prose ("run/approval/finding/note/audit/orchestration
  services"), but EP-17 (`GET /evidence/{ref}`) is an explicitly Allowed route and needs a
  data-shaping module; the module is a thin aggregate entirely over `services.runs`'s
  already-in-scope `StageRunView`/`ValidationEntry` (no new persistence, no new adapter). Recorded
  here rather than silently included. `generated_prompts` and `consistency_history` tables exist
  in the schema (per `DATA_MODEL.md` §3's full table list) but have no writer yet:
  `services/prompts.py` and `services/consistency.py` are DASH-007/DASH-006 files outside this
  stage's Allowed list, so migrating either onto `dashboard.db` is left to a future stage.
- **Reason for change:** DASH-008's implementation.
- **Authorizing task:** DASH-008, authorized by the Human Owner 2026-08-10 through
  `scripts/workflow-authorize.sh` (`STAGE_REGISTRY.md` §4).
- **Approver:** pending — the implementation is uncommitted and awaits Human Owner approval.
- **Date:** 2026-08-10.

### CL-20260810-01 — PLAN-001: requirement-to-stage ownership correction (governance-only)

- **Documents:** `STAGE_REGISTRY.md` §5 (rewritten as an explicit per-requirement table; prior
  prose-range form retained in a collapsed audit-trail block) and §6; `DECISIONS.md` (new DD-16);
  `stage-prompts/DASH-007.md`, `DASH-008.md`, `DASH-010.md` (each amended and bumped to
  documentation-only `1.1`); `docs/DECISION_LOG.md` (new 2026-08-10 entry); `docs/TASK_QUEUE.md`,
  `docs/current_task.md`, `docs/remaining_tasks.md`, `docs/PROJECT_STATE.md`, `docs/CHANGELOG.md`
  (PLAN-001 task record and mirrors; the DASH-007/DASH-008/DASH-010 queue summaries are
  reconciled with their amended contracts).
- **Versions:** `STAGE_REGISTRY.md` 5.0 → **5.1**; `DECISIONS.md` 1.7 → **1.8**; this file 1.6 →
  **1.7**; `stage-prompts/DASH-007.md` 1.0 → **1.1**; `stage-prompts/DASH-008.md` 1.0 → **1.1**;
  `stage-prompts/DASH-010.md` 1.0 → **1.1**.
- **Authorizing task:** PLAN-001 — Close dashboard requirement-to-stage coverage gaps. Human
  Owner: "PLAN-001 is authorized as a governance/documentation-only correction to close Dashboard
  MVP requirement-to-stage ownership gaps." Explicitly does **not** authorize DASH-007
  implementation.
- **Correction, in one line each:** DR-090/DR-091/EP-07/EP-08/PG-08 → DASH-007 (new: a bounded
  read-only Governance browser/search surface); DR-120 → DASH-006 sole owner (confirmed, already
  correct); DR-121/DR-122 → DASH-010 final cross-page delivery/evidence closure (new); EP-18 →
  DASH-008, made an explicit Build/Acceptance/evidence responsibility rather than a bare allowlist
  mention; PG-12 → DASH-010 (new: a bounded read-only Settings/About surface, explicitly excluding
  editable config, preferences, governance editing, repository switching, agent/provider config,
  secrets, and any authoritative write). DASH-003 confirmed a foundation-only contributor for
  DR-120..122, never their final normative owner. No DASH-011 created; no MVP requirement
  deferred; sequence DASH-007 → DASH-008 → DASH-009 → DASH-010 unchanged.
- **Code delivered:** none. This is a contract-amendment-only correction — no file under `src/`,
  `tests/`, `agentos_workflow/`, or `agentos_dashboard/` (runtime) changed, and no code for any of
  the amended clauses (Governance browser/search, EP-18 evidence, PG-12, DR-121/122 final
  verification) was written. DASH-007 remains `Planned`/`NOT_STARTED` and unauthorized; this
  closure does not begin, authorize, or start DASH-007.
- **Approver:** Human Owner (authorization recorded above; commit/closeout left for separate
  Human Owner review per this session's git-safety bound).

### CL-20260809-01 — DASH-006 implemented: Git, upstream, handover, and consistency views

- **Documents:** `DECISIONS.md` (new DD-14), `STAGE_REGISTRY.md` §3 (state cell `AUTHORIZED` →
  `IN_PROGRESS`) and §4 (new append-only preflight row), and the new report
  `docs/reports/agentos-dashboard/STAGE-06-completion.md`.
- **Versions:** `DECISIONS.md` 1.5 → **1.6**; `STAGE_REGISTRY.md` 5.0 → 5.0 (append-only log
  growth and a state-cell update, neither of which §8 versions).
- **Code delivered (outside this documentation set):** `agentos_dashboard/services/{git.py,
  handover.py}` (the Git page's status/commits/branches/tags/upstream-check aggregate, TR-07
  commit-badge resolution, DR-082 PR references, and the handover viewer's checksum
  reconciliation and staleness detection), `agentos_dashboard/api/{git.py, handover.py,
  consistency.py, acknowledgments.py}` (EP-09..EP-12, wired into `api/routes.py`, including the
  local acknowledgment-note action), `agentos_dashboard/web/templates/{git.html, handover.html,
  consistency.html}` (PG-07/PG-09/PG-11) plus a nav update to `base.html`/`style.css`/`app.js`,
  and `agentos_dashboard/tests/**` (62 new tests) — the stage contract's Allowed list, plus one
  narrow, justified extension to `core/gitread.py` (`read_merged_branch_names`, DD-14) — no new
  dependency.
- **Reason for change:** DASH-006's implementation.
- **Authorizing task:** DASH-006, authorized by the Human Owner 2026-08-09 through
  `scripts/workflow-authorize.sh` (`STAGE_REGISTRY.md` §4).
- **Approver:** pending — the implementation is uncommitted and awaits Human Owner approval.
- **Date:** 2026-08-09.

### CL-20260808-01 — DASH-005 implemented: workflow board and task detail

- **Documents:** `DECISIONS.md` (new DD-12, DD-13), `OPEN_QUESTIONS.md` (new OD-D12, Open),
  `STAGE_REGISTRY.md` §3 (state cell `AUTHORIZED` → `IN_PROGRESS`) and §4 (new append-only
  preflight row), and the new report `docs/reports/agentos-dashboard/STAGE-05-completion.md`.
- **Versions:** `DECISIONS.md` 1.4 → **1.5**; `OPEN_QUESTIONS.md` 1.2 → **1.3**;
  `STAGE_REGISTRY.md` 5.0 → 5.0 (append-only log growth and a state-cell update, neither of which
  §8 versions).
- **Code delivered (outside this documentation set):** `agentos_dashboard/services/{workflow.py,
  board.py, tasks.py, _prose.py}` (the coded engine workflow-stage mirror and queue-status
  transitions, DR-020/DR-021's board data, and DR-030..033's task detail), `agentos_dashboard/api/
  board.py` (EP-04/EP-05/EP-06, wired into `api/routes.py`), `agentos_dashboard/web/templates/
  {board.html, _board_card.html, task_detail.html}` (PG-02/PG-03) plus a nav update to
  `base.html`/`style.css`, and `agentos_dashboard/tests/**` (72 new tests) — exactly the stage
  contract's Allowed list. One narrow, justified refinement to an existing DASH-002 test
  (`test_gitread.py::test_no_mutating_git_verb_in_package_source`, DD-13) — no new dependency.
- **Reason for change:** DASH-005's implementation. Against the real repository: GOV-1 and T-501
  render as `Done`; T-401's two-round plan review renders as lifecycle history; DASH-001 renders
  in its actual `Done` state.
- **Authorizing task:** DASH-005, authorized by the Human Owner 2026-08-08 through
  `scripts/workflow-authorize.sh` (`STAGE_REGISTRY.md` §4).
- **Approver:** pending — the implementation is uncommitted and awaits Human Owner approval.
- **Date:** 2026-08-08.

### CL-20260730-01 — DASH-004 implemented: local backend and dashboard shell

- **Documents:** `DECISIONS.md` (new DD-10, DD-11), `STAGE_REGISTRY.md` §3 (state cell
  `AUTHORIZED` → `IN_PROGRESS`) and §4 (new append-only preflight row), and the new report
  `docs/reports/agentos-dashboard/STAGE-04-completion.md`.
- **Versions:** `DECISIONS.md` 1.3 → **1.4**; `STAGE_REGISTRY.md` 5.0 → 5.0 (append-only log
  growth and a state-cell update, neither of which §8 versions).
- **Code delivered (outside this documentation set):** `agentos_dashboard/settings.py`
  (`AWED_`-prefixed, loopback-only Pydantic settings), `agentos_dashboard/main.py` (the
  `create_app()` factory), `agentos_dashboard/__main__.py` (the startup entry point, PID
  lockfile, `--check` smoke mode), `agentos_dashboard/api/**` (envelope, typed error catalogue,
  the Host-allowlist/CSRF/CSP security middleware, the snapshot cache, the DR-010..013 Overview
  aggregate, and EP-01/EP-02/EP-03/EP-20), `agentos_dashboard/web/**` (the base layout and PG-01
  Overview page, self-hosted CSS/JS), and `agentos_dashboard/tests/**` (71 new tests, including a
  dependency-free ASGI test client, `_asgi_client.py`) — exactly the stage contract's Allowed
  list. Dependencies: exactly the optional `dashboard` group OD-D9 already declared (`fastapi`,
  `jinja2`, `uvicorn`); no new dependency was added.
- **Reason for change:** DASH-004's implementation. This is the first DASH stage run entirely on
  its registered branch (`feature/dash-004-dashboard-shell`, prepared automatically by
  GOV-AUTO-04) without recurring OD-D10.
- **Authorizing task:** DASH-004, authorized by the Human Owner 2026-07-30 through
  `scripts/workflow-authorize.sh` (`STAGE_REGISTRY.md` §4).
- **Approver:** pending — the implementation is uncommitted and awaits Human Owner approval.
- **Date:** 2026-07-30.

### CL-20260729-03 — OD-D9 resolved: FastAPI + Uvicorn + Jinja2 in an optional `dashboard` group

- **Documents:** `OPEN_QUESTIONS.md` (OD-D9 moved Open → Resolved with the full disposition;
  the Open section is now empty), `DECISIONS.md` (new DD-09), `ARCHITECTURE.md` (§1 constraints,
  §6 Frontend/Backend rows, §8 rejected options, §9, §10), `MASTER_PLAN.md` (§3
  minimal-dependency posture, §11 register summary), `MVP_SCOPE.md` §7, `PRODUCT_SPEC.md` §6,
  `API_SPEC.md` §7, `UI_SPEC.md` §6, `SECURITY_MODEL.md` §9, `STAGE_REGISTRY.md` §5 and §7
  (factual status updates only — no control rule, state, or registry row changed), and this
  changelog.
- **Versions:** `OPEN_QUESTIONS.md` 1.1 → **1.2**; `DECISIONS.md` 1.2 → **1.3**;
  `ARCHITECTURE.md` 1.0 → **1.1**; this changelog 1.2 → **1.3**. `STAGE_REGISTRY.md` 5.0 → 5.0
  (§8 versions control-rule changes; this was neither).
- **Change outside this documentation set:** `pyproject.toml` gains one new optional dependency
  group, `dashboard = ["fastapi>=0.111,<1", "jinja2>=3.1,<4", "uvicorn>=0.30,<1"]`.
  `[project].dependencies`, the `dev` extra, wheel packaging, `testpaths`, and every lint/type
  setting are unchanged, so the default `ai-workflow-engine` install still carries no
  HTTP-serving dependency. Nothing was installed and no lockfile exists to update. Repository
  records: `docs/TASK_QUEUE.md`, `docs/remaining_tasks.md`, `docs/PROJECT_STATE.md`,
  `docs/DECISION_LOG.md`, `docs/CHANGELOG.md`, and the handover pair.
- **Reason for change:** the Human Owner's OD-D9 decision. Stdlib `http.server` is explicitly
  rejected as the primary implementation; loopback-only binding is unchanged, and remote
  exposure, authentication, TLS, and production deployment remain later-stage concerns.
- **Effect on DASH-004:** no longer blocked by OD-D9 as of this commit; the dependency
  declaration its Allowed list defers to is already performed, so it needs no `pyproject.toml`
  edit of its own. **DASH-004 remains `Planned` and unauthorized** — this decision authorizes
  no stage and moves no task to `Current`.
- **Authorizing task:** none — a Human Owner governance/architecture decision recorded directly,
  not stage work. No task is `Current`.
- **Approver:** Human Owner (the OD-D9 decision itself, 2026-07-29).
- **Date:** 2026-07-29.

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
DD-01, DD-02, DD-03, DD-09, DD-12, DD-13.

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

## 2026-07-30 — DASH-004 authorized

The Human Owner authorized DASH-004 through the two-confirmation local gate. The stage is
`AUTHORIZED`; implementation, approval, push, and merge remain separate.

## 2026-07-30 — DASH-004 implemented

Implemented and validated on the registered branch `feature/dash-004-dashboard-shell`,
uncommitted, stopped for Human Owner approval. Registry state `AUTHORIZED` → `IN_PROGRESS`. See
`CL-20260730-01` above and `docs/reports/agentos-dashboard/STAGE-04-completion.md`.

## 2026-07-30 — DASH-004 closed

The Human Owner approved and closed DASH-004 through the automatic task-closeout gate
(`scripts/workflow-approve.sh`, GOV-AUTO-03). Registry state `COMPLETE`; task status `Done`.

## 2026-08-08 — DASH-005 authorized

The Human Owner authorized DASH-005 through the two-confirmation local gate. The stage is
`AUTHORIZED`; implementation, approval, push, and merge remain separate.

## 2026-08-08 — DASH-005 implemented

Implemented and validated on the registered branch `feature/dash-005-board-task-detail`,
uncommitted, stopped for Human Owner approval. Registry state `AUTHORIZED` → `IN_PROGRESS`. See
`CL-20260808-01` above and `docs/reports/agentos-dashboard/STAGE-05-completion.md`.

## 2026-08-08 — DASH-005 closed

The Human Owner approved and closed DASH-005 through the automatic task-closeout gate
(`scripts/workflow-approve.sh`, GOV-AUTO-03). Registry state `COMPLETE`; task status `Done`.

## 2026-08-09 — DASH-006 authorized

The Human Owner authorized DASH-006 through the two-confirmation local gate. The stage is
`AUTHORIZED`; implementation, approval, push, and merge remain separate.

## 2026-08-09 — DASH-006 implemented

Implemented and validated on the registered branch `feature/dash-006-git-handover-views`,
uncommitted, stopped for Human Owner approval. Registry state `AUTHORIZED` → `IN_PROGRESS`. See
`CL-20260809-01` above and `docs/reports/agentos-dashboard/STAGE-06-completion.md`.

## 2026-08-09 — DASH-006 closed

The Human Owner approved and closed DASH-006 through the automatic task-closeout gate
(`scripts/workflow-approve.sh`, GOV-AUTO-03). Registry state `COMPLETE`; task status `Done`.

## 2026-08-10 — DASH-007 authorized

The Human Owner authorized DASH-007 through the two-confirmation local gate. The stage is
`AUTHORIZED`; implementation, approval, push, and merge remain separate.

## 2026-08-10 — DASH-007 closed

The Human Owner approved and closed DASH-007 through the automatic task-closeout gate
(`scripts/workflow-approve.sh`, GOV-AUTO-03). Registry state `COMPLETE`; task status `Done`.

## 2026-08-10 — DASH-008 authorized

The Human Owner authorized DASH-008 through the two-confirmation local gate. The stage is
`AUTHORIZED`; implementation, approval, push, and merge remain separate.

## 2026-08-10 — DASH-008 implemented

Implemented and validated on the registered branch `feature/dash-008-runs-evidence-audit`,
uncommitted, stopped for Human Owner approval. Registry state `AUTHORIZED` → `IN_PROGRESS`. See
`CL-20260810-02` above and `docs/reports/agentos-dashboard/STAGE-08-completion.md`.

## 2026-08-10 — DASH-008 closed

The Human Owner approved and closed DASH-008 through the automatic task-closeout gate
(`scripts/workflow-approve.sh`, GOV-AUTO-03). Registry state `COMPLETE`; task status `Done`.

## 2026-08-10 — DASH-009 authorized

The Human Owner authorized DASH-009 through the two-confirmation local gate. The stage is
`AUTHORIZED`; implementation, approval, push, and merge remain separate.

## 2026-08-10 — DASH-009 implemented

Implemented and validated on the registered branch `fix/dash-009-security-hardening`,
uncommitted, stopped for the mandatory independent security review and then Human Owner
approval. Registry state `AUTHORIZED` → `IN_PROGRESS`. See `CL-20260810-04` above and
`docs/reports/agentos-dashboard/STAGE-09-completion.md`.

## 2026-08-10 — DASH-009 closed

The Human Owner approved and closed DASH-009 through the automatic task-closeout gate
(`scripts/workflow-approve.sh`, GOV-AUTO-03). Registry state `COMPLETE`; task status `Done`.

## 2026-08-11 — DASH-010 authorized

The Human Owner authorized DASH-010 through the two-confirmation local gate. The stage is
`AUTHORIZED`; implementation, approval, push, and merge remain separate.

## 2026-08-11 — DASH-010 implemented

Implemented and validated on the registered branch `feature/dash-010-release-readiness`,
uncommitted, stopped for Human Owner approval. Registry state `AUTHORIZED` → `IN_PROGRESS`. See
`CL-20260811-01` above and `docs/reports/agentos-dashboard/STAGE-10-completion.md`.

## 2026-08-11 — DASH-010 closed

The Human Owner approved and closed DASH-010 through the automatic task-closeout gate
(`scripts/workflow-approve.sh`, GOV-AUTO-03). Registry state `COMPLETE`; task status `Done`.
