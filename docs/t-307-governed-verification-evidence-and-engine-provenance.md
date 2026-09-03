# T-307 Task Contract — Target-Bound Governed Verification Evidence and Engine Execution Provenance

Status: PLANNED — REGISTERED FOR HUMAN OWNER AUTHORIZATION; NOT AUTHORIZED, NOT STARTED, NOT
IMPLEMENTED

Registered: 2026-09-02
Registration baseline: `main` at `f632ebe458f21a1ccccb988b57c103237be4774e`, clean worktree,
`workflowctl verify --config self-governance.yaml` = PASS, 0 Current tasks.

**Revision 2 — amended 2026-09-02.** Revision 1 (committed as
`a9a769f152a7cf6f66882645a7b0faa5d091154f`) left OD-1 and OD-2 open. Both are now resolved by
Human Owner decision and recorded in section 12; OD-1's ruling is **stricter** than Revision 1's
frozen text and supersedes it, changing §4.3, §5.6, and acceptance criteria 7 and 10. Every other
requirement, the frozen scope, and the forbidden surface are unchanged. No implementation has
occurred.

**Revision 3 — amended 2026-09-03 (bounded scope amendment; one test path).** The Human Owner
explicitly approved adding exactly one path to the frozen §7.2 test allowlist:
`tests/test_prompt_store.py`. Rationale: schema-version test coupling only — this contract's frozen
design bumps the prompt payload/metadata schema `1.1` → `1.2`, and that file carries
current-schema `"1.1"` literals that are coupled directly to the bump (a `PromptSuccess(schema_version="1.1", …)`
construction, a duplicate-key literal, and a legacy-sidecar test that rewrites the current schema
to the previous one). **No production path was added and no production scope expanded**;
`src/ai_workflow_engine/prompt/store.py` itself pins no schema version and stays excluded by §7.4.
The objective, OD-1, OD-2, §7.1, every other §7.2 entry, §7.3, §7.5, and §8 in its entirety are
unchanged — §8 is byte-identical to the pre-amendment contract. T-307 remains `Current`; **implementation has not started** under the
amended scope, and `tests/test_prompt_store.py` is itself untouched by this amendment. Recorded in
`docs/DECISION_LOG.md`, 2026-09-03 entry.

**Lifecycle note (supersedes the two paragraphs below).** The `Status:` line at the top of this
document and the "preparation artifact" paragraph that follows record this contract's
*registration-time* state. Both were superseded on 2026-09-03, when the Human Owner authorized
T-307 through `scripts/workflow-authorize.sh T-307` (authorization commit
`f624bd605b24304a88d43f314f5e2a8723e9c54b`) and the task moved `Planned → Current`. The canonical,
parseable status for T-307 is the `Status:` line in `docs/TASK_QUEUE.md`, not this document.

This contract is a *preparation* artifact. It authorizes nothing. No source, test, script, or
packaging path may change until the Human Owner authorizes T-307 through
`scripts/workflow-authorize.sh T-307` and a fresh planning session is opened under section 11.

## 1. Ownership and task-ID derivation

The repository has no task-ID allocator and no reserved-ID queue. `docs/MASTER_ROADMAP.md` line 10
defines the ordinary engine namespace as `T-<milestone><nn>`, and
`src/ai_workflow_engine/governance/parser.py` accepts any `[A-Za-z]+-\d+` identifier, so the
namespace — not the parser — is the binding constraint. T-405's own registration records the
selection rule this task follows: pick the next unused contiguous ID *in the milestone that owns
the capability being extended*.

The capability being extended here is Milestone 3 — "non-interactive agent execution". T-304
delivered the disposable sandbox clone, the scrubbed-environment subprocess executor, and the
`verification_argv` observation path; T-305 delivered independent claim verification and the
agent-run artifact. T-307 makes that executor reachable as target-bound evidence independent of a
configured agent, and binds engine provenance into both the Milestone 2 prompt payload and the
Milestone 3 run artifact. Milestone 2's prompt pipeline is the *transport* for that evidence, not
its owner; Milestone 4 (controlled commit and push) is untouched.

`T-301` through `T-306` exist contiguously and `T-307` occurs nowhere in `docs/`, `handover/`,
`src/`, `tests/`, `scripts/`, `agentos_workflow/`, or `agentos_dashboard/`. **T-307 is therefore
the next unused canonical ID in the owning task family.** `T-406` was rejected: Milestone 4 owns
controlled commit and push, and this task changes neither.

