# Project Checksum Manifest

Verified by `workflowctl check-handover --config self-governance.yaml`. Each row's digest is the
full SHA-256 of the referenced file's exact working-tree bytes at the time this manifest was
generated. A mismatch means the file changed after this manifest was written — regenerate the
manifest (recompute size + `sha256sum`) rather than treating a legitimate edit as tampering.

| Relative path | Size (bytes) | Last modified | SHA-256 (prefix) |
|---|---|---|---|
| handover/PROJECT_HANDOVER.md | 63902 | 2026-08-02 | 239a7175e40e657bc7d94cb8c32fa6fff34b777d569b642e6a2d4cd2235e2bc7 |
