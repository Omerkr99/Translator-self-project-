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

## Honest conclusion (current)

`classify_playback_backend()` now returns `CD_INPUT_UNKNOWN_FORMAT`,
backed by direct, repeated, hands-on evidence (not architectural
inference): the dialogue-carrying audio survives every regular SPU
voice being muted, in two independently tested scenes. This is the
strongest, most direct evidence this whole investigation chain has
produced, and finally moves the classification off `UNKNOWN`.
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
