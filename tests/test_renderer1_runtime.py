import struct

from gcrts.editor_layout_plan import LayoutAlignment
from gcrts.layout_descriptor import DecodedLayoutDescriptor, DecodedLine
from gcrts.renderer1_profile import ProfileStatus, Renderer1Profile, ValidationResult
from gcrts.renderer1_runtime import (
    RecordConfidence,
    apply_overrides_live,
    build_overrides_from_descriptor,
    capture_snapshot,
    compute_char_positions,
    decode_record,
    group_into_lines,
    renderer1_screen_objects,
    restore_live,
)

FINGERPRINT_ADDR = 0x800397BC
FINGERPRINT_BYTES = bytes.fromhex("0800229600000000080002a60a002296000000000a0002a6")
RECORD_BASE = 0x800A2AD4
RECORD_STRIDE = 0x0E
RECORD_FORMAT = "<HHHHHHH"


def _profile(**overrides) -> Renderer1Profile:
    kwargs = dict(
        profile_name="test_profile",
        status=ProfileStatus.LIVE_CONFIRMED_THIS_SESSION,
        record_base_addr=RECORD_BASE,
        record_stride=RECORD_STRIDE,
        record_count=3,
        x_offset=0x8,
        y_offset=0xA,
        code_fingerprint_addr=FINGERPRINT_ADDR,
        code_fingerprint_bytes=FINGERPRINT_BYTES,
    )
    kwargs.update(overrides)
    return Renderer1Profile(**kwargs)


def _pack_record(counter, font_id, x, y, terminator=0xFFFF, reserved=0, sentinel=0x7FC0):
    return struct.pack(RECORD_FORMAT, counter, reserved, font_id, sentinel, x, y, terminator)


class FakeRam:
    """Minimal dict-backed fake memory -- byte-addressable reads/writes
    just like the live GdbClient, so the driver's pure logic can be
    exercised without an emulator."""

    def __init__(self):
        self.data: dict[int, int] = {}

    def load(self, addr: int, raw: bytes) -> None:
        for i, b in enumerate(raw):
            self.data[addr + i] = b

    def read(self, addr: int, length: int) -> bytes | None:
        out = bytearray()
        for i in range(length):
            if addr + i not in self.data:
                return None
            out.append(self.data[addr + i])
        return bytes(out)

    def write(self, addr: int, data: bytes) -> bool:
        self.load(addr, data)
        return True


def test_decode_record_classifies_active():
    raw = _pack_record(counter=0x10, font_id=0x15, x=26, y=152)
    record = decode_record(raw, index=1, addr=RECORD_BASE + RECORD_STRIDE)
    assert record.confidence == RecordConfidence.ACTIVE
    assert (record.x, record.y) == (26, 152)


def test_decode_record_classifies_empty():
    raw = _pack_record(counter=0, font_id=0, x=0, y=0, terminator=0)
    record = decode_record(raw, index=0, addr=RECORD_BASE)
    assert record.confidence == RecordConfidence.EMPTY


def test_decode_record_classifies_partial_on_out_of_bounds_position():
    raw = _pack_record(counter=0x10, font_id=0x15, x=9000, y=152)
    record = decode_record(raw, index=0, addr=RECORD_BASE)
    assert record.confidence == RecordConfidence.PARTIAL


def test_capture_snapshot_refuses_to_read_records_when_profile_invalid():
    ram = FakeRam()
    ram.load(FINGERPRINT_ADDR, b"\x00" * len(FINGERPRINT_BYTES))  # wrong bytes -> drift
    ram.load(RECORD_BASE, _pack_record(0x10, 0x15, 26, 152))  # a real-looking record, should never be read
    profile = _profile()

    snapshot = capture_snapshot(ram.read, profile)

    assert snapshot.validation == ValidationResult.LAYOUT_DRIFT_DETECTED
    assert snapshot.records == []
    assert not snapshot.usable


