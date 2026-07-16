# Milestones

1. **Deterministic inspection and validation (implemented in 0.1.0).** Configuration, bounded
   paths, read-only Git inspection, governance/task checks, source-aware handover verification,
   protected paths, structured results, CLI, and CI-friendly JSON.
2. **Prompt generation.** Versioned prompt templates derived from verified state, with explicit
   scopes and human approval artifacts.
3. **Non-interactive agent execution.** Codex read-only review and scoped OpenCode writes, strict
   report schemas, isolation, timeouts, and independent claim verification.
4. **Controlled commit and push.** Approval-bound staging allowlists, commit verification,
   protected-path enforcement, remote/upstream checks, and explicit push gates.

Later milestones must preserve the Milestone 1 rule that agent output is evidence to verify, not
an authority. They are documented extension points only and are not implemented in 0.1.0.
