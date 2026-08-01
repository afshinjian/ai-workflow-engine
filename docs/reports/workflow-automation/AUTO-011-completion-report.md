# AUTO-011 — Unified Provider and Agent Result Contract — Completion Report

| Field | Value |
|---|---|
| **Stage** | AUTO-011 |
| **Branch** | `feature/auto-011-agent-result-contract` |
| **Base** | `fd0b34fe0df21d2c6af8cfc2d681ff17ed2984e1` (AUTO-010 publication merge) |
| **Contract** | `docs/workflow-automation/stage-prompts/AUTO-011.md` |
| **Status** | Implemented and fully validated; **uncommitted**, awaiting Human Owner approval |

## 0. Verdict in one paragraph

The engine now has one canonical result type for every execution it performs. `AgentRunResult`
(`agentos_workflow/results.py`) carries all eighteen fields the contract required, enforces the
four-status terminal contract and every invariant on construction *and* on parse, serializes
deterministically with sorted keys, round-trips through a strict parser that rejects unknown fields
and duplicate keys, redacts secrets in every free-text field including artifact paths, and refers
to evidence by path rather than embedding it. It reuses `ProviderRunStatus`, `ProviderVerdict`,
`ProviderFailureKind`, `RetryClassification`, `ProviderKind`, `AgentKind`, and `WorkflowState`
rather than declaring parallel versions of any of them — `RunStatus is ProviderRunStatus` is an
identity, not a mapping. AUTO-010 is reached through an adapter and is **byte-identical**: no
production file outside the new module was modified, all 240 AUTO-010 tests pass, all 25 live CLI
tests pass with zero skips, and six `workflowctl` invocations are byte-identical to the baseline
verified against a clean `fd0b34f` worktree. `recommended_next_state` is advisory and proven so
structurally: no module in `agentos_workflow` outside `results.py` contains the string.
**3,352 tests pass** (3,241 + 111); `mypy --strict` is clean over 121 source files.

---

## 1. Baseline evidence

Every declared precondition was verified before any file was touched.

| Check | Required | Observed | Result |
|---|---|---|---|
| Branch | `main` | `main` | PASS |
| HEAD | `fd0b34fe0df21d2c6af8cfc2d681ff17ed2984e1` | `fd0b34fe0df21d2c6af8cfc2d681ff17ed2984e1` | PASS |
| `main` vs `origin/main` | equal | both `fd0b34f`, 0 ahead / 0 behind | PASS |
| Working tree | clean | clean, no untracked files | PASS |
| `workflowctl verify --config self-governance.yaml` | passes | **PASS** (all five checks) | PASS |
| `pytest -q` | passes at merged AUTO-010 baseline | **3,241 passed, 25 deselected** (153.71s) | PASS |
| `pytest -q -m live_cli -rs` | passes, zero skips | **25 passed, 0 skipped** (277.34s) | PASS |
| AUTO-008..AUTO-010 merged and published | yes | PR #6, PR #9, PR #10 all merged | PASS |
| No AUTO-011 work exists | none | no branch, no `AgentRunResult` symbol, no registry row | PASS |

The five baseline verification checks read:

```text
git        PASS  Git state satisfies configured invariants
task-state PASS  Detected 0 Current, 43 Done, and 6 Planned tasks
governance PASS  Governance mirrors are consistent
registries PASS  Checked 20 stage(s) across 2 registry(ies) against the task queue
handover   PASS  Verified 1 manifest record(s) from working-tree
Verdict: PASS
```

Branch `feature/auto-011-agent-result-contract` was then created from that clean, synchronized
`main`.

## 2. Governance authorization

AUTO-011 had never been registered, so registration and authorization are one act, recorded in
every mirror the governance tooling checks:

| Document | What was added |
|---|---|
| `docs/TASK_QUEUE.md` | Full AUTO-011 entry, `Status: Current`, scope and prohibitions |
| `docs/current_task.md` | Rewritten to mirror the single `Current` task |
| `docs/remaining_tasks.md` | AUTO-010 publication recorded; AUTO-011 registered; AUTO-012 unauthorized |
| `docs/PROJECT_STATE.md` | AUTO-011 section, `Status: Current` |
| `docs/DECISION_LOG.md` | Dated entry with alternatives considered and rejected (append-only, inserted newest-first) |
| `docs/workflow-automation/STAGE_REGISTRY.md` | Registry row (`IN_PROGRESS`) + three authorization-log entries: AUTO-010 publication, AUTO-011 authorization, AUTO-011 preflight |
| `docs/workflow-automation/stage-prompts/AUTO-011.md` | The stage contract file |

`workflowctl verify` after registration reports `task-state` PASS at **1 Current, 43 Done, 6
Planned** and `registries` PASS across **21 stages**.

## 3. Existing result-model inventory

Every result type in the repository was read before anything was designed.

