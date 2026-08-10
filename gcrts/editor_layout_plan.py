"""Alternative Text Engine, Phase 1: the explicit layout-plan data model.

This is the data model only. Nothing here talks to the emulator, computes
a real layout automatically, or changes what gets injected -- that is
later-phase scope (Phase 2's binary descriptor, Phase 3's editor
integration, Phase 4's software preview). Phase 1's job is exactly what
the master prompt's section 6 and section 9 ask for: a concrete
`EditorLayoutPlan` a ScriptUnit can hold, with explicit per-line
placement, alignment, and validation-summary fields, plus the layout-mode
vocabulary those lines are described in terms of.

Why this doesn't reuse gcrts.layout_validation.LayoutReport/
LayoutValidationStatus: those describe the *result of checking* a unit's
current edited_text against the game's real (word-blind) wrap engine --
a single highest-priority status out of 8. This module describes the
editor's *own intended* layout -- explicit lines, positions, and a
multi-flag validation summary -- which is a different shape of
information entirely (an EditorLayoutPlan is input to a future custom
renderer; a LayoutReport is a verdict on HOST_FITTED's padding output).
Conflating the two would make neither model clean.

`start_character_index`/`end_character_index` on LayoutLine index into
`EditorLayoutPlan.edited_text` (the same string ScriptUnit.edited_text
would hold), not into the encoded word stream -- consistent with how
gcrts.control_position_risk already projects control-code positions as
character indices into edited_text.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from gcrts.render_mode import RenderMode

SCHEMA_VERSION = 1


class LayoutAlignment(Enum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class LayoutMode(Enum):
    """How a plan's `lines` were produced -- required minimum per the
    master prompt's section 9; the remaining modes it lists
    (SINGLE_LINE, CENTER_BLOCK, RIGHT_ALIGN) are included too since they
    cost nothing to represent, but only the first four have any producer
    implemented anywhere in this project yet (gcrts.text_fitting's
    HOST_FITTED logic, adapted case-by-case as CUSTOM_ENGINE plans start
    getting built in a later phase)."""

    AUTO_WORD_WRAP = "auto_word_wrap"
    MANUAL_LINES = "manual_lines"
    SINGLE_LINE = "single_line"
    CENTER_EACH_LINE = "center_each_line"
    CENTER_BLOCK = "center_block"
    LEFT_ALIGN = "left_align"
    RIGHT_ALIGN = "right_align"


class PageTransition(Enum):
    WAIT_FOR_INPUT = "wait_for_input"
    AUTO_CONTINUE = "auto_continue"
    NONE = "none"


@dataclass
class LayoutLine:
    text: str
    start_character_index: int
    end_character_index: int
    x: int
    y: int
    alignment: LayoutAlignment = LayoutAlignment.LEFT
    max_width_px: int | None = None
    measured_width_px: int | None = None

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "start_character_index": self.start_character_index,
            "end_character_index": self.end_character_index,
            "x": self.x,
            "y": self.y,
            "alignment": self.alignment.value,
            "max_width_px": self.max_width_px,
            "measured_width_px": self.measured_width_px,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LayoutLine":
        return cls(
            text=d["text"],
            start_character_index=d["start_character_index"],
            end_character_index=d["end_character_index"],
            x=d["x"],
            y=d["y"],
            alignment=LayoutAlignment(d.get("alignment", "left")),
            max_width_px=d.get("max_width_px"),
            measured_width_px=d.get("measured_width_px"),
        )


@dataclass
class LayoutPlanValidation:
    """A multi-flag summary, distinct from LayoutValidationStatus's single
    highest-priority verdict (see module docstring) -- an EditorLayoutPlan
    can be simultaneously missing a glyph AND overflowing, and a later
    phase's validator will want to report both, not just whichever this
    project's existing priority order picks first."""

    missing_glyphs: list[str] = field(default_factory=list)
    pixel_overflow: bool = False
    too_many_lines: bool = False
    boundary_risk: bool = False

    @property
    def ok(self) -> bool:
        return not self.missing_glyphs and not self.pixel_overflow and not self.too_many_lines and not self.boundary_risk

    def to_dict(self) -> dict:
        return {
            "missing_glyphs": list(self.missing_glyphs),
            "pixel_overflow": self.pixel_overflow,
            "too_many_lines": self.too_many_lines,
            "boundary_risk": self.boundary_risk,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LayoutPlanValidation":
        return cls(
            missing_glyphs=list(d.get("missing_glyphs", [])),
            pixel_overflow=bool(d.get("pixel_overflow", False)),
            too_many_lines=bool(d.get("too_many_lines", False)),
            boundary_risk=bool(d.get("boundary_risk", False)),
        )


@dataclass
class EditorLayoutPlan:
    """Attached to a ScriptUnit (via its new `layout_plan` field -- see
    gcrts.script_unit's Phase 1 changes) when render_mode is CUSTOM_ENGINE,
    or kept around as a preview/draft even under HOST_FITTED/ORIGINAL.
    `unit_id` duplicates the owning ScriptUnit's id rather than holding a
    live reference, matching how gcrts.editor_state already keeps units in
    a flat list addressed by id -- this stays trivially JSON-serializable
    and avoids a circular reference between the two models."""

    unit_id: str
    render_mode: RenderMode
    language: str
    source_text: str
    edited_text: str
    lines: list[LayoutLine] = field(default_factory=list)
    layout_mode: LayoutMode = LayoutMode.AUTO_WORD_WRAP
    paragraph_end: bool = True
    page_transition: PageTransition = PageTransition.WAIT_FOR_INPUT
    control_events: list[dict] = field(default_factory=list)
    validation: LayoutPlanValidation = field(default_factory=LayoutPlanValidation)

    # --- Phase 3: manual line editing ---------------------------------
    # These mutate `self.lines` in place and return nothing, matching
    # gcrts.editor_state's own mutation style (e.g. EditorState.edit()) --
    # an operator-facing CLI command calls one of these, then re-reads
    # `self.lines` to show the result, rather than threading a return
    # value through.

    def add_line(self, line: LayoutLine, index: int | None = None) -> None:
        """Insert `line` at `index` (default: append at the end)."""
        if index is None:
            self.lines.append(line)
        else:
            self.lines.insert(index, line)

    def remove_line(self, index: int) -> None:
        if not (0 <= index < len(self.lines)):
            raise IndexError(f"line index {index} out of range (plan has {len(self.lines)} lines)")
        del self.lines[index]

    def update_line(
        self,
        index: int,
        text: str | None = None,
        x: int | None = None,
        y: int | None = None,
        alignment: LayoutAlignment | None = None,
    ) -> None:
        """Update only the fields explicitly given; leaves the rest of the
        line -- including start/end_character_index, which a text change
        does NOT automatically recompute here (that's the auto-planner's
        job in gcrts.layout_plan_builder, not this low-level editor)."""
        if not (0 <= index < len(self.lines)):
            raise IndexError(f"line index {index} out of range (plan has {len(self.lines)} lines)")
        line = self.lines[index]
        if text is not None:
            line.text = text
        if x is not None:
            line.x = x
        if y is not None:
            line.y = y
        if alignment is not None:
            line.alignment = alignment

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "unit_id": self.unit_id,
            "render_mode": self.render_mode.value,
            "language": self.language,
            "source_text": self.source_text,
            "edited_text": self.edited_text,
            "lines": [line.to_dict() for line in self.lines],
            "layout_mode": self.layout_mode.value,
            "paragraph_end": self.paragraph_end,
            "page_transition": self.page_transition.value,
            "control_events": list(self.control_events),
            "validation": self.validation.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EditorLayoutPlan":
        """Tolerant of a dict missing any field this version didn't have
        yet -- schema_version itself is read but not currently branched
        on, since there has only ever been version 1; a future version
        bump should add a real migration step here rather than assume
        the shape never changes again."""
        return cls(
            unit_id=d["unit_id"],
            render_mode=RenderMode(d.get("render_mode", RenderMode.HOST_FITTED.value)),
            language=d.get("language", "en"),
            source_text=d.get("source_text", ""),
            edited_text=d.get("edited_text", ""),
            lines=[LayoutLine.from_dict(line) for line in d.get("lines", [])],
            layout_mode=LayoutMode(d.get("layout_mode", LayoutMode.AUTO_WORD_WRAP.value)),
            paragraph_end=bool(d.get("paragraph_end", True)),
            page_transition=PageTransition(d.get("page_transition", PageTransition.WAIT_FOR_INPUT.value)),
            control_events=list(d.get("control_events", [])),
            validation=LayoutPlanValidation.from_dict(d.get("validation", {})),
        )
