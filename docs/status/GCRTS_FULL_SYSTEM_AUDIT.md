# GCRTS Full System Audit

**Audit date/time:** 2026-08-09, immediately following a single continuous
session that ran from before noon through 5:13 PM local time.
**Claude's last-known state before this catch-up:** none reliable — the
assistant had not touched this project since approximately 12:00 today, and
per `GCRTS_CHANGES_SINCE_1200.md`, effectively the entire visible repository
state (Renderer 1 live proof write-up, the whole Asset Inspector / Visual
Inspector / Runtime Asset Tracker system, ~20 new docs) was produced inside
the catch-up window. There is no earlier commit or snapshot to compare
against; "last-known state" is reconstructed from documentation and file
timestamps only.
**Current test count:** **348 passed, 6 warnings, 0 failed** (`py -m pytest
tests/ -q`, re-run live for this audit, 14.57s, Python 3.13, 45 test files).
**Repository health:** zero Git commits, 102 untracked top-level paths, no
rollback safety, session/emulator artifacts mixed with source
(`.sentry-native/`, save states, memory cards, shader files). See §1.
**Current strongest completed capability:** a fully reversible, exact-size,
disc-file-level image edit-and-reinject pipeline for `PROGDAT`/`MENUDAT` TIM
assets, live-verified in PCSX-Redux and surviving Hard Reset (background
white-square + text edit, MENUDAT Start/Settings label edit).
**Current biggest blocker:** no automatic runtime consumer exists anywhere in
the system. Renderer 1's position mechanism is solved but not wired to the
game automatically; the asset/runtime tracker can prove one asset is
`DRAWN_THIS_FRAME` but the archive-read → decompress → VRAM-upload call chain
that would generalize this is not traced; and the Renderer-1 vs.
GCRTS-track OT-root evidence has never been cross-checked against each
other.

---

## Reading the status labels used throughout

`LIVE_VERIFIED`, `OFFLINE_VERIFIED`, `IMPLEMENTED`, `PARTIAL`,
`EXPERIMENTAL`, `DESIGNED_ONLY`, `UNKNOWN`, `UNSUPPORTED`, `BLOCKED`,
`RULED_OUT`, `STALE`. A capability is `IMPLEMENTED` only when working host
code exists and is tested; it does not imply the game consumes it.
`LIVE_VERIFIED` requires a running-emulator demonstration with readback
and/or a visible, reversible result. A format header match alone is never
"supported." VRAM residency alone is never `DRAWN_THIS_FRAME`. A saved
screenshot rectangle is never runtime detection.

---

## 1. Repository Health

- **Git**: `git log` reports "your current branch 'main' does not have any
  commits yet." Zero history, zero diffs, zero rollback safety. `git status`
  lists **102** top-level untracked paths (some directories inaccessible due
  to Windows permission locks — `asset_test_tmp/`, `visual_*_tmp/`,
  `workflow_*_tmp/`, etc. — themselves leftover experiment scratch
  directories that should not be part of a clean tree).
- **Tracked/untracked**: everything is untracked. There is no baseline
  commit to audit "modified files" against — every file is new relative to
  Git.
- **Tests**: **348 passed, 0 failed, 6 warnings**, 45 test files under
  `tests/`, re-run live for this audit. Warnings are all
  `Image.Image.getdata` Pillow deprecation notices, not correctness issues.
  Eleven `gcrts` modules have no same-named dedicated test file
  (`__init__`, `cli`, `editable_script`, `encoding`, `font_extension`,
  `glyph_atlas`, `glyph_char_map`, `live_extract`, `loader`,
  `script_decoder`, `script_encoder`) — most are exercised indirectly.
- **Generated/experimental artifacts in the repo root**: PCSX-Redux save
  states (`SLPS00102.sstate0-8`, `global.sstate`), memory cards
  (`memcard1.mcd`, `memcard2.mcd`), emulator config (`pcsx.json`), shader
  files (`offscreen.*`, `output.*`, `vram-viewer.*`), a Sentry crash-report
  directory (`.sentry-native/`), and a raw VRAM dump
  (`sdb_main_menu_asset/vram_original.raw`). None of this is source code;
  none of it should likely ship in a clean commit.
- **Stale docs**: `README.md` says "43 tests total" (accurate around Phase
  2, now off by 305). `RENDERER_SYSTEM_STATUS.md` cites "294 passing" as the
  newest number it could confirm — that count was itself superseded later
  the same day (348). `IMAGE_ASSET_STATUS.md` briefly said MENUDAT 7/8 were
  "not yet edited" before being superseded within the same afternoon by
  `MENUDAT_ASSET_CATALOG.md`.
- **Encoding problems**: multiple Markdown files contain mojibake in arrows/
  punctuation/Japanese text (noted independently by both
  `CURRENT_SYSTEM_STATUS.md` and `RENDERER_SYSTEM_STATUS.md`). This does not
  invalidate hex/byte evidence but is a real hygiene issue.
- **Missing helper scripts**: `RENDERER_LIVE_PROOF.md` references
  `scratchpad/estate.py`, `scratchpad/validate_profile.py`,
  `scratchpad/final_precise_trial_v2.py`, `scratchpad/ot_full_proof.py` —
  none of these are present in the repository (they lived in a session
  scratchpad outside the tracked tree). `pcsx.lua` is 2 bytes; `vram-viewer.lua`
  is effectively empty. The capture tooling that produced the live proof is
  not reproducible from what is checked in.
- **Duplicated/superseded reports**: `IMAGE_ASSET_STATUS.md` vs.
  `SDB_MAIN_MENU_ASSET_REPORT.md` vs. `sdb_main_menu_asset/README.md` cover
  overlapping ground with `IMAGE_ASSET_STATUS.md` self-declared as current
  and `SDB_MAIN_MENU_ASSET_REPORT.md` self-declared as the chronological log.
  `CURRENT_SYSTEM_STATUS.md` contains its own internal supersession (a
  "consolidated update" and "correction" section at the top, followed by
  ~1000 lines of older history below it that is only partly still valid).
- Nothing was cleaned up as part of this audit, per instructions.

## 2. Disc / Container Layer

| Capability | Status | Evidence |
|---|---|---|
| BIN/CUE reading | LIVE_VERIFIED | Real 636MB disc image loaded and walked throughout the project. |
| MODE2/2352 de-interleaving | OFFLINE_VERIFIED | `gcrts/cdrom.py`; confirmed necessary for any asset >~2KB. |
| ISO9660 extraction | OFFLINE_VERIFIED | `gcrts/iso9660.py`; walks real PVD/directory records against the disc. |
| CDB read (custom container) | OFFLINE_VERIFIED | `gcrts/cdb_codec.py`, cross-validated against the external toolkit's `rle.py`. |
| CDB write | IMPLEMENTED | `gcrts/asset_compression.py` deterministic encoder; not the same codec family as CDB specifically (see §3). |
| Concatenated compressed streams (PROGDAT/MENUDAT style) | LIVE_VERIFIED | Read, decode, edit, re-encode, reinject all proven for these two files. |
| Temporary PCSX-Redux disc replacement | LIVE_VERIFIED | `gcrts/pcsx_patch.py`, PCSX-Redux `POST /api/v1/cd/patch`, survives Hard Reset. |
| Persistent disc rebuild (real BIN/CUE) | NOT_IMPLEMENTED | No code path writes back into a physical disc image. External toolkit has `build.py`/`merge.py` but this is not ported or proven end-to-end here. |
| PPF support | NOT_IMPLEMENTED | Only a `POST /api/v1/cd/ppf?function=clear` *clear* endpoint is used (to remove temporary patches) — this is not PPF patch authoring. |
| Real-hardware support | UNKNOWN | Everything tested is PCSX-Redux only; no evidence anywhere of real-hardware testing. |

## 3. Compression Layer

Two distinct codecs exist and must not be conflated:

1. **CDB inner codec** (`gcrts/cdb_codec.py`) — decompiled from
   `FUN_8007681c`, used for `KFONT.CDB`/`K0LINK.CDB` chunks. Decode-only in
   practice; independently cross-validated against the external toolkit's
   `rle.py` byte-for-byte.
2. **PROGDAT/MENUDAT game codec** (`gcrts/asset_compression.py`) — same
   control-byte family (`00-7F` literal, `80-BF` repeat, `C0-DF` LZ
   back-reference, `E0-EF` arithmetic/delta, `FF` end), decode AND a
   deterministic encoder with exact-size expansion.

**EXACT_CONSUMED_SIZE vs MAX_ALLOCATED_SIZE**: for `PROGDAT`, a shorter
re-encoded stream is *not* sufficient — block boundaries are fixed offsets
into the container, so a shorter block shifts every later block and corrupts
the image (proven experimentally: a 9-byte-shorter block 0 turned the rest
of the image white/corrupt). The encoder therefore supports
`EXACT_CONSUMED_SIZE`: it re-encodes normally, and if the result is shorter
than the original, deliberately swaps compressed tokens (e.g. a 12-byte RLE
span) for size-equivalent literal-run tokens — same decoded output, larger
encoded length — until the exact original byte count is hit, verified by a
decode/re-encode round trip. `MAX_ALLOCATED_SIZE` (output may be smaller,
never larger) and `RELOCATABLE` (reserved, no proven container uses it yet)
also exist as descriptor policies but are not exercised by any live-verified
asset in this repository. **This exact-size rule is proven specifically for
PROGDAT/MENUDAT streams; it must not be assumed for every container without
separate evidence** — `UNKNOWN` policy blocks encoding/injection entirely
until a container's real constraint is established.

