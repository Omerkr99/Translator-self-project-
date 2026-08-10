import struct

import pytest

from gcrts.editor_layout_plan import EditorLayoutPlan, LayoutAlignment, LayoutLine, PageTransition
from gcrts.layout_descriptor import (
    HEADER_SIZE,
    LINE_RECORD_SIZE,
    MAGIC,
    MAX_LINE_CHARS,
    MAX_LINES,
    MAX_TOTAL_CHARS,
    DescriptorValidationError,
    decode_layout_descriptor,
    encode_layout_descriptor,
)
from gcrts.render_mode import RenderMode


def _plan(lines, paragraph_end=True, page_transition=PageTransition.WAIT_FOR_INPUT):
    return EditorLayoutPlan(
        unit_id="s_line_00",
        render_mode=RenderMode.CUSTOM_ENGINE,
        language="en",
        source_text="",
        edited_text="",
        lines=lines,
        paragraph_end=paragraph_end,
        page_transition=page_transition,
    )


def test_header_and_line_record_sizes_match_the_formal_spec():
    # These exact sizes are load-bearing for the (future) MIPS parser's
    # fixed-offset arithmetic -- a size change here must be a deliberate,
    # documented spec change, not an accidental struct-format edit.
    assert HEADER_SIZE == 18
    assert LINE_RECORD_SIZE == 10


def test_golden_single_line_exact_bytes():
    # "Hi." -> glyph codes 0xc3 ('H'), 0xde ('i'), 0xfe ('.') -- confirmed
    # via gcrts.glyph_char_map.code_for_char, not guessed.
    plan = _plan([LayoutLine("Hi.", 0, 3, 10, 160, LayoutAlignment.LEFT)])
    data = encode_layout_descriptor(plan)

    expected_header = struct.pack(
        "<4sHHHhhHBB",
        MAGIC,
        1,  # version
        1,  # flags: paragraph_end bit set
        1,  # line_count
        10,  # base_x (first line's x)
        160,  # base_y (first line's y)
        0,  # line_height (only one line -> 0)
        0,  # page_transition: wait_for_input
        0,  # reserved
    )
    expected_line_record = struct.pack("<HHhhBB", 0, 3, 10, 160, 0, 0)
    expected_char_stream = struct.pack("<3H", 0xC3, 0xDE, 0xFE)

    assert data == expected_header + expected_line_record + expected_char_stream


def test_golden_two_lines_computes_line_height_and_offsets():
    plan = _plan(
        [
            LayoutLine("Hi.", 0, 3, 10, 160, LayoutAlignment.LEFT),
            LayoutLine("Hi.", 3, 6, 10, 176, LayoutAlignment.CENTER),
        ]
    )
    data = encode_layout_descriptor(plan)

    header = data[:HEADER_SIZE]
    magic, version, flags, line_count, base_x, base_y, line_height, page_transition, reserved = struct.unpack(
        "<4sHHHhhHBB", header
    )
    assert (line_count, base_x, base_y, line_height) == (2, 10, 160, 16)

    second_record = data[HEADER_SIZE + LINE_RECORD_SIZE : HEADER_SIZE + 2 * LINE_RECORD_SIZE]
    start_char_index, char_count, x, y, alignment, line_reserved = struct.unpack("<HHhhBB", second_record)
    # second line's characters start right after the first line's 3
    assert (start_char_index, char_count, alignment) == (3, 3, 1)  # 1 = CENTER


def test_encode_resolves_center_alignment_into_a_final_x():
    # Alternative Text Engine Phase 6 design-review fix: the binary format
    # has no per-line width-budget field, so a future MIPS consumer would
    # have nothing to center within -- alignment must be resolved to a
    # final x ONCE, at encode time, not left for the consumer to compute.
    # "Hi" -> 2 chars * FALLBACK_HALF_WIDTH_PX(8) = 16px measured (no atlas).
    line = LayoutLine("Hi", 0, 2, 10, 160, LayoutAlignment.CENTER, max_width_px=100)
    data = encode_layout_descriptor(_plan([line]))
    record = data[HEADER_SIZE : HEADER_SIZE + LINE_RECORD_SIZE]
    _, _, x, _, alignment, _ = struct.unpack("<HHhhBB", record)
    assert x == 10 + (100 - 16) // 2  # base_x + (budget - measured_width) // 2
    assert alignment == 1  # CENTER -- kept as informational metadata


def test_encode_resolves_right_alignment_into_a_final_x():
    line = LayoutLine("Hi", 0, 2, 10, 160, LayoutAlignment.RIGHT, max_width_px=100)
    data = encode_layout_descriptor(_plan([line]))
    record = data[HEADER_SIZE : HEADER_SIZE + LINE_RECORD_SIZE]
    _, _, x, _, alignment, _ = struct.unpack("<HHhhBB", record)
    assert x == 10 + (100 - 16)  # base_x + (budget - measured_width)
    assert alignment == 2  # RIGHT


