# Local Human-Gated Task Runner

A small local automation layer for this repository's standard task cycle. It automates the
mechanical steps around a task — preflight, prompt delivery, change review, closeout, and the
commit itself — **without replacing the Human Owner approval gate**.

## 1. Purpose

The repository's task cycle has always been:

```text
read handoff → identify one authorised task → implement → validate
→ stop for Human Owner approval → approve → verify scope → one local commit
→ deterministic governance closeout → stop
```

Running that by hand means retyping the same preflight checks and the same implementation prompt
every session, makes the commit step a free-form `git add`/`git commit` where the exact staged
set is easy to get wrong, and leaves the governance closeout (task queue, mirrors, decision log,
changelog, stage registry, completion report, handover, checksum) as a second, easy-to-forget
manual pass after the fact. These scripts make the mechanical parts repeatable while leaving
every judgment call — which task, whether the work is acceptable, whether to commit — with the
Human Owner.

What they deliberately do **not** do: decide what to work on, approve anything, push, or merge.

| Script | Role |
|---|---|
| `scripts/workflow-authorize.sh` | Authorize and record **one Human-named task**, create one governance-only local commit, and optionally launch the runner |
| `scripts/workflow-next.sh` | Read-only preflight, then launch **one** agent session with the canonical prompt |
| `scripts/prompts/implement-next-task.md` | The canonical implementation prompt both agents receive |
| `scripts/workflow-approve.sh` | The Human approval gate and the **only** path that creates a commit. In this repository it also performs the deterministic governance closeout of the Current task in that same commit (GOV-AUTO-03); in any other repository it is the plain GOV-AUTO-01 approval/commit gate |

**GOV-AUTO-03 — automatic task closeout.** `workflow-approve.sh` now closes out the single
`Current` task as part of the one commit it creates, instead of leaving closeout as a separate,
manual governance pass. It is still one commit, still requires two exact `APPROVE` confirmations,
and still never pushes or merges. This behaviour is scoped to repositories carrying the
`project.id: ai-workflow-engine` marker in `self-governance.yaml` (the same marker
`workflow-authorize.sh` already uses) with the full governance file set present; any other
repository — including every disposable test sandbox — gets the unchanged GOV-AUTO-01 gate that
only commits the approved diff. See §5 and §9 below for the new cycle and its failure behaviour.

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
scripts/workflow-authorize.sh AUTO-007 claude

# Agent implements, validates, writes its completion report, and stops for approval.

scripts/workflow-approve.sh
```

The separated form is equivalent:

```bash
scripts/workflow-authorize.sh AUTO-007
scripts/workflow-next.sh claude
```

`workflow-authorize.sh` authorizes and records only the exact task named by the Human Owner. It
requires a clean default-branch baseline, verifies task/governance/handover state, checks task
readiness and structured program predecessor/decision gates, displays the complete transition,
and requires two exact `AUTHORIZE` confirmations. It then creates exactly one local
governance-only commit. With an agent argument it launches `workflow-next.sh` only after that
commit is verified and the worktree is clean.

`workflow-next.sh` implements the already-authorized task; it does not authorize one.

`workflow-approve.sh` performs the later Human approval gate. In this repository it also closes
out the task in the same operation: after the two `APPROVE` confirmations it identifies the
single `Current` task, verifies the approved diff and commit message correspond to it, performs
the deterministic closeout (task queue, mirrors, project state, decision log, changelog, stage
registry where applicable, program changelog where applicable, completion report addendum,
handover, checksum), re-runs `task-state`/`governance`/`handover` validation, and only then
creates **exactly one** local commit containing both the approved implementation and the
generated closeout records:

```text
scripts/workflow-authorize.sh TASK_ID claude|codex
        ↓
authorization governance commit
        ↓
agent implements one task
        ↓
agent validates and reports
        ↓
Human Owner runs workflow-approve.sh
        ↓
script verifies scope and approval
        ↓
