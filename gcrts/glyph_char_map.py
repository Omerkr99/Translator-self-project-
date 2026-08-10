"""Character-code -> Unicode character mapping for this game's custom font,
transcribed by visually reading the decoded glyph atlas (see
`gcrts/glyph_atlas.py` and `NOTES.md`'s "PHASE 2 BREAKTHROUGH" section).

This covers the FIXED base range (codes 0x000-0x10c) that decoded cleanly
to a full 16x16 4bpp glyph in a live capture: blank/space, full hiragana,
full katakana, small/extended kana, dakuten/handakuten variants, digits,
kanji numerals, punctuation, and Latin upper/lowercase.

Codes above 0x10c are NOT fixed -- that region is a per-scene dynamic
kanji cache (empirically: 55 codes right after 0x10c returned no glyph at
all in this capture, then a handful of real kanji appeared scattered much
higher, e.g. 0x144/0x19d/0x217). Whatever specific kanji occupy that space
depends on which chapter/scene is currently loaded, so there is no single
fixed mapping for it -- each extraction run must resolve those codes
against a fresh live glyph-blob capture from that same session.

CONFIDENCE_LOW marks entries transcribed from a low-resolution render
where visually similar glyphs are genuinely hard to tell apart (mainly:
dakuten "゛" vs handakuten "゜" marks, small vs full kana, and a couple of
rare/archaic kana and punctuation/icon glyphs). Verify these against the
actual running game before trusting them in translated output -- this is
exactly the kind of case the editor layer's manual-override capability
exists for.
"""
from __future__ import annotations