| Model | Location | Disposition |
|---|---|---|
| `ProviderRunStatus` | `providers/base.py:152` | **Canonical.** Reused directly; exported as `RunStatus` (an alias, asserted by identity) |
| `ProviderVerdict` | `providers/base.py:141` | **Canonical.** Reused as `final_verdict`'s type |
| `ProviderFailureKind` | `providers/base.py:174` | **Canonical.** Reused as `RunFailure.kind` |
| `RetryClassification` | `skills/__init__.py:72` | **Canonical.** Reused; answers retryability *and* side-effect certainty |
| `ProviderKind` | `providers/base.py:120` | **Canonical.** Reused as the provider identity |
| `AgentKind` | `agents/__init__.py:108` | **Canonical.** Reused as the agent identity |
| `WorkflowState` | `orchestrator/engine.py:100` | **Canonical.** Reused as `recommended_next_state`'s vocabulary |
| `ProviderFailure` | `providers/base.py:192` | **Adapted.** Projected into `RunFailure`; unchanged |
| `ProviderReport` | `providers/base.py:206` | **Adapted.** Source of `changed_files`, `tests_run`, `final_verdict`; unchanged |
| `ProviderRunResult` | `providers/runtime.py:180` | **Adapted.** The AUTO-010 boundary type; unchanged, still the Provider Runtime's return type |
| `ProviderResult` | `providers/base.py:241` | Left as-is — an internal ok/error envelope below the runtime |
| `AgentResult` | `agents/__init__.py:145` | **Legacy, unchanged.** AUTO-005's per-action evidence result; deliberately not merged (see §7) |
| `AgentReport` | `src/ai_workflow_engine/agents/models.py:36` | **Legacy, unchanged.** Milestone-3 model; not deleted, not modified, pinned by a test |
| `StatusResult` / `WorkflowListResult` / `AuditResult` / `ReportResult` | `service.py` | Untouched — read projections, not execution results |

Nothing was deleted. No legacy model was modified.

## 4. Canonical model design

```text
WorkflowService.invoke_provider
    -> ProviderRuntime.invoke -> ProviderRunResult        (AUTO-010, unchanged)
        -> agent_run_result_from_provider_run              (AUTO-011, the adapter)
            -> AgentRunResult                              (AUTO-011, canonical)
```

Three types, one module (`agentos_workflow/results.py`, 439 lines):

* **`AgentRunResult`** — the canonical result. Frozen, `extra="forbid"`.
* **`RunFailure`** — a typed failure projection. Frozen, `extra="forbid"`.
* **`ArtifactReference`** — a `(kind, path)` pointer, never content. Frozen, `extra="forbid"`.

Plus two enums that nothing in the repository already had: `ExecutionMode` and `ArtifactKind`. A
test parses the module and asserts those are the *only* enums it declares, so a second status or
verdict vocabulary cannot be added without failing.

### Why a new type instead of promoting `ProviderRunResult`

`ProviderRunResult` is the Provider Runtime's boundary type and callers depend on it unchanged.
It is also provider-shaped in ways a unified contract cannot be: no execution mode, no agent
identity, no artifact vocabulary beyond stdout/stderr, and nowhere for a producer's own read of
what should happen next. Changing it in place would have broken the compatibility this stage was
required to preserve.

## 5. Field-by-field rationale

Every field answers a question a caller must be able to ask without reaching past the boundary. No
field was added speculatively.

| Field | Type | Purpose |
|---|---|---|
| `workflow_id` | `str` | Which workflow this execution belongs to. A parameter to the adapter because AUTO-010's result does not carry one. |
| `session_id` | `str` | The invocation's audit identity, tying the result to the isolated directory that holds its evidence. Artifacts give paths; only this gives identity. |
| `mode` | `ExecutionMode` | Which kind of execution produced the result. The one field that distinguishes a bare provider invocation from a future Preparation/Reviewer/Implementer run. |
| `provider` | `ProviderKind \| None` | Which CLI ran. `None` for a future internal agent that runs no CLI. |
| `agent` | `AgentKind \| None` | Which agent ran. `None` for a raw provider invocation. At least one of `provider`/`agent` is required — a result must name its producer. |
| `status` | `ProviderRunStatus` | How the execution terminated. The four-status contract. |
| `summary` | `str` | What the producer says it did. Redacted. |
| `assumptions` | `tuple[str, ...]` | Each safe, scope-preserving assumption relied on. Required non-empty for `COMPLETED_WITH_ASSUMPTIONS`. Order preserved. |
| `blocking_issues` | `tuple[str, ...]` | Each concrete reason safe continuation was impossible. Required non-empty for `BLOCKED`, forbidden for `COMPLETED`. Order preserved. |
| `changed_files` | `tuple[str, ...]` | What the producer claims it changed. Sorted and de-duplicated — a changed-file list is a set, and normalizing is what makes two results for the same work serialize identically. |
| `tests_run` | `tuple[str, ...]` | Each validation actually run. Maps from `ProviderReport.validation_performed`; named per the contract. Order is **not** normalized, because the sequence of validations is information. |
| `artifacts` | `tuple[ArtifactReference, ...]` | Where the evidence is. References only. |
| `started_at` / `completed_at` | `datetime` | The interval. Both must be timezone-aware; completion may not precede start. |
| `duration_seconds` | `float` | The interval as a number, so it survives serialization. Filled when omitted, cross-checked when supplied — it can never disagree with the timestamps. |
| `exit_code` | `int \| None` | The process's own answer. `None` when no process ran or when termination produced a signal-derived code the engine chose (AUTO-010's rule, preserved). |
| `failure` | `RunFailure \| None` | Why it failed, typed. Required for `FAILED`, forbidden otherwise. |
| `final_verdict` | `ProviderVerdict \| None` | The producer's pass/fail. A different axis from `status`: a `COMPLETED` run reporting `fail` (QA finding real defects) is a successful execution. `None` when no verdict was stated. |
| `recommended_next_state` | `WorkflowState \| None` | **Advisory only.** What the producer thinks should happen next. Never read by anything that transitions a workflow. |

