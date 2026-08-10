"""Live Text Editor Workbench, Phase 3: boundary validation.

Reports the boundary-relevant consequences of an edit, calibrated
honestly to how gcrts.live_injection actually works: it ALWAYS re-encodes
and rewrites every unit sharing a buffer together, concatenated in
order, from each unit's own raw_codes (control codes replayed verbatim,
never regenerated -- see that module's docstring). That design already
structurally prevents several of the failure modes this phase's spec
worries about: control events can't be deleted, the end marker can't be
corrupted, and the stream can't become ambiguous, because nothing ever
patches bytes in place at a fixed offset.

What CAN genuinely happen, and what this module actually checks:

1. A length-changing edit shifts where every later unit in the SAME
   buffer lands once re-injected. Not corruption -- later units' own
   content and control codes are untouched, just relocated -- but the
   operator should know it's happening. It matters most if injection
   happens while the game's own read cursor is already partway through
   the buffer: anything already consumed won't be re-read (a silent
   no-op, not a crash -- confirmed empirically in NOTES.md's Phase 5
   live testing), so a length change only actually affects units still
   ahead of the live cursor.
2. contiguous_with_next() going False on a stored unit -- the boundary
   bookkeeping itself drifting from what re-decoding raw_codes would
   produce. Reuses gcrts.script_unit.ScriptUnit.contiguous_with_next()
   rather than re-deriving it.
3. Whether re-encoding this unit's *current* edited_text still succeeds
   at all (e.g. a missing glyph) -- runs the real encode path exactly
   like gcrts.validation's control-preservation check does, rather than
   guessing whether it would.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from gcrts.live_injection import segment_from_unit
from gcrts.script_encoder import MissingGlyphError, encode_segment
from gcrts.script_unit import ScriptUnit


@dataclass
class BoundaryReport:
    unit_id: str
    original_word_count: int
    new_word_count: int | None  # None if encoding failed
    word_count_delta: int | None  # None if encoding failed
    shifts_subsequent_units: bool
    boundary_bookkeeping_ok: bool
    can_encode: bool
    encode_error: str = ""
    warnings: list[str] = field(default_factory=list)


def check_boundary(unit: ScriptUnit) -> BoundaryReport:
    """Check one unit's current edited_text against its stored boundary.
    Safe to call whether or not the unit has actually been edited --
    an untouched unit just reports zero delta."""
    original_word_count = unit.unit_end_offset - unit.unit_start_offset
    warnings: list[str] = []

    boundary_ok = unit.contiguous_with_next()
    if not boundary_ok:
        warnings.append(
            f"{unit.id}: stored boundary offsets are NOT contiguous with the next unit "
            f"(end={unit.unit_end_offset}, next_start={unit.next_unit_start_offset}) -- "
            "boundary bookkeeping has drifted from what re-decoding raw_codes would produce"
        )

    new_word_count: int | None
    delta: int | None
    shifts_subsequent = False
    can_encode = True
    encode_error = ""
    try:
        segment = segment_from_unit(unit)
        words = encode_segment(segment)
        new_word_count = len(words)
        delta = new_word_count - original_word_count
        shifts_subsequent = delta != 0 and unit.next_unit_start_offset is not None
        if shifts_subsequent:
            direction = "longer" if delta > 0 else "shorter"
            warnings.append(
                f"{unit.id}: edited text encodes to {abs(delta)} word(s) {direction} than the "
                f"original -- every unit after this one in the same buffer will shift by "
                f"{delta:+d} word(s) when re-injected (safe: their own content/control codes "
                "are never touched, only relocated -- just be aware if timing injection "
                "against a live read cursor that may already be past this point)"
            )
    except MissingGlyphError as e:
        new_word_count = None
        delta = None
        can_encode = False
        encode_error = str(e)
        warnings.append(f"{unit.id}: cannot encode -- {e}")

    return BoundaryReport(
        unit_id=unit.id,
        original_word_count=original_word_count,
        new_word_count=new_word_count,
        word_count_delta=delta,
        shifts_subsequent_units=shifts_subsequent,
        boundary_bookkeeping_ok=boundary_ok,
        can_encode=can_encode,
        encode_error=encode_error,
        warnings=warnings,
    )


def check_chain(units: list[ScriptUnit]) -> list[str]:
    """Whole-list integrity check: compares each unit's ACTUAL end offset
    against the NEXT unit's ACTUAL start offset in the given list order
    (not just each unit's own self-reported next_unit_start_offset,
    which could in principle be stale even if contiguous_with_next()
    looks fine in isolation). Returns a list of problem descriptions;
    empty means the chain is fully gapless."""
    problems: list[str] = []
    for a, b in zip(units, units[1:]):
        if a.unit_end_offset != b.unit_start_offset:
            problems.append(
                f"{a.id} ends at offset {a.unit_end_offset} but the next unit in this list, "
                f"{b.id}, starts at offset {b.unit_start_offset} -- gap or overlap between them"
            )
    return problems
