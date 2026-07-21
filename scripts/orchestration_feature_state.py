#!/usr/bin/env python3
"""Durable feature-state validator for the ORCH feature's implementation-state.yaml.

Implements ORCH-001 ("Durable feature-state validator"): a standalone,
dependency-free (stdlib + PyYAML only) tool that machine-enforces the
cross-session state-transition contract defined by
docs/implementation/orchestration/implementation-state.schema.yaml (structural
shape) and its trailing semantic-rules comment block, together with the legal
stage-transition table in docs/implementation/orchestration/session-protocol.md
section 2.

Three read/write surfaces:

- ``validate``   read-only: full structural + semantic validation of a state
                 file (optionally cross-checked against implementation-plan.md
                 and a prior state file for true append-only history proof).
- ``status``     read-only: recomputed current/candidate/next stage,
                 prerequisite closure and evidence/review health. Acquires no
                 lock and changes nothing (session-protocol.md section 9).
- ``transition`` the only write path: performs exactly one legal stage
                 transition, guarded by an optional CAS digest (optimistic
                 concurrency control), and replaces the state file atomically
                 (temp file + os.replace on the same filesystem).

This module exposes a small, pure, unit-testable function surface
(``validate_state``, ``compute_status``, ``check_transition_legal``,
``apply_transition``) in addition to the CLI in ``main``.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

# --------------------------------------------------------------------------
# Schema-derived constants (implementation-state.schema.yaml)
# --------------------------------------------------------------------------

STAGE_ID_PATTERN = re.compile(r"^ORCH-[0-9]{3}$")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")
BLOCKER_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]+$")

SCHEMA_NAME_CONST = "orchestration-implementation-state"
SCHEMA_VERSION_CONST = "1.0.0"
FEATURE_ID_CONST = "ORCH"
ARCHITECTURE_VERSION_CONST = "3.0.0"
PLAN_VERSION_CONST = "1.1.0"

PACKAGE_STATUS_ENUM = {"DRAFT", "PENDING_HUMAN_COMMIT", "PUBLISHED", "SUPERSEDED"}
WORKING_TREE_POLICY_ENUM = {"CLEAN_REQUIRED", "DESIGN_PACKAGE_PENDING_HUMAN_COMMIT"}
STAGE_STATUS_ENUM = {
    "NOT_STARTED",
    "IN_PROGRESS",
    "IMPLEMENTED",
    "VERIFIED",
    "REVIEW_REJECTED",
    "REVIEW_APPROVED",
    "BLOCKED",
    "SUPERSEDED",
}
REVIEW_STATUS_ENUM = {"NOT_REQUESTED", "PENDING", "REJECTED", "APPROVED"}
VERIFICATION_STATUS_ENUM = {"NOT_RUN", "FAILED", "PASSED"}
ROLE_ENUM = {
    "ARCHITECT",
    "IMPLEMENTER",
    "REVIEWER",
    "REMEDIATOR",
    "MIGRATOR",
    "RELEASE_MANAGER",
    "HUMAN_OWNER",
}
RISK_SEVERITY_ENUM = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

STAGE_REQUIRED_FIELDS = {
    "title",
    "status",
    "prerequisites",
    "expected_base_head",
    "implementation_commit",
    "implementer",
    "review_status",
    "reviewer",
    "verification_status",
    "evidence",
    "review_evidence",
    "handoff",
    "blockers",
}
BLOCKER_REQUIRED_FIELDS = {"code", "summary", "owner", "introduced_at", "resolution"}
HISTORY_REQUIRED_FIELDS = {"sequence", "at", "actor", "role", "action", "from", "to", "evidence"}
RISK_REQUIRED_FIELDS = {"id", "severity", "summary", "disposition"}
TOP_LEVEL_REQUIRED_FIELDS = {
    "schema_name",
    "schema_version",
    "feature_id",
    "architecture_version",
    "plan_version",
    "repository",
    "package_status",
    "current_stage",
    "next_eligible_stage",
    "candidate_next_stage",
    "delivery_order",
    "stages",
    "blockers",
    "schema_versions",
    "migrations",
    "history",
    "last_updated",
}
TOP_LEVEL_OPTIONAL_FIELDS = {"unresolved_risks"}
TOP_LEVEL_ALLOWED_FIELDS = TOP_LEVEL_REQUIRED_FIELDS | TOP_LEVEL_OPTIONAL_FIELDS
REPOSITORY_REQUIRED_FIELDS = {
    "project_id",
    "canonical_root",
    "branch",
    "expected_base_head",
    "package_commit",
    "working_tree_policy",
}

# --------------------------------------------------------------------------
# Legal transition table (session-protocol.md section 2)
# --------------------------------------------------------------------------
# roles=None means "any role in ROLE_ENUM" (the table's "Active role" /
# "appropriate role" wording).


@dataclass(frozen=True)
class TransitionRule:
    from_statuses: frozenset
    to_status: str
    roles: frozenset | None


LEGAL_TRANSITIONS: tuple[TransitionRule, ...] = (
    TransitionRule(frozenset({"NOT_STARTED"}), "IN_PROGRESS", frozenset({"IMPLEMENTER"})),
    TransitionRule(frozenset({"IN_PROGRESS"}), "IMPLEMENTED", frozenset({"IMPLEMENTER"})),
    TransitionRule(frozenset({"IMPLEMENTED"}), "VERIFIED", frozenset({"IMPLEMENTER"})),
    TransitionRule(frozenset({"IN_PROGRESS", "IMPLEMENTED", "VERIFIED"}), "BLOCKED", None),
    TransitionRule(frozenset({"VERIFIED"}), "REVIEW_APPROVED", frozenset({"REVIEWER"})),
    TransitionRule(frozenset({"VERIFIED"}), "REVIEW_REJECTED", frozenset({"REVIEWER"})),
    TransitionRule(frozenset({"REVIEW_REJECTED"}), "IN_PROGRESS", frozenset({"REMEDIATOR"})),
    TransitionRule(frozenset({"BLOCKED"}), "IN_PROGRESS", None),
    TransitionRule(
        frozenset({"NOT_STARTED", "IN_PROGRESS", "BLOCKED", "REVIEW_REJECTED"}),
        "SUPERSEDED",
        frozenset({"HUMAN_OWNER", "ARCHITECT"}),
    ),
)


def check_transition_legal(from_status: str, to_status: str, role: str) -> str | None:
    """Return None if legal, else a human-readable rejection reason."""
    matching_edges = [
        r for r in LEGAL_TRANSITIONS if to_status == r.to_status and from_status in r.from_statuses
    ]
    if not matching_edges:
        return (
            f"ILLEGAL_TRANSITION: {from_status} -> {to_status} is not in the legal transition table"
        )
    for rule in matching_edges:
        if rule.roles is None or role in rule.roles:
            return None
    allowed = sorted({r for rule in matching_edges for r in (rule.roles or ROLE_ENUM)})
    return (
        f"ROLE_NOT_AUTHORIZED: role {role!r} may not perform {from_status} -> {to_status} "
        f"(allowed: {allowed})"
    )


# --------------------------------------------------------------------------
# I/O helpers
# --------------------------------------------------------------------------


def compute_digest(raw_bytes: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw_bytes).hexdigest()


def read_state_bytes(path: Path) -> bytes:
    return path.read_bytes()


def load_yaml_bytes(raw: bytes) -> Any:
    return yaml.safe_load(raw)


def load_state_file(path: Path) -> tuple[Any, bytes, str]:
    raw = read_state_bytes(path)
    return load_yaml_bytes(raw), raw, compute_digest(raw)


def dump_state(state: dict) -> str:
    return yaml.safe_dump(state, sort_keys=False, default_flow_style=False, allow_unicode=True)


def write_state_atomic(path: Path, state: dict) -> None:
    """Atomic same-filesystem replace: write to a temp file, then os.replace."""
    text = dump_state(state)
    directory = path.parent
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(directory))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# --------------------------------------------------------------------------
# Structural (schema-shape) validation
# --------------------------------------------------------------------------


def _err(errors: list[str], path: str, message: str) -> None:
    errors.append(f"{path}: {message}")


def _check_pattern_or_null(value: Any, pattern: re.Pattern, path: str, errors: list[str]) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not pattern.match(value):
        _err(errors, path, f"must match {pattern.pattern!r} or be null, got {value!r}")


def _check_datetime(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str):
        _err(errors, path, f"must be an ISO-8601 date-time string, got {value!r}")
        return
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        datetime.fromisoformat(candidate)
    except ValueError:
        _err(errors, path, f"is not a valid ISO-8601 date-time: {value!r}")


def _validate_blocker(blocker: Any, path: str, errors: list[str]) -> None:
    if not isinstance(blocker, dict):
        _err(errors, path, "blocker must be an object")
        return
    missing = BLOCKER_REQUIRED_FIELDS - blocker.keys()
    extra = blocker.keys() - BLOCKER_REQUIRED_FIELDS
    if missing:
        _err(errors, path, f"missing required fields: {sorted(missing)}")
    if extra:
        _err(errors, path, f"unknown fields not allowed: {sorted(extra)}")
    code = blocker.get("code")
    if code is not None and (not isinstance(code, str) or not BLOCKER_CODE_PATTERN.match(code)):
        _err(errors, f"{path}.code", f"must match {BLOCKER_CODE_PATTERN.pattern!r}, got {code!r}")
    if not isinstance(blocker.get("summary"), str) or not blocker.get("summary"):
        _err(errors, f"{path}.summary", "must be a non-empty string")
    if not isinstance(blocker.get("owner"), str) or not blocker.get("owner"):
        _err(errors, f"{path}.owner", "must be a non-empty string")
    if "introduced_at" in blocker:
        _check_datetime(blocker["introduced_at"], f"{path}.introduced_at", errors)
    resolution = blocker.get("resolution")
    if resolution is not None and not isinstance(resolution, str):
        _err(errors, f"{path}.resolution", "must be a string or null")


def _validate_stage(stage_id: str, stage: Any, errors: list[str]) -> None:
    path = f"stages.{stage_id}"
    if not isinstance(stage, dict):
        _err(errors, path, "stage must be an object")
        return
    missing = STAGE_REQUIRED_FIELDS - stage.keys()
    extra = stage.keys() - STAGE_REQUIRED_FIELDS
    if missing:
        _err(errors, path, f"missing required fields: {sorted(missing)}")
    if extra:
        _err(errors, path, f"unknown fields not allowed: {sorted(extra)}")
    if not isinstance(stage.get("title"), str) or not stage.get("title"):
        _err(errors, f"{path}.title", "must be a non-empty string")
    if stage.get("status") not in STAGE_STATUS_ENUM:
        _err(
            errors,
            f"{path}.status",
            f"must be one of {sorted(STAGE_STATUS_ENUM)}, got {stage.get('status')!r}",
        )
    prereqs = stage.get("prerequisites")
    if not isinstance(prereqs, list):
        _err(errors, f"{path}.prerequisites", "must be an array")
    else:
        if len(set(prereqs)) != len(prereqs):
            _err(errors, f"{path}.prerequisites", "must not contain duplicates")
        for i, p in enumerate(prereqs):
            if not isinstance(p, str) or not STAGE_ID_PATTERN.match(p):
                _err(
                    errors,
                    f"{path}.prerequisites[{i}]",
                    f"must match {STAGE_ID_PATTERN.pattern!r}, got {p!r}",
                )
    _check_pattern_or_null(
        stage.get("expected_base_head"), SHA_PATTERN, f"{path}.expected_base_head", errors
    )
    _check_pattern_or_null(
        stage.get("implementation_commit"), SHA_PATTERN, f"{path}.implementation_commit", errors
    )
    if (
        "implementer" in stage
        and stage["implementer"] is not None
        and not isinstance(stage["implementer"], str)
    ):
        _err(errors, f"{path}.implementer", "must be a string or null")
    if stage.get("review_status") not in REVIEW_STATUS_ENUM:
        _err(errors, f"{path}.review_status", f"must be one of {sorted(REVIEW_STATUS_ENUM)}")
    if (
        "reviewer" in stage
        and stage["reviewer"] is not None
        and not isinstance(stage["reviewer"], str)
    ):
        _err(errors, f"{path}.reviewer", "must be a string or null")
    if stage.get("verification_status") not in VERIFICATION_STATUS_ENUM:
        _err(
            errors,
            f"{path}.verification_status",
            f"must be one of {sorted(VERIFICATION_STATUS_ENUM)}",
        )
    for field_name in ("evidence", "review_evidence"):
        arr = stage.get(field_name)
        if not isinstance(arr, list) or not all(isinstance(x, str) for x in arr):
            _err(errors, f"{path}.{field_name}", "must be an array of strings")
        elif len(set(arr)) != len(arr):
            _err(errors, f"{path}.{field_name}", "must not contain duplicates")
    if (
        "handoff" in stage
        and stage["handoff"] is not None
        and not isinstance(stage["handoff"], str)
    ):
        _err(errors, f"{path}.handoff", "must be a string or null")
    blockers = stage.get("blockers")
    if not isinstance(blockers, list):
        _err(errors, f"{path}.blockers", "must be an array")
    else:
        for i, b in enumerate(blockers):
            _validate_blocker(b, f"{path}.blockers[{i}]", errors)


def validate_schema(state: Any) -> list[str]:
    """Structural validation mirroring implementation-state.schema.yaml."""
    errors: list[str] = []
    if not isinstance(state, dict):
        return ["<root>: state document must be a mapping"]

    missing = TOP_LEVEL_REQUIRED_FIELDS - state.keys()
    extra = state.keys() - TOP_LEVEL_ALLOWED_FIELDS
    if missing:
        _err(errors, "<root>", f"missing required fields: {sorted(missing)}")
    if extra:
        _err(errors, "<root>", f"unknown fields not allowed: {sorted(extra)}")

    if state.get("schema_name") != SCHEMA_NAME_CONST:
        _err(errors, "schema_name", f"must equal {SCHEMA_NAME_CONST!r}")
    if state.get("schema_version") != SCHEMA_VERSION_CONST:
        _err(errors, "schema_version", f"must equal {SCHEMA_VERSION_CONST!r}")
    if state.get("feature_id") != FEATURE_ID_CONST:
        _err(errors, "feature_id", f"must equal {FEATURE_ID_CONST!r}")
    if state.get("architecture_version") != ARCHITECTURE_VERSION_CONST:
        _err(errors, "architecture_version", f"must equal {ARCHITECTURE_VERSION_CONST!r}")
    if state.get("plan_version") != PLAN_VERSION_CONST:
        _err(errors, "plan_version", f"must equal {PLAN_VERSION_CONST!r}")

    repository = state.get("repository")
    if not isinstance(repository, dict):
        _err(errors, "repository", "must be an object")
    else:
        rmissing = REPOSITORY_REQUIRED_FIELDS - repository.keys()
        rextra = repository.keys() - REPOSITORY_REQUIRED_FIELDS
        if rmissing:
            _err(errors, "repository", f"missing required fields: {sorted(rmissing)}")
        if rextra:
            _err(errors, "repository", f"unknown fields not allowed: {sorted(rextra)}")
        if not isinstance(repository.get("project_id"), str) or not repository.get("project_id"):
            _err(errors, "repository.project_id", "must be a non-empty string")
        root = repository.get("canonical_root")
        if not isinstance(root, str) or not root.startswith("/"):
            _err(errors, "repository.canonical_root", "must be a string starting with '/'")
        if not isinstance(repository.get("branch"), str) or not repository.get("branch"):
            _err(errors, "repository.branch", "must be a non-empty string")
        _check_pattern_or_null(
            repository.get("expected_base_head"),
            SHA_PATTERN,
            "repository.expected_base_head",
            errors,
        )
        _check_pattern_or_null(
            repository.get("package_commit"), SHA_PATTERN, "repository.package_commit", errors
        )
        if repository.get("working_tree_policy") not in WORKING_TREE_POLICY_ENUM:
            _err(
                errors,
                "repository.working_tree_policy",
                f"must be one of {sorted(WORKING_TREE_POLICY_ENUM)}",
            )

    if state.get("package_status") not in PACKAGE_STATUS_ENUM:
        _err(errors, "package_status", f"must be one of {sorted(PACKAGE_STATUS_ENUM)}")

    for key in ("current_stage", "next_eligible_stage", "candidate_next_stage"):
        _check_pattern_or_null(state.get(key), STAGE_ID_PATTERN, key, errors)

    delivery_order = state.get("delivery_order")
    if not isinstance(delivery_order, list) or not delivery_order:
        _err(errors, "delivery_order", "must be a non-empty array")
    else:
        for i, sid in enumerate(delivery_order):
            if not isinstance(sid, str) or not STAGE_ID_PATTERN.match(sid):
                _err(
                    errors,
                    f"delivery_order[{i}]",
                    f"must match {STAGE_ID_PATTERN.pattern!r}, got {sid!r}",
                )
        if len(set(delivery_order)) != len(delivery_order):
            _err(errors, "delivery_order", "must not contain duplicates")

    stages = state.get("stages")
    if not isinstance(stages, dict) or not stages:
        _err(errors, "stages", "must be a non-empty object")
    else:
        for stage_id, stage in stages.items():
            if not isinstance(stage_id, str) or not STAGE_ID_PATTERN.match(stage_id):
                _err(errors, f"stages.{stage_id}", f"key must match {STAGE_ID_PATTERN.pattern!r}")
            _validate_stage(stage_id, stage, errors)

    blockers = state.get("blockers")
    if not isinstance(blockers, list):
        _err(errors, "blockers", "must be an array")
    else:
        for i, b in enumerate(blockers):
            _validate_blocker(b, f"blockers[{i}]", errors)

    schema_versions = state.get("schema_versions")
    if not isinstance(schema_versions, dict) or not all(
        isinstance(v, str) for v in schema_versions.values()
    ):
        _err(errors, "schema_versions", "must be an object mapping strings to strings")

    migrations = state.get("migrations")
    if not isinstance(migrations, dict):
        _err(errors, "migrations", "must be an object")
    else:
        mmissing = {"required", "completed", "blocked"} - migrations.keys()
        mextra = migrations.keys() - {"required", "completed", "blocked"}
        if mmissing:
            _err(errors, "migrations", f"missing required fields: {sorted(mmissing)}")
        if mextra:
            _err(errors, "migrations", f"unknown fields not allowed: {sorted(mextra)}")
        for key in ("required", "completed", "blocked"):
            arr = migrations.get(key)
            if not isinstance(arr, list) or not all(isinstance(x, str) for x in arr):
                _err(errors, f"migrations.{key}", "must be an array of strings")
            elif arr is not None and len(set(arr)) != len(arr):
                _err(errors, f"migrations.{key}", "must not contain duplicates")

    if "unresolved_risks" in state:
        risks = state["unresolved_risks"]
        if not isinstance(risks, list):
            _err(errors, "unresolved_risks", "must be an array")
        else:
            for i, risk in enumerate(risks):
                rpath = f"unresolved_risks[{i}]"
                if not isinstance(risk, dict):
                    _err(errors, rpath, "must be an object")
                    continue
                rmissing = RISK_REQUIRED_FIELDS - risk.keys()
                rextra = risk.keys() - RISK_REQUIRED_FIELDS
                if rmissing:
                    _err(errors, rpath, f"missing required fields: {sorted(rmissing)}")
                if rextra:
                    _err(errors, rpath, f"unknown fields not allowed: {sorted(rextra)}")
                if risk.get("severity") not in RISK_SEVERITY_ENUM:
                    _err(
                        errors, f"{rpath}.severity", f"must be one of {sorted(RISK_SEVERITY_ENUM)}"
                    )

    history = state.get("history")
    if not isinstance(history, list):
        _err(errors, "history", "must be an array")
    else:
        for i, entry in enumerate(history):
            hpath = f"history[{i}]"
            if not isinstance(entry, dict):
                _err(errors, hpath, "must be an object")
                continue
            hmissing = HISTORY_REQUIRED_FIELDS - entry.keys()
            hextra = entry.keys() - HISTORY_REQUIRED_FIELDS
            if hmissing:
                _err(errors, hpath, f"missing required fields: {sorted(hmissing)}")
            if hextra:
                _err(errors, hpath, f"unknown fields not allowed: {sorted(hextra)}")
            if not isinstance(entry.get("sequence"), int) or isinstance(
                entry.get("sequence"), bool
            ):
                _err(errors, f"{hpath}.sequence", "must be an integer >= 1")
            elif entry["sequence"] < 1:
                _err(errors, f"{hpath}.sequence", "must be >= 1")
            if "at" in entry:
                _check_datetime(entry["at"], f"{hpath}.at", errors)
            if not isinstance(entry.get("actor"), str) or not entry.get("actor"):
                _err(errors, f"{hpath}.actor", "must be a non-empty string")
            if entry.get("role") not in ROLE_ENUM:
                _err(errors, f"{hpath}.role", f"must be one of {sorted(ROLE_ENUM)}")
            if not isinstance(entry.get("action"), str) or not entry.get("action"):
                _err(errors, f"{hpath}.action", "must be a non-empty string")
            for key in ("from", "to"):
                if key in entry and entry[key] is not None and not isinstance(entry[key], str):
                    _err(errors, f"{hpath}.{key}", "must be a string or null")
            if not isinstance(entry.get("evidence"), list) or not all(
                isinstance(x, str) for x in entry.get("evidence", [])
            ):
                _err(errors, f"{hpath}.evidence", "must be an array of strings")

    last_updated = state.get("last_updated")
    if not isinstance(last_updated, dict):
        _err(errors, "last_updated", "must be an object")
    else:
        lmissing = {"at", "by", "role", "reason"} - last_updated.keys()
        lextra = last_updated.keys() - {"at", "by", "role", "reason"}
        if lmissing:
            _err(errors, "last_updated", f"missing required fields: {sorted(lmissing)}")
        if lextra:
            _err(errors, "last_updated", f"unknown fields not allowed: {sorted(lextra)}")
        if "at" in last_updated:
            _check_datetime(last_updated["at"], "last_updated.at", errors)
        if not isinstance(last_updated.get("by"), str) or not last_updated.get("by"):
            _err(errors, "last_updated.by", "must be a non-empty string")
        if last_updated.get("role") not in ROLE_ENUM:
            _err(errors, "last_updated.role", f"must be one of {sorted(ROLE_ENUM)}")
        if not isinstance(last_updated.get("reason"), str) or not last_updated.get("reason"):
            _err(errors, "last_updated.reason", "must be a non-empty string")

    return errors


# --------------------------------------------------------------------------
# Semantic validation (implementation-state.schema.yaml trailing comment block)
# --------------------------------------------------------------------------

PLAN_STAGE_ROW_PATTERN = re.compile(r"^\|\s*(ORCH-\d{3})\s*\|")


def extract_plan_stage_ids(plan_text: str) -> set[str]:
    """Stage IDs from implementation-plan.md's '## 3. Ordered stage graph' table."""
    ids: set[str] = set()
    for line in plan_text.splitlines():
        m = PLAN_STAGE_ROW_PATTERN.match(line)
        if m:
            ids.add(m.group(1))
    return ids


