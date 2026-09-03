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

`verification` is optional and defaults to no configured bundles. Bundles are named, ordered sets
of argv arrays; they are never shell strings. Names are unique and match
`[A-Za-z][A-Za-z0-9._-]{0,63}`. Each bundle has at least one non-empty command, every token is a
non-empty string without NUL, newline, or surrogate code points, and `timeout_seconds` defaults to
3600 and must be in `[1, 86400]`.

```yaml
verification:
  bundles:
    - name: quality
      commands:
        - ["python", "-m", "pytest", "-q"]
        - ["git", "diff", "--check"]
      timeout_seconds: 3600
```

Select configured bundles with repeatable `--verification-bundle NAME` options on any
`workflowctl prompt <stage>` command. Selection order is execution order; unknown and duplicate
selections fail before execution. Commands run with `shell=False` in one disposable clone checked
out at the target's exact clean HEAD, never in the target worktree. Evidence records bundle name,
global command index, exact argv, exit code, and timeout state; stdout and stderr are not included.
With no selection, no verification sandbox is created and prompt evidence records
`verification_evidence: null`.

Governed prompt and agent execution also records the running engine's version, Git HEAD,
worktree-cleanliness flag, install mode, and resolved imported-package path. Version disagreement
fails closed. Under OD-1, an editable installation with a dirty worktree, or without a resolvable
worktree, is refused even when no bundle is selected. This enforcement is deliberately limited to
governed prompt/review/provenance and agent execution; ordinary inspection, governance, migration,
commit/push, apply-patch, automation, milestone-runner, and version commands remain unaffected.

Milestone 3 never applies an agent's changes to the target repository — that is Milestone 4.

See [examples/amozesh_konkur.yaml](../examples/amozesh_konkur.yaml) for a complete configuration.
