# AUTO-004 Completion Report

| Field | Value |
|---|---|
| **Stage** | AUTO-004 — Claude Code CLI and Codex CLI providers |
| **Assigned role** | Engine implementation session |
| **Branch** | `feature/auto-004-model-providers` |
| **Registry state** | `IN_PROGRESS` (stopped for Human Owner approval) |
| **Contract** | `docs/workflow-automation/stage-prompts/AUTO-004.md` |
| **Report version** | 1.0 |

## Objective

Implement the Model Provider layer of `docs/workflow-automation/MODEL_PROVIDER_CONTRACTS.md`: the
common `Provider` interface (§1), `ClaudeCLIProvider` (§2) and `CodexCLIProvider` (§3) as
subprocess adapters over the configured executable and timeout, `MockProvider` (§4) as an offline
substitute structurally excluded from real workflows, and session isolation between provider
invocations (§5).

## Authorization evidence

Human Owner, 2026-07-28: *"I authorize AUTO-004 — Claude Code CLI and Codex CLI providers … Create
the required feature branch from the current clean and synchronized `main`. Then implement AUTO-004
using the repository handoff and standard implementation workflow. Implement exactly one task. Do
not commit. Do not push. Do not merge. Do not begin AUTO-005 or another task."*

**Rule-16 predecessor conflict, presented and resolved before any change.** The authorization
precondition check (`STAGE_REGISTRY.md` §3 rule 1) found GOV-AUTO-01 still recorded `Current` in
`docs/TASK_QUEUE.md` and both mirrors, although its commit `a302c95` was already merged into `main`
via `a3b5b0a`. Under `maximum_current_tasks: 1` that blocked "no other `Current` task anywhere in
the queue". Per rule 16 this session stopped, made no change, and reported the conflict rather than
resolving it on its own initiative. The Human Owner, presented with it, gave one written decision
resolving both:

> *"Close GOV-AUTO-01 from Current to Done, recording that it was: implemented; validated;
> approved; committed as `a302c95`; merged into main via `a3b5b0a`. … Then authorize and begin
> AUTO-004 as the single Current task."*

Recorded in `STAGE_REGISTRY.md` §5 (two 2026-07-28 rows) and `docs/DECISION_LOG.md`
(2026-07-28 entry). Registry state moved `NOT_STARTED → AUTHORIZED → IN_PROGRESS` per rule 17(a);
task status `Planned → Current`.

## Initial repository state

| Fact | Value |
|---|---|
| Branch at start | `main`, `git status` clean |
| HEAD | `a3b5b0a` (`main` == `origin/main`) |
| Branch created | `feature/auto-004-model-providers` from clean `main` at `a3b5b0a` |
| Stashes | `stash@{0}`, `stash@{1}` — untouched, as before |

## Preconditions checked

| Precondition | Result | Evidence |
|---|---|---|
| Active stage is exactly AUTO-004 | PASS | `STAGE_REGISTRY.md` §4; `docs/current_task.md` |
| Predecessor AUTO-002 `COMPLETE` (contract's named precondition) | PASS | `STAGE_REGISTRY.md` §4 |
| AUTO-003 `COMPLETE` | PASS | `STAGE_REGISTRY.md` §4 |
| Recorded authorization naming AUTO-004 | PASS | §5, 2026-07-28 row |
| No other `Current` task | PASS | after the Human-Owner-directed GOV-AUTO-01 closure; `workflowctl check-task-state` → 1 Current |
| Stage's named branch from clean baseline | PASS | `feature/auto-004-model-providers` from `a3b5b0a` |
| `git status` clean before starting | PASS | verified before branch creation |

Initial-start preflight (SSP), not resume preflight: the registry showed AUTO-004 `NOT_STARTED`.

## Implementation summary

`agentos_workflow/providers/` implements the layer in five modules.

**`base.py` — the interface and shared primitives.** `Provider` is an ABC whose entire surface is
`kind` and `invoke(invocation) -> ProviderResult`; nothing else exists to call, which is what makes
a substitute genuinely drop-in. `CLIProvider` implements the whole invocation sequence once
(validate → isolate → run → classify → parse) so the two CLI adapters cannot drift apart in how
they enforce the timeout, the environment allowlist, or isolation. Failures are typed
`ProviderFailure` values; **nothing in the package raises to the Orchestrator**, matching the Skill
layer's discipline.

**Retry classification (§2)** follows the contract's "*when*, not *what*" rule exactly: a spawn
failure is the single `PROVEN_PRE_SIDE_EFFECT` case (the CLI never ran, so it cannot have written
anything); a timeout, an abnormal exit, and a clean exit with unparseable output are all
`POSSIBLE_SIDE_EFFECT` — never eligible for a blind retry, because each may already have left a
partial diff on the stage branch.

**`claude_cli.py`** — default implementation and repair provider; fixed argv
`--print --output-format json`; unwraps the CLI's result envelope (a string `result` field holding
the answer) before the shared schema validation, and still accepts a bare report object.

