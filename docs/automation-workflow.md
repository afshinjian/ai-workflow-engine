# Local Human-Gated Task Runner

A small local automation layer for this repository's standard task cycle. It automates the
mechanical steps around a task — preflight, prompt delivery, change review, and the commit
itself — **without replacing the Human Owner approval gate**.

## 1. Purpose

The repository's task cycle has always been:

```text
read handoff → identify one authorised task → implement → validate
→ stop for Human Owner approval → approve → verify scope → one local commit → stop
```

Running that by hand means retyping the same preflight checks and the same implementation prompt
every session, and it makes the commit step a free-form `git add`/`git commit` where the exact
staged set is easy to get wrong. These scripts make the mechanical parts repeatable while
leaving every judgment call — which task, whether the work is acceptable, whether to commit —
with the Human Owner.

What they deliberately do **not** do: decide what to work on, approve anything, push, or merge.

| Script | Role |
|---|---|
| `scripts/workflow-authorize.sh` | Authorize and record **one Human-named task**, create one governance-only local commit, and optionally launch the runner |
| `scripts/workflow-next.sh` | Read-only preflight, then launch **one** agent session with the canonical prompt |
| `scripts/prompts/implement-next-task.md` | The canonical implementation prompt both agents receive |
| `scripts/workflow-approve.sh` | The Human approval gate and the **only** path that creates a commit |

## 2. Prerequisites

- Bash 4+ (the approval script uses `mapfile -d`), Git, and standard POSIX tools. No new
  dependencies were added.
- The conda environment `ai-workflow-engine`, for the validation gates the prompt instructs the
  agent to run:
  ```bash
  conda run -n ai-workflow-engine <command>
  ```
- At least one agent CLI on `PATH`: `claude` or `codex`. The runner checks and fails clearly if
  the one you asked for is absent.

## 3. Executable setup

All three scripts are committed with their executable bit set. If a checkout loses it:

```bash
chmod +x scripts/workflow-authorize.sh scripts/workflow-next.sh scripts/workflow-approve.sh
```

All three resolve the repository root from **their own location**, following symlinks, so they work
when invoked from any directory:

```bash
/anywhere$ /path/to/ai-workflow-engine/scripts/workflow-next.sh claude
```

## 4. Command usage

```bash
scripts/workflow-authorize.sh <TASK_ID> [claude|codex]

scripts/workflow-next.sh <claude|codex>

scripts/workflow-approve.sh [-m "<conventional commit message>"]
```

`workflow-authorize.sh` requires one exact task ID and accepts at most one allowlisted agent. It
never selects a task from queue order.

`workflow-next.sh` takes exactly one argument and fails closed on anything else — no argument, two
arguments, `CLAUDE`, `gemini`, or a shell fragment all exit `2` without launching anything.

### Claude example

```bash
$ scripts/workflow-next.sh claude
AgentOS local task runner — preflight
---------------------------------------------------------------
Repository : /home/afshin-jian/ai-workflow-engine
Agent      : claude
---------------------------------------------------------------
Branch     : feature/auto-003-repository-validation-skills
HEAD       : 908be94be32f8dc42a2f66f86de61f0c121ac5ec

Git status:
## feature/auto-003-repository-validation-skills

Stashes (must remain unchanged):
  stash@{0}: WIP on feature/auto-002-orchestrator-foundation: ...
  stash@{1}: On main: pre-dashboard-recovery-snapshot

git diff --check : clean
Worktree         : clean
Prompt file      : /home/afshin-jian/ai-workflow-engine/scripts/prompts/implement-next-task.md
---------------------------------------------------------------
Preflight passed. Launching one claude session.
No commit, push, merge, branch change, or stash operation will be performed.
---------------------------------------------------------------
```

### Codex example

```bash
$ scripts/workflow-next.sh codex
```

Identical preflight; the prompt is handed to `codex` instead. Both agents receive the prompt as a
single argv element.

### Approval and commit example

