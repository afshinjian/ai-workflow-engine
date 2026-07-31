# AUTO-009 — Completion Report

| Field | Value |
|---|---|
| **Stage** | AUTO-009 — WorkflowService boundary and read-only `workflowctl auto` surface |
| **Role** | Engine implementation session |
| **Branch** | `feature/auto-009-workflow-service` |
| **Baseline** | `main` == `origin/main` == `98acc1951f0d5d361af907c4333a04992f901918` |
| **Registry state** | `NOT_STARTED → AUTHORIZED → IN_PROGRESS` |
| **Task status** | `Planned → Current` |
| **Date** | 2026-07-31 |
| **Status** | Implemented and validated; **stopped before any commit, push, PR, or merge**, pending Human Owner review |

---

## 1. Baseline evidence

Verified before any change was made:

| Precondition | Evidence |
|---|---|
| Branch | `main` |
| HEAD | `98acc1951f0d5d361af907c4333a04992f901918` |
| `main == origin/main` | `git rev-parse HEAD` and `git rev-parse origin/main` both `98acc195…` |
| Working tree | `git status --porcelain` empty |
| Predecessors | AUTO-001..AUTO-008 all `COMPLETE`; GOV-AUTO-06 and GOV-AUTO-07 both `Done`, each having explicitly recorded that AUTO-009 remained unauthorized |
| Other `Current` tasks | none — the `Current` set was empty (a legal state under `maximum_current_tasks: 1`) |
| `workflowctl verify` | PASS on all five checks |
| `pytest -q` | 3,005 passed |

The stage branch `feature/auto-009-workflow-service` was created from that clean, synchronized
`main`; `git rev-parse HEAD` on the new branch was still `98acc195…`.

### Task-ID selection

`AUTO-009` was checked against the governance parser before being used. `TASK_ID` /
`TASK_HEADING` are `\b([A-Za-z]+-\d+)\b` (`src/ai_workflow_engine/governance/parser.py`), so
`AUTO-009` resolves to the literal id `AUTO-009`, which appears in no task record, no registry
row, and no mirror. It is the correct next id in the AUTO family — unlike GOV-AUTO-06/07, which
were deliberately non-AUTO governance follow-ups, this is a real stage and takes a real §4
registry row.

### Governance registration

Registered and authorized in one act (AUTO-009 had never been registered before, exactly as with
AUTO-008), across the rule-1 sanctioned edit set only:

* `docs/TASK_QUEUE.md` — new `## AUTO-009` section, `Status: Current`, full scope and prohibitions
* `docs/current_task.md`, `docs/remaining_tasks.md` — mirrors
* `docs/PROJECT_STATE.md` — prose only; the `Current Version:` fact line untouched
* `docs/DECISION_LOG.md` — one new dated entry (decision, alternatives considered, rationale, boundaries)
* `docs/CHANGELOG.md` and `docs/workflow-automation/CHANGELOG.md` — one `[Unreleased]` entry each
* `docs/workflow-automation/STAGE_REGISTRY.md` — §4 row (state `IN_PROGRESS`), two §5 authorization-log
  rows (authorization; initial-start preflight), Version 6.12 → 6.13

`handover/**` was deliberately **not** touched: rule 1 excludes it from the sanctioned set, and
leaving it alone keeps `check-handover` green.

---

## 2. Architecture implemented

```text
workflowctl auto  ->  agentos_workflow.cli_auto  ->  agentos_workflow.service.WorkflowService
                                                              |
                                                              v
                          agentos_workflow read-only state, audit, report, configuration APIs
                          (StateStore readers · skills.reporting.read_reports · config.loader)
```

Dependency direction is one-way and narrow. `src/ai_workflow_engine/cli.py` reaches AgentOS
through **exactly one name** — `agentos_workflow.cli_auto.auto_app` — and no AgentOS internal
module is imported anywhere else in that file. `agentos_workflow.service` imports nothing from
`ai_workflow_engine` at all, so the domain half of the boundary is independent of the CLI.

`cli_auto` reaches back into `ai_workflow_engine.cli` for `_protected`, `_write_stdout`, and
`_contract_v2_success` through **function-body (deferred) imports**. This is deliberate and is
documented in the module docstring: `ai_workflow_engine.cli` imports `cli_auto` to register the
sub-app, so a module-level import back would be a cycle that breaks whichever module is imported
first — and importing `cli_auto` directly is exactly what its tests do. Deferring removes the
cycle while letting all four commands reuse the *existing* error-envelope / exit-code / stderr
implementation verbatim rather than growing a second copy of the CLI contract that could drift.
Both import orders are tested (`python -c "import agentos_workflow.cli_auto"` and
`python -c "import ai_workflow_engine.cli"` each succeed standalone).

