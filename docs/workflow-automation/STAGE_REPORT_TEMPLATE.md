# AgentOS Workflow Automation — Stage Report Template

| Field | Value |
|---|---|
| **Title** | AgentOS Workflow Automation — Stage Report Template |
| **Purpose** | Mandatory skeleton for every `docs/reports/workflow-automation/AUTO-0XX-completion-report.md`. |
| **Status** | Draft |
| **Version** | 1.0 |
| **Owner** | Documentation & Governance session · Human Owner (approval) |
| **Dependencies** | `stage-prompts/README.md` (SSP); `docs/AGENT_PROTOCOL.md` |
| **Related Documents** | `STAGE_REGISTRY.md` |

## Template

```markdown
# AUTO-0XX Completion Report
- Stage identity / title / assigned role / objective
- Authorization evidence (owner directive quote + date; registry state)
- Initial repository state (branch, HEAD sha, git status output)
- Preconditions checked (each: PASS/FAIL + evidence)
## Implementation summary
## Architecture decisions (or "none")
## Created files / Modified files / Deleted files (exact lists)
## Runtime code changes / Dependency changes / Security changes (each: exact list or "none")
## Tests added
## Validation
- Focused: <command> → <result>
- Regression (engine suite collection unchanged): python -m pytest tests --collect-only -q → <count>
- Quality: git diff --check → result
- Governance: workflowctl verify --config self-governance.yaml → per-check results
- Changed-file scope audit: <allowed-list comparison result>
## Acceptance-criteria checklist (each criterion: PASS/FAIL + evidence)
## Known limitations / Risks / Deviations from plan
## Open questions
## Git diff summary (`git diff --stat`)
## Recommended commit message
## Final stage status: COMPLETE | BLOCKED | RETURNED
## Confirmation: no commit, push, pull request, merge, or branch deletion was performed
```