## 4. Visual Format Coverage

| Format | Identified | Decode | Preview | PNG Export | Edit | Encode | Temp Inject | Persistent Rebuild | Runtime Detection | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| TIM 4bpp indexed | YES | YES | YES | YES | YES | YES | YES | NO | YES (1 asset) | `asset_tim.py`, MENUDAT blocks; `vram_asset_detector.py` matched block 9 in live VRAM |
| TIM 8bpp indexed | YES | YES | YES | YES | YES | YES | YES | NO | NO | PROGDAT group 0; VRAM detection code exists generically but no live match logged for an 8bpp stream specifically |
| TIM 16bpp direct | YES | YES | YES | YES | NO | YES | NO | NO | NO | `IMAGE_FORMAT_ADAPTERS.md`: encode implemented, indexed editing explicitly N/A, no live inject attempt recorded for PROGDAT group 2 |
| Composite TIM (multi-strip) | YES | YES | YES | YES | YES | YES | YES | NO | PARTIAL | PROGDAT group 0 (5×64×240 strips → 320×240); live-injected and confirmed |
| Compressed TIM stream (game codec) | YES | YES | YES | YES | YES | YES | YES | NO | N/A (container-level, not a pixel format) | `asset_compression.py` |
| SDB2.0 | NO | NO | NO | NO | NO | NO | NO | NO | NO | Explicitly ruled out as the format for the studied assets (`SDB_MAIN_MENU_ASSET_REPORT.md` §8); no SDB asset has been located/confirmed anywhere in the repo |
| SDB2.2 | NO | NO | NO | NO | NO | NO | NO | NO | NO | Same — unsupported placeholder only, by policy (`IMAGE_FORMAT_ADAPTERS.md`) |
| MS 4 | NO | NO | NO | NO | NO | NO | NO | NO | NO | Unsupported placeholder |
| GP 4 | NO | NO | NO | NO | NO | NO | NO | NO | NO | Unsupported placeholder |
| Other/unknown formats | NO | NO | NO | NO | NO | NO | NO | NO | NO | Not encountered/investigated this session |

Recognition of a format is explicitly separated from support: `asset_descriptor.py`
allows a descriptor to record `SDB2.0`/`SDB2.2`/`MS4`/`GP4` as a known-but-
unsupported format tag without granting decode/edit/inject capability, per
`IMAGE_FORMAT_ADAPTERS.md`. None of these four have actually been located in
this game's data — "unsupported" here means "no decoder exists," not "found
and rejected."

## 5. Asset System

- **AssetDescriptor** (`gcrts/asset_descriptor.py`): JSON-serializable,
  records identity, disc source, container block/offset/size, decoded image
  metadata, encoding policy, semantic confidence, screen mapping, runtime
  state, verification facts, capabilities. Unknown JSON fields ignored for
  forward compatibility; invalid dimensions/offsets/unsafe policy
  combinations rejected.
- **Canonical asset IDs**: strings like `main_menu.start`, `main_menu.prepare`,
  `category.photos`, `progdat.group0` — assigned only where semantics are
  independently confirmed (Start/Prepare/five classroom strips); everything
  else uses a stable but semantically-uncommitted ID (per
  `ASSET_DESCRIPTOR_SPEC.md`: "meanings are not invented").
- **Registry** (`gcrts/asset_registry.py`): 32 manually-verified MENUDAT
  entries (confirmed by direct file inspection: 32 tuple literals) + 15
  PROGDAT stream entries across 3 groups.
- **Identity basis**: mixed and explicitly acknowledged as such —
  source-provenance (disc file + block index) for the registry entries;
  hash/binary-content match for VRAM detection (`asset_fingerprint.py`,
  `vram_asset_detector.py`); manual screen rectangle for the fallback mapper
  (`screen_mapping_registry.py`); and live GPU/OT correlation for the one
  proven `DRAWN_THIS_FRAME` case. **Weakness**: no single asset ID scheme
  unifies all four; a given asset can simultaneously have a registry entry,
  a manual rectangle, and (rarely) a live draw correlation, and the system
  resolves priority order (runtime > VRAM/GPU > manual mapping >
  candidate > unknown, per `VISUAL_INSPECTOR_ARCHITECTURE.md`) but does not
  merge or reconcile conflicting identities automatically.
- **Format/compression adapters**: separated cleanly (`asset_compression.py`
  vs. `asset_tim.py`), which is a real strength — UI code contains no
  TIM-parsing or compression-token logic per `ASSET_INSPECTOR_ARCHITECTURE.md`.
- **contains_text / translation_relevant**: fields exist on
  `CanonicalAssetIdentity` (`gcrts/runtime_content.py`) but are not populated
  by any observed live pipeline in this audit — present as schema, not
  demonstrated as populated end-to-end.

## 6. MENUDAT Current State

Catalog confirmed current: `MENUDAT_ASSET_CATALOG.md`'s 32-row table matches
`gcrts/asset_registry.py`'s 32 tuple entries exactly (spot-checked block
count, not every offset). All 32 blocks are 4bpp indexed TIM with a 16-entry
BGR555/STP CLUT from a single 30,318-byte file
(`DAT/SINKOU/MENUDAT.BIN;1`).

