"""Decoder for this game's custom dialogue script bytecode.

Reverse-engineered from FUN_80049168 in CAP0.EXE (see
C:\\GhidraTools\\ghidra_project\\NOTES.md's "BREAKTHROUGH" section and
scratchpad/full_script_reader.c for the full decompiled source this is
derived from). The live script buffer lives at 0x801fe800 in RAM; this
module only handles the *format*, independent of where the bytes came
from (live RAM dump or, once identified, the on-disc .CDB source).

Stream format: 16-bit little-endian words, one "unit" read per position
(`DAT_800a4cea`, the cursor) advancing by 1 word for most units, or by 2
for a specific set of control codes that read an inline parameter word
(one subtype's extra word is only consumed conditionally, based on that
code's own low byte -- see CONTROL_B_TWO_WORD_CONDITIONAL below).

  0xFFFF                     -> end of string
  (word & 0xC000) == 0x0000  -> character code: the value IS the index
                                into the glyph pointer table (see
                                FUN_8004aa08 / PTR_DAT_80093b34 in NOTES.md)
  (word & 0xC000) == 0x8000  -> control code, "family A". Subtype is
                                (word & 0x3F00). No family-A subtype
                                consumes an extra word.
  otherwise (0x4000/0xC000)  -> control code, "family B" (both top-bit
                                patterns are handled by the same code path
                                in the decompile -- there is no evidence
                                they differ). Subtype is (word & 0x3F00).
                                Some subtypes consume one extra inline
                                word; see CONTROL_B_TWO_WORD_ALWAYS and
                                CONTROL_B_TWO_WORD_CONDITIONAL below.

Only a subset of control-code subtypes have a confirmed *meaning* (which
game function they call) from the decompile; the rest are recorded with
meaning=None rather than guessed, per the project's "never assume" rule.
Getting the word-count/cursor math exactly right (so a whole script
decodes without desyncing) was the priority for this module; simulating
each control code's actual gameplay effect was not attempted.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import Enum


class CodeKind(Enum):
    CHARACTER = "character"
    CONTROL = "control"
    END = "end"


class ControlFamily(Enum):
    A = "A"  # (word & 0xC000) == 0x8000
    B = "B"  # (word & 0xC000) in (0x4000, 0xC000)


# Family A (tag == 0x8000): confirmed from the decompile, none of these
# consume an extra word.
CONTROL_A_MEANINGS: dict[int, str] = {
    0x0100: "set_flag_d10",              # DAT_800a4d10 = 1
    0x0200: "call_FUN_80048c44",
    0x0300: "low_byte_passthrough",
    0x0400: "set_mode_ce4",              # DAT_800a4ce4 = word & 0xff
    0x0500: "pause_flag_a",
    0x0600: "pause_flag_b",              # also sets DAT_800a4ce4 = 0xfffe
    0x0900: "speaker_name_start",        # DAT_800a4cd5 = 1
    0x0a00: "speaker_name_end",          # DAT_800a4cd5 = -1
    0x0b00: "set_counter_cf6",           # FUN_8004abd8 then DAT_800a4cf6 = word & 0xff
    0x0c00: "call_FUN_8004a230",
    0x0d00: "line_center_calc",          # reads ahead (not via the shared cursor) for
                                          # kerning-width summation via DAT_80093b38
    0x0e00: "alias_of_0x400",            # goes to the 0x400 handler via goto
    0x0f00: "alias_of_0x400_b",          # ditto
    0x1700: "portrait_or_anim_a",        # FUN_8004ac18 + FUN_8004acdc/FUN_8004ada0
    0x1800: "centered_text_setup",       # FUN_8004a21c, FUN_80048c44(1), ...
    0x2700: "alias_of_0x1700",
    0x2800: "alias_of_0x1800",
}

# Family B (tag == 0x4000 or 0xC000): subtypes that unconditionally consume
# one extra inline word (2 words total for this control code).
CONTROL_B_TWO_WORD_ALWAYS: set[int] = {0x0d00, 0x0100, 0x0800, 0x1000, 0x1100, 0x1200}

# Family B subtypes that consume an extra word ONLY if (word & 0xff) < 2 --
# otherwise they're single-word. Confirmed via the LAB_80049aa8 shared code
# in the decompile.
CONTROL_B_TWO_WORD_CONDITIONAL: set[int] = {0x1600, 0x1700, 0x1800}

CONTROL_B_MEANINGS: dict[int, str] = {
    0x0100: "speaker_name_char",         # FUN_8006e4e4/e4a0, reads inline param
    0x0200: "call_FUN_8006e4bc",
    0x0300: "call_FUN_8006e4b0",
    0x0400: "call_FUN_8006e4ec",
    0x0500: "call_FUN_8006e51c",
    0x0600: "alias_of_0x8000_family_0x400_style",  # goes to LAB_80049c64
    0x0700: "call_FUN_800753f8",
    0x0800: "sound_or_voice_cue",        # reads inline param, 4 calls incl. FUN_80075b14
    0x0900: "clear_flag_cd4",
    0x0a00: "set_flag_cd4_2",
    0x0c00: "call_FUN_8004ab98",
    0x0d00: "kerning_or_name_slot_param",  # reads inline param, calls FUN_80050fe4
    0x0e00: "call_FUN_80049e30",
    0x0f00: "set_flag_0x20_and_c60",
    0x1000: "cue_mode_0",                # reads inline param, calls FUN_80058fc4(0, param)
    0x1100: "cue_mode_1",                # ditto, mode 1
    0x1200: "cue_mode_2",                # ditto, mode 2
    0x1400: "set_mode_ce4_fffd",
    0x1500: "call_FUN_8006d618",
    0x1600: "slot_lookup_0",             # conditionally reads inline param
    0x1700: "slot_lookup_1",             # conditionally reads inline param
    0x1800: "slot_lookup_2",             # conditionally reads inline param
    0x1900: "alias_of_0x1400",
}


@dataclass
class ScriptCode:
    offset: int                    # word offset within the buffer where this code started
    raw: int                       # raw 16-bit value of the opcode word
    kind: CodeKind
    family: ControlFamily | None = None   # only for CONTROL
    subtype: int | None = None            # only for CONTROL (word & 0x3F00)
    param: int | None = None              # inline parameter word, if one was consumed
    meaning: str | None = None            # known description, if any
    words_consumed: int = 1               # 1 or 2

    def to_dict(self) -> dict:
        d: dict = {
            "offset": self.offset,
            "raw": self.raw,
            "kind": self.kind.value,
            "words_consumed": self.words_consumed,
        }
        if self.family is not None:
            d["family"] = self.family.value
        if self.subtype is not None:
            d["subtype"] = self.subtype
        if self.param is not None:
            d["param"] = self.param
        if self.meaning is not None:
            d["meaning"] = self.meaning
        return d


@dataclass
class ScriptDocument:
    codes: list[ScriptCode] = field(default_factory=list)

    @property
    def control_events(self) -> list[ScriptCode]:
        return [c for c in self.codes if c.kind == CodeKind.CONTROL]

    @property
    def character_codes(self) -> list[ScriptCode]:
        return [c for c in self.codes if c.kind == CodeKind.CHARACTER]

    def to_dict(self) -> dict:
        return {
            "codes": [c.to_dict() for c in self.codes],
            "control_events": [c.to_dict() for c in self.control_events],
        }


def decode_script(data: bytes, max_words: int | None = None) -> ScriptDocument:
    """Decode a raw script buffer (bytes) into a ScriptDocument.

    `data` should start at the buffer's first word (e.g. a dump of
    0x801fe800 onward). Decoding stops at the first 0xFFFF word, at the
    end of `data`, or after `max_words` words if given (useful for a
    partial/bounded capture where the true end may not have been reached).
    """
    doc = ScriptDocument()
    n_words = len(data) // 2
    if max_words is not None:
        n_words = min(n_words, max_words)

    i = 0
    while i < n_words:
        offset = i
        raw = struct.unpack_from("<H", data, i * 2)[0]
        i += 1

        if raw == 0xFFFF:
            doc.codes.append(ScriptCode(offset, raw, CodeKind.END))
            break

        if (raw & 0xC000) == 0x0000:
            doc.codes.append(ScriptCode(offset, raw, CodeKind.CHARACTER))
            continue

        subtype = raw & 0x3F00
        if (raw & 0xC000) == 0x8000:
            family = ControlFamily.A
            meaning = CONTROL_A_MEANINGS.get(subtype)
            param = None
            words_consumed = 1
        else:
            family = ControlFamily.B
            meaning = CONTROL_B_MEANINGS.get(subtype)
            param = None
            words_consumed = 1
            consumes_extra = subtype in CONTROL_B_TWO_WORD_ALWAYS or (
                subtype in CONTROL_B_TWO_WORD_CONDITIONAL and (raw & 0xFF) < 2
            )
            if consumes_extra and i < n_words:
                param = struct.unpack_from("<H", data, i * 2)[0]
                i += 1
                words_consumed = 2

        doc.codes.append(
            ScriptCode(offset, raw, CodeKind.CONTROL, family, subtype, param, meaning, words_consumed)
        )

    return doc
