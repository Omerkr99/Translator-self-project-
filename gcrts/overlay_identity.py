"""Overlay/executable identity: the missing piece the SPU Playback
Trace milestone's own live runs exposed. A raw virtual address alone
is not a stable unit of meaning on this disc -- `gcrts.spu_audio_path`'s
11 writer-site addresses were validated against ONE loaded executable
at authoring time, but this game loads at least 15 different `.EXE`
files that reuse overlapping address ranges:

    PROG.EXE   0x80035000-0x8006a800
    CAP0.EXE   0x80045000-0x800a4000
    CAP1.EXE   0x80035000-0x800a3000
    CAP2.EXE   0x80035000-0x8009e800
    CAP3.EXE   0x80035000-0x800a3800
    CAP4.EXE   0x80035000-0x800a3800
    CAPX.EXE   0x80035000-0x80093800
    MPRO/MOVER/MKUBI/MNINO/MOP/MRIKA/MYOKO.EXE   0x80100000-0x8012c800 (movie-player family)

All 11 addresses in `gcrts.spu_audio_path.SPUCNT_WRITER_SITES`/
`KEY_WRITER_SITES` (0x800866xx-0x8008Exxx) fall OUTSIDE `PROG.EXE`'s
own range (which ends at 0x8006a800) -- they must have been captured
against one of the CAP*.EXE variants, not literally "PROG.EXE" as
earlier module docstrings assumed. This is a real, live-discovered
correction: **do not interpret a bare address independently of which
executable currently owns it.** The unit of meaning from here on is
`(executable identity, address)`, never address alone.

Every signature below is a real 16-byte fingerprint read from the
actual disc image at each `.EXE` file's own entry point (`pc0` in its
PS-X EXE header) -- never guessed from the address range. Two or more
files can share an identical signature (confirmed here for
`MPRO.EXE`/`MYOKO.EXE`, and separately for `MKUBI.EXE`/`MNINO.EXE`/
`MRIKA.EXE`) when they are near-identical generic harnesses (the
movie-player family, differing only in which movie data they load, not
in their own code) -- `identify_overlay` reports the first matching
name in that case, and the module docstring records the ambiguity
rather than hiding it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class OverlayProfile:
    name: str
    pc0: int  # entry point address -- where this signature was read from
    t_addr: int
    t_size: int
    signature: bytes  # 16 real bytes read from the disc image at pc0, this session

    @property
    def address_range(self) -> tuple[int, int]:
        return self.t_addr, self.t_addr + self.t_size


SIGNATURE_LENGTH = 16

# Real signatures, read directly from the actual disc image
# (קיבצי דמה/Twilight Syndrome - Tansaku Hen (Japan).bin) this session --
# see the module docstring for how (pc0's own file-body offset, 16 bytes).
KNOWN_OVERLAYS: tuple[OverlayProfile, ...] = (
    OverlayProfile("PROG.EXE", 0x8004718C, 0x80035000, 0x035800, bytes.fromhex("07801c3c50a69c27280f010800000000")),
    OverlayProfile("CAP0.EXE", 0x80077D18, 0x80045000, 0x05F000, bytes.fromhex("0a801c3ce03b9c27f1d1010800000000")),
    OverlayProfile("CAP1.EXE", 0x8007431C, 0x80035000, 0x06E000, bytes.fromhex("0a801c3ce4289c2772c3010800000000")),
    OverlayProfile("CAP2.EXE", 0x80070034, 0x80035000, 0x069800, bytes.fromhex("0a801c3cdce79c27b8b2010800000000")),
    OverlayProfile("CAP3.EXE", 0x8007599C, 0x80035000, 0x06E800, bytes.fromhex("0a801c3cf4369c2712c9010800000000")),
    OverlayProfile("CAP4.EXE", 0x80074398, 0x80035000, 0x06E800, bytes.fromhex("0a801c3c8c369c2791c3010800000000")),
    OverlayProfile("CAPX.EXE", 0x80067E08, 0x80035000, 0x05E800, bytes.fromhex("09801c3c44339c272d92010800000000")),
    # Movie-player family -- MPRO/MYOKO share one signature, MKUBI/MNINO/MRIKA
    # share another (near-identical generic harnesses, see module docstring).
    OverlayProfile("MPRO.EXE (or MYOKO.EXE)", 0x80102654, 0x80100000, 0x02C800, bytes.fromhex("13801c3c40c19c27f103040800000000")),
    OverlayProfile("MKUBI.EXE (or MNINO.EXE/MRIKA.EXE)", 0x80102680, 0x80100000, 0x02C800, bytes.fromhex("13801c3c6cc19c27fc03040800000000")),
    OverlayProfile("MOP.EXE", 0x801026CC, 0x80100000, 0x02C800, bytes.fromhex("13801c3c08c29c270f04040800000000")),
    OverlayProfile("MOVER.EXE", 0x80102658, 0x80100000, 0x02C800, bytes.fromhex("13801c3c44c19c27f203040800000000")),
)

# The 11 addresses gcrts.spu_audio_path already established -- kept here
# only as a cross-reference for overlay_covers_known_breakpoints, not
# re-derived or duplicated as the source of truth (that stays in
# gcrts.spu_audio_path itself).
_KNOWN_BREAKPOINT_RANGE = (0x800866A0, 0x8008EB84)


def overlay_covers_known_breakpoints(profile: OverlayProfile) -> bool:
    """True if this overlay's own address range fully contains the
    span of gcrts.spu_audio_path's 11 already-established breakpoint
    addresses -- i.e. whether arming them while THIS overlay is loaded
    would land on this overlay's own code (right or wrong instructions
    is a separate question; this only answers whether the addresses
    are even inside the loaded region at all)."""
    lo, hi = profile.address_range
    return lo <= _KNOWN_BREAKPOINT_RANGE[0] and _KNOWN_BREAKPOINT_RANGE[1] < hi


def identify_overlay(read_memory: Callable[[int, int], "bytes | None"]) -> OverlayProfile | None:
    """Pure, injected-`read_memory` (no breakpoints) -- reads each known
    overlay's own real signature location and returns the first
    profile whose live bytes match exactly. Returns None if nothing
    matches (a still-unknown/undiscovered overlay, or mid-transition
    RAM state) -- never guesses from address range alone, per this
    module's own standing rule."""
    for profile in KNOWN_OVERLAYS:
        live = read_memory(profile.pc0, SIGNATURE_LENGTH)
        if live == profile.signature:
            return profile
    return None
