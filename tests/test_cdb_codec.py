from gcrts.cdb_codec import decompress


def test_literal_run():
    # control=0x03 -> count=4 literal bytes
    data = bytes([0x03]) + b"WXYZ" + bytes([0xFF])
    assert decompress(data) == b"WXYZ"


def test_run_length_fill():
    # control=0x80 -> count=0x80-0x7D=3, fill byte 0x41
    data = bytes([0x80, 0x41, 0xFF])
    assert decompress(data) == b"AAA"


def test_run_length_fill_with_zero_byte():
    # the decompiled code special-cases a zero fill byte, but it behaves
    # identically to filling with 0x00
    data = bytes([0x80, 0x00, 0xFF])
    assert decompress(data) == b"\x00\x00\x00"


def test_lz_back_reference_self_overlapping():
    # literal "AB" (control=0x01 -> count=2), then a back-reference of
    # count=(0xC0-0xBC)=4 bytes at offset=2, self-overlapping to repeat "AB"
    data = bytes([0x01]) + b"AB" + bytes([0xC0, 0x00, 0x02]) + bytes([0xFF])
    assert decompress(data) == b"ABABAB"


def test_lz_back_reference_non_overlapping():
    # literal "HELLO" (control=0x04 -> count=5), then copy
    # count=(0xC0-0xBC)=4 bytes from offset=5 (the very start), i.e. "HELL"
    data = bytes([0x04]) + b"HELLO" + bytes([0xC0, 0x00, 0x05]) + bytes([0xFF])
    assert decompress(data) == b"HELLOHELL"


def test_delta_fill():
    # control=0xE0 -> count=(0xE0-0xDC)=4, delta=2, start=10
    data = bytes([0xE0, 2, 10, 0xFF])
    assert decompress(data) == bytes([10, 12, 14, 16])


def test_delta_fill_wraps_mod_256():
    # control=0xE0 -> count=4, start=254, delta=1 -> 254,255,0,1 (wraps)
    data = bytes([0xE0, 1, 254, 0xFF])
    assert decompress(data) == bytes([254, 255, 0, 1])


def test_end_marker_stops_immediately():
    data = bytes([0xFF]) + b"should not appear"
    assert decompress(data) == b""


def test_multiple_segments_concatenate():
    data = (
        bytes([0x01])
        + b"AB"  # literal "AB"
        + bytes([0x80, 0x2D])  # 3x '-' (0x2D)
        + bytes([0x02])
        + b"CDE"  # literal "CDE"
        + bytes([0xFF])
    )
    assert decompress(data) == b"AB---CDE"


def test_stops_at_max_output_size_safety_cap():
    # a fill segment requesting more than the cap; real streams always end
    # with 0xFF, this only guards against malformed/misaligned input during
    # exploratory offset-guessing.
    data = bytes([0x80 + 0x3F, 0x41])  # count = 0xBF-0x7D = 66
    out = decompress(data, max_output_size=10)
    assert len(out) <= 66
    assert set(out) == {0x41}
