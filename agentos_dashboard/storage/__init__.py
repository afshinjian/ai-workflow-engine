"""The dashboard's local, non-authoritative SQLite storage (`DATA_MODEL.md` §3, OD-D5).

`storage.db` is the only place in this package that opens `dashboard.db`; every service module
under `agentos_dashboard/services/{runs,approvals,findings,notes,audit}.py` goes through
`DashboardDatabase.connection()` rather than opening `sqlite3` directly, so the schema, the
`data/agentos_dashboard/` layout, and the append-only discipline on `audit_events` are each
defined in exactly one place.
"""

from __future__ import annotations