def has_open_global_blocker(state: dict) -> bool:
    return any(
        b.get("resolution") is None for b in state.get("blockers", []) if isinstance(b, dict)
    )


def recompute_next_eligible(state: dict) -> str | None:
    """First non-approved delivery-order entry whose prerequisites are all
    REVIEW_APPROVED; null whenever an open global blocker exists."""
    if has_open_global_blocker(state):
        return None
    stages = state.get("stages", {})
    for stage_id in state.get("delivery_order", []):
        stage = stages.get(stage_id)
        if stage is None:
            continue
        if stage.get("status") == "REVIEW_APPROVED":
            continue
        prereqs = stage.get("prerequisites", [])
        if all(stages.get(p, {}).get("status") == "REVIEW_APPROVED" for p in prereqs):
            return stage_id
    return None


def _find_cycle(stages: dict) -> list[str] | None:
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {sid: WHITE for sid in stages}
    path: list[str] = []

    def visit(node: str) -> list[str] | None:
        color[node] = GRAY
        path.append(node)
        for dep in stages.get(node, {}).get("prerequisites", []) or []:
            if dep not in stages:
                continue
            if color.get(dep, WHITE) == GRAY:
                cycle_start = path.index(dep)
                return [*path[cycle_start:], dep]
            if color.get(dep, WHITE) == WHITE:
                result = visit(dep)
                if result:
                    return result
        path.pop()
        color[node] = BLACK
        return None

    for sid in stages:
        if color[sid] == WHITE:
            result = visit(sid)
            if result:
                return result
    return None


