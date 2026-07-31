"""The closed permission and sandbox policies a provider may execute under (AUTO-010).

A leaf module by necessity and by design. By necessity, because both the configuration schema and
the CLI adapters need these values: the adapters already import `config.schema`, so defining the
enums in an adapter would make the schema import its own importer, and defining them anywhere under
`providers/` would drag that package's `__init__` — which imports both adapters — into every
configuration load. By design, because a policy enum should not be able to acquire a dependency:
this module imports nothing from this engine at all, so nothing it names can change meaning based
on how the rest of the engine is wired.

**What is absent here is the security property.** Neither enum lists the unrestricted mode its CLI
offers (`bypassPermissions` for Claude, `danger-full-access` for Codex). Because configuration is
typed to these enums and the adapters build argv from them, there is no configuration file, no
request field, and no call site anywhere in the engine that can name an unrestricted mode. That is
a stronger guarantee than a validator rejecting the value, and a much stronger one than a rule
saying not to use it.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["ClaudePermissionMode", "CodexSandboxMode"]


class ClaudePermissionMode(StrEnum):
    """The permission modes AUTO-010 permits for a non-interactive Claude invocation.

    The installed CLI (2.1.220) accepts six values for `--permission-mode`: `acceptEdits`, `auto`,
    `bypassPermissions`, `manual`, `dontAsk`, and `plan`. This enum admits three, and the omissions
    are the point:

    * `bypassPermissions` disables every permission check. AUTO-010 forbids it outright, and
      leaving it out of the enum is what makes that structural rather than a rule to remember.
    * `manual` and `auto` are interactive or ambiguous. The whole stage rests on the provider never
      reaching a state where it waits for a human, and a mode that means "ask" cannot be part of
      that.

    What remains is an ordered ladder of capability whose bottom rung is the default: `plan` (read
    and reason, change nothing), `dontAsk` (act without prompting), `acceptEdits` (additionally
    accept file edits). An operator who wants a provider that can write must say so explicitly.
    """

    PLAN = "plan"
    DONT_ASK = "dontAsk"
    ACCEPT_EDITS = "acceptEdits"


class CodexSandboxMode(StrEnum):
    """The sandbox policies AUTO-010 permits for a non-interactive Codex invocation.

    `codex exec --help` (codex-cli 0.146.0) documents three possible values for `-s/--sandbox`:
    `read-only`, `workspace-write`, and `danger-full-access`. This enum admits the first two, so an
    unsandboxed Codex run is unreachable from this engine rather than merely discouraged. The same
    reasoning excludes the CLI's `--dangerously-bypass-approvals-and-sandbox` and
    `--dangerously-bypass-hook-trust` flags, which the adapter's fixed argv never contains.

    `read-only` is the default: a provider that has not been explicitly granted write access to a
    workspace does not get it.
    """

    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
