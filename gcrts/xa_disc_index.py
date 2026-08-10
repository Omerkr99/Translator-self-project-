"""Static, offline XA stream file table for the real disc, used to resolve
a live-observed LBA to the physical `XAPACK*.BIN` file it falls inside.

Grounded in `gcrts.iso9660`, not estimated: every `(path, start_lba)` pair
below was read directly from the real disc's ISO9660 directory records
(`DAT/XA1` and `DAT/XA2`), sorted by LBA. Table entries are contiguous --
each file's END is simply the next file's START -- confirmed live this
session: a real observed LBA (116010) landed EXACTLY on `XAPACK06.BIN`'s
own start LBA, not an estimate, the same way an earlier session found
LBA 126218 landing exactly on `XAPACK08.BIN`'s start.

Why this exists (Audio Cue Resolution Generalization milestone): a live
trace found the SAME raw script parameter (127) resolving, at two
different real-time dispatches, to two DIFFERENT physical LBA regions --
`DAT/XA1/XAPACK08.BIN` (Stage C's original capture) and `DAT/XA1/
XAPACK06.BIN` (this session). That directly disproves "script parameter
alone determines the physical source" as a general rule (see
`gcrts.runtime_audio`'s module docstring and `RUNTIME_AUDIO_TRACKER.md`
for the full evidence). What IS general and always correct is resolving
whatever LBA is ACTUALLY live-observed (via `0x800A61AC`) against the
disc's own real file layout -- that's what this module does.
"""
from __future__ import annotations

from dataclasses import dataclass

# (disc_path, start_lba) pairs, sorted by LBA, read directly from the real
# disc's ISO9660 directory records this session (DAT/XA1 + DAT/XA2).
_XAPACK_TABLE: list[tuple[str, int]] = [
    ("DAT/XA1/XAPACK00.BIN", 2034),
    ("DAT/XA1/XAPACK01.BIN", 52890),
    ("DAT/XA1/XAPACK02.BIN", 77650),
    ("DAT/XA1/XAPACK03.BIN", 91018),
    ("DAT/XA1/XAPACK04.BIN", 102474),
    ("DAT/XA1/XAPACK05.BIN", 109794),
    ("DAT/XA1/XAPACK06.BIN", 116010),
    ("DAT/XA1/XAPACK07.BIN", 121066),
    ("DAT/XA1/XAPACK08.BIN", 126218),
    ("DAT/XA1/XAPACK09.BIN", 131002),
    ("DAT/XA1/XAPACK10.BIN", 134610),
    ("DAT/XA1/XAPACK11.BIN", 137762),
    ("DAT/XA1/XAPACK12.BIN", 140970),
    ("DAT/XA1/XAPACK13.BIN", 143586),
    ("DAT/XA1/XAPACK14.BIN", 145994),
    ("DAT/XA1/XAPACK15.BIN", 148290),
    ("DAT/XA1/XAPACK16.BIN", 150402),
    ("DAT/XA1/XAPACK17.BIN", 152378),
    ("DAT/XA1/XAPACK18.BIN", 154442),
    ("DAT/XA1/XAPACK19.BIN", 156170),
    ("DAT/XA1/XAPACK20.BIN", 157914),
    ("DAT/XA1/XAPACK21.BIN", 159482),
    ("DAT/XA1/XAPACK22.BIN", 160970),
    ("DAT/XA1/XAPACK23.BIN", 162426),
    ("DAT/XA1/XAPACK24.BIN", 163890),
    ("DAT/XA1/XAPACK25.BIN", 165250),
    ("DAT/XA1/XAPACK26.BIN", 166538),
    ("DAT/XA1/XAPACK27.BIN", 167898),
    ("DAT/XA1/XAPACK28.BIN", 169050),
    ("DAT/XA1/XAPACK29.BIN", 170242),
    ("DAT/XA2/XAPACK30.BIN", 171403),
    ("DAT/XA2/XAPACK31.BIN", 173075),
    ("DAT/XA2/XAPACK32.BIN", 174083),
    ("DAT/XA2/XAPACK33.BIN", 175139),
    ("DAT/XA2/XAPACK34.BIN", 176075),
    ("DAT/XA2/XAPACK35.BIN", 176979),
    ("DAT/XA2/XAPACK36.BIN", 177867),
    ("DAT/XA2/XAPACK37.BIN", 178763),
    ("DAT/XA2/XAPACK38.BIN", 179603),
    ("DAT/XA2/XAPACK39.BIN", 180467),
    ("DAT/XA2/XAPACK40.BIN", 181275),
    ("DAT/XA2/XAPACK41.BIN", 182083),
    ("DAT/XA2/XAPACK42.BIN", 182827),
]

