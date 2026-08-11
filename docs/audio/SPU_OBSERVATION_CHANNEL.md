# PCSX-Redux SPU Observation Channel

Milestone goal: tooling-first. The SPU-Side XA Playback Discovery
milestone's own follow-up proved GDB's memory read/write path for the
SPU hardware I/O range (`0x1F801xxx`) does not round-trip even a
debug-issued write while genuinely running -- meaning no conclusion
about real SPU register state drawn from raw GDB peeks can be trusted.
Before returning to voice-capture research, build a reliable,
non-GDB way to observe true SPU hardware state. New module:
`gcrts/pcsx_spu_observer.py`, `tests/test_pcsx_spu_observer.py` (14
tests).

## PCSX-Redux observation capability

PCSX-Redux ships a **native, built-in SPU debugger** -- no Lua
scripting, no source patch, no external instrumentation needed. Menu
path: `Debug -> SPU -> Show SPU debug`. It opens a dockable ImGui
window titled `"SPU Debug"` showing, per psx-spx-documented register:

| Section | Fields |
|---|---|
| `SPU` | `IRQ`, `CTRL` (SPUCNT), `STAT` (SPUSTAT), `MEM` |
| `XA` | `Frequency`, `Stereo`, `Samples`, `Volume L`, `Volume R` |
| `Channels` (all 24 voices) | On/Off/Mute/Solo, Noise/FMod, a live waveform `Plot`, Frequency (Active/Used), Position (Start/Current/Loop) |

This capability table, per the milestone's own required format:

| Feature | Available? | API/UI | Automatable? | Reliable? |
|---|---|---|---|---|
| Built-in SPU debugger window | Yes | `Debug > SPU > Show SPU debug` (ImGui menu) | Yes, via mouse-click automation (see below) | Yes -- confirmed against a real, independently-verified state change |
| Lua scripting (`PCSX.getMemPtr`, `PCSX.Events`, `PCSX.WebServer.Handlers`) | Yes (already used by this project's `gcrts_runtime_probe.lua`) | Debug > Show Lua Console/Editor | Requires the same GUI menu interaction to load a script; no remote Lua-exec HTTP endpoint was found | Not evaluated this pass -- the native SPU debugger made it unnecessary |
| Web API SPU/Lua-exec endpoint | No | -- | -- | -- (probed `api/v1/lua`, `/lua/exec`, `/execute`, `/eval` -- all 404) |
| Raw GDB memory peek of `0x1F801xxx` | Yes, but wrong | GDB remote `m`/`M` | Yes | **No** -- confirmed unreliable, see `SPU_AUDIO_PATH_DISCOVERY.md`'s follow-up section |

## Validation

Opening the window once (menu path above) makes it a genuine,
separately-titled OS window (confirmed via `EnumWindows`), safely
screenshot-automatable. Every capture in this pass used an
abort-on-unfocus pattern: re-verify the target window is still the
true foreground window immediately before, and again immediately
after, `GetWindowRect`/`ImageGrab.grab` -- discarding rather than
saving if focus moved during the sequence. This guard exists because
of a real incident this same session: a blind screenshot attempt
(before the guard existed) nearly saved an unrelated, private window's
content; both accidental captures were deleted immediately without
being acted on, and the guard was added before any further automated
capture.

**Proven live, not just present**: captured the window twice, ~3 real
seconds apart, with execution independently verified to be genuinely
running throughout (RAM position counter climbing). Channel 0
transitioned to "On" with a real waveform appearing in its `Plot`
column between the two captures, and `Position/Current` advanced for
most channels -- direct proof this window reflects true, live-changing
hardware state, not a frozen or cached display.

## GDB comparison

At the same live instant: GDB's `read_memory(0x1F801DAA, 2)` (SPUCNT)
returned `0x0000`; the native tool's `CTRL` field showed `0xC081`
(bit 0, CD Audio Enable, genuinely set). **`STAT` (SPUSTAT) agreed
with GDB's read at `0x0000` in the same comparison** -- this is not a
blanket "GDB can't read `0x1F801xxx` at all" failure, it's specific to
(at least) SPUCNT. `gcrts.pcsx_spu_observer.gdb_spucnt_read_confirmed_wrong()`
→ `True`.

## SPUCNT

`0xC081` -- bit 0 (CD Audio Enable) set, per psx-spx. Confirmed
**identical** in both the silent-baseline and the user-confirmed-
audible capture (below): CD Audio Enable is evidently a persistent,
always-on state in this game, not something that toggles per dialogue
line. This directly reverses `gcrts.spu_audio_path`'s earlier "the
write does not persist" finding -- `CD_init`'s effect (or an
equivalent) genuinely IS live on real hardware; only GDB's read of it
was wrong. It also explains, retroactively, why the live-correlation
experiment never caught `CD_init` firing during a confirmed-audible
window: the bit was almost certainly already set well before that
capture began, so there was no new "firing" left to observe.
`gcrts.pcsx_spu_observer.cd_audio_enable_confirmed_persistent_via_native_tool()`
→ `True`.

