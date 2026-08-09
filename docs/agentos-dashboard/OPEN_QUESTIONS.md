# AgentOS Dashboard — Open Questions

| Field | Value |
|---|---|
| **Title** | AgentOS Dashboard — Open Questions |
| **Purpose** | Owner-decision register (OD-D#) with dispositions and the requirement IDs each question blocks. |
| **Status** | Draft |
| **Version** | 1.4 |
| **Owner** | Documentation & Governance session · Human Owner (dispositions) |
| **Dependencies** | `MASTER_PLAN.md` §11 |
| **Related Documents** | `STAGE_REGISTRY.md` (preconditions cite entries here) |

## Format

Each entry: question, recommendation, disposition, date, blocked IDs. Entries move to
Resolved append-only; they are never deleted.

## Open

None currently open.

## Resolved

### OD-D12 — Reading the engine's persisted workflow-event store from the task detail page

- **Question:** `DR-031` asks the task detail page (PG-03) to show "lifecycle history parsed
  from queue prose **and, where present, the engine's persisted workflow events**". The engine's
  persisted workflow events (`ai_workflow_engine.workflow.event_store`) live under
  `~/.ai-workflow-engine/workflow-runs/state/<project_id>/<task_dir>/` — outside the repository
  working copy entirely, and therefore outside every adapter's `RepositoryRoot` confinement
  (`ARCHITECTURE.md` §3; `SECURITY_MODEL.md` SC-06..SC-08). No dashboard document authorizes a
  read path outside that confinement (the same class of decision OD-D9/OD-D5 each required for a
  narrower scope expansion). May a future stage add a second, explicitly-scoped read-only adapter
  for this one out-of-repo location, and if so under what confinement (a fixed, non-configurable
  path only; no traversal of any kind beyond it)?
- **Recommendation:** yes, as a narrowly-scoped follow-on stage: a second adapter confined to
  exactly `~/.ai-workflow-engine/workflow-runs/state/<this repo's project_id>/**`, read-only,
  with its own SC-06-equivalent containment tests, gated on its own Human Owner decision before
  any DASH stage reads it.
- **Disposition:** **Resolved 2026-08-08** by the DASH-005 remediation session (independent
  review found DASH-005 `PARTIAL` for not consuming the authoritative Legacy event store; see
  `docs/reports/agentos-dashboard/STAGE-05-completion.md`'s "Remediation Addendum"). Implemented
  exactly the recommended shape: `agentos_dashboard/services/legacy_workflow.py` reads
  `self-governance.yaml`'s `project.id` (already an in-repo watched file) and calls the engine's
  own `ai_workflow_engine.workflow.event_store.load_history`/`derive_state` directly — the
  engine's fixed, non-configurable state-root confinement and verified replay are relied on as
  the containment guarantee, rather than a second `RepositoryRoot`-style adapter reimplementing
  it. Read-only: only `load_history`/`derive_state` are called, never `append`/`record_outcome`
  (asserted by `agentos_dashboard/tests/test_api_board.py::
  test_legacy_workflow_module_never_calls_the_engines_write_path`).
- **Blocked:** none remaining.

### OD-D9 — Web-framework dependency for the serving layer

- **Question:** `ai-workflow-engine` pins no web framework (`pyproject.toml`: pydantic,
  PyYAML, rich, typer; dev: black, mypy, pre-commit, pytest, ruff). Which HTTP-serving and
  templating stack may the dashboard add, and where is it declared (e.g., a new optional
  dependency group such as `dashboard` in `pyproject.toml`, or a standalone requirements file
  outside the packaged project)?
- **Recommendation:** A minimal, pinned optional-dependency group; stdlib-only
  (`http.server`-based) serving is the fallback if the Human Owner declines any new
  dependency.
- **Disposition:** **Resolved 2026-07-29** by Human Owner decision (`DECISIONS.md` DD-09;
  `docs/DECISION_LOG.md`, 2026-07-29 entry). The recommendation was adopted in its
  optional-dependency-group form; the stdlib `http.server` fallback was explicitly **not**
  selected and may not be the primary implementation. The selected stack is exactly:
  - **FastAPI** — the local HTTP application framework;
  - **Uvicorn** — the ASGI server;
  - **Jinja2** — server-rendered HTML templates.

  Declared in a new optional dependency group named `dashboard` in `pyproject.toml`
  (`fastapi>=0.111,<1`, `jinja2>=3.1,<4`, `uvicorn>=0.30,<1`), added by this governance commit.
  The default/core `ai-workflow-engine` installation stays free of every dashboard-serving
  dependency: `[project].dependencies` is unchanged, so `pip install ai-workflow-engine` still
  installs no web framework and the engine's own runtime, CLI, lint/type gates, and test
  collection are untouched. **DASH-004 and every later dashboard stage may use only the three
  distributions declared in this group** (plus the stdlib and the already-pinned core
  dependencies); any addition to the group, and any dependency outside it, requires a separate
  Human Owner authorization.
- **Security boundary:** the serving layer binds loopback-only by default, unchanged from
  `SECURITY_MODEL.md` SC-01..SC-05 and `ARCHITECTURE.md` §5 — this decision selects an
  implementation, it does not widen exposure. Remote exposure, authentication, TLS, and any
  production deployment posture remain out of scope and are later-stage concerns requiring
  their own decisions. Framework choice affects how SC-03/SC-05 are implemented, never their
  intent.
- **Effect on DASH-004:** the dependency-declaration change DASH-004's Allowed list defers to
  ("exactly the dependency-declaration change OD-D9's disposition names") is already performed
  here, so DASH-004 needs no `pyproject.toml` edit of its own and gains no license to add
  further dependencies. **DASH-004 is no longer blocked by OD-D9 as of this governance commit.**
  It remains `Planned` and **unauthorized**: it still requires DASH-003 `COMPLETE` (satisfied),
  its own fresh written Human Owner authorization, and its registered branch before any
  implementation may begin. Resolving OD-D9 authorizes nothing.
- **Blocked:** formerly DASH-004..DASH-010 serving-layer work and the `ARCHITECTURE.md` §6 rows
  marked "pending OD-D9" (now filled in); no longer blocked. DASH-002/DASH-003 were never
  blocked by this question and remain stdlib + existing-dependency only.

### OD-D10 — The stage branch versus the local runner's no-branch rule

- **Question:** The SSP's initial-start preflight (`stage-prompts/README.md`;
  `STAGE_REGISTRY.md` §2 rules 4 and 15) requires a DASH stage to run on its registered branch,
  created from clean `main` — for DASH-002, `feature/dash-002-repo-adapter`. The local runner
  prompt the Human Owner now launches implementation sessions with
  (`scripts/prompts/implement-next-task.md` §7) forbids the session from creating or switching
  branches at all, and `scripts/workflow-authorize.sh` (lines 265-266) states that the canonical
  implementation branch "is created later by the implementation session, never by this gate."
  The two instructions cannot both be satisfied by one session. Which governs?
- **Effect at the time:** the DASH-002 implementation was performed on `main` in the working
  tree, uncommitted, because the runner prompt's prohibition is explicit and creating a branch
  would have violated it. `scripts/workflow-approve.sh` enforced the registry's branch cell
  (`EXIT_SCOPE_MISMATCH`, exit 15), so the approval gate refused the closeout until the working
  tree was manually switched.
- **Recommendation:** either (a) the Human Owner runs `git switch -c feature/dash-002-repo-adapter`
  before `scripts/workflow-approve.sh` — uncommitted changes carry across, and the stage then
  satisfies rules 4/15 exactly; or (b) the runner prompt gains an explicit exception permitting
  a registry-governed stage session to create its own registered branch from clean `main`,
  matching what AUTO-007 did and what `workflow-authorize.sh` already documents.
- **Disposition:** **Resolved 2026-07-29** (GOV-AUTO-04, `DECISIONS.md` DD-08) — neither (a) nor
  (b) above: `scripts/workflow-authorize.sh` now creates or safely switches to a registry-governed
  stage's registered branch itself, immediately after its own authorization commit, via the new
  shared `scripts/lib/branch_prepare.sh`. The runner prompt's no-branch-creation rule is
  untouched; by the time an implementation session starts, the registered branch already exists
  and is already checked out. `scripts/workflow-next.sh` additionally verifies (read-only) that
  the branch precondition holds before launching an agent. Report:
  `docs/reports/GOV-AUTO-04-completion-report.md`.
- **Blocked:** formerly the DASH-002 approval/closeout path, and every later DASH stage run
  through the same local runner; no longer blocked.

### OD-D11 — Completion-report filename expected by the approval gate

- **Question:** This program's naming convention (`stage-prompts/README.md` "Naming
  Conventions"; `STAGE_REGISTRY.md` §3) is
  `docs/reports/agentos-dashboard/STAGE-XX-completion.md`, and DASH-001's report follows it.
  `scripts/workflow-approve.sh`'s closeout looks only for
  `docs/reports/agentos-dashboard/<TASK_ID>-completion-report.md`, so it cannot find a report
  written under the documented name and exits `EXIT_MISSING_REPORT`.
- **Recommendation:** teach the approval gate this program's naming convention (a `scripts/`
  change, out of scope for any DASH stage), rather than renaming the report and breaking the
  convention DASH-001 already established.
