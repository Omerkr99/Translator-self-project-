"""SPU-Side XA Playback Discovery milestone: pivots from the exhausted
CD-ROM command-side search (`gcrts.xa_playback_path`,
`gcrts.cdrom_driver_discovery`) to the SPU side -- what SPU hardware
state changes during real playback, traced backward to its writer.

## What this milestone found

A full-RAM raw-value scan for the SPU base address (`0x1F801C00`)
found **7 pointer-holder addresses** storing that exact value:
`0x8001587C`, `0x800A30CC`, `0x800A32C0`, `0x800A38A8`, `0x800A3BCC`,
`0x800A3BD0`, `0x800A3BDC`. `0x800A30CC` sits immediately adjacent to
the already-known, already-understood CD-ROM 4-register pointer block
(`0x800A30BC`-`0x800A30C8`).

### `CD_init` -- a real, named, live-firing function

Static tracing from `0x800A30CC` led to a function at
`0x80081B04`-`0x80081BCC` that:

  - reads back Current Main Volume L/R (`+0x1B8`/`+0x1BA`); sets Main
    Volume L/R (`+0x180`/`+0x182`) = `0x3FFF` only if not already set
  - unconditionally sets CD Volume L/R (`+0x1B0`/`+0x1B2`) = `0x3FFF`
  - unconditionally sets SPUCNT (`+0x1AA`) = `0xC001`

The game's own debug string, referenced a few instructions earlier in
the same function, is literally `"CD_init:addr=%08x\\n"` -- this is the
game's own CD-audio-init routine, not a guessed label.

**Confirmed live** across two separate capture sessions
(`m14_arm_spucnt.py`: 18 hits / 3961 interrupts over ~560s;
`m15_combined_watch.py`: 0 hits over 300s in a session where it simply
never got invoked) that `CD_init` genuinely executes during real
gameplay -- 6 total observed firings, not a one-time boot-only init.
Per psx-spx, **SPUCNT bit 0 is documented as "CD Audio Enable" (0=Off,
1=On), controlling both CD-DA and XA-ADPCM streaming into the SPU
output** -- `0xC001` has that bit set. A full-RAM scan for writers of
SPUCNT's offset (`+0x1AA`) across all 7 base holders found 9 call
sites into `CD_init` (`0x80080428`, `0x80081308`, `0x80081548`,
`0x80081928`, `0x80081D28`, `0x80081E50`, `0x80082064`, `0x800824F0`,
`0x80082724`), plus a second, much larger writer family (see below).

### The write does not persist

In both capture sessions, reading SPUCNT/CD-Volume/Main-Volume
immediately before the *next* `CD_init` firing, and in `m14`'s final
post-loop snapshot taken after the loop's last write had already been
allowed to execute, **all three registers read back `0x0000`/
`0x00000000` every single time** -- never once observed holding
`CD_init`'s own `0xC001`/`0x3FFF` values on a later read. Something
resets them (or the write does not stick) faster than this project's
poll granularity has yet caught. This is recorded as a genuine open
question, not swept under the "it must be working" assumption.

### A second, much larger SPU writer family (`0x800A38A8`)

The same `+0x1AA` writer scan found 18 total sites; 17 of them cluster
around base `0x800A38A8`, spanning a much larger code region
(`0x8008E748`-`0x80090A14`, roughly 9 KB). Direct disassembly of the
first site (`0x8008E744`-`0x8008E7D0`) shows a generic
read-AND-clear-bits/delay-loop/read-OR-restore-bits pattern touching
SPUCNT bits `0x8030` (not bit 0) -- consistent with a general-purpose
SPU control/reset utility used broadly across the game's whole SPU
subsystem, not something CD-audio-specific. This family is `0x800A38A8`
in the taxonomy below.

### Key ON / Key OFF activity

A writer scan for SPU Key ON (`+0x188`) and Key OFF (`+0x18C`) found 5
real call sites: one pair at base `0x800A32C0` (writers at
`0x800866A0`/`0x800866A8`, called from a single site `0x8008664C`), and
three at base `0x800A38A8` (`0x8008E934`, `0x8008E9D8`, `0x8008EB84`).

Live-armed for 300s across a real save-slot-9 reload
(`m15_combined_watch.py`): the `0x800A32C0` pair fired constantly
(2657/2659 hits -- a roughly 9.5 Hz periodic call), but **5312 of 5316
total hits carried `a0=0x0`** (an empty voice bitmask -- a no-op sync,
not a real trigger). The only nonzero hits (`a0=0x4` then `a0=0x3`,
both within 4 seconds of the state-slot load) are far more consistent
with a UI/menu confirmation blip than a sustained dialogue-voice
segment. The `0x800A38A8` Key ON/OFF sites never fired at all in this
session. `CD_init`'s SPUCNT write also never fired in this same
300-second window, despite firing reliably in the earlier session --
confirming it is conditional on some game state this project has not
yet isolated, not a guaranteed per-load event.

## Honest conclusion (original pass)

Neither hypothesis achieved a clean, live, user-confirmed audible
correlation within a single capture window this pass. `CD_init` is
real, live-firing, and demonstrably touches the one hardware bit
psx-spx documents as gating CD-audio-to-SPU streaming -- the strongest
concrete anchor this project has found across all six audio milestones
so far. But its write not persisting, and the total absence of a
same-session "armed breakpoint + real audible confirmation" capture,
means the actual playback backend is **not yet confirmed** either way.

## Follow-up: Live Audible Trigger Correlation experiment

Closed the exact gap the previous pass left open -- a capture window
combining armed breakpoints AND a real, user-confirmed audible line.
Used the project's own established automated-input technique
(`Keyboard_PadCircle` = `0x44`/'D', per `pcsx.json`, the confirmed
confirm/advance button from an earlier session) to trigger dialogue
deterministically from save-slot 9, with `CD_INIT_SPUCNT_WRITE` and all
5 known Key ON/OFF sites armed *before* the trigger.

**Run 2 result (decisive):** the user confirmed hearing a real voice
line during the exact ~24-second captured window. `script_parameter`/
`position_counter`/`source_file` genuinely changed across the window
(`XAPACK42.BIN@182935` -> `XAPACK20.BIN@158842`), proving the
automated input reached the game. **Zero** of the 6 armed sites fired
meaningfully: `CD_INIT_SPUCNT_WRITE` never fired at all; the
`0x800A32C0` Key ON/OFF pair fired 814/815 times, every single one
`a0=0x0` (no-op); the `0x800A38A8` sites never fired. This is a real,
CPU-register-level-confirmed negative result (register reads via `g`
are unaffected by the finding below) -- per this milestone's own Phase
8, the conclusion is stated directly: **audible playback in this
observed instance is not triggered through any of these known SPU
writer sites at event start.**

### A second, independent finding: the SPU MMIO read/write channel itself is unreliable

While attempting Phase 9/10 (poll the full SPU register block during
the confirmed-audible window), the poll showed **zero byte-level
change across all 640 bytes** (24 voices + control registers) for the
entire session. Before trusting that as a real negative, a direct
diagnostic was run: write `0x3FFF` to Main Volume (`0x1F801D80`) via
GDB, then read it back -- **while independently verified to be
genuinely, continuously running** (RAM position counter climbing every
second under a corrected continue-loop). The write did **not**
round-trip: readback was `0x0000` immediately and still `0x0000` a
full second later. Plain RAM writes (a scratch address) round-tripped
perfectly in the same session, and the KSEG1 uncached mirror
(`0xBF801D80`) showed the same stuck-zero behavior. **Conclusion: GDB's
memory read/write path for the SPU hardware I/O range
(`0x1F801xxx`) does not reflect true emulated hardware state in this
PCSX-Redux build** -- most likely because its debug-memory bridge
proxies only the main 2MB RAM array, not each peripheral's internal
register file. This is a genuine, confirmed **tooling limitation**, not
a game-behavior fact.

This *retroactively reclassifies* the original pass's "the write does
not persist" finding: it was never established that `CD_init`'s write
fails to persist on the real emulated hardware -- only that this
project's chosen read channel cannot verify it either way. Every
previous "SPU register reads back 0" observation across this whole
investigation (this module and its predecessor passes) inherits the
same caveat. By contrast, every finding based on **CPU register
reads** at breakpoint hits (the command/value actually loaded into
`$v0`/`$a0` at the exact write instruction) remains fully valid and
unaffected -- that read path (`g`, GDB's register-read command) has
been reliable throughout this entire project.

## Honest conclusion (superseded -- see below)

Per this milestone's own required taxonomy, this stayed classified
`UNKNOWN` -- not `XA_ADPCM_CONFIRMED`, not `SPU_SAMPLE_PLAYBACK` --
but the reasoning was stronger and more precise: a real capture
window with a user-confirmed audible trigger WAS achieved, and it
decisively ruled out the known writer sites as the mechanism for that
specific instance. What remained open was not "did we ever catch the
right moment" but "what mechanism actually is responsible," compounded
by a confirmed inability to directly verify SPU hardware register
state through this project's GDB-based tooling.

## Follow-up: manual all-voices-muted experiment -- the decisive result

Using PCSX-Redux's native SPU Debug window (`gcrts.pcsx_spu_observer`,
`Debug > SPU > Show SPU debug`) and its per-voice Mute/Solo controls,
the user manually muted every SPU voice channel that showed any
activity at the moment of a real, triggered dialogue line, working
directly and repeatedly rather than through this project's own
automation (synthetic-input limitations made automated triggering
unavailable this pass -- see `docs/tooling/PCSX_REDUX_CAPTURE_PROTOCOL.md`
section 8). **With every regular SPU voice channel muted, the spoken
dialogue line continued to play, completely unaffected.** This was
independently reproduced a second time, in a different scene the user
had initially suspected was a pre-rendered movie/FMV segment -- same
result: muting all 24 regular voices did not silence or alter the
voice line at all.

This is the single most decisive finding of this entire investigation
chain. It directly proves the dialogue audio is **not** being mixed
through the SPU's normal 24-voice engine -- if it were, muting every
voice would silence it. The audio must be entering through a path that
bypasses per-voice mixing entirely, which on real PS1 hardware means
exactly one thing: **the CD input path** -- the same mechanism gated by
SPUCNT bit 0 (CD Audio Enable), which this project has already
confirmed, via the trustworthy native SPU debugger, to be genuinely
and persistently set (`gcrts.pcsx_spu_observer.cd_audio_enable_confirmed_persistent_via_native_tool()`
-> `True`, `docs/audio/SPU_OBSERVATION_CHANNEL.md`). This does not by
itself prove the stream format is XA-ADPCM specifically (CD-DA is
structurally ruled out on this disc, per `XA_PLAYBACK_PATH.md` --
XA-ADPCM is the only real remaining candidate for what the CD input
path could be carrying, but that inference is architectural, not
independently re-verified this pass) -- so the classification below
uses the taxonomy's own `CD_INPUT_UNKNOWN_FORMAT` value rather than
overclaiming `XA_ADPCM_CONFIRMED`.

## Honest conclusion (superseded -- see below)

`classify_playback_backend()` returned `CD_INPUT_UNKNOWN_FORMAT`,
backed by direct, repeated, hands-on evidence (not architectural
inference): the dialogue-carrying audio survives every regular SPU
voice being muted, in two independently tested scenes.

## Follow-up: chasing the exact CD input stream format -- two more negatives, no format confirmation yet

With the routing mechanism (CD input, bypassing SPU voices) established,
this pass tried to independently confirm the stream format is
XA-ADPCM by tracing forward from `CD_init`'s own callers.

**Static analysis found real structure**: of `CD_init`'s 9 call sites,
7 share an identical "log + call + check return code" pattern
consistent with generic retry-after-error logic. Two
(`0x80081D28`, `0x80082064`) are different -- they poll a CD-ROM
"not busy" flag (`0x800A2E14` bit 4), then compare a cached position
(`0x800A2E18`) against a live target (`0x800A3120`), calling `CD_init`
**only when that target changed**. This looked like the real
per-event trigger this project had been missing.

**Live-armed across a real, user-triggered voice line: zero hits.**
Neither gatekeeper call site fired despite the user confirming the
line played, reproduced across two separate trigger attempts. This is
consistent with (not contradicting) the already-established finding
that CD Audio Enable is a persistent, scene-level state, not something
re-armed per dialogue line -- `CD_init` genuinely is not the per-line
trigger, confirmed from a second angle.

**Re-armed the original 3 known CD-ROM command-write sites, logging
every single `Setmode` value (not just the first one found in an
earlier milestone) across ~150 real seconds spanning a confirmed voice
line: 46 Setmode captures, every single one `mode_byte=0x01` -- XA-ADPCM
and XA-Filter bits both off, 100% of the time.** This is a far more
statistically decisive version of the same negative result
`AUDIO_PLAYBACK_TRUTH.md` first found from a single sample. A
methodological note from this same capture: the second breakpoint site
(`0x80081AC8`) showed `$v0` sweeping through every value from `0x00` to
`0x80` in strict sequence during one interval -- clearly a loop
counter incidentally passing through that PC's register, not 129 real
CD-ROM commands. Reading a shared breakpoint site's register as "the
command" is only valid when the calling convention is actually known
to put a command there; this is recorded so a future pass doesn't
mistake register noise for command traffic again.

## Honest conclusion (superseded -- see below)

`classify_playback_backend()` stayed `CD_INPUT_UNKNOWN_FORMAT` -- the
routing finding (CD input bypasses SPU voices) remained this project's
strongest, most direct evidence. What that pass added was two further
negatives on the *format*-confirmation side: neither `CD_init`'s real
per-event trigger candidates nor the already-known Setmode dispatch
site ever show XA-ADPCM being enabled, even during confirmed real
playback.

## Follow-up: DMA data-path investigation -- the real transport found

Per the explicit instruction to stop chasing Setmode/`ReadS` and
instead ask what actually *feeds* CD Input during a confirmed audible
line, this pass used PCSX-Redux's native `Debug > Misc hardware > Show
HW Registers` window -- a reliable, non-GDB channel exposing all 7
system DMA channels' `MADR`/`BCR`/`CHCR` plus the 3 hardware timers,
found by inventorying the Debug menu rather than assuming raw GDB MMIO
was the only option.

With a save state positioned right at a confirmed voice-line moment,
and the emulator genuinely, continuously running (verified via
Timer 1's own counter changing across every captured frame -- not
just an "interrupts happened" proxy, an actual elapsed-time signal),
**DMA channel 3 (CD-ROM) and DMA channel 4 (SPU) showed zero change
whatsoever across the entire captured window** -- `MADR`, `BCR`, and
`CHCR` all stayed byte-identical from the first frame to the last.
This is not an absence-of-execution artifact: DMA channel 2 (GPU), in
the same captures, showed a real, distinct transfer-completion pattern
(`MADR` hitting `0xFFFFFF`, `BCR` dropping to `0`, `CHCR`'s busy-adjacent
bit shifting), exactly as expected for a game that keeps rendering
frames throughout.

**This directly answers the milestone's core question.** Whatever
carries the confirmed audible dialogue, it does not move through the
system DMA controller's CD-ROM or SPU channels at all -- no `MADR`
advances, no transfer-size decrements, no busy-bit toggling, for the
entire window a real voice line was known to be playing. Combined with
the earlier finding that no regular SPU voice carries the dialogue
either (`all_spu_voices_muted_dialogue_still_audible()`), this is
consistent with a genuine PS1 hardware fact this project had not yet
confirmed directly: CD-ROM audio output (CD-DA/XA-ADPCM alike) is
typically wired to the SPU's CD Input as a **direct hardware audio
bus**, separate from the general-purpose DMA controller entirely --
DMA channel 3 exists for transferring CD-ROM *sector data* into main
RAM (used for loading game assets), which is architecturally a
different signal path from the CD-ROM's own decoded audio output
feeding straight into the SPU's mixer. This pass did not independently
re-verify that specific PS1 architectural claim beyond what the DMA
observation itself rules out (no DMA involvement), so it is recorded
as the leading interpretation of solid negative evidence, not as an
independently proven mechanism.

## Honest conclusion (current)

`classify_playback_backend()` stays `CD_INPUT_UNKNOWN_FORMAT`. The new
DMA evidence does not change the classification, but it substantially
narrows what "CD input" means in practice: it is confirmed **not**
DMA-mediated through channels 3 or 4, on top of the earlier
confirmation that it is not routed through any of the SPU's 24 regular
voices either. `TransportPath` and `StreamFormat` are now modeled as
explicitly separate concepts (see below) rather than folded into one
enum, per this milestone's own instruction -- the transport question
(how does the data physically move) is now reasonably well-understood;
the format question (is it really XA-ADPCM, and if so how is it
decoded) remains genuinely open.

## Follow-up: SPU-internal RAM inspection -- a confirmed tooling blocker

The previous milestone's own "next task" was to find a way to inspect
the PS1 SPU's internal 512KB sound RAM directly (distinct from its
MMIO-mapped control registers, already covered above). Every avenue
this project has access to was checked and closed:

- **PCSX-Redux's GUI Memory Editor windows** (the 8 generic "Memory
  Editor #1"-"#8" slots, plus the named presets for Parallel Port,
  Scratch Pad, Hardware Registers, BIOS, and VRAM): none offer a
  memory-space/buffer selector. The "Options" dropdown on a Memory
  Editor window is display formatting only (column count, hex casing,
  ASCII panel toggle, zero-greying) -- confirmed live via screenshot.
  There is no SPU RAM preset among the named editors.
- **The native "SPU Debug" window itself**: its full layout is exactly
  three collapsible sections -- `SPU` (IRQ/CTRL/STAT/MEM),
  `XA` (Frequency/Stereo/Samples/Volume L/R), and `Channels` (per-voice
  On/Off/Mute/Solo/waveform/frequency/position) -- confirmed via a
  full-window screenshot. No raw memory/hex byte view exists anywhere
  in it.
- **PCSX-Redux's documented Lua scripting API**
  (`pcsx-redux.consoledev.net/Lua/{memory-and-registers,redux-basics,
  introduction,case-studies,libraries}`, fetched and checked directly):
  the documented memory accessors are `PCSX.getMemPtr()` (up to 8MB
  main RAM), `PCSX.getParPtr()` (EXP1/parallel port), `PCSX.getRomPtr()`
  (BIOS), `PCSX.getScratchPtr()` (1kB scratchpad), `PCSX.getRegisters()`
  (CPU registers), and `PCSX.getReadLUT()` (the CPU's read
  lookup table) -- none of these reach SPU RAM. The only SPU-adjacent
  Lua functions found (`Adpcm:processSPUBlock()`/`:finishSPU()`) are an
  **offline ADPCM encoder utility** for authoring sample data, unrelated
  to reading live emulator state.
- **GDB's own SPU MMIO read/write path**: already independently
  confirmed unreliable (stuck-zero readback on a debug-issued write)
  on *both* the direct KUSEG address (`0x1F801D80`) and the KSEG1
  uncached mirror (`0xBF801D80`) -- see the SPU MMIO section above.
  This closes the one remaining theoretical route too: manually driving
  the real-hardware Sound RAM Data Transfer Address/FIFO protocol
  (`0x1F801DA6`/`0x1F801DA8`) to read SPU RAM the way real hardware
  does would itself require a working SPU register write path, which
  this project's GDB channel does not have.

**Conclusion: SPU-internal RAM content is not inspectable through any
tool available to this project** (GUI, Lua scripting, or GDB). This is
recorded as a genuine tooling limitation, not a game-behavior fact --
see `spu_internal_ram_directly_inspectable()` below.

## Follow-up: the SPU Debug window's own XA panel does not correlate with dialogue either

While confirming the RAM-inspection dead end, the SPU Debug window's
`XA` section (Frequency/Stereo/Samples/Volume L/R) stood out as a
field this project had not previously captured in detail -- a
screenshot taken during active gameplay showed `Frequency: 37800`, one
of the PS1's two standard XA-ADPCM sample rates, alongside `Stereo: 1`
and non-zero `Samples`/`Volume` fields. This looked like a promising
direct format signal, worth testing before concluding.

Two independent live burst captures were run (60 frames at ~1fps each,
screenshotting the "SPU Debug" window, with a self-resuming GDB
continue loop keeping the emulator genuinely running throughout --
verified via per-channel `Position/Current` values actively changing
across frames in both captures):

- **First capture**: save slot 6 loaded (positioned just before a
  confirmed voice line), 60 frames captured. A user-triggered line was
  reported to have occurred during this window, but without a specific
  timestamp. `XA` panel values were byte-identical across all sampled
  frames (0, 10, 20, 30, 45, 59): `Frequency 37800 / Stereo 1 /
  Samples 2016 / Volume L 32767 / Volume R 32767`. The `SPU` panel's
  `MEM` field was likewise static the entire capture at `494288`.
- **Second capture**: save slot 6 reloaded fresh for a cleanly timed
  attempt. The user confirmed triggering the voice line **9-10 seconds**
  into this capture. Frames spanning the full window before, at, and
  well after that trigger (0, 8, 10, 13, 17, 20, 40-42, 45, 50) were
  inspected: the `XA` panel values were **again byte-identical across
  every single frame** in the entire 60-second capture --
  `Frequency 37800 / Stereo 1 / Samples 2016 / Volume L 32767 /
  Volume R 32767`, unchanged through the trigger moment and the
  several seconds after it where the line would have been playing. The
  `SPU` panel's `MEM` field did change once, from `482580` (frames
  0-40) to `494288` (frames 42 onward) -- but that transition lands
  ~30 seconds after the reported 9-10s trigger, and `494288` is the
  same value the *entire first capture* sat at regardless of any
  trigger, making a generic post-load settling artifact the more
  plausible explanation than a dialogue-driven event.

**Conclusion**: the SPU Debug window's live `XA` panel and `MEM`
field -- despite showing a real, non-zero, standard-XA-ADPCM-rate
`Frequency` value at all times -- do not visibly react to a confirmed,
precisely-timed voice-line trigger. This is consistent with (not
contradicting) the standing finding that dialogue bypasses the
instrumented parts of the SPU pipeline entirely: whatever plays it
does not move the needle on any field this debugger window exposes,
reinforcing rather than resolving the "format still unknown"
conclusion. See `spu_debug_xa_panel_changed_during_confirmed_voice_line()`
below.

## Follow-up: the stream format question, finally resolved -- statically, not live

The "GCRTS XAPACK Raw Format + Audio Asset Discovery" milestone
(`docs/audio/XAPACK_FORMAT.md`, `gcrts.xapack`) deliberately stopped
chasing the format question through live SPU capture and went offline:
a byte-level scan of the real disc's own `XAPACK*.BIN` sectors (not a
debugger reading, not the filename) found every audio-carrying sector,
across all 43 real pack files, shows the exact standard Green Book
CD-XA real-time-audio submode (`0x64`/`0xE4`: Audio+Form2+Realtime,
optionally EOF) with `coding_info=0x01` -- stereo, 37800 Hz, 4-bit
ADPCM. This independently explains the SPU Debug window's own earlier
static `Frequency: 37800`/`Stereo: 1` reading (not meaningless after
all -- an accurate, constant report of the real hardware decode
configuration, just not something that toggles per dialogue event
because the format never changes).

Two real, independently-established live LBA anchors already on
record elsewhere in this project (the confirmed dialogue cue's
observed LBA `126921` with `xa_channel=7`, and a second capture landing
exactly on `XAPACK06.BIN`'s own start LBA) both fall exactly where this
disc-structural model predicts: `126921` lands inside channel 7's own
physically-bounded audio stream in `XAPACK08.BIN` (LBA
`126225`-`129273`, EOF-marker-terminated). Neither anchor was used to
derive the model; both were used only to check it afterward, and both
checks passed -- satisfying this project's own standing bar for
`classify_stream_format()` to finally leave `UNKNOWN` (see
`gcrts.xapack`'s module docstring for the full evidence and the
explicit, honest confidence breakdown on the ADPCM decoder itself).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# All 7 addresses found by the full-RAM scan for the SPU base value
# (0x1F801C00), live-verified to each hold that exact value.
SPU_BASE_POINTER_HOLDERS = (
    0x8001587C,
    0x800A30CC,
    0x800A32C0,
    0x800A38A8,
    0x800A3BCC,
    0x800A3BD0,
    0x800A3BDC,
)

SPU_BASE_VALUE = 0x1F801C00

# Hardware register offsets from the SPU base, per psx-spx.
OFFSET_MAIN_VOL_L = 0x180
OFFSET_MAIN_VOL_R = 0x182
OFFSET_KEY_ON = 0x188
OFFSET_KEY_OFF = 0x18C
OFFSET_CD_VOL_L = 0x1B0
OFFSET_CD_VOL_R = 0x1B2
OFFSET_SPUCNT = 0x1AA
OFFSET_SPUSTAT = 0x1AE
OFFSET_CURRENT_MAIN_VOL_L = 0x1B8
OFFSET_CURRENT_MAIN_VOL_R = 0x1BA

SPUCNT_CD_AUDIO_ENABLE_BIT = 0x0001  # psx-spx: bit0, gates CD-DA and XA-ADPCM streaming to the SPU

CD_INIT_FUNC_ADDR = 0x80081B04
CD_INIT_DEBUG_STRING = "CD_init:addr=%08x\n"
CD_INIT_SPUCNT_WRITE_PC = 0x80081BB8
CD_INIT_SPUCNT_WRITE_VALUE = 0xC001
CD_INIT_MAIN_VOL_WRITE_PC = 0x80081B90
CD_INIT_CD_VOL_WRITE_PC = 0x80081BAC

CD_INIT_CALL_SITES = (
    0x80080428,
    0x80081308,
    0x80081548,
    0x80081928,
    0x80081D28,
    0x80081E50,
    0x80082064,
    0x800824F0,
    0x80082724,
)


class SpuWriterFamily(str, Enum):
    """Which base-pointer holder a writer site's SPU access traces back
    to -- these behave differently enough (see module docstring) that
    conflating them would hide real structure."""

    CD_INIT = "CD_INIT"  # 0x800A30CC -- CD-audio-enable specific
    GENERIC_SPU_DRIVER = "GENERIC_SPU_DRIVER"  # 0x800A38A8 -- broad, non-CD-specific SPU control
    PERIODIC_VOICE_SYNC = "PERIODIC_VOICE_SYNC"  # 0x800A32C0 -- fires constantly, near-always a no-op


@dataclass(frozen=True)
class SpuWriterSite:
    write_pc: int
    base_holder: int
    family: SpuWriterFamily
    register_offset: int
    live_confirmed: bool
    evidence: str


SPUCNT_WRITER_SITES: tuple[SpuWriterSite, ...] = (
    SpuWriterSite(
        CD_INIT_SPUCNT_WRITE_PC, 0x800A30CC, SpuWriterFamily.CD_INIT, OFFSET_SPUCNT,
        True,
        "Live-armed and hit 6 times across 2 sessions; writes 0xC001 (CD Audio Enable bit set). Write does not persist on later reads -- see module docstring.",
    ),
    SpuWriterSite(
        0x8008E75C, 0x800A38A8, SpuWriterFamily.GENERIC_SPU_DRIVER, OFFSET_SPUCNT,
        False,
        "Static only: clears bits 0x8030 (not CD-audio-enable bit0), runs a ~240-iteration delay loop, then restores them -- a generic reset/mute pulse pattern, not CD-audio specific.",
    ),
)

KEY_WRITER_SITES: tuple[SpuWriterSite, ...] = (
    SpuWriterSite(
        0x800866A8, 0x800A32C0, SpuWriterFamily.PERIODIC_VOICE_SYNC, OFFSET_KEY_ON,
        True,
        "Live-armed 300s: 2657 hits, 2655 with a0=0x0 (no-op). 2 hits with a0=0x4/0x3 immediately after a state-slot load, most consistent with a UI blip, not confirmed as dialogue voice.",
    ),
    SpuWriterSite(
        0x800866A0, 0x800A32C0, SpuWriterFamily.PERIODIC_VOICE_SYNC, OFFSET_KEY_OFF,
        True,
        "Same call site pattern as the Key ON pair above; fires in lockstep with it.",
    ),
    SpuWriterSite(
        0x8008E9D8, 0x800A38A8, SpuWriterFamily.GENERIC_SPU_DRIVER, OFFSET_KEY_ON,
        False,
        "Found by static scan; never fired in any live capture session this project has taken.",
    ),
    SpuWriterSite(
        0x8008E934, 0x800A38A8, SpuWriterFamily.GENERIC_SPU_DRIVER, OFFSET_KEY_OFF,
        False,
        "Found by static scan; never fired in any live capture session this project has taken.",
    ),
    SpuWriterSite(
        0x8008EB84, 0x800A38A8, SpuWriterFamily.GENERIC_SPU_DRIVER, OFFSET_KEY_OFF,
        False,
        "Found by static scan; never fired in any live capture session this project has taken.",
    ),
)


KEY_PADCIRCLE_VK = 0x44  # 'D', pcsx.json Keyboard_PadCircle -- confirmed real advance/confirm button

SPU_MMIO_READ_WRITE_ROUNDTRIP_RELIABLE = False  # confirmed broken: see module docstring's diagnostic


@dataclass(frozen=True)
class LiveCorrelationRun:
    run_id: str
    press_count: int
    duration_seconds: float
    source_file_before: str
    source_file_after: str
    position_before: int
    position_after: int
    user_confirmed_audible: bool | None
    meaningful_hits: int
    evidence: str


LIVE_CORRELATION_RUNS: tuple[LiveCorrelationRun, ...] = (
    LiveCorrelationRun(
        "m16_run1", 20, 19.5, "DAT/XA2/XAPACK42.BIN", "DAT/XA1/XAPACK20.BIN",
        182935, 158685, None, 0,
        "First attempt; script context genuinely changed (proving the automated trigger reached the game), but the user was not positioned to confirm audibility for this specific run. Script itself also crashed at final cleanup (threading bug, fixed for run 2) -- data up to the crash is intact and used here.",
    ),
    LiveCorrelationRun(
        "m16_run2", 20, 24.4, "DAT/XA2/XAPACK42.BIN", "DAT/XA1/XAPACK20.BIN",
        182935, 158842, True, 0,
        "User explicitly confirmed hearing a real voice line during this exact captured window. Zero of the 6 armed sites (CD_INIT_SPUCNT_WRITE, both Key ON/OFF site pairs) fired meaningfully -- Key ON/OFF at 0x800A32C0 fired 814/815 times, all a0=0x0 (no-op). Decisive Phase-8 negative result.",
    ),
)


def live_correlation_confirmed_audible_with_zero_known_hits() -> bool:
    """True: run2 combined a real, user-confirmed audible trigger with
    zero meaningful hits across every known SPU writer site this
    project has found. The one clean, decisive negative result this
    whole investigation chain has produced."""
    return any(
        r.user_confirmed_audible is True and r.meaningful_hits == 0
        for r in LIVE_CORRELATION_RUNS
    )


def spu_mmio_read_write_roundtrip_reliable() -> bool:
    """False: a direct GDB write of 0x3FFF to Main Volume (0x1F801D80),
    performed while independently verified to be genuinely running
    (RAM position counter climbing), did not round-trip -- readback was
    0x0000 immediately and a full second later. Plain RAM writes
    round-trip correctly in the same session, isolating the problem to
    the SPU hardware I/O address range specifically, not GDB memory
    access in general. See module docstring for the full diagnostic."""
    return SPU_MMIO_READ_WRITE_ROUNDTRIP_RELIABLE


class PlaybackBackendClassification(str, Enum):
    """The milestone's own required taxonomy for the actual playback
    backend. Only set to a *_CONFIRMED value on real, live,
    user-confirmed-audible evidence -- never on structural plausibility
    alone."""

    XA_ADPCM_CONFIRMED = "XA_ADPCM_CONFIRMED"
    SPU_SAMPLE_PLAYBACK = "SPU_SAMPLE_PLAYBACK"
    SPU_STREAMED_SAMPLE = "SPU_STREAMED_SAMPLE"
    CD_INPUT_UNKNOWN_FORMAT = "CD_INPUT_UNKNOWN_FORMAT"
    HYBRID = "HYBRID"
    UNKNOWN = "UNKNOWN"


def cd_init_confirmed_live() -> bool:
    """True: CD_init (0x80081B04) was observed to actually execute
    during real gameplay in a live capture (6 firings across 2
    sessions), not just found via static analysis."""
    return True


def cd_init_sets_documented_cd_audio_enable_bit() -> bool:
    """True: CD_init's SPUCNT write (0xC001) sets bit 0, which psx-spx
    documents as "CD Audio Enable" for both CD-DA and XA-ADPCM."""
    return bool(CD_INIT_SPUCNT_WRITE_VALUE & SPUCNT_CD_AUDIO_ENABLE_BIT)


def cd_init_write_confirmed_persistent() -> bool:
    """False -- but read the follow-up section of the module docstring
    before treating this as "the write fails on real hardware." A
    direct diagnostic (write 0x3FFF to Main Volume while genuinely
    running, read it back) proved GDB's own memory read/write path for
    the SPU hardware I/O range does not round-trip at all, even for a
    debug-issued write. This function honestly reports "not confirmed
    persistent" -- it must NOT be read as "confirmed non-persistent";
    that would overclaim past what this project's tooling can verify."""
    return False


