# AUTO-010 — Real Non-Interactive Provider Runtime — Completion Report

| Field | Value |
|---|---|
| **Stage** | AUTO-010 |
| **Title** | Real Non-Interactive Provider Runtime |
| **Branch** | `feature/auto-010-provider-runtime` |
| **Baseline** | `main` == `origin/main` == `5d1b6be516519daf640d45724c910a114fd28104` |
| **Contract** | `docs/workflow-automation/stage-prompts/AUTO-010.md` |
| **Date** | 2026-07-31 |
| **Status** | Implemented · **partially validated** — see §15 and §19 |

> **Superseded by §24: the stage is now fully validated — `PARTIALLY_VALIDATED` is removed.**
> Read §22, §23, and §24 for the current status; the `Status` field above and §15 below record the
> *first* validation pass and are deliberately left exactly as first written, because the failed
> attempt and its diagnosis are part of the record.
>
> * **§22** — the Codex failure was a credential-*selection* error, not an expired account: the
>   first pass ran Codex against the default credential store instead of the authenticated one.
> * **§23** — read-only host diagnosis of the one remaining blocker: Ubuntu 24.04's
>   `apparmor_restrict_unprivileged_userns` denied bubblewrap's `uid_map` write and `CAP_NET_ADMIN`.
> * **§24** — after the Human Owner's scoped AppArmor correction: **25 live tests pass, 0 skipped**;
>   Claude and Codex are each live-validated on all ten acceptance criteria.

## 0. Verdict in one paragraph

The engine can now really run Claude Code non-interactively, and that claim is backed by live
acceptance tests against the installed CLI, not by mocks. `WorkflowService → ProviderRuntime →
ClaudeCLIProvider / CodexCLIProvider → shared process runner` is in place, all three never-ask
layers are implemented and tested, and the process runner was hardened to actually deliver the
guarantees this stage requires (process-group termination, no controlling terminal, enforced
output ceilings). **Codex is implemented but not live-validated**: the installed CLI's stored
credential is expired, so the eight live Codex tests that need an authenticated session *skip*
with the exact 401 recorded. Per the stage contract, that is reported as a blocked validation
rather than papered over with mocked results, and the stage is presented as **partially
validated**. Three blockers were fixed, all minimal and all documented in §18; six non-blocking
defects are recorded and deferred in §19.

---

## 1. Baseline and governance evidence

Verified before any change:

| Check | Required | Observed |
|---|---|---|
| Branch | `main` | `main` |
| HEAD | `5d1b6be516519daf640d45724c910a114fd28104` | identical |
| `main` == `origin/main` | yes | identical |
| Working tree | clean | clean (`git status --porcelain` empty) |
| `workflowctl verify --config self-governance.yaml` | PASS | **PASS**, all five checks |
| `pytest -q` | 3,151 passing | **3,151 passed in 146.21s** |
| AUTO-008, GOV-AUTO-06, GOV-AUTO-07, AUTO-009 | complete and merged | all `Done`; `git log` shows AUTO-009 merged as `5d1b6be` (PR #9) |

Task-state at baseline: 0 `Current`, 42 `Done`, 6 `Planned` — the `Current` set was empty, so
rule 1's "no other `Current` task" precondition held.

**Registration.** AUTO-010 had never been registered. It was registered and authorized in one act,
recorded in all four governance surfaces the repository requires:

* `docs/TASK_QUEUE.md` — new `## AUTO-010` entry, `Status: Current`;
* `docs/current_task.md` — mirrored;
* `docs/remaining_tasks.md` — mirrored (`AUTO-010 | ... | Current`);
* `docs/workflow-automation/STAGE_REGISTRY.md` — registry row (state `IN_PROGRESS`) plus two
  append-only authorization-log rows (registration/authorization, then initial-start preflight).

A stage contract file was issued at `docs/workflow-automation/stage-prompts/AUTO-010.md`,
following the AUTO-001..AUTO-008 convention (AUTO-009 was the exception that shipped without one).

**Governance after registration:** `workflowctl verify` reports `task-state` PASS (1 `Current`),
`governance` PASS, `registries` PASS (20 stages across 2 registries), `handover` PASS. The `git`
check reports exactly one finding, `upstream_missing`, because the stage branch has no upstream
and pushing is prohibited by the stop condition. This is the same tolerated, stage-inherent state
every prior AUTO stage recorded (AUTO-009 report §9); it clears at publication.

---

## 2. Provider-runtime architecture

```text
WorkflowService.invoke_provider
        │
        ▼
ProviderRuntime.invoke(ProviderRunRequest) -> ProviderRunResult      providers/runtime.py
        │
        ├─ build_provider_prompt(task)        auto-mode contract (never-ask layer 1)
        ├─ select_live_provider(role, config) providers/selection.py — the existing registry
        │
        ▼
ClaudeCLIProvider / CodexCLIProvider          providers/claude_cli.py, providers/codex_cli.py
        │   argv from closed enums; transport-specific report extraction
        ▼
CLIProvider.invoke                            providers/base.py — validate, isolate, run, classify
        │
        ▼
run_provider_process                          providers/base.py — the one and only spawn point
```

**No second provider framework was created.** Everything below `runtime.py` is AUTO-004's, reused:
`ProviderInvocation`, `ProviderReport`, `ProviderFailure`, `ProviderVerdict`, `ProviderResult`,
the environment allowlist, the session-directory layout, the retry classification, and secret
redaction. The runtime owns exactly three things the layer below cannot: the prompt contract, the
target→provider mapping, and the terminal-result contract.

**One module was moved, not duplicated.** `select_live_provider` and the live registry were
extracted verbatim from `providers/__init__.py` into `providers/selection.py`, because
`__init__.py` re-exports `runtime`, and `runtime` needs to select a provider — importing the
package from inside it would be a cycle. The registry's contents, typing, and behaviour are
unchanged, and `agentos_workflow.providers` still re-exports both names, so no existing caller
sees a difference.

**Why the enums live in `config/policy.py`.** Both the configuration schema and the CLI adapters
need `ClaudePermissionMode`/`CodexSandboxMode`. The adapters already import `config.schema`, so
defining the enums in an adapter would make the schema import its own importer, and defining them
anywhere under `providers/` would drag that package's `__init__` — which imports both adapters —
into every configuration load. `config/policy.py` imports nothing from this engine at all.

---

## 3. WorkflowService integration

`WorkflowService` gained exactly one operation:

```python
def invoke_provider(self, request: ProviderRunRequest) -> ProviderRunResult:
    return self._provider_runtime.invoke(request)
```

The public surface is now five names: `status`, `list`, `audit`, `report` (unchanged, still
read-only) and `invoke_provider`. Bounded and asserted structurally:

* **No workflow lifecycle verb was added.** All twelve forbidden verbs — `start`, `authorize`,
  `approve`, `reject`, `resume`, `cancel`, `prepare`, `review`, `implement`, `commit`, `push`,
  `merge` — remain absent, and AUTO-009's parametrized absence test still runs over all twelve.
* **No provider internals are imported.** An AST assertion over `service.py` proves the *only*
  `agentos_workflow.providers.*` import in the module is `agentos_workflow.providers.runtime`.
* **No CLI detail appears.** A second AST assertion proves `service.py` imports no `subprocess`
  and contains no code string literal beginning `--`, nor any naming `claude_cli`/`codex_cli`.
  (Judged over the parsed tree, not the source text: the module docstring discusses subprocesses
  at length, and prose about a subprocess is not a subprocess call.)
* **A provider run cannot transition workflow state.** `ProviderRuntime` holds exactly one
  attribute, a `WorkflowConfig` — no `StateStore`, no `RepositoryLock`, no `WorkflowSession` — and
  a test booby-traps `StateStore.record_transition` and `record_command_execution` for the
  duration of a real invocation; neither is reached.

The AUTO-009 read-only claims survive intact: the four read operations were not touched, and their
mutation-channel booby-trap suite still passes unmodified.

---

## 4. Exact Claude argv

Verified by `provider.argv(session_directory)`, which is the literal vector `invoke` executes:

```text
<claude_cli_executable> --print --output-format json --permission-mode plan
<claude_cli_executable> --print --output-format json --permission-mode dontAsk
<claude_cli_executable> --print --output-format json --permission-mode acceptEdits
```

Observed with the real executable path:

```text
/home/afshin-jian/.local/bin/claude --print --output-format json --permission-mode plan
```

The prompt is **never** in argv; it travels on stdin. The permission mode is passed on every
invocation rather than left to the CLI's default, so the recorded argv states the policy the run
actually used instead of deferring to whatever the operator's settings file happens to say.

## 5. Exact Codex argv

```text
<codex_cli_executable> exec --json --sandbox read-only \
    -c approval_policy="never" \
    --output-last-message <session_directory>/codex-last-message.txt

<codex_cli_executable> exec --json --sandbox workspace-write \
    -c approval_policy="never" \
    --output-last-message <session_directory>/codex-last-message.txt
```

Every element is a provider-owned constant, a value from `CodexSandboxMode`, or a path this engine
constructed. The `-c` override carries one fixed key/value pair; it is not a general configuration
channel, and no caller can reach it.

---

## 6. Exact installed CLI versions

```text
$ claude --version
2.1.220 (Claude Code)

$ codex --version
codex-cli 0.146.0
```

Executables discovered at `/home/afshin-jian/.local/bin/claude` and
`/home/afshin-jian/.nvm/versions/node/v22.22.3/bin/codex`.

**Every flag was verified against these installed binaries, not against documentation.**

From `claude --help` (2.1.220), verbatim:

* `-p, --print` — "Print response and exit (useful for pipes)."
* `--output-format <format>` — "Output format (only works with --print): \"text\" (default),
  \"json\" (single result), or \"stream-json\"".
* `--permission-mode <mode>` — "Permission mode to use for the session (choices: \"acceptEdits\",
  \"auto\", \"bypassPermissions\", \"manual\", \"dontAsk\", \"plan\")".

From `codex exec --help` (codex-cli 0.146.0), verbatim:

* the subcommand's own summary — "Run Codex non-interactively".
* `[PROMPT]` — "If not provided as an argument (or if `-` is used), instructions are read from
  stdin."
* `--json` — "Print events to stdout as JSONL".
* `-s, --sandbox <SANDBOX_MODE>` — "[possible values: read-only, workspace-write,
  danger-full-access]".