Fields deliberately **not** added: `stage_id` (`workflow_id` + `session_id` already identify the
run), a separate side-effect-certainty field (`RetryClassification` is one question by design, per
`SKILL_CONTRACTS.md` §5), and any field carrying artifact content.

## 6. Status invariants

Enforced in one `model_validator(mode="after")` so none can be satisfied in isolation, and re-run
on every parse.

| Invariant | Enforced |
|---|---|
| `COMPLETED_WITH_ASSUMPTIONS` requires ≥1 assumption | yes |
| `BLOCKED` requires ≥1 blocking issue | yes |
| `FAILED` requires a typed failure | yes |
| `COMPLETED` carries no failure | yes |
| `COMPLETED` carries no blocking issues | yes |
| Any non-`FAILED` status carries no failure | yes (matches AUTO-010) |
| Unknown statuses rejected | yes (closed enum) |
| A result must name a producer (`provider` or `agent`) | yes |
| `completed_at` ≥ `started_at` | yes |
| `duration_seconds` agrees with the interval | yes |
| `duration_seconds` ≥ 0 | yes |
| Timestamps timezone-aware | yes |
| Unknown fields rejected | yes (`extra="forbid"`) |
| Unknown provider/agent identity rejected | yes (closed enums) |

`COMPLETED_WITH_ASSUMPTIONS` alongside blocking issues is deliberately **permitted**: only
`COMPLETED` is forbidden from carrying them, because AUTO-010 permits that combination and
forbidding it would make the adapter fail on real provider output.

## 7. Adapter and compatibility strategy

`agent_run_result_from_provider_run(result, *, workflow_id, mode, agent, session_directory)`.

**Total** for every `ProviderRunResult` the Provider Runtime can construct, and a pure field copy
for all but one shape. Nothing is inferred: `final_verdict`, `changed_files`, and `tests_run` come
from the parsed report when there was one and stay *absent* when there was not, because an absent
claim must not become an empty claim that looks checked.

`recommended_next_state` is always `None` from this adapter. That is the point: a provider run says
how an execution ended; deciding what a workflow should do next belongs to the Orchestrator, and an
adapter that guessed a next state from a status would be exactly the invented transition the
authority rule forbids.

### The one non-copy, stated plainly

A provider reporting `COMPLETED` while also naming blocking issues has violated the auto-mode
output contract — it claims both that the work finished and that something stopped it. AUTO-010
permits that shape (recorded below as **D-8**); the canonical contract does not. Neither available
alternative was acceptable: dropping the blockers erases the only evidence something was wrong, and
raising would make the adapter partial. It is therefore recorded as `FAILED` with a
`MALFORMED_OUTPUT` failure naming the contradiction — precisely how AUTO-010 already classifies
every other violation of that same contract — and **nothing is lost**: the summary and the blocking
issues are both preserved on the canonical result. One test asserts each of those properties.

### What was *not* consolidated, and why

`AgentResult` (AUTO-005) was left alone. It is a per-*action* evidence envelope
(`agent`, `action`, `ok`, `evidence`, `error`) that the Orchestrator's machine gates read, not an
execution result — merging it would have required editing `agents/**`, which is outside this
stage's scope, and would have conflated two genuinely different things. `AgentReport`
(`src/ai_workflow_engine`) is Milestone-3's prompt-bound schema and was neither deleted nor
modified; a test pins its exact field set.

## 8. Serialization design