def key_on_real_voice_trigger_confirmed_live() -> bool:
    """False: the only live-firing Key ON site (0x800866A8) carried a
    nonzero voice bitmask in just 2 of 2657 observed hits (an earlier
    session), both immediately after a state-slot load and not
    confirmed against a real heard dialogue-voice segment. A dedicated
    follow-up correlation run (LIVE_CORRELATION_RUNS, run2) then
    combined a user-confirmed real audible line with this exact site
    armed and found 0/815 nonzero hits across the whole window -- this
    is now a decisive negative, not just an unconfirmed positive. Read
    via CPU register capture (`$a0` at the breakpoint), a channel
    unaffected by the separate SPU-MMIO-read-path finding."""
    return False


@dataclass(frozen=True)
class ManualMuteExperiment:
    experiment_id: str
    scene_description: str
    voices_muted: str
    dialogue_still_audible: bool
    reproduced: bool
    evidence: str


MANUAL_MUTE_EXPERIMENTS: tuple[ManualMuteExperiment, ...] = (
    ManualMuteExperiment(
        "manual_mute_1", "Normal dialogue scene (save-state slot 6, a real voiced line)",
        "all SPU voice channels showing any activity at the moment of the triggered line",
        True, False,
        "User manually muted every active-looking SPU voice channel via the native SPU Debug window's per-channel Mute controls during a real, self-triggered dialogue line. The voice line continued playing, completely unaffected.",
    ),
    ManualMuteExperiment(
        "manual_mute_2", "A second scene the user initially suspected was a pre-rendered movie/FMV segment",
        "all 24 regular SPU voice channels",
        True, True,
        "Independent repeat in a different scene. Same result: muting all 24 regular voices did not silence or alter the dialogue line at all -- reproducing manual_mute_1's finding in a structurally different context.",
    ),
)


