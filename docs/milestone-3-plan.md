# Milestone 3 Architecture Plan — Non-Interactive Agent Execution

Status: REVISED DRAFT (round 2), awaiting a fresh, independent Plan Review. Not implemented.
Round 1 returned REJECTED; this revision remediates all of its findings B1–B3, S4–S5, and
N6–N9 (renderer.py added to the file list; verification-command execution mechanism specified as
structured argv; collision-free state addressing plus embedded-identity load check; clean-tree
run precondition; exact base64 stdout/stderr storage; `agent apply` deferred to Milestone 4;
module renames avoiding the pre-existing `workflow/state.py`; integration test coverage added).
Per `docs/AGENT_PROTOCOL.md`, this round is reviewed by an independent session with no memory of
round 1.

## Goal and hard boundary

Milestone 3 adds two capabilities on top of Milestones 1–2, exactly as scoped by
`docs/milestones.md` and by Milestone 2's explicit deferrals:

1. **Persisted workflow state:** a per-task, append-only, hash-chained event log recording stage
   outcomes and verdicts, with mechanical transition enforcement and next-stage computation.
2. **Non-interactive agent execution:** running one configured external agent process against
   one stored, verified Milestone 2 prompt, inside an isolated sandbox snapshot, with a hard
   timeout, a strict report schema, and independent verification of every claim the agent makes.

The following decisions are binding:

1. `GitClient.READ_ONLY_FORMS` remains byte-for-byte unchanged. All sandbox Git operations go
   through a new, separate `SandboxGit` class that operates **only** on sandbox directories
   created by this milestone and refuses any directory that is not a registered sandbox.
2. **Milestone 3 makes no change to the target repository at all.** Every write it performs
   lands either in a throwaway sandbox clone or under `~/.ai-workflow-engine/`. A scoped-write
   agent's output is captured as a **verified patch artifact**; it is never applied to the
   target working tree, index, ref, commit, or remote in this milestone. Applying a verified
   patch to the working tree is deferred to Milestone 4's controlled-change surface, which
   consumes the artifact this milestone produces. (This was tightened after plan review found
   the earlier `agent apply` verb sat adjacent to Milestone 4 and introduced a third,
   un-allowlisted writable-Git surface on the real repository.)
3. The `push` stage is never agent-executable. No agent, mode, or configuration can be bound to
   it.
4. Agent output is evidence, not authority: every claim in an agent report is either
   independently verified against sandbox state or the run **fails**. There is no
   "unverified but accepted" outcome.
5. No clock-derived value appears in any persisted state event, run artifact identity, or
   verification decision.
6. Isolation is a **correctness** boundary, not a security boundary: agents run with
   `cwd=<sandbox>` on a snapshot clone, with a scrubbed environment, and the target repository
   is status-fingerprinted before and after every run (any change fails the run) — but a
   malicious agent with absolute-path write access to the machine cannot be *prevented* by a
   local runner, only detected. The documentation must state this honestly.
7. `agent run` requires the target repository working tree to be **clean** (no modified, staged,
   or untracked files) and its live HEAD to equal the prompt's recorded `repository_head`.
   Because the sandbox is checked out at that committed HEAD, this precondition guarantees the
   sandbox faithfully reproduces the exact state the prompt's working-tree-derived evidence
   describes. A dirty tree or HEAD drift fails the run before any agent starts.
8. Live Codex/OpenCode binaries are never a test dependency. All tests use stub executables the
   tests themselves write.

## Package design

```text
src/ai_workflow_engine/workflow/
  events.py       # WorkflowEvent and derived-state models (new)
  transitions.py  # the fixed transition table and replay/enforcement logic (new)
  event_store.py  # append-only no-clobber event storage and verified load (new)
  state.py        # WorkflowSummary — pre-existing (Milestone 1), unchanged
  invariants.py   # summarize_workflow — pre-existing (Milestone 1), unchanged
src/ai_workflow_engine/agents/
  __init__.py
  models.py       # AgentSettings (config), AgentReport, AgentRunRecord, results
  sandbox.py      # SandboxGit + sandbox lifecycle (create from snapshot, destroy)
  runner.py       # subprocess execution: stdin/stdout contract, timeout, env scrubbing
  verification.py # independent claim verification -> CheckResult
  artifacts.py    # no-clobber run-artifact storage and verified load
```

