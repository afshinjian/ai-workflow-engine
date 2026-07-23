# AgentOS Dashboard — Stage Report Template

| Field | Value |
|---|---|
| **Title** | AgentOS Dashboard — Stage Report Template |
| **Purpose** | Mandatory skeleton for every `docs/reports/agentos-dashboard/STAGE-XX-completion.md`. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Documentation & Governance session · Human Owner (approval) |
| **Dependencies** | `stage-prompts/README.md` (SSP); `docs/AGENT_PROTOCOL.md` |
| **Related Documents** | `STAGE_REGISTRY.md` |

## Template

```markdown
# STAGE-XX Completion Report
- Stage identity / title / assigned role / objective
- Authorization evidence (owner directive quote + date; registry state)
- Initial repository state (branch, HEAD sha, git status output)
- Preconditions checked (each: PASS/FAIL + evidence)
## Implementation summary
## Architecture decisions (or "none")
## Created files / Modified files / Deleted files (exact lists)
## Database changes (dashboard.db only or "none") / API changes / UI changes / Security changes
## Tests added
## Validation
- Focused: <command> → <result>
- Regression (engine suite collection unchanged): python -m pytest tests --collect-only -q → <count>; pytest tests → <result>
- Quality: ruff check . / black --check . / mypy agentos_dashboard / pre-commit run --all-files / git diff --check → results
- Governance: workflowctl verify --config self-governance.yaml → per-check results (pre-existing failures identified as such)
- Changed-file scope audit: <allowed-list comparison result>
## Acceptance-criteria checklist (each criterion: PASS/FAIL + evidence)
## Known limitations / Risks / Deviations from plan
## Rollback instructions
## Git diff summary (`git diff --stat`)
## Recommended commit message
## Final stage status: COMPLETE | BLOCKED | RETURNED
## Confirmation: the next stage was NOT started, selected, or prepared; no commit, push, or merge was performed.
```
