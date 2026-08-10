# GCRTS — Game Content Reconstruction & Translation System

## Project status & documentation map

This README documents the project's *original* phases (below) — the
data-only investigation, disassembly, and the `.CDB` codec breakthrough.
A large amount of work has happened since then: a live runtime-tracking
stack (asset lifecycle, screen object mapping, a Visual Inspector), a
full script bytecode decoder/encoder, and a complete audio/XA
investigation chain culminating in a live-captured, reproduced
`Setfilter(file=2, channel=1)` call. 506 tests pass as of the last
update.

- **For current, up-to-date project state**: [`docs/status/CURRENT_SYSTEM_STATUS.md`](docs/status/CURRENT_SYSTEM_STATUS.md)
  — the single, continuously-updated "present truth" doc (test counts,
  capability matrix, what's live-verified vs. still open).
- **For everything else, by topic**: [`docs/README.md`](docs/README.md)
  — the full documentation index (audio, assets, renderer, text engine,
  runtime tracking, tooling, investigations).

The rest of this file is the original, still-accurate account of Phases
1–5 and the `.CDB` codec breakthrough.

## Phases implemented so far

- **Phase 1** — binary loader, ASCII string extraction, JSON output.
  Extended with real CD-ROM XA Mode2/2352 sector de-interleaving
  (`gcrts/cdrom.py`) once real-disc testing showed it was necessary for
  anything bigger than ~2KB.
- **Phase 2** — encoding detection (ASCII / Shift-JIS / UTF-16LE) and
  proximity-based clustering.
- **Phase 5 (partial, pulled forward)** — PS1 TIM texture decoding
  (`gcrts/tim.py`), added while chasing this game's font/text encoding.
- **ISO9660 filesystem walking** (`gcrts/iso9660.py`) — not in the
  original phase plan at all, added because reading the disc's real
  file table turned out to be far more informative than guessing at
  content from raw byte patterns.
- **Custom `.CDB` resource decompression** (`gcrts/cdb_codec.py`) — a
  real RLE/LZ77/delta-encoding hybrid codec, ported faithfully from the
  game's own decompiled decompression function (found via Ghidra +
  live emulator debugging, not guessed). This is the codec both
  `KFONT.CDB` (font) and `K0LINK.CDB` (chapter 0 script) use.

Not implemented yet: classification (dialogue/menu/system), layout
reconstruction, the exact indexing scheme that selects *which*
compressed chunk corresponds to a given character code or dialogue
line, UI border/box detection, screen reconstruction, translation
pipeline.

## Status on this game's actual text (important, unresolved)

Tested against a real disc image (*Twilight Syndrome - Tansaku Hen*,
PS1, `MODE2/2352`). Findings so far, roughly in the order they were
discovered:

- The disc's dialogue/menu text is **not stored as plain Shift-JIS**.
  A literal search across the entire 636MB image found zero
  occurrences of common words (アイテム, メニュー, です, ください) and
  even single common particles (の, は, を) appeared only at a rate
  consistent with random chance, not real embedded text.
- A real, working **TIM image decoder** (`gcrts/tim.py`) was built and
  validated against this disc: it correctly renders backgrounds
  (a shelf of jars, a skeleton prop by a door) and a character sprite
  (128x128, 8bpp indexed). CD sector de-interleaving
  (`gcrts/cdrom.py`) was required to decode anything over ~2KB
  correctly — without it, large images decoded as scanline noise.
- A genuine **ASCII font atlas** was found this way: an 8x8-pixel
  bitmap font covering space (0x20) through underscore (0x5F) in exact
  ASCII code order (`glyph_index = ascii_code - 0x20`).
- Reading the actual **ISO9660 file table** (`gcrts/iso9660.py`)
  revealed the real disc architecture instead of continuing to guess
  from raw bytes: a small boot executable (`SLPS_001.02`, 24KB — too
  small to contain real game logic), per-chapter/per-character overlay
  executables (`CAP0-4.EXE`, `CAPX.EXE`, and character-named overlays
  like `MRIKA.EXE`, `MYOKO.EXE`), and a `DAT/` resource tree containing
  a `FONT/` directory and per-chapter script files.
