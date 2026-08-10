# STAGE-08 Completion Report

- **Stage identity / title / assigned role / objective:** DASH-008 — Run records, evidence, and
  audit timeline. Role: Dashboard implementation session. Objective (contract
  `docs/agentos-dashboard/stage-prompts/DASH-008.md`, Version 1.1): a non-authoritative local
  SQLite store (`dashboard.db`), an append-only audit trail, run/evidence/audit pages, and the
  explicit read-only EP-18 orchestration view over DASH-003's existing parser/state source.
- **Authorization evidence:** Human Owner supplied both exact `AUTHORIZE` confirmations through
  `scripts/workflow-authorize.sh` on 2026-08-10. Preconditions passed on the default-branch
  baseline at `c664fcb58d3fae64877ce04020e4d0dbcdc961a6`. Registry moved `NOT_STARTED →
  AUTHORIZED` (`docs/agentos-dashboard/STAGE_REGISTRY.md` §4, 2026-08-10 row).
- **Initial repository state:** branch `feature/dash-008-runs-evidence-audit`, checked out at
  `7277943c75787f76040d4d36c551202f9db3d587` (the DASH-008 authorization commit), `main` at the
  identical commit, `git status` clean, both pre-existing stashes untouched.
- **Preconditions checked (initial-start preflight, `stage-prompts/README.md`):**
  - Active stage is exactly DASH-008 with registry state `AUTHORIZED` — **PASS**.
  - DASH-007 is `COMPLETE` — **PASS** (`STAGE_REGISTRY.md` §3).
  - `docs/TASK_QUEUE.md`, `docs/current_task.md`, `docs/remaining_tasks.md` all agree (`Current`)
    — **PASS**.
  - No other task is `Current` — **PASS**.
  - `docs/agentos-dashboard/OPEN_QUESTIONS.md` §Open is empty — **PASS**.
  - Working branch is exactly `feature/dash-008-runs-evidence-audit`, created from clean `main` —
    **PASS**.
  - `git status` clean before starting — **PASS**.

  All preconditions passed; registry state moved `AUTHORIZED → IN_PROGRESS`
  (`STAGE_REGISTRY.md` §4, 2026-08-10 "initial-start preflight passed" row).

## Implementation summary

Delivered exactly the stage contract's Allowed scope:

1. **Storage layer** (`agentos_dashboard/storage/`): stdlib `sqlite3` only, no ORM, no Alembic.
   `storage.db.connect()` creates `data/agentos_dashboard/dashboard.db` (and its parent
   directories) on first use, sets `PRAGMA user_version = 1` and `PRAGMA foreign_keys = ON`, and
   applies the complete `DATA_MODEL.md` §3 schema (all eight tables:
   `stage_runs`, `validation_runs`, `generated_prompts`, `approvals`, `findings`, `user_notes`,
   `consistency_history`, `audit_events`) via idempotent `CREATE TABLE IF NOT EXISTS` statements.
   Initialization is atomic and fail-closed: only a genuinely empty version-0 file is initialized;
   unsupported versions, partial schemas, wrong columns/constraints/triggers, and runtime-path
   symlink escapes are rejected without migration or recreation. Every connection re-enables
   foreign keys, a 5-second busy timeout, WAL, and `synchronous=FULL`. Schema triggers reject
   UPDATE/DELETE against every DASH-008 stored entity. `DashboardDatabase.connection()` opens and
   closes a fresh transactional connection per use, so a manually deleted `dashboard.db` is
   recreated empty on the next access rather than breaking derived/read-only state (TR-06/TR-08).
