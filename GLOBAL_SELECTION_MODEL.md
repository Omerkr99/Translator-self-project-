# Global Selection Model

`ProjectSelection` is the in-process boundary and `FileProjectSelection` synchronizes separate desktop processes through `project_selection.json`. Visual selection publishes the canonical asset ID; Asset Inspector selection publishes in reverse. The Visual Inspector follows currently drawn matching selections, and Asset Browser cards display `[DRAWN]` badges from the runtime provider.

## 2026-08-10: Milestone 4 -- closing the "publish but nobody reacts" gap

The paragraph above describes the plumbing that already existed: both
windows already *wrote* to `project_selection.json` on click, and the
Visual Inspector already had a `sync_external_selection` that could find a
matching live object. What was missing, confirmed by reading both UI
modules in full before writing any code: **the Asset Browser never read
the file at all**, and **neither window visually distinguished the
selected object from everything else on screen**. Writing a selection was
a broadcast nobody was listening to in one direction, and invisible even
when it worked in the other.

### 4.1 Asset selection (runtime/other window -> Asset Browser)

`AssetInspectorApp.poll_external_selection()` (new, polls every 1000ms,
mirroring the pre-existing `poll_runtime_badges` pattern) reads the
selection file and, if the asset_id changed and resolves to something this
project/window actually knows about (`resolve_asset_selection()`, a pure
function -- tests in `tests/test_global_selection.py`), calls
`select(block, publish=False)` / `select_composite(publish=False)`. That
now: **highlights** the matching card (`Selected.TButton` style, tracked
via a new `self._cards` dict built in `refresh_browser()`), **scrolls it
into view** (`_highlight_and_reveal()`, computes the card's position in the
scrollable grid and calls `canvas.yview_moveto`), and loads the full
Inspector state (image/metadata/palette/budget -- `select()`'s existing
job, now reachable from an external trigger too). `publish=False` plus
`_last_external_asset_id` being updated by every select call (local or
external alike) prevents a republish loop without needing a fragile
source-string check.

**Live-verified** (`m4_selfcontained_test.py`, screenshots this session): a
fresh window opens on block 7 (Start, highlighted); writing
`{"asset_id": "category.photos", "source": "visual_inspector"}` externally
switches it to block 9 (Photos) within one poll tick -- highlighted,
scrolled into view, full detail panel loaded, zero clicks.

### 4.2 Reverse selection (Asset Browser -> ask Runtime Tracker)

Every selection now appends a `Runtime:` line to the detail panel via
`runtime_status_text()` (pure, tested): `"LIVE -- currently drawn this
frame"` or `"Known asset -- not currently drawn"`, a live check against the
same tracker-backed `RuntimeVisualProvider` Milestone 2 wired up.

On the Visual Inspector side, `sync_external_selection` existed but had two
real gaps: **no visual highlight at all** (`redraw()` drew every object
identically regardless of `self.selected` -- fixed with a white selection
ring plus a thicker outline) and **silent no-op when the asset isn't
currently drawn** (anything not in `self.runtime_objects` was just
ignored -- fixed: `select(None, publish=False, not_drawn_asset_id=asset_id)`
now shows the asset_id as heading with `"Known asset -- not currently
drawn"`, matching the milestone's own example wording). Selections also
now trigger an immediate `redraw()` instead of waiting for the next 750ms
poll.

**Live-verified** (`m4_visual_inspector_test.py`): selecting `main_menu.start`
shows a visibly ringed box; publishing an asset_id absent from the current
context shows the not-drawn heading/detail with no ring anywhere (nothing
falsely highlighted).

### 4.3 Runtime text stays out of the Asset Browser

Already correct before this milestone: `gcrts.screen_dispatch.dispatch()`
routes `renderer_1_object()`-built objects to `TEXT_LAYOUT_INSPECTOR`, never
`ASSET_INSPECTOR` (pre-existing `tests/test_screen_dispatch.py`). The new
external-selection listener only resolves against
`AssetProject.descriptors`, which runtime-text asset_ids never appear in --
no special-casing needed. `TEXT_LAYOUT_INSPECTOR` itself is still an
informational dialog, not a real editor window; that's a separate, future
piece of work, not a global-selection gap.

### Tests and a testing caveat

`tests/test_global_selection.py` (5 new: known block, known composite,
wrong composite group, two "genuinely unknown -> None, don't guess" cases,
plus the status-text helper). Full suite: **373 passed** (368 + 5), no
regressions.

Worth recording: an early live-test attempt left a window idle for a few
real-world seconds between screenshots and observed several card buttons
fire on their own with no corresponding click -- traced via a temporary
call-stack dump to the plain, pre-existing, UNMODIFIED card lambda, not
anything this milestone touched. A synthetic/stray-input artifact of idle
GUI windows in this automation environment, not a product bug. Worked
around by driving verification through a single script's own
`after()`-scheduled callbacks inside one short-lived `mainloop()`, rather
than external multi-step shell orchestration with real-time sleeps.
