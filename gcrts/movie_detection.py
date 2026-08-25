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

## A second, better disambiguation signal found this session

`RAM`-diffing two overlay snapshots (the originally planned next step)
turned out not to be necessary. The PS1 kernel prints its own literal
"Load Exec : \\NAME.EXE;1" (or, for this movie-player family,
"MovieLoad Exec : \\NAME.EXE;1") debug line every time it loads an
executable -- forwarded live over GDB's asynchronous 'O' console
packets. Arming a GDB breakpoint at the movie overlay's real entry PC
(0x80102654, read directly off this same console trace) while save
slot 6's movie triggered caught this exact text:
"MovieLoad Exec : \\MPRO.EXE;1" -- naming `MPRO.EXE`, not `MYOKO.EXE`,
directly and unambiguously, at the very moment `identify_overlay()`
itself could only report the combined "MPRO.EXE (or MYOKO.EXE)" for
the same resident overlay. `parse_exec_load_name()` and
`resolve_ambiguous_group_via_console_text()` below formalize this as a
reusable secondary confirmation path. It doesn't change what
`identify_overlay()` can report from RAM signature alone (that
architectural ambiguity is real and permanent), but it lets any live
capture session that's already watching the GDB console stream resolve
the ambiguity for whichever specific instance it observes.
"""
from __future__ import annotations

import re
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
    STATIC_CODE_MATCH = "STATIC_CODE_MATCH"  # a hardcoded call site found via disassembly, not yet observed live (see STATIC_MOVIE_TRIGGERS)
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

# The literal, individual executable filenames folded into each ambiguous
# combined overlay.name string above (identify_overlay() itself can never
# return these standalone -- see the module docstring -- but the PS1
# kernel's own boot/overlay-load debug trace names them directly, see
# parse_exec_load_name() below).
AMBIGUOUS_GROUP_MEMBERS: dict[str, tuple[str, ...]] = {
    "MPRO.EXE (or MYOKO.EXE)": ("MPRO.EXE", "MYOKO.EXE"),
    "MKUBI.EXE (or MNINO.EXE/MRIKA.EXE)": ("MKUBI.EXE", "MNINO.EXE", "MRIKA.EXE"),
}

# Filename-correlation hypothesis (prefix match against MOVIE_CATALOG),
# same one documented in the module docstring -- kept separate from
# OVERLAY_TO_MOVIE_FILE because identify_overlay() can never key on these
# individual exe names live; this table only exists to be looked up once
# a literal exe name has been recovered some other way (e.g. console text).
EXE_NAME_TO_MOVIE_FILE: dict[str, str] = {
    "MPRO.EXE": "PRO.STR",
    "MYOKO.EXE": "YOKO.STR",
    "MKUBI.EXE": "KUBI.STR",
    "MNINO.EXE": "NINO.STR",
}

# The PS1 kernel prints this exact debug line (forwarded live over GDB 'O'
# console packets) every time it loads an executable from disc, e.g.
# "Load Exec : \PROG.EXE;1" or, for the movie-player family specifically,
# "MovieLoad Exec : \MPRO.EXE;1" -- confirmed live this session by arming a
# GDB breakpoint at the movie overlay's real entry PC (0x80102654) while
# save slot 6's movie triggered: identify_overlay() itself could only
# report the ambiguous combined "MPRO.EXE (or MYOKO.EXE)" for that same
# resident overlay, but the console text named "MPRO.EXE" directly and
# unambiguously. This is genuine ground truth from the game's own loader,
# not a guess -- unlike RAM-diffing (which would need a fair like-for-like
# comparison point this session's single capture didn't have), it needs no
# baseline at all.
_LOAD_EXEC_PATTERN = re.compile(r"(?:Movie)?Load Exec\s*:\s*\\(\w+\.EXE);1")


def parse_exec_load_name(console_text: str) -> str | None:
    """Extract the literal executable filename from one line of the
    kernel's own "(Movie)Load Exec : \\NAME.EXE;1" debug trace, or None if
    the text doesn't contain that pattern."""
    match = _LOAD_EXEC_PATTERN.search(console_text)
    return match.group(1) if match else None


