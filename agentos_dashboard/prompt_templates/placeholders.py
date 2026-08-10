"""The runtime placeholder grammar `stage-prompts/README.md` documents ("Placeholder
Substitution"): five named tokens a stage-specific note section may use, substituted with live
repository facts at generation time. No stage-prompt document currently contains one of these
tokens — the grammar is declared for future note sections to use — so substitution is a
structural no-op today and is exercised here with synthetic fixtures (`TEST_STRATEGY.md`).

Substitution is literal and single-pass: a value is never rescanned for further placeholders, so
a live fact that happened to contain `{{...}}` text (impossible for the five facts this module
populates, all of which are Git/date scalars) could not smuggle a second substitution.
"""

from __future__ import annotations

import re

__all__ = ["PLACEHOLDER_NAMES", "substitute"]

PLACEHOLDER_NAMES: frozenset[str] = frozenset(
    {"branch", "head_sha", "tree_state", "date", "precondition_report"}
)

_NAME_ALTERNATION = "|".join(re.escape(name) for name in PLACEHOLDER_NAMES)
_PLACEHOLDER_RE = re.compile(r"\{\{(" + _NAME_ALTERNATION + r")\}\}")


def substitute(text: str, values: dict[str, str]) -> str:
    """Replace every `{{name}}` occurrence of a known placeholder with `values[name]`.

    A named placeholder with no supplied value is left untouched rather than raising: a stage
    document that does not yet use the grammar (all of them, today) must render unchanged.
    """

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        return values.get(name, match.group(0))

    return _PLACEHOLDER_RE.sub(_replace, text)
