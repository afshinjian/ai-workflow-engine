# Milestone 2 Architecture Plan — Governed Prompt Generation

Status: IMPLEMENTED AND APPROVED. Approved after plan review, implemented, and accepted through
three independent fresh implementation reviews (2026-07-16/17; see `docs/DECISION_LOG.md` and
`docs/CHANGELOG.md`). The contracts below are the as-built normative specification and are
retained unchanged as the implementation's reference.

## Goal and hard boundary

Milestone 2 deterministically renders, validates, and optionally stores a self-contained prompt
for a workflow stage explicitly requested by an operator. It reuses Milestone 1's read-only
repository and governance inspection. It does not execute the prompt or decide which stage
comes next.

The following decisions are binding:

1. The CLI exposes exactly the seven prompt commands listed below.
2. Persisted workflow state, verdict recording, transition enforcement, reachability checks,
   and automatic next-stage computation are deferred to Milestone 3. Milestone 2 has no
   `prior_state`, state model, state store, state command, or record-verdict command.
3. `project.conda_environment` is required and rejects an empty or whitespace-only value.
4. Prompt artifacts are stored below the expanded user home directory, never in the target
   repository.
5. Writable allowed paths come only from repeatable CLI options on implementation and
   remediation commands.
6. No clock-derived value is a prompt input or appears in prompt Markdown or metadata.

Milestone 2 must not add agent execution, agent subprocesses, worktrees, writable Git, staging,
committing, pushing, promotion, agent-output parsing, persisted state, verdict behavior,
transitions, or next-stage behavior. `GitClient.READ_ONLY_FORMS` remains byte-for-byte
unchanged. Prompt code may call only existing public read-only Git and validator APIs.

## Package design

The pipeline is configuration loading, read-only inspection, exact template lookup, canonical
context construction, deterministic rendering, validation, and optional external storage.

```text
src/ai_workflow_engine/prompt/
  __init__.py
  models.py       # all strict models and type aliases specified below
  templates.py    # seven-entry versioned built-in registry
  context.py      # normalization and read-only context collection
  renderer.py     # canonical JSON, hashes, and Markdown rendering
  validator.py    # structural CheckResult validation
  store.py        # external addressing, no-clobber publication, and verified load
```

Templates use standard-library string handling or explicit builders. No template-engine
dependency is added.

## Configuration migration

`ProjectSettings` gains exactly this field, with a validator that rejects `value.strip() == ""`:

```python
conda_environment: str = Field(min_length=1)
```

There is no default. The migration updates `models.py`, the example configuration,
configuration documentation, fixtures, and configuration tests listed in the closed file list.

## Commands, options, and textual normalization

The complete command surface is:

```text
workflowctl prompt plan-review
workflowctl prompt implementation
workflowctl prompt implementation-review
workflowctl prompt remediation
workflowctl prompt governance-closeout
workflowctl prompt governance-review
workflowctl prompt push
```

Every command has required `--config <file>` using `ConfigOption`, required `--task-id <id>`,
`--output human|json` using `OutputOption` and defaulting to `human`, and
`--store/--no-store` defaulting to `--store`.

Only `implementation` and `remediation` expose repeatable `--allowed-path`; each requires one
or more occurrences. Only `remediation` exposes repeatable `--finding`; it requires one or more
occurrences. Supplying `--allowed-path` to any other command or `--finding` to any other command
is a CLI usage error and cannot render or store a prompt.

Task IDs and remediation findings use this exact normalization algorithm:

1. Reject a string containing a Unicode surrogate code point (`U+D800` through `U+DFFF`).
2. Apply Unicode NFC normalization.
3. Replace every maximal run of characters for which Python `str.isspace()` is true with one
   ASCII space (`U+0020`).
4. Remove leading and trailing ASCII spaces.
5. Reject the result if it is empty. Do not otherwise change case or punctuation.

The normalized task ID is used everywhere. Findings preserve CLI occurrence order and
duplicates after normalization. Non-remediation stages carry `remediation_findings=[]`.

## Repository-relative allowed paths

Each raw allowed path is processed independently in this order, on every operating system:

1. Reject surrogates, apply NFC, and reject the result if empty or if any character satisfies
   `str.isspace()`. Whitespace is never trimmed from a path.
2. Reject any backslash (`\\`); backslashes are never converted to slashes.
3. Reject a leading `/`, a leading `//`, or any value for which `PureWindowsPath(value).drive`
   or `.root` is non-empty. These checks explicitly reject POSIX-rooted paths, Windows
   drive-qualified paths (`C:/x`), drive-relative paths (`C:x`), Windows rooted paths
   (`\\x`), and UNC/device paths using either slash spelling, even on POSIX.
4. Apply `posixpath.normpath`. Reject `""`, `"."`, `".."`, and a result beginning `"../"`.
   Interior `.` and `..` components are therefore normalized; an allowed path cannot name the
   repository root.
5. Let `root = config.project.repository.expanduser().resolve(strict=True)` and
   `candidate = (root / Path(normalized)).resolve(strict=False)`. Reject unless
   `candidate.is_relative_to(root)`. Because `resolve` follows every existing prefix symlink,
   this also rejects an existing-symlink escape. A nonexistent final component is allowed.
6. Convert `candidate.relative_to(root)` to `PurePosixPath(...).as_posix()` and reapply the root
   and escape rejections as a defensive assertion.

Canonical allowed paths are de-duplicated by exact normalized string and sorted by the Unicode
code-point ordering defined for canonical JSON keys below. That list is used in context,
identity, Markdown, metadata, and validation. Missing or invalid required paths are runtime
errors; no prompt or artifact directory is produced.

## Exact prompt models

Every model added under `prompt/models.py` inherits the existing Pydantic v2
`ai_workflow_engine.models.StrictModel`; no prompt model derives directly from `BaseModel`.
Consequently unknown fields are forbidden. Validators enforce the normalization, literal,
digest, integer, and collection invariants in this plan.

The aliases are:

```python
WorkflowStage = Literal[
    "plan-review", "implementation", "implementation-review", "remediation",
    "governance-closeout", "governance-review", "push",
]
JsonScalar = None | bool | int | str
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
```

`JsonValue` validators reject floats, non-string mapping keys, surrogates, integers outside
`[-9223372036854775808, 9223372036854775807]`, and NFC key collisions. `bool` is handled before
`int` because it is an `int` subclass in Python.

The exact in-memory models and fields are:

```python
class PromptTemplate(StrictModel):
    stage: WorkflowStage
    version: str
    content: str
    sha256: str                 # 64 lowercase hexadecimal characters

class CanonicalGitStatus(StrictModel):
    branch: str
    head: str
    upstream: str | None
    ahead: int | None
    behind: int | None
    modified_files: list[str]
    staged_files: list[str]
    untracked_files: list[str]

class CanonicalTaskRecord(StrictModel):
    task_id: str
    status: Literal["Current", "Done", "Planned"]
    source: str
    line: int

class CanonicalTaskSnapshot(StrictModel):
    by_source: dict[str, list[CanonicalTaskRecord]]
    current: list[str]
    done: list[str]
    planned: list[str]

class CanonicalFinding(StrictModel):
    code: str
    message: str
    severity: str
    path: str | None

class CanonicalCheckResult(StrictModel):
    check_name: Literal["git", "task-state", "governance", "handover"]
    status: Literal["PASS", "FAIL", "ERROR"]
    summary: str
    findings: list[CanonicalFinding]
    evidence: dict[str, JsonValue]
    affected_paths: list[str]
    remediation_hint: str | None

class CanonicalProjectSettings(StrictModel):
    id: str
    repository: str
    default_branch: str
    timezone: str
    require_upstream: bool
    conda_environment: str

class CanonicalFactRule(StrictModel):
    name: str
    paths: list[str]
    pattern: str
    group: int | str
    required: bool

class CanonicalGovernanceSettings(StrictModel):
    project_state: str
    task_queue: str
    current_task: str
    remaining_tasks: str
    context: str
    pyproject: str
    facts: list[CanonicalFactRule]

class CanonicalHandoverSettings(StrictModel):
    manifest: str
    files: list[str]

class CanonicalProtectedPathsSettings(StrictModel):
    never_stage: list[str]
    never_commit: list[str]

class CanonicalWorkflowSettings(StrictModel):
    maximum_current_tasks: int
    require_designer_approval_for_promotion: bool
    allow_automatic_commit: bool
    allow_automatic_push: bool

class CanonicalEngineConfig(StrictModel):
    project: CanonicalProjectSettings
    governance: CanonicalGovernanceSettings
    handover: CanonicalHandoverSettings
    protected_paths: CanonicalProtectedPathsSettings
    workflow: CanonicalWorkflowSettings

class PromptContext(StrictModel):
    schema_version: Literal["1.0"]
    config: CanonicalEngineConfig
    stage: WorkflowStage
    task_id: str
    template: PromptTemplate
    git_status: CanonicalGitStatus
    task_snapshot: CanonicalTaskSnapshot
    protected_path_violations: list[str]
    checks: list[CanonicalCheckResult]
    remediation_findings: list[str]
    allowed_paths: list[str]

class PromptMetadata(StrictModel):
    schema_version: Literal["1.0"]
    prompt_id: str              # exactly 16 lowercase hexadecimal characters
    project_id: str
    task_id: str
    stage: WorkflowStage
    template_version: str
    template_sha256: str
    repository_head: str
    allowed_paths: list[str]
    remediation_findings: list[str]
    payload_sha256: str
    markdown_sha256: str
    payload: PromptContext

class RenderedPrompt(StrictModel):
    context: PromptContext
    canonical_payload_bytes: bytes
    prompt_id: str
    markdown: str
    metadata: PromptMetadata
    metadata_bytes: bytes

class StoredPromptPaths(StrictModel):
    markdown: Path              # resolved absolute artifact path
    metadata: Path              # resolved absolute sidecar path

class PromptSuccess(StrictModel):
    schema_version: Literal["1.0"]
    stored: bool
    prompt_artifact: str | None
    metadata_artifact: str | None
    prompt: str
    metadata: PromptMetadata
```

`PromptMetadata` is closed: these are all and only its fields. Implementers may not add
timestamps, extension dictionaries, invocation data, or optional fields.

## Complete canonical payload and collection ordering

`PromptContext` is the complete canonical payload. No rendering input may exist outside it.
It contains every current `EngineConfig` field; the field enumeration above is exhaustive.
The resolved repository is serialized with `Path.as_posix()`. All other configuration strings
are NFC-normalized without trimming. Configuration arrays are normalized as follows:

- each fact rule's `paths`, `handover.files`, `never_stage`, and `never_commit` are NFC-normalized,
  de-duplicated, and code-point sorted;
- `governance.facts` is sorted by the tuple `(name, canonical_json(paths), pattern,
  canonical_json(group), required)` after member normalization; duplicate complete rules are
  retained;
- no other configuration field is a collection.

The context builder invokes exactly these existing inspections with exactly these arguments:

1. `GitClient(config.project.repository).status()` for `git_status`;
2. `task_snapshot(config)` for `task_snapshot`;
3. `_safe_check("git", lambda: check_git(config))`;
4. `_safe_check("task-state", lambda: check_task_state(config))`;
5. `_safe_check("governance", lambda: check_governance(config))`;
6. `_safe_check("handover", lambda: check_handover(config,
   source=HandoverSource.WORKING_TREE, commit="HEAD"))`.

The four timestamp-free check results are stored in order `git`, `task-state`, `governance`,
`handover`. No other `CheckResult` is included. The `timestamp` field is removed; every other
`CheckResult` field is copied into `CanonicalCheckResult`.

The exact evidence shapes are:

- `git`: exactly the eight `CanonicalGitStatus` fields `branch`, `head`, `upstream`, `ahead`,
  `behind`, `modified_files`, `staged_files`, and `untracked_files`, with the exact types and
  path-collection normalization declared by that model;
- `task-state`: `by_source`, `current`, `done`, and `planned` with the task snapshot shapes above,
  plus integer `current_count` and `maximum_current_tasks`;
- `governance`: `{"facts": {fact_name: {repository_path: string | null}}}`;
- successful/failed `handover`: `source`, `commit`, and `records`, where each record has string
  `path`, integer `expected_size`, integer `actual_size`, string `expected_digest`, and string
  `actual_digest`; an early handover error has only `source` and `commit`;
- an exception converted by `_safe_check` has `{}` evidence.

Any other evidence key or shape is a context-construction error. Status enum values become
their strings. All strings and dynamic map keys undergo surrogate rejection and NFC.

Ordering is exhaustive:

- Git modified, staged, and untracked paths, protected-path violations, affected paths, and
  task `current`/`done`/`planned` arrays are de-duplicated and code-point sorted.
- `protected_path_violations` is the sorted union of staged paths matching
  `never_stage` or `never_commit` via the existing `matching_paths` function.
- Each `by_source` record array is sorted by `(source, line, task_id, status)`; source-map and
  evidence-map keys are ordered by canonical JSON serialization.
- Check findings are sorted by `(code, path_or_empty_string, severity, message)` and exact
  duplicates are retained.