2. **Services** (`agentos_dashboard/services/`): `runs.py` (EN-11 `StageRun` + EN-16
   `ValidationRun`, DR-050/052, with report existence, bounded size, stable SHA-256, traversal,
   directory, and symlink-escape checks recomputed live — DR-051's verified-vs-claimed split); `approvals.py`
   (EN-14 draft `Approval`, DR-060/061 — a `target_commit` is resolved against real Git history at
   creation time, and an unresolvable one automatically raises a `findings` row plus a
   `reconciliation_divergence` audit event); `findings.py` (EN-15 draft `Finding`); `notes.py`
   (EN-29 `UserNote`); `audit.py` (EN-26 append-only `AuditEvent` plus its JSONL mirror, and the
   merged local+repository audit timeline for EP-16); `evidence.py` (the EP-17 verified-vs-claimed
   aggregate, a thin view over `runs.py` — see Deviations); `orchestration.py` (the EP-18
   read-only ORCH feature-state view, reusing DASH-003's `parsing.orchestration` parser with zero
   new persistence, Git, or subprocess reach).
3. **API routes** (`agentos_dashboard/api/{runs,drafts,audit,evidence,orchestration}.py`, wired
   into `api/routes.py`): `GET/POST /runs`, `GET /runs/{uuid}` (EP-15/EP-22); `POST /approvals`,
   `POST /findings`, `POST /notes` (EP-23); `GET /audit` (EP-16); `GET /evidence/{ref}` (EP-17);
   `GET /orchestration` (EP-18). Every mutating endpoint is idempotent on a caller-supplied
   `client_token` UUID (same payload returns the original; a conflicting payload returns typed
   HTTP 409; `UNIQUE` plus `INSERT OR IGNORE` resolves concurrent duplicates) and requires the
   CSRF double-submit header already enforced by `SecurityMiddleware`. UUID path parameters,
   pagination bounds, malformed JSON, and unexpected fields are validated with typed envelopes.
4. **Web pages** (`agentos_dashboard/web/templates/{runs,run_detail,evidence,audit}.html`, PG-05/
   PG-06/PG-10; wired into `web/routes.py`): `/runs` (list + "record a run" form), `/runs/{uuid}`
   (record detail, validation matrix, verified/claimed badges, add-note form), `/evidence` (gate
   matrix across every run), `/audit` (merged timeline with kind/task filters and a copy action).
   `base.html`'s left navigation and `app.js` (create-run/add-note/copy-timeline handlers, CSRF +
   idempotency-UUID discipline matching the existing prompt-generation/acknowledge patterns) were
   updated to reach the new pages, the same pattern DASH-005/DASH-006/DASH-007 used for their own
   template deliveries.
5. **`.gitignore`**: one new rule, `/data/agentos_dashboard/`, the narrowest pattern covering the
   new runtime directory (allowed modification per the stage contract).

## Architecture decisions

- **Per-call connections, not a long-lived one.** `DashboardDatabase.connection()` opens and
  closes a fresh `sqlite3.Connection` on every use rather than holding one for the process
  lifetime. This is what makes the "deleting `dashboard.db` breaks nothing" acceptance criterion
  hold structurally: a long-lived connection would keep working against an unlinked inode after
  manual deletion, masking rather than proving the non-authoritative property.
- **DB/JSONL commit model.** Audit lines are canonical single-line ASCII JSON, queued with the
  transaction, appended with `O_APPEND`, fully written and `fsync`ed before SQLite commit. Mirror
  failure rolls the DB mutation back. A later DB commit failure can leave an orphan JSONL line;
  `inspect_audit_mirror` detects orphan/missing/duplicate/malformed/truncated/oversized records and
  the audit timeline surfaces a bounded `audit_mirror_divergence` contradiction. It never repairs,
  rewrites, or truncates evidence. This is the explicit reconciliation model for the unavoidable
  two-file commit boundary.
- **Conflict-safe idempotency.** Each idempotent entity stores a canonical request SHA-256 beside
  its unique UUID token. Same token+same payload replays across connections/restarts; same
  token+different payload fails 409; failed transactions leave no consumed token.
- **`report_path_verified` is always recomputed at read time, never persisted.** The claim
  (`report_path`) and the verification (`report_path_verified`) are two different data paths by
  construction — one is a stored column, the other is a live `stat_file` call — so the split
  DR-051 requires cannot drift even if the underlying report file is created, moved, or deleted
  after the run record was written.
- **Approval authority is never inferred.** A named `target_commit` is resolved with fixed-argv,
  read-only Git and recorded separately as `target_commit_resolved`; the draft's `reconciled`
  field remains false because commit existence does not prove an authoritative approval. Unknown
  revisions raise a local divergence finding; timeouts, unavailable Git, malformed output, and
  abnormal command exits produce no approval, finding, or audit row. An absent target has nothing
  to compare and raises nothing.
- **The merged audit timeline does not force one synthetic clock.** Local `audit_events` carry a
  real timestamp; the engine's persisted Legacy workflow events (`services.legacy_workflow`)
  carry only a monotonic `sequence`, never a timestamp. Rather than inventing one, `TimelineEntry`
  keeps both fields and sorts local entries by `ts` and repository entries by `sequence`,
  presenting the two streams honestly rather than implying a precision the source data does not
  have (`SOURCE_OF_TRUTH.md` TR-02).

## Created files