script updates task Current → Done
        ↓
script updates registry active state → COMPLETE (where applicable)
        ↓
script regenerates handoff/checksum
        ↓
one final implementation + closeout commit
        ↓
working tree clean, no Current task
```

After `workflow-approve.sh` succeeds in this repository:

- one final task commit exists, containing the approved implementation and the closeout records
  together — never a separate `docs(governance): close TASK_ID` commit;
- the task is `Done`, and its stage registry (if any) is `COMPLETE`;
- no task is `Current`;
- the working tree is clean;
- the next `Planned` task is reported but remains unauthorized;
- push and merge are still separate, deliberate Human Owner actions performed afterward — because
  the commit that closes a task cannot record its own future hash, a later publication/merge may
  still need its own append-only record (an addendum to the completion report, a new decision-log
  entry, or a new registry row), exactly as prior AUTO-00x closures already do.

None of the scripts pushes or merges. A completed predecessor must be approved, closed, and
published separately by the Human Owner before a successor can be authorized; previous-task
closure is never automatic, and closing a task never authorizes its successor — the Human Owner
must still name and authorize the next task explicitly through `workflow-authorize.sh`.

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
identify the single Current task, verify mirrors/registry/report/message correspond to it
   │  any precondition fails → exit 10-15, unchanged repository
   ▼
display task, branch, base HEAD, implementation files, closeout files, proposed commit message
   ▼
APPROVE → APPROVE
   │  either declined → exit 7, unchanged repository
   ▼
deterministic closeout generation (queue, mirrors, state, decision log, changelog, registry,
program changelog, completion-report addendum, handover, checksum)
   │  any step fails → generated files restored, implementation preserved, exit 16, no commit
   ▼
post-closeout task-state / governance / handover validation
   │  fails → generated files restored, implementation preserved, exit 16, no commit
   ▼
stage implementation + closeout files together → exactly one local commit
   │
   ▼
clean worktree, task Done, no Current task (not pushed, not merged, no successor authorized)
```

In any other repository (no `project.id: ai-workflow-engine` marker, or the marker present but the
governance files absent), the flow is the unchanged GOV-AUTO-01 gate:

