# AgentOS Dashboard — Test Strategy

| Field | Value |
|---|---|
| **Title** | AgentOS Dashboard — Test Strategy |
| **Purpose** | Test classes (TC-##), mock-vs-real policy, per-stage gates, and coverage expectations. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Dashboard implementation session · Human Owner via independent review (approval) |
| **Dependencies** | All Tier 1 documents |
| **Related Documents** | `STAGE_REGISTRY.md`, `docs/AGENT_PROTOCOL.md` |

## Table of Contents
1. Principles · 2. Test Classes · 3. Mock vs Real · 4. Gates · 5. Coverage ·
6. Decision References · 7. Open Questions · 8. Future Revisions

## 1. Principles

Dashboard tests live in `agentos_dashboard/tests/` and run via
`pytest agentos_dashboard/tests` (OD-D8). The engine suite (`pytest`, `testpaths=["tests"]`)
must remain byte-identical in collection count before and after every stage — this is a
mandatory regression assertion of every stage report, proven with
`python -m pytest tests --collect-only -q`.

## 2. Test Classes

| ID | Class | Content |
|---|---|---|
| TC-01 | Parser units | PROJECT_STATE fields, task-queue sections and mirrors, decision-log entries, implementation-state YAML |
| TC-02 | Malformed documents | missing headings, broken tables, truncated files, non-UTF8, invalid YAML → raw fallback + finding, never a crash |
| TC-03 | Repository adapter | traversal (`../`, absolute, encoded), symlink escape, deny-list, caps — real tmpdirs |
| TC-04 | Git adapter | temporary real Git repos: init/commit/tag/branch/merge/dirty/detached/missing-upstream; timeout mocked |
| TC-05 | API | envelope shape, CSRF negative, idempotency replay, typed 404/422, Host rejection |
| TC-06 | UI/template render | escaping proof: hostile `<script>`, `javascript:` links neutralized |
| TC-07 | Security | CSRF, XSS, traversal, symlink, redaction (fixture secrets absent from all output/logs), bind refusal, rebinding |
| TC-08 | Stale/contradiction | fixtures with deliberate PROJECT_STATE vs TASK_QUEUE conflicts; fingerprint change detection |
| TC-09 | Large files | 5 MB fixture → capped render + finding |
| TC-10 | Snapshot/golden | golden-file renders of key pages from a fixture repo |
| TC-11 | Failure recovery | mid-write crash → transaction intact; lockfile contention |
| TC-12 | Append-only audit | source scan (no UPDATE/DELETE) + behavioral assertion |
| TC-13 | Precondition engine | refusal matrix incl. out-of-order stage, dirty tree, wrong branch |
| TC-14 | Checksum/handover | recompute vs manifest; tampered fixture flagged |
| TC-15 | Packaging/startup | `--check` smoke, port-in-use, non-loopback refusal |
| TC-16 | End-to-end | full page set vs fixture repo and read-only vs this repository |
| TC-17 | Accessibility | landmarks/labels/tab-order assertions at template level |
| TC-18 | Engine-suite regression | collection-count equality gate |

## 3. Mock vs Real

Mock only: time, subprocess timeouts, clipboard. Real: filesystem tmpdirs, real Git
repositories, real `sqlite3`.

## 4. Gates (every stage)

`pytest agentos_dashboard/tests` (focused + full dashboard suite) ·
`python -m pytest tests --collect-only -q` collection-count equality + `pytest tests` green
(TC-18) · `ruff check .` · `black --check .` · `mypy agentos_dashboard` (the repo's configured
`mypy` gate covers `src/` and stays untouched) · `pre-commit run --all-files` ·
`git diff --check` · changed-file scope audit · stage-named security checks.

## 5. Coverage

Qualitative rule: every SC control and every included DR must map to at least one TC instance
by DASH-010; the mapping is recorded in stage reports. No numeric coverage floor is imposed on
the dashboard package in MVP.

## 6. Decision References
DD-01, DD-03; OD-D8 disposition.

## 7. Open Questions
None open.

## 8. Future Revisions
A numeric coverage floor may be added post-MVP via `MASTER_PLAN.md` §8.
