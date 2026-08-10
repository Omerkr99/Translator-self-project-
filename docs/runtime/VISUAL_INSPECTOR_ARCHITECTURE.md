# Visual Inspector Architecture

The primary input is live runtime evidence: exact packed textures in VRAM correlated with textured primitives reachable from current Ordering Table roots. This yields canonical asset ID, VRAM region, primitive address, UV/TPAGE and dynamic screen bounds. Only this path produces `DRAWN_THIS_FRAME`.

Resolution priority is runtime provenance, VRAM/GPU correlation, renderer correlation, verified page evidence, manual mapping fallback, candidate, unknown. `screen_mappings.json` is never active-state proof.

The Visual Inspector refreshes runtime objects every 750 ms after capture. Manual fallback is explicit and disabled by default. Runtime objects route through the existing dispatcher and Asset Inspector.

## 2026-08-10: Milestone 5 -- Unified Visual Inspector

`RuntimeVisualProvider.scan()` now combines BOTH live systems in one call:
the Milestone 2 asset tracker (MENUDAT/PROGDAT via VRAM/GPU/OT) and the
Milestone 1 Renderer 1 driver (position records via a plain RAM read),
reusing the SAME already-fetched RAM snapshot for both -- one HTTP round
trip, two independent detectors. Before this milestone these were two
disconnected systems: Renderer 1's live driver existed but nothing fed its
output into the Visual Inspector at all, so a real dialogue scene always
showed zero runtime text no matter what was actually rendering.

**The critical bug this exposed and fixed**: `scan()` used to
`if not roots: return frame, []` -- an early return that skipped
everything, including a Renderer 1 check that didn't even exist yet at the
time. Since PROG.EXE's roots are never present during a dialogue scene
(`GPU_OT_RUNTIME_MAP.md`'s Milestone 3 finding), this early return meant
runtime text could NEVER have been detected even after wiring it in, unless
the early return was removed too. `_renderer1_objects()` is now called
unconditionally, before any roots check; `tests/test_runtime_visual_provider.py`
has a synthetic-RAM regression test specifically for this (`test_scan_finds_renderer1_text_even_when_prog_profile_does_not_validate`).

**Live-verified both halves through the one unified `scan()` call this
session**: loaded a real dialogue scene (`SLPS00102.sstate7`) -- returned 2
`RUNTIME_TEXT`/`RUNTIME_TEXT_RENDERER_1` objects at the exact live
positions (`(26,152)` and `(64,171)`, matching the two-line dialogue on
screen). Loaded the main menu (`SLPS00102.sstate8`) with the same provider
-- returned the same 3 asset objects as Milestone 2 (`main_menu.start`,
`main_menu.prepare`, `progdat.group0`).

**Honest limit, not fudged**: per Milestone 3's own finding, these two
scenes never coexist in this game (different loaded executables) -- there
is no real scene to demonstrate "both an image asset and Renderer 1 text
visible simultaneously" against actual game data. The unification is real
at the CODE level (one call, one merged list, proven to carry both types
correctly by the synthetic regression test above) but could not be
demonstrated on one live frame because the game itself never puts both on
screen at once. This is not a shortcoming of this milestone's work --
forcing a fake "both visible" demo would contradict Milestone 3's own
verified finding.

**5.2 color scheme** (`gcrts.visual_inspector_ui.object_color`): switched
from confidence-keyed (`COLORS[obj.confidence]`, which could not
distinguish "runtime-confirmed image" from "runtime-confirmed Renderer 1
text") to a scheme that reads both source and type: blue = runtime-
confirmed image/raster asset, cyan = runtime-confirmed Renderer 1 text,
yellow = candidate/unresolved, gray = manual-fallback-only. A short text
tag (`object_status_label`) is drawn alongside every box so nothing depends
on color alone. 6 new tests (`tests/test_visual_inspector_colors.py`).

**5.3 real bug found and fixed while building type-aware hover text**:
`hit()` (used by both hover and click) tested exclusively against the
static `ScreenMappingRegistry`, never against `self.objects` (what's
actually drawn -- live runtime objects when a scan succeeded). A purely
live object like a Renderer 1 line -- which has no reason to ever get a
manual registry entry -- could never have been hovered or clicked at all
before this fix. `hit()` now tests against `self.objects`, preserving the
registry's existing "smaller object wins" ordering. `tooltip()` now shows
type-appropriate fields (Renderer 1: line/script_unit/position/glyph
count/profile; assets: asset_id/block/format/runtime state/VRAM/primitive
count/confidence) instead of one generic line for everything.

**5.4/5.5**: click routing (`gcrts.screen_dispatch.dispatch`) and the
Translation View's text-only filter were already structurally correct
before this milestone -- both simply had no live Renderer 1 data flowing
through them to prove it. Confirmed unchanged and now exercisable with
real data via the `hit()` fix and the `scan()` wiring above.

Full suite after this milestone: **384 passed** (376 + 8 new: 6 color
tests, 2 provider tests), no regressions.