| Requirement | How |
|---|---|
| Strict validation | Pydantic, `extra="forbid"`, all invariants re-checked on parse |
| Deterministic serialization | `json.dumps(..., sort_keys=True, separators=(",", ":"))` — bytes stay stable even if fields are later reordered |
| Stable JSON output | asserted byte-equal across repeated calls and across a round trip |
| Unknown-field rejection | `extra="forbid"`, tested on both construction and parse |
| Duplicate-key rejection | `strict_json_loads` — the package's existing single JSON entry point, reused rather than reimplemented |
| Timezone-aware timestamps | field validator rejects naive values; serialized with offset |
| Deterministic duration | stored, filled when omitted, cross-checked against the interval so it can never disagree |
| Secret redaction | every free-text field, every string sequence, every failure detail, and every artifact path; proven idempotent so round-tripping is stable |
| Safe artifact references | `..` segments, NUL bytes, and empty paths refused; paths redacted |
| Round-trip parsing | `AgentRunResult.from_canonical_json(x.to_canonical_json()) == x` |

## 9. Failure preservation

`RunFailure` is a projection of `ProviderFailure`, not a duplicate. The difference is deliberate:
`ProviderFailure` carries a whole `CommandExecution` including captured stdout and stderr, which a
canonical result must not embed.

| Facet the contract required | Preserved as |
|---|---|
| Failure category | `kind: ProviderFailureKind` — all 8 kinds, each parametrized-tested |
| Retryability | `retry_classification` — all 4 values, each parametrized-tested |
| Side-effect certainty | the same field; `SKILL_CONTRACTS.md` §5 makes these one question, and inventing a second field would create two answers |
| Timeout classification | `timed_out`, derived from the kind *or* the execution record's `timeout_status`; a `TIMEOUT` failure that denies timing out is rejected |
| Output-limit classification | `output_limit_exceeded` |
| Provider-contract violations | `kind = MALFORMED_OUTPUT` / `PROVIDER_REPORTED` |
| Spawn failures | `kind = SPAWN_FAILED` |
| Authentication / availability failures | `kind = SPAWN_FAILED` / `COMMAND_FAILED` with the redacted detail |

Nothing is flattened into a free-form string: `failure` is typed `RunFailure | None`, asserted.

**On output-limit classification.** AUTO-010 records an output-limit breach as `MALFORMED_OUTPUT`
with a detail beginning `"stdout exceeds "` / `"stderr exceeds "`, and this stage may not change
that classification. The canonical failure therefore recovers the fact by matching those prefixes.
That is a coupling to wording, so it is pinned by two tests that provoke a **real** breach through
the **real** process runner (a child actually writing past the ceiling) and assert
`output_limit_exceeded` — if `base.py`'s message ever changes, those tests fail rather than the
classification silently going wrong. The underlying gap is recorded as deferred finding **D-9**.

## 10. Artifact-reference design

`ArtifactReference` has exactly two fields — `kind` and `path` — asserted by a test, so content
cannot be smuggled in. Six kinds: `stdout`, `stderr`, `provider_report`, `session_directory`,
`changed_file_evidence`, `test_result_evidence`.

Confinement is enforced by refusing the constructs that defeat it rather than by resolving against
a root this module does not know: a `..` segment is the one way a stored reference escapes wherever
a reader joins it, and a NUL byte is how a path means one thing to a validator and another to the
kernel. Both are refused. Redaction runs last and applies to the path itself, because a session or
repository path can embed a credential.

`changed_files` is deliberately *not* held to the same rule: the provider layer does not validate
what a model claims it changed, so rejecting an absolute or traversing path there would make the
adapter fail on real output. Those strings are a producer's claim to be verified elsewhere, never
a path this engine opens. `ArtifactReference`, which *is* a path a reader follows, is strict. This
asymmetry is documented in the code.

## 11. Authority-boundary proof

Ten tests, structural rather than declarative.

| Claim | Evidence |
|---|---|
| The engine never reads the field | `"recommended_next_state" not in engine.py` |
| Nothing outside the contract reads it | every `agentos_workflow/**/*.py` except `results.py` scanned; offenders list is empty |
| The module holds no transition machinery | AST of imports: `StateStore`, `RepositoryLock`, `WorkflowSession`, `WorkflowStateMachine`, `ResumedWorkflow`, `AuthorizationRecord`, `StateTransitionRecord` all absent; `WorkflowState` (a vocabulary) present |
| The module executes nothing | AST of calls: no `Popen`, `run`, `system`, `spawn`, `write_text`, `mkdir`, `append_transition`, `invoke` |
| It cannot invoke a skill or provider | asserted over the **parsed syntax tree**, not the source text — the module docstring discusses the Provider Runtime at length, and prose about an executor is not an executor |
| Constructing a result transitions nothing | a result naming `READY_TO_COMMIT` is built, serialized, and re-parsed; no state directory is created |
| A result cannot grant authorization | `AUTHORIZED` is expressible as *advice* — refusing to let a producer say it would be a weaker, different claim — but nothing consumes it, and the result exposes no `authorize`/`approve`/`transition`/`advance`/`commit`/`invoke` callable |
| The result adds only serialization | its own public callables are exactly `to_canonical_json` and `from_canonical_json` |
| The field is optional and defaults absent | asserted |
| Transitions still come from the table | `ALLOWED_TRANSITIONS` still holds 37 state pairs and knows nothing about results |

