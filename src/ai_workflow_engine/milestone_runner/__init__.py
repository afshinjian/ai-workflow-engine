"""Integrated milestone automation runner (AUTO-016).

This package is a docstring-only marker: it deliberately re-exports nothing, so every
consumer imports the submodule it actually needs
(`ai_workflow_engine.milestone_runner.models`, ...) rather than a package-level alias.
Keeping the marker empty means no later addition to this package requires editing this
file, and no import of one submodule drags in the rest -- the recorded rationale
`successor_planning/__init__.py` already established and contract section 8 fixes for this
package.

The capability itself is supervised execution: it drives an already-authorized stage's
implementation as a bounded, resumable sequence of typed milestones, writes durable run
state *outside* the repository, and stops at explicit human gates. It authorizes nothing,
registers nothing, and takes no irreversible action on its own initiative.
"""