The pre-existing `workflow/state.py` (`WorkflowSummary`) and `workflow/invariants.py`
(`summarize_workflow`) are the Milestone 1 read-only task-summary helpers; they are left
untouched, and the new event-sourced state machine is deliberately given non-colliding module
names (`events.py`, `event_store.py`) to avoid confusion with them. There is no verified-patch
`apply` module: per binding decision 2, Milestone 3 never writes the target repository.

No new third-party dependency is added.

## Configuration migration

`EngineConfig` gains exactly one optional section:

```python
class AgentSettings(StrictModel):
    name: str                      # fullmatch [A-Za-z][A-Za-z0-9._-]{0,63}
    executable: Path               # absolute path required; no PATH lookup
    args: list[str] = []           # passed verbatim after executable
    mode: Literal["read-only", "scoped-write"]
    timeout_seconds: int           # ge=1, le=86400
    stages: list[WorkflowStage]    # non-empty, unique, each compatible with mode

class EngineConfig(StrictModel):
    ...existing fields...
    agents: list[AgentSettings] = Field(default_factory=list)
```

Validation rules: agent names unique across the list; `executable` must be absolute (existence
is checked at run time, not load time, matching the existing path philosophy); stage/mode
compatibility is fixed: `read-only` agents may list only
`plan-review`, `implementation-review`, `governance-closeout`, `governance-review`;
`scoped-write` agents may list only `implementation`, `remediation`; `push` is rejected for
every agent. The `agents` list is canonically sorted by `name` wherever it is serialized.

### Prompt-payload impact (deliberate, breaking for stored artifacts)

Milestone 2's `CanonicalEngineConfig` is defined as containing every `EngineConfig` field, so it
gains `agents: list[CanonicalAgentSettings]` (same fields as `AgentSettings`, `executable`
serialized with `Path.as_posix()`, `args` preserved in order, `stages` sorted by the stage
literal). Because the payload shape changes, `PromptContext.schema_version`,
`PromptMetadata.schema_version`, and `PromptSuccess.schema_version` are all bumped to the
literal `"1.1"`, and store `load()` rejects any sidecar whose schema_version is not `"1.1"` with
a clear error. Previously stored prompt artifacts become unloadable; they are local, ephemeral
operator artifacts and this is an accepted, documented break. Prompt **templates** are unchanged
(same seven entries, version `1.0.0`, same byte counts and digests), and no template placeholder
draws from `agents`, so the `agents` list enters only the hashed payload — never the rendered
Markdown body directly. But the body is not entirely fixed: `PROMPT_ID_SCALAR` is rendered into
the Identity section, and `prompt_id` changes because the payload changed, so the exact rendered
Markdown golden bytes and `markdown_sha256` for a given input **do** change (only via the
prompt-id line). Concretely, the following test pins change and must be regenerated:
per-context payload/`prompt_id` fixtures, the full rendered-Markdown golden bytes, and
`markdown_sha256` (in `test_prompt_context.py`, `test_prompt_renderer.py`, `test_prompt_store.py`,
`test_cli.py`). The seven **template** content byte-counts and SHA-256 digests in
`test_prompt_templates.py` do **not** change and must stay byte-identical.

## Workflow state model

### Event schema

State is an append-only sequence of events per `(project_id, task_id)`. Replay of the sequence
is the only source of truth; there is no separate mutable "current state" record.

```python
StateAction = Literal["completed", "verdict"]
Verdict = Literal["APPROVED", "REJECTED"]

class WorkflowEvent(StrictModel):
    schema_version: Literal["1.0"]
    project_id: str            # same rule as store project_id: [A-Za-z0-9][A-Za-z0-9._-]*
    task_id: str               # M-2 task-ID normalization applied
    sequence: int              # 1-based, contiguous
    parent_digest: str | None  # 64-hex sha256 of previous event's exact stored bytes;
                               # None exactly when sequence == 1
    stage: WorkflowStage
    action: StateAction
    verdict: Verdict | None    # non-null exactly when action == "verdict"
    prompt_id: str | None      # 16-hex when given; the prompt that governed the stage
    agent_run_id: str | None   # 16-hex when given; links to a stored agent-run artifact
    head: str                  # repository HEAD commit hash when the event was recorded
    note: str                  # M-2 text normalization; may be empty
```

