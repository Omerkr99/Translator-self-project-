"""Live Text Workbench, Phase 3: connects the editor's edited text
(gcrts.editor_state) to the live RAM writer (gcrts.live_extract), reusing
the already-validated re-encoding engine (gcrts.script_encoder) unchanged.

Design: a ScriptUnit's `raw_codes` is its own exact original word stream
(gcrts.script_unit's docstring calls this out explicitly), so re-decoding
it via gcrts.script_decoder.decode_script reconstructs the identical
ScriptCode list -- including every control code's family/subtype/param --
without needing to keep live ScriptCode objects around on the unit
itself. That reconstructed segment is then handed to
gcrts.script_encoder.encode_segment exactly as gcrts.editable_script
would have produced it, so control-code preservation and the
untouched-segment byte-exact shortcut both keep working unchanged.

Injection always rewrites the WHOLE buffer a set of units came from (all
units sharing one base_ram_address, in order), not one unit in isolation
-- patching a single unit's bytes in place would corrupt everything
after it the moment an edit changes length (English translations rarely
have the same character count as the Japanese they replace). Writing
the complete reconstructed buffer from its start, terminated by the
0xFFFF marker the reader already stops at (confirmed in NOTES.md's
Phase 5 live test), is what keeps this safe.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from gcrts.control_position_risk import STALE_POSITION_MEANINGS
from gcrts.editable_script import ScriptSegment
from gcrts.editor_state import EditorState, UnitStatus
from gcrts.live_extract import write_script_buffer
from gcrts.script_decoder import CodeKind, decode_script
from gcrts.script_encoder import MissingGlyphError, encode_segment
from gcrts.script_unit import ScriptUnit

# Coarse heuristic only -- real per-scene rendering limits (max chars per
# line/box) are not known yet; that's the workbench's Phase 4 (validation
# layer / layout inspection) job. This just flags a large size jump so an
# operator doesn't inject something wildly longer than the original
# without at least a heads-up.
LENGTH_GROWTH_WARNING_THRESHOLD = 20


@dataclass
class InjectionResult:
    success: bool
    bytes_written: int
    error: str | None
    warnings: list[str] = field(default_factory=list)


def segment_from_unit(unit: ScriptUnit) -> ScriptSegment:
    """Rebuild a ScriptSegment from a unit's raw_codes -- decode_script is
    a pure function of the bytes, so this reconstructs the exact same
    ScriptCode list (family/subtype/param/meaning included) the original
    gcrts.editable_script.to_editable() call produced, without needing to
    have kept those objects around on the ScriptUnit itself.

    For a MODIFIED unit only, STALE_POSITION_MEANINGS control codes
    (pause_flag_a/pause_flag_b -- see gcrts.control_position_risk) are
    dropped before encoding. Live testing found these mid-word split text
    unpredictably: they position the character immediately after them
    using whatever DAT_800a4d13 happens to hold at that moment, leftover
    state from wherever it was last set -- not something this project can
    predict without a whole-scene simulation. They exist in the original
    Japanese script for a subtle mid-sentence pacing pause; dropping them
    loses that pause but eliminates the unpredictable split, a tradeoff
    confirmed with the user after DAT_800a4d10-forced wraps (a genuinely
    predictable, separate mechanism -- see FORCED_WRAP_MEANINGS) were
    fixed precisely and this one still wasn't. Unmodified units keep
    every code exactly as authored -- only edited units diverge from
    the original playback."""
    packed = struct.pack(f"<{len(unit.raw_codes)}H", *unit.raw_codes)
    doc = decode_script(packed)
    codes = doc.codes
    if unit.is_modified:
        codes = [c for c in codes if c.meaning not in STALE_POSITION_MEANINGS]
    return ScriptSegment(
        codes=codes,
        original=unit.original_text,
        translated=unit.edited_text,
        layout_constraints=unit.layout_constraints,
    )


def encode_units(units: list[ScriptUnit]) -> bytes:
    """Re-encode a list of units -- assumed to be ALL units from the same
    original buffer, in their original order -- into one contiguous byte
    stream ready to write back over that buffer. Raises MissingGlyphError
    (from gcrts.script_encoder) if an edited unit's text uses a character
    with no known glyph code."""
    words: list[int] = []
    for unit in units:
        segment = segment_from_unit(unit)
        words.extend(encode_segment(segment))
    return struct.pack(f"<{len(words)}H", *words)


def validate_encoded_units(units: list[ScriptUnit], encoded: bytes) -> list[str]:
    """Non-blocking warnings for the caller to display before/after
    writing. Hard failures (bad glyphs, malformed output) are reported
    via InjectionResult.error instead, not here."""
    warnings: list[str] = []
    for unit in units:
        if not unit.is_modified:
            continue
        growth = len(unit.edited_text) - len(unit.original_text)
        if growth > LENGTH_GROWTH_WARNING_THRESHOLD:
            warnings.append(
                f"{unit.id}: edited text is {growth} characters longer than the original -- "
                "may overflow the textbox (real fit-checking isn't implemented yet)"
            )

    redecoded = decode_script(encoded)
    if not redecoded.codes or redecoded.codes[-1].kind != CodeKind.END:
        warnings.append(
            "encoded output has no trailing 0xFFFF end marker -- the game may read past "
            "the intended end into stale/unrelated buffer contents"
        )
    return warnings


def inject_units_live(
    units: list[ScriptUnit], host: str = "127.0.0.1", port: int = 3333
) -> InjectionResult:
    """Re-encode and write `units` (all from the same buffer, in order)
    back into live RAM at their shared base address. Never partially
    writes: encoding and validation happen before any write_memory call,
    so a bad edit fails closed rather than corrupting the buffer."""
    if not units:
        return InjectionResult(success=False, bytes_written=0, error="no units to inject")

    base = units[0].ram_address
    if base is None:
        return InjectionResult(
            success=False, bytes_written=0, error="units have no known ram_address (not a live_ram capture?)"
        )

    try:
        encoded = encode_units(units)
    except MissingGlyphError as e:
        return InjectionResult(success=False, bytes_written=0, error=str(e))

    warnings = validate_encoded_units(units, encoded)
    if any("no trailing 0xFFFF" in w for w in warnings):
        return InjectionResult(
            success=False, bytes_written=0, error="refusing to write: malformed encoded output", warnings=warnings
        )

    ok = write_script_buffer(encoded, host=host, port=port)
    if not ok:
        return InjectionResult(success=False, bytes_written=0, error="live write failed", warnings=warnings)

    return InjectionResult(success=True, bytes_written=len(encoded), error=None, warnings=warnings)


def inject_all_live(state: EditorState, host: str = "127.0.0.1", port: int = 3333) -> InjectionResult:
    """Inject every unit currently loaded in `state` (assumed to all
    share one buffer -- true for anything loaded via a single
    gcrts.script_unit.extract_live_script_units() call). On success,
    marks every unit INJECTED so the editor can track what's actually
    live versus just edited in-session."""
    result = inject_units_live(state.units, host=host, port=port)
    if result.success:
        for unit in state.units:
            state.set_status(unit.id, UnitStatus.INJECTED)
    else:
        for unit in state.units:
            if unit.is_modified:
                state.set_status(unit.id, UnitStatus.INVALID)
    return result
