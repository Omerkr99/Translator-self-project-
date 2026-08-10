# Runtime Asset Tracker

The Runtime Asset Tracker is the primary evidence source for the Visual Inspector. `gcrts.runtime_content` defines identities, instances, lifecycle states and frame content. `gcrts.runtime_asset_tracker` handles lifecycle transitions and VRAM overwrite semantics. `gcrts.asset_fingerprint` resolves known decoded/source signatures.

## Current PCSX-Redux transport

Production tracking is read-only and external. `RuntimeVisualProvider` obtains RAM and VRAM snapshots through the PCSX-Redux web server, validates the loaded GPU-submit routine byte-for-byte against the local `PROG.EXE`, parses the four proven ordering-table roots, and correlates their textured primitives with exact packed TIM rows in VRAM.

Persistent Lua breakpoints are disabled. Both GPU I/O-write callbacks and execution breakpoints eventually crashed this PCSX-Redux build. `gcrts_runtime_probe.lua` is therefore only a disabled compatibility stub and must not be loaded for normal tracking.

The provider fails closed: if the executable profile does not match exactly, it emits no live objects instead of trusting stale absolute addresses. `screen_mappings.json` remains an explicit manual fallback, not runtime evidence.

## Verified result

MENUDAT block 9 is matched exactly at VRAM word `(640,96)`. On the Photos page, a live `POLY_GT4` reference maps it to screen bounds `(40,24,64,32)`, so its state is `DRAWN_THIS_FRAME`. Back on Main Menu, the texture remains resident in VRAM but no active primitive references it, so it is correctly absent from the drawn set.

The current external scan generation is a snapshot identifier, not a hardware VSync frame number. Exact load/decompress source and destination pointers still require a future non-crashing trace transport.

## 2026-08-10: Milestone 2 -- generalizing beyond the one proven asset

The audit that preceded this milestone found the architecture above already
solid but proven live for exactly one asset (MENUDAT block 9), and found
`RuntimeVisualProvider` and `RuntimeAssetTracker` were two disconnected
implementations: the provider built `InspectableScreenObject`s directly from
`gcrts.gpu_asset_correlation.correlate()` hits and stamped every one with a
hardcoded `"DRAWN_THIS_FRAME"` string, never actually running anything through
the tested lifecycle state machine. That meant `UPLOADED_TO_VRAM` /
`STALE_IN_VRAM` / `UNLOADED` -- all correctly modeled and unit-tested in
`gcrts.runtime_asset_tracker` -- were unreachable from the live path.

**Fixed**: `RuntimeVisualProvider` now takes an optional persistent
`RuntimeAssetTracker` (a fresh one by default) and feeds every correlated hit
through it -- `loaded()` once per asset_id (cached across calls), then
`uploaded()`/`draw()` on every scan that still correlates it.
`scan()`'s own return contract (`frame, objects`) is unchanged, so
`asset_inspector_ui.py` and `visual_inspector_ui.py` keep working unmodified;
`provider.tracker` is purely additive. Since `visual_inspector_ui.py` already
polls `scan()` every 750ms, this means the next time that UI runs, an asset
that stops being drawn between polls now genuinely demotes in the tracker,
inspectable independently of whatever the current poll returned.

**Added**: `RuntimeAssetTracker.unloaded()` -- the lifecycle enum
(`gcrts.runtime_content.RuntimeAssetState`) has always included `UNLOADED`,
but nothing ever produced it. It's deliberately never inferred automatically
(this class doesn't guess that a caller has stopped caring about an
instance) -- a caller with independent evidence an asset's decoded buffer and
VRAM residency are both gone calls it explicitly. Distinct from
`STALE_IN_VRAM` (still resident, just not drawn this frame) by design; both
have their own tests (`tests/test_runtime_asset_tracker.py`).

**Live proof** (`milestone1`-style discipline: real PCSX-Redux, real
save-state loads via the Web API, not synthetic data): scanned two genuinely
different live contexts with the SAME provider instance --

1. Title/main menu (`SLPS00102.sstate8`): `main_menu.start` (block 7),
   `main_menu.prepare` (block 8), `progdat.group0` (Classroom Background
   composite) -- all `DRAWN_THIS_FRAME`, real GPU/OT/VRAM correlation.
2. Photos/spoils menu (`SLPS00102.sstate0`): `category.photos` (block 9),
   `progdat.group2` (Spoils Table Background composite) -- `DRAWN_THIS_FRAME`.

**5 distinct assets, real runtime provenance, no screenshot mapping
involved.** Reading `provider.tracker.instances` after both scans confirms
the state machine actually moved: all three context-1 assets demoted from
`DRAWN_THIS_FRAME` to `UPLOADED_TO_VRAM` the moment context 2 was scanned and
they weren't redrawn, while the two context-2 assets show `DRAWN_THIS_FRAME`
with real draw counts. This is the live version of what
`tests/test_runtime_asset_tracker.py::test_full_lifecycle_and_draw_is_frame_scoped`
already proved in isolation -- now proven through the actual production
scanning path, against a real emulator.

**Honestly incomplete**: only 2 live, MENUDAT/PROGDAT-driving contexts were
reachable this session (title menu, photos/spoils menu) -- not the 3 the
milestone's own definition-of-done asks for. A third menu context (e.g. the
"system menu" -- blocks 0-2, `View Spoils`/`Window Color`/`Return to Title`
per `MENUDAT_ASSET_CATALOG.md`) exists in the catalog but no reachable save
state shows it, and simulated controller input (`SendKeys`, raw `SendInput`
scan codes) did not register with the PCSX-Redux window, matching this
project's established preference for save-state/Web-API-driven testing over
GUI automation. A chapter-select screen (`SLPS00102.sstate1`) was tried and
produced a genuine, informative negative result: the PROG.EXE code
fingerprint still validated (so the 4 OT roots are real for that screen too),
but zero primitives correlated to any cataloged MENUDAT/PROGDAT asset --
consistent with chapter titles rendering through a different path (most
likely Renderer 1's own text engine, not a raster MENUDAT label) rather than
a detector bug; raw OT command bytes were dumped and inspected to rule out
an unrecognized primitive type (only `POLY_FT4`/`POLY_GT4`/an untextured
`0x32` triangle/padding were present -- no sprite commands silently
skipped).
