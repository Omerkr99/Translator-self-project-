# PCSX-Redux SPU Observation Channel

Milestone goal: tooling-first. The SPU-Side XA Playback Discovery
milestone's own follow-up proved GDB's memory read/write path for the
SPU hardware I/O range (`0x1F801xxx`) does not round-trip even a
debug-issued write while genuinely running -- meaning no conclusion
about real SPU register state drawn from raw GDB peeks can be trusted.
Before returning to voice-capture research, build a reliable,
non-GDB way to observe true SPU hardware state. New module:
`gcrts/pcsx_spu_observer.py`, `tests/test_pcsx_spu_observer.py` (18
tests after the crash-loop/synthetic-input follow-up, below).

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

**592 passed** (588 baseline + 4 new in `test_pcsx_spu_observer.py`,
now 18 total in that file), no regressions.

## Follow-up: a real crash-loop bug, and a hard synthetic-input limit

Attempting the channel-isolation next step (comparing SPU state across
successive dialogue lines) surfaced two genuine, separate findings.

**A reproducible crash loop.** The process began faulting on every
resume: `cause` register decoded to exception code 10 (Reserved
Instruction), PC stuck at `0xA0010000` (the low-RAM exception-vector
area) on every subsequent stop. Neither reloading the save state nor
an in-emulator Hard Reset fixed it — the same fault recurred
immediately both times. The save file itself was checked and
confirmed byte-identical (matching MD5) to the version in this
project's very first git commit, ruling out a corrupted save. The
fault lived in the running process's own accumulated internal state
(plausibly from the many GDB attach/detach cycles this whole
project's live-capture sessions perform) and was only resolved by
fully closing and relaunching the PCSX-Redux process.
`gcrts.pcsx_spu_observer.crash_loop_requires_full_process_restart()`
→ `True`.

**Synthetic keyboard input does not reach the game.** After the fresh
restart, emulation was confirmed genuinely healthy (real FPS/audio-
buffer stats, frames verifiably changing frame-to-frame) but no
synthetic key press (`keybd_event` with Circle or Cross; `SendInput`
with a raw scancode; each preceded by explicit window/click focus)
advanced dialogue — while the user's own real physical key press did,
immediately. The same synthetic-input mechanisms reliably drive
PCSX-Redux's own ImGui menus (menu clicks, Solo/Mute buttons all
worked throughout this investigation), so this is specific to the
emulated controller's input path, most likely reading raw/low-level
input state that filters out OS-injected synthetic events by design.
`gcrts.pcsx_spu_observer.synthetic_input_reaches_game_controller()`
→ `False`. This explains why the earlier "Live Audible Trigger
Correlation" milestone's automated triggers worked in that session but
could not be reproduced later in this one — a real environmental
constraint, not a regression in this project's own code.

## Remaining blocker before Audio Inspector

No single SPU voice channel has been isolated as specifically
responsible for dialogue audio, since background music/ambience
channels are already active in every "silent" baseline this project
has captured so far. Compounding this, unattended automated dialogue
triggering is no longer reliable in this environment (synthetic input
does not reach the game), so any further live-correlation work needs
either a human physically providing the trigger or a different input
path (e.g. a virtual gamepad/XInput device).

## Next milestone

Build or adopt a synthetic-input path the emulator's controller
backend actually accepts (e.g. a virtual XInput/DirectInput device),
then find or construct a scene genuinely free of background music and
repeat the silent-vs-audible SPU Debug comparison to isolate the
dialogue channel.
