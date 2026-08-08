# AUTO-016 — Completion Report

| Field | Value |
|---|---|
| Stage | AUTO-016 — Integrated Milestone Automation Runner |
| Branch | `feature/auto-016-milestone-runner` |
| Contract | `docs/workflow-automation/stage-prompts/AUTO-016.md` (Revision 4), sha256 `56f6a8f5720f30543f5b0623f5cb52ffa2cc45cbe51be8c5f9b9f5f256b90a7e` |
| Baseline commit | `4fa9212ff47171c162ddf863360413a90e0ee79f` |
| Implementation run | `auto016-20260805T213855Z-7fea75fc`, milestones AUTO-016-M01 … AUTO-016-M09, plus the GOV-AUTO-11 correction round |
| Report written at | AUTO-016-M09, the stage's closing milestone |
| Status | Implemented up to §31's stop condition. Every §25 command that was run passes; nothing was committed, pushed, opened as a pull request, or merged |

This report records evidence. It authorizes nothing, registers nothing, and transitions nothing:
no Registry row, task status, mirror or handover record is edited by the work it describes.

## Verdict

AUTO-016 is implemented as the Core Engine Milestone Runner DEC-016-001 selected: a new
`src/ai_workflow_engine/milestone_runner/` subpackage of exactly the nineteen files §8 and §23.1
fix, plus one additive `workflowctl milestone-runner` Typer sub-app with thirteen thin command
functions. It drives an already-authorized stage's implementation as a bounded, resumable sequence
of typed milestones, runs deterministic verification, obtains one bounded review, permits at most
one correction round and one closure verification, and stops at `READY_FOR_COMMIT_APPROVAL` with a
commit gate that is disabled by default.

With the shipped defaults it commits nothing, pushes nothing, opens no pull request and merges
nothing. §27 requires that to be proved four independent ways, and it is
(`TestNoAutomaticGitMutation`): an AST proof, a behavioural print-only proof, a Git-level
`HEAD`/reflog/remote-ref proof across a complete run, and a process-level proof that no
`git commit`, `git push` or `gh` process was ever spawned.

Four findings were raised against the implementation and are now closed under the GOV-AUTO-11
correction round, and three further High blockers raised by an independent review of the delivered
code are closed under the correction round recorded after it; each of the seven was reproduced
first, and each is now held closed by a named test rather than by prose. They are recorded in full
below. Two §25 commands — `pre-commit run --all-files` and `pytest -q -m live_cli -rs` — were
deliberately not executed, and that omission is recorded rather than papered over.

## What was delivered

| File | Role |
|---|---|
| `milestone_runner/__init__.py` | Docstring-only marker; re-exports nothing (the `successor_planning` precedent). |
| `milestone_runner/models.py` | Typed run state, the milestone spec, results, the outcome/failure taxonomy, `ALLOWED_RUN_TRANSITIONS`. |
| `milestone_runner/config.py` | The validated runner configuration of §21, with closed capability enums. |
| `milestone_runner/plan.py` | `MilestonePlanLoader`: load, validate, dependency-order, coverage-reconcile, and DEC-016-005's plan-root rules. |
| `milestone_runner/state.py` | `RunStateStore`: atomic publication, schema versioning, resume, and §17a's single redaction write boundary. |
| `milestone_runner/lock.py` | `RunLock`: an `fcntl.flock` process lock adopting `RepositoryLock`'s disciplines and importing nothing. |
| `milestone_runner/scope.py` | `ScopeGuard`: segment-aware matching, the cumulative allowlist, per-milestone scope, forbidden paths. |
| `milestone_runner/git_inspect.py` | `GitReadOnlyInspector`: six fixed read-only argv forms and nothing else. |
| `milestone_runner/approval_git.py` | The single gated façade able to construct a mutating argv (§20); ships disabled. |
| `milestone_runner/verification.py` | `VerificationExecutor`: bounded execution, full-output persistence, the machine-readable governance gate. |
| `milestone_runner/providers/{__init__,base,claude_cli,codex_cli}.py` | The package-owned provider subpackage (DEC-016-002). |
| `milestone_runner/results.py` | §18's machine-result grammar, extraction and strict parsing. |
| `milestone_runner/review.py` | `ReviewCoordinator`: the shared budget helper, the severity policy, the findings ledger. |
| `milestone_runner/recovery.py` | `RecoveryCoordinator`: the four recovery commands and their append-only ledgers. |
| `milestone_runner/prompts.py` | The four fixed prompt templates and typed interpolation. |
| `milestone_runner/application.py` | `MilestoneRunnerApplication`: the sole transition authority. |
| `src/ai_workflow_engine/cli.py` | Additive only: one sub-app, one `add_typer`, thirteen thin commands. No existing command moved, renamed or changed. |
| `tests/test_milestone_runner_*.py`, `tests/test_cli.py` | The §26 matrix, the §22 invariant suite, and the §27 Tier 1 and Tier 2 acceptance suites. |

