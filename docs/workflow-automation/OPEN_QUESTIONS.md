# AgentOS Workflow Automation — Open Questions

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Open Questions |
| **Purpose** | Owner-decision register (OD-#) with dispositions and what each question blocks. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Documentation & Governance session · Human Owner (dispositions) |
| **Dependencies** | `DECISIONS.md` |
| **Related Documents** | `STAGE_REGISTRY.md` (preconditions cite entries here) |

## Format

Each entry: question, recommendation, disposition, blocked IDs. Entries move to Resolved
append-only; they are never deleted.

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
- **Disposition:** Open. Blocks AUTO-003/AUTO-004 security hardening; does not block AUTO-001.

### OD-3 — Repository lock implementation

- **Question:** A local lock file with PID/heartbeat checking, an OS-level advisory lock
  (`flock`), or both?
- **Recommendation:** A lock file recording the workflow ID and process identity, checked for
  liveness on every command, with an OS-level advisory lock as the actual mutual-exclusion
  primitive underneath it.
- **Disposition:** Open. Blocks AUTO-002 implementation; does not block AUTO-001.

### OD-4 — Separation of infrastructure retries from the repair-attempt counter

- **Question:** Confirm that transient infrastructure retries (e.g. a flaky GitHub API call
  during `WAITING_FOR_CHECKS`) never increment the 3-attempt repair counter
  (`FAILURE_RECOVERY.md` §1, `WORKFLOW_STATES.md` §5).
- **Recommendation:** Confirmed by design intent in this document set; needs Human Owner
  sign-off before AUTO-002 encodes it as load-bearing behavior rather than documentation intent.
- **Disposition:** Open. Blocks AUTO-002 authorization confidence; does not block AUTO-001.

### OD-5 — Final configuration file location/naming

- **Question:** Is `.agentos/workflow.yaml` (per target repository) the final convention, or
  should it be configurable/discoverable differently (e.g. `--config` always required, no
  default path)?
- **Recommendation:** Keep the default path for ergonomics, `--config` override always
  available (`CLI_SPEC.md` §3), matching this repository's own `--config` convention for
  `workflowctl`.
- **Disposition:** Open. Blocks nothing in AUTO-001; affects AUTO-002 discovery code.

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

None yet.
