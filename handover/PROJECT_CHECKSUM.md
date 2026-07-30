# Project Checksum Manifest

Verified by `workflowctl check-handover --config self-governance.yaml`. Each row's digest is the
full SHA-256 of the referenced file's exact working-tree bytes at the time this manifest was
generated. A mismatch means the file changed after this manifest was written — regenerate the
manifest (recompute size + `sha256sum`) rather than treating a legitimate edit as tampering.

| Relative path | Size (bytes) | Last modified | SHA-256 (prefix) |
|---|---|---|---|
| handover/PROJECT_HANDOVER.md | 36018 | 2026-07-30 | 590d37acbbd9214e1df5965b61dc824f55645a822637f2de20ea1baa5a1fc0fd |
