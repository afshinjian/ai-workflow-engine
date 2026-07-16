"""Parser for the project's Markdown checksum table format."""

import re

from pydantic import BaseModel, ConfigDict, Field

from ai_workflow_engine.config import normalize_repository_path
from ai_workflow_engine.exceptions import InvalidConfigurationError, ManifestParseError

ROW = re.compile(
    r"^\|\s*`?(?P<path>[^|`]+)`?\s*\|\s*(?P<size>\d+)\s*\|"
    r"(?:[^|]*\|)?\s*`?(?P<digest>[0-9a-fA-F]{8,64})(?:…|\.\.\.)?`?\s*\|\s*$"
)


class ManifestRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1)
    size: int = Field(ge=0)
    digest: str


def parse_manifest(data: bytes) -> list[ManifestRecord]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ManifestParseError("Checksum manifest is not UTF-8") from exc
    records: list[ManifestRecord] = []
    seen: set[str] = set()
    candidate_rows = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.startswith("|") or "---" in line or "Relative path" in line:
            continue
        candidate_rows += 1
        match = ROW.match(line)
        if not match:
            raise ManifestParseError(f"Malformed manifest record at line {line_number}: {line}")
        raw_path = match.group("path").strip()
        try:
            path = normalize_repository_path(raw_path)
        except InvalidConfigurationError as exc:
            raise ManifestParseError(
                f"Invalid manifest path at line {line_number}: {raw_path}: {exc}"
            ) from exc
        if path in seen:
            raise ManifestParseError(f"Duplicate manifest path at line {line_number}: {path}")
        seen.add(path)
        records.append(
            ManifestRecord(
                path=path, size=int(match.group("size")), digest=match.group("digest").lower()
            )
        )
    if candidate_rows == 0 or not records:
        raise ManifestParseError("Checksum manifest contains no records")
    return records