## 12. Exact files changed

Nine files. **No production file outside the new module was modified.**

| File | Status | What |
|---|---|---|
| `agentos_workflow/results.py` | **new** | The canonical contract: `AgentRunResult`, `RunFailure`, `ArtifactReference`, `ExecutionMode`, `ArtifactKind`, `RunStatus`, and the adapter |
| `agentos_workflow/tests/test_results.py` | **new** | 111 tests |
| `docs/workflow-automation/stage-prompts/AUTO-011.md` | **new** | Stage contract |
| `docs/TASK_QUEUE.md` | modified | AUTO-011 registration entry |
| `docs/current_task.md` | modified | Current-set mirror |
| `docs/remaining_tasks.md` | modified | AUTO-010 publication + AUTO-011 registration |
| `docs/PROJECT_STATE.md` | modified | AUTO-011 section |
| `docs/DECISION_LOG.md` | modified | Dated decision entry |
| `docs/workflow-automation/STAGE_REGISTRY.md` | modified | Registry row + three authorization-log entries |

Verified byte-identical to `fd0b34f` (`git diff --stat` empty): `agentos_workflow/providers/**`,
`agentos_workflow/service.py`, `agentos_workflow/orchestrator/**`, `agentos_workflow/agents/**`,
`agentos_workflow/skills/**`, `agentos_workflow/config/**`, `agentos_workflow/cli_auto.py`,
`src/**`, `scripts/**`, `pyproject.toml`.

## 13. Focused test results

`agentos_workflow/tests/test_results.py` — **111 tests, all passing.**

| Class | Tests | Covers |
|---|---|---|
| `TestFailurePreservation` | 18 | every failure kind, every retry classification, timeout and output-limit classification, no flattening, no embedded output |
| `TestProviderAdapterCompatibility` | 17 | completed/blocked/assumed/failed Claude and Codex runs, spawn failure, malformed output, missing status, timeout, both output-limit breaches, artifacts, no inferred next state, the contradictory-`COMPLETED` mapping |
| `TestStatusInvariants` | 12 | all status invariants, unknown status, producer requirement, `succeeded` |
| `TestSerialization` | 11 | round trip, byte stability, sorted keys, duplicate keys, unknown fields, re-checked invariants, tampered duration, nested references |
| `TestAuthorityBoundaries` | 10 | the ten claims in §11 |
| `TestTimestampsAndDuration` | 8 | naive rejection, ordering, derivation, determinism, contradiction, negative, zero |
| `TestSecretRedaction` | 8 | summary, all four string sequences, failure detail, idempotency, nothing survives serialization |
| `TestArtifactReferences` | 7 | traversal, empty, NUL, redaction, relative paths, all six kinds, no content field |
| `TestReuseNotDuplication` | 5 | `RunStatus is ProviderRunStatus`, the four statuses, every reused enum, no second enum declared, all 18 fields present |
| `TestExistingBehaviourUnchanged` | 5 | `ProviderRunResult` invariants, `ProviderReport`'s two axes, legacy `AgentReport`, service surface, no CLI change |
| `TestStrictnessAndImmutability` | 4 | unknown fields, frozen result, frozen nested models |
| `TestChangedFileNormalization` | 4 | sorted/deduped, idempotent, `tests_run` order preserved, assumption order preserved |
| `TestLiveShapedOutputsMap` | 2 | the exact report payloads the live suites assert against |

The provider-facing tests use the **real** `ProviderRuntime` against stub executables, and the
harness is imported from `test_provider_runtime` rather than copied — so a change in AUTO-010
surfaces as a failure here instead of being hidden behind a private fixture.

## 14. Full validation results

| Command | Result |
|---|---|
| `pytest -q` | **3,352 passed, 25 deselected** in 154.89s (baseline 3,241; +111) |
| `pytest -q -m live_cli -rs` | **25 passed, 0 skipped**, 3,352 deselected in 329.01s |
| `ruff check .` | All checks passed |
| `black --check .` | 222 files unchanged |
| `mypy --strict` | Success: no issues in **121** source files (baseline 120; +1) |
| `pre-commit run --all-files` | ruff Passed · black Passed · mypy Passed |
| `workflowctl verify --config self-governance.yaml` | `task-state`/`governance`/`registries`/`handover` **PASS**; `git` FAIL with exactly `["upstream_missing"]` |

