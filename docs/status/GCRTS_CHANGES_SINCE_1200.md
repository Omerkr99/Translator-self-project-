# GCRTS — Changes Since 12:00 on 2026-08-09

**Compiled:** 2026-08-09, catch-up/audit pass. No code was written or modified
to produce this document; it is based on reading the actual current files,
running the test suite, and checking `git status`/filesystem timestamps.

## How this was reconstructed

`git log` reports zero commits — there is no history to diff. Every file in
the repository is untracked (`git status` lists 102 top-level entries, all
`??`). So "what changed since 12:00" was reconstructed from Windows file
`LastWriteTime` across the whole tree (405 non-ignored files), cross-checked
by reading file contents (a timestamp alone is not proof of what a file
contains or supersedes).

**Key finding: almost the entire day's work is inside the "since 12:00"
window.** The earliest touched file after noon is
`.pytest_cache/v/cache/nodeids` at **12:16:05 PM**, immediately followed by
`RENDERER_LIVE_PROOF.md` at **12:16:40 PM**. The single latest file in the
repository is `runtime_pages.json` at **5:13:27 PM**, essentially the current
moment. Only save states (`SLPS00102.sstate0-8`), memory cards, a handful of
July design docs (`MASTER_RENDER_MODE_MAP.md`, `MIPS_JAL_DECODER.md`, etc.),
and the external `twilight_syndrome-main` toolkit predate the window.

This means the "seed context" framing that described the Renderer-1 live-proof
track and the GCRTS asset-editing track as two separate, differently-timed
efforts (one implicitly "today", one implicitly "earlier") is **not accurate
by timestamp**. Both happened today, in immediate succession, in the same
session:

1. **12:16 PM – ~1:34 PM**: `RENDERER_LIVE_PROOF.md` (sections 10-22) and
   `RENDERER_SYSTEM_STATUS.md` were written/finalized. This is a
   documentation/audit pass over live GDB/PCSX-Redux work (the actual live
   sessions that produced sections 1-22 evidently happened before 12:00, but
   the write-up, correction, and status-audit documents were produced in this
   window — `RENDERER_SYSTEM_STATUS.md` in particular reads as a from-scratch
   audit of the renderer track, timestamped 12:58 PM).
2. **1:13 PM – ~2:38 PM**: ad hoc image-asset research
   (`sdb_main_menu_asset/*`, `SDB_MAIN_MENU_ASSET_REPORT.md`,
   `IMAGE_ASSET_STATUS.md`) — PROGDAT/MENUDAT extraction, TIM decode,
   exact-size re-encoding, and the first live PCSX-Redux background/text
   injection.
3. **2:46 PM – 5:13 PM**: the entire `gcrts` Asset Inspector / Visual
   Inspector / Runtime Asset Tracker system was built from scratch —
   `asset_descriptor.py` through `runtime_visual_provider.py`, `runtime_pages.py`,
   and about 20 new documentation files, ending with
   `GCRTS_COMPLETE_WORK_SUMMARY_HE.md` (4:56 PM) and the final
   `CURRENT_SYSTEM_STATUS.md` update (5:04 PM) and `runtime_pages.json` (5:13 PM).

So the correct mental model is: **one continuous session, two work tracks
running back-to-back** (Renderer 1 position proof, then Asset
Inspector/Visual Inspector image-editing + runtime tracking), not "old vs.
new" tracks. `CURRENT_SYSTEM_STATUS.md`'s own "2026-08-09 correction" section
already recognized this and explicitly cross-references both tracks — that
cross-reference is itself part of the since-12:00 work and should be trusted
over the seed context's "separate, earlier" framing.

## Change log

