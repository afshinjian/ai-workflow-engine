"""The Codex CLI adapter: review and closure, fixed read-only.

Contract: `docs/workflow-automation/stage-prompts/AUTO-016.md` (Revision 4) section 17 (the
provider boundary, the fixed read-only review invocation and session isolation), section 17a (no
byte reaches a durable artifact unredacted), section 22 invariants 17 and 20, and section 8, which
fixes this file's existence and location.

Codex drives the two roles that only *read*: `REVIEW` and `CLOSURE`. Implementation and correction
belong to Claude, and this adapter refuses them.

`danger-full-access` is unrepresentable, and read-only is not merely the default
-------------------------------------------------------------------------------
The sandbox mode is a `CodexSandboxMode`, a closed enum with exactly `read-only` and
`workspace-write` (invariant 17). There is no `danger-full-access` member, so nothing can express
one. Section 17 goes further for this adapter -- "Codex's review invocation is fixed read-only" --
so a configuration that selected `workspace-write` is **refused at construction** rather than
silently downgraded: a silent override would leave the configuration file saying one thing while
the runner did another, and the operator would never learn which had won.

Session isolation, structurally
-------------------------------
Codex never receives Claude's transcript or reasoning (section 17, `SECURITY_MODEL.md` section 3).
This adapter takes a single already-rendered prompt string and has no parameter, field or method
through which a transcript could arrive; `prompts.render_review_prompt` is the only thing that
builds that string, and its own signature admits only the diff, the changed-path list and the
deterministic verification results. The two providers also share no process state: each invocation
is its own process group with its own allowlisted environment.

The last-message file, and why it is scratch
--------------------------------------------
`codex exec` writes its final message to the file named by `--output-last-message`, which means a
*child* writes those bytes. Section 17a requires every byte of a durable artifact to pass through
the runner's single redaction boundary, and a child's write cannot. So the file is created in a
private scratch directory that is neither the repository the runner is guarding nor the state root
where everything must already be redacted; :class:`~...providers.base.ProviderInvoker` reads it,
writes it through the boundary as a durable transcript, and then removes the scratch original.

The flags are the ones documented for the installed CLI: `exec` runs non-interactively and reads
the prompt from stdin, `--json` prints events as JSONL, `--sandbox` selects the sandbox, the single
`-c approval_policy="never"` pair is defence in depth against a future default that reintroduces
prompting, and `--output-last-message` names the answer file. The prompt is not among them.
"""

import tempfile
from pathlib import Path
from typing import ClassVar, Final

from ai_workflow_engine.milestone_runner.config import CodexProviderSettings, CodexSandboxMode
from ai_workflow_engine.milestone_runner.models import ProviderRole
from ai_workflow_engine.milestone_runner.providers.base import (
    ArgvSlot,
    ProviderAdapter,
    ProviderArgvRefused,
    ProviderRequest,
    render_argv,
    transcript_label_for,
)

#: The fixed argument vector for every Codex invocation, with three whole-element slots. Owned by
#: this module; `render_argv` substitutes a slot for its value and copies every other element
#: through, so no configured value can add a flag this template does not declare.
CODEX_ARGV_TEMPLATE: Final[tuple[str, ...]] = (
    ArgvSlot.EXECUTABLE.value,
    "exec",
    "--json",
    "--sandbox",
    ArgvSlot.SANDBOX_MODE.value,
    "-c",
    'approval_policy="never"',
    "--output-last-message",
    ArgvSlot.LAST_MESSAGE_PATH.value,
)

#: The name Codex is told to write its final message under, inside a per-invocation scratch
#: directory. Two invocations therefore never read each other's answer.
CODEX_LAST_MESSAGE_FILENAME: Final = "codex-last-message.md"

#: The scratch directory's prefix, so an operator finding one knows what made it.
CODEX_SCRATCH_PREFIX: Final = "milestone-runner-codex-"

#: The single sandbox mode this adapter admits (section 17: the review invocation is fixed
#: read-only). Named rather than inlined so the refusal below and the rendered argv cannot drift.
CODEX_FIXED_SANDBOX_MODE: Final = CodexSandboxMode.READ_ONLY


class CodexCLIAdapter(ProviderAdapter):
    """Codex, bound to review and closure, fixed read-only, under one fixed vector.

    Like the Claude adapter it holds validated configuration and its own template, spawns nothing
    and records nothing. The one filesystem act it performs is creating the private scratch
    directory the last-message file needs, which has to exist before the vector naming it can be
    rendered.
    """

    name: ClassVar[str] = "codex"
    roles: ClassVar[frozenset[ProviderRole]] = frozenset(
        {ProviderRole.REVIEW, ProviderRole.CLOSURE}
    )

    def __init__(self, *, settings: CodexProviderSettings) -> None:
        if settings.arguments:
            raise ProviderArgvRefused(
                "Codex's argument vector is CODEX_ARGV_TEMPLATE and nothing else; "
                f"providers.codex.arguments must be empty, not {settings.arguments!r}"
            )
        if settings.sandbox_mode is not CODEX_FIXED_SANDBOX_MODE:
            raise ProviderArgvRefused(
                f"Codex's review and closure invocations are fixed {CODEX_FIXED_SANDBOX_MODE}; "
                f"providers.codex.sandbox_mode is {settings.sandbox_mode}, which this adapter "
                "refuses rather than silently downgrades"
            )
        self._settings = settings

    @property
    def sandbox_mode(self) -> CodexSandboxMode:
        """Always `read-only`: the constructor refuses anything else (section 17)."""
        return CODEX_FIXED_SANDBOX_MODE

    @property
    def timeout_seconds(self) -> int:
        """The configured per-provider bound. There is no default anywhere behind this value."""
        return self._settings.timeout_seconds

    def build_request(
        self, *, role: ProviderRole, prompt: str, milestone_id: str | None = None
    ) -> ProviderRequest:
        """Render the fixed vector for `role`, with a fresh scratch path for the answer file."""
        self._require_role(role)
        last_message_path = self._new_last_message_path()
        argv = render_argv(
            CODEX_ARGV_TEMPLATE,
            {
                ArgvSlot.EXECUTABLE: self._settings.executable,
                ArgvSlot.SANDBOX_MODE: CODEX_FIXED_SANDBOX_MODE.value,
                ArgvSlot.LAST_MESSAGE_PATH: str(last_message_path),
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
            last_message_path=str(last_message_path),
        )

    def _new_last_message_path(self) -> Path:
        """Create this invocation's private scratch directory and return the file path in it.

        `mkdtemp` creates the directory with mode `0o700` and a name no other process guessed, so
        the answer file is readable only by this user and is not shared with any other invocation.
        The directory is deliberately outside both the repository and the state root, for the
        reason the module docstring gives.
        """
        directory = Path(tempfile.mkdtemp(prefix=CODEX_SCRATCH_PREFIX))
        return directory / CODEX_LAST_MESSAGE_FILENAME
