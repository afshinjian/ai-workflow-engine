# AUTO-008 Completion Report

## Stage identity

- **Stage:** AUTO-008 — Engine CI baseline: land `agentos_workflow` in CI, packaging, and
  type-checking; fix the three verified blockers; make the end-to-end dry run green.
- **Role:** Engine implementation session
- **Branch:** `feature/auto-008-engine-ci-baseline`
- **Baseline:** `main` @ `96a6bb4` (DASH-004 published to `main` as a prerequisite of this stage)
- **Status at time of writing:** implemented and validated; **uncommitted**, stopped for Human
  Owner approval before any AUTO-008 commit or push. (Superseded by the closure addendum at the end
  of this report — approved and closed 2026-07-30. This line is preserved unchanged as the record of
  what was submitted for review.)
- **Scope discipline:** no new features and no new public interfaces. No command, flag, config
  field, state, or agent capability was added.

---

## 1. Prerequisite publication (authorized separately)

`main` was at `8dba9c5` — DASH-004's *authorization* commit only. DASH-004's implementation
(`96a6bb4`, 26 files) sat on `feature/dash-004-dashboard-shell`, pushed but unmerged, while
governance already recorded DASH-004 as `Done`. `main` therefore did not match governance.

Resolved by explicit Human Owner instruction, as a clean fast-forward:

| Step | Evidence |
|---|---|
| Fast-forward eligibility confirmed | `96a6bb4^` == `8dba9c5` == `main`; `git merge-base --is-ancestor` → yes |
| Merge performed | `git merge --ff-only 96a6bb4` → `main` = `96a6bb4`, no merge commit |
| Contents verified | dashboard files on `main`: 36 → **62**; `agentos_dashboard/main.py`, `api/security.py`, `web/templates/overview.html`, `docs/reports/agentos-dashboard/STAGE-04-completion.md` all present |
| Working tree | clean before and after |
| Published | `git push origin main` → `e181737..96a6bb4` |

`main` and `origin/main` are now both `96a6bb4`, and `main` matches what governance records.

---

## 2. What was changed, and why

15 files modified, 1 added; **+344 / −93**. No file outside the approved scope was touched.

### 2.1 Independent engine version — root cause of the failing acceptance test

**Added `agentos_workflow/__about__.py`** (`__version__ = "0.1.0"`) and rewrote
`observation/local.py::running_engine_version` to read it.

Previously that function returned `importlib.metadata.version("ai-workflow-engine")` — the version
of the whole repository's *distribution*, which also covers the entirely separate legacy
`src/ai_workflow_engine/` engine that `agentos_workflow` neither imports nor depends on.

Because `HUMAN_AUTHORIZATION_MODEL.md` §2 item 11 binds the engine version into every
authorization and §4 makes a later mismatch an authorization invalidator, that coupling had two
consequences:

1. **The observed failure.** The AUTO-007 end-to-end dry run pins `engine_version="0.1.0"`. Once
   `pyproject.toml` moved to `1.0.0`, the live observer reported `1.0.0`, the bound record said
   `0.1.0`, and the run died with `AuthorizationBindingDriftError`.
2. **The latent defect that mattered more.** Any future release of the legacy engine would
   silently invalidate every in-flight `agentos_workflow` authorization and force
   re-authorization from `CREATED` — a safety-critical state transition triggered by an unrelated
   package's version bump.

Two independently-versioned subsystems must not share one version number. The
`_DEVELOPMENT_VERSION` fallback was also removed as newly meaningless: a module constant reads
identically whether the package is installed, editable, or imported from source, so a resume can
no longer observe a different engine version merely because of how the code was loaded.

**Verified live:** engine version `0.1.0` while distribution version is `1.0.0`, coexisting with
no drift error. Pinned by
`test_f03_live_resume.py::test_running_engine_version_is_independent_of_the_distribution_version`.

### 2.2 OD-11 — `stage_contract_hash` format disagreement (resolved)

`PMOAgent.check_preconditions` compared `calculate_contract_hash`'s bare-hex `ContractHash.sha256`
against `authorization.stage_contract_hash`, while `LocalResumeObserver` — the live observer
`resume_workflow` uses whenever a real `config` is supplied, i.e. **the production path** — computed
and compared a `"sha256:<hex>"`-prefixed value for the same semantic field.