**`codex_cli.py`** — default independent QA provider; fixed argv `exec --json`; reads the **last**
decodable JSON object from a JSON Lines event stream, so a progress event is never mistaken for the
final verdict. Non-decodable progress lines are skipped; stdout with no JSON object at all is an
error, never an assumed pass.

**`mock.py`** — offline substitute returning queued canned results, the last repeating so a repair
loop can be driven past the queue length. It spawns no process, reads no environment, and creates
no directory.

**`__init__.py`** — the live selection registry mapping role → provider (Claude =
implementation/repair, Codex = QA), the single place that assignment exists.

### Session isolation (§5, `SECURITY_MODEL.md` §3)

Each invocation gets `<session_root>/<workflow_id>/<provider_kind>/<invocation_id>`, created
`0o700` with `exist_ok=False`, and the process's `TMPDIR` and `AGENTOS_SESSION_DIRECTORY` are
pointed at it. Two providers in one workflow therefore cannot collide in, or read, each other's
scratch. Provider instances hold no cross-invocation state, `select_live_provider` returns a fresh
instance per call, and neither provider's raw output is ever routed into the other's process — only
what the Orchestrator assembles crosses the boundary.

### `MockProvider` structural exclusion (§4, `MVP_SCOPE.md` §3)

Four independent properties, none of them a comment asking a caller to behave:

1. `MockProvider` subclasses `Provider` directly, **not** `CLIProvider`; `select_live_provider` is
   typed to return a `CLIProvider`, so returning a mock from it fails mypy.
2. It is absent from the live registry entirely.
3. It has no `from_config` constructor, and the configuration schema has no provider-selection
   field at all — there is no value a target repository could set to request one.
4. No live module imports or names it; asserted by AST inspection over the modules' own source.

## Architecture decisions

- **Providers own their subprocess and environment primitives** rather than reusing
  `skills.run_fixed_argv`. The Skill primitive binds stdin to `DEVNULL` by design; a Provider must
  deliver its prompt on stdin. Passing a multi-kilobyte prompt through argv was rejected — argv is
  world-readable in `/proc` and `ps`, and the prompt carries the stage contract and the diff. The
  allowlist rule is the same rule at a second boundary, deliberately independent so neither layer's
  hardening depends on the other's internals.
- **Parse first, redact each extracted value** — see Known limitations for the defect this fixed.
- **`HOME` is never forwarded implicitly.** A CLI needing its credential store must have `HOME`
  named in `allowed_environment_variables` as a visible configuration act.
- **The report schema is strict.** A missing verdict is an error, not an assumed pass; a
  wrong-typed field is an error, not a coerced value. A report is evidence the machine gates act
  on, so defaulting either would manufacture a claim the CLI never made.
- **`stage_id` is carried, not consumed**, and deliberately kept out of the audit identity: an
  unvalidated caller string in an audit identity is a log-injection surface for no benefit.

No new `DD-` entry was required: each of these implements an existing contract rather than
deciding an open architectural question.

## Created files

| Path | Lines |
|---|---|
| `agentos_workflow/providers/__init__.py` | 106 |
| `agentos_workflow/providers/base.py` | 699 |
| `agentos_workflow/providers/claude_cli.py` | 73 |
| `agentos_workflow/providers/codex_cli.py` | 79 |
| `agentos_workflow/providers/mock.py` | 112 |
| `agentos_workflow/tests/test_providers_base.py` | 560 |
| `agentos_workflow/tests/test_providers_cli.py` | 245 |
| `agentos_workflow/tests/test_providers_isolation.py` | 257 |
| `agentos_workflow/tests/test_providers_mock.py` | 229 |
| `docs/reports/workflow-automation/AUTO-004-completion-report.md` | this file |

## Modified files