`pyproject.toml`, `self-governance.yaml`, `.pre-commit-config.yaml`, `.github/**` and `scripts/**`
were not changed, exactly as §23.4 predicted: the wheel `packages`, `mypy.files` and
`pytest.testpaths` entries all name whole trees, and live acceptance reuses the existing `live_cli`
marker rather than introducing a second exclusion.

## Verification evidence (§25)

Every command was run in the `ai-workflow-engine` conda environment against this branch at
baseline `4fa9212`, after the GOV-AUTO-11 correction round closed.

| Check | Result |
|---|---|
| `pytest -q` | PASS — 5252 passed, 34 deselected (455.3 s) |
| `pytest -q tests/test_milestone_runner_security.py tests/test_milestone_runner_acceptance.py` | PASS — 171 passed, 2 deselected (162.9 s): 79 security, 92 acceptance, the 2 deselected being Tier 2 |
| `ruff check .` | PASS — all checks passed |
| `black --check .` | PASS — 274 files unchanged |
| `mypy --strict` | PASS — no issues in 153 source files |
| `workflowctl verify --config self-governance.yaml` | PASS before and after the suite — git, task-state, governance, registries, handover |
| `git diff --check` | PASS |
| `pip wheel --no-deps` | PASS — built inside `TestWheelContainsMilestoneRunner`; all nineteen package files shipped |
| Out-of-tree import from a fresh venv | PASS — `TestOutOfTreeImport` |
| Changed-path allowlist (`git status --porcelain`) | PASS — every path inside §23 |
| Mutating Git / commit / push / PR / merge | PASS — none run, proved four ways (§27) |

The two §25 commands **not** executed for this evidence set, each recorded rather than assumed:

- `pytest -q -m live_cli -rs`. The Tier 2 tests this stage adds spawn real provider CLIs, and §27
  makes them executable only during an authorized implementation or verification phase. They are
  written, collected under the existing marker, and excluded from the default run by `addopts`.
- `pre-commit run --all-files`. `.pre-commit-config.yaml` configures exactly three hooks —
  `ruff-check --fix`, `black`, and `mypy` with no `args` — and all three were run directly against
  the whole tree and are recorded above. The hook run would therefore be expected to be a no-op,
  but "expected" is not "observed": this report claims only what was actually run. The command
  remains part of the pre-merge verification the Human Owner performs alongside the commit and push
  acts §31 reserves to them.

### Governance state before and after

`workflowctl verify --config self-governance.yaml` returns `PASS` on all five checks both before
and after the suite runs — 1 Current, 51 Done and 6 Planned tasks; 26 stages across 2 registries;
1 handover manifest record. AUTO-016's own tests never perturb this repository's governance state,
because every one of them writes only under `tmp_path` and a `HOME` redirected into `tmp_path`.

### Security invariants (§22)

`tests/test_milestone_runner_security.py` carries one negative test per invariant, all twenty
covered, and `INVARIANT_TESTS` in that module maps each invariant to the class that carries it —
asserted total and asserted to name only classes that exist and hold tests.

Each structural invariant is proved by an AST sweep over the package **and** by running the same
detector over a deliberately offending module written to `tmp_path`, so no invariant is proved by a
detector that could not have failed.

