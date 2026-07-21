"""Explicit (schema_name, schema_version) dispatch to a validating Pydantic model.

Registration is closed: only names and versions registered via ``register`` may be
looked up or dispatched. An unknown schema name or an unregistered version of a
known name always raises a stable, typed error rather than silently defaulting or
guessing compatibility — callers fail closed, per architecture-v3.md section 14.
"""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from ai_workflow_engine.exceptions import UnknownSchemaNameError, UnsupportedSchemaVersionError


class SchemaRegistry:
    """A closed registry mapping ``(name, version)`` to a Pydantic model class."""

    def __init__(self) -> None:
        self._schemas: dict[str, dict[str, type[BaseModel]]] = {}

    def register(self, name: str, version: str, model: type[BaseModel]) -> None:
        versions = self._schemas.setdefault(name, {})
        if version in versions:
            raise ValueError(f"schema {name!r} version {version!r} is already registered")
        versions[version] = model

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._schemas))

    def versions(self, name: str) -> tuple[str, ...]:
        self._require_name(name)
        return tuple(sorted(self._schemas[name]))

    def get(self, name: str, version: str) -> type[BaseModel]:
        """Return the registered model for ``name``/``version``, or fail closed."""
        self._require_name(name)
        try:
            return self._schemas[name][version]
        except KeyError:
            known = ", ".join(self.versions(name)) or "(none)"
            raise UnsupportedSchemaVersionError(
                f"schema {name!r} has no registered version {version!r}; "
                f"supported versions: {known}"
            ) from None

    def dispatch(self, name: str, version: str, payload: Mapping[str, Any]) -> BaseModel:
        """Validate ``payload`` against the model registered for ``name``/``version``."""
        model = self.get(name, version)
        return model.model_validate(payload)

    def _require_name(self, name: str) -> None:
        if name not in self._schemas:
            known = ", ".join(self.names()) or "(none)"
            raise UnknownSchemaNameError(f"unknown schema name {name!r}; known names: {known}")