| Path | Change |
|---|---|
| `docs/TASK_QUEUE.md` | GOV-AUTO-01 `Current → Done`; AUTO-004 `Planned → Current` |
| `docs/current_task.md` | mirror — AUTO-004 replaces GOV-AUTO-01 |
| `docs/remaining_tasks.md` | mirror — table and prose |
| `docs/PROJECT_STATE.md` | prose only; `Current Version:` fact line untouched |
| `docs/DECISION_LOG.md` | one new dated entry (append-only, prepended as newest-first) |
| `docs/CHANGELOG.md` | one new `[Unreleased]` entry |
| `docs/workflow-automation/CHANGELOG.md` | one new `[Unreleased]` entry |
| `docs/workflow-automation/STAGE_REGISTRY.md` | §4 AUTO-004 state cell; §5 two appended rows |
| `handover/PROJECT_HANDOVER.md` | refreshed (was stale: described GOV-AUTO-01 as uncommitted) |
| `handover/PROJECT_CHECKSUM.md` | regenerated for the above |

## Deleted files

None.

## Runtime code changes

New package `agentos_workflow/providers/` only. **No existing runtime module was modified.**
`src/`, `tests/`, `scripts/`, `examples/`, `pyproject.toml`, `.pre-commit-config.yaml`, and
`self-governance.yaml` are untouched. `agentos_workflow/skills/` and
`agentos_workflow/orchestrator/` are unmodified; the providers package imports five public names
from `agentos_workflow.skills` (`CommandExecution`, `CommandOutcome`, `RetryClassification`,
`redact_secrets`, `utc_now`) and invokes no Skill.

## Dependency changes

None. Standard library plus the already-present `pydantic` (via the existing config schema).

## Security changes

Additive only, all inside the new package: environment allowlist enforcement at the provider
boundary, `0o700` per-invocation session directories with `TMPDIR` redirected into them, redaction
of every string leaving the package, an audit identity that never contains argv or the prompt, and
prompt-on-stdin so no prompt appears in `ps`/`/proc`. No credential is constructed, stored, or
logged (`SECURITY_MODEL.md` §1). No forbidden Git/GitHub operation is reachable from this package —
it performs no Git or GitHub operation at all.

## Tests added

106 tests across four files:

| File | Tests | Covers |
|---|---|---|
| `test_providers_base.py` | 54 | interface shape, stdin delivery, argv ownership, environment allowlist, timeout, classification, report parsing, redaction, invocation validation |
| `test_providers_cli.py` | 17 | Claude envelope unwrapping, Codex JSONL last-object rule, per-provider argv and config binding, live selection |
| `test_providers_isolation.py` | 21 | session-directory disjointness and permissions, no shared objects, no cross-provider output, mock structural exclusion (incl. AST assertions) |
| `test_providers_mock.py` | 14 | canned reports, queue semantics, drop-in equivalence, no process/no config path |

The process boundary is mocked by **substituting the executable** with a stub script, not by
patching `subprocess` — so the allowlist and timeout tests observe what a real child process
actually received and how the real timeout actually fired. No Claude or Codex CLI is required.
Tests that must assert on argv patch `subprocess.run`, since argv is not otherwise observable.

## Validation

| Check | Command | Result |
|---|---|---|
| Focused | `pytest agentos_workflow/tests/test_providers_*.py -q` | **106 passed** |
| Engine suite | `pytest agentos_workflow/tests -q` | **1332 passed** |
| Regression (collection unchanged) | `python -m pytest tests --collect-only -q` | **1037 collected** — unchanged from baseline (978 at AUTO-003 + 59 GOV-AUTO-01 script tests); this stage adds nothing under `tests/` |
| Full suite | `pytest tests -q` | **1037 passed** |
| Lint | `ruff check .` | All checks passed |
| Format | `black --check .` | 131 files unchanged |
| Types | `mypy agentos_workflow` | Success, no issues in 42 source files |
| Hooks | `pre-commit run --all-files` | ruff / black / mypy all Passed; **no file outside the allowed list was mutated** |
| Whitespace | `git diff --check` | clean |
| Governance | `workflowctl verify --config self-governance.yaml` | `task-state` PASS, `governance` PASS, `handover` PASS, `git` **FAIL — pre-existing** |

### The one failing check, identified as pre-existing

