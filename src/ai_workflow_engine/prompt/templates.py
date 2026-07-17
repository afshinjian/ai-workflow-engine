"""Seven-entry versioned built-in prompt template registry.

This module is specification data, constructed once at import time from the common
literal and per-stage fragments below. It performs no runtime `{{...}}` substitution;
that belongs to :mod:`ai_workflow_engine.prompt.renderer`.
"""

import hashlib
import re

from ai_workflow_engine.prompt.models import PromptTemplate, WorkflowStage

_COMMON_LITERAL = (
    "# Governed Workflow Prompt\n"
    "\n"
    "## Identity\n"
    "- Prompt ID: {{PROMPT_ID_SCALAR}}\n"
    "- Stage: {{STAGE_SCALAR}}\n"
    "- Task: {{TASK_ID_SCALAR}}\n"
    "- Repository: {{REPOSITORY_PATH_SCALAR}}\n"
    "- Default branch: {{DEFAULT_BRANCH_SCALAR}}\n"
    "- Conda environment: {{CONDA_ENVIRONMENT_SCALAR}}\n"
    "\n"
    "## Role\n"
    "@@ROLE@@\n"
    "\n"
    "## Scope and allowed operations\n"
    "@@SCOPE@@\n"
    "\n"
    "## Allowed paths\n"
    "{{ALLOWED_PATHS_LIST}}\n"
    "\n"
    "## Prohibited operations\n"
    "@@PROHIBITED@@\n"
    "\n"
    "## Repository inspection evidence\n"
    "\n"
    "### Git status\n"
    "{{GIT_STATUS_JSON}}\n"
    "\n"
    "### Task snapshot\n"
    "{{TASK_SNAPSHOT_JSON}}\n"
    "\n"
    "### Protected-path violations\n"
    "{{PROTECTED_PATH_VIOLATIONS_LIST}}\n"
    "\n"
    "### Validation checks\n"
    "{{CHECKS_JSON}}\n"
    "\n"
    "## Remediation findings\n"
    "{{REMEDIATION_FINDINGS_LIST}}\n"
    "\n"
    "## Verification commands\n"
    "@@VERIFICATION@@\n"
    "\n"
    "## Stop condition\n"
    "@@STOP@@\n"
    "\n"
    "## Verdict instruction\n"
    "@@VERDICT@@\n"
)

_VERIFICATION_STANDARD = (
    "conda run -n {{CONDA_ENVIRONMENT_SHELL}} git status --short --branch\n"
    "conda run -n {{CONDA_ENVIRONMENT_SHELL}} git diff --check\n"
    "conda run -n {{CONDA_ENVIRONMENT_SHELL}} pytest -p no:cacheprovider"
)

_REVIEW_PROHIBITED_NO_PROMOTION = (
    "- Do not modify any file.\n"
    "- Do not stage, commit, push, reset, clean, rebase, create or alter a worktree, or run "
    "any other writable Git operation.\n"
    "- Do not execute an agent, add workflow state, record a verdict, perform a transition, "
    "or choose a next stage."
)

_REVIEW_VERDICT = "Return exactly one final verdict token: APPROVED or REJECTED."
_NO_VERDICT = "No APPROVED or REJECTED verdict is requested for this stage."