`agentos_dashboard/storage/__init__.py`, `agentos_dashboard/storage/db.py`,
`agentos_dashboard/services/runs.py`, `agentos_dashboard/services/approvals.py`,
`agentos_dashboard/services/findings.py`, `agentos_dashboard/services/notes.py`,
`agentos_dashboard/services/audit.py`, `agentos_dashboard/services/evidence.py`,
`agentos_dashboard/services/orchestration.py`, `agentos_dashboard/api/runs.py`,
`agentos_dashboard/api/drafts.py`, `agentos_dashboard/api/audit.py`,
`agentos_dashboard/api/evidence.py`, `agentos_dashboard/api/orchestration.py`,
`agentos_dashboard/web/templates/runs.html`, `agentos_dashboard/web/templates/run_detail.html`,
`agentos_dashboard/web/templates/evidence.html`, `agentos_dashboard/web/templates/audit.html`,
and 16 test files under `agentos_dashboard/tests/` (listed in full under "Tests added").

## Modified files

`.gitignore` (new `/data/agentos_dashboard/` rule), `agentos_dashboard/api/errors.py` (typed 409
idempotency conflict), `agentos_dashboard/api/routes.py` (EP-15/16/
17/18/22/23 wired in), `agentos_dashboard/main.py` (`DashboardDatabase` constructed and passed to
both routers, exposed on `app.state`), `agentos_dashboard/web/routes.py` (`/runs`, `/runs/{uuid}`,
`/evidence`, `/audit` page routes), `agentos_dashboard/web/static/app.js` (create-run/add-note/
copy-timeline handlers), `agentos_dashboard/web/templates/base.html` (nav links for Runs,
Evidence, Audit; Orchestration left disabled — see UI changes), `docs/agentos-dashboard/
STAGE_REGISTRY.md` (§3 state cell, §4 log row), `docs/agentos-dashboard/CHANGELOG.md` (CL-20260810-
02, the final-review CL-20260810-03 entry, and the chronological trailer entry).

## Deleted files

None.

## Database changes

New: `data/agentos_dashboard/dashboard.db` (created at runtime, gitignored) with the complete
`DATA_MODEL.md` §3 schema (eight tables) and `data/agentos_dashboard/logs/audit.jsonl` (the
append-only JSONL mirror of `audit_events`). No existing database changed (none existed before
this stage).

## API changes

New: `GET /dash/api/v1/runs`, `GET /dash/api/v1/runs/{uuid}`, `POST /dash/api/v1/runs` (EP-15/
EP-22); `POST /dash/api/v1/approvals`, `POST /dash/api/v1/findings`, `POST /dash/api/v1/notes`
(EP-23); `GET /dash/api/v1/audit` (EP-16); `GET /dash/api/v1/evidence/{ref}` (EP-17); `GET
/dash/api/v1/orchestration` (EP-18). No existing endpoint's request or response shape changed.

## UI changes

New pages: `/runs`, `/runs/{uuid}` (PG-05), `/evidence` (PG-06), `/audit` (PG-10). `base.html`'s
left navigation now links Runs, Evidence, and Audit (previously disabled placeholders).
Orchestration deliberately stays a disabled nav placeholder: per the stage contract, EP-18
"introduces no separate page: it renders inside PG-02's board program lane and as a PG-03-style
drill-down for ORCH stages," and `PG-02`/`PG-03` (`board.html`/`task_detail.html`) are not in this
stage's Allowed templates list, so wiring EP-18's data into those existing pages is left to a
future stage or correction.

## Security changes

The existing middleware still uniformly supplies CSRF, Host allowlisting, CSP/no-sniff/no-store,
and redacted 500s. DASH-008 additionally confines both runtime paths on construction and every
use, rejects parent/final symlinks, never mirrors free-text claims into JSONL, rejects extra JSON
fields and malformed UUIDs, bounds list/timeline responses, and renders hostile claims through
Jinja autoescaping. The store remains unreachable through repository-content adapters.

## Tests added

The 16 DASH-008 test files now cover 104 focused cases. The final review added real-SQLite tests
for unsupported/partial schema refusal, every-connection pragmas/WAL, runtime symlink escape,
schema-level immutability, concurrent DB-unique idempotency, restart replay, failed-token rollback,
mirror write and post-mirror commit failures, orphan/truncated/malformed mirror detection, secret-
free JSONL, stable evidence hashes, traversal/symlink evidence refusal, transient/abnormal Git
failure, cross-origin audit-kind filtering, bounded/paginated note reads, server-side HTML filter
bounds, conflicting-token HTTP 409s, strict JSON/UUID/method handling, whole-HTTP-path EP-18
zero-subprocess, and hostile-HTML escaping. No production SQLite behavior is mocked.