```bash
$ scripts/workflow-approve.sh
AgentOS approval and local commit gate
---------------------------------------------------------------
Repository : /home/afshin-jian/ai-workflow-engine
Branch     : feature/auto-003-repository-validation-skills
HEAD       : 908be94be32f8dc42a2f66f86de61f0c121ac5ec
---------------------------------------------------------------
git diff --check : clean

Changed files (3):
 M docs/TASK_QUEUE.md
?? scripts/workflow-next.sh
?? scripts/workflow-approve.sh

Diff stat (tracked changes):
 docs/TASK_QUEUE.md | 11 ++++++++---

---------------------------------------------------------------
Review the changes above.
Type exactly APPROVE to continue, or anything else to abort.
Approval: APPROVE

Enter the Conventional Commit message (single line):
Message: feat(workflow): add local human-gated task runner (GOV-AUTO-01)

---------------------------------------------------------------
The following 3 file(s) will be staged and committed:
  docs/TASK_QUEUE.md
  scripts/workflow-next.sh
  scripts/workflow-approve.sh

Commit message:
  feat(workflow): add local human-gated task runner (GOV-AUTO-01)
---------------------------------------------------------------
Type exactly APPROVE to create this commit, or anything else to abort.
Confirm commit: APPROVE
...
COMMIT_COMPLETE_READY_FOR_NEXT_TASK
```

**`workflow-approve.sh` does not push and does not merge.** Publishing is always a separate,
deliberate act you perform yourself.

## 5. Intended daily workflow

```bash
scripts/workflow-authorize.sh AUTO-006 claude

# Agent implements, validates, and stops for approval.

scripts/workflow-approve.sh
```

The separated form is equivalent:

```bash
scripts/workflow-authorize.sh AUTO-006
scripts/workflow-next.sh claude
```

`workflow-authorize.sh` authorizes and records only the exact task named by the Human Owner. It
requires a clean default-branch baseline, verifies task/governance/handover state, checks task
readiness and structured program predecessor/decision gates, displays the complete transition,
and requires two exact `AUTHORIZE` confirmations. It then creates exactly one local
governance-only commit. With an agent argument it launches `workflow-next.sh` only after that
commit is verified and the worktree is clean.

`workflow-next.sh` implements the already-authorized task; it does not authorize one.
`workflow-approve.sh` performs the later Human approval gate and local implementation commit.
None of the scripts pushes or merges. A completed predecessor must be approved, closed, and
published separately by the Human Owner before a successor can be authorized; previous-task
closure is never automatic.

## 6. State transitions

```text
clean default-branch baseline, no Current task
   │  workflow-authorize.sh <Human-named task> [agent]
   ▼
validate readiness → AUTHORIZE → display transition → AUTHORIZE
   │  both confirmations pass             │  either declined → unchanged repository
   ▼                                      ▼
one governance-only local commit         stop
   │  optional agent, clean tree
   ▼
preflight (read-only: branch, HEAD, status, stashes, diff --check, prompt present)
   │  passes                              │  fails → exit 2..7, nothing launched
   ▼                                      ▼
one agent session                      unchanged repository
   │  agent implements + validates + updates governance, then STOPS
   ▼
dirty worktree, no commit  ◄── the Human Owner reviews the report and the diff
   │  scripts/workflow-approve.sh
   ▼
display changes → APPROVE → commit message → display exact file list → APPROVE
   │  both confirmations given            │  either declined → exit 7, nothing staged
   ▼                                      ▼
exactly one local commit                unchanged repository
   │
   ▼
clean worktree (not pushed, not merged)
```

## 7. Safety guarantees

| Guarantee | How it is enforced |
|---|---|
| No automatic task selection | The authorization gate accepts one exact Human-supplied task ID and derives none from queue order |
| No task starts without repository-recorded authorization | The authorization gate commits the task/mirror/registry transition before optional runner launch; the prompt independently verifies that record |
| Previous-task closure is separate | Any existing `Current` task fails with `ACTIVE_TASK_MUST_BE_CLOSED_FIRST`; no status is closed automatically |
| Authorization and implementation commits stay distinct | The authorization allowlist contains only governance/changelog/handoff records; implementation starts after that commit and clean-tree verification |
| Only one task per run | The prompt mandates one task; the runner launches exactly one session |
| No automatic commit after implementation | `workflow-next.sh` contains no commit path at all |
| Commit requires explicit Human input | Two separate confirmations, each requiring the exact token `APPROVE` |
| Push and merge never happen | None of the three scripts contains a push/merge implementation path; focused tests use a real bare remote and verify it remains untouched |
| Stashes are never changed | Only read-only `stash list` is used; `workflow-next.sh` also compares the stash count before and after the session and warns on any change |
| A dirty worktree prevents starting | `workflow-next.sh` exits `4` on any uncommitted change |
| An empty worktree prevents approval | `workflow-approve.sh` exits `4` when there is nothing to commit |
| Unknown agent fails closed | `case` statement with an explicit allowlist; anything else exits `2` |
| No `eval`, no shell interpolation | Commands are built as Bash arrays and expanded `"${cmd[@]}"`; the prompt is one argv element, so metacharacters in it are inert data |
| Failed commands return non-zero | `set -euo pipefail`; the agent's exit status is propagated verbatim |
| Works from outside the repo root | Root resolved from `BASH_SOURCE` with symlink resolution, never the caller's `cwd` |
| Only displayed files are staged | `git add --` with the explicit, previously shown path list — never `git add -A` |