| # | Invariant | Negative test |
|---|---|---|
| 1 | No credential storage or forwarding | `TestNoCredentialInAnyRecord` |
| 2 | Transcripts sanitized before writing, referenced not inlined | `TestSecretShapedProviderOutputNeverReachesDisk` |
| 3 | No shell | `TestNoShellTrue` |
| 4 | Mutating Git only inside the gated façade | `TestMutatingGitOnlyInApprovalGitModule` |
| 5 | No GitHub access, no network call | `TestNoGhInvocation`, `TestNoNetworkCall` |
| 6 | No `agentos_workflow` import | `TestNoAgentosWorkflowImport` |
| 7 | State root outside the repository | `TestStateRootOutsideRepositoryEnforced` |
| 8 | Symlink and path-escape rejection | `TestSymlinkComponentRejected` |
| 9 | Atomic publication | `TestAtomicPublicationNeverLeavesATornRecord` |
| 10 | Single-holder mutual exclusion | `TestSingleHolderMutualExclusion` |
| 11 | Budget integrity | `TestBudgetIntegrity` |
| 12 | Scope integrity | `TestScopeIntegrity` |
| 13 | Non-destruction | `TestNoDestructiveGitPathAnywhere` |
| 14 | Untrusted provider text is data, never control | `TestUntrustedProviderTextNeverDirective` |
| 15 | Evidence preservation | `TestEvidencePreservedOnRejection` |
| 16 | Governance non-mutation | `TestGovernanceNonMutation` |
| 17 | Capability modes unrepresentable | `TestCapabilityModesUnrepresentable` |
| 18 | No fabricated success | `TestNoFabricatedSuccess` |
| 19 | No plan discovery inside the repository | `TestNoPlanDiscoveryInsideTheRepository` |
| 20 | Provider adapters are package-owned | `TestProviderSpawnOnlyFromProvidersSubpackage` |

Two invariants are worth naming for how they are proved rather than only that they are. Invariant 1
is proved with a control: the same on-disk scan that fails to find a credential-shaped value
succeeds in finding a benign allowlisted value the run really did persist, so its silence about the
credential is evidence of absence rather than of a scan that could see nothing. Invariant 6 is
proved twice — no module names `agentos_workflow`, and a subprocess importing
`milestone_runner.application` ends with no `agentos_*` module in `sys.modules`.

### Prototype-defect regressions (§26)

All ten are present under their contract-named test names and pass;
`TestPrototypeDefectRegressionsAreComplete` asserts the set is complete and that each named class
really exists in the suite it is recorded against.

| Defect | Regression test | Suite |
|---|---|---|
| P-1 allowlist widening | `TestP1GlobDoesNotCrossPathSeparator` | `test_milestone_runner_scope.py` |
| P-2 uncaught `KeyError` | `TestP2MissingResultFieldIsTypedRejection` | `test_milestone_runner_results.py` |
| P-3 inconsistent budget accounting | `TestP3RoundConsumedOnlyAfterResultParses` | `test_milestone_runner_review.py` |
| P-4 unreachable retry constant | `TestP4NoUnreachableRetryCeiling` | `test_milestone_runner_review.py` |
| P-5 mutating Git bypasses the guard | `TestP5AllGitRoutesThroughGuard` | `test_milestone_runner_application.py` |
| P-6 unlocked state write | `TestP6AbortAcquiresLock` | `test_milestone_runner_application.py` |
| P-7 fragile governance gate | `TestP7GovernanceGateUsesMachineReadableOutput` | `test_milestone_runner_results.py` |
| P-8 evidence loss | `TestP8FullVerificationOutputPersisted` | `test_milestone_runner_results.py` |
| P-9 transcript collisions | `TestP9TranscriptSequenceNumberPreventsCollision` | `test_milestone_runner_state.py` |
| P-10 heuristic failure classification | `TestP10FailureClassRecordedNotRegrepped` | `test_milestone_runner_providers.py` |

### Packaging and out-of-tree import (§25)

`TestWheelContainsMilestoneRunner` builds a real wheel with
`pip wheel --no-deps --no-build-isolation` and asserts the archive carries exactly the nineteen
`ai_workflow_engine/milestone_runner/**.py` files §8 fixes — no more and no fewer — and that the
three top-level packages `pyproject.toml` already shipped are still there.

`TestOutOfTreeImport` creates a fresh virtual environment, installs that wheel with
`--no-deps --no-index`, and imports `ai_workflow_engine.milestone_runner`,
`...milestone_runner.application` and `...milestone_runner.providers.codex_cli` with the working
directory outside the repository. The imported module's `__file__` is asserted to resolve inside
the virtual environment and **not** inside this checkout, so the proof is about the installed wheel
rather than about a path that happened to be importable. The installed console script's
`workflowctl milestone-runner --help` is exercised in the same environment.