_FRAGMENTS: dict[WorkflowStage, dict[str, str]] = {
    "plan-review": {
        "ROLE": "Act as the read-only planning reviewer for the requested task.",
        "SCOPE": (
            "- Inspect the plan, repository, governance documents, configuration, diffs, "
            "and supplied evidence.\n"
            "- Run only read-only inspection commands and the verification commands below.\n"
            "- Evaluate whether the plan is complete, internally consistent, deterministic, "
            "testable, and within the stated milestone boundary."
        ),
        "PROHIBITED": _REVIEW_PROHIBITED_NO_PROMOTION,
        "VERIFICATION": _VERIFICATION_STANDARD,
        "STOP": (
            "Stop after reporting every blocking and non-blocking plan finding with file and "
            "line references where available; make no repository change."
        ),
        "VERDICT": _REVIEW_VERDICT,
    },
    "implementation": {
        "ROLE": "Act as the implementation agent for the requested task.",
        "SCOPE": (
            "- Implement only the requested task and only within the rendered allowed-path "
            "list.\n"
            "- Read any repository file needed for context and run the verification commands "
            "below.\n"
            "- Keep all edits deterministic, minimal, and within the current milestone "
            "boundary."
        ),
        "PROHIBITED": (
            "- Do not modify a path absent from the rendered allowed-path list.\n"
            "- Do not stage, commit, push, reset, clean, rebase, create or alter a worktree, "
            "or run any other writable Git operation.\n"
            "- Do not execute another agent, add workflow state, record a verdict, perform a "
            "transition, or choose a next stage."
        ),
        "VERIFICATION": _VERIFICATION_STANDARD,
        "STOP": (
            "Stop after the implementation and verification are complete, or immediately on a "
            "blocker; report changed paths, verification results, and blockers without "
            "staging, committing, or pushing."
        ),
        "VERDICT": _NO_VERDICT,
    },
    "implementation-review": {
        "ROLE": "Act as the read-only implementation reviewer for the requested task.",
        "SCOPE": (
            "- Inspect the implementation, repository, diffs, tests, governance constraints, "
            "and supplied evidence.\n"
            "- Run only read-only inspection commands and the verification commands below.\n"
            "- Evaluate correctness, regressions, test coverage, determinism, and compliance "
            "with the requested scope and allowed paths."
        ),
        "PROHIBITED": _REVIEW_PROHIBITED_NO_PROMOTION,
        "VERIFICATION": _VERIFICATION_STANDARD,
        "STOP": (
            "Stop after reporting every blocking and non-blocking implementation finding with "
            "file and line references where available; make no repository change."
        ),
        "VERDICT": _REVIEW_VERDICT,
    },
    "remediation": {
        "ROLE": "Act as the remediation agent for the requested task.",
        "SCOPE": (
            "- Address every rendered remediation finding and no unlisted objective.\n"
            "- Modify only paths in the rendered allowed-path list; read other files only for "
            "context.\n"
            "- Run the verification commands below and preserve unrelated user changes."
        ),
        "PROHIBITED": (
            "- Do not modify a path absent from the rendered allowed-path list or expand the "
            "remediation beyond the rendered findings.\n"
            "- Do not stage, commit, push, reset, clean, rebase, create or alter a worktree, "
            "or run any other writable Git operation.\n"
            "- Do not execute another agent, add workflow state, record a verdict, perform a "
            "transition, or choose a next stage."
        ),
        "VERIFICATION": _VERIFICATION_STANDARD,
        "STOP": (
            "Stop after every rendered finding is resolved and verified, or immediately on a "
            "blocker; report each finding's disposition, changed paths, verification results, "
            "and blockers without staging, committing, or pushing."
        ),
        "VERDICT": _NO_VERDICT,
    },
    "governance-closeout": {
        "ROLE": "Act as the read-only governance closeout assessor for the requested task.",
        "SCOPE": (
            "- Inspect repository, task, governance, handover, configuration, diff, and "
            "supplied check evidence.\n"
            "- Run only read-only inspection commands and the verification commands below.\n"
            "- Determine and report the exact closeout actions still required; this stage does "
            "not perform them."
        ),
        "PROHIBITED": (
            "- Do not modify any file.\n"
            "- Do not stage, commit, push, reset, clean, rebase, create or alter a worktree, "
            "or run any other writable Git operation.\n"
            "- Do not execute an agent, add workflow state, record a verdict, perform a "
            "transition, promote work, or choose a next stage."
        ),
        "VERIFICATION": _VERIFICATION_STANDARD,
        "STOP": (
            "Stop after reporting closeout readiness, every remaining governance or handover "
            "gap, and the evidence for each conclusion; make no repository change and perform "
            "no promotion."
        ),
        "VERDICT": _NO_VERDICT,
    },
    "governance-review": {
        "ROLE": "Act as the read-only governance reviewer for the requested task.",
        "SCOPE": (
            "- Inspect repository, task, governance, handover, configuration, diff, and "
            "supplied check evidence.\n"
            "- Run only read-only inspection commands and the verification commands below.\n"
            "- Evaluate governance consistency, handover integrity, protected-path compliance, "
            "and closeout completeness."
        ),
        "PROHIBITED": (
            "- Do not modify any file.\n"
            "- Do not stage, commit, push, reset, clean, rebase, create or alter a worktree, "
            "or run any other writable Git operation.\n"
            "- Do not execute an agent, add workflow state, record a verdict, perform a "
            "transition, promote work, or choose a next stage."
        ),
        "VERIFICATION": _VERIFICATION_STANDARD,
        "STOP": (
            "Stop after reporting every blocking and non-blocking governance finding with file "
            "and line references where available; make no repository change and perform no "
            "promotion."
        ),
        "VERDICT": _REVIEW_VERDICT,
    },
    "push": {
        "ROLE": "Act as the constrained publisher for the requested task.",
        "SCOPE": (
            "- The only permitted state-changing operation is one `git push` after every "
            "verification below passes.\n"
            "- The authorized branch is {{GIT_BRANCH_SCALAR}} and the authorized HEAD is "
            "{{GIT_HEAD_SCALAR}}.\n"
            "- The recorded upstream is {{GIT_UPSTREAM_SCALAR}}, recorded ahead count is "
            "{{GIT_AHEAD_SCALAR}}, and recorded behind count is {{GIT_BEHIND_SCALAR}}.\n"
            "- Require the live branch and HEAD to equal the authorized values, the live "
            "upstream to equal the non-null recorded upstream, and all modified, staged, and "
            "untracked path lists in both rendered and live status to be empty.\n"
            "- For the commit-chain check, run the exact `git rev-list` command below, parse "
            "its sole output as two base-10 nonnegative integers separated by one tab and one "
            "terminal newline, and interpret them as behind then ahead. Require them to equal "
            "the recorded behind and ahead counts and require behind to equal zero.\n"
            "- Only after all requirements pass, run the exact `git push` command below once."
        ),
        "PROHIBITED": (
            "- Do not create, edit, delete, rename, chmod, format, or otherwise change any "
            "file.\n"
            "- Do not stage, commit, reset, clean, rebase, merge, cherry-pick, amend, create "
            "or alter a worktree, or run any writable Git operation other than the single "
            "authorized `git push`.\n"
            "- Do not execute another agent, add workflow state, record a verdict, perform a "
            "transition, promote work, or choose a next stage."
        ),
        "VERIFICATION": (
            "conda run -n {{CONDA_ENVIRONMENT_SHELL}} git status --short --branch\n"
            "conda run -n {{CONDA_ENVIRONMENT_SHELL}} git branch --show-current\n"
            "conda run -n {{CONDA_ENVIRONMENT_SHELL}} git rev-parse HEAD\n"
            "conda run -n {{CONDA_ENVIRONMENT_SHELL}} git rev-parse --abbrev-ref "
            "--symbolic-full-name @{upstream}\n"
            "conda run -n {{CONDA_ENVIRONMENT_SHELL}} git rev-list --left-right --count "
            "@{upstream}...HEAD\n"
            "conda run -n {{CONDA_ENVIRONMENT_SHELL}} git diff --check\n"
            "conda run -n {{CONDA_ENVIRONMENT_SHELL}} git push"
        ),
        "STOP": (
            "Stop without pushing on any mismatch, missing upstream, nonzero behind count, "
            "dirty-file evidence, verification failure, or file change. Otherwise stop "
            "immediately after the single push and report its result; do not change any file."
        ),
        "VERDICT": _NO_VERDICT,
    },
}

