# AgentOS Workflow Automation — Open Questions

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Open Questions |
| **Purpose** | Owner-decision register (OD-#) with dispositions and what each question blocks. |
| **Status** | Draft |
| **Version** | 1.6 |
| **Owner** | Documentation & Governance session · Human Owner (dispositions) |
| **Dependencies** | `DECISIONS.md` |
| **Related Documents** | `STAGE_REGISTRY.md` (preconditions cite entries here) |

## Format

Each entry: question, recommendation, disposition, blocked IDs. Entries move to Resolved
append-only; they are never deleted.

**"Blocks stage X's authorization"** means a `STAGE_REGISTRY.md` §3 rule 1 hard gate: X may not
be authorized while the entry is `Open`. **"Blocks/affects stage X's implementation"** (or
"confidence") means X's implementer must resolve the question before X can reach `COMPLETE`
(rule 12) — it does not gate X's authorization or its start, and an entry in this weaker category
being `Open` at authorization time is expected, not a defect.

## Open

### OD-1 — GitHub auto-merge / required-checks read mechanism

- **Question:** Should `enable_automatic_squash_merge` use `gh pr merge --auto --squash`
  (GitHub's native auto-merge, waiting server-side for checks) or should the engine poll
  `read_required_checks` itself and call a plain squash merge once green?
- **Recommendation:** Prefer native GitHub auto-merge where the target repository's branch
  protection supports it, with `read_required_checks` used for the engine's own
  `WAITING_FOR_CHECKS` visibility either way — never as a substitute for GitHub's own merge
  decision.
- **Disposition:** Resolved 2026-07-28, as an AUTO-006 implementation decision (the stage
  contract, `stage-prompts/AUTO-006.md`, already named this resolution). `enable_automatic_squash_merge`
  (`agentos_workflow/skills/git_github.py`) calls only `gh pr merge <number> --auto --squash`;
  `read_required_checks` is implemented and used solely for `WAITING_FOR_CHECKS` visibility, never
  to gate or substitute for GitHub's own merge decision. Full rationale: `DECISIONS.md` DD-37.

### OD-2 — Secret-redaction implementation

- **Question:** Regex-pattern-based redaction of known secret shapes, an allowlist-only
  environment capture (never redaction, just never forwarding), or both together?
- **Recommendation:** Both — allowlist environment forwarding (`SECURITY_MODEL.md` §1) as the
  primary control, plus regex-based output redaction as defense-in-depth for secrets that leak
  into command output despite the allowlist.
- **Disposition:** Resolved 2026-07-27, as an AUTO-003 implementation decision (not a Human Owner
  policy call — `stage-prompts/AUTO-003.md` names this as the question AUTO-003 itself resolves,
  the same posture DD-10 took for OD-3 under AUTO-002). Both controls are implemented, with an
  explicit primacy ordering: `agentos_workflow/skills/__init__.py::_build_environment` builds every
  subprocess environment from the configured `allowed_environment_variables` allowlist (the primary
  control), and `redact_secrets` applies named, linear-time secret-shape patterns to every string
  leaving a Skill (defense-in-depth). Entropy-based detection was considered and rejected — it
  would flag Git SHAs and content hashes, and a redactor that fires on ordinary output trains
  operators to ignore it. Full rationale: `DECISIONS.md` DD-33.

### OD-3 — Repository lock implementation

- **Question:** A local lock file with PID/heartbeat checking, an OS-level advisory lock
  (`flock`), or both?
- **Recommendation:** A lock file recording the workflow ID and process identity, checked for
  liveness on every command, with an OS-level advisory lock as the actual mutual-exclusion
  primitive underneath it.
- **Disposition:** Resolved 2026-07-26, as an AUTO-002 implementation decision (not a Human
  Owner policy call — `stage-prompts/AUTO-002.md`'s Stage-Specific Notes name this as one of two
  questions AUTO-002 itself resolves). `agentos_workflow/orchestrator/lock.py` uses `flock` alone
  as the sole mutual-exclusion authority; the metadata file is diagnostic-only and no PID
  liveness check is performed against it (a refinement of this entry's recommendation, not a
  verbatim adoption — PID reuse makes liveness-checking a stale PID unsafe). Full rationale:
  `DECISIONS.md` DD-10.

### OD-5 — Final configuration file location/naming

- **Question:** Is `.agentos/workflow.yaml` (per target repository) the final convention, or
  should it be configurable/discoverable differently (e.g. `--config` always required, no
  default path)?
- **Recommendation:** Keep the default path for ergonomics, `--config` override always
  available (`CLI_SPEC.md` §3), matching this repository's own `--config` convention for
  `workflowctl`.
- **Disposition:** Resolved 2026-07-26, as an AUTO-002 implementation decision finalizing DD-02's
  "naming open" parenthetical. `agentos_workflow/config/loader.py` keeps `.agentos/workflow.yaml`
  (relative to `repository_path`) as the default, discovered via `discover_config_path`, with an
  explicit override path always accepted and taking precedence; a missing file at the resolved
  path is a precondition failure, never an assumed default. Full rationale: `DECISIONS.md` DD-11.

### OD-6 — Cancellation semantics once a stage branch carries agent work

- **Question:** Should `CANCELLED` remain reachable only before `IMPLEMENTING`
  (`WORKFLOW_STATES.md` §3), or should a later-stage operator abort also be modeled as
  `CANCELLED` (with cleanup) rather than always becoming `FAILED`?
- **Recommendation:** Keep the current MVP rule (abort after work exists is `FAILED`, preserving
  evidence) unless the Human Owner wants a distinct "human-aborted-with-cleanup" path.
- **Disposition:** Open, low risk. Does not block AUTO-001 or AUTO-002.

### OD-7 — Safe re-authorization policy for baseline-commit drift

- **Question:** Should there ever be a defined, safe way to re-bind an authorization when only
  the baseline commit SHA has advanced (e.g. an unrelated commit landed on the baseline) without
  requiring a full new `authorize` call?
- **Recommendation:** None yet — deliberately left undefined per the requesting policy; drift is
  always a hard stop until this is explicitly resolved.
- **Disposition:** Open. Blocks nothing now; would be a MAJOR change to `HUMAN_AUTHORIZATION_MODEL.md`
  §4 and `WORKFLOW_STATES.md` if ever resolved.

### OD-10 — Five of eight Git/GitHub Skill call sites never forward `allowed_environment_variables`

- **Question:** `GitAgent.create_pull_request`, `GitAgent.read_pull_request_state`,
  `MergeAgent.enable_auto_merge`, `MergeAgent.await_required_checks`, and
  `MergeAgent.confirm_merge` (`agents/git.py`/`agents/merge.py`, AUTO-005) each invoke a `gh`-based
  Skill (`agentos_workflow/skills/git_github.py`, AUTO-006) without passing
  `allowed_environment_variables` at all — only `GitAgent.push_stage_branch` forwards it. Every
  Skill subprocess environment is built from an explicit allowlist and nothing else
  (`SECURITY_MODEL.md` §1; `skills/__init__.py::_build_environment`), so with no allowlisted
  variables reaching these five calls, `gh` has no path to a `GH_TOKEN`/`GITHUB_TOKEN` or a
  readable `$HOME` in a real deployment. Should `agents/git.py`/`agents/merge.py` be amended to
  forward it (mirroring `push_stage_branch`'s existing call), and if so, in which stage?
- **Recommendation:** Add `allowed_environment_variables=self._allowed_environment_variables` to
  the five call sites named above; give `MergeAgent` the same constructor field `GitAgent` and
  `CloseoutAgent` already carry. Small and mechanical, but it touches `agentos_workflow/agents/**`,
  which was outside AUTO-006's allowed files — discovered during AUTO-006's self-review and
  recorded rather than fixed in that stage, per the Standard Stage Protocol.
- **Disposition:** Open. Blocks nothing's *authorization*, but a real (non-fake-`gh`) run of
  `GitAgent`/`MergeAgent` against actual GitHub cannot authenticate until this is fixed — affects
  AUTO-007's end-to-end dry run and any real deployment. Full context: `DECISIONS.md` DD-38.
  **Addendum, 2026-07-28 (AUTO-007):** empirically confirmed, not merely theoretical — the
  end-to-end dry run's `CapabilityBroker` skill bindings for `GitAgent`/`MergeAgent` needed a
  test-only wrapper forwarding the fake `gh`'s environment allowlist for exactly these five call
  sites before the dry run could complete; without it, every `gh`-based call in the PR/merge
  phase failed for lack of environment, reproducing precisely the deployment failure this entry
  already predicted. Full detail: `docs/reports/workflow-automation/AUTO-007-completion-report.md`.

### OD-11 — `stage_contract_hash` format disagreement between `PMOAgent` and `LocalResumeObserver`

- **Question:** `PMOAgent.check_preconditions` (`agentos_workflow/agents/pmo.py`) compares
  `calculate_contract_hash`'s bare-hex `ContractHash.sha256`
  (`agentos_workflow/skills/contract.py`) directly against `authorization.stage_contract_hash`
  with no prefix. `LocalResumeObserver` (`agentos_workflow/observation/local.py`) — the live
  observer `resume_workflow` uses whenever a real `WorkflowConfig` is supplied, i.e. the
  production resume path — computes and compares a `"sha256:<hex>"`-*prefixed* value for the same
  semantic field. No single `AuthorizationRecord.stage_contract_hash` value can satisfy both: a
  bare-hex value passes `PRECONDITIONS_CHECKED` but any later real resume raises a false-positive
  `AuthorizationBindingDriftError` (moving the workflow to `FAILED` and requiring re-authorization,
  `HUMAN_AUTHORIZATION_MODEL.md` §4); a `"sha256:"`-prefixed value would instead fail
  `PRECONDITIONS_CHECKED`. Which of the two representations should be the one true convention, and
  in which file should the other be corrected to match?
- **Recommendation:** Standardize on the `"sha256:<hex>"`-prefixed form (matching
  `LocalResumeObserver`'s existing convention, which is closer to a self-describing content
  hash), and correct `PMOAgent.check_preconditions`'s comparison at
  `agentos_workflow/agents/pmo.py:201` to expect the same prefix `calculate_contract_hash`
  produces once that Skill is updated to emit it (or, if `calculate_contract_hash`'s bare-hex
  output must stay stable for another reason, correct `PMOAgent`'s comparison to add the prefix
  before comparing). Either fix touches `agentos_workflow/agents/**` and/or
  `agentos_workflow/skills/**` and/or `agentos_workflow/observation/**`, all outside AUTO-007's
  allowed files, and neither test suite (`test_agents_pmo.py`, hand-built with a bare-hex
  authorization; `test_engine_resume.py`, hand-built with a `"sha256:deadbeef"`-prefixed one)
  currently proves either side against the other, so whichever fix lands needs a new test binding
  the two together (e.g. an authorization built via `calculate_contract_hash`'s real output,
  checked against both `PMOAgent` and a real resume in the same test).
- **Disposition:** Open, discovered 2026-07-28 by AUTO-007's end-to-end dry run — the first
  session to drive `PMOAgent` and a real `resume_workflow`/`WorkflowSession.resume` call against
  the *same* authorization record end to end; each of `PMOAgent`'s and `resume_workflow`'s own
  unit test suites had separately assumed its own convention was authoritative and so never
  caught the mismatch. Blocks nothing's authorization, but every real workflow that reaches
  `PRECONDITIONS_CHECKED` today and is later resumed would hit a false authorization-binding-drift
  failure once it reaches any state at or after `BRANCH_CREATED` — a correctness defect, not a
  security one, but one that would surface on the very first real (non-dry-run) production use of
  the engine. Full detail: `docs/reports/workflow-automation/AUTO-007-completion-report.md`.

### OD-12 — Who assigns QA round numbers: the pre-loop round and the loop's first round are both attempt 1

- **Question:** A workflow's first QA round is run by the Orchestrator *before* the repair loop
  starts, with `attempt_number=1`; `run_repair_loop` (`agentos_workflow/agents/__init__.py`) then
  numbers its own internal rounds from 1 as well, so the loop's first round reuses the number the
  pre-loop round already consumed. The two rounds are genuinely different reviews with different
  verdicts, so their artifacts differ in content — and, correctly, the second write is refused
  (`AUDIT_MODEL.md`; `DECISIONS.md` DD-40). The observable effect is that the loop's attempt 1
  fails on the artifact rather than on the code under review, and a repair that should complete on
  the first iteration completes on the second. Should the pre-loop round be numbered 0, should
  `run_repair_loop` take a starting round number, or should QA round numbers be allocated by the
  Orchestrator's own counter rather than by each caller independently?
- **Recommendation:** Give the round number a single owner. The narrowest fix is a
  `first_attempt_number` (or an explicit round counter) threaded through `run_repair_loop`, so the
  loop continues the sequence the pre-loop round began instead of restarting it. This is a change
  to `agentos_workflow/agents/**` (and to whichever Orchestrator sequence drives the pre-loop
  round), which was outside GOV-3's authorized shape — GOV-3 was scoped to artifact *naming* in
  `skills/reporting.py` and to removing `QAAgent`'s workaround, not to who allocates the numbers.
- **Disposition:** Open, first observed 2026-07-28 by AUTO-007's end-to-end dry run (which asserts
  `repair_attempts_used == 2` and documents why) and confirmed by GOV-3 to be unaffected by the
  artifact-naming fix: sequencing distinguishes rounds, but two rounds that claim the same number
  still collide, which is the correct append-only behaviour. Blocks nothing's authorization; it
  costs one wasted repair attempt out of a budget of three (`FAILURE_RECOVERY.md` §1) on every
  real workflow that repairs, so a workflow could report `repair_attempts_exhausted` after two
  genuine attempts rather than three. Full detail: `docs/reports/GOV-3-completion-report.md`.

## Resolved

### OD-8 — Task-status semantics for a `SUPERSEDED` development stage

- **Question:** When an AUTO or DASH development-stage registry moves a stage to `SUPERSEDED`,
  which of this repository's three task statuses (`Current`, `Planned`, `Done`) represents that
  abandoned-but-not-completed stage, and what exact mirror/closeout steps permit its successor to
  become the sole `Current` task?
- **Resolution (2026-07-24):** `SUPERSEDED` ≈ `Done` (administratively closed, never successful
  completion — `docs/TASK_QUEUE.md` prose must say so explicitly). Legal source states:
  `AUTHORIZED`, `BLOCKED`, `IN_PROGRESS`, `SELF_REVIEW`, `REVIEW`, `APPROVAL`. Never a fourth task
  status. Never automatically authorizes or starts a successor — a successor requires its own
  independent task record and fresh authorization. Human Owner policy decision, verbatim text and
  full rationale: `docs/DECISION_LOG.md` (2026-07-24 entry); normative text: `STAGE_REGISTRY.md`
  §2/§3 rule 9 (DD-08).
- **Does not change:** AUTO-002's current `BLOCKED` state, authorization, or execution
  preconditions — no stage is currently `SUPERSEDED`.

### OD-9 — Initial-execution failure policy for provider, commit, push, and PR operations

- **Question:** What state/retry policy applies when an initial-execution provider invocation,
  `create_commit`, `push_stage_branch`, or `create_pull_request` returns a typed failure after its
  source state has been reached: immediate `FAILED`, a bounded same-state infrastructure retry,
  a repair path, or another explicitly modeled outcome?
- **Resolution (2026-07-24):** bounded same-state retry for a transient pre-side-effect failure;
  idempotency/reconciliation check (never a blind retry) once a side effect may have occurred;
  reconciliation success advances normally; a recoverable inconsistency uses the existing
  `REPAIRING` path (`IMPLEMENTING` only — no new edge into `REPAIRING`); everything else reaches
  `FAILED`. No new state or transition — only new reasons on existing edges plus a same-state
  retry sub-procedure. Human Owner policy decision, verbatim text and full rationale:
  `docs/DECISION_LOG.md` (2026-07-24 entry); normative text: `WORKFLOW_STATES.md` §5a (DD-09).
- **Does not change:** the transition table's edges, the authorization model, the repair-attempt
  counter, or AUTO-002's current lifecycle state.

### OD-4 — Separation of infrastructure retries from the repair-attempt counter

- **Question:** Confirm that transient infrastructure retries (e.g. a flaky GitHub API call
  during `WAITING_FOR_CHECKS`) never increment the 3-attempt repair counter
  (`FAILURE_RECOVERY.md` §1, `WORKFLOW_STATES.md` §5).
- **Resolution (2026-07-26):** Human Owner confirmed the separation and additionally directed
  that infrastructure retries, repair attempts, and initial-execution attempts are three separate
  durable event streams and counters; infrastructure retry is permitted only on durable
  proven-no-side-effect evidence and is prohibited (mandatory reconciliation instead) once
  invocation may have started. `WORKFLOW_STATES.md` §5 updated to state this explicitly (version
  4.1 → 4.2). Human Owner policy decision, verbatim text and full rationale:
  `docs/DECISION_LOG.md` (2026-07-26 entry); normative text: `WORKFLOW_STATES.md` §5 (DD-13).
- **Does not change:** any AUTO-002 code. AUTO-002 already implements two of the three streams
  (`AttemptKind.INITIAL_EXECUTION`, `AttemptKind.REPAIR`) as independent durable counters; the
  third (infrastructure retry) has no implementation anywhere in AUTO-002 because no Skill,
  Provider, or Git/GitHub call exists yet to retry — deferred to whichever future stage first
  introduces one (most likely AUTO-003 or AUTO-006), which must implement it as its own
  independent counter from the outset.
