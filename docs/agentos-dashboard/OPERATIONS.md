# AgentOS Dashboard — Operations Manual

| Field | Value |
|---|---|
| **Title** | AgentOS Dashboard — Operations Manual |
| **Purpose** | Start/stop, the manual handover manifest-refresh procedure, `dashboard.db` backup/disposal, troubleshooting, and the explicit statement of prohibited operations for the running dashboard. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Dashboard implementation session · Human Owner (approval) |
| **Dependencies** | `ARCHITECTURE.md` §5, §6; `SECURITY_MODEL.md` §5 |
| **Related Documents** | `MVP_SCOPE.md` §4; `STAGE_REGISTRY.md` |

## Table of Contents
1. Start · 2. Stop · 3. Configuration · 4. Manual Handover Manifest Refresh · 5. `dashboard.db`
Backup and Disposal · 6. Troubleshooting · 7. Prohibited Operations · 8. Decision References ·
9. Open Questions · 10. Future Revisions

## 1. Start

From the root of the repository the dashboard should observe, with the `ai-workflow-engine`
Conda environment activated and the optional `dashboard` extra installed
(`pip install -e '.[dashboard]'`, `DECISIONS.md` DD-09):

```bash
conda activate ai-workflow-engine
python -m agentos_dashboard
```

The process prints the exact URL to open (default `http://127.0.0.1:8642`), refuses any
non-loopback bind before it does anything else (SC-01), and acquires a single-instance PID
lockfile keyed to the resolved repository root (SC-02/SC-24) — a second `python -m
agentos_dashboard` against the same root refuses to start rather than silently running two
servers. This is the two-command cold-start path `MVP_SCOPE.md` §4's acceptance criterion
measures: activate the environment, then run the module.

`python -m agentos_dashboard --check` validates configuration, briefly acquires and releases the
real single-instance lock, builds the repository snapshot once, and opens one local-database
connection, all without binding a socket — the fast smoke test to run before trusting a fresh
environment or a changed `AWED_*` setting (`TEST_STRATEGY.md` TC-15). It therefore refuses a live
lock conflict just like a real start and leaves the advisory lock released on every exit path.

## 2. Stop

`Ctrl-C` (`SIGINT`) or `SIGTERM` the process. Uvicorn shuts down the ASGI app, and the PID
lockfile is released in the `finally` block that wraps the server run — no separate stop command
or cleanup step exists, and none is needed. If the process is killed with `SIGKILL` (or the host
loses power) the advisory lock is released by the kernel on process exit regardless, so a later
start never wedges on a stale holder (`api/lock.py`).

## 3. Configuration

Every setting is an `AWED_`-prefixed environment variable, validated eagerly before any socket or
lockfile is touched (SC-01, SC-10). No `.env` file is ever read.

| Variable | Default | Notes |
|---|---|---|
| `AWED_HOST` | `127.0.0.1` | Must be a loopback address (`127.0.0.1`, `localhost`, `::1`) — anything else is refused at startup, never silently rebound. |
| `AWED_PORT` | `8642` | `1..65535`. |
| `AWED_REPO_ROOT` | the current working directory | The one repository this instance may read; resolved once at startup. |

The full page set is visible at `/settings` (PG-12) once the server is running: repository root,
bind address/port, the accepted `Host` header set, every configured cap, and the current
process's lock status — read-only, with a browser-side "copy config" action that copies those
displayed values to the clipboard and makes no server request.

## 4. Manual Handover Manifest Refresh

MVP deliberately ships no refresh *button* for `handover/PROJECT_CHECKSUM.md` (OD-D6, deferred to
DR-906): the Handover page (`/handover`) is read-only and shows the manifest's own documented
preamble verbatim, plus a per-record VERIFIED/MISMATCH/MISSING comparison against the real files.
When the dashboard reports a mismatch or a stale narrative (DR-101), refresh the manifest by hand
from a shell, following `handover/PROJECT_CHECKSUM.md`'s own instructions — recompute each row's
size and digest and rewrite the table:

```bash
f=handover/PROJECT_HANDOVER.md
printf '%s\t%s\t%s\n' "$f" "$(wc -c < "$f")" "$(sha256sum "$f" | cut -d' ' -f1)"
```

Update the existing `handover/PROJECT_HANDOVER.md` row in the manifest with that size and full
digest. Do not add a row for `PROJECT_CHECKSUM.md` itself: a manifest cannot stably contain its own
digest, and the repository's manifest/checker deliberately contains only the narrative row.
During normal Human Owner approval, `scripts/workflow-approve.sh` appends the closeout narrative
and regenerates this row automatically before it runs `check-handover`; the manual command above
is the equivalent recovery procedure when the pair was edited outside that closeout transaction.
After the authorized update, reload `/handover` and confirm the row reads VERIFIED. The dashboard
never performs this refresh itself — it has no write path into `handover/**` or anywhere else in
the repository (`SECURITY_MODEL.md` §5).

