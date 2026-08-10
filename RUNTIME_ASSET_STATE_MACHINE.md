# Runtime Asset State Machine

Runtime evidence, not screenshot rectangles, determines activity. A canonical asset may have multiple runtime instances. Each instance records frame IDs, RAM pointers, VRAM generations, draw evidence, confidence, and an append-only provenance chain.

The implemented core transitions are `LOADED -> DECOMPRESSED -> UPLOADED_TO_VRAM -> DRAWN_THIS_FRAME`. At the next frame, an unreferenced resident asset returns to `UPLOADED_TO_VRAM`; a VRAM overwrite removes that residency and marks it `STALE_IN_VRAM`. Unknown decode events are retained.

`DRAWN_THIS_FRAME` can only be produced by a GPU draw observation. RAM presence, VRAM residency, and a manual rectangle are insufficient.
