"""Character-code -> glyph bitmap extraction for this game's custom font
system.

Reverse-engineered from FUN_8004aa08 in CAP0.EXE (see NOTES.md's
"BREAKTHROUGH" section):

    FUN_8007681c((&PTR_DAT_80093b34)[(param_3 & 0xffff) * 2], &DAT_800a4c00);

`PTR_DAT_80093b34` is a static table baked directly into the chapter
overlay executable's own compiled data (confirmed: zero runtime writers,
only one reference in the whole binary -- this read). Each character code
`c` has an 8-byte entry at `0x80093b34 + c*8`: a 4-byte pointer to that
glyph's *compressed* bitmap data (compressed with the same custom
RLE/LZ77/delta codec used for .CDB resource files, `gcrts/cdb_codec.py`),
followed by a 4-byte length. Decompressing gives 128 bytes = a 16x16
4bpp (2 pixels/byte) glyph cell.

The pointer TABLE itself is embedded in the overlay executable's own
compiled data segment (confirmed: falls within `CAP0.EXE`'s declared
[text_addr, text_addr+text_size) range). The compressed glyph DATA it
points to does not -- it lives in a separately, dynamically loaded
per-chapter resource blob (observed live at RAM 0x8001a200 onward).
Pass a captured dump of that blob (`glyph_data`/`glyph_data_base`) to
resolve glyph bytes; a disc-extracted file is not reliable here since the
resource actually resident at that address depends on which
chapter/scene is currently loaded -- use a fresh live RAM capture that
matches the session you're extracting from.

The 8-byte table entry's second 4 bytes are NOT the compressed byte
count (empirically: slicing to that length truncates streams before
their real 0xFF end marker). Each glyph decompresses to exactly
GLYPH_DECOMPRESSED_SIZE bytes, so this module instead hands the codec a
generous read window past the pointer and caps *output* at the true
glyph size.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from gcrts import cdb_codec

TABLE_RAM_ADDR = 0x80093B34
GLYPH_WIDTH = 16
GLYPH_HEIGHT = 16
GLYPH_DECOMPRESSED_SIZE = GLYPH_WIDTH * GLYPH_HEIGHT // 2  # 4bpp: 2px/byte

# Standard PS-EXE header size before the executable's own text/data body.
PS_EXE_HEADER_SIZE = 0x800


@dataclass
class GlyphAtlas:
    exe_data: bytes
    text_addr: int
    text_size: int
    # the compressed glyph *data* the table points to lives in a separate,
    # dynamically-loaded per-chapter resource blob, not in the overlay EXE
    # itself -- supply a captured dump of it (e.g. a live RAM dump of
    # 0x8001a200 onward) plus its RAM base address to resolve glyph bytes.
    glyph_data: bytes | None = None
    glyph_data_base: int | None = None

    @classmethod
    def from_exe_file(cls, path: str, glyph_data: bytes | None = None,
                       glyph_data_base: int | None = None) -> "GlyphAtlas":
        with open(path, "rb") as f:
            data = f.read()
        if data[:8] != b"PS-X EXE":
            raise ValueError(f"{path} is not a PS-X EXE file")
        text_addr, text_size = struct.unpack_from("<II", data, 0x18)
        return cls(data, text_addr, text_size, glyph_data, glyph_data_base)

    def _ram_to_file_offset(self, ram_addr: int) -> int:
        if not (self.text_addr <= ram_addr < self.text_addr + self.text_size):
            raise ValueError(
                f"RAM address {ram_addr:#x} is outside this EXE's declared range "
                f"[{self.text_addr:#x}, {self.text_addr + self.text_size:#x})"
            )
        return PS_EXE_HEADER_SIZE + (ram_addr - self.text_addr)

    def table_entry(self, code: int) -> tuple[int, int] | None:
        """Return (compressed_data_ram_addr, length) for a character code,
        or None if the table entry itself isn't resolvable from this EXE
        file (the entry's ram address must be inside the EXE's own range;
        the pointer *value* it holds usually is not -- see raw_compressed_bytes)."""
        entry_addr = TABLE_RAM_ADDR + code * 8
        try:
            off = self._ram_to_file_offset(entry_addr)
        except ValueError:
            return None
        ptr, length = struct.unpack_from("<II", self.exe_data, off)
        return ptr, length

    # A generous read window past the pointer: the table's own "length"
    # field does NOT hold the compressed byte count (confirmed empirically
    # -- truncating to it cuts streams off before their real 0xFF end
    # marker). Each glyph decompresses to exactly GLYPH_DECOMPRESSED_SIZE
    # bytes, so instead we hand the codec a generous window and cap
    # *output* at the true glyph size, matching how FUN_8004aa08 actually
    # calls FUN_8007681c (source pointer only, no explicit length).
    RAW_WINDOW = 512

    def raw_compressed_bytes(self, code: int) -> bytes | None:
        entry = self.table_entry(code)
        if entry is None:
            return None
        ptr, _length = entry
        # first try resolving against the EXE's own data (in case some
        # entries genuinely point into the overlay itself)
        try:
            off = self._ram_to_file_offset(ptr)
            return self.exe_data[off : off + self.RAW_WINDOW]
        except ValueError:
            pass
        # otherwise resolve against the separately-captured glyph data blob
        if self.glyph_data is not None and self.glyph_data_base is not None:
            blob_size = len(self.glyph_data)
            if self.glyph_data_base <= ptr < self.glyph_data_base + blob_size:
                off = ptr - self.glyph_data_base
                return self.glyph_data[off : off + self.RAW_WINDOW]
        return None

    def decode_glyph(self, code: int) -> bytes | None:
        """Return the decompressed 128-byte (16x16, 4bpp) glyph bitmap for
        a character code, or None if unresolvable/decompression failed."""
        raw = self.raw_compressed_bytes(code)
        if raw is None:
            return None
        try:
            out = cdb_codec.decompress(raw, max_output_size=GLYPH_DECOMPRESSED_SIZE)
        except Exception:
            return None
        if len(out) != GLYPH_DECOMPRESSED_SIZE:
            return None
        return out

    def glyph_to_pixels(self, glyph_bytes: bytes) -> list[list[int]]:
        """Unpack a 128-byte 4bpp glyph into a 16x16 grid of 0-15 pixel values."""
        rows: list[list[int]] = []
        for y in range(GLYPH_HEIGHT):
            row: list[int] = []
            for x in range(0, GLYPH_WIDTH, 2):
                idx = y * (GLYPH_WIDTH // 2) + x // 2
                b = glyph_bytes[idx] if idx < len(glyph_bytes) else 0
                row.append(b & 0xF)
                row.append((b >> 4) & 0xF)
            rows.append(row)
        return rows
