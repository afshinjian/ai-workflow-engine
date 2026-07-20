# Prompt: Resume after prerequisite or repository HEAD change

Work in `/home/afshin-jian/ai-workflow-engine`. This is a controlled resume, not
permission to rebase or reuse candidates. Do not rely on chat history.

Read repository governance and the entire orchestration architecture, plan,
state/schema, session protocol, affected stage specification, evidence, review
and migration records. Require a clean committed target and no concurrent or
recovery operation. Determine why HEAD changed and prove the new commit is the
expected reviewed prerequisite/governance transition. If provenance is absent or
unrelated, stop and record/report `UNEXPECTED_HEAD`.

For runtime task work, verify the old parent attempt is/will be `SUPERSEDED`, its
candidate is ineligible, all prerequisites are terminal successful, and a signed
unblock/new-attempt mutation is required. Never rebase the old chain. The new
attempt must bind current HEAD/spec/governance and restart at plan review.

For implementation-stage work, do not edit an already reviewed stage's base.
Revalidate completed-stage evidence against the changed repository. If still
valid, a reviewed state transition may set the next stage's expected base to
current HEAD; otherwise record `BLOCKED`/`SUPERSEDED` and request plan review.
Write evidence only for a legal resume transition, produce a handoff and stop.
Do not implement the next stage in the same resume session.

