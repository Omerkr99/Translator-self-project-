"""Custom RLE/LZ77/delta decompression codec used by this game's *.CDB resource
files (confirmed: DAT/FONT/KFONT.CDB, DAT/CAP0/K0LINK.CDB, and presumably every
sibling K#LINK.CDB / HAN.CDB file, since they share the same directory-table
convention in gcrts/iso9660.py-discovered files).

Not reverse-engineered from data alone -- this is a faithful port of
FUN_8007681c, the actual decompression function found in CAP0.EXE via Ghidra's
decompiler (see the main investigation's README section and
GhidraTools/ghidra_project/NOTES.md for the call chain that reaches it:
0x8006e2d8 -> resource_load (0x8005342c) -> ... -> 0x80076aa0 -> this function).

Control byte at each step (byte values, not ranges of the decompressed size):
  c == 0xFF        : end of stream
  c <  0x80        : literal run of (c+1) bytes, copied verbatim from input
  0x80 <= c < 0xC0 : run-length fill of (c-0x7D) bytes, all equal to the next
                     input byte (including the c==0 fill-byte case -- the
                     decompiled code special-cases a zero fill byte but it's
                     behaviorally identical to filling with 0)
  0xC0 <= c < 0xE0 : LZ77-style back-reference copy of (c-0xBC) bytes from
                     (current_output_position - offset), where offset is a
                     16-bit value built from the next two input bytes as
                     (input[0] << 8) | input[1] -- copied byte-by-byte since
                     the source range can overlap the bytes being written
                     (this is what makes short back-references work as
                     "repeat the last N bytes" runs)
  0xE0 <= c < 0xF0 : arithmetic/delta fill of (c-0xDC) bytes: successive
                     values start, start+delta, start+2*delta, ... (mod 256),
                     where delta and start are the next two input bytes
  0xF0 <= c < 0xFF : not exercised by any real data seen so far; the
                     decompiled control flow does not define a behavior for
                     this range, so decoding stops rather than guessing
"""

from __future__ import annotations


def decompress(src: bytes, max_output_size: int = 1 << 20) -> bytes:
    """Decompress one CDB-codec stream. Stops at the 0xFF end marker, running
    out of input, or max_output_size (a safety cap, not part of the format)."""
    out = bytearray()
    i = 0
    n = len(src)

    while i < n:
        control = src[i]
        i += 1

        if control == 0xFF:
            break

        if control < 0x80:
            count = control + 1
            out += src[i : i + count]
            i += count

        elif control < 0xC0:
            count = control - 0x7D
            fill_byte = src[i]
            i += 1
            out += bytes([fill_byte]) * count

        elif control < 0xE0:
            count = control - 0xBC
            offset = (src[i] << 8) | src[i + 1]
            i += 2
            start = len(out) - offset
            for k in range(count):
                out.append(out[start + k])

        elif control < 0xF0:
            count = control - 0xDC
            delta = src[i]
            value = src[i + 1]
            i += 2
            for k in range(count):
                out.append((value + k * delta) & 0xFF)

        else:
            break

        if len(out) > max_output_size:
            break

    return bytes(out)
