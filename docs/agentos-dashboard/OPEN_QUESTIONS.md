# AgentOS Dashboard — Open Questions

| Field | Value |
|---|---|
| **Title** | AgentOS Dashboard — Open Questions |
| **Purpose** | Owner-decision register (OD-D#) with dispositions and the requirement IDs each question blocks. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Documentation & Governance session · Human Owner (dispositions) |
| **Dependencies** | `MASTER_PLAN.md` §11 |
| **Related Documents** | `STAGE_REGISTRY.md` (preconditions cite entries here) |

## Format

Each entry: question, recommendation, disposition, date, blocked IDs. Entries move to
Resolved append-only; they are never deleted.

## Open

### OD-D9 — Web-framework dependency for the serving layer

- **Question:** `ai-workflow-engine` pins no web framework (`pyproject.toml`: pydantic,
  PyYAML, rich, typer; dev: black, mypy, pre-commit, pytest, ruff). Which HTTP-serving and
  templating stack may the dashboard add, and where is it declared (e.g., a new optional
  dependency group such as `dashboard` in `pyproject.toml`, or a standalone requirements file
  outside the packaged project)?
- **Recommendation:** A minimal, pinned optional-dependency group; stdlib-only
  (`http.server`-based) serving is the fallback if the Human Owner declines any new
  dependency.
- **Disposition:** **Open.** Blocks DASH-004 authorization (and, transitively, every
  page-serving stage). DASH-002/DASH-003 are deliberately stdlib + existing-dependency only
  and are not blocked.
- **Blocked:** DASH-004..DASH-010 serving-layer work; `ARCHITECTURE.md` §6 rows marked
  "pending OD-D9".

## Resolved

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
DD-01, DD-02, DD-03.

## Future Revisions
New questions are appended with the next OD-D number.
