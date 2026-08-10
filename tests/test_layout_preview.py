from gcrts.editor_layout_plan import EditorLayoutPlan, LayoutAlignment, LayoutLine
from gcrts.layout_preview import build_preview
from gcrts.layout_validation import FALLBACK_HALF_WIDTH_PX, MAX_VISIBLE_LINES
from gcrts.render_mode import RenderMode


def _plan(lines):
    return EditorLayoutPlan(
        unit_id="s_line_00", render_mode=RenderMode.CUSTOM_ENGINE, language="en", source_text="", edited_text="",
        lines=lines,
    )


def test_build_preview_measures_each_line_and_reports_fits_true_when_clean():
    line_width = len("hello") * FALLBACK_HALF_WIDTH_PX
    plan = _plan([LayoutLine("hello", 0, 5, 10, 160, LayoutAlignment.LEFT, max_width_px=line_width + 10)])
    preview = build_preview(plan)
    assert preview.fits is True
    assert preview.lines[0].measured_width_px == line_width
    assert preview.lines[0].overflows is False


def test_build_preview_flags_overflow_when_line_exceeds_its_own_budget():
    line_width = len("hello world") * FALLBACK_HALF_WIDTH_PX
    plan = _plan([LayoutLine("hello world", 0, 11, 10, 160, LayoutAlignment.LEFT, max_width_px=line_width - 1)])
    preview = build_preview(plan)
    assert preview.lines[0].overflows is True
    assert preview.fits is False
    assert 0 in preview.overflowing_line_indices


def test_build_preview_flags_too_many_lines():
    lines = [LayoutLine(f"line {i}", 0, 6, 10, 160 + i * 16, LayoutAlignment.LEFT) for i in range(MAX_VISIBLE_LINES + 1)]
    preview = build_preview(_plan(lines))
    assert preview.too_many_lines is True
    assert preview.fits is False


def test_build_preview_collects_missing_glyphs_across_lines():
    plan = _plan(
        [
            LayoutLine("café", 0, 4, 10, 160, LayoutAlignment.LEFT),
            LayoutLine("naïve", 5, 10, 10, 176, LayoutAlignment.LEFT),
        ]
    )
    preview = build_preview(plan)
    assert "é" in preview.missing_glyphs
    assert "ï" in preview.missing_glyphs
    assert preview.fits is False


def test_build_preview_uses_lines_own_budget_default_when_none_set():
    from gcrts.text_fitting import MEASURED_MAX_WIDTH_PX

    plan = _plan([LayoutLine("hi", 0, 2, 10, 160, LayoutAlignment.LEFT, max_width_px=None)])
    preview = build_preview(plan)
    assert preview.lines[0].budget_px == MEASURED_MAX_WIDTH_PX


def test_layout_preview_to_dict_roundtrips_the_summary():
    plan = _plan([LayoutLine("hi", 0, 2, 10, 160, LayoutAlignment.LEFT, max_width_px=100)])
    preview = build_preview(plan)
    d = preview.to_dict()
    assert d["unit_id"] == "s_line_00"
    assert d["fits"] is True
    assert d["lines"][0]["text"] == "hi"
