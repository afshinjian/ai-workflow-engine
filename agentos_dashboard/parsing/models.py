"""Shared types for every tolerant parser in this package.

`ParsedDocument` is the one return shape every parser produces: a structural `value` when
parsing succeeded well enough to trust, always the untouched `raw_text` as a fallback, and a
`Confidence` a caller can branch on without inspecting exception types (no parser here raises
for malformed input — see the package docstring). `TaskStatus` mirrors
`ai_workflow_engine.governance.models.TaskStatus` by value only; this package never imports the
engine (`agentos_dashboard/__init__.py`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Generic, TypeVar

__all__ = [
    "Confidence",
    "ParsedDocument",
    "TaskStatus",
]

T = TypeVar("T")


class Confidence(StrEnum):
    """How much of a document's expected structure a parser was able to recognize."""

    HIGH = "high"
    """Every expected structural element was found and well-formed."""

    LOW = "low"
    """Some structure was recognized; part of the document was skipped or unparsable."""

    NONE = "none"
    """Nothing recognizable was found; only the raw text is available."""


class TaskStatus(StrEnum):
    """The three statuses `docs/TASK_QUEUE.md` and its mirrors know, verbatim."""

    CURRENT = "Current"
    DONE = "Done"
    PLANNED = "Planned"


@dataclass(frozen=True)
class ParsedDocument(Generic[T]):
    """One parser's tolerant result.

    `value` is `None` exactly when `confidence` is `Confidence.NONE`; `raw_text` is always the
    complete, unmodified input, so a caller can show *something* even on total parse failure
    (`SOURCE_OF_TRUTH.md` TR-02: parsed views always carry a raw-source fallback). `notes`
    records what a `LOW`/`NONE` confidence means in practice (e.g. "3 heading(s) skipped: no
    recognizable Status field"), for direct inclusion in a `ConsistencyFinding` message.
    """

    source: str
    confidence: Confidence
    value: T | None
    raw_text: str
    notes: tuple[str, ...] = field(default_factory=tuple)
