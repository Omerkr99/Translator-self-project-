# Movie-Time Source: Host Wall-Clock Timing, Partially Deterministic

Second concrete investigation into Stage 5's prerequisites (alongside
`docs/renderer/VRAM_WRITE_PATH_INVESTIGATION.md`), gated by SRS §12 /
SDD §19. Scoped narrowly: does host-side wall-clock time, measured from
a fixed reset point, reliably tell you "how far into the boot/movie
sequence you are" -- without any PS1-side hook or disassembly? If so,
that alone would satisfy SDD O5's external-subtitle-sync need.

## A GUI-automation detour, and the actual fix

Most of this investigation's live time went into an unrelated tooling
problem, not the movie-time question itself: reliably reaching a fresh
boot via OS-level menu clicks (`File > Reboot`, `File > Open Disk
Image`, `Emulation > Start emulation`) turned out to be fragile --
dialogs sometimes didn't close on the expected click, menu-tab click
coordinates measured at one point in the session stopped landing
correctly later, and `find_window_by_process_name` could return either
the main window or an open dialog belonging to the same process
(ambiguous by design, since it only matches by process, not title),
causing later clicks meant for the main window to silently land on a
leftover dialog instead.

**The fix: stop using GUI menu clicks for emulator control entirely.**
PCSX-Redux's Lua API (already used for the pad-override bridge, see
`docs/tooling/PCSX_PAD_INPUT_BRIDGE.md`) also registers
`hardResetEmulator()` and `resumeEmulator()`
(`src/core/pcsxlua.cc`'s `REGISTER` list). Calling
`PCSX.hardResetEmulator() PCSX.resumeEmulator()` through the already-
reliable Lua Console text-input mechanism
(`gcrts.pcsx_lua_console.run_lua`) reproducibly resets and starts the
emulator from a disc already loaded once via the GUI, with none of the
menu-click fragility -- confirmed live, twice, both producing a real,
fresh boot sequence (BIOS trace, `PS-X Control PAD Driver`, changing
on-screen content). This is now the preferred way to drive
reset/start for any future live experiment in this project; GUI menu
clicks should be reserved for the one thing Lua can't do (opening a
disc image file).

## The experiment

Two independent runs, each: `PCSX.hardResetEmulator()` +
`PCSX.resumeEmulator()` via Lua (anchor `t=0` set immediately after),
then a screenshot every 2.0 seconds for 40.0 seconds, each hashed
(SHA-256 of the raw pixel bytes, not compared by eye -- see
`docs/renderer/VRAM_WRITE_PATH_INVESTIGATION.md`'s own account of why
eyeballing screenshots led to a wrong conclusion earlier in this same
research thread).

## Result

**17 of 20 samples matched byte-for-byte** at the same `t` value across
both runs. More precisely: **every sample from `t=0.00s` through
`t=22.77s` (12 consecutive samples) matched exactly** -- the BIOS/logo
portion of boot is fully deterministic against wall-clock time. From
`t=24.82s` onward (plausibly into the opening movie/cinematic, per the
Stage 4 boot timeline), most samples still matched (5 of 8) but 3 did
not (`t=24.82s`, `t=30.99s`, `t=35.11s`).

Full data: `evidence/movie_time_source_investigation/run1.json`,
`run2.json`, `record.json`.

## Interpretation

The most likely explanation for the later mismatches is ordinary host-
side timing jitter: each screenshot is a real HTTP round-trip to
PCSX-Redux's Web API, and a few hundred milliseconds of variance in
that round-trip is invisible while the same frame persists for seconds
(the early boot logos), but can land on an adjacent, different frame
once content changes every frame (real movie playback). **This was not
proven** -- distinguishing "host jitter picked a neighboring frame"
from "the game's own playback timing genuinely varies run to run" would
need either a finer sampling interval, per-request round-trip timing
correlated against the mismatches, or saving the actual mismatched
frames for visual comparison (not done here -- the script only hashed,
never saved, the images, a real gap in this pass worth fixing before
reusing the script).

## Relevance to Stage 5

**Encouraging, partial result for O5 (external subtitle sync)**:
subtitle cues span multiple seconds, so occasional sub-second drift
during fast-changing content is unlikely to be perceptible to a
viewer, and the mechanism is exact during slower-paced segments. This
does not require solving VRAM-write-path either -- O5 is external
(host-rendered) overlay work, already architecturally unblocked per
SDD §18.

**Does not establish** a frame-exact PS1-side timing source, which is
what O6 (internal/native movie subtitle composition, gated alongside
VRAM-write-path) would need. That remains unproven and would still
require either resolving the jitter-vs-nondeterminism question above,
or genuine in-RAM instrumentation of the movie-player executable
family (`MPRO`/`MOVER`/`MKUBI`/`MNINO`/`MOP`/`MRIKA`/`MYOKO.EXE`) --
real, unstarted reverse engineering, deliberately out of scope for
this pass.

## What's still needed

- Isolate jitter from genuine non-determinism (finer sampling, or
  round-trip-time correlation, or saving frames for the 3 mismatched
  samples specifically).
- If genuinely deterministic once jitter is controlled for: O5's
  external-sync mechanism is essentially proven and could move to
  actual subtitle-track authoring against a known movie.
- If genuinely non-deterministic: O5 would need either a coarser
  subtitle-timing granularity (tolerable, given cues span seconds) or
  a real in-RAM signal after all.
- O6/O7 (internal path) still blocked on both this prerequisite and
  VRAM-write-path regardless of how the above resolves.