MARKER_ORDER: tuple[str, ...] = ("ROLE", "SCOPE", "PROHIBITED", "VERIFICATION", "STOP", "VERDICT")
_MARKER_ORDER = MARKER_ORDER

# A minimal, self-contained placeholder-occurrence counter for constructed (already
# `@@...@@`-resolved) content. This intentionally duplicates only the tiny `{{NAME}}`
# pattern from renderer.py's tokenizer, rather than importing it, so that templates.py
# never depends on renderer.py: renderer.py depends on templates.py's expected-count
# table, and a reverse import here would create a cycle.
_PLACEHOLDER_RE = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")


def _expected_placeholder_counts(content: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for match in _PLACEHOLDER_RE.finditer(content):
        name = match.group(1)
        counts[name] = counts.get(name, 0) + 1
    return counts


def _construct_content(stage: WorkflowStage) -> str:
    fragments = _FRAGMENTS[stage]
    content = _COMMON_LITERAL
    for name in _MARKER_ORDER:
        marker = f"@@{name}@@"
        occurrences = content.count(marker)
        if occurrences != 1:
            raise ValueError(
                f"{stage}: construction marker {marker} must occur exactly once before "
                f"replacement, found {occurrences}"
            )
        content = content.replace(marker, fragments[name])
    for name in _MARKER_ORDER:
        marker = f"@@{name}@@"
        if marker in content:
            raise ValueError(f"{stage}: construction marker {marker} remains after replacement")
    return content


def _build_template(stage: WorkflowStage) -> PromptTemplate:
    content = _construct_content(stage)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return PromptTemplate(stage=stage, version="1.0.0", content=content, sha256=digest)


TEMPLATE_REGISTRY: dict[WorkflowStage, PromptTemplate] = {
    stage: _build_template(stage) for stage in _FRAGMENTS
}

# The exact expected runtime-placeholder occurrence count for each stage, computed once
# from that stage's own registry content: the common literal plus its six fragments. A
# name absent from a stage's table has an expected count of zero (it must not appear).
EXPECTED_PLACEHOLDER_COUNTS: dict[WorkflowStage, dict[str, int]] = {
    stage: _expected_placeholder_counts(template.content)
    for stage, template in TEMPLATE_REGISTRY.items()
}


def get_template(stage: WorkflowStage) -> PromptTemplate:
    try:
        return TEMPLATE_REGISTRY[stage]
    except KeyError as exc:
        raise ValueError(f"No registered prompt template for stage {stage!r}") from exc


def get_expected_placeholder_counts(stage: WorkflowStage) -> dict[str, int]:
    try:
        return dict(EXPECTED_PLACEHOLDER_COUNTS[stage])
    except KeyError as exc:
        raise ValueError(f"No expected placeholder counts for stage {stage!r}") from exc


def get_fragments(stage: WorkflowStage) -> dict[str, str]:
    try:
        return dict(_FRAGMENTS[stage])
    except KeyError as exc:
        raise ValueError(f"No registered prompt fragments for stage {stage!r}") from exc
