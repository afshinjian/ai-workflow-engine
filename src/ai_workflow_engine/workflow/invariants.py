from ai_workflow_engine.governance.validators import task_snapshot
from ai_workflow_engine.models import EngineConfig
from ai_workflow_engine.workflow.state import WorkflowSummary


def summarize_workflow(config: EngineConfig) -> WorkflowSummary:
    snapshot = task_snapshot(config)
    return WorkflowSummary(
        current_tasks=snapshot.current,
        done_tasks=snapshot.done,
        planned_tasks=snapshot.planned,
    )
