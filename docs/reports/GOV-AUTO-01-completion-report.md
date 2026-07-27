# GOV-AUTO-01 Completion Report — Local Human-Gated Task Runner

- **Task:** GOV-AUTO-01 — Local Human-Gated Task Runner
- **Type:** Governance and developer experience (non-AUTO-family; no stage-registry lifecycle)
- **Repository:** `/home/afshin-jian/ai-workflow-engine`
- **Status:** Implemented and validated, **pending Human Owner approval. Not committed.**

## Authorization evidence

Human Owner, 2026-07-27: *"I authorize one new governance and developer-experience task"* —
Task ID `GOV-AUTO-01`, title `Local Human-Gated Task Runner`, with an explicit authorised file
scope, an explicit do-not-modify list, "Do not add dependencies", and the Git restriction that no
commit, push, merge, branch change, upstream change, rebase, reset, restore, amend, cherry-pick,
or stash modification may be performed.

## Initial repository state (recorded before implementation)

| Fact | Value |
|---|---|
| Worktree | **clean** — `GOV_AUTO_01_BLOCKED_DIRTY_WORKTREE` did not apply |
| Branch | `feature/auto-003-repository-validation-skills` |
| HEAD | `908be94be32f8dc42a2f66f86de61f0c121ac5ec` |
| Stashes | `stash@{0}` WIP on auto-002-orchestrator-foundation; `stash@{1}` pre-dashboard-recovery-snapshot |
| Remotes | `origin` → `https://github.com/afshinjian/ai-workflow-engine.git` (fetch + push) |
| Upstream | **none** for the current branch (AUTO-003 was never pushed) |

## Implementation summary

Three executable artifacts plus documentation, all Bash and standard tools, no new dependency:

1. **`scripts/workflow-next.sh`** — read-only preflight, then exactly one agent session.
2. **`scripts/prompts/implement-next-task.md`** — the canonical implementation prompt.
3. **`scripts/workflow-approve.sh`** — the Human approval gate and the only commit path.
4. **`docs/automation-workflow.md`** — operator documentation.

## Script behaviour

### `scripts/workflow-next.sh <claude|codex>`