def all_spu_voices_muted_dialogue_still_audible() -> bool:
    """True: confirmed directly and repeatedly by the user, via
    PCSX-Redux's native SPU Debug per-channel Mute controls, across two
    independently tested scenes (MANUAL_MUTE_EXPERIMENTS). Dialogue
    audio survives every regular SPU voice being muted -- it is not
    mixed through the SPU's normal 24-voice engine. This is the
    decisive evidence behind classify_playback_backend()'s current
    CD_INPUT_UNKNOWN_FORMAT result."""
    return all(e.dialogue_still_audible for e in MANUAL_MUTE_EXPERIMENTS)


def classify_playback_backend() -> PlaybackBackendClassification:
    """CD_INPUT_UNKNOWN_FORMAT -- backed by direct, repeated, hands-on
    evidence: muting every regular SPU voice channel does not silence
    or alter the dialogue audio, confirmed in two independently tested
    scenes (all_spu_voices_muted_dialogue_still_audible() -> True).
    Combined with SPUCNT's CD Audio Enable bit being confirmed
    genuinely and persistently set via the trustworthy native SPU
    debugger (gcrts.pcsx_spu_observer), this decisively points to the
    CD input path bypassing per-voice mixing entirely -- not an
    architectural guess, but what was actually heard. Not upgraded to
    XA_ADPCM_CONFIRMED: CD-DA is structurally ruled out on this disc
    (XA_PLAYBACK_PATH.md), making XA-ADPCM the only realistic remaining
    candidate for the CD input stream's format, but that specific
    format was not independently re-verified this pass -- the
    taxonomy's own CD_INPUT_UNKNOWN_FORMAT value exists precisely for
    this evidence level."""
    return PlaybackBackendClassification.CD_INPUT_UNKNOWN_FORMAT