Verdict stages are exactly `plan-review`, `implementation-review`, `governance-review`: their
events must have `action == "verdict"` and a non-null verdict. The other four stages must have
`action == "completed"` and null verdict.

### Transition table (complete)

The expected next stage is a pure function of the last event (empty history means the expected
stage is `plan-review`):

| Last event | Next expected stage |
|---|---|
| (none) | `plan-review` |
| `plan-review` APPROVED | `implementation` |
| `plan-review` REJECTED | `plan-review` |
| `implementation` completed | `implementation-review` |
| `implementation-review` APPROVED | `governance-closeout` |
| `implementation-review` REJECTED | `remediation` |
| `remediation` completed | `implementation-review` |
| `governance-closeout` completed | `governance-review` |
| `governance-review` APPROVED | `push` |
| `governance-review` REJECTED | `governance-closeout` |
| `push` completed | (terminal — recording any further event fails) |

Recording an event whose `stage` is not the expected next stage fails with a
`transition_violation` finding naming both stages. This is the complete graph; there are no
other transitions, no skips, and no administrative overrides in Milestone 3.

### Storage protocol

Events live at:

```text
~/.ai-workflow-engine/workflow-runs/state/<project_id>/<task_dir>/<NNNNNNNN>.json
```

`task_dir` must be **collision-free** across distinct normalized task IDs, because M-2 task-ID
normalization permits arbitrary non-whitespace Unicode (`context.py: normalize_text`), so a
lossy sanitizing slug would map e.g. `a/b` and `a_b` to one directory. `task_dir` is therefore
`<readable>-<task_hash16>` where `task_hash16` is the first 16 lowercase hex characters of
`sha256(normalized_task_id.encode("utf-8"))` — the authoritative, collision-free component —
and `<readable>` is the task ID with every character outside `[A-Za-z0-9._-]` replaced by `_`
and truncated to 40 characters, present only for human legibility. Two distinct task IDs cannot
share a `task_dir` because they cannot share `task_hash16`. `NNNNNNNN` is the zero-padded
8-digit sequence number. File bytes are exactly
`canonical_json(event.model_dump(mode="json")) + b"\n"` using the Milestone 2 canonical
serializer. Publication reuses the Milestone 2 no-clobber protocol: unique temp file in the
same directory (`O_WRONLY | O_CREAT | O_EXCL`, `0o600`), write-all, flush, fsync, then
`os.link(temp, final)`; on `FileExistsError`, byte-compare — identical bytes are idempotent
success, different bytes are a `sequence_conflict` failure. Final files are never modified or
removed. Directory fsync where supported; each invocation cleans only its own temp files.

Load reads the directory, requires file names to be exactly the contiguous set
`00000001.json..NNNNNNNN.json` (a gap, duplicate-ignoring collision, or foreign file name is a
`state_corrupt` error), parses each with strict UTF-8 / single-trailing-newline / duplicate-key
rejection, validates each event model, requires `sequence` to match the file name, **requires
every event's embedded `project_id` and `task_id` to equal the requested (normalized) address**
(a `state_identity_mismatch` corruption error otherwise — defense in depth against any future
addressing bug or hand-editing that lands foreign events in a directory), verifies the
`parent_digest` chain against the actual prior file bytes, and replays the transition table.
Any mismatch is tampering and fails the load. An empty or absent directory is an empty history,
not an error.

### State CLI

```text
workflowctl state show   --config <file> --task-id <id> [--output human|json]
workflowctl state next   --config <file> --task-id <id> [--output human|json]
workflowctl state record --config <file> --task-id <id> --stage <stage>
                         (--verdict APPROVED|REJECTED | --completed)
                         [--prompt-id <16hex>] [--agent-run <16hex>] [--note <text>]
                         [--output human|json]
```

`record` validates the event against the transition table and verdict rules, sets `head` from
`GitClient(config.project.repository).head()`, and appends. Success emits a `CheckResult`-style
PASS (`check_name="state"`) whose evidence contains the appended event and the new expected
next stage; failures are FAIL with the specific finding (`transition_violation`,
`verdict_required`, `verdict_forbidden`, `terminal_task`, `sequence_conflict`, `state_corrupt`).
`show` emits the full replayed history plus derived state; `next` emits just the expected next
stage (`"(terminal)"` rendering for a completed task, JSON `null`). JSON success payloads are
canonical-JSON bytes plus one newline on stdout, exit 0; FAIL exits 1; unexpected errors go
through `_protected` (`ERROR: <message>`, exit 2). Human output uses plain labels like the
existing commands; no Rich markup is introduced on these paths.

