from pydantic import BaseModel


def render_json(model: BaseModel) -> str:
    """Stable field order and formatting for CI consumers."""
    return model.model_dump_json(indent=2, exclude_none=False)
