"""Phase 6: font extension -- add glyphs for characters missing from the
base font (e.g. plain ASCII punctuation like "," or accented Latin
letters), so translated text isn't limited to gcrts.glyph_char_map's
existing 272 codes.

Architecture recap (see gcrts/glyph_atlas.py and NOTES.md's "PHASE 2
BREAKTHROUGH"): a character code indexes an 8-byte table entry
(pointer + length) baked into the chapter overlay EXE; the pointer
targets compressed glyph data in a separately-loaded per-chapter blob.
Phase 2 also found that codes 0x10d-0x143 (55 codes right after the
fixed base range ends at 0x10c) have PLAUSIBLE table entries -- real
pointers into the glyph blob -- but decode to nothing in any given
capture, because that range is a per-scene dynamic kanji cache the game
fills in on demand. Nothing in a given session actually depends on
those exact bytes being anything in particular, which makes them safe,
reusable slots for injecting new custom glyphs FOR THAT SESSION (this
is a live-RAM experiment, not a permanent on-disc font patch).

New glyph data is encoded with the codec's simplest, always-valid
control byte: a literal run (control < 0x80: copy the next `control+1`
bytes verbatim), terminated by 0xFF. This sidesteps needing a real
RLE/LZ77 compressor -- gcrts/cdb_codec.py only implements decompress().
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from gcrts.glyph_atlas import GLYPH_DECOMPRESSED_SIZE, GLYPH_HEIGHT, GLYPH_WIDTH, GlyphAtlas
from gcrts.glyph_char_map import CHAR_TO_CODE, CODE_TO_CHAR

# The per-scene dynamic kanji cache hole found in Phase 2 -- empirically
# unused/overwritable within a given live session.
UNUSED_CODE_RANGE = range(0x10D, 0x144)

DEFAULT_FONT_PATH = r"C:\Windows\Fonts\arial.ttf"


FONT_BACKGROUND_VALUE = 0x4
FONT_INK_VALUE = 0x6


def render_char_bitmap(
    ch: str, font_path: str = DEFAULT_FONT_PATH, font_size: int = 14, binary: bool = True
) -> list[list[int]]:
    """Rasterize a single character into a 16x16 grid of 0-15 (4bpp)
    pixel values, matching gcrts.glyph_atlas.GlyphAtlas.glyph_to_pixels'
    layout (row-major, [y][x]).

    Live testing revealed the real font's palette convention: background
    is index 4 (NOT 0) and ink is index 6 (NOT 15) -- confirmed by
    inspecting the actual decompressed bytes of the existing "A" glyph,
    whose pixel-value histogram is overwhelmingly 4 (background) and 6
    (the "A" stroke), with a handful of 0/2/3/5 only on internal
    antialiased edges. A bitmap built with the naive 0=background/
    15=foreground assumption renders in-game as a solid opaque block,
    not a transparent-background glyph -- index 0 is evidently just
    another opaque palette color for this slot, not a transparency key.

    `binary=True` (default) thresholds to pure background/ink (no
    in-between antialiasing shades), since we don't know the exact
    antialiasing palette ramp the original artists used and a clean
    binary shape is safer than guessing intermediate values."""
    img = Image.new("L", (GLYPH_WIDTH, GLYPH_HEIGHT), 0)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(font_path, font_size)
    bbox = draw.textbbox((0, 0), ch, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (GLYPH_WIDTH - w) // 2 - bbox[0]
    y = (GLYPH_HEIGHT - h) // 2 - bbox[1]
    draw.text((x, y), ch, font=font, fill=255)
    raw = [[img.getpixel((x, y)) for x in range(GLYPH_WIDTH)] for y in range(GLYPH_HEIGHT)]
    if binary:
        return [[FONT_INK_VALUE if v >= 128 else FONT_BACKGROUND_VALUE for v in row] for row in raw]
    # scale anti-aliased 0-255 into the [background, ink] range instead of 0-15
    lo, hi = FONT_BACKGROUND_VALUE, FONT_INK_VALUE
    return [[lo + (v * (hi - lo)) // 255 for v in row] for row in raw]


def pixels_to_glyph_bytes(pixels: list[list[int]]) -> bytes:
    """Inverse of GlyphAtlas.glyph_to_pixels: pack a 16x16 4bpp pixel
    grid into the game's 128-byte glyph cell format (2px/byte, low
    nibble first)."""
    out = bytearray(GLYPH_DECOMPRESSED_SIZE)
    for y in range(GLYPH_HEIGHT):
        for x in range(0, GLYPH_WIDTH, 2):
            lo = pixels[y][x] & 0xF
            hi = pixels[y][x + 1] & 0xF
            out[y * (GLYPH_WIDTH // 2) + x // 2] = lo | (hi << 4)
    return bytes(out)


def encode_glyph_literal(glyph_bytes: bytes) -> bytes:
    """Encode raw glyph bytes as a literal run in the CDB codec format
    (control byte < 0x80 means "copy the next control+1 bytes verbatim"),
    terminated by 0xFF. Always valid regardless of content, unlike
    RLE/LZ77/delta encoding, which would need matching gcrts.cdb_codec's
    exact compressor (not implemented -- only decompress() exists)."""
    if len(glyph_bytes) > 128:
        raise ValueError("literal run control byte can encode at most 128 bytes")
    return bytes([len(glyph_bytes) - 1]) + glyph_bytes + b"\xff"


def next_unused_code(atlas: GlyphAtlas, taken: set[int] = frozenset()) -> int:
    """Return the first code in UNUSED_CODE_RANGE that currently fails to
    decode (i.e. is safe to repurpose) and isn't already claimed by
    `taken` (codes assigned earlier in the same session)."""
    for code in UNUSED_CODE_RANGE:
        if code in taken:
            continue
        if atlas.decode_glyph(code) is None:
            return code
    raise RuntimeError("no unused glyph code slots left in UNUSED_CODE_RANGE")


def inject_glyph_live(
    code: int,
    ch: str,
    atlas: GlyphAtlas,
    gdb_client,
    font_path: str = DEFAULT_FONT_PATH,
    font_size: int = 14,
    binary: bool = True,
) -> None:
    """Render `ch`, encode it, and write it directly into the live glyph
    blob at `code`'s existing table-entry pointer address (no pointer
    table changes needed -- we reuse the pointer that's already there).
    Also registers `ch` in gcrts.glyph_char_map's CODE_TO_CHAR/
    CHAR_TO_CODE for the rest of this process's lifetime.

    `font_path`/`font_size`/`binary` are forwarded to render_char_bitmap
    so callers (e.g. gcrts.font_workbench, testing alternate styles) can
    actually control how the glyph is rendered instead of always getting
    the default 14pt Arial binary rendering."""
    entry = atlas.table_entry(code)
    if entry is None:
        raise ValueError(f"code {code:#x} has no table entry to reuse")
    ptr, _length = entry

    pixels = render_char_bitmap(ch, font_path=font_path, font_size=font_size, binary=binary)
    glyph_bytes = pixels_to_glyph_bytes(pixels)
    encoded = encode_glyph_literal(glyph_bytes)

    if not gdb_client.write_memory(ptr, encoded):
        raise RuntimeError(f"live write to {ptr:#x} failed")

    CODE_TO_CHAR[code] = ch
    if ch not in CHAR_TO_CODE:
        CHAR_TO_CODE[ch] = code