The one thing `cli_auto` restates rather than imports is the two-member `OutputFormat` enum, which
Typer needs at decoration time — the single moment the cycle cannot be deferred past. A test pins
its member names and values as identical to `ai_workflow_engine.cli.OutputFormat`, which is what
keeps the `cast` in `cli_auto._protected` honest.

---

## 3. Public service API

```python
class WorkflowService:
    def __init__(self, config: WorkflowConfig) -> None: ...
    def status(self, workflow_id: str | None = None) -> StatusResult: ...
    def list(self) -> WorkflowListResult: ...
    def audit(self, workflow_id: str) -> AuditResult: ...
    def report(self, workflow_id: str, *, report_kind: str | None = None) -> ReportResult: ...

def open_workflow_service(
    repository_path: Path, config_path_override: Path | None = None
) -> WorkflowService: ...
```

`open_workflow_service` is a module-level function rather than a classmethod precisely so the
class's public surface is *exactly* the four operations — a structural claim a test can assert,
which a constructor hanging off the class would have quietly weakened.

### Typed results

All are frozen, `extra="forbid"` pydantic models, matching this package's existing record-model
convention:

| Model | Contents |
|---|---|
| `RepositoryContext` | `repository_identity`, `repository_path`, `baseline_branch`, `remote_name`, `stage_contract_directory`, `state_directory`, `audit_directory` |
| `WorkflowStatus` | `workflow_id`, `current_state`, `terminal`, `stage_id`, `target_repository`, `repository_path`, `transition_count`, `first_transition_at`, `last_transition_at` |
| `StatusResult` | `repository`, `workflow` (nullable), `workflow_count` |
| `WorkflowSummary` / `WorkflowListResult` | per-workflow summary rows plus the repository context |
| `AuditResult` | `workflow_id`, `transitions: list[StateTransitionRecord]`, `command_executions: list[CommandExecutionRecord]` |
| `ReportArtifactView` / `ReportResult` | `report_kind`, `sequence`, `path`, `sha256`, `size_bytes`, `content` |

`AuditResult` deliberately carries the store's **own** record models rather than a projection of
them, so every field `AUDIT_MODEL.md` §2-3 names — including the `gate_evidence_ref`, `stdout_ref`,
and `stderr_ref` evidence references — survives the boundary intact.

`current_state` is reported as a plain string rather than a `WorkflowState`: an unrecognized state
in a persisted history is a fact about the audit trail that must remain reportable, and coercing it
would either hide it or fail the whole read. `terminal` answers the enum's question about that
string honestly (an unrecognized state is not terminal).

### Errors

| Case | Error |
|---|---|
| Missing configuration | `ConfigurationNotFoundError` (existing, unchanged) |
| Invalid configuration | `InvalidConfigurationError` (existing, unchanged) |
| Configuration naming a different repository | `ConfigurationRepositoryMismatchError` (existing, unchanged) |
| Unsafe `workflow_id` | `StateStoreError` (existing, unchanged) |
| Symlinked record path | `StateStorePathConfinementError` (existing, unchanged) |
| Corrupt / non-replayable history | `StateStoreCorruptionError` (existing, unchanged) |
| Workflow with no persisted history | `WorkflowNotFoundError` (**new**) |
| Named `report_kind` with no artifact | `ReportNotFoundError` (**new**) |
| Skill-level report failure | `WorkflowServiceError`, carrying the original typed `SkillFailure` on `.skill_failure` |

The two new errors exist only because no pre-existing error means "this read-only lookup found
nothing": the closest candidates (`MissingPersistedStateError` and siblings) are `ResumeError`
subclasses whose meaning is bound to resuming a workflow, which is not what happened. See §11.

---

## 4. CLI commands added

```text
workflowctl auto status --target-repo PATH [--config PATH] [--workflow-id ID] [--output human|json]
workflowctl auto list   --target-repo PATH [--config PATH]                     [--output human|json]
workflowctl auto audit  --target-repo PATH [--config PATH]  --workflow-id ID   [--output human|json]
workflowctl auto report --target-repo PATH [--config PATH]  --workflow-id ID
                                                            [--report-kind KIND] [--output human|json]
```

Conventions, all matching the pre-existing CLI:

* **Human output** — rendered lines through `_write_stdout`, as `state show` does.
* **JSON v1** — canonical JSON as exact bytes on stdout, unenveloped, as `state` / `agent run` /
  `migrate` do.
* **JSON v2** (`--contract-version 2`) — the stable success envelope with commands named
  `auto-status`, `auto-list`, `auto-audit`, `auto-report`, following the `migrate-inspect`
  precedent.
* **Exit codes** — `0` success; v1/human failure `2` with `ERROR: …` on stderr and empty stdout;
  v2 JSON failure `1` with exactly one error envelope on stdout and empty stderr. These come from
  the reused `_protected`, so they are the same code path, not a re-implementation.
* **Debug** — the root `--debug` adds a traceback on stderr and leaves stdout untouched.
* **Machine output never goes through Rich**, so `FORCE_COLOR` cannot inject escape sequences.

`--target-repo`/`--config` keep `CLI_SPEC.md` §3's names and meanings. Where CLI_SPEC and the
existing engine CLI differ, the engine CLI wins — see §11 (assumption A2).

Argument-parsing note: `--target-repo`/`--config` set `exists=False, readable=False` so Click
never rejects a path before the command body runs; every existence and readability failure is
reported through the stable contract instead, the same reason `migrate`'s `--source` does this.

---

## 5. Exact files changed

### Added (4)

| File | Lines | Purpose |
|---|---|---|
| `agentos_workflow/service.py` | 403 | `WorkflowService`, its typed results, and its errors |
| `agentos_workflow/cli_auto.py` | 306 | The `workflowctl auto` Typer sub-application |
| `agentos_workflow/tests/test_service.py` | 661 | Service-boundary tests (58) |
| `tests/test_cli_auto.py` | 493 | CLI tests (61) |

### Modified — implementation (3)

| File | Change |
|---|---|
| `agentos_workflow/orchestrator/state_store.py` | **+33.** One new read-only method, `StateStore.list_workflow_ids()`. No existing method, record schema, confinement rule, or append path touched. |
| `agentos_workflow/skills/reporting.py` | **+180.** New `PersistedReport` dataclass, `read_reports()`, `_parse_report_filename()`, `_read_confined_report()`; `_open_confined_directory` gained a `missing_ok: bool = False` keyword. No existing generator, naming rule, idempotency rule, or write path changed; every existing caller passes `create=True` and is unaffected by the new default-`False` keyword. |
| `src/ai_workflow_engine/cli.py` | **+14, −0.** One comment block, one import, one `add_typer` call, at the bottom of the file. No existing command moved, renamed, reordered, or altered. |

### Modified — tests (2)

`agentos_workflow/tests/test_state_store.py` (+60, 7 tests) and
`agentos_workflow/tests/test_skills_reporting.py` (+137, 20 tests), each appended to the existing
suite for the module it covers.

### Modified — governance (8)

`docs/TASK_QUEUE.md`, `docs/current_task.md`, `docs/remaining_tasks.md`, `docs/PROJECT_STATE.md`,
`docs/DECISION_LOG.md`, `docs/CHANGELOG.md`, `docs/workflow-automation/CHANGELOG.md`,
`docs/workflow-automation/STAGE_REGISTRY.md`.

---

## 6. Reuse of existing components

Nothing about persistence, parsing, validation, confinement, or the CLI contract was
re-implemented:

| Concern | Reused component |
|---|---|
| Configuration discovery, strict schema, repository-identity fail-closed check | `config.loader.load_config`, `config.schema.WorkflowConfig` |
| Transition history, command-execution history, current-state derivation | `StateStore.read_transitions` / `read_command_executions` / `current_state` |
| Path confinement (descriptor-relative `O_NOFOLLOW` walk, hard-link and regular-file checks) | `state_store._confined_record_fd`, `reporting._open_confined_directory` |
| Duplicate-JSON-key rejection, monotonic-ordering enforcement, corruption taxonomy | `state_store._parse_jsonl`, `_require_monotonic_order`, `StateStoreCorruptionError` |
| Terminal-state definition | `orchestrator.engine.TERMINAL_STATES` |
| Report naming rule and audit-root confinement | `skills.reporting` (the reader is the inverse of the existing writer, kept in the same module so the two cannot drift) |
| CLI error envelopes, exit codes, stderr discipline, debug behaviour, canonical JSON | `ai_workflow_engine.cli._protected` / `_write_stdout` / `_contract_v2_success`, `prompt.renderer.canonical_json` |