No completed task is reopened or rewritten. T-303, T-304, T-305, and the Milestone 2 prompt
contract remain `Done`; T-307 extends them additively.

## 2. Objective

> Restore target-bound governed review evidence and execution provenance in `ai-workflow-engine`
> so a reviewer can receive engine-executed verification evidence for the exact target HEAD while
> remaining filesystem read-only, with the exact engine version/HEAD/install provenance recorded
> and fail-closed.

This is a general engine capability. No consumer repository is named, special-cased, or
hardcoded anywhere in the delivered surface.

## 3. Verified problem statement

Each defect below was reproduced against the registration baseline and is stated with its
file/line evidence. They are separate defects and must be separately closed.

### C1 — Task-specific verification evidence cannot reach a governed prompt

- `src/ai_workflow_engine/prompt/templates.py:63` defines `_VERIFICATION_STANDARD` as three
  hardcoded literal commands (`git status --short --branch`, `git diff --check`,
  `pytest -p no:cacheprovider`), substituted into six of the seven stage templates. The `push`
  stage carries its own equally hardcoded list at line 239.
- `PromptContext` (`src/ai_workflow_engine/prompt/models.py:334`) has no field through which a
  caller could supply a task-specific verification bundle, and
  `ALLOWED_PLACEHOLDER_NAMES` (`src/ai_workflow_engine/prompt/renderer.py:22`) is a closed set
  with no verification-evidence member. There is no injection surface at any layer.
- Consequently a rendered reviewer prompt displays the engine's own generic commands and never
  the target task's actual required verification bundle.
- `src/ai_workflow_engine/agents/runner.py:303` (`_run_verification_commands`) is the only code
  path that executes verification, it re-derives the same three hardcoded commands from
  `verification_argv()` (line 81), and it is reachable **only** from `run_agent()`. This
  repository's `self-governance.yaml` declares `agents: []`, so today there is no execution path
  at all that produces engine-observed verification evidence.
- Reviewer self-execution is not a substitute: an agent's account of a command it says it ran is
  self-report, which `docs/AGENT_PROTOCOL.md` ("What no agent may do") already forbids treating
  as evidence.

**Required capability.** Configurable named verification bundles; explicit bundle selection at
prompt-render time; engine execution of the selected commands against a disposable clone of the
exact target HEAD; capture of exact argv and observed exit codes; those observations rendered as
target-bound prompt evidence. The evidence is an engine observation and is never sourced from,
influenced by, or reconciled against an agent's own report.

### C2 — The reviewer needs verification evidence but must remain filesystem read-only

`AgentSettings.mode` (`src/ai_workflow_engine/models.py:107`) admits only `read-only` and
`scoped-write`, and `_READ_ONLY_STAGES` (line 95) binds every review stage to `read-only`. That
constraint is correct and is **preserved unchanged**. The fix is not to give reviewers write
access so they can run verification themselves; it is to move execution to the engine's own
trusted disposable clone (`create_sandbox`, `src/ai_workflow_engine/agents/sandbox.py:83`),
which already clones the target at an exact recorded HEAD and is never the target worktree. The
reviewer judges engine-observed evidence and writes nothing.

### C3 — Engine provenance is not bound into prompts or runs

`PromptMetadata` (`src/ai_workflow_engine/prompt/models.py:361`) records `repository_head`,
`template_version`, and `template_sha256`, but nothing about the engine that produced the prompt.
`AgentRunRecord` (`src/ai_workflow_engine/agents/artifacts.py:58`) likewise records the agent and
the target head but not the engine. Missing: engine HEAD, engine version, engine worktree
cleanliness, install mode, and the resolved package/source path.

This matters specifically because the engine is installed **editable**: both observed
environments load `ai_workflow_engine` from
`/home/afshin-jian/ai-workflow-engine/src/ai_workflow_engine/__init__.py` via
`_editable_impl_ai_workflow_engine.pth`, so the code that executes a governed prompt is the
working tree at that moment, not a frozen release. A governed prompt or run must identify exactly
which engine code produced and executed it.

### C4 — Version and install drift (disposition)

Observed at the registration baseline:

| Environment | `ai_workflow_engine.__version__` | distribution metadata | `workflowctl` |
|---|---|---|---|
| `ai-workflow-engine` (py3.11) | `1.0.0` | `1.0.0` | works, prints `1.0.0` |
| `base` (py3.13) | `1.0.0` (editable, same source tree) | `0.1.0` | **broken**: `ModuleNotFoundError: No module named 'agentos_workflow'` |

