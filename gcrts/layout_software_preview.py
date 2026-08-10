"""Alternative Text Engine, Phase 4: software preview renderer.

Actually draws pixels. `gcrts.layout_preview` (Phase 3) measures a plan
without drawing anything; this module consumes that measurement plus the
REAL glyph bitmaps (`gcrts.glyph_atlas.GlyphAtlas.decode_glyph`/
`glyph_to_pixels`, reverse-engineered from FUN_8004aa08 -- see
glyph_atlas.py's own module docstring) to produce a real image. Per the
master prompt's section 20: "The preview is not a substitute for live
testing. It is a fast validation layer" -- this exists to catch obvious
problems (overflow, missing glyphs, misalignment) in seconds, not to
replace watching the actual emulator render the actual game.

Reuses the CONFIRMED palette convention from gcrts.font_extension
(`FONT_BACKGROUND_VALUE = 4`, `FONT_INK_VALUE = 6` -- live-confirmed by
inspecting a real glyph's decompressed pixel-value histogram, see
NOTES.md's "Phase 6 CONFIRMED LIVE" section) rather than assuming the
naive 0=background/15=ink convention, which live testing already showed
renders as a solid opaque block, not transparent text. Values strictly
between 4 and 6 (or beyond 6) are treated as a linear blend toward ink --
a small handful of antialiasing edge pixels exist in real glyph data
(per font_extension.py's own docstring) and only the two endpoints are
actually confirmed, so this blend is a reasonable rendering choice, not
a claim about the exact intended antialiasing ramp.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

from gcrts.editor_layout_plan import EditorLayoutPlan, LayoutAlignment, LayoutLine
from gcrts.font_extension import FONT_BACKGROUND_VALUE, FONT_INK_VALUE
from gcrts.glyph_atlas import GLYPH_HEIGHT, GlyphAtlas
from gcrts.glyph_char_map import code_for_char
from gcrts.layout_preview import LayoutPreview, build_preview

BACKGROUND_RGB = (20, 24, 32)
INK_RGB = (232, 230, 220)
TEXTBOX_BOUNDS_RGB = (100, 140, 220)
BASELINE_RGB = (90, 100, 115)
OVERFLOW_RGB = (220, 90, 80)
MISSING_GLYPH_RGB = (220, 90, 80)

MARGIN = 8


def _char_advance_width(ch: str, atlas: GlyphAtlas) -> int:
    """The real advance width for one character -- same source
    (`atlas.table_entry(code)[1]`) gcrts.layout_validation.measure_pixel_width
    already uses, read per-character here since rendering needs to place
    each glyph individually, not just sum a total."""
    code = code_for_char(ch)
    if code is None:
        return 0
    entry = atlas.table_entry(code)
    if entry is None:
        return 0
    return entry[1]


def _line_start_x(line: LayoutLine, measured_width_px: int) -> int:
    """Where this line's first glyph actually starts, given its alignment
    -- the same math gcrts.text_fitting.center_line uses conceptually,
    applied directly at render time since here we have explicit position
    control rather than needing to insert padding spaces."""
    budget = line.max_width_px if line.max_width_px is not None else measured_width_px
    if line.alignment == LayoutAlignment.CENTER:
        return line.x + max(0, (budget - measured_width_px) // 2)
    if line.alignment == LayoutAlignment.RIGHT:
        return line.x + max(0, budget - measured_width_px)
    return line.x


def _blend(value: int) -> tuple[int, int, int]:
    span = FONT_INK_VALUE - FONT_BACKGROUND_VALUE
    t = (value - FONT_BACKGROUND_VALUE) / span if span else 1.0
    t = max(0.0, min(1.0, t))
    return tuple(int(b + (i - b) * t) for b, i in zip(BACKGROUND_RGB, INK_RGB))


def render_layout_plan(
    plan: EditorLayoutPlan, atlas: GlyphAtlas, preview: LayoutPreview | None = None
) -> Image.Image:
    """Render `plan` into a real RGB image using `atlas`'s actual glyph
    bitmaps. `preview` (from gcrts.layout_preview.build_preview) is
    computed automatically if not given, to know which lines overflow and
    which characters are missing so they can be flagged visually rather
    than silently skipped."""
    if preview is None:
        preview = build_preview(plan, atlas)

    if not plan.lines:
        return Image.new("RGB", (2 * MARGIN + 16, 2 * MARGIN + GLYPH_HEIGHT), BACKGROUND_RGB)

    max_x = max(line.x + (line.max_width_px or 0) for line in plan.lines)
    max_y = max(line.y for line in plan.lines) + GLYPH_HEIGHT
    canvas = Image.new("RGB", (max_x + MARGIN * 2, max_y + MARGIN * 2), BACKGROUND_RGB)
    draw = ImageDraw.Draw(canvas)

    for line, line_preview in zip(plan.lines, preview.lines):
        ox, oy = MARGIN + line.x, MARGIN + line.y
        budget = line.max_width_px if line.max_width_px is not None else line_preview.measured_width_px

        # Draw glyphs FIRST, bounds/baseline/missing-glyph markers AFTER --
        # so those indicators are always visible on top of the ink, never
        # obscured by a glyph that happens to cover the same corner (a
        # real bug caught by this module's own test suite: an overflow
        # outline at a line's top-left corner was invisible whenever a
        # solid glyph was drawn there afterward).
        cursor_x = MARGIN + _line_start_x(line, line_preview.measured_width_px)
        missing_glyph_spans: list[tuple[int, int]] = []
        for ch in line.text:
            width_px = _char_advance_width(ch, atlas)
            code = code_for_char(ch)
            glyph_bytes = atlas.decode_glyph(code) if code is not None else None

            if glyph_bytes is not None:
                pixels = atlas.glyph_to_pixels(glyph_bytes)
                for gy, row in enumerate(pixels):
                    for gx, value in enumerate(row):
                        if value == FONT_BACKGROUND_VALUE:
                            continue
                        px, py = cursor_x + gx, oy + gy
                        if 0 <= px < canvas.width and 0 <= py < canvas.height:
                            canvas.putpixel((px, py), _blend(value))
            else:
                # no known glyph -- remember to draw a visible marker
                # instead of silently leaving blank space, matching the
                # master prompt's "no memory/behavior assumed safe without
                # evidence" spirit applied to missing glyphs: never
                # pretend nothing is wrong.
                missing_glyph_spans.append((cursor_x, cursor_x + max(width_px, 4)))
            cursor_x += width_px

        # textbox bounds for this line -- red if it overflows its own budget
        draw.rectangle(
            [ox, oy, ox + budget, oy + GLYPH_HEIGHT],
            outline=OVERFLOW_RGB if line_preview.overflows else TEXTBOX_BOUNDS_RGB,
        )
        # baseline
        draw.line([ox, oy + GLYPH_HEIGHT, ox + budget, oy + GLYPH_HEIGHT], fill=BASELINE_RGB)
        for start_x, end_x in missing_glyph_spans:
            draw.rectangle([start_x, oy, end_x, oy + GLYPH_HEIGHT], outline=MISSING_GLYPH_RGB)

    return canvas


def render_layout_plan_to_file(
    plan: EditorLayoutPlan, atlas: GlyphAtlas, path: str, preview: LayoutPreview | None = None
) -> None:
    image = render_layout_plan(plan, atlas, preview)
    image.save(path)
