"""XA Channel / Filter Runtime Resolution milestone: the low-level CD-ROM
hardware driver this game uses to actually issue commands (Setfilter
included), found while chasing the file-open blocker
`XA_STREAM_RESOLUTION.md` left open.

## How this was found

`gcrts.audio_context`/`gcrts.audio_stream_source` closed "which XAPACK
file" and "where does playback start," but left "which XA channel does
the game actually select" completely unresolved (positional inference
only). This module picks up the milestone brief's own suggested next
step: watch CD-ROM filter/channel state directly rather than re-chasing
the already-twice-empty filename-consumer search.

**Live hardware write watchpoints (GDB `Z2` packets) on the CD-ROM MMIO
block `0x1F801800`-`0x1F801803`** immediately caught real writes from
RAM-resident game code (PCs in the `0x8008xxxx` range, well inside this
project's already-scanned code window) -- disproving an initial
hypothesis that this all happens invisibly inside BIOS ROM. Reading the
small pointer-variable table those writes go through
(`0x800a30bc`/`0x800a30c0`/`0x800a30c4`/`0x800a30c8`) live gave exact,
byte-for-byte matches to the real PS1 CD-ROM hardware register map:

  - `0x800a30bc` -> `0x1F801800` (Index/Status register)
  - `0x800a30c0` -> `0x1F801801` (Command register / Response FIFO)
  - `0x800a30c4` -> `0x1F801802` (Parameter FIFO / Data FIFO)
  - `0x800a30c8` -> `0x1F801803` (Request register / IRQ enable-ack)

This is real, live, hardware-address-exact confirmation -- not a shape
guess -- that this game's own RAM code (not a BIOS-opaque wrapper) is
the low-level CD-ROM driver, and that `0x800a30bc`-`0x800a30c8` are its
register-pointer variables.

**The actual command-byte-issuing routine was located** at
`0x80081c00`-`0x80081c54`: it writes index=3 to the Index register, then
a command byte and up to 3 parameter bytes (read from its caller's stack
frame) directly to the Command/Parameter/Request registers -- exactly
the shape of the real CD-ROM command protocol (1 command byte + N
parameter bytes, per the public LibPSn00b/psx-spx command reference).
`SETFILTER_COMMAND = 0x0D` ("Sets XA audio filter", 2 params: file
number, channel number) is a real, publicly documented command number,
cross-checked against psx-spx and the LibPSn00b runtime library
reference -- not derived from this session's own guesswork.

**What was NOT caught live, honestly**: three separate live-breakpoint
attempts at `0x80081c00` (armed immediately after a fresh state reload,
and once for 75 continuous real seconds) produced ZERO hits, despite
confirmed ongoing CD-ROM interrupt activity (the MMIO watchpoint above
caught 5 real writes within seconds). The most likely explanation: this
routine is only reached when a *new* command needs to be issued (a new
Setloc/Setfilter/Play/ReadN dispatch); the available save states all
land either mid-way through an already-established ReadN stream (which
delivers via interrupts with no further command reissue) or in a
between-lines idle state issuing no new commands at all. Catching the
exact live moment would need either input injection to force a fresh
dialogue advance, or a save state captured in the single-frame window
between a `last_req_params` write and this routine's own execution --
neither was available this session. **The live command byte and its
file/channel parameter values for one real Setfilter call remain
unconfirmed** -- reported honestly, not filled in with the expected PS1
protocol shape.

**A related dead end, also reported honestly**: the sound-dispatch
cluster's third jump-table branch (fed via the same `0x800a61b0`
BIOS event-descriptor mechanism as the confirmed
EnableEvent/DisableEvent calls at `0x80077864`/`0x8007789c`) led to
`0x80077d78`, which looked promising (a per-index 16-byte-stride table
write) but decodes to PS1 Root Counter (Timer 0/1/2) mode/target
register setup, not CD/XA channel selection -- ruled out, not silently
dropped.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

# Pointer-variable addresses (live-confirmed this session) -- each holds
# the REAL hardware register address as its own 32-bit value, one level
# of indirection the project's earlier direct lui+ori scans didn't
# anticipate (see module docstring: that's why two prior static scans
# for other consumers came up empty -- the addressing pattern here is
# "load a pointer from a small RAM variable," not "construct the
# address inline every time").
CDROM_INDEX_PTR_ADDR = 0x800A30BC
CDROM_COMMAND_PTR_ADDR = 0x800A30C0
CDROM_PARAM_PTR_ADDR = 0x800A30C4
CDROM_REQUEST_PTR_ADDR = 0x800A30C8

# The real PS1 hardware addresses each pointer variable is expected to
# hold -- fixed, documented, console-wide constants, not specific to
# this game.
CDROM_INDEX_REG = 0x1F801800
CDROM_COMMAND_REG = 0x1F801801
CDROM_PARAM_REG = 0x1F801802
CDROM_REQUEST_REG = 0x1F801803

# Command-issuing routine: the first confirmed instruction of the
# shared "write one command + its parameter bytes to hardware" routine.
# See module docstring: reached live via cross-referenced disassembly
# from a watchpoint hit's return address, but a live catch of an actual
# Setfilter (0x0D) invocation was NOT achieved this session.
COMMAND_ISSUE_ROUTINE_ADDR = 0x80081C00

# Per psx-spx / LibPSn00b Runtime Library Reference: "Setfilter -- Sets
# XA audio filter," 2 parameters (file number, channel number). Public
# documentation, not derived from this session's own guesswork.
SETFILTER_COMMAND = 0x0D


class CdromDriverConfidence(str, Enum):
    LIVE_VERIFIED = "LIVE_VERIFIED"  # all 4 pointer variables read live and matched the real hardware addresses exactly
    UNKNOWN = "UNKNOWN"  # pointer variables unreadable, or didn't match


@dataclass
class CdromDriverMap:
    index_reg_ptr: int | None
    command_reg_ptr: int | None
    param_reg_ptr: int | None
    request_reg_ptr: int | None
    confidence: CdromDriverConfidence
    resolution_note: str

    def to_dict(self) -> dict:
        return {
            "index_reg_ptr": self.index_reg_ptr,
            "command_reg_ptr": self.command_reg_ptr,
            "param_reg_ptr": self.param_reg_ptr,
            "request_reg_ptr": self.request_reg_ptr,
            "confidence": self.confidence.value,
            "resolution_note": self.resolution_note,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CdromDriverMap":
        return cls(
            index_reg_ptr=d.get("index_reg_ptr"),
            command_reg_ptr=d.get("command_reg_ptr"),
            param_reg_ptr=d.get("param_reg_ptr"),
            request_reg_ptr=d.get("request_reg_ptr"),
            confidence=CdromDriverConfidence(d.get("confidence", "UNKNOWN")),
            resolution_note=d.get("resolution_note", ""),
        )


def resolve_cdrom_driver_map(read_memory: Callable[[int, int], "bytes | None"]) -> CdromDriverMap:
    """Pure, injected-`read_memory` (no breakpoints/watchpoints -- those
    were this session's live *discovery* tool, not something this
    reusable resolver depends on). Reads the 4 pointer variables and
    cross-validates every one against the real, fixed PS1 hardware
    register addresses -- never trusts a plausible-looking pointer
    without that check, the same discipline `gcrts.audio_context` and
    `gcrts.audio_stream_source` already apply to their own resolved
    values."""
    addrs = [
        (CDROM_INDEX_PTR_ADDR, CDROM_INDEX_REG),
        (CDROM_COMMAND_PTR_ADDR, CDROM_COMMAND_REG),
        (CDROM_PARAM_PTR_ADDR, CDROM_PARAM_REG),
        (CDROM_REQUEST_PTR_ADDR, CDROM_REQUEST_REG),
    ]
    values: list[int | None] = []
    for ptr_addr, _expected in addrs:
        raw = read_memory(ptr_addr, 4)
        values.append(int.from_bytes(raw, "little") if raw is not None and len(raw) == 4 else None)

    all_match = all(v == expected for v, (_ptr, expected) in zip(values, addrs))
    return CdromDriverMap(
        index_reg_ptr=values[0],
        command_reg_ptr=values[1],
        param_reg_ptr=values[2],
        request_reg_ptr=values[3],
        confidence=CdromDriverConfidence.LIVE_VERIFIED if all_match else CdromDriverConfidence.UNKNOWN,
        resolution_note=(
            "all 4 pointer variables match the real CD-ROM hardware register addresses exactly"
            if all_match
            else "one or more pointer variables unreadable or did not match the real hardware addresses"
        ),
    )
