# Configuration

Configuration is strict YAML: unknown keys and malformed values are rejected. `project.repository`
must be an existing Git worktree. Every configured project path must be relative and remain beneath
the repository after resolution; file/blob existence is not checked at config-load time. Existence
is validated later, against whichever source (working tree, staged index, or commit) the check
actually reads. Symlink-based and `..` traversal are rejected.

`governance.facts` is an optional list of deterministic mirror rules. Each rule names two or more
files, supplies one Python regular expression, and selects a capture `group` (default 1). Set
`required: true` to fail if any mirror omits it. Values found in multiple mirrors must be equal.

Task rows must contain a task identifier such as `T-1010` and an exact `Current`, `Done`, or
`Planned` cell. The first occurrence of a task in each document is treated as its live statement,
which supports documents that retain older snapshots below the current snapshot.

Protected path values use case-sensitive shell-style matching. In Milestone 1, every staged path
is unexpected; a staged path matching `never_stage` receives an additional protected-path finding.
Automatic commit/push flags must remain false.

See [examples/amozesh_konkur.yaml](../examples/amozesh_konkur.yaml) for a complete configuration.