def test_encode_left_alignment_is_unaffected_by_resolution():
    line = LayoutLine("Hi", 0, 2, 10, 160, LayoutAlignment.LEFT, max_width_px=100)
    data = encode_layout_descriptor(_plan([line]))
    record = data[HEADER_SIZE : HEADER_SIZE + LINE_RECORD_SIZE]
    _, _, x, _, _, _ = struct.unpack("<HHhhBB", record)
    assert x == 10


def test_roundtrip_preserves_text_position_and_alignment():
    plan = _plan(
        [
            LayoutLine("Hello there.", 0, 12, 10, 160, LayoutAlignment.LEFT),
            LayoutLine("Goodbye.", 13, 21, 20, 176, LayoutAlignment.RIGHT),
        ],
        paragraph_end=False,
        page_transition=PageTransition.AUTO_CONTINUE,
    )
    data = encode_layout_descriptor(plan)
    decoded = decode_layout_descriptor(data)

    assert decoded.paragraph_end is False
    assert decoded.page_transition == PageTransition.AUTO_CONTINUE
    assert [line.decoded_text() for line in decoded.lines] == ["Hello there.", "Goodbye."]
    assert [(line.x, line.y, line.alignment) for line in decoded.lines] == [
        (10, 160, LayoutAlignment.LEFT),
        (20, 176, LayoutAlignment.RIGHT),
    ]


def test_roundtrip_with_no_lines_at_all():
    plan = _plan([])
    data = encode_layout_descriptor(plan)
    decoded = decode_layout_descriptor(data)
    assert decoded.lines == []


def test_encode_rejects_too_many_lines_without_truncating():
    lines = [LayoutLine("a", i, i + 1, 10, 160, LayoutAlignment.LEFT) for i in range(MAX_LINES + 1)]
    with pytest.raises(DescriptorValidationError, match="exceeds MAX_LINES"):
        encode_layout_descriptor(_plan(lines))


def test_encode_rejects_a_line_with_too_many_characters():
    huge_line = LayoutLine("a" * (MAX_LINE_CHARS + 1), 0, MAX_LINE_CHARS + 1, 10, 160, LayoutAlignment.LEFT)
    with pytest.raises(DescriptorValidationError, match="exceeds MAX_LINE_CHARS"):
        encode_layout_descriptor(_plan([huge_line]))


def test_encode_rejects_total_characters_over_the_cap():
    # Several lines individually under MAX_LINE_CHARS but summing past
    # MAX_TOTAL_CHARS.
    per_line = MAX_LINE_CHARS
    count = MAX_TOTAL_CHARS // per_line + 2
    lines = [LayoutLine("a" * per_line, 0, per_line, 10, 160, LayoutAlignment.LEFT) for _ in range(count)]
    with pytest.raises(DescriptorValidationError, match="exceeds MAX_TOTAL_CHARS"):
        encode_layout_descriptor(_plan(lines))


def test_encode_rejects_a_line_using_an_unmapped_character():
    with pytest.raises(DescriptorValidationError, match="unmapped character"):
        encode_layout_descriptor(_plan([LayoutLine("café", 0, 4, 10, 160, LayoutAlignment.LEFT)]))


def test_decode_rejects_bad_magic():
    plan = _plan([LayoutLine("Hi.", 0, 3, 10, 160, LayoutAlignment.LEFT)])
    data = bytearray(encode_layout_descriptor(plan))
    data[0:4] = b"XXXX"
    with pytest.raises(DescriptorValidationError, match="bad magic"):
        decode_layout_descriptor(bytes(data))


def test_decode_rejects_unsupported_version():
    plan = _plan([LayoutLine("Hi.", 0, 3, 10, 160, LayoutAlignment.LEFT)])
    data = bytearray(encode_layout_descriptor(plan))
    data[4:6] = struct.pack("<H", 99)
    with pytest.raises(DescriptorValidationError, match="unsupported version"):
        decode_layout_descriptor(bytes(data))


def test_decode_rejects_a_truncated_buffer():
    plan = _plan([LayoutLine("Hi.", 0, 3, 10, 160, LayoutAlignment.LEFT)])
    data = encode_layout_descriptor(plan)
    with pytest.raises(DescriptorValidationError, match="too short"):
        decode_layout_descriptor(data[:-2])


def test_decode_rejects_a_buffer_shorter_than_the_header():
    with pytest.raises(DescriptorValidationError, match="too short for header"):
        decode_layout_descriptor(b"\x00\x01\x02")


def test_decode_rejects_a_header_claiming_too_many_lines():
    header = struct.pack("<4sHHHhhHBB", MAGIC, 1, 0, MAX_LINES + 1, 10, 160, 0, 0, 0)
    with pytest.raises(DescriptorValidationError, match="exceeds MAX_LINES"):
        decode_layout_descriptor(header)


def test_decode_rejects_nonzero_reserved_byte():
    plan = _plan([LayoutLine("Hi.", 0, 3, 10, 160, LayoutAlignment.LEFT)])
    data = bytearray(encode_layout_descriptor(plan))
    data[17] = 1  # header's reserved byte
    with pytest.raises(DescriptorValidationError, match="reserved byte"):
        decode_layout_descriptor(bytes(data))
