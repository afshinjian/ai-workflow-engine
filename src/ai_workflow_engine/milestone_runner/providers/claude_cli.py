"""The Claude CLI adapter: implementation and correction, and nothing else.

Contract: `docs/workflow-automation/stage-prompts/AUTO-016.md` (Revision 4) section 17 (the
provider boundary and DEC-016-002's ruling), section 22 invariants 17 and 20, and section 8, which
fixes this file's existence and location.

Claude drives the two roles that *write*: `IMPLEMENTATION` and `CORRECTION`. Review and closure
belong to Codex, and this adapter refuses them, so the role binding is a property of which adapter
can build which request rather than a configuration key a call site could point the wrong way.

`bypassPermissions` is unrepresentable, not rejected
----------------------------------------------------
The permission mode is a `ClaudePermissionMode`, a closed enum whose three members are `plan`,
`default` and `acceptEdits` (invariant 17). There is no `bypassPermissions` member, so no
configuration, request or call site can express one -- the type system forbids it, not a validator
this adapter runs. The value reaches argv only through :data:`CLAUDE_ARGV_TEMPLATE`'s
`{permission_mode}` slot, which :func:`~...providers.base.render_argv` substitutes whole.

The vector is this module's, not the configuration's
-----------------------------------------------------
Section 17 admits a closed, typed template -- an executable, a fixed argument vector and a small
set of named slots -- and never a caller-supplied command string. So the shape below is a constant
owned by the adapter, and configuration supplies only the executable name, the permission mode and
the required timeout. `ProviderSettings.arguments` is a general fixed-argument vector, which is
broader than that: a configured `arguments` entry could carry a flag this adapter never reviewed.
The narrower reading is implemented -- a non-empty `arguments` is refused at construction -- so the
vector Claude receives is always exactly the one written here.

The flags are the ones documented for the installed CLI: `--print` runs non-interactively and
prints the response, and `--permission-mode` selects the mode. The prompt is **not** among them:
it travels on stdin (section 17), so it never appears in a process listing.
"""

from typing import ClassVar, Final

from ai_workflow_engine.milestone_runner.config import ClaudePermissionMode, ClaudeProviderSettings
from ai_workflow_engine.milestone_runner.models import ProviderRole
from ai_workflow_engine.milestone_runner.providers.base import (
    ArgvSlot,
    ProviderAdapter,
    ProviderArgvRefused,
    ProviderRequest,
    render_argv,
    transcript_label_for,
)

#: The fixed argument vector for every Claude invocation, with two whole-element slots. Owned by
#: this module and never assembled from a string: `render_argv` substitutes a slot for its value
#: and copies every other element through unchanged, so nothing can extend the vector.
CLAUDE_ARGV_TEMPLATE: Final[tuple[str, ...]] = (
    ArgvSlot.EXECUTABLE.value,
    "--print",
    "--permission-mode",
    ArgvSlot.PERMISSION_MODE.value,
)


class ClaudeCLIAdapter(ProviderAdapter):
    """Claude, bound to implementation and correction, under one fixed vector.

    The adapter holds validated configuration and its own template. It reads no file, spawns no
    process and writes no record: :class:`~...providers.base.ProviderInvoker` owns all three, so
    the subprocess discipline exists once rather than once per provider.
    """

    name: ClassVar[str] = "claude"
    roles: ClassVar[frozenset[ProviderRole]] = frozenset(
        {ProviderRole.IMPLEMENTATION, ProviderRole.CORRECTION}
    )

    def __init__(self, *, settings: ClaudeProviderSettings) -> None:
        if settings.arguments:
            raise ProviderArgvRefused(
                "Claude's argument vector is CLAUDE_ARGV_TEMPLATE and nothing else; "
                f"providers.claude.arguments must be empty, not {settings.arguments!r}"
            )
        self._settings = settings

    @property
    def permission_mode(self) -> ClaudePermissionMode:
        """The configured mode. Its type is what makes `bypassPermissions` unrepresentable."""
        return self._settings.permission_mode

    @property
    def timeout_seconds(self) -> int:
        """The configured per-provider bound. There is no default anywhere behind this value."""
        return self._settings.timeout_seconds

    def build_request(
        self, *, role: ProviderRole, prompt: str, milestone_id: str | None = None
    ) -> ProviderRequest:
        """Render the fixed vector for `role` and pair it with a stdin-delivered prompt."""
        self._require_role(role)
        argv = render_argv(
            CLAUDE_ARGV_TEMPLATE,
            {
                ArgvSlot.EXECUTABLE: self._settings.executable,
                ArgvSlot.PERMISSION_MODE: self._settings.permission_mode.value,
            },
        )
        return ProviderRequest(
            provider=self.name,
            role=role,
            argv=argv,
            prompt=prompt,
            timeout_seconds=self._settings.timeout_seconds,
            transcript_label=transcript_label_for(self.name, role),
            milestone_id=milestone_id,
        )