## 5. `dashboard.db` Backup and Disposal

`data/agentos_dashboard/dashboard.db` (plus its `logs/audit.jsonl` mirror in the same directory)
is the dashboard's own local, **non-authoritative** SQLite store for manually recorded run
records, draft approvals, findings, notes, and consistency acknowledgments (`DATA_MODEL.md`). It
is git-ignored (`/data/agentos_dashboard/` in `.gitignore`) and holds nothing the engine's own
governance record depends on — every value the dashboard treats as authoritative is read live
from the repository's tracked files on every request.

**Backup.** Copy the directory while the dashboard process is stopped, or use SQLite's own
online-backup-safe tooling if a live copy is needed. Choose an absolute path outside the runtime
directory so disposal does not remove the backup:

```bash
backup_path=/absolute/path/to/dashboard.db.backup
sqlite3 data/agentos_dashboard/dashboard.db ".backup '$backup_path'"
```

Every write goes through one `sqlite3.Connection` per request inside a transaction, so a
`.backup` invocation never observes a torn write.

**Disposal.** Stop the dashboard process first (`kill %1`, `Ctrl-C`, or wait for the
`SIGTERM`/lockfile-release each release path already performs), then delete the directory:

```bash
rm -rf data/agentos_dashboard
```

The next `python -m agentos_dashboard` (or `--check`) recreates an empty, freshly schema'd
database on first use — no migration, seed data, or manual recreation step is required, and no
governance record, task status, or handover fact is lost, because none of them live there.

## 6. Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `configuration error: non-loopback bind address refused` | `AWED_HOST` is not `127.0.0.1`/`localhost`/`::1` | Unset `AWED_HOST` or set it to a loopback value; the dashboard has no remote-exposure mode (`SECURITY_MODEL.md`). |
| `another dashboard process (pid N) already holds the lock` | A second instance was started against the same repository root | Stop the process holding pid `N`, or point the new instance at a different `AWED_REPO_ROOT` if that is genuinely intended. |
| `failed to bind http://127.0.0.1:PORT` | Another process (dashboard or otherwise) already owns that port | Stop the other process, or set a free `AWED_PORT`. |
| A page shows the `STALE` badge in the header | The repository changed after the held snapshot was built | Open Overview and click **Refresh**. Reloading alone intentionally keeps the stale snapshot visible (TR-05); a `409 SNAPSHOT_BUILDING` response means a rebuild is already under way, not stuck. |
| `--check` reports that another process holds the lock | A dashboard instance for this repository is already running | Use the running instance or stop it cleanly, then rerun `--check`; never delete the persistent lock sentinel to bypass a live advisory lock. |
| `--check` reports an unsupported or malformed database | `dashboard.db` is incompatible/corrupt | Stop the dashboard, preserve a backup if the local drafts matter, then follow §5 disposal. Repository/Git/governance authority is unaffected. |
| A page shows a `Traceback`-free generic error page/JSON envelope | An unexpected exception was contained at the outer boundary (SC-05) | Nothing was logged to the browser by design (SC-09); check the process's own stderr for the real cause, and treat it as a bug report if the input was not itself malicious/malformed. |
| Handover page shows `MISMATCH`/`MISSING` rows | `handover/PROJECT_CHECKSUM.md` disagrees with the real files | Follow §4 above. |
| `--check` fails with a database-related error | `data/agentos_dashboard/` is unwritable or the disk is full | Fix filesystem permissions/space for the repository's working tree; the dashboard never falls back to another location. |

## 7. Prohibited Operations

Restated from `SECURITY_MODEL.md` §5 for operators who read this manual and not that one: no
arbitrary shell execution; no Git mutation (commit/push/merge/tag/branch-delete/history rewrite);
no automatic lifecycle transition; no automatic task selection; no unattended agent execution; no
modification of authoritative governance documents; no write under
`docs/implementation/orchestration/`; no network exposure beyond loopback; and the dashboard never
reads or serves `.env*` files or its own `data/agentos_dashboard/**` store as if it were
repository content. Every write this application performs is confined to
`data/agentos_dashboard/**`, and nothing above can widen that boundary — including this manual,
which describes operating the dashboard as delivered, not extending it.

## 8. Decision References
DD-01, DD-03, DD-09, DD-16.

## 9. Open Questions
OD-D6 (manual-only handover refresh in MVP, restated in §4); OD-D7 (no `gh` integration, so no
merge-status action exists to document here).

## 10. Future Revisions
New operational procedures are appended; a change to what the dashboard is permitted to do
(§7) requires the same MVP-scope-change process as `SECURITY_MODEL.md` §5 itself.