| Area | What changed | Evidence | Status | Impact on prior conclusions |
|---|---|---|---|---|
| Renderer 1 write-up | `RENDERER_LIVE_PROOF.md` §§10-22 and `RENDERER_SYSTEM_STATUS.md` finalized: 14-byte glyph record fully mapped (base `0x800A2AD4`, stride `0x0E`, X `+0x8`, Y `+0xA`), live reversible edits (1 glyph, 1 full line, 2 independent lines, CLD1-driven centering), OT splice test, one Renderer-2 hit | `RENDERER_LIVE_PROOF.md`, `RENDERER_SYSTEM_STATUS.md` | LIVE_VERIFIED (position mechanism) / DESIGNED_ONLY (automatic integration) | Invalidates any earlier belief that "the screen-position writer is unknown" or that Phase 9 is blocked on finding it. That question is closed; automatic runtime integration is the new blocker. |
| `CURRENT_SYSTEM_STATUS.md` | Two large sections appended: a "2026-08-09 consolidated update" summarizing the Renderer 1 proof, and a later "2026-08-09 correction" that cross-links the GCRTS asset-editing track and corrects its own earlier "background editing remains open" claim | `CURRENT_SYSTEM_STATUS.md` lines 1-274 (new), rest is retained history | DOCUMENTATION_UPDATE | The file's own older body (§§0-10, pre-existing) is explicitly marked partially superseded by its own newer top section. Treat only the two 2026-08-09 sections plus `RENDERER_SYSTEM_STATUS.md` as current for renderer status. |
| PROGDAT/MENUDAT discovery | Classroom main-menu background identified as 5 concatenated compressed 8bpp TIM strips in `DAT/SINKOU/PROGDAT.BIN;1` (69,663 bytes); 32 independent 4bpp TIM sprites identified in `DAT/SINKOU/MENUDAT.BIN;1` (30,318 bytes); confirmed NOT SDB/MS/CDB | `IMAGE_ASSET_STATUS.md`, `SDB_MAIN_MENU_ASSET_REPORT.md`, `sdb_main_menu_asset/*` | OFFLINE_VERIFIED (format/offsets) + LIVE_VERIFIED (edits below) | New. No prior conclusion existed about this asset; this closes the previously-open "how are menu/background images stored" question for these two files specifically (not for SDB/MS in general). |
| PROGDAT background edit | White 20×20 square and multi-strip "TRANSLATED WITH GCRTS" text encoded into PROGDAT at exact original consumed size per stream, injected via PCSX-Redux temporary CD patch, survived Hard Reset | `sdb_main_menu_asset/PROGDAT_white_square_exact_v2.BIN`, `PROGDAT_translated_with_gcrts_exact.BIN`, `build_text_patch.ps1` | LIVE_VERIFIED | Directly corrects `RENDERER_LIVE_PROOF.md` §18 / `CURRENT_SYSTEM_STATUS.md` item 8's claim that background/VRAM editing is "still open" — it is open only for the raw-VRAM/GDB-Lua route that section tested; this alternate compressed-file route works and is proven with Hard Reset persistence. |
| MENUDAT block 7/8 edit | START and SETTINGS/PREPARE labels edited, re-encoded, injected, and visually confirmed in-game (label color still changes red/pink on selection, mechanism for that color change unknown) | `MENUDAT_ASSET_CATALOG.md`, `CURRENT_SYSTEM_STATUS.md` "Asset Inspector implementation update" | LIVE_VERIFIED (edit+display) / UNKNOWN (selection-color mechanism) | **Supersedes `IMAGE_ASSET_STATUS.md`'s own earlier-in-the-day claim** ("Blocks 7 and 8 have been identified and decoded but have not yet been edited, re-encoded, or reinjected" — written ~2:38 PM) — this is a same-day stale-within-hours case, not just a pre-noon one. `MENUDAT_ASSET_CATALOG.md` (3:03 PM) and later docs are authoritative. |
| Asset Inspector system | New package: `asset_descriptor.py`, `asset_compression.py`, `asset_tim.py`, `asset_registry.py`, `asset_project.py`, `asset_workspace.py`, `pcsx_patch.py`, `asset_inspector_ui.py`, `asset_cli.py` | `gcrts/*.py`, `ASSET_INSPECTOR_ARCHITECTURE.md`, `ASSET_DESCRIPTOR_SPEC.md`, `IMAGE_FORMAT_ADAPTERS.md`, `ASSET_INJECTION_SAFETY.md` | IMPLEMENTED, partially LIVE_VERIFIED (MENUDAT 7/8, PROGDAT group 0) | New capability. Formalizes the ad hoc PROGDAT/MENUDAT scripts above into a reusable, tested tool with a registry of all 32 MENUDAT + 15 PROGDAT streams. |
| Screen/Visual Inspector | New package: `screen_objects.py`, `screen_capture.py`, `screen_dispatch.py`, `screen_mapping_registry.py`, `visual_inspector_ui.py`, `runtime_visual_provider.py` | `gcrts/*.py`, `VISUAL_INSPECTOR_ARCHITECTURE.md`, `SCREEN_OBJECT_MODEL.md`, `SCREEN_MAPPING_REGISTRY.md`, `SCREEN_ASSET_MAPPING.md`, `TRANSLATION_VIEW.md`, `RENDERER_ASSET_INTEGRATION.md` | IMPLEMENTED; manual mapping is OFFLINE_VERIFIED, runtime-driven detection is LIVE_VERIFIED for specific assets (see below) | New. Explicitly demotes the manual screenshot/rectangle mapper to fallback status partway through this same window (see `RUNTIME_ASSET_TRACKER.md`'s "pivot" note in `CURRENT_SYSTEM_STATUS.md`). |
| Runtime Asset Tracker | New: `runtime_content.py`, `runtime_asset_tracker.py`, `asset_fingerprint.py`, `runtime_content_resolver.py`, `vram_asset_detector.py`, `gpu_asset_correlation.py`, `psx_ordering_table.py`, `runtime_gpu_scan.py`, `runtime_scan_cli.py`, `runtime_probe.py` | `gcrts/*.py`, `RUNTIME_ASSET_STATE_MACHINE.md`, `RUNTIME_ASSET_TRACKER.md`, `GPU_ASSET_CORRELATION.md`, `VRAM_PROVENANCE_TRACKING.md` | IMPLEMENTED (state machine/models); LIVE_VERIFIED for exactly one case (MENUDAT block 9 on the Photos screen) | New capability class: `DRAWN_THIS_FRAME` is now backed by real VRAM+OT+GPU-primitive correlation for one proven asset, not by a saved screenshot rectangle. This did not exist in any pre-12:00 state. |
| Runtime pages | New: `runtime_pages.py`, `runtime_pages.json`, `project_selection.py`, `project_selection.json` | `RUNTIME_PAGE_DISCOVERY.md`, `GLOBAL_SELECTION_MODEL.md`, live JSON files (`runtime.page.1` observations=1687, `runtime.page.2` observations=41) | LIVE_VERIFIED for exactly 2 discovered pages | New. "Page" here means a live composition of active asset IDs, explicitly not a saved screenshot — this is a real, if narrow, working instance of the "user pages vs. runtime truth" idea the audit spec asks about (see §18 below). |
| Test suite | Grew from a session-start baseline (`RENDERER_LIVE_PROOF.md` cites 294 passing) to **348 passed, 6 warnings** by end of window | Live `pytest` run performed for this audit: `348 passed, 6 warnings in 14.57s` | LIVE_VERIFIED (re-run just now) | Confirms `CURRENT_SYSTEM_STATUS.md`'s and `GCRTS_COMPLETE_WORK_SUMMARY_HE.md`'s own claim of 348. `README.md` still says "43 tests total" — stale since Phase 2, not a since-12:00 regression, but still uncorrected. `RENDERER_SYSTEM_STATUS.md` (12:58 PM) could not re-run tests itself (no Python in its shell) and cites 294 as "newest recorded" — that count is now stale, superseded by the 348 recorded later the same day. |
| Repository hygiene | No git commits made; `.sentry-native/` crash-report directory and several session artifacts (`pcsx.json`, shader `.frag`/`.vert`/`.lua` files, `memcard1.mcd`, `memcard2.mcd`) appeared/changed | `git status`, filesystem listing | GENERATED_ARTIFACT | Unchanged risk already flagged twice today (`CURRENT_SYSTEM_STATUS.md`, `RENDERER_SYSTEM_STATUS.md`): zero commits, zero rollback safety, project files mixed with emulator session state. |
| Movie/audio | No new code. `runtime_content.py`'s `CurrentFrameContent` dataclass has `movies: tuple[Any, ...] = ()` and `audio_events: tuple[Any, ...] = ()` fields | `gcrts/runtime_content.py` line 41 | DESIGNED_ONLY | Confirms these are inert placeholders in a data model, not evidence of any movie/audio detection capability. No movie/audio work happened since 12:00 or before. |

## What this invalidates from "before 12:00" thinking

- **"The screen-position writer for dialogue text is unknown."** Closed. It is
  known and live-proven for one (unidentified) overlay; only automatic
  integration remains open.
- **"Background/VRAM image editing is blocked."** Only true for the specific
  raw-VRAM-via-GDB/Lua route. A working alternative (compressed-file
  extract → decode → edit → exact-size re-encode → temporary CD-file inject)
  is proven end-to-end with Hard Reset persistence.
- **"MENUDAT blocks 7/8 are identified but not yet edited."** True only for a
  ~25-minute window this same afternoon; superseded within the same session.
- **"The Screenshot Mapper is how GCRTS knows what's on screen."** No longer
  accurate as of this session: it is now explicitly demoted to fallback/
  evidence status, with runtime VRAM+GPU-primitive correlation as the primary
  (but narrow — one proven asset) mechanism.
- **Any test count below 348** (43, 294, or any other historically-cited
  number) is stale.
- **Renderer 1 and the GCRTS asset system as "separate, unrelated tracks"**
  is an oversimplification — they are sequential parts of the same session,
  explicitly cross-referenced by `CURRENT_SYSTEM_STATUS.md`'s own correction
  section, and share an unresolved cross-check (the 4 GCRTS-found OT roots
  vs. Renderer-1's own `addPrim` address `0x800774B4` have not been diffed
  against each other).

## What is still genuinely unverified going into this audit

- Whether the 4 OT roots found by the GCRTS track (`0x80076A24`, `0x80076A64`,
  `0x80075770`, `0x800757B0`) and GPU DMA trigger (`0x80049670`) belong to the
  same build/overlay as Renderer 1's `addPrim` (`0x800774B4`) — explicitly
  flagged as not cross-checked by `CURRENT_SYSTEM_STATUS.md` itself.
- The named executable/profile for either track's live addresses (both
  tracks operated against an "unidentified" or profile-validated-but-unnamed
  overlay).
- Whether `PROGDAT` groups 1 and 2 have any confirmed runtime role beyond
  "extracted and visually reconstructed."

This document is the Phase 0/Phase 1 deliverable. The full current-state
audit is in `GCRTS_FULL_SYSTEM_AUDIT.md`.
