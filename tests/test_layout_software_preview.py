from gcrts.editor_layout_plan import EditorLayoutPlan, LayoutAlignment, LayoutLine
from gcrts.font_extension import FONT_BACKGROUND_VALUE, FONT_INK_VALUE
from gcrts.glyph_atlas import GLYPH_HEIGHT, GLYPH_WIDTH, GlyphAtlas
from gcrts.glyph_char_map import CHAR_TO_CODE
from gcrts.layout_software_preview import BACKGROUND_RGB, INK_RGB, MARGIN, OVERFLOW_RGB, render_layout_plan
from gcrts.render_mode import RenderMode


def _fake_atlas(char_widths: dict[str, int], solid_ink_chars: set[str] = frozenset()) -> GlyphAtlas:
    """A deterministic fake atlas: solid_ink_chars decode to a glyph that's
    entirely FONT_INK_VALUE (a fully "drawn" 16x16 cell); everything else
    with a known width decodes to a glyph that's entirely
    FONT_BACKGROUND_VALUE (a blank cell). glyph_to_pixels is the REAL
    implementation -- it's a pure unpacking function with no game/live
    dependency, so there's no reason to fake it too."""
    entries = {CHAR_TO_CODE[ch]: (0, width) for ch, width in char_widths.items()}
    ink_codes = {CHAR_TO_CODE[ch] for ch in solid_ink_chars if ch in CHAR_TO_CODE}

    atlas = GlyphAtlas(exe_data=b"", text_addr=0, text_size=0)
    atlas.table_entry = lambda code: entries.get(code)

    def decode_glyph(code):
        if code not in entries:
            return None
        byte = 0x66 if code in ink_codes else 0x44  # both nibbles = ink or background value
        return bytes([byte]) * (GLYPH_WIDTH * GLYPH_HEIGHT // 2)

    atlas.decode_glyph = decode_glyph
    return atlas


def _plan(lines):
    return EditorLayoutPlan(
        unit_id="s_line_00", render_mode=RenderMode.CUSTOM_ENGINE, language="en", source_text="", edited_text="",
        lines=lines,
    )


def test_render_produces_an_image_sized_to_fit_all_lines():
    atlas = _fake_atlas({"A": 14})
    plan = _plan([LayoutLine("A", 0, 1, 10, 160, LayoutAlignment.LEFT, max_width_px=280)])
    image = render_layout_plan(plan, atlas)
    assert image.width >= 10 + 280 + MARGIN
    assert image.height >= 160 + GLYPH_HEIGHT + MARGIN


def test_render_draws_ink_pixels_for_a_solid_ink_glyph():
    atlas = _fake_atlas({"A": 14}, solid_ink_chars={"A"})
    plan = _plan([LayoutLine("A", 0, 1, 10, 160, LayoutAlignment.LEFT, max_width_px=280)])
    image = render_layout_plan(plan, atlas)
    # the glyph cell's interior (avoiding the border-drawn textbox outline)
    # should be pure ink color, since the fake glyph is solid FONT_INK_VALUE
    px = image.getpixel((MARGIN + 10 + 3, MARGIN + 160 + 3))
    assert px == INK_RGB


def test_render_leaves_background_for_a_blank_glyph():
    atlas = _fake_atlas({" ": 8})
    plan = _plan([LayoutLine(" ", 0, 1, 10, 160, LayoutAlignment.LEFT, max_width_px=280)])
    image = render_layout_plan(plan, atlas)
    px = image.getpixel((MARGIN + 10 + 3, MARGIN + 160 + 3))
    assert px == BACKGROUND_RGB


def test_render_marks_overflowing_line_with_the_overflow_color():
    atlas = _fake_atlas({"A": 14}, solid_ink_chars={"A"})
    # budget of 5px is far smaller than the measured 14px -- guaranteed overflow
    plan = _plan([LayoutLine("A", 0, 1, 10, 160, LayoutAlignment.LEFT, max_width_px=5)])
    image = render_layout_plan(plan, atlas)
    # top-left corner of the line's textbox-bounds rectangle
    px = image.getpixel((MARGIN + 10, MARGIN + 160))
    assert px == OVERFLOW_RGB


def test_render_marks_missing_glyph_distinctly():
    atlas = _fake_atlas({})  # "é" has no entry at all
    plan = _plan([LayoutLine("é", 0, 1, 10, 160, LayoutAlignment.LEFT, max_width_px=280)])
    image = render_layout_plan(plan, atlas)
    # the missing-glyph marker rectangle's top-left corner
    px = image.getpixel((MARGIN + 10, MARGIN + 160))
    from gcrts.layout_software_preview import MISSING_GLYPH_RGB

    assert px == MISSING_GLYPH_RGB


def test_render_center_alignment_shifts_the_start_position():
    atlas = _fake_atlas({"A": 14}, solid_ink_chars={"A"})
    plan = _plan([LayoutLine("A", 0, 1, 10, 160, LayoutAlignment.CENTER, max_width_px=280)])
    image = render_layout_plan(plan, atlas)
    # centered: start_x = 10 + (280-14)//2 = 10 + 133 = 143, well clear of the left edge
    px_left_edge = image.getpixel((MARGIN + 10 + 3, MARGIN + 160 + 3))
    assert px_left_edge == BACKGROUND_RGB  # nothing drawn at the un-centered left position
    px_centered = image.getpixel((MARGIN + 143 + 3, MARGIN + 160 + 3))
    assert px_centered == INK_RGB


def test_render_empty_plan_returns_a_small_valid_image():
    atlas = _fake_atlas({})
    plan = _plan([])
    image = render_layout_plan(plan, atlas)
    assert image.width > 0
    assert image.height > 0


def test_render_to_file_writes_a_real_png(tmp_path):
    from gcrts.layout_software_preview import render_layout_plan_to_file

    atlas = _fake_atlas({"A": 14}, solid_ink_chars={"A"})
    plan = _plan([LayoutLine("A", 0, 1, 10, 160, LayoutAlignment.LEFT, max_width_px=280)])
    path = tmp_path / "preview.png"
    render_layout_plan_to_file(plan, atlas, str(path))
    assert path.exists()
    assert path.stat().st_size > 0
