"""The dashboard's JSON API (`API_SPEC.md`): `{ok, data, error}` envelope at `/dash/api/v1`.

DASH-004 implements exactly EP-01 (health), EP-02 (snapshot), EP-03 (status), and EP-20
(snapshot refresh) — the read surface `PG-01` (Overview) needs. Every later `EP-##` in
`API_SPEC.md` is a later stage's responsibility.
"""

from __future__ import annotations