def test_capture_snapshot_reads_records_when_profile_valid():
    ram = FakeRam()
    ram.load(FINGERPRINT_ADDR, FINGERPRINT_BYTES)
    ram.load(RECORD_BASE + 0 * RECORD_STRIDE, _pack_record(0x00, 0x15, 10, 152))
    ram.load(RECORD_BASE + 1 * RECORD_STRIDE, _pack_record(0x10, 0x15, 26, 152))
    ram.load(RECORD_BASE + 2 * RECORD_STRIDE, _pack_record(0, 0, 0, 0, terminator=0))
    profile = _profile()

    snapshot = capture_snapshot(ram.read, profile)

    assert snapshot.usable
    assert len(snapshot.records) == 3
    assert len(snapshot.active_records) == 2
    assert snapshot.active_records[0].x == 10
    assert snapshot.active_records[1].x == 26


def test_compute_char_positions_accumulates_fallback_widths():
    from gcrts.glyph_char_map import code_for_char

    codes = [code_for_char("A"), code_for_char("B")]  # both half-width -> FALLBACK_HALF_WIDTH_PX (8) apart
    line = DecodedLine(
        start_char_index=0,
        char_count=2,
        x=100,
        y=50,
        alignment=LayoutAlignment.LEFT,
        char_codes=codes,
    )
    positions = compute_char_positions(line)
    assert positions == [(100, 50), (108, 50)]


def test_compute_char_positions_empty_line_has_no_positions():
    line = DecodedLine(start_char_index=0, char_count=0, x=100, y=50, alignment=LayoutAlignment.LEFT, char_codes=[])
    assert compute_char_positions(line) == []


def test_build_overrides_from_descriptor_flattens_in_record_order():
    from gcrts.glyph_char_map import code_for_char

    line1 = DecodedLine(
        start_char_index=0,
        char_count=1,
        x=10,
        y=100,
        alignment=LayoutAlignment.LEFT,
        char_codes=[code_for_char("A")],
    )
    line2 = DecodedLine(
        start_char_index=1,
        char_count=2,
        x=20,
        y=120,
        alignment=LayoutAlignment.LEFT,
        char_codes=[code_for_char("A"), code_for_char("B")],
    )
    decoded = DecodedLayoutDescriptor(
        version=1,
        paragraph_end=False,
        base_x=10,
        base_y=100,
        line_height=20,
        page_transition=None,
        lines=[line1, line2],
    )
    overrides = build_overrides_from_descriptor(decoded)
    # record index is assigned in flattened (line, then char) order, 0..2 --
    # NOT the char_stream's own start_char_index, matching how the game
    # fills the 14-slot record array per line, not per whole descriptor.
    assert [o.record_index for o in overrides] == [0, 1, 2]
    assert (overrides[0].x, overrides[0].y) == (10, 100)
    assert (overrides[1].x, overrides[1].y) == (20, 120)
    assert (overrides[2].x, overrides[2].y) == (28, 120)


def test_apply_and_restore_round_trip():
    ram = FakeRam()
    ram.load(FINGERPRINT_ADDR, FINGERPRINT_BYTES)
    ram.load(RECORD_BASE + 0 * RECORD_STRIDE, _pack_record(0x00, 0x15, 10, 152))
    ram.load(RECORD_BASE + 1 * RECORD_STRIDE, _pack_record(0x10, 0x15, 26, 152))
    profile = _profile(record_count=2)

    snapshot = capture_snapshot(ram.read, profile)
    assert len(snapshot.active_records) == 2

    from gcrts.renderer1_runtime import PositionOverride

    overrides = [PositionOverride(record_index=0, x=999, y=888)]
    result = apply_overrides_live(ram.read, ram.write, profile, snapshot, overrides)

    assert result.success
    moved = ram.read(RECORD_BASE + 0 * RECORD_STRIDE + 0x8, 2)
    assert struct.unpack("<H", moved)[0] == 999

    restore_result = restore_live(ram.read, ram.write, result.backups)
    assert restore_result.success
    restored = ram.read(RECORD_BASE + 0 * RECORD_STRIDE + 0x8, 2)
    assert struct.unpack("<H", restored)[0] == 10


