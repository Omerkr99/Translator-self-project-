# Asset Injection Safety

- Canonical extracted inputs are registered under `asset_workspace/source` and
  cannot be overwritten with different bytes.
- Work products are written under `asset_workspace/output` with SHA-256 journal entries.
- `UNKNOWN` policies block encoding and injection.
- Oversized streams are never truncated.
- `EXACT_CONSUMED_SIZE` streams are expanded only with equivalent literal-token
  transformations; decoded equality and exact length are asserted.
- Container rebuild replaces only the descriptor's fixed slot.
- Temporary testing uses the PCSX-Redux web API.
- Physical BIN/CUE modification is not implemented.
- Restore clears the in-memory edit; PCSX temporary patches have a separate
  explicit clear operation.
