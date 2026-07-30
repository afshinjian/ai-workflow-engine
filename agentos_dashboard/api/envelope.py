"""The `{ok, data, error}` response envelope (`API_SPEC.md` §1).

`ok=true` responses carry `data` and no `error`; `ok=false` responses carry `error` and no
`data` — the two helpers below are the only way this package builds a response body, so that
invariant holds structurally rather than by convention.
"""

from __future__ import annotations

from typing import Any, TypedDict

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
    return {"ok": True, "data": data, "error": None}


def err(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "data": None, "error": {"code": code, "message": message}}