def validate_semantics(state: dict, plan_stage_ids: set[str] | None = None) -> list[str]:
    errors: list[str] = []
    stages = state.get("stages", {})
    stage_ids = set(stages.keys())
    delivery_order = state.get("delivery_order", [])

    # Rule: stages keys exactly match plan stage IDs.
    if plan_stage_ids is not None:
        missing = plan_stage_ids - stage_ids
        extra = stage_ids - plan_stage_ids
        if missing:
            _err(
                errors,
                "stages",
                f"missing stage keys present in implementation-plan.md: {sorted(missing)}",
            )
        if extra:
            _err(
                errors,
                "stages",
                f"stage keys not present in implementation-plan.md: {sorted(extra)}",
            )

    # Rule: prerequisites exist and form an acyclic graph.
    for stage_id, stage in stages.items():
        for prereq in stage.get("prerequisites", []) or []:
            if prereq not in stage_ids:
                _err(
                    errors,
                    f"stages.{stage_id}.prerequisites",
                    f"references unknown stage {prereq!r}",
                )
    cycle = _find_cycle(stages)
    if cycle:
        _err(
            errors,
            "stages.*.prerequisites",
            f"prerequisite graph has a cycle: {' -> '.join(cycle)}",
        )

    # Rule: delivery_order contains every stage key exactly once.
    if set(delivery_order) != stage_ids or len(delivery_order) != len(stage_ids):
        _err(
            errors,
            "delivery_order",
            f"must contain every stage key exactly once (delivery_order has {len(delivery_order)} "
            f"entries, {len(set(delivery_order))} unique, stages has {len(stage_ids)} keys)",
        )

    # Rule: next_eligible_stage / candidate_next_stage recomputation.
    if not cycle:
        recomputed = recompute_next_eligible(state)
        if state.get("next_eligible_stage") != recomputed:
            _err(
                errors,
                "next_eligible_stage",
                f"declared {state.get('next_eligible_stage')!r} but recomputes to {recomputed!r}",
            )
        if state.get("candidate_next_stage") != state.get("next_eligible_stage"):
            _err(
                errors,
                "candidate_next_stage",
                f"must equal next_eligible_stage ({state.get('next_eligible_stage')!r}), "
                f"got {state.get('candidate_next_stage')!r}",
            )

    # Rule: only REVIEWER may make VERIFIED -> REVIEW_APPROVED/REVIEW_REJECTED.
    for i, entry in enumerate(state.get("history", [])):
        if entry.get("from") == "VERIFIED" and entry.get("to") in (
            "REVIEW_APPROVED",
            "REVIEW_REJECTED",
        ):
            if entry.get("role") != "REVIEWER":
                _err(
                    errors,
                    f"history[{i}]",
                    f"VERIFIED -> {entry.get('to')} requires role REVIEWER, "
                    f"got {entry.get('role')!r}",
                )

    # Rule: reviewer must differ from implementer for approval.
    for stage_id, stage in stages.items():
        if stage.get("status") == "REVIEW_APPROVED" or stage.get("review_status") == "APPROVED":
            if stage.get("reviewer") is not None and stage.get("reviewer") == stage.get(
                "implementer"
            ):
                _err(
                    errors,
                    f"stages.{stage_id}",
                    "reviewer must differ from implementer for approval, "
                    f"both are {stage.get('reviewer')!r}",
                )

    # Rule: passed implementation evidence required at VERIFIED (and beyond,
    # since REVIEW_APPROVED/REVIEW_REJECTED are only reachable from VERIFIED).
    # implementation_commit may remain null (uncommitted implementer handoff).
    for stage_id, stage in stages.items():
        if stage.get("status") in ("VERIFIED", "REVIEW_APPROVED"):
            if stage.get("verification_status") != "PASSED":
                _err(
                    errors,
                    f"stages.{stage_id}.verification_status",
                    "must be PASSED at VERIFIED or later",
                )
            if not stage.get("evidence"):
                _err(
                    errors, f"stages.{stage_id}.evidence", "must be non-empty at VERIFIED or later"
                )

    # Rule: REVIEW_APPROVED requires implementation_commit and approved review evidence.
    for stage_id, stage in stages.items():
        if stage.get("status") == "REVIEW_APPROVED":
            if not stage.get("implementation_commit"):
                _err(
                    errors,
                    f"stages.{stage_id}.implementation_commit",
                    "must be set at REVIEW_APPROVED",
                )
            if not stage.get("review_evidence"):
                _err(
                    errors,
                    f"stages.{stage_id}.review_evidence",
                    "must be non-empty at REVIEW_APPROVED",
                )
            if stage.get("review_status") != "APPROVED":
                _err(
                    errors,
                    f"stages.{stage_id}.review_status",
                    "must be APPROVED at REVIEW_APPROVED",
                )

    # Rule: history sequence is contiguous and append-only (self-consistency).
    history = state.get("history", [])
    sequences = [
        entry.get("sequence") for entry in history if isinstance(entry.get("sequence"), int)
    ]
    expected = list(range(1, len(history) + 1))
    if sequences != expected:
        _err(
            errors,
            "history",
            f"sequence numbers must be exactly contiguous 1..N in order, got {sequences}",
        )

    # Additional invariant (not in the schema's literal list, but required by
    # session-protocol.md's "record current HEAD as the selected stage's
    # expected_base_head" instruction): once a stage has left NOT_STARTED its
    # expected_base_head must be explicitly recorded, not left null.
    for stage_id, stage in stages.items():
        if stage.get("status") not in ("NOT_STARTED",) and not stage.get("expected_base_head"):
            _err(
                errors,
                f"stages.{stage_id}.expected_base_head",
                "must be recorded (non-null) once a stage has left NOT_STARTED",
            )

    return errors