def test_apply_rolls_back_on_missing_record_index():
    ram = FakeRam()
    ram.load(FINGERPRINT_ADDR, FINGERPRINT_BYTES)
    ram.load(RECORD_BASE + 0 * RECORD_STRIDE, _pack_record(0x00, 0x15, 10, 152))
    profile = _profile(record_count=1)
    snapshot = capture_snapshot(ram.read, profile)

    from gcrts.renderer1_runtime import PositionOverride

    overrides = [
        PositionOverride(record_index=0, x=999, y=888),
        PositionOverride(record_index=5, x=1, y=1),  # no such record in this snapshot
    ]
    result = apply_overrides_live(ram.read, ram.write, profile, snapshot, overrides)

    assert not result.success
    # record 0's write must have been rolled back, not left applied
    untouched = ram.read(RECORD_BASE + 0 * RECORD_STRIDE + 0x8, 2)
    assert struct.unpack("<H", untouched)[0] == 10


def test_apply_refuses_unusable_snapshot():
    ram = FakeRam()
    profile = _profile()
    from gcrts.renderer1_runtime import PositionOverride, Renderer1Snapshot

    unusable = Renderer1Snapshot(validation=ValidationResult.LAYOUT_DRIFT_DETECTED, records=[])
    result = apply_overrides_live(ram.read, ram.write, profile, unusable, [PositionOverride(0, 1, 1)])
    assert not result.success
    assert "layout_drift_detected" in result.error


def test_group_into_lines_clusters_by_y_not_index_adjacency():
    ram = FakeRam()
    ram.load(FINGERPRINT_ADDR, FINGERPRINT_BYTES)
    # Two lines interleaved in record-index order -- index adjacency must
    # NOT be used to decide "same line", only Y.
    ram.load(RECORD_BASE + 0 * RECORD_STRIDE, _pack_record(0x00, 0x15, 10, 152))
    ram.load(RECORD_BASE + 1 * RECORD_STRIDE, _pack_record(0x10, 0x15, 64, 171))
    ram.load(RECORD_BASE + 2 * RECORD_STRIDE, _pack_record(0x20, 0x15, 26, 152))
    profile = _profile(record_count=3)

    snapshot = capture_snapshot(ram.read, profile)
    lines = group_into_lines(snapshot)

    assert [line.y for line in lines] == [152, 171]
    assert [r.x for r in lines[0].records] == [10, 26]  # sorted by X within the line
    assert [r.x for r in lines[1].records] == [64]


def test_group_into_lines_ignores_non_active_records():
    ram = FakeRam()
    ram.load(FINGERPRINT_ADDR, FINGERPRINT_BYTES)
    ram.load(RECORD_BASE + 0 * RECORD_STRIDE, _pack_record(0x00, 0x15, 10, 152))
    ram.load(RECORD_BASE + 1 * RECORD_STRIDE, _pack_record(0, 0, 0, 0, terminator=0))  # EMPTY
    profile = _profile(record_count=2)

    snapshot = capture_snapshot(ram.read, profile)
    lines = group_into_lines(snapshot)

    assert len(lines) == 1 and len(lines[0].records) == 1


def test_renderer1_screen_objects_builds_one_object_per_line():
    ram = FakeRam()
    ram.load(FINGERPRINT_ADDR, FINGERPRINT_BYTES)
    ram.load(RECORD_BASE + 0 * RECORD_STRIDE, _pack_record(0x00, 0x15, 10, 152))
    ram.load(RECORD_BASE + 1 * RECORD_STRIDE, _pack_record(0x10, 0x15, 26, 152))
    ram.load(RECORD_BASE + 2 * RECORD_STRIDE, _pack_record(0x20, 0x15, 64, 171))
    profile = _profile(record_count=3)

    snapshot = capture_snapshot(ram.read, profile)
    objects = renderer1_screen_objects(snapshot, profile, snapshot_id=42)

    assert len(objects) == 2
    first = objects[0]
    assert first.metadata["glyph_count"] == 2
    assert first.metadata["snapshot_id"] == 42
    assert first.screen_bounds.y == 152
    from gcrts.screen_objects import ScreenObjectType, TextRepresentation

    assert first.object_type == ScreenObjectType.RUNTIME_TEXT
    assert first.text_representation == TextRepresentation.RUNTIME_TEXT_RENDERER_1
