# AUTO-006 Completion Report

## Stage identity

- **Stage:** AUTO-006 — GitHub pull request, automatic squash merge, and closeout integration
- **Role:** Engine implementation session
- **Objective:** Deliver the eight GitHub-facing Git/GitHub Skills of `SKILL_CONTRACTS.md` §5,
  binding the eight Skill names `GitAgent`/`MergeAgent` (AUTO-005) already call against fakes and
  named-but-unbound (`agentos_workflow.agents.PROVISIONAL_SKILL_NAMES`).
- **Contract:** `docs/workflow-automation/stage-prompts/AUTO-006.md`

## Authorization evidence

- Human Owner supplied both exact `AUTHORIZE` confirmations through
  `scripts/workflow-authorize.sh`, recorded 2026-07-28
  (`docs/workflow-automation/STAGE_REGISTRY.md` §5; `docs/DECISION_LOG.md`,
  "Human Owner authorized AUTO-006" entry). Registry moved `NOT_STARTED → AUTHORIZED`.
- `docs/current_task.md` / `docs/TASK_QUEUE.md`: AUTO-006 `Status: Current`, sole `Current` task.

## Initial repository state

- Branch at session start: `main`, clean (`git status --porcelain=v1` empty).
- HEAD: `3336184619bc6464f62a162ee34d869957b08928` ("docs(governance): authorize AUTO-006").
- Predecessors `docs/workflow-automation/STAGE_REGISTRY.md` §4: AUTO-003 `COMPLETE`, AUTO-005
  `COMPLETE`.

## Preconditions checked (initial-start preflight, SSP / `STAGE_REGISTRY.md` §3 rule 4)

| Precondition | Result |
|---|---|
| Active stage exactly AUTO-006, registry status `AUTHORIZED` | PASS |
| Predecessors AUTO-003, AUTO-005 `COMPLETE` | PASS |
| `docs/current_task.md` / `docs/TASK_QUEUE.md` agree (`Current`) | PASS |
| `main` == `origin/main`, clean working tree, no stray files | PASS |
| Branch `feature/auto-006-pr-merge-closeout` created from clean `main` | PASS — created at this session |

