"""Movie/`.STR` runtime detection -- the piece `CURRENT_SYSTEM_STATUS.md`
flagged as this project's single largest blocked thread (Movies ->
Subtitles). Five internal-instrumentation hypotheses (the generic
`.CDB` resource loader, the BCD MSF-to-LBA converter, direct BIOS
CD-ROM calls, a DMA-channel-kickoff function, and a live DMA-argument
trace) were all ruled out or blocked in earlier sessions -- the last
one specifically because it assumed `PROG.EXE` was the resident
overlay during movie playback, which this project's own later audio
investigation proved wrong for regular gameplay (`CAP0.EXE`/`CAP1.EXE`
are actually resident, not `PROG.EXE`).

This module follows the same governing principle that resolved audio
identification: **identify from observable evidence, not by tracing
internal DMA arguments.** `gcrts.overlay_identity.identify_overlay()`
already exists, live-verified, and the movie-player family it already
catalogs (`MPRO`/`MOVER`/`MKUBI`/`MNINO`/`MOP`/`MRIKA`/`MYOKO.EXE`,
`0x80100000-0x8012c800`) is architecturally distinct from the
`CAP*.EXE` chapter/scene family used for regular dialogue. Since this
overlay family's entire purpose is playing movies, its mere residency
is itself the movie-playback signal -- confirmed live this session:
`MOP.EXE` was detected resident for the full duration of a real,
user-confirmed opening-movie (`OP.STR`) playthrough.

## The filename correlation, and a correction caught before it shipped

Real files from `DAT/MOVIE/` (LBA/size read directly from the disc,
this session) line up with the movie-player executable names by
prefix for 5 of 7 (`MKUBI.EXE`<->`KUBI.STR`, `MNINO.EXE`<->`NINO.STR`,
`MOP.EXE`<->`OP.STR`, `MPRO.EXE`<->`PRO.STR`, `MYOKO.EXE`<->`YOKO.STR`)
-- but that name correlation is **not the same thing** as what
`identify_overlay()` can actually distinguish at runtime.
`gcrts.overlay_identity.KNOWN_OVERLAYS` only lists literal, standalone
`name` strings for executables with a *unique* 16-byte code signature;
`MPRO.EXE`/`MYOKO.EXE` share one signature and `MKUBI.EXE`/`MNINO.EXE`/
`MRIKA.EXE` share another (near-identical generic harnesses, differing
only in which movie data they load), so `identify_overlay()` can only
ever return the combined `"X.EXE (or Y.EXE)"` string for those five --
never the individual name. Only `MOP.EXE` and `MOVER.EXE` are
independently reachable as standalone results.

This means, honestly: **one file is confirmed live** (`OP.STR` via
`MOP.EXE`, this session). The other six are only resolvable to a
*group* of 2-4 plausible files (`AMBIGUOUS_GROUPS` below) until a
further distinguishing signal is found -- reported as `AMBIGUOUS`
confidence, never guessed down to one. A first version of this module
mapped all 5 name-correlated executables individually and would have
silently never matched anything for 4 of them (dead code, caught by a
test asserting against the real `KNOWN_OVERLAYS` values before this
was committed).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from gcrts.overlay_identity import OverlayProfile


@dataclass(frozen=True)
class MovieFileEntry:
    name: str
    lba: int
    size: int


# Real LBA/size, read directly from the actual disc image's DAT/MOVIE/
# directory this session (gcrts.iso9660), not estimated.
MOVIE_CATALOG: tuple[MovieFileEntry, ...] = (
    MovieFileEntry("GAI.STR", 203228, 3160064),
    MovieFileEntry("KIKU.STR", 204771, 2799616),
    MovieFileEntry("KUBI.STR", 206138, 5371904),
    MovieFileEntry("NINO.STR", 208761, 4012032),
    MovieFileEntry("OP.STR", 210720, 47691776),
    MovieFileEntry("PRO.STR", 234007, 14680064),
    MovieFileEntry("YOKO.STR", 241175, 27105280),
)


class MovieMatchConfidence(str, Enum):
    CONFIRMED_LIVE = "CONFIRMED_LIVE"  # this session actually watched this pairing play
    NAME_MATCH = "NAME_MATCH"  # direct filename correlation, not yet independently live-confirmed
    AMBIGUOUS = "AMBIGUOUS"  # overlay's own code signature is shared by 2-3 executables
    NONE = "NONE"  # no movie-player overlay resident at all


# Overlay executable name -> the one movie file it's confirmed or
# believed to correspond to. IMPORTANT: `gcrts.overlay_identity.
# identify_overlay()` only ever returns one of the exact `name` strings
# literally present in `KNOWN_OVERLAYS` -- `MPRO.EXE`, `MYOKO.EXE`,
# `MKUBI.EXE`, `MNINO.EXE`, and `MRIKA.EXE` do NOT appear there as
# standalone names (they share code signatures with siblings, so
# `KNOWN_OVERLAYS` only lists the combined "X.EXE (or Y.EXE)" string
# for each group) -- mapping those standalone names here would be dead
# code that could never match a real live result. Only `MOP.EXE` and
# `MOVER.EXE` are real, independently-reachable standalone names.
OVERLAY_TO_MOVIE_FILE: dict[str, tuple[str, MovieMatchConfidence]] = {
    "MOP.EXE": ("OP.STR", MovieMatchConfidence.CONFIRMED_LIVE),
}

# The three shared-signature/unresolved-pairing groups gcrts.
# overlay_identity can actually return (its `name` field literally
# contains one of these exact strings) -- each maps to the plausible
# file candidates within it, since code signature or name alone cannot
# tell them apart yet.
AMBIGUOUS_GROUPS: dict[str, tuple[str, ...]] = {
    "MPRO.EXE (or MYOKO.EXE)": ("PRO.STR", "YOKO.STR"),
    "MKUBI.EXE (or MNINO.EXE/MRIKA.EXE)": ("KUBI.STR", "NINO.STR"),
    # MOVER.EXE is a real, standalone, independently-reachable overlay,
    # but which of the two unmatched files (GAI.STR/KIKU.STR) it plays
    # has not been independently confirmed -- reported as ambiguous
    # between exactly those two, never guessed down to one.
    "MOVER.EXE": ("GAI.STR", "KIKU.STR"),
}

MOVIE_PLAYER_OVERLAY_NAMES = frozenset(OVERLAY_TO_MOVIE_FILE) | frozenset(AMBIGUOUS_GROUPS)


@dataclass
class MovieDetectionResult:
    movie_active: bool
    overlay_name: str | None
    candidate_files: tuple[str, ...]
    confidence: MovieMatchConfidence

    def to_dict(self) -> dict:
        return {
            "movie_active": self.movie_active,
            "overlay_name": self.overlay_name,
            "candidate_files": list(self.candidate_files),
            "confidence": self.confidence.value,
        }


def classify_movie_state(overlay: OverlayProfile | None) -> MovieDetectionResult:
    """Pure classification from an already-identified overlay (or
    `None`) -- never performs its own live read. Callers with live
    access should get `overlay` from
    `gcrts.overlay_identity.identify_overlay()` first."""
    if overlay is None or overlay.name not in MOVIE_PLAYER_OVERLAY_NAMES:
        return MovieDetectionResult(movie_active=False, overlay_name=None, candidate_files=(), confidence=MovieMatchConfidence.NONE)

    if overlay.name in OVERLAY_TO_MOVIE_FILE:
        file_name, confidence = OVERLAY_TO_MOVIE_FILE[overlay.name]
        return MovieDetectionResult(movie_active=True, overlay_name=overlay.name, candidate_files=(file_name,), confidence=confidence)

    candidates = AMBIGUOUS_GROUPS[overlay.name]
    return MovieDetectionResult(movie_active=True, overlay_name=overlay.name, candidate_files=candidates, confidence=MovieMatchConfidence.AMBIGUOUS)


def get_movie_file(name: str) -> MovieFileEntry | None:
    for entry in MOVIE_CATALOG:
        if entry.name == name:
            return entry
    return None