`pyproject.toml:7` declares `1.0.0`; `src/ai_workflow_engine/__init__.py:3` declares `1.0.0`.

**In scope for T-307:** exactly one thing — a deterministic, fail-closed reconciliation of the
*running* engine's version. The canonical source is the executing module constant
`ai_workflow_engine.__version__`, following the reasoning already committed in
`agentos_workflow/__about__.py` (a module constant is identical whether the package is installed,
editable, or imported from source, so provenance cannot vary with load mechanism). Installed
distribution metadata is *observed for cross-checking only*. When both are resolvable and
disagree, governed prompt rendering and governed agent execution **fail closed** with a
deterministic compatibility error naming both values. Neither value is silently preferred. When
distribution metadata is unresolvable, install mode is `source` and no mismatch error is raised.

Under this rule the working `ai-workflow-engine` environment is unaffected and the broken `base`
environment fails closed with a precise error rather than producing an unattributable prompt.
That is the intended behaviour, not a defect to be papered over by repairing the environment.

**Explicitly out of scope, recorded as separable follow-up:** repairing or reinstalling the
`base`-environment distribution metadata; fixing `base`'s broken `workflowctl` entry point;
removing or consolidating editable installs; and any environment cleanup. None of it is required
by the objective, and absorbing it would convert a bounded engine task into environment
administration.

**Not reproduced.** The reported stray `lib/python3.1/site-packages` directory does **not exist**
at this baseline: `find /home/afshin-jian -maxdepth 6 -type d -path "*lib/python3.1/site-packages*"`
and a `-name python3.1` directory search both return nothing, and the engine repository has no
`lib/` directory. No remediation is contracted for a condition that could not be observed. If it
reappears it is environment cleanup, i.e. the same out-of-scope class above.

## 4. Architecture invariants

These are binding. A plan or implementation that violates any of them is rejected regardless of
test results.

### 4.1 Reviewer immutability

Review-stage agents remain `read-only`. No configuration key, CLI option, bundle definition, or
default introduced by this task may set, imply, widen, or be composable into `workspace-write`
for a review stage. `_READ_ONLY_STAGES`/`_SCOPED_WRITE_STAGES` and the `AgentSettings` mode
validator are unchanged. A test must prove no new configuration path can promote a reviewer.

### 4.2 Target HEAD binding

For every selected verification bundle, in this order:

1. the engine resolves the exact target repository HEAD from the target worktree;
2. the target worktree must be clean — modified, staged, and untracked sets all empty — or the
   command fails closed before any execution;
3. the engine clones exactly that HEAD into a disposable sandbox
   (`agents.sandbox.create_sandbox`, detached checkout of the recorded OID);
4. every bundle command executes inside that clone and nowhere else;
5. the engine records the exact argv and the observed exit code for each command;
6. the rendered prompt payload binds the evidence to that target HEAD, and the evidence's
   `target_head` must equal `PromptMetadata.repository_head` or rendering fails closed;
7. the reviewer is subsequently run against that same immutable target HEAD.

No target-repository commit may occur between verification execution and reviewer execution. The
existing `run_agent` HEAD-drift gate (`agents/runner.py:198`, `HeadDrift`) already enforces the
consuming half of this and is preserved unchanged. The target repository is never written.

### 4.3 Engine HEAD binding

Prompt payload, stored prompt metadata, and the agent-run artifact each record:

- `engine_version` — the canonical running version (§3 C4);
- `engine_head` — the engine repository HEAD at execution time;
- `engine_worktree_clean` — boolean;
- `engine_install_mode` — `editable` | `installed` | `source`;
- `engine_package_path` — the resolved package directory actually imported.

Provenance is resolved from the imported package's own location, never from
`config.project.repository` (which names the *target*, and only incidentally coincides with the
engine under self-governance).

**Fail-closed rule — Human Owner decision OD-1, 2026-09-02, binding.** If the resolved engine
installation is `editable` and its resolved engine source worktree is dirty, every governed
prompt/review/provenance execution covered by T-307 fails closed, **whether or not a verification
bundle is selected**. Governed review evidence must never be produced using uncommitted engine
code. The complete ruling:

| Engine installation | Engine worktree | Result |
|---|---|---|
| `editable` | clean | permitted; provenance recorded |
| `editable` | dirty | **refused** — deterministic `EngineProvenanceError` |
| `installed` (non-editable distribution) | n/a | permitted only if §4.4 version/provenance validation succeeds |
| `source` (no distribution metadata) | n/a | treated as non-editable for this rule; §4.4 still applies |