def validate_history_append_only(previous_history: list, current_history: list) -> list[str]:
    """True cross-version proof of append-only history: the new history must
    be exactly the old history plus zero or more new entries, byte-identical
    on the shared prefix."""
    errors: list[str] = []
    if len(current_history) < len(previous_history):
        _err(
            errors, "history", "is shorter than the previous state's history (entries were removed)"
        )
        return errors
    for i, prior_entry in enumerate(previous_history):
        if current_history[i] != prior_entry:
            _err(
                errors,
                f"history[{i}]",
                "differs from the previously committed entry (history was rewritten)",
            )
    return errors


@dataclass
class ValidationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"status": "PASS" if self.passed else "FAIL", "errors": self.errors}


def validate_state(
    state: Any,
    plan_text: str | None = None,
    previous_state: Any | None = None,
) -> ValidationResult:
    errors = validate_schema(state)
    if not errors and isinstance(state, dict):
        plan_stage_ids = extract_plan_stage_ids(plan_text) if plan_text is not None else None
        errors.extend(validate_semantics(state, plan_stage_ids))
        if previous_state is not None and isinstance(previous_state, dict):
            errors.extend(
                validate_history_append_only(
                    previous_state.get("history", []), state.get("history", [])
                )
            )
    return ValidationResult(passed=not errors, errors=errors)


