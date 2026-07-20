# Prompt: Implement next eligible stage

Work in `/home/afshin-jian/ai-workflow-engine`.

This is a continuation of the repository-backed autonomous-orchestration
implementation. Do not rely on chat history. Read the existing governance, then
read completely:

- `docs/implementation/orchestration/README.md`
- `architecture-v3.md`
- `implementation-plan.md`
- `implementation-state.schema.yaml`
- `implementation-state.yaml`
- `session-protocol.md`
- the specification in `stages/` for the uniquely eligible stage

Follow the implementation role protocol. Validate state, repository identity,
branch, HEAD, clean worktree/index, concurrency lock, prerequisite review
approvals, prior evidence reruns and migrations. If the package is pending human
commit, no unique `next_eligible_stage` exists, or any precondition disagrees,
make no production change and report/record the blocker when safe.

Implement only the exact eligible stage and only its allowed paths. Do not skip,
combine or begin a later stage. Run every specified verification command. Write
immutable structured evidence and a handoff, update state only through legal
transitions through at most `VERIFIED`, and stop for human commit and independent
review. Do not mark `REVIEW_APPROVED`, commit, push, migrate production data or
expand scope without separate explicit authority.