Registry state moved `AUTHORIZED → IN_PROGRESS` per rule 4 (`STAGE_REGISTRY.md` §5, "initial-start
preflight passed" row).

## Implementation summary

Implemented all eight Skills the contract's "Build" section names, in one new file,
`agentos_workflow/skills/git_github.py`:

- **Local Git Skills** (no GitHub CLI): `create_commit` (stages the working tree's current diff
  via `git add -A`, then commits — see "Architecture decisions" below), `push_stage_branch`
  (never `--force`, idempotent when the remote already matches), `verify_head_sha` (pure local
  `git rev-parse`, no remote counterpart).
- **GitHub Skills** (fixed-argv `gh` CLI, always `cwd`-scoped to the target repository with no
  `--repo` flag): `create_pull_request` (idempotent — reuses an existing open PR for the branch
  before ever calling `gh pr create`), `read_pull_request_state`, `read_required_checks` (reads
  only `--required` checks; tolerates `gh`'s "no checks reported" case as "nothing required"),
  `enable_automatic_squash_merge` (re-verifies the head SHA against GitHub immediately before its
  one `gh pr merge <number> --auto --squash` call site — never `--admin`, never any other flag),
  `verify_merge_completion` (the only Skill that produces a `MergeConfirmation`, refusing unless
  the PR's head branch still matches the caller's).

Every Skill returns the exact typed value shape `GitAgent`/`MergeAgent` already read via
`getattr` in `agents/git.py`/`agents/merge.py` (verified line-by-line against those modules
before writing the dataclasses) — no Agent code was read for anything other than determining the
call shape, and none was modified.

## Architecture decisions

1. **`create_commit` stages `git add -A` rather than a caller-supplied path list.**
   `SKILL_CONTRACTS.md` §5's table names "staged allowed paths" as input, but `GitAgent`'s actual
   call (`repository_path`, `branch`, `message`, `expected_head_sha` only) has no path parameter,
   and no other Agent has a staging Skill in its capability set. Recorded as `DECISIONS.md`
   DD-36; safe by construction because this Skill is only reachable after
   `run_scope_validation` has already passed on the same working-tree diff.
2. **OD-1 resolved: native GitHub auto-merge, never engine-side polling.**
   `enable_automatic_squash_merge`'s only merge-enabling call is `gh pr merge --auto --squash`;
   `read_required_checks` exists solely for the engine's own `WAITING_FOR_CHECKS` visibility.
   Recorded as `DECISIONS.md` DD-37.
3. **Retry classification is asymmetric across the eight Skills**, following
   `SKILL_CONTRACTS.md` §5 precisely: `create_commit`, `push_stage_branch`, and
   `create_pull_request` classify `POSSIBLE_SIDE_EFFECT` once their subprocess has run — even
   `create_commit`, which never touches a remote, because a hook or partial local write could
   already have applied. The other five Skills use the same network-failure convention
   `repository.py` already established. `verify_head_sha` is the sole Skill with no remote
   counterpart at all, so its failures are always `NOT_APPLICABLE`. A spawn failure is
   `PROVEN_PRE_SIDE_EFFECT` everywhere; a diagnosably permanent failure (auth/permission, unknown
   ref, non-429 4xx) is `NON_RETRYABLE` regardless of the above.

## Created files

- `agentos_workflow/skills/git_github.py` (900 lines)
- `agentos_workflow/tests/test_skills_git_github.py` (783 lines)

## Modified files

- `docs/workflow-automation/STAGE_REGISTRY.md` — §4 AUTO-006 row `AUTHORIZED → IN_PROGRESS`; new
  §5 row for the initial-start preflight; §6/§7 notes on DD-36..38 and OD-1/OD-10; version
  6.10 → 6.11.
- `docs/workflow-automation/DECISIONS.md` — new DD-36, DD-37, DD-38; version 1.9 → 1.10.
- `docs/workflow-automation/OPEN_QUESTIONS.md` — OD-1 disposition updated to Resolved; new OD-10;
  version 1.4 → 1.5.
- `docs/workflow-automation/CHANGELOG.md` — new AUTO-006 implementation entry; version
  2.13 → 2.14.
- `docs/CHANGELOG.md` — AUTO-006 `[Unreleased]` entry expanded from "authorized" to the full
  implementation narrative.
- `docs/DECISION_LOG.md` — new "AUTO-006 implemented, awaiting Human Owner approval" entry
  (newest-first, prepended above the existing authorization entry).

## Deleted files

None.

## Runtime code changes

`agentos_workflow/skills/git_github.py` only — a new file inside the AUTO Skill layer. No
existing runtime module (`agentos_workflow/agents/**`, `agentos_workflow/orchestrator/**`,
`agentos_workflow/config/**`, `agentos_workflow/providers/**`, or any other existing
`agentos_workflow/skills/*.py`) was modified. `src/ai_workflow_engine/**` untouched.

## Dependency changes

None. `gh` and `git` are invoked as external executables located via `PATH`, exactly as `git` is
already invoked throughout `skills/repository.py`; no new Python dependency was added to
`pyproject.toml`.

## Security changes

None to the audited engine (`src/`). Within the new file: three structural properties (not
merely reviewed) are each backed by a dedicated test —

- No admin-bypass path (`SECURITY_MODEL.md` §4): `enable_automatic_squash_merge` has exactly one
  `gh pr merge` call site, always `--auto --squash`, never `--admin`
  (`test_no_forbidden_argv_tokens`, `test_exactly_one_merge_enabling_call_site`).
- No repository redirection: every `gh` call is `cwd`-scoped with no `--repo` flag.
- No force-push, no baseline-target pull request: `push_stage_branch` never emits
  `--force`/`--force-with-lease`; `create_pull_request` refuses `branch == baseline_branch`.

## Tests added

`agentos_workflow/tests/test_skills_git_github.py` — 33 tests:

- `TestCreateCommit` (6): commits the working tree's diff, idempotent repeat, blank message,
  branch-moved precondition, nothing-to-commit, wrong current branch.
- `TestPushStageBranch` (4): pushes a new branch, idempotent when remote already matches,
  local-branch-moved precondition, unsafe remote name.
- `TestVerifyHeadSha` (3): matches, mismatches, missing branch.
- `TestCreatePullRequest` (5): creates new, reuses an existing open PR (asserts `pr create` is
  never called), refuses baseline target, refuses blank title, reports malformed `gh` JSON.
- `TestReadPullRequestState` (3): open, merged, invalid PR number rejected before any `gh` call.
- `TestReadRequiredChecks` (4): all passed, a failing check blocks, a pending check is not a
  failure verdict, "no checks reported" reads as nothing required.
- `TestEnableAutomaticSquashMerge` (3): refuses on head-SHA mismatch (asserts `pr merge` never
  called), enables when heads match (asserts `--auto`/`--squash` present, `--admin` absent),
  idempotent when GitHub reports auto-merge already enabled.
- `TestVerifyMergeCompletion` (3): confirms a real merge, refuses when not yet merged, refuses a
  head-branch mismatch.
- `TestStructuralSecurityProperties` (2): AST-based forbidden-token scan; exactly one
  merge-enabling call-site tuple.

`git`-based Skills run against real temporary repositories with a local bare remote (the
technique `test_skills_repository.py` already established — no network). `gh`-based Skills use a
fake `gh` executable placed first on `PATH` for the duration of each test ("mocked at the process
boundary," the stage contract's own words) that also logs every invocation's argv to a file, so
tests can assert not only what a Skill returned but whether — and in what order — it actually
called `gh`.

## Validation

- Focused: `pytest agentos_workflow/tests/test_skills_git_github.py -q` → **33 passed**.
- `pytest agentos_workflow/tests -q` → **1,498 passed** (up from 1,465 before this stage).
- Regression (engine suite collection unchanged): `python -m pytest tests --collect-only -q` →
  **1,066 collected** — unchanged by construction, since no file under `tests/` or `src/` was
  touched (`git diff --stat main..HEAD -- tests/ src/` is empty).
- `pytest tests -q` → **1,066 passed**.
- `ruff check --no-cache .` → **All checks passed!**
- `black --check .` → **147 files would be left unchanged.**
- `mypy --no-incremental agentos_workflow` → **Success: no issues found in 57 source files.**
- `mypy --no-incremental src` → **Success: no issues found in 55 source files.**
- `git diff --check` → clean (no whitespace errors), verified against the staged diff.
- `workflowctl verify --config self-governance.yaml`:

  | Check | Status | Summary |
  |---|---|---|
  | `git` | **FAIL** | 1 finding: `upstream_missing` — the stage branch has no upstream, which is expected and pre-existing for a branch this session created and, per the SSP, must not push (`STAGE_REGISTRY.md` §3 rule 16's named tolerance: "a branch never intended to be pushed"). |
  | `task-state` | PASS | 1 Current, 28 Done, 12 Planned tasks |
  | `governance` | PASS | Governance mirrors consistent |
  | `handover` | PASS | 1 manifest record verified |

  The `git` finding is the same pre-existing, documented condition the handover already names
  ("A stage branch created later and not yet pushed will produce the pre-existing
  `upstream_missing` finding"); it is not introduced by this stage's diff.
- Changed-file scope audit: every created/modified path is `agentos_workflow/skills/git_github.py`,
  `agentos_workflow/tests/test_skills_git_github.py`, or a `docs/**` governance/report file — all
  within the contract's allowed set (`agentos_workflow/skills/git_github.py`,
  `agentos_workflow/tests/**`, plus SSP-required documentation/report updates). No `src/`,
  `tests/`, `scripts/`, `pyproject.toml`, `self-governance.yaml`, `agentos_workflow/agents/**`, or
  `agentos_workflow/orchestrator/**` file was touched.

## Acceptance-criteria checklist

Per the contract's "Build" and "Tests" sections:

| Criterion | Result |
|---|---|
| `create_commit`, `push_stage_branch`, `create_pull_request`, `read_pull_request_state`, `read_required_checks`, `verify_head_sha`, `enable_automatic_squash_merge`, `verify_merge_completion` implemented per `SKILL_CONTRACTS.md` §5 | PASS |
| Fixed-argv `gh` CLI invocations | PASS |
| OD-1 resolved (native auto-merge) | PASS — `DECISIONS.md` DD-37 |
| Merge Safety Gate / Checks-Wait Gate (`MACHINE_GATES.md` §5-6) semantics honored | PASS at the Skill layer — head-SHA re-verified immediately before merge-enabling; required-checks read distinct from the merge decision. Wiring these gates into the Orchestrator's own execution loop is **not** performed — see "Known limitations" below. |
| No code path can construct `gh pr merge --admin` or any other admin-bypass invocation, verified by inspection and test | PASS |
| `gh` invocations mocked at the process boundary for the default suite | PASS |
| Expected-head-SHA mismatch blocks `AUTO_MERGE_ENABLED` | PASS — `test_refuses_on_head_mismatch` |
| A required check reported failed blocks merge, never a retried merge | PASS — `test_failed_check_blocks`; no retry logic exists anywhere in this Skill layer (retry/reconciliation is an Orchestrator decision per `WORKFLOW_STATES.md` §5a, out of this stage's scope) |
| `verify_merge_completion` is the only path that can produce a `MergeConfirmation` | PASS — the only function in the module returning one |
| Idempotent `create_pull_request` reuses an existing open PR | PASS — `test_reuses_existing_open_pull_request` |

## Known limitations / Risks / Deviations from plan

1. **Orchestrator wiring not performed.** The contract's Build section says "Wire the Merge
   Safety Gate and Checks-Wait Gate (`MACHINE_GATES.md` §5-6) into the Orchestrator," but the
   contract's own Allowed-files list names only `agentos_workflow/skills/git_github.py`,
   `agentos_workflow/tests/**`, and documentation — not `agentos_workflow/orchestrator/**`. This
   session treated the explicit Allowed-files list as controlling and did not touch
   `orchestrator/engine.py`, consistent with AUTO-005's own report, which states plainly that
   "the Agents are not yet driven by the Orchestrator's state machine — that wiring is outside
   this stage's allowed files and belongs to AUTO-007." The two gates' *logic* is implemented and
   tested at the Skill/Agent layer (head-SHA re-verification immediately before the merge call;
   required-checks read separately from the merge decision); only the Orchestrator's own
   execution-loop wiring is deferred. Flagged for an explicit Human Owner scope decision rather
   than resolved unilaterally in either direction.
2. **Five of eight Skill calls never receive `allowed_environment_variables` from their Agents**
   (discovered during self-review; `DECISIONS.md` DD-38, `OPEN_QUESTIONS.md` OD-10). In a real
   deployment, `gh` cannot authenticate for `create_pull_request`, `read_pull_request_state`,
   `enable_automatic_squash_merge`, `read_required_checks`, or `verify_merge_completion` until a
   future stage adds `allowed_environment_variables=self._allowed_environment_variables` to those
   five call sites in `agents/git.py`/`agents/merge.py` — outside this stage's allowed files.
   This does not affect the default test suite (the fake `gh` needs no authentication) but would
   block AUTO-007's real end-to-end dry run until fixed.
3. **`create_commit`'s staging behavior** (`git add -A`) is a documented interpretation of an
   input-shape mismatch between `SKILL_CONTRACTS.md` §5's table and `GitAgent`'s actual call
   (`DECISIONS.md` DD-36), not a literal reading of "staged allowed paths." Safe at the point this
   Skill is reachable in the workflow, but worth an explicit Human Owner confirmation.
4. **`gh` version/flag assumptions.** `--required` on `gh pr checks` and `--json headRefOid` /
   `mergeCommit.oid` on `gh pr view` assume a reasonably current `gh` CLI. Not verified against a
   real `gh` binary's actual output shape — the default suite mocks `gh` at the process boundary
   per the contract's own instruction, so this is unverified against real GitHub, exactly as the
   contract's "Out of scope" section anticipates (deferred to AUTO-007's opt-in real-repository
   run).
5. **`push_stage_branch` has no `baseline_branch` parameter to defensively reject a baseline
   target**, unlike `create_pull_request`. `GitAgent.push_stage_branch` never passes
   `baseline_branch` (its call shape has none), so the guarantee that this Skill is
   "structurally incapable of targeting the configured baseline branch" (`SKILL_CONTRACTS.md` §5)
   rests on the trust boundary that `GitAgent` always constructs `branch` from the workflow's own
   configured stage branch, never from arbitrary external input at the call site — the same trust
   boundary `create_commit`'s `branch` parameter already relies on. Not fixed, since adding the
   parameter would diverge from `GitAgent`'s actual call shape (out of this stage's allowed
   files); recorded for awareness.

## Open questions

- **OD-10** (new): should `agents/git.py`/`agents/merge.py` be amended to forward
  `allowed_environment_variables` to the five `gh`-based Skill calls that currently omit it?
  Recommended fix is small and mechanical but requires authorization to touch
  `agentos_workflow/agents/**`. See `OPEN_QUESTIONS.md` OD-10, `DECISIONS.md` DD-38.
- Whether Orchestrator wiring of the Merge Safety Gate / Checks-Wait Gate belongs to a later
  AUTO-006 continuation session (same stage, resumed) or is entirely AUTO-007's responsibility, as
  AUTO-005's own report already asserted for Agent-to-Orchestrator wiring generally. This report
  does not resolve that; it records the same limitation AUTO-005 already flagged, applied here to
  the two specific gates this stage's contract names.

## Git diff summary

```
 agentos_workflow/skills/git_github.py            | 900 +++++++++++++++++++++++
 agentos_workflow/tests/test_skills_git_github.py | 783 ++++++++++++++++++++
 2 files changed, 1683 insertions(+)
```

(plus the governance/documentation files listed under "Modified files" above)

## Recommended commit message

```
feat(workflow): add GitHub PR, automatic squash merge, and closeout integration (AUTO-006)
```

## Final stage status

**RETURNED** for Human Owner review — implemented, validated, and self-reviewed; two limitations
(Orchestrator wiring scope; the `allowed_environment_variables` gap, OD-10) recorded for an
explicit Human Owner decision before AUTO-007 or a real end-to-end run. Registry state
`IN_PROGRESS`, awaiting approval and closure per the SSP.

## Confirmation

No commit, push, pull request, merge, or branch deletion was performed. The complete diff is left
uncommitted in the working tree on `feature/auto-006-pr-merge-closeout` for Human Owner
inspection. Neither pre-existing stash (`stash@{0}`, `stash@{1}`) was touched. No branch other
than `feature/auto-006-pr-merge-closeout` was created, and no branch was deleted.

---

## Addendum 1 — Human Owner approval, commit, closure, and merge (2026-07-28)

**This addendum is appended, not merged into the text above.** Nothing earlier in this report has
been edited. In particular the Confirmation section's statement that no commit, push, pull
request, or merge had been performed was **accurate when written**: every event recorded below
happened afterwards, under a separate Human Owner decision. Rewriting that section to make it
read as though the commit already existed would falsify what the delivering session actually did,
which `docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 8 forbids and the Human Owner's
decision explicitly prohibited.

### What the Human Owner decided

> *"I approve the formal closure and publication of AUTO-006. The approved AUTO-006
> implementation commit is `d8d356d060076be4ad78afb4d20891004a946204`."*

The decision directed, in order: record AUTO-006 as implemented, validated, approved, and
committed locally as `d8d356d060076be4ad78afb4d20891004a946204`; move the task `Current → Done`
and the registry state `IN_PROGRESS → COMPLETE`; append a closure entry to the Authorization Log
and an approval/closure entry to `docs/DECISION_LOG.md`; reconcile every governance mirror and the
handover checksum in exactly one governance-only local commit with no implementation changes
bundled into it; then push, merge into `main`, and push `main` — retaining the stage branch and
leaving both stashes untouched. The decision explicitly withheld authorization for AUTO-007 and
for GOV-AUTO-03.

### Events recorded by this addendum

| Event | Value |
|---|---|
| Approved implementation commit | `d8d356d060076be4ad78afb4d20891004a946204` — `feat(workflow): add GitHub PR, automatic squash merge, and closeout integration (AUTO-006)` |
| Commit authored | 2026-07-28, after this report was written |
| Task status | `Current → Done` |
| Registry state | `IN_PROGRESS → COMPLETE` (§4); closure row appended to §5 |
| Stage branch | `feature/auto-006-pr-merge-closeout` — pushed to `origin`, **retained** (not deleted) |
| Stashes | `stash@{0}`, `stash@{1}` — untouched throughout |

### Governance closure commit

A single governance-only commit (`docs(governance): record AUTO-006 approval, closure, and
publication`) reconciles `docs/TASK_QUEUE.md`, `docs/current_task.md`, `docs/remaining_tasks.md`,
`docs/PROJECT_STATE.md`, `docs/DECISION_LOG.md`, `docs/CHANGELOG.md`,
`docs/workflow-automation/CHANGELOG.md`, `docs/workflow-automation/STAGE_REGISTRY.md`,
`handover/PROJECT_HANDOVER.md`, `handover/PROJECT_CHECKSUM.md`, and this addendum — no
`agentos_workflow/**`, `src/`, or `tests/` file is touched by it.

### Integration result

`main` is updated from `origin/main` and the stage branch merged by the repository's established
policy (the same explicit merge-commit shape used for AUTO-002's `87a5062`, AUTO-003/GOV-AUTO-01's
`a3b5b0a`, AUTO-004's `4721f9a`, and AUTO-005's `2c5c1c4` — never a fast-forward, never a rebase).
Post-merge verification confirms: `main` contains `d8d356d060076be4ad78afb4d20891004a946204`;
`agentos_workflow/skills/git_github.py` exists on `main`; local `main` equals `origin/main`; the
working tree is clean; AUTO-006 is `Done`/`COMPLETE`; no task is `Current`; `workflowctl verify`
passes every check; and both pre-existing stashes remain untouched. The exact merge commit hash is
recorded in this repository's Git history and in the Human Owner's closure report for this
session.

### Status of this stage

**COMPLETE.** No part of the AUTO-006 implementation was changed by this addendum — it is a
governance record only. The two known limitations recorded above (Orchestrator wiring of the
Merge Safety Gate / Checks-Wait Gate; the `allowed_environment_variables` gap, OD-10) were
explicitly accepted by the Human Owner's approval and remain open for a future stage's scope
decision — neither is fixed by this closure.
