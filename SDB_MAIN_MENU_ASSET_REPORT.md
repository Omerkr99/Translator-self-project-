# Main-menu classroom photo: end-to-end asset result

> **Current-document note:** This focused experiment log is retained as the
> chronological proof record. The broader, current status and artifact index are
> maintained in `IMAGE_ASSET_STATUS.md` and `sdb_main_menu_asset/README.md`.

## Result

The visible classroom background was extracted, reconstructed offline, edited,
re-encoded, and injected through PCSX-Redux. The white 20x20 square remained
part of the image after a hard reset and across frames. This proves a reversible
asset-level modification path.

The selected main-menu asset is **not an SDB2/MS asset and is not a CDB entry**.
It is stored in `DAT/SINKOU/PROGDAT.BIN` as concatenated game-codec streams
whose decoded payloads are standard PlayStation TIM images.

## Exact asset

- Disc file: `DAT/SINKOU/PROGDAT.BIN;1`
- File size: 69,663 bytes
- Selected visible frame: streams/blocks 0 through 4
- Composite: five adjacent 64x240-pixel vertical strips, producing 320x240
- Original reconstructed PNG: `sdb_main_menu_asset/PROGDAT_group_0.png`
- Modified reconstructed PNG: `sdb_main_menu_asset/PROGDAT_group_0_white_square.png`
- Tested patched file: `sdb_main_menu_asset/PROGDAT_white_square_exact_v2.BIN`
- Patched-file SHA-256:
  `7D3A5407C947B8F5063D3A9C94BE159D69C8FEA438CBDE298C3737A040BE7D25`

## Stream layout

| Strip | Compressed offset | Allocated/consumed size | Decoded size | TIM mode | Dimensions |
|---:|---:|---:|---:|---|---|
| 0 | `0x0000` | 1,926 | 15,904 | 8-bit indexed | 64x240 |
| 1 | `0x0786` | 4,183 | 15,904 | 8-bit indexed | 64x240 |
| 2 | `0x17DD` | 4,246 | 15,904 | 8-bit indexed | 64x240 |
| 3 | `0x2873` | 5,353 | 15,904 | 8-bit indexed | 64x240 |
| 4 | `0x3D5C` | 3,282 | 15,904 | 8-bit indexed | 64x240 |

Each decoded strip has the same standard TIM header map:

| Decoded offset | Field | Value |
|---:|---|---|
| `0x00` | TIM magic | `0x00000010` |
| `0x04` | Flags | `0x00000009` (8-bit indexed + CLUT) |
| `0x08` | CLUT block size | 524 bytes |
| `0x0C` | CLUT X | 0 |
| `0x0E` | CLUT Y | 480 |
| `0x10` | CLUT width | 256 colors |
| `0x12` | CLUT height | 1 |
| `0x14` | CLUT pixels | 256 little-endian BGR555/STP words |
| `0x214` | Image block size | 15,372 bytes |
| `0x218` | Image X | 0 |
| `0x21A` | Image Y | 0 |
| `0x21C` | Stored word width | 32 words = 64 8-bit pixels |
| `0x21E` | Height | 240 |
| `0x220` | Indexed pixels | 64x240 bytes |

The five TIMs reuse the same staging coordinates (`image 0,0`, `CLUT 0,480`).
This indicates sequential upload/rendering rather than five simultaneously
resident source textures.

## Compression and exact-size re-encoding

The outer stream uses the project's confirmed custom codec:

- `00..7F`: literal run
- `80..BF`: repeated-byte run
- `C0..DF`: LZ back-reference
- `E0..EF`: arithmetic/delta run
- `FF`: end marker

For the final edit, pixels `(20..39, 80..99)` in strip 0 were changed to
palette index 1. Original CLUT index 1 is `0xFFFE`, a near-white BGR555/STP
color. The CLUT itself was not modified in the final version.

The modified strip initially encoded to 1,915 bytes. One 12-byte RLE span was
represented as an equivalent literal span, adding exactly 11 bytes. The final
stream therefore consumes exactly 1,926 bytes, preserving the fixed start of
strip 1. Decode/re-encode round-trip verification passed.

An earlier 1,917-byte experiment shifted strip 1 and made the remainder of the
screen white. That failure proved the strip offsets are fixed and that merely
being smaller than the allocation is insufficient here: the first stream must
retain its exact consumed length unless the offset table/loader is also changed.