- Governance fact rule maps, fact path maps, and every other JSON object use canonical key
  ordering. Handover records are sorted by `(path, expected_size, actual_size,
  expected_digest, actual_digest)`.
- `checks` uses the fixed four-item order above. Configuration arrays, findings, task records,
  status paths, handover records, remediation findings, and allowed paths have no ordering rule
  beyond the rules explicitly stated here; remediation findings alone preserve CLI order.

The template registry has exactly one entry for each `WorkflowStage`. Lookup is exact and has no
fallback. `PromptTemplate.version` must be an ASCII SemVer 2.0.0 string accepted by this exact
full-match regular expression (shown as one logical line):

```text
(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-((?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?
```

`PromptTemplate`'s `version` field validator uses `re.fullmatch(..., flags=re.ASCII)`: a `v`
prefix, whitespace, empty
prerelease/build identifiers, and leading zeroes in numeric core or numeric prerelease
identifiers are rejected. Prerelease and build identifiers are accepted exactly as the regex
allows. Versions are not trimmed, case-folded, Unicode-normalized, or otherwise normalized;
their ASCII spelling is preserved and compared case-sensitively, including build metadata.
`content` is NFC-normalized UTF-8 text with `\n` line endings and exactly one final newline.
`sha256` is the lowercase SHA-256 of `content.encode("utf-8")`. A material content edit requires
a version change; the digest makes an unversioned edit identity-changing as well. Carrying the
content in the payload makes load verification independent of the installed registry version.

## Normative built-in templates and rendering grammar

This section is the complete template specification. Prose elsewhere in this plan does not
authorize an implementer to add, remove, or reword prompt content. All seven registry entries
have version `1.0.0`. Their `content` is constructed at import time from the common literal and
the stage fragments below; this construction is specification data, not runtime prompt
rendering. The command lines are inert Markdown instructions for an external operator or agent;
Milestone 2 stores or prints them and never executes them.

The common literal is exactly the bytes between the following fence lines, excluding the fence
lines themselves. It uses LF line endings and has one LF after the final `{{VERDICT}}` marker.
There are no trailing spaces.

```text
# Governed Workflow Prompt

## Identity
- Prompt ID: {{PROMPT_ID_SCALAR}}
- Stage: {{STAGE_SCALAR}}
- Task: {{TASK_ID_SCALAR}}
- Repository: {{REPOSITORY_PATH_SCALAR}}
- Default branch: {{DEFAULT_BRANCH_SCALAR}}
- Conda environment: {{CONDA_ENVIRONMENT_SCALAR}}

## Role
@@ROLE@@

## Scope and allowed operations
@@SCOPE@@

## Allowed paths
{{ALLOWED_PATHS_LIST}}

## Prohibited operations
@@PROHIBITED@@

## Repository inspection evidence

### Git status
{{GIT_STATUS_JSON}}

### Task snapshot
{{TASK_SNAPSHOT_JSON}}

### Protected-path violations
{{PROTECTED_PATH_VIOLATIONS_LIST}}

### Validation checks
{{CHECKS_JSON}}

## Remediation findings
{{REMEDIATION_FINDINGS_LIST}}

## Verification commands
@@VERIFICATION@@

## Stop condition
@@STOP@@

## Verdict instruction
@@VERDICT@@
```

The six `@@...@@` construction markers are not runtime placeholders. For the selected stage,
replace them in this exact order: `@@ROLE@@`, `@@SCOPE@@`, `@@PROHIBITED@@`,
`@@VERIFICATION@@`, `@@STOP@@`, `@@VERDICT@@`. Each marker must occur exactly once before
replacement and zero times afterward. Each replacement is the exact text inside its stage's
corresponding fence below, excluding fence lines and excluding any LF immediately before the
closing fence. A replacement has no implicit leading or terminal LF. No normalization other
than the registry-wide NFC/LF/final-LF requirements is permitted.

### `plan-review` fragments

`ROLE`

```text
Act as the read-only planning reviewer for the requested task.
```

`SCOPE`

```text
- Inspect the plan, repository, governance documents, configuration, diffs, and supplied evidence.
- Run only read-only inspection commands and the verification commands below.
- Evaluate whether the plan is complete, internally consistent, deterministic, testable, and within the stated milestone boundary.
```

`PROHIBITED`

```text
- Do not modify any file.
- Do not stage, commit, push, reset, clean, rebase, create or alter a worktree, or run any other writable Git operation.
- Do not execute an agent, add workflow state, record a verdict, perform a transition, or choose a next stage.
```

`VERIFICATION`

```text
conda run -n {{CONDA_ENVIRONMENT_SHELL}} git status --short --branch
conda run -n {{CONDA_ENVIRONMENT_SHELL}} git diff --check
conda run -n {{CONDA_ENVIRONMENT_SHELL}} pytest -p no:cacheprovider
```

`STOP`

```text
Stop after reporting every blocking and non-blocking plan finding with file and line references where available; make no repository change.
```

`VERDICT`

```text
Return exactly one final verdict token: APPROVED or REJECTED.
```

### `implementation` fragments

`ROLE`

```text
Act as the implementation agent for the requested task.
```

`SCOPE`

```text
- Implement only the requested task and only within the rendered allowed-path list.
- Read any repository file needed for context and run the verification commands below.
- Keep all edits deterministic, minimal, and within the current milestone boundary.
```

`PROHIBITED`

```text
- Do not modify a path absent from the rendered allowed-path list.
- Do not stage, commit, push, reset, clean, rebase, create or alter a worktree, or run any other writable Git operation.
- Do not execute another agent, add workflow state, record a verdict, perform a transition, or choose a next stage.
```

`VERIFICATION`

```text
conda run -n {{CONDA_ENVIRONMENT_SHELL}} git status --short --branch
conda run -n {{CONDA_ENVIRONMENT_SHELL}} git diff --check
conda run -n {{CONDA_ENVIRONMENT_SHELL}} pytest -p no:cacheprovider
```

`STOP`

```text
Stop after the implementation and verification are complete, or immediately on a blocker; report changed paths, verification results, and blockers without staging, committing, or pushing.
```

`VERDICT`

```text
No APPROVED or REJECTED verdict is requested for this stage.
```

### `implementation-review` fragments

`ROLE`

```text
Act as the read-only implementation reviewer for the requested task.
```

`SCOPE`

```text
- Inspect the implementation, repository, diffs, tests, governance constraints, and supplied evidence.
- Run only read-only inspection commands and the verification commands below.
- Evaluate correctness, regressions, test coverage, determinism, and compliance with the requested scope and allowed paths.
```

`PROHIBITED`

