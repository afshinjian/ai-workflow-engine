"""The verified-vs-claimed evidence view (`API_SPEC.md` EP-17; `PRODUCT_SPEC.md` DR-070/DR-071;
`UI_SPEC.md` PG-06).

Every field here is already produced by `services.runs`: `EvidenceView` is a thin aggregate over
one `StageRunView` — its `report_path_verified` flag *is* the one repo-verified fact (DR-051), and
its `validation_entries` are the run's own recorded, tri-state, user-entered gate results (DR-071)
— plus the small PASS/FAIL/UNKNOWN tally `PG-06`'s gate-matrix summary needs. This module adds no
new persistence and performs no additional repository access beyond what `services.runs.to_view`
already does.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from sqlite3 import Connection

from agentos_dashboard.core.paths import RepositoryRoot
from agentos_dashboard.services.runs import (
    StageRunView,
    ValidationResult,
    get_run,
    list_runs,
    to_view,
)

__all__ = ["EvidenceView", "build_evidence_view", "list_evidence_views"]


@dataclass(frozen=True)
class EvidenceView:
    run: StageRunView
    pass_count: int
    fail_count: int
    unknown_count: int


def _tally(view: StageRunView) -> EvidenceView:
    counts = Counter(entry.result for entry in view.validation_entries)
    return EvidenceView(
        run=view,
        pass_count=counts.get(ValidationResult.PASS, 0),
        fail_count=counts.get(ValidationResult.FAIL, 0),
        unknown_count=counts.get(ValidationResult.UNKNOWN, 0),
    )


def build_evidence_view(
    root: RepositoryRoot, conn: Connection, run_uuid: str
) -> EvidenceView | None:
    """The evidence aggregate for one run (EP-17's `{ref}`), or `None` if `run_uuid` is unknown."""
    run = get_run(conn, run_uuid)
    if run is None:
        return None
    return _tally(to_view(root, run))


def list_evidence_views(root: RepositoryRoot, conn: Connection) -> tuple[EvidenceView, ...]:
    """Every run's evidence aggregate, newest run first (`PG-06`'s gate matrix)."""
    return tuple(_tally(to_view(root, run)) for run in list_runs(conn))
