# Image Format Adapters

## Implemented

| Format | Decode | PNG | Indexed edit | Palette | Encode |
|---|---|---|---|---|---|
| TIM 4bpp indexed | YES | YES | YES | 16 BGR555/STP | YES |
| TIM 8bpp indexed | YES | YES | YES | 256 BGR555/STP | YES |
| TIM 16bpp direct | YES | YES | NO | N/A | YES |

TIM parsing is separate from the game's RLE/LZ/delta stream compression.
Transparency is derived from raw CLUT value `0x0000`, not a hard-coded palette
index. Palette-preserving PNG import rejects unrepresentable colors instead of
silently expanding or optimizing the palette.

## Unsupported

SDB2.0, SDB2.2, MS4, GP4 and TIM 24bpp are explicitly unsupported. Recognition
may be added later without granting decode/edit/injection capabilities.

**2026-08-10 update**: SDB2.0 is no longer "never located." A real sample
was found and its magic string confirmed directly: `DAT/HITO/AFRM.CDB`,
decompressed with the existing `gcrts.cdb_codec` (the same codec confirmed
via disassembly for `KFONT.CDB`/`K0LINK.CDB`) after skipping its
2048-byte directory-table prefix, produces a stream beginning with the
literal ASCII bytes `"SDB2.0 "`. See `BACKLOG_INVESTIGATION_RESULTS.md`
for the full finding, including a plausible (not yet confirmed) frame/
offset table immediately following the magic. Still no decode/PNG/edit
capability — this is location + identification only, not an adapter.
`DAT/HITO/SIKFORM.CDB` shows a structurally similar directory-table
pattern and is a candidate for one of the remaining formats (SDB2.2/MS4/
GP4), not yet identified specifically.
