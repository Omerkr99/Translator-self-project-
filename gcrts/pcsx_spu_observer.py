"""PCSX-Redux SPU Observation Channel milestone: builds a reliable,
non-GDB way to observe true SPU hardware state, after the SPU-Side XA
Playback Discovery milestone's own follow-up proved GDB's memory
read/write path for the SPU hardware I/O range (`0x1F801xxx`) does not
round-trip even a debug-issued write while genuinely running.

## What this milestone found

PCSX-Redux ships a **native, built-in SPU debugger** -- no Lua
scripting, no source patch, no third instrumentation layer needed.
Menu path: `Debug -> SPU -> Show SPU debug`. It renders a dockable
ImGui window titled `"SPU Debug"` showing, per psx-spx-documented
register:

  - `SPU` section: `IRQ`, `CTRL` (SPUCNT), `STAT` (SPUSTAT), `MEM`
  - `XA` section: `Frequency`, `Stereo`, `Samples`, `Volume L`,
    `Volume R`
  - `Channels` section: all 24 voices, each with On/Off/Mute/Solo
    state, Noise/FMod flags, a live waveform `Plot`, Frequency
    (Active/Used), and Position (Start/Current/Loop)

This window is a genuine, separately-titled OS window once opened
(confirmed via `EnumWindows`), making it safely screenshot-automatable
-- captured only when independently verified to be the foreground
window at the exact instant of capture (`safe_screenshot`'s
abort-on-unfocus pattern), after an earlier mishap this same session
where a screenshot of the wrong (unrelated, private) window was nearly
saved. That automation lives in this project's own scratchpad tooling,
not in `gcrts/`, since it is Windows-GUI-specific and not part of the
portable analysis toolkit -- this module captures the *validated
methodology and real evidence*, not the screenshot bot itself.

### Decisive cross-check: GDB is wrong specifically about SPUCNT

At the same live instant, `GdbClient.read_memory(0x1F801DAA, 2)`
returned `0x0000` while the native SPU Debug window's `CTRL` field
showed `0xC081` -- bit 0 (CD Audio Enable, psx-spx) genuinely SET.
**`STAT` (SPUSTAT) agreed with GDB's read at `0x0000` in the same
comparison** -- so this is not a blanket "GDB can't read `0x1F801xxx`
at all" failure; it is specific to (at least) SPUCNT. This directly
overturns the previous milestone's "the write does not persist"
finding: `CD_init`'s effect (or an equivalent) genuinely IS live on
real emulated hardware -- only GDB's read of that one register was
stale.

### Validated against a real, independently-verified state change

Captured the SPU Debug window twice, ~3 real seconds apart, with
execution independently confirmed to be genuinely running throughout
(RAM position counter advancing). Between the two captures: Channel 0
transitioned to "On" with a real waveform appearing in its `Plot`
column, and `Position/Current` advanced for most channels. This proves
the window reflects true, live-changing hardware state -- not a frozen
or cached display.

### Silent-baseline vs. user-confirmed-audible comparison

Captured immediately after a save-slot-9 reload (baseline) and again
after a real, automated trigger (`Keyboard_PadCircle`/'D') the user
explicitly confirmed as audible. `CTRL` was `0xC081` in **both**
captures -- CD Audio Enable is evidently a persistent, always-on
state in this game, not something that toggles per dialogue line
(consistent with, and now explaining, why `CD_init`'s SPUCNT write was
never caught firing during the earlier live-correlation experiment: it
was very likely already set well before that capture window began).
The XA block (`Frequency=37800` Hz, a genuine PS1 XA-ADPCM sample
rate; `Volume L/R=32767`; `Samples=2016`) was also byte-identical in
both captures. Many SPU voice channels (roughly 0-13) already showed
active waveforms in the *baseline* capture too -- consistent with
persistent background music/ambience layers running underneath
dialogue, not a clean silence. This pass could not cleanly isolate one
single channel as "the dialogue voice channel" from that shared
baseline activity; a controlled experiment (e.g. muting all channels
but a scene with no BGM) is the natural next step, honestly left open.

## What this milestone did NOT achieve

No runtime integration (no `RuntimeSnapshot` field) and no Visual
Inspector panel -- this observation channel is screenshot/GUI-based,
not yet a structured, machine-readable data source. No single-voice
isolation of the dialogue-specific channel. No DMA/transfer-activity
inspection (not exposed in this debug window; a further avenue, not
pursued this pass).

## Follow-up: a real crash-loop bug, and a hard synthetic-input limit

While attempting the channel-isolation follow-up (comparing SPU state
across successive dialogue lines within a single save state), the
target process entered a genuine, reproducible crash loop: `cause`
register decoded to exception code 10 (Reserved Instruction), PC stuck
at `0xA0010000` (the low-RAM exception-vector area) on every
subsequent stop, regardless of reloading the save state or issuing a
Soft/Hard Reset from the emulator's own menu -- both left the same
fault recurring. The save file itself was checked and confirmed
byte-identical (matching MD5) to the version in this project's initial
git commit -- **not** corrupted by anything written this session. The
fault lived in the running process's own internal state (plausibly
accumulated across the many GDB attach/detach cycles this whole
project's live-capture sessions perform), and was only resolved by a
full process restart (`gcrts.pcsx_spu_observer.crash_loop_requires_full_process_restart()`
-> `True`) -- an in-process Soft/Hard Reset is not sufficient.

Separately, and decisively for further automated correlation work:
**synthetic keyboard input (Win32 `keybd_event`/`SendInput`) does not
reach the emulated game's controller input**, confirmed by a direct
A/B check -- the user's real physical key presses advanced dialogue
immediately, while every synthetic-input variant tried (`keybd_event`
with Circle, with Cross; `SendInput` with a raw scancode; each
preceded by explicit window-focus and click-to-focus steps) did not,
even though the exact same synthetic-input mechanism reliably drives
PCSX-Redux's own ImGui menus (confirmed repeatedly this session:
opening the Debug/File menus, clicking Solo/Mute buttons, all worked).
This is consistent with the emulator's controller backend reading raw
input state rather than window messages, a common pattern that
filters out OS-injected synthetic key events by design.
`gcrts.pcsx_spu_observer.synthetic_input_reaches_game_controller()`
-> `False`. This is why the earlier "Live Audible Trigger Correlation"
milestone's automated triggers worked in that session but could not be
reproduced later in this one -- not a regression in this project's own
code, but a real environmental constraint on unattended automation
that any future live-capture work needs to route around (e.g. a
virtual gamepad/XInput device, or a human physically present to
provide the trigger).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

SPU_DEBUG_WINDOW_TITLE = "SPU Debug"
SPU_DEBUG_MENU_PATH = ("Debug", "SPU", "Show SPU debug")

SPUCNT_ADDR = 0x1F801DAA
SPUSTAT_ADDR = 0x1F801DAE


class ObservationBackend(str, Enum):
    GDB = "GDB"
    PCSX_REDUX_NATIVE = "PCSX_REDUX_NATIVE"
    MOCK = "MOCK"


@dataclass(frozen=True)
class BackendCapability:
    backend: ObservationBackend
    normal_ram_reliable: bool
    spu_mmio_reliable: bool
    evidence: str


BACKEND_CAPABILITIES: tuple[BackendCapability, ...] = (
    BackendCapability(
        ObservationBackend.GDB, True, False,
        "RAM reads/writes (0x80000000-0x801FFFFF) and CPU register reads ('g') are reliable throughout this whole project. "
        "SPU hardware I/O reads (0x1F801xxx) are NOT: a write-then-readback of Main Volume never round-tripped even while "
        "genuinely running, and a live cross-check found SPUCNT reading 0x0000 via GDB at the exact instant the native "
        "SPU Debug window showed CTRL=0xC081.",
    ),
    BackendCapability(
        ObservationBackend.PCSX_REDUX_NATIVE, False, True,
        "The built-in 'SPU Debug' window (Debug > SPU > Show SPU debug) reads the emulator's own internal SPU state "
        "directly, bypassing the GDB memory bridge entirely. Confirmed to show live-changing values (a channel turning "
        "On with a real waveform) across a real ~3s window of verified execution. Does not expose general RAM -- "
        "'normal_ram_reliable' is False only because this channel was not evaluated for that use case, not because it's "
        "known to fail.",
    ),
)


def spu_mmio_reliable_backend() -> ObservationBackend:
    """PCSX_REDUX_NATIVE: the only backend confirmed to show true SPU
    hardware state in this project. Never silently fall back to GDB's
    unreliable SPU MMIO reads."""
    for cap in BACKEND_CAPABILITIES:
        if cap.spu_mmio_reliable:
            return cap.backend
    raise RuntimeError("no backend is confirmed reliable for SPU MMIO -- do not guess one")


@dataclass(frozen=True)
class SpuChannelObservation:
    channel: int
    on: bool
    off: bool
    has_waveform: bool
    frequency_active: int
    frequency_used: int
    position_start: int
    position_current: int
    position_loop: int


@dataclass(frozen=True)
class SpuHardwareSnapshot:
    """A single real, screenshot-transcribed observation from the
    native SPU Debug window -- not a live-parsed structure yet (no OCR
    pipeline was built this pass; see module docstring)."""

    label: str
    spucnt: int
    spustat: int
    xa_frequency: int
    xa_stereo: int
    xa_samples: int
    xa_volume_l: int
    xa_volume_r: int
    channels: tuple[SpuChannelObservation, ...]
    evidence: str


SPUCNT_CD_AUDIO_ENABLE_BIT = 0x0001

# Real values transcribed from live screenshots of the native SPU
# Debug window this pass. Channel data is summarized (not all 24
# entered per-field) -- full per-channel detail lives in the
# screenshots themselves (session-local, not committed).
KNOWN_SNAPSHOTS: tuple[SpuHardwareSnapshot, ...] = (
    SpuHardwareSnapshot(
        "silent_baseline_post_slot9_load", 0xC081, 0x0000, 37800, 1, 2016, 32767, 32767,
        (
            SpuChannelObservation(0, True, True, True, 5512, 5512, 138672, 149152, 138688),
            SpuChannelObservation(1, True, True, True, 5566, 5566, 138672, 149248, 138688),
        ),
        "Captured immediately after a save-slot-9 reload, before any input. Many channels (0-13ish) already show active waveforms -- likely persistent BGM/ambience, not true silence.",
    ),
    SpuHardwareSnapshot(
        "user_confirmed_audible_after_trigger", 0xC081, 0x0000, 37800, 1, 2016, 32767, 32767,
        (
            SpuChannelObservation(0, True, True, True, 5512, 5512, 138672, 188848, 138688),
            SpuChannelObservation(1, True, True, True, 5566, 5566, 138672, 189328, 138688),
        ),
        "Captured after a real, automated Keyboard_PadCircle('D') trigger sequence the user explicitly confirmed as audible. CTRL/XA block byte-identical to the silent baseline; channel Position/Current values advanced.",
    ),
)


def cd_audio_enable_confirmed_persistent_via_native_tool() -> bool:
    """True: both KNOWN_SNAPSHOTS (silent baseline AND user-confirmed
    audible) show SPUCNT/CTRL = 0xC081 with bit 0 set, via the
    validated native observation channel -- unlike GDB, which read
    0x0000 for the same register at the same live instant. This
    reverses gcrts.spu_audio_path's earlier "not confirmed persistent"
    finding: the write does persist on real hardware; only GDB's read
    of it was wrong."""
    return all(
        snap.spucnt & SPUCNT_CD_AUDIO_ENABLE_BIT == SPUCNT_CD_AUDIO_ENABLE_BIT
        for snap in KNOWN_SNAPSHOTS
    )


def gdb_spucnt_read_confirmed_wrong() -> bool:
    """True: a live cross-check (same instant as the first
    KNOWN_SNAPSHOTS entry) found GDB's own SPUCNT read at 0x0000 while
    the native tool showed 0xC081."""
    return True


def single_voice_channel_isolated_for_dialogue() -> bool:
    """False, honestly: many SPU channels were already active in the
    silent-baseline snapshot (persistent BGM/ambience), so this pass
    could not attribute any one specific channel to the dialogue line
    itself from a single before/after comparison."""
    return False


RESERVED_INSTRUCTION_EXCEPTION_CODE = 10  # MIPS R3000 cause-register exc_code field
CRASH_LOOP_STUCK_PC = 0xA0010000


def crash_loop_requires_full_process_restart() -> bool:
    """True: a real crash loop (cause register decoding to exception
    code 10 / Reserved Instruction, PC stuck at 0xA0010000 on every
    subsequent stop) was confirmed to survive both a save-state reload
    AND an in-emulator Hard Reset. Only closing and relaunching the
    PCSX-Redux process itself resolved it. The save file was verified
    byte-identical (MD5) to this project's initial git commit -- the
    fault lived in the process's own accumulated internal state, not
    in corrupted saved data."""
    return True


def synthetic_input_reaches_game_controller() -> bool:
    """False: confirmed via direct A/B test -- real physical key
    presses advanced dialogue immediately; every synthetic-input
    variant tried (keybd_event, SendInput with a raw scancode, each
    with explicit window/click focus first) did not, despite the same
    mechanisms reliably driving PCSX-Redux's own ImGui menus. Any
    future unattended live-trigger automation needs a different input
    path (e.g. a virtual gamepad/XInput device) or a human physically
    providing the trigger -- this is a real environmental constraint,
    not a bug in this project's own code."""
    return False
