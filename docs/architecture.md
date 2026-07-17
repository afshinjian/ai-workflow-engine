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