CD_INIT_GATEKEEPER_SITES = (0x80081D28, 0x80082064)  # the 2 of 9 call sites gated by a real position-change check
CD_INIT_POSITION_CACHE_ADDR = 0x800A2E18
CD_INIT_POSITION_TARGET_ADDR = 0x800A3120
CD_INIT_BUSY_FLAG_ADDR = 0x800A2E14
CD_INIT_BUSY_FLAG_BIT = 0x0010

SETMODE_CAPTURE_SAMPLE_COUNT = 46  # real, live-captured Setmode calls across ~150s spanning a confirmed voice line
SETMODE_CAPTURE_ALL_MODE_BYTE = 0x01  # every single one of the 46 captures carried this exact value


def cd_init_gatekeeper_sites_fired_during_confirmed_trigger() -> bool:
    """False: both position-change-gated CD_init call sites
    (CD_INIT_GATEKEEPER_SITES) were live-armed across a real,
    user-confirmed voice line (two separate trigger attempts) and
    neither fired. Consistent with CD Audio Enable being a persistent,
    scene-level state rather than something re-armed per line --
    CD_init genuinely is not the per-line trigger, confirmed from a
    second, more targeted angle than the original Live Audible Trigger
    Correlation experiment."""
    return False


def setmode_xa_adpcm_bit_ever_observed_set() -> bool:
    """False: 46 live Setmode captures across ~150 real seconds
    spanning a confirmed voice line, every single one carrying
    mode_byte=0x01 (SETMODE_CAPTURE_ALL_MODE_BYTE) -- XA-ADPCM and
    XA-Filter both off, 100% of the time. A far more statistically
    decisive version of the single-sample finding in
    gcrts.audio_playback_truth. Does not contradict the CD input
    routing finding -- it means the CD-ROM controller's hardware-level
    XA-ADPCM decode, if that is what is happening, is not gated by this
    specific software Setmode toggle at this specific dispatch site."""
    return False


