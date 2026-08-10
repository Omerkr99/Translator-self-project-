"""Renderer 1 automatic runtime driver, Milestone 1 steps 4-6: active-line
detection, CLD1 consumption, and reversible live writes.

Design choice worth calling out: active-line detection here is a single
targeted SNAPSHOT read of the known record array (record_count * stride
bytes -- 196 bytes for the default profile), not a breakpoint-arm-and-
collect-hits loop like the manual investigation in RENDERER_LIVE_PROOF.md
section 11 used. Three reasons:

1. This project's own history is full of hangs and crashes traced to
   breakpoint/continue automation on this GDB stub (see
   RENDERER_LIVE_PROOF.md's repeated "emulator hangs/crashes" notes and
   gcrts.mips_patch_profile's Phase 7 lessons) -- a plain memory read has
   none of that risk.
2. The renderer re-writes every active record from scratch every frame
   (RENDERER_LIVE_PROOF.md section 10/12), so a snapshot read already
   reflects "what's showing right now" without needing to catch the
   write in the act.
3. It matches this project's safety rule against polling large ranges
   every frame -- this is a one-shot, small (196-byte), on-demand read,
   never a per-frame loop.

The trade-off: a snapshot can't distinguish "this record is genuinely
part of the current dialogue" from "this record still holds the last
frame's data for a slot nothing is using yet" purely from one read. See
`RecordConfidence` -- ambiguous records are reported PARTIAL rather than
silently treated as certain, per this project's "don't silently identify
unknown content" rule.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from gcrts.layout_descriptor import DecodedLayoutDescriptor, DecodedLine
from gcrts.layout_validation import measure_pixel_width
from gcrts.glyph_atlas import GlyphAtlas
from gcrts.renderer1_profile import Renderer1Profile, ValidationResult, validate_profile

_RECORD_FORMAT = "<HHHHHHH"  # counter, reserved, font_id, sentinel, x, y, terminator
_RECORD_SIZE = struct.calcsize(_RECORD_FORMAT)  # 14 bytes

_SCREEN_WIDTH = 320
_SCREEN_HEIGHT = 240
_TERMINATOR = 0xFFFF


class RecordConfidence(Enum):
    ACTIVE = "active"  # plausible on-screen position, real font id, correct terminator
    PARTIAL = "partial"  # readable but at least one field looks implausible -- don't trust blindly
    EMPTY = "empty"  # all-zero record -- this slot has no data at all (e.g. array not initialized for this screen)


@dataclass
class ActiveRecord:
    index: int
    addr: int
    counter: int
    font_id: int
    sentinel: int
    x: int
    y: int
    terminator: int
    confidence: RecordConfidence


def decode_record(raw: bytes, index: int, addr: int) -> ActiveRecord:
    if len(raw) != _RECORD_SIZE:
        raise ValueError(f"record must be exactly {_RECORD_SIZE} bytes, got {len(raw)}")
    counter, reserved, font_id, sentinel, x, y, terminator = struct.unpack(_RECORD_FORMAT, raw)

    if counter == 0 and font_id == 0 and x == 0 and y == 0 and terminator == 0:
        confidence = RecordConfidence.EMPTY
    elif terminator == _TERMINATOR and 0 <= x < _SCREEN_WIDTH and 0 <= y < _SCREEN_HEIGHT and font_id != 0:
        confidence = RecordConfidence.ACTIVE
    else:
        confidence = RecordConfidence.PARTIAL

    return ActiveRecord(
        index=index,
        addr=addr,
        counter=counter,
        font_id=font_id,
        sentinel=sentinel,
        x=x,
        y=y,
        terminator=terminator,
        confidence=confidence,
    )


@dataclass
class Renderer1Snapshot:
    validation: ValidationResult
    records: list[ActiveRecord] = field(default_factory=list)

    @property
    def active_records(self) -> list[ActiveRecord]:
        return [r for r in self.records if r.confidence == RecordConfidence.ACTIVE]

    @property
    def usable(self) -> bool:
        return self.validation == ValidationResult.PROFILE_VALID


def capture_snapshot(
    read_memory: Callable[[int, int], bytes | None], profile: Renderer1Profile
) -> Renderer1Snapshot:
    """Validate `profile` against live memory, then -- only if valid --
    read and decode every record slot. Never reads the record array at
    all if validation fails, so a stale/drifted profile can never even
    produce a misleading snapshot."""
    validation = validate_profile(profile, read_memory)
    if validation != ValidationResult.PROFILE_VALID:
        return Renderer1Snapshot(validation=validation, records=[])

    records: list[ActiveRecord] = []
    for i in range(profile.record_count):
        addr = profile.record_base_addr + i * profile.record_stride
        raw = read_memory(addr, _RECORD_SIZE)
        if raw is None:
            continue
        records.append(decode_record(raw, i, addr))
    return Renderer1Snapshot(validation=validation, records=records)


@dataclass
class PositionOverride:
    record_index: int
    x: int
    y: int


def compute_char_positions(line: DecodedLine, atlas: GlyphAtlas | None = None) -> list[tuple[int, int]]:
    """Per-character (x, y) for one decoded CLD1 line, starting from its
    already alignment-resolved `line.x`/`line.y` and accumulating real
    (or fallback) glyph advance widths -- the same per-character
    proportional spacing confirmed live in RENDERER_LIVE_PROOF.md section
    11 (observed deltas of 12/14/16px between consecutive characters)."""
    positions: list[tuple[int, int]] = []
    cursor_x = line.x
    for code in line.char_codes:
        positions.append((cursor_x, line.y))
        ch = _char_for_code_safe(code)
        cursor_x += measure_pixel_width(ch, atlas) if ch is not None else 0
    return positions


def _char_for_code_safe(code: int) -> str | None:
    from gcrts.glyph_char_map import char_for_code

    return char_for_code(code)


def build_overrides_from_descriptor(
    decoded: DecodedLayoutDescriptor, atlas: GlyphAtlas | None = None
) -> list[PositionOverride]:
    """Flatten every line's per-character positions into record-index
    order (0, 1, 2, ...) -- matching how the game itself fills the
    14-slot record array one character at a time, per line, confirmed
    live for multi-line layouts in RENDERER_LIVE_PROOF.md section 19."""
    overrides: list[PositionOverride] = []
    record_index = 0
    for line in decoded.lines:
        for x, y in compute_char_positions(line, atlas):
            overrides.append(PositionOverride(record_index=record_index, x=x, y=y))
            record_index += 1
    return overrides


@dataclass
class RecordBackup:
    addr: int
    x_offset: int
    y_offset: int
    original_x_bytes: bytes
    original_y_bytes: bytes


@dataclass
class ApplyResult:
    success: bool
    applied: list[PositionOverride] = field(default_factory=list)
    backups: list[RecordBackup] = field(default_factory=list)
    error: str | None = None


def apply_overrides_live(
    read_memory: Callable[[int, int], bytes | None],
    write_memory: Callable[[int, bytes], bool],
    profile: Renderer1Profile,
    snapshot: Renderer1Snapshot,
    overrides: list[PositionOverride],
) -> ApplyResult:
    """Write `overrides` onto the records `snapshot` already captured, one
    at a time, each individually verified by readback. On ANY failure --
    including an override targeting a record index the snapshot doesn't
    have, or a readback mismatch -- every already-applied write from THIS
    call is rolled back to its backed-up original before returning, so a
    partially-successful apply can never be left live. Does not
    re-validate the profile itself (the caller's snapshot already did);
    callers should discard a snapshot and recapture before applying if any
    time has passed, per validate_profile()'s own freshness contract."""
    if not snapshot.usable:
        return ApplyResult(success=False, error=f"snapshot is not usable: {snapshot.validation.value}")

    by_index = {r.index: r for r in snapshot.records}
    backups: list[RecordBackup] = []
    applied: list[PositionOverride] = []

    def rollback() -> None:
        for backup in reversed(backups):
            write_memory(backup.addr + backup.x_offset, backup.original_x_bytes)
            write_memory(backup.addr + backup.y_offset, backup.original_y_bytes)

    for override in overrides:
        record = by_index.get(override.record_index)
        if record is None:
            rollback()
            return ApplyResult(
                success=False,
                error=f"no active record at index {override.record_index} in this snapshot",
            )

        x_addr = record.addr + profile.x_offset
        y_addr = record.addr + profile.y_offset
        original_x = read_memory(x_addr, 2)
        original_y = read_memory(y_addr, 2)
        if original_x is None or original_y is None:
            rollback()
            return ApplyResult(success=False, error=f"could not read original bytes at record {override.record_index}")

        backups.append(
            RecordBackup(
                addr=record.addr,
                x_offset=profile.x_offset,
                y_offset=profile.y_offset,
                original_x_bytes=original_x,
                original_y_bytes=original_y,
            )
        )

        new_x_bytes = struct.pack("<H", override.x & 0xFFFF)
        new_y_bytes = struct.pack("<H", override.y & 0xFFFF)

        if not write_memory(x_addr, new_x_bytes) or read_memory(x_addr, 2) != new_x_bytes:
            rollback()
            return ApplyResult(success=False, error=f"X write/readback failed at record {override.record_index}")
        if not write_memory(y_addr, new_y_bytes) or read_memory(y_addr, 2) != new_y_bytes:
            rollback()
            return ApplyResult(success=False, error=f"Y write/readback failed at record {override.record_index}")

        applied.append(override)

    return ApplyResult(success=True, applied=applied, backups=backups)


@dataclass
class RestoreResult:
    success: bool
    error: str | None = None


def restore_live(
    read_memory: Callable[[int, int], bytes | None],
    write_memory: Callable[[int, bytes], bool],
    backups: list[RecordBackup],
) -> RestoreResult:
    """Write every backed-up original value back, verifying each by
    readback. Attempts every backup even if one fails, so a single bad
    restore doesn't leave the rest of the line stuck at the override
    position -- returns success=False if any single restore failed, with
    every successfully-restored record still fixed."""
    all_ok = True
    for backup in backups:
        x_addr = backup.addr + backup.x_offset
        y_addr = backup.addr + backup.y_offset
        ok_x = write_memory(x_addr, backup.original_x_bytes) and read_memory(x_addr, 2) == backup.original_x_bytes
        ok_y = write_memory(y_addr, backup.original_y_bytes) and read_memory(y_addr, 2) == backup.original_y_bytes
        if not ok_x or not ok_y:
            all_ok = False
    return RestoreResult(success=all_ok, error=None if all_ok else "one or more records failed to restore")


# --- Milestone 5: feeding a snapshot into the unified Visual Inspector -----
# A "line" here is a Y-coordinate cluster of ACTIVE records -- matches the
# live-confirmed layout (RENDERER_LIVE_PROOF.md section 11: 9 characters at
# Y=152, 5 more at Y=171 for the second line of the same textbox). Grouping
# by Y rather than trusting record index order is deliberate: the record
# array wraps and is reused across double-buffered destinations, so index
# adjacency is not a reliable "same line" signal, but every character of a
# rendered line shares one Y by construction.

@dataclass
class RuntimeTextLine:
    y: int
    records: list[ActiveRecord]

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        """(x, y, width, height) in native screen pixels. width extends one
        nominal glyph past the last character's X (matching this project's
        established fallback advance width -- see gcrts.layout_validation)
        since a record's X is a glyph's LEFT edge, not the line's full
        extent. height is a nominal single-line box (16px), not measured --
        this driver only ever confirmed baseline Y, not glyph height."""
        xs = [r.x for r in self.records]
        return (min(xs), self.y, max(xs) - min(xs) + 16, 16)


def group_into_lines(snapshot: Renderer1Snapshot) -> list[RuntimeTextLine]:
    """Pure grouping of a snapshot's ACTIVE records by Y -- PARTIAL/EMPTY
    records are excluded (see RecordConfidence), never guessed into a line."""
    by_y: dict[int, list[ActiveRecord]] = {}
    for record in snapshot.active_records:
        by_y.setdefault(record.y, []).append(record)
    return [
        RuntimeTextLine(y=y, records=sorted(records, key=lambda r: r.x))
        for y, records in sorted(by_y.items())
    ]


def renderer1_screen_objects(snapshot: Renderer1Snapshot, profile: Renderer1Profile, snapshot_id: int):
    """Turn a live snapshot into `InspectableScreenObject`s for the Visual
    Inspector -- one per detected line. Deliberately does NOT claim a
    `script_unit` (the actual dialogue text/meaning): this driver only ever
    observed POSITION records, never correlated them with the live script
    buffer gcrts.live_extract/gcrts.editor_state read -- that correlation is
    a distinct, unimplemented piece of future work, not something to guess
    at here. Import is local to avoid gcrts.screen_objects <-> this module
    ever becoming a real import cycle if screen_objects grows a dependency
    back this way later."""
    from gcrts.screen_objects import ScreenBounds, renderer_1_object

    objects = []
    for index, line in enumerate(group_into_lines(snapshot)):
        x, y, w, h = line.bounds
        objects.append(
            renderer_1_object(
                id=f"runtime:renderer1:{profile.profile_name}:y{y}",
                name=f"Renderer 1 text (line {index})",
                bounds=ScreenBounds(x, y, w, h),
                script_unit="unknown",
                line_index=index,
                profile_valid=True,
                metadata={
                    "runtime_state": "DRAWN_THIS_FRAME",
                    "snapshot_id": snapshot_id,
                    "glyph_count": len(line.records),
                    "profile": profile.profile_name,
                    "record_addrs": [r.addr for r in line.records],
                    "confidence": "LIVE_EXACT_VRAM_GPU",
                    "script_unit_association": "not implemented -- position only, no script-buffer correlation yet",
                },
            )
        )
    return objects
