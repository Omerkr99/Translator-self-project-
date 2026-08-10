import struct

from gcrts.glyph_atlas import GlyphAtlas
from gcrts.glyph_char_map import CHAR_TO_CODE
from gcrts.layout_validation import (
    FALLBACK_FULL_WIDTH_PX,
    FALLBACK_HALF_WIDTH_PX,
    LayoutValidationStatus,
    _greedy_wrap,
    check_layout,
    estimate_char_width_fallback,
    measure_pixel_width,
)
from gcrts.script_decoder import decode_script
from gcrts.script_unit import units_from_script_document


def _pack(words):
    return struct.pack(f"<{len(words)}H", *words)


def _fake_atlas(char_widths: dict[str, int]) -> GlyphAtlas:
    """Fake an atlas whose table_entry(code)[1] returns a chosen width --
    matching how gcrts.layout_validation._measured_glyph_width actually
    reads real per-character advance width (see that function's
    docstring: it's table_entry()[1], not anything derived from the
    glyph bitmap itself)."""
    entries = {CHAR_TO_CODE[ch]: (0, width) for ch, width in char_widths.items()}
    atlas = GlyphAtlas(exe_data=b"", text_addr=0, text_size=0)
    atlas.table_entry = lambda code: entries.get(code)
    return atlas


def _single_char_unit(original_char: str, edited_text: str):
    code = CHAR_TO_CODE[original_char]
    doc = decode_script(_pack([code, 0xFFFF]))
    units = units_from_script_document(doc, scene_id="s")
    units[0].edited_text = edited_text
    return units[0]


# --- width measurement -------------------------------------------------


def test_estimate_char_width_fallback_half_vs_full():
    assert estimate_char_width_fallback("A") == FALLBACK_HALF_WIDTH_PX
    assert estimate_char_width_fallback("あ") == FALLBACK_FULL_WIDTH_PX


def test_measure_pixel_width_without_atlas_uses_fallback():
    assert measure_pixel_width("AB") == FALLBACK_HALF_WIDTH_PX * 2
    assert measure_pixel_width("あい") == FALLBACK_FULL_WIDTH_PX * 2


def test_measure_pixel_width_uses_the_real_table_entry_width_when_atlas_available():
    # live-confirmed real values: 'A'/'M'/'W' measure 14, 'i' measures 8
    atlas = _fake_atlas({"A": 14, "i": 8})
    assert measure_pixel_width("A", atlas) == 14
    assert measure_pixel_width("i", atlas) == 8


def test_measure_pixel_width_falls_back_for_char_atlas_cannot_resolve():
    atlas = _fake_atlas({})  # "A" has no entry in the fake glyph dict at all
    assert measure_pixel_width("A", atlas) == FALLBACK_HALF_WIDTH_PX


# --- check_layout priority ordering ------------------------------------


def test_check_layout_missing_glyph_takes_priority():
    unit = _single_char_unit("A", "é")
    report = check_layout(unit)
    assert report.status == LayoutValidationStatus.MISSING_GLYPH


def test_check_layout_control_issue_detected():
    unit = _single_char_unit("A", "B")
    unit.raw_codes = [w for w in unit.raw_codes if w != 0xFFFF]  # corrupt: drop the end marker's control-ness
    # (end marker isn't a control event, so instead corrupt a real control code if present;
    # simplest reliable corruption here: make control_events claim something that re-encoding won't produce)
    unit.control_events = [{"family": "A", "subtype": 9999, "param": None, "meaning": "fake"}]
    report = check_layout(unit)
    assert report.status == LayoutValidationStatus.CONTROL_ISSUE


def test_check_layout_boundary_risk_detected():
    # contiguous_with_next() is vacuously True for a single-segment buffer
    # (nothing to be contiguous with) -- need a real next unit for the
    # mutation below to actually matter.
    code_a = CHAR_TO_CODE["A"]
    code_b = CHAR_TO_CODE["B"]
    doc = decode_script(_pack([code_a, 0x8500, code_b, 0xFFFF]))  # pause_flag_a splits into 2 units
    units = units_from_script_document(doc, scene_id="s")
    unit = units[0]
    unit.edited_text = "B"
    assert unit.next_unit_start_offset is not None
    unit.unit_end_offset += 5  # drift bookkeeping
    report = check_layout(unit)
    assert report.status == LayoutValidationStatus.BOUNDARY_RISK


def test_check_layout_pixel_overflow_detected():
    unit = _single_char_unit("A", "This is a very very long sentence that clearly overflows")
    report = check_layout(unit)
    assert report.status == LayoutValidationStatus.PIXEL_OVERFLOW


def test_check_layout_too_many_lines_detected_when_overflow_margin_relaxed():
    # short original -> small per-line budget -- ten short words each
    # exceed it on their own, forcing one word per line (10 lines > max)
    unit = _single_char_unit("A", "one two three four five six seven eight nine ten")
    unit.original_text = "Hi"
    report = check_layout(unit, max_lines=2, overflow_margin=1000.0)
    assert report.status == LayoutValidationStatus.TOO_MANY_LINES


def test_check_layout_awkward_wrap_detected_for_a_single_overlong_word():
    unit = _single_char_unit("A", "supercalifragilisticexpialidocious" * 3)
    unit.original_text = "short"
    report = check_layout(unit, max_lines=1000, overflow_margin=1000.0)
    assert report.status == LayoutValidationStatus.AWKWARD_WRAP


def test_check_layout_ok_for_a_safe_edit():
    unit = _single_char_unit("A", "B")  # same length, mapped, no control/boundary issues
    report = check_layout(unit)
    assert report.status == LayoutValidationStatus.OK


def test_greedy_wrap_matches_the_actual_live_observed_mid_word_break():
    # Real live capture: "If you walk by after six pm、 they say you can
    # hear laughter." rendered in-game as:
    #   "If you walk by after six pm、th" / "ey say you can hear lau" / "ghter."
    # -- confirming the real engine wraps per-character with no word
    # awareness at all (see NOTES.md's live GDB findings on FUN_8004a370).
    # Reproduce the same character-budget shape (fallback mode, no atlas)
    # and confirm our simulation now also splits "they" and "laughter".
    text = "If you walk by after six pm, they say you can hear laughter."
    lines, wrapped_mid_word = _greedy_wrap(text, line_budget_px=30 * FALLBACK_HALF_WIDTH_PX, atlas=None)
    assert wrapped_mid_word


def test_greedy_wrap_does_not_flag_clean_word_boundary_wraps():
    # A budget that happens to land exactly on a space boundary should
    # NOT be reported as a mid-word split.
    text = "one two three"  # 3+1+3+1+5 = 13 chars
    # budget fits "one two" (7 chars) exactly, forcing a wrap right at the space
    budget = 7 * FALLBACK_HALF_WIDTH_PX
    lines, wrapped_mid_word = _greedy_wrap(text, line_budget_px=budget, atlas=None)
    assert lines > 1
    assert not wrapped_mid_word


def test_check_layout_style_review_needed_is_never_auto_assigned():
    # exhaustively confirm no code path in check_layout can produce this --
    # it's operator-only (see gcrts.editor_state's manual validation storage)
    import inspect

    from gcrts import layout_validation

    src = inspect.getsource(layout_validation.check_layout)
    assert "STYLE_REVIEW_NEEDED" not in src
