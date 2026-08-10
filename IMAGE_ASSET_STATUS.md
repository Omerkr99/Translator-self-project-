# GCRTS Image Asset Status — Main Menu Investigation

**Status date:** 2026-08-09  
**Scope:** the classroom main menu and its immediately related visual assets  
**Evidence level:** offline extraction + exact-size re-encoding + live PCSX-Redux reinjection

## Executive result

The classroom main-menu background has been taken through a complete reversible
asset workflow: disc-file identification, stream extraction, decompression,
offline reconstruction, PNG export, deterministic editing, exact-size
re-encoding, temporary disc injection, hard reset, and visual confirmation.

The visible background is not SDB and is not a CDB entry. It is stored in
`DAT/SINKOU/PROGDAT.BIN;1` as five compressed standard TIM strips. A second
disc file, `DAT/SINKOU/MENUDAT.BIN;1`, contains 32 independent 4bpp TIM menu
sprites, including the Start and Prepare labels.

## What has been identified

| Visible element | Disc source | Internal asset | Status |
|---|---|---|---|
| Classroom background | `DAT/SINKOU/PROGDAT.BIN;1` | blocks 0–4 | Extracted, decoded, edited, re-encoded, live-verified |
| High-contrast scene layer/mask | `DAT/SINKOU/PROGDAT.BIN;1` | blocks 5–9 | Extracted and reconstructed; exact runtime role not yet traced |
| Desk/device scene | `DAT/SINKOU/PROGDAT.BIN;1` | blocks 10–14 | Extracted and reconstructed; not edited live |
| Start label (`開始`) | `DAT/SINKOU/MENUDAT.BIN;1` | block 7 | Identified and decoded; not yet modified live |
| Prepare label (`準備`) | `DAT/SINKOU/MENUDAT.BIN;1` | block 8 | Identified and decoded; not yet modified live |
| Other menu labels/sounds/locations | `DAT/SINKOU/MENUDAT.BIN;1` | blocks 0–31 | Contact sheet reconstructed; semantics partly visible from glyphs |

## 1. Classroom background (`PROGDAT`, blocks 0–4)

### Exact source

- ISO path: `DAT/SINKOU/PROGDAT.BIN;1`
- Extracted file: `sdb_main_menu_asset/PROGDAT.BIN`
- File length: 69,663 bytes
- SHA-256: `CD265BC097F53B374A8E9A15E041AAB20F20B0413C65A36F8332131ACE03CA30`
- Composite output: 320x240 pixels
- Composition: five adjacent 64x240 strips
- Pixel format: 8bpp indexed TIM
- Palette: 256 little-endian BGR555/STP entries per decoded TIM

### Fixed stream layout

| Block | Compressed offset | Exact consumed size | Decoded size | Visible X range |
|---:|---:|---:|---:|---:|
| 0 | `0x0000` | 1,926 | 15,904 | 0–63 |
| 1 | `0x0786` | 4,183 | 15,904 | 64–127 |
| 2 | `0x17DD` | 4,246 | 15,904 | 128–191 |
| 3 | `0x2873` | 5,353 | 15,904 | 192–255 |
| 4 | `0x3D5C` | 3,282 | 15,904 | 256–319 |

The boundaries are functionally fixed. An early patch shortened block 0 by nine
bytes and moved block 1 forward; the first strip rendered correctly while the
remaining image became white/corrupt. Restoring block 0 to exactly 1,926
consumed bytes restored all later strips. “Equal to or smaller than the
allocation” is therefore insufficient for this file unless offsets are also
updated; every replaced stream should retain its exact original consumed size.

### Decoded TIM header

| Offset | Field | Value |
|---:|---|---|
| `0x000` | Magic | `0x00000010` |
| `0x004` | Flags | `0x00000009` — 8bpp indexed, CLUT present |
| `0x008` | CLUT block length | 524 bytes |
| `0x00C` | CLUT X | 0 |
| `0x00E` | CLUT Y | 480 |
| `0x010` | CLUT width | 256 |
| `0x012` | CLUT height | 1 |
| `0x014` | CLUT data | 512 bytes, BGR555/STP |
| `0x214` | Image block length | 15,372 bytes |
| `0x218` | Image X | 0 |
| `0x21A` | Image Y | 0 |
| `0x21C` | VRAM word width | 32 words = 64 8bpp pixels |
| `0x21E` | Height | 240 |
| `0x220` | Pixel indices | 15,360 bytes |

All five strips declare the same staging coordinates: image `(0,0)` and CLUT
`(0,480)`. They are therefore uploaded/rendered sequentially through a reused
staging region rather than being resident side-by-side as source textures.

### Compression

The containing streams use the confirmed game codec:

- `00..7F`: literal run of `control + 1` bytes
- `80..BF`: repeated-byte run of `control - 0x7D` bytes
- `C0..DF`: LZ back-reference of `control - 0xBC` bytes
- `E0..EF`: arithmetic/delta run of `control - 0xDC` bytes
- `FF`: stream terminator

The exact-size builder can deliberately replace selected compressed tokens with
equivalent literal tokens. This increases encoded length without changing the
decoded TIM and allows a smaller re-encode to be expanded to the exact original
consumed size.

## 2. Proven edits

### White-square proof

A 20x20 area in strip 0 at composite coordinates `(20,80)` was changed to
palette index 1. In the original strip-0 CLUT, index 1 is `0xFFFE`, a near-white
BGR555/STP color.

- Final file: `PROGDAT_white_square_exact_v2.BIN`
- Length: 69,663 bytes
- SHA-256: `7D3A5407C947B8F5063D3A9C94BE159D69C8FEA438CBDE298C3737A040BE7D25`
- Result: stable white square after hard reset; background otherwise intact

This test also distinguished asset injection from framebuffer injection.
Writing the final framebuffer produced a mark for only a frame because the game
redrew it. Editing the compressed TIM made the square a persistent part of the
background.

### Multi-strip text proof

`TRANSLATED WITH GCRTS` was rendered at the top of a deterministic 320x240
preview and converted into palette indices across all affected TIM strips.
White glyph pixels use existing palette index 1. The shadow from the visual
preview was intentionally omitted from the encoded asset to remain within the
fixed stream budgets.

- Preview: `PROGDAT_translated_with_gcrts_320x240.png`
- Encoded file: `PROGDAT_translated_with_gcrts_exact.BIN`
- File length: 69,663 bytes
- SHA-256: `3C5BBEEC3AF947A0C3E080A62F54EB8F7453925FB7C80A5D9CFA66912DCF8518`

| Strip | Original size | Re-encoded size | Exact final size |
|---:|---:|---:|---:|
| 0 | 1,926 | 1,844 | 1,926 |
| 1 | 4,183 | 4,170 | 4,183 |
| 2 | 4,246 | 4,240 | 4,246 |
| 3 | 5,353 | 5,278 | 5,353 |
| 4 | 3,282 | 3,166 | 3,282 |

All five streams passed decode/re-encode comparison. The modified file was
accepted by PCSX-Redux's temporary CD patch API. After hard reset, the text was
visible across strip boundaries, stable across frames, and the background and
menu UI remained correct.

## 3. VRAM findings

The main VRAM viewer showed the fully composed classroom image in two buffers:

- approximately `(0,0)` to `(319,239)`
- approximately `(0,256)` to `(319,495)`

The untouched 1 MiB VRAM snapshot is saved as `vram_original.raw` with SHA-256
`A69AA3CBD6E8D37FC9B45D8B39EF792CBD39CD40662E5EE5A308B3950769223B`.

PCSX-Redux web API operations proven in this investigation:

- `GET /api/v1/gpu/vram/raw` — full VRAM capture
- `POST /api/v1/gpu/vram/raw?...` — partial VRAM update
- `POST /api/v1/cd/patch?filename=DAT/SINKOU/PROGDAT.BIN;1` — temporary disc-file replacement
- `POST /api/v1/cd/ppf?function=clear` — documented rollback path for accumulated temporary disc patches

No physical BIN/CUE rebuild was performed.

## 4. Other `PROGDAT` image groups

`PROGDAT.BIN` contains fifteen decoded TIM streams organized into three groups
of five vertical strips:

| Group | Blocks | Format | Composite | Current interpretation |
|---:|---:|---|---|---|
| 0 | 0–4 | 8bpp indexed | `PROGDAT_group_0.png` | Classroom background; live-confirmed |
| 1 | 5–9 | 4bpp indexed | `PROGDAT_group_1.png` | High-contrast scene mask/layer; runtime purpose not proven |
| 2 | 10–14 | 16bpp direct | `PROGDAT_group_2.png` | Desk/device scene; visually reconstructed |

Do not currently describe group 1 as the menu-button layer. The extracted image
is a scene-wide high-contrast mask. The actual menu-label sprites are in
`MENUDAT.BIN`.

## 5. Menu sprites (`MENUDAT.BIN`)

### Container

- ISO path: `DAT/SINKOU/MENUDAT.BIN;1`
- Extracted file: `sdb_main_menu_asset/MENUDAT.BIN`
- Length: 30,318 bytes
- SHA-256: `1E31ABC2987F73F9C253E45329A97D2CCD1B83C486EE99EE324712D02DE7DE10`
- Contents: 32 concatenated compressed standard TIM sprites
- Format: 4bpp indexed TIM with 16-color BGR555/STP CLUT
- Contact sheet: `MENUDAT_contact_sheet.png`

