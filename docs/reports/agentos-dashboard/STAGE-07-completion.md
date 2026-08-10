# STAGE-07 Completion Report

- **Stage identity / title / assigned role / objective**: DASH-007 — Stage registry and prompt
  generation. Role: Dashboard implementation session. Objective: a stage-registry loader
  cross-checked against a coded schema, a precondition engine, gated hash-recorded prompt
  generation with a refusal path (EP-13, EP-14, EP-21; PG-04), and — added to this stage's
  contract by PLAN-001 — a bounded read-only Governance browser/search surface (DR-090, DR-091;
  EP-07, EP-08; PG-08).
- **Authorization evidence**: Human Owner supplied both exact `AUTHORIZE` confirmations through
  `scripts/workflow-authorize.sh`, recorded in `docs/agentos-dashboard/STAGE_REGISTRY.md` §4
  (2026-08-10 row) and `docs/DECISION_LOG.md`. Preconditions passed on the default-branch baseline
  at `92fb3e0ace48f7ce34cea8b53f49d48e5f63889a`; the authorization-only commit is `089750f`.
  Registry state `NOT_STARTED → AUTHORIZED`.
- **Initial repository state**: branch `feature/dash-007-prompt-generation` at `089750f`, `main`
  at the identical commit, `git status` clean, both pre-existing stashes untouched.
- **Preconditions checked** (SSP initial-start preflight, `STAGE_REGISTRY.md` §2 rule 4): active
  stage exactly DASH-007 with registry state `AUTHORIZED` — PASS; DASH-006 `COMPLETE` — PASS;
  `docs/TASK_QUEUE.md`/`docs/current_task.md`/`docs/remaining_tasks.md` agree (`Current`) — PASS;
  no other task `Current` — PASS; `OPEN_QUESTIONS.md` §Open empty — PASS; working branch exactly
  `feature/dash-007-prompt-generation` — PASS; `git status` clean — PASS. Registry state moved
  `AUTHORIZED → IN_PROGRESS` under this entry (§4 row appended before implementation began).

## Implementation summary

**Stage registry and precondition engine** (`agentos_dashboard/services/stages.py`,
`agentos_dashboard/prompt_templates/schema.py`). A coded, independently-maintained
`StageSchema` for all ten DASH stages (id, title, role, branch, prompt path, report path,
prerequisite) lives in `prompt_templates/schema.py` and calls nothing. `services/stages.py`
parses `STAGE_REGISTRY.md` §3's live Markdown table and cross-checks every row against that coded
schema. Missing, malformed, duplicate, unknown, out-of-order, invalid-state, and mismatched rows
become `ConsistencyFinding`s and block generation. The engine evaluates the six named contract
preconditions plus two integrity gates: explicit authorization evidence (trusted queue Current
record, current-like registry state, and Human Owner authorization-log row), predecessor exactly
`COMPLETE` (never merely `SUPERSEDED`), clean tree, exact coded branch, sole-active agreement
across the queue, both mirrors, and registry, no blocking open question, registry/schema
consistency, and complete readable tracked SSP/stage-prompt sources. Missing, degraded,
ambiguous, or inconsistent evidence fails closed.

