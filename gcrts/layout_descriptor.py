"""Alternative Text Engine, Phase 2: the custom layout descriptor binary format.

Pure Python serializer/parser. No MIPS code, no code-cave search, no
emulator interaction -- this module produces and consumes bytes only, and
every function in it is a pure function of its input. Per the master
prompt's section 12: "Produce a formal binary specification before
implementing MIPS code" -- see CUSTOM_LAYOUT_DESCRIPTOR.md for the formal
spec this module implements; keep the two in sync if either changes.

Design choices and why:

- All multi-byte fields are little-endian (`<` in every struct format
  string) -- the PS1's MIPS R3000 is little-endian, so the eventual MIPS
  parser can load a field with a single `lw`/`lh` instruction and never
  needs a byte-swap.
- Every multi-byte field sits at an even byte offset in both the header
  and each line record (verified by test_layout_descriptor.py) -- an
  unaligned MIPS load either faults or requires extra instructions to
  work around, so this is a real hardware constraint, not just tidiness.
- Line records reference a character-code stream by (start_char_index,
  char_count) rather than embedding each line's text inline -- this keeps
  every record a fixed 10 bytes (indexable in O(1) by a future MIPS
  parser without walking variable-length data), and the character codes
  in that stream are the EXACT SAME 16-bit glyph codes
  gcrts.script_encoder.tokenize_translated_text already produces, so a
  future MIPS-side renderer can hand a line's slice straight to the
  game's existing, already-proven glyph lookup/blit routine (see the
  master prompt's section 11: "Reuse the already proven game functions
  ... Avoid duplicating already-understood rendering code") instead of
  needing its own text representation.
- Every bound (MAX_LINES, MAX_LINE_CHARS, MAX_TOTAL_CHARS) is enforced
  by the ENCODER (raises DescriptorValidationError rather than silently
  truncating -- see the master prompt's section 27: "Descriptor too
  large -- Do not truncate silently") and re-checked independently by the
  DECODER against the bytes actually present, so a corrupt or foreign
  buffer can never cause an out-of-bounds read no matter how it was
  produced.
- Each line's stored `x` is its FINAL, alignment-ALREADY-RESOLVED screen
  position, computed once at encode time (gcrts.layout_validation's real
  per-character width measurement, same fallback convention as every
  other function in this project: `atlas` is optional, falling back to a
  character-count heuristic when not given) -- not a raw editor-chosen
  position plus an alignment code the consumer has to resolve itself.
  This was a real design gap caught during Alternative Text Engine Phase
  6's design review (see MIPS_PATCH_PLAN.md): the binary format has no
  per-line width-BUDGET field, so a MIPS-side consumer reading only these
  bytes would have nothing to center or right-align WITHIN even if it
  wanted to resolve alignment itself. Resolving once here, in Python,
  where the same width table is already being read for tokenization
  anyway, means the MIPS parser never needs alignment math at all -- it
  places each line's glyphs starting at its stored `x`, verbatim. The
  `alignment` field is kept in the format regardless, informational for
  a human/editor reading the bytes back, not required for correct
  rendering.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from gcrts.editor_layout_plan import EditorLayoutPlan, LayoutAlignment, PageTransition
from gcrts.glyph_atlas import GlyphAtlas
from gcrts.glyph_char_map import char_for_code
from gcrts.layout_validation import measure_pixel_width
from gcrts.script_encoder import MissingGlyphError, tokenize_translated_text

MAGIC = b"CLD1"
FORMAT_VERSION = 1

# Hard caps enforced by both encode (reject before producing bytes) and
# decode (reject before trusting a header's claimed counts) -- see module
# docstring. Not a claim about the VISIBLE line count (that's the
# confirmed, separate MAX_VISIBLE_LINES=4 in gcrts.layout_validation);
# this is a defensive upper bound for a single descriptor buffer, sized
# generously above any real dialogue line seen in this project so far.
MAX_LINES = 64
MAX_LINE_CHARS = 256
MAX_TOTAL_CHARS = 4096

_HEADER_FORMAT = "<4sHHHhhHBB"
HEADER_SIZE = struct.calcsize(_HEADER_FORMAT)  # 18 bytes

_LINE_RECORD_FORMAT = "<HHhhBB"
LINE_RECORD_SIZE = struct.calcsize(_LINE_RECORD_FORMAT)  # 10 bytes

_ALIGNMENT_TO_CODE = {
    LayoutAlignment.LEFT: 0,
    LayoutAlignment.CENTER: 1,
    LayoutAlignment.RIGHT: 2,
}
_CODE_TO_ALIGNMENT = {v: k for k, v in _ALIGNMENT_TO_CODE.items()}

_PAGE_TRANSITION_TO_CODE = {
    PageTransition.WAIT_FOR_INPUT: 0,
    PageTransition.AUTO_CONTINUE: 1,
    PageTransition.NONE: 2,
}
_CODE_TO_PAGE_TRANSITION = {v: k for k, v in _PAGE_TRANSITION_TO_CODE.items()}

_FLAG_PARAGRAPH_END = 0x0001


class DescriptorValidationError(ValueError):
    """Raised by both encode (a plan violates a bound or references an
    unmapped character) and decode (the bytes are corrupt, truncated, or
    claim counts that don't fit the buffer actually given). Never
    silently truncates or guesses -- see module docstring."""


@dataclass
class DecodedLine:
    start_char_index: int
    char_count: int
    x: int
    y: int
    alignment: LayoutAlignment
    char_codes: list[int] = field(default_factory=list)

    def decoded_text(self) -> str:
        """Best-effort round-trip back to a Python string, for tests and
        human inspection only -- the real MIPS-side consumer would use
        char_codes directly against the glyph table, never this."""
        chars = []
        for code in self.char_codes:
            ch = char_for_code(code)
            chars.append(ch if ch is not None else f"<?0x{code:04x}>")
        return "".join(chars)


@dataclass
class DecodedLayoutDescriptor:
    version: int
    paragraph_end: bool
    base_x: int
    base_y: int
    line_height: int
    page_transition: PageTransition
    lines: list[DecodedLine]


def _char_codes_for_line(text: str) -> list[int]:
    try:
        return tokenize_translated_text(text)
    except MissingGlyphError as e:
        raise DescriptorValidationError(f"line text uses an unmapped character: {e.char!r}") from e


def _resolve_line_x(line, measured_width_px: int) -> int:
    """The FINAL, alignment-resolved starting X for `line` -- same math as
    gcrts.layout_software_preview._line_start_x, duplicated here (not
    imported) so this module doesn't pull in Pillow as a transitive
    dependency for an unrelated, non-rendering concern. See module
    docstring for why this is resolved once here rather than left for a
    future MIPS consumer to compute."""
    budget = line.max_width_px if line.max_width_px is not None else measured_width_px
    if line.alignment == LayoutAlignment.CENTER:
        return line.x + max(0, (budget - measured_width_px) // 2)
    if line.alignment == LayoutAlignment.RIGHT:
        return line.x + max(0, budget - measured_width_px)
    return line.x


def encode_layout_descriptor(plan: EditorLayoutPlan, atlas: GlyphAtlas | None = None) -> bytes:
    """Serialize an EditorLayoutPlan's lines into the binary descriptor
    format. Raises DescriptorValidationError (never truncates) if the plan
    exceeds MAX_LINES/MAX_LINE_CHARS/MAX_TOTAL_CHARS, or if any line's text
    contains a character with no known glyph code.

    `atlas` is optional, matching this project's established convention
    (gcrts.layout_validation.measure_pixel_width and everything built on
    it): when given, alignment is resolved using real glyph advance
    widths; when omitted, the same character-count fallback heuristic
    applies. Either way, the ENCODED `x` is always the final, resolved
    position -- see module docstring."""
    if len(plan.lines) > MAX_LINES:
        raise DescriptorValidationError(f"plan has {len(plan.lines)} lines, exceeds MAX_LINES={MAX_LINES}")

    per_line_codes: list[list[int]] = []
    for line in plan.lines:
        codes = _char_codes_for_line(line.text)
        if len(codes) > MAX_LINE_CHARS:
            raise DescriptorValidationError(
                f"line {line.text!r} has {len(codes)} characters, exceeds MAX_LINE_CHARS={MAX_LINE_CHARS}"
            )
        per_line_codes.append(codes)

    total_chars = sum(len(codes) for codes in per_line_codes)
    if total_chars > MAX_TOTAL_CHARS:
        raise DescriptorValidationError(f"plan has {total_chars} total characters, exceeds MAX_TOTAL_CHARS={MAX_TOTAL_CHARS}")

    flags = _FLAG_PARAGRAPH_END if plan.paragraph_end else 0
    page_transition_code = _PAGE_TRANSITION_TO_CODE[plan.page_transition]

    # base_x/base_y/line_height describe the FIRST line's origin and a
    # nominal line spacing -- useful summary fields for a MIPS-side
    # dispatcher deciding where a fresh textbox starts, even though every
    # line's own x/y is already explicit and authoritative.
    base_x = plan.lines[0].x if plan.lines else 0
    base_y = plan.lines[0].y if plan.lines else 0
    line_height = (plan.lines[1].y - plan.lines[0].y) if len(plan.lines) > 1 else 0

    header = struct.pack(
        _HEADER_FORMAT,
        MAGIC,
        FORMAT_VERSION,
        flags,
        len(plan.lines),
        base_x,
        base_y,
        line_height,
        page_transition_code,
        0,  # reserved
    )

    line_records = bytearray()
    char_stream: list[int] = []
    cursor = 0
    for line, codes in zip(plan.lines, per_line_codes):
        measured_width_px = measure_pixel_width(line.text, atlas)
        resolved_x = _resolve_line_x(line, measured_width_px)
        line_records += struct.pack(
            _LINE_RECORD_FORMAT,
            cursor,
            len(codes),
            resolved_x,
            line.y,
            _ALIGNMENT_TO_CODE[line.alignment],
            0,  # reserved
        )
        char_stream.extend(codes)
        cursor += len(codes)

    char_stream_bytes = struct.pack(f"<{len(char_stream)}H", *char_stream)
    return header + bytes(line_records) + char_stream_bytes


def decode_layout_descriptor(data: bytes) -> DecodedLayoutDescriptor:
    """Parse a descriptor produced by encode_layout_descriptor(). Every
    bound is re-checked against the ACTUAL bytes given -- never trusts a
    header field further than the buffer's real length allows, so a
    corrupt or truncated buffer raises DescriptorValidationError instead
    of reading out of bounds or returning wrong data silently."""
    if len(data) < HEADER_SIZE:
        raise DescriptorValidationError(f"buffer too short for header: {len(data)} bytes, need at least {HEADER_SIZE}")

    magic, version, flags, line_count, base_x, base_y, line_height, page_transition_code, reserved = struct.unpack(
        _HEADER_FORMAT, data[:HEADER_SIZE]
    )

    if magic != MAGIC:
        raise DescriptorValidationError(f"bad magic: {magic!r}, expected {MAGIC!r}")
    if version != FORMAT_VERSION:
        raise DescriptorValidationError(f"unsupported version: {version}, this module only reads {FORMAT_VERSION}")
    if reserved != 0:
        raise DescriptorValidationError(f"header reserved byte is {reserved}, expected 0 -- buffer may not be a real descriptor")
    if line_count > MAX_LINES:
        raise DescriptorValidationError(f"header claims {line_count} lines, exceeds MAX_LINES={MAX_LINES}")
    if page_transition_code not in _CODE_TO_PAGE_TRANSITION:
        raise DescriptorValidationError(f"unknown page_transition code: {page_transition_code}")

    lines_end = HEADER_SIZE + line_count * LINE_RECORD_SIZE
    if len(data) < lines_end:
        raise DescriptorValidationError(
            f"buffer too short for {line_count} line records: have {len(data)} bytes, need {lines_end}"
        )

    raw_lines = []
    max_char_index = 0
    for i in range(line_count):
        offset = HEADER_SIZE + i * LINE_RECORD_SIZE
        start_char_index, char_count, x, y, alignment_code, line_reserved = struct.unpack(
            _LINE_RECORD_FORMAT, data[offset : offset + LINE_RECORD_SIZE]
        )
        if line_reserved != 0:
            raise DescriptorValidationError(f"line {i} reserved byte is {line_reserved}, expected 0")
        if char_count > MAX_LINE_CHARS:
            raise DescriptorValidationError(f"line {i} claims {char_count} characters, exceeds MAX_LINE_CHARS={MAX_LINE_CHARS}")
        if alignment_code not in _CODE_TO_ALIGNMENT:
            raise DescriptorValidationError(f"line {i} has unknown alignment code: {alignment_code}")
        raw_lines.append((start_char_index, char_count, x, y, alignment_code))
        max_char_index = max(max_char_index, start_char_index + char_count)

    if max_char_index > MAX_TOTAL_CHARS:
        raise DescriptorValidationError(f"descriptor references {max_char_index} total characters, exceeds MAX_TOTAL_CHARS={MAX_TOTAL_CHARS}")

    char_stream_bytes_needed = max_char_index * 2
    char_stream_end = lines_end + char_stream_bytes_needed
    if len(data) < char_stream_end:
        raise DescriptorValidationError(
            f"buffer too short for character stream: have {len(data) - lines_end} bytes after line records, "
            f"need {char_stream_bytes_needed}"
        )

    full_char_stream = list(struct.unpack(f"<{max_char_index}H", data[lines_end:char_stream_end])) if max_char_index else []

    decoded_lines = [
        DecodedLine(
            start_char_index=start,
            char_count=count,
            x=x,
            y=y,
            alignment=_CODE_TO_ALIGNMENT[alignment_code],
            char_codes=full_char_stream[start : start + count],
        )
        for start, count, x, y, alignment_code in raw_lines
    ]

    return DecodedLayoutDescriptor(
        version=version,
        paragraph_end=bool(flags & _FLAG_PARAGRAPH_END),
        base_x=base_x,
        base_y=base_y,
        line_height=line_height,
        page_transition=_CODE_TO_PAGE_TRANSITION[page_transition_code],
        lines=decoded_lines,
    )