```text
- Do not modify any file.
- Do not stage, commit, push, reset, clean, rebase, create or alter a worktree, or run any other writable Git operation.
- Do not execute an agent, add workflow state, record a verdict, perform a transition, or choose a next stage.
```

`VERIFICATION`

```text
conda run -n {{CONDA_ENVIRONMENT_SHELL}} git status --short --branch
conda run -n {{CONDA_ENVIRONMENT_SHELL}} git diff --check
conda run -n {{CONDA_ENVIRONMENT_SHELL}} pytest -p no:cacheprovider
```

`STOP`

```text
Stop after reporting every blocking and non-blocking implementation finding with file and line references where available; make no repository change.
```

`VERDICT`

```text
Return exactly one final verdict token: APPROVED or REJECTED.
```

### `remediation` fragments

`ROLE`

```text
Act as the remediation agent for the requested task.
```

`SCOPE`

```text
- Address every rendered remediation finding and no unlisted objective.
- Modify only paths in the rendered allowed-path list; read other files only for context.
- Run the verification commands below and preserve unrelated user changes.
```

`PROHIBITED`

```text
- Do not modify a path absent from the rendered allowed-path list or expand the remediation beyond the rendered findings.
- Do not stage, commit, push, reset, clean, rebase, create or alter a worktree, or run any other writable Git operation.
- Do not execute another agent, add workflow state, record a verdict, perform a transition, or choose a next stage.
```

`VERIFICATION`

```text
conda run -n {{CONDA_ENVIRONMENT_SHELL}} git status --short --branch
conda run -n {{CONDA_ENVIRONMENT_SHELL}} git diff --check
conda run -n {{CONDA_ENVIRONMENT_SHELL}} pytest -p no:cacheprovider
```

`STOP`

```text
Stop after every rendered finding is resolved and verified, or immediately on a blocker; report each finding's disposition, changed paths, verification results, and blockers without staging, committing, or pushing.
```

`VERDICT`

```text
No APPROVED or REJECTED verdict is requested for this stage.
```

### `governance-closeout` fragments

`ROLE`

```text
Act as the read-only governance closeout assessor for the requested task.
```

`SCOPE`

```text
- Inspect repository, task, governance, handover, configuration, diff, and supplied check evidence.
- Run only read-only inspection commands and the verification commands below.
- Determine and report the exact closeout actions still required; this stage does not perform them.
```

`PROHIBITED`

```text
- Do not modify any file.
- Do not stage, commit, push, reset, clean, rebase, create or alter a worktree, or run any other writable Git operation.
- Do not execute an agent, add workflow state, record a verdict, perform a transition, promote work, or choose a next stage.
```

`VERIFICATION`

```text
conda run -n {{CONDA_ENVIRONMENT_SHELL}} git status --short --branch
conda run -n {{CONDA_ENVIRONMENT_SHELL}} git diff --check
conda run -n {{CONDA_ENVIRONMENT_SHELL}} pytest -p no:cacheprovider
```

`STOP`

```text
Stop after reporting closeout readiness, every remaining governance or handover gap, and the evidence for each conclusion; make no repository change and perform no promotion.
```

`VERDICT`

```text
No APPROVED or REJECTED verdict is requested for this stage.
```

### `governance-review` fragments

`ROLE`

```text
Act as the read-only governance reviewer for the requested task.
```

`SCOPE`

```text
- Inspect repository, task, governance, handover, configuration, diff, and supplied check evidence.
- Run only read-only inspection commands and the verification commands below.
- Evaluate governance consistency, handover integrity, protected-path compliance, and closeout completeness.
```

`PROHIBITED`

```text
- Do not modify any file.
- Do not stage, commit, push, reset, clean, rebase, create or alter a worktree, or run any other writable Git operation.
- Do not execute an agent, add workflow state, record a verdict, perform a transition, promote work, or choose a next stage.
```

`VERIFICATION`

```text
conda run -n {{CONDA_ENVIRONMENT_SHELL}} git status --short --branch
conda run -n {{CONDA_ENVIRONMENT_SHELL}} git diff --check
conda run -n {{CONDA_ENVIRONMENT_SHELL}} pytest -p no:cacheprovider
```

`STOP`

```text
Stop after reporting every blocking and non-blocking governance finding with file and line references where available; make no repository change and perform no promotion.
```

`VERDICT`

```text
Return exactly one final verdict token: APPROVED or REJECTED.
```

### `push` fragments

`ROLE`

```text
Act as the constrained publisher for the requested task.
```

`SCOPE`

```text
- The only permitted state-changing operation is one `git push` after every verification below passes.
- The authorized branch is {{GIT_BRANCH_SCALAR}} and the authorized HEAD is {{GIT_HEAD_SCALAR}}.
- The recorded upstream is {{GIT_UPSTREAM_SCALAR}}, recorded ahead count is {{GIT_AHEAD_SCALAR}}, and recorded behind count is {{GIT_BEHIND_SCALAR}}.
- Require the live branch and HEAD to equal the authorized values, the live upstream to equal the non-null recorded upstream, and all modified, staged, and untracked path lists in both rendered and live status to be empty.
- For the commit-chain check, run the exact `git rev-list` command below, parse its sole output as two base-10 nonnegative integers separated by one tab and one terminal newline, and interpret them as behind then ahead. Require them to equal the recorded behind and ahead counts and require behind to equal zero.
- Only after all requirements pass, run the exact `git push` command below once.
```

`PROHIBITED`

```text
- Do not create, edit, delete, rename, chmod, format, or otherwise change any file.
- Do not stage, commit, reset, clean, rebase, merge, cherry-pick, amend, create or alter a worktree, or run any writable Git operation other than the single authorized `git push`.
- Do not execute another agent, add workflow state, record a verdict, perform a transition, promote work, or choose a next stage.
```

`VERIFICATION`

```text
conda run -n {{CONDA_ENVIRONMENT_SHELL}} git status --short --branch
conda run -n {{CONDA_ENVIRONMENT_SHELL}} git branch --show-current
conda run -n {{CONDA_ENVIRONMENT_SHELL}} git rev-parse HEAD
conda run -n {{CONDA_ENVIRONMENT_SHELL}} git rev-parse --abbrev-ref --symbolic-full-name @{upstream}
conda run -n {{CONDA_ENVIRONMENT_SHELL}} git rev-list --left-right --count @{upstream}...HEAD
conda run -n {{CONDA_ENVIRONMENT_SHELL}} git diff --check
conda run -n {{CONDA_ENVIRONMENT_SHELL}} git push
```

`STOP`

```text
Stop without pushing on any mismatch, missing upstream, nonzero behind count, dirty-file evidence, verification failure, or file change. Otherwise stop immediately after the single push and report its result; do not change any file.
```

