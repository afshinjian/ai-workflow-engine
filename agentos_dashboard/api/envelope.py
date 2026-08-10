"""The `{ok, data, error}` response envelope (`API_SPEC.md` §1).

`ok=true` responses carry `data` and no `error`; `ok=false` responses carry `error` and no
`data` — the two helpers below are the only way this package builds a response body, so that
invariant holds structurally rather than by convention.
"""

from __future__ import annotations

from typing import Any, TypedDict

from agentos_dashboard.core.redact import redact_mapping, redact_secrets

__all__ = ["Envelope", "EnvelopeErrorBody", "err", "ok"]


class EnvelopeErrorBody(TypedDict):
    code: str
    message: str


class Envelope(TypedDict):
    ok: bool
    data: Any | None
    error: EnvelopeErrorBody | None


def ok(data: Any) -> dict[str, Any]:
    """Returns `dict[str, Any]`, not `Envelope`: FastAPI infers a `response_model` from a route
    handler's return annotation, and `pydantic.TypedDict` schema generation on Python < 3.12
    requires `typing_extensions.TypedDict` (not stdlib `typing.TypedDict`, used above for the
    documented shape) — a dependency this stage does not add. The dict this returns still has
    exactly `Envelope`'s shape; only the static type of the helper differs from it.
    """
    # Every JSON success response is a display/export boundary. Services still redact before
    # persistence where required; this recursive final guard catches repository-derived fields
    # that are deliberately kept raw for integrity checks inside their service.
    return {"ok": True, "data": redact_mapping({"value": data})["value"], "error": None}


def err(code: str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "data": None,
        "error": {"code": code, "message": redact_secrets(message)},
    }