## 8. Failure behaviour

`workflow-next.sh` exit codes:

| Code | Meaning |
|---|---|
| `2` | Bad usage or unsupported agent |
| `3` | Not a Git repository, or missing the `self-governance.yaml` marker |
| `4` | Worktree not clean |
| `5` | Prompt file missing or empty |
| `6` | `git diff --check` reported whitespace/conflict errors |
| `7` | Requested agent CLI not on `PATH` |
| *other* | The agent's own exit status, propagated |

`workflow-approve.sh` exit codes:

| Code | Meaning |
|---|---|
| `2` | Unrecognised argument |
| `3` | Not a Git repository |
| `4` | Nothing to commit |
| `5` | `git diff --check` errors |
| `6` | Unresolved merge conflicts |
| `7` | Approval declined at either confirmation |
| `8` | Empty or non-Conventional commit message |
| `9` | `git commit` itself failed |

## 9. Recovery

- **Declined approval** — nothing was staged and nothing committed. Your working tree is
  untouched; re-run when ready.
- **Failure after staging but before commit** — an `EXIT` trap unstages exactly the files the
  script staged, using `git restore --staged` (index only). **No working-tree content is
  discarded.** The script prints `Working-tree content is NOT modified` so this is unambiguous.
  Re-run once the underlying problem (a rejecting hook, a full disk) is fixed.
- **Started on a dirty worktree by mistake** — `workflow-next.sh` refuses before launching
  anything. Either approve and commit the pending work, or set it aside yourself.
- **Committed the wrong thing** — this is outside the scripts' remit by design. Nothing was
  pushed, so recovery is an ordinary local Git operation you perform deliberately.

## 10. Known limitations

- **Ordinary queue-only tasks have no structured predecessor metadata.** For AUTO/DASH stages,
  the gate verifies the numbered predecessor's registry state and canonical branch. Ordinary GOV
  tasks are treated as having no declared predecessor unless they join a structured registry;
  their explicit queue status, blocker language, clean baseline, and Human confirmations still
  apply.
- **Open-decision checks rely on established governance wording.** Explicit `blocked on` task
  language and “must be resolved before TASK authorization” program records fail closed. A future
  structured dependency schema would make this stronger without free-form Markdown matching.
- **Commit-message validation is structural, not semantic.** It enforces the Conventional Commit
  shape and a minimum length; it cannot tell whether the message honestly describes the diff.
- **The whole-worktree staging model.** The approval script stages every changed file, after
  displaying them. It has no partial-commit mode; if you need to split a change, do it manually.
- **Interactive agent invocation.** Both agents are launched in their default interactive mode
  with the prompt as the first argument. If a future CLI version changes that contract, the
  `cmd=(...)` arrays in `workflow-next.sh` are the single place to update.
- **`workflow-next.sh` cannot enforce what the agent does.** Its guarantees cover its own
  behaviour; the agent's restraint comes from the prompt. The approval gate is what actually
  prevents an unreviewed commit.
- **Bash-and-POSIX only**, consistent with the task's constraints — no new dependency, and no
  Python wrapper around the Git operations.

## 11. When independent review is still required

The prompt states plainly that **independent review is not mandatory for every ordinary task** —
a bounded self-review is the normal standard, and requiring a fresh review session for routine
work is friction that buys nothing.

Reserve a separate independent review session for:

- milestone completion;
- releases;
- tasks whose governance explicitly requires it (for example a stage contract that names a review);
- tasks where the Human Owner explicitly requests it;
- critical trust-boundary changes — authorization, authentication, secrets handling, sandboxing,
  destructive Git or filesystem operations, or anything that widens what the engine may do without
  a human in the loop.

When a task falls into one of those categories the agent must say so and recommend the review
rather than performing it in the same session — a reviewer who just wrote the code is not
independent, and a session that reviews its own work will reliably confirm it.