# --- DMA data-path investigation: what actually feeds CD Input ---

HW_REGISTERS_MENU_PATH = ("Debug", "Misc hardware", "Show HW Registers")

DMA_CHANNEL_NAMES = {
    0: "MDECin", 1: "MDECout", 2: "GPU", 3: "CDROM", 4: "SPU", 5: "PIO", 6: "OTC",
}
DMA_CDROM_CHANNEL = 3
DMA_SPU_CHANNEL = 4


@dataclass(frozen=True)
class DmaChannelObservation:
    channel: int
    name: str
    madr_first: str
    madr_last: str
    bcr_first: str
    bcr_last: str
    chcr_first: str
    chcr_last: str
    changed_during_window: bool
    evidence: str


# Real values transcribed from a 25-frame, ~24-second live capture of
# PCSX-Redux's native "HW Registers" window, with a save state
# positioned right at a confirmed voice-line moment and the emulator
# verified genuinely, continuously running throughout (Timer 1's own
# counter changed on every single frame).
DMA_TRANSPORT_OBSERVATIONS: tuple[DmaChannelObservation, ...] = (
    DmaChannelObservation(
        DMA_CDROM_CHANNEL, "CDROM", "0x0ade34", "0x0ade34", "0x00010000", "0x00010000", "0x10000000", "0x10000000",
        False,
        "Byte-identical MADR/BCR/CHCR across all 25 captured frames spanning a confirmed voice line -- zero DMA activity on the CD-ROM sector-transfer channel during audible playback.",
    ),
    DmaChannelObservation(
        DMA_SPU_CHANNEL, "SPU", "0x174d00", "0x174d00", "0x00010000", "0x00010000", "0x00000201", "0x00000201",
        False,
        "Byte-identical MADR/BCR/CHCR across all 25 captured frames spanning a confirmed voice line -- zero DMA activity on the SPU channel during audible playback.",
    ),
    DmaChannelObservation(
        2, "GPU", "0x1e4000", "0xffffff", "0x00000010", "0x00000000", "0x00000201", "0x00000401",
        True,
        "Real, distinct transfer-completion pattern observed mid-capture (MADR hitting 0xFFFFFF, BCR exhausted, CHCR's status bit shifting) -- confirms genuine execution and DMA activity were happening throughout the window, making the CDROM/SPU channels' total silence a real negative, not a frozen-emulator artifact.",
    ),
)


