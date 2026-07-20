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
| D3-016 | Correct the ORCH-000 stage contract's evidence-path/lifecycle gap in `stages/ORCH-000.md` instead of changing `architecture-v3.md` or `implementation-plan.md`. | `stages/ORCH-000.md` now explicitly authorizes `evidence/ORCH-000/` and describes the full `NOT_STARTED`→...→`REVIEW_APPROVED`/`REVIEW_REJECTED` lifecycle and its four evidence categories; the architecture and plan documents, and `architecture_version`/`plan_version`, are unchanged. |

### D3-016 detail — ORCH-000 stage-contract remediation

Recorded by a REMEDIATOR session on 2026-07-20, following the independent
review rejection of ORCH-000 (`reviews/ORCH-000/20260720T172520Z-claude-code-independent-reviewer-59f68d54.yaml`,
findings F-1/F-2 blocking, F-3 non-blocking).

**Why the original stage contract was inconsistent (F-2).** `stages/ORCH-000.md`'s
"Exact allowed files or directories" and "Files expected to be created"
sections named only `reviews/ORCH-000/`, `handoffs/ORCH-000/` and
`implementation-state.yaml`, omitting `evidence/ORCH-000/` — unlike every
other stage file (e.g. `stages/ORCH-001.md`, which explicitly lists "ORCH
state/evidence/handoff"). But `implementation-state.schema.yaml`'s semantic
rules require "passed implementation evidence... at VERIFIED",
`implementation-plan.md`'s common stage contract (section 2, item 6) requires
every implementation session to write
`evidence/<stage-id>/<implementation-id>.yaml`, and the stage file's own
boilerplate footer said the same. No combination of the stage file's allowed
paths let a session satisfy all three simultaneously, so ORCH-000 had no
fully legal route to `VERIFIED` — exactly the "hidden lifecycle gap" the
stage file's own Risks section named as grounds for rejection.

**Why `evidence/ORCH-000/` is now explicitly authorized.** The gap is closed
by amending `stages/ORCH-000.md` directly: its allowed-paths list now
includes `evidence/ORCH-000/`, and a new "Lifecycle" section names all four
evidence categories (implementation, verification, independent review,
handoff) and their exact paths, so a fresh session needs no unilateral
interpretation. `implementation-plan.md`'s common stage contract already
required this; only the per-stage file was wrong, so only the per-stage file
changed. `architecture_version` (3.0.0) and `plan_version` (1.0.0) are
schema-pinned constants in `implementation-state.schema.yaml` and are
unaffected.

**Why this is a reviewed remediation, not retroactive self-authorization
(F-1).** The rejected bootstrap session widened its own allowed-path scope
unilaterally (its own `DEC-1`) instead of stopping for a plan amendment, which
`implementation-plan.md` section 1 and `session-protocol.md` section 8
explicitly forbid. This remediation does not repeat that error: the amendment
is authored by a session distinct from both the original implementer
(`claude-code-bootstrap`) and the rejecting reviewer
(`claude-code-independent-reviewer`), is recorded here with its full
rationale before any new evidence is written under the newly-authorized path,
and — critically — does not itself confer approval. ORCH-000 returns only to
`VERIFIED`; a subsequent independent reviewer, who must differ from this
remediation session as well as from `claude-code-bootstrap` and
`claude-code-independent-reviewer`, must still assess both the amendment and
the resulting evidence before ORCH-000 can reach `REVIEW_APPROVED`. See the
`R-REMEDIATION-AMENDMENT-UNREVIEWED` risk recorded in
`implementation-state.yaml`.

**Whether the existing bootstrap evidence remains admissible.** Yes —
`evidence/ORCH-000/20260720T164147Z-claude-code-bootstrap-d24e29f6.yaml` and
its logs remain admissible and are retained (not superseded, not deleted).
F-1 and F-2 are scope/specification defects in *where* that evidence was
filed and in the stage contract that should have permitted it, not defects in
the evidence's substance. The design package it verifies (commit `a676e0b`)
is unchanged, the commands it recorded are unchanged, and the rejecting
reviewer independently reran the same commands from a separate session and
got matching or byte-identical results (`git show --stat a676e0b`,
`workflowctl verify`, `pytest -q` 684 passed) — recording
`verification_status: PASSED` even while rejecting on scope grounds. Nothing
about the amendment changes the repository, the design package, or those
results. The bootstrap evidence is therefore retained as-is in
`stages.ORCH-000.evidence`, alongside (not replacing) this remediation's own
new evidence entry.

**Whether a new verification run is required.** Not for the bootstrap
evidence's own substantive claims (see above — already independently
reproduced once). This remediation session nonetheless reruns the full
required verification (`git status`, `workflowctl verify`, `pytest -q`, the
state/schema/DAG validator) at its own starting HEAD as part of writing its
own implementation evidence, per the common stage contract's requirement that
every implementation session run and record the exact stage commands — this
confirms the repository is still in the assumed state and is standard
practice for any implementation/remediation session, independent of whether
prior evidence remains valid.

