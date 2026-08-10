"""Content Detection Engine (Phase 2 subset): per-position encoding detectors.

Each detector answers one question: "starting at this byte offset, is there
a valid run of this encoding, and how far does it extend?" The extractor
tries every detector at each offset and keeps whichever produces the longest
match, so (for example) a UTF-16LE-encoded string isn't mis-split into a run
of single unrelated ASCII bytes.

Font glyph-table detection and UI border/box detection are separate Phase 2
line items in the spec but are not implemented here yet -- this module only
covers the "Detect TEXT" heuristics (ASCII / Shift-JIS / UTF-16LE).
"""

from __future__ import annotations

from dataclasses import dataclass

_ASCII_PRINTABLE_MIN = 0x20
_ASCII_PRINTABLE_MAX = 0x7E


@dataclass
class RunMatch:
    encoding: str
    text: str
    end: int  # exclusive byte offset where the run stops


def _is_ascii_printable(byte: int) -> bool:
    return _ASCII_PRINTABLE_MIN <= byte <= _ASCII_PRINTABLE_MAX


def _is_sjis_lead_byte(byte: int) -> bool:
    return (0x81 <= byte <= 0x9F) or (0xE0 <= byte <= 0xFC)


def _is_sjis_trail_byte(byte: int) -> bool:
    return (0x40 <= byte <= 0x7E) or (0x80 <= byte <= 0xFC)


def _is_sjis_halfwidth_katakana(byte: int) -> bool:
    return 0xA1 <= byte <= 0xDF


# Real Japanese sentences are overwhelmingly mixed kana+kanji (particles, verb
# endings, loanwords) -- a run with zero kana is far more likely to be a
# coincidental valid lead/trail byte-pair sequence in unrelated binary data
# than real text. Confirmed against a real PS1 disc image: without this
# check, ~70% of matches were minimum-length runs decoding to nonsense.
# Longer runs are exempted since the odds of a long run being coincidental
# drop sharply, and it allows genuine kanji-only proper nouns through.
#
# Deliberately excludes half-width katakana (0xA1-0xDF, decoded to
# U+FF61-U+FF9F): unlike a double-byte pair, a single half-width-katakana
# byte has no structural pairing constraint, so ~1/4 of all random bytes
# decode to "a kana character" and satisfying this check on that basis
# alone is nearly meaningless (confirmed empirically: doing so raised, not
# lowered, the false-positive count on the real disc image).
_KANA_REQUIRED_BELOW_LENGTH = 12


def _has_kana(text: str) -> bool:
    for ch in text:
        code_point = ord(ch)
        if 0x3040 <= code_point <= 0x309F:  # hiragana
            return True
        if 0x30A0 <= code_point <= 0x30FF:  # full-width katakana
            return True
    return False


def match_ascii_run(data: bytes, start: int) -> RunMatch | None:
    """Contiguous printable ASCII bytes (the Phase 1 detector)."""
    i = start
    n = len(data)
    while i < n and _is_ascii_printable(data[i]):
        i += 1
    if i == start:
        return None
    return RunMatch(encoding="ascii", text=data[start:i].decode("ascii"), end=i)


def match_utf16le_run(data: bytes, start: int) -> RunMatch | None:
    """`<ascii-printable-byte><0x00>` pairs -- how plain-ASCII text looks under UTF-16LE."""
    i = start
    n = len(data)
    chars: list[str] = []
    while i + 1 < n and _is_ascii_printable(data[i]) and data[i + 1] == 0x00:
        chars.append(chr(data[i]))
        i += 2
    if not chars:
        return None
    return RunMatch(encoding="utf-16le", text="".join(chars), end=i)


def match_shift_jis_run(data: bytes, start: int) -> RunMatch | None:
    """A run mixing ASCII-compatible bytes, half-width katakana, and valid
    Shift-JIS double-byte pairs.

    Only reported as shift_jis if at least one non-ASCII byte actually
    occurs -- a run with none is indistinguishable from plain ASCII, which
    the ascii detector already covers. Short runs are further required to
    contain kana (see _has_kana) to reject coincidental byte-pair matches in
    unrelated binary data.
    """
    i = start
    n = len(data)
    had_non_ascii = False
    while i < n:
        byte = data[i]
        if _is_ascii_printable(byte):
            i += 1
            continue
        if _is_sjis_halfwidth_katakana(byte):
            i += 1
            had_non_ascii = True
            continue
        if _is_sjis_lead_byte(byte) and i + 1 < n and _is_sjis_trail_byte(data[i + 1]):
            i += 2
            had_non_ascii = True
            continue
        break

    if not had_non_ascii or i == start:
        return None

    try:
        text = data[start:i].decode("shift_jis")
    except UnicodeDecodeError:
        return None

    length = i - start
    if length < _KANA_REQUIRED_BELOW_LENGTH and not _has_kana(text):
        return None

    return RunMatch(encoding="shift_jis", text=text, end=i)


# Tried at every offset; the extractor keeps whichever returns the longest match.
DETECTORS = (match_utf16le_run, match_shift_jis_run, match_ascii_run)
