# GOV-AUTO-06 Completion Report

## Task identity

- **Task:** GOV-AUTO-06 — Bind delivered Git/GitHub skills into the default AgentOS skill registry
- **Resolves:** AUTO-008's deferred finding **F-2**
- **Branch:** `feature/auto-008-f2-bind-github-skills`
- **Baseline:** `main` @ `2c8844c4e2c3f78271743b41e4f489155169e5d0` (verified before any change; tree clean)
- **Status:** implemented and validated; **implementation uncommitted**, stopped for Human Owner
  approval. One governance-only commit (`268198b`) exists, per the approved workflow. (Superseded
  by the closure addendum at the end of this report — approved and closed 2026-07-30. Preserved
  unchanged as the record of what was submitted for review.)
- **Scope:** F-2 only. No new GitHub feature, no new public interface, no capability-contract
  change, no `CapabilityBroker` weakening, no state-machine change. F-1 untouched; AUTO-009 not begun.

---

## 1. Task-identifier deviation (documented decision, not a preference)

The stage was requested as **`AUTO-008-F2`**. That identifier **cannot be used**, and this is the
one place I departed from the instruction.

The governance parser is `src/ai_workflow_engine/governance/parser.py`:

```python
TASK_ID = re.compile(r"\b([A-Za-z]+-\d+)\b")
```

`AUTO-008-F2` resolves to **`AUTO-008`** — an existing `Done` task. A queue heading under that ID
would have registered a second, `Current` AUTO-008, breaking `check-task-state` (mirror
disagreement) and `check-registries` (registry `COMPLETE`→`Done` vs queue `Current`). Verified
directly against the parser before registering anything.

**`GOV-AUTO-06`** is used instead: it resolves to `AUTO-06`, which is unused (GOV-AUTO-01..05
resolve to `AUTO-01`..`AUTO-05`), and it matches the established convention for narrowly-scoped
follow-up fixes **outside the AUTO family**. That convention is explicit in `STAGE_REGISTRY.md` §5,
which records GOV-AUTO-01 as *"a governance/developer-experience task outside the AUTO family. It
has no stage in this registry, no stage contract, and no lifecycle state here."* Accordingly
GOV-AUTO-06 has **no registry §4 row and no stage contract** — only a continuity row in the
append-only authorization log. The registry stage count is unchanged at 18.

**Your recommended branch name is kept verbatim** (`feature/auto-008-f2-bind-github-skills`): GOV
tasks have no registered-branch constraint, so the branch carries the requested `auto-008-f2` label
while the governed task ID stays parseable.

---

## 2. The defect, precisely

AUTO-006 delivered all eight Git/GitHub Skills in `agentos_workflow/skills/git_github.py`. Nothing
updated `agentos_workflow/agents/__init__.py`. The result:

- `PROVISIONAL_SKILL_NAMES` still listed all eight as undelivered — with the comment *"belong to
  AUTO-006"* — long after AUTO-006 was `COMPLETE`.
- `_DEFAULT_SKILL_BINDINGS` still omitted all eight, so `default_skill_registry()` returned 32
  Skills instead of 40.
- `CapabilityBroker.invoke_skill` therefore answered every one of them with a typed failure:
  *"skill 'create_commit' is not yet implemented; it is delivered by AUTO-006"* — **a message
  emitted by the very stage that had already delivered it**.

Net effect: `GitAgent` and `MergeAgent` could not invoke a single one of their own contracted
Skills through the production registry. Both Agents were unusable in production, and every method
returned `SKILL_UNAVAILABLE`.

**Why no test caught it.** The only test exercising these Agents end-to-end
(`tests/e2e/test_dry_run.py`) supplies its own registry and hand-binds all eight, so the production
path was never traversed. Meanwhile `test_every_non_provisional_contract_skill_is_bound` asserted
`unbound == set(PROVISIONAL_SKILL_NAMES)` — which passed, because *both sides were the same wrong
eight*. The invariant held perfectly while the system was broken.

### Verified inventory (required work items 1–4)

| Item | Finding |
|---|---|
| 1. Delivered skills | Exactly 8 public functions in `git_github.py`, matching its `__all__` |
| 2. `PROVISIONAL_SKILL_NAMES` | Contained exactly those same 8 — verified set-equal |
| 3. `default_skill_registry()` | 32 entries; **zero** of the 8 present; **no name collisions** with existing entries |
| 4. Capability contracts | `GIT` permits 5 of the 8 + `append_audit_event`; `MERGE` permits 4 (sharing `verify_head_sha`); union = exactly 8. **No other Agent's contract names any of them.** |
| 4. Affected tests | `test_agents_capabilities.py` (registry invariant), `test_agents_git_merge.py` (`TestProvisionalSkillsAreHonestlyUnavailable`), `tests/e2e/test_dry_run.py` (hand-binding) |

---

## 3. Changes made

Six files, **+268 / −42**.

### `agents/__init__.py` — the fix

- Added `from agentos_workflow.skills import git_github as git_github_skills`, following the
  existing pattern for the other four families. (The structural-isolation test governs the six
  *Agent* modules, not `__init__.py`, which already imports every other Skill family.)