## Validation

- **Focused:** the exact final command over all 16 DASH-008 test files → **104 passed in 6.47s**.
- **Dashboard regression:** `pytest agentos_dashboard/tests -q` → **623 passed, 1 failed in
  22.45s**. The sole failure,
  `test_parsing_task_queue.py::test_real_current_task_is_recognized_as_a_valid_empty_state`, is
  **pre-existing and live-state-dependent**: it hardcodes zero `Current` tasks while authorized
  DASH-008 is correctly the sole `Current` task. The final reviewer reproduced the same failure
  against both the working tree and a clean read-only `git archive HEAD` extraction; no stash,
  restore, or other Git mutation was used.
- **Broader regression:** `pytest tests agentos_workflow/tests -q` → **5076 passed, 34 deselected
  in 481.56s**.
- **Quality:** `ruff check --no-cache .` → clean; `black --check .` → **351 files unchanged**;
  canonical `mypy` → **no issues in 188 source files**; `git diff --check` → clean. Canonical
  `mypy` also passed on clean authorized base HEAD (**174 source files**), proving DASH-008 adds no
  type-check regression.
- **Startup:** `python -m agentos_dashboard --check` → configuration OK at
  `http://127.0.0.1:8642`.
- **Manual probes:** fresh initialization, reopen, transaction rollback, same-payload replay,
  conflicting-token rejection, JSONL append, mirror-failure rollback, traversal refusal, symlink
  refusal, duplicate reconciliation finding prevention, approval-draft non-authority, and direct
  SQL audit immutability all passed against temporary repositories and reopened databases.
- **Governance:** `workflowctl verify --config self-governance.yaml` → `task-state` PASS,
  `governance` PASS, `registries` PASS (26 stages across 2 registries), `handover` PASS; `git`
  FAILs on the single, pre-existing, expected `upstream_missing` finding for this freshly created,
  not-yet-pushed stage branch — the same documented pattern every prior DASH stage's report
  records at this point in its lifecycle.
