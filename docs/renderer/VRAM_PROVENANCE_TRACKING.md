# VRAM Provenance Tracking

Exact packed TIM rows are matched against the live 1024×512 VRAM dump. This is binary texture evidence, not screenshot similarity. Matches report word coordinates, dimensions and pixel mode.

Residency alone never means drawing. Ordering Table primitives supply TPAGE and UV; their derived texture rectangles are intersected with residency matches. Overlapping VRAM generations invalidate earlier ownership. The tracker distinguishes `UPLOADED_TO_VRAM`, `DRAWN_THIS_FRAME`, and `STALE_IN_VRAM`.

MENUDAT block 9 was live-matched at word x=640, y=96. On Photos it was referenced by two double-buffered GT4 packets; after returning to Main Menu it remained resident but had no current primitive, proving stale removal.