```text
dirty worktree, no commit
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
| Closeout only in the recognised repository | Gated on the same stable `project.id: ai-workflow-engine` marker `workflow-authorize.sh` already uses, plus the full governance file set; any other repository gets the unchanged plain commit gate |
| Exactly one Current task, verified from multiple sources | The authoritative task queue, the `current_task.md` mirror, and `remaining_tasks.md` must all agree on exactly one task before anything is generated; disagreement, zero, or multiple Current tasks all fail closed |
| Approval evidence bound to the task | The approved Conventional Commit message must literally name the Current task ID, or the gate refuses before generating anything |
| Closeout precondition checks run before any Human prompt | Task/mirror/registry/report discovery and validation happen before the first `APPROVE`, so a doomed run fails fast without wasting a Human confirmation |
| Closeout never edits by broad text replacement | Every generated edit is an `awk`-guarded, precondition-checked replacement (exact heading, exact old status, exact single table row) that fails closed (`exit 42` inside `awk`) if its expected marker is missing or duplicated |
| Closeout failures are atomic | A pre-closeout backup of every governance file the closeout may touch is restored verbatim on any failure; the implementation diff and the index are never touched by a closeout failure |
| No separate closure commit | Implementation and closeout are staged and committed together; the script contains no second `git commit` invocation |
| No successor authorized by closeout | Closing a task never authorizes or begins the next one; the script only reports the next `Planned` task's ID |

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
| `10` | Closeout mode only: no `Current` task found |
| `11` | Closeout mode only: more than one `Current` task |
| `12` | Closeout mode only: a mirror (task queue, `current_task.md`, `remaining_tasks.md`, duplicate heading) disagrees |
| `13` | Closeout mode only: the Current task is `BLOCKED`/blocked language and not closeable |
| `14` | Closeout mode only: no completion report found for the Current task |
| `15` | Closeout mode only: the commit message doesn't name the Current task, or the branch doesn't match the stage's registered branch |
| `16` | Closeout mode only: closeout generation or post-closeout governance validation failed — nothing committed, generated files restored |
| `17` | Closeout mode only: the `project.id: ai-workflow-engine` marker is present but a required governance file is missing |

Codes `10`-`17` only occur in this repository (the marker/governance-file-gated closeout path);
any other repository never reaches them and behaves exactly as the original GOV-AUTO-01 gate.

## 9. Recovery

- **Declined approval** — nothing was staged, nothing was closed out, and nothing was committed.
  Your working tree is untouched; re-run when ready.
- **A closeout precondition fails (exit `10`-`15`)** — this happens *before* either `APPROVE`
  prompt, so nothing was displayed as approved and nothing was touched. Fix the underlying
  governance disagreement (or the commit message) and re-run.
- **Closeout generation or post-closeout validation fails (exit `16`)** — this is the one case
  where the script has already started mutating governance files when it detects the problem. Its
  `EXIT` trap restores every governance file the closeout touches from a pre-closeout backup taken
  before the first edit, so those files end up byte-identical to how they were before the run. The
  approved implementation diff was never staged at this point and is completely untouched. The
  script prints which files were restored; fix the underlying problem (commonly a missing or
  duplicated governance marker) and re-run.
- **Failure after staging but before commit** — an `EXIT` trap unstages exactly the files the
  script staged, using `git restore --staged` (index only), and — in closeout mode — also restores
  any governance files the closeout had generated. **No working-tree content is discarded.** The
  script prints `Working-tree content is NOT modified` (legacy path) or the equivalent closeout
  diagnostic, so this is unambiguous. Re-run once the underlying problem (a rejecting hook, a full
  disk) is fixed.
- **Started on a dirty worktree by mistake** — `workflow-next.sh` refuses before launching
  anything. Either approve and commit the pending work, or set it aside yourself.
- **Committed the wrong thing** — this is outside the scripts' remit by design. Nothing was
  pushed, so recovery is an ordinary local Git operation you perform deliberately. If the commit
  already closed a task, correcting it is a Governance Correction Record (an append-only entry),
  never an edit to the closed record itself — see `docs/workflow-automation/STAGE_REGISTRY.md` §3
  rule 18 for the pattern this repository already follows.
- **Publication and merge after closeout** — `workflow-approve.sh` never pushes or merges. Because
  the commit that closes a task cannot record its own future hash, a later push/merge may still
  need its own append-only publication record (an addendum to the completion report, a new
  decision-log entry, or a new registry row naming the merge commit) — exactly the pattern
  AUTO-004/005/006 already used when their closure commit post-dated their completion report.

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
- **Closeout requires a completion report to already exist.** `workflow-approve.sh` only
  *appends* an addendum to `docs/reports/<TASK_ID>-completion-report.md` (or the
  `workflow-automation`/`agentos-dashboard` program variant); it never creates the report body
  itself. The canonical implementation prompt already directs the agent to write one, so this is
  ordinarily satisfied before approval is even requested.
- **Closeout is scoped to this repository's own governance shape.** It recognises stage registries
  only at `docs/workflow-automation/STAGE_REGISTRY.md` and `docs/agentos-dashboard/STAGE_REGISTRY.md`,
  and completion reports only under the three fixed `docs/reports/**` conventions already in use.
  A future program with a differently-shaped registry or report path would need the same kind of
  extension `workflow-authorize.sh`'s registry-candidate loop would also need.
- **Task-ID-in-message is a structural, not semantic, evidence check.** Requiring the approved
  commit message to literally name the Current task ID (alongside the two `APPROVE` confirmations
  and the full displayed transition) catches an obviously mismatched approval; it cannot verify
  that the message honestly describes the diff, the same limitation the Conventional-Commit-shape
  check already has.

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
