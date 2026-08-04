"""Deterministic, read-only successor-planning capability (AUTO-015).

This package is a docstring-only marker: it deliberately re-exports nothing, so every
consumer imports the submodule it actually needs
(`ai_workflow_engine.successor_planning.models`,
`ai_workflow_engine.successor_planning.redaction`, ...) rather than a package-level
alias. Keeping the marker empty means no later addition to this package requires editing
this file, and no import of one submodule drags in the rest.

The capability itself is read-only: it inspects this repository's own governance
evidence, produces a hash-bound proposal artifact labelled `NOT_AUTHORIZED`, and stops at
the Human Owner decision gate. It selects, registers and authorizes nothing.
"""