## VRAM path and live proof

The VRAM viewer showed the composed 320x240 classroom frame in two buffers:

- first framebuffer: approximately `(0,0)` through `(319,239)`
- second framebuffer: approximately `(0,256)` through `(319,495)`

Direct framebuffer writes through the PCSX-Redux web API appeared briefly and
were overwritten by subsequent rendering. This ruled out framebuffer patching
as an asset modification.

The successful path was:

```text
DAT/SINKOU/PROGDAT.BIN;1
  -> custom stream decompression
  -> standard 8-bit TIM strip
  -> CLUT + indexed texture upload to staging VRAM
  -> strip rendering into both framebuffers
  -> visible main-menu background
```

PCSX-Redux accepted the full edited file through its temporary CD patch API.
After a hard reset and return to the menu, the complete classroom image was
correct and the white square remained visible across frames. The underlying
`game.bin` was not rebuilt or modified.

## Reversibility

The original extracted file remains at
`sdb_main_menu_asset/PROGDAT.BIN`. PCSX-Redux's accumulated temporary disc
patches can be cleared through `POST /api/v1/cd/ppf?function=clear`, followed by
a hard reset. This has not been done yet, so the successful test remains visible.

## Decoder call chain and runtime captures

Static work identified the same custom decompressor in `PROG.EXE` at file
offset `0x10214`, corresponding to runtime address `0x80044A14` when that EXE is
loaded at `0x80035000`. Its signature matches the previously confirmed
decompressor implementation.

However, the classroom menu did not map that executable/address while visible,
and breakpoints armed before reset did not survive or observe this load path.
Therefore the following requested items remain **not yet captured for this
specific menu load**:

- exact active loader executable/overlay
- compressed source RAM pointer
- decompressed TIM destination pointer
- return address and complete caller chain
- exact TIM-to-GPU upload function address
- GPU command/LoadImage call site

The offline archive identity, decoded format, VRAM result, exact-size reversible
encoding, and runtime asset reinjection are proven. The CPU-side pointer/call
chain portion remains open and must not be reported as complete.

## SDB fields that do not apply

There is no `SDB2.x`/`MS` header, animation frame count, tile/delta frame graph,
or SDB output buffer for this selected asset. Frame count is one composite still
image assembled from five TIM strips. Those SDB-specific questions belong to a
different photo asset and were deliberately not generalized from this test.

## Remaining unknowns

- The exact table or code that supplies the five fixed compressed offsets.
- The active executable responsible for this menu's load/render cycle.
- Whether the strips are decompressed every frame or cached and re-uploaded by
  another redraw path; direct framebuffer writes alone only prove recurring
  framebuffer replacement.
- The exact GPU packet and function call chain for staging upload and strip draw.
- Persistent physical BIN/CUE reinsertion and real-hardware validation; neither
  was attempted.

## Multi-strip text reinjection proof

A second asset-level test added `TRANSLATED WITH GCRTS` across the upper part
of the 320x240 image. Unlike the first square test, this modification crosses
multiple 64-pixel TIM strip boundaries.

- Exact patched file: `sdb_main_menu_asset/PROGDAT_translated_with_gcrts_exact.BIN`
- SHA-256:
  `3C5BBEEC3AF947A0C3E080A62F54EB8F7453925FB7C80A5D9CFA66912DCF8518`
- Deterministic 320x240 preview:
  `sdb_main_menu_asset/PROGDAT_translated_with_gcrts_320x240.png`
- Reproducible builder:
  `sdb_main_menu_asset/build_text_patch.ps1`

All five edited streams passed decode/re-encode comparison and retained their
exact original consumed sizes:

| Strip | Original | Initial re-encode | Final exact size |
|---:|---:|---:|---:|
| 0 | 1,926 | 1,844 | 1,926 |
| 1 | 4,183 | 4,170 | 4,183 |
| 2 | 4,246 | 4,240 | 4,246 |
| 3 | 5,353 | 5,278 | 5,353 |
| 4 | 3,282 | 3,166 | 3,282 |

The patch was accepted by the PCSX-Redux temporary CD API. After a hard reset,
the complete text was visible in-game, remained stable across frames, aligned
correctly across strip boundaries, and did not corrupt the background or menu
UI. This is the strongest current proof of reversible extraction, editing,
exact-size encoding, and runtime reinjection for this specific asset.