No `AuthorizationRecord` value could satisfy both. A bare-hex value passed
`PRECONDITIONS_CHECKED` and then **guaranteed** a false-positive `AuthorizationBindingDriftError`
on the workflow's first real resume; a prefixed value failed `PRECONDITIONS_CHECKED` instead.

Resolved by unifying on the algorithm-prefixed form — the format the production resume path
already observes, and the one that keeps a stored digest self-describing:

- `skills/contract.py`: added `CONTRACT_HASH_ALGORITHM_PREFIX` and
  `ContractHash.authorization_value`, the single canonical authorization format.
  `ContractHash.sha256` deliberately remains the bare digest, so callers wanting the raw hash do
  not have to strip a prefix.
- `agents/pmo.py`: compares `authorization_value`.

**Why the test suite never caught it:** `test_agents_pmo.py` and `test_engine_resume.py` each
unit-tested their own side against a hand-built record in their own module's convention — bare and
prefixed respectively — so both suites passed while the two halves disagreed. `test_agents_pmo.py`'s
`contract_hash` helper has been corrected to the canonical format, and the cross-module agreement
is now pinned directly by
`test_skills_contract.py::test_authorization_value_matches_the_resume_observer_format`, which
computes both independently and asserts byte equality. That test is the actual regression guard:
the two implementations cannot import each other (the AUTO-002 observation component must not
depend on the AUTO-003 Skill layer, `ARCHITECTURE.md` §10), so only a test that computes both can
keep them aligned.

### 2.3 OD-10 — `allowed_environment_variables` never forwarded (resolved)

`GitAgent` and `MergeAgent` invoked their `gh`-facing Skills without forwarding the environment
allowlist, so `gh` ran with an empty environment and could not see its own credential or
configuration variables. `MergeAgent` had no allowlist parameter at all.

All call sites whose Skill accepts the parameter now forward it — **seven** in total (one,
`push_stage_branch`, was already correct):

| File | Skill | Before | After |
|---|---|---|---|
| `agents/git.py` | `create_commit` | not forwarded | forwarded |
| `agents/git.py` | `push_stage_branch` | forwarded | unchanged |
| `agents/git.py` | `create_pull_request` | not forwarded | forwarded |
| `agents/git.py` | `read_pull_request_state` | not forwarded | forwarded |
| `agents/git.py` | `verify_head_sha` | n/a | **deliberately excluded** |
| `agents/merge.py` | `verify_head_sha` | n/a | **deliberately excluded** |
| `agents/merge.py` | `enable_automatic_squash_merge` | not forwarded | forwarded |
| `agents/merge.py` | `read_required_checks` | not forwarded | forwarded |
| `agents/merge.py` | `verify_merge_completion` | not forwarded | forwarded |

`verify_head_sha` is excluded because its Skill signature
(`git_github.py:367`) takes no `allowed_environment_variables`: it is a purely local
`git rev-parse` against the repository's own refs, with no network call and therefore no
environment to allowlist. Forwarding there would have been a `TypeError`, not a fix.

`MergeAgent` gained an `allowed_environment_variables` parameter defaulting to `()`, matching
`GitAgent`, so an omitted value is an explicitly empty allowlist rather than a silently inherited
process environment.

### 2.4 `AuthorizationBindingDriftError` message — corrected, and a deeper finding

The message interpolated `actual` as "bound value" and `expected` as "current value". Verified
live: a `repository_identity` drift where the bound record said `github.com/org/drifted-repo`
printed *"bound value 'github.com/org/repo' … current value 'github.com/org/drifted-repo'"* —
exactly backwards, on the primary safety-invalidation path.

**This could not be fixed by swapping the two words**, and finding out why produced the most
significant new discovery of this stage. Auditing all 13 raise sites in `orchestrator/engine.py`:

- **11 sites** follow one convention: `expected` = the required/reference value, `actual` = what
  was actually found.
- **`_detect_authorization_binding_drift`** (line 1696) passes the independently-supplied
  **current** value as `expected` and the **persisted record** as `actual`.
- **`_validate_live_resume_observation`** / `_live_drift` (lines 1766, 1812) passes the
  **persisted record** as `expected` and the **live observation** as `actual`.

The two "bound vs current" sites are **mutually inverted**, so any fixed "bound value X / current
value Y" wording is necessarily backwards at one of them. The message therefore no longer claims
to know which side is the binding; it states the reference and the finding in received-argument
order, which is faithful at every raise site. `field` already tells the reader which binding
drifted, and callers needing the sides distinguished read `.expected` / `.actual`.

