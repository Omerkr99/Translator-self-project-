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
3. Confirm the Lua console/log shows: `SPU Playback Trace armed: 8
   breakpoints, heartbeat + save-state + marker listeners active.
   Writing to spu_playback_trace.jsonl. Press the marker key (default
   F9) when the target dialogue is heard.`

## 5. How to create a marker

Press **F9** (the script's `MARK_KEY` default, `GLFW_KEY_F9 = 298`,
`GLFW_PRESS = 1` -- both standard, stable GLFW constants, but **not
independently live-verified against this specific PCSX-Redux build
this session**) while the target dialogue line is audible. This is
PCSX-Redux's own application receiving a real physical keypress -- a
genuinely different channel from the already-confirmed-broken
"synthetic input into the emulated game controller" problem
(`gcrts.pcsx_spu_observer.synthetic_input_reaches_game_controller()`
-> `False`); it does not need to reach the emulated console at all,
only the host application, the same way PCSX-Redux's own menu
shortcuts already work.

**If F9 does not produce a `MARK recorded` log line**: every real
keypress is logged as `SPU Playback Trace: keyboard event key=<N>
action=<N>` (a diagnostic line, not written into the JSONL trace).
Check the console for the real `key`/`action` values and update
`MARK_KEY`/`MARK_ACTION_PRESS` at the top of the script.

## 6. How to stop and analyze

Stop the Lua script (or just stop playing) once a marker plus a few
seconds of surrounding context have been captured. Then, in Python:

```python
from gcrts.spu_playback_trace import load_trace
from gcrts.spu_trace_analyzer import events_near_marker, first_marker, classify_playback_from_trace

events = load_trace("spu_playback_trace.jsonl")
marker = first_marker(events)
window = events_near_marker(events, marker, before_seconds=2.0, after_seconds=2.0)  # configurable, not hardcoded
result = classify_playback_from_trace(window)
print(result.classification, "--", result.evidence)
```

To also see which `AudioAsset` (if any) the CD position resolved to
during the same window -- correlation evidence, never the
classification's own basis (section 2's methodological constraint):

```python
from gcrts.spu_trace_analyzer import correlate_heartbeats_with_resolver
disc_bytes = open(DISC_PATH, "rb").read()
for c in correlate_heartbeats_with_resolver(window, disc_bytes):
    print(c.heartbeat.t, c.resolution.confidence, c.resolution.asset)
```

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

## 8. What evidence distinguishes SPU voice playback from CD audio input

| Evidence | SPU_VOICE_PLAYBACK | CD_AUDIO_INPUT |
|---|---|---|
| Key ON/OFF writer hit with a nonzero voice mask in the marker window | Present (never yet observed for this game's dialogue) | Absent (only the empty/no-op mask, matching every prior capture) |
| Position-counter lifecycle state (`gcrts.runtime_audio`) | Not required | `PLAYING` (0x01), or a `SAVE_STATE_LOADED` anchor immediately before the marker (the already-observed "t=0.0s" pattern) |
| Muting all 24 SPU voices (manual, native SPU Debug window) | Would silence the line | Confirmed NOT to silence the line, twice, independently (`gcrts.spu_audio_path.MANUAL_MUTE_EXPERIMENTS`) |
| System DMA channels 3 (CDROM) / 4 (SPU) | Not expected to be involved either way (voice sample delivery is a separate SPU-internal mechanism from system DMA) | Confirmed inactive during a real audible window (`gcrts.spu_audio_path.DMA_TRANSPORT_OBSERVATIONS`) |

## 9. Current unresolved questions

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
