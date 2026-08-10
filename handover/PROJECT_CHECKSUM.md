# Project Checksum Manifest

Verified by `workflowctl check-handover --config self-governance.yaml`. Each row's digest is the
full SHA-256 of the referenced file's exact working-tree bytes at the time this manifest was
generated. A mismatch means the file changed after this manifest was written — regenerate the
manifest (recompute size + `sha256sum`) rather than treating a legitimate edit as tampering.

| Relative path | Size (bytes) | Last modified | SHA-256 (prefix) |
|---|---|---|---|
| handover/PROJECT_HANDOVER.md | 67856 | 2026-08-10 | 1ede94a5e11051ab98d70d67662b3e46a647f07b28acdcc43b45a7b41af6d0f4 |
