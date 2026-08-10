"""EP-07/EP-08 (`API_SPEC.md` §2): the governance document browser and bounded search
(PG-08, added by PLAN-001)."""

from __future__ import annotations

from typing import Any

from agentos_dashboard.services.governance import (
    GovernanceDocument,
    RenderedDocument,
    SearchResult,
    list_governance_documents,
)

__all__ = [
    "document_list_to_json",
    "document_summary_to_json",
    "rendered_document_to_json",
    "search_result_to_json",
]


def document_summary_to_json(doc: GovernanceDocument) -> dict[str, Any]:
    return {"doc_id": doc.doc_id, "title": doc.title, "authority": doc.authority}


def document_list_to_json() -> dict[str, Any]:
    return {"documents": [document_summary_to_json(doc) for doc in list_governance_documents()]}


def rendered_document_to_json(document: RenderedDocument) -> dict[str, Any]:
    return {
        "doc_id": document.doc_id,
        "title": document.title,
        "authority": document.authority,
        "path": document.path,
        "raw_text": document.raw_text,
        "rendered_html": document.rendered_html,
        "headings": [
            {"level": h.level, "text": h.text, "anchor": h.anchor} for h in document.headings
        ],
        "truncated": document.truncated,
        "degraded": document.degraded,
        "findings": [
            {
                "rule": f.rule,
                "severity": f.severity.value,
                "message": f.message,
                "sources": list(f.sources),
            }
            for f in document.findings
        ],
    }


def search_result_to_json(result: SearchResult) -> dict[str, Any]:
    return {
        "doc_id": result.doc_id,
        "title": result.title,
        "line": result.line,
        "snippet": result.snippet,
    }