## Live acceptance evidence (§27)

### Tier 1 — disposable-repository acceptance

`tests/test_milestone_runner_acceptance.py` drives a real `git init` repository under `tmp_path`,
with a real remote, a real commit, real governance documents and a real contract, against a
three-milestone plan at the external default plan root, using a scripted **fake** provider: a real
Python program spawned through the production `ProviderInvoker` by a test-owned adapter with its own
argv. The run state, the run lock, the transcripts, the redaction boundary and the verification
commands are all the production ones.

| §27 case | Observed outcome |
|---|---|
| Full happy path | `READY_FOR_COMMIT_APPROVAL`, three milestones complete, one review round, zero provider failures |
| One correction round | `READY_FOR_COMMIT_APPROVAL`; review 1, correction 1, closure 1; the blocker `CLOSED` by closure verification |
| Still blocked after correction | `HUMAN_INTERVENTION_REQUIRED`, the blocker still `OPEN`, the tree untouched, `resume` refused |
| Forbidden path written | stop, `DIRTY_TREE`, the offending file left exactly where the provider wrote it |
| Outside the cumulative allowlist | stop, `DIRTY_TREE`, working tree byte-identical afterwards |
| Outside the active milestone's scope | stop, `OUT_OF_MILESTONE_SCOPE` |
| Disjoint per-milestone scopes | runs to the commit gate; each milestone answers for its own delta against the previous checkpoint (GOV-AUTO-11-F1) |
| Twelve parser-rejection classes | every one refused with a published `MILESTONE_FAILED`; no milestone completed, no budget consumed, every transcript preserved, `reopen-milestone` able to clear the stop |
| Malformed review result | `HUMAN_INTERVENTION_REQUIRED`; `provider_failure_count` 1, `successful_review_rounds` 0 |
| Provider exits non-zero | refused, `COMMAND_FAILED` recorded at invocation time, `MILESTONE_FAILED` published |
| Failing focused verification | `MILESTONE_FAILED` published with the failing result recorded |
| Interruption and resume | a real `SIGKILL` mid-invocation, then `resume` drives the run to the commit gate |
| Resume from each published state | all six mid-run states and all five post-milestone states continue to the commit gate; `resume` twice with no change is a no-op |
| Lock contention | `start`, `resume` and `abort` refused while another process holds the lock; the four read-only commands unaffected |
| `reopen-milestone` | clears a `MILESTONE_FAILED` run; budgets, completed milestones and prior transcripts preserved |
| `reconcile-milestone` | accepts a result hash-matching the run's own transcript; records `reconstructed_from_verified_evidence`; post-state `FOCUSED_VERIFYING` |
| `revalidate-correction` | clears a post-correction verification failure with every budget untouched; post-state `CLOSURE_VERIFYING` |
| `recover-failed-review` | restores exactly one review budget; the paired case proves the driven flow never creates the combination it repairs |
| Print-only commit gate | prints `git add --` and `commit --message`, executes nothing, `HEAD`/reflog/remote refs unchanged |
| Push gate | unreachable from `READY_FOR_COMMIT_APPROVAL`, refused |
| Typed confirmation alone | executes nothing: the configuration flip ships `false` and both are required |

After every case: `git status --porcelain` shows only allowlisted paths, `HEAD` is unchanged, no
governance document's bytes or mtime moved, no `claude`/`codex`/`gh` process was spawned, and the
disposable repository is discarded with `tmp_path`.

### The four-way no-automatic-mutation proof

| Means | Evidence |
|---|---|
| (a) AST | No `gh` literal anywhere, and no mutating Git subcommand in any package file except `approval_git.py` |
| (b) Behavioural | `approve-commit` with shipped defaults returns `executed=False` and the exact commands as text |
| (c) Git-level | `HEAD`, `reflog` and `for-each-ref refs/remotes` identical across a complete run plus an approval |
| (d) Process-level | No spawned vector carries `commit` or `push`; no `claude`, `codex` or `gh` process; and the recorder is shown non-empty by the `rev-parse --verify HEAD` observations it did capture |

### Prototype non-interference (DEC-016-006)

