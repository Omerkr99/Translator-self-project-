"""Secondary CD-ROM Driver Discovery milestone: searches live RAM
directly for values equal to the CD-ROM MMIO register addresses,
rather than searching CODE for a specific address-construction pattern
(the technique `gcrts.cdrom_driver_map`'s single known pointer set and
two earlier static scans all used, and which the "Locate the Real
XA-ADPCM Playback Path" milestone confirmed is exhausted).

## What this found

A full 2MB RAM scan for the 4-byte little-endian values
`0x1F801800`/`01`/`02`/`03` found **28 occurrences beyond the 4 already
known** (`0x800A30BC`-`0x800A30C8`), organized as 7 additional complete
4-register sets (index/command/param/request, each spaced exactly 4
bytes apart, matching the known set's own layout exactly):

  - `0x8001586C`, `0x800158F0`, `0x80015940`, `0x80015950` (a
    low-memory cluster)
  - `0x800A3140`, `0x800A3190`, `0x800A31A0` (in the same page as the
    already-known set)

**None of these new sets has a writer reachable through the same
address-construction pattern this project's static scans have used**
(a fresh, targeted scan for `lui`+`lw`+`sb` sequences touching each new
offset found zero hits) -- consistent with, not contradicting, the
"exhausted the known pattern" finding from the previous milestone.

## What the `0x800A31xx` cluster actually is

Direct inspection of the surrounding memory (`0x800A3100`-`0x800A3200`)
shows this is **not** an isolated audio-driver pointer set -- it sits
inside a broader hardware-register descriptor table that also holds:

  - DMA channel address pairs for channels 1, 2, 3, and 5 (MDEC-out,
    GPU, CD-ROM, and PIO -- `MADR`/`CHCR` pairs at their real, standard
    PS1 offsets from `0x1F801080`)
  - `I_STAT`/`I_MASK` (`0x1F801070`/`0x1F801074`, the interrupt
    status/mask registers)
  - a block of function-pointer-shaped values (`0x800475EC`,
    `0x800846E0`, `0x80084010`, ... -- all real, plausible code
    addresses in this game's own loaded range)

This is architecturally consistent with a **generic interrupt/DMA
dispatch configuration table** shared across multiple hardware
subsystems (GPU, MDEC, CD-ROM, PIO all appear together), not a
dedicated second CD-ROM *command-issuing* driver. One real link to the
already-known audio system was found: code at `0x80081B10` passes the
address `0x800A3108` (which itself holds `0x800A30D4`, the already-
confirmed command-staging byte address) to a function
(`0x80077F68`) alongside what looks like a format string -- most
consistent with a debug-log call annotating the known system, not a
second functional path.

## Classification (per this milestone's own required taxonomy)

Does not cleanly fit any of `SAME_DRIVER_DIFFERENT_ENTRY` /
`SECOND_DRIVER` / `OVERLAY_VARIANT`. Recorded honestly as its own,
more precise finding: `HW_DISPATCH_TABLE_NOT_A_COMMAND_DRIVER` -- real,
verified data, but not itself a second command-issuing driver. The
underlying question (what issues `ReadS`) remains open.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# The already-known set (gcrts.cdrom_driver_map's own addresses).
KNOWN_POINTER_SET_ADDRS = (0x800A30BC, 0x800A30C0, 0x800A30C4, 0x800A30C8)

# The 7 additional complete 4-register sets found by the full-RAM value
# scan, each verified live to hold the real hardware addresses
# (0x1F801800/01/02/03) in the same relative order/spacing as the known
# set.
ADDITIONAL_POINTER_SET_BASES = (
    0x8001586C,
    0x800158F0,
    0x80015940,
    0x80015950,
    0x800A3140,
    0x800A3190,
    0x800A31A0,
)


class DriverRelationship(str, Enum):
    SAME_DRIVER_DIFFERENT_ENTRY = "SAME_DRIVER_DIFFERENT_ENTRY"
    SECOND_DRIVER = "SECOND_DRIVER"
    OVERLAY_VARIANT = "OVERLAY_VARIANT"
    HW_DISPATCH_TABLE_NOT_A_COMMAND_DRIVER = "HW_DISPATCH_TABLE_NOT_A_COMMAND_DRIVER"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class CdromDriverDiscovery:
    pointer_set_base: int
    has_known_writer: bool
    relationship: DriverRelationship
    evidence: str


# The 0x800A31xx cluster specifically -- the 3 sets found in the same
# page as the already-known one, and the only ones this pass
# investigated in enough depth to classify with real evidence.
DISCOVERED_SETS: tuple[CdromDriverDiscovery, ...] = (
    CdromDriverDiscovery(
        pointer_set_base=0x800A3140,
        has_known_writer=False,
        relationship=DriverRelationship.HW_DISPATCH_TABLE_NOT_A_COMMAND_DRIVER,
        evidence="Sits inside 0x800A3100-0x800A3200, a table also holding DMA channel 1/2/3/5 address pairs and I_STAT/I_MASK -- a generic interrupt/DMA dispatch table, not an isolated audio driver.",
    ),
    CdromDriverDiscovery(
        pointer_set_base=0x800A3190,
        has_known_writer=False,
        relationship=DriverRelationship.HW_DISPATCH_TABLE_NOT_A_COMMAND_DRIVER,
        evidence="Same table as 0x800A3140; immediately adjacent, same structure.",
    ),
    CdromDriverDiscovery(
        pointer_set_base=0x800A31A0,
        has_known_writer=False,
        relationship=DriverRelationship.HW_DISPATCH_TABLE_NOT_A_COMMAND_DRIVER,
        evidence="Same table; immediately follows 0x800A3190's set with no gap.",
    ),
)


def additional_pointer_sets_found() -> int:
    """7: real, live-verified count of complete 4-register CD-ROM
    pointer sets beyond the already-known one. Does not by itself mean
    7 independent drivers exist -- see module docstring."""
    return len(ADDITIONAL_POINTER_SET_BASES)


def any_new_command_driver_confirmed() -> bool:
    """False: none of the newly-found pointer sets has a confirmed
    command-issuing writer. The additional sets are real, but this
    milestone did not find a second working CD-ROM command path --
    only a broader hardware-register table that happens to reference
    the same registers for a different (interrupt/DMA dispatch)
    purpose."""
    return any(d.relationship == DriverRelationship.SECOND_DRIVER for d in DISCOVERED_SETS)