# One past the last table entry's own end (XAPACK42's real end LBA, from
# the same disc read this table was built from).
_LAST_END_LBA = 183635


@dataclass(frozen=True)
class XaLocation:
    disc_path: str
    file_start_lba: int
    offset_in_file_sectors: int  # (lba - file_start_lba) -- position within the file, in raw 2352-byte sectors


def resolve_lba_to_file(lba: int) -> XaLocation | None:
    """Pure, offline, no disc I/O needed at call time (the table is static
    data). Returns None for an LBA outside every known XAPACK file's range
    -- never guesses the nearest file."""
    if lba < _XAPACK_TABLE[0][1] or lba >= _LAST_END_LBA:
        return None
    for i, (path, start) in enumerate(_XAPACK_TABLE):
        end = _XAPACK_TABLE[i + 1][1] if i + 1 < len(_XAPACK_TABLE) else _LAST_END_LBA
        if start <= lba < end:
            return XaLocation(disc_path=path, file_start_lba=start, offset_in_file_sectors=lba - start)
    return None


_FILENAME_TO_PATH: dict[str, str] = {path.rsplit("/", 1)[1].split(".")[0]: path for path, _ in _XAPACK_TABLE}


def resolve_filename_to_path(filename: str) -> str | None:
    """Cross-checks a bare filename (e.g. "XAPACK08", as read live from
    the game's own embedded string table by `gcrts.audio_context`)
    against the REAL disc's own file list -- not a pattern match ("does
    this look like XAPACK-shaped text"), an exact lookup against the 43
    files that actually exist. This matters because live memory beyond
    the real file count was found to keep producing plausible-looking
    "XAPACK43", "XAPACK44", ... text (see AUDIO_CONTEXT_RESOLUTION.md) --
    a shape check alone would have wrongly trusted those as real
    resolved sources. Returns None for anything not an exact match to a
    real disc file, including well-formed-looking but non-existent
    names."""
    return _FILENAME_TO_PATH.get(filename.upper())


@dataclass(frozen=True)
class SectorMeta:
    file_number: int
    channel_number: int
    submode: int
    coding_info: int


_SYNC_PATTERN = b"\x00" + b"\xff" * 10 + b"\x00"
_SECTOR_SIZE = 2352


def read_sector_meta(disc_bytes: bytes, lba: int) -> SectorMeta | None:
    """Pure given already-loaded `disc_bytes` (a caller reads the .bin once
    and reuses it -- this function does no I/O of its own, matching this
    project's established "inject the dependency" testing discipline).
    Returns None for a non-sync-matching or out-of-range offset rather
    than guessing.

    IMPORTANT CAVEAT (see gcrts.runtime_audio's module docstring and
    RUNTIME_AUDIO_TRACKER.md for the full live evidence): the returned
    `channel_number` is whatever this SPECIFIC physical sector's XA
    subheader says -- confirmed live this session to be a pure, fully
    predictable function of position within the file
    (`channel_number == (lba - file_start_lba) % 8`, the standard 8-way
    CD-XA interleave). It is NOT independently confirmed to be "the
    channel currently selected for SPU decode" -- a live-observed LBA
    that happens to land on channel 7 does not by itself prove channel 7
    is what's audibly playing, only that channel 7's sector sits at that
    disc position. Treat this as descriptive metadata about the disc
    layout at a position, not a proven playback-channel selection."""
    off = lba * _SECTOR_SIZE
    sector = disc_bytes[off:off + _SECTOR_SIZE]
    if len(sector) < 24 or sector[:12] != _SYNC_PATTERN:
        return None
    return SectorMeta(
        file_number=sector[16],
        channel_number=sector[17],
        submode=sector[18],
        coding_info=sector[19],
    )
