# AUTO-007 — End-to-End Dry Run, Recovery Tests, and DASH Integration

| Field | Value |
|---|---|
| **Stage** | AUTO-007 · Role: Engine implementation session (+ mandatory independent security review) |
| **Branch** | `fix/auto-007-e2e-dry-run-recovery` |
| **Commit message** | `test(workflow): add end-to-end dry run, recovery tests, and DASH integration validation (AUTO-007)` |
| **Report** | `docs/reports/workflow-automation/AUTO-007-completion-report.md` |
| **Status/Version** | Draft · 1.0 |

Apply the Standard Stage Protocol in `README.md` in full.

## Canonical Prompt

You are the **Engine implementation session** executing **AUTO-007 — End-to-end dry run,
recovery tests, and DASH integration**, with a mandatory independent, fresh-session security
review before this stage may close. Preconditions: AUTO-002..AUTO-006 all `COMPLETE`; recorded
authorization "I authorize AUTO-007"; branch `fix/auto-007-e2e-dry-run-recovery` from clean
`main`.

**Allowed**: `agentos_workflow/tests/e2e/**`, `agentos_workflow/tests/recovery/**`, fixture
target repositories under a test-only scratch location, plus SSP-required documentation/report
updates. No new production module unless a genuine gap surfaces during dry-run testing, in
which case it is recorded as a new `../OPEN_QUESTIONS.md` entry rather than silently implemented
beyond this stage's scope.

**Build**: the full end-to-end dry run described in `../TEST_STRATEGY.md` §5, using
`MockProvider` for both roles against a disposable target repository whose stage-contract
format mirrors `docs/agentos-dashboard/stage-prompts/` (read-only reference, never modified);
the interruption/resume test matrix from `../TEST_STRATEGY.md` §4a; the full security test
suite from `../TEST_STRATEGY.md` §4, run and recorded as evidence for the mandatory independent
security review. Confirm every `../SECURITY_MODEL.md` rule (secrets, forbidden operations,
isolation, no admin bypass, scope enforcement) has at least one passing dedicated test.

**Tests**: as above — this stage *is* the test-authoring stage; there is no further
"tests added" separate from this section.

**Independent security review**: a fresh reviewer session, with no memory of the AUTO-002..006
implementation sessions, re-derives whether every `../SECURITY_MODEL.md` rule is actually enforced
(not merely tested for the happy path) before this stage may reach `COMPLETE`.

**Out of scope**: any change to `docs/agentos-dashboard/**` (read-only reference for this
stage's fixture shape only); any real (non-dry-run) authorization against a real target
repository — that begins only after the Human Owner separately authorizes a first real
production use of the engine, outside this stage's scope.

Write the report, recommend the commit message above, then STOP per SSP.

## Stage-Specific Notes

Reference: `../MVP_SCOPE.md` §4 (MVP acceptance definition — this stage's dry run is the
acceptance demonstration), `../TEST_STRATEGY.md` (all sections). This is the last stage before
MVP acceptance; its report should explicitly state whether every `../MVP_SCOPE.md` §4 acceptance
condition is met.
