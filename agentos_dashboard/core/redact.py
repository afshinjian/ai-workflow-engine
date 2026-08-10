"""Secret-shaped substring redaction (`SECURITY_MODEL.md` SC-09).

Applied at genuinely free-text boundaries where an operator or the repository could introduce a
pasted credential: operator-authored draft fields (`services/notes.py`, `services/runs.py`) and
display-only repository text (`services/governance.py`'s rendered/raw document text,
`services/handover.py`'s narrative). It is deliberately **not** applied inside `core/files.py` or
any other path `services/consistency.py`/`services/tasks.py`/`services/board.py` also read for
byte-exact contradiction detection or checksum verification — mutating that text would corrupt
the very fidelity SC-30 exists to guarantee, trading one control for a worse one. Content that
must remain byte-exact (a report's SHA-256, a handover checksum) is always computed from raw
bytes via `core.files.digest_file`, never from redacted text, so redaction here can never make an
integrity check pass or fail incorrectly.

This is deliberately a denylist of recognizable secret *shapes* (bearer tokens, key=value
assignments naming a sensitive key, common vendor token prefixes), not a generic high-entropy
detector: the latter would false-positive on ordinary hex content this dashboard displays
constantly (commit SHAs, content digests), silently corrupting exactly the evidence an operator
relies on.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

__all__ = ["REDACTED_PLACEHOLDER", "redact_mapping", "redact_secrets"]

REDACTED_PLACEHOLDER = "[REDACTED]"

# The policy is deliberately name/shape based. It does not guess from entropy.  These names are
# the credential-bearing fields the Dashboard accepts or commonly displays.  Boundaries prevent
# ordinary identifiers such as ``tokenizer`` and ``monkey`` from matching.
_SENSITIVE_KEY = r"""
    (?:
        api[_-]?key | apikey | x[_-]?api[_-]?key |
        secret | client[_-]?secret |
        token | auth[_-]?token | access[_-]?token | refresh[_-]?token | id[_-]?token |
        password | passwd | pwd |
        private[_-]?key
    )
"""
_OPTIONAL_KEY_QUOTE = r"(?:[\"']|&(?:quot|apos|\#34|\#39|\#x22|\#x27);|%2[27])?"
_KEY_PREFIX = (
    rf"(?P<prefix>(?<![A-Za-z0-9/\\]){_OPTIONAL_KEY_QUOTE}{_SENSITIVE_KEY}"
    rf"(?![A-Za-z0-9]){_OPTIONAL_KEY_QUOTE}"
    rf"(?:\s|%20)*(?:[:=]|%3[aAdD])(?:\s|%20)*)"
)

# Quoted forms run before the unquoted form so spaces and punctuation inside a quoted value are
# removed as one credential. HTML-escaped quotes are handled because repository Markdown may
# already contain escaped JSON/HTML when it reaches this filter.
_DOUBLE_QUOTED_ASSIGNMENT_RE = re.compile(
    rf'{_KEY_PREFIX}"(?P<value>[^"\r\n]+)"', re.IGNORECASE | re.VERBOSE
)
_SINGLE_QUOTED_ASSIGNMENT_RE = re.compile(
    rf"{_KEY_PREFIX}'(?P<value>[^'\r\n]+)'", re.IGNORECASE | re.VERBOSE
)
_HTML_QUOTED_ASSIGNMENT_RE = re.compile(
    rf"{_KEY_PREFIX}(?P<quote>&(?:quot|apos|\#34|\#39|\#x22|\#x27);)" rf"(?P<value>.+?)(?P=quote)",
    re.IGNORECASE | re.VERBOSE,
)
_UNQUOTED_ASSIGNMENT_RE = re.compile(
    rf"{_KEY_PREFIX}(?P<value>[^\s&<>'\",;\[\]\)}}]+)",
    re.IGNORECASE | re.VERBOSE,
)

# Authorization-like headers need their own rule: in ``Authorization: Basic <blob>`` the first
# word is a scheme, not the credential.  Unknown/no-scheme forms are still redacted wholesale.
_AUTHORIZATION_RE = re.compile(
    r"""(?ix)
    (?P<prefix>
        (?<![A-Za-z0-9/\\])(?:[\"']|&quot;|%22)?
        (?:proxy[_-]?)?authorization(?![A-Za-z0-9])(?:[\"']|&quot;|%22)?
        (?:\s|%20)*(?:[:=]|%3[aAdD])(?:\s|%20)*
    )
    (?:(?P<scheme>bearer|basic|digest|token|apikey)(?P<scheme_space>\s+))?
    (?P<value>"[^"\r\n]+"|'[^'\r\n]+'|&quot;.+?&quot;|[^\s,;]+)
    """
)

# Bare ``Bearer <token>`` mentions (with or without an Authorization field name).
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-_.~+/=]{4,}")

# Recognizable vendor/service token prefixes, redacted wholesale wherever they appear even
# without a preceding key= assignment (e.g. pasted directly into a note).
_VENDOR_TOKEN_RE = re.compile(
    r"""(?x)
    AKIA[0-9A-Z]{16} |                       # AWS access key id
    gh[pousr]_[A-Za-z0-9]{20,} |             # GitHub personal/OAuth/app tokens
    github_pat_[A-Za-z0-9_]{20,} |           # GitHub fine-grained PAT
    xox[baprs]-[A-Za-z0-9-]{10,} |           # Slack tokens
    sk-[A-Za-z0-9_-]{20,} |                  # OpenAI/Anthropic-style secret keys
    glpat-[A-Za-z0-9_-]{20,} |               # GitLab personal access tokens
    (?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,} | # Stripe-style secret/restricted keys
    AIza[0-9A-Za-z_-]{20,} |                 # Google API keys
    eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}  # JWT
    """
)


def redact_secrets(text: str) -> str:
    """Replace recognizable secret-shaped substrings in `text` with `[REDACTED]`.

    Order matters: authorization and quoted assignments run before unquoted assignments; vendor
    prefixes and bare Bearer tokens then catch credentials pasted with no key name at all.
    """
    redacted = _AUTHORIZATION_RE.sub(
        lambda m: (
            f"{m.group('prefix')}"
            f"{m.group('scheme') + m.group('scheme_space') if m.group('scheme') else ''}"
            f"{REDACTED_PLACEHOLDER}"
        ),
        text,
    )
    for pattern in (
        _DOUBLE_QUOTED_ASSIGNMENT_RE,
        _SINGLE_QUOTED_ASSIGNMENT_RE,
        _HTML_QUOTED_ASSIGNMENT_RE,
        _UNQUOTED_ASSIGNMENT_RE,
    ):
        redacted = pattern.sub(lambda m: f"{m.group('prefix')}{REDACTED_PLACEHOLDER}", redacted)
    redacted = _BEARER_RE.sub(f"Bearer {REDACTED_PLACEHOLDER}", redacted)
    redacted = _VENDOR_TOKEN_RE.sub(REDACTED_PLACEHOLDER, redacted)
    return redacted


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, Mapping):
        return {key: _redact_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


def redact_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively redact string values in an audit/response mapping.

    Mapping keys are schema identities and remain byte-exact. Values retain their container
    shape, so redaction cannot change the canonical meaning of non-text audit fields.
    """
    return {key: _redact_value(value) for key, value in payload.items()}
