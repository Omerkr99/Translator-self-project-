# Runtime Pause Snapshot

Milestone 6 of the post-audit development workflow: a coherent,
persistable snapshot of runtime evidence-pipeline state, captured at any
moment and inspectable later without needing PCSX-Redux to stay paused,
running, or even open. Explicitly framed as groundwork for future
movie/audio/subtitle work, not a feature in its own right yet.

## What's captured (`gcrts/runtime_snapshot.py`)

`RuntimeSnapshot`: `snapshot_id` (the same monotonic frame id
`RuntimeVisualProvider.scan()` returns), `captured_at` (wall-clock time),
`objects` (every `InspectableScreenObject` the last scan returned, already
serialized via each object's own `to_dict()` -- image/raster assets AND
Renderer 1 text together, per Milestone 5's unification),
`tracker_instances` (a summary of every `RuntimeAssetInstance` the
Milestone 2 tracker knows about -- state, VRAM regions, draw count --
giving the "active runtime assets"/"VRAM residency"/"draw primitives"
fields the milestone asked for beyond just the flattened screen objects),
`renderer1_profile`/`renderer1_validation` (which profile, and whether it
validated this moment). `active_movie`/`active_audio` are declared,
always empty -- no movie/audio runtime detection exists yet; the fields
exist now so a future snapshot can start populating them without changing
this shape, per the master workflow's own "future placeholders, don't
implement detection yet" instruction.

Every field is plain JSON-serializable data (dict/list/str/int/float) --
deliberately, since that's what makes 6.1 possible at all.

## 6.1 Persistence -- proven live, not just round-tripped through JSON

`capture_runtime_snapshot(provider, frame, objects)` builds a snapshot
from a `RuntimeVisualProvider` that has JUST returned `(frame, objects)`
from its own `scan()` -- no second live connection. `save_snapshot()` /
`load_snapshot()` write/read one JSON file.

**Live-verified this session** (not a synthetic test only): captured a
real snapshot of an active dialogue scene (`SLPS00102.sstate7`, 2 live
Renderer 1 text lines), saved it, then switched PCSX-Redux to a completely
different scene (`SLPS00102.sstate8`, the main menu) -- simulating
gameplay resuming and moving on, exactly the milestone's own scenario.
Loading the saved snapshot back showed the ORIGINAL dialogue-scene data
(`snapshot_id` unchanged, the same two Renderer 1 lines), completely
disjoint from the new live menu objects -- confirmed the saved snapshot
never silently re-synced to whatever the emulator was doing by the time it
was reopened.

Visual Inspector UI: "Save Snapshot" (captures the last scan, prompts for
a save path under `runtime_snapshots/`), "Load Snapshot" (loads a file,
sets `live_tracking` off so the next 750ms poll doesn't overwrite what's
being inspected, and redraws from the frozen data).

## 6.2 Diff -- kept deliberately small

`diff_snapshots(a, b)` -> `SnapshotDiff(appeared, disappeared, changed)`,
by a canonical per-object identity (`object_identity_key`) -- NOT the
object's own `id` field, which embeds screen position for both assets and
Renderer 1 lines and would make any moved-but-still-the-same object look
like one thing disappearing and an unrelated thing appearing. `changed`
compares runtime state and screen bounds, not full-dict equality (a
re-serialized identical object with a different primitive address for the
same asset in the same place is noise, not a real change).

**A real bug found by live testing, not the unit tests**: the first
version of `object_identity_key` only ever recognized `source.asset_id`.
Renderer 1 objects have no `asset_id` at all (`renderer_1_object()`'s
`source` is `kind`/`script_unit`/`line_index`) -- so every Renderer 1 line
was silently invisible to diffing, and `capture_runtime_snapshot(...).active_asset_ids`
was always missing them too. This was caught live: diffing a real dialogue
snapshot against a real menu snapshot showed `disappeared: []` when it
obviously should have listed the two vanished dialogue lines. My own unit
tests hadn't caught it because every one of them used only asset-shaped
test data -- none exercised a real `renderer_1_object()`. Fixed
(`object_identity_key` now falls back to `f"renderer1:line{line_index}"`
for Renderer 1 objects) and pinned with a regression test using a real
`renderer_1_object()`, then re-confirmed live: the same real diff now
correctly reports `disappeared: ['renderer1:line0', 'renderer1:line1']`.

Visual Inspector UI: "Diff vs Saved..." compares whatever is currently
being viewed (live or an already-loaded snapshot) against one more file on
disk, shown in a plain summary dialog.

## Tests

`tests/test_runtime_snapshot.py` (6): capture carries objects + tracker
state + future-placeholder fields always empty, JSON round-trip, "readable
without a provider" (the actual point of 6.1), appeared/disappeared/changed
detection, identical-snapshots-diff-to-empty, and the Renderer 1 identity
regression test above. Full suite: **390 passed** (384 + 6), no
regressions.
