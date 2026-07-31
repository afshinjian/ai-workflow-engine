# GOV-AUTO-07 — Completion Report

**Task:** Normalize the `AuthorizationBindingDriftError` expected/actual convention (resolves
AUTO-008 finding F-1)
**Status at time of writing:** Implemented and validated; **uncommitted and stopped for Human Owner
approval**. No implementation or closeout commit, no push, no merge, no upstream change, no stash.
*(Superseded by the 2026-07-31 closure addendum at the end of this report — the Human Owner has
since approved this stage; §9's stopping point describes the state as it stood at approval time and
is retained unedited as the accurate historical record.)*
**Branch:** `feature/gov-auto-07-drift-argument-convention`, created from clean, synchronized `main`
at `d8d10ec54c38571f6a4453a11d0e99c53d151743`.
**Governance commit (already made, separate from implementation):** `55dd9ad`
`docs(governance): register and authorize GOV-AUTO-07`.

---

## 1. Baseline verification (before any edit)

| Check | Result |
|---|---|
| `git rev-parse HEAD` | `d8d10ec54c38571f6a4453a11d0e99c53d151743` — matches expected |
| `git rev-parse origin/main` | `d8d10ec54c38571f6a4453a11d0e99c53d151743` — `main == origin/main` |
| `git status --porcelain` | empty — working tree clean |
| Branch | `main` |
| `workflowctl verify --config self-governance.yaml` | **PASS** (all five checks; 0 Current, 40 Done, 6 Planned) |

## 2. Governance

`GOV-AUTO-07` was chosen as the task identifier. The governance parser
(`src/ai_workflow_engine/governance/parser.py`, `TASK_ID = re.compile(r"\b([A-Za-z]+-\d+)\b")`)
resolves it to `AUTO-07`, which is unused — verified by enumerating every `AUTO-\d{1,2}` and
`GOV-AUTO-\d+` token across `docs/` and `handover/` (`GOV-AUTO-01..06` / `AUTO-01..06` present,
nothing at `07`). An `AUTO-008-F1`-style identifier is unusable for the reason already recorded for
GOV-AUTO-06: the parser resolves it to the existing `Done` task `AUTO-008`, producing a duplicate
`Current` entry that breaks `check-task-state` and `check-registries`.

Registration and authorization were recorded **before any implementation edit**, in their own
commit `55dd9ad`, across the nine documents the GOV-AUTO-06 precedent establishes:
`docs/TASK_QUEUE.md`, `docs/current_task.md`, `docs/remaining_tasks.md`, `docs/PROJECT_STATE.md`,
`docs/DECISION_LOG.md`, `docs/CHANGELOG.md`, `docs/workflow-automation/STAGE_REGISTRY.md`,
`handover/PROJECT_HANDOVER.md`, `handover/PROJECT_CHECKSUM.md`. Per the GOV-AUTO-01 precedent
(`STAGE_REGISTRY.md` §5) the task is recorded **outside the AUTO family**: no stage-registry row,
no stage contract, no lifecycle state there — only a continuity row in the append-only
authorization log. Registry stage count is unchanged at 18.

After registration, `workflowctl verify` reported `task-state` 1 Current / 40 Done / 6 Planned,
with `governance`, `registries`, and `handover` all PASS.

---

## 3. The original inconsistency

`AuthorizationBindingDriftError(field, expected, actual)` was raised from **13 sites** in
`agentos_workflow/orchestrator/engine.py`. AUTO-008 §2.4 discovered, while fixing the error's
inverted rendered message, that the two authorization-drift call paths pass those two arguments in
**opposite senses**:

| Call path | `expected` was… | `actual` was… |
|---|---|---|
| `_detect_authorization_binding_drift` | the independently-supplied **current** value | the persisted `AuthorizationRecord` |
| `_validate_live_resume_observation` / `_live_drift` | the persisted `AuthorizationRecord` | the **live observation** |