# --------------------------------------------------------------------------
# status (read-only report)
# --------------------------------------------------------------------------


def compute_status(state: dict) -> dict:
    stages = state.get("stages", {})
    recomputed_next = recompute_next_eligible(state)
    stage_reports = {}
    for stage_id, stage in stages.items():
        prereqs = stage.get("prerequisites", [])
        prereqs_closed = all(stages.get(p, {}).get("status") == "REVIEW_APPROVED" for p in prereqs)
        stage_reports[stage_id] = {
            "status": stage.get("status"),
            "review_status": stage.get("review_status"),
            "verification_status": stage.get("verification_status"),
            "prerequisites": prereqs,
            "prerequisites_closed": prereqs_closed,
            "eligible_now": prereqs_closed and stage.get("status") != "REVIEW_APPROVED",
            "evidence_count": len(stage.get("evidence", [])),
            "review_evidence_count": len(stage.get("review_evidence", [])),
            "blockers_open": [b for b in stage.get("blockers", []) if b.get("resolution") is None],
        }
    return {
        "package_status": state.get("package_status"),
        "current_stage": state.get("current_stage"),
        "declared_next_eligible_stage": state.get("next_eligible_stage"),
        "recomputed_next_eligible_stage": recomputed_next,
        "next_eligible_matches_declared": recomputed_next == state.get("next_eligible_stage"),
        "candidate_next_stage": state.get("candidate_next_stage"),
        "global_blockers_open": [
            b for b in state.get("blockers", []) if b.get("resolution") is None
        ],
        "history_length": len(state.get("history", [])),
        "stages": stage_reports,
    }