def dma_cdrom_or_spu_channel_active_during_confirmed_voice_line() -> bool:
    """False: neither DMA channel 3 (CDROM) nor DMA channel 4 (SPU)
    showed any MADR/BCR/CHCR change across a 25-frame capture spanning
    a confirmed voice line, while DMA channel 2 (GPU) showed a real,
    distinct transfer-completion pattern in the same window -- proving
    the capture caught genuine execution, not a frozen emulator. This
    directly answers the milestone's core question: whatever carries
    the confirmed audible dialogue does not move through the system
    DMA controller's CD-ROM or SPU channels at all."""
    return any(o.changed_during_window for o in DMA_TRANSPORT_OBSERVATIONS if o.channel in (DMA_CDROM_CHANNEL, DMA_SPU_CHANNEL))


class TransportPath(str, Enum):
    """How the confirmed-audible data physically moves -- kept
    deliberately separate from StreamFormat (what format it's encoded
    in). Collapsing these two questions into one enum was an earlier
    mistake this project corrected: CD_INPUT_UNKNOWN_FORMAT answered
    "how" reasonably well while leaving "what format" open, but as a
    single string it invited conflating the two."""

    SYSTEM_DMA_CDROM_CHANNEL = "SYSTEM_DMA_CDROM_CHANNEL"
    SYSTEM_DMA_SPU_CHANNEL = "SYSTEM_DMA_SPU_CHANNEL"
    DIRECT_HARDWARE_AUDIO_BUS = "DIRECT_HARDWARE_AUDIO_BUS"
    SPU_VOICE_RAM = "SPU_VOICE_RAM"
    UNKNOWN = "UNKNOWN"