Because the two are mirror images, no fixed "bound value X / current value Y" wording can be
correct at both. AUTO-008 could therefore only *neutralize* the message — restating it as
"expected …, found …" in received-argument order — and reported the underlying parameter
divergence as F-1 rather than fixing it, since normalizing it changes `.expected`/`.actual`
semantics on a safety path and is a deliberate decision rather than a side effect of a message fix.

The operational consequence: a caller or operator reading `.expected` on the primary
authorization-invalidation path got **opposite answers depending on which path happened to raise**.
`.field` was always correct, which is why no existing test caught it — every drift test asserted
`.field` and lock release, never the sides.

**Inspection found a third, smaller instance of the same defect** that the AUTO-008 audit had
classified as conforming under its weaker "required/reference value" framing. It is inverted under
the stricter convention this stage was directed to establish, and is documented in §4/§5 below.

---

## 4. The canonical convention selected

> * **`expected`** is the **reference** the check enforces: the authorization-bound value where the
>   comparison has one, otherwise the invariant/required value the check demands.
> * **`actual`** is the **value under judgement**: the current runtime, repository, live
>   observation, or caller/disk-supplied value found in the reference's place.
>
> Where a persisted `AuthorizationRecord` (or a value derived from it) is one side of the
> comparison, that side is always `expected` — the human authorization is the root of trust, so it
> is never the side reported as "found".

This is exactly the convention the stage directive specified (`expected` = authorization-bound or
required reference; `actual` = currently observed runtime or repository value), with one
disambiguation added because the directive's two clauses do not by themselves resolve every site:

**Precedence and its one deliberate exception.** Where a comparison has an authorization binding on
one side, the binding wins the `expected` slot. Where no binding is involved at all
(`working_tree_forbidden_paths`, `working_tree_unexpected_paths`, `resume_state_policy`,
`repository_exists`, `git_repository`, `planned_branch_exists`, `planned_branch_ancestry`, …),
`expected` carries the required invariant and `actual` carries what violated it. The exception is a
**containment** check — `stage_contract_path` "inside `<contract_root>`": there the reference is the
containment requirement imposed by configuration, and the record-derived path is the value being
judged, so the record-derived path is correctly `actual`. Reversing it would report the violating
path as the thing that was "expected", which is nonsense.

The convention is now written into `AuthorizationBindingDriftError`'s own docstring, so a future
raise site has a stated rule to follow rather than a majority to infer.

**The rendered message wording is deliberately unchanged**, byte for byte. With the convention now
uniform, naming the sides explicitly ("bound value X / current value Y") would finally be correct on
the bound-vs-current paths — but *not* at the sites where neither side is a binding; "bound value
`()`" for `working_tree_forbidden_paths` would substitute a new falsehood for the old one.
"expected …, found …" is exact at every site. This is recorded in a code comment so the choice is
not mistaken for an oversight.

---

## 5. Every call site changed

All changes are in `agentos_workflow/orchestrator/engine.py`. **Every comparison is symmetric
(`!=` on two values), so which drifts are detected, in what order, and with what durable
`-> FAILED` consequence is entirely unchanged. Only which value is reported on which side moved.**

### 5.1 Cluster 1 — `_detect_authorization_binding_drift` (the primary F-1 path)

The loop over `_BINDING_DRIFT_FIELDS` was rewritten so the bound value from `record` is `expected`
and the independently-supplied current value is `actual`:

```python
# before
expected = current_values[field]
actual = getattr(record, field)
if expected != actual:
    raise AuthorizationBindingDriftError(field, expected, actual)

# after
bound = str(getattr(record, field))
current = current_values[field]
if bound != current:
    raise AuthorizationBindingDriftError(field, bound, current)
```

This affects **all ten** `_BINDING_DRIFT_FIELDS`: `workflow_id`, `repository_identity`,
`repository_path`, `stage_id`, `stage_contract_path`, `stage_contract_hash`, `baseline_branch`,
`baseline_commit_sha`, `planned_stage_branch`, `engine_version`. The local names were changed from
`expected`/`actual` to `bound`/`current` so the code states which side is which rather than
restating the parameter names. The added `str(...)` is a no-op at runtime — every one of the ten
fields is declared `str` on `AuthorizationRecord` — and exists only so the value passed to a
`str`-typed parameter is statically `str` rather than `Any` from `getattr`.

