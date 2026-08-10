"""The typed error catalogue (`API_SPEC.md` §5).

`DashboardAPIError` is the one exception this package's route handlers raise for an
anticipated, named failure; `main.py` installs the exception handler that turns it (and a few
framework-level exceptions) into an envelope response with the matching HTTP status. Nothing
about an `INTERNAL` error ever includes exception text or a traceback in the response body
(SC-09): only the fixed, non-identifying message below crosses the response boundary.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["INTERNAL_ERROR_MESSAGE", "ApiErrorCode", "DashboardAPIError", "status_code_for"]


class ApiErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    CSRF_REQUIRED = "CSRF_REQUIRED"
    HOST_REJECTED = "HOST_REJECTED"
    SNAPSHOT_BUILDING = "SNAPSHOT_BUILDING"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    GIT_TIMEOUT = "GIT_TIMEOUT"
    INTERNAL = "INTERNAL"


_STATUS_CODES: dict[ApiErrorCode, int] = {
    ApiErrorCode.VALIDATION_ERROR: 422,
    ApiErrorCode.NOT_FOUND: 404,
    ApiErrorCode.CSRF_REQUIRED: 403,
    ApiErrorCode.HOST_REJECTED: 400,
    ApiErrorCode.SNAPSHOT_BUILDING: 409,
    ApiErrorCode.IDEMPOTENCY_CONFLICT: 409,
    ApiErrorCode.GIT_TIMEOUT: 504,
    ApiErrorCode.INTERNAL: 500,
}

INTERNAL_ERROR_MESSAGE = "internal error"


def status_code_for(code: ApiErrorCode) -> int:
    return _STATUS_CODES[code]


class DashboardAPIError(Exception):
    """A typed, anticipated API failure. Carries no repository content or secret material."""

    def __init__(self, code: ApiErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    @property
    def status_code(self) -> int:
        return status_code_for(self.code)