New message: `Authorization binding drift on 'X': expected 'A', found 'B'. Per
HUMAN_AUTHORIZATION_MODEL.md §4, …`

Pinned by
`test_engine_resume.py::TestAuthorizationBindingDrift::test_drift_message_reports_expected_and_found_in_argument_order`,
which asserts argument order *and* that the message no longer re-asserts which side is the
binding. Both attributes were always correct, so only the rendered text could catch this — no
prior test asserted the message text at all.

**The underlying parameter-convention divergence is reported, not fixed** — see §6, finding F-1.
Normalising it changes `.expected` / `.actual` semantics at a raise site on a safety path, which
is a deliberate decision, not a side effect of a message fix.

### 2.5 Test-only production workarounds removed

`tests/e2e/test_dry_run.py` carried two test-only wrappers that papered over §2.2 and §2.3:
`_prefixed_contract_hash` and `_gh_env_forwarding`. Both are **deleted**, along with the three
`CapabilityBroker` registry overrides that applied them; `MergeAgent` now receives the fake `gh`'s
allowlist the way a real configuration will.

Their removal is the point. That dry run's value was always that it found defects unit tests could
not; a workaround left in place would have quietly re-hidden them. The module docstring — which
documented both defects as open and unfixable within AUTO-007's allowed paths — has been rewritten
to record them as resolved, and to state plainly that this test proves orchestration logic against
`MockProvider` and a fake `gh` and is **not** evidence about real CLI or real GitHub behaviour.

### 2.6 CI, packaging, and type-checking

| Setting | Before | After |
|---|---|---|
| `pytest` `testpaths` | `["tests"]` | `["tests", "agentos_workflow/tests", "agentos_dashboard/tests"]` |
| wheel `packages` | `src/ai_workflow_engine` | + `agentos_workflow`, `agentos_dashboard` |
| `mypy` scope | `packages = ["ai_workflow_engine"]`, invoked `mypy src` | `files` = all three source trees, invoked bare `mypy` |
| CI install | `.[dev]` | `.[dev,dashboard]` |
| CI tests | `pytest -q` | `pytest -q` (**unchanged**; `testpaths` does the work) |
| pre-commit mypy | `args: [src]` | no `args` (uses configured `files`) |

**Measured CI blind spot this closes:** default collection was **1,160** tests. `agentos_workflow`
has **1,575** and `agentos_dashboard` **228** — so **1,803 of 2,963 tests (61%)** never ran in CI,
covering the newest and largest subsystem. Default collection is now **2,967**.

Two deliberate choices:

- **`files` rather than `packages` for mypy.** `packages` resolves names through the installed
  distribution and refuses a package with no `py.typed` marker; `files` checks them as source
  trees, exactly as the previous `mypy src` did. Declaring the set in `pyproject.toml` rather than
  on the command line is what lets CI and pre-commit both run a bare `mypy` and check an identical
  set — a path argument in either place could silently drift out of date.
- **Test suites excluded from mypy** (`exclude = "^(agentos_workflow|agentos_dashboard)/tests/"`),
  matching the pre-existing standard: `mypy src` never checked the top-level `tests/` tree either.
  Bringing ~2,000 tests under `strict` is a separate, deliberate decision.

**A scope correction made during final review.** An earlier revision of this stage also declared
`live_cli` / `live_gh` pytest markers and changed the CI command to
`pytest -q -m "not live_cli and not live_gh"`. Both were removed before commit: no test carries
either marker, so they were anticipatory infrastructure for AUTO-010 with no current consumer, and
the `-m` filter was a behavioural change to CI beyond this stage's objective of "run all three
suites". AUTO-010 should add the markers when it adds the tests that need them. The CI test command
is therefore byte-unchanged from baseline.

### 2.7 Dashboard test decoupled from mutable governance content

`test_real_task_queue_parses_dash_003_as_current` asserted the *live* `docs/TASK_QUEUE.md` shows
DASH-003 as `Current`. DASH-003 closed to `Done` on 2026-07-29, so the test failed on normal
project progress it was never meant to police.