- `DAT/FONT/KFONT.CDB` (602KB, "K" almost certainly for Kanji) is very
  likely the real dialogue font — a proprietary format (not a TIM):
  it opens with a table of `(offset, length)` 16-bit pairs, one per
  glyph, where each entry's `offset + length` equals the *next*
  entry's `offset` (a variable-length glyph directory). This chained
  arithmetic relationship held for 7 consecutive entries before hitting
  a run of `(0,0)` gap entries — far too improbable to be coincidence,
  so the directory-table structure itself is confirmed, even though the
  glyph bitmap's exact bit-packing isn't decoded yet.
- `DAT/CAP0/K0LINK.CDB` (2.7MB, almost certainly chapter 0's actual
  script) uses the **same convention**: a fixed one-sector (2048-byte,
  512-entry) directory table followed by a variable-length data blob —
  confirmed by both files independently breaking their offset/length
  chain at exactly entry 512. Decoding one real message's raw bytes
  this way, though, shows dense, high-entropy content — not simple
  1-byte or 2-byte glyph-index sequences — so `K0LINK.CDB` is more
  likely a mixed script/bytecode format (game logic opcodes interleaved
  with encoded text) than a plain message-text table.
- **Net result of the data-only investigation:** the text's *location*
  is known precisely (which file, which table entry, which byte range)
  even though the exact in-message character encoding wasn't cracked
  from data alone.

### Executable disassembly (capstone + MIPS), and where it stalled

Went further: extracted `CAP0.EXE` via `gcrts/iso9660.py`, parsed its
PS-X EXE header (`text_addr=0x80045000`, entry `0x80077d18`), and used
`capstone` (MIPS32LE) to disassemble it directly. This is real,
verified findings from reading actual code — not guessing:

