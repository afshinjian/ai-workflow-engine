"""Tolerant, confidence-scored parsers for the repository's governance Markdown/YAML documents.

Each module here mirrors the *semantics* of the engine's own conservative parsers
(`src/ai_workflow_engine/governance/parser.py`, `.../registry.py`,
`src/ai_workflow_engine/handover/manifest.py`) without importing or modifying them
(`agentos_dashboard/__init__.py`: this package imports nothing from the engine). No parser in
this package ever raises for malformed input — every function returns a
`agentos_dashboard.parsing.models.ParsedDocument` carrying a `Confidence`, the best structural
value it could recover, and the untouched raw text as a fallback (`DASH-003.md`: "every parser
failure degrades to raw text + ConsistencyFinding — no exceptions escape"). Turning a low or
absent confidence into a `ConsistencyFinding` is `agentos_dashboard.services.consistency`'s job,
not this package's.
"""

from __future__ import annotations