**Bounded, deliberately.** The refusal governs only the T-307 governed prompt/review/provenance
surface. It is **not** a general prohibition on ordinary development commands: `workflowctl
inspect`, `check-git`, `check-task-state`, `check-governance`, `check-registries`,
`check-handover`, `verify`, `state`, `commit`, `push`, `apply-patch`, `migrate`, `auto`,
`milestone-runner`, and `version` are unaffected, and `pytest`/`ruff`/`black`/`mypy` are untouched.
A test must pin that boundary in both directions.

**Scope note.** This rule constrains the **engine** worktree, which is a different worktree from
the target repository constrained by §4.2. They coincide only under self-governance. Verified at
amendment time: no script under `scripts/` invokes `workflowctl prompt` — this repository drives
its own lifecycle from the static `scripts/prompts/implement-next-task.md` — so the strict rule
creates no conflict with the engine's own governed workflow, and `workflow-authorize.sh` already
requires a clean tree.

**Required test seam (derived consequence).** Because provenance is resolved from the *imported
package's* location, an un-seamed implementation would make the entire prompt test suite fail
closed whenever the engine checkout is dirty — i.e. during all normal development. Tests must
therefore substitute the resolver by monkeypatching it at module scope, exactly as
`tests/test_agent_runner.py` already does with `verification_argv`. **No production injection
parameter, CLI option, configuration key, or environment-variable bypass may exist**, and a test
must assert that the CLI exposes no option reaching the resolver.

### 4.4 Version reconciliation

As frozen in §3 C4: canonical = executing module constant; distribution metadata cross-checked;
resolvable disagreement is a deterministic fail-closed compatibility error naming both values;
neither is silently chosen. This check runs on every governed prompt render and every governed
agent run, independent of bundle selection.

### 4.5 Template compatibility

- The `## Identity` block (`prompt/templates.py:16-22`) is preserved **byte-for-byte**. No new
  line is added to it, and no line anywhere else in any template may take the
  `- <Label>: <scalar>` shape that consumers use to parse it.
- The template version moves `1.0.0` → `1.1.0` explicitly, for all seven stages, with all seven
  golden byte counts and SHA-256 digests in `tests/test_prompt_templates.py` updated in the same
  change.
- `ALLOWED_PLACEHOLDER_NAMES`, `EXPECTED_PLACEHOLDER_COUNTS`, `REQUIRED_HEADINGS`, the validator's
  fragment/list span tables, and the templates move in lockstep: adding the placeholder without
  the validator entry, or vice versa, must fail the suite.
- `validator.REQUIRED_HEADINGS` and `_FRAGMENT_SPAN_HEADINGS["VERIFICATION"]`'s terminator change
  together with the new section's position.

## 5. Frozen design

The planning session may refine wording and internal helper structure. Any change to the
following normative shapes requires a recorded contract amendment and re-authorization.

### 5.1 Configuration

A new optional top-level `verification` section on `EngineConfig`, modelled on the existing
`agents` section (a list of named, strictly-validated entries) rather than a bare mapping, so it
matches current `EngineConfig` conventions:

```yaml
verification:
  bundles:
    - name: Q
      commands:
        - ["conda", "run", "-n", "<env>", "python", "-m", "pytest", "-q"]
        - ["conda", "run", "-n", "<env>", "git", "diff", "--check"]
      timeout_seconds: 3600
```

- `VerificationBundleSettings.name`: `[A-Za-z][A-Za-z0-9._-]{0,63}` (the `AgentSettings` name
  shape).
- `commands`: `list[list[str]]`, at least one argv; each argv at least one token; every token
  non-empty and free of NUL, newline, and surrogate code points.
- `timeout_seconds`: `int`, `ge=1`, `le=86400`, default `3600` (the current
  `_VERIFICATION_TIMEOUT`).
- `VerificationSettings.bundles`: default empty; names unique.
- `EngineConfig.verification`: `Field(default_factory=VerificationSettings)` — absent section
  means no bundles, which is exactly today's behaviour.

`src/ai_workflow_engine/config.py` requires no change: `load_config` validates through Pydantic
and the new section names no repository paths.

### 5.2 CLI

`--verification-bundle NAME`, repeatable, on every `workflowctl prompt <stage>` subcommand —
the established repeatable-singular convention of `--allowed-path` and `--finding`. Selection
order is the execution order. An unknown name, or the same name selected twice, is a
deterministic error before any execution.

### 5.3 Engine execution