- The literal strings `"KFONT"` and `"K0LINK"` exist in `CAP0.EXE`,
  alongside a full path/filename table (`\DAT\CAP0\`, `\DAT\FONT\`,
  `K0LINK`/`K1LINK`/.../`KXLINK`, `MYOKO.EXE`, `MPRO.EXE`, etc.) —
  matching the ISO9660 findings exactly.
- Found the real cross-reference: code at `0x8006e2d8` reads a mode
  byte from a struct, indexes an array to get a parameter, and calls a
  generic resource-loader at `0x8005342c` with the `"KFONT"` string
  address, a fixed RAM buffer address (`0x8001a200`), and that
  parameter.
- Disassembling `0x8005342c` and recognizing the PS1 BIOS syscall
  trampolines it calls (`jr $t2` with `$t2=0xA0`/`0xB0` is the standard
  BIOS dispatch mechanism — identified `strlen`, `strcpy`, `strcat`,
  `strcmp` this way) showed it builds the exact path
  `\DAT\FONT\KFONT.CDB;1`, checks CD-ROM status, opens the file (with a
  retry loop), and loads it into that fixed buffer — **with no
  decompression call anywhere in the chain**. That's a real, useful
  negative result: the raw on-disc bytes are used as-is at runtime, so
  the directory-table format found from data alone is the right track,
  not an intermediate compressed form.
- Searching for further code references to the `0x8001a200` buffer
  found the actual glyph-lookup function (`0x80076b20`). Carefully
  hand-simulating its register arithmetic instruction-by-instruction
  shows character codes DO directly index the font: a 16-bit count `H`
  at `buffer+8`, an `H`-entry array of 32-bit values at `buffer+12`
  (indexed as `buffer+12+4*code`), and a 1-byte flag array right after
  it (at `buffer+12+4*H+code`) — a genuine two-level lookup, not the
  flat sequential array assumed during the data-only phase. This
  explains why every "does the table just continue past entry 8/18?"
  hypothesis tried during data-only analysis failed: the real indexing
  isn't sequential.
- **Where static analysis stalled:** testing the reconstructed
  glyph-lookup formula against raw file bytes gave numbers too large
  to be valid file offsets *or* valid PS1 RAM addresses. Tracing the
  load call by hand (`0x800538e0` → `0x800809b0`) turned into guessing
  register semantics one function at a time with no way to verify —
  a real practical wall for static-only reading.

### Breaking through with a live emulator (PCSX-Redux + GDB + Ghidra decompiler)

Set up **PCSX-Redux** (built from Azure CI artifacts) with a
legitimately-owned BIOS dump, wired its `-gdb` server to a custom
Python GDB-remote-protocol client, and used it alongside Ghidra's
*headless decompiler* (not just capstone disassembly) against the same
`CAP0.EXE` project:

- Paused the running game mid-gameplay and read live RAM. Scanning all
  2MB of PS1 RAM for the exact `KFONT.CDB` file bytes found **zero
  matches** — but scanning for a chunk starting at *file offset 2048*
  found a **perfect byte-for-byte match** at RAM address `0x8001a200`.
  The loader simply skips the first 2048-byte table sector and copies
  the rest verbatim; no transformation on that copy step at all.
- The same technique on `K0LINK.CDB` found its *first* 2048 bytes
  (the table) copied verbatim to `0x800dad44` — the exact address our
  hand-disassembly had predicted — but the data blob after it does
  **not** match the raw file, confirming real compression there.
- Ghidra's headless decompiler (`analyzeHeadless -postScript`, far
  clearer than raw capstone output) on the loader chain revealed
  `FUN_8007681c`: a genuine custom decompression codec (literal runs,
  RLE fill, LZ77-style back-references, arithmetic/delta fills, `0xFF`
  end marker) called on-demand when a specific glyph/message chunk is
  needed. This is a faithful port, not a guess — see
  `gcrts/cdb_codec.py`.
- `FUN_800538e0`, decompiled cleanly, confirmed the very first
  data-only finding was right all along: `(offset, length)` **16-bit**
  pairs (not the 32-bit two-level scheme guessed mid-investigation),
  read from a shared table buffer and indexed by a per-call parameter.

**Bottom line:** the actual compression codec used by this game's
`.CDB` resource files is now solved and implemented
(`gcrts/cdb_codec.py`, unit-tested against the decompiled algorithm's
exact control-byte semantics). What's left open is the precise
indexing rule connecting a character code or dialogue-line number to
*which* compressed chunk to feed the codec — the codec itself no
longer needs guessing once that's found.

## Run

### Asset Inspector (MENUDAT MVP)

```powershell
python -m gcrts.asset_inspector_ui sdb_main_menu_asset/MENUDAT.BIN `
  --disc-path "DAT/SINKOU/MENUDAT.BIN;1" `
  --workspace asset_workspace
```

CLI discovery uses the same backend:

```powershell
python -m gcrts.asset_cli sdb_main_menu_asset/MENUDAT.BIN list
python -m gcrts.asset_cli sdb_main_menu_asset/MENUDAT.BIN show 7
```

The browser decodes all 32 sprites individually and opens on block 7 / Start.
It exposes metadata, CLUT usage, palette-preserving PNG operations, indexed text
replacement, exact-size compression feedback, safe output building and temporary
PCSX-Redux testing. Canonical inputs are never overwritten.

```bash
python -m gcrts.cli path/to/game.bin
```

Options:

- `--min-length N` — minimum run length in bytes to count as an
  extracted string (default: 4)
- `--max-cluster-gap N` — max byte gap between two strings for them to
  be merged into the same cluster (default: 32)
- `--output path.json` — where to write results (default:
  `<input>.gcrts.json`)

Note: `cli.py` currently scans the **raw** disc image, not the
de-interleaved payload — see `gcrts/cdrom.py` design note below.

Output JSON shape:

```json
{
  "source_file": "game.bin",
  "file_size": 123456,
  "min_length": 4,
  "max_cluster_gap": 32,
  "strings_found": 4,
  "clusters_found": 2,
  "strings": [
    { "offset": 128, "text": "HELLO", "encoding": "ascii", "length": 5 }
  ],
  "clusters": [
    {
      "cluster_id": 0,
      "start_offset": 128,
      "end_offset": 133,
      "strings": [ { "offset": 128, "text": "HELLO", "encoding": "ascii", "length": 5 } ]
    }
  ]
}
```

## Visual Inspector

With PCSX-Redux running and its web server enabled, launch the screen-driven
inspector with:

```powershell
python -m gcrts.visual_inspector_ui --registry screen_mappings.json --asset-source sdb_main_menu_asset/MENUDAT.BIN
```

Choose `twilight.main_menu`, then capture the current frame or load a screenshot.
START and SETTINGS/PREPARE route directly to their existing Asset Inspector
entries. See [`docs/assets/VISUAL_ASSET_INSPECTOR.md`](docs/assets/VISUAL_ASSET_INSPECTOR.md) for the workflow and current limits.

## Test

```bash
python -m pip install -r requirements.txt
python -m pytest tests/
```

43 tests total. Most use small synthetic byte fixtures (ASCII/Shift-JIS/
UTF-16LE run detection, minimum-length filtering, clustering, CD-ROM
sector parsing, ISO9660 directory walking, TIM image decoding, the
`.CDB` decompression codec). The Shift-JIS detector's
plausibility heuristics were specifically tuned and re-validated against
the real disc image described above (see `gcrts/encoding.py` docstrings
for the false-positive/false-negative findings that shaped them) — that
is real-data validation, not just synthetic-fixture coverage. Treat
`--min-length` and `--max-cluster-gap` as adjustable starting points,
not tuned constants.

## Design notes

- `gcrts/loader.py` — Binary Segmentation Engine (Phase 1 subset): just
  loads the whole file as one `RawSegment`. No entropy-based splitting
  into TEXT/IMAGE/FONT/UI segments yet.
- `gcrts/cdrom.py` — strips CD-ROM XA Mode2/2352 sector framing (12-byte
  sync + 4-byte header + 8-byte subheader + trailing EDC/ECC) and
  concatenates the real Form1/Form2 data payloads. Required for
  correctly decoding any asset bigger than a single sector's payload
  (~2048 bytes) — confirmed by two >100KB images that decoded as noise
  without it and perfectly once it was applied.
- `gcrts/encoding.py` — per-offset run detectors, tried in priority
  order (utf-16le > shift_jis > ascii); the extractor keeps whichever
  detector produces the longest match at each position. The Shift-JIS
  detector requires either a kana character or a longer run length
  before trusting a match — added after real-data testing showed ~70%
  of raw matches were minimum-length noise from coincidental byte
  patterns in unrelated binary data.
- `gcrts/extractor.py` — scans a segment end-to-end using the detectors
  above, emitting `ExtractedString(offset, text, encoding, length)`.
- `gcrts/cluster.py` — groups strings by offset proximity only
  (`max_gap` bytes between end of one string and start of the next).
  Does not yet cluster by repeated structure or classify cluster
  semantics (dialogue/menu/system) — that's Phase 3.
- `gcrts/tim.py` — decodes PS1 TIM textures (4bpp/8bpp indexed with
  CLUT, 16bpp direct color; 24bpp not implemented, not encountered
  yet). `find_tim_images()` scans a buffer for the `0x10000000` magic
  and rejects coincidental matches by cross-checking each block's
  length field against what its declared width/height implies.
- `gcrts/iso9660.py` — walks the disc's actual ISO9660 filesystem
  (Primary Volume Descriptor + directory records) to read real
  filenames/sizes/locations instead of guessing content from raw byte
  patterns. Only what's needed to walk the tree is implemented: no
  Rock Ridge/Joliet extensions, no multi-extent files, no path table
  (directories are walked directly). `read_logical_sectors()` reads
  sectors by exact LBA rather than using `gcrts.cdrom`'s concatenated
  stream, since ISO9660 offsets are defined relative to specific LBAs.
- `gcrts/cdb_codec.py` — decompresses this game's custom `.CDB`
  resource format: literal runs, RLE fill, LZ77-style back-references,
  arithmetic/delta fills, and an `0xFF` end marker. Ported directly
  from `FUN_8007681c`, decompiled via Ghidra from `CAP0.EXE` (see the
  Status section above and `GhidraTools/ghidra_project/NOTES.md` for
  the live-debugging investigation that found it) — not reverse
  engineered from data alone. Tests construct synthetic byte streams
  for each control-byte range and check exact decompiled semantics
  (including the mod-256 wraparound on delta fills and self-overlapping
  LZ back-references).
