# AgentOS Dashboard — Open Questions

| Field | Value |
|---|---|
| **Title** | AgentOS Dashboard — Open Questions |
| **Purpose** | Owner-decision register (OD-D#) with dispositions and the requirement IDs each question blocks. |
| **Status** | Draft |
| **Version** | 1.1 |
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
DD-01, DD-02, DD-03, DD-08.

## Future Revisions
New questions are appended with the next OD-D number.