- **Disposition:** **Resolved 2026-07-29** (GOV-AUTO-04, `DECISIONS.md` DD-08) — the
  recommendation was adopted: `scripts/workflow-approve.sh`'s report-discovery now also accepts
  `docs/reports/agentos-dashboard/STAGE-XX-completion.md` for a DASH task, with the stage number
  cross-checked against the registry's own Branch cell rather than derived from unchecked
  filename construction; a disagreeing or malformed registry silently disables the canonical
  lookup, and two present reports with differing content are refused outright. Existing
  `<TASK_ID>-completion-report.md` behavior for AUTO/GOV tasks is unchanged. Report:
  `docs/reports/GOV-AUTO-04-completion-report.md`.
- **Blocked:** formerly the automated closeout half of the DASH-002 approval path (the same path
  OD-D10 blocked); no longer blocked.

### OD-D1 — DASH task-family authorization
- **Question:** Authorize DASH-001..010 and enrollment of the DASH task family in
  `docs/TASK_QUEUE.md`?
- **Recommendation:** Yes; nothing may proceed without it.
- **Disposition:** **Resolved 2026-07-23** — the Human Owner recorded "I authorize DASH-001"
  and subsequently "I authorize recovery and correct execution of DASH-001 in the
  ai-workflow-engine repository", directing execution on branch
  `governance/dash-001-documentation`; both records are logged in `STAGE_REGISTRY.md` §4.
  Successor stages each require their own fresh authorization.
