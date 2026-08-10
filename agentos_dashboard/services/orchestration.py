"""EN-24 `OrchStage` — the read-only ORCH feature-state view (`API_SPEC.md` EP-18;
`SOURCE_OF_TRUTH.md` TR-09).

`build_orchestration_view` does exactly one thing: read
`docs/implementation/orchestration/implementation-state.yaml` through the root-confined file
adapter and parse it with `parsing.orchestration.parse_implementation_state` — the same parser
`services.board`'s ORCH program lane and `services.consistency`'s TR-09 check already use, so
this module adds no second reading of that document's structure. Nothing here opens a database
connection, invokes Git, or spawns a subprocess: the whole call graph below is `read_text` (one
`open()`, no write mode) and pure parsing, which is what lets EP-18's acceptance criteria — zero
`dashboard.db` write, zero Git invocation, zero agent/subprocess invocation — hold by construction
rather than by a runtime guard.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentos_dashboard.core.files import FileAccessError, read_text
from agentos_dashboard.core.paths import PathRefusedError, RepositoryRoot
from agentos_dashboard.parsing.orchestration import OrchestrationStage, parse_implementation_state
from agentos_dashboard.services.consistency import IMPLEMENTATION_STATE_PATH

__all__ = ["OrchestrationView", "build_orchestration_view"]


@dataclass(frozen=True)
class OrchestrationView:
    """The whole read-only ORCH feature-state surface EP-18 exposes."""

    available: bool
    source: str
    notes: tuple[str, ...]
    feature_id: str | None
    current_stage: str | None
    next_eligible_stage: str | None
    delivery_order: tuple[str, ...]
    stages: tuple[OrchestrationStage, ...]


_UNAVAILABLE_NOTE = "implementation-state.yaml is missing or unreadable"


def build_orchestration_view(root: RepositoryRoot) -> OrchestrationView:
    """Never raises: a missing or unreadable document degrades to `available=False`
    (`SOURCE_OF_TRUTH.md` TR-04), exactly like every other adapter in this package."""
    try:
        text = read_text(root, IMPLEMENTATION_STATE_PATH).text
    except (FileAccessError, PathRefusedError):
        return OrchestrationView(
            available=False,
            source=IMPLEMENTATION_STATE_PATH,
            notes=(_UNAVAILABLE_NOTE,),
            feature_id=None,
            current_stage=None,
            next_eligible_stage=None,
            delivery_order=(),
            stages=(),
        )

    parsed = parse_implementation_state(text, IMPLEMENTATION_STATE_PATH)
    if parsed.value is None:
        return OrchestrationView(
            available=False,
            source=IMPLEMENTATION_STATE_PATH,
            notes=parsed.notes,
            feature_id=None,
            current_stage=None,
            next_eligible_stage=None,
            delivery_order=(),
            stages=(),
        )

    view = parsed.value
    return OrchestrationView(
        available=True,
        source=IMPLEMENTATION_STATE_PATH,
        notes=parsed.notes,
        feature_id=view.feature_id,
        current_stage=view.current_stage,
        next_eligible_stage=view.next_eligible_stage,
        delivery_order=view.delivery_order,
        stages=view.stages,
    )
