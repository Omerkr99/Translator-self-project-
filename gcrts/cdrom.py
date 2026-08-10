"""CD-ROM XA Mode2/2352 sector de-interleaving (Binary Segmentation Engine, Phase 1 extension).

A raw .BIN dumped from a PS1 disc (MODE2/2352 per the .cue) is not a flat
data stream: every 2352-byte sector wraps 12 bytes of sync + 4 bytes of
header + 8 bytes of XA subheader around the actual payload, then trails off
with an EDC checksum and (for Form1 sectors) ECC parity bytes. Scanning the
raw bytes directly works fine for small assets that happen to fit inside a
single sector's payload, but silently corrupts anything spanning multiple
sectors -- confirmed empirically: two >100KB TIM images decoded as pure
scanline noise until this de-interleaving was added.

This module strips that framing and concatenates the real payload bytes
into one contiguous stream, matching what the game's own filesystem driver
would hand to the game code.
"""

from __future__ import annotations

SECTOR_SIZE = 2352
SYNC_PATTERN = b"\x00" + b"\xff" * 10 + b"\x00"
HEADER_SIZE = 12 + 4 + 8  # sync + header (min:sec:sector, mode) + XA subheader
_FORM2_FLAG = 0x20  # bit 5 of the subheader submode byte
_FORM1_DATA_SIZE = 2048
_FORM2_DATA_SIZE = 2324


def extract_sector_payloads(data: bytes) -> bytes:
    """Strip CD-ROM XA sector framing, returning the concatenated data payloads.

    Sectors that don't start with the expected sync pattern are skipped
    entirely (their 2352-byte slot contributes nothing) rather than guessed
    at -- misaligned or non-sector data shouldn't be silently included.
    """
    payloads: list[bytes] = []
    n = len(data)

    for offset in range(0, n - SECTOR_SIZE + 1, SECTOR_SIZE):
        sector = data[offset : offset + SECTOR_SIZE]
        if sector[:12] != SYNC_PATTERN:
            continue

        submode = sector[18]
        if submode & _FORM2_FLAG:
            payloads.append(sector[HEADER_SIZE : HEADER_SIZE + _FORM2_DATA_SIZE])
        else:
            payloads.append(sector[HEADER_SIZE : HEADER_SIZE + _FORM1_DATA_SIZE])

    return b"".join(payloads)