An autouse fixture snapshots `~/.local/share/auto015-runner/` — every file's size, SHA-256 and
`st_mtime_ns`, `state/` and its historical transcripts included — before and after **every** test in
the acceptance module, and asserts the snapshots are equal. A second autouse fixture wraps `os.open`
and fails any call whose path names the prototype, so no acceptance case reads prototype state as
input either; the same guard rides along with every test in the security module.
`TestPrototypeRunnerUnchanged` additionally proves the comparison is capable of noticing a change,
on a directory the test itself owns, and asserts that no executable string in the package addresses
the prototype at all.

The prototype is unchanged by this work in every respect. Its post-acceptance deprecation is a
separate operator act outside this stage's allowlist, and deletion remains barred pending a separate
explicit Human Owner decision (§28).

### Plan-location assertions (DEC-016-005)

Each run asserts the plan was loaded from the external root
`~/.ai-workflow-engine/milestone-runs/<repository-id>/plans/`, that no `*.yaml` and no `plan.json`
exists anywhere inside the disposable repository afterwards, and that no `os.listdir`/`os.scandir`
call touched a path inside the worktree during the run. The source plan files are byte-identical
after the run, so the resolved snapshot under the artifact root never rewrites its source.

### Tier 2 — real-provider smoke acceptance

`TestLiveProviderSmokeAcceptance` is written under the existing `live_cli` marker, excluded from the
default run and from CI by `addopts = "-ra -m 'not live_cli'"`, and skips when the provider
executables are absent. It drives a real Claude implementation invocation and a real Codex read-only
review against a disposable repository and asserts the run reaches `READY_FOR_COMMIT_APPROVAL`
without committing, with the prototype snapshot and the repository's Git evidence unchanged. It was
**not executed** as part of this milestone's verification: §27 makes it executable only during an
authorized implementation or verification phase, and presenting a fake-provider result as evidence
that a real CLI works is exactly the conflation the marker exists to prevent.

## Correction round — GOV-AUTO-11

One correction round occurred. The Tier 1 acceptance suite, written last, found four defects in
work earlier milestones had already delivered. §29's discipline was followed in each case:
**reproduced first**, then classified, then fixed at the smallest possible scope under an explicit
Human Owner remediation ruling (GOV-AUTO-11) that reopened the owning milestone — because none of
the four lay inside AUTO-016-M09's own `allowed_files`, and M09 fixes nothing it does not own.

Each finding's reproduction is a test that is still in the suite, so the closure is held by an
assertion rather than by this paragraph. The ruling itself is a record of the run that made it and
of the Human Owner who gave it; it is not written into this repository, because §24 forbids this
stage from editing any governance document, and a completion report is a report and not a
governance record.

| Finding | Reproduced by | Remediation | Now held by |
|---|---|---|---|
| **GOV-AUTO-11-F1** | `TestPerMilestoneScopeAgainstAnAccumulatingTree` | §15 check 2 answers for the current milestone's *delta* since the previous durable checkpoint, decided by content digest; checks 1 and 3 still see every changed path (`scope.py`, `models.py`, `application.py`) | `test_a_disjoint_scope_plan_now_runs_to_the_commit_gate`, `test_a_milestone_writing_another_milestones_file_still_stops`, `TestMilestoneCheckpoint` in `test_milestone_runner_state.py` |
| **GOV-AUTO-11-F2** | `TestEveryParserRejectionClass` | `(IMPLEMENTING, MILESTONE_FAILED)` added to `ALLOWED_RUN_TRANSITIONS`, so a malformed implementation result stops durably instead of raising `TransitionRefused` (`models.py`) | the twelve parametrized rejection cases, and `test_a_reopened_milestone_can_be_resumed_after_a_malformed_result` |
| **GOV-AUTO-11-F3** | `TestInterruptionAndResume` | `resume` dispatches on the state it loaded rather than restarting the flow, so all six mid-run and all five post-milestone states continue (`application.py`) | `test_resume_drives_a_mid_run_state_to_the_commit_gate`, `test_resume_from_a_post_milestone_state_advances_the_run`, and the paired "repeats nothing" assertions |
| **GOV-AUTO-11-F4** | `tests/test_milestone_runner_providers.py::TestProviderSpawnOnlyFromProvidersSubpackage` | The provider-ownership AST test's allowed set had predated the §20 approval façade and read `approval_git.py`'s contract-required `subprocess.run` as a violation; the set now distinguishes the four spawn capabilities instead of conflating them | `SPAWN_CAPABILITIES` in that module, asserted against the package, and the same invariant stated independently in `tests/test_milestone_runner_security.py` |