### Main-menu buttons

| Meaning | Visible text | Block | Compressed offset | Exact size | Dimensions |
|---|---|---:|---:|---:|---:|
| Start | `開始` | 7 | `0x1BD4` | 514 bytes | 100x24 |
| Prepare | `準備` | 8 | `0x1DD6` | 498 bytes | 100x24 |

The contact sheet shows the glyph shapes in a neutral palette. In-game, the
selected Start label is red/pink while Prepare is dark. Current evidence favors
runtime CLUT selection or primitive color modulation rather than separate
selected/unselected bitmaps, but that color-state mechanism is not yet traced
and remains **LIKELY**, not confirmed.

Blocks 7 and 8 have been identified and decoded but have not yet been edited,
re-encoded, or reinjected. They are the best next target for a focused menu
sprite editor proof.

## 6. Reproducible files

| File | Purpose | Status |
|---|---|---|
| `PROGDAT.BIN` | Untouched extracted source | Canonical source |
| `PROGDAT_group_0.png` | Reconstructed original classroom | Canonical reference |
| `PROGDAT_group_1.png` | Reconstructed high-contrast layer | Reference; role partial |
| `PROGDAT_group_2.png` | Reconstructed desk/device scene | Reference |
| `PROGDAT_white_square_exact_v2.BIN` | First correct persistent edit | Verified artifact |
| `PROGDAT_translated_with_gcrts_320x240.png` | Deterministic text preview | Builder input |
| `PROGDAT_translated_with_gcrts_exact.BIN` | Final text patch | Verified artifact |
| `build_text_patch.ps1` | Rebuilds exact text patch | Reproducible tool |
| `MENUDAT.BIN` | Untouched menu-sprite source | Canonical source |
| `MENUDAT_contact_sheet.png` | All 32 sprites labeled by block | Navigation/reference |
| `vram_original.raw` | Untouched live VRAM capture | Runtime evidence |

Experimental or superseded files are documented in
`sdb_main_menu_asset/README.md` and must not be mistaken for final patches.

## 7. What is proven and what is not

### LIVE VERIFIED

- Exact disc file for the classroom background.
- Complete offline reconstruction of the visible 320x240 frame.
- 8bpp TIM header, palette, pixel, and five-strip layout.
- Custom-codec decoding and round-trip re-encoding.
- Exact consumed-size preservation for all five edited streams.
- Temporary full-file replacement through PCSX-Redux.
- Persistent white-square edit after hard reset.
- Persistent text edit across multiple strip boundaries after hard reset.
- Two composed framebuffer locations in VRAM.

### STATIC/OFFLINE CONFIRMED

- Three five-strip image groups in `PROGDAT.BIN`.
- 32 independent 4bpp TIM sprites in `MENUDAT.BIN`.
- Start is `MENUDAT` block 7; Prepare is block 8.
- Standard TIM palette/pixel layouts for these decoded assets.

### PARTIAL OR UNKNOWN

- Active executable/overlay that owns this classroom load path.
- Compressed source and decoded destination RAM pointers during the actual load.
- Complete CPU decoder caller chain for this specific menu.
- Exact TIM upload/DrawSync/GPU packet call sites.
- Exact reason and consumer for `PROGDAT` group 1.
- Selected/unselected button color implementation.
- Persistent ISO/BIN/CUE rebuilding and real-hardware behavior.

## 8. SDB scope correction

No `SDB2.x` or `MS` header is involved in the selected classroom background or
the two identified menu buttons. There is no animation frame count, SDB tile
graph, or SDB delta dependency to report for these assets. The original broader
SDB-photo objective remains a separate future investigation and must use a
different visible photo asset.

## 9. Asset-inspector direction

The evidence supports a future editor model where a visible region maps to an
asset descriptor:

```json
{
  "name": "main_menu.start",
  "file": "DAT/SINKOU/MENUDAT.BIN",
  "block": 7,
  "compressed_offset": 7124,
  "compressed_size": 514,
  "width": 100,
  "height": 24,
  "pixel_format": "TIM_4BPP_INDEXED"
}
```

The first safe implementation milestone is a `MENUDAT` browser/editor that
shows all 32 blocks, opens block 7 or 8 directly, exposes the 16-color CLUT,
exports/replaces PNG, reports encoded size, expands to the exact original size,
and applies a temporary PCSX-Redux patch. Screen-click-to-asset resolution can
then be added on top of these verified descriptors.

## Bottom line

The classroom background workflow is solved at the asset level for this one
file: extraction, decoding, reconstruction, deterministic editing, exact-size
encoding, temporary injection, reset, and visual verification all work. The
menu-button assets are now located and decoded, but their editing/injection
cycle and runtime color-state path are the next unfinished pieces.