## Agent report contract

An agent receives the governed prompt Markdown on **stdin** (exact stored bytes) and must write
exactly one UTF-8 JSON object to **stdout** (leading/trailing ASCII whitespace tolerated;
duplicate keys rejected; anything else on stdout is a schema failure — agents must put logs on
stderr, which is captured as opaque evidence):

```python
class AgentFinding(StrictModel):
    code: str                      # non-empty after M-2 text normalization
    message: str
    severity: Literal["blocking", "non-blocking"]
    path: str | None

class AgentReport(StrictModel):
    schema_version: Literal["1.0"]
    task_id: str
    stage: WorkflowStage
    prompt_id: str                 # [0-9a-f]{16}
    verdict: Verdict | None
    summary: str
    findings: list[AgentFinding]
    changed_paths: list[str]       # repo-relative POSIX paths, sorted, unique
    verification_commands_run: list[str]
    blockers: list[str]
```

Binding rules (each violation is a distinct failure finding): `task_id`, `stage`, `prompt_id`
must equal the stored prompt's values exactly; verdict must be non-null exactly for the three
verdict stages; `changed_paths` must be `[]` for `read-only` mode. Extra fields, wrong types,
and malformed values are rejected by the strict model. The report alone proves nothing — see
verification below.

## Sandbox and runner

### Sandbox lifecycle

A sandbox is a snapshot clone in a fresh temporary directory outside the repository:

1. `git clone --quiet --no-local --no-hardlinks file://<repository> <tmp>/sandbox` — read-only
   with respect to the source repository.
2. `git -C <sandbox> checkout --detach <repository_head>` where `repository_head` is the exact
   commit recorded in the prompt's metadata. If that commit is unreachable, the run fails
   (`snapshot_unavailable`) — a prompt rendered against state that no longer exists must not be
   executed against different state.
3. For review stages, an optional `--patch <run_id>` applies a previously stored, re-verified
   scoped-write patch artifact to the sandbox first (so a reviewer reviews the candidate
   change). The patch's own recorded `repository_head` must equal this sandbox's checkout.
4. After the run (success or failure), the sandbox directory is removed; `--keep-sandbox`
   retains it and prints its path for debugging.

`SandboxGit` executes `git -C <sandbox> <args>` for exactly the forms it needs
(`clone` is issued targeting the sandbox parent; then `checkout --detach`, `status`, `add -A`,
`diff --cached --binary`, `apply --check`, `apply`) and refuses to operate on any path that is
not a sandbox directory it created itself (tracked in-process; the class takes no caller-chosen
repository argument). It is a separate class in `agents/sandbox.py`; `GitClient` is untouched.

### Execution protocol

1. Verified-load the prompt from the Milestone 2 store (this alone re-verifies every byte).
2. Resolve the agent by `--agent <name>`; require the requested stage in the agent's `stages`.
3. **Precondition gate (binding decision 7).** Fingerprint the target repository with
   `GitClient.status()`. Require the working tree to be clean — `modified_files`, `staged_files`,
   and `untracked_files` all empty — and require `head` to equal the prompt's recorded
   `repository_head`. A dirty tree fails with `dirty_worktree`; HEAD drift fails with
   `head_drift`. Neither builds a sandbox nor starts an agent. This is what makes the sandbox's
   committed-HEAD checkout a faithful reproduction of the working-tree-derived evidence the
   prompt embeds.
4. Build the sandbox as above (clone + `checkout --detach <repository_head>`).
5. `subprocess.run([executable, *args], cwd=sandbox, stdin=prompt_markdown_bytes,
   capture_output=True, timeout=timeout_seconds, start_new_session=True, env=scrubbed)` where
   `scrubbed` contains exactly `PATH`, `HOME`, `LANG`, `LC_ALL` copied from the parent (when
   set) and nothing else. On timeout the whole process group is killed (`os.killpg`) and the
   run fails with `agent_timeout`.
6. Classify failures in order: `agent_timeout`, `agent_nonzero_exit`,
   `agent_stdout_not_utf8`, `agent_report_invalid` (JSON/schema/duplicate keys),
   `agent_report_mismatch` (binding rules). stdout and stderr are always captured and stored
   exactly (see Run artifacts); stderr is never parsed.
