# Main-menu image investigation artifacts

This directory contains extracted originals, decoded previews, runtime captures,
and exact-size test patches for the Twilight Syndrome classroom main menu.

The authoritative technical report is `../IMAGE_ASSET_STATUS.md`.

## Canonical original inputs

| File | Bytes | SHA-256 |
|---|---:|---|
| `PROGDAT.BIN` | 69,663 | `CD265BC097F53B374A8E9A15E041AAB20F20B0413C65A36F8332131ACE03CA30` |
| `MENUDAT.BIN` | 30,318 | `1E31ABC2987F73F9C253E45329A97D2CCD1B83C486EE99EE324712D02DE7DE10` |

Treat these two files as read-only source material.

## Recommended artifacts

- `PROGDAT_group_0.png` — original reconstructed classroom, 320x240.
- `PROGDAT_group_1.png` — reconstructed high-contrast scene layer/mask.
- `PROGDAT_group_2.png` — reconstructed desk/device scene.
- `PROGDAT_translated_with_gcrts_320x240.png` — deterministic text preview.
- `PROGDAT_translated_with_gcrts_exact.BIN` — live-verified text patch.
- `PROGDAT_white_square_exact_v2.BIN` — live-verified white-square patch.
- `MENUDAT_contact_sheet.png` — numbered view of all 32 menu sprites.
- `build_text_patch.ps1` — reproducible exact-size text patch builder.
- `vram_original.raw` — 1 MiB untouched VRAM capture from the menu session.

## Superseded or intermediate artifacts

- `PROGDAT_white_square.BIN` — stream 0 was shorter than its fixed slot; caused
  later strips to shift and rendered most of the screen white. Keep only as
  negative evidence.
- `PROGDAT_white_square_exact.BIN` — exact-size version that still used the
  wrong/black-looking palette choice. Superseded by `*_exact_v2.BIN`.
- `stream_white_index1.bin` — intermediate compressed stream, not a complete
  disc file and not suitable for direct patching.
- `PROGDAT_translated_with_gcrts_preview.png` — AI-generated conceptual preview
  at a different resolution; do not encode it. Use the 320x240 deterministic
  preview instead.
- `live_80100000.bin` — targeted live RAM capture; it did not identify the
  expected `PROG.EXE` loader and is not a decoded image asset.

## Rebuild the verified text patch

From the repository root on Windows:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\sdb_main_menu_asset\build_text_patch.ps1
```

Expected output:

- `PROGDAT_translated_with_gcrts_exact.BIN`
- length: 69,663 bytes
- SHA-256:
  `3C5BBEEC3AF947A0C3E080A62F54EB8F7453925FB7C80A5D9CFA66912DCF8518`

The script preserves the exact compressed length of each of blocks 0–4 and
verifies every edited stream by decoding it again.

## Temporary PCSX-Redux injection

With the PCSX-Redux web server enabled on port 8080, post the complete modified
file to:

```text
/api/v1/cd/patch?filename=DAT%2FSINKOU%2FPROGDAT.BIN%3B1
```

Then hard-reset and return to the classroom menu. This is a temporary emulator
patch; it does not rebuild or overwrite the physical `game.bin`.

To clear accumulated temporary disc patches, use the documented endpoint:

```text
POST /api/v1/cd/ppf?function=clear
```

Then hard-reset again.

## Menu sprite landmarks

- Start (`開始`): `MENUDAT.BIN` block 7, offset `0x1BD4`, 514 bytes, 100x24.
- Prepare (`準備`): block 8, offset `0x1DD6`, 498 bytes, 100x24.

Both are 4bpp indexed TIM sprites with 16-color CLUTs. They are identified and
decoded but have not yet completed the edit/re-encode/live-injection cycle.
