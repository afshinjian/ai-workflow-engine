"""Isolated secret-redaction utility for successor planning (AUTO-015 section 19.3).

No primitive in `src/ai_workflow_engine/` performs text-content secret redaction, so this
module defines a new, narrowly-scoped one. It deliberately does **not** import
`agentos_workflow.skills.redact_secrets`: section 24 forbids that import outright, and
section 19.3 requires only that this utility follow the same *design discipline*, not the
same pattern table. That discipline is:

* **Linear-time matching.** Every pattern below is anchored on a distinctive literal prefix
  and uses only bounded, non-nested, unambiguous quantifiers over disjoint character
  classes. There is no nested repetition and no alternation inside a repetition, so no input
  can force catastrophic backtracking (ReDoS) on untrusted repository content.
* **Lossy and non-reversible.** A match is replaced by a fixed `[REDACTED:<pattern>]`
  marker. The original bytes are discarded, not encoded, escaped or hashed, so the redacted
  text cannot be used to recover the secret.
* **Explicit findings.** Redaction is never silent: every pattern that fired is returned as
  a :class:`RedactionFinding`, which section 22 invariant 2 requires be surfaced as a
  visible warning rather than dropped.
* **Defense in depth, not a guarantee.** This is a bounded set of well-known secret shapes.
  It will not catch every secret, and a caller must never treat "redaction ran" as proof
  that no secret remains. A secret-shaped string this pass cannot safely neutralize is the
  caller's `SECRET_DETECTED` failure (section 13), not this function's problem to hide.

:func:`redact_text` never raises. It accepts any `str`, including one carrying control
characters, Unicode bidirectional controls or lone surrogates -- exactly the adversarial
input a rejecting validator would refuse -- because redaction runs on content that has not
necessarily passed validation yet.
"""

import re

from pydantic import ConfigDict

from ai_workflow_engine.models import StrictModel


class RedactionFinding(StrictModel):
    """One pattern that fired, reported without ever carrying the secret itself.

    Only the pattern name, the number of occurrences and the offset of the first one are
    recorded. Nothing here narrows what the redacted value was, so a finding is safe to embed
    in an artifact or render in a prompt.
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    pattern_name: str
    occurrences: int
    first_offset: int


# (name, pattern, group to redact, priority). Group 0 redacts the whole match; group 1 redacts
# only the captured value, which is what the two contextual patterns use so the key or the
# host stays readable and a reviewer can still see *which* setting was redacted.
#
# Priority 0 is a pattern that recognizes a specific, self-identifying credential format;
# priority 1 is a contextual pattern that only knows "a secret-shaped value follows this
# keyword". When both match the same span -- `token=ghp_...` matches each -- the specific one
# wins, so the reported finding names the real credential type instead of the generic one.
# Redaction itself is identical either way; only the finding's precision differs.
_PATTERNS: tuple[tuple[str, re.Pattern[str], int, int], ...] = (
    (
        "aws_access_key_id",
        re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|ANPA|ANVA|ABIA|ACCA)[0-9A-Z]{16}\b"),
        0,
        0,
    ),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,255}\b"), 0, 0),
    ("slack_token", re.compile(r"\bxox[abeoprs]-[A-Za-z0-9-]{10,255}\b"), 0, 0),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]{0,40}PRIVATE KEY-----"), 0, 0),
    ("bearer_token", re.compile(r"\b[Bb]earer [A-Za-z0-9._~+/=-]{16,512}"), 0, 0),
    (
        "json_web_token",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{8,512}\.[A-Za-z0-9_-]{8,512}\.[A-Za-z0-9_-]{8,512}",
        ),
        0,
        0,
    ),
    (
        "credential_assignment",
        re.compile(
            r"(?:api[_-]?key|secret[_-]?key|secret|password|passwd|token|access[_-]?key)"
            r"[ \t]{0,8}[:=][ \t]{0,8}[\"']?([A-Za-z0-9_./+=-]{8,256})[\"']?",
            re.IGNORECASE,
        ),
        1,
        1,
    ),
    (
        "url_userinfo",
        re.compile(r"\b[a-z][a-z0-9+.-]{1,31}://[^\s/@:]{1,128}:([^\s/@]{1,256})@"),
        1,
        1,
    ),
)


def redact_text(text: str) -> tuple[str, list[RedactionFinding]]:
    """Return `text` with every recognized secret shape replaced, plus explicit findings.

    Matches are collected across all patterns in one pass each, then resolved
    left-to-right taking the longest match at each position, so two patterns that overlap
    never produce interleaved or doubly-substituted output. Findings are returned sorted by
    `pattern_name`, so the same input always yields the same order regardless of which
    pattern happened to match first.
    """
    spans: list[tuple[int, int, int, str]] = []
    for name, pattern, group, priority in _PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span(group)
            if start < 0 or end <= start:
                continue
            spans.append((start, end, priority, name))

    if not spans:
        return text, []

    # Earliest start wins; on a tie the longest span wins, so a broad pattern is never
    # truncated by a narrower one starting at the same offset; then the more specific
    # pattern wins, and finally the name, so the ordering is total and deterministic.
    spans.sort(key=lambda span: (span[0], -span[1], span[2], span[3]))

    pieces: list[str] = []
    counts: dict[str, int] = {}
    first_offsets: dict[str, int] = {}
    position = 0
    for start, end, _priority, name in spans:
        if start < position:
            continue
        pieces.append(text[position:start])
        pieces.append(f"[REDACTED:{name}]")
        position = end
        counts[name] = counts.get(name, 0) + 1
        if name not in first_offsets:
            first_offsets[name] = start
    pieces.append(text[position:])

    findings = [
        RedactionFinding(
            pattern_name=name,
            occurrences=counts[name],
            first_offset=first_offsets[name],
        )
        for name in sorted(counts)
    ]
    return "".join(pieces), findings