### 5.2 Cluster 2 — `_validate_live_resume_observation` / `_live_drift` (2 of 26 calls)

| Site | Before | After |
|---|---|---|
| `repository_path`, bound record vs. configured path | `(str(expected_repository), record.repository_path)` | `(record.repository_path, str(expected_repository))` |
| `repository_identity`, configured vs. bound identity | `(configured_identity, bound_identity)` | `(bound_identity, configured_identity)` |

The second of these is the sharpest evidence that this was a genuine defect and not a stylistic
preference: it sat **immediately adjacent** to `_live_drift("repository_identity", bound_identity,
observed_identity)`. Two consecutive raises on the *same field* put the bound identity on opposite
sides of each other. They now agree.

The other **24** `_live_drift` calls already conformed and are unchanged — including every
bound-vs-observed check (`stage_contract_hash`, `engine_version`, `baseline_commit_sha`,
`current_branch`, `planned_branch_sha`, observed `repository_identity`), every
invariant-vs-observed check, and the `stage_contract_path` containment check discussed in §4.
`_live_drift` gained a docstring stating the convention its callers follow.

### 5.3 Cluster 3 — `_validate_persisted_authorization_evidence` (4 of 8 sites)

This is the instance beyond the two paths F-1 named. Four checks compare the persisted
`AuthorizationRecord` against the `StateTransitionRecord` being replayed, and reported the
**authorization record** — the root of trust — as `actual`:

| Field | Before (`expected`, `actual`) | After (`expected`, `actual`) |
|---|---|---|
| `workflow_id` | `record.workflow_id`, `authorization_record.workflow_id` | `authorization_record.workflow_id`, `record.workflow_id` |
| `repository_identity` | `record.target_repository`, `authorization_record.repository_identity` | `authorization_record.repository_identity`, `record.target_repository` |
| `repository_path` | `record.repository_path`, `authorization_record.repository_path` | `authorization_record.repository_path`, `record.repository_path` |
| `stage_id` | `record.stage_id`, `authorization_record.stage_id` | `authorization_record.stage_id`, `record.stage_id` |

**Why this is in scope, stated plainly.** The stage directive named two divergent paths and
directed that existing conforming callers remain unchanged — but it also required *one unambiguous
convention across all relevant raise sites*, with `expected` defined as the authorization-bound
value. These four sites have an authorization binding on one side and put it in `actual`. Leaving
them would have reproduced, in a third place, exactly the ambiguity F-1 exists to remove, and would
have made the convention unstateable as a rule. The function's own docstring settles the direction
independently: it exists so that "every replayed transition is bound to the *same* canonical path
the authorization itself is bound to, not merely internally consistent with the other transitions
sitting next to it" — the authorization is the anchor, so it is the reference.

I am flagging this explicitly as a judgement call that went slightly beyond the two paths named in
the finding. It is reversible in isolation: the four raise statements are independent one-line
argument swaps with dedicated tests, and reverting them does not disturb clusters 1 or 2.

The other **four** sites in this function are unchanged — `from_state`, `to_state`, `actor`
(required constants as `expected`) and `transition_history` (required description as `expected`).
None has an authorization record on either side.

### 5.4 Sites verified conforming and left untouched

| Site | Why it already conformed |
|---|---|
| `_require_exact_persisted_history` — `transition_history` | required "exact persisted sequence" is `expected`; supplied non-matching sequence is `actual` |
| `_replay_history` — `transition_history` (missing history) | required "persisted transition history for …" is `expected`; "no persisted transition history" is `actual` |
| `resume_workflow` — `ResumeObservationError` wrapper | "independently observable live value" (the requirement) is `expected`; `exc.detail` (what happened) is `actual` |
| 24 of 26 `_live_drift` calls | see §5.2 |
| 4 of 8 `_validate_persisted_authorization_evidence` sites | see §5.3 |

