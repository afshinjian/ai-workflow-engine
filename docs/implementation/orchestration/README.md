# Autonomous Orchestration v3 Design Package

Feature ID: `ORCH`

This directory is the durable design and handoff package for autonomous
workflow orchestration. It is not a second authority for `docs/TASK_QUEUE.md`
or runtime workflow evidence.

Read in order:

1. `architecture-v3.md`
2. `implementation-plan.md`
3. `implementation-state.yaml` (the one authoritative implementation-state file)
4. the selected `stages/<stage-id>.md`
5. `session-protocol.md`

Supporting registries are `implementation-state.schema.yaml`,
`decision-log.md`, `migration-registry.yaml`, `evidence/`, `reviews/`,
`handoffs/`, and `prompts/`.

No production work is authorized until the independent `ORCH-000` review is
recorded as `REVIEW_APPROVED`.

