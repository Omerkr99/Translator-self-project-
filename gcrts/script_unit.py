"""Live Text Editor Workbench, Phase 1: script unit model with explicit
boundary tracking.

This normalizes what the already-validated pipeline (gcrts.script_decoder,
gcrts.editable_script, gcrts.glyph_char_map, gcrts.live_extract) already
knows about one translatable segment into a single editor-facing
structure. It is a normalization/adapter layer, not a new decode/encode
implementation -- decoding, segmentation, and glyph lookup are all still
done by the existing modules; this just packages their output uniformly.

Boundary model (the reason this phase exists): every unit knows exactly
which word-offset range in its source buffer it owns --
`unit_start_offset` (inclusive) through `unit_end_offset` (exclusive) --
and `next_unit_start_offset`, the start offset of whatever comes right
after it (None if this is the last unit in the buffer). For every unit
but the last, `unit_end_offset == next_unit_start_offset` is a real
invariant: gcrts.editable_script.to_editable's segmentation is exhaustive
and gapless, so this always holds for units built via
units_from_editable_script/units_from_script_document. `contiguous_with()`
lets a caller (the boundary-validation phase, or a test) check this
rather than assume it. This is deliberately just the DATA -- deciding
what to warn about when an edit risks the boundary is a later phase's
job, not this one's.

`layout_constraints` here is still only the descriptive stats
`gcrts.editable_script` already computes per segment (character count,
which control-code meanings appear, whether any character code is
unmapped) -- it is NOT yet the game's actual rendering limits (max
characters per line, max lines per box). Those aren't known yet; a later
workbench phase is specifically about discovering them through layout
inspection. Don't conflate the two meanings of "layout constraints".

`text_type` defaults to "dialogue" because that's the only render path
this project has decoded and live-validated so far (see NOTES.md's
Phase 5/6 confirmations). No text-type classifier exists yet -- that is
future workbench scope, not implemented here.

Alternative Text Engine, Phase 1 addendum: `render_mode`, `layout_plan`,
`runtime_patch_status`, and `preview_status` were added below with
defaults so every existing construction call site (unit_from_segment,
every test's hand-built ScriptUnit) keeps working unchanged -- see
BASELINE_REPORT.md's "components that must remain unchanged" section.
`render_mode` defaults to HOST_FITTED, matching this project's actual
proven-reliable default path; `layout_plan` defaults to None since no
CUSTOM_ENGINE plan exists until an operator explicitly builds one.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from gcrts.editable_script import EditableScript, ScriptSegment, to_editable
from gcrts.editor_layout_plan import EditorLayoutPlan
from gcrts.glyph_char_map import char_for_code
from gcrts.render_mode import RenderMode, RuntimePatchState
from gcrts.script_decoder import CodeKind, ScriptDocument


@dataclass
class ScriptUnit:
    id: str
    source: str  # "live_ram" today; "disk" is future scope, not implemented
    ram_address: int | None  # absolute RAM address of this unit's first word, if known
    unit_start_offset: int  # word offset (within the source buffer) this unit starts at
    unit_end_offset: int  # word offset one-past this unit's last word (exclusive)
    next_unit_start_offset: int | None  # word offset the next unit starts at, or None if this is the last unit
    raw_codes: list[int]  # flat word stream (control params inline) -- encode-ready
    control_events: list[dict]
    original_text: str
    edited_text: str
    layout_constraints: dict
    text_type: str
    glyphs_used: list[int]
    missing_glyphs: list[int]
    render_mode: RenderMode = RenderMode.HOST_FITTED
    layout_plan: EditorLayoutPlan | None = None
    runtime_patch_status: RuntimePatchState = field(default_factory=RuntimePatchState)
    preview_status: str = "unknown"

    @property
    def is_modified(self) -> bool:
        return self.edited_text != self.original_text

    def contiguous_with_next(self) -> bool:
        """True if this unit's end offset exactly meets the next unit's
        start offset -- i.e. no gap and no overlap between them. Always
        True for units built by this module's own extraction functions
        (segmentation is gapless by construction); meaningful to check
        again after anything that might have altered a unit's boundaries.
        Vacuously True if this is the last unit (nothing to be contiguous
        with)."""
        if self.next_unit_start_offset is None:
            return True
        return self.unit_end_offset == self.next_unit_start_offset

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "ram_address": f"{self.ram_address:#x}" if self.ram_address is not None else None,
            "unit_start_offset": self.unit_start_offset,
            "unit_end_offset": self.unit_end_offset,
            "next_unit_start_offset": self.next_unit_start_offset,
            "raw_codes": self.raw_codes,
            "control_events": self.control_events,
            "original_text": self.original_text,
            "edited_text": self.edited_text,
            "layout_constraints": self.layout_constraints,
            "text_type": self.text_type,
            "glyphs_used": self.glyphs_used,
            "missing_glyphs": self.missing_glyphs,
            "render_mode": self.render_mode.value,
            "layout_plan": self.layout_plan.to_dict() if self.layout_plan is not None else None,
            "runtime_patch_status": self.runtime_patch_status.to_dict(),
            "preview_status": self.preview_status,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ScriptUnit":
        """Inverse of to_dict() -- used by the editor session save/load
        (gcrts.editor_state) to round-trip a unit exactly, including any
        edits already made to `edited_text`.

        The four Alternative-Text-Engine fields (render_mode, layout_plan,
        runtime_patch_status, preview_status) all use `.get()` with the
        same defaults the dataclass itself uses, so a session file saved
        before these fields existed loads exactly as if every unit had
        always been HOST_FITTED with no layout plan -- the correct
        backward-compatible behavior per BASELINE_REPORT.md."""
        ram_address = int(d["ram_address"], 16) if d["ram_address"] is not None else None
        layout_plan_dict = d.get("layout_plan")
        return cls(
            id=d["id"],
            source=d["source"],
            ram_address=ram_address,
            unit_start_offset=d["unit_start_offset"],
            unit_end_offset=d["unit_end_offset"],
            next_unit_start_offset=d["next_unit_start_offset"],
            raw_codes=list(d["raw_codes"]),
            control_events=list(d["control_events"]),
            original_text=d["original_text"],
            edited_text=d["edited_text"],
            layout_constraints=dict(d["layout_constraints"]),
            text_type=d["text_type"],
            glyphs_used=list(d["glyphs_used"]),
            missing_glyphs=list(d["missing_glyphs"]),
            render_mode=RenderMode(d.get("render_mode", RenderMode.HOST_FITTED.value)),
            layout_plan=EditorLayoutPlan.from_dict(layout_plan_dict) if layout_plan_dict is not None else None,
            runtime_patch_status=RuntimePatchState.from_dict(d.get("runtime_patch_status", {})),
            preview_status=d.get("preview_status", "unknown"),
        )


def _raw_codes_for(segment: ScriptSegment) -> list[int]:
    words: list[int] = []
    for c in segment.codes:
        words.append(c.raw)
        if c.param is not None:
            words.append(c.param)
    return words


def _glyph_usage_for(segment: ScriptSegment) -> tuple[list[int], list[int]]:
    used: list[int] = []
    missing: list[int] = []
    for c in segment.codes:
        if c.kind != CodeKind.CHARACTER:
            continue
        used.append(c.raw)
        if char_for_code(c.raw) is None:
            missing.append(c.raw)
    return used, missing


def _unit_start_offset(segment: ScriptSegment) -> int:
    return segment.codes[0].offset


def _unit_end_offset(segment: ScriptSegment) -> int:
    last = segment.codes[-1]
    return last.offset + last.words_consumed


def unit_from_segment(
    segment: ScriptSegment,
    index: int,
    scene_id: str,
    source: str = "live_ram",
    base_ram_address: int | None = None,
    text_type: str = "dialogue",
    next_unit_start_offset: int | None = None,
) -> ScriptUnit:
    """Build one ScriptUnit from an already-decoded ScriptSegment
    (gcrts.editable_script.to_editable output). `base_ram_address` is the
    address the underlying buffer capture started at (e.g.
    gcrts.live_extract.SCRIPT_BUF_ADDR); the unit's own address is derived
    from its own start offset within that buffer. `next_unit_start_offset`
    should be the following segment's start offset (get it from
    units_from_editable_script rather than computing it ad hoc, so it's
    guaranteed consistent with how segmentation actually ordered things)."""
    unit_start_offset = _unit_start_offset(segment)
    unit_end_offset = _unit_end_offset(segment)
    ram_address = base_ram_address + unit_start_offset * 2 if base_ram_address is not None else None
    used, missing = _glyph_usage_for(segment)
    return ScriptUnit(
        id=f"{scene_id}_line_{index:02d}",
        source=source,
        ram_address=ram_address,
        unit_start_offset=unit_start_offset,
        unit_end_offset=unit_end_offset,
        next_unit_start_offset=next_unit_start_offset,
        raw_codes=_raw_codes_for(segment),
        control_events=[c.to_dict() for c in segment.codes if c.kind == CodeKind.CONTROL],
        original_text=segment.original,
        edited_text=segment.translated,
        layout_constraints=dict(segment.layout_constraints),
        text_type=text_type,
        glyphs_used=used,
        missing_glyphs=missing,
    )


def units_from_editable_script(
    script: EditableScript,
    scene_id: str,
    source: str = "live_ram",
    base_ram_address: int | None = None,
    text_type: str = "dialogue",
) -> list[ScriptUnit]:
    segments = script.segments
    units = []
    for i, seg in enumerate(segments):
        next_start = _unit_start_offset(segments[i + 1]) if i + 1 < len(segments) else None
        units.append(unit_from_segment(seg, i, scene_id, source, base_ram_address, text_type, next_start))
    return units


def units_from_script_document(
    doc: ScriptDocument,
    scene_id: str,
    source: str = "live_ram",
    base_ram_address: int | None = None,
    text_type: str = "dialogue",
) -> list[ScriptUnit]:
    """Convenience wrapper: segment a raw ScriptDocument (gcrts.script_decoder
    output) via gcrts.editable_script.to_editable and normalize it in one
    call."""
    return units_from_editable_script(to_editable(doc), scene_id, source, base_ram_address, text_type)


def extract_live_script_units(
    scene_id: str, host: str = "127.0.0.1", port: int = 3333, text_type: str = "dialogue"
) -> list[ScriptUnit]:
    """Capture the current live script buffer and normalize it into
    ScriptUnits. Thin wrapper over gcrts.live_extract + gcrts.editable_script
    -- does not reimplement decoding or capture logic."""
    from gcrts.live_extract import SCRIPT_BUF_ADDR, extract_and_decode

    _raw, doc = extract_and_decode(host, port)
    return units_from_script_document(
        doc, scene_id, source="live_ram", base_ram_address=SCRIPT_BUF_ADDR, text_type=text_type
    )