A new module `src/ai_workflow_engine/verification_bundles.py` executes selected bundles. It
imports `agents.sandbox` (which imports only `exceptions`, so no cycle is created) and owns no
prompt-model dependency.

- `shell=False`, argv lists only, `cwd` = the sandbox clone.
- Environment: the same scrubbed key set the runner already uses (§6).
- Per-command timeout from the bundle, enforced with the existing process-group kill discipline.
- Exit-code mapping identical to `_run_verification_commands`: `124` on timeout, `127` on `OSError`,
  otherwise the observed return code (`1` if `None`).
- Captured per command: `bundle`, `index` (global 0-based execution order), `argv` (exact),
  `exit_code`, `timed_out`.
- **stdout/stderr bytes are not captured into prompt evidence.** Exit codes and argv are the
  contracted observation; command output may carry secrets and is not needed for the judgement.
- The sandbox is torn down unconditionally.
- Non-zero exit codes are *evidence*, not an engine error: rendering succeeds and the reviewer
  judges them. Only the §4.2/§4.3/§4.4 preconditions fail closed.

### 5.4 Prompt payload and evidence schema

`PromptContext.schema_version` and `PromptMetadata`/`PromptSuccess` move `"1.1"` → `"1.2"`,
following T-303's `1.0` → `1.1` precedent (the prior version is rejected, not tolerated).

```
CanonicalVerificationCommandObservation: bundle: str; index: int; argv: list[str];
                                         exit_code: int; timed_out: bool
CanonicalVerificationEvidence:           target_head: str; bundles: list[str];
                                         observations: list[CanonicalVerificationCommandObservation]
CanonicalEngineProvenance:               engine_version: str; engine_head: str;
                                         engine_worktree_clean: bool;
                                         engine_install_mode: Literal["editable","installed","source"];
                                         engine_package_path: str
```

- `PromptContext` gains `engine_provenance: CanonicalEngineProvenance` (always present) and
  `verification_evidence: CanonicalVerificationEvidence | None` (`None` when no bundle selected).
- `PromptMetadata` gains the same two fields, mirrored from the payload.
- Invariants enforced at model level: `bundles` non-empty and unique when evidence is present;
  `observations` non-empty; every `observation.bundle` ∈ `bundles`; `index` values are exactly
  `0..n-1` in order; `target_head` equals `PromptMetadata.repository_head`.

### 5.5 Rendered section

`_COMMON_LITERAL` gains, immediately after the `## Verification commands` fragment and before
`## Stop condition`:

```
## Verification evidence
{{VERIFICATION_EVIDENCE_JSON}}
```

`VERIFICATION_EVIDENCE_JSON` renders one fenced JSON block (the existing `_json_block` helper)
containing exactly two keys: `engine_provenance` and `verification_evidence` (the latter `null`
when no bundle was selected). A fenced JSON block is chosen deliberately: it cannot introduce a
`- <Label>: <value>` line and therefore cannot be mistaken for `## Identity` content by any
consumer.

The existing `## Verification commands` section is unchanged in content and position, so
`tests/test_agent_runner.py::test_verification_argv_matches_template` — which proves the displayed
commands equal the argv the runner executes — continues to hold verbatim. The new section is
additive evidence, not a replacement for that invariant.

### 5.6 Provenance module

A new module `src/ai_workflow_engine/provenance.py` resolves `CanonicalEngineProvenance` and
raises a single deterministic `EngineProvenanceError` for: unresolvable engine HEAD, an editable
package whose directory is not inside a Git worktree, a resolvable version disagreement (§4.4),
and — per §4.3/OD-1 — an `editable` installation whose engine worktree is dirty, on every governed
prompt/review/provenance execution regardless of bundle selection. It is the only place either
version is read for provenance purposes, and the only symbol tests substitute to obtain
deterministic provenance.

### 5.7 Agent-run artifact

`AgentRunRecord.schema_version` moves `"1.0"` → `"1.1"` and gains `engine_provenance`.
`RunObservation` carries the same value so `build_record` can store it. `run_id` remains the
content hash of the record with `run_id` excluded, so existing tamper-evidence is unchanged.

### 5.8 Migration reader

`src/ai_workflow_engine/migration/legacy_readers.py` pins
`_PROMPT_METADATA_SCHEMA_VERSION = "1.1"` (line 73) and `_AGENT_RUN_SCHEMA_VERSION = "1.0"`
(line 71) and rejects anything else as `UNSUPPORTED_SCHEMA_VERSION` (line 949). Both pins must
move in the same change, or every newly written artifact becomes unreadable by the migration
inspector. This is derived scope, not optional.