`upstream_missing` is the expected pre-push finding — the branch has no remote tracking yet, and
pushing is outside this stage's stop condition. It is the identical finding AUTO-010 recorded at
the same point and it clears at the push.

### Additional verification

* **Wheel packaging** — built with `pip wheel --no-deps`; `agentos_workflow/results.py` is present,
  alongside `runtime.py`, `selection.py`, `config/policy.py`, and `service.py`.
* **Out-of-tree imports** — `AgentRunResult`, `agent_run_result_from_provider_run`, and `RunStatus`
  all import cleanly from `/tmp`; the service surface is still exactly
  `audit, invoke_provider, list, report, status`.
* **CLI unchanged** — six invocations (`auto --help`, `auto status|list|audit|report --help`,
  `--help`) run against a **clean `fd0b34f` git worktree** and against this branch produce
  **byte-identical** output (MD5 compared, all six identical).
* **Provider Runtime unchanged** — `git diff --stat fd0b34f` over every provider, orchestrator,
  agent, skill, config, CLI, `src/`, `scripts/`, and packaging path is empty.
* **Only AUTO-011 files modified** — `git status` shows exactly the nine files in §12.

## 15. Live-provider regression results

```text
$ pytest -q -m live_cli -rs
25 passed, 3352 deselected in 329.01s
```

Run with `-rs`, which prints a skip summary if any test skips. None did. `TestLiveClaude` 9,
`TestLiveCodex` 9, `TestLiveSuiteGuards` 7 — unchanged from AUTO-010's closing numbers, against the
real installed CLIs. The live suite file itself was not modified.

The AUTO-010 mocked suites were also run as a group: `test_provider_runtime.py`,
`test_providers_base.py`, `test_providers_cli.py`, `test_providers_isolation.py`,
`test_service.py` — **240 passed**.

## 16. Blockers fixed

**None.** No defect blocked AUTO-011, so nothing outside the new module was changed. One defect
found in this stage's own new code during development — a `mode="before"` validator that subtracted
a naive timestamp from an aware one and surfaced a `TypeError` about subtraction instead of the
real "timestamps must be timezone-aware" error — was fixed in `results.py` itself and is covered by
`test_naive_timestamps_are_rejected`.

## 17. Deferred findings

Recorded, classified, not implemented. No GOV stage was created for any of them.

### D-8 — `ProviderRunResult` permits `COMPLETED` alongside blocking issues — `RECOMMENDED`

AUTO-010's `__post_init__` checks that `BLOCKED` has blockers, `COMPLETED_WITH_ASSUMPTIONS` has
assumptions, and `FAILED` has a failure, but never that a `COMPLETED` result has *no* blockers. A
provider claiming both is expressible at that boundary. **Impact:** the contradiction reaches
callers of AUTO-010's type unflagged; the canonical adapter catches it (§7) but the underlying type
still permits it. **Defer to:** a stage authorized to edit `providers/runtime.py`. Fixing it here
would have modified AUTO-010, which this stage's compatibility rule forbids.

### D-9 — an output-limit breach is not distinguishable by failure kind — `RECOMMENDED`

`providers/base.py` records a stdout/stderr ceiling breach as `MALFORMED_OUTPUT` with a detail
string, and `stdout_limit_exceeded`/`stderr_limit_exceeded` never propagate past `ProviderExecution`.
The canonical failure therefore recovers the fact by prefix-matching engine-generated wording.
**Impact:** a coupling to message text, mitigated but not removed by the two real-breach tests that
pin it. **Defer to:** a stage authorized to change provider failure classification — the honest fix
is to carry the two flags on `CommandExecution` or add a distinct failure kind, both of which change
AUTO-010 behaviour that tests currently pin.

### D-10 — the canonical result's enum imports invite a future import cycle — `RECOMMENDED`

`results.py` imports `AgentKind` from `agents/__init__.py` and `WorkflowState` from
`orchestrator/engine.py`. Reusing them was required ("avoid duplicate models") and is correct
today, because neither package imports `results`. But the whole point of this contract is that
agents will eventually *produce* it, and on that day `agents -> results -> agents` becomes a cycle.
**Impact:** none now; a latent constraint on the stage that wires agents to canonical results.
**Defer to:** that stage, whose scope-preserving remedy is to move `AgentKind` (and, if needed,
`WorkflowState`) into a leaf module — exactly what AUTO-010 did with `config/policy.py`.

### D-3 through D-6 (AUTO-010) — unchanged

