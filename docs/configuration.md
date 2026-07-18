# Configuration

Configuration is strict YAML: unknown keys and malformed values are rejected. `project.repository`
must be an existing Git worktree. Every configured project path must be relative and remain beneath
the repository after resolution; file/blob existence is not checked at config-load time. Existence
is validated later, against whichever source (working tree, staged index, or commit) the check
actually reads. Symlink-based and `..` traversal are rejected.

`project.conda_environment` is required and must not be empty or whitespace-only. It names the
Conda environment the rendered `workflowctl prompt` commands instruct an operator or agent to run
verification commands in; it is never inferred from the current process environment.

`governance.facts` is an optional list of deterministic mirror rules. Each rule names two or more
files, supplies one Python regular expression, and selects a capture `group` (default 1). Set
`required: true` to fail if any mirror omits it. Values found in multiple mirrors must be equal.

Task rows must contain a task identifier such as `T-1010` and an exact `Current`, `Done`, or
`Planned` cell. The first occurrence of a task in each document is treated as its live statement,
which supports documents that retain older snapshots below the current snapshot.

Protected path values use case-sensitive shell-style matching. In Milestone 1, every staged path
is unexpected; a staged path matching `never_stage` receives an additional protected-path finding.
Automatic commit/push flags must remain false.

`agents` is an optional list (default empty) describing the non-interactive agents Milestone 3
may run. Each entry has:

- `name` — unique across the list; matches `[A-Za-z][A-Za-z0-9._-]{0,63}`.
- `executable` — an **absolute** path (no `PATH` lookup); existence is checked at run time, not
  at config load, matching how repository paths defer existence checks.
- `args` — optional list of arguments passed verbatim after the executable.
- `mode` — `read-only` or `scoped-write`.
- `timeout_seconds` — integer in `[1, 86400]`.
- `stages` — a non-empty, unique list of workflow stages the agent may run, each compatible with
  its mode: `read-only` agents may take `plan-review`, `implementation-review`,
  `governance-closeout`, `governance-review`; `scoped-write` agents may take `implementation`,
  `remediation`. The `push` stage is never permitted for any agent.

Milestone 3 defines these schemas and (in later tasks) the runner; Milestone 3 never applies an
agent's changes to the target repository — that is Milestone 4.

See [examples/amozesh_konkur.yaml](../examples/amozesh_konkur.yaml) for a complete configuration.

