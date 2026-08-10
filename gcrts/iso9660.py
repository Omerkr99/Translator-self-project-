"""ISO9660 filesystem walker (Binary Segmentation Engine extension).

A PS1 disc image is not just "one big blob of assets" -- it's a real
ISO9660 filesystem. Reading the actual file table turned out to be far
more informative than guessing at content from raw byte patterns alone:
it surfaced this game's real architecture (a small boot executable, a set
of per-chapter/per-character overlay executables, and a DAT resource tree
containing FONT/ and per-chapter script files) directly from disc
structure, with zero guessing.

Only what's needed to walk the directory tree is implemented: the
Primary Volume Descriptor and directory record parsing. No Rock Ridge /
Joliet extensions, no multi-extent files, no path table (directory
records are walked directly instead).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from gcrts.cdrom import HEADER_SIZE, SECTOR_SIZE, SYNC_PATTERN

_LOGICAL_BLOCK_SIZE = 2048
_PVD_LBA = 16  # fixed by the ISO9660 spec


@dataclass
class DirEntry:
    name: str
    lba: int
    size: int
    is_directory: bool


def read_logical_sectors(raw: bytes, lba: int, count: int = 1) -> bytes | None:
    """Read `count` consecutive logical (2048-byte) sectors starting at `lba`.

    Unlike gcrts.cdrom.extract_sector_payloads (which concatenates every
    sector in the image regardless of position), ISO9660 offsets are
    defined in terms of a specific LBA -- so sectors must be read directly
    by index here, not from the concatenated stream.
    """
    out = bytearray()
    for i in range(count):
        offset = (lba + i) * SECTOR_SIZE
        sector = raw[offset : offset + SECTOR_SIZE]
        if len(sector) < SECTOR_SIZE or sector[:12] != SYNC_PATTERN:
            return None
        out += sector[HEADER_SIZE : HEADER_SIZE + _LOGICAL_BLOCK_SIZE]
    return bytes(out)


def _parse_dir_records(data: bytes) -> list[DirEntry]:
    entries = []
    pos = 0
    while pos < len(data):
        rec_len = data[pos]
        if rec_len == 0:
            pos += 1  # padding to the next sector boundary
            continue
        record = data[pos : pos + rec_len]
        extent_lba = struct.unpack_from("<I", record, 2)[0]
        extent_size = struct.unpack_from("<I", record, 10)[0]
        flags = record[25]
        name_len = record[32]
        raw_name = record[33 : 33 + name_len]
        name = raw_name.decode("ascii", errors="replace")
        entries.append(
            DirEntry(
                name=name, lba=extent_lba, size=extent_size, is_directory=bool(flags & 0x2)
            )
        )
        pos += rec_len
    return entries


def read_root_directory(raw: bytes) -> list[DirEntry]:
    """Read the Primary Volume Descriptor and return the root directory's entries."""
    pvd = read_logical_sectors(raw, _PVD_LBA)
    if pvd is None or pvd[1:6] != b"CD001":
        raise ValueError("no valid ISO9660 Primary Volume Descriptor at LBA 16")

    root_record = pvd[156 : 156 + 34]
    root_lba = struct.unpack_from("<I", root_record, 2)[0]
    root_size = struct.unpack_from("<I", root_record, 10)[0]
    sectors = (root_size + _LOGICAL_BLOCK_SIZE - 1) // _LOGICAL_BLOCK_SIZE
    root_data = read_logical_sectors(raw, root_lba, sectors)
    if root_data is None:
        raise ValueError(f"could not read root directory at LBA {root_lba}")
    return _parse_dir_records(root_data)


def read_directory(raw: bytes, entry: DirEntry) -> list[DirEntry]:
    """Read the entries of a directory (as returned by read_root_directory/read_directory)."""
    if not entry.is_directory:
        raise ValueError(f"{entry.name!r} is not a directory")
    sectors = (entry.size + _LOGICAL_BLOCK_SIZE - 1) // _LOGICAL_BLOCK_SIZE
    data = read_logical_sectors(raw, entry.lba, sectors)
    if data is None:
        raise ValueError(f"could not read directory {entry.name!r} at LBA {entry.lba}")
    return _parse_dir_records(data)


def read_file(raw: bytes, entry: DirEntry) -> bytes:
    """Read a file's full contents given its directory entry."""
    if entry.is_directory:
        raise ValueError(f"{entry.name!r} is a directory, not a file")
    sectors = (entry.size + _LOGICAL_BLOCK_SIZE - 1) // _LOGICAL_BLOCK_SIZE
    data = read_logical_sectors(raw, entry.lba, sectors)
    if data is None:
        raise ValueError(f"could not read file {entry.name!r} at LBA {entry.lba}")
    return data[: entry.size]
