# DASH-002 — Repository Adapter and Read-Only Snapshot

| Field | Value |
|---|---|
| **Stage** | DASH-002 · Role: Dashboard implementation session (Backend discipline) |
| **Branch** | `feature/dash-002-repo-adapter` |
| **Commit message** | `feat(dashboard): add read-only repository and git adapters (DASH-002)` |
| **Report** | `docs/reports/agentos-dashboard/STAGE-02-completion.md` |
| **Status/Version** | Draft · 1.0 |

Apply the Standard Stage Protocol in `README.md` in full.

## Canonical Prompt

You are the **Dashboard implementation session** executing **DASH-002 — Repository adapter and
read-only snapshot**. Preconditions: DASH-001 `COMPLETE`; recorded authorization "I authorize
DASH-002"; branch `feature/dash-002-repo-adapter` from clean `main`.

**Allowed**: create `agentos_dashboard/{__init__.py, core/__init__.py, core/paths.py,
core/files.py, core/gitread.py, core/snapshot.py}`, `agentos_dashboard/tests/**` (+ fixtures),
plus SSP-required documentation/report updates. Stdlib + already-pinned dependencies only
(OD-D9 does not gate this stage).

**Build**: (a) root-confinement path resolver rejecting traversal, absolute escapes, and
symlinks leaving the root, with the deny-list (`.env*`, `data/agentos_dashboard/**`, `.git/**`
except via gitread) and per-file read caps; (b) Git read adapter as named functions over
`subprocess.run` with fixed argv (`status --porcelain=v2 --branch`, bounded `log` with fixed
format, `branch -a --format`, `tag --format`, `rev-parse`, `diff --stat <sha>..<sha>`,
`diff --check`), `LC_ALL=C`, 5 s timeout, typed errors, never any mutating verb; (c) snapshot
builder producing an immutable object with fingerprint (watched-file mtimes per
`../SOURCE_OF_TRUTH.md` §3 + HEAD) and staleness test.

**Tests**: traversal/symlink/deny-list/caps against tmpdirs; git functions against temporary
real Git repositories (init/commit/tag/branch/merge/dirty/detached/missing-upstream);
fingerprint stability; engine-suite collection unchanged.

**Out of scope**: HTTP, parsing semantics, persistence, any new dependency.

Write the report, recommend the commit message above, then STOP per SSP.

## Stage-Specific Notes

Risk: git output localization → force `LC_ALL=C`. Reference contracts: `../ARCHITECTURE.md` §3;
controls SC-06..SC-08, SC-25, SC-29. The engine's own read-only `GitClient`
(`src/ai_workflow_engine/git/`) is prior art for the allowlist discipline but must not be
imported or modified.