`AuthorizationScopeMismatchError` was deliberately **not** touched. It is a different exception type
covering a different condition (rejecting a *fresh* authorization request, which never mutates an
in-progress workflow), and its message names its own sides explicitly — "context requires X, record
is bound to Y" — so it is internally unambiguous with no reader able to mistake which is which.
Changing it would be the unrelated exception-handling refactor this stage prohibits.

### 5.5 Public surface

`field`, `expected`, and `actual` are preserved as public attributes; the exception's
`__init__` signature is unchanged; the rendered message template is byte-identical. **No caller
migration is required**, and a test pins this (§6). No new public symbol was added.

---

## 6. Tests added

### New module: `agentos_workflow/tests/test_engine_drift_argument_convention.py` (27 tests)

Every test asserts the **sides**, not merely `.field` — `.field` was already correct before this
stage and so could never have detected the inversion.

| Group | Tests | Coverage |
|---|---|---|
| `TestBoundVsCurrentPath` | 12 | All **ten** `_BINDING_DRIFT_FIELDS`, parametrized: bound value is `expected`, current value is `actual`, message renders in that order. Plus a guard that the parametrization set equals `_BINDING_DRIFT_FIELDS` (a new binding cannot silently escape the suite), plus a no-drift negative control proving the reordering did not become a behaviour change. |
| `TestLiveObservationPath` | 7 | Both **normalized** sites (bound `repository_path` vs. configured; bound identity vs. configured identity), the adjacent already-conforming observed-identity site, three already-conforming bound-vs-observed sites (`stage_contract_hash`, `engine_version`, `baseline_commit_sha`) pinned so normalization did not flip them, and a no-binding site (`working_tree_forbidden_paths`) proving the invariant stays in `expected`. |
| `TestPersistedAuthorizationEvidencePath` | 6 | All four cross-record checks (authorization record is `expected`, transition record is `actual`), plus two required-constant sites (`from_state`, `actor`) pinned as unchanged. |
| Module-level | 2 | `test_both_drift_paths_report_the_binding_on_the_same_side` — drives the *same field's* drift through both authorization-drift call paths and requires both to put the binding in `.expected`. This is the F-1 defect stated directly as an assertion. And `test_public_exception_attributes_are_unchanged`, which pins the attribute names and the exact rendered message string. |

### Updated: `test_engine_resume.py::TestAuthorizationBindingDrift::test_drift_message_reports_expected_and_found_in_argument_order`

This was AUTO-008's pin, and it asserted the *old* inverted semantics
(`error.actual == "github.com/org/drifted-repo"`, the tampered record). It was the **only**
pre-existing test in the entire 2,978-test suite that broke — a precise signal that the change
landed where intended and nowhere else. It now asserts the tampered record is `expected` and the
live identity is `actual`, keeps the argument-order assertion, and additionally requires the message
to contain neither `"bound value"` nor `"current value"`. Its docstring records what AUTO-008 fixed
versus what GOV-AUTO-07 fixed.

### Evidence the new tests are real regressions

The engine change was stashed and the new module re-run against the **pre-fix** engine:

> **17 failed, 10 passed in 0.52s**

The 17 failures are exactly the assertions on changed sides (all ten `_BINDING_DRIFT_FIELDS`, both
normalized live sites, all four cross-record checks, and the two-path agreement test). The 10
passes are exactly the already-conforming sites and the invariant/public-surface tests — which
independently confirms §5.4's claim that those sites were not disturbed. The stash was then
restored.

---

## 7. Validation results

All commands run in the `ai-workflow-engine` conda environment (Python 3.11.15) from the repository
root, with the full implementation in the working tree.