`check-git` reports `upstream_missing: The configured project requires an upstream`. This is the
expected condition for a stage branch that has never been pushed and is not intended to be, and is
exactly the tolerance `STAGE_REGISTRY.md` §3 rule 16 and the SSP name ("`upstream_missing` on a
branch never intended to be pushed"). AUTO-003 recorded the identical finding. It is not caused by
this stage's changes; every other check passes.

### Changed-file scope audit

Contract's allowed list: `agentos_workflow/providers/{__init__,base,claude_cli,codex_cli,mock}.py`,
`agentos_workflow/tests/**`, plus SSP-required documentation/report updates.

Every changed path falls inside it. The five provider modules are exactly the five named — no
sixth. The four test files are under `agentos_workflow/tests/`. The documentation changes are the
sanctioned governance-transition set plus this report and the handoff. **Nothing under `src/`,
`tests/`, `scripts/`, `examples/`, `pyproject.toml`, `.pre-commit-config.yaml`, or
`self-governance.yaml` was touched**, and `docs/implementation/orchestration/**` and
`docs/agentos-dashboard/**` are untouched. `handover/**` was modified under the Human Owner's
explicit instruction to update the handoff.

## Acceptance-criteria checklist

| # | Criterion (from the stage contract) | Result | Evidence |
|---|---|---|---|
| 1 | Common `Provider` interface per §1 | **PASS** | `base.Provider`; `test_every_provider_exposes_exactly_invoke_and_kind` |
| 2 | `ClaudeCLIProvider` subprocess adapter over configured executable + timeout | **PASS** | `claude_cli.py`; `TestClaudeCLIProvider`, `test_timeout_comes_from_configuration_not_a_default` |
| 3 | `CodexCLIProvider` likewise, with its own budget | **PASS** | `codex_cli.py`; `test_from_config_binds_the_codex_fields_and_its_own_timeout` |
| 4 | Only `allowed_environment_variables` passed | **PASS** | `TestEnvironmentAllowlist` (5 tests), incl. observation of the real child environment |
| 5 | `MockProvider` returns configurable canned reports | **PASS** | `TestCannedReports` |
| 6 | `MockProvider` structurally excluded from live selection | **PASS** | `TestMockProviderIsStructurallyExcluded` (7 tests), incl. type and AST assertions |
| 7 | Session isolation between the two providers | **PASS** | `TestSessionIsolation` (8 tests) |
| 8 | Subprocess mocked at the process boundary; no real CLI needed | **PASS** | stub-executable strategy; suite runs with no CLI installed |
| 9 | Timeout enforcement and typed timeout error | **PASS** | `test_timeout_is_enforced_and_typed`, `test_timeout_is_possible_side_effect_never_a_blind_retry` |
| 10 | `MockProvider` drop-in equivalence | **PASS** | `TestDropInEquivalence` (5 tests) — one caller drives both |
| 11 | No shared state/object between two instances in one workflow | **PASS** | `test_no_object_is_shared_between_two_provider_instances`, `test_providers_hold_no_cross_invocation_state` |
| 12 | No credentials constructed, stored, or logged | **PASS** | `TestSecretsNeverSurface` (4 tests); no credential path exists in the package |
| 13 | Engine behavior and default `pytest` collection provably unchanged | **PASS** | 1037 collected before and after; no existing module modified |

## Known limitations / Risks / Deviations from plan

1. **The exact CLI flags are not verified against a live CLI.** `--print --output-format json` and
   `exec --json` are defined here as this stage's argv contract (`MODEL_PROVIDER_CONTRACTS.md` §7
   assigns the invocation shape to AUTO-004), but the contract explicitly assigns *real end-to-end
   invocation of a live Claude/Codex CLI* to AUTO-007. If a live CLI rejects a flag, the fix is a
   one-line change to that provider's `_ARGV_SUFFIX`. **This is the stage's main open risk** and is
   stated plainly rather than papered over: the tests prove adapter behavior, not that any
   particular installed binary accepts these arguments.
2. **The stdout report schema is this stage's own definition.** A real CLI emits whatever it is
   prompted to emit; making it emit this schema is the Agent layer's prompt-assembly job
   (AUTO-005). The `_extract_report_payload` hook exists so AUTO-007 can adapt a live CLI's
   transport without touching shared schema validation.
3. **A defect was found and fixed during self-review, not merely noted.** Redacting stdout *before*
   `json.loads` corrupted valid reports: redaction rewrites arbitrary spans, so a QA finding
   containing `password = hunter2` had its closing quote swallowed and the entire report became
   `MALFORMED_OUTPUT`. That failed in the worst direction — the reports most likely to be destroyed
   were exactly the credential-related QA findings an operator most needs. Fixed by parsing raw
   stdout and redacting each extracted value; the audit record still holds only redacted output.
   Regression test: `test_redaction_never_corrupts_the_report_structure`.
4. **Isolation was nominal before self-review.** The session directory was created but never given
   to the CLI. `TMPDIR`/`AGENTOS_SESSION_DIRECTORY` now point at it and it is created `0o700`, so
   the directory is a real boundary rather than an empty directory nothing uses.