`VERDICT`

```text
No APPROVED or REJECTED verdict is requested for this stage.
```

The runtime placeholder grammar is exactly `{{` + a name matching
`[A-Z][A-Z0-9_]*` under ASCII rules + `}}`. A single left-to-right tokenizer recognizes
placeholders; there is no delimiter escaping and literal `{{` or `}}` outside a valid marker is
a template error. The complete allowed name set is:

```text
ALLOWED_PATHS_LIST
CHECKS_JSON
CONDA_ENVIRONMENT_SCALAR
CONDA_ENVIRONMENT_SHELL
DEFAULT_BRANCH_SCALAR
GIT_AHEAD_SCALAR
GIT_BEHIND_SCALAR
GIT_BRANCH_SCALAR
GIT_HEAD_SCALAR
GIT_STATUS_JSON
GIT_UPSTREAM_SCALAR
PROMPT_ID_SCALAR
PROTECTED_PATH_VIOLATIONS_LIST
REMEDIATION_FINDINGS_LIST
REPOSITORY_PATH_SCALAR
STAGE_SCALAR
TASK_ID_SCALAR
TASK_SNAPSHOT_JSON
```

Every marker present in the constructed template is substituted simultaneously from the
following closed mapping; inserted text is never scanned again. Therefore placeholder-looking
user data is inert. An unknown name, a missing mapping value, a marker occurring other than the
number of times fixed by the common literal and selected fragments, or any placeholder token
remaining in the token stream is an error and produces no `RenderedPrompt`. Duplicate means
an occurrence count greater than that literal count, not repeated user data. `ROLE`, `SCOPE`,
`PROHIBITED`, `VERIFICATION`, `STOP`, and `VERDICT` are never runtime mapping keys.

- Scalar placeholder sources are exactly the following table. Each replacement is the
  canonical-JSON spelling of that source scalar. Strings and paths therefore include JSON
  quotation marks; `None` is `null`; booleans are lowercase; integers are unquoted base-10 with
  a leading `-` only when negative. JSON escaping and NFC are exactly the canonical serializer
  rules below.

  | Placeholder | Source |
  | --- | --- |
  | `PROMPT_ID_SCALAR` | computed `prompt_id` |
  | `STAGE_SCALAR` | `context.stage` |
  | `TASK_ID_SCALAR` | `context.task_id` |
  | `REPOSITORY_PATH_SCALAR` | `context.config.project.repository` |
  | `DEFAULT_BRANCH_SCALAR` | `context.config.project.default_branch` |
  | `CONDA_ENVIRONMENT_SCALAR` | `context.config.project.conda_environment` |
  | `GIT_BRANCH_SCALAR` | `context.git_status.branch` |
  | `GIT_HEAD_SCALAR` | `context.git_status.head` |
  | `GIT_UPSTREAM_SCALAR` | `context.git_status.upstream` |
  | `GIT_AHEAD_SCALAR` | `context.git_status.ahead` |
  | `GIT_BEHIND_SCALAR` | `context.git_status.behind` |
- `CONDA_ENVIRONMENT_SHELL` is one Bash ANSI-C-quoted word formed from
  `context.config.project.conda_environment.encode("utf-8", errors="strict")`. Emit the two
  ASCII bytes `$'`, then emit every source byte, without exception, as a reverse solidus,
  lowercase `x`, and exactly two lowercase hexadecimal digits, then emit one ASCII apostrophe.
  For example, `a b'` becomes `$'\x61\x20\x62\x27'`. This is the complete shell-escaping
  algorithm; it never emits a literal control or non-ASCII byte and never calls `shlex.quote`.
- `ALLOWED_PATHS_LIST` and `PROTECTED_PATH_VIOLATIONS_LIST` use the path-list formatter;
  `REMEDIATION_FINDINGS_LIST` uses the string-list formatter. An empty list is exactly
  `- (none)`. A non-empty list is one line per element in existing context order, exactly
  `- ` followed by that element's canonical-JSON string spelling, joined by LF with no leading
  or terminal LF.
