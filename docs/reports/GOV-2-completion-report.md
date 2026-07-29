# GOV-2 Completion Report

## Result

Implemented GOV-2 — "Extend `check-governance` to validate stage-registry/lifecycle
consistency" — as a new deterministic governance check, `check-registries`, that cross-checks
each configured stage registry's per-stage lifecycle `State` against the authoritative
`docs/TASK_QUEUE.md` status under the state→task-status mapping both program registries document
identically. The check is wired into `workflowctl verify` and exposed as a standalone
`workflowctl check-registries` command, and `self-governance.yaml` now names this repository's two
registries. The implementation is complete and validated; it is **uncommitted**, stopped for
Human Owner approval per the standard workflow. Task status remains `Current`.

## Scope decision

GOV-2's task-queue record identifies three candidate consistency properties and, in its
"Recommended shape when authorized" section, gives a concrete design for only the first:

1. **Registry per-stage `State` vs. task-queue status** — the machine-checkable core, and the
   one the recommended shape fully specifies (a `governance/registry.py` module, a documented
   state→task-status mapping table, a new `check-registries` wired into `workflowctl verify`, and
   a config surface naming the registries). **Implemented here.**
2. **Cross-registry shared-control-rule equivalence** (AUTO §1 / DASH §1 claim rules are
   substantively identical). No recommended shape is given; "substantive equivalence" of prose
   rules is not something the task specifies a safe deterministic test for. **Not implemented**
   — recorded as a limitation below; it is a distinct property that would need its own design and
   authorization, not slipped into this pass.
3. **Version-policy (MAJOR/MINOR) classification correctness.** The task itself flags this as
   "the hardest of the three to automate safely and may need to stay a documented, human-reviewed
   judgment call rather than a machine check." **Not implemented**, consistent with that guidance.

This report implements the well-specified core (property 1) and documents 2 and 3 as deliberate,
authorized-scope deferrals rather than silently dropping them.

The task title says "extend `check-governance`", but the task's own recommended shape asks for a
*separate* `check-registries` wired into `verify`. A separate check was chosen: it keeps
`check-governance`'s stable 1.0 JSON contract (`check_name: "governance"`, its evidence shape)
unchanged, and `workflowctl verify` — the authoritative gate — now runs the new check alongside
the existing four, which is what makes the extension effective in practice.

## Delivered

New file `src/ai_workflow_engine/governance/registry.py`:
- `RegistryState` (in `governance/models.py`): the ten lifecycle states both registries' State
  Model sections enumerate (`NOT_STARTED`, `PROPOSED`, `AUTHORIZED`, `IN_PROGRESS`,
  `SELF_REVIEW`, `REVIEW`, `APPROVAL`, `COMPLETE`, `BLOCKED`, `SUPERSEDED`).
- `REGISTRY_STATE_TO_TASK_STATUS`: the single documented mapping (`AUTHORIZED`/`IN_PROGRESS`/
  `SELF_REVIEW`/`REVIEW`/`APPROVAL`/`BLOCKED` → `Current`; `NOT_STARTED`/`PROPOSED` → `Planned`;
  `COMPLETE`/`SUPERSEDED` → `Done`), defined once rather than hard-coded per program because both
  registries state it identically.
- `classify_state`: recognizes a verbatim `State` cell as a `RegistryState`, or `None`.
- `parse_registry`: tolerant Markdown-table parsing confined to the `## N. Registry` section
  (locating columns by their `Stage`/`State` header labels, not fixed indices, and stopping at
  the next heading so the append-only Authorization Log table — which also has a `Stage` column —
  is never misread). Deliberately preserves underscores in state names (the task parser's `_plain`
  strips `_` as emphasis, which would corrupt `IN_PROGRESS`/`NOT_STARTED`).

New models in `src/ai_workflow_engine/governance/models.py`: `RegistryState`, `RegistryRow`
(structural: stage id + verbatim state cell), `RegistryParse`.

New validator `check_registries` in `src/ai_workflow_engine/governance/validators.py`: reads the
authoritative task queue directly (the mirrors are already proven consistent by
`check-task-state`), parses each configured registry, and emits one of four findings per problem:
`registry_table_missing`, `registry_unknown_state`, `registry_stage_missing_from_queue`, or
`registry_state_mismatch`. Empty registry list → PASS with "No stage registries configured".

Config surface: `GovernanceSettings.registries: list[str]` (default empty, like `agents: []`),
validated as repository-relative in `config.load_config`. `self-governance.yaml` gains
`governance.registries` naming `docs/workflow-automation/STAGE_REGISTRY.md` and
`docs/agentos-dashboard/STAGE_REGISTRY.md`.

