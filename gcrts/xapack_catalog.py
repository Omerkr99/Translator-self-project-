"""XAPACK Catalog: a complete, real inventory of every XA stream container
file on the disc (`DAT/XA1/XAPACK00.BIN` .. `DAT/XA2/XAPACK42.BIN`, 43
files total), built directly on `gcrts.xa_disc_index`'s own exact,
ISO9660-derived file table rather than re-deriving or estimating anything.

Part of the XAPACK Raw Format milestone (`docs/audio/XAPACK_FORMAT.md`):
Phase 1's "complete XAPACK inventory". Every entry's `start_lba`/`end_lba`
is real disc data, not a guess -- `gcrts.xa_disc_index`'s table was itself
built from the real disc's own ISO9660 directory records and confirmed
live twice (a genuinely observed LBA landed exactly on two different
files' own start boundaries).
"""
from __future__ import annotations

from dataclasses import dataclass

from gcrts.xa_disc_index import all_xapack_files

SECTOR_SIZE = 2352


@dataclass(frozen=True)
class XaPackCatalogEntry:
    index: int
    disc_path: str
    start_lba: int
    end_lba: int  # exclusive
    sector_count: int
    byte_size: int

    @property
    def filename(self) -> str:
        return self.disc_path.rsplit("/", 1)[1]


def build_catalog() -> list[XaPackCatalogEntry]:
    """Pure, offline -- no disc I/O needed, the table itself is static
    data. Ordered by disc position (ascending LBA), matching
    gcrts.xa_disc_index's own table order."""
    entries: list[XaPackCatalogEntry] = []
    for i, (path, start, end) in enumerate(all_xapack_files()):
        entries.append(
            XaPackCatalogEntry(
                index=i,
                disc_path=path,
                start_lba=start,
                end_lba=end,
                sector_count=end - start,
                byte_size=(end - start) * SECTOR_SIZE,
            )
        )
    return entries


def catalog_entry_for_path(disc_path: str) -> XaPackCatalogEntry | None:
    for entry in build_catalog():
        if entry.disc_path == disc_path:
            return entry
    return None


def catalog_entry_for_lba(lba: int) -> XaPackCatalogEntry | None:
    for entry in build_catalog():
        if entry.start_lba <= lba < entry.end_lba:
            return entry
    return None