**Prompt renderer and in-memory store/audit** (`agentos_dashboard/services/prompts.py`,
`agentos_dashboard/prompt_templates/placeholders.py`). `generate_stage_prompt` evaluates the
precondition report and either renders, hashes, stores, and audits a new prompt, or audits the
refusal and returns the unmet report untouched. The rendered Markdown is the tracked
`stage-prompts/README.md` SSP section plus the stage's own `stage-prompts/DASH-0XX.md` text,
verbatim after `{{branch}}`/`{{head_sha}}`/`{{tree_state}}`/`{{date}}`/`{{precondition_report}}`
substitution (the grammar `stage-prompts/README.md` documents; no current stage document uses it
yet, so substitution is presently a structural no-op, exercised by synthetic fixtures) — never a
duplicated or rewritten copy, per that document's own rule 2. Every live, repository-derived fact
is embedded only inside a fenced ` ```text ` block explicitly labeled `(data)`, never inlined into
prose (SC-20): a hostile branch name or finding message can only ever read as inert data. The
whole rendered document is SHA-256 hashed; `GeneratedPromptRecord`/`AuditEntry` are held in
`PromptStore`/`PromptAuditLog`, process-lifetime in-memory stores — `DATA_MODEL.md` §3 assigns
`dashboard.db` persistence to DASH-008, which does not exist yet, so this mirrors
`api.acknowledgments.AcknowledgmentStore`'s disposable-cache posture exactly. A caller-supplied
`client_token` makes a repeat POST idempotent (replay returns the original record without
re-rendering or re-auditing).

**Governance browser and search** (`agentos_dashboard/services/governance.py`, added by
PLAN-001). A fixed, coded allowlist of fifteen documents (`README.md`, `self-governance.yaml`,
`docs/AGENT_PROTOCOL.md`, `docs/CONTEXT.md`, the four governance mirrors, `docs/DECISION_LOG.md`,
`docs/GOVERNANCE_AUDIT.md`, and the five top-level Markdown documents under
`docs/implementation/orchestration/` — its YAML state files are data already covered by
`parsing.orchestration`, not "package documents" in DR-090's sense), each addressed only by an
opaque coded identifier. `render_document`/`search_governance` look the identifier up in a fixed
`dict` built at import time; an identifier not already a key — including every traversal-shaped
string — is refused before any filesystem call, structurally rather than by a runtime check.
Rendering is a small, dependency-free Markdown-*lite* transform (headings with stable anchors,
fenced code, bold, inline code, and code-span/Markdown cross-reference links resolved only
between allowlisted documents) — not a
CommonMark implementation, since this package's `dashboard` dependency group is FastAPI/Jinja2/
Uvicorn only and adding a Markdown library is outside this stage's authorization. Every text
fragment is escaped with `html.escape` before assembly; malformed UTF-8 or an unterminated fenced
code block degrades to the raw-source fallback plus a `governance_render_degraded` finding, never
a crash. Full-text search is bounded: `q` over 200 characters and traversal-shaped queries are
refused before any file is read; results are capped at 200.

**Wiring**: EP-13 (`GET /stages`), EP-14 (`GET /prompts/{uuid}/export`), EP-21
(`POST /prompts/generate`), EP-07 (`GET /governance/docs`, `/governance/docs/{name}`), and EP-08
(`GET /governance/search`) added to `agentos_dashboard/api/routes.py`; `PromptStore`/
`PromptAuditLog` constructed once per process in `main.py`, following the existing
`AcknowledgmentStore` pattern. `PG-04` (`/stages`) and `PG-08` (`/governance`,
`/governance/{doc_id}`) added to `agentos_dashboard/web/routes.py` and templates; `base.html`'s
"Stages & Prompts" and "Governance" navigation entries are enabled (previously `disabled`).
`app.js` gained the generate/copy/export interaction (confirmation dialog, CSRF header, Clipboard
API with an `execCommand` fallback, a client-side Blob download so "export" and "preview" are
byte-identical by construction, and visible failure states for all three actions).

## Architecture decisions

None requiring `DECISIONS.md`. One implementation judgment call, recorded here rather than as a
formal decision: `EP-14`'s export endpoint returns the `{ok, data, error}` envelope (matching
`API_SPEC.md` §1's "every response" rule) rather than a raw `Content-Disposition` file download;
the web page's "Export .md" button constructs the download client-side from the fetched JSON via
a Blob, which is what actually makes "export bytes hash-match the preview" trivially true rather
than merely tested.

## Created files

`agentos_dashboard/prompt_templates/{__init__,schema,placeholders}.py`;
`agentos_dashboard/services/{stages,prompts,governance}.py`;
`agentos_dashboard/api/{stages,prompts,governance}.py`;
`agentos_dashboard/web/templates/{stages,governance,governance_doc}.html`;
`agentos_dashboard/tests/test_prompt_templates_{schema,placeholders}.py`;
`agentos_dashboard/tests/test_services_{stages,prompts,governance}.py`;
`agentos_dashboard/tests/test_api_{stages,prompts,governance}.py`;
`agentos_dashboard/tests/test_web_{stages,governance}.py`;
`agentos_dashboard/tests/test_dash007_no_repository_write.py`;
`docs/reports/agentos-dashboard/STAGE-07-completion.md` (this report).

## Modified files

`agentos_dashboard/api/routes.py` (EP-13/14/21/07/08 wiring); `agentos_dashboard/main.py`
(`PromptStore`/`PromptAuditLog` construction and injection); `agentos_dashboard/web/routes.py`
(`/stages`, `/governance`, `/governance/{doc_id}` pages); `agentos_dashboard/web/static/app.js`
(generate/copy/export handling); `agentos_dashboard/web/static/style.css` (disabled-button,
`<pre>` wrapping, and governance-doc styling); `agentos_dashboard/web/templates/base.html`
(enabled the "Stages & Prompts" and "Governance" navigation links);
`docs/agentos-dashboard/STAGE_REGISTRY.md` (§3 DASH-007 state `AUTHORIZED → IN_PROGRESS`; §4 the
initial-start preflight row — the sanctioned in-stage edit set, per this stage's own SSP).

## Deleted files

None.

## Database changes

None — `dashboard.db` does not exist yet (DASH-008's responsibility); `PromptStore`/
`PromptAuditLog` are process-lifetime in-memory stores.

## API changes

Six new read-only-to-the-repository endpoints under `/dash/api/v1`: `GET /stages`,
`GET /prompts/{uuid}/export`, `POST /prompts/generate` (process-lifetime in-memory prompt/audit
mutation only, per `API_SPEC.md` §3 — no repository file or database is ever written), `GET /governance/docs`,
`GET /governance/docs/{name}`, `GET /governance/search`.

## UI changes

Two new pages: `/stages` (PG-04, the stage registry with a live precondition panel per stage, a
generate action disabled with itemized reasons when preconditions are unmet, and a
copy/export-capable preview area) and `/governance` + `/governance/{doc_id}` (PG-08, a document
list, bounded search, rendered/raw toggle, and in-page heading anchors). `base.html`'s navigation
enables both entries.

## Security changes

SC-20 (prompt-injection resistance: live facts embedded only in fenced `(data)` blocks); SC-04
(escape-first governance rendering, no inline HTML pass-through); the governance browser's
identifier-as-opaque-key design structurally satisfies the traversal-refusal requirement without
a runtime path check. No new Git-mutating capability, no new subprocess call, no new network call,
no new dependency.

## Tests added

96 new tests across eleven files (see Created files). Every DASH-007.md acceptance criterion has
a direct test (see the Acceptance-criteria checklist below).

## Validation

- **Focused**: `pytest agentos_dashboard/tests/test_{prompt_templates_schema,prompt_templates_placeholders,services_stages,services_prompts,services_governance,api_stages,api_prompts,api_governance,web_stages,web_governance,dash007_no_repository_write}.py` → 96 passed.
- **`pytest agentos_dashboard/tests`** → 519 passed, 1 failed. The one failure
  (`test_parsing_task_queue.py::test_real_current_task_is_recognized_as_a_valid_empty_state`) is
  pre-existing and content-driven, not a defect in this diff: it asserts the *live*
  `docs/current_task.md` currently declares zero Current tasks, which was true when the test was
  written but has been false since the DASH-007 authorization commit (`089750f`, before this
  session began) recorded DASH-007 as `Current`. `git diff --stat` confirms neither
  `docs/current_task.md` nor this test file is touched by this diff — the failure reproduces
  identically against the pre-implementation `HEAD`.
- **Regression**: `python -m pytest tests --collect-only -q` → unchanged (this diff touches no
  `tests/`/`src/`/`agentos_workflow/` file); `pytest tests agentos_workflow/tests` → 5076 passed,
  34 deselected (unchanged from the pre-session baseline; `agentos_dashboard/**` is not part of
  either default collection).
- **Quality**: `ruff check --no-cache .` → All checks passed. `black --check .` → all files
  unchanged (two files needed one reformatting pass during this session, applied and re-verified
  clean). `mypy --no-incremental agentos_dashboard` → clean except two files this diff does not
  touch (`services/legacy_workflow.py`, `services/workflow.py`), each already skipping four/three
  `ai_workflow_engine.*` submodules for a missing `py.typed`/stub marker — pre-existing,
  reproduced identically against files `git diff --stat` shows untouched. `mypy --no-incremental
  src` → clean (85 files). `mypy --no-incremental agentos_workflow` → clean except
  `cli_auto.py` (3 pre-existing errors, same untouched-file class, confirmed via `git diff
  --stat`). `pre-commit run --all-files` → `ruff check`, `black`, `mypy` all Passed; no hook
  mutated any file outside this stage's changed-file set (`git status --porcelain` re-checked
  immediately after). `git diff --check` → clean.
- **Governance**: `workflowctl verify --config self-governance.yaml` → `task-state` PASS,
  `governance` PASS, `registries` PASS (26 stages across 2 registries), `handover` PASS; `git`
  FAILs with exactly one finding, `upstream_missing`, on `feature/dash-007-prompt-generation` —
  a freshly-created, not-yet-pushed stage branch has no upstream by construction, the same
  pre-existing, documented, tolerated condition every prior DASH/AUTO stage's mid-implementation
  verification has recorded (`STAGE_REGISTRY.md` §2 rule 17's own named example).
- **Changed-file scope audit**: every created/modified path is inside
  `agentos_dashboard/prompt_templates/**`, `agentos_dashboard/services/**`,
  `agentos_dashboard/api/**`, `agentos_dashboard/web/**`, `agentos_dashboard/tests/**`, or this
  stage's sanctioned `STAGE_REGISTRY.md`/report edits — nothing under `src/`, `tests/`,
  `scripts/`, `examples/`, `pyproject.toml`, `.pre-commit-config.yaml`, `self-governance.yaml`,
  `docs/implementation/orchestration/**`, or `handover/**` was touched.
- **Named security checks**: traversal-shaped governance document identifiers refused without a
  filesystem call outside the allowlist (`test_render_document_traversal_shaped_identifier_is_refused`,
  `test_traversal_shaped_identifier_is_404_not_500`); hostile script-injection-shaped content
  renders as inert escaped text at both the render layer and the live HTML page
  (`test_render_document_escapes_hostile_script_content`,
  `test_governance_search_page_escapes_hostile_content`,
  `test_governance_doc_page_escapes_hostile_body_content`); no repository write method or
  write-mode `open()` call exists anywhere in the new modules
  (`test_dash007_no_repository_write.py`, source-AST-scanned).

## Acceptance-criteria checklist

- Generating a prompt for a stage whose predecessor is not `COMPLETE` is refused — **PASS**
  (`test_generate_stage_prompt_refused_for_unmet_preconditions_and_audited`,
  `test_generate_refuses_stage_with_unmet_preconditions`).
- Export bytes hash-match the preview — **PASS** (`test_export_bytes_hash_match_the_preview`,
  `test_generate_success_and_export_bytes_hash_match_preview`).
- An unknown governance document identifier is refused (404) — **PASS**
  (`test_unknown_document_is_404`, `test_governance_doc_page_unknown_id_is_404`).
- A traversal-shaped identifier or query is refused without touching the filesystem outside the
  allowlist — **PASS** (`test_render_document_traversal_shaped_identifier_is_refused`,
  `test_traversal_shaped_identifier_is_404_not_500`,
  `test_search_governance_refuses_traversal_shaped_query_before_file_reads`,
  `test_search_traversal_shaped_query_is_422`).
- A `q` over 200 chars is refused — **PASS** (`test_search_query_too_long_is_422`,
  `test_search_governance_rejects_overlong_query`).
- A search against hostile (script-injection-shaped) document content renders as inert escaped
  text — **PASS** (`test_governance_search_page_escapes_hostile_content`,
  `test_search_finds_hostile_content_only_as_plain_text`).

## Final independent machine-review correction addendum (2026-08-10)

The final bounded Codex review found and corrected four in-scope substantive defect groups; no
Claude correction loop followed:

1. **DASH007-REV-001 (HIGH)** — Registry/schema findings were display-only and did not gate
   generation; duplicate/malformed/out-of-order rows, non-`COMPLETE` predecessor semantics,
   ambiguous task evidence, stale `BLOCKED` state, and cross-mirror/registry active-stage
   disagreement could therefore pass too far. Corrected in `services/stages.py` with fail-closed
   integrity checks and direct regressions.
2. **DASH007-REV-002 (HIGH)** — Missing/truncated/malformed tracked prompt sources could silently
   render as incomplete text, and fixed triple-backtick fences were not delimiter-safe for hostile
   live facts. Corrected in `services/prompts.py` with source-availability gating, a final evidence
   recheck, adaptive data fences, deterministic-byte tests, and changed-live-HEAD coverage.
3. **DASH007-REV-003 (MEDIUM)** — Traversal-shaped search queries were not refused; the
   Markdown-lite sentinel scheme could crash on hostile NUL-shaped input; malformed UTF-8 did not
   degrade with a finding; and normal allowlisted Markdown links were not resolved. Corrected in
   `services/governance.py`, its routes/templates, and service/API/web regressions; incomplete
   search-corpus reads now produce visible deterministic findings rather than silent omissions.
4. **DASH007-REV-004 (MEDIUM)** — Prompt/client route UUIDs were not structurally validated, and
   generate/copy/export browser failures could remain silent. Corrected in `api/prompts.py`,
   `api/routes.py`, `web/static/app.js`, and API/web regressions.

Final review evidence: 96 focused tests pass; the full Dashboard suite is 519 passed / 1 known
authorization-baseline failure; engine/agent regressions are 5,076 passed / 34 deselected; Ruff,
Black, canonical `mypy`, `git diff --check`, and dashboard startup check pass. The scoped
`mypy --no-incremental agentos_dashboard` and `... agentos_workflow` historical errors reproduce
byte-for-byte in an archive of authorization HEAD `089750f`, while no new scoped type error is
present. `workflowctl verify` has exactly the expected `upstream_missing` Git finding; task-state,
governance, registries, and handover pass. This addendum records machine review and correction,
not Human Owner approval.

## Known limitations / Risks / Deviations from plan

- The `{{branch}}`/`{{head_sha}}`/`{{tree_state}}`/`{{date}}`/`{{precondition_report}}`
  placeholder grammar is implemented and tested against synthetic fixtures, but no tracked
  `stage-prompts/*.md` document currently uses one of these tokens — substitution is a structural
  no-op against today's real documents. This is a pre-existing gap in the *documents*, not in
  this stage's renderer, and needs a separate documentation decision if the Human Owner wants a
  future stage prompt to actually use the grammar.
- The governance browser's Markdown-*lite* renderer supports headings, fenced code, bold, inline
  code, allowlist-only code-span and Markdown cross-reference links, and bullet lists; it does
  not support tables, nested lists,
  numbered lists, or blockquotes as distinct HTML constructs — unrecognized syntax renders as
  plain escaped paragraph text rather than a crash or a missing section. Full CommonMark fidelity
  would require a dependency this stage is not authorized to add (OD-D9).
- The "orchestration package documents" clause of DR-090 was read as the five top-level Markdown
  files directly under `docs/implementation/orchestration/` (`README.md`, `architecture-v3.md`,
  `decision-log.md`, `implementation-plan.md`, `session-protocol.md`); its `evidence/`,
  `handoffs/`, `prompts/`, `reviews/`, and `stages/` subdirectories and its YAML state files are
  excluded as evidence artifacts and already-covered data, respectively, not "package documents"
  in DR-090's sense. This is a reasonable, defensible reading rather than a specified list;
  flagged here in case the Human Owner wants a different allowlist scope.
- `GET /prompts/{uuid}/export` returns the `{ok, data, error}` JSON envelope rather than a raw
  file download with `Content-Disposition`; the web page's "Export .md" button performs the
  actual file save client-side from the already-fetched JSON via a Blob. This keeps every
  response uniform per `API_SPEC.md` §1 and is what makes the export-hash-matches-preview
  acceptance criterion true by construction rather than merely by test coverage.

## Rollback instructions

Revert this stage's exact diff (the created files above, plus the six modified files and the
`STAGE_REGISTRY.md` state/log edit). No database, dependency, or engine (`src/`,
`agentos_workflow/`) file is touched, so rollback is a pure file-level revert with no migration
concern.

## Git diff summary

```
 agentos_dashboard/api/routes.py           |  79 +++++++++++++
 agentos_dashboard/main.py                 |  10 +-
 agentos_dashboard/web/routes.py           |  57 +++++++++
 agentos_dashboard/web/static/app.js       | 108 ++++++++++++++++
 agentos_dashboard/web/static/style.css    |  25 ++++
 agentos_dashboard/web/templates/base.html |   4 +-
 docs/agentos-dashboard/STAGE_REGISTRY.md  |   4 +-
 7 files changed, 283 insertions(+), 4 deletions(-)
```
Plus 26 new untracked files: 3 under `prompt_templates/`, 3 under `services/`, 3 under `api/`, 3
under `web/templates/`, 11 new test files under `tests/`, and this report (1,515 lines of new
production/template code; 1,010 lines of new test code).

## Recommended commit message

```
feat(dashboard): add stage registry and gated prompt generation (DASH-007)
```

## Final stage status: COMPLETE

## Confirmation

The next stage (DASH-008) was **not** started, selected, or prepared. No commit, push, merge,
branch creation or switching, rebase, reset, amend, or stash operation was performed. The
complete diff is left in the working tree for Human Owner review.

## Addendum — Human Owner approval and closure (2026-08-10)

The Human Owner reviewed this report and the implementation diff, typed the two exact `APPROVE`
confirmations required by `scripts/workflow-approve.sh`, and approved the Conventional Commit
message `feat(dashboard): add stage registry and gated prompt generation (DASH-007)`. The script then performed the deterministic governance closeout
recorded in `docs/DECISION_LOG.md`'s matching entry and staged the approved implementation
together with the generated closeout records in one local commit. This commit's hash, and any
later publication or merge, are recorded separately — a commit cannot record its own hash.