7. Fingerprint the target repository again with `GitClient.status()`: any difference between the
   before/after `GitStatus` models fails the run with `repository_mutated` regardless of agent
   mode. Because step 3 already required a clean tree at the recorded HEAD, the expected
   after-state is identical to the before-state, so this is an exact-equality check.

### Independent claim verification

Performed by the engine, in the sandbox, after a schema-valid report; result is a standard
`CheckResult` (`check_name="agent-run"`):

1. **Actual change set:** `git -C sandbox add -A` then `git -C sandbox diff --cached
   --binary` (the patch) and `git -C sandbox status --porcelain` (the path set), computed by
   the engine. For `read-only` mode the actual change set must be empty.
2. **Claim equality:** actual changed path set must equal `report.changed_paths` exactly —
   under-claiming and over-claiming both fail (`claim_mismatch`).
3. **Scope containment:** every actual changed path must be inside the prompt's rendered
   `allowed_paths` (equal to an entry, or strictly beneath an entry treated as a directory
   prefix). Violation: `scope_violation`.
4. **Protected paths:** no actual changed path may match `never_stage` or `never_commit`
   patterns (`protected_path_violation`).
5. **Verdict extraction:** for verdict stages, `report.verdict` is the single authoritative
   token (the schema already forbids hedging; prose is not scanned).
6. **Verification commands:** the engine re-executes the stage's verification commands in the
   sandbox. It does **not** parse the rendered Markdown to recover them (those rendered lines
   are Bash source using ANSI-C `$'\xHH'` quoting that only `bash` interprets, and they are, as
   in Milestone 2, inert human/agent-facing text). Instead a single pure function
   `verification_argv(conda_environment) -> list[list[str]]` in `agents/verification.py` is the
   one source of truth, returning the exact argv lists:

   ```python
   [
       ["conda", "run", "-n", conda_environment, "git", "status", "--short", "--branch"],
       ["conda", "run", "-n", conda_environment, "git", "diff", "--check"],
       ["conda", "run", "-n", conda_environment, "pytest", "-p", "no:cacheprovider"],
   ]
   ```

   Each is run via `subprocess.run(argv, cwd=sandbox, capture_output=True, shell=False,
   timeout=timeout_seconds, start_new_session=True, env=verify_env)`, in order, requiring exit 0
   (`verification_command_failed` otherwise, carrying the argv and exit code). `shell=False`
   means no shell quoting is ever involved, so the `conda_environment` value is passed as one
   exact argv token with no escaping question. `verify_env` is the scrubbed env plus
   `PYTHONPATH=<sandbox>/src` prepended, so `import ai_workflow_engine` resolves to the
   **sandbox's** source rather than whatever an editable install points the conda env at —
   otherwise `pytest` could exercise the original repository instead of the snapshot. A test
   pins that `verification_argv(env)` rendered through the M-2 shell escaper and template grammar
   reproduces the template's `## Verification commands` lines byte-for-byte, so the executed
   commands and the displayed commands are provably the same commands. The push stage never
   reaches this step (binding rules exclude it), so `git push` is never among them.

### Run artifacts

Every completed run — PASS or FAIL — is stored (unless `--no-store`) under:

```text
~/.ai-workflow-engine/workflow-runs/agent-runs/<project_id>/<task_dir>/<stage>/<run_id>.json
~/.ai-workflow-engine/workflow-runs/agent-runs/<project_id>/<task_dir>/<stage>/<run_id>.patch
```

`<task_dir>` uses the same collision-free `<readable>-<task_hash16>` scheme as the state store.
The sidecar is the closed `AgentRunRecord`: schema_version `"1.0"`, the binding fields, agent
name/mode/executable/args/timeout, prompt_id and `repository_head`, the full `AgentReport` (or
the failure classification when no valid report exists), exit code, the verification
`CheckResult` (timestamp field removed, exactly as M-2 canonicalizes checks), the patch SHA-256,
and the applied-patch base head. To keep every stored digest re-verifiable from the record
alone, the **exact** captured bytes are stored, not a lossy decode:

- `stdout_b64` / `stderr_b64` — standard base64 (`base64.b64encode`) of the raw captured bytes,
  exactly reproducing them on decode;
- `stdout_sha256` / `stderr_sha256` — SHA-256 of the raw bytes (i.e. of `b64decode(field)`).

