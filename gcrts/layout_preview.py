"""Alternative Text Engine, Phase 3: layout preview data model.

This is the DATA an eventual software renderer (Phase 4's scope -- see
the master prompt's section 20) would draw from -- measured widths,
overflow flags, missing glyphs -- computed here with no drawing at all.
Keeping this a separate, earlier step than the actual renderer matches
the master prompt's own phase split ("Phase 3 -- ... preview data model"
vs "Phase 4 -- Software preview -- Render the text using the real glyph
atlas"): this module answers "would this plan fit and use only glyphs we
have," not "what does it look like."

Reuses gcrts.layout_validation.measure_pixel_width (the same real-glyph-
width measurement HOST_FITTED's own validation uses) and
gcrts.font_workbench.classify_char (the same glyph-coverage check
gcrts.font_workbench.audit_text uses) rather than re-implementing either.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from gcrts.editor_layout_plan import EditorLayoutPlan
from gcrts.font_workbench import classify_char
from gcrts.glyph_atlas import GlyphAtlas
from gcrts.layout_validation import MAX_VISIBLE_LINES, measure_pixel_width
from gcrts.text_fitting import MEASURED_MAX_WIDTH_PX


@dataclass
class LinePreview:
    index: int
    text: str
    x: int
    y: int
    measured_width_px: int
    budget_px: int
    overflows: bool
    missing_glyphs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "text": self.text,
            "x": self.x,
            "y": self.y,
            "measured_width_px": self.measured_width_px,
            "budget_px": self.budget_px,
            "overflows": self.overflows,
            "missing_glyphs": list(self.missing_glyphs),
        }


@dataclass
class LayoutPreview:
    unit_id: str
    lines: list[LinePreview] = field(default_factory=list)
    too_many_lines: bool = False

    @property
    def overflowing_line_indices(self) -> list[int]:
        return [line.index for line in self.lines if line.overflows]

    @property
    def missing_glyphs(self) -> list[str]:
        seen: list[str] = []
        for line in self.lines:
            for ch in line.missing_glyphs:
                if ch not in seen:
                    seen.append(ch)
        return seen

    @property
    def fits(self) -> bool:
        """True if nothing here would block or warrant a warning: no line
        overflows its own budget, the plan doesn't exceed MAX_VISIBLE_LINES,
        and every character has a known glyph."""
        return not self.too_many_lines and not self.overflowing_line_indices and not self.missing_glyphs

    def to_dict(self) -> dict:
        return {
            "unit_id": self.unit_id,
            "lines": [line.to_dict() for line in self.lines],
            "too_many_lines": self.too_many_lines,
            "fits": self.fits,
        }


def build_preview(plan: EditorLayoutPlan, atlas: GlyphAtlas | None = None) -> LayoutPreview:
    """Compute a LayoutPreview for `plan` -- no drawing, no emulator
    interaction, just measurement against the same real glyph-width table
    (when `atlas` is given) gcrts.layout_validation already uses."""
    line_previews: list[LinePreview] = []
    for i, line in enumerate(plan.lines):
        budget = line.max_width_px if line.max_width_px is not None else MEASURED_MAX_WIDTH_PX
        width = measure_pixel_width(line.text, atlas)
        missing = [ch for ch in line.text if classify_char(ch) == "unmapped"]
        line_previews.append(
            LinePreview(
                index=i,
                text=line.text,
                x=line.x,
                y=line.y,
                measured_width_px=width,
                budget_px=budget,
                overflows=width > budget,
                missing_glyphs=missing,
            )
        )

    return LayoutPreview(
        unit_id=plan.unit_id,
        lines=line_previews,
        too_many_lines=len(plan.lines) > MAX_VISIBLE_LINES,
    )