**Each blocker was reproduced before it was closed.** F-1, F-2 and F-3 were reproduced by
acceptance cases that asserted the defective behaviour before the remediation and assert the
corrected behaviour now; each of those cases carries the finding's identifier in its docstring, so
the reproduction is traceable in the file rather than only in this report. F-4 was reproduced twice
in isolation (`pytest -q <nodeid>` → 1 failed) and in two full-suite runs, and its own module now
records the finding at the definition of the allowed set.

No second correction round was needed, and none was taken: §19 permits exactly one, and one is
what this stage used.

## Correction round — the independent implementation review

A review conducted independently of the implementation run raised three High blockers against
`application.py`. They are distinct from the GOV-AUTO-11 round above, which the run raised against
itself; these were found afterwards, against the delivered code, and closed in one bounded round.
Each was **reproduced first** by a test that failed against the delivered code and passes against
the correction, so the closure is held by an assertion and not by this paragraph.

| Blocker | What it was | Reproduced by | Correction |
|---|---|---|---|
| **AUTO016-IMPL-001** | `_invoke_provider` published `PROVIDER_WAIT` but appended the `ProviderRunRecord` only *after* `adapter.invoke` returned. `state.py`'s reconciliation keys on "the last provider run has no `completed_at`", so that row never existed and the pair could never be true: a crash after an effectful provider left a record showing nothing in flight, and resume returned `CONTINUE` and re-invoked — violating §13, §22 invariant 14 and `MACHINE_GATES.md` §2a | `TestProviderInvocationIsDurableBeforeItRuns` (three cases, including one that reads the durable `state.json` at the exact crash window through a real adapter seam) | `ProviderInvoker.invoke` gained an `on_started` hook, called once the sequence and the three transcript names are fixed and **before the process exists**. `_invoke_provider` publishes the incomplete row there and the completed record replaces that same row, so one invocation stays one entry. `state.transcript_reference` is the single definition of the reference, so a row written before its transcript names it the way the write later does |
| **AUTO016-IMPL-002** | The push gate was unreachable after the runner's own approved commit: the commit advanced `HEAD` and transitioned to `READY_FOR_PUSH_APPROVAL`, but `approve-push` re-ran a preflight whose condition 4 still demanded `config.repository.baseline_sha` and returned `HEAD_DRIFT`. The contracted §5 commit-to-push flow could not execute at all | `TestTheCommitGateLeadsToTheReachablePushGate` | §4 item 4 admits exactly one event that may advance `HEAD` — "a Human Owner–approved commit executed through that gate … recorded with the approval that authorized it". `ApprovalRecord.resulting_head_sha` is that record; `run_preflight` gained an `expected_head_sha` parameter defaulting to the configured baseline, and only the §20 gates pass the recorded value. A commit no approval authorized still fails condition 4, which is asserted |
| **AUTO016-IMPL-003** | The approval and its consumption were persisted only *after* the Git mutation, so process loss after Git succeeded left no durable grant and no consumption record. Because a successful push leaves local `HEAD` unchanged, the same durable `READY_FOR_PUSH_APPROVAL` state could execute it again — against §20's durable-recording and single-use requirements and §22's evidence guarantees | `TestGitApprovalIsDurableBeforeTheMutation` (three cases: the attempt is durable before the first vector; process loss after Git leaves an attempted, unconsumed grant; that pair refuses a second execution) | The gate stamps `ApprovalRecord.execution_started_at` and hands the approval to an `on_execute` hook *after* all three §20 gates pass and *before* the first vector, and the application publishes it there. The consumption replaces that same row afterwards. `unreconciled_attempt` reads an attempted-but-unconsumed grant as an act nobody reconciled and refuses the gate; the print-only default never reaches the hook, so repeated print-only invocations are unaffected |

The model carries the two new invariants rather than leaving them to a call site: a consumed
approval must record when its execution was attempted, and only a consumed approval may name where
it landed `HEAD`. Both are asserted in `test_milestone_runner_state.py`.

Scope was held to what the three blockers required. No deferred (Medium/Low) finding was addressed,
nothing was committed or pushed, and no governance document, task record, Registry row, mirror or
handover file was touched.

