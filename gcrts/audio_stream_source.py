"""XA File Open / Stream Resolution -- the causal chain past
`gcrts.audio_context`'s resolved filename: `AUDIO_CONTEXT_RESOLUTION.md`
closed "which XAPACK file" completely, down to a live-read, real ISO9660
path string (`"\\DAT\\XA1\\XAPACK09.BIN;1"`) built at a fixed runtime
address (`0x800A5F54`). This module picks up from there.

**Two systematic static searches for whatever reads FROM `0x800A5F54`
came up empty** (documented honestly, not glossed over):

  1. A scan of every `lui`+`ori`/`addiu` pair across ~576KB of loaded
     code (`0x80000000`-`0x80090000`, covering every previously-traced
     sound-system address with wide margin) for a second construction of
     the exact address `0x800A5F54` -- zero hits besides the one
     already-known writer (`0x80075c88`).
  2. A scan for `$gp`-relative small-data access at the matching offset
     (`0x800A5F54 - $gp`, `$gp` read live as `0x800A3BE0` this session,
     giving offset `0x2374` -- well within the standard PSY-Q/MIPS ABI
     small-data window) -- zero hits.

Both are real, systematic techniques already proven elsewhere in this
project; neither found a consumer. The most likely explanation is an
addressing scheme this project's tooling doesn't yet search for (e.g. a
pointer stored once in a register-resident or heap structure rather than
re-derived from a constant each time), or that the consumer lives in
code this session's live RAM window didn't happen to have resident.
Genuinely unresolved -- not filled in with inference, per this project's
own standing rule.

**A separate, real finding fills part of the same gap anyway.** Reading
the structure `0x800A61A8` already points to (`0x800A60EC`, from Stage
C's own earlier, never-fully-decoded trace) shows a real, live,
DOUBLY-CONFIRMED "file start LBA" field at offset `+0x04`: read live for
two different resolved files, it matched `gcrts.xa_disc_index`'s real
disc-catalog start LBA EXACTLY both times (`XAPACK06.BIN` -> 116010;
`XAPACK08.BIN` -> 126218) -- not close, not approximately, exactly. This
is genuine progress on "event boundaries" even though the file-open call
itself remains untraced.

Other fields in the same structure were read and are exposed here
(`field_0x08`, `field_0x14`) but their exact semantics are NOT
confirmed with the same certainty -- `field_0x08` stayed constant across
repeated polls (ruling out "a live position counter", unlike
`0x800A61AC`) and is a plausible "event end LBA" candidate, but its
value did not cleanly match either observed file's own real end
boundary; `field_0x14` was observed IDENTICAL across two different
resolved files, meaning it is NOT file-specific and its role is
unclear. Both are reported honestly as observed-but-unconfirmed, never
upgraded to a confident claim they don't have evidence for.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import Enum
from typing import Callable

STREAM_DESCRIPTOR_PTR_ADDR = 0x800A61A8  # confirmed live (this session and, unknowingly, referenced in Stage C's own earlier trace): holds a pointer to the real descriptor structure
STRUCT_SIZE = 24

# Field offsets within the pointed-to structure, all confirmed to be
# READABLE at these positions; only OFFSET_FILE_START_LBA's MEANING is
# independently confirmed (see module docstring).
OFFSET_LAST_PARAMS = 0x00  # duplicate of 0x800A6114's own last-requested raw params
OFFSET_FILE_START_LBA = 0x04  # CONFIRMED: exact match to the real disc file's own start LBA, for two different files
OFFSET_FIELD_08 = 0x08  # observed static per-context (not a live counter); plausible "event end LBA", not independently confirmed
OFFSET_FILE_START_LBA_DUP = 0x0C  # observed identical to OFFSET_FILE_START_LBA in every sample so far
OFFSET_FIELD_10_DUP = 0x10  # observed identical to OFFSET_FIELD_08 in every sample so far
OFFSET_FIELD_14 = 0x14  # observed IDENTICAL across two different resolved files -- likely not file-specific; role unclear


class AudioStreamConfidence(str, Enum):
    LIVE_VERIFIED = "LIVE_VERIFIED"  # file_start_lba read live and cross-validated exactly against the real disc catalog
    LIVE_OBSERVED_UNCONFIRMED = "LIVE_OBSERVED_UNCONFIRMED"  # real bytes were read, but cross-validation did not confirm them
    UNKNOWN = "UNKNOWN"  # descriptor pointer or structure unreadable


@dataclass
class AudioStreamSource:
    source_id: str
    descriptor_ptr: int | None  # value read from STREAM_DESCRIPTOR_PTR_ADDR
    file_start_lba: int | None  # OFFSET_FILE_START_LBA -- the confirmed field
    file_start_lba_matches_disc: bool | None  # True iff this LBA is exactly a real XAPACK file's own start (gcrts.xa_disc_index)
    matched_disc_path: str | None  # the disc path file_start_lba matched, if any
    field_0x08_value: int | None  # observed, semantics not independently confirmed -- see module docstring
    field_0x14_value: int | None  # observed, semantics not independently confirmed -- see module docstring
    confidence: AudioStreamConfidence
    resolution_note: str

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "descriptor_ptr": self.descriptor_ptr,
            "file_start_lba": self.file_start_lba,
            "file_start_lba_matches_disc": self.file_start_lba_matches_disc,
            "matched_disc_path": self.matched_disc_path,
            "field_0x08_value": self.field_0x08_value,
            "field_0x14_value": self.field_0x14_value,
            "confidence": self.confidence.value,
            "resolution_note": self.resolution_note,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AudioStreamSource":
        return cls(
            source_id=d["source_id"],
            descriptor_ptr=d.get("descriptor_ptr"),
            file_start_lba=d.get("file_start_lba"),
            file_start_lba_matches_disc=d.get("file_start_lba_matches_disc"),
            matched_disc_path=d.get("matched_disc_path"),
            field_0x08_value=d.get("field_0x08_value"),
            field_0x14_value=d.get("field_0x14_value"),
            confidence=AudioStreamConfidence(d.get("confidence", "UNKNOWN")),
            resolution_note=d.get("resolution_note", ""),
        )


def resolve_audio_stream_source(
    read_memory: Callable[[int, int], bytes | None],
    source_id: str = "current",
) -> AudioStreamSource:
    """Pure, injected-`read_memory` (no breakpoints). Reads the
    descriptor pointer and its pointed-to structure's known-readable
    fields, and cross-validates `file_start_lba` against the real disc
    file table -- never trusts a plausible-looking number without that
    check, the same discipline `gcrts.audio_context` learned to apply
    the hard way this session."""
    from gcrts.xa_disc_index import resolve_lba_to_file

    ptr_bytes = read_memory(STREAM_DESCRIPTOR_PTR_ADDR, 4)
    if ptr_bytes is None:
        return AudioStreamSource(
            source_id=source_id,
            descriptor_ptr=None,
            file_start_lba=None,
            file_start_lba_matches_disc=None,
            matched_disc_path=None,
            field_0x08_value=None,
            field_0x14_value=None,
            confidence=AudioStreamConfidence.UNKNOWN,
            resolution_note="descriptor pointer address unreadable",
        )
    ptr = int.from_bytes(ptr_bytes, "little")

    struct_bytes = read_memory(ptr, STRUCT_SIZE)
    if struct_bytes is None or len(struct_bytes) < STRUCT_SIZE:
        return AudioStreamSource(
            source_id=source_id,
            descriptor_ptr=ptr,
            file_start_lba=None,
            file_start_lba_matches_disc=None,
            matched_disc_path=None,
            field_0x08_value=None,
            field_0x14_value=None,
            confidence=AudioStreamConfidence.UNKNOWN,
            resolution_note="descriptor structure unreadable",
        )

    file_start_lba = struct.unpack_from("<I", struct_bytes, OFFSET_FILE_START_LBA)[0]
    field_08 = struct.unpack_from("<I", struct_bytes, OFFSET_FIELD_08)[0]
    field_14 = struct.unpack_from("<I", struct_bytes, OFFSET_FIELD_14)[0]

    location = resolve_lba_to_file(file_start_lba)
    matches_disc = location is not None and location.offset_in_file_sectors == 0
    matched_path = location.disc_path if matches_disc else None

    return AudioStreamSource(
        source_id=source_id,
        descriptor_ptr=ptr,
        file_start_lba=file_start_lba,
        file_start_lba_matches_disc=matches_disc,
        matched_disc_path=matched_path,
        field_0x08_value=field_08,
        field_0x14_value=field_14,
        confidence=AudioStreamConfidence.LIVE_VERIFIED if matches_disc else AudioStreamConfidence.LIVE_OBSERVED_UNCONFIRMED,
        resolution_note=(
            "file_start_lba matches the real disc file's own start LBA exactly"
            if matches_disc
            else "file_start_lba read live but did not match any real disc file's exact start"
        ),
    )