* `-o, --output-last-message <FILE>` — "Specifies file where the last message from the agent
  should be written".
* **`codex exec` has no `--ask-for-approval` flag at all** — approval prompting belongs to the
  interactive `codex` command, so non-interactivity is a property of the subcommand.

Additionally observed from a real `codex exec --json` invocation on this host: the event grammar
is dotted `type` names (`thread.started`, `turn.started`, `error`, `turn.failed`); the prompt is
genuinely read from stdin (`Reading prompt from stdin...` on stderr); an empty stdin exits
immediately rather than waiting; and a failed turn exits **1** rather than hanging.

---

## 7. Explicit permission and sandbox policies

| Provider | Field | Permitted | Default | Excluded |
|---|---|---|---|---|
| Claude | `claude_cli_permission_mode` | `plan`, `dontAsk`, `acceptEdits` | `plan` | `bypassPermissions`, `auto`, `manual` |
| Codex | `codex_cli_sandbox_mode` | `read-only`, `workspace-write` | `read-only` | `danger-full-access` |

The exclusions are **structural, not procedural**. Configuration is typed to the enums and the
adapters build argv from them, so there is no configuration file, no request field, and no call
site anywhere in the engine that can name an unrestricted mode. Tests assert both that the value
is absent from the enum and that `WorkflowConfig.model_validate` rejects it, and a further test
asserts no `--dangerously*` flag and no `danger-full-access` appears in any provider's argv.

Both defaults are the least capable mode their CLI offers. An operator acquires write capability
only by writing it down.

`bypassPermissions` was **not** required by any blocker and is not implemented; it is reported and
deferred, exactly as the stage contract directs.

---

## 8. Never-ask enforcement

### Layer 1 — prompt contract

`AUTO_MODE_PROMPT_CONTRACT` states all four required clauses verbatim (each pinned by its own
test), then specifies the required JSON result shape and the rules the engine enforces
mechanically. `build_provider_prompt(task)` puts the contract **first** and the caller's task
second, so a task that tries to countermand the contract — including one assembled from untrusted
target-repository content — is read as work to be done, after the rules.

The contract is not optional: `ProviderRunRequest` has **no `prompt` field**, only `task`. A
caller cannot express a provider prompt that lacks the contract. This is asserted both on the
dataclass fields and at the process boundary, where a stub echoes back the prompt it actually
received on stdin and the test finds the clauses in it.

### Layer 2 — mechanical non-interactivity

Each property is proven by observing a real child process, not by reading the code:

| Property | Evidence |
|---|---|
| No TTY on any standard stream | child reports `os.isatty(0/1/2)` → `[False, False, False]` |
| No controlling terminal at all | child's `open('/dev/tty')` raises `OSError` |
| Own process group | child's `getpgid(0) != getpgid(getppid())` |
| Exactly one prompt on stdin | child's first `read()` returns the prompt; second returns 0 bytes |
| stdin closed after the prompt | same test — EOF, not a wait |
| Non-interactive CLI flags | §4/§5 argv, verified against `--help` |
| Terminated on timeout | §10 |

`start_new_session=True` is what makes the second row true: the child is detached from this
process's controlling terminal, so a CLI that tries to open `/dev/tty` to prompt a human finds no
terminal rather than finding the operator's.

A dedicated test covers the literal forbidden case — a CLI that blocks reading input — and
confirms it is killed by the timeout and classified `FAILED`/`TIMEOUT`, never left running.

### Layer 3 — structured terminal result

`ProviderRunStatus` is `COMPLETED | COMPLETED_WITH_ASSUMPTIONS | BLOCKED | FAILED`, and every
invocation reaches exactly one. Enforced at two points:

* **During report parsing** (`_report_from_payload`), a provider-caused violation is
  `MALFORMED_OUTPUT`: `blocked` with no `blocking_issues` is rejected; `completed_with_assumptions`
  with no `assumptions` is rejected; an unrecognized status string is rejected rather than coerced
  or treated as absent.
* **On result construction** (`ProviderRunResult.__post_init__`), the same invariants plus
  "`FAILED` carries a typed failure" and "nothing else carries one" raise, because reaching them
  means the engine built a result wrongly.

A report with **no** `status` is `FAILED`, not an inferred success: inferring a terminal status
from the pass/fail verdict would manufacture the exact claim this stage exists to verify. A
question, or any conversational text where a report belongs, is `MALFORMED_OUTPUT` → `FAILED`.
`BLOCKED` is deliberately **not** success (`result.succeeded` is false for it) — it is a
well-formed report that the work was not done.

---

## 9. Typed result and failure behaviour

`ProviderRunResult` carries every field the contract requires: `provider`, `status`, `summary`,
`session_id`, `started_at`, `completed_at`, `exit_code`, `stdout_artifact`, `stderr_artifact`,
`assumptions`, `blocking_issues`, `failure`, plus the parsed `report` so nothing the provider said
is lost at the boundary.

Existing models were reused. The **smallest compatible extension** was made where they could not
express an auto-mode outcome, and only there:

| Extension | Why | Compatibility |
|---|---|---|
| `ProviderReport.status`, `.assumptions`, `.blocking_issues` | the pass/fail `verdict` cannot distinguish "finished", "finished by assuming", "could not safely continue", and "failed", nor a provider that stopped safely from one that stopped to ask | all three optional, defaulting absent/empty — every AUTO-004 report shape still parses |
| `ProviderFailureKind.PROVIDER_REPORTED` | a provider that reports its own failure exited cleanly, so `COMMAND_FAILED` ("exited non-zero") would be a false statement | additive enum member |
| `ProviderExecution.stdout_limit_exceeded`, `.stderr_limit_exceeded` | records that a stream was cut at its ceiling rather than ending on its own | additive, default `False` |

