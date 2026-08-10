"""Live Text Workbench, Phase 4: validation layer.

Two different things get checked here, and they're deliberately kept
separate because only one of them can actually be automated right now:

- Missing-glyph and control-preservation checks CAN be automated: we
  already know the full glyph map (gcrts.glyph_char_map) and the
  invariant that injection never regenerates control codes
  (gcrts.live_injection always replays them verbatim), so both are
  checkable by inspection without ever touching the game.
- Whether edited text actually FITS on screen (overflow, bad wrapping)
  CANNOT be automated yet -- no max-chars-per-line/max-lines limit has
  been reverse-engineered (that's the workbench's still-open "layout
  and writing-behavior inspection" research task). Per the workbench
  spec: "This is not image automation yet. The validation can initially
  be manual + operator-entered." So fit status starts UNKNOWN and stays
  that way until an operator watches the injected line render in-game
  and calls manual_confirm() with what they saw.

ValidationStatus intentionally has exactly the five values the workbench
spec calls for -- "wraps badly" from that spec's requirements list is a
symptom an operator would report AS an OVERFLOW confirmation (with the
specifics in the free-text `detail`), not a sixth status value.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import Enum

from gcrts.control_position_risk import STALE_POSITION_MEANINGS
from gcrts.live_injection import segment_from_unit
from gcrts.script_decoder import CodeKind, decode_script
from gcrts.script_encoder import MissingGlyphError, encode_segment, tokenize_translated_text
from gcrts.script_unit import ScriptUnit


class ValidationStatus(Enum):
    UNKNOWN = "unknown"  # not yet checked, or automatic checks passed but no manual confirmation yet
    OK = "ok"  # operator-confirmed: renders correctly in-game
    OVERFLOW = "overflow"  # operator-confirmed: overflowed / wrapped badly / got cut off
    MISSING_GLYPH = "missing_glyph"  # automatic: edited text uses a character with no known code
    CONTROL_ISSUE = "control_issue"  # automatic: re-encoding didn't preserve control codes as expected


@dataclass
class ValidationReport:
    status: ValidationStatus
    detail: str = ""


def control_signature_from_events(events: list[dict], exclude_meanings: frozenset[str] = frozenset()) -> list[tuple]:
    return [
        (e.get("family"), e.get("subtype"), e.get("param"), e.get("meaning"))
        for e in events
        if e.get("meaning") not in exclude_meanings
    ]


def control_signature_after_reencoding(unit: ScriptUnit) -> list[tuple]:
    """Actually run this unit's current edited_text through the real
    encoder (the same one gcrts.live_injection uses) and see what control
    events come out the other end -- a genuine regression check, not a
    tautology. (Just re-deriving from unit.raw_codes would always match,
    since raw_codes never changes when edited_text does.)"""
    segment = segment_from_unit(unit)
    words = encode_segment(segment)
    packed = struct.pack(f"<{len(words)}H", *words)
    doc = decode_script(packed)
    return [
        (c.family.value if c.family else None, c.subtype, c.param, c.meaning)
        for c in doc.codes
        if c.kind == CodeKind.CONTROL
    ]


def auto_validate(unit: ScriptUnit) -> ValidationReport:
    """Run the checks that don't require watching the game. Returns
    MISSING_GLYPH or CONTROL_ISSUE if either fails; otherwise UNKNOWN,
    meaning "no automatic problems found, but fit is still unconfirmed"."""
    try:
        tokenize_translated_text(unit.edited_text)
    except MissingGlyphError as e:
        return ValidationReport(ValidationStatus.MISSING_GLYPH, detail=str(e))

    # A modified unit's segment_from_unit() intentionally drops
    # STALE_POSITION_MEANINGS codes (see its docstring) -- exclude them
    # from the "expected" signature too, or this would always false-flag
    # CONTROL_ISSUE on any unit that has one.
    exclude = STALE_POSITION_MEANINGS if unit.is_modified else frozenset()
    original_sig = control_signature_from_events(unit.control_events, exclude_meanings=exclude)
    current_sig = control_signature_after_reencoding(unit)
    if original_sig != current_sig:
        return ValidationReport(
            ValidationStatus.CONTROL_ISSUE,
            detail=f"control event sequence changed: {original_sig} -> {current_sig}",
        )

    return ValidationReport(
        ValidationStatus.UNKNOWN, detail="automatic checks passed; needs manual in-game confirmation"
    )