`run_id` is the first 16 hex characters of the SHA-256 of the record's canonical JSON with the
`run_id` field itself excluded from the hashed payload; the `.patch` member holds the exact
patch bytes (empty file for read-only runs). Storage uses the Milestone 2 no-clobber protocol
(record first, patch second, byte-compare on collision). Load decodes `stdout_b64`/`stderr_b64`,
recomputes both SHA-256 digests and requires equality, recomputes the patch digest and `run_id`,
and rejects any mismatch as tampering. Because the digested bytes are themselves stored, every
digest in the record is recomputable at load time — there is no unverifiable field.

### Agent CLI

```text
workflowctl agent run --config <file> --agent <name> --task-id <id> --stage <stage>
                      --prompt-id <16hex> [--patch <run_id>] [--store/--no-store]
                      [--keep-sandbox] [--output human|json]
```

`agent run` exits 0 only when execution and verification both PASS; verification FAIL exits 1
(artifact still stored, so failures are auditable); infrastructure errors exit 2 via
`_protected`. Success output mirrors the prompt commands: labeled human block (run id, stage,
verdict or `(none)`, stored paths) or canonical-JSON `AgentRunSuccess`.

There is no `agent apply` verb in Milestone 3. A scoped-write run's verified patch is produced
and stored, but applying it to the target working tree is Milestone 4's controlled-change
responsibility (binding decision 2); it consumes the stored, re-verifiable `AgentRunRecord` +
`.patch` pair. Keeping application out of this milestone means Milestone 3 introduces no
writable-Git surface against the real repository at all — only the read-only `GitClient` (for
fingerprinting) and the sandbox-only `SandboxGit`.

## State/agent integration

`state record --agent-run <run_id>` loads and re-verifies the named artifact and requires its
task/stage to match the event being recorded, its verification status to be PASS, and — for
verdict events — the recorded verdict to equal the report's verdict exactly. Recording a
verdict different from a cited agent run's verdict is a `verdict_evidence_mismatch` failure.
Events without `--agent-run` remain legal (human-performed stages).

## Exact planned files

- add `src/ai_workflow_engine/workflow/events.py`
- add `src/ai_workflow_engine/workflow/transitions.py`
- add `src/ai_workflow_engine/workflow/event_store.py`
- add `src/ai_workflow_engine/agents/__init__.py`
- add `src/ai_workflow_engine/agents/models.py`
- add `src/ai_workflow_engine/agents/sandbox.py`
- add `src/ai_workflow_engine/agents/runner.py`
- add `src/ai_workflow_engine/agents/verification.py`
- add `src/ai_workflow_engine/agents/artifacts.py`
- modify `src/ai_workflow_engine/models.py`
- modify `src/ai_workflow_engine/cli.py`
- modify `src/ai_workflow_engine/prompt/models.py`
- modify `src/ai_workflow_engine/prompt/context.py`
- modify `src/ai_workflow_engine/prompt/renderer.py` (bump the `PromptMetadata` construction from
  `schema_version="1.0"` to `"1.1"`; found missing from this list by plan review — it is the
  third and last hardcoded construction site of the bumped literal, alongside `context.py` and
  `cli.py`)
- modify `docs/configuration.md`
- modify `docs/architecture.md`
- modify `examples/amozesh_konkur.yaml`
- modify `self-governance.yaml`
- add `tests/test_workflow_events.py`
- add `tests/test_workflow_transitions.py`
- add `tests/test_workflow_event_store.py`
- add `tests/test_agent_models.py`
- add `tests/test_agent_sandbox.py`
- add `tests/test_agent_runner.py`
- add `tests/test_agent_verification.py`
- modify `tests/conftest.py`
- modify `tests/test_cli.py`
- modify `tests/test_config.py`
- modify `tests/test_prompt_context.py`
- modify `tests/test_prompt_renderer.py`
- modify `tests/test_prompt_store.py`
- modify `tests/test_prompt_validator.py`

`workflow/__init__.py`, `workflow/state.py`, and `workflow/invariants.py` are intentionally
absent from this list: the package `__init__.py` is empty and stays so, and the two pre-existing
Milestone 1 helpers are untouched (N8).

## Testing strategy and acceptance coverage

All agent tests use stub executables written by the tests themselves (small Python scripts made
executable in `tmp_path`). Coverage must include:

