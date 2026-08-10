"""TR-08/SC-06: DASH-007's new modules never construct a repository write path — mirrors
`test_api_git.py::test_no_repository_write_in_git_module`'s source-scan discipline."""

from __future__ import annotations

import ast
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_MODULES = (
    "services/stages.py",
    "services/prompts.py",
    "services/governance.py",
    "api/stages.py",
    "api/prompts.py",
    "api/governance.py",
    "prompt_templates/__init__.py",
    "prompt_templates/schema.py",
    "prompt_templates/placeholders.py",
)
_WRITE_METHODS = {"write_text", "write_bytes", "unlink"}


def test_no_repository_write_method_called() -> None:
    for relative in _MODULES:
        source = (_PACKAGE_ROOT / relative).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in _WRITE_METHODS:
                raise AssertionError(f"{relative} calls a write method: {node.attr}")


def _is_open_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open"


def test_no_open_call_in_write_mode() -> None:
    for relative in _MODULES:
        source = (_PACKAGE_ROOT / relative).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and _is_open_call(node)):
                continue
            mode_args = node.args[1:] + [kw.value for kw in node.keywords if kw.arg == "mode"]
            for arg in mode_args:
                is_write_mode = (
                    isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and "w" in arg.value
                )
                if is_write_mode:
                    message = f"{relative} opens a file in a write mode: {ast.dump(node)}"
                    raise AssertionError(message)
