# Current Task

Mirror of docs/TASK_QUEUE.md's Current set. This task was selected explicitly by the
Human Owner; no ordering was inferred.

## AUTO-009

Status: Current

Registered and authorized by the Human Owner on 2026-07-31 as the single `Current` task:
AUTO-009 — WorkflowService boundary and read-only `workflowctl auto` surface. The stage creates
the first public application-service boundary for the automated workflow engine and exposes only
read-only capabilities: `WorkflowService.status/list/audit/report`, plus the additive
`workflowctl auto status|list|audit|report` sub-application that forwards to it.

Implementation remains a separate phase and must stop for Human Owner approval before any
implementation or closeout commit, push, PR, or merge. Authorizing AUTO-009 authorizes no
successor; AUTO-010 and every later roadmap phase remain unauthorized.