- `GIT_STATUS_JSON`, `TASK_SNAPSHOT_JSON`, and `CHECKS_JSON` are JSON-block formatters. The
  value is exactly `````json``, LF, canonical JSON of respectively
  `git_status.model_dump(mode="json")`, `task_snapshot.model_dump(mode="json")`, or
  `[check.model_dump(mode="json") for check in checks]`, LF, and ``````, with no terminal LF.
  Thus empty lists inside evidence are exactly `[]`; non-empty lists are compact comma-separated
  JSON arrays in their already-normalized order. Every check is a compact object in fixed check
  order. Check findings are the `findings` array inside that object, each finding is a compact
  object, and each check's evidence is the compact `evidence` object; no alternate findings,
  checks, or evidence presentation is allowed.

Substitution is over Unicode strings but must produce NFC. The renderer concatenates literal
and formatted token values, rejects surrogates, rejects `\r`, and requires the result to be NFC;
it does not trim or wrap any line. It then requires LF-only line endings and exactly one terminal
LF. `markdown` is that exact string and Markdown bytes are exactly
`markdown.encode("utf-8", errors="strict")`, without a BOM.

The registry constructor computes `sha256(content.encode("utf-8"))` and refuses a supplied or
computed mismatch. Tests pin all seven resulting content byte strings and digests, rather than
copying a second production constructor. Byte counts include the one terminal LF. The registry
is exactly:

| Stage | Version | Bytes | SHA-256 | Content construction |
| --- | --- | ---: | --- | --- |
| `plan-review` | `1.0.0` | 1739 | `27dde6b824ec24aef65736fb8e66a90985f73bce04323e4957122faf7963008a` | common literal plus the six `plan-review` fragments |
| `implementation` | `1.0.0` | 1772 | `4aae483d3402332a26bab1ba813d6d7084c9da273702749d8911490198f6bea3` | common literal plus the six `implementation` fragments |
| `implementation-review` | `1.0.0` | 1752 | `3417515b3001ae3d105b9e18cfda1892e2fa0774d14345d1f8e55be09d89a575` | common literal plus the six `implementation-review` fragments |
| `remediation` | `1.0.0` | 1833 | `135e61a751b226dff796e143cf17cf5143c3f48e0e0ad374d5534d491a73e2d8` | common literal plus the six `remediation` fragments |
| `governance-closeout` | `1.0.0` | 1768 | `9d0ab6e86cc26e555eaaa60493827ef33a27931c5360485424523a354b12f247` | common literal plus the six `governance-closeout` fragments |
| `governance-review` | `1.0.0` | 1765 | `7dbd4ace9b1f1af39808a542f4ba90a17abe5e7ce418ebf52034ac712a520cce` | common literal plus the six `governance-review` fragments |
| `push` | `1.0.0` | 2924 | `e175957cf5939c01fb10381ef04df410c830daa285df8f23757d929b1ea5ec84` | common literal plus the six `push` fragments |

## Canonical JSON and prompt identity

Canonicalization recursively accepts only `None`, exact `bool`, signed 64-bit exact `int`,
surrogate-free `str`, `list`, and `dict[str, JsonValue]`. Tuples, sets, enums, paths, bytes,
floats, decimals, datetimes, non-finite numbers, and arbitrary objects must be converted by the
typed builders before canonicalization; reaching the serializer is an error. Strings and keys
are NFC-normalized. If two keys become equal after NFC, serialization fails.

Object keys are sorted by Python string ordering after NFC: lexicographic ascending Unicode
code-point order, with a shorter equal prefix first. Arrays are never reordered by the
serializer. Serialization is exactly:

```python
text = json.dumps(
    normalized_value,
    ensure_ascii=False,
    allow_nan=False,
    sort_keys=True,
    separators=(",", ":"),
    check_circular=True,
)
canonical_bytes = text.encode("utf-8", errors="strict")
```

This uses Python's standard JSON escapes: quotation mark, reverse solidus, and control
characters are escaped; `/` and non-ASCII scalar values are not escaped. Escape letters and
hexadecimal digits emitted by `json.dumps` are lowercase. Canonical payload bytes have no BOM
and no trailing newline.

Normative serializer golden vector (the input notation is a Python value; the `z` value is
decomposed `e` plus `U+0301` before NFC):

```text
input:  {"z": "e\u0301", "a": ["line\n", 0, True, None, {"beta": "\t"}]}
bytes:  {"a":["line\n",0,true,null,{"beta":"\t"}],"z":"é"}
hex:    7b2261223a5b226c696e655c6e222c302c747275652c6e756c6c2c7b2262657461223a225c74227d5d2c227a223a22c3a9227d
sha256: 4f382bf736997a397b150feccf86a3d3f288010c86c33b40c2e184cd088db364
```

For a `PromptContext`:

```text
canonical_payload_bytes = canonical_json(context.model_dump(mode="json"))
payload_sha256 = sha256(canonical_payload_bytes).hexdigest()
prompt_id = payload_sha256[:16]
```

The renderer applies only the tokenization, closed mapping, formatters, simultaneous
substitution, and byte rules in the normative rendering section to the saved template content.
No ad hoc builder, fallback prose, or stage-specific renderer branch is permitted.
`PromptTemplate.version`, `PromptTemplate.content`, and `PromptTemplate.sha256` remain fields of
`PromptContext` and therefore remain part of prompt identity. `markdown_sha256` hashes the exact
rendered bytes. Prompt identity and Markdown contain no time value.

Metadata duplicates addressing fields deliberately. Each duplicate must equal its value in
`payload`, and its two SHA-256 fields must match the recomputed payload and Markdown hashes.
Metadata bytes are `canonical_json(metadata.model_dump(mode="json")) + b"\n"`: UTF-8, no BOM,
exactly one final newline.

Every rendered prompt states role, repository and Conda environment, exact task and stage,
inspection evidence, allowed and prohibited operations, verification commands, and a stop
condition. Review prompts require exactly one `APPROVED` or `REJECTED` verdict. The push prompt
states the exact branch and HEAD from context, specifies the required commit-chain check, and
forbids file changes.

## Artifact addressing, publication, and verified load

After `Path.expanduser()`, the fixed final paths are:

```text
~/.ai-workflow-engine/workflow-runs/prompts/<project_id>/<stage>/<prompt_id>.md
~/.ai-workflow-engine/workflow-runs/prompts/<project_id>/<stage>/<prompt_id>.json
```

The artifact root and repository are resolved. Storage fails if the selected artifact directory
is inside the target repository. Storage never depends on the current directory or repository
`.gitignore`.

The public API is exactly:

```python
save(rendered: RenderedPrompt) -> StoredPromptPaths
load(project_id: str, stage: WorkflowStage, prompt_id: str) -> RenderedPrompt
```

`project_id` must match `[A-Za-z0-9][A-Za-z0-9._-]*`; stage must be a registry literal; prompt ID
must match `[0-9a-f]{16}`. Before joining, reject separators, dot components, absolute/rooted,
drive-qualified, drive-relative, and UNC spellings. Resolve parent and candidate paths and
reject symlink escape or a final location outside the artifact root.

The sidecar is exactly the closed `PromptMetadata` JSON. Its embedded `payload` contains the
normalized config, requested inputs, exact template content, all snapshots, and all check
evidence. Therefore load needs no CLI arguments, current repository inspection, clock value,
or installed template-registry state.

Save uses this race-safe, no-clobber protocol:

1. Fully validate `RenderedPrompt`, including recomputing canonical payload, prompt ID, template
   digest, Markdown from the saved template content, Markdown digest, metadata fields, and
   metadata bytes, before creating a directory.
2. Create the parent directory, then create uniquely named same-directory temporary Markdown
   and JSON files using exactly `os.open(path, O_WRONLY | O_CREAT | O_EXCL, 0o600)`. Write the
   exact bytes to the appropriate descriptor, handling short writes, then flush any wrapping
   stream and `os.fsync` each file before publication. This invocation owns only its uniquely
   named temporary files.
3. If a Markdown final exists while the JSON final does not, byte-compare the Markdown before
   publishing anything: continue only when it exactly equals this save's expected Markdown;
   otherwise fail with an incomplete-artifact collision and preserve it. This permits safe
   recovery of a matching Markdown-only partial left by an older implementation or external
   interruption, although the metadata-first protocol itself cannot create that state.
4. Publish canonical JSON metadata as the first final member with `os.link(json_temp,
   json_final)`. A successful hard link is an atomic no-clobber create on the same filesystem;
   `os.replace` is forbidden for final publication. On `FileExistsError`, read the JSON final
   and continue only if its bytes exactly equal this save's expected canonical metadata bytes.
   Differing metadata is a collision and must fail before any attempt to publish Markdown.
5. Only after metadata publication or exact metadata equality, publish Markdown with
   `os.link(markdown_temp, markdown_final)`. On `FileExistsError`, continue only if the existing
   Markdown bytes exactly equal this save's expected bytes; otherwise fail with a collision.
6. After both finals exist, re-read both and require exact equality, `fsync` the parent directory
   where supported, then unlink this invocation's temporary files. In a handled failure, remove
   only this invocation's temporary files. Final files are never unlinked, truncated,
   overwritten, replaced, or otherwise removed by save or recovery.

No lock is used or required. The metadata hard link selects the pair's winning identity, and
exact comparison makes concurrent identical saves idempotent. In particular, if valid writers
are forced to the same 16-character prompt ID and render identical Markdown but have different
embedded payload metadata, only one metadata final can win; every loser detects differing
metadata and fails before publishing Markdown. A writer allowed to reach Markdown publication
has metadata identical to the winner, including `markdown_sha256`, and deterministic rendering
therefore requires the same Markdown bytes. Thus no interleaving of valid writers can combine
members from different rendered prompts.

A crash of this protocol can leave no final or a metadata-only final, never a Markdown-only
final. A later save with identical metadata completes a metadata-only partial by publishing the
matching Markdown; differing metadata fails before Markdown and preserves the partial. For a
pre-existing Markdown-only partial, step 3 permits completion only by a writer with matching
Markdown, after which metadata publication still selects exactly one winner; a differing
Markdown fails before metadata. A pre-existing complete pair must match metadata first and then
Markdown or save reports a collision without changing either member. Crash-left unique
temporary files are ignored by load and later saves; normal returns and handled failures clean
only their own temps.

Load requires both finals; a missing member is an incomplete artifact and is never returned.
It reads metadata with strict UTF-8 and exactly one terminal `\n`, parses
it into `PromptMetadata`, and rejects duplicate JSON keys. It then reconstructs the embedded
`PromptContext` and `PromptTemplate`, recomputes canonical payload bytes, full payload hash,
16-character prompt ID, template digest, and Markdown solely by applying the normative
tokenization, mapping, formatting, substitution, and newline algorithm to the embedded template
content and embedded context. It does not consult the current registry, invocation state, or
implementer-written prose. It then recomputes Markdown bytes/digest, every duplicated metadata
field, and canonical metadata bytes. It also
checks the three address arguments against metadata and resolved paths. Any byte mismatch,
missing member, extra field, malformed model, hash mismatch, render mismatch, or noncanonical
JSON is tampering. Because metadata is validated against both its embedded payload and the
Markdown bytes, load never returns a partial or mixed pair, including while a save is between
its two publication links. On success it returns the exact `RenderedPrompt` model above. A
save/load round trip preserves Markdown, payload, metadata, and both byte fields exactly.

## Validation and CLI output

`prompt/validator.py` returns the existing `CheckResult` and `Status`. It performs no fuzzy
keyword or prose search. Every structural result is defined by a template marker, a model
invariant, or exact rendered bytes as follows:

1. Tokenize `context.template.content` with the normative grammar. An unresolved placeholder is
   mechanically defined as a recognized placeholder token for which the closed mapping has no
   value after mapping construction. Unknown names, malformed delimiters, missing occurrences,
   and duplicate occurrences have the exact meanings and failure behavior defined above. A
   placeholder-looking substring introduced by formatted data is not a token and is not an
   unresolved placeholder because formatted values are never rescanned.
2. Re-render from `context.template.content` and `context` with the normative algorithm and
   require exact Unicode-string and UTF-8 byte equality with `rendered.markdown`. This exact
   comparison is the authoritative check for every literal role, scope, prohibited-operation,
   verification, stop, verdict, push, allowed-path, remediation-finding, check, and evidence
   statement.
3. Define a required section as a line exactly equal to its heading. The complete heading
   sequence must occur exactly once each and in this order, with no other ATX heading line:
   `# Governed Workflow Prompt`, `## Identity`, `## Role`,
   `## Scope and allowed operations`, `## Allowed paths`, `## Prohibited operations`,
   `## Repository inspection evidence`, `### Git status`, `### Task snapshot`,
   `### Protected-path violations`, `### Validation checks`, `## Remediation findings`,
   `## Verification commands`, `## Stop condition`, and `## Verdict instruction`.
   An ATX heading line is mechanically any line beginning with one through six `#` characters
   followed by one ASCII space. JSON string newlines are escaped and cannot create headings.