# code -> (character, is_low_confidence)
_RAW: dict[int, tuple[str, bool]] = {
    0x00: (" ", False),
    # hiragana
    0x01: ("あ", False), 0x02: ("い", False), 0x03: ("う", False), 0x04: ("え", False), 0x05: ("お", False),
    0x06: ("か", False), 0x07: ("き", False), 0x08: ("く", False), 0x09: ("け", False), 0x0a: ("こ", False),
    0x0b: ("さ", False), 0x0c: ("し", False), 0x0d: ("す", False), 0x0e: ("せ", False), 0x0f: ("そ", False),
    0x10: ("た", False), 0x11: ("ち", False), 0x12: ("つ", False), 0x13: ("て", False), 0x14: ("と", False),
    0x15: ("な", False), 0x16: ("に", False), 0x17: ("ぬ", False), 0x18: ("ね", False), 0x19: ("の", False),
    0x1a: ("は", False), 0x1b: ("ひ", False), 0x1c: ("ふ", False), 0x1d: ("へ", False), 0x1e: ("ほ", False),
    0x1f: ("ま", False), 0x20: ("み", False), 0x21: ("む", False), 0x22: ("め", False), 0x23: ("も", False),
    0x24: ("や", False), 0x25: ("ゆ", False), 0x26: ("よ", False),
    0x27: ("ら", False), 0x28: ("り", False), 0x29: ("る", False), 0x2a: ("れ", False), 0x2b: ("ろ", False),
    0x2c: ("わ", False), 0x2d: ("を", False), 0x2e: ("ん", False),
    # katakana
    0x2f: ("ア", False), 0x30: ("イ", False), 0x31: ("ウ", False), 0x32: ("エ", False), 0x33: ("オ", False),
    0x34: ("カ", False), 0x35: ("キ", False), 0x36: ("ク", False), 0x37: ("ケ", False), 0x38: ("コ", False),
    0x39: ("サ", False), 0x3a: ("シ", False), 0x3b: ("ス", False), 0x3c: ("セ", False), 0x3d: ("ソ", False),
    0x3e: ("タ", False), 0x3f: ("チ", False),
    0x40: ("ツ", False), 0x41: ("テ", False), 0x42: ("ト", False), 0x43: ("ナ", False), 0x44: ("ニ", False),
    0x45: ("ヌ", False), 0x46: ("ネ", False), 0x47: ("ノ", False),
    0x48: ("ハ", False), 0x49: ("ヒ", False), 0x4a: ("フ", False), 0x4b: ("ヘ", False), 0x4c: ("ホ", False),
    0x4d: ("マ", False), 0x4e: ("ミ", False), 0x4f: ("ム", False),
    0x50: ("メ", False), 0x51: ("モ", False), 0x52: ("ヤ", False), 0x53: ("ユ", False), 0x54: ("ヨ", False),
    0x55: ("ラ", False), 0x56: ("リ", False), 0x57: ("ル", False),
    0x58: ("レ", False), 0x59: ("ロ", False), 0x5a: ("ワ", False), 0x5b: ("ヲ", False), 0x5c: ("ン", False),
    # archaic/rare kana -- visually ambiguous at this resolution
    0x5d: ("ヰ", True), 0x5e: ("ヱ", True), 0x5f: ("ァ", True),
    # small katakana
    0x60: ("ィ", False), 0x61: ("ゥ", False), 0x62: ("ェ", False), 0x63: ("ォ", False),
    0x64: ("ャ", False), 0x65: ("ュ", False), 0x66: ("ョ", False), 0x67: ("ッ", False),
    0x68: ("ヮ", True),
    # katakana dakuten
    0x69: ("ガ", False), 0x6a: ("ギ", False), 0x6b: ("グ", False), 0x6c: ("ゲ", False), 0x6d: ("ゴ", False),
    0x6e: ("ザ", False), 0x6f: ("ジ", False),
    0x70: ("ズ", False), 0x71: ("ゼ", False), 0x72: ("ゾ", False), 0x73: ("ダ", False), 0x74: ("ヂ", False),
    0x75: ("ヅ", True), 0x76: ("デ", False), 0x77: ("ド", False),
    0x78: ("バ", True), 0x79: ("ビ", True), 0x7a: ("ブ", True), 0x7b: ("ベ", True), 0x7c: ("ボ", True),
    0x7d: ("パ", True), 0x7e: ("ピ", True), 0x7f: ("プ", True),
    0x80: ("ペ", True), 0x81: ("ポ", True), 0x82: ("ヴ", True), 0x83: ("ヵ", True),
    # digits
    0x84: ("0", False), 0x85: ("1", False), 0x86: ("2", False), 0x87: ("3", False),
    0x88: ("4", False), 0x89: ("5", False), 0x8a: ("6", False), 0x8b: ("7", False),
    0x8c: ("8", False), 0x8d: ("9", False),
    # kanji numerals
    0x8e: ("零", False), 0x8f: ("一", False),
    0x90: ("二", False), 0x91: ("三", False), 0x92: ("四", False), 0x93: ("五", False),
    0x94: ("六", False), 0x95: ("七", False), 0x96: ("八", False), 0x97: ("九", False),
    # second, partial hiragana pass
    0x98: ("あ", False), 0x99: ("い", False), 0x9a: ("う", False), 0x9b: ("え", False), 0x9c: ("お", False),
    0x9d: ("っ", False), 0x9e: ("や", False), 0x9f: ("ゆ", False),
    0xa0: ("よ", False), 0xa1: ("わ", False),
    # hiragana dakuten
    0xa2: ("が", False), 0xa3: ("ぎ", False), 0xa4: ("ぐ", False), 0xa5: ("げ", False), 0xa6: ("ご", False),
    0xa7: ("ざ", False),
    0xa8: ("じ", False), 0xa9: ("ず", False), 0xaa: ("ぜ", False), 0xab: ("ぞ", False), 0xac: ("だ", False),
    0xad: ("ぢ", False), 0xae: ("づ", False), 0xaf: ("で", False),
    0xb0: ("ど", False), 0xb1: ("ば", True), 0xb2: ("び", True), 0xb3: ("ぶ", True), 0xb4: ("べ", True),
    0xb5: ("ぼ", True),
    0xb6: ("ぱ", True), 0xb7: ("ぴ", True), 0xb8: ("ぷ", True), 0xb9: ("ぺ", True), 0xba: ("ぽ", True),
    0xbb: ("ー", False),
    # Latin uppercase
    0xbc: ("A", False), 0xbd: ("B", False), 0xbe: ("C", False), 0xbf: ("D", False),
    0xc0: ("E", False), 0xc1: ("F", False), 0xc2: ("G", False), 0xc3: ("H", False),
    0xc4: ("I", False), 0xc5: ("J", False), 0xc6: ("K", False), 0xc7: ("L", False),
    0xc8: ("M", False), 0xc9: ("N", False), 0xca: ("O", False), 0xcb: ("P", False),
    0xcc: ("Q", False), 0xcd: ("R", False), 0xce: ("S", False), 0xcf: ("T", False),
    0xd0: ("U", False), 0xd1: ("V", False), 0xd2: ("W", False), 0xd3: ("X", False),
    0xd4: ("Y", False), 0xd5: ("Z", False),
    # Latin lowercase
    0xd6: ("a", False), 0xd7: ("b", False), 0xd8: ("c", False), 0xd9: ("d", False),
    0xda: ("e", False), 0xdb: ("f", False), 0xdc: ("g", False), 0xdd: ("h", False),
    0xde: ("i", False), 0xdf: ("j", False), 0xe0: ("k", False), 0xe1: ("l", False),
    0xe2: ("m", False), 0xe3: ("n", False), 0xe4: ("o", False), 0xe5: ("p", False),
    0xe6: ("q", False), 0xe7: ("r", False), 0xe8: ("s", False), 0xe9: ("t", False),
    0xea: ("u", False), 0xeb: ("v", False), 0xec: ("w", False), 0xed: ("x", False),
    0xee: ("y", False), 0xef: ("z", False),
    # punctuation
    0xf0: ("。", False), 0xf1: ("、", False), 0xf2: ("!", False), 0xf3: ("?", False),
    0xf4: ("”", True),  # closing double quote "
    0xf5: ("$", False), 0xf6: ("%", False), 0xf7: ("&", False),
    0xf8: ("’", True),  # closing single quote ' -- uncertain variant
    0xf9: ("", True),  # unidentified UI/button icon glyph (placeholder codepoint)
    0xfa: ("=", False), 0xfb: (":", False), 0xfc: ("…", False),  # ellipsis
    0xfd: ("・", False),  # ・ middle dot
    0xfe: (".", True), 0xff: ("‘", True),  # opening single quote -- uncertain variant
    # more punctuation / brackets
    0x100: ("(", False), 0x101: (")", False), 0x102: ("―", False),  # horizontal bar
    0x103: ("「", False), 0x104: ("」", False),  # 「 」
    0x105: ("『", False), 0x106: ("』", False),  # 『 』
    0x107: ("〜", False),  # 〜 wave dash
    0x108: ("‥", False),  # ‥ two-dot leader
    0x109: ("▼", False),  # ▼
    0x10a: ("", True),  # unidentified page/document icon
    0x10b: ("▶", False),  # ▶
    # dynamic per-scene kanji cache -- only meaningful for the specific
    # live session `kfont_live_big.bin` was captured from; DO NOT treat
    # these as fixed/universal
    0x10c: ("昨", False),
    0x144: ("簡", False),
    0x19d: ("怪", False),
    0x217: ("包", False),
}

