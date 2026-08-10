# AgentOS Dashboard — Security Model

| Field | Value |
|---|---|
| **Title** | AgentOS Dashboard — Security Model |
| **Purpose** | Threat model, security controls (SC-##), operation classification, and prohibited operations for the dashboard. Subordinate to `docs/AGENT_PROTOCOL.md`; may only strengthen it. |
| **Status** | Draft |
| **Version** | 1.2 |
| **Owner** | Dashboard implementation session · Human Owner via independent security review (approval) |
| **Dependencies** | `MASTER_PLAN.md` §2; `ARCHITECTURE.md` |
| **Related Documents** | `docs/AGENT_PROTOCOL.md`, `TEST_STRATEGY.md`, `API_SPEC.md` |

## Table of Contents
1. Trust Boundary · 2. Threats · 3. Controls · 4. Operation Classification ·
5. Prohibited Operations · 6. Future Multi-User Threat Sketch · 7. DASH-009 Reconciliation Log ·
8. Decision References · 9. Open Questions · 10. Future Revisions

## 1. Trust Boundary

One machine, one OS user, one operator. The filesystem boundary of the repository working copy
is the trust boundary. The browser is semi-trusted (same user, but subject to web-borne attacks
such as CSRF/DNS rebinding). Repository content is **untrusted input** (hostile Markdown must be
inert). Any local secret material (e.g., `.env*` files, key files) is out-of-bounds.

## 2. Threats

Web-borne request forgery against the local port; DNS rebinding; XSS via repository Markdown;
path traversal / symlink escape; secret disclosure (`.env*`, keys in logs); accidental
repository mutation; governance bypass via the dashboard; prompt injection via repo content
embedded in generated prompts; local DB tampering misrepresented as authority; stale/partial
state misleading the operator.

## 3. Controls (SC-01..SC-36)

| ID | Control |
|---|---|
| SC-01 | Startup refuses any non-loopback bind address |
| SC-02 | Single-user: no accounts; one process; PID lockfile |
| SC-03 | CSRF: per-session token, double-submit (cookie + `X-CSRF-Token`) on every POST; GETs side-effect-free |
| SC-04 | XSS: escape-first rendering; no inline HTML pass-through; no `javascript:` URLs |
| SC-05 | Safe Markdown: stdlib mini-renderer over `html.escape` with whitelisted tag set; CSP `default-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'`; `X-Content-Type-Options: nosniff` |
| SC-06 | Path traversal prevention: resolve + `is_relative_to(root)` on every access |
| SC-07 | Symlinks resolving outside the repository root are rejected |
| SC-08 | Repository-root confinement; deny-list: `.env*`, `data/agentos_dashboard/**`, `.git/**` (except Git adapter) |
| SC-09 | Secret redaction filter (key-like tokens, bearer patterns) on logs, errors, displayed evidence |
| SC-10 | Credential protection: dashboard loads no `.env` file; `AWED_`-prefixed environment settings only |
| SC-11 | No arbitrary command execution: no endpoint accepts a command string |
| SC-12 | Any future execution requires a versioned strict allowlist and a separate owner-approved design |
| SC-13 | Human approval is final authority; the dashboard displays and refuses, it never overrides |
| SC-14 | The `maximum_current_tasks: 1` invariant (`self-governance.yaml`) is enforced in the precondition engine |
| SC-15 | Sole-active-DASH-stage invariant checked; violation raises a finding |
| SC-16 | Only workflow-legal transitions (the engine's fixed transition table) displayed as allowed (display-only in MVP) |
| SC-17 | Task-record enforcement in prompt generation (task facts embedded; generation refused without an enrolled task) |
| SC-18 | Allowed-file scope displayed; out-of-scope changed files flagged as findings |
| SC-19 | Forbidden-file detection against stage contracts |
| SC-20 | Prompt-injection resistance: repo text embedded only in delimited data blocks marked as data, never instructions; rendered Markdown inert |
| SC-21 | Audit logging of every generation, refusal, record, and draft |
| SC-22 | Append-only audit store: no UPDATE/DELETE code path exists; JSONL mirror |
| SC-23 | Idempotent POSTs via client UUIDs; replay returns the original record |
| SC-24 | Concurrency: single-instance lockfile; local DB transactions |
| SC-25 | Cancellation/timeout: 5 s git subprocess timeout; bounded response sizes |
| SC-26 | Failure recovery: dashboard is stateless over the repo; restart rebuilds all derived state |
| SC-27 | Rollback: each stage reverts by commit; dashboard.db disposable without governance loss |
| SC-28 | Upstream protection: read-only verification of default branch `main` and its upstream (mirroring `workflowctl check-git` semantics) |
| SC-29 | No mutating Git verb exists in the codebase (tested by source scan) |
| SC-30 | Display state vs authoritative state labeled on every screen; local data tagged non-authoritative |
| SC-31 | Contradiction detection across mirrored records; findings never auto-resolved |
| SC-32 | Stale-snapshot detection via fingerprint; banner on divergence |
| SC-33 | Partial-write prevention: transactional local writes; zero repo writes |
| SC-34 | Malformed/missing Markdown or YAML degrades to raw escaped view + finding; never a crash |
| SC-35 | Large files: per-file caps, head/tail log views, lazy sectioning of large documents |
| SC-36 | Host-header allowlist (`localhost`/`127.0.0.1` with port) rejects DNS-rebinding requests |

## 4. Operation Classification (most conservative wins)

| Class | Operations |
|---|---|
| Read-only, safe for MVP | All repo/Git/handover/governance/queue/task/evidence/orchestration views; checksum verify; consistency checks; search |
| Prompt generation only | Stage prompt preview/copy/export (hash + audit) |
| Local draft record only | Run records, draft approvals, findings, notes, reconciliation marks |
| Requires explicit human confirmation | (future) handover manifest refresh via allowlist; (future) authoritative write-back |
| Deferred | Agent API execution, `gh` calls, live updates, `workflowctl` subprocess invocation (DR-912) |
| Explicitly prohibited | See §5 |

## 5. Prohibited Operations

Arbitrary shell; any Git mutation (commit/push/merge/tag/branch-delete/history rewrite);
automatic lifecycle transitions; automatic task selection; unattended agent execution;
modification of authoritative governance documents; any write under
`docs/implementation/orchestration/`; network exposure beyond loopback; reading/serving
`.env*` files or the dashboard's own `data/agentos_dashboard/**` store as repository content.
These restate and strengthen `docs/AGENT_PROTOCOL.md` ("What no agent may do") for this
application.

## 6. Future Multi-User Threat Sketch (documented only; out of scope)

Would require: real authentication, per-role authorization mapped to the roles in
`docs/AGENT_PROTOCOL.md`, server-side enforcement of reviewer independence, TLS, session
management, and a Human Owner-approved architecture and threat-model decision recorded in
`docs/DECISION_LOG.md`.

## 7. DASH-009 Reconciliation Log

Every control below was independently re-verified against the final reviewed DASH-009 tree, not
assumed from design intent or the implementation-session report. "Implemented" means production
code or a deliberate structural absence exists and the cited automated evidence exercises it.
The mandatory fresh-session review found four additional substantive defects and corrected all
four in the authorized DASH-009 surface: incomplete redaction boundaries, no whole-request body
cap, a stale-PID lockfile race, and unbounded audit-row retrieval. Stars identify controls changed
by either the implementation or independent correction pass; unstarred controls were reconciled
against DASH-002..DASH-008 code and tests.

| ID | Status | Evidence |
|---|---|---|
| SC-01 | Implemented | `settings.py` (non-loopback `AWED_HOST` refused at construction); `tests/test_settings.py` |
| SC-02 | Implemented ★ | `api/lock.py` holds a POSIX `flock(LOCK_EX\|LOCK_NB)` on an `O_NOFOLLOW` 0600 PID sentinel for process lifetime; the persistent inode avoids stale-file read/unlink replacement races and the kernel releases the lock on process exit. `tests/test_api_lock.py` covers real cross-process contention, abrupt exit, malformed content, symlink refusal, and reacquisition. |
| SC-03 | Implemented ★ | `api/security.py::SecurityMiddleware` protects every POST with same-origin double-submit cookie/header comparison via `secrets.compare_digest`; missing, malformed, and mismatched tokens fail. `RequestBodyLimitMiddleware` rejects over-cap requests before route parsing. `tests/test_api_security.py`, `tests/test_main_error_handling.py`. |
| SC-04 | Implemented ★ | Jinja2 autoescaping, a plain-text `redact_secrets` filter (never marked safe), and `services/governance.py`'s escape-first mini-renderer. XSS corpus includes scripts, event attributes, malformed/raw HTML, entities, Markdown links/code, persisted SQLite text, and reflected identifiers. `tests/test_services_governance.py`, `tests/test_web_runs.py`, `tests/test_web_overview.py`. |
| SC-05 | Implemented ★ | `api/security.py` applies CSP, `X-Content-Type-Options: nosniff`, `Cache-Control: no-store`, and the CSRF cookie. `main.py::_UnhandledErrorMiddleware` contains route exceptions *inside* that security boundary, preventing Starlette/Uvicorn from re-raising exception text for server logging; API crashes are typed JSON and browser crashes render escaped generic HTML. Status/header/cookie matrix in `tests/test_main_error_handling.py` and `tests/test_api_security.py`. |
| SC-06 | Implemented | `core/paths.py::RepositoryRoot.resolve` (lexical `..` rejection, `is_relative_to` check); `tests/test_paths.py` |
| SC-07 | Implemented | `core/paths.py` (symlink resolution checked against the root, deny-list re-checked post-resolution); `tests/test_paths.py` |
| SC-08 | Implemented | `core/paths.py::DENIED_COMPONENT_PATTERNS`/`DENIED_PREFIXES` (`.env*`, `.git`, `data/agentos_dashboard`); `tests/test_paths.py` |
| SC-09 | Implemented ★ | `core/redact.py` recognizes authorization schemes, sensitive assignment/JSON/query forms (case/spacing/newline/colon/URL/HTML encoding), and documented vendor prefixes without generic entropy heuristics. Notes, runs, findings, approval drafts, acknowledgments, audit actor/payload, and JSONL are redacted before hashing/persistence; credential-shaped identity fields are rejected. Final JSON envelopes and every repository/Git/governance/handover/task/board/prompt/legacy display boundary redact independently, while `core.files.read_text` stays byte exact (DD-17/DD-18). Outer crash containment never exposes or logs exception text. `tests/test_core_redact.py`, persistence tests for each entity, `tests/test_main_error_handling.py`, display/XSS tests, and audit DB/JSONL assertions. |
| SC-10 | Implemented | `settings.py` (`AWED_`-prefixed env only; no dotenv load); `tests/test_settings.py` |
| SC-11 | Implemented | No route accepts a command string; source-scan proof for the security module; `tests/test_api_security.py::test_no_mutating_git_verb_or_shell_call_in_security_module_source` |
| SC-12 | Implemented (structural absence) | No execution endpoint or capability exists, so there is no command allowlist to misconfigure; source-scan tests prove no route/surface accepts or launches commands. |
| SC-13 | Implemented (structural) | No code path anywhere writes an `approvals` row as anything but a local draft (`services/approvals.py`); nothing auto-transitions a stage or governance record. Proven negatively by SC-22/SC-29's source scans and by `services/approvals.py`'s own `reconciled` field always defaulting false for an unresolved target |
| SC-14 | Implemented | `services/consistency.py`'s `too_many_current_tasks` rule against `self-governance.yaml`'s `workflow.maximum_current_tasks`; `tests/test_services_consistency.py::test_too_many_current_tasks_is_detected` |
| SC-15 | Implemented | Sole-active-DASH-stage checked alongside the task-queue invariant in the same consistency pass; `tests/test_services_consistency.py` |
| SC-16 | Implemented (display-only, by design — DD-12) | `services/workflow.py`'s fixed reference transition table, never a per-task computed position; `tests/test_services_workflow.py`, `tests/test_web_stages.py` |
| SC-17 | Implemented | `services/prompts.py` refuses generation without an enrolled task record; `tests/test_services_prompts.py` |
| SC-18 | Implemented | Allowed-file scope surfaced from each stage contract; `tests/test_services_stages.py` |
| SC-19 | Implemented | `services/consistency.py` forbidden-file findings; `tests/test_services_consistency.py` |
| SC-20 | Implemented | `prompt_templates/placeholders.py` — repository text only ever fills a delimited data placeholder, never instruction text; `tests/test_prompt_templates_placeholders.py` |
| SC-21 | Implemented ★ | `services/audit.py::record_audit_event`, called from every create/generate/refusal path, recursively redacts actor/payload before DB and mirror writes; `tests/test_services_audit.py` and entity service tests. |
| SC-22 | Implemented | `storage/db.py` schema triggers reject UPDATE/DELETE on every DASH-008 entity; JSONL mirror is append-only (`O_APPEND`, never seeks backward); `tests/test_dash008_append_only.py` |
| SC-23 | Implemented ★ | UUID client token plus canonical request hash on every mutation; redaction occurs before hashing, so equivalent secret-bearing inputs normalize deterministically and original bytes are not retained. Replay/conflict tests span notes, runs, findings, approvals, and audit. |
| SC-24 | Implemented ★ | Kernel advisory process lock in `api/lock.py` plus transactional SQLite connections/`busy_timeout` in `storage/db.py`. `tests/test_api_lock.py` is genuinely cross-process and covers contention, crash release, malformed/symlink sentinels, and startup reacquisition; storage tests cover DB-lock contention and recovery. |
| SC-25 | Implemented ★ | Five-second Git subprocess timeout; capped file/evidence/search/render/note/run/audit pagination; and a 1 MiB whole-request ASGI cap before parsing. Boundary/over-boundary tests prove typed rejection and no partial state (`tests/test_api_security.py`, `tests/test_api_runs.py`, `tests/test_api_drafts.py`, `tests/test_files.py`, `tests/test_services_audit.py`, `tests/test_gitread.py`). |
| SC-26 | Implemented | `api/snapshot_cache.py` rebuilds from the repository on every process start; no in-memory state survives a restart |
| SC-27 | Implemented (structural) | Each stage's diff reverts by ordinary Git revert; `tests/test_dash008_db_deletion_safety.py` proves `dashboard.db` is disposable without losing any repository-authoritative record |
| SC-28 | Implemented | `services/git.py::build_upstream_check`, read-only; `tests/test_services_git.py` |
| SC-29 | Implemented | Source-scan tests across every module that could plausibly shell out; `tests/test_dash007_no_repository_write.py`, `tests/test_api_git.py::test_no_repository_write_in_git_module`, `tests/test_api_security.py::test_no_mutating_git_verb_or_shell_call_in_security_module_source` |
| SC-30 | Implemented | Every template labels local/draft data explicitly ("as recorded", non-authoritative badges); `tests/test_web_runs.py`, `tests/test_web_evidence.py` |
| SC-31 | Implemented ★ | `services/consistency.py` surfaces contradictions without auto-resolution; acknowledgment only records a redacted local note. DB/JSONL reconciliation exposes malformed, truncated, duplicate, missing, and orphan records. `tests/test_services_consistency.py`, `tests/test_services_audit.py`, `tests/test_api_consistency.py`. |
| SC-32 | Implemented | `core/snapshot.py` fingerprint + `is_stale()`; `tests/test_snapshot.py` |
| SC-33 | Implemented ★ | `storage/db.py` transactions prevent partial authoritative-looking DB results; mirror append/fsync precedes commit and failure rolls back, while unavoidable commit-after-mirror orphans remain detectable. Tests cover locked/read-only/corrupt/partial-schema DBs, transaction exceptions, mirror failure/symlink/unwritable paths, and reopen behavior (`tests/test_storage_db.py`, `tests/test_services_audit.py`). |
| SC-34 | Implemented (test coverage extended) | `core/files.py::_decode` (tolerant UTF-8, `errors="replace"`) underlies every parser; `parsing/orchestration.py` degrades on invalid YAML (`tests/test_parsing_orchestration.py::test_invalid_yaml_syntax_degrades_to_raw_text`). **DASH-009 adds** an explicit empty-document case for the two parsers that lacked one: `tests/test_parsing_project_state.py::test_empty_document_degrades_without_crashing`, `tests/test_parsing_decision_log.py::test_empty_document_degrades_without_crashing` |
| SC-35 | Implemented ★ | `core/files.py` enforces display/head-tail caps; truncated governance documents expose separately redacted head and tail; search/results and DB audit retrieval are bounded at the query layer, and all local free text/request bodies have caps. Boundary tests: `tests/test_files.py`, `tests/test_services_governance.py`, `tests/test_services_audit.py`, `tests/test_api_security.py`, `tests/test_api_runs.py`. |
| SC-36 | Implemented | `api/security.py::SecurityMiddleware` Host-header allowlist; `tests/test_api_security.py::test_disallowed_host_headers_are_rejected` |

The independent pass also verified graceful error behavior outside the table: normal HTML/API,
404, 405, validation 422, handled errors, and unhandled browser/API 500 responses preserve status,
format, CSP/no-sniff/no-store, and appropriate CSRF-cookie behavior without traceback, filesystem
path, secret, request body, or exception-text disclosure. `tests/_asgi_client.py` can operate in
strict re-raise mode; the strict 500 tests prove containment happens in production middleware,
not merely in the test client.

## 8. Decision References
DD-01, DD-03.

## 9. Open Questions
OD-D6, OD-D7 (both resolved as deferred); OD-D9 (resolved 2026-07-29 — FastAPI + Uvicorn +
Jinja2; the framework choice affects SC-03/SC-05 implementation detail, not intent. Loopback-only
binding is unchanged; remote exposure, authentication, and TLS remain out of scope and require
their own decisions).

## 10. Future Revisions
Any relaxation of a control is a MAJOR change requiring independent security review and Human
Owner approval.
