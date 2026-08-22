# SPU Playback Trace

## 1. Why LBA-only audio identification was insufficient

Every earlier audio milestone in this project answers "what LBA is the
CD-ROM subsystem's read position pointing at right now" and resolves
that to a physically-bounded `AudioAsset` (`gcrts.runtime_audio`,
`gcrts.audio_asset_resolver`, `gcrts.live_audio_inspector`). That is
real, correctly-computed evidence about the CD subsystem's position --
it was never proof of what is actually audible at a given instant.

A live capture session (2026-08-22/23) demonstrated the gap directly:
polling the current LBA during a save-slot-9 scene produced five
different resolved candidates (`XAPACK40:0`, `XAPACK22` channels 0/1/2,
and `XAPACK22:7`) across a few dozen seconds of ordinary play. Direct
listening rejected every one of them -- including `XAPACK22:7`, which
had previously been confirmed the same way in an earlier session. The
"current LBA -> guess XAPACK -> audition candidate" workflow was
retracted as a methodology at that point (see
`docs/status/CURRENT_SYSTEM_STATUS.md`'s 2026-08-23 entries) in favor
of what this document describes: observe the actual SPU-side playback
mechanism first, and only afterward ask what CD position (if any)
correlates with it.

## 2. The new methodology: playback-first, not CD-first

The central question this milestone answers is: **what PS1 audio path
is actually producing the sound at the moment a human marks it as
heard** -- classified into exactly one of:

- `SPU_VOICE_PLAYBACK` -- a real SPU voice Key ON with a nonzero,
  meaningful voice bitmask inside the marker window.
- `CD_AUDIO_INPUT` -- no meaningful Key ON/OFF activity, but a CD-input
  lifecycle signal (the position/state fields `gcrts.runtime_audio`
  already tracks) is active in the same window.
- `OTHER_OR_UNKNOWN` -- a marker exists but neither signal is present.
- `NOT_YET_CLASSIFIED` -- no marker yet; a human capture is still
  required.

This project has **already established, with real, repeated, hands-on
evidence** (`gcrts.spu_audio_path`'s module docstring, in full) that
this game's dialogue **in general** does not go through the SPU's
24-voice mixing engine (`all_spu_voices_muted_dialogue_still_audible()`
-> `True`, twice, independently, in two structurally different scenes)
and does not move through the system DMA controller's CD-ROM/SPU
channels either (`dma_cdrom_or_spu_channel_active_during_confirmed_
voice_line()` -> `False`). `classify_playback_backend()` already
returns `CD_INPUT_UNKNOWN_FORMAT`. **This milestone does not re-open
that question for the game in general** -- it applies the same
evidence-gathering discipline to the specific, still-unidentified
save-slot-9 target line, whose earlier `XAPACK22:7` identification was
retracted (see section 9).

## 3. Architecture: why GDB polling and not a new "guess more candidates" loop

Two producers write the same structured JSONL schema
(`gcrts.spu_playback_trace`):

1. **`pcsx_lua/spu_playback_trace.lua`** -- the primary producer,
   running IN-PROCESS inside PCSX-Redux via its own real Lua API.
2. This project's existing GDB-based tooling, as a fallback.

### Why not live SPU-MMIO polling

GDB's own memory read/write path for the SPU hardware I/O range
(`0x1F801xxx`) is **confirmed unreliable** -- a debug-issued write does
not round-trip even while genuinely running
(`gcrts.spu_audio_path.spu_mmio_read_write_roundtrip_reliable()` ->
`False`). This milestone re-checked PCSX-Redux's Lua memory API against
its **actual FFI source** (`src/core/pcsxffi.lua`'s real `ffi.cdef`
block, fetched fresh this session, not from memory or paraphrased
docs) and confirmed it exposes exactly `getMemPtr`/`getParPtr`/
`getRomPtr`/`getScratchPtr`/`getRegisters`/`getReadLUT`/`getWriteLUT`
-- **no SPU RAM or SPU-register accessor exists in either channel.**
This re-confirms, with a stronger (primary-source) evidence class than
before, the already-established `spu_internal_ram_directly_
inspectable() -> False` conclusion. It is not new information, but
independent corroboration -- see section 8.

### Why a CPU breakpoint at a known writer PC, reading CPU registers, IS reliable

This project has already used this exact evidence channel successfully
(`gcrts.spu_audio_path.KEY_WRITER_SITES`/`SPUCNT_WRITER_SITES`, and the
decisive `LIVE_CORRELATION_RUNS` negative result). It never touches SPU
MMIO: it arms an **execution breakpoint on the CPU instruction that is
about to WRITE a value into an SPU register**, then reads the CPU's own
general-purpose registers (`$a0` at that instant) -- a read path
that has been reliable throughout this entire project. PCSX-Redux's
real Lua API supports this natively:
`PCSX.addBreakpoint(address, 'Exec', width, cause, invoker, label)`
with an `invoker` callback that receives `PCSX.getRegisters()`, running
in-process (avoiding this project's own well-documented GDB
breakpoint-cycling fragility, `PCSX_REDUX_CAPTURE_PROTOCOL.md` section
3, and the real crash loop `gcrts.pcsx_spu_observer` hit from repeated
GDB attach/detach cycles).

### Per-voice register map (verified, but writer sites not yet found)

`gcrts.spu_playback_trace` documents the full per-voice register layout
(Volume L/R, ADPCM sample rate/pitch, ADPCM start address, ADSR,
ADSR current volume, ADPCM repeat address) at psx-spx-documented
offsets from each voice's own base
(`SPU_BASE_VALUE + voice_index*0x10`). This is **verified two ways**:
against psx-spx directly, and internally cross-checked against this
project's own already-verified `OFFSET_MAIN_VOL_L = 0x180` control
register offset (`24 * 0x10 == 0x180` exactly -- the control registers
begin precisely where the 24th voice block ends, which would not line
up if either constant were wrong). **What is NOT yet found**: the
actual game-code write sites for these per-voice fields (only Key
ON/OFF's writer PCs are live-confirmed). Finding them would need new
static disassembly work, out of this milestone's scope --
`PER_VOICE_WRITER_SITES_CONFIRMED = False`, recorded explicitly as the
narrowest unresolved gap for this register class.

## 4. How to arm the trace

1. Launch PCSX-Redux from the project root (so its working directory
   matches where `pcsx_lua/spu_playback_trace.lua` expects to write
   `spu_playback_trace.jsonl`).
2. `Debug > Lua Editor` (or `Lua Console`), open
   `pcsx_lua/spu_playback_trace.lua`, click Run.
3. Confirm the Lua console/log shows: `SPU Playback Trace armed: 11
   breakpoints, heartbeat + save-state + marker listeners active.
   Writing to spu_playback_trace.jsonl.` (6 SPU Key ON/OFF sites + 2
   SPUCNT sites + 4 CD-ROM command sites, plus the periodic heartbeat
   and the save-state/keyboard listeners).
4. **Arm BEFORE gameplay begins** -- load save slot 9 only after the
   script is confirmed running, so the trace covers several seconds of
   context before the target line, not just the line itself.

## 5. How to create a marker: TARGET_BEGIN and TARGET_END

Press **F9** (the script's `MARK_KEY` default, `GLFW_KEY_F9 = 298`,
`GLFW_PRESS = 1` -- both standard, stable GLFW constants, but **not
independently live-verified against this specific PCSX-Redux build
this session**) **once** the instant the target dialogue line
**starts**, and **again** the instant it **ends**. The same key
alternates the label every press (`TARGET_BEGIN` then `TARGET_END`
then `TARGET_BEGIN` again for a repeat run, ...) -- `gcrts.
spu_trace_analyzer.pair_target_runs` turns this flat, alternating
sequence into `TargetRun`s, explicitly reporting a trailing unpaired
`TARGET_BEGIN` (an odd number of total presses) rather than silently
mis-pairing it.

This is PCSX-Redux's own application receiving a real physical
keypress -- a genuinely different channel from the already-confirmed-
broken "synthetic input into the emulated game controller" problem
(`gcrts.pcsx_spu_observer.synthetic_input_reaches_game_controller()`
-> `False`); it does not need to reach the emulated console at all,
only the host application, the same way PCSX-Redux's own menu
shortcuts already work. This is the simplest reliable alternative
available through PCSX-Redux -- no separate hardware, no synthetic
input, no reliance on the (already-broken) game-controller path.

**If F9 does not produce a `MARK <label> recorded` log line**: every
real keypress is logged as `SPU Playback Trace: keyboard event
key=<N> action=<N>` (a diagnostic line, not written into the JSONL
trace). Check the console for the real `key`/`action` values and
update `MARK_KEY`/`MARK_ACTION_PRESS` at the top of the script.

## 6. How to stop and analyze

Stop the Lua script (or just stop playing) once TARGET_BEGIN,
TARGET_END, and a few seconds of surrounding context (before AND
after) have been captured. Then run the analyzer CLI directly:

```
python -m gcrts.spu_trace_analyzer spu_playback_trace.jsonl
```

This prints the full report: trace integrity, paired TARGET_BEGIN/
TARGET_END runs, Control A (silence before)/Control C (post-dialogue)
derived automatically from the same markers, target SPU/CD activity in
both the tight (±250ms) and context (±2s) windows, mixer state, and a
classification with a cited confidence level. Pass multiple trace
files (one per repeated run) for the cross-run correlation section:

```
python -m gcrts.spu_trace_analyzer run1.jsonl run2.jsonl run3.jsonl
```

For programmatic use, the same building blocks are directly callable:
`pair_target_runs`, `tight_window`/`context_window`/`control_windows`,
`assess_instrumentation_health`, `classify_playback_from_trace`,
`correlate_heartbeats_with_resolver` (to see which `AudioAsset`, if
any, the CD position resolved to in the same window -- correlation
evidence, never the classification's own basis, section 2's
methodological constraint), and `correlate_runs`.

## 7. How to extract a candidate SPU sample

Only meaningful if `classify_playback_from_trace` returns
`SPU_VOICE_PLAYBACK` with a real voice index and start address from a
`SpuKeyWriteEvent`. `gcrts.spu_trace_analyzer.attempt_spu_sample_
extraction(voice_index, start_address_units_of_8)` checks this
project's own confirmed tooling limitation
(`spu_internal_ram_directly_inspectable()`) first and refuses cleanly
with an honest reason rather than fabricating sample bytes -- **as of
this milestone, that check still returns `False`** (re-confirmed via
primary-source Lua FFI evidence, section 3), so this function will
currently always report `available=False`. It is left in place,
explicit and callable, for the moment a future session finds a real
SPU-RAM-reading channel -- see its own docstring for exactly what
would need to change.

## 8. Experiment design: controls, windows, instrumentation validation, repetition

**Controls.** Control A (silence, immediately before `TARGET_BEGIN`)
and Control C (post-dialogue, immediately after `TARGET_END`) are
derived automatically from the two markers already captured -- no
extra marker press needed, since the tracer runs continuously
(`gcrts.spu_trace_analyzer.control_windows`). Control B (a naturally-
occurring, clearly audible SFX/UI sound) has no dedicated marker in
this tooling; if one occurs in the captured session, it shows up as
ordinary `SPU_KEY_WRITE`/`CD_COMMAND` activity outside the target
run's own window in the report -- this tooling does not require
artificially triggering one.

**Two window widths, never just one.** `tight_window` (`TARGET_BEGIN -
250ms` to `TARGET_END + 250ms`, both configurable) for events tightly
synchronized to the audible line; `context_window` (`TARGET_BEGIN -
2s` to `TARGET_END + 2s`, also configurable) for setup events (CD
seek/read, mixer changes) that precede audible playback.

**Instrumentation validation is mandatory before trusting a negative
result.** `assess_instrumentation_health` requires at least one
`HEARTBEAT` (main-RAM read path alive) and at least one
`SPU_KEY_WRITE` of ANY kind, meaningful or not (the Key ON/OFF
breakpoints have actually fired -- prior sessions found the periodic
sync pair firing constantly, ~9.5 Hz, so a total absence across a real
multi-second session is itself suspicious, not evidence of anything
about the game). `classify_playback_from_trace` applies this gate
**only** to the CD_AUDIO_INPUT/OTHER_OR_UNKNOWN paths (which rest on
an absence of a meaningful Key write) -- a genuinely observed
meaningful Key write is self-certifying and needs no separate proof of
life. When the gate fails, the result is `NOT_YET_CLASSIFIED` with
`instrumentation_not_yet_validated` named explicitly in the evidence
string, never silently folded into a confident negative.

**Repetition and cross-run correlation.** The Lua script's alternating
marker label supports repeating BEGIN/END within one continuous
recording, or across separately saved trace files. `correlate_runs`
builds the comparison table this milestone's brief asked for (same
Key ON voice? same writer PC? same CD command(s)? same LBA region?),
marking each row `stable` only when every run agrees -- distinguishing
deterministic behavior from incidental timing coincidence.

## 9. What evidence distinguishes SPU voice playback from CD audio input

| Evidence | SPU_VOICE_PLAYBACK | CD_AUDIO_INPUT |
|---|---|---|
| Key ON/OFF writer hit with a nonzero voice mask in the marker window | Present (never yet observed for this game's dialogue) | Absent (only the empty/no-op mask, matching every prior capture) -- but ONLY meaningful once instrumentation health passes (section 8) |
| CD-ROM command traffic (`CdCommandEvent`, e.g. `ReadN`/`Setloc`/`GetlocP`) in the context window | Not required either way | Presence alone is NOT sufficient (per this milestone's own rule) -- must align temporally with `TARGET_BEGIN`/`TARGET_END`, not just exist somewhere in the window |
| Position-counter lifecycle state (`gcrts.runtime_audio`) | Not required | `PLAYING` (0x01), or a `SAVE_STATE_LOADED` anchor immediately before the marker (the already-observed "t=0.0s" pattern) |
| Muting all 24 SPU voices (manual, native SPU Debug window) | Would silence the line | Confirmed NOT to silence the line, twice, independently (`gcrts.spu_audio_path.MANUAL_MUTE_EXPERIMENTS`) |
| System DMA channels 3 (CDROM) / 4 (SPU) | Not expected to be involved either way (voice sample delivery is a separate SPU-internal mechanism from system DMA) | Confirmed inactive during a real audible window (`gcrts.spu_audio_path.DMA_TRANSPORT_OBSERVATIONS`) |
| Reproducible across 3 repeated runs (`correlate_runs`) | Raises confidence from MEDIUM to HIGH | Raises confidence from MEDIUM to HIGH |

## 10. Current unresolved questions

- **What is the actual save-slot-9 target line's real source?** Fully
  open again after the `XAPACK22:7` retraction (2026-08-23) -- five
  live-captured candidates were auditioned and rejected. This
  document's tooling exists to answer that with playback-path evidence
  instead of another round of LBA-guessing.
- **The Lua script has not been live-tested this session.** Every API
  call is grounded in this project's own direct read of the real FFI
  source (`src/core/pcsxffi.lua`, `src/core/eventslua.cc`), but no tool
  available to this project can load/run a Lua script inside
  PCSX-Redux's GUI without a human action -- the first real run is the
  natural next experiment (see the status report's own "Next
  experiment" section).
- **`MARK_KEY = 298` (GLFW_KEY_F9) is an assumption**, not
  independently confirmed against this exact PCSX-Redux build. The
  script's own raw-keypress diagnostic logging exists specifically to
  correct this cheaply if wrong.
- **Per-voice configuration writer sites (pitch/volume/ADSR/start
  address) are not yet found** -- only the register layout is verified
  (section 3). If the critical experiment does classify
  `SPU_VOICE_PLAYBACK`, finding these writer sites becomes the natural
  follow-up, not before.
- **SPU-internal RAM remains confirmed uninspectable** through every
  channel this project has access to (GUI, Lua, GDB) -- re-confirmed,
  not newly discovered, this session.
- **The 3 CD-ROM command-write sites now armed (`gcrts.cdrom_setfilter.
  SETFILTER_CALL_SITE_ADDR`/`OTHER_COMMAND_WRITE_SITES`,
  `gcrts.cdrom_driver_map.COMMAND_ISSUE_ROUTINE_ADDR`) previously
  produced only Sync (`0x00`) hits from the OLD, now-superseded
  `0x80081C00` entry point in one prior milestone -- the corrected 3
  sites (see `gcrts.cdrom_setfilter`'s own docstring) found real,
  varied command traffic including one live Setfilter hit. Whether
  this new experiment's continuous, marker-anchored capture catches
  meaningful command traffic during the actual target window is an
  open question this milestone's live run will answer, not assumed.
- **Live validation checklist for the FIRST real run** (see the
  companion status report's own "Live validation result"): script
  loads without error; heartbeat events appear in the JSONL; a marker
  keypress produces both the diagnostic log line and a `MARK` event in
  the file; the trace survives a save-state load without breaking;
  timestamps stay monotonically non-decreasing throughout. All five
  must pass before any classification from a real session is trusted.