## 6. Temporary-directory disposition

Investigated empirically at the baseline. `_SCRUBBED_KEYS = ("PATH", "HOME", "LANG", "LC_ALL")`
(`agents/runner.py:30`) contains no `TMPDIR`. Running `conda run -n ai-workflow-engine git
--version` under exactly that scrubbed environment returns **0** with `TMPDIR` absent, and also
returns 0 with `TMPDIR` set to a nonexistent path.

**Disposition: `TMPDIR` is NOT added to the scrubbed allowlist.** The failure previously observed
in a consumer repository was a property of the *Codex read-only sandbox* having no writable
temporary directory, not of the engine-side executor, which runs on the host where `/tmp` is
writable. Adding an ambient `TMPDIR` passthrough would import exactly the ambient-environment
dependence this contract is trying to remove.

Required instead: a test that pins the **exact** scrubbed key set (equality, not membership) and
a test that a bundle executes successfully with `TMPDIR` absent from the parent environment. If a
future bundle genuinely requires a writable temporary directory beyond `/tmp`, that is a separate
amendment with its own deterministic, non-ambient definition. Reviewer sandboxing is not weakened
in any case.

## 7. Exact frozen scope

Derived from the baseline source, not assumed. Only these paths may be created or modified.

### 7.1 Allowed paths — production

```
src/ai_workflow_engine/models.py
src/ai_workflow_engine/provenance.py                     (new)
src/ai_workflow_engine/verification_bundles.py           (new)
src/ai_workflow_engine/prompt/models.py
src/ai_workflow_engine/prompt/context.py
src/ai_workflow_engine/prompt/templates.py
src/ai_workflow_engine/prompt/renderer.py
src/ai_workflow_engine/prompt/validator.py
src/ai_workflow_engine/agents/runner.py
src/ai_workflow_engine/agents/artifacts.py
src/ai_workflow_engine/migration/legacy_readers.py
src/ai_workflow_engine/cli.py
```

### 7.2 Allowed paths — tests

```
tests/conftest.py
tests/test_config.py
tests/test_prompt_templates.py
tests/test_prompt_renderer.py
tests/test_prompt_validator.py
tests/test_prompt_context.py
tests/test_prompt_store.py                                (added by Revision 3)
tests/test_agent_runner.py
tests/test_agent_artifacts.py
tests/test_migration_readers.py
tests/test_cli.py
tests/test_cli_contract_v2.py
tests/test_verification_bundles.py                       (new)
tests/test_engine_provenance.py                          (new)
```

### 7.3 Allowed paths — documentation and governance

```
docs/t-307-governed-verification-evidence-and-engine-provenance.md
docs/configuration.md
docs/architecture.md
docs/TASK_QUEUE.md
docs/current_task.md
docs/remaining_tasks.md
docs/PROJECT_STATE.md
docs/CHANGELOG.md
docs/DECISION_LOG.md
README.md
handover/PROJECT_HANDOVER.md
handover/PROJECT_CHECKSUM.md
```

### 7.4 Deliberately excluded from the allowlist, with reasons

- `src/ai_workflow_engine/agents/sandbox.py` — `create_sandbox`/`teardown` already provide the
  exact-HEAD disposable clone and need no change. If the planning session proves a change is
  strictly required, that is a **scope amendment**, not a silent addition.
- `src/ai_workflow_engine/agents/verification.py` — judging an agent run is unchanged (criterion 13).
- `src/ai_workflow_engine/prompt/store.py` — `load()` re-renders deterministically from the
  payload; a payload field addition flows through without a storage change.
  This exclusion is **unchanged by Revision 3**: the module pins no schema version and must not be
  modified. Revision 3 added only its test file, `tests/test_prompt_store.py`, to §7.2, because
  that file hardcodes the current schema literal and is coupled to the `1.1` → `1.2` bump.
- `src/ai_workflow_engine/config.py` — Pydantic validates the new section; no loader change.
- `self-governance.yaml` — this repository configures no bundles. Criterion 10 requires the
  no-bundle path to stay behaviour-identical, so its own governance must not change under this
  task. Dogfooding a bundle here is separable follow-up.

### 7.5 Forbidden paths and operations

- Every file in `/home/afshin-jian/dahua-ai-vms`, and any Dahua-specific name, environment,
  command, or default anywhere in this repository.
- Any weakening of Codex/agent sandbox mode; any path that could promote a review agent to
  `workspace-write`.