- **State:** every transition-table row accepted, every off-table transition rejected; verdict
  required/forbidden per stage; terminal-task rejection; contiguity, chain-digest, duplicate-key,
  and file-name/sequence-mismatch corruption cases; `state_identity_mismatch` when an event's
  embedded `project_id`/`task_id` differs from the address; **collision-free addressing — two
  distinct task IDs that share a sanitized `<readable>` (e.g. `a/b` and `a_b`) must land in
  different `task_dir`s and never conflate**; idempotent identical concurrent appends and
  `sequence_conflict` on differing concurrent appends (real threads, as in M-2 store tests);
  empty-history behavior; full CLI human/JSON/exit-code contracts.
- **State/agent-run integration (N7):** `state record --agent-run <id>` loads and re-verifies
  the artifact and requires task/stage match and verification PASS; a verdict event whose
  verdict differs from the cited run's report verdict fails with `verdict_evidence_mismatch`; an
  event citing a FAIL-verification run is rejected; `--prompt-id`/`--agent-run` are recorded on
  the event; events without `--agent-run` (human-performed) remain legal.
- **Config:** agents section round-trip; duplicate names, relative executable, empty stages,
  mode/stage incompatibility, `push` assignment, timeout bounds all rejected; canonical
  serialization ordering; prompt-payload sensitivity — identical inputs except one agents field
  produce different prompt IDs; schema_version `"1.1"` at all three construction sites
  (`context.py`, `renderer.py`, `cli.py`); store `load()` rejects a `"1.0"` sidecar.
- **Precondition gate:** `agent run` fails with `dirty_worktree` when the target tree has any
  modified/staged/untracked file, and with `head_drift` when live HEAD differs from the prompt's
  `repository_head`, in both cases before any sandbox or agent process is created.
- **Runner:** honest stub passes end-to-end (read-only and scoped-write); timeout stub is
  killed with `agent_timeout`; nonzero-exit, non-UTF-8 stdout, malformed JSON, duplicate JSON
  keys, extra report fields, binding mismatches (task/stage/prompt-id), verdict on non-verdict
  stage and missing verdict on verdict stage; env scrubbing proven by a stub that prints its
  environment; stdout/stderr stored exactly and their digests recompute from the stored base64;
  stderr never parsed; repository before/after fingerprint failure (`repository_mutated`) when a
  stub mutates the real repository via an absolute path.
- **Verification:** lying stubs — claims fewer paths than changed, claims more, exact match
  passes; out-of-scope write; protected-path write; read-only agent that writes; verification
  command failure (stub makes the sandbox `pytest` argv exit nonzero); patch bytes exactly
  reproduce the sandbox diff; **`verification_argv(env)` rendered through the M-2 shell escaper
  and template grammar reproduces the template's `## Verification commands` lines byte-for-byte**
  (proving executed argv == displayed commands); `PYTHONPATH=<sandbox>/src` makes `pytest`
  exercise sandbox source (a deliberately altered sandbox source file changes the outcome).
- **Sandbox:** clone/checkout at recorded head; `snapshot_unavailable` on missing commit;
  sandbox removed on success and on failure; `--keep-sandbox` retention; `--patch` pre-
  application including head-mismatch rejection; `SandboxGit` refuses non-sandbox directories.
- **Artifacts:** run-id determinism (identical record → identical id), no-clobber collision
  semantics, tamper rejection on every field class (record bytes, patch bytes, stdout/stderr
  base64 vs digest, id).
- **Regression:** `GitClient.READ_ONLY_FORMS` unchanged; no Milestone 3 module performs any
  writable-Git operation on the target repository (only read-only `GitClient` fingerprinting and
  sandbox-only `SandboxGit`); existing 448 tests still pass (modulo the regenerated
  prompt-payload fixtures, whose template-byte pins must be byte-identical).

## Versioning

Milestone 3 closes at version `0.2.0` (SemVer minor: backward-compatible CLI additions plus the
documented prompt-artifact schema break, acceptable pre-1.0), with `docs/PROJECT_STATE.md` and
`pyproject.toml` bumped together so the `version` governance fact stays consistent.

## Plan Review disposition

This plan contains no open design question. Implementation (T-302..T-305) begins only after a
fresh, independent Plan Review — one with no memory of round 1's findings, per
`docs/AGENT_PROTOCOL.md` — approves these contracts.