Replaced with `test_real_task_queue_remains_parseable`, which asserts parseability and internal
consistency — `HIGH` confidence, non-empty, unique task IDs, valid statuses, and at most one
`Current` task (`maximum_current_tasks: 1` is a ceiling, so an empty Current set is legal) — and
asserts no particular task's status. Status-specific parsing behaviour remains covered
exhaustively by the fixture-based tests, where the input is fixed and the expected output can be
stated precisely.

---

## 3. Validation results

Every command below was run on this branch with the working tree as submitted.

| # | Check | Command | Result |
|---|---|---|---|
| 1 | Tests | `pytest -q` | **2967 passed, 0 failed** (125.09s) |
| 2 | Lint | `ruff check .` | **All checks passed** |
| 3 | Format | `black --check .` | **209 files unchanged** |
| 4 | Types | `mypy` | **Success: no issues found in 115 source files** |
| 5 | pre-commit | `pre-commit run --all-files` | **ruff / black / mypy all Passed** |
| 6 | Wheel build | `pip wheel . --no-deps` | built; contains `ai_workflow_engine` (56), `agentos_workflow` (64), `agentos_dashboard` (62) |
| 7 | Editable install | `pip install -e ".[dev,dashboard]"` | succeeded |
| 8 | Importability from outside repo root | probe from `/tmp` | all three packages **OK** (previously 2 of 3 `NOT IMPORTABLE`) |
| 9 | Version decoupling | live probe | engine `0.1.0`, distribution `1.0.0`, no drift |
| 10 | CI config | YAML parse + step extraction | parses; steps are `ruff check .`, `black --check .`, `mypy`, `pytest -q`, governance checks |
| 11 | pre-commit config | YAML parse | parses |
| 12 | CI governance checks (isolated copy) | `check-task-state`, `check-governance`, `check-handover`, `check-registries` | **all PASS** |

### 3.1 End-to-end acceptance test

`agentos_workflow/tests/e2e/test_dry_run.py::test_full_workflow_created_to_done_with_one_repair_and_one_interruption`
— **failing at baseline, now passing**, with **zero** test-only production workarounds. This is
`MVP_SCOPE.md` §4's first acceptance demonstration (`MockProvider`-driven).

### 3.2 Test-count reconciliation

| Suite | Baseline (collected) | Now |
|---|---|---|
| `tests/` | 1,160 | 1,160 |
| `agentos_workflow/tests/` | 1,575 (never in CI) | 1,579 (+4 added) |
| `agentos_dashboard/tests/` | 228 (never in CI) | 228 |
| **Default `pytest` collection** | **1,160** | **2,967** |
| Failing | 2 | **0** |

Four tests added: two OD-11 format tests, one drift-message test, one version-decoupling test.

### 3.3 One check does not pass, and why

`workflowctl verify --config self-governance.yaml` → **FAIL**, on exactly one finding:

```
FAIL git: Git check found 1 violation(s)
  - upstream_missing: The configured project requires an upstream
```

The other four checks (`task-state`, `governance`, `registries`, `handover`) **PASS**.

This is an artifact of `feature/auto-008-engine-ci-baseline` having no upstream yet, against
`self-governance.yaml`'s `require_upstream: true`. It is **not** caused by any change in this stage
— the same command PASSED at baseline on `feature/dash-004-dashboard-shell`, which had an upstream
— and it will clear when this branch is pushed. CI does not run `check-git` at all (per the
existing comment in `ci.yml`: `actions/checkout` produces a detached HEAD with no upstream).

I am reporting this rather than presenting a fully green `verify`, because a green `verify`
is not achievable before publication and I was instructed to stop before pushing.

---

## 4. What this stage did **not** do

Stated explicitly so no downstream reader over-reads the result:

- **No real Claude CLI, Codex CLI, or GitHub call was made.** Provider behaviour against the real
  CLIs remains unverified; `MVP_SCOPE.md` §4's second acceptance demonstration ("a real
  target-repository run") is still outstanding. That is AUTO-010 / AUTO-013 scope.
- **No new features or public interfaces.** No CLI command, config field, workflow state, agent
  capability, or provider flag was added.
- **No `WorkflowService`, mode driver, approval subsystem, or orchestration driver.** There is
  still no production code that sequences the six agents; the only end-to-end composition remains
  the dry-run test.
- **No shell script was changed or retired.** `scripts/*.sh` remains the working automation path.
- **`src/ai_workflow_engine/` was not touched.** Its Milestone 1–4 surface and JSON contract are
  byte-unchanged.