**D-3** (`ProviderReport` carries two overlapping outcome axes) was deferred *to* AUTO-011. It is
**not resolved here, and deliberately so.** The canonical result keeps both axes — `status` and
`final_verdict` — because they answer genuinely different questions: a `COMPLETED` run reporting
`fail` is a QA provider finding real defects, which is a successful execution with a failing
verdict. Collapsing them would destroy that distinction. What AUTO-011 removes is the *ambiguity*,
by giving each axis one canonical type and one documented meaning; what it does not do is delete a
field from `ProviderReport`, which would modify AUTO-010. A test asserts both axes still exist
there. **D-4** (artifacts have no reader or audit linkage), **D-5** (no retry/repair policy for
contract violations), and **D-6** (AUTO-009's six deferred defects) are all confirmed untouched.

### D1–D6 (AUTO-009) — unchanged

Confirmed untouched, including D3: **no CLI command was added**, so the `cli_auto` finding is
unaffected. A test asserts `cli_auto.py` names neither `results` nor `AgentRunResult`.

## 18. Confirmation that no successor behaviour was implemented

| Prohibited | Evidence |
|---|---|
| Preparation / Reviewer / Implementer Mode | no such module, class, or command exists. `ExecutionMode` *names* three of them so the canonical result can type them; naming a mode implements nothing, and no code produces them |
| workflow authorization, approval, approval timeout | none added; `WorkflowService`'s public surface is still exactly the AUTO-010 five (asserted) |
| task scheduling, daemon, Telegram | no dependency, module, or configuration field |
| workflow start / resume / cancel | absent, asserted |
| Claude–Codex coordination, Codex direct correction | the adapter projects exactly one provider run and holds no cross-provider state |
| Git commit / push / PR / CI polling / merge / branch cleanup | no Git or GitHub call anywhere in the new code; none performed |
| Python governance closeout, shell-script retirement | `scripts/` byte-identical to `fd0b34f` |
| workflow state transitions modified | `orchestrator/` byte-identical; `ALLOWED_TRANSITIONS` still 37 edges (asserted) |
| Git/GitHub skill registration modified | `skills/` byte-identical |
| existing `workflowctl auto` behaviour/output | six invocations byte-identical to a clean `fd0b34f` worktree |
| a new public CLI command | none added |
| **AUTO-012 or any successor** | absent; no approval policy, no lifecycle, no orchestration |

## 19. Proposed commit and publication plan

Nothing was committed, pushed, merged, or opened as a pull request. The complete diff is in the
working tree on `feature/auto-011-agent-result-contract` for Human Owner inspection.

Recommended commit message:

```text
feat(results): add the canonical AgentRunResult contract for providers and agents (AUTO-011)
```

Proposed closeout sequence, **all of it requiring explicit Human Owner authorization**:

1. Human Owner reviews this report and the diff, with particular attention to §7 (the one
   non-copy in the adapter), §9 (the output-limit prefix coupling), and §17 (three new deferred
   findings, none fixed).
2. On approval, the closeout commit additionally updates `docs/CHANGELOG.md`,
   `docs/workflow-automation/CHANGELOG.md`, `handover/PROJECT_HANDOVER.md`, and
   `handover/PROJECT_CHECKSUM.md`, and moves the registry row `IN_PROGRESS → COMPLETE` with the
   task status `Current → Done`.
3. Publication: push `feature/auto-011-agent-result-contract`; PR and merge only if separately
   authorized. The `upstream_missing` finding in `workflowctl verify` clears at the push. Note that
   AUTO-010 sat closed-but-unpublished for a day because closure and publication are separate
   authorizations here — the same applies to this stage.
4. AUTO-012 remains unauthorized and must not begin.

**Confirmation:** no commit, push, merge, pull request, branch deletion, stash operation, or
successor-stage work was performed by this session. The temporary `fd0b34f` worktree created for
the CLI byte-comparison was removed; `git worktree list` shows only the primary checkout.

---

# 20. Approval, final verification, and closure (2026-08-01, append-only)

Sections 0–19 above are unchanged. This section records the Human Owner's approval, the required
final verification, and the closeout performed under it.

## 20.1 The fourteen-point verification

The Human Owner approved AUTO-011 for finalization and required a final scope, contract, and
compatibility verification before any commit. **All fourteen passed.**

| # | Check | Result |
|---|---|---|
| 1 | Exactly the approved canonical fields, no speculative successor fields | **PASS with one disclosure** — all 18 present; a 19th, `session_id`, is carried (§20.2) |
| 2 | The four-status contract enforced | PASS — `[completed, completed_with_assumptions, blocked, failed]`; `RunStatus is ProviderRunStatus` |
| 3 | All status invariants | PASS — all six rejections re-checked live: CWA without assumptions, BLOCKED without blockers, FAILED without failure, COMPLETED with failure, COMPLETED with blockers, unknown status |
| 4 | `status` and `final_verdict` distinct, not collapsed | PASS — `ProviderRunStatus` vs `ProviderVerdict \| None`, different types, both retained |
| 5 | `recommended_next_state` advisory only | PASS — 10 authority tests; no module in `agentos_workflow`, `src`, or `agentos_dashboard` outside the contract contains the string |
| 6 | Adapter preserves every AUTO-010 result and failure classification | PASS — 37 adapter and failure-preservation tests; all 8 failure kinds and all 4 retry classifications parametrized |
| 7 | The one documented normalization, preserving summary and blockers | PASS — asserted by `test_a_contradictory_completed_result_is_recorded_not_silently_dropped`; it is the only non-copy |
| 8 | Serialization deterministic, strict, duplicate-key rejecting, round-trip safe, timezone aware, immutable, secret redacted | PASS — 50 tests across the serialization, strictness, timestamp, artifact, and redaction classes |
| 9 | Artifacts are references only; unsafe paths rejected | PASS — `ArtifactReference` has exactly `{kind, path}`; `..`, NUL, and empty refused |
| 10 | No provider, process-runner, service, CLI, agent, skill, state-machine, configuration, Git, GitHub, or shell behaviour changed | PASS — `git diff --stat fd0b34f` empty across all of them, plus `agentos_dashboard/` and `self-governance.yaml` |
| 11 | AUTO-010 provider-runtime and live CLI tests unchanged and passing | PASS — those five test files and `tests/live/` byte-identical; **240 passed**; live **25 passed, 0 skipped** |
| 12 | D-8, D-9, D-10 and all earlier findings still deferred | PASS — none implemented, no GOV stage created |
| 13 | AUTO-012 and successor behaviour untouched | PASS — no successor symbol in the new code; service surface still the AUTO-010 five |
| 14 | No debug code, TODO, FIXME, skip, xfail, workaround, commented-out implementation, or unrelated refactor | PASS — see §20.3 |

## 20.2 The one disclosure: `session_id`

`AgentRunResult` carries a nineteenth field beyond the eighteen the contract enumerated.

It is **not speculative and not successor behaviour.** `session_id` is the invocation's audit
identity — `<workflow_id>/<provider>/<invocation_id>` — populated today from
`ProviderRunResult.session_id`, which AUTO-010 already produces. It is what ties a canonical result
to the isolated session directory holding its evidence: `artifacts` give paths, but only this gives
identity, and a result that cannot be traced back to the invocation that produced it is weaker
evidence than one that can. It is documented in §5's field table and exercised by the adapter tests.

Recording it here rather than quietly leaving it in §5 is the point: the check asked for *exactly*
the approved fields, and this is one more.

## 20.3 Cleanliness scan

* No `TODO`, `FIXME`, `XXX`, `HACK`, `breakpoint(`, `pdb`, `NotImplementedError`, `xfail`,
  `pytest.mark.skip`, or `pytest.skip` in either new file.
* One `print(` match in `test_results.py` is inside a **stub CLI script body string** — the fake
  executable emitting its transport envelope, the same idiom `test_provider_runtime.py` uses. Not
  debug output.
* No commented-out implementation in `results.py` (scanned for commented `def`/`class`/`return`/
  control-flow/assignment/import lines; none).
* Repo-wide `pytest -q -rsxX`: **3,352 passed**, no skips, no xfails, no xpasses reported.
* No unrelated refactor: the diff outside the two new files and the governance documents is empty.

## 20.4 Governance closeout

| Document | Change |
|---|---|
| `docs/TASK_QUEUE.md` | `Status: Current -> Done`, closure paragraph appended |
| `docs/current_task.md` | Rewritten to the empty-`Current` state |
| `docs/remaining_tasks.md` | AUTO-011 recorded as approved and closed |
| `docs/PROJECT_STATE.md` | `Status: Current -> Done`, closure paragraph appended |
| `docs/DECISION_LOG.md` | Approval-and-closure entry, including the `session_id` disclosure and the decision not to collapse D-3 |
| `docs/workflow-automation/STAGE_REGISTRY.md` | Row `IN_PROGRESS -> COMPLETE`; approval-and-closure log entry |
| `docs/CHANGELOG.md` | AUTO-011 entry under Added |
| `docs/workflow-automation/CHANGELOG.md` | AUTO-011 implementation entry; version 2.18 -> 2.19 |
| `handover/PROJECT_HANDOVER.md` | AUTO-011 section |
| `handover/PROJECT_CHECKSUM.md` | Regenerated for the new handover bytes |

`workflowctl verify` after closeout: `task-state` **0 Current, 44 Done, 6 Planned**; `governance`,
`registries` (21 stages), and `handover` all PASS.

## 20.5 Provenance

The approval was given in conversation and the closeout performed **manually**, not through
`scripts/workflow-approve.sh`, whose two interactive `APPROVE` confirmations an agent must never
supply. No scripted confirmations were typed and none were supplied by this session.

## 20.6 Stop condition

Commit and push only. **No pull request was opened, no merge was performed, and AUTO-012 was not
begun.** Publication beyond the push requires its own separate Human Owner authorization — the same
separation that left AUTO-010 closed but unpublished for a day.
