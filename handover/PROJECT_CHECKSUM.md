# Project Checksum Manifest

Verified by `workflowctl check-handover --config self-governance.yaml`. Each row's digest is the
full SHA-256 of the referenced file's exact working-tree bytes at the time this manifest was
generated. A mismatch means the file changed after this manifest was written — regenerate the
manifest (recompute size + `sha256sum`) rather than treating a legitimate edit as tampering.

| Relative path | Size (bytes) | Last modified | SHA-256 (prefix) |
|---|---|---|---|
| handover/PROJECT_HANDOVER.md | 69252 | 2026-08-11 | 581f38deea9be7169ee28ad31072b0e0430a1c2bc7e6f8d119439d689e4ff10a |