- **Blocked:** formerly all stages; DASH-002..010 remain individually gated.

### Resolved by approval of the implementation-ready plan (2026-07-23), as adapted by DD-03

| ID | Question | Disposition |
|---|---|---|
| OD-D2 | Markdown rendering dependency vs stdlib | Stdlib escape-first mini-renderer for MVP; revisit post-MVP |
| OD-D3 | Dashboard port | `127.0.0.1:8642`, configurable via `AWED_PORT`, loopback enforced in code |
| OD-D4 | Package/route naming | Top-level `agentos_dashboard/`; keeps the engine package `src/ai_workflow_engine/` and its wheel packaging (`[tool.hatch.build.targets.wheel]`) untouched |
| OD-D5 | Local database | Approved: `data/agentos_dashboard/dashboard.db`, stdlib sqlite3, non-authoritative, no Alembic; `data/` does not exist yet — DASH-008 creates it and adds the narrowest `.gitignore` rule |
| OD-D6 | Handover manifest refresh action | Deferred (DR-906); manual documented procedure only in MVP (recompute size + `sha256sum` per `handover/PROJECT_CHECKSUM.md`'s own instructions) |
| OD-D7 | GitHub `gh` integration | Deferred (DR-907); MVP shows merge commits + doc references |
| OD-D8 | Dashboard tests in canonical suite | No for MVP; separate `agentos_dashboard/tests/` invocation; engine `testpaths=["tests"]` untouched |

## Decision References
DD-01, DD-02, DD-03, DD-08, DD-09.

## Future Revisions
New questions are appended with the next OD-D number.
