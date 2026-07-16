# Architecture

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

Milestones 2–4 will plug into the same result/invariant layer. No execution or mutation interface
is enabled in Milestone 1.

