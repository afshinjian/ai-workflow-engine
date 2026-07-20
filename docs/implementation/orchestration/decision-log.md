# Architecture v3 Decision Log

Entries are append-only. Changes require an architecture/plan version increment
and review; implementation sessions cannot rewrite accepted decisions.

| ID | Decision | Consequence |
|---|---|---|
| D3-001 | Keep engine primitives separate from orchestrator process. | Orchestrator uses only CLI contract v2 and has no direct stores/Git. |
| D3-002 | Attempt is the base-HEAD epoch. | Prerequisite commit supersedes parent; plan review restarts. |
| D3-003 | Do not implement candidate rebase in v3 initial scope. | No stale candidate reuse; less automation, stronger correctness. |
| D3-004 | Task records own dependency declarations. | No shadow graph; execution stores only linked evidence. |
| D3-005 | Governance mutation is external until atomic commit. | Agent execution always resumes from clean committed governance. |
| D3-006 | Use journal plus per-file replace and Git boundary. | Crash recovery is explicit; no false multi-file atomicity claim. |
| D3-007 | Use deterministic sandbox-only synthetic commits. | Review/remediation sees full chain; new patch ownership is exact. |
| D3-008 | Chain ordering is derived from accepted workflow events. | Caller cannot reorder or splice candidates. |
| D3-009 | Integrity gates outcome routing. | Honest failing checks are trusted evidence, not integrity failure. |
| D3-010 | Coarse failure delta cannot create prerequisites automatically. | Ambiguity requires human classification. |
| D3-011 | Use detached Ed25519 plus isolated replay authority. | Crypto-enforced mode is required for autonomous writes. |
| D3-012 | Trusted-local mode is manual compatibility only. | Free-text approval never grants autonomous mutation capability. |
| D3-013 | Implementation and review are separate sessions/commits. | No implementation agent can approve its own stage. |
| D3-014 | Governance terminal projection is in final reviewed candidate. | Post-push task completion is evidence finalization, not a repo edit. |
| D3-015 | Persisted baseline cache requires complete reproducible identity. | Unknown identity disables cache rather than weakening attribution. |

