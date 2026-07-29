"""Regex primitives shared by more than one parser in this package.

`TASK_ID` and `_plain` are deliberately identical in shape to
`ai_workflow_engine.governance.parser.TASK_ID`/`MARKUP` — this package mirrors the engine's
conservative task-id extraction (including its known limitation on multi-hyphen ids such as
`GOV-AUTO-03`, which tokenizes as `AUTO-03`) rather than improving on it, so that a dashboard
view and `workflowctl check-task-state` never disagree about what a task's id *is*
(`DASH-003.md` Stage-Specific Notes: "mirror them, do not import or modify"). Not exported from
the package `__init__`; each parser module imports directly from here.
"""

from __future__ import annotations

import re

TASK_ID = re.compile(r"\b([A-Za-z]+-\d+)\b")
_MARKUP = re.compile(r"[*_`~]")


def plain(value: str) -> str:
    """Strip Markdown emphasis/code markers, mirroring the engine parser's `_plain`."""
    return _MARKUP.sub("", value).strip()