| Block | Name | Identified | Decoded | Edited | Re-encoded | Live-injected | Restored |
|---:|---|---|---|---|---|---|---|
| 7 | Start | YES | YES | YES | YES | YES (LIVE_VERIFIED, survives Hard Reset) | YES (restore path exists and was exercised) |
| 8 | Prepare/Settings | YES | YES | YES | YES | YES (LIVE_VERIFIED, survives Hard Reset) | YES |
| 9 | Photos (category label) | YES | YES | NO | NO | NO | N/A — this block's significance is instead as the one proven `DRAWN_THIS_FRAME` runtime-tracking case (VRAM word `640,96`, screen bounds `40,24,64,32` on the Photos page), not as an edit target |
| 0-6, 10-31 (remaining 29 blocks) | Various (system menu, chapter titles, photo/sound labels) | YES (offset/size/dimension level) | YES (all 32 individually decodable per the catalog's "direct access" column) | NO | NO | NO | N/A |

All 32 blocks can be opened, decoded, exported, and are individually
addressable through the Asset Browser (`asset_inspector_ui.py`) and CLI
(`asset_cli.py`); this is a real, tested capability. Only blocks 7 and 8 have
been carried through the full edit → re-encode → inject → live-verify cycle.
Canonical `MENUDAT.BIN` is never overwritten (`asset_workspace.py` enforces
immutable-source semantics).

## 7. PROGDAT Current State

`DAT/SINKOU/PROGDAT.BIN;1` (69,663 bytes) contains 15 compressed TIM streams
in 3 groups of 5 vertical strips each:

| Group | Blocks | Format | Composite | Dimensions | Runtime proof | Edit proof | Exact-size rule | Unresolved role |
|---:|---|---|---|---|---|---|---|---|
| 0 | 0-4 | 8bpp indexed | Classroom main-menu background | 320×240 (5×64×240 strips) | LIVE_VERIFIED (visible in two VRAM framebuffer regions, `(0,0)-(319,239)` and `(0,256)-(319,495)`) | LIVE_VERIFIED (white square + multi-strip text, both survive Hard Reset) | Confirmed and enforced (§3) | None — this group's role is fully explained |
| 1 | 5-9 | 4bpp indexed | High-contrast scene mask/layer | 320×240 (same strip geometry) | NOT PROVEN | NOT EDITED LIVE | Not separately tested | Exact runtime consumer/purpose unknown; **do not describe as a "menu-button layer"** — the actual menu-label sprites live in `MENUDAT.BIN`, not here (explicitly corrected in `IMAGE_ASSET_STATUS.md` §4) |
| 2 | 10-14 | 16bpp direct | Desk/device ("Spoils" table) scene | 320×240 (same strip geometry) | Referenced by `runtime.page.2` (`progdat.group2` is part of the live-detected Photos-page composition) — this is composition-level runtime evidence, weaker than a per-primitive GPU correlation | NOT EDITED LIVE | Not separately tested | Visually reconstructed and offline-confirmed as a coherent image; runtime consumer beyond page-composition membership not traced |

The main-menu classroom background is explicitly and repeatedly confirmed to
be **ordinary compressed TIM content, not SDB**: no `SDB2.x`/`MS` header,
no animation frame count, no tile/delta graph exists for it
(`SDB_MAIN_MENU_ASSET_REPORT.md` §"SDB fields that do not apply",
`IMAGE_ASSET_STATUS.md` §8). This was checked directly against the decoded
stream structure, not assumed.

## 8. Asset Browser / Asset Inspector

| Piece | Status |
|---|---|
| Cards/thumbnails | IMPLEMENTED — individual live-decoded thumbnails for all 32 MENUDAT blocks |
| Semantic labels | IMPLEMENTED for registry-known blocks; stable unknown IDs elsewhere |
| Metadata (offset, sizes, dims, format) | IMPLEMENTED |
| Direct selection (click → exact block) | IMPLEMENTED |
| CLUT display/edit | IMPLEMENTED — raw BGR555/STP values, per-index usage counts, value-based (not hard-coded-index) transparency |
| Palette usage counts | IMPLEMENTED |
| Indexed pixel editing | IMPLEMENTED (4bpp/8bpp); 16bpp direct explicitly NOT editable |
| PNG export | IMPLEMENTED |
| PNG import/replace | IMPLEMENTED, palette-preserving, rejects unrepresentable colors rather than silently expanding the palette |
| English text overlay | IMPLEMENTED (indexed text helper reusing existing palette indices) |
| Compression budget meter | IMPLEMENTED (encoded vs. required-exact-size feedback) |
| Exact-size build | IMPLEMENTED and LIVE_VERIFIED |
| Output workspace | IMPLEMENTED (`asset_workspace.py`: source/output/preview separation, SHA-256 journal) |
| Temporary PCSX-Redux testing | IMPLEMENTED and LIVE_VERIFIED |
| Restore | IMPLEMENTED (in-memory edit restore; separate explicit PCSX temporary-patch clear) |
| Canonical-source protection | IMPLEMENTED — source registered read-only, cannot be overwritten with different bytes |

**Missing pieces** (explicitly named in `ASSET_INSPECTOR_ARCHITECTURE.md` and
`CURRENT_SYSTEM_STATUS.md`'s Asset Inspector update): a full pixel-editor
tool/undo stack, automatic GPU-driven mapping inside the Inspector itself,
a trace of the Start/Prepare selection-color mechanism, a dedicated PROGDAT
composite-editing UI, SDB/MS/GP adapters, and persistent BIN/CUE rebuilding.

## 9. Screenshot Mapper

`screen_mappings.json` / `gcrts/screen_mapping_registry.py` is explicitly and
repeatedly documented as **manual evidence/fallback, not a Runtime Asset
Detector** (`VISUAL_INSPECTOR_ARCHITECTURE.md`: "`screen_mappings.json` is
never active-state proof"; `RUNTIME_ASSET_TRACKER.md`: "remains an explicit
manual fallback, not runtime evidence"). It stores `ScreenContext`-scoped
manual rectangles (currently one context, `twilight.main_menu`, with two
`LIVE_VERIFIED` objects: Start at `65,200,100,24` and Prepare at
`160,200,100,24`), and enforces that a lower-confidence mapping cannot
replace or delete a `LIVE_VERIFIED` one.

**Known failure mode, explicitly documented**: a saved rectangle persists in
the registry regardless of whether the underlying runtime asset is currently
being drawn, still loaded, or has been replaced by something else on screen.
This is exactly why `VISUAL_INSPECTOR_ARCHITECTURE.md` places manual mapping
below runtime provenance and VRAM/GPU correlation in its resolution priority
order, and why the Runtime Asset Tracker's own documentation frames its
introduction as a "pivot" away from treating screenshot mapping as ground
truth (`CURRENT_SYSTEM_STATUS.md`, "2026-08-09 Runtime Asset Tracker pivot").

## 10. Runtime Asset Detector/Tracker

This exists in code today (`gcrts/runtime_asset_tracker.py`,
`runtime_content.py`, `asset_fingerprint.py`, `vram_asset_detector.py`,
`gpu_asset_correlation.py`, `psx_ordering_table.py`,
`runtime_visual_provider.py`), and is not merely a design document.

Chain status:

| Link | Status |
|---|---|
| Disc/Archive → Entry (which file/block an asset comes from) | IMPLEMENTED (registry-level, static) |
| Entry → Decode (compressed stream → pixels) | IMPLEMENTED (offline; live decompressed-pointer capture not achieved — see below) |
| Decode → RAM (`LOADED`/`DECOMPRESSED` states) | DESIGNED_ONLY — the state machine models these states, but no live transport captures the actual compressed-source/decompressed-destination RAM pointers or a decode event in progress. Explicitly named as still-open in both `GCRTS_COMPLETE_WORK_SUMMARY_HE.md` and `RUNTIME_ASSET_TRACKER.md`. |
| RAM → VRAM Upload (`UPLOADED_TO_VRAM`) | PARTIAL — VRAM residency is detected via exact packed-TIM-row matching (`vram_asset_detector.py`) for known assets, but this is a snapshot match, not an observed upload *event*; no upload call site is traced. |
| VRAM → GPU Draw (`DRAWN_THIS_FRAME`) | LIVE_VERIFIED for exactly one asset (MENUDAT block 9, on the Photos page) via exact OT-root parsing + primitive UV/TPAGE → VRAM-rectangle intersection (`gpu_asset_correlation.py`, `psx_ordering_table.py`). This is real primitive-level correlation, not inference. |
| GPU Draw → Screen Bounds | LIVE_VERIFIED for the same one asset: `(40,24,64,32)` screen bounds derived from two double-buffered `POLY_GT4` packets. |

**Explicit answer to the audit's question**: *Can GCRTS today know that
MENUDAT block 9 is actually being drawn in the current frame?* **Yes, but
only when the loaded code passes byte-for-byte validation against the known
`PROG.EXE` GPU-submit routine at `0x80049630`, and only by re-running the
external RAM/VRAM/OT snapshot-and-parse pipeline** (there is no continuous
live "is it drawn right now" query — it is a point-in-time scan). For every
*other* asset in the registry (all 31 remaining MENUDAT blocks and all 15
PROGDAT streams), the same mechanism is architecturally available but has
not been exercised or proven — the missing link is not code, it is
per-asset verification work: confirming each asset's real VRAM upload
signature and finding a primitive that references it, one at a time, the
way block 9 was found.

## 11. VRAM/GPU Tooling

- **VRAM capture**: LIVE_VERIFIED (`GET /api/v1/gpu/vram/raw`, full 1MiB
  capture; `vram_original.raw` on disk with a recorded SHA-256).
- **VRAM writes**: LIVE_VERIFIED for research purposes
  (`POST /api/v1/gpu/vram/raw` partial update), but proven to be
  frame-transient (a direct write is redrawn-over within one frame) — this
  is exactly why the asset-level (compressed-file) edit route was adopted
  instead of framebuffer poking.
- **LoadImage/upload tracking**: NOT achieved. Multiple attempts (tracing
  GPU DMA MADR writes at `0x8007a184`, watching for new addresses at scene
  transitions) found the routine per-frame OT/primitive DMA cycle
  (8 repeating addresses) but never caught an actual bulk texture upload
  event; leading hypothesis is that backgrounds are pre-loaded and scene
  transitions only switch references — an inference, not a completed trace.
- **Upload provenance / VRAM overwrite detection**: IMPLEMENTED at the model
  level (`VramRegion.overlaps`, generation counters in
  `runtime_content.py`), LIVE_VERIFIED for the one case where block 9 was
  shown to remain VRAM-resident-but-undrawn after leaving the Photos page.
- **CLUT/TPAGE/UV parsing**: IMPLEMENTED and LIVE_VERIFIED
  (`psx_ordering_table.py` decodes flat/Gouraud textured triangles and
  quads from real RAM dumps).
- **Ordering Table / DrawOTag**: IMPLEMENTED and LIVE_VERIFIED for both
  tracks independently — Renderer 1's OT-splice proof (`RENDERER_LIVE_PROOF.md`
  §21) and the GCRTS track's OT-root parsing (`psx_ordering_table.py`,
  `GPU_ASSET_CORRELATION.md`) — but these two OT investigations have **not
  been cross-checked against each other** (see §31).
- **Primitive-to-asset correlation**: LIVE_VERIFIED for one asset (§10).
- **Research vs. product tooling**: the honest split is that VRAM capture,
  OT parsing, and GPU correlation are real, tested, reusable library code
  (`gcrts/*.py`, unit-tested), while the *live capture protocol itself*
  (breakpoint sequencing, Lua scripting) is explicitly research/debug-only
  and has an established failure mode: **persistent Lua breakpoints on GPU
  DMA writes or execution eventually crash this PCSX-Redux build**,
  independently discovered and confirmed by both tracks this session. The
  production path is therefore restricted to read-only external RAM/VRAM
  snapshots taken between game frames, never in-process hooks.

## 12. Runtime Text

### Renderer 1

| Step | Status |
|---|---|
| Script/Layout → position records | LIVE_VERIFIED manually (host reads/writes the live 14-byte records); no automatic mapping from active `ScriptUnit`/line to record exists |
| Position record (`base 0x800A2AD4 + i*0x0E`, X `+0x8`, Y `+0xA`) | LIVE_VERIFIED, stable across scenes and one full process relaunch in the tested overlay |
| GTE quad builder | NOT part of Renderer 1 — that belongs to Renderer 2 (see below); Renderer 1 uses plain scalar `lhu`/`sh` stores, confirmed distinct in a second (Chapter 0) overlay too |
| POLY_FT4 construction | LIVE_VERIFIED — 40-byte primitives in two alternating double-buffered destinations, each holding two 14-slot line blocks |
| addPrim | LIVE_VERIFIED + STATIC_CONFIRMED (`0x800774B4`, links by reference not copy) |
| OT | LIVE_VERIFIED (direction proven newest-first; one-node splice test performed and correctly reverted) |
| DrawOTag | STATIC_CONFIRMED (shared PS1 SDK path, addresses recorded for one overlay) |
| X control | LIVE_VERIFIED |
| Y control | LIVE_VERIFIED |
| Line movement (rigid, proportional spacing preserved) | LIVE_VERIFIED, held 8 real seconds, restored |
| Two independent lines from one CLD1 descriptor | LIVE_VERIFIED, all 24 records read back |
| Centering | LIVE_VERIFIED, but **using fallback character-count widths only** — not yet done with a real `GlyphAtlas` measurement |
| CLD1 association | LIVE_VERIFIED as a **manual, host-driven** procedure (decode CLD1 on the host, compute delta, write RAM by hand) — **not** an automatic runtime consumer; no MIPS-side code parses CLD1 |
| Profile selection | BLOCKED — zero named executable profiles are truly verified; the live base address is confirmed stable but tied to an "unidentified" overlay, not a named `.EXE` |
| Runtime hookup (automatic) | NOT_IMPLEMENTED — this is the single largest gap; see §9 of `RENDERER_SYSTEM_STATUS.md` for the 14-point list of what an automatic dispatcher would still need to do |
| Glyph widths | PARTIAL — `GlyphAtlas` width lookup is implemented and static-confirmed host-side, but was not used in the live centering proof |
| Safe line count | Lines 1-2 proven; lines 3-4 explicitly **not safe** — the naive "next slot" guess (`char23_addr + 0x28`) turned out to be the active continue/wait icon's primitive, not free space |

**Structurally solved vs. fully automated — kept separate as required**: the
mechanism that moves pixels is proven (structural). Nothing in the
repository automatically decides which descriptor applies to which
currently-displayed line, or writes it at the right moment, during normal
gameplay (automation). Every demonstrated result in this document required
a human operator driving GDB/PCSX-Redux by hand.

### Renderer 2

A structurally distinct GTE `RTPT`/`RTPS` quad-builder path
(`0x8007B224` in the tested overlay, called from `0x8004500C`). **Confirmed
different front end from Renderer 1**, not just "another caller" — it stages
vertices through the GTE coprocessor rather than plain scalar copies.
**LIVE VERIFIED exactly once**: one breakpoint hit during an atmospheric
narration sequence ("Hanako-san" urban legend). Immediately after that hit,
re-validating the three known chain addresses showed they had already
drifted (overlay swap), and the hit was not reproduced despite further
attempts. Its source records, callers, content coverage, and full
chain-to-screen are **entirely unmapped**. `RENDERER_SYSTEM_STATUS.md`
explicitly states the two-renderer model is a working map of two proven
front ends, **not a complete taxonomy** — system prompts, status overlays,
independent speaker-label objects, non-A/B/C menus, and chapter titles
remain unclassified, and the repository does not justify naming a
"Renderer 3" yet. An earlier claim that photo-inset dialogue and the A/B/C
choice UI used Renderer 2 is **STALE**: later evidence showed both actually
use Renderer 1, and the earlier zero-hit result was a false negative caused
by testing settled (no-longer-redrawn) text.

## 13. CLD1/Layout Descriptor

| Link | Status |
|---|---|
| Editor/Layout → CLD1 descriptor | IMPLEMENTED, golden/round-trip tested (`layout_descriptor.py`) |
| CLD1 → runtime lookup | NOT_IMPLEMENTED — `find_descriptor_for(a0)` is a fixed diagnostic pointer slot proven only for a canary/marker stub, not a real per-unit lookup |
| Runtime lookup → position data | N/A (no real lookup exists to feed this) |
| Host-decoded position data → Renderer (manual) | LIVE_VERIFIED — this is the actual proven chain: decode CLD1 on the host, take its resolved X/Y, write it directly into the live 14-byte record |
| Renderer → visible screen result | LIVE_VERIFIED (one line, two lines, centering) |

**Explicitly not fully automated**: every step from "CLD1 bytes exist in
RAM" to "a pixel changed" required a human-driven debugger write in this
session's proof. `RENDERER_SYSTEM_STATUS.md` §4 states this precisely:
"Automatic runtime integration works: no." The current checked-in
`mips_patch_profiles.json` doesn't even have a configured
`pointer_slot_addr`/`descriptor_region_addr` for its one live-positive
profile — so there is presently no reusable injection target at all, only a
proven-possible mechanism.

## 14. Script Translation Pipeline

The **only actually-live-rendering pipeline** in the whole project is the
pre-existing HOST_FITTED chain (predates this session, unchanged by it):

```
extract_live_script_units() -> EditorState.load_units()
  -> edit/resolve/fit (editor_cli, font_workbench, text_fitting)
  -> check_layout() (layout_validation)
  -> inject_unit_guarded()/inject_all_live() (guarded_injection -> live_injection -> script_encoder)
  -> EditorState.record_injection() / save_session()
```

- **Live extraction**: IMPLEMENTED (`live_extract.py`, from
  `0x801FE800` in the tested profile).
- **Disc extraction (`source="disk"`)**: NOT_IMPLEMENTED — `script_unit.py`'s
  disk-source path remains a stub; the external toolkit's `linkdec.py` was
  run and independently verified (190 coherent paragraphs decoded from the
  real `K0LINK.CDB`) but has not been ported into `gcrts` proper.
- **Decoder/encoder**: IMPLEMENTED (`script_decoder.py`/`script_encoder.py`);
  GCRTS's own control-code table is explicitly documented as *less complete*
  than the external toolkit's `linkdec.py` table.
- **Control-code preservation**: IMPLEMENTED (`control_policy.py`,
  `control_position_risk.py`, `control_code_index.py`).
- **ScriptUnit / editable script**: IMPLEMENTED and tested.
- **Japanese/English**: Japanese renders via existing game glyphs; English
  support exists through HOST_FITTED text-fitting and live font injection,
  but is session-only (not persisted to disc).
- **Fitting / layout constraints**: IMPLEMENTED (`text_fitting.py`,
  `layout_validation.py`, `boundary_validation.py`), largely reusable
  planning logic with game-specific constants.
- **HOST_FITTED mode**: this is the actual usable, live-rendering workflow
  today.
- **CUSTOM_ENGINE render mode**: EXPERIMENTAL — a data tag only
  (`render_mode.py`); selecting it records intent but nothing in the
  running game consumes it. HOST_FITTED remains what actually renders.
- **Injection / validation**: IMPLEMENTED and LIVE_VERIFIED for the
  HOST_FITTED path specifically (this predates today and was explicitly
  named in `BASELINE_REPORT.md` as the "must remain unchanged" set —
  nothing in today's work touched it).

**Actual usable workflow today**: edit dialogue text through the
HOST_FITTED editor/CLI pipeline for one verified profile; this is real and
working. A custom-positioned/custom-rendered pipeline (CLD1-driven) is
proven possible manually but not usable as a workflow without a human
operator running a debugger.

## 15. Font System

- **KFONT decode**: OFFLINE_VERIFIED independently twice — once by this
  project's own earlier static analysis (directory structure confirmed) and
  once, this session, by actually running the external toolkit's
  `fontdec.py`/`fontlib.py` against the real extracted `KFONT.CDB`, producing
  a correct, legible atlas PNG.
- **Atlas / glyph mapping**: IMPLEMENTED (`glyph_atlas.py`,
  `glyph_char_map.py`), tested against a deterministic fake atlas — **the
  real glyph-bitmap resource blob has never been captured live and wired
  into the editor's own preview path**; `EditorCLI.do_layout_render`
  currently renders every character as a missing-glyph marker against the
  real game, by explicit no-silent-fallback design.
- **Font extension**: IMPLEMENTED (`font_extension.py`, `font_workbench.py`),
  unit-tested; injecting a genuinely new glyph bitmap into a live session
  and confirming it renders on screen has **not** been done.
- **Palette**: handled within TIM/CLUT plumbing generically; no
  font-specific palette issue is separately flagged.
- **Real widths in the editor**: **Partially yes.** `GlyphAtlas` width
  lookup is implemented and static-confirmed, but the one live centering
  proof this session used fallback character-count widths (`8px`/`16px`),
  not measured glyph bitmaps — so the answer to "can the editor use actual
  glyph widths?" is *host-side code exists; not yet exercised live*.
- **Can GCRTS add new glyphs?** Code exists (`font_extension.py`) and is
  unit-tested offline; **no new glyph has been proven rendering in-game**
  this session or documented as proven in any prior session's live evidence.

## 16. Unified Visual Content Architecture

`gcrts/runtime_content.py`'s `CurrentFrameContent` dataclass is the closest
thing to this model today:
`(active_assets, runtime_text, movies, audio_events, unknown_primitives,
page_id)`. **Current vs. planned, explicitly**:

- `active_assets` (→ VisualAsset): IMPLEMENTED, LIVE_VERIFIED for one asset.
- `runtime_text` (→ RuntimeText): field exists, typed as `tuple[Any, ...]` —
  no evidence of it being populated by a live pipeline; Renderer 1/2 data
  lives in separate research documents, not wired into this dataclass.
- `movies`: field exists, typed `tuple[Any, ...] = ()` — **inert
  placeholder, no producer anywhere**.
- `audio_events`: same — **inert placeholder, no producer anywhere**.
- `unknown_primitives`: field exists; whether anything populates it with
  real unclassified primitives was not confirmed in this audit.
- `page_id`: IMPLEMENTED and LIVE_VERIFIED (`runtime_pages.py`).

The long-term model ("select something happening → identify what it is →
open the right inspector") is **partially real** for one narrow case: a
Visual Inspector click on a runtime-drawn asset routes to the correct Asset
Inspector block (`RENDERER_ASSET_INTEGRATION.md`'s dispatch boundary). It is
not real for runtime text (Renderer 1 objects require a validated profile
and route to a "Text/Layout Inspector" that is more contract than
implementation), and not real at all for movie/audio, which have zero
producers.

## 17. Global Selection

`ProjectSelection`/`FileProjectSelection` (`gcrts/project_selection.py`,
`project_selection.json`) is real and cross-process: selecting an asset in
one tool (e.g. Visual Inspector) writes the canonical asset ID to a shared
JSON file; the Asset Inspector process can read it back. Verified by direct
inspection of `project_selection.json` (currently holds
`{"asset_id": "main_menu.prepare", "source": "visual_inspector", ...}`).
Asset Browser cards display `[DRAWN]` badges sourced from the runtime
provider. **Current status**: synchronized for the two Inspector UIs
specifically; not demonstrated for "text/renderer tools" or "runtime/GPU
views" as independent participants — those are described in docs as future
integration, not shown wired into the selection bus in this audit.

## 18. User-Controlled Pages/Scenes

This is a real, working, and — importantly — **already correctly
separated** mechanism, which is worth stating plainly since the audit
brief specifically warns against hard-coded scene names: `runtime_pages.py`
does **not** label anything "Main Menu" or "Photos Menu." It stores
composition-based IDs (`runtime.page.1`, `runtime.page.2`) with a `name:
null` field and a `status: "CANDIDATE"` field, explicitly leaving naming and
confirmation to a human. `RuntimePageDetector` uses set-similarity over
active asset-ID compositions to decide whether to reuse an existing
candidate or create a new one — verified live: leaving Main Menu for Photos
created page 2; returning to Main Menu re-matched page 1 (observation count
now 1687, vs. page 2's 41) rather than creating a duplicate.

**Runtime Truth vs. User Organization**: currently, "Runtime Truth" (what
composition is active) and "User Organization" (a confirmed, named page) are
already separate fields in the same record rather than separate systems —
`status` and `name` are the not-yet-exercised user-control hooks. **No
current code path lets a user promote a candidate to a named/confirmed page,
rename it, merge it, or reject it** — `RUNTIME_PAGE_DISCOVERY.md` states
this directly: "naming, confirmation and merge controls remain pending."
So: the principle is not violated (nothing is silently declared "the Main
Menu"), but the user-control half of the promised workflow does not exist
yet — it is a data model with the right shape and no UI to exercise it.

## 19. Runtime Snapshot/Pause Inspection

No dedicated "pause and freeze one coherent snapshot" feature exists as a
named capability. What exists that could compose into one:

- PCSX-Redux pause/resume via its debugger/GDB stub: LIVE used constantly
  throughout the session (implicitly, via breakpoints) but not wrapped in
  any GCRTS-side "snapshot" API.
- RAM snapshot: LIVE_VERIFIED (full-RAM reads used throughout).
- VRAM snapshot: LIVE_VERIFIED (`vram_original.raw`, full 1MiB captures).
- GPU primitives at a point in time: LIVE_VERIFIED (OT parsing off a RAM
  dump).
- Runtime text state: only via manual GDB reads of specific known records,
  not a general "read all currently displayed text" call.
- Movie/audio state: NOT_IMPLEMENTED (no producer, §21-22).
- Playback positions: NOT_IMPLEMENTED.

**Assessment**: the individual primitives needed (pause, RAM read, VRAM
read, OT parse) all exist and are proven reliable *outside* of Lua
in-process hooks. A genuine "one coherent frozen snapshot" object that
bundles frame/assets/text/VRAM/GPU/movie/audio together does not exist as
code; building it would be assembling already-proven pieces rather than
new reverse-engineering, for everything except movie/audio (which have no
underlying pieces yet).

## 20. Image Identification Roadmap

- **Ordinary TIM (4/8/16bpp)**: fully understood (decode/encode both ways,
  live round-tripped).
- **Compressed TIM stream (PROGDAT/MENUDAT codec)**: fully understood for
  this codec family specifically.
- **Composite/multi-strip TIM**: fully understood for the one proven layout
  (5×64×240 → 320×240); not generalized to other possible composite shapes.
- **SDB (any version)**: format identified only at the level of "this is
  not what PROGDAT/MENUDAT are" — no actual SDB asset has been located,
  decoded, or even confirmed to exist in this game's data during this
  session. Unknown.
- **MS, GP**: unknown — no format sample has been located or analyzed.
- **Photo/scene formats beyond the two studied files**: partially
  understood only insofar as PROGDAT groups 1 and 2 are visually
  reconstructed; their runtime role is unknown.
- **Animation formats**: unknown — no evidence of any animated-image
  format anywhere in the repository.

## 21. Movie/Video Audit

Searched `gcrts/*.py`, all Markdown docs, and the external toolkit for
`MDEC`, `.STR`, XA video, movie/cutscene/frame-decode/playback/timing
terminology. **Result: nothing found anywhere except one inert data
field.** `gcrts/runtime_content.py`'s `CurrentFrameContent.movies:
tuple[Any, ...] = ()` is a placeholder with no producer, no `Movie` type
definition, and no reference to it from any other module beyond its own
declaration. No `SDB` asset has been confirmed to exist at all (§20), so
the audit brief's caution "do not assume SDB == movie" is moot here — there
is no confirmed SDB anything yet, movie or otherwise.

**Direct answers**: Can GCRTS currently identify that a movie is playing?
**No.** Identify the source movie file? **No.** Know the current movie
time/frame? **No.** All three are `NOT_IMPLEMENTED`, and no partial
groundwork (no MDEC register tracing, no STR sector-detection code) exists
to build on.

## 22. Audio Audit

Searched for `XA`, `SPU`, voice/music/SFX/sound-ID/playback terminology.
**Result: text labels only, no runtime tracking.** `asset_registry.py`
contains 6 MENUDAT entries semantically named as sound labels ("Voice in
Sculpture Hall," "Voice at Koube Bridge," etc.) — these are **image assets**
(TIM sprites showing Japanese sound-menu labels), not audio files or audio
playback tracking. `script_decoder.py` has one decoded control-code family,
`sound_or_voice_cue` (`0x0800`), and `control_policy.py` classifies it as
`_UNRESOLVED_NAMED_ONLY` — i.e., the control code's existence and general
shape are known, but its parameter meaning, target sound asset, or playback
semantics are not resolved. `runtime_content.py`'s `audio_events` field is
the same kind of inert placeholder as `movies`.

The external toolkit's decoded control-code table (referenced in
`CURRENT_SYSTEM_STATUS.md` §0) includes an `XA`/`AWAIT` pair of codes with
names, giving a plausible richer meaning than GCRTS's own table, but this
has not been cross-verified live and is reference material, not integrated.

**Direct answers**: Can GCRTS currently know which voice clip is playing?
**No.** How far into that clip playback currently is? **No.** "Audio file
identified" (a sound-label *image* exists, and one *control code* is known
to exist) is present; "runtime audio event tracked" (an actual playing clip,
its ID, its position) is **not** — these two are cleanly separate today,
and only the first has any evidence.

## 23. Future Audio Subtitle Workflow (assessment only — not implemented)

Prerequisite gap analysis against the desired flow (voice begins → runtime
event identified → canonical Audio Asset ID → playback timer → pause →
Audio Inspector → extract/listen → cue → continue → stop → save cue):

| Prerequisite | Current state |
|---|---|
| Runtime voice event identification | NOT_IMPLEMENTED — no SPU/XA playback-start detection exists |
| Canonical Audio Asset ID | NOT_IMPLEMENTED — no audio entries exist in the asset registry (only image labels *about* sounds) |
| Playback timer | NOT_IMPLEMENTED |
| Audio Inspector | NOT_IMPLEMENTED (no equivalent of the Asset/Visual Inspector exists for audio) |
| Extract/listen | NOT_IMPLEMENTED — no audio extraction code found anywhere |
| Cue creation relative to voice_asset_id + offset | NOT_IMPLEMENTED — no subtitle data model exists at all (§25) |

This entire workflow has **zero built infrastructure** to extend from. The
one relevant lead is the unresolved `sound_or_voice_cue` (`0x0800`) script
control code — understanding what it actually triggers (which SPU
voice/XA stream, with what ID) would be the necessary first
reverse-engineering step before any engineering work here is possible.

## 24. Future Movie Subtitle Workflow (assessment only — not implemented)

Same conclusion, more severe: movies have **no** identified format, no
control-code lead (unlike audio's `sound_or_voice_cue`), and no data field
beyond the same inert `movies` tuple. Every prerequisite in the desired flow
(movie detected → stream identified → timestamp/frame known → pause → cue →
preview) is `NOT_IMPLEMENTED`, and unlike audio, there is not even a partial
reverse-engineering foothold to build from yet — the first step here would
be locating whether this game has movie assets (an MDEC/`.STR` stream) at
all, which has not been attempted.

## 25. Subtitle Data Model

**Does not exist.** No `Cue`/`Subtitle`/similar type was found anywhere in
`gcrts/*.py`. `Translation View` (§ below, `TRANSLATION_VIEW.md`) has a
per-text-object status enum (`ORIGINAL`, `TRANSLATED`, `PARTIAL`,
`NEEDS_REVIEW`, `NOT_EDITABLE`, `UNKNOWN`) that is conceptually adjacent but
attaches to a screen *object* (a rasterized label, a runtime text region),
not to a timed audio/movie cue. Nothing in the repository models
`cue_id`/`source`/`start_offset`/`end_offset`/`speaker`/`position`/`style`
for time-based media. This is confirmed absent, not just undocumented — no
implementation to audit here. Per instructions, not implemented as part of
this audit.

## 26. Unknown Content

The architecture handles this reasonably well for what exists today:
`ScreenObjectType` includes explicit `UNKNOWN_TEXT`/candidate/unknown
classifications rather than forcing a guess (`SCREEN_OBJECT_MODEL.md`), and
`AssetDescriptor` supports recording a recognized-but-unsupported format tag
without inventing semantics (`ASSET_DESCRIPTOR_SPEC.md`: "meanings are not
invented" for non-registry blocks). `RuntimeConfidence.CANDIDATE` and
`RuntimeAssetState.UNKNOWN` exist as first-class states, and
`unknown_primitives` is a field on `CurrentFrameContent`. **However**,
`UnknownVisualAsset`/`UnknownRuntimeText`/`UnknownMovie`/`UnknownAudio`/
`UnknownGpuPrimitive` as the audit brief's specific named future categories
do **not** exist as distinct types — today's "unknown" handling is a status
enum value attached to the same object types, not a parallel type hierarchy
that would let unknown content carry different fields than known content.
For movie/audio specifically, since no producer exists at all (§21-22),
there is nothing yet to retain as "unknown" — the gap there is upstream of
this question.

## 27. External Twilight Syndrome Toolkit

Located at `קיבצי דמה/twilight_syndrome-main/`. Confirmed NOT part of
`gcrts`; a separate, complete, pre-existing fan-translation toolkit found on
disk, apparently Chinese-authored tooling for this exact game.

| Capability | Classification |
|---|---|
| Script control-code table (`linkdec.py`) | USED_AS_REFERENCE — cross-validated (independent `PRESS`/`0x8500` match), explicitly documented as *more complete* than GCRTS's own table; not ported |
| Per-executable table addresses (`cap0-4.ini`, `capX.ini`) | USED_AS_REFERENCE — `cap0.ini`/`cap1.ini` reviewed and cross-checked; `cap2-4.ini`/`capX.ini` present but not individually reviewed this session per prior notes; NOT_YET_REVIEWED for behavioral validation beyond presence |
| Font glyph decode (`fontlib.py`/`fontdec.py`) | USED_AS_REFERENCE — actually run against real `KFONT.CDB`, produced a correct atlas; NOT ported into `gcrts.glyph_atlas`/`font_extension` |
| CDB inner codec (`rle.py`) | USED_AS_REFERENCE for cross-validation only — GCRTS's own `cdb_codec.py` is independently implemented and is the one actually used |
| CDB outer container (`cdb.py`) | USED_AS_REFERENCE — matches GCRTS's own understanding; GCRTS does not import this code |
| Static binary patcher (`patch.py`) | NOT_INTEGRATED — offline/permanent approach, fundamentally different from GCRTS's live-injection method; not ported |
| `sinkou.py`, `fontdb.py`, `mkfont.py`, `merge.py`, `build.py`, `linkcfg.py`, `dec.c` | NOT_YET_REVIEWED (per `CURRENT_SYSTEM_STATUS.md`'s own §0 note; note the filename coincidence with `DAT/SINKOU/` — this file has **not** been checked for relevance to the PROGDAT/MENUDAT `SINKOU` discovery this session, a real open thread) |

No wholesale porting of this toolkit's control table, CDB pipeline, font
atlas pipeline, or patch/rebuild system into `gcrts` has occurred. It
remains reference-only. Its capabilities (font/script decode, executable
table addresses) are **not** GCRTS-native capabilities and must not be
reported as such.

## 28. PCSX-Redux Integration

- **GDB**: LIVE_VERIFIED — the primary tool throughout both tracks
  (breakpoints, watchpoints, register reads, memory read/write).
- **Breakpoints/watchpoints**: LIVE_VERIFIED for software breakpoints
  (`Z0`) and write watchpoints (`Z2`); one reproducible unexplained
  discrepancy where a `Z0` at an exact instruction never fired while a `Z2`
  on its target address fired reliably (noted, not resolved).
  **Persistent execution/I/O-write breakpoints used as always-on hooks are
  RULED_OUT** — both variants eventually crash this PCSX-Redux build,
  independently confirmed by both tracks.
- **Frame synchronization / emulator pause-resume**: manual, breakpoint- and
  script-driven; no formal "wait for next frame" API is wrapped.
- **Runtime profile detection**: IMPLEMENTED as a framework
  (`mips_patch_profile.py`, `mips_jal_decoder.py`) but with **zero named
  executable profiles truly verified** — all entries in
  `mips_patch_profiles.json` (`CAP0-4.EXE`, `CAPX.EXE`, `MNINO/MPRO/MRIKA/
  MYOKO.EXE`) are `status: "unverified"` with null addresses. The GCRTS
  track's own profile validation (byte-for-byte check of
  `0x80049630` against `PROG.EXE`) is a real, working, fail-closed
  mechanism, but "`PROG.EXE`" itself is not one of the named profiles in
  the JSON registry — it is validated ad hoc in code.
- **Web API**: LIVE_VERIFIED and is the actual production transport —
  full RAM read, full VRAM read, partial VRAM write (research only),
  temporary CD-file patch, patch-clear.
- **VRAM capture/write**: covered above (§11).
- **CD patch**: LIVE_VERIFIED, temporary only.
- **Screenshot capture**: LIVE_VERIFIED, but with a documented, fixed bug
  history — an earlier `BitBlt`-based capture silently returned stale
  frames for this GPU-accelerated window; fixed by switching to
  `PrintWindow(..., PW_RENDERFULLCONTENT)`. Any conclusion drawn from a
  screenshot captured before this fix should be treated with suspicion.
- **Hard reset**: LIVE_VERIFIED as the persistence test for asset edits.
- **Patch clearing**: LIVE_VERIFIED (`POST /api/v1/cd/ppf?function=clear`).
- **Lua integration**: explicitly abandoned for production use.
  `gcrts_runtime_probe.lua` is a disabled stub; `pcsx.lua` is 2 bytes. Two
  independent investigations this session reached the same conclusion
  separately.

**Separation of stable automation vs. manual procedure**: the Web API
transport (RAM/VRAM read, CD patch) is stable, repeatable automation. The
GDB breakpoint-driven live-editing procedures that produced the Renderer 1
proof are manual debugger procedures, run by a human operator following a
documented recipe — not automated, not currently scriptable into a
one-command reproduction (the scripts that did it, e.g. `scratchpad/
final_precise_trial_v2.py`, are not present in the tracked repository — §1).

## 29. Runtime Profile/Overlay Drift

Extensively documented and directly relevant to trusting any address in
this repository. Confirmed drift sources: different chapters/overlays
loading different code at the same conceptual function; savestate loads
replacing overlay RAM outright; layout drift observed *within* a single
continuous session at least three times, not only across quickloads. The
`mips_jal_decoder.py` module was built specifically to stop
hand-computed-JAL-arithmetic mistakes that cost real investigation time.

**Can the system automatically know which runtime profile is valid?**
**Partially, and only where it was built to fail closed.** The GCRTS
runtime tracker validates the loaded GPU-submit routine byte-for-byte
against `PROG.EXE` before trusting any OT root, and returns zero live
objects rather than guessing on mismatch — this is a real, working,
automatic check for that one specific code region. The Renderer 1 track has
no equivalent automatic check: its record base/writer addresses are used
directly without a wrapping fingerprint validation step in any live-run
tooling currently in the tracked repository (the validation script that did
this, `scratchpad/validate_profile.py`, is referenced but not present).

## 30. Persistent Build

- **Output working files**: IMPLEMENTED (`asset_workspace.py` source/
  output/preview separation with hash journal).
- **Temporary emulator patch**: LIVE_VERIFIED, the actual proven mechanism
  for every live result in this session.
- **Physical BIN/CUE modification**: NOT_IMPLEMENTED anywhere in `gcrts`.
- **CDB resize / ISO relocation**: NOT_IMPLEMENTED; the exact-size
  constraint (§3) exists specifically *because* offset relocation is not
  attempted — every proven edit stays within its original byte budget to
  avoid needing it.
- **MODE2/2352 rebuild**: NOT_IMPLEMENTED (only read/de-interleave exists).
- **PPF**: only a clear/rollback endpoint is used, not PPF patch authoring.
- **Real hardware**: UNKNOWN, untested.

**Strict safety assessment**: nothing in this repository is safe to call
"persistent" in the sense of surviving outside the current PCSX-Redux
session's temporary CD-patch state plus a Hard Reset. All proven
persistence is emulator-session-level (survives Hard Reset within that
session), not disc-level (survives ejecting/reloading a rebuilt image) or
hardware-level.

## 31. Stale / Superseded Findings

| Old conclusion | Current conclusion | Why it changed | Evidence |
|---|---|---|---|
| The screen-position writer for dialogue text is unknown; Phase 9 is blocked on finding it. | Known and live-proven for one overlay (14-byte record, `+0x8`/`+0xA`). Automatic integration is now the blocker, not discovery. | Sections 10-14 of `RENDERER_LIVE_PROOF.md`, produced/finalized in the catch-up window. | `RENDERER_LIVE_PROOF.md`, `CURRENT_SYSTEM_STATUS.md` top section. |
| Record `+8`/`+0xA` doesn't affect visible output (RULED OUT earlier this session). | The earlier tests edited a write-only *destination copy*, or used a breakpoint mis-timed relative to the X load. The true source (`$s1`) does drive visible pixels. | Disassembly-level re-investigation found the actual write-only-copy relationship. | `RENDERER_LIVE_PROOF.md` §10, §12. |
| Photo-inset dialogue and the A/B/C choice UI use a second, distinct renderer. | They use Renderer 1. The zero-hit test happened on settled (no-longer-redrawn) text. | A later live session caught the same content on the proven writer and produced visible edits. | `RENDERER_LIVE_PROOF.md` §10-12; `RENDERER_SYSTEM_STATUS.md` §13. |
| Background/VRAM image editing is blocked (raw VRAM access confirmed unavailable via GDB/Lua). | Correct for that specific route only. A separate compressed-file-level route (extract → decode → edit PNG → exact-size re-encode → temporary CD patch) is proven, live, surviving Hard Reset. | The GCRTS asset track, built in the same session immediately after the renderer track. | `CURRENT_SYSTEM_STATUS.md` "2026-08-09 correction"; `IMAGE_ASSET_STATUS.md`. |
| MENUDAT blocks 7/8 are identified/decoded but not yet edited or reinjected. | Edited, re-encoded, live-injected, and visually confirmed, including surviving Hard Reset. | Work continued the same afternoon after `IMAGE_ASSET_STATUS.md` was written. | `MENUDAT_ASSET_CATALOG.md`, `CURRENT_SYSTEM_STATUS.md` Asset Inspector update. |
| The Screenshot Mapper (manual rectangles) is the way GCRTS knows what's on screen. | Explicitly demoted to fallback/evidence; runtime VRAM+GPU-primitive correlation is now the primary (though narrow) mechanism. | `RUNTIME_ASSET_TRACKER.md`'s "pivot," built in the same session. | `CURRENT_SYSTEM_STATUS.md` "Runtime Asset Tracker pivot" section. |
| Test suite has 43 / 279 / 282 / 294 tests. | 348 passed, 0 failed, 6 warnings (re-confirmed live for this audit). | Continued test-writing throughout the whole session, most heavily in the Asset Inspector/Runtime Tracker track (2:46 PM-5:13 PM). | Live `pytest` run performed for this audit; `CURRENT_SYSTEM_STATUS.md`, `GCRTS_COMPLETE_WORK_SUMMARY_HE.md`. |
| The GTE/RTPS path's content is entirely unidentified. | Partly stale — one atmospheric-narration use is now confirmed; broader coverage remains unknown. | One real breakpoint hit during narration, chain not traced further. | `RENDERER_LIVE_PROOF.md` §22. |
| `char23_addr + 0x28` is a free "next line" primitive slot. | Ruled out — it is the active continue/wait icon's primitive, chained into the same OT list. | Direct read-before-write check. | `RENDERER_LIVE_PROOF.md` §21. |
| Renderer 1 and the GCRTS asset track are unrelated/sequential-in-time-only findings. | They are two tracks of the *same* session with an explicit, still-open cross-check gap (OT roots vs. `addPrim`). | Timestamp reconstruction (§Phase 0/`GCRTS_CHANGES_SINCE_1200.md`) plus `CURRENT_SYSTEM_STATUS.md`'s own correction section. | `GCRTS_CHANGES_SINCE_1200.md`. |

## 32. Full Capability Matrix

| Capability | Status | Evidence | Manual/Automatic | Main blocker |
|---|---|---|---|---|
| Disc extraction (BIN/CUE, ISO9660) | LIVE_VERIFIED | `loader.py`, `iso9660.py` | Automatic | None — solid |
| CDB read | OFFLINE_VERIFIED | `cdb_codec.py` | Automatic | Indexing rule for arbitrary chunks (K0LINK) unresolved without external toolkit's `linkdec` |
| Compression (PROGDAT/MENUDAT codec) | LIVE_VERIFIED | `asset_compression.py` | Automatic | None for this codec family |
| Scripts (decode/encode/edit) | IMPLEMENTED, LIVE_VERIFIED (HOST_FITTED) | `script_decoder.py` et al. | Semi-automatic (human-edited, auto-injected) | Control-code table less complete than external toolkit |
| Control codes | PARTIAL | `control_policy.py` | N/A | `sound_or_voice_cue` and others unresolved |
| Font (decode) | OFFLINE_VERIFIED | External toolkit run against real disc | Automatic (external tool) | Not ported into `gcrts` |
| Font (extend) | EXPERIMENTAL | `font_extension.py` | Manual | No live new-glyph proof |
| Renderer 1 (position) | LIVE_VERIFIED (manual) | `RENDERER_LIVE_PROOF.md` §10-21 | Manual | No automatic dispatcher/profile |
| Renderer 2 | PARTIAL | `RENDERER_LIVE_PROOF.md` §22 | Manual, unrepeated | Overlay reproduction |
| CLD1 | IMPLEMENTED + LIVE_VERIFIED (manual apply) | `layout_descriptor.py`, live proof §16/19/20 | Manual | No runtime consumer |
| TIM (4/8/16bpp) | LIVE_VERIFIED | `asset_tim.py` | Automatic | 16bpp indexed-edit N/A by format |
| MENUDAT | LIVE_VERIFIED (2/32 edited) | `MENUDAT_ASSET_CATALOG.md` | Automatic tooling, manual per-asset decision | 30/32 blocks not yet edit-tested |
| PROGDAT | LIVE_VERIFIED (group 0 only) | `IMAGE_ASSET_STATUS.md` | Automatic tooling | Groups 1/2 role unproven |
| SDB/MS/GP | UNSUPPORTED | `IMAGE_FORMAT_ADAPTERS.md` | N/A | No sample located yet |
| Asset Browser | IMPLEMENTED | `asset_inspector_ui.py` | Automatic | Missing pixel-editor/undo |
| Asset Inspector | IMPLEMENTED, LIVE_VERIFIED | Same | Automatic | Same |
| Screenshot Mapper | IMPLEMENTED (fallback only) | `screen_mapping_registry.py` | Manual | Stale-rectangle risk by design |
| Runtime Asset Tracker | LIVE_VERIFIED (1 asset) | `runtime_asset_tracker.py`, §10 | Automatic (per-run scan) | Per-asset verification not scaled past block 9 |
| VRAM tracking | LIVE_VERIFIED | `vram_asset_detector.py` | Automatic | Upload-event tracing still open |
| GPU correlation | LIVE_VERIFIED (1 asset) | `gpu_asset_correlation.py` | Automatic | Not cross-checked against Renderer 1's own addPrim |
| Visual Inspector | IMPLEMENTED, LIVE_VERIFIED (2 assets) | `visual_inspector_ui.py` | Automatic (runtime priority) + manual fallback | Line-level Renderer 1 collection not built |
| Global selection | IMPLEMENTED, LIVE_VERIFIED (2 tools) | `project_selection.py` | Automatic | Not extended to text/renderer/GPU views |
| User pages/scenes | LIVE_VERIFIED (composition detection), DESIGNED_ONLY (user control) | `runtime_pages.py`/`.json` | Automatic detection; no user UI yet | Naming/confirm/merge controls absent |
| Runtime snapshots | PARTIAL (pieces exist, not assembled) | §19 | Manual assembly today | No unifying API |
| Movies | NOT_IMPLEMENTED | §21 | N/A | No format located |
| Audio | NOT_IMPLEMENTED (tracking); PARTIAL (image labels only) | §22 | N/A | No format/event tracing started |
| Subtitles | NOT_IMPLEMENTED | §25 | N/A | Depends on movie/audio tracking first |
| Persistent build | NOT_IMPLEMENTED | §30 | N/A | No BIN/CUE rebuild path |

## 33. Engineering vs Reverse Engineering

| Missing piece | Classification |
|---|---|
| Automatic Renderer 1 dispatcher/hook | ENGINEERING (mechanism is known; needs building) |
| Named executable profile fingerprints | REVERSE_ENGINEERING (must identify + verify each `.EXE`) |
| `find_descriptor_for()` real per-unit lookup | BOTH (needs a discovered association mechanism, then engineered) |
| Renderer 2 full trace | REVERSE_ENGINEERING |
| Lines 3-4 safe allocation | REVERSE_ENGINEERING (survey real multi-line scenes) then ENGINEERING (safe insertion) |
| Archive-load → decompress → VRAM-upload CPU trace | REVERSE_ENGINEERING |
| SDB/MS/GP format support | REVERSE_ENGINEERING first (locate a real sample) |
| PROGDAT groups 1/2 runtime role | REVERSE_ENGINEERING |
| Persistent BIN/CUE rebuild | ENGINEERING (offline external toolkit already shows feasibility) |
| Movie format/detection | REVERSE_ENGINEERING (nothing located yet) |
| Audio event tracking | REVERSE_ENGINEERING (`sound_or_voice_cue` semantics) then ENGINEERING |
| Subtitle data model | ENGINEERING (but explicitly deferred; depends on the above) |
| User page naming/confirm/merge UI | ENGINEERING (data model already correct) |
| Cross-check GCRTS OT roots vs. Renderer 1 `addPrim` | REVERSE_ENGINEERING (a few hours of directed comparison, not new discovery) |

## 34. Dependency Map

```
Disc/Container (SOLVED)
  -> Compression codec(s) (SOLVED for CDB + PROGDAT/MENUDAT families)
    -> Visual formats: TIM 4/8/16bpp (SOLVED) ; SDB/MS/GP (UNKNOWN, blocks nothing yet since unencountered)
      -> Asset system / registry (SOLVED for 32+15 known streams)
        -> Asset Inspector edit/encode/inject (SOLVED for 2/32 + 1/15 proven, tooling generalizes)
          -> Runtime detection (VRAM match + GPU correlation) (SOLVED for 1 asset; needs per-asset repetition)
            -> Visual Inspector / global selection (SOLVED for what runtime detection covers)
              -> User pages/scenes (data model SOLVED; user-control UI MISSING)
                -> Runtime snapshot assembly (pieces exist; MISSING as a unit)

Script/Control codes (MOSTLY SOLVED, external toolkit ahead of gcrts's own table)
  -> Font/glyph decode (SOLVED, not ported) -> Font extension (EXPERIMENTAL, unproven live)
  -> Renderer 1 position mechanism (SOLVED, manual)
    -> CLD1 (SOLVED as format + manual apply; MISSING as runtime consumer)
      -> Automatic Renderer 1 dispatcher (MISSING — biggest blocker in this branch)
        -> Multi-line/multi-overlay generalization (MISSING)
  -> Renderer 2 (BARELY STARTED — one hit, no chain)

Movie detection (NOT STARTED) -> Movie timing (blocked by above) -> Movie subtitles (blocked by above)
Audio event tracking (NOT STARTED, one unresolved control code as sole lead) -> Audio timing (blocked) -> Audio subtitles (blocked, also needs Subtitle Data Model which is NOT STARTED)
```

Philosophy check against actual evidence: **Detect first → Understand →
Edit → Automate** holds up well for the image/asset branch (detect
PROGDAT/MENUDAT → understand TIM/codec → edit/inject → automation is the
current frontier, i.e., scaling from 2/32 proven edits to all 32, and from 1
proven `DRAWN_THIS_FRAME` asset to general detection). It also holds for the
renderer branch (detect the writer → understand the record → edit position →
automate is explicitly the next milestone per `RENDERER_SYSTEM_STATUS.md`).
For movie/audio, there is not yet a "detect" step to build on — the
dependency chain for those two branches has not started.

## 35. Direct Answers

1. **What changed since 12:00?** See `GCRTS_CHANGES_SINCE_1200.md` in full;
   summary: Renderer 1's position mechanism was fully mapped and live-proven
   (manual), and an entirely new Asset Inspector/Visual Inspector/Runtime
   Asset Tracker system was built and partially live-verified, all in one
   continuous session.
2. **What can GCRTS fully do today (automatic, no human debugger)?**
   Extract the disc, decode/encode the CDB and PROGDAT/MENUDAT codecs,
   decode/encode/edit TIM images, edit and re-inject 2 specific MENUDAT
   blocks and 1 specific PROGDAT composite through a tested tool, detect
   that 1 specific asset is drawn this frame, and edit dialogue text through
   the HOST_FITTED live pipeline for one verified profile.
3. **What's manual-only?** Everything involving Renderer 1/2 position
   editing (requires a human running GDB by hand); any CLD1 application;
   any new named-profile onboarding; extending asset editing beyond the 3
   proven assets to the other 44.
4. **Which image types are understood / unresolved?** TIM (all bit depths)
   and the two compression codecs are understood. SDB/MS/GP are entirely
   unresolved — not even a confirmed sample exists yet.
5. **Can it determine what's drawn this frame?** Yes, for exactly one asset
   (MENUDAT block 9), through real OT/GPU-primitive correlation, contingent
   on profile validation succeeding. Not generalized to other assets yet.
6. **Can selection work reliably?** Between the two Inspector UIs, yes,
   file-backed and demonstrated. Not extended to text/renderer/GPU views.
7. **Screenshot Mapper vs. true Runtime Asset Detector gap?** The mapper is
   explicit fallback that can go stale (a rectangle survives even if the
   asset stops being drawn); the tracker is real but currently proven for
   one asset only. The gap is scale, not architecture — the mechanism to
   close it (repeat the block-9 procedure per asset) already exists.
8. **Renderer 1 capabilities/manual parts?** Can move any glyph or line to
   any position, center with fallback widths, control two lines
   independently — all live-proven, all manual. Cannot yet identify the
   active line/glyph automatically, use real measured widths live, support
   3-4 lines safely, or run without a human at the debugger.
9. **Renderer 2 knowledge?** A structurally distinct GTE quad builder,
   confirmed to exist and fire during atmospheric narration once. Source
   records, other callers, and full chain are unknown.
10. **CLD1 completeness?** Format complete and tested; manual application
    proven live (1 line, 2 lines, centering); zero automatic runtime
    consumption.
11. **Coherent paused runtime state?** All the raw pieces exist (RAM/VRAM/OT
    snapshots); no unifying "snapshot" object/API exists yet.
12. **Movie identification/timing?** Not possible; no code exists.
13. **Audio identification/voice/offset?** Not possible for playback
    tracking; one unresolved script control code (`sound_or_voice_cue`) is
    the only lead, and six *image* labels about sounds exist (not audio
    tracking).
14. **Subtitle infrastructure?** None exists.
15. **Prerequisites for audio/movie subtitles?** Movie: locate a movie
    format sample first (nothing found yet). Audio: resolve
    `sound_or_voice_cue`'s real target/parameters, then build event
    detection, then a canonical Audio Asset ID scheme, then a Subtitle Data
    Model (§25) — none of these exist.
16. **What to build next?** See §36.
17. **What to postpone?** Persistent BIN/CUE rebuild, Renderer 2 chain
    completion, lines 3-4 allocation, SDB/MS/GP support, and the entire
    movie/audio/subtitle chain — all explicitly lower priority than closing
    the automation gap on what is already proven (per §36's reasoning and
    the task brief's own stated priority order).
18-24. Covered in aggregate above and throughout §§1-31; no additional
    distinct facts remain unaddressed from the original 24-question set.

## 36. Recommended Development Order

**Primary next milestone: Build one reversible, single-profile, automatic
Renderer 1 prototype** — a host- or hook-driven mechanism that identifies
one currently-active dialogue line, resolves its CLD1 descriptor, and
writes the resulting X/Y into the live 14-byte records at the correct
lifecycle point, for exactly one fingerprinted executable/overlay,
falling back cleanly to original rendering on any validation failure.

**Follow-up milestones, in dependency order:**

1. **Fingerprint and formally register the executable(s)** used by the
   Renderer 1 prototype in `mips_patch_profiles.json`, replacing the
   current "unidentified overlay" basis with a named, byte-verified
   profile — this is a prerequisite for the prototype to be trustworthy
   beyond one debugging session.
2. **Cross-check the GCRTS track's 4 OT roots and GPU DMA trigger against
   Renderer 1's own `addPrim` (`0x800774B4`)** — cheap (a few hours of
   comparison, not new discovery), and resolves a real, flagged, unresolved
   question connecting the session's two tracks; also a natural stepping
   stone toward generalizing runtime asset detection past the single
   proven MENUDAT block 9 case.
3. **Scale runtime asset detection from 1 proven asset to the rest of the
   32+15 registry** using the same block-9 procedure — this directly
   answers the audit's own "can GCRTS know X is drawn" question for
   everything else in the registry, and is prerequisite to any believable
   "select what's on screen" experience.
4. **Wire real `GlyphAtlas` widths into the live centering/positioning
   path**, replacing the fallback character-count approximation — needed
   before CLD1 positioning can be trusted for proportional text.
5. **Only after 1-4**: begin Renderer 2's reverse-engineering track
   (reproduce narration on demand, fingerprint, trace chain) and separately
   begin the movie/audio detection groundwork (locate a movie sample;
   resolve `sound_or_voice_cue`) — these are legitimate next frontiers but
   are explicitly *not* blocking or blocked by 1-4, and per the task's own
   stated priority (visual/runtime understanding before movie/audio/
   subtitle systems), should not be started before the automation gap on
   already-proven capability is addressed.

**Why this order**: everything demonstrated this session for Renderer 1 is
structurally solved but zero-percent automated; that gap is the single
highest-leverage piece of unfinished work because closing it converts a
one-off manual debugger proof into a reusable, demonstrable feature — a
prerequisite for any credible "custom renderer" claim, and a template the
Runtime Asset Tracker's own scaling problem (item 3) can reuse. Movie and
audio work is explicitly deprioritized per the task brief's own stated
philosophy (visual/runtime understanding before movie/audio/subtitle
systems) and because, unlike every other open item, movie support currently
has literally no reverse-engineering foothold to build from.