- **Test suites were not brought under mypy.**

---

## 5. Files changed

```
 .github/workflows/ci.yml                           |  13 ++-
 .pre-commit-config.yaml                            |   8 +-
 agentos_dashboard/tests/test_parsing_task_queue.py |  23 +++-
 agentos_workflow/__about__.py                      |  new
 agentos_workflow/agents/git.py                     |   3 +
 agentos_workflow/agents/merge.py                   |   9 ++
 agentos_workflow/agents/pmo.py                     |  11 +-
 agentos_workflow/observation/local.py              |  22 ++--
 agentos_workflow/orchestrator/engine.py            |  21 +++-
 agentos_workflow/skills/contract.py                |  31 ++++++
 agentos_workflow/tests/e2e/test_dry_run.py         | 120 +++++++-----------
 agentos_workflow/tests/test_agents_pmo.py          |  18 +++-
 agentos_workflow/tests/test_engine_resume.py       |  42 ++++++++
 agentos_workflow/tests/test_f03_live_resume.py     |  35 ++++++
 agentos_workflow/tests/test_skills_contract.py     |  40 +++++++
 pyproject.toml                                     |  41 ++++++-
 15 files changed, 344 insertions(+), 93 deletions(-)
```

---

## 6. Findings reported, not fixed

Each is outside AUTO-008's approved scope. None blocks this stage; **F-1 and F-2 block a first
real run** and should be scheduled before AUTO-013.

**F-1 — `expected`/`actual` convention is inverted between the two drift call sites.**
`_detect_authorization_binding_drift` (`engine.py:1696`) passes current-as-`expected`,
record-as-`actual`; `_validate_live_resume_observation` (`engine.py:1812`) passes
record-as-`expected`, observation-as-`actual`. §2.4 made the *message* faithful at both, but the
divergence itself remains and will mislead any future code that branches on which side is the
binding. Normalising it changes `.expected`/`.actual` semantics on a safety path and needs its own
decision. **Recommend: RECOMMENDED, before AUTO-013.**

**F-2 — the eight Git/GitHub Skills delivered by AUTO-006 are still not bound in
`default_skill_registry()`.** `agents/__init__.py`'s `PROVISIONAL_SKILL_NAMES` still lists
`create_commit`, `push_stage_branch`, `create_pull_request`, `read_pull_request_state`,
`verify_head_sha`, `read_required_checks`, `enable_automatic_squash_merge`, and
`verify_merge_completion` as undelivered, with the comment "belong to AUTO-006" — but AUTO-006 is
`COMPLETE` and `skills/git_github.py` implements all eight. The default registry was never
updated, so `GitAgent` and `MergeAgent` cannot function with it; the dry run has to bind those
eight by hand. This is a wiring gap of exactly the kind AUTO-008 exists to surface, but binding
them changes agent capability reachability and is therefore a functional change, not a CI fix.
**Recommend: REQUIRED, before AUTO-013.**

**F-3 — the wheel ships both test suites.** `agentos_workflow` (64 files) and `agentos_dashboard`
(62 files) include their `tests/` trees, because tests live inside the packages. Harmless (size
only) and excluding them risks breaking source-tree test runs. **Recommend: OPTIONAL.**

**F-4 — `MergeAgent`'s module docstring is stale.** It states "All four Skills here are delivered
by AUTO-006 and are unbound today", which is now half-true: they are delivered, and unbound only
because of F-2. Correct alongside F-2. **Recommend: OPTIONAL.**

**F-5 — `docs/implementation/orchestration/` does not exist**, yet `pyproject.toml`'s `black`
`force-exclude` and `ruff` `extend-exclude` both reference it as frozen evidence. Dead
configuration. **Recommend: OPTIONAL.**

---

## 7. Governance position

AUTO-008 is a **new** stage. It is not registered in
`docs/workflow-automation/STAGE_REGISTRY.md`, is not present in `docs/TASK_QUEUE.md`, and no
authorization record naming it exists in the repository. Per `docs/current_task.md`, the `Current`
set is empty and "every remaining task is Planned and requires its own fresh written Human Owner
authorization naming it before it may become Current."

Accordingly, **no governance mutation has been performed**: no task-queue row, no registry row, no
authorization-log entry, no mirror update, and no closeout. The implementation stands alone and
uncommitted.