`ProviderRunStatus` lives in `base.py` rather than `runtime.py` because `base` owns the report
schema that parses it. **The AUTO-011 unified `AgentRunResult` was not implemented.**

`started_at`/`completed_at` are timezone-aware `datetime`s from the engine's single timestamp
source and measure the *boundary's* work, so a request refused before spawn still has an honest
interval; the process's own start/completion remain on its `CommandExecution`.

---

## 10. Timeout and process-cleanup evidence

`run_provider_process` moved from `subprocess.run` to `Popen` with `start_new_session=True`, and
`_terminate_process_group` sends **SIGTERM to the child's process group**, waits a 5-second grace,
then sends **SIGKILL to the group unconditionally** — because the direct child exiting politely
says nothing about whether its grandchildren did, and those are exactly what a bounded timeout has
to reclaim.

Evidence:

* **Mocked:** a stub spawns a grandchild (`sleep 300`), records its PID, and sleeps; the timeout
  fires; the test polls until the grandchild PID is gone and asserts it within 15s. It is gone.
* **Live (real Claude):** a slow task with a 5-second timeout returns `FAILED`/`TIMEOUT`, and a
  `/proc` sweep for any process whose environment names this invocation's session directory
  (`AGENTOS_SESSION_DIRECTORY`, inherited by every descendant) returns empty.
* **Suite-wide:** an autouse fixture repeats that sweep after *every* live test.
* **Post-run:** a manual `/proc` sweep for `AGENTOS_SESSION_DIRECTORY` and for `sleep 300`
  found no surviving process. No interactive Claude or Codex process remains running.

A timed-out run reports `exit_code=None` even though termination produced a signal-derived code:
the signal this engine chose is not the CLI's answer, and recording it as one would put a
fabricated result in the audit trail.

---

## 11. Environment-allowlist evidence

Unchanged policy (`build_provider_environment`), now exercised through the runtime:

* **Mocked:** with `allowed_environment_variables: ["AGENTOS_ALLOWED_MARKER"]` and a
  secret-shaped `AGENTOS_FORBIDDEN_TOKEN` set in the parent, the child's `os.environ` contains the
  marker, does **not** contain the forbidden token, and does **not** contain `HOME`.
* **Live (real Claude, `acceptEdits`):** with `AGENTOS_FORBIDDEN_TOKEN` set in the parent and
  absent from the allowlist, the CLI was explicitly asked to report that variable's value. The
  secret appears nowhere in the result summary, the disposable repository's contents, or either
  persisted artifact.
