# Prompt: Review current implemented stage

Work in `/home/afshin-jian/ai-workflow-engine` and act only as an independent
reviewer. Do not rely on chat history and do not repair code.

Read repository governance and every core file under
`docs/implementation/orchestration/`, including the current stage specification,
implementation evidence and handoff. Follow `session-protocol.md` review rules.
Require a clean committed implementation HEAD, stage status `VERIFIED`, complete
evidence, approved prerequisites, and a reviewer identity different from every
implementation/remediation actor for this candidate.

Inspect the exact commit/diff for scope, contracts, schemas, migrations,
invariants, security, compatibility, tests and rollback. Re-run all required
commands and compare recorded results. Write a new immutable review YAML and
advance only to `REVIEW_APPROVED` or `REVIEW_REJECTED`. If evidence is missing,
state is stale, the tree is dirty, concurrency exists, or verification differs,
record/recommend `BLOCKED`; never infer approval. Compute but do not implement the
next eligible stage. Do not commit or push without explicit authority.

