"""Audio Event Isolation / Extraction milestone: given a runtime audio
event's already-resolved coordinates (source file, LBA range, XA
file/channel), select and extract exactly the physical CD-XA sectors
that belong to it -- and only those, not the whole interleaved
physical region.

## Why this needs its own sector-selection pass

`gcrts.cdrom.extract_sector_payloads` strips CD-ROM framing from EVERY
sector in a buffer indiscriminately -- correct for decoding a single
contiguous asset like a TIM image, but wrong for an XA audio stream:
`XAPACK*.BIN` files are 8-way interleaved (`gcrts.xa_disc_index`'s own
finding, confirmed live: `channel_number == (lba - file_start) % 8`),
so blindly concatenating every sector in an LBA range would splice
together up to 8 DIFFERENT logical streams. This module filters by the
sector's own subheader (`file_number`, `channel_number`, and the CD-XA
Audio flag) before extracting, using the exact same
`gcrts.xa_disc_index.read_sector_meta` this project already
live-validated.

## Why the channel/file values are parameters, not hardcoded

An earlier milestone (`XA_STREAM_RESOLUTION.md`) live-captured a real,
reproduced Setfilter call: `file=2, channel=1`. A follow-up capture in
THIS milestone, cross-checking the position counter and playback state
at the exact same instant as a second Setfilter hit, found it fired
while `state=STOPPED` and `last_req_params` held a stale, unrelated
value -- meaning that specific captured Setfilter is NOT proven to be
the channel selection for any one specific, actively-playing
`RuntimeAudioEvent`. It may be a default/idle-state reset value rather
than a per-cue selection (see `AUDIO_EVENT_EXTRACTION.md` for the full
account). This module therefore takes `xa_file_number`/`xa_channel` as
explicit caller-supplied parameters -- it does NOT default to `(2, 1)`
or silently assume any single historical observation applies to
whatever event is being extracted. A caller must supply values it has
independently confirmed for the specific event being extracted.

## Read-only

This module never writes to the disc image. It only ever reads
already-loaded `disc_bytes` and returns new, independent output data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from gcrts.xa_disc_index import SectorMeta, read_sector_meta

SECTOR_SIZE = 2352
_AUDIO_FLAG = 0x04  # CD-XA submode bit 2 ("Audio"), standard White Book encoding
_FORM2_FLAG = 0x20  # CD-XA submode bit 5 ("Form2"), same encoding gcrts.cdrom already uses
_FORM2_HEADER_SIZE = 12 + 4 + 8  # sync + header + XA subheader, matches gcrts.cdrom.HEADER_SIZE
_FORM2_DATA_SIZE = 2324


class ExtractionConfidence(str, Enum):
    READY = "READY"  # start and end LBA both confirmed, at least one matching sector found
    CHANNEL_CONFIRMED = "CHANNEL_CONFIRMED"  # file/channel given, but end boundary unresolved
    START_CONFIRMED = "START_CONFIRMED"  # start LBA known, channel/end not confirmed for this event
    END_UNRESOLVED = "END_UNRESOLVED"  # explicit: extraction attempted but no confirmed end
    NOT_READY = "NOT_READY"  # insufficient inputs to attempt extraction at all


@dataclass
class ExtractedAudioEvent:
    event_id: str
    source_file: str | None
    start_lba: int
    end_lba: int | None
    xa_file_number: int
    xa_channel: int
    sector_count: int
    physical_lbas: list[int]
    raw_xa_payload: bytes
    confidence: ExtractionConfidence
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "source_file": self.source_file,
            "start_lba": self.start_lba,
            "end_lba": self.end_lba,
            "xa_file_number": self.xa_file_number,
            "xa_channel": self.xa_channel,
            "sector_count": self.sector_count,
            "physical_lbas": list(self.physical_lbas),
            "raw_xa_payload_len": len(self.raw_xa_payload),
            "confidence": self.confidence.value,
            "provenance": dict(self.provenance),
        }


def select_event_sectors(
    disc_bytes: bytes,
    start_lba: int,
    end_lba: int,
    xa_file_number: int,
    xa_channel: int,
) -> list[int]:
    """Scan `[start_lba, end_lba)` and return the LBAs that are real
    CD-XA AUDIO sectors (submode Audio flag set) matching the given
    file/channel -- never sectors from other interleaved channels or
    non-audio (data/video) sectors sharing the same physical range.
    Pure given already-loaded `disc_bytes`, matching this project's
    established injected-dependency testing discipline. Preserves
    physical LBA order (the logical stream order, per the CD-XA
    interleave scheme)."""
    selected: list[int] = []
    for lba in range(start_lba, end_lba):
        meta = read_sector_meta(disc_bytes, lba)
        if meta is None:
            continue
        if meta.file_number != xa_file_number or meta.channel_number != xa_channel:
            continue
        if not (meta.submode & _AUDIO_FLAG):
            continue
        selected.append(lba)
    return selected


def _sector_payload(disc_bytes: bytes, lba: int) -> bytes:
    off = lba * SECTOR_SIZE
    sector = disc_bytes[off : off + SECTOR_SIZE]
    return sector[_FORM2_HEADER_SIZE : _FORM2_HEADER_SIZE + _FORM2_DATA_SIZE]


def extract_runtime_audio_event(
    disc_bytes: bytes,
    start_lba: int,
    end_lba: int | None,
    xa_file_number: int,
    xa_channel: int,
    event_id: str = "event",
    source_file: str | None = None,
    provenance: dict | None = None,
) -> ExtractedAudioEvent:
    """Isolate exactly the physical XA-audio sectors belonging to one
    event, filtered by file/channel, in physical (== logical) order.
    Read-only: never modifies `disc_bytes` or any file.

    `end_lba=None` means the true end boundary is unresolved -- this
    function reports that honestly (`ExtractionConfidence.END_UNRESOLVED`)
    rather than guessing a window from timing, per this project's own
    standing rule against fabricating evidence it doesn't have."""
    if end_lba is None:
        return ExtractedAudioEvent(
            event_id=event_id,
            source_file=source_file,
            start_lba=start_lba,
            end_lba=None,
            xa_file_number=xa_file_number,
            xa_channel=xa_channel,
            sector_count=0,
            physical_lbas=[],
            raw_xa_payload=b"",
            confidence=ExtractionConfidence.END_UNRESOLVED,
            provenance=provenance or {},
        )

    lbas = select_event_sectors(disc_bytes, start_lba, end_lba, xa_file_number, xa_channel)
    payload = b"".join(_sector_payload(disc_bytes, lba) for lba in lbas)
    confidence = ExtractionConfidence.READY if lbas else ExtractionConfidence.CHANNEL_CONFIRMED
    return ExtractedAudioEvent(
        event_id=event_id,
        source_file=source_file,
        start_lba=start_lba,
        end_lba=end_lba,
        xa_file_number=xa_file_number,
        xa_channel=xa_channel,
        sector_count=len(lbas),
        physical_lbas=lbas,
        raw_xa_payload=payload,
        confidence=confidence,
        provenance=provenance or {},
    )


def extraction_readiness(
    start_lba: int | None,
    end_lba: int | None,
    xa_file_number: int | None,
    xa_channel: int | None,
) -> ExtractionConfidence:
    """Pure classification, no disc access -- lets a caller (e.g. the
    Visual Inspector) report readiness before attempting a real
    extraction, and explain exactly what's missing rather than a vague
    boolean."""
    if start_lba is None:
        return ExtractionConfidence.NOT_READY
    if xa_file_number is None or xa_channel is None:
        return ExtractionConfidence.START_CONFIRMED
    if end_lba is None:
        return ExtractionConfidence.CHANNEL_CONFIRMED
    return ExtractionConfidence.READY