Uses `set -euo pipefail`. Resolves the repository root from `BASH_SOURCE` with full symlink
resolution (never the caller's `cwd`), then confirms it is the expected repository by requiring
`self-governance.yaml` at that root — a marker check rather than a hard-coded absolute path, so a
clone elsewhere still works while an unrelated tree is refused.

Preflight, all read-only: prints branch, HEAD, `git status --short --branch`, and the stash list;
runs `git diff --check`; refuses on **any** uncommitted change (exit `4`); requires the prompt file
to exist and be non-empty (exit `5`); requires the requested agent CLI on `PATH` (exit `7`).

Agent selection is an explicit `case` allowlist — `claude` or `codex`; everything else (no
argument, two arguments, `CLAUDE`, `gemini`, a shell fragment) exits `2` without launching
anything. The command is built as a Bash array and expanded `"${cmd[@]}"`, so the prompt is one
argv element: `eval` is never used and shell metacharacters in the prompt are inert data.

Exactly one session is launched. The agent's exit status is captured and propagated verbatim.
Afterwards the script re-reads the stash count and warns if it changed. It contains no commit,
push, merge, branch, upstream, or stash-mutating call.

### `scripts/workflow-approve.sh [-m "<message>"]`

Uses `set -euo pipefail` and the same root-resolution logic. Refuses when there is nothing to
commit (exit `4`). Refuses on unresolved conflicts, detected both from porcelain status codes
(`U.`/`.U`/`AA`/`DD`) and from `git ls-files --unmerged` (exit `6`). Runs `git diff --check`
(exit `5`).

Builds the changed-file list from `git status --porcelain=v1 -z --untracked-files=all` read with
`mapfile -d ''`, so paths containing spaces, quotes, or newlines survive intact; rename/copy
records contribute both their new and origin paths. Displays the full list and `git diff --stat`.

Two gates, each requiring the **exact** token `APPROVE`: the first after reviewing the changes,
the second after seeing the precise file list and commit message. Anything else exits `7` with
nothing staged and nothing committed.

The commit message is trimmed and validated against the Conventional Commit shape
(`type(scope)!: subject`) with a minimum length, so a pasted diff, a bare filename, or a stray
shell fragment cannot become a subject (exit `8`).

Staging is `git add --` with the explicit, previously displayed path list — **never** `git add
-A` — so a file appearing after the list was shown cannot be swept in unseen. It then runs
`git diff --cached --name-status` and `git diff --cached --check`, and creates exactly one commit.

Between staging and a successful commit an `EXIT` trap fires on failure and unstages exactly the
files this script staged, via `git restore --staged` (index only). **No working-tree content is
ever discarded**, and the script says so explicitly on stderr.

On success it prints commit hash, message, committed files, and final status, ending with
`COMMIT_COMPLETE_READY_FOR_NEXT_TASK`. It never pushes, merges, changes branches, alters
upstream, or touches stashes.

## Safety properties

| Required invariant | Enforcement |
|---|---|
| No implementation without recorded authorization | Prompt requires verifying the task queue/registry; stops with `NO_AUTHORISED_NEXT_TASK` |
| One task per run | One `case`-selected session; prompt mandates a single task |
| No automatic commit after implementation | `workflow-next.sh` has no commit path |
| Commit requires explicit Human input | Two exact-`APPROVE` confirmations |
| Push and merge never performed | Absent from both scripts; asserted by regex over every executable line |
| Stashes never changed | Only `stash list`; before/after count comparison in the runner |
| Dirty worktree prevents starting | exit `4` |
| Empty worktree prevents approval | exit `4` |
| Unknown agent fails closed | `case` allowlist, exit `2` |
| No `eval`, no unsafe interpolation | Arrays + `"${cmd[@]}"`; asserted by test |
| Failed commands return non-zero | `set -euo pipefail`; agent status propagated |
| Works outside the repo root | `BASH_SOURCE` + symlink resolution; tested from `/` |
| Executable bits set | `chmod +x` applied; asserted by test |

## Tests added

`tests/test_workflow_runner_scripts.py` — **59 tests**, all against disposable temporary Git
repositories built by a `sandbox` fixture whose path deliberately contains a space. The real
repository is never staged, committed, or stashed. Agent launches are intercepted with a **PATH
stub**, not a production test flag — a test-only branch in the script would itself be an injection
surface, and stubbing PATH exercises the real launch path end to end.

`workflow-next.sh`: clean-worktree preflight success; dirty rejection (untracked and modified);
missing and empty prompt; seven unsupported-agent cases plus zero/two arguments; correct Claude and
Codex selection with the other never invoked; exactly one session; full prompt content delivered;
exit-code propagation (42); paths with spaces; invocation from outside the repository; missing
governance marker; **no Git mutation during preflight** (HEAD, branch, stash list, and reflog all
unchanged); stashes preserved.

`workflow-approve.sh`: empty-worktree rejection; seven near-miss approval tokens rejected
(including `"APPROVE "` with a trailing space); second confirmation required with nothing left
staged; eight invalid commit messages; staged list equals displayed list; exactly one commit;
clean worktree afterwards; hash/message/files/status reported; **no push** (verified against a real
bare remote whose refs stay empty); branch unchanged; stashes unchanged; unresolved conflicts
rejected; **failure after staging** (via a rejecting `pre-commit` hook) restores the index and
preserves working-tree content; untracked files included; paths with spaces; invocation from
outside the root; unrecognised argument fails closed.

Two tests were deliberately strengthened after first passing:

- The forbidden-Git-verb assertion originally used substring matching for `"git stash"`, which
  **never matched** because the scripts always write `git -C "$repo_root" stash list`. It now uses
  a regex tolerating `-C <path>`, permits read-only `stash list`, and rejects every mutating stash
  subcommand — plus a `test_forbidden_verb_regex_actually_detects_violations` guard proving the
  patterns fire on real violations and not on read-only forms.
- The post-staging failure test originally chmod-ed `.git/objects` read-only, which makes
  `git add` fail *before* the path under test. It now installs a rejecting `pre-commit` hook, a
  deterministic failure strictly after staging, and asserts the index was restored.

## Validation results

| Command | Result |
|---|---|
| `pytest tests/test_workflow_runner_scripts.py` | **59 passed** |
| `conda run -n ai-workflow-engine pytest tests agentos_workflow/tests` | **2,263 passed** |
| `conda run -n ai-workflow-engine ruff check --no-cache .` | All checks passed |
| `conda run -n ai-workflow-engine black --check .` | 122 files unchanged |
| `conda run -n ai-workflow-engine mypy --no-incremental src` | Success, 55 source files |
| `conda run -n ai-workflow-engine mypy --no-incremental agentos_workflow` | Success, 33 source files |
| `git diff --check` | clean |
| `conda run -n ai-workflow-engine workflowctl verify --config self-governance.yaml` | `task-state`, `governance`, `handover` PASS; `git` FAIL — `upstream_missing` only |
| `bash -n` (both scripts) | syntax OK |
| `shellcheck` (already installed; not installed by this task) | clean, zero findings |

The `git` FAIL is the same pre-existing `upstream_missing` condition recorded for AUTO-002 and
AUTO-003: `require_upstream: true` versus a branch that has deliberately never been pushed.

Manual smoke tests in disposable temporary repositories: unsupported agent rejected (exit 2);
approval with no changes rejected (exit 4); full approval happy path producing exactly one commit
and `COMMIT_COMPLETE_READY_FOR_NEXT_TASK`; and `workflow-next.sh` invoked from `/` with a stub
agent, delivering a 5,963-character prompt as a single argument and leaving the repository
unchanged. The smoke repositories were deleted afterwards.

## Files changed

**Created:** `scripts/workflow-next.sh`, `scripts/workflow-approve.sh`,
`scripts/prompts/implement-next-task.md`, `docs/automation-workflow.md`,
`tests/test_workflow_runner_scripts.py`, `docs/reports/GOV-AUTO-01-completion-report.md`.

**Modified (governance/handoff only):** `docs/TASK_QUEUE.md`, `docs/current_task.md`,
`docs/remaining_tasks.md`, `docs/CHANGELOG.md`,
`docs/workflow-automation/STAGE_REGISTRY.md`, `handover/PROJECT_HANDOVER.md`,
`handover/PROJECT_CHECKSUM.md`.

**Untouched, as required:** `src/ai_workflow_engine/`, `agentos_workflow/`, existing test suites,
`pyproject.toml` (no test integration needed it), dashboard documentation and implementation, and
every AUTO-004+ artifact.

## Governance and handoff updates

- GOV-AUTO-01 recorded as `Current` in the task queue and both mirrors.
- **AUTO-003 closed `Current` → `Done`** (registry `IN_PROGRESS` → `COMPLETE`). See "Remaining
  limitations" — this is a judgment call requiring Human Owner confirmation.
- Changelog entry added; stage-registry authorization log records both the AUTO-003 closure and a
  continuity-only note that GOV-AUTO-01 is outside the AUTO family.
- Handover rewritten and `handover/PROJECT_CHECKSUM.md` regenerated.
- **Next task recorded but neither authorised nor begun.** No independent review is claimed. The
  task is **not** marked committed.

## Remaining limitations

1. **AUTO-003 closure was a judgment call.** The instruction to record GOV-AUTO-01 as "the single
   active and Human-Owner-authorized task" is incompatible with AUTO-003 remaining `Current` under
   `maximum_current_tasks: 1` — leaving both would have failed `check-task-state` and broken a
   validation gate this task requires to pass. Given you approved AUTO-003's implementation and its
   commit was created, closing it to `Done` is the reading I acted on. **If you intended AUTO-003 to
   stay open, this closure should be reverted.**
2. **The runner cannot verify task authorization.** It checks repository state, not governance
   semantics; authorization is enforced by the prompt, a human instruction rather than a machine
   gate.
3. **Commit-message validation is structural, not semantic** — shape and length only.
4. **Whole-worktree staging.** The approval script has no partial-commit mode.
5. **Agent invocation assumes the current CLI contract** (prompt as first positional argument,
   verified against local `--help` for both). The `cmd=(...)` arrays are the single update point.
6. **Adding a test file changes the engine collection count** (978 → 1,037). This is expected and
   authorised here — unlike an AUTO stage, GOV-AUTO-01's scope explicitly permits script tests in
   the established `tests/` location.

## Repository integrity

No commit, push, merge, pull request, branch creation or switch, upstream change, rebase, reset,
restore, amend, cherry-pick, tag, or stash operation was performed against the real repository.
HEAD remains `908be94`; the branch remains `feature/auto-003-repository-validation-skills`; both
stashes are byte-identical to the state recorded at the start. The complete GOV-AUTO-01 diff
remains in the working tree for inspection.

## Proposed commit

```
feat(workflow): add local human-gated task runner (GOV-AUTO-01)
```