### An observed flake, recorded rather than presented as a defect

An earlier full-suite run failed
`tests/test_cli.py::test_successor_planning_publishes_once_and_is_idempotent`
(`publication` was `None` on the second invocation, so `second["created"]` raised `TypeError`). It
did **not** reproduce: the identical command passed on re-run, the suite with every AUTO-016 module
excluded passed, and every subsequent clean full-suite run — including the one recorded above —
passed that test. Both observed failures occurred while `mypy --strict` and `workflowctl verify`
were running concurrently against the same checkout, which is the load condition the
successor-planning publication path — `os.chmod`, a re-checked no-follow root, and a
content-addressed atomic write — is sensitive to. It is recorded here as a suspected load-sensitive
flake in a pre-existing AUTO-015 test, not as an AUTO-016 defect and not as a proven defect at all;
no fix is attempted on that evidence, and none is bundled into this stage.

## Deferred findings (§24, §29)

Every finding §24 and §29 name was re-verified as non-blocking for this implementation, and none was
bundled into this stage.

| Finding | Disposition |
|---|---|
| **OD-6** — cancellation semantics for an actively-implementing runtime workflow | Not applicable. AUTO-016 owns no runtime `WorkflowState` and drives no `WorkflowState` transition; its run status is its own `StrEnum`. Untouched. |
| **OD-7** — safe re-authorization after baseline-commit drift | Not a blocker. Any baseline drift is an unconditional hard stop (§4 item 4), and no approval is ever re-bound, so the strict reading is implemented rather than the open question resolved. Untouched. |
| **OD-10** — Git/GitHub Skill call sites not forwarding `allowed_environment_variables` | Not applicable. AUTO-016 invokes no Skill and no `gh`; invariant 5's tests prove the `gh` surface does not exist here. Untouched. |
| **OD-11** — `stage_contract_hash` prefix disagreement | Structurally avoided. The contract is pinned by full SHA-256 in the runner's own configuration and shares no code with `calculate_contract_hash`. Untouched. |
| **OD-12** — QA round-numbering collision in `run_repair_loop` | Not applicable. AUTO-016 runs no repair loop and owns five separately-tested counters (§19). Untouched. |
| **D-14, D-15, D-16** — AUTO-013's `RemoteRefEvidence`/`PullRequestEvidence` reconciliation and report sequencing | Not applicable. They concern `agentos_workflow`'s runtime evidence model, which AUTO-016 neither reads nor writes. Untouched. |
| **GOV-AUTO-11-F1 … F4** (this report) | Not deferred. Reproduced, ruled on, remediated in the reopened owning milestones, and each held closed by a named test. |
| Suspected `test_successor_planning_publishes_once_and_is_idempotent` flake | Deferred, unfixed, and not claimed as a defect: it did not reproduce, and it lies in AUTO-015's surface. |

## Recorded contract ambiguities

Three ambiguities were resolved by implementing the narrower reading and recording the gap rather
than by choosing the broader one.

- **`StopReason` has no code for two reachable stops.** §10's vocabulary transcribes only the twelve
  codes the contract writes in backticks. A failed deterministic verification set and a provider
  failure the run may not repeat are named by none of them, so both are recorded under an existing
  code and the gap is reported instead of a thirteenth code being coined.
- **§15's other two checks are stops without codes.** The cumulative-allowlist and forbidden-path
  checks are described as stops and given no code; `ScopeViolation` therefore carries `None` for them
  and records which check failed.
- **§15 check 2's "every changed path"** does not say whether "changed" means changed by this run or
  changed by this milestone. Both readings satisfy §4 item 6. The literal, wider reading was
  implemented first and produced GOV-AUTO-11-F1; the Human Owner's remediation ruling made the
  narrower reading binding, and it is the one that ships.

## Stop condition (§31)

The implementation stops here. It has not authorized a stage, registered or transitioned a stage,
changed a task status or a mirror, accepted a scope expansion, widened an allowlist at runtime,
accepted or closed a Critical or High finding, created or switched a branch, opened a pull request,
merged, reset, restored, stashed, rebased, cleaned, or discarded any repository work.

Commit, push, pull-request creation and merge for AUTO-016 itself remain the Human Owner's separate
acts.
