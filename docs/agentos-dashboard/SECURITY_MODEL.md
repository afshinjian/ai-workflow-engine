# AgentOS Dashboard — Security Model

| Field | Value |
|---|---|
| **Title** | AgentOS Dashboard — Security Model |
| **Purpose** | Threat model, security controls (SC-##), operation classification, and prohibited operations for the dashboard. Subordinate to `docs/AGENT_PROTOCOL.md`; may only strengthen it. |
| **Status** | Draft |
| **Version** | 1.0 |
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

Populated during DASH-009: each SC row gains implementation status and test evidence
references. Until then, all controls are Design status.

## 8. Decision References
DD-01, DD-03.

## 9. Open Questions
OD-D6, OD-D7 (both resolved as deferred); OD-D9 (framework choice affects SC-03/SC-05
implementation detail, not intent).

## 10. Future Revisions
Any relaxation of a control is a MAJOR change requiring independent security review and Human
Owner approval.