- **Changed-file scope audit:** every created/modified file falls under the stage contract's
  Allowed list (`agentos_dashboard/storage/**`, run/approval/finding/note/audit/orchestration
  services, EP-15/16/17/18/22/23 routes, PG-05/06/10 templates, tests, `.gitignore`, and this
  program's SSP documentation: the stage registry and changelog). No file under `src/`, `tests/`,
  `scripts/`, `pyproject.toml`, `handover/**`, or `docs/implementation/orchestration/**` was
  touched. One scope note is recorded under Deviations below.

## Acceptance-criteria checklist

- `dashboard.db` with `PRAGMA user_version = 1`, foreign keys ON — **PASS**
  (`test_storage_db.py::test_connect_sets_user_version_and_foreign_keys`).
- Tables per `DATA_MODEL.md` §3 including an append-only `audit_events` table (no UPDATE/DELETE
  code path; source scan plus schema triggers reject adversarial UPDATE/DELETE) + JSONL mirror — **PASS**
  (`test_storage_db.py::test_connect_creates_every_table`,
  `test_dash008_append_only.py` both tests).
- Idempotent POSTs via client UUIDs — **PASS** (same-payload replay returns the original across
  restart; conflicting payload returns 409; concurrent duplicates exercise DB uniqueness; mirror
  failure rolls back without consuming the token).
- Run records verifying report-path existence and linking prompt hashes — **PASS**
  (`test_services_runs.py::test_report_path_verified_*`, `test_create_run_persists_all_dr050_fields`
  covering `prompt_hash`).
- Evidence pages splitting repo-verified from user-claimed values — **PASS**
  (`test_services_evidence.py`, `test_api_audit_evidence_orchestration.py::
  test_evidence_detail_reflects_verified_and_claimed_split`, `run_detail.html`/`evidence.html`'s
  VERIFIED/CLAIMED badges, stable bounded SHA-256 metadata, traversal and symlink refusals).
- Merged audit timeline — **PASS** (`test_services_audit.py::
  test_build_audit_timeline_merges_repository_derived_events`).
- The database is non-authoritative: deleting it must not break any read-only view (test) —
  **PASS** (`test_dash008_db_deletion_safety.py`).
- EP-18: reachable with zero write to `dashboard.db`, zero Git invocation, zero agent/subprocess
  invocation (each proved by a negative test) — **PASS**
  (`test_api_audit_evidence_orchestration.py::test_orchestration_endpoint_writes_nothing_to_dashboard_db`
  for zero-write and `test_orchestration_http_path_never_invokes_git_or_subprocess` around the
  complete HTTP request; the endpoint uses `cache.root`, not Git-reading `cache.get()`).
- EP-18 response is read-only ORCH feature-state, never a mutation affordance — **PASS**
  (`test_api_audit_evidence_orchestration.py::
  test_orchestration_response_never_carries_a_mutation_affordance`).

## Scope interpretations / residual risks

1. **`services/evidence.py`/`api/evidence.py` are an authorized implied subdivision (scope A).**
   They are not literally named in the Allowed-files prose. The contract names
   "run/approval/finding/note/audit/orchestration
   services," and EP-17 (`GET /evidence/{ref}`) is separately named as an Allowed route requiring
   *some* data-shaping module. The module added is a thin aggregate entirely over the in-scope
   `services.runs` types, with no new persistence, entity, adapter, or capability. This is the
   necessary implementation subdivision of expressly authorized EP-17, not a scope expansion.
2. **`generated_prompts` and `consistency_history` tables exist but have no writer.** `DATA_MODEL.md`
   §3 lists eight tables for this stage to build; two of them belong conceptually to
   `services/prompts.py` (DASH-007) and `services/consistency.py` (DASH-006), neither of which is
   in this stage's Allowed list. The tables are created (so the schema matches the full spec) but
   nothing writes to them yet — migrating those two in-memory stores onto `dashboard.db` is
   explicit future work, not performed here.
3. **EP-18 has no separate page, as contracted.** PG-02's existing ORCH lane continues to render
   the same DASH-003 parser/state source directly; EP-18 exposes that source through a strictly
   read-only endpoint without introducing a second parser, persistence source, or page.
4. **LOW — the `/runs` create-run web form does not expose structured validation-matrix input.**
   The API (`POST /runs`) accepts a full `validation` array; the web form only submits the four
   core DR-050 fields plus free-text `validation_summary`/`findings_text`/`notes`. Structured
   validation entries can still be recorded via the API (exercised by
   `test_api_runs.py::test_create_run_records_validation_matrix`); adding a matching repeating-row
   web form is straightforward follow-up work, not performed here to keep the template's scope
   bounded.
5. **INFO — pre-existing, unrelated to this diff:** `test_parsing_task_queue.py::
   test_real_current_task_is_recognized_as_a_valid_empty_state` fails whenever any task is
   `Current` (see Validation above) — a DASH-003 test asserting a transient repository fact, not a
   DASH-008 defect.

## Rollback instructions

Per `STAGE_REGISTRY.md` §2 rule 14: revert this stage's exact commit(s) once approved and
committed; `dashboard.db` never blocks rollback (it is gitignored, local-only, and non-
authoritative — deleting or leaving it behind after a revert affects no governance conclusion).
Before commit (current state): discard the working-tree diff listed above; no other rollback step
is needed since nothing was committed, pushed, or merged.

## Git diff summary (`git diff --stat`)

The final tracked diff and complete untracked-path inventory were re-read after correction.
`git diff --stat` omits the untracked deliverables by definition; the authoritative inventory is
the Created/Modified/Deleted list above together with the final `git status --short` recorded by
the reviewer. No staged path exists.

## Recommended commit message

```
feat(dashboard): add run records, evidence and audit timeline (DASH-008)
```

## Final stage status: IMPLEMENTATION COMPLETE; GOVERNANCE IN_PROGRESS PENDING HUMAN OWNER

## Confirmation

The next stage (DASH-009) was **not** started, selected, or prepared. No commit, push, merge,
branch creation/switch, rebase, reset, amend, or stash operation was performed.

## Addendum — Human Owner approval and closure (2026-08-10)

The Human Owner reviewed this report and the implementation diff, typed the two exact `APPROVE`
confirmations required by `scripts/workflow-approve.sh`, and approved the Conventional Commit
message `feat(dashboard): add run records, evidence and audit timeline (DASH-008)`. The script then performed the deterministic governance closeout
recorded in `docs/DECISION_LOG.md`'s matching entry and staged the approved implementation
together with the generated closeout records in one local commit. This commit's hash, and any
later publication or merge, are recorded separately — a commit cannot record its own hash.
