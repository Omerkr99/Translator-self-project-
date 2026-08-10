# Renderer 1 Runtime Driver

Milestone 1 of the post-audit development workflow: convert the manual,
debugger-only Renderer 1 proof (`RENDERER_LIVE_PROOF.md` sections 10-22)
into a reusable, tested GCRTS capability. This document describes what
was built, what was live-proven this session, and what is still open.

## What "Renderer 1" is

The game's own native glyph renderer (not the still-unbuilt
`gcrts.render_mode.RenderMode.CUSTOM_ENGINE` path, which is a different,
pre-existing project track aimed at a custom MIPS-patched renderer that
does not exist yet). Renderer 1 reads glyph position from a 14-byte
per-character record array and redraws every active record from scratch
every frame -- no code patch, no hook installation, and no breakpoint is
needed to drive it: a plain memory write is visible on the very next
frame. This is a materially simpler and lower-risk mechanism than the
`CUSTOM_ENGINE` design, which depends on installing a MIPS hook stub.

## New modules

- **`gcrts/renderer1_profile.py`** -- `Renderer1Profile` (addresses +
  record geometry + a code fingerprint), `ProfileStatus`,
  `ValidationResult`, and `validate_profile()`. A profile is only ever a
  named hypothesis for one loaded state, exactly like the existing
  `gcrts.mips_patch_profile.PatchProfile` -- `validate_profile()` must
  return `PROFILE_VALID` before any read/write is attempted.
- **`gcrts/renderer1_runtime.py`** -- `capture_snapshot()` (active-line
  detection via a single targeted 196-byte read, not a breakpoint loop),
  `compute_char_positions()` / `build_overrides_from_descriptor()` (CLD1
  consumption -- turns a decoded `CLD1` descriptor into per-character
  position overrides), and `apply_overrides_live()` / `restore_live()`
  (backup-verify-write-verify, atomic rollback on any single failure).

### Why active-line detection is a snapshot, not a breakpoint loop

The manual investigation in `RENDERER_LIVE_PROOF.md` section 11 used a
breakpoint arm-and-collect-hits loop to enumerate active records. This
project's own history has repeated hangs/crashes traced to exactly that
kind of breakpoint/continue automation on this GDB stub (see that
document's "emulator hangs/crashes" notes, and `mips_patch_profile.py`'s
Phase 7 lessons). Since Renderer 1 rewrites every active record from
scratch every frame anyway, a single plain read of the known array
already reflects "what's showing right now" -- no need to catch a write
in the act. This also matches the standing safety rule against polling
large ranges every frame: it's one 196-byte read, on demand, not a loop.

The trade-off, honestly documented in code: a snapshot can't always tell
"genuinely part of the current line" from "stale leftover data in an
unused slot" from one read alone. `RecordConfidence` (`ACTIVE` / `PARTIAL`
/ `EMPTY`) exists so an ambiguous record is reported as such, not
silently trusted -- see `gcrts/renderer1_runtime.py`'s module docstring.

## Live proof (this session, `SLPS00102.sstate7` -- the "Mika" hallway
scene, loaded via the PCSX-Redux Web API `/api/v1/state/load?slot=7`, not
manual GDB)

**Profile drift, confirmed live before any of the rest of this**: reading
the profile's exact recorded addresses while the emulator sat at the
title/photo-menu screen (a different loaded state) returned bytes that do
not decode as the expected instructions at all -- direct, fresh evidence
(not a rerun of an old claim) that `validate_profile()` is necessary, not
defensive theater. The same addresses matched byte-for-byte once a real
dialogue scene was loaded.

**Milestone 1 direct-override proof** (`milestone1_live_proof.py`):
`capture_snapshot()` found 14 active records unattended; the driver moved
record 0's X by +80px, screenshot showed the character visibly displaced
from its line, `restore_live()` put it back -- confirmed both by readback
(`10 -> 90 -> 10`) and a third screenshot matching the pre-edit one.

**Milestone 1 CLD1-consumption proof** (`milestone1_cld1_proof.py`): built
a real `EditorLayoutPlan` (3 characters, `LayoutAlignment.CENTER`,
200px budget) -> `encode_layout_descriptor()` -> real `CLD1` bytes (34
bytes, magic verified) -> `decode_layout_descriptor()` -> resolved
`x=128` (centering math, not a hand-picked number) ->
`build_overrides_from_descriptor()` -> `apply_overrides_live()`. Screenshot
showed the line's first three characters (「ミカ：」) jump to the computed
position, visibly displaced past later text; `restore_live()` returned
the line to its exact original reading order, confirmed by screenshot.

Both runs used only `gcrts.live_extract.GdbClient.read_memory`/
`write_memory` -- no breakpoints, no manual address entry at test time,
no GUI input simulation (which was tried first via `SendKeys` and raw
`SendInput` scancodes and did not register with the PCSX-Redux window;
reaching a live dialogue scene instead used the existing save-state
files and PCSX-Redux's own Web API, which is the reliable, low-cost path
this project's history already established over GUI automation).

## Tests

`tests/test_renderer1_profile.py` (7 tests) and
`tests/test_renderer1_runtime.py` (11 tests) -- pure-function tests
against fake/dict-backed memory, matching this project's established
testing convention (e.g. `tests/test_runtime_visual_profile.py`). Cover:
every `ValidationResult` branch, `RecordConfidence` classification,
snapshot refusing to read records when the profile doesn't validate,
per-character position accumulation, CLD1-descriptor-to-override
flattening, apply+restore round trip, and atomic rollback when an
override targets a record index the snapshot doesn't have.

Full suite: **366 passed** (348 pre-existing + 18 new), run via
`py -3 -m pytest tests -q`. No regressions.

## Definition of Done -- status

| # | Requirement | Status |
|---|---|---|
| 1-2 | Start PCSX-Redux, reach a known Renderer 1 dialogue | DONE (via Web API save-state load) |
| 3 | GCRTS identifies a valid Renderer 1 profile | DONE (`validate_profile` -> `PROFILE_VALID`) |
| 4 | GCRTS automatically finds active dialogue line(s) | DONE (`capture_snapshot` -> 14 active records, unattended) |
| 5 | Load/apply a CLD1 layout | DONE (full encode -> decode -> apply chain, live) |
| 6 | Position changes visibly in-game | DONE (screenshots) |
| 7 | Centering applied where supported | DONE (used in the CLD1 proof) |
| 8 | Restore returns the original layout | DONE (readback + screenshot match) |
| 9 | No manual GDB memory editing required | DONE (driver API only) |
| 10 | Invalid/stale profile -> safe failure, not a write | DONE (`capture_snapshot`/`apply_overrides_live` both refuse) |
| 11 | Existing tests remain green | DONE (366/366) |
| 12 | New tests for validation/addressing/apply/restore | DONE (18 new) |

## Known limitations / next steps

- `record_count=14` is the wrap point observed for a single line in the
  original manual investigation; a scene with multiple simultaneous
  lines beyond 14 total characters, or the second double-buffered
  destination noted in `RENDERER_LIVE_PROOF.md` section 14, has not been
  separately exercised through this driver yet.
- `SLPS00102_BASE_PROFILE` is one profile for one loaded state family.
  Whether the same addresses hold across every chapter/overlay (the
  project's own overlay-drift concern) is exactly what
  `validate_profile()` is for at call time -- it has not been swept
  across every known executable.
- The driver has no automatic "detect that a dialogue is currently
  showing" trigger yet -- a caller still decides when to call
  `capture_snapshot()`. That kind of automatic trigger is Milestone 2/5
  territory (Runtime Asset Tracker / Visual Inspector), not Milestone 1.
