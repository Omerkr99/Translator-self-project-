# Asset Descriptor Specification

`AssetDescriptor` is JSON-serializable and records identity, disc source,
container block/offset/size, decoded image metadata, encoding policy, semantic
confidence, screen mapping, runtime state, verification facts and capabilities.

Supported size policies:

- `EXACT_CONSUMED_SIZE`: final encoded stream must consume exactly the original size.
- `MAX_ALLOCATED_SIZE`: output may be smaller, never larger.
- `RELOCATABLE`: reserved for proven containers with offset rebuilding.
- `UNKNOWN`: all writing is blocked.

Unknown JSON fields are ignored when loading for forward compatibility. Invalid
dimensions, offsets and unsafe policy/capability combinations are rejected.

The initial registry assigns known semantics only to Start, Prepare and the five
classroom strips. Other blocks use stable unknown IDs; meanings are not invented.
