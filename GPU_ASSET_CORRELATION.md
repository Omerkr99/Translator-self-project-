# GPU Asset Correlation

GPU correlation converts TPAGE plus UV bounds into a VRAM word rectangle and intersects it with exact runtime residency matches. A match is `LIVE_EXACT_VRAM_GPU` evidence and supplies primitive address and actual screen bounds. This is the only path that promotes an asset from resident to `DRAWN_THIS_FRAME`.

The PCSX-Redux Lua probe observes GPU DMA channel 2 but records only the CPU writer PC and `$a0` OT root. Linked-list traversal happens externally against a RAM dump, outside the unsafe callback. The parser supports flat and Gouraud textured triangles/quads. Sprites, texture-window effects, and non-DMA GP0 submissions remain to be added as encountered.

## Live MENUDAT block 9 proof

The safe two-stage capture found the DMA starter at `0x80049670`; static live-RAM disassembly proved `$a0` is written to GPU DMA MADR at `0x80049650`. Logged OT roots alternate with the double buffer. External RAM parsing found two `POLY_GT4` instances at `0x80075D6C` and `0x80077020`. Both use TPAGE 10 and UV `(0,96)-(64,128)`, exactly overlapping the independently matched block-9 texture at VRAM word `(640,96)`. Their screen union is `(40,24,64,32)`. This is `LIVE_EXACT_VRAM_GPU` evidence and establishes `DRAWN_THIS_FRAME` without screenshot mapping.

Both GPU I/O breakpoint variants proved unstable over time in PCSX-Redux: the first read I/O and crashed immediately; the second only read CPU registers but later closed the emulator. Both are permanently removed. The captured `$a0` roots remain valid evidence, while continuing detection must use external RAM/VRAM snapshots with no persistent GPU-I/O breakpoint.