4. Require the Git evidence object to have exactly `branch`, `head`, `upstream`, `ahead`,
   `behind`, `modified_files`, `staged_files`, and `untracked_files`, with the types and
   normalized path collections of `CanonicalGitStatus`. Require each rendered JSON block and
   list span between its exact adjacent headings to equal its specified formatter output.
5. Require allowed paths to be non-empty exactly for `implementation` and `remediation` and
   empty for the other five stages. Require remediation findings to be non-empty exactly for
   `remediation` and empty for the other six stages. Their rendered spans must equal the exact
   list formatters, including `- (none)`.
6. Require the constructed template's six literal fragments and their rendered spans to equal
   the fragments for `context.stage`. For `plan-review`, `implementation-review`, and
   `governance-review`, require the exact review verdict fragment; for the other four stages,
   require the exact no-verdict fragment. This is the complete definition of the review
   prohibited-operation and verdict checks.
7. For `push`, additionally require exact equality with the `push` scope, prohibited,
   verification, and stop fragments. This mechanically verifies the rendered branch, HEAD,
   upstream, ahead/behind wording, the exact commit-chain command and algorithm, the single push
   command, and the file-change prohibition; none is inferred from keywords.
8. Require exact consistency of context, canonical payload bytes, full payload hash, prompt ID,
   template version/content/hash, Markdown bytes/hash, every metadata duplicate, and canonical
   metadata bytes.

Validation runs through `_safe_check`. `FAIL` or converted `ERROR` uses existing `_emit`
formatting and exits 1 without emitting a prompt or creating any directory/file. Configuration,
normalization, collection, lookup, rendering, and store/load exceptions run through `_protected`,
write exactly `ERROR: <message>` to stderr even in JSON mode, emit no stdout success payload,
and exit 2. Save occurs only after `PASS`.

Human success is these labels, a blank line, and the exact Markdown body:

```text
Prompt ID: <prompt_id>
Stage: <stage>
Stored: yes|no
Prompt artifact: <resolved-absolute-posix-md-path>|(not stored)
Metadata artifact: <resolved-absolute-posix-json-path>|(not stored)

<rendered Markdown body>
```

JSON success is exactly `PromptSuccess`. Stored paths are resolved absolute `Path.as_posix()`
strings; with `--no-store`, both are null and `stored` is false. Stdout bytes are exactly
`canonical_json(success.model_dump(mode="json")) + b"\n"`, written without Rich decoration or
other stdout. Thus the success JSON names and embeds the exact closed `PromptMetadata` schema.
Both success modes exit 0; `--no-store` performs no filesystem write.

## Exact planned files

Milestone 2 implementation is limited to this closed list:

- add `src/ai_workflow_engine/prompt/__init__.py`
- add `src/ai_workflow_engine/prompt/models.py`
- add `src/ai_workflow_engine/prompt/templates.py`
- add `src/ai_workflow_engine/prompt/context.py`
- add `src/ai_workflow_engine/prompt/renderer.py`
- add `src/ai_workflow_engine/prompt/validator.py`
- add `src/ai_workflow_engine/prompt/store.py`
- modify `src/ai_workflow_engine/cli.py`
- modify `src/ai_workflow_engine/models.py`
- modify `examples/amozesh_konkur.yaml`
- modify `docs/configuration.md`
- modify `tests/conftest.py`
- modify `tests/test_config.py`
- add `tests/test_prompt_context.py`
- add `tests/test_prompt_templates.py`
- add `tests/test_prompt_renderer.py`
- add `tests/test_prompt_validator.py`
- add `tests/test_prompt_store.py`
- modify `tests/test_cli.py`

No additional serializer or lock file is needed: canonicalization belongs in `renderer.py`, and
the no-clobber protocol belongs in `store.py`. There are no planned state, verdict, transition,
agent, worktree, or writable-Git files.

## Testing strategy and acceptance coverage

Tests must cover all of the following:

- all seven commands in human and JSON modes; exact stdout/stderr bytes, closed success and
  metadata schemas, exit codes, `--store`, and write-free `--no-store`;
- missing, empty, whitespace-only, Unicode-whitespace, NFC-equivalent, and ordinary task IDs,
  including exact whitespace collapse and identity behavior;
- required findings, empty/whitespace-only finding rejection, NFC/whitespace normalization,
  CLI-order and duplicate preservation, and `--finding` rejection on each of the six
  non-remediation commands;
- missing/repeated/duplicate/sorted allowed paths; dot-component normalization; empty, root,
  absolute, whitespace, `..` escape, and symlink escape; POSIX input containing a backslash;
  `C:/x`, `C:x`, `\\x`, `\\server\\share`, and `//server/share` cases on POSIX and Windows;
  and `--allowed-path` rejection on each of the five commands that does not expose it;
- the normative canonical JSON vector above, a pinned complete `PromptContext` fixture with
  exact payload bytes and digest, NFC key collision, surrogate, float, non-finite, out-of-range
  integer, non-string-key, escaping, UTF-8, and newline cases;
- repeat-run equality of payload, Markdown, metadata, and prompt ID, plus separate identity
  sensitivity tests for every declared material input: every configuration field, stage, task
  ID, template version/content, all eight Git status fields (`branch`, `head`, `upstream`,
  `ahead`, `behind`, `modified_files`, `staged_files`, and `untracked_files`), full task snapshot
  and task records, each of the four check statuses,
  summaries, findings and evidence (including governance facts and handover records), protected
  path violations, remediation findings, and allowed paths;
- timestamp removal and proof that changing only any `CheckResult.timestamp` changes no output;
- exact check invocation/order/evidence schemas, including the named eight-field Git evidence
  object, and every collection-ordering/de-duplication rule;
- Pydantic v2 tests proving every prompt model subclasses existing `StrictModel`, rejects every
  unknown field, enforces each exact field type/literal, and proving `PromptMetadata.model_fields`
  is exactly the closed field set specified above with no optional implementer field;
- exact-stage template lookup, unknown-stage failure, exactly seven registry entries, the pinned
  `1.0.0` version for every entry, exact content UTF-8 bytes, byte counts, and the seven pinned
  SHA-256 digests above; accepted core/prerelease/build SemVer examples; rejection of prefixes,
  whitespace, non-ASCII, missing/empty identifiers, and forbidden leading zeroes; and
  preservation and case-sensitive identity of prerelease/build spelling;
- exact rendered Markdown golden bytes for all seven stages from one pinned context family,
  including every heading, fragment, scalar, path list, empty and non-empty list, JSON check,
  finding, evidence, LF, and terminal-newline byte; separate golden cases for JSON and shell
  escaping, `None`, booleans, negative and nonnegative integers, non-ASCII NFC strings, embedded
  apostrophes, and placeholder-looking user data that must remain inert;
- template-construction failures for every missing, duplicate, and residual `@@...@@` marker;
  runtime-token failures for malformed delimiters, every unknown allowed-set miss, every missing
  mapping value, every missing or duplicate expected occurrence, and every unresolved token;
  proof that substitution is simultaneous and inserted values are not rescanned;
- stage-specific validator tests for exact fragment and rendered-span equality for all seven
  stages; exact heading set, order, and uniqueness; exact allowed-path/remediation cardinality
  and list spans; the three exact review verdict instructions; all four exact no-verdict
  instructions; and push branch/HEAD/upstream/count wording, commit-chain command and parsing
  algorithm, single push command, stop rules, and file-change prohibition;
- every validator failure, including one-byte changes to each literal and dynamic section,
  `_safe_check`/`_emit` exit 1, `_protected` exit 2, and no artifact or directory after validation
  failure;
- expanded-home storage, current-directory independence, repository containment refusal,
  `.gitignore` independence, safe address components, traversal/drive/UNC/symlink defense;
- load-time reconstruction solely through the normative rendering algorithm, without invocation
  state, current registry, or fallback prose; exact round trip; noncanonical sidecar rejection;
  duplicate-key rejection; and separate tampering tests for addressing fields, payload, payload
  hash/ID, template version/content/digest, Markdown/digest, metadata duplicates, extra fields,
  missing member, and mixed pairs;
- exact temporary creation flags `O_WRONLY | O_CREAT | O_EXCL`, mode `0o600`, same-directory
  placement, short-write handling, exact bytes, flush/fsync, and per-invocation cleanup ownership;
- concurrent identical saves; concurrent forced same-ID writers with different metadata, both
  when Markdown differs and when Markdown is identical; proof that metadata is linked first and
  differing metadata fails before any Markdown link; atomic no-clobber behavior; metadata-only
  matching repair and differing preservation/failure; matching and differing legacy
  Markdown-only partial handling; complete-pair comparison in metadata-then-Markdown order;
  final-file immutability; temporary-file cleanup on success and handled error; crash-left-temp
  ignoring; and load rejection of missing, in-progress, or mixed pairs;
- missing/empty/whitespace-only and valid `project.conda_environment` across models, fixtures,
  example configuration, and documentation;
- regression proof that `GitClient.READ_ONLY_FORMS` is unchanged and prompt code contains no
  agent execution, subprocess, worktree, writable Git, stage/commit/push/promotion, persisted
  state, verdict recording, transition enforcement, or automatic next-stage behavior.

## Plan Review disposition

This revision contains no open design question. Implementation begins only after a fresh Plan
Review approves these contracts.
