"""Legacy readers and the additive, read-only migration framework (architecture-v3.md
sections 14 and 18; stage ORCH-003).

This package only inspects existing legacy artifacts and plans a hypothetical future
migration; it never writes a new-schema artifact and never mutates a legacy one. Real
(non-dry-run) migration apply is deliberately unauthorized here and is deferred to a
dedicated migration session per `implementation-plan.md` section 6 and stage ORCH-026.
"""
