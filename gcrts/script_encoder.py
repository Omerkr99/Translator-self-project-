"""Phase 4: re-encode an edited EditableScript (gcrts/editable_script.py)
back into the game's raw 16-bit script bytecode.

Core rule (per the pipeline's own constraints): control codes are NEVER
regenerated or reinterpreted -- every control-code word (and its inline
parameter, if any) is copied verbatim from the original decode. Only
CHARACTER-code words are replaced, driven by each segment's `translated`
text.

Ordering rule: a translator's `translated` text is free-form and will
usually have a different character count than the original (translation
changes word order and length). To still respect "never break control
flow" when a control code originally appeared *in the middle* of a
character run (not just before/after it), new characters are emitted
proportionally: by the time N% of the original character-code slots have
been passed, at least N% of the new characters have been emitted. This
exactly preserves prefix/suffix control-code placement (the common case
observed in live captures) and degrades gracefully to an approximate,
order-preserving placement for the rarer case of a control code
genuinely embedded mid-run. An untouched segment (`translated ==
original`) skips this entirely and is replayed byte-for-byte from its
original codes -- necessary because several characters have more than one
valid code (e.g. "よ" is both 0x26 and 0xa0), so text-driven
re-tokenization alone can't reconstruct the exact original bytes for
unedited text.

Unmapped/dynamic character codes that a translator leaves untouched are
shown as literal `<?0xNNNN>` tokens in `translated` (see
gcrts/editable_script.py) -- this module parses that exact token back
into its original raw code. A character with no entry in
gcrts.glyph_char_map.CHAR_TO_CODE (e.g. a new Latin/English letter not in
the base font) raises MissingGlyphError rather than silently guessing or
dropping it; adding new glyphs is Phase 6's job (font extension).
"""
from __future__ import annotations

import re
import struct

from gcrts.editable_script import EditableScript, ScriptSegment
from gcrts.glyph_char_map import code_for_char
from gcrts.script_decoder import CodeKind

_PLACEHOLDER_RE = re.compile(r"<\?0x([0-9a-fA-F]{1,4})>")


class MissingGlyphError(ValueError):
    def __init__(self, ch: str):
        super().__init__(f"no glyph code known for character {ch!r} (needs Phase 6 font extension)")
        self.char = ch


def tokenize_translated_text(text: str) -> list[int]:
    """Turn a segment's `translated` string into a list of raw 16-bit
    character codes, resolving `<?0xNNNN>` placeholders back to their
    literal code and every other character via CHAR_TO_CODE."""
    codes: list[int] = []
    i = 0
    n = len(text)
    while i < n:
        m = _PLACEHOLDER_RE.match(text, i)
        if m:
            codes.append(int(m.group(1), 16))
            i = m.end()
            continue
        ch = text[i]
        code = code_for_char(ch)
        if code is None:
            raise MissingGlyphError(ch)
        codes.append(code)
        i += 1
    return codes


def encode_segment(segment: ScriptSegment) -> list[int]:
    """Return the raw 16-bit word stream for one segment, with its
    character codes replaced by the (re-tokenized) `translated` text and
    every control/end code preserved exactly.

    If `translated` is untouched (still equal to `original`), the segment
    is replayed byte-for-byte from its original codes instead of being
    re-tokenized -- several characters (e.g. the base and second-pass
    hiragana both containing "よ") have more than one valid code, so
    text-driven re-tokenization alone can't guarantee picking the exact
    original code for an unedited character."""
    if segment.translated == segment.original:
        out: list[int] = []
        for code in segment.codes:
            out.append(code.raw)
            if code.param is not None:
                out.append(code.param)
        return out

    new_chars = tokenize_translated_text(segment.translated)
    total_original_chars = sum(1 for c in segment.codes if c.kind == CodeKind.CHARACTER)

    out: list[int] = []
    emitted = 0
    seen = 0

    def emit_up_to(target: int) -> None:
        nonlocal emitted
        while emitted < target and emitted < len(new_chars):
            out.append(new_chars[emitted])
            emitted += 1

    for code in segment.codes:
        if code.kind == CodeKind.CHARACTER:
            seen += 1
            target = round(seen / total_original_chars * len(new_chars)) if total_original_chars else 0
            emit_up_to(target)
        else:
            out.append(code.raw)
            if code.param is not None:
                out.append(code.param)

    emit_up_to(len(new_chars))  # flush any remainder (translated longer than original, or no chars at all)
    return out


def encode_script(script: EditableScript) -> bytes:
    """Re-encode a full EditableScript into a raw script buffer (bytes),
    ready to be written back over the original buffer in RAM/on disc."""
    words: list[int] = []
    for segment in script.segments:
        words.extend(encode_segment(segment))
    return struct.pack(f"<{len(words)}H", *words)
