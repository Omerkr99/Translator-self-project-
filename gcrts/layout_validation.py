"""Live Text Editor Workbench, Phase 4: layout and glyph validation.

Combines the checks already built in earlier phases -- missing-glyph and
control-code preservation (gcrts.validation), boundary/shift risk
(gcrts.boundary_validation) -- with NEW layout-fit checks, into the
single richer status set this phase's spec asks for:

    ok, pixel_overflow, too_many_lines, awkward_wrap, missing_glyph,
    boundary_risk, control_issue, style_review_needed

Layout fit is HONESTLY approximate, but the WRAP ALGORITHM itself is no
longer guessed at -- it was reverse-engineered via a live GDB breakpoint
on CAP0.EXE's FUN_8004a370 (the per-character cursor-advance/wrap
decision, called from the master render loop FUN_800481b0). Confirmed
findings:

- The wrap check is `current_X + char_width + spacing <= base_X +
  max_width`, evaluated PER CHARACTER, with zero word-boundary logic.
  This matches the live-observed behavior exactly: injected English text
  wrapped mid-word ("th"/"ey" from "they", "lau"/"ghter" from "laughter").
- Live-captured struct values for the active dialogue textbox: base_X=10,
  max_width=280 (both in the engine's internal coordinate unit --
  FUN_8004aa08 right-shifts the stored X by 2 before the final VRAM blit,
  suggesting these may be quarter-pixel subunits, i.e. ~70px in real
  screen pixels, but that conversion factor isn't independently confirmed
  yet). Per-character width comes from a lookup table at
  `DAT_80093b38 + code*8` in CAP0.EXE, keyed by character code.

**Per-character width is no longer a heuristic either.** `DAT_80093b38`
turned out to equal `gcrts.glyph_atlas.TABLE_RAM_ADDR + 4` with the same
8-byte stride -- i.e. it's just `atlas.table_entry(code)[1]`, the glyph
pointer table's own second field. That field was originally assumed (in
glyph_atlas.py) to be a compressed-byte count, which turned out to be
wrong (truncating to it cut streams short); it's actually the glyph's
advance width, hiding in data this project already had. Live-verified:
'A'/'M'/'W' all measure 14, 'i' measures 8, 'l' measures 7 -- exactly a
real proportional font's shape, not a guess. `measure_pixel_width()`
below reads this directly via `atlas.table_entry()` when an atlas is
given, and only falls back to the documented half/full-width
character-count heuristic when one isn't available.

What's still approximate: the absolute max_width in real screen pixels
(the /4 conversion factor), and whether it varies by textbox/scene type
(`box_profile` in the terms of this phase's own JSON schema) -- only the
one narration textbox instance was actually measured live, and attempts
to fit text to a wider budget (250) than the conservative first estimate
(70) produced a visible regression in live testing (a word split again),
meaning the real max_width for that textbox sits somewhere between the
two -- not yet narrowed down further.

**MAX_VISIBLE_LINES = 4 is confirmed, not guessed**: it's the byte at
offset 4 of the same live layout struct (`*(byte *)(param_3 + 2)` in
`FUN_8004a6fc`'s scroll-trigger math -- read as a short-pointer offset,
which lands on the struct's low byte at byte-offset 4), and it matches
observed behavior twice: a 100-character live probe filled exactly 4
lines before the box paused on a "press to continue" prompt, both when
the box held a short run of text and when it held a much longer one.

**Scroll-transition X-formula is IDENTICAL to a normal wrap's, not
different** (this corrects an earlier, wrong reading of the same
decompile): `FUN_8004a370`'s own wrap-reset (line `*(ushort
*)(DAT_800a4cd8*0xe+param_1+8) = (ushort)bVar1 + sVar4 + *param_2;`) and
`FUN_8004a6fc`'s scroll-reset (`*(short *)(...+8) = param_4 + param_5 +
*param_3;`, where param_4/param_5 are the SAME sVar4/bVar1 the caller
just computed) compute the exact same value -- the scroll case just has
to re-home that value to a new array slot after compacting out the
oldest visible line. A live 100-character probe confirmed this: once
past the first line, two consecutive wraps (lines 2 and 3) both landed
at a clean, exactly-predicted 20 characters -- no anomaly at a scroll
boundary at all.

The REAL, still-unmodeled source of variable wrap position is a pair of
additive terms folded into every wrap-reset X, unrelated to scrolling:
`bVar1` (= `DAT_800a4d13`, read fresh at the top of every
`FUN_8004a370` call) and `sVar4` (0 normally, but `*(short
*)(param_3+8)*3+6` whenever a separate flag `DAT_800a4d12` -- read via
`FUN_8004a240()` -- is set). Something elsewhere in the script-control-
code handling sets these two globals (most likely centering/indent
control codes, given `DAT_80093b38`'s established role in
`line_center_calc`), and this project hasn't traced their writers. This
is very likely why a fresh textbox's first line sometimes measured a
full 20 characters and other times only 11 -- not scrolling, not a width
measurement error, but this pair of per-wrap offsets depending on
whatever control codes preceded the text. Tracing every writer of
`DAT_800a4d12`/`DAT_800a4d13` across the EXE would be a distinct,
open-ended follow-up if fully eliminating that variability ever matters.

Per this phase's own instruction ("use pixel-aware logic if available;
character count only as a fallback approximation"):

- When a GlyphAtlas is available, per-character width is the REAL
  advance width from `atlas.table_entry(code)[1]` -- genuine game data,
  not an assumed font metric or a bitmap-derived approximation.
- Without one, width falls back to a documented full-width/half-width
  character-count heuristic (CJK characters conventionally render about
  2x the advance width of Latin/ASCII ones in most fonts -- a generic
  typographic convention, not something measured from this game).

Either way, the fit BUDGET itself is derived from the original
Japanese's own measured width for this same unit -- since that text
definitely rendered correctly in-game, it is the one concrete "this
fits" reference actually available, rather than a fabricated absolute
pixel limit.

style_review_needed is NEVER assigned automatically -- whether a
translation reads naturally is a human judgment call, not a checkable
property. It exists purely as a state an operator can flag manually
(see gcrts.editor_state's validation storage, reused here).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from gcrts.boundary_validation import check_boundary
from gcrts.control_position_risk import STALE_POSITION_MEANINGS
from gcrts.glyph_atlas import GlyphAtlas
from gcrts.glyph_char_map import code_for_char
from gcrts.script_encoder import MissingGlyphError, tokenize_translated_text
from gcrts.script_unit import ScriptUnit
from gcrts.validation import control_signature_after_reencoding, control_signature_from_events


class LayoutValidationStatus(Enum):
    OK = "ok"
    PIXEL_OVERFLOW = "pixel_overflow"
    TOO_MANY_LINES = "too_many_lines"
    AWKWARD_WRAP = "awkward_wrap"
    MISSING_GLYPH = "missing_glyph"
    BOUNDARY_RISK = "boundary_risk"
    CONTROL_ISSUE = "control_issue"
    STYLE_REVIEW_NEEDED = "style_review_needed"  # manual only, never auto-assigned


# Generic typographic convention (full-width CJK glyphs are roughly 2x a
# half-width Latin/ASCII glyph's advance width in most fonts) -- used
# ONLY as a fallback when no glyph atlas is available to measure real
# per-character pixel widths. Not measured from this game specifically.
FALLBACK_HALF_WIDTH_PX = 8
FALLBACK_FULL_WIDTH_PX = 16

# Confirmed, not guessed: the byte at offset 4 of the live layout struct
# (see module docstring's "MAX_VISIBLE_LINES is confirmed" section) --
# matches two independent live probes, both of which filled exactly 4
# lines before the textbox paused for input.
MAX_VISIBLE_LINES = 4


def _is_fullwidth(ch: str) -> bool:
    return ord(ch) > 0x2FFF or ch in "、。・ー―〜"


def estimate_char_width_fallback(ch: str) -> int:
    return FALLBACK_FULL_WIDTH_PX if _is_fullwidth(ch) else FALLBACK_HALF_WIDTH_PX


def _measured_glyph_width(ch: str, atlas: GlyphAtlas) -> int | None:
    """The REAL per-character advance width the game's own renderer
    uses -- not an approximation. Confirmed via live investigation
    (see NOTES.md): CAP0.EXE's wrap/kerning code reads width from
    `DAT_80093b38 + code*8`, and `DAT_80093b38 == TABLE_RAM_ADDR + 4`
    (gcrts.glyph_atlas.TABLE_RAM_ADDR) with the same 8-byte stride --
    i.e. this is exactly `atlas.table_entry(code)[1]`, the second value
    of the glyph pointer table's 8-byte entry. That field was originally
    (wrongly) assumed to be a compressed-byte count (see glyph_atlas.py's
    own docstring on why that assumption failed); it's actually the
    glyph's advance width, and reusing table_entry() rather than
    duplicating a table read keeps this from drifting out of sync with
    that module. Live-verified: 'A'/'M'/'W' all measure 14, 'i' measures
    8, 'l' measures 7 -- exactly the shape of a real proportional font."""
    code = code_for_char(ch)
    if code is None:
        return None
    entry = atlas.table_entry(code)
    if entry is None:
        return None
    return entry[1]


def measure_pixel_width(text: str, atlas: GlyphAtlas | None = None) -> int:
    """Total advance width of `text` in pixels. Uses real glyph bitmap
    data per character when `atlas` is given and has that character;
    falls back to the documented half/full-width heuristic otherwise."""
    total = 0
    for ch in text:
        width = _measured_glyph_width(ch, atlas) if atlas is not None else None
        if width is None:
            width = estimate_char_width_fallback(ch)
        total += width
    return total


@dataclass
class LayoutReport:
    status: LayoutValidationStatus
    detail: str = ""
    original_width_px: int = 0
    edited_width_px: int = 0
    estimated_lines: int = 1


def _greedy_wrap(text: str, line_budget_px: int, atlas: GlyphAtlas | None) -> tuple[int, bool]:
    """Simulate the game's REAL wrap algorithm -- confirmed via a live GDB
    breakpoint on FUN_800481b0's cursor-advance callee (FUN_8004a370) in
    CAP0.EXE, not guessed: it accumulates character width one glyph at a
    time and wraps the instant the NEXT character would push the running
    total past the line budget --

        current_X + this_char_width + spacing <= base_X + max_width

    -- with NO word/space-boundary awareness whatsoever. This is exactly
    why the live test that started this investigation showed "they" and
    "laughter" split mid-word ("th"/"ey", "lau"/"ghter") -- that's not an
    edge case, it's how this engine always wraps. An earlier version of
    this function modeled word-aware wrapping (never breaking mid-word)
    because that's the sane assumption absent evidence -- that assumption
    was wrong and has been replaced with what was actually observed.

    Returns (line_count, wrapped_mid_word) -- the second is True if any
    wrap point in THIS simulation landed between two non-space characters
    (i.e. actually split a word), which is what `awkward_wrap` now
    specifically flags -- a real, checkable condition using the
    confirmed algorithm, not a guess about word length."""
    lines = 1
    current_width = 0
    wrapped_mid_word = False
    prev_char: str | None = None
    for ch in text:
        width = measure_pixel_width(ch, atlas)
        if current_width + width > line_budget_px and current_width > 0:
            if prev_char is not None and prev_char != " " and ch != " ":
                wrapped_mid_word = True
            lines += 1
            current_width = 0
        current_width += width
        prev_char = ch
    return lines, wrapped_mid_word


def check_layout(
    unit: ScriptUnit,
    atlas: GlyphAtlas | None = None,
    max_lines: int = MAX_VISIBLE_LINES,
    overflow_margin: float = 1.15,
) -> LayoutReport:
    """Run every automatic check for `unit`'s current edited_text and
    return the single highest-priority issue found, in this order:
    missing glyph > control issue > boundary risk > pixel overflow >
    too many lines > awkward wrap > ok. (style_review_needed is never
    returned here -- see the module docstring.)"""
    try:
        tokenize_translated_text(unit.edited_text)
    except MissingGlyphError as e:
        return LayoutReport(LayoutValidationStatus.MISSING_GLYPH, detail=str(e))

    # A modified unit's gcrts.live_injection.segment_from_unit() intentionally
    # drops STALE_POSITION_MEANINGS codes (see its docstring) -- exclude
    # them from the "expected" signature too, or this would always
    # false-flag CONTROL_ISSUE on any unit that has one.
    exclude = STALE_POSITION_MEANINGS if unit.is_modified else frozenset()
    original_sig = control_signature_from_events(unit.control_events, exclude_meanings=exclude)
    current_sig = control_signature_after_reencoding(unit)
    if original_sig != current_sig:
        return LayoutReport(
            LayoutValidationStatus.CONTROL_ISSUE,
            detail=f"control event sequence changed: {original_sig} -> {current_sig}",
        )

    boundary = check_boundary(unit)
    if not boundary.boundary_bookkeeping_ok:
        return LayoutReport(LayoutValidationStatus.BOUNDARY_RISK, detail="; ".join(boundary.warnings))

    original_width = measure_pixel_width(unit.original_text, atlas)
    edited_width = measure_pixel_width(unit.edited_text, atlas)

    if edited_width > original_width * overflow_margin:
        return LayoutReport(
            LayoutValidationStatus.PIXEL_OVERFLOW,
            detail=f"edited text measures {edited_width}px vs original's {original_width}px "
            f"(over the {overflow_margin:.0%} margin)",
            original_width_px=original_width,
            edited_width_px=edited_width,
        )

    # per-line budget derived from the original's own measured width --
    # the one concrete "this fit" reference actually available
    line_budget = max(original_width, FALLBACK_FULL_WIDTH_PX)
    lines, broke_a_word = _greedy_wrap(unit.edited_text, line_budget, atlas)

    if lines > max_lines:
        return LayoutReport(
            LayoutValidationStatus.TOO_MANY_LINES,
            detail=f"estimated {lines} lines (assumed budget {line_budget}px/line, max {max_lines})",
            original_width_px=original_width,
            edited_width_px=edited_width,
            estimated_lines=lines,
        )

    if broke_a_word:
        return LayoutReport(
            LayoutValidationStatus.AWKWARD_WRAP,
            detail="at least one word is wider than the assumed per-line budget on its own, "
            "forcing a mid-word break",
            original_width_px=original_width,
            edited_width_px=edited_width,
            estimated_lines=lines,
        )

    return LayoutReport(
        LayoutValidationStatus.OK,
        detail="automatic checks passed (layout fit is approximate -- see module docstring)",
        original_width_px=original_width,
        edited_width_px=edited_width,
        estimated_lines=lines,
    )
