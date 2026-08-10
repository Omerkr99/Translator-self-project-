"""Live Text Editor Workbench: a reusable index over observed script
control words, built for the mode-3 (`Y_COLLECTION_MODE`) trigger
investigation but intentionally general -- future control-code research
should extend this rather than write another one-off scanner.

Every classifier here is derived from live MIPS disassembly of
`FUN_80049168` (CAP0.EXE's script-bytecode decoder), not guessed from
the word format alone -- see `MODE3_TRIGGER_INVESTIGATION.md` for the
full instruction-level trace backing `produces_y_collection_mode`.
Only that one decoder output is currently modeled with runtime-verified
confidence; everything else in `gcrts.script_decoder.CONTROL_A_MEANINGS`/
`CONTROL_B_MEANINGS` remains classified by name only (a decompiled name
is not a confirmed runtime behavior -- the same caution
`gcrts.control_policy` already applies elsewhere in this project).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from gcrts.script_decoder import CONTROL_A_MEANINGS, CONTROL_B_MEANINGS

FAMILY_MASK = 0xC000
FAMILY_A = 0x8000
FAMILY_B = 0xC000
SUBTYPE_MASK = 0x3F00
PARAM_MASK = 0x00FF

# Confirmed via live MIPS disassembly of FUN_80049168 (see
# MODE3_TRIGGER_INVESTIGATION.md): subtype 0x0500 ("pause_flag_a", per
# gcrts.control_position_risk's existing naming) with a nonzero
# parameter byte is the only known producer of Y_COLLECTION_MODE.
SUBTYPE_PAUSE_FLAG_A = 0x0500


def word_family(word: int) -> str:
    masked = word & FAMILY_MASK
    if masked == 0:
        return "direct_character"
    if masked == FAMILY_A:
        return "control_a"
    if masked == FAMILY_B:
        return "control_b"
    return "unknown"  # the decoder's own dispatch never observed this combination


def word_subtype(word: int) -> int:
    return word & SUBTYPE_MASK


def word_parameter(word: int) -> int:
    return word & PARAM_MASK


def produces_y_collection_mode(word: int) -> bool:
    """Runtime-verified (see MODE3_TRIGGER_INVESTIGATION.md): family A,
    subtype 0x0500 (pause_flag_a), nonzero parameter byte. This is the
    ONLY confirmed producer of Y_COLLECTION_MODE found this project --
    it does not claim completeness (other subtypes were not individually
    ruled out as alternate producers, only this one was traced and
    confirmed by full branch/loop-back analysis)."""
    return (
        word_family(word) == "control_a"
        and word_subtype(word) == SUBTYPE_PAUSE_FLAG_A
        and word_parameter(word) != 0
    )


@dataclass
class ControlWordRecord:
    """One observed (or hypothesized) control word and everything known
    about it. `runtime_verified` distinguishes a word whose DECODER
    OUTPUT was actually observed live from one that's merely classified
    by bit pattern -- the same "don't overclaim" discipline
    `gcrts.mips_patch_profile.PatchProfileStatus` already enforces for
    MIPS patch profiles."""

    raw_word: int
    occurrences: int = 0
    units: list[str] = field(default_factory=list)
    known_decoder_output: str | None = None
    runtime_verified: bool = False

    @property
    def family(self) -> str:
        return word_family(self.raw_word)

    @property
    def subtype(self) -> int:
        return word_subtype(self.raw_word)

    @property
    def parameter(self) -> int:
        return word_parameter(self.raw_word)

    @property
    def meaning(self) -> str | None:
        if self.family == "control_a":
            return CONTROL_A_MEANINGS.get(self.subtype)
        if self.family == "control_b":
            return CONTROL_B_MEANINGS.get(self.subtype)
        return None

    def to_dict(self) -> dict:
        return {
            "raw_word": f"{self.raw_word:#06x}",
            "family": self.family,
            "subtype": f"{self.subtype:#06x}",
            "parameter": self.parameter,
            "meaning": self.meaning,
            "occurrences": self.occurrences,
            "units": list(self.units),
            "known_decoder_output": self.known_decoder_output,
            "runtime_verified": self.runtime_verified,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ControlWordRecord":
        return cls(
            raw_word=int(d["raw_word"], 16),
            occurrences=d.get("occurrences", 0),
            units=list(d.get("units", [])),
            known_decoder_output=d.get("known_decoder_output"),
            runtime_verified=bool(d.get("runtime_verified", False)),
        )


class ControlCodeIndex:
    """A growable index of observed control words, keyed by exact raw
    word value (not just subtype) since the parameter byte can change a
    word's decoder-output classification entirely -- see
    `produces_y_collection_mode`, which depends on the parameter being
    nonzero, not just the subtype matching."""

    def __init__(self) -> None:
        self._records: dict[int, ControlWordRecord] = {}

    def observe(self, word: int, unit_id: str | None = None) -> ControlWordRecord:
        """Record one occurrence of `word`, optionally tagging which
        unit it came from. Idempotent-safe to call repeatedly across a
        scan."""
        rec = self._records.get(word)
        if rec is None:
            rec = ControlWordRecord(raw_word=word)
            self._records[word] = rec
        rec.occurrences += 1
        if unit_id is not None and unit_id not in rec.units:
            rec.units.append(unit_id)
        if produces_y_collection_mode(word):
            rec.known_decoder_output = "Y_COLLECTION_MODE"
        return rec

    def scan_words(self, words: list[int], unit_id: str | None = None) -> list[ControlWordRecord]:
        """Observe every control-family word (family A or B) in
        `words`, skipping direct character codes and the 0xFFFF
        terminator -- callers researching a specific control code don't
        need every glyph in the index."""
        hits = []
        for w in words:
            if w == 0xFFFF:
                break
            if word_family(w) in ("control_a", "control_b"):
                hits.append(self.observe(w, unit_id))
        return hits

    def by_family(self, family: str) -> list[ControlWordRecord]:
        return [r for r in self._records.values() if r.family == family]

    def by_subtype(self, subtype: int) -> list[ControlWordRecord]:
        return [r for r in self._records.values() if r.subtype == subtype]

    def by_decoder_output(self, output: str) -> list[ControlWordRecord]:
        return [r for r in self._records.values() if r.known_decoder_output == output]

    def all_records(self) -> list[ControlWordRecord]:
        return sorted(self._records.values(), key=lambda r: r.raw_word)

    def to_json(self) -> list[dict]:
        return [r.to_dict() for r in self.all_records()]

    def to_markdown(self) -> str:
        lines = [
            "| raw_word | family | subtype | parameter | meaning | occurrences | decoder_output | verified |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for r in self.all_records():
            lines.append(
                f"| {r.raw_word:#06x} | {r.family} | {r.subtype:#06x} | {r.parameter} | "
                f"{r.meaning or '-'} | {r.occurrences} | {r.known_decoder_output or '-'} | "
                f"{'yes' if r.runtime_verified else 'no'} |"
            )
        return "\n".join(lines)
