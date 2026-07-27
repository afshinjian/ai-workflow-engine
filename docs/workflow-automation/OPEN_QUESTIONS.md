# AgentOS Workflow Automation — Open Questions

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Open Questions |
| **Purpose** | Owner-decision register (OD-#) with dispositions and what each question blocks. |
| **Status** | Draft |
| **Version** | 1.4 |
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
- **Disposition:** Open. Blocks AUTO-006 implementation detail; does not block AUTO-001.

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
