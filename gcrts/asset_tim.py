"""Editable standard-TIM adapter used by the Asset Inspector."""
from __future__ import annotations

import io
import struct
from dataclasses import dataclass, replace
from pathlib import Path

from PIL import Image


def bgr555_to_rgba(value: int, transparent: bool = False) -> tuple[int, int, int, int]:
    return ((value & 31) * 255 // 31, ((value >> 5) & 31) * 255 // 31,
            ((value >> 10) & 31) * 255 // 31, 0 if transparent else 255)


@dataclass(frozen=True)
class EditableTim:
    bpp: int
    width: int
    height: int
    indices: bytes | None
    direct_pixels: tuple[int, ...] | None
    palette: tuple[int, ...]
    clut_x: int
    clut_y: int
    image_x: int
    image_y: int

    @property
    def format_name(self) -> str:
        return {0: "TIM_4BPP_INDEXED", 1: "TIM_8BPP_INDEXED", 2: "TIM_16BPP_DIRECT"}[self.bpp]

    def usage_counts(self) -> list[int]:
        counts = [0] * len(self.palette)
        for index in self.indices or b"":
            if index < len(counts): counts[index] += 1
        return counts

    def to_image(self) -> Image.Image:
        image = Image.new("RGBA", (self.width, self.height))
        if self.indices is not None:
            pixels = [bgr555_to_rgba(self.palette[i], self.palette[i] == 0) for i in self.indices]
        else:
            pixels = [bgr555_to_rgba(value) for value in self.direct_pixels or ()]
        image.putdata(pixels)
        return image

    def export_png(self, path: str | Path) -> None:
        self.to_image().save(path, "PNG")

    def with_palette_entry(self, index: int, value: int) -> "EditableTim":
        if not self.palette: raise ValueError("direct-color TIM has no palette")
        palette = list(self.palette); palette[index] = value & 0xFFFF
        return replace(self, palette=tuple(palette))

    def with_indices(self, indices: bytes) -> "EditableTim":
        if self.indices is None: raise ValueError("direct-color TIM has no indices")
        if len(indices) != self.width * self.height: raise ValueError("pixel index length mismatch")
        if indices and max(indices) >= len(self.palette): raise ValueError("pixel index exceeds palette")
        return replace(self, indices=bytes(indices))

    def import_palette_preserving_png(self, source: str | Path | Image.Image) -> "EditableTim":
        if self.indices is None: raise ValueError("palette-preserving import requires indexed TIM")
        image = source.convert("RGBA") if isinstance(source, Image.Image) else Image.open(source).convert("RGBA")
        if image.size != (self.width, self.height):
            raise ValueError(f"PNG dimensions {image.size} do not match {(self.width, self.height)}")
        rgba_palette = [bgr555_to_rgba(v, v == 0) for v in self.palette]
        exact = {rgba: i for i, rgba in enumerate(rgba_palette)}
        output = bytearray()
        missing: set[tuple[int, int, int, int]] = set()
        for pixel in image.getdata():
            if pixel[3] == 0:
                transparent = next((i for i, value in enumerate(self.palette) if value == 0), None)
                if transparent is None: missing.add(pixel)
                else: output.append(transparent)
                continue
            index = exact.get(pixel)
            if index is None:
                missing.add(pixel); continue
            output.append(index)
        if missing:
            raise ValueError(f"PNG contains {len(missing)} colors not present in the original palette")
        return self.with_indices(bytes(output))


def decode_tim(data: bytes) -> EditableTim:
    if data[:4] != b"\x10\0\0\0" or len(data) < 20: raise ValueError("not a TIM image")
    flags = struct.unpack_from("<I", data, 4)[0]
    bpp, has_clut, pos = flags & 3, bool(flags & 8), 8
    palette: tuple[int, ...] = (); clut_x = clut_y = 0
    if has_clut:
        length, clut_x, clut_y, cw, ch = struct.unpack_from("<IHHHH", data, pos)
        if length != 12 + cw * ch * 2: raise ValueError("invalid TIM CLUT length")
        palette = struct.unpack_from(f"<{cw*ch}H", data, pos + 12)
        pos += length
    length, image_x, image_y, word_width, height = struct.unpack_from("<IHHHH", data, pos)
    if length != 12 + word_width * height * 2: raise ValueError("invalid TIM image length")
    raw = data[pos + 12 : pos + length]
    if bpp == 0:
        indices = bytes(nibble for byte in raw for nibble in (byte & 15, byte >> 4)); width = word_width * 4
        return EditableTim(bpp,width,height,indices,None,palette,clut_x,clut_y,image_x,image_y)
    if bpp == 1:
        return EditableTim(bpp,word_width*2,height,bytes(raw),None,palette,clut_x,clut_y,image_x,image_y)
    if bpp == 2:
        values = struct.unpack_from(f"<{word_width*height}H", raw)
        return EditableTim(bpp,word_width,height,None,values,palette,clut_x,clut_y,image_x,image_y)
    raise ValueError("TIM 24bpp is unsupported")


def encode_tim(tim: EditableTim) -> bytes:
    flags = tim.bpp | (8 if tim.palette else 0)
    output = bytearray(struct.pack("<II", 0x10, flags))
    if tim.palette:
        payload = struct.pack(f"<{len(tim.palette)}H", *tim.palette)
        output.extend(struct.pack("<IHHHH", 12+len(payload),tim.clut_x,tim.clut_y,len(tim.palette),1));output.extend(payload)
    if tim.bpp == 0:
        raw = bytes((tim.indices[i] | (tim.indices[i+1] << 4)) for i in range(0,len(tim.indices or b""),2)); word_width=tim.width//4
    elif tim.bpp == 1:
        raw=tim.indices or b"";word_width=tim.width//2
    else:
        raw=struct.pack(f"<{len(tim.direct_pixels or ())}H",*(tim.direct_pixels or ()));word_width=tim.width
    output.extend(struct.pack("<IHHHH",12+len(raw),tim.image_x,tim.image_y,word_width,tim.height));output.extend(raw)
    return bytes(output)