# --------------------------------------------------------------------------
# transition (the only write path)
# --------------------------------------------------------------------------


class TransitionError(Exception):
    pass


def apply_transition(
    state: dict,
    *,
    stage_id: str,
    to_status: str,
    actor: str,
    role: str,
    action: str,
    reason: str,
    at: str,
    evidence: list[str] | None = None,
    implementer: str | None = None,
    reviewer: str | None = None,
    review_status: str | None = None,
    verification_status: str | None = None,
    implementation_commit: str | None = None,
    clear_implementation_commit: bool = False,
    expected_base_head: str | None = None,
    add_evidence: list[str] | None = None,
    add_review_evidence: list[str] | None = None,
    handoff: str | None = None,
    add_blockers: list[dict] | None = None,
    resolve_blockers: dict[str, str] | None = None,
    add_global_blockers: list[dict] | None = None,
    resolve_global_blockers: dict[str, str] | None = None,
) -> dict:
    """Pure function: returns a new state dict reflecting exactly one legal
    stage transition. Raises TransitionError on any illegal request. Performs
    no I/O."""
    if role not in ROLE_ENUM:
        raise TransitionError(f"INVALID_ROLE: {role!r} is not one of {sorted(ROLE_ENUM)}")
    if to_status not in STAGE_STATUS_ENUM:
        raise TransitionError(
            f"INVALID_STATUS: {to_status!r} is not one of {sorted(STAGE_STATUS_ENUM)}"
        )

    stages = state.get("stages", {})
    stage = stages.get(stage_id)
    if stage is None:
        raise TransitionError(f"UNKNOWN_STAGE: {stage_id!r} is not present in stages")
    from_status = stage.get("status")

    rejection = check_transition_legal(from_status, to_status, role)
    if rejection:
        raise TransitionError(rejection)

    if from_status == "NOT_STARTED" and to_status == "IN_PROGRESS":
        recomputed = recompute_next_eligible(state)
        if recomputed != stage_id:
            raise TransitionError(
                f"NOT_UNIQUELY_ELIGIBLE: {stage_id!r} is not the sole next_eligible_stage "
                f"(recomputes to {recomputed!r})"
            )
        if not expected_base_head:
            raise TransitionError(
                "MISSING_EXPECTED_BASE_HEAD: required to start NOT_STARTED -> IN_PROGRESS"
            )

    if from_status == "BLOCKED" and to_status == "IN_PROGRESS":
        # session-protocol.md section 2, BLOCKED -> IN_PROGRESS row: "blocker
        # resolution is evidenced and prerequisites still approved". A blocker
        # counts as resolved if it already carries a non-null resolution, or
        # if this same call resolves it via resolve_blockers.
        resolved_now = set(resolve_blockers or {})
        unresolved_codes = sorted(
            {
                b.get("code")
                for b in stage.get("blockers", []) or []
                if b.get("resolution") is None and b.get("code") not in resolved_now
            }
        )
        if unresolved_codes:
            raise TransitionError(
                "UNRESOLVED_BLOCKER: cannot resume BLOCKED -> IN_PROGRESS while blocker(s) "
                f"{unresolved_codes} remain unresolved"
            )
        unapproved_prereqs = sorted(
            p
            for p in stage.get("prerequisites", []) or []
            if stages.get(p, {}).get("status") != "REVIEW_APPROVED"
        )
        if unapproved_prereqs:
            raise TransitionError(
                "PREREQUISITE_NOT_APPROVED: cannot resume BLOCKED -> IN_PROGRESS while "
                f"prerequisite(s) {unapproved_prereqs} are not REVIEW_APPROVED"
            )

    effective_reviewer = reviewer if reviewer is not None else actor
    if to_status in ("REVIEW_APPROVED", "REVIEW_REJECTED"):
        if effective_reviewer == stage.get("implementer"):
            raise TransitionError(
                f"REVIEWER_EQUALS_IMPLEMENTER: reviewer {effective_reviewer!r} must differ from "
                f"implementer {stage.get('implementer')!r}"
            )

    if to_status == "REVIEW_APPROVED":
        pending_commit = (
            implementation_commit
            if implementation_commit is not None
            else stage.get("implementation_commit")
        )
        if not pending_commit:
            raise TransitionError(
                "MISSING_IMPLEMENTATION_COMMIT: required to reach REVIEW_APPROVED"
            )

    if to_status == "BLOCKED" and not (add_blockers or stage.get("blockers")):
        raise TransitionError(
            "MISSING_BLOCKER: at least one blocker record is required to reach BLOCKED"
        )

    new_state = copy.deepcopy(state)
    new_stage = new_state["stages"][stage_id]
    new_stage["status"] = to_status

    if implementer is not None:
        new_stage["implementer"] = implementer
    elif from_status == "NOT_STARTED" and to_status == "IN_PROGRESS":
        new_stage["implementer"] = actor
    elif from_status == "REVIEW_REJECTED" and to_status == "IN_PROGRESS":
        new_stage["implementer"] = actor

    if to_status in ("REVIEW_APPROVED", "REVIEW_REJECTED"):
        new_stage["reviewer"] = effective_reviewer
    elif reviewer is not None:
        new_stage["reviewer"] = reviewer

    if review_status is not None:
        if review_status not in REVIEW_STATUS_ENUM:
            raise TransitionError(f"INVALID_REVIEW_STATUS: {review_status!r}")
        new_stage["review_status"] = review_status
    elif to_status == "REVIEW_APPROVED":
        new_stage["review_status"] = "APPROVED"
    elif to_status == "REVIEW_REJECTED":
        new_stage["review_status"] = "REJECTED"

    if verification_status is not None:
        if verification_status not in VERIFICATION_STATUS_ENUM:
            raise TransitionError(f"INVALID_VERIFICATION_STATUS: {verification_status!r}")
        new_stage["verification_status"] = verification_status

    if clear_implementation_commit:
        new_stage["implementation_commit"] = None
    elif implementation_commit is not None:
        if not SHA_PATTERN.match(implementation_commit):
            raise TransitionError(f"INVALID_SHA: implementation_commit {implementation_commit!r}")
        new_stage["implementation_commit"] = implementation_commit

    if expected_base_head is not None:
        if not SHA_PATTERN.match(expected_base_head):
            raise TransitionError(f"INVALID_SHA: expected_base_head {expected_base_head!r}")
        new_stage["expected_base_head"] = expected_base_head

    for e in add_evidence or []:
        if e not in new_stage["evidence"]:
            new_stage["evidence"].append(e)
    for e in add_review_evidence or []:
        if e not in new_stage["review_evidence"]:
            new_stage["review_evidence"].append(e)

    if handoff is not None:
        new_stage["handoff"] = handoff

    for blocker in add_blockers or []:
        berrors: list[str] = []
        _validate_blocker(blocker, f"stages.{stage_id}.blockers[new]", berrors)
        if berrors:
            raise TransitionError(f"INVALID_BLOCKER: {berrors}")
        new_stage["blockers"].append(blocker)
    for code, resolution_text in (resolve_blockers or {}).items():
        matched = [b for b in new_stage["blockers"] if b.get("code") == code]
        if not matched:
            raise TransitionError(f"UNKNOWN_BLOCKER_CODE: {code!r} not found on stage {stage_id!r}")
        for b in matched:
            b["resolution"] = resolution_text

    for blocker in add_global_blockers or []:
        berrors = []
        _validate_blocker(blocker, "blockers[new]", berrors)
        if berrors:
            raise TransitionError(f"INVALID_BLOCKER: {berrors}")
        new_state["blockers"].append(blocker)
    for code, resolution_text in (resolve_global_blockers or {}).items():
        matched = [b for b in new_state["blockers"] if b.get("code") == code]
        if not matched:
            raise TransitionError(f"UNKNOWN_GLOBAL_BLOCKER_CODE: {code!r} not found")
        for b in matched:
            b["resolution"] = resolution_text

    history = new_state["history"]
    next_sequence = (max((h["sequence"] for h in history), default=0)) + 1
    history.append(
        {
            "sequence": next_sequence,
            "at": at,
            "actor": actor,
            "role": role,
            "action": action,
            "from": from_status,
            "to": to_status,
            "evidence": list(evidence or []),
        }
    )

    recomputed_next = recompute_next_eligible(new_state)
    new_state["next_eligible_stage"] = recomputed_next
    new_state["candidate_next_stage"] = recomputed_next
    if recomputed_next is not None:
        new_state["current_stage"] = recomputed_next

    new_state["last_updated"] = {"at": at, "by": actor, "role": role, "reason": reason}

    return new_state


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _print_result(payload: dict, output: str) -> None:
    if output == "json":
        print(json.dumps(payload, indent=2, sort_keys=False))
    else:
        print(yaml.safe_dump(payload, sort_keys=False, default_flow_style=False))


