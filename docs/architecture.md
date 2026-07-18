# Architecture

## Inspection pipeline (Milestone 1)

Milestone 1 is a one-way inspection pipeline:

```text
YAML config -> bounded repository paths -> read-only Git/file readers
            -> deterministic validators -> structured results -> Rich/JSON output
```

The package separates configuration, Git inspection, governance parsing, handover verification,
workflow invariants, and reporting. `GitClient` exposes only audited read operations. Handover
verification reads bytes from the working tree, index (`git show :path`), or a selected commit
(`git show commit:path`), so a dirty working tree cannot masquerade as committed integrity.

Governance parsing is deliberately conservative: task states come from explicit Markdown table
rows and configurable regular expressions extract repeated scalar facts. The configured task
queue is authoritative; other documents are mirrors.

## Prompt generation pipeline (Milestone 2)

Milestone 2 layers governed prompt generation on top of the same read-only inspection:

```text
YAML config -> read-only inspection (git status, task snapshot, four checks)
            -> canonical context (strict models, NFC, sorted collections)
            -> exact template lookup (7 stages, pinned versions + SHA-256 digests)
            -> deterministic rendering (closed placeholder mapping, simultaneous substitution)
            -> structural validation -> optional atomic no-clobber storage
```

Key properties, specified normatively in [milestone-2-plan.md](milestone-2-plan.md):

- **Prompt identity is content-derived:** `prompt_id` is the first 16 hex characters of the
  SHA-256 of a canonical JSON serialization of the complete `PromptContext` (config, git
  status, task snapshot, check evidence, template content/version/digest). No clock value is an
  input; two renders of the same state are byte-identical.
- **Storage is race-safe and no-clobber:** artifacts live under
  `~/.ai-workflow-engine/workflow-runs/prompts/<project_id>/<stage>/<prompt_id>.{md,json}`,
  published via hard-link creates (metadata first), never inside the target repository, never
  overwritten. `load()` re-derives and re-verifies everything from the stored sidecar alone.
- **Prompts are inert:** rendered command lines are instructions for an external operator or
  agent; Milestone 2 never executes them, and `GitClient.READ_ONLY_FORMS` is unchanged.

## Agent execution and workflow state (Milestone 3)

Milestone 3 adds non-interactive agent execution on top of the same read-only inspection and
governed prompts, plus the persisted workflow state the earlier milestones deferred:

```text
governed prompt (M2) -> configured agent (EngineConfig.agents)
  -> snapshot sandbox (clone at recorded HEAD, clean-tree precondition)
  -> subprocess (stdin=prompt, JSON AgentReport on stdout, hard timeout, scrubbed env)
  -> observe raw facts (change set, patch, verification-command exit codes)
  -> independent verification (claim equality, scope + protected containment, commands passed)
  -> tamper-evident AgentRunRecord artifact  ──cites──>  workflow state event
```

Key invariants (normative detail in `docs/milestone-3-plan.md`):

- **Agent output is evidence, not authority.** Every claim an agent makes is verified against the
  sandbox reality the runner observed; a false or unverifiable claim is a FAIL, never a warning.
- **The target repository is never written.** Agent writes land only in a throwaway sandbox clone
  (via a separate sandbox-only `SandboxGit`) or under `~/.ai-workflow-engine/`. A before/after
  `GitStatus` fingerprint fails any run that mutated the target. A scoped-write agent's verified
  patch is stored, not applied — application is Milestone 4.
- **Workflow state is an append-only, hash-chained event log** with a fixed transition table
  (`plan-review → implementation → implementation-review ⇄ remediation → governance-closeout →
  governance-review → push`), verdict recording, and next-stage computation. Storage reuses the
  Milestone 2 atomic no-clobber protocol; load re-verifies canonical bytes, contiguity, embedded
  identity, and the parent-digest chain.
- **Determinism holds end-to-end.** `prompt_id` and `run_id` are content hashes; no clock value
  enters any prompt, run identity, or state event.

CLI surfaces added: `workflowctl state show|next|record` and `workflowctl agent run`.

## Controlled commit and push (Milestone 4)

Milestone 4 adds the first — and only — writable-Git operations on the target repository, each
behind an explicit gate:

```text
human approval artifact (branch/HEAD/allowed-paths/message)
  -> commit gate (protected-path + branch/HEAD + clean-index + subset/existence checks)
  -> GitWriter.stage_paths -> staged-set assertion -> GitWriter.commit
  -> post-hoc verify (parent, path set, message)

human approval artifact (branch/HEAD/upstream)
  -> push gate (branch/HEAD/upstream equality, clean tree,
                rev-list behind==0 & ahead>0, diff --check)
  -> GitWriter.push   (exactly one `git push`, no refspec/force)
```

Invariants (normative detail in `docs/milestone-4-plan.md`):

- **A separate writable surface.** All writes go through `GitWriter`, whose typed methods emit
  fixed argv shapes; force-push, branch deletion, `reset`, `--amend`/`-a`, `add -A`/glob, and
  `clean` are structurally unreachable. The read-only `GitClient.READ_ONLY_FORMS` tuple is
  byte-unchanged; the gate-read methods use only forms already in it.
- **No unapproved write.** A commit can never include a change outside its approval's allowed-path
  set, and protected paths are rejected even if an approval lists them. `allow_automatic_commit`/
  `allow_automatic_push` remain hard-false and never bypass a gate. Every gate failure writes
  nothing.
- **`apply-patch`** applies a verified Milestone 3 patch to the working tree only (never the
  index), gated by the run artifact + live-HEAD match + clean-tree + `apply --check` + a digest
  re-check. It is the one writable op bound to a run artifact rather than a human approval.

CLI surfaces added: `workflowctl commit`, `workflowctl push`, `workflowctl apply-patch`.

## JSON contract

Every check serializes these stable top-level fields:

```json
{
  "check_name": "git",
  "status": "PASS",
  "summary": "...",
  "findings": [],
  "evidence": {},
  "affected_paths": [],
  "remediation_hint": null,
  "timestamp": "2026-07-15T00:00:00Z"
}
```

`verify` wraps checks with `schema_version`, `project_id`, combined `status`, `checks`, and
`timestamp`. `ERROR` takes precedence over `FAIL`, which takes precedence over `PASS`.
Timestamps are UTC ISO-8601 values; field names and enum values form the 1.0 schema.
(`workflowctl prompt` success output is the separate closed `PromptSuccess` schema defined in
the Milestone 2 plan; prompt *failures* reuse the `CheckResult` contract above.)

Milestones 3–4 will plug into the same result/invariant layer. No execution or mutation
interface is enabled through Milestone 2.