| Command | Result |
|---|---|
| Focused drift/resume tests (`test_engine_resume.py`, `test_engine_authorization.py`, `test_f03_live_resume.py`, `recovery/`, `test_engine_retry.py`, `test_workflow_session.py`, new module) | **435 passed** |
| `pytest -q` (full suite) | **3005 passed** in 128.23s |
| `ruff check .` | **All checks passed!** |
| `black --check .` | **210 files would be left unchanged** |
| `mypy` (strict, configured `files`) | **Success: no issues found in 115 source files** |
| `pre-commit run --all-files` | **ruff Passed · black Passed · mypy Passed** |
| `workflowctl verify --config self-governance.yaml` | `task-state` **PASS** (1 Current, 40 Done, 6 Planned) · `governance` **PASS** · `registries` **PASS** (18 stages, 2 registries) · `handover` **PASS** · `git` **FAIL — `upstream_missing` only** |

**Test count:** 2,978 → **3,005**, exactly the 27 tests added. No test was deleted, skipped, or
`xfail`ed. `mypy`'s 115 source files is unchanged because test suites are excluded from type
checking by the pre-existing `[tool.mypy] exclude` setting (AUTO-008's deliberate standard).

**On the single `git` FAIL:** the sole violation is `upstream_missing` — this stage branch has never
been pushed, and `self-governance.yaml` sets `require_upstream: true`. This is pre-existing and
expected by construction for an unpushed stage branch, is the same condition recorded in the
AUTO-001, AUTO-002, AUTO-003, AUTO-005, AUTO-006, AUTO-007, AUTO-008, GOV-AUTO-01, GOV-AUTO-06,
DASH-001 and STAGE-01 reports, clears on push, and is not run by CI. It was verified to be the
**only** violation both before and after the implementation edits. I report it rather than
presenting a green `verify`.

---

## 8. Scope confirmation

**Files changed by the implementation** (uncommitted; the governance commit `55dd9ad` is separate):

```
 M agentos_workflow/orchestrator/engine.py
 M agentos_workflow/tests/test_engine_resume.py
 M docs/CHANGELOG.md
 M docs/workflow-automation/CHANGELOG.md
?? agentos_workflow/tests/test_engine_drift_argument_convention.py
```

Prohibited work — each verified not done:

| Prohibition | Verification |
|---|---|
| Do not begin AUTO-009 | No diff hunk contains the string `AUTO-009`; no file referencing AUTO-009 was touched |
| Do not modify Git/GitHub skill registration | `agentos_workflow/agents/__init__.py` and `skills/git_github.py` unchanged |
| Do not change workflow transitions | No change to `validate_transition`, the transition table, `WorkflowState`, or any `transition_to` path |
| Do not add new features | No new public symbol; no new behaviour — only which value is reported on which side |
| Do not refactor unrelated exception handling | `AuthorizationScopeMismatchError` and every other exception type untouched (§5.4) |
| Do not alter the public CLI | `src/ai_workflow_engine/**` entirely untouched |
| Do not modify shell scripts | `scripts/**` untouched; no shell script consumes this exception contract (`AuthorizationBindingDriftError` appears in no `*.sh` file) |
| Do not clean up redundant E2E manual bindings | `agentos_workflow/tests/e2e/**` untouched |

Documentation updated is limited to what is directly relevant: `docs/CHANGELOG.md` and
`docs/workflow-automation/CHANGELOG.md` (one `### Fixed` entry each), plus this report. No prior
completion report was edited — AUTO-008's report remains the accurate historical record of what it
found and deliberately deferred.

---

## 9. Stopping point

Implementation and validation are complete. Per the stage directive and this repository's
governance, work **stops here, before the implementation/closeout commit and push**:

- The implementation is in the working tree, **uncommitted**.
- `GOV-AUTO-07` remains **`Current`**. No status flip, no closure record, no `DECISION_LOG.md`
  approval entry, no `STAGE_REGISTRY.md` closure row, no handover refresh — those are the closeout,
  and require explicit Human Owner approval of this report first.
- No push, merge, upstream change, branch rewrite, or stash operation was performed.

---

## Addendum — 2026-07-31: Human Owner approval and closure

The Human Owner reviewed this report and the implementation diff, required a final eight-point
verification before any commit, and on its outcome approved the implementation and authorized the
implementation/closeout commit and the push of `feature/gov-auto-07-drift-argument-convention`.

### The eight required checks, and how each was verified

| # | Check | Verification |
|---|---|---|
| 1 | Convention consistently enforced | All **43** raise/helper call sites re-enumerated and audited individually against the rule (8 in `_validate_persisted_authorization_evidence`, 1 in `_require_exact_persisted_history`, 1 in `_replay_history`, 1 covering the 10 `_BINDING_DRIFT_FIELDS`, 26 `_live_drift` calls, 1 `ResumeObservationError` wrapper). Every one conforms; the one deliberate carve-out (the `stage_contract_path` containment check) is documented in §4 and on the exception itself. |
| 2 | All changed sites belong to this fix | The engine diff contains exactly three semantic clusters plus docstrings/comments. No unrelated hunk. |
| 3 | Detection behaviour unchanged | The **only** conditional line in the entire engine diff is `- if expected != actual:` → `+ if bound != current:` — the same two operands under the same symmetric operator, renamed to state which side is which. Clusters 2 and 3 changed argument order only; their `if` conditions are untouched. |
| 4 | Public surface compatible | The message template produced **zero** `+`/`-` lines in the diff — byte-identical. Attribute names and `__init__` signature unchanged, pinned by `test_public_exception_attributes_are_unchanged`. |
| 5 | Cross-record checks correctly included | All four verified to place `authorization_record.*` in `expected` and the replayed `StateTransitionRecord` in `actual`, consistent with the function's own stated purpose. The four sites in the same function with no authorization record on either side (`from_state`, `to_state`, `actor`, `transition_history`) correctly keep the required constant as `expected`. |
| 6 | Regression tests genuinely exercise the paths | Re-confirmed at the final formatted state by stashing `engine.py`: **17 failed, 10 passed** against the pre-fix engine; **27 passed** with it restored. The 10 pre-fix passes are exactly the already-conforming sites and the invariant/public-surface tests. |
| 7 | Prohibited surfaces untouched | `scripts/`, `src/ai_workflow_engine/`, `agentos_workflow/agents/`, `agentos_workflow/skills/`, `agentos_workflow/tests/e2e/`, `agentos_dashboard/`, `.github/`, and the root `tests/` tree all report **0 changed files**. No diff hunk adds or removes any reference to `AUTO-009`, `validate_transition`, the transition table, `default_skill_registry`, or `PROVISIONAL_SKILL_NAMES` (the single grep hit is an unmodified context line in `docs/CHANGELOG.md`). |
| 8 | No residue | No `TODO`, `FIXME`, `XXX`, `HACK`, `breakpoint()`, `pdb.set_trace`, or stray `print(` in any changed file. No `pytest.skip`, `xfail`, or skip marker anywhere. The single `# type: ignore[arg-type]` in the new test module annotates a `dict[str, object]` splat into a frozen dataclass and matches three pre-existing instances of the identical pattern (`test_workflow_session.py:116`, `test_f03_live_resume.py:174`); test suites are excluded from `mypy` by the pre-existing `[tool.mypy] exclude` setting. |

### Final validation, re-run immediately before commit

| Command | Result |
|---|---|
| `pytest -q` | **3005 passed** in 146.98s |
| `ruff check .` | All checks passed! |
| `black --check .` | 210 files would be left unchanged |
| `mypy` (strict) | Success: no issues found in 115 source files |

### Provenance of this closure

Approval was given directly in session, and the governance closeout was performed manually rather
than through `scripts/workflow-approve.sh`. That script requires the Human Owner to type two exact
`APPROVE` confirmations interactively; the implementation agent must not supply them on the Human
Owner's behalf, since that gate exists specifically to be human-supplied. The document set and
commit structure match what the script produces, and the wording here records what actually
happened rather than claiming a script-mediated confirmation that did not occur.

### State after closure

Task status moves `Current -> Done`. The implementation and this closeout were committed together
in one local commit and the branch was pushed. **No PR was opened and no merge was performed.**
This closure authorizes no successor: AUTO-009 and every later roadmap phase require their own
fresh written authorization.
