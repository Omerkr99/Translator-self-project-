"""Alternative Text Engine, Phase 3: automatic EditorLayoutPlan construction.

Per the master prompt's section 9 ("Do not implement word segmentation
only in MIPS unless there is a proven need... The host-side layout planner
must remain the primary source of word segmentation"), this builds a
starting CUSTOM_ENGINE plan by reusing gcrts.text_fitting.fit_text_to_lines
-- the same word-safe line grouping HOST_FITTED already relies on -- rather
than re-implementing tokenization a second time. What's new here is turning
those grouped line STRINGS into explicit LayoutLine records with real x/y/
character-index positions, since fit_text_to_lines only groups words; it
has no concept of assigning each line a screen position (that's HOST_FITTED's
job done implicitly via padding, and CUSTOM_ENGINE's job done explicitly
here).

`base_x=10` reuses the one confirmed constant from the live wrap-algorithm
investigation (gcrts.layout_validation's module docstring). `base_y` and
`line_height` are NOT confirmed game constants -- no live Y-position
investigation has been done for CUSTOM_ENGINE mode yet, since nothing
consumes these values in-game today. They are reasonable, operator-
adjustable starting points, documented as such rather than presented as
measured facts.
"""
from __future__ import annotations

from gcrts.editor_layout_plan import EditorLayoutPlan, LayoutAlignment, LayoutLine, LayoutMode
from gcrts.glyph_atlas import GlyphAtlas
from gcrts.render_mode import RenderMode
from gcrts.script_unit import ScriptUnit
from gcrts.text_fitting import MEASURED_MAX_WIDTH_PX, fit_text_to_lines

# Not confirmed from live investigation (see module docstring) -- starting
# defaults only, freely overridden per call or by manual editing afterward.
DEFAULT_BASE_Y = 0
DEFAULT_LINE_HEIGHT = 16


def build_auto_layout_plan(
    unit: ScriptUnit,
    max_width_px: int | None = None,
    base_x: int = 10,
    base_y: int = DEFAULT_BASE_Y,
    line_height: int = DEFAULT_LINE_HEIGHT,
    alignment: LayoutAlignment = LayoutAlignment.LEFT,
    atlas: GlyphAtlas | None = None,
) -> EditorLayoutPlan:
    """Build a starting CUSTOM_ENGINE plan from `unit.edited_text`, grouping
    words into lines via gcrts.text_fitting.fit_text_to_lines (word-safe,
    same logic HOST_FITTED uses) and assigning each line a sequential
    (base_x, base_y + i*line_height) position. Character indices are
    computed by walking `unit.edited_text` in order -- fit_text_to_lines
    never adds, removes, or reorders words or spaces, so each line's
    length plus one separating space exactly accounts for the next
    line's start, with no text lost or duplicated between lines."""
    budget = max_width_px if max_width_px is not None else MEASURED_MAX_WIDTH_PX
    line_texts = fit_text_to_lines(unit.edited_text, budget, atlas)

    lines: list[LayoutLine] = []
    cursor = 0
    for i, text in enumerate(line_texts):
        start = cursor
        end = start + len(text)
        lines.append(
            LayoutLine(
                text=text,
                start_character_index=start,
                end_character_index=end,
                x=base_x,
                y=base_y + i * line_height,
                alignment=alignment,
                max_width_px=budget,
            )
        )
        cursor = end + 1  # +1 skips the single space that separated this line from the next in edited_text

    return EditorLayoutPlan(
        unit_id=unit.id,
        render_mode=RenderMode.CUSTOM_ENGINE,
        language="en",
        source_text=unit.original_text,
        edited_text=unit.edited_text,
        lines=lines,
        layout_mode=LayoutMode.AUTO_WORD_WRAP,
        control_events=list(unit.control_events),
    )