5. **`MockProvider` deliberately does not re-implement invocation validation**, so a test wanting
   the refusal path must use a real adapter. This is intentional — two validators could disagree
   while both claiming to have checked — and is asserted by
   `test_mock_tolerates_an_invocation_a_cli_provider_would_refuse`.
6. **Deviation from plan: none.** No out-of-scope work was performed; no AUTO-005 work was begun.

## Open questions

None new. No `OPEN_QUESTIONS.md` entry was added: nothing in this stage required an owner decision.
OD-2 (secret redaction) was already resolved by AUTO-003 (DD-33) and is consumed here unchanged.

## Git diff summary

Tracked modifications (`git diff --stat`), governance/documentation only:

```
 docs/DECISION_LOG.md                       | 34 ++++++++++++++++++++++++++
 docs/PROJECT_STATE.md                      | 10 +++++---
 docs/TASK_QUEUE.md                         | 39 +++++++++++++++++++++++++-----
 docs/current_task.md                       | 37 +++++++++++++++++-----------
 docs/remaining_tasks.md                    | 16 ++++++------
 docs/workflow-automation/STAGE_REGISTRY.md |  4 ++-
```

Plus the untracked new package and tests (2,360 lines across 9 files), this report, the two
changelog entries, and the refreshed handoff.

## Recommended commit message

```
feat(workflow): add Claude Code CLI and Codex CLI provider adapters (AUTO-004)
```

## Final stage status

**IN_PROGRESS — stopped for Human Owner approval.** Not `COMPLETE`: closure is the Human Owner's
act.

## Confirmation

No commit, push, pull request, merge, tag, branch rename, branch deletion, or history alteration
was performed. Both pre-existing stashes are untouched. No successor stage was begun, selected, or
prepared: AUTO-005 remains `NOT_STARTED` and unauthorized.

---

## Addendum 1 — Human Owner approval, commit, closure, and merge (2026-07-28)

**This addendum is appended, not merged into the text above.** Nothing earlier in this report has
been edited. In particular the Confirmation section's statement that no commit, push, pull
request, or merge was performed was **accurate when written**: every event recorded below happened
afterwards, under a separate Human Owner decision. Rewriting that section to make it read as
though the commit already existed would falsify what the delivering session actually did, which
`docs/workflow-automation/STAGE_REGISTRY.md` §3 rule 8 forbids and the Human Owner's decision
explicitly prohibited.

### What the Human Owner decided

> *"I approve the AUTO-004 implementation and authorize its formal closure and publication. The
> approved AUTO-004 commit is `84616d5`."*

The decision directed, in order: record AUTO-004 as implemented, validated, approved, and
committed locally as `84616d5`; move the task `Current → Done` and the registry state
`IN_PROGRESS → COMPLETE`; append a closure entry to the Authorization Log and a Human Owner
approval entry to `docs/DECISION_LOG.md`; reconcile every governance mirror and the handover
checksum; then push, merge into `main`, and push `main` — retaining the stage branch and leaving
both stashes untouched.

### Events recorded by this addendum

| Event | Value |
|---|---|
| Approved implementation commit | `84616d5` — `feat(workflow): add Claude Code CLI and Codex CLI provider adapters (AUTO-004)` |
| Commit authored | 2026-07-28, after this report was written |
| Task status | `Current → Done` |
| Registry state | `IN_PROGRESS → COMPLETE` (§4); closure row appended to §5 |
| Stage branch | `feature/auto-004-model-providers` — pushed to `origin`, **retained** (not deleted) |
| Merge into `main` | see the integration table below |
| Stashes | `stash@{0}`, `stash@{1}` — untouched throughout |

### Integration result

`main` was updated from `origin/main` without rewriting history and the stage branch merged by the
repository's established policy (the same no-fast-forward merge shape used for AUTO-002's `87a5062`
and AUTO-003/GOV-AUTO-01's `a3b5b0a`). Post-merge verification confirmed: `main` contains
`84616d5`; `agentos_workflow/providers/` exists on `main`; local `main` equals `origin/main`; the
working tree is clean; AUTO-004 is `Done`/`COMPLETE`; and the governance, task-state, and handover
checks pass. Exact commit identifiers and command output are recorded in the AUTO-005 stage report
(`AUTO-005-completion-report.md`, "AUTO-004 closure and merge results"), which is the session
record for the integration itself.

### Status of this stage

**COMPLETE.** No part of the AUTO-004 implementation was changed by this addendum — it is a
governance record only. The two known limitations recorded above (the providers' argv shapes are
unverified against a live CLI, deferred to AUTO-007) remain open and unaffected.