CODE_TO_CHAR: dict[int, str] = {code: ch for code, (ch, _) in _RAW.items()}
LOW_CONFIDENCE_CODES: frozenset[int] = frozenset(code for code, (_, low) in _RAW.items() if low)

# Reverse mapping for re-encoding (gcrts/script_encoder.py). Several codes
# render the same character (e.g. both 0x01 and 0x98 are "あ" -- the second,
# partial hiragana pass at 0x098-0x0a1); iterating _RAW in ascending code
# order and keeping the first hit means the earlier/lower code wins, which
# is an arbitrary but deterministic and stable choice.
CHAR_TO_CODE: dict[str, int] = {}
for _code in sorted(_RAW):
    _ch, _ = _RAW[_code]
    if _ch and _ch not in CHAR_TO_CODE:
        CHAR_TO_CODE[_ch] = _code
del _code, _ch


def code_for_char(ch: str) -> int | None:
    return CHAR_TO_CODE.get(ch)

# codes >= this are the per-scene dynamic kanji cache: not part of the
# fixed base table, must be re-resolved per capture session
DYNAMIC_RANGE_START = 0x10d


def char_for_code(code: int) -> str | None:
    return CODE_TO_CHAR.get(code)


def is_dynamic_code(code: int) -> bool:
    return code >= DYNAMIC_RANGE_START