- Bound all eight into `_DEFAULT_SKILL_BINDINGS` under a new "Git/GitHub family (§5)" section.
  Registry: **32 → 40**.
- `PROVISIONAL_SKILL_NAMES` → `frozenset()`.
- Broker's unbound-skill message no longer names AUTO-006: `"skill {name!r} is not yet
  implemented"`. Naming one stage is precisely what let the message go stale on the day that stage
  shipped.

**Why `PROVISIONAL_SKILL_NAMES` was emptied, not deleted.** The *membership* was stale; the
*mechanism* is sound and general. A contract may legitimately name a Skill before its implementing
stage lands, and answering that with a typed `PRECONDITION` failure rather than a
`CapabilityViolation` is the right distinction — "not built yet" is a deployment state a machine
gate can act on; "not permitted" is a programming error. Deleting the name would also have removed
a public symbol from `__all__`, which is a public-interface change this stage forbids. An empty set
simply means nothing is currently in that state.

### `agents/git.py` — preserving existing behaviour

`_is_unbound` previously required membership in `PROVISIONAL_SKILL_NAMES` **and** the literal
string `"AUTO-006"`. With the set now empty, that narrow form would have silently reclassified
every missing binding from `SKILL_UNAVAILABLE` to `SKILL_FAILED` — **a behavioural change well
beyond binding the Skills.** I widened it instead to match both of the broker's no-binding answers.
From the Agent's side, "the Skill is not available to me" is the same situation whether nothing
implements it yet or this registry does not bind it.

The string coupling is deliberate and guarded: `test_agents_capabilities.py` now asserts both exact
broker detail strings, so changing either wording fails there rather than silently degrading this
classification. The now-unused `PROVISIONAL_SKILL_NAMES` import was removed.

### Documentation corrections

