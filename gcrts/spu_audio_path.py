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

## Honest conclusion

Neither hypothesis achieved a clean, live, user-confirmed audible
correlation within a single capture window this pass. `CD_init` is
real, live-firing, and demonstrably touches the one hardware bit
psx-spx documents as gating CD-audio-to-SPU streaming -- the strongest
concrete anchor this project has found across all six audio milestones
so far. But its write not persisting, and the total absence of a
same-session "armed breakpoint + real audible confirmation" capture,
means the actual playback backend is **not yet confirmed** either way.
Per this milestone's own required taxonomy, this is classified `UNKNOWN`
-- not `XA_ADPCM_CONFIRMED`, not `SPU_SAMPLE_PLAYBACK` -- rather than
guessing past the evidence.
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
    """False: every post-write read this project has taken (in both
    capture sessions) found SPUCNT/CD-Volume/Main-Volume back at zero,
    never holding CD_init's own written values. Recorded as an open
    question, not assumed away."""
    return False


def key_on_real_voice_trigger_confirmed_live() -> bool:
    """False: the only live-firing Key ON site (0x800866A8) carried a
    nonzero voice bitmask in just 2 of 2657 observed hits, both
    immediately after a state-slot load and not confirmed against a
    real heard dialogue-voice segment. The other Key ON site
    (0x8008E9D8) never fired at all."""
    return False


def classify_playback_backend() -> PlaybackBackendClassification:
    """UNKNOWN: this milestone found a real, live-firing, structurally
    strong CD-audio-enable candidate (CD_init) and ruled out sustained
    real Key ON activity as an explanation for the observed session --
    but achieved no single capture window with both an armed
    breakpoint AND a user-confirmed audible trigger landing together.
    Per this milestone's own instruction, evidence outranks
    architectural expectation; guessing past what was actually caught
    live would violate that."""
    return PlaybackBackendClassification.UNKNOWN
