# DASH-009 — Security Hardening and Failure Handling

| Field | Value |
|---|---|
| **Stage** | DASH-009 · Role: Dashboard implementation session · mandatory independent security review (fresh session, per `docs/AGENT_PROTOCOL.md`) |
| **Branch** | `fix/dash-009-security-hardening` |
| **Commit message** | `test(dashboard): harden security and failure handling (DASH-009)` |
| **Report** | `docs/reports/agentos-dashboard/STAGE-09-completion.md` |
| **Status/Version** | Draft · 1.0 |

Apply the Standard Stage Protocol in `README.md` in full.

## Canonical Prompt

You are the **Dashboard implementation session** executing **DASH-009 — Security hardening and
failure handling**, with a mandatory independent security review by a fresh session before
approval. Preconditions: DASH-008 `COMPLETE`; recorded authorization; branch
`fix/dash-009-security-hardening`.

**Allowed**: `agentos_dashboard/**` (hardening + tests),
`docs/agentos-dashboard/SECURITY_MODEL.md`; SSP documentation updates.

**Build/verify with failing-before/passing-after tests where feasible**: XSS corpus through the
mini-renderer and every user-input echo; CSRF matrix; traversal/symlink/deny-list;
Host-header/DNS-rebinding; secret-redaction filter over logs, errors, and displayed evidence
(fixture secrets must appear nowhere in any response or log file); large-file caps and
head/tail log views; malformed/truncated/non-UTF8 document and invalid-YAML resilience;
lockfile contention; mid-write crash transaction integrity; graceful error pages without
tracebacks; subprocess timeout handling.

**Documentation**: update `SECURITY_MODEL.md` §7 so every SC-## row records implementation
status and test evidence; the checklist must match implemented reality.

Write the report including the signed security checklist, recommend the commit message above,
then STOP per SSP.

## Stage-Specific Notes

Reference: SC-01..SC-36; TC security classes in `../TEST_STRATEGY.md`. Review independence
follows `docs/AGENT_PROTOCOL.md`: the reviewing session must be fresh, with no memory of this
implementation.