Module docstrings in `agents/git.py`, `agents/merge.py`, and `skills/git_github.py` all asserted
the Skills were unbound/pending. `git_github.py`'s claim to *"deliver all eight"* read as complete
while half the wiring was missing — that is recorded there now. (This also closes AUTO-008's F-4.)

---

## 4. Regression tests

Nine new tests in `test_agents_capabilities.py::TestGitHubSkillsAreBoundInTheProductionRegistry`,
plus a strengthened existing invariant. Mapped to your required proofs:

| Required proof | Test |
|---|---|
| All eight present in `default_skill_registry()` | `test_all_eight_delivered_skills_are_in_the_default_registry` |
| — bound to the *real* implementations, not look-alikes | `test_the_bound_implementations_are_the_delivered_ones` (identity vs `git_github` module) |
| No longer listed as provisional | `test_none_of_the_eight_is_classified_provisional` |
| `GitAgent`/`MergeAgent` resolve capabilities via the default registry | `test_git_and_merge_resolve_every_contracted_skill_via_the_default_registry` (real `CapabilityBroker` + unmodified production registry — the path no test previously traversed) |
| **No unauthorized skill becomes available** | `test_binding_widened_no_agent_reach` (asserts the negative directly: all six Agents × every non-permitted Git/GitHub name still raise `CapabilityViolation`) and `test_github_skills_reach_only_git_and_merge` |
| Test-only manual registration no longer required | `test_no_manual_registration_is_required_for_this_capability_path` |

Plus two guarding the preserved mechanism:
`test_a_permitted_but_unbound_skill_returns_a_typed_failure_not_a_raise` and
`test_the_provisional_message_no_longer_names_a_shipped_stage`.

And `test_no_contract_skill_is_unbound_today`, added **because** the pre-existing invariant
(`unbound == PROVISIONAL_SKILL_NAMES`) would also have held in the broken state. Stating the
concrete guarantee separately is what makes the regression detectable.

**Two of my own test defects, found and corrected during this work** — recorded because both would
otherwise have shipped as tests that assert nothing useful:

1. `test_the_provisional_message_no_longer_names_a_shipped_stage` initially asserted the
   `"not yet implemented"` branch against a thinned registry. With `PROVISIONAL_SKILL_NAMES` empty
   that path is unreachable, so it was asserting the wrong branch. Now monkeypatches the set —
   which is also the only way to prove the preserved mechanism still works.
2. The two thinned-registry tests duplicated setup; factored into `_thinned_broker()`.

### One updated existing test

`test_agents_git_merge.py::TestProvisionalSkillsAreHonestlyUnavailable` →
`TestUnboundSkillsAreHonestlyUnavailable`. It asserted `"AUTO-006" in detail`, which is now false
and *should* be. The `SKILL_UNAVAILABLE` assertion is deliberately **unchanged** — that is the
behaviour preservation described in §3. These Agents are constructed with `skills={}`, so the test
still covers what it always covered: an Agent's handling of an absent binding.

---

## 5. Validation results

| Check | Result |
|---|---|
| Focused: capabilities suite | **64 passed** |
| Focused: capabilities + git/merge + git_github skills + e2e | **136 passed** |
| Full `pytest -q` | **2,978 passed, 0 failed** (2m26s) |
| `ruff check .` | All checks passed |
| `black --check .` | 209 files unchanged |
| `mypy` (3 packages, `strict`) | **no issues, 115 source files** |
| `pre-commit run --all-files` | ruff / black / mypy all Passed |
| Packaging / import (from `/tmp`) | registry resolves outside repo root; 40 entries; all 8 bound to `git_github`; GIT and MERGE contracts fully satisfied |
| `workflowctl verify` | 4 of 5 PASS — see below |

Test count **2,967 → 2,978** (+11: 10 added, 1 renamed).

**`workflowctl verify` reports one FAIL**, identical to AUTO-008's pre-push state:

```
FAIL git: Git check found 1 violation(s)
  - upstream_missing: The configured project requires an upstream
```

`task-state` (1 Current, 39 Done, 6 Planned), `governance`, `registries` (18 stages — unchanged,
confirming GOV-AUTO-06 correctly adds no registry stage), and `handover` all **PASS**. The `git`
finding is solely the unpushed branch against `require_upstream: true`; it clears on push and CI
does not run `check-git`. I report it rather than presenting a green `verify`, because a green
`verify` is unreachable before publication and I was instructed to stop before pushing.

---

## 6. Scope confirmation

| Constraint | Status |
|---|---|
| Only the F-2 defect corrected | ✅ |
| Stale provisional classification removed **only** for genuinely-implemented skills | ✅ all 8 verified callable in `git_github.py` |
| Registered using existing implementations | ✅ identity-asserted against the module |
| Capability isolation preserved | ✅ `AGENT_SKILL_CONTRACTS` **byte-unchanged**; negative test proves no Agent gained reach |
| Environment allowlist rules preserved | ✅ untouched; AUTO-008's forwarding intact |
| `CapabilityBroker` not weakened | ✅ enforcement order unchanged; contract still checked before the registry; only a message string changed |
| No new GitHub features | ✅ no new function, flag, or argv |
| No state-machine change | ✅ `orchestrator/` untouched |
| AUTO-009 not begun | ✅ |
| F-1 not addressed | ✅ `AuthorizationBindingDriftError` untouched |

---

## 7. Note on the e2e dry run

`tests/e2e/test_dry_run.py` still hand-binds the eight Skills. I deliberately left it alone: it is
outside this task's defect, it passes unchanged, and its explicit bindings are now **redundant
rather than load-bearing** — proven by `test_no_manual_registration_is_required_for_this_capability_path`.
Simplifying that test to consume `default_skill_registry()` directly would be a genuine improvement
and a reasonable follow-up, but it changes what the acceptance demonstration exercises, which is
not a change to make inside a narrowly-scoped fix.

---

## 8. Requested decision

Implementation complete and validated. **Nothing has been committed or pushed for the
implementation.** The governance authorization commit `268198b` is on the branch, unpushed.

On approval I will commit the implementation with its governance closeout and push.

---

## Closure addendum — 2026-07-30 (append-only)

The Human Owner required a final seven-point scope and integrity verification before approving.
All seven passed; no corrective change was needed.

| # | Check | Evidence |
|---|---|---|
| 1 | Changes strictly within GOV-AUTO-06 | 6 files, all F-2; no unrelated file touched |
| 2 | `AGENT_SKILL_CONTRACTS` unchanged | **AST-identical** to `HEAD` (compared by parsing both revisions, so prose edits nearby cannot mask a real change); the only diff lines mentioning it are comments |
| 3 | All eight in the default registry | 40 entries; each of the eight `is` the function object from `skills/git_github.py` |
| 4 | `PROVISIONAL_SKILL_NAMES` empty but public | `frozenset()`, still in `__all__`, still importable |
| 5 | No test-only manual binding, no unrelated e2e cleanup | no e2e file modified; the one grep hit was `assert registry[name] is …`, a read, not a binding |
| 6 | F-1 and AUTO-009 untouched | `orchestrator/` unmodified; zero `AUTO-009` references added |
| 7 | No debug code, workaround, TODO, FIXME, skipped test, or commented-out implementation | all scans clean; zero `pytest.skip`/`skipif`/`xfail` added |

**Final validation, unchanged from §5:** `pytest -q` → 2,978 passed, 0 failed; `ruff check .` →
all checks passed; `black --check .` → 209 files unchanged; `mypy` → no issues in 115 source files;
`pre-commit run --all-files` → ruff, black, mypy all passed; packaging/import verified from outside
the repository root.

**Commit sequence:** `docs(governance): register and authorize GOV-AUTO-06` (`268198b`, governance
only), then the implementation together with its governance closeout in one commit, per
`scripts/workflow-approve.sh`'s automatic-closeout model (GOV-AUTO-03).

Task status `Current → Done`. This closure authorizes no successor: **F-1 and AUTO-009 remain
unauthorized**. The end-to-end dry run's hand-registration of the eight Skills was deliberately
left in place — outside this task's defect, and now provably redundant rather than load-bearing.