* The live allowlist is `["HOME"]` and nothing else. `HOME` is a deliberate, visible concession —
  both CLIs keep their credential store under it, so a live run without it cannot authenticate —
  and a guard test asserts no credential-shaped variable (`GITHUB_TOKEN`, `GH_TOKEN`,
  `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) is ever added to it.

---

## 12. Session-isolation evidence

Layout is AUTO-004's, unchanged: `<session_root>/<workflow_id>/<provider>/<invocation_id>`,
created `0o700`, with `TMPDIR` and `AGENTOS_SESSION_DIRECTORY` pointed at it.

AUTO-010 additions and evidence:

* `CLIProvider.session_directory()` became public so the runtime can persist artifacts into the
  same directory the process was given, without either layer re-deriving the other's layout.
* The runtime writes `stdout.txt` and `stderr.txt` there, holding the **redacted** text (these
  files persist; the unredacted stdout exists only long enough to be parsed). Writing is
  best-effort: a failure to persist evidence must not turn a successful run into a failed one.
* Codex's `--output-last-message` file is written **inside** the same isolated directory, so two
  concurrent invocations can never read each other's answer.
* Tests: two invocations never share a directory or `session_id`; the two providers get different
  directories within one workflow; a reused `invocation_id` is refused (`PRECONDITION`) rather
  than silently merged; live runs confirm the directory mode has no group/other bits.

---

## 13. Mocked and contract test results

`agentos_workflow/tests/test_provider_runtime.py` — **76 tests, all passing**. Every item the
stage contract enumerates is covered:

| Required proof | Covered by |
|---|---|
| exact provider argv from closed enums | `TestClosedArgvAndPolicy` (parametrized over every enum member) |
| callers cannot inject arbitrary flags | request-field assertion; flag-shaped task travels on stdin and changes nothing; hostile `invocation_id` refused pre-spawn |
| no provider uses `shell=True` | AST assertion over all five provider modules (no `shell=` keyword, no `os.system`/`os.popen`) |
| no provider requests a TTY | `isatty` all false; `/dev/tty` unopenable; own process group |
| prompt bytes sent through stdin | stub echoes the received prompt |
| stdin closed afterward | second `read()` returns 0 bytes |
| timeout terminates the process group | grandchild PID gone after timeout |
| oversized stdout rejected | real child writes past the ceiling → `MALFORMED_OUTPUT` "stdout exceeds" |
| oversized stderr rejected | same for stderr |
| invalid or incomplete JSON rejected | 8-case parametrization, none defaulted |
| duplicate JSON keys rejected | `strict_json_loads` → "duplicate key" |
| secret redaction covers captured errors | secret absent from failure detail *and* persisted artifacts |
| `BLOCKED` with empty blockers rejected | parse-level and construction-level |
| `COMPLETED_WITH_ASSUMPTIONS` with empty assumptions rejected | parse-level and construction-level |
| provider execution cannot transition workflow state | booby-trapped `StateStore` writers; runtime holds only a config; AST import assertion |
| `WorkflowService` delegates through the boundary | delegation recorded; `subprocess.run`/`Popen` booby-trapped; AST import assertions |

**Mocked results are never presented as proof of real CLI operation.** Both the runtime test
module and the live module say so in their docstrings, and the two suites are separated by marker.

---

## 14. Real Claude acceptance results — **PASS**

`pytest -q -m live_cli` → the Claude half is **11 passed** (plus 2 provider-agnostic guard tests
and the executable-discovery tests).

| # | Contract requirement | Result |
|---|---|---|
| 1 | real executable discovered | PASS — absolute path, `--version` returns `2.1.220 (Claude Code)` |
| 2 | runs non-interactively | PASS — exit 0, structured result, no terminal |
| 3 | prompt received through stdin | PASS — a token existing only in the prompt is echoed back |
| 4 | parseable structured output | PASS — envelope unwrapped, report parsed, `report` populated |
| 5 | read-only/planning execution performs no write | PASS — full before/after content digest of the disposable repository is identical; the requested file does not exist |
| 6 | write-enabled mode writes exactly one allowed file | PASS — created set is exactly `{auto-010-live.txt}`, modified set is empty, contents exactly `auto-010` |
| 7 | ambiguous task returns a terminal result rather than waiting | PASS — terminates promptly, never `TIMEOUT` (see note below) |
| 8 | timeout kills the process group | PASS — `FAILED`/`TIMEOUT`; `/proc` sweep finds no survivor |
| 9 | disallowed environment variables unavailable | PASS — secret absent from summary, repository, and artifacts |
| 10 | output and session artifacts persisted correctly | PASS — both artifacts at the expected paths, `session_id` correct, directory mode `0o700` |

**Note on #7, recorded because it is a real observation about model behaviour.** The first run of
this test asserted that an ambiguous task always yields `BLOCKED`/`COMPLETED*`, and it failed: the
same prompt produced, on one invocation, a well-formed `blocked` report with three concrete
blocking issues — including the model's own observation that "this non-interactive session has no
channel to ask the team or user for it" — and on another, output the parser could not read, which
the engine correctly classified as a contract failure. Both terminated promptly. The assertion was
therefore **wrong, not the engine**: it was testing model format compliance rather than the
property the stage requires. It now asserts what AUTO-010 actually demands — that the run reaches
a terminal status, that the failure is never `TIMEOUT`, and that wall-clock time stays well under
the ceiling — and additionally checks the evidence rules whenever a report did parse. The
underlying observation (a model may occasionally violate the output contract) is recorded as
deferred defect **D-5**.

Verbatim excerpt from a live `blocked` result, as evidence that layer 1 works against the real CLI:

```json
{"status": "blocked", "verdict": "fail",
 "summary": "Could not update any configuration value because the repository contains no
             configuration file and no record of the agreed-upon number.",
 "blocking_issues": [
   "Repository contains only a README.md ... no configuration file of any kind exists to update.",
   "No commit history, comments, issues, or other artifacts ... reference a 'team agreement' ...",
   "Task explicitly states the agreed-upon value is not recorded ... and this non-interactive
    session has no channel to ask the team or user for it."]}
```

---

## 15. Real Codex acceptance results — **BLOCKED (not validated)**

**The eight live Codex tests that require an authenticated session did not run.** They skipped.
No mocked result is substituted for any of them, and none of the ten contract requirements for
Codex is claimed as passing.

Exact evidence — the installed CLI's stored credential is expired:

```text
$ codex exec --json --sandbox read-only     (prompt on stdin, in a disposable git repository)
{"type":"thread.started","thread_id":"019fb90b-4ca0-7051-9e3c-ae715d422c7e"}
{"type":"turn.started"}
{"type":"error","message":"Your access token could not be refreshed. Please log out and sign in again."}
{"type":"turn.failed","error":{"message":"Your access token could not be refreshed. ..."}}
exit code 1

stderr: ERROR codex_login::auth::manager: Failed to refresh token: 401 Unauthorized:
        {"error": {"message": "Could not validate your refresh token. Please try signing in
         again.", "type": "invalid_request_error", "code": "invalid_refresh_token"}}
```

The session-scoped availability probe reproduces this and skips with the cause attached:

```text
SKIPPED [1] .../test_live_providers.py:496: codex could not complete a trivial invocation:
            codex_cli exited 1: Reading prompt from stdin... [401 / invalid_refresh_token]
```

| # | Contract requirement | Result |
|---|---|---|
| 1 | real executable discovered | **PASS** — absolute path, `--version` returns `codex-cli 0.146.0` |
| 2 | `codex exec --json` runs non-interactively | **PARTIAL** — proven to run without a terminal, read its prompt from stdin, emit JSONL, and exit 1 rather than wait; **not** proven to complete a task |
| 3 | read-only sandbox does not modify the repository | NOT VALIDATED (skipped) |
| 4 | workspace-write modifies only the allowed path | NOT VALIDATED (skipped) |
| 5 | no question or approval prompt blocks execution | **PARTIAL** — `codex exec` has no approval flag and the failed run never blocked; not proven for a completing run |
| 6 | ambiguous input returns `BLOCKED` or a safe assumption | NOT VALIDATED (skipped) |
| 7 | timeout kills the process group | NOT VALIDATED (skipped) |
| 8 | environment allowlist works | NOT VALIDATED (skipped) |
| 9 | structured JSON is parsed | NOT VALIDATED (skipped) — see D-2 |
| 10 | session artifacts are isolated | NOT VALIDATED (skipped) |

**Remediation is outside this stage's authority**: it requires a human to run `codex login` on
this host. Once authenticated, `pytest -q -m live_cli` runs the eight tests unchanged — they are
written, collected, and skipping only on the credential gate.

---

## 16. Full repository validation

| Command | Result |
|---|---|
| `pytest -q` | **3,230 passed, 21 deselected** in 151s (baseline 3,151 → **+79**; 21 `live_cli` deselected by default) |
| `pytest -q -m live_cli` | **13 passed, 8 skipped, 3,230 deselected** in 237s — see §14, §15 |
| `ruff check .` | **All checks passed!** |
| `black --check .` | **220 files would be left unchanged** |
| `mypy --strict` | **Success: no issues found in 120 source files** (117 → 120) |
| `pre-commit run --all-files` | **ruff Passed · black Passed · mypy Passed** |
| `workflowctl verify --config self-governance.yaml` | `task-state` PASS · `governance` PASS · `registries` PASS (20 stages) · `handover` PASS · `git` **FAIL: `upstream_missing`** (expected, §1) |

Additional verification:

* **Wheel packaging** — built `ai_workflow_engine-1.0.0-py3-none-any.whl`; it contains
  `agentos_workflow/providers/runtime.py`, `providers/selection.py`, `config/policy.py`, and every
  pre-existing provider module.
* **Imports from outside the repository root** — from `/tmp`, `providers.runtime`,
  `providers.selection`, `config.policy`, and `service` all import cleanly.
* **`workflowctl auto` compatibility** — six help invocations and three real invocations
  byte-compared against a `5d1b6be` worktree: **all nine identical**, including `workflowctl
  --help`. No existing command changed behaviour or output.
* **Target repository never used as a live write target** — `_refuse_engine_repository` raises for
  the engine checkout or anything inside it, and is called on both the disposable-repository path
  and the configured `repository_path`; two guard tests assert it. A post-run search of the
  checkout for `auto-010-live.txt`, `codex-last-message.txt`, and session `stdout.txt` finds
  nothing, and `git status` shows only AUTO-010's own files.
* **Temporary repositories and session directories** — all live write targets are fresh git
  repositories under pytest's `tmp_path`, reclaimed by pytest's standard retention policy. Nothing
  is created inside the engine checkout or in a shared location.
* **No interactive provider process remains** and **no child survives a timeout test** — verified
  by `/proc` sweep (§10).
* **`git diff --check`** — clean.
* **Working-tree changes belong only to AUTO-010** — §17.

---

## 17. Exact files changed

**New (6):**

| File | Lines | Purpose |
|---|---|---|
| `agentos_workflow/providers/runtime.py` | 491 | the public Provider Runtime boundary |
| `agentos_workflow/providers/selection.py` | 63 | live selection registry, extracted verbatim from `__init__.py` |
| `agentos_workflow/config/policy.py` | 63 | the two closed policy enums |
| `agentos_workflow/tests/test_provider_runtime.py` | 982 | 76 mocked and contract tests |
| `agentos_workflow/tests/live/test_live_providers.py` (+ `__init__.py`) | 663 | 21 opt-in live acceptance tests |
| `docs/workflow-automation/stage-prompts/AUTO-010.md` | 145 | stage contract |

**Modified (16):**

| File | Δ | What |
|---|---|---|
| `agentos_workflow/providers/base.py` | +421/−… | `Popen` + process-group termination + bounded capture; `ProviderRunStatus`; report-schema extension; `strict_json_loads`; `unfenced`; public `argv()`/`session_directory()`; per-invocation argv hook |
| `agentos_workflow/providers/codex_cli.py` | +163 | sandbox mode, verified argv, answer-file extraction |
| `agentos_workflow/providers/claude_cli.py` | +71 | permission mode, verified argv |
| `agentos_workflow/providers/__init__.py` | +85/−… | re-exports runtime, selection, and policy names |
| `agentos_workflow/service.py` | +66 | `invoke_provider` and its bounding docstring |
| `agentos_workflow/config/schema.py` | +14 | the two new configuration fields |
| `pyproject.toml` | +13 | `live_cli` marker and default deselection |
| `agentos_workflow/tests/test_providers_base.py` | +51/−… | argv test reads `argv()`; oversize/UTF-8 tests use real children |
| `agentos_workflow/tests/test_providers_cli.py` | +122/−… | verified argv; Codex answer-file and event-stream tests |
| `agentos_workflow/tests/test_providers_isolation.py` | +4/−2 | QA stub answers through Codex's own channel |
| `agentos_workflow/tests/test_service.py` | +8 | approved surface is four reads + `invoke_provider` |
| `docs/workflow-automation/CONFIGURATION_MODEL.md` | +14 | documents the two new fields and the closed-enum rule |
| `docs/TASK_QUEUE.md`, `docs/current_task.md`, `docs/remaining_tasks.md`, `docs/workflow-automation/STAGE_REGISTRY.md` | +99 | governance registration (§1) |

Not touched: the workflow state machine, `workflowctl auto` behaviour or output, Git/GitHub skill
registration, the Orchestrator, the Agents, and every other subsystem.

---

## 18. Blockers fixed

Each prevented real non-interactive execution, had no safe scope-preserving workaround, and was
corrected minimally.

### B-1 — the timeout killed only the direct child, and the child kept a controlling terminal

`run_provider_process` used `subprocess.run(timeout=...)`, which kills the direct child alone. A
model CLI spawns subprocesses (a test run, a language server, a sandbox helper), so a timeout left
grandchildren running, reparented and unowned — the stage explicitly requires "terminate the whole
process group on timeout". The same call also left the child in this process's session, holding
the operator's controlling terminal, which contradicts "run without TTY allocation" and leaves a
`/dev/tty` prompting path open.

**Fix:** `Popen(..., start_new_session=True)` plus `_terminate_process_group` (SIGTERM → 5s grace →
unconditional SIGKILL, to the group). Both properties are now tested. Minimal: no behaviour
outside spawning and terminating changed, and the classification, audit record, and never-raise
contract are identical.

### B-2 — output ceilings were not enforced during capture

`capture_output=True` buffers both streams without limit; the stdout ceiling was checked only
*after* the whole stream was already in memory, and stderr had no ceiling at all. The stage
requires enforced stdout and stderr limits.

**Fix:** two `_BoundedStreamReader` threads that keep at most the ceiling and keep draining past
it (stopping the reads would deadlock the child; discarding would lose evidence), firing a
one-shot callback that reclaims the process group. Added `MAX_PROVIDER_STDERR_BYTES` (1 MiB;
nothing parses stderr). The existing failure kind and detail text for oversized stdout are
preserved, so the pre-existing contract is unchanged.

### B-3 — the Codex adapter could never have parsed a real Codex report

AUTO-004's `CodexCLIProvider._extract_report_payload` took "the last decodable JSON object on
stdout", with a comment noting the flags were to be confirmed against a live CLI in AUTO-007 —
which never happened. Against the real `codex exec --json`, the last object is always an event
envelope (`{"type":"turn.completed"}` / `{"type":"turn.failed",...}`), never the report. The
adapter would have read an envelope as a report and failed every real invocation.

**Fix:** read the final message from the file named by `--output-last-message` (a flag verified
present in `codex exec --help`), inside this invocation's own session directory, with a narrow
fallback that accepts only an `item.completed` event whose item is an `agent_message`. The
fallback is explicitly **unverified against a successful live run** and is recorded as D-2.

---

## 19. Non-blocking defects deferred

None of these was fixed.

### D-1 — the installed Codex CLI's credential is expired — `REQUIRED`

401 `invalid_refresh_token` (§15). Blocks all live Codex acceptance validation and therefore
leaves AUTO-010 partially validated. Not a code defect: it needs a human to run `codex login` on
this host. **Impact:** the Codex half of this stage's central claim is unproven. **Defer to:** a
human credential action, after which `pytest -q -m live_cli` validates it with no code change.

### D-2 — the Codex JSONL fallback is unverified against a successful run — `REQUIRED` (before Codex is trusted)

The primary answer-file channel and the fallback are both unexercised by a *completing* Codex run,
because of D-1. The event grammar the fallback matches was derived from a real (failing)
invocation's output and from strings in the installed binary, not from an observed success.
**Impact:** Codex report extraction may need adjustment on first authenticated use. **Defer to:**
the same session that resolves D-1.

### D-3 — `ProviderReport` now carries two overlapping outcome axes — `RECOMMENDED`

`verdict` (pass/fail) and `status` (four terminal states) coexist, and the auto-mode contract asks
providers for both. They answer genuinely different questions (§8), but the overlap is a seam.
**Impact:** conceptual only; both are validated and neither is inferred from the other.
**Defer to:** AUTO-011's unified agent result, which is the stage chartered to collapse them.

### D-4 — persisted provider artifacts have no reader and no audit linkage — `FUTURE`

The runtime writes `stdout.txt`/`stderr.txt` per invocation, but nothing reads them back, and no
audit record links a provider run to a workflow. This is deliberate — AUTO-010 implements no
workflow lifecycle — but it means the evidence is currently write-only. **Impact:** an operator
must find artifacts by path. **Defer to:** the stage that wires provider runs into the audit trail.

### D-5 — a model may violate the output contract, and the engine's only response is to fail the run — `FUTURE`

Observed once live (§14, note): the same prompt produced a valid `blocked` report on one
invocation and unparseable output on another. The engine classifies the latter correctly as
`MALFORMED_OUTPUT`/`FAILED`, which is right for this stage, but there is no retry or
reformat-and-retry policy. **Impact:** an occasional otherwise-successful run is reported as a
contract failure. **Defer to:** the stage that owns provider retry/repair policy (`FAILURE_
RECOVERY.md` §1 governs repair attempts; this is a distinct, narrower case).

### D-6 — AUTO-009's six deferred defects (D1–D6) remain deferred — `OPTIONAL`/`FUTURE`

Confirmed untouched: `STAGE_REGISTRY.md` §1 and §6 wording, `cli_auto`'s restated `OutputFormat`
and deferred imports (**D3 was not needed** — no CLI command was added, §20), the unread Skill
`audit.jsonl`, `agentos_workflow/tests/` shipping inside the wheel, and the empty
`config/__init__.py`. `pyproject.toml` was modified for the `live_cli` marker only, which does not
touch AUTO-009's D5 packaging finding.

---

## 20. Proof that no successor behaviour was implemented

| Prohibited | Evidence |
|---|---|
| Preparation / Reviewer / Implementer Mode | no such module, class, or command exists |
| workflow authorization, approval, approval timeouts | none added; `WorkflowService` still has none of the twelve forbidden verbs (parametrized test) |
| Telegram, daemon, task scheduling | no dependency, module, or configuration field |
| workflow start / resume / cancel | absent, asserted |
| Codex direct correction, Claude–Codex orchestration | the runtime invokes exactly one provider per request and holds no cross-provider state |
| Git commit / push / PR / CI polling / merge / branch cleanup | no Git or GitHub call anywhere in the new code; no commit, push, PR, or merge performed |
| Python governance closeout, shell-script retirement | `scripts/` untouched |
| AUTO-011 unified agent result | no `AgentRunResult`; extensions limited to §9's three, each justified |
| AUTO-012 approval policy | absent |
| workflow state-machine change | `orchestrator/` untouched; no blocker required one |
| Git/GitHub skill registration | `skills/` registration untouched |
| existing `workflowctl auto` behaviour/output | nine invocations byte-identical to baseline (§16) |
| **a second AgentOS sub-application or new CLI command** | **none added** — the runtime is proven by tests and the service, exactly as the contract preferred, which is also why AUTO-009's D3 stayed deferred |

---

## 21. Proposed commit and publication plan

**Nothing has been committed, pushed, merged, or opened as a PR.** The complete diff is in the
working tree on `feature/auto-010-provider-runtime` for Human Owner inspection.

Recommended commit message:

```text
feat(providers): add the real non-interactive Provider Runtime for Claude and Codex (AUTO-010)
```

Proposed closeout sequence, **all of it requiring explicit Human Owner authorization**:

1. Human Owner reviews this report and the diff, with particular attention to §15 (Codex is not
   live-validated) and §18 (three blockers fixed inside the provider process runner).
2. Decide the stage's disposition given partial validation — either accept it as partially
   validated with D-1/D-2 recorded, or restore Codex credentials first and re-run
   `pytest -q -m live_cli` to complete §15 before approving.
3. On approval, the closeout commit additionally updates `docs/CHANGELOG.md`,
   `docs/workflow-automation/CHANGELOG.md`, `handover/PROJECT_HANDOVER.md`, and
   `handover/PROJECT_CHECKSUM.md`, and moves the registry row `IN_PROGRESS → COMPLETE` with the
   task `Current → Done`. These were deliberately left for the closeout rather than written now,
   because they record an outcome the Human Owner has not yet decided.
4. Publication: push `feature/auto-010-provider-runtime`; PR and merge only if separately
   authorized. The `upstream_missing` finding in `workflowctl verify` clears at the push.
5. AUTO-011 remains unauthorized and must not begin.

**Confirmation:** no commit, push, merge, pull request, branch deletion, stash operation, or
successor-stage work was performed by this session.

---

# 22. Correction addendum — Codex account selection (2026-07-31, append-only)

Sections 0–21 above are unchanged. This addendum supersedes the parts of §0, §11, §15, and §19
that it names, and records why the original conclusion was wrong.

## 22.1 What was actually wrong

**Not an expired account — the wrong account.** §15 reported a `401 invalid_refresh_token` and
concluded the installed Codex CLI's credential was expired. The 401 was real, but the diagnosis
stopped one step short: the engine had allowlisted only `HOME`, so `codex` fell back to its
*default* credential store (`$HOME/.codex`), which does hold a stale token. The host also has a
second, authenticated store, and nothing in the first validation pass ever pointed Codex at it.

The same blind spot silently affected the Claude results, which is worth stating plainly even
though they passed: with only `HOME` allowlisted, Claude also used its default store. It happened
to be authenticated, so §14's results were valid — but they validated whichever account the
default store held, not a deliberately selected one. Both providers now select their account
explicitly.

This was a **direct AUTO-010 blocker**: real Codex validation is an explicit acceptance criterion
of this stage, so correcting it belongs here and not to a successor.

## 22.2 Why `codexA` / `claudeA` cannot be the configured executables

The host defines:

```bash
alias codexA='CODEX_HOME="$CODEX_HOME_A" codex'
alias claudeA='CLAUDE_CONFIG_DIR="$CLAUDE_CONFIG_DIR_A" command claude'
```

These are **shell aliases**, not executables. They are unusable as `codex_cli_executable` /
`claude_cli_executable`, and deliberately so:

* an alias exists only inside an interactive shell's own expansion, and this engine spawns with
  `shell=False` and a fixed argv — there is no shell in the path to expand it;
* `shutil.which("codexA")` returns nothing, because no such file exists;
* configuring one would therefore not "work differently", it would fail at spawn.

A test asserts exactly this rather than describing it: pointing the configuration at an alias name
produces a `SPAWN_FAILED` result. Making an alias work would have required `shell=True` or an
`env NAME=value …` wrapper in argv, both of which this stage forbids and neither of which is
present.

What the alias *does* is set one environment variable. That is already expressible.

## 22.3 The correct model: real executable + allowlisted environment

```text
executable: codex        environment: CODEX_HOME        = <account's store>
executable: claude       environment: CLAUDE_CONFIG_DIR = <account's store>
```

Account selection uses the **existing** provider environment allowlist and nothing else. The
operator sets each CLI's own credential-store variable in the engine's environment and names it in
`allowed_environment_variables`; `build_provider_environment` forwards it by name, as it forwards
any allowlisted variable. Consequences worth stating:

* **No production code changed for this correction.** The mechanism already existed; the first pass
  simply did not use it. The only source changes in §22 are tests.
* **No account path is hard-coded anywhere** — not in the engine, not in the test suite. The live
  suite maps `CODEX_HOME ← $CODEX_HOME_A` and `CLAUDE_CONFIG_DIR ← $CLAUDE_CONFIG_DIR_A`, reading
  both values from the environment at run time. The engine knows nothing of the `*_A` convention;
  translating "account A" into a store location happens outside it, once.
* **Every invariant is preserved:** `shell=False`, fixed argv, closed permission/sandbox enums, no
  command strings, no alias expansion, no shell configuration sourced, no TTY, prompt on stdin,
  explicit timeout, process-group cleanup. The effective argv is byte-identical to §4 and §5 —
  selection is invisible to it.
* **The allowlist widens by exactly one name per provider, never by a category.** `CODEX_HOME` and
  `CLAUDE_CONFIG_DIR` are *locations*, not credentials; no token-shaped variable is ever added, and
  a guard test asserts that.

## 22.4 Tests added

Ten deterministic tests in `TestAccountSelection`
(`agentos_workflow/tests/test_provider_runtime.py`), covering each required proof:

| # | Required proof | Test |
|---|---|---|
| 1 | executables remain the real binaries | configured and effective argv[0] basenames are exactly `claude` / `codex` |
| 2 | alias names are not required or resolved | no provider or config module names `codexA`/`claudeA`; configuring an alias yields `SPAWN_FAILED` |
| 3 | `CODEX_HOME` passed only when allowlisted | present with it, absent without it (observed in the child's own environment) |
| 4 | `CLAUDE_CONFIG_DIR` passed only when allowlisted | same, parametrized; and allowlisting one does not admit the other |
| 5 | arbitrary variables still removed | with a store selected, the child's environment is still a subset of {store, PATH, LC_ALL, LANG, TMPDIR, AGENTOS_SESSION_DIRECTORY}; `GITHUB_TOKEN` absent |
| 6 | secret values not written to reports or logs | an allowlisted secret-shaped value appears in neither the result, the failure, nor either persisted artifact |
| 7 | selection needs no `shell=True` | AST assertion that the `Popen` call passes no `shell` keyword at all |
| 8 | argv has no alias wrapper or inline assignment | argv[0] is the CLI; no `env`/`sh`/`bash`; no `NAME=value` element |

Plus four live guard tests (aliases are not executables; selection is environment-only; no account
path is hard-coded in the suite; the selection actually took effect), and one test pinning the
Codex parser to **verbatim captured output from a real authenticated run** (§22.6).

## 22.5 Real Codex acceptance results — **9 of 10 validated**

Authentication probe through the real Provider Runtime, before anything else: **passed**. Then the
eight previously-skipped tests ran unchanged apart from the corrected account environment.

`pytest -q -m live_cli` → **24 passed, 1 skipped**.

| # | Contract requirement | First pass | Now |
|---|---|---|---|
| 1 | real executable discovered | PASS | **PASS** |
| 2 | `codex exec --json` runs non-interactively | PARTIAL | **PASS** — completes a real task, exit 0 |
| 3 | read-only sandbox does not modify the repository | skipped | **PASS** (see the caveat in §22.7) |
| 4 | workspace-write modifies only the allowed path | skipped | **SKIPPED** — host cannot run Codex's sandbox (§22.7) |
| 5 | no question or approval prompt blocks execution | PARTIAL | **PASS** |
| 6 | ambiguous input returns `BLOCKED` or a safe assumption | skipped | **PASS** |
| 7 | timeout kills the process group | skipped | **PASS** — `/proc` sweep finds no survivor |
| 8 | environment allowlist works | skipped | **PASS** — forbidden token absent from summary, repository, artifacts |
| 9 | structured JSON is parsed | skipped | **PASS** — answer file read, report parsed |
| 10 | session artifacts are isolated | skipped | **PASS** — both artifacts plus `codex-last-message.txt` in the invocation's own `0o700` directory |

## 22.6 Deferred defect D-2 is resolved

D-2 recorded that the Codex report-extraction path was unverified against a successful live run.
It now is. A real authenticated invocation produced:

```text
{"type":"thread.started","thread_id":"019fb95d-…"}
{"type":"turn.started"}
{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"READY"}}
{"type":"turn.completed","usage":{…}}
```

Three things follow, all now pinned by a test carrying these lines verbatim:

* the primary channel works — `--output-last-message` contained exactly `READY`;
* the JSONL fallback's expected shape is confirmed, not inferred: the final answer is an
  `item.completed` event whose item is an `agent_message` with a `text` field;
* **blocker B-3's diagnosis is confirmed against reality.** The last JSON object on stdout is
  `turn.completed`. AUTO-004's "take the last decodable object" parser would have handed that
  envelope to the report validator on every real Codex run, and could never have worked.

## 22.7 New non-blocking defect

### D-7 — this host cannot run Codex's writable sandbox — `RECOMMENDED` (environmental)

Codex implements `--sandbox workspace-write` with **bubblewrap**, which needs a user namespace and
a loopback interface. This host denies both:

```text
$ bwrap --dev-bind / / --unshare-net true
bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted
```

Reproduced independently of the engine, and independently of this session's own tool sandbox.

**The engine behaved correctly throughout**, which is the important part: it passed
`--sandbox workspace-write`, Codex attempted the write three times, its sandbox refused, and Codex
returned a well-formed `blocked` result naming the exact evidence —

```json
{"status":"blocked","verdict":"fail",
 "summary":"Attempted to create auto-010-live.txt …, but the repository filesystem rejected every
            write attempt and no file was changed.",
 "blocking_issues":["Three apply_patch attempts failed …; diagnostic shell checks also failed
                     because the sandbox reported \"bwrap: loopback: Failed RTM_NEWADDR:
                     Operation not permitted\"."]}
```

— which is the never-ask contract working exactly as designed under a real environmental failure.

The test now **skips with that precise reason** rather than asserting a weaker condition.
Accepting "no file was created" as a pass would have made it unfalsifiable: a Codex that had
genuinely stopped writing would look identical to one whose sandbox was unavailable. **Impact:**
requirement 4 is unvalidated on this host and needs a re-run where bubblewrap can construct a
namespace. **Defer to:** a live run on such a host; no code change is anticipated.

**Caveat on requirement 3, stated because it would otherwise overclaim:** on a host where no write
can succeed in any mode, "the read-only sandbox modified nothing" is weaker evidence than it
appears. The workspace-write test is what distinguishes refusal from impossibility, and it is the
one that skipped. This is noted in the test itself, not only here.

## 22.8 Revised validation status

| Command | Result |
|---|---|
| `pytest -q` | **3,241 passed, 25 deselected** (was 3,230 / 21; +11) |
| `pytest -q -m live_cli` | **24 passed, 1 skipped, 3,241 deselected** |
| `ruff check .` · `black --check .` · `mypy --strict` | clean · clean · **120 source files, no issues** |
| `pre-commit run --all-files` | ruff Passed · black Passed · mypy Passed |
| `workflowctl verify --config self-governance.yaml` | four content checks PASS; `git` FAIL `upstream_missing` only |

**Status: implemented; Claude fully live-validated; Codex live-validated on 9 of 10 acceptance
criteria.** The `PARTIALLY_VALIDATED` conclusion of §0 is **narrowed but deliberately not
removed**, because one required Codex acceptance test did not pass — it skipped on a host
limitation (D-7). The original condition for removing it was that *every* required Codex live test
pass, and that is not yet true. It becomes true on a host where bubblewrap can run, with no code
change.

D-1 ("credential expired") is **withdrawn as misdiagnosed** and replaced by this addendum: the
default store's token is indeed stale, but the engine simply should not have been using that store.
D-2 is **resolved** (§22.6). D-3 through D-6 remain deferred and untouched. No unrelated defect was
fixed, and AUTO-011 was not begun.

## 22.9 Files changed by this correction

| File | What |
|---|---|
| `agentos_workflow/tests/live/test_live_providers.py` | account selection fixture, widened allowlist, Codex write-sandbox precondition, four guard tests |
| `agentos_workflow/tests/test_provider_runtime.py` | `TestAccountSelection` (10 tests) |
| `agentos_workflow/tests/test_providers_cli.py` | parser pinned to verbatim real Codex output |
| `docs/reports/workflow-automation/AUTO-010-completion-report.md` | this addendum |

**No production module was modified by this correction.** The engine already supported account
selection; the first validation pass simply failed to use it. The stop condition is unchanged: no
commit, no push, no PR, no merge.

---

# 23. Host diagnosis for D-7 — why bubblewrap cannot create a namespace (2026-07-31, append-only)

Strictly read-only investigation. No system setting was changed, no `sudo` mutation was performed,
the Codex sandbox was not weakened, `danger-full-access` was not used, and the live acceptance test
was not altered. D-7 remains a **skip**, not a pass.

## 23.1 The exact blocker

Ubuntu 24.04's unprivileged-user-namespace restriction is active, and **`bwrap` is the one
userns-dependent binary on this host with no AppArmor profile to exempt it.**

The chain, each link evidenced below:

1. `/usr/lib/sysctl.d/10-apparmor.conf` sets `kernel.apparmor_restrict_unprivileged_userns = 1`.
2. Under that setting, when an *unconfined* process creates a user namespace, AppArmor transitions
   it into the built-in restrictive `unprivileged_userns` profile.
3. That profile begins `audit deny capability,` and its file rules cannot resolve the (by then
   mount-namespace-disconnected) `/proc/<pid>/uid_map`.
4. `bwrap` 0.9.0 is **not** setuid (`-rwxr-xr-x root root`) and carries **no file capabilities**
   (`getcap` returns nothing), so it depends entirely on unprivileged user namespaces.
5. The `bubblewrap` package ships **no** AppArmor profile, and none exists in `/etc/apparmor.d/`.

## 23.2 Evidence

Kernel audit records the transition and both denials verbatim:

```text
apparmor="AUDIT"  operation="userns_create" class="namespace"
                  info="Userns create - transitioning profile"
                  profile="unconfined" comm="bwrap" requested="userns_create"
                  target="unprivileged_userns" execpath="/usr/bin/bwrap"

apparmor="DENIED" operation="open" class="file" error=-13
                  info="Failed name lookup - disconnected path"
                  profile="unprivileged_userns" name="proc/<pid>/uid_map"
                  requested_mask="wr" denied_mask="wr" comm="bwrap"

apparmor="DENIED" operation="capable" class="cap"
                  profile="unprivileged_userns" comm="bwrap"
                  capability=12 capname="net_admin"
```

Those two denials are exactly the two error messages observed:

| Denial | Resulting message |
|---|---|
| `open … proc/<pid>/uid_map` `wr` | `bwrap: setting up uid map: Permission denied` |
| `capable … net_admin` | `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted` |

Namespace *creation* itself succeeds; only the mapping and the capability are refused:

```text
$ unshare --user true                      -> exit 0
$ unshare --user -- id                     -> uid=65534(nobody) gid=65534(nogroup)
$ unshare --user --map-root-user true      -> write failed /proc/self/uid_map: Operation not permitted
```

So this is not a missing kernel feature. Kernel support is present and enabled:

| Setting | Value |
|---|---|
| `kernel.unprivileged_userns_clone` | `1` |
| `user.max_user_namespaces` | `255498` |
| `kernel.apparmor_restrict_unprivileged_userns` | **`1`** ← the blocker |
| `kernel.apparmor_restrict_unprivileged_unconfined` | `0` |

## 23.3 Scope: host-general, not specific to this execution environment

| Question | Evidence |
|---|---|
| A container? | `systemd-detect-virt` → **none**; no `/.dockerenv`; PID 1 is the real `/usr/lib/systemd/systemd --system` |
| A nested namespace? | `/proc/self/ns/user` = `user:[4026531837]` — the **initial** user namespace; `uid_map` is the full identity map `0 0 4294967295` |
| Sandboxed/filtered? | `Seccomp: 0`, `Seccomp_filters: 0`, `NoNewPrivs: 0`, `/proc/self/attr/current` = `unconfined` |
| Session-specific? | Reproduced identically with this session's own tool sandbox disabled |

**It applies to the host generally** — to any unprivileged user, and to every program that relies on
bubblewrap (Flatpak, Steam, and Codex's `workspace-write` alike). It is not an artifact of how
AUTO-010's tests are run.

## 23.4 Minimal safe correction (for the Human Owner)

Ubuntu's own mechanism for a binary that legitimately needs unprivileged user namespaces is a
named profile in `flags=(unconfined)` mode granting `userns`. The host already carries eight such
profiles — `userbindmount`, `vpnns`, `vdens`, `stress-ng`, `tup`, `msedge`, `loupe`,
`sbuild-distupgrade` — and `bwrap` is simply missing one. Two commands, following that shipped
pattern exactly:

```bash
sudo tee /etc/apparmor.d/bwrap >/dev/null <<'EOF'
# This profile allows everything and only exists to give the
# application a name instead of having the label "unconfined"

abi <abi/4.0>,
include <tunables/global>

profile bwrap /usr/bin/bwrap flags=(unconfined) {
  userns,

  # Site-specific additions and overrides. See local/README for details.
  include if exists <local/bwrap>
}
EOF

sudo apparmor_parser -r /etc/apparmor.d/bwrap
```

Verify, as the ordinary user and with no `sudo`:

```bash
bwrap --dev-bind / / --unshare-net true && echo "bwrap OK"
```

**Why this does not weaken anything.** It grants `bwrap` the ability to *construct* a namespace —
which is what a bubblewrap sandbox **is**. It does not relax Codex's `--sandbox workspace-write`
policy, does not touch `danger-full-access`, and does not change what the engine passes on the
command line. Without it bwrap cannot sandbox at all; with it, Codex's sandbox works as designed.
The change is persistent across reboots and scoped to one executable.

**The blunt alternative is *not* recommended:** `kernel.apparmor_restrict_unprivileged_userns=0`
would lift the restriction for **every** binary on the host, which is a real, host-wide reduction
in security to fix one program.

## 23.5 Status

Unchanged pending the host correction: **`PARTIALLY_VALIDATED`**. Codex remains live-validated on
9 of 10 acceptance criteria; requirement 4 (`workspace-write` modifies only the allowed path) is
still skipped on a probed precondition and is **not** counted as a pass. AUTO-010 is not finalized.

---

# 24. Final validation — D-7 resolved, stage fully validated (2026-07-31, append-only)

The Human Owner applied the host-side correction recommended in §23.4. This section records the
verification, the previously-blocked result, and the resulting status change. Sections 0–23 are
unchanged.

## 24.1 Human Owner host-side correction

A scoped AppArmor profile for `/usr/bin/bwrap` was installed at `/etc/apparmor.d/bwrap`
(139 bytes, `root:root`, 2026-07-31 22:27), following the `flags=(unconfined)` + `userns,` pattern
Ubuntu already ships for eight other userns-dependent binaries on this host.

This is a **host configuration** change made by the Human Owner. **No engine code, no test, and no
sandbox policy was changed to accommodate it.** In particular: `--sandbox workspace-write` is still
what the engine passes, `danger-full-access` is still unreachable, the acceptance test is
byte-identical to the version that skipped, and its precondition probe was not relaxed — it now
simply reports satisfied.

## 24.2 bwrap verification

```text
$ bwrap --dev-bind / / --unshare-net true
exit=0                       (no output; previously: "loopback: Failed RTM_NEWADDR: …")
```

The suite's own precondition function agrees independently:

```text
_codex_write_sandbox_reason() -> None      # satisfied; no skip
```

## 24.3 Real Codex `workspace-write` result — **PASS**

The last outstanding acceptance criterion, run unchanged:

```text
agentos_workflow/tests/live/test_live_providers.py::TestLiveCodex
    ::test_workspace_write_modifies_only_the_allowed_path      1 passed in 38.99s
```

Against a disposable git repository, with a full before/after content digest: the created set is
exactly `{auto-010-live.txt}` and the modified set is empty. Real Codex, real
`--sandbox workspace-write`, real write, correctly bounded to the one allowed path.

This also retires the §22.7 caveat about requirement 3. Now that a write *can* succeed on this
host, "the read-only sandbox modified nothing" is a genuine refusal rather than an impossibility,
and the read-only/workspace-write pair distinguishes the two as it was designed to.

## 24.4 Live acceptance totals — **25 passed, 0 skipped**

```text
$ pytest -q -m live_cli
25 passed, 3241 deselected in 289.72s
```

Run with `-rs`, which prints a skip summary if any test skips. None did.

| Class | Tests | Result |
|---|---|---|
| `TestLiveClaude` | 9 | **9 passed** — all ten contract requirements of §14 |
| `TestLiveCodex` | 9 | **9 passed** — all ten contract requirements of §15 |
| `TestLiveSuiteGuards` | 7 | **7 passed** — disposable-target and account-selection guards |

Codex's ten acceptance requirements, final state — every one validated against the real CLI:

| # | Requirement | Result |
|---|---|---|
| 1 | real executable discovered | PASS |
| 2 | `codex exec --json` runs non-interactively | PASS |
| 3 | read-only sandbox does not modify the repository | PASS |
| 4 | workspace-write modifies only the allowed path | **PASS** (was the last blocker) |
| 5 | no question or approval prompt blocks execution | PASS |
| 6 | ambiguous input terminates rather than waiting | PASS |
| 7 | timeout kills the process group | PASS |
| 8 | environment allowlist works | PASS |
| 9 | structured JSON is parsed | PASS |
| 10 | session artifacts are isolated | PASS |

## 24.5 Complete AUTO-010 validation suite

| Command | Result |
|---|---|
| `pytest -q` | **3,241 passed, 25 deselected** |
| `pytest -q -m live_cli` | **25 passed, 0 skipped, 3,241 deselected** |
| `ruff check .` | All checks passed |
| `black --check .` | 220 files unchanged |
| `mypy --strict` | Success: no issues in 120 source files |
| `pre-commit run --all-files` | ruff Passed · black Passed · mypy Passed |
| `workflowctl verify --config self-governance.yaml` | `task-state`/`governance`/`registries`/`handover` **PASS**; `git` FAIL with exactly `["upstream_missing"]` |

Additional verification, all re-run:

* **Wheel packaging** — `runtime.py`, `selection.py`, `config/policy.py`, and `service.py` all present.
* **Out-of-tree imports** — clean from `/tmp`; service surface is exactly
  `audit, invoke_provider, list, report, status`.
* **`workflowctl auto` compatibility** — all nine invocations byte-identical to baseline `5d1b6be`.
* **No process leaked** — `/proc` sweep for `AGENTOS_SESSION_DIRECTORY`: none; no `sleep 300`
  grandchild survived the timeout tests.
* **Engine repository never a live write target** — no `auto-010-live.txt` or
  `codex-last-message.txt` anywhere in the checkout; `git diff --check` clean.

## 24.6 Status: `PARTIALLY_VALIDATED` is removed

The condition set for removing it — *every required Codex live test passes* — is now met, with no
test skipped and none weakened to get there.

**Status: implemented and fully validated.** Claude and Codex are both live-validated against the
real installed CLIs on all ten acceptance criteria each.

Defect ledger, final:

| Defect | State |
|---|---|
| D-1 (credential expired) | **Withdrawn** — misdiagnosed; it was account selection (§22) |
| D-2 (Codex parsing unverified live) | **Resolved** (§22.6) |
| D-7 (host cannot run Codex's sandbox) | **Resolved** by the Human Owner's host correction (§24.1) |
| D-3, D-4, D-5, D-6 | Deferred, untouched, none fixed |

Three blockers were fixed during the stage (§18), all inside the shared provider process runner and
all minimal. No unrelated defect was fixed. AUTO-011 was not begun.

## 24.7 Stop condition

Unchanged and observed: **no implementation/closeout commit, no push, no PR, no merge.** The
complete diff remains in the working tree on `feature/auto-010-provider-runtime` awaiting Human
Owner approval. The proposed closeout sequence is §21; the only amendment is that step 2's choice
no longer arises — Codex is fully validated, so the stage can be approved on its merits rather than
accepted as partial.
