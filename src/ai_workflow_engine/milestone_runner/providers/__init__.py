"""Package-owned provider adapters for the AUTO-016 milestone runner (DEC-016-002).

This subpackage is a docstring-only marker: it deliberately re-exports nothing, so adding a
future adapter never edits an existing file and importing one adapter never drags in the other
-- the rule contract section 8 fixes for `providers/` and the rationale
`successor_planning/__init__.py` recorded first.

The Human Owner ruled (DEC-016-002) that provider adapters belong to this package and that the
`agentos_workflow` provider runtime is **not** reused. The ruling is binding and the alternative
is closed: nothing here imports `agentos_workflow`, and no code was copied from it. What was
adopted is its documented discipline -- a fixed argv from a provider-owned constant, no shell,
`Popen` with process-group termination on timeout, bounded stream readers, environment
allowlisting and a normalized command identity in the record.

The subpackage boundary is load-bearing rather than cosmetic (section 8): these three modules are
the only part of the runner that spawns an external process on untrusted-output terms, and giving
them a boundary the AST tests can name is what makes "the runner owns its providers" a structural
property instead of a comment.
"""
