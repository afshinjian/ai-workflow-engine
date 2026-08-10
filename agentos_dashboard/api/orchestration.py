"""EP-18 (`API_SPEC.md` §2): the read-only ORCH feature-state view.

`orchestration_view_to_json` performs no I/O of its own — it only shapes an already-built
`OrchestrationView` (`services.orchestration`) into the envelope payload, so the route handler
that calls it (`api/routes.py`) is the only place in the call graph that touches anything besides
pure data transformation, exactly what EP-18's zero-DB-write/zero-Git/zero-subprocess acceptance
criteria require.
"""

from __future__ import annotations

from typing import Any

from agentos_dashboard.parsing.orchestration import OrchestrationStage
from agentos_dashboard.services.orchestration import OrchestrationView

__all__ = ["orchestration_stage_to_json", "orchestration_view_to_json"]


def orchestration_stage_to_json(stage: OrchestrationStage) -> dict[str, Any]:
    return {
        "stage_id": stage.stage_id,
        "title": stage.title,
        "status": stage.status,
        "prerequisites": list(stage.prerequisites),
        "blockers": list(stage.blockers),
        "evidence": list(stage.evidence),
    }


def orchestration_view_to_json(view: OrchestrationView) -> dict[str, Any]:
    return {
        "available": view.available,
        "source": view.source,
        "notes": list(view.notes),
        "feature_id": view.feature_id,
        "current_stage": view.current_stage,
        "next_eligible_stage": view.next_eligible_stage,
        "delivery_order": list(view.delivery_order),
        "stages": [orchestration_stage_to_json(stage) for stage in view.stages],
    }