class StreamFormat(str, Enum):
    XA_ADPCM = "XA_ADPCM"
    CDDA = "CDDA"
    CUSTOM = "CUSTOM"
    PCM = "PCM"
    UNKNOWN = "UNKNOWN"


def classify_transport_path() -> TransportPath:
    """DIRECT_HARDWARE_AUDIO_BUS -- backed by the DMA observation
    above: the confirmed audible dialogue does not move through system
    DMA channel 3 (CDROM) or 4 (SPU), and earlier evidence already
    ruled out any of the SPU's 24 regular voices
    (all_spu_voices_muted_dialogue_still_audible() -> True). By
    elimination, the leading interpretation is that CD-ROM audio
    output connects to the SPU's CD Input as a direct hardware bus,
    separate from the general-purpose DMA controller entirely -- this
    project has not independently re-verified that specific PS1
    architectural claim beyond what the DMA observation itself rules
    out, so it is recorded as the leading interpretation of solid
    negative evidence, not an independently proven mechanism."""
    return TransportPath.DIRECT_HARDWARE_AUDIO_BUS


def classify_stream_format() -> StreamFormat:
    """XA_ADPCM -- resolved by the "GCRTS XAPACK Raw Format" milestone,
    statically, not through the software Setmode toggle this project
    could never observe set (setmode_xa_adpcm_bit_ever_observed_set()
    stays False, and remains correct: Setmode was never the right
    signal). A byte-level scan of every audio sector across all 43 real
    `XAPACK*.BIN` files on the disc found the exact standard Green Book
    CD-XA real-time-audio submode with `coding_info=0x01` (stereo,
    37800 Hz, 4-bit ADPCM) -- see `gcrts.xapack`'s module docstring for
    the full evidence, including cross-validation against two real,
    independently-established live LBA anchors that both land exactly
    where this disc-structural model predicts. This is a genuinely
    different, stronger evidence source than the SPU Debug window's
    static XA panel reading (which this project correctly declined to
    trust alone, see spu_debug_xa_panel_changed_during_confirmed_voice_line
    above) -- it comes from the disc's own physical sector headers, not
    a debugger display."""
    return StreamFormat.XA_ADPCM


