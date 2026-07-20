# Prompt: Remediate rejected stage

Work in `/home/afshin-jian/ai-workflow-engine`. Do not rely on chat history.
Read repository governance, the complete orchestration package, the rejected
stage specification, all implementation evidence, handoffs and the newest
independent rejection report.

Follow the remediation role in `session-protocol.md`. Require a clean committed
review state, exact HEAD, status `REVIEW_REJECTED`, valid prerequisites and no
concurrent work. Transition that same stage to `IN_PROGRESS`; do not select a new
stage. Fix only the cited findings within the original or narrower allowed path
scope. If a fix requires wider scope or a contract/plan change, stop and record
`BLOCKED` for reviewed replanning.

Run all original and rejection-specific verification. Add new immutable evidence
and handoff without altering old records; return the stage through at most
`VERIFIED` for another independent review. Do not approve, commit, push or begin
another stage.