The two genuinely new primitives (`list_workflow_ids`, `read_reports`) were placed **in the modules
that already own the corresponding storage layout**, not in the service. Putting them in the
service would have meant a second copy of the confinement discipline, and two copies of a
confinement rule are two rules that can drift apart.

---

## 7. Proof that the surface is read-only

Demonstrated, not asserted:

1. **Storage-tree hashing.** Every operation (`status()`, `status(id)`, `list()`, `audit()`,
   `report()`, `report(kind=…)`) is run with a SHA-256 over every path, mode, and byte under the
   state directory, the audit directory, **and the target repository**, taken before and after.
   All six are byte-identical.
2. **Lock booby-trap.** `RepositoryLock.acquire` and `__enter__` are monkeypatched to raise
   `AssertionError`, on the lock class itself, so an acquisition through *any* path — the service,
   anything it imports, anything either calls — fails the test. All six operations pass.
3. **No storage creation.** `list()`, `status()`, and `report()` against a repository that has
   never run a workflow return empty results and leave the state and audit directories
   non-existent. `read_reports` likewise creates no `reports/` directory.
4. **Import-graph assertion.** `agentos_workflow.service`'s parsed AST imports no name containing
   `lock`, and no `WorkflowSession` or `RepositoryLock`.
5. **Call-graph assertion.** The same AST contains no call to `record_transition`,
   `record_command_execution`, `append_audit_event`, any `generate_*_report`,
   `write_sanitized_output`, `mkdir`, `write_text`, or `write_bytes`.
6. **No write handle escapes.** `dir(WorkflowService)` has no public name beyond the four
   operations, so no property or attribute hands the `StateStore` (and its append path) back out.
7. **Reports are not regenerated.** After `report()`, the artifact's bytes, `st_mtime_ns`, and mode
   are unchanged; a malformed report is surfaced as malformed and its bytes are left exactly as
   found, not repaired.
8. **Confinement still enforced.** A symlinked workflow directory, a symlinked `transitions.jsonl`,
   and a symlinked report file are each refused — and for `list()` the refusal fails the *whole*
   listing rather than silently omitting the affected workflow, since presenting a short list as a
   complete one would be worse than failing.
9. **Idempotent reads.** `audit()`, `report()`, and `list()` each return equal results on repeated
   calls, and CLI JSON output is byte-identical across runs.
10. **No forbidden verb exists.** Asserted structurally against the real registered command names
    and the real class attributes — see §8.

---

## 8. Tests added

**146 new tests. 3,005 → 3,151, none skipped, none `xfail`.**

| Suite | Count | Covers |
|---|---|---|
| `agentos_workflow/tests/test_service.py` | 58 | surface shape, read-only proof, `status`, `list`, `audit`, `report`, configuration, Skill-failure pass-through |
| `tests/test_cli_auto.py` | 61 | registration, scope protection, human output, JSON v1/v2, error contract, compatibility |
| `agentos_workflow/tests/test_state_store.py` (appended) | 7 | `list_workflow_ids` — absence, filtering, ordering, creation-freeness, symlink refusal |
| `agentos_workflow/tests/test_skills_reporting.py` (appended) | 20 | `read_reports` — content, ordering, filtering, creation-freeness, non-rewriting, hashes, malformed input, unsafe input, symlink refusal |

### Scope-protection test

Both suites carry the full forbidden list — `start`, `authorize`, `approve`, `reject`, `resume`,
`cancel`, `prepare`, `review`, `implement`, `commit`, `push`, `merge` — as a parametrized
structural assertion:

* on `WorkflowService`, `hasattr` is false for every one;
* on `auto_app`, none appears among the registered command names;
* invoking `workflowctl auto <forbidden>` is rejected by the CLI;
* the registered command set is asserted **equal** to `{status, list, audit, report}`, and
  `auto_app.registered_groups == []`, so nothing can hide one level down.

### Compatibility tests

`verify` still returns PASS with the sub-app registered; `version` output is byte-identical
(`"1.0.0\n"`, empty stderr); every pre-existing top-level command and every pre-existing sub-app
(`prompt`, `state`, `agent`, `migrate`) is still registered; `inspect`'s JSON key set is unchanged;
root `--help` still documents every pre-existing command.

---

## 9. Full validation results

Run on `feature/auto-009-workflow-service` with the complete change set in place:

| Command | Result |
|---|---|
| `pytest -q` | **3,151 passed** in 148.58s (baseline 3,005 + 146) |
| `ruff check .` | **All checks passed!** |
| `black --check .` | **214 files would be left unchanged** |
| `mypy --strict` | **Success: no issues found in 117 source files** (baseline 115 + `service.py` + `cli_auto.py`) |
| `pre-commit run --all-files` | ruff **Passed**, black **Passed**, mypy **Passed** |
| `workflowctl verify --config self-governance.yaml` | `task-state` PASS · `governance` PASS · `registries` PASS (19 stages) · `handover` PASS · `git` **FAIL: `upstream_missing`** |

### The single `git` finding

`check-git --output json` reports exactly one finding code: `["upstream_missing"]`. This is the
inherent, pre-existing, already-documented condition of a stage branch that has not been pushed —
the stop condition forbids pushing it. `STAGE_REGISTRY.md` §3 rule 16 names this exact code as the
tolerated case ("`upstream_missing` on a branch never intended to be pushed"), and every prior
AUTO stage reported it identically at this point. It is not caused by any AUTO-009 change: the
same command on the baseline `main` returned PASS. It resolves on publication.

### Packaging and out-of-tree import

* `pip wheel --no-deps` produces `ai_workflow_engine-1.0.0-py3-none-any.whl` containing
  `agentos_workflow/service.py` and `agentos_workflow/cli_auto.py` (no `pyproject.toml` change was
  needed — AUTO-008's `packages` list already covers the whole `agentos_workflow` tree).
* Installed into a clean venv and imported from `cwd == /`: `WorkflowService` exposes
  `['audit', 'list', 'report', 'status']`; `auto_app` registers `['status', 'list', 'audit',
  'report']`; `ai_workflow_engine.cli` shows `auto` among its groups; the installed `workflowctl
  auto --help` console script works.
* Both import orders verified standalone: `import agentos_workflow.cli_auto` first, and
  `import ai_workflow_engine.cli` first.

### Working-tree scope

`git status --porcelain` shows 18 entries and nothing else: 4 added source/test files, this
report, 5 modified implementation/test files, and 8 modified governance documents. No unrelated
file, no stray artifact, no `handover/**` change.

---

## 10. Compatibility evidence

* **`src/ai_workflow_engine/cli.py` diff is +14/−0**, entirely additive, at the bottom of the file.
  No existing command was moved, renamed, reordered, or altered.
* **Every pre-existing test passes unchanged.** The 3,005 baseline tests — including
  `tests/test_cli.py` and `tests/test_cli_contract_v2.py`, the byte-exactness and stdout-purity
  contract suites — were not modified and all pass.
* **No existing public signature changed.** `_open_confined_directory` gained a keyword with a
  default that preserves prior behaviour for all four existing call sites (all pass `create=True`);
  `StateStore` and `skills.reporting` gained names only.
* **Existing schemas untouched.** `StateTransitionRecord`, `CommandExecutionRecord`,
  `ReportArtifact`, `WorkflowConfig`, and `AuthorizationRecord` are unchanged.
* **State machine untouched.** `WorkflowState`, `ALLOWED_TRANSITIONS`, `TERMINAL_STATES`, and every
  transition rule are byte-identical; `TERMINAL_STATES` is read, never modified. No state-machine
  change was needed, exactly as the stage predicted.
* **One intended output change:** `workflowctl --help` now lists `auto` among its command groups.
  That is the requested feature, not drift; no other command's output changed.

---

## 11. Assumptions

Recorded where evidence was incomplete and the safest read-only, compatibility-preserving reading
was taken.

* **A1 — `status` with no `--workflow-id` reports the repository context.** The stage says "one
  workflow **or** the configured target repository context". Both halves are always present in the
  result *shape* (`workflow` is `null` when absent), so a JSON consumer never has to branch on
  which keys exist.
* **A2 — Repository CLI conventions beat `CLI_SPEC.md` §3-4 where they differ.** `--output
  human|json` (not `text|json`) and exit codes 0/1/2 (not 0/1/2/3). CLI_SPEC governs the
  not-yet-built `agentos workflow` namespace; this is `workflowctl`, and the stage instruction to
  "use the repository's existing CLI patterns" is explicit. `--target-repo`/`--config` keep
  CLI_SPEC's names, since they denote AgentOS concepts the engine CLI has none of. CLI_SPEC §8
  already states that adding a read-only command such as `list` is additive.
* **A3 — `audit` returns the two record types `AUDIT_MODEL.md` §2-3 defines.** The Skill-level
  `audit.jsonl` event log written by `append_audit_event` is *not* included: its events are
  free-form dicts, and including them would have weakened the "typed results" requirement. Recorded
  as deferred defect D4.
* **A4 — Two new error types were added.** "Return existing typed errors" is honoured for every
  case where an existing error expresses the condition (config, corruption, confinement, unsafe
  id — all pass through unchanged). No existing error means "this read-only lookup found nothing",
  so `WorkflowNotFoundError` and `ReportNotFoundError` were added rather than misusing a
  `ResumeError` subclass, which would have implied a resume attempt that never happened.
* **A5 — A symlinked entry fails the whole `list()`.** Skipping it would present a short list as a
  complete one. A name that is not a legal `workflow_id` is skipped instead (it was never writable
  through this API, so it is not a workflow this store owns).
* **A6 — Report filename parsing prefers the sequenced reading.** `qa.3.json` is read as kind `qa`,
  sequence 3. `<kind>` may legally contain `.`, so this is ambiguous in general — but the sequence
  is a validated integer in `1..9999`, so this module has never written a kind ending in
  `.<digits>`, and the sequenced reading is the only one it can actually produce.
* **A7 — No example configuration file was added.** The instruction permits one "only when required
  to validate the read-only surface". It was not required: both test suites build a valid
  `WorkflowConfig` in-process, following `test_config.py`'s existing pattern. Adding a file would
  have been speculative.
* **A8 — `handover/**` was not updated.** `STAGE_REGISTRY.md` §3 rule 1 explicitly excludes it from
  the sanctioned authorization edit set. It is maintained on its own cadence and belongs to
  closeout, not to this stage.

---

## 12. Discovered blockers fixed

**None.** No defect blocked AUTO-009, so the narrow exception clause was never invoked. Every
change in §5 is new capability or its registration; nothing existing was repaired, deleted, or
deprecated.

---

## 13. Discovered non-blocking defects, deferred

All found while reading the code AUTO-009 builds on. **None was fixed**; each is deferred to a
future governed stage.

### D1 — `STAGE_REGISTRY.md` §1 and its Purpose field still say "AUTO-001..007" — `OPTIONAL`

The document's Purpose field and §1's scope sentence both stop at AUTO-007, though AUTO-008 has
been `COMPLETE` since 2026-07-30 and AUTO-009 is now registered. **Impact:** documentation
accuracy only; the governing rules in §2-3 are written generically and apply unchanged, and
`check-registries` reads §4's table, not the prose. Fixing it in this stage would have been an
unrelated documentation edit. **Defer to:** the next governance-maintenance task touching that
registry.

### D2 — `STAGE_REGISTRY.md` §6's decision-reference line is self-admittedly stale — `OPTIONAL`

The line says "DD-01 through DD-39" while itself noting that it "has historically lagged DD
additions". **Impact:** a reader chasing decision records may miss recent ones; no machine check
consumes this line. **Defer to:** the same governance-maintenance task as D1.

### D3 — `cli_auto` must restate `OutputFormat` and reach the engine CLI's helpers through deferred
imports — `RECOMMENDED`

`ai_workflow_engine.cli` holds `OutputFormat`, `_protected`, `_write_stdout`, and
`_contract_v2_success` as module-private members of a 1,166-line module that also imports the
sub-app. That forces `cli_auto` to mirror the enum (Typer needs it at decoration time) and to
import the helpers inside function bodies. **Impact:** the mirror is pinned by a test and the
deferred imports are correct and tested in both orders, so nothing is wrong today — but a future
sub-app will face the identical constraint, and a third copy of the enum would be the point at
which drift becomes likely. **Correct fix:** extract the shared CLI-contract helpers into a small
importable module. That is a refactor of the existing CLI, which this stage is explicitly forbidden
to perform. **Defer to:** a dedicated CLI-boundary refactor stage, ideally before a second AgentOS
sub-app is added.

### D4 — The Skill-level `audit.jsonl` event log has no reader — `FUTURE`

`skills.reporting.append_audit_event` writes `<audit_root>/<workflow_id>/audit.jsonl`, and nothing
reads it back. `workflowctl auto audit` therefore reports the two schemas `AUDIT_MODEL.md` §2-3
defines but not this Skill-level log. **Impact:** none today — no production code path currently
writes `audit.jsonl` outside tests, and §2-3 is what `AUDIT_MODEL.md` makes binding. It becomes a
real completeness gap once the Orchestrator starts emitting Skill events during live runs.
**Blocked on:** a decision about whether those events get a schema (which would make them typeable)
or stay free-form. **Defer to:** the stage that first wires Skill-event emission into a live run.

### D5 — `agentos_workflow/tests/` ships inside the wheel — `RECOMMENDED`

`[tool.hatch.build.targets.wheel] packages` names the whole `agentos_workflow` tree, so the
distributed wheel contains ~2,000 tests, including AUTO-009's new `test_service.py`. **Impact:**
distribution size and a slightly confusing installed layout; no correctness or security
consequence — the tests import nothing they should not and run nothing on import. Pre-existing
since AUTO-008; AUTO-009 adds to it only by adding tests. **Defer to:** a packaging-hygiene task
(a `[tool.hatch.build.targets.wheel.exclude]` entry).

### D6 — `agentos_workflow/config/__init__.py` is empty while `orchestrator/__init__.py` curates a
deliberate `__all__` — `OPTIONAL`

The two sibling subpackages take opposite approaches to their public surface. **Impact:** callers
must import from `config.loader` / `config.schema` directly, which `service.py` does. Purely a
consistency observation. **Defer to:** any future stage that revisits the package's public surface.

---

## 14. Confirmation that no successor behaviour was implemented

Verified by reading the diff and by the structural tests in §8. **None** of the following exists
anywhere in the change set:

workflow start · workflow authorization · workflow approval · workflow rejection · workflow
resume · workflow cancellation · Preparation Mode · Reviewer Mode · Implementer Mode · Claude
execution · Codex execution · result-contract redesign · configurable approval · timeout
behaviour · daemon · Telegram · Git commit · Git push · GitHub PR · CI polling · merge · branch
deletion · Python governance closeout · shell-script retirement · AUTO-010 or any successor.

Additionally: no subprocess is spawned; no interactive prompt exists; no write lock is acquired;
no workflow state transition is recorded; no report is generated; no existing code was deleted or
deprecated; and no unrelated defect was fixed.

---

## 15. Commit and publication plan

**Nothing has been committed. Nothing has been pushed. No PR exists. No merge has occurred.**
The working tree holds the complete AUTO-009 change set and nothing else.

Proposed sequence, **each step requiring explicit Human Owner authorization**:

1. **Review** this report and the working-tree diff.
2. **Implementation commit** on `feature/auto-009-workflow-service` (governance registration and
   implementation may be one commit or two, at the Human Owner's preference — the GOV-AUTO-06/07
   precedent used two: `docs(governance): register and authorize AUTO-009` followed by
   `feat(workflow): add the WorkflowService boundary and read-only workflowctl auto surface
   (AUTO-009)`).
3. **Closeout** — registry §4 `IN_PROGRESS → COMPLETE`, a §5 closure row, task `Current → Done`,
   and the mirrors; via `scripts/workflow-approve.sh` if the Human Owner prefers the GOV-AUTO-03
   automatic path.
4. **Publication** — push the branch, open a PR, wait for CI, merge into `main`, push `main`.
   `check-git`'s `upstream_missing` finding resolves at the push.
5. **Post-merge** — re-run `workflowctl verify --config self-governance.yaml` and confirm all five
   checks PASS.

Per `STAGE_REGISTRY.md` §3 rule 16, this closure would authorize **no successor**: AUTO-010 and
every later roadmap phase remain unauthorized, and none of D1–D6 above is authorized to be fixed.

---

## Addendum — Human Owner approval, closure, and publication (2026-07-31)

**Append-only (`STAGE_REGISTRY.md` §3 rule 8).** Everything above this line was written before any
commit existed and is accurate as of that moment; it is **not** rewritten. This addendum records
what happened afterwards, following the AUTO-004, AUTO-005, and AUTO-006 precedent.

### Approval

The Human Owner approved AUTO-009 for finalization and required a final twelve-point scope, API,
and read-only integrity verification before any commit. **All twelve passed.** Beyond what §7 above
already reported, the verification added:

* **Every mutation channel booby-trapped simultaneously**, not just the lock:
  `RepositoryLock.acquire` / `__enter__` / `release`, `subprocess.run` / `Popen`, `os.system` /
  `os.fork` / `os.posix_spawn`, `StateStore.record_transition` / `record_command_execution`, and
  all six `skills.reporting` writers. None was reached by any of the six operation invocations.
* **A stronger read-only digest** than §7's: path + mode + **mtime_ns** + size + bytes, over the
  state directory, the audit directory, *and* the target repository. Identical before and after
  each of the six operations.
* **`read_reports` byte-, mtime-, mode-, and inode-identity preservation** on the artifact it
  reads, plus an unchanged digest over the whole audit tree.
* **Baseline byte-comparison.** Fourteen existing command invocations were run in a git worktree
  at `98acc195` and against the current tree: `version`, `inspect --help`, `verify --help`,
  `check-git --help`, `commit --help`, `push --help`, `apply-patch --help`, `prompt --help`,
  `state --help`, `agent --help`, `migrate --help`, `state show --help`, `migrate inspect --help`
  — **all thirteen byte-identical**. The fourteenth, `workflowctl --help`, differs by exactly the
  three lines introducing the `auto` group, and by nothing else.
* **A3 confirmed as documented:** `AuditResult` carries only `list[StateTransitionRecord]` and
  `list[CommandExecutionRecord]`; `append_audit_event` and `audit.jsonl` appear nowhere in the
  service; no field on any of the eight result models is `Any` or `object` (the one
  `dict[str, Any]` is `ReportArtifactView.content`, the report artifact's own JSON payload).
* **A4 confirmed as documented:** both new errors' MROs are
  `… -> WorkflowServiceError -> Exception`; neither inherits `ResumeError`, `StateStoreError`, or
  `ConfigurationError`. Their CLI mapping was compared side by side against a pre-existing
  operational error (`verify` with a bad config) and is identical: exit **2**, empty stdout,
  `ERROR: ` on stderr under contract v1; exit **1**, empty stderr, one envelope with
  `ok=false`/`retryable=false` and `code` equal to the exception type name under v2.
* **Deferred defects confirmed untouched:** `pyproject.toml` unmodified (D5),
  `agentos_workflow/config/__init__.py` unmodified (D6), the `STAGE_REGISTRY.md` Purpose line and
  §6 decision-reference line unmodified (D1, D2), no `audit.jsonl` reader added (D4). The only
  `STAGE_REGISTRY.md` changes are the version bump, the §4 row, and the §5 log rows.
* **Hygiene:** no `TODO`, `FIXME`, `XXX`, `HACK`, `WORKAROUND`, `breakpoint`, `pdb.set_trace`,
  stray `print(`, commented-out implementation, skipped test, or `xfail` anywhere in the added or
  modified code; 3,151 collected, 3,151 run.
* **No successor reference:** no `AUTO-01[0-9]` token appears in any code file in the change set.

### One incident, corrected before it entered a commit

A `git worktree add` used for the baseline byte-comparison was run once with a relative path and
created `baseline_wt/` **inside the repository**, where `git status` showed it as untracked. It was
detected during the pre-commit scope check, removed with `git worktree remove --force`, and
`git worktree prune` run; `git status --porcelain` returned to exactly the expected 18 entries
before anything was staged. No commit ever contained it. It is recorded here because a stray
artifact caught only by the scope check is worth stating plainly rather than omitting.

### Commits

Two commits, following the GOV-AUTO-06 / GOV-AUTO-07 precedent, so that the authorization record
exists as a commit containing no implementation:

1. **`fca4628` — `docs(governance): register and authorize AUTO-009`.** The eight governance
   documents only. Registry `NOT_STARTED → AUTHORIZED → IN_PROGRESS`; task `Planned → Current`.
2. **The implementation and closeout commit** — `feat(workflow): add the WorkflowService boundary
   and read-only workflowctl auto surface (AUTO-009)`. Carries the implementation, its tests, this
   report including this addendum, and the governance closeout (registry `IN_PROGRESS → COMPLETE`,
   task `Current → Done`, mirrors, changelogs, decision log, handover, checksum). **This addendum
   is written before that commit exists, so it names no hash for it** — the same rule-8-compliant
   pattern AUTO-005's report used. The hash was reported to the Human Owner on completion.

### Publication

The Human Owner authorized pushing `feature/auto-009-workflow-service` and **nothing further**: no
PR, no merge, no successor stage. The `upstream_missing` finding recorded in §9 clears at that
push, after which all five `workflowctl verify` checks PASS.

### Unchanged by this closure

The six non-blocking defects D1–D6 remain deferred and explicitly unauthorized to fix. AUTO-010 and
every later roadmap phase remain unauthorized. `MVP_SCOPE.md` §4's second acceptance demonstration —
a real target-repository run — remains unmet, and this stage deliberately did not move toward it.
