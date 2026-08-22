"""SPU Playback Trace: structured, machine-readable event schema for the
"playback-first identification" milestone -- moving from "what LBA is
the CD subsystem pointing at right now" (correlation evidence only) to
"what PS1 audio path is actually producing the sound the user hears
right now" (the real question).

## Why this exists: LBA-only identification was insufficient

Every earlier milestone in this project's audio investigation (see
`gcrts.runtime_audio`, `gcrts.audio_asset_resolver`,
`gcrts.live_audio_inspector`) answers "which `XAPACK*.BIN` channel does
the CD-ROM's current read position fall inside." That is real,
correctly-computed evidence -- but it is evidence about the CD
subsystem's position, not proof of what is audible at any given
instant. A live capture session (2026-08-22/23) demonstrated the gap
directly: polling the current LBA against a save-slot-9 scene produced
five different resolved `AudioAsset` candidates across a few dozen
seconds of normal play, and a direct listening test rejected every one
of them, including one (`XAPACK22:7`) that had previously been
confirmed the same way. Polling "what LBA is active" was never
guaranteed to coincide with "what the user is hearing right now" --
this module (and `gcrts.spu_trace_analyzer`) exist to close that gap by
observing the actual SPU-side playback mechanism instead.

## What this module does NOT re-decide

This project has ALREADY established, with real, repeated,
hands-on/live evidence (see `gcrts.spu_audio_path`'s module docstring
in full):

  - `all_spu_voices_muted_dialogue_still_audible()` -> `True`, twice,
    independently: muting every one of the 24 regular SPU voice
    channels during a real, confirmed dialogue line does not silence
    or alter it. Dialogue in this game, in general, does not go
    through the SPU's normal voice-mixing engine.
  - `classify_playback_backend()` -> `CD_INPUT_UNKNOWN_FORMAT` and
    `classify_transport_path()` -> `DIRECT_HARDWARE_AUDIO_BUS`: the
    audio enters via the SPU's CD Input path, bypassing both the
    24-voice engine and the system DMA controller's CD-ROM/SPU
    channels entirely.
  - `classify_stream_format()` -> `XA_ADPCM`, resolved statically from
    the disc's own sector headers (`gcrts.xapack`), independent of any
    live SPU capture.
  - The known Key ON/OFF writer sites (`SPUCNT_WRITER_SITES`,
    `KEY_WRITER_SITES` in `gcrts.spu_audio_path`) were live-armed
    across a real, user-confirmed audible line and produced a decisive
    negative: every hit carried an empty/no-op voice bitmask.
  - GDB's own SPU MMIO read/write path is confirmed unreliable (a
    debug-issued write does not round-trip); the only channel
    confirmed to show true SPU hardware state is PCSX-Redux's native
    GUI SPU Debug window, which is screenshot-only, not a structured
    data source.
  - The PCSX-Redux Lua API's real, verified memory accessors
    (`getMemPtr`/`getParPtr`/`getRomPtr`/`getScratchPtr`, confirmed
    against the project's actual `src/core/pcsxffi.lua` FFI
    declarations this session -- primary source, not documentation
    paraphrase) do not include an SPU RAM or SPU-register accessor.
    This re-confirms, with a STRONGER evidence source than before, the
    existing `spu_internal_ram_directly_inspectable() -> False`
    conclusion -- not new information, but independent corroboration.

None of that is re-litigated here. This module's job is to apply the
SAME already-proven-reliable evidence channel (a CPU breakpoint at a
known writer instruction's address, reading the CPU's own registers at
that exact instant -- never the SPU's own MMIO registers) to the
CURRENTLY OPEN question: what is the real playback path for the
specific, still-unidentified save-slot-9 target line (the earlier
`XAPACK22:7` identification for that line was retracted after direct
listening rejected it, see `docs/status/CURRENT_SYSTEM_STATUS.md`).

## Two producers, one schema

Trace events are produced by either:

  1. `pcsx_lua/spu_playback_trace.lua`, running IN-PROCESS inside
     PCSX-Redux via its real, verified Lua API
     (`PCSX.addBreakpoint`/`PCSX.getRegisters`/
     `PCSX.Events.createEventListener`, all confirmed against the
     actual FFI source this session, not assumed from memory) -- the
     primary producer, capturing `SPU_KEY_WRITE`/`SPUCNT_WRITE`/
     `HEARTBEAT`/`SAVE_STATE_LOADED`/`MARK` events with in-process
     timing, avoiding this project's own well-documented GDB
     breakpoint-cycling fragility (`PCSX_REDUX_CAPTURE_PROTOCOL.md`
     section 3).
  2. This project's existing GDB-based tooling
     (`gcrts.runtime_audio.capture_audio_event`,
     `gcrts.audio_asset_resolver.resolve_audio_asset`), as a fallback
     producer of `HEARTBEAT`-equivalent data when the Lua script isn't
     loaded.

Both write the same JSONL schema so `gcrts.spu_trace_analyzer` never
needs to know which one produced a given file.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import IO

# Re-exported, not re-derived: the already-verified writer sites and
# register offsets this project's own live investigation established.
# See gcrts.spu_audio_path's module docstring for the full evidence
# trail behind each of these.
from gcrts.spu_audio_path import (
    CD_INIT_SPUCNT_WRITE_PC,
    KEY_WRITER_SITES,
    OFFSET_KEY_OFF,
    OFFSET_KEY_ON,
    SPU_BASE_VALUE,
    SPUCNT_WRITER_SITES,
    SpuWriterFamily,
)

VOICE_COUNT = 24
VOICE_BLOCK_SIZE = 0x10  # bytes per voice, psx-spx: 24 voices * 0x10 == 0x180 == OFFSET_MAIN_VOL_L, cross-validated

# Per-voice register offsets from a voice's own base (SPU_BASE_VALUE +
# voice_index * VOICE_BLOCK_SIZE), per psx-spx's SPU Voice register
# map. Verified two ways: (1) directly against psx-spx's own
# documented layout, (2) internally cross-validated against this
# project's ALREADY-VERIFIED control-register offsets
# (gcrts.spu_audio_path.OFFSET_MAIN_VOL_L == 0x180), since
# VOICE_COUNT * VOICE_BLOCK_SIZE == 0x180 exactly -- the control
# registers begin precisely where the 24th voice block ends, which
# would not line up if either constant were wrong.
VOICE_OFFSET_VOLUME_L = 0x00
VOICE_OFFSET_VOLUME_R = 0x02
VOICE_OFFSET_ADPCM_SAMPLE_RATE = 0x04  # "pitch": 4096 == normal speed
VOICE_OFFSET_ADPCM_START_ADDRESS = 0x06  # SPU RAM address / 8
VOICE_OFFSET_ADSR_LO = 0x08  # attack shift/step, decay shift, sustain level
VOICE_OFFSET_ADSR_HI = 0x0A  # sustain shift/step/direction, release shift/mode
VOICE_OFFSET_ADSR_CURRENT_VOLUME = 0x0C
VOICE_OFFSET_ADPCM_REPEAT_ADDRESS = 0x0E  # loop address / 8

# NOTE on confidence: these offsets are HIGH-CONFIDENCE from psx-spx
# and the internal cross-check above, but -- unlike KEY_WRITER_SITES's
# 0x800866A0/0x800866A8 -- this project has not yet found and
# live-confirmed the actual game-code WRITE SITES that populate these
# per-voice fields (sample start address, pitch, volume, ADSR) for any
# specific voice. That would require new static disassembly work
# (searching for `SPU_base + voice*0x10 + offset` address
# computations) beyond this milestone's scope. Recorded here as the
# narrowest unresolved gap for this register class -- do not treat
# "we know the offsets" as "we know where they're written."
PER_VOICE_WRITER_SITES_CONFIRMED = False


def voice_register_address(voice_index: int, offset: int) -> int:
    """SPU_BASE_VALUE + voice_index*VOICE_BLOCK_SIZE + offset -- pure
    arithmetic, no live dependency. Raises ValueError for an
    out-of-range voice index rather than silently computing a bogus
    address."""
    if not 0 <= voice_index < VOICE_COUNT:
        raise ValueError(f"voice_index must be 0-{VOICE_COUNT - 1}, got {voice_index}")
    return SPU_BASE_VALUE + voice_index * VOICE_BLOCK_SIZE + offset


def decode_voice_mask(mask: int) -> list[int]:
    """KON/KOFF (and this project's own $a0-at-breakpoint captures of
    them) are 24-bit masks, bit N = voice N. Returns the sorted list of
    active voice indices -- empty for a mask of 0 (the "no-op sync"
    pattern this project's own live captures found in the overwhelming
    majority of real hits)."""
    return [i for i in range(VOICE_COUNT) if mask & (1 << i)]


class TraceEventType(str, Enum):
    SPU_KEY_WRITE = "SPU_KEY_WRITE"
    SPUCNT_WRITE = "SPUCNT_WRITE"
    HEARTBEAT = "HEARTBEAT"
    SAVE_STATE_LOADED = "SAVE_STATE_LOADED"
    MARK = "MARK"


@dataclass
class SpuKeyWriteEvent:
    """One hit of a known Key ON/OFF writer site -- the SAME evidence
    class this project already used to reach a decisive negative
    result for the game's dialogue in general (see module docstring).
    `voice_mask` is the raw value read from the CPU's own $a0 register
    at the exact breakpoint PC (never an SPU MMIO read)."""

    t: float  # trace-relative wall-clock seconds (Lua os.clock(), or Python time.time() - session start)
    write_pc: int
    family: str  # SpuWriterFamily value
    register: str  # "KEY_ON" | "KEY_OFF" | "SPUCNT"
    voice_mask: int
    cpu_pc: int | None = None  # PC at the moment of the hit, if captured
    frame: int | None = None  # PS1 CPU-cycle count or vsync-frame counter, if available
    event: str = TraceEventType.SPU_KEY_WRITE.value

    @property
    def active_voices(self) -> list[int]:
        return decode_voice_mask(self.voice_mask)

    @property
    def is_meaningful(self) -> bool:
        """False for the empty/no-op mask this project's own prior
        live captures found in >99% of real Key ON/OFF hits -- a
        meaningful hit is one that actually names at least one voice."""
        return self.voice_mask != 0

    def to_dict(self) -> dict:
        return {
            "event": self.event, "t": self.t, "write_pc": self.write_pc, "family": self.family,
            "register": self.register, "voice_mask": self.voice_mask, "cpu_pc": self.cpu_pc, "frame": self.frame,
        }


@dataclass
class SpucntWriteEvent:
    t: float
    write_pc: int
    value: int
    cpu_pc: int | None = None
    frame: int | None = None
    event: str = TraceEventType.SPUCNT_WRITE.value

    @property
    def cd_audio_enable_bit_set(self) -> bool:
        return bool(self.value & 0x0001)

    def to_dict(self) -> dict:
        return {
            "event": self.event, "t": self.t, "write_pc": self.write_pc, "value": self.value,
            "cpu_pc": self.cpu_pc, "frame": self.frame,
        }


@dataclass
class HeartbeatEvent:
    """A periodic (per-vsync, or per-poll) snapshot of the already-known,
    already-reliable CD-audio-lifecycle CPU RAM fields
    (`gcrts.runtime_audio`'s own addresses) -- NOT an SPU MMIO read.
    Resolving `position_counter` to a real `AudioAsset` happens
    OFFLINE in `gcrts.spu_trace_analyzer` (which already has the disc
    image loaded), not inside the Lua producer -- keeping the live
    tracer cheap and dependency-free."""

    t: float
    position_counter: int | None
    lifecycle_state_raw: int | None  # raw 0x800A6107 byte
    last_req_params: int | None  # raw 0x800A6114 u32
    frame: int | None = None
    event: str = TraceEventType.HEARTBEAT.value

    def to_dict(self) -> dict:
        return {
            "event": self.event, "t": self.t, "position_counter": self.position_counter,
            "lifecycle_state_raw": self.lifecycle_state_raw, "last_req_params": self.last_req_params,
            "frame": self.frame,
        }


@dataclass
class SaveStateLoadedEvent:
    t: float
    hard: bool | None = None  # from ExecutionFlow::Reset if that fired instead; None for a real state load
    frame: int | None = None
    event: str = TraceEventType.SAVE_STATE_LOADED.value

    def to_dict(self) -> dict:
        return {"event": self.event, "t": self.t, "hard": self.hard, "frame": self.frame}


@dataclass
class MarkEvent:
    """The user's own signal: 'the target dialogue line is audible
    right now.' In the Lua producer this fires from a real
    `PCSX.Events.createEventListener("Keyboard", ...)` listener --
    genuinely different from the already-proven-broken "synthetic
    input into the game controller" problem (`pcsx_spu_observer.
    synthetic_input_reaches_game_controller() -> False`): this is the
    PCSX-Redux APPLICATION receiving a real physical keypress from the
    person at the keyboard, the same class of event that already
    drives its own menu shortcuts, not an attempt to inject input into
    the emulated console."""

    t: float
    label: str = ""
    frame: int | None = None
    event: str = TraceEventType.MARK.value

    def to_dict(self) -> dict:
        return {"event": self.event, "t": self.t, "label": self.label, "frame": self.frame}


TraceEvent = SpuKeyWriteEvent | SpucntWriteEvent | HeartbeatEvent | SaveStateLoadedEvent | MarkEvent

_EVENT_CLASSES: dict[str, type] = {
    TraceEventType.SPU_KEY_WRITE.value: SpuKeyWriteEvent,
    TraceEventType.SPUCNT_WRITE.value: SpucntWriteEvent,
    TraceEventType.HEARTBEAT.value: HeartbeatEvent,
    TraceEventType.SAVE_STATE_LOADED.value: SaveStateLoadedEvent,
    TraceEventType.MARK.value: MarkEvent,
}


class UnknownTraceEventError(ValueError):
    """Raised by parse_jsonl_line for a JSON object with an unrecognized
    or missing 'event' field -- never silently coerced into a guessed type."""


def parse_jsonl_line(line: str) -> TraceEvent:
    line = line.strip()
    d = json.loads(line)
    event_type = d.get("event")
    cls = _EVENT_CLASSES.get(event_type)
    if cls is None:
        raise UnknownTraceEventError(f"unrecognized trace event type: {event_type!r}")
    kwargs = {k: v for k, v in d.items() if k != "event"}
    return cls(**kwargs)


def load_trace(path: str) -> list[TraceEvent]:
    """Loads a JSONL trace file, in file order. Blank lines are
    skipped (a Lua script under active development may leave a
    trailing newline or two). Does not sort by timestamp -- callers
    that need chronological order should sort explicitly, since a
    merged multi-producer file (see merge_traces) may not already be
    ordered."""
    events: list[TraceEvent] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            events.append(parse_jsonl_line(line))
    return events


def write_event(event: TraceEvent, f: IO[str]) -> None:
    f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")


def merge_traces(*paths: str) -> list[TraceEvent]:
    """Loads and time-sorts events from multiple JSONL files (e.g. the
    Lua tracer's own output plus a separately-produced marker file) --
    real merge-by-timestamp, not a naive concatenation, since a
    separate marker-hotkey process and the in-emulator Lua tracer do
    not share a write ordering guarantee."""
    events: list[TraceEvent] = []
    for path in paths:
        events.extend(load_trace(path))
    events.sort(key=lambda e: e.t)
    return events