## CD input

The `XA` block (`Frequency=37800` Hz -- a genuine PS1 XA-ADPCM sample
rate; `Volume L/R=32767`; `Samples=2016`) was byte-identical in both
the silent-baseline and audible captures. Consistent with a fixed,
persistently-configured parameter set rather than a moment-by-moment
streaming counter; this pass could not distinguish "actively
streaming XA-ADPCM" from "configured but currently idle" from these
fields alone.

## Active voices

Roughly channels 0-13 already showed active waveforms in the
**silent-baseline** capture (taken immediately after a save-slot-9
reload, before any input) -- consistent with persistent background
music/ambience layers running underneath dialogue, not true silence.
After a real, automated trigger (`Keyboard_PadCircle`/'D') the user
explicitly confirmed as audible, `Position/Current` advanced across
most active channels, but **no single channel could be honestly
isolated as "the dialogue voice channel"** from this one before/after
pair, since the baseline was already busy.
`gcrts.pcsx_spu_observer.single_voice_channel_isolated_for_dialogue()`
→ `False`.

## DMA/transfer

Not exposed in this debug window; not investigated this pass.

## Audible correlation

Exact synchronized result: baseline captured immediately post-load →
real automated trigger (20 presses, ~11s) → capture immediately after
→ user explicitly confirmed hearing a real voice line during that
exact window (`AskUserQuestion`, answer: "Yes, I heard a voice line").
`CTRL`/`XA` block unchanged between the two captures; per-channel
`Position/Current` values advanced.

## Playback backend

Still not newly classified with a `*_CONFIRMED` value this pass --
`gcrts.spu_audio_path.classify_playback_backend()` remains `UNKNOWN`.
What changed is the confidence behind the `CD_INPUT` hypothesis: CD
Audio Enable is now confirmed, via a trustworthy channel, to be
genuinely and persistently set during real gameplay including a
confirmed-audible window -- a real, positive (if not yet exclusive)
signal, no longer undermined by "the write doesn't even persist."

## XAPACK relationship

Not re-traced this pass; unaffected by these findings.

## Runtime integration

None added. This observation channel is screenshot/GUI-based, not yet
a structured, machine-readable data source -- no `RuntimeSnapshot`
field or Visual Inspector panel was built this pass.

## Tests

**588 passed** (574 baseline + 14 new in `test_pcsx_spu_observer.py`),
no regressions.

## Remaining blocker before Audio Inspector

No single SPU voice channel has been isolated as specifically
responsible for dialogue audio, since background music/ambience
channels are already active in every "silent" baseline this project
has captured so far.

## Next milestone

Find or construct a scene/state with genuinely no background
music/ambience active, then repeat this same silent-vs-audible SPU
Debug comparison to isolate the one channel (if any single channel)
responsible for dialogue playback.
