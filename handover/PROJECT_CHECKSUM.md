# Project Checksum Manifest

Verified by `workflowctl check-handover --config self-governance.yaml`. Each row's digest is the
full SHA-256 of the referenced file's exact working-tree bytes at the time this manifest was
generated. A mismatch means the file changed after this manifest was written — regenerate the
manifest (recompute size + `sha256sum`) rather than treating a legitimate edit as tampering.

| Relative path | Size (bytes) | Last modified | SHA-256 (prefix) |
|---|---|---|---|
| handover/PROJECT_HANDOVER.md | 4367 | 2026-07-27 | 29cd87929b7f9a06e72d242b62885ad25f6bbd543bc4957a99e5eead9e27c587 |