On approval, the governance sequence this repository uses (per AUTO/DASH precedent) is:

1. Register AUTO-008 as `Planned`, then record the Human Owner authorization naming it — one
   governance-only commit (`docs(governance): authorize AUTO-008`), matching `8dba9c5`'s pattern.
2. Commit the implementation with its closeout in one commit, as
   `scripts/workflow-approve.sh`'s automatic closeout (GOV-AUTO-03) does.
3. Push, and publish per your instruction.

I have not performed step 1, because registering and authorizing a stage is the Human Owner's act,
not the implementation session's.

---

## 8. Requested decision

The implementation is complete and validated within the approved Phase 0 scope. **Nothing has been
committed or pushed for AUTO-008.** The only publication performed was the separately-authorized
DASH-004 fast-forward to `main` (§1).

On your approval I will finalize, commit, and push. Please also indicate whether you want F-1 and
F-2 folded into a follow-up stage before AUTO-013.

---

## Closure addendum — 2026-07-30 (append-only)

The Human Owner required an explicit verification of scope, behavioural containment, and cleanliness
before approving. That verification is recorded here because it changed the delivered code.

**Two self-inflicted defects were found and corrected before commit:**

1. **Scope creep — `live_cli`/`live_gh` markers and the CI `-m` filter.** An earlier revision
   declared both pytest markers and changed the CI command to
   `pytest -q -m "not live_cli and not live_gh"`. No test carried either marker, so they were
   anticipatory infrastructure for AUTO-010 with no current consumer, and the `-m` filter was a
   behavioural change to CI beyond this stage's objective of "run all three suites". Both removed;
   the CI test command is byte-unchanged from baseline. AUTO-010 should add the markers alongside
   the tests that need them. §2.6 reflects the corrected state.

2. **A tautological assertion in the new version test.** The test ended with
   `assert running_engine_version() == declared != "" and (distribution_version == declared or
   running_engine_version() != distribution_version)`. Given the test's own preceding assertion,
   that expression could never fail — it asserted nothing while appearing to assert the central
   property. It also used a conditional `pytest.skip` that could silently disable the check.
   Rewritten to parse `observation/local.py`'s AST and assert the module imports no distribution
   metadata at all. That pins the decoupling *structurally*, which matters because asserting the two
   version values merely differ would pass today (0.1.0 vs 1.0.0) and then silently pass for the
   wrong reason the day they coincide. A first attempt used a plain substring scan and failed
   correctly — the module's own docstring quotes the `importlib.metadata.version(...)` call it no
   longer makes — which is why the check parses rather than greps.

**Verification outcomes as approved:**

| Question | Answer |
|---|---|
| Every modification strictly within approved AUTO-008 scope? | **Yes**, after removing the markers and CI `-m` filter |
| No behavioural change outside documented Phase 0 objectives? | **Yes.** The only runtime-behaviour changes are the four documented fixes. The drift-message change affects the rendered text of all 13 raise sites, which is the documented fix itself, not a side effect |
| No debugging code, compatibility workaround, commented-out code, TODO marker, or test-only production path? | **Yes.** Zero `TODO`/`FIXME`/`XXX`/`HACK`, no `print`/`pdb`/`breakpoint`, no commented-out code, no `skipif`/`xfail`. The only occurrences of the word "workaround" are in a comment documenting the removal of the two that existed. Both test-only production paths (`_prefixed_contract_hash`, `_gh_env_forwarding`) are deleted |

**Final validation, re-run after the corrections:** `pytest -q` → 2,967 passed, 0 failed;
`ruff check .` → all checks passed; `black --check .` → 209 files unchanged; `mypy` → no issues in
115 source files; `pre-commit run --all-files` → ruff, black, mypy all passed; all four CI
governance checks PASS.

**Commit sequence:** `docs(governance): register and authorize AUTO-008` (`d7df318`, governance
only), then this stage's implementation together with its governance closeout in one commit, per
`scripts/workflow-approve.sh`'s automatic-closeout model (GOV-AUTO-03).

Registry state `AUTHORIZED → COMPLETE`; task status `Current → Done`. This closure authorizes no
successor. F-1 and F-2 (§6) remain open; **F-2 is REQUIRED before AUTO-013**, since `GitAgent` and
`MergeAgent` cannot function with the default skill registry until AUTO-006's eight Git/GitHub
Skills are bound into it.
