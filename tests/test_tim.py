import struct

from gcrts.tim import find_tim_images

RED = 0x001F  # BGR555: R=31
BLUE = 0x7C00  # BGR555: B=31
WHITE = 0x7FFF
BLACK = 0x0000


def block(length: int, x: int, y: int, w: int, h: int, payload: bytes) -> bytes:
    return struct.pack("<IHHHH", length, x, y, w, h) + payload


def make_4bpp_tim() -> bytes:
    palette = struct.pack("<HH", RED, BLUE)
    clut = block(12 + len(palette), 0, 0, 2, 1, palette)
    # iw=1 halfword -> 2 bytes/row -> 4px wide; 2 rows -> 4 bytes total.
    # row0: 0x01 -> (BLUE,RED); 0x00 -> (RED,RED)
    # row1: 0x10 -> (RED,BLUE); 0x11 -> (BLUE,BLUE)
    pixel_data = bytes([0x01, 0x00, 0x10, 0x11])
    image = block(12 + len(pixel_data), 0, 0, 1, 2, pixel_data)
    flag = struct.pack("<I", 0x8)  # bpp=0 (4bpp), has_clut
    return b"\x10\x00\x00\x00" + flag + clut + image


def make_16bpp_tim() -> bytes:
    pixel_data = struct.pack("<HH", BLACK, WHITE)
    image = block(12 + len(pixel_data), 0, 0, 2, 1, pixel_data)
    flag = struct.pack("<I", 0x2)  # bpp=2 (16bpp direct), no clut
    return b"\x10\x00\x00\x00" + flag + image


def test_decodes_4bpp_indexed_image():
    data = make_4bpp_tim()
    results = find_tim_images(data)
    assert len(results) == 1
    img = results[0]
    assert img.bpp_mode == 0
    assert img.width == 4
    assert img.height == 2
    assert img.pixels == [
        (0, 0, 248),  # row0: BLUE
        (248, 0, 0),  # row0: RED
        (248, 0, 0),  # row0: RED
        (248, 0, 0),  # row0: RED
        (248, 0, 0),  # row1: RED
        (0, 0, 248),  # row1: BLUE
        (0, 0, 248),  # row1: BLUE
        (0, 0, 248),  # row1: BLUE
    ]


def test_decodes_16bpp_direct_image():
    data = make_16bpp_tim()
    results = find_tim_images(data)
    assert len(results) == 1
    img = results[0]
    assert img.bpp_mode == 2
    assert img.width == 2
    assert img.height == 1
    assert img.pixels == [(0, 0, 0), (248, 248, 248)]


def test_rejects_coincidental_magic_in_unrelated_data():
    # The magic bytes with a plausible-looking flag, but garbage/inconsistent
    # length fields afterward -- should not be mistaken for a real TIM.
    data = b"\x10\x00\x00\x00" + b"\x08\x00\x00\x00" + b"\xAA" * 40
    assert find_tim_images(data) == []


def test_finds_multiple_images_in_sequence():
    data = make_4bpp_tim() + b"\x00\x00" + make_16bpp_tim()
    results = find_tim_images(data)
    assert len(results) == 2
    assert results[0].bpp_mode == 0
    assert results[1].bpp_mode == 2


def test_end_offset_points_past_image_data():
    data = make_4bpp_tim()
    results = find_tim_images(data)
    assert results[0].end_offset == len(data)