def _cmd_validate(args: argparse.Namespace) -> int:
    state_path = Path(args.state)
    state, _, digest = load_state_file(state_path)
    plan_text = Path(args.plan).read_text(encoding="utf-8") if args.plan else None
    previous_state = None
    if args.previous_state:
        previous_state, _, _ = load_state_file(Path(args.previous_state))
    result = validate_state(state, plan_text=plan_text, previous_state=previous_state)
    payload = result.to_dict()
    payload["state_digest"] = digest
    _print_result(payload, args.output)
    return 0 if result.passed else 1


def _cmd_status(args: argparse.Namespace) -> int:
    state_path = Path(args.state)
    state, _, digest = load_state_file(state_path)
    payload = compute_status(state)
    payload["state_digest"] = digest
    _print_result(payload, args.output)
    return 0


def _cmd_digest(args: argparse.Namespace) -> int:
    raw = read_state_bytes(Path(args.state))
    print(compute_digest(raw))
    return 0


def _parse_kv_list(pairs: list[str] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in pairs or []:
        if "=" not in item:
            raise SystemExit(f"error: expected CODE=TEXT, got {item!r}")
        code, text = item.split("=", 1)
        result[code] = text
    return result


def _cmd_transition(args: argparse.Namespace) -> int:
    state_path = Path(args.state)
    state, _, digest = load_state_file(state_path)

    if args.expected_digest and args.expected_digest != digest:
        print(
            json.dumps(
                {
                    "status": "REJECTED",
                    "error": "CAS_MISMATCH",
                    "message": (
                        f"expected digest {args.expected_digest!r} but file is currently "
                        f"{digest!r}; the state file was modified since it was last read"
                    ),
                },
                indent=2,
            )
        )
        return 1

    action = args.action or f"{args.to}_{args.stage.replace('-', '_')}"
    at = args.at or _now_iso()

    add_blockers = [json.loads(b) for b in (args.add_blocker or [])]
    add_global_blockers = [json.loads(b) for b in (args.add_global_blocker or [])]

    try:
        new_state = apply_transition(
            state,
            stage_id=args.stage,
            to_status=args.to,
            actor=args.actor,
            role=args.role,
            action=action,
            reason=args.reason,
            at=at,
            evidence=args.evidence or [],
            implementer=args.implementer,
            reviewer=args.reviewer,
            review_status=args.review_status,
            verification_status=args.verification_status,
            implementation_commit=args.implementation_commit,
            clear_implementation_commit=args.clear_implementation_commit,
            expected_base_head=args.expected_base_head,
            add_evidence=args.add_evidence or [],
            add_review_evidence=args.add_review_evidence or [],
            handoff=args.handoff,
            add_blockers=add_blockers,
            resolve_blockers=_parse_kv_list(args.resolve_blocker),
            add_global_blockers=add_global_blockers,
            resolve_global_blockers=_parse_kv_list(args.resolve_global_blocker),
        )
    except TransitionError as exc:
        print(json.dumps({"status": "REJECTED", "error": str(exc)}, indent=2))
        return 1

    result = validate_state(new_state)
    if not result.passed:
        print(
            json.dumps(
                {"status": "REJECTED", "error": "RESULT_WOULD_BE_INVALID", "errors": result.errors},
                indent=2,
            )
        )
        return 1

    new_digest = compute_digest(dump_state(new_state).encode("utf-8"))
    payload = {
        "status": "DRY_RUN" if args.dry_run else "APPLIED",
        "stage": args.stage,
        "from_digest": digest,
        "to_digest": new_digest,
        "new_next_eligible_stage": new_state.get("next_eligible_stage"),
        "new_history_length": len(new_state.get("history", [])),
    }
    if not args.dry_run:
        write_state_atomic(state_path, new_state)
    _print_result(payload, args.output)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orchestration_feature_state.py",
        description="Durable ORCH feature-state validator (ORCH-001).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="Read-only structural + semantic validation.")
    p_validate.add_argument("--output", choices=["human", "json"], default="human")
    p_validate.add_argument("--state", required=True)
    p_validate.add_argument(
        "--plan", default=None, help="implementation-plan.md, for stage-key cross-check"
    )
    p_validate.add_argument(
        "--previous-state", default=None, help="prior state file for append-only proof"
    )
    p_validate.set_defaults(func=_cmd_validate)

    p_status = sub.add_parser("status", help="Read-only recomputed status report.")
    p_status.add_argument("--output", choices=["human", "json"], default="human")
    p_status.add_argument("--state", required=True)
    p_status.set_defaults(func=_cmd_status)

    p_digest = sub.add_parser("digest", help="Print the CAS digest of a state file.")
    p_digest.add_argument("--state", required=True)
    p_digest.set_defaults(func=_cmd_digest)

    p_transition = sub.add_parser("transition", help="Perform exactly one legal stage transition.")
    p_transition.add_argument("--output", choices=["human", "json"], default="human")
    p_transition.add_argument("--state", required=True)
    p_transition.add_argument("--stage", required=True)
    p_transition.add_argument("--to", required=True, choices=sorted(STAGE_STATUS_ENUM))
    p_transition.add_argument("--actor", required=True)
    p_transition.add_argument("--role", required=True, choices=sorted(ROLE_ENUM))
    p_transition.add_argument("--action", default=None)
    p_transition.add_argument("--reason", required=True)
    p_transition.add_argument("--at", default=None)
    p_transition.add_argument(
        "--evidence", action="append", default=None, help="history entry evidence path"
    )
    p_transition.add_argument("--implementer", default=None)
    p_transition.add_argument("--reviewer", default=None)
    p_transition.add_argument("--review-status", default=None, choices=sorted(REVIEW_STATUS_ENUM))
    p_transition.add_argument(
        "--verification-status", default=None, choices=sorted(VERIFICATION_STATUS_ENUM)
    )
    p_transition.add_argument("--implementation-commit", default=None)
    p_transition.add_argument("--clear-implementation-commit", action="store_true")
    p_transition.add_argument("--expected-base-head", default=None)
    p_transition.add_argument("--add-evidence", action="append", default=None)
    p_transition.add_argument("--add-review-evidence", action="append", default=None)
    p_transition.add_argument("--handoff", default=None)
    p_transition.add_argument(
        "--add-blocker", action="append", default=None, help="JSON blocker object"
    )
    p_transition.add_argument(
        "--resolve-blocker", action="append", default=None, help="CODE=RESOLUTION_TEXT"
    )
    p_transition.add_argument(
        "--add-global-blocker", action="append", default=None, help="JSON blocker object"
    )
    p_transition.add_argument(
        "--resolve-global-blocker", action="append", default=None, help="CODE=RESOLUTION_TEXT"
    )
    p_transition.add_argument("--expected-digest", default=None, help="CAS guard: sha256:<hex>")
    p_transition.add_argument("--dry-run", action="store_true")
    p_transition.set_defaults(func=_cmd_transition)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, yaml.YAMLError, json.JSONDecodeError) as exc:
        print(
            json.dumps({"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