# The avenues checked (and closed) while looking for a way to inspect
# the SPU's internal 512KB sound RAM content, distinct from its MMIO
# control registers. Each is a real, confirmed dead end -- see the
# module docstring's "SPU-internal RAM inspection" section for detail.
SPU_RAM_INSPECTION_AVENUES_CHECKED = (
    "PCSX-Redux GUI Memory Editors (#1-8 generic slots + Parallel Port/"
    "Scratch Pad/Hardware Registers/BIOS/VRAM presets): no memory-space "
    "selector; 'Options' menu is display formatting only.",
    "Native 'SPU Debug' window: exactly 3 sections (SPU/XA/Channels), "
    "no raw memory/hex view.",
    "PCSX-Redux documented Lua API (getMemPtr/getParPtr/getRomPtr/"
    "getScratchPtr/getRegisters/getReadLUT): none reach SPU RAM; the "
    "only SPU-adjacent Lua functions are an offline ADPCM encoder "
    "utility (Adpcm:processSPUBlock/:finishSPU), unrelated to reading "
    "live emulator state.",
    "GDB SPU MMIO read/write path (both KUSEG 0x1F801xxx and KSEG1 "
    "0xBF801xxx): already confirmed stuck-zero/unreliable, which also "
    "closes simulating the real-hardware Sound RAM Data Transfer "
    "Address/FIFO protocol (0x1F801DA6/0x1F801DA8) as a fallback.",
)


def spu_internal_ram_directly_inspectable() -> bool:
    """False: every avenue this project has access to (GUI Memory
    Editors, the native SPU Debug window, PCSX-Redux's documented Lua
    scripting API, and GDB's own SPU-register read/write path) was
    checked and found not to expose the SPU's internal 512KB sound RAM
    content. This is a genuine, confirmed tooling limitation -- see
    SPU_RAM_INSPECTION_AVENUES_CHECKED for the specific dead ends."""
    return False


@dataclass(frozen=True)
class XaPanelSample:
    capture_id: str
    frame_index: int
    seconds_offset: float
    mem: str
    frequency: int
    stereo: int
    samples: int
    volume_l: int
    volume_r: int
    note: str


# Real values transcribed from two independent 60-frame (~1fps) live
# captures of PCSX-Redux's native "SPU Debug" window, each with a
# self-resuming GDB continue loop keeping the emulator genuinely
# running throughout (verified via per-channel Position/Current values
# actively changing across frames in both captures).
XA_PANEL_OBSERVATIONS: tuple[XaPanelSample, ...] = (
    XaPanelSample(
        "m37", 0, 0.0, "494288", 37800, 1, 2016, 32767, 32767,
        "Baseline frame; save slot 6 just loaded. A user-triggered voice "
        "line was reported during this capture, but without a specific timestamp.",
    ),
    XaPanelSample(
        "m37", 30, 30.0, "494288", 37800, 1, 2016, 32767, 32767,
        "Mid-capture; byte-identical to frame 0 despite real channel "
        "activity (genuine execution confirmed via changing Position/Current values).",
    ),
    XaPanelSample(
        "m37", 59, 59.0, "494288", 37800, 1, 2016, 32767, 32767,
        "Final frame; still byte-identical to frame 0.",
    ),
    XaPanelSample(
        "m38", 0, 0.0, "482580", 37800, 1, 2016, 32767, 32767,
        "Baseline frame; save slot 6 freshly reloaded for a cleanly timed re-attempt.",
    ),
    XaPanelSample(
        "m38", 8, 8.0, "482580", 37800, 1, 2016, 32767, 32767,
        "Immediately before the user's reported 9-10s trigger point.",
    ),
    XaPanelSample(
        "m38", 10, 10.0, "482580", 37800, 1, 2016, 32767, 32767,
        "At the user's reported trigger point -- XA panel unchanged.",
    ),
    XaPanelSample(
        "m38", 13, 13.0, "482580", 37800, 1, 2016, 32767, 32767,
        "A few seconds into the expected voice-line duration -- still unchanged.",
    ),
    XaPanelSample(
        "m38", 17, 17.0, "482580", 37800, 1, 2016, 32767, 32767,
        "Well after the line should have finished -- still unchanged.",
    ),
    XaPanelSample(
        "m38", 42, 42.0, "494288", 37800, 1, 2016, 32767, 32767,
        "MEM shifted here (482580 -> 494288), ~30s after the reported "
        "trigger -- too late to be the trigger's effect, and 494288 is "
        "the same value the entire first (m37) capture sat at regardless "
        "of any trigger, consistent with a generic post-load settling "
        "artifact rather than a dialogue-driven event.",
    ),
    XaPanelSample(
        "m38", 50, 50.0, "494288", 37800, 1, 2016, 32767, 32767,
        "Late frame; XA panel still unchanged from frame 0.",
    ),
)


def spu_debug_xa_panel_changed_during_confirmed_voice_line() -> bool:
    """False: across two independent 60-frame live captures of the SPU
    Debug window's XA panel (Frequency/Stereo/Samples/Volume L/R) --
    including one with a precisely user-confirmed trigger at 9-10
    seconds into the capture -- every single sampled frame showed
    byte-identical XA panel values. The one MEM field change observed
    (in the second capture, ~30s after the trigger) does not correlate
    with the trigger timing. Consistent with, not contradicting, the
    standing finding that dialogue bypasses the instrumented parts of
    the SPU pipeline entirely."""
    return any(
        (s.frequency, s.stereo, s.samples, s.volume_l, s.volume_r)
        != (
            XA_PANEL_OBSERVATIONS[0].frequency,
            XA_PANEL_OBSERVATIONS[0].stereo,
            XA_PANEL_OBSERVATIONS[0].samples,
            XA_PANEL_OBSERVATIONS[0].volume_l,
            XA_PANEL_OBSERVATIONS[0].volume_r,
        )
        for s in XA_PANEL_OBSERVATIONS
    )