- Commit and push gates: `src/ai_workflow_engine/commit/**`, `src/ai_workflow_engine/git/**`,
  `apply-patch` semantics, `PushApproval`, and all T-405/first-publication work.
- `agentos_workflow/**`, `agentos_dashboard/**`, and all dashboard functionality.
- `src/ai_workflow_engine/milestone_runner/**`, `src/ai_workflow_engine/successor_planning/**`.
- `scripts/**`, `pyproject.toml`, `environment.yml`-equivalents, and any dependency change.
- Unrelated version cleanup, base-environment repair, stray-directory remediation (§3 C4).
- `docs/t-405-governed-first-push-remediation.md` and every completed task's record.

## 8. Acceptance criteria

Each is an objective, automated test. A criterion without a failing-before/passing-after test is
not closed.

1. Named verification bundle configuration parses and validates; malformed names, empty commands,
   empty argv, non-string tokens, duplicate names, and out-of-range timeouts are each rejected
   with a deterministic error.
2. Selected bundles execute against a clone of the exact target HEAD — proved by a bundle command
   that reads a file whose content differs between the target worktree and the recorded HEAD, and
   by asserting the clone's HEAD equals the recorded OID.
3. Exact argv and observed exit codes are stored as engine evidence, in configured order, with the
   documented timeout/OSError exit-code mapping.
4. The rendered prompt contains target-bound verification evidence under `## Verification evidence`.
5. Prompt metadata includes the target HEAD and all five engine-provenance fields; the evidence's
   `target_head` equals `PromptMetadata.repository_head`.
6. The agent-run artifact includes matching engine provenance, and `run_id` still equals the
   record's content hash.
7. A dirty **editable** engine worktree causes **every** governed prompt/review/provenance
   execution to fail closed with a specific error — proved **both** with a bundle selected and
   with none selected (§4.3/OD-1). `editable` + clean is permitted and records provenance; a
   non-editable distribution is permitted only when §4.4 validation succeeds; `source` behaves as
   non-editable. A further test pins the boundary: the refusal does not extend to the
   non-governed command surface enumerated in §4.3.
8. An engine version mismatch between the module constant and resolvable distribution metadata is
   detected deterministically and fails closed, naming both values; matching versions and absent
   metadata each behave as specified.
9. The reviewer remains read-only: `_READ_ONLY_STAGES` binding is unchanged and no new
   configuration or CLI path yields a `workspace-write` review agent.
10. With no bundle configured **and** none selected **and** the engine passing §4.3/§4.4
    provenance validation, behaviour is backward compatible: the payload's
    `verification_evidence` is `null`, the `## Verification commands` section is byte-identical to
    the baseline, and no bundle execution occurs. Backward compatibility is defined over the
    provenance-valid case only: under OD-1 a dirty editable engine refuses this path too
    (criterion 7). That is a deliberate, Human-Owner-approved behaviour change from the baseline,
    not a regression, and criteria 7 and 10 are internally consistent because they partition on
    provenance validity rather than on bundle selection.
11. `## Identity` is byte-identical across the `1.0.0` → `1.1.0` template change, for all seven
    stages, and the seven golden byte counts and digests are updated explicitly.
12. The prompt validator FAILs on malformed or missing verification evidence when bundles are
    selected: absent section, non-JSON block, evidence not re-serializable from the payload,
    index gaps or reordering, an observation naming an unselected bundle, or a `target_head`
    differing from `repository_head`.
13. Existing runner verification invariants remain intact — in particular
    `tests/test_agent_runner.py::test_verification_argv_matches_template` still passes unmodified
    in substance, and `agents/verification.py`'s judgement behaviour is unchanged.
14. The full quality suite passes: `pytest -q`, `ruff check .`, `black --check .`, `mypy src`, and
    `workflowctl verify --config self-governance.yaml` — all green, with and without `FORCE_COLOR`.

**Cross-repository compatibility proof (criterion 15).** A test asserts that in a rendered prompt
carrying a populated verification-evidence section, no line **outside** the `## Identity` span
matches the identity-line shape `^- (Prompt ID|Stage|Task|Repository|Default branch|Conda
environment): `, and that the `## Identity` span itself still contains exactly its six baseline
lines. This proves the new section cannot confuse a consumer that parses the canonical Identity
block. It is a fixture-based test inside this repository; **no file in `dahua-ai-vms` is read,
written, or referenced to perform it.**

## 9. Validation requirements