CLI: new `workflowctl check-registries` command and a `registries` entry added to
`workflowctl verify` (now five checks: git, task-state, governance, registries, handover). The
generic `_emit`/`_safe_check`/`print_check`/contract-JSON machinery required no change.

## Validation

All commands run via `conda run -n ai-workflow-engine`.

- `pytest tests agentos_workflow/tests` → **2680 passed, 1 failed**. The single failure,
  `agentos_workflow/tests/e2e/test_dry_run.py::test_full_workflow_created_to_done_with_one_repair_and_one_interruption`,
  is **pre-existing and unrelated to this change**: it raises `AuthorizationBindingDriftError` on
  `engine_version` because `agentos_workflow/observation/local.py:running_engine_version()`
  resolves `importlib.metadata.version("ai-workflow-engine")` → `1.0.0` (the editable install in
  this environment) while the test hardcodes `engine_version="0.1.0"` (the
  `_DEVELOPMENT_VERSION` fallback used when the package is not installed). Reproduced identically
  on a clean `HEAD` (919fef2) worktree with none of this change present. My diff touches no file
  under `agentos_workflow/` and changes no version string.
- `pytest tests/test_registry.py tests/test_governance.py` → **36 passed** (24 new registry
  tests + the pre-existing governance suite unaffected).
- `ruff check --no-cache .` → **All checks passed!**
- `black --check .` → **156 files would be left unchanged.**
- `mypy --no-incremental src` → **Success: no issues found in 56 source files.**
- `mypy --no-incremental agentos_workflow` → **Success: no issues found in 63 source files.**
- `git diff --check` → clean.
- `workflowctl verify --config self-governance.yaml` → **Verdict: PASS**. The new `registries`
  check PASSes on the live repository: "Checked 17 stage(s) across 2 registry(ies) against the
  task queue" — AUTO-001..007 all `COMPLETE` ↔ `Done`, DASH-001 `COMPLETE` ↔ `Done`, DASH-002..010
  `NOT_STARTED` ↔ `Planned`.

## Tests Added or Updated

New `tests/test_registry.py` (24 tests): `parse_registry` structural extraction (stage/state,
line numbers, Authorization-Log isolation, reordered columns, markup and underscore handling,
missing section, rows without a stage id); `classify_state` and full mapping coverage
(`test_mapping_covers_every_state` guards against a state added without a mapping); and
`check_registries` behavior (no registries → PASS, consistent → PASS, and one test per finding
code, plus multi-registry attribution).

Updated `tests/test_cli.py::test_verify_json_wrapper` and
`tests/test_cli_contract_v2.py::test_v2_envelope_for_verify_command`: `verify` now reports five
checks (was four); both now also assert the exact set of check names.

## Limitations and follow-ups

- **Cross-registry rule-equivalence (property 2)** and **version-policy classification
  (property 3)** are not machine-checked — see "Scope decision". Property 3 is expected by the
  task to remain a human judgment call.
- The check validates registry↔queue **status-class** agreement, not the finer distinctions the
  registries draw within a class (e.g. `COMPLETE` vs. `SUPERSEDED`, both `Done`; the "prose must
  say superseded" rule). Those remain a documented human-review concern, as the task notes.
- `dashboard.db`-style DASH-specific rules and the `Version`/`Future Revisions` policy are out of
  scope for this check.

## Environment note

The `ai-workflow-engine` conda environment did not have the `dev` extra installed at the start of
this session (no `pytest`/`ruff`/`black`/`mypy`). `pip install -e ".[dev]"` was run to install the
declared dev dependencies so the authoritative gates could execute. No project source, dependency
declaration, or lockfile was changed by that install.

## Review and Git

Bounded self-review performed (see the session report). This is an ordinary engine task; it is
not a milestone, release, or trust-boundary change, so no independent review is mandated — a
bounded self-review is the standard here. No commit, push, merge, branch change, or stash
operation was performed; the complete diff is left in the working tree for Human Owner inspection.

## Addendum — Human Owner approval and closure (2026-07-29)

The Human Owner reviewed this report and the implementation diff, typed the two exact `APPROVE`
confirmations required by `scripts/workflow-approve.sh`, and approved the Conventional Commit
message `feat(governance): add check-registries stage-registry/lifecycle consistency check (GOV-2)`. The script then performed the deterministic governance closeout
recorded in `docs/DECISION_LOG.md`'s matching entry and staged the approved implementation
together with the generated closeout records in one local commit. This commit's hash, and any
later publication or merge, are recorded separately — a commit cannot record its own hash.
