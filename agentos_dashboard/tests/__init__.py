"""Dashboard tests (`TEST_STRATEGY.md` §1, OD-D8).

These live inside the dashboard package and run under an explicit path
(`pytest agentos_dashboard/tests`) so the engine's audited collection —
`pytest` with `testpaths=["tests"]` — stays byte-for-byte unchanged.
"""
