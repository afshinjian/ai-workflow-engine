"""EP-17 (`API_SPEC.md` §2): the verified-vs-claimed evidence view (PG-06)."""

from __future__ import annotations

from typing import Any

from agentos_dashboard.api.runs import run_view_to_json
from agentos_dashboard.services.evidence import EvidenceView

__all__ = ["evidence_view_to_json"]


def evidence_view_to_json(view: EvidenceView) -> dict[str, Any]:
    return {
        "run": run_view_to_json(view.run),
        "pass_count": view.pass_count,
        "fail_count": view.fail_count,
        "unknown_count": view.unknown_count,
    }
