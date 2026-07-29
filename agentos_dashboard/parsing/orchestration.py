"""Tolerant, safe parser for `docs/implementation/orchestration/implementation-state.yaml`
(`SOURCE_OF_TRUTH.md` TR-09: read-only, displayed as a separate program view, never merged into
the task queue).

Uses `yaml.SafeLoader` with mapping construction overridden to reject a duplicate key at any
nesting level, mirroring the hardened-loader posture the engine's own migration tooling already
established for this exact document family
(`src/ai_workflow_engine/migration/legacy_readers.py`'s `_NoDuplicateKeySafeLoader`, not
imported here — this package must not depend on engine internals). Only structural fields
(`feature_id`, `current_stage`, `next_eligible_stage`, `delivery_order`, and each stage's
`title`/`status`/`prerequisites`/`blockers`/`evidence`) are extracted; the document's rich
`history`/`unresolved_risks` sections are left as raw text for a later stage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml

from agentos_dashboard.parsing.models import Confidence, ParsedDocument

__all__ = [
    "OrchestrationStage",
    "OrchestrationStateView",
    "parse_implementation_state",
]


class _NoDuplicateKeySafeLoader(yaml.SafeLoader):
    """`yaml.SafeLoader`, except a repeated mapping key is a parse error, not last-key-wins."""


def _construct_mapping_no_duplicates(
    loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_NoDuplicateKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping_no_duplicates
)


@dataclass(frozen=True)
class OrchestrationStage:
    """EN-24: one ORCH stage's structural facts."""

    stage_id: str
    title: str | None
    status: str | None
    prerequisites: tuple[str, ...]
    blockers: tuple[str, ...]
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class OrchestrationStateView:
    feature_id: str | None
    current_stage: str | None
    next_eligible_stage: str | None
    delivery_order: tuple[str, ...]
    stages: tuple[OrchestrationStage, ...]


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def _blocker_summaries(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    summaries: list[str] = []
    for entry in value:
        if isinstance(entry, dict):
            summaries.append(str(entry.get("summary") or entry.get("code") or entry))
        else:
            summaries.append(str(entry))
    return tuple(summaries)


def parse_implementation_state(text: str, source: str) -> ParsedDocument[OrchestrationStateView]:
    try:
        data = yaml.load(text, Loader=_NoDuplicateKeySafeLoader)
    except yaml.YAMLError as exc:
        return ParsedDocument(
            source=source,
            confidence=Confidence.NONE,
            value=None,
            raw_text=text,
            notes=(f"YAML parse error: {exc}",),
        )

    if not isinstance(data, dict):
        return ParsedDocument(
            source=source,
            confidence=Confidence.NONE,
            value=None,
            raw_text=text,
            notes=("document root is not a mapping",),
        )

    notes: list[str] = []
    raw_stages = data.get("stages")
    stages: list[OrchestrationStage] = []
    if isinstance(raw_stages, dict):
        for stage_id, stage_data in raw_stages.items():
            if not isinstance(stage_data, dict):
                notes.append(f"stage {stage_id!r}: value is not a mapping, skipped")
                continue
            stages.append(
                OrchestrationStage(
                    stage_id=str(stage_id),
                    title=stage_data.get("title"),
                    status=stage_data.get("status"),
                    prerequisites=_string_tuple(stage_data.get("prerequisites")),
                    blockers=_blocker_summaries(stage_data.get("blockers")),
                    evidence=_string_tuple(stage_data.get("evidence")),
                )
            )
    else:
        notes.append("'stages' key is missing or not a mapping")

    view = OrchestrationStateView(
        feature_id=data.get("feature_id"),
        current_stage=data.get("current_stage"),
        next_eligible_stage=data.get("next_eligible_stage"),
        delivery_order=_string_tuple(data.get("delivery_order")),
        stages=tuple(stages),
    )
    confidence = Confidence.HIGH if not notes else Confidence.LOW
    return ParsedDocument(
        source=source, confidence=confidence, value=view, raw_text=text, notes=tuple(notes)
    )
