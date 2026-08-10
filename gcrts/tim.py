"""Image & Texture Engine (minimal subset): PS1 TIM texture decoding.

Pulled forward from Phase 5 because locating the game's actual font
(needed to crack its dialogue text encoding) required finding and
rendering candidate texture data to check whether it's a glyph atlas.
Only handles what's been validated against a real disc image so far:
4bpp/8bpp indexed color (with CLUT) and 16bpp direct color. 24bpp direct
color is not implemented (not encountered yet).

A TIM asset is: 4-byte magic (0x10000000) + 4-byte flag, then an optional
CLUT block (present if flag bit 3 is set) and an image data block. Both
blocks share the same shape: a 4-byte byte-length, a 2-byte X/Y position,
a 2-byte W/H size (W in 16-bit-halfword units, not pixels), then payload.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

_MAGIC = b"\x10\x00\x00\x00"
_HEADER_SIZE = 8  # magic + flag


@dataclass
class TimImage:
    offset: int
    bpp_mode: int  # 0=4bpp indexed, 1=8bpp indexed, 2=16bpp direct, 3=24bpp direct
    width: int  # pixels
    height: int  # pixels
    pixels: list[tuple[int, int, int]]  # row-major RGB, length == width*height
    end_offset: int  # exclusive byte offset where this TIM's data ends


def _bgr555_to_rgb(value: int) -> tuple[int, int, int]:
    r = (value & 0x1F) << 3
    g = ((value >> 5) & 0x1F) << 3
    b = ((value >> 10) & 0x1F) << 3
    return (r, g, b)


def _find_tim_at(data: bytes, offset: int) -> TimImage | None:
    """Try to parse a structurally valid TIM at an exact offset.

    Every length field is cross-checked against the W/H it should imply
    (clut_len == 12 + cw*ch*2, img_len == 12 + iw*ih*2) -- this is what
    rejects the vast majority of coincidental 4-byte magic matches in
    unrelated binary data (see gcrts/encoding.py for the same principle
    applied to text).
    """
    n = len(data)
    if offset + _HEADER_SIZE > n:
        return None
    if data[offset : offset + 4] != _MAGIC:
        return None

    flag = struct.unpack_from("<I", data, offset + 4)[0]
    if (flag & ~0xF) != 0:
        return None
    bpp_mode = flag & 0x3
    has_clut = bool(flag & 0x8)

    pos = offset + _HEADER_SIZE
    palette: list[tuple[int, int, int]] = []

    if has_clut:
        if pos + 4 > n:
            return None
        clut_len = struct.unpack_from("<I", data, pos)[0]
        if clut_len < 12 or pos + clut_len > n:
            return None
        cw, ch = struct.unpack_from("<HH", data, pos + 8)
        if cw == 0 or ch == 0 or cw > 256 or ch > 256:
            return None
        if clut_len != 12 + cw * ch * 2:
            return None
        pal_raw = data[pos + 12 : pos + 12 + cw * ch * 2]
        palette = [
            _bgr555_to_rgb(struct.unpack_from("<H", pal_raw, i * 2)[0])
            for i in range(cw * ch)
        ]
        pos += clut_len

    if pos + 4 > n:
        return None
    img_len = struct.unpack_from("<I", data, pos)[0]
    if img_len < 12 or pos + img_len > n:
        return None
    iw, ih = struct.unpack_from("<HH", data, pos + 8)
    if iw == 0 or ih == 0 or iw > 1024 or ih > 1024:
        return None
    if img_len != 12 + iw * ih * 2:
        return None

    pixel_raw = data[pos + 12 : pos + 12 + img_len - 12]
    end_offset = pos + img_len

    if bpp_mode == 2:  # 16bpp direct color: one pixel per halfword
        width = iw
        pixels = [
            _bgr555_to_rgb(struct.unpack_from("<H", pixel_raw, i * 2)[0])
            for i in range(iw * ih)
        ]
    elif bpp_mode == 1:  # 8bpp indexed: one pixel per byte
        if not palette:
            return None
        width = iw * 2
        pixels = [
            palette[b] if b < len(palette) else (0, 0, 0)
            for row in range(ih)
            for b in pixel_raw[row * width : row * width + width]
        ]
    elif bpp_mode == 0:  # 4bpp indexed: two pixels per byte (low nibble first)
        if not palette:
            return None
        width = iw * 4
        pixels = []
        bytes_per_row = iw * 2
        for row in range(ih):
            row_bytes = pixel_raw[row * bytes_per_row : (row + 1) * bytes_per_row]
            for byte in row_bytes:
                pixels.append(palette[byte & 0xF])
                pixels.append(palette[(byte >> 4) & 0xF])
    else:  # bpp_mode == 3: 24bpp direct color -- not implemented, no case seen yet
        return None

    return TimImage(
        offset=offset,
        bpp_mode=bpp_mode,
        width=width,
        height=ih,
        pixels=pixels,
        end_offset=end_offset,
    )


def find_tim_images(data: bytes) -> list[TimImage]:
    """Scan for every structurally-valid TIM image in a byte buffer."""
    results: list[TimImage] = []
    start = 0
    while True:
        idx = data.find(_MAGIC, start)
        if idx == -1:
            break
        start = idx + 1
        match = _find_tim_at(data, idx)
        if match is not None:
            results.append(match)
    return results