The standing roadmap set (§ `docs/MASTER_ROADMAP.md`): `pytest -q`, `ruff check .`,
`black --check .`, `mypy src`, `workflowctl verify --config self-governance.yaml`. Additionally:
both `FORCE_COLOR` modes; `git diff --check` clean; and an explicit statement in the completion
report of the seven new template digests and the two schema-version bumps.

## 10. Explicit exclusions

Restated for the avoidance of doubt: Dahua repository files; sandbox-mode weakening; commit/push
gate changes; apply-patch semantics; dashboard functionality; unrelated version cleanup;
first-push/T-405 work; base-environment cleanup; dependency changes; and any production analyzer,
provider, or model integration.

## 11. Review lifecycle

This repository configures no non-interactive agents (`self-governance.yaml`: `agents: []`), so
independence is achieved through fresh independent sessions, per `docs/AGENT_PROTOCOL.md`
("Review discipline"). **`workflowctl agent run` must not be invented for this repository.**

```
task preparation (this document)
→ Human Owner authorization              (scripts/workflow-authorize.sh T-307)
→ task becomes Current
→ fresh planning session
→ fresh independent plan review          (no memory of the planning session)
→ implementation
→ fresh independent implementation review
→ bounded remediation if required        (repeat review → remediation until APPROVED)
→ governance closeout
→ Done
→ Human-approved commit
```

Every review round after the first uses a reviewer with no memory of prior rounds. Verdicts are
exactly one token: `APPROVED` or `REJECTED`. No workflow event may be recorded for a stage that
was not actually performed, and no review artifact may be narrated without a preserved artifact —
the T-405 ratification (`docs/DECISION_LOG.md`, 2026-09-02) is the standing reason this is stated
explicitly.

## 12. Human Owner decisions — resolved 2026-09-02

Both decisions this contract left open are now settled by the Human Owner and are **binding**. No
open decision remains; nothing here waits on further direction.

### OD-1 — dirty editable engine strictness — RESOLVED (stricter than originally frozen)

For governed review/provenance functionality:

- `editable` engine install + **clean** resolved engine worktree → permitted;
- `editable` engine install + **dirty** resolved engine worktree → **FAIL CLOSED**;
- non-editable installed distribution → permitted only if version/provenance validation succeeds;
- governed review evidence must **never** be produced using uncommitted engine code.

**This rule applies regardless of whether a verification bundle is selected.** It supersedes the
weaker rule this contract originally froze, which limited the refusal to bundle-selecting
execution. §4.3 now carries the authoritative text, §5.6 carries the error, and acceptance
criteria 7 and 10 were rewritten to partition on provenance validity rather than on bundle
selection.

The refusal is bounded to the governed prompt/review/provenance surface T-307 delivers. It must
not be broadened into a prohibition on ordinary development commands; §4.3 enumerates the
unaffected surface and requires a test pinning that boundary. §4.3 also records the derived
consequence — the mandatory module-scope test seam, with no production bypass of any kind.

### OD-2 — verification bundle availability — RESOLVED (confirms the frozen design)

- verification bundles are **optional** configuration;
- only bundles **explicitly configured for that project** may be selected;
- unknown bundle → deterministic fail-closed error **before** any verification execution;
- duplicate selection → deterministic error;
- selection order determines execution order;
- no selected bundle → preserve backward-compatible default verification behaviour (subject to
  §4.3 and §4.4);
- configuration remains **project-generic**; no Dahua-specific bundle names, paths, commands, or
  defaults may be hardcoded anywhere.

**Disposition: confirmatory.** Every clause above is already the design frozen in §5.1, §5.2, and
§5.3, so no architecture is rewritten. The ruling additionally settles this contract's original
"availability by stage" question by a different axis than the one posed: availability is a
function of **configuration**, not of stage. §5.2's uniform exposure across the `workflowctl
prompt` subcommands therefore stands unchanged, bounded by "only explicitly configured bundles may
be selected".

## 13. Dependency on `dahua-ai-vms` (recorded, not acted on)

`DV-029` in `/home/afshin-jian/dahua-ai-vms` is that repository's `Current` task, and its final
governed implementation-review is blocked on the engine capability contracted here: without it, a
read-only reviewer cannot receive engine-executed, target-HEAD-bound verification evidence.

That repository is the **discovering consumer only**. T-307 does not alter DV-029, does not read
or write any Dahua file, and introduces no Dahua-specific behaviour. After T-307 closes, that
repository will — under its own separate governance and its own Human Owner authorization — use
the resulting clean engine HEAD to generate target-bound evidence for its bundles and perform a
fresh governed review. Nothing in this contract authorizes any action in that repository.