def resolve_ambiguous_group_via_console_text(overlay_name: str, console_exec_name: str) -> tuple[str, str] | None:
    """Given the ambiguous combined name identify_overlay() returned (e.g.
    "MPRO.EXE (or MYOKO.EXE)") and a literal exe filename recovered from
    the kernel's own console trace (parse_exec_load_name()), confirm which
    specific member of that group it actually is. Returns
    (confirmed_exe_name, candidate_movie_file) only when console_exec_name
    is a real member of that group AND has a known name-correlated movie
    file; returns None otherwise (never guesses)."""
    members = AMBIGUOUS_GROUP_MEMBERS.get(overlay_name)
    if members is None or console_exec_name not in members:
        return None
    movie_file = EXE_NAME_TO_MOVIE_FILE.get(console_exec_name)
    if movie_file is None:
        return None
    return console_exec_name, movie_file


@dataclass(frozen=True)
class StaticMovieTrigger:
    """One real, disassembly-verified call site: `chapter_exe`'s own code
    calls its local copy of the generic movie-dispatch function (the same
    one that prints "MovieLoad Exec : %s") with `movie_id` as a hardcoded
    immediate constant, which that dispatcher's own local pointer table
    resolves to `movie_exe`. `caller_ram` is the exact call-site address,
    kept for audit -- this is not a guess, every field here was read
    directly from the real disc image's compiled code and its own local
    string/pointer tables, cross-checked against each other (see
    docs/renderer/MOVIE_DETECTION.md for the full method and the checks
    that caught two of this module author's own wrong assumptions along
    the way: an unverified pointer-table ordering, and an unverified
    identical-across-files ordering)."""

    chapter_exe: str
    movie_id: int
    movie_exe: str
    caller_ram: int


# Every CAP*.EXE embeds an identical 10-entry table of every movie-player
# executable name (including three -- MCAVE.EXE, MSB.EXE, MGOKI.EXE -- that
# don't exist as real files on disc, presumably cut content) and its own
# copy of a generic "load movie by index" dispatcher function. The
# per-chapter choice of *which* index to call it with is genuinely
# hardcoded as a compile-time constant for some chapters -- found by
# locating each file's own copy of the "MovieLoad Exec : %s" format string,
# walking backward to that dispatcher function's entry point, then
# scanning the whole file for JAL call sites targeting it with an
# immediate constant in the branch-delay slot.
#
# CAP0.EXE's result (movie_id=8 -> MPRO.EXE) matches this session's own
# CONFIRMED_LIVE result for save slot 6 exactly -- slot 6 loads directly
# into CAP0.EXE (confirmed via identify_overlay()), which then hands off
# execution to CAPX.EXE (a shared movie-launch front-end used by multiple
# chapters) to perform the actual disc load. That corroboration is strong
# real evidence, but this table still reports STATIC_CODE_MATCH rather
# than CONFIRMED_LIVE for every other entry, since none of them have
# actually been watched playing -- per this whole project's standing
# rule, a static/structural match is not the same as a human-witnessed
# result, and is never promoted to CONFIRMED_LIVE on its own.
#
# CAPX.EXE itself also has exactly one such hardcoded call site
# (movie_id=9 -> MYOKO.EXE) -- deliberately NOT included below. It
# contradicts the live-confirmed MPRO.EXE result for the same CAPX.EXE
# residency window, meaning CAPX.EXE's real per-invocation movie_id must
# come from a runtime value (most likely written by whichever chapter
# handed off to it) for at least the slot-6 case, not always this one
# hardcoded constant -- an honest, unresolved limitation of this method
# for CAPX.EXE specifically, not a value to trust.
#
# CAP2.EXE and CAP3.EXE had zero such call sites found at all -- either
# they don't trigger a movie via this path, or (like CAPX.EXE) they do so
# through a runtime-computed index this method can't statically resolve.
STATIC_MOVIE_TRIGGERS: tuple[StaticMovieTrigger, ...] = (
    StaticMovieTrigger("CAP0.EXE", 8, "MPRO.EXE", 0x8006CCB0),
    StaticMovieTrigger("CAP1.EXE", 1, "MKUBI.EXE", 0x8005DBE4),
    StaticMovieTrigger("CAP1.EXE", 1, "MKUBI.EXE", 0x8005E700),
    StaticMovieTrigger("CAP4.EXE", 4, "MRIKA.EXE", 0x8004CB00),
    StaticMovieTrigger("CAP4.EXE", 2, "MNINO.EXE", 0x8005033C),
)


def get_static_movie_triggers_for_chapter(chapter_exe: str) -> tuple[StaticMovieTrigger, ...]:
    """All statically-found movie triggers belonging to one chapter
    executable (e.g. "CAP1.EXE"), in no particular order. Empty if none
    were found for that chapter -- never guesses."""
    return tuple(t for t in STATIC_MOVIE_TRIGGERS if t.chapter_exe == chapter_exe)


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
