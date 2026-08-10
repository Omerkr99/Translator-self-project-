"""Editable script format: the JSON layer between a decoded ScriptDocument
(gcrts/script_decoder.py) and a human translator.

Per the pipeline's own rules ("never assume text encoding", "always
preserve original control codes", "never break pointer structure"), this
module does NOT interpret or discard any control code -- every ScriptCode
from the decoded buffer is preserved verbatim, in its original order,
inside a segment's `codes` list, so the re-encoding stage (Phase 4) can
reconstruct an exact byte stream, substituting only the character runs a
translator actually edited.

Segmentation heuristic (NOT confirmed from the decompile -- treat as
provisional and revise if it turns out wrong): a new segment starts right
after a `pause_flag_a` (family A, subtype 0x0500) or `pause_flag_b`
(family A, subtype 0x0600) control code, since those are the closest
candidates found so far for a textbox/page-advance boundary. This choice
only affects how the JSON is chunked for editing convenience -- it has
zero effect on re-encoding correctness, since every code (including the
pause codes themselves) is still stored and replayed exactly regardless of
where segment boundaries fall.

Character codes with no entry in gcrts.glyph_char_map (either genuinely
unmapped, or part of the per-scene dynamic kanji cache -- see that
module's docstring) are rendered as a `<?0xNNNN>` placeholder in
`original`/`translated` rather than silently dropped or guessed at.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from gcrts.glyph_char_map import char_for_code
from gcrts.script_decoder import CodeKind, ControlFamily, ScriptCode, ScriptDocument

SEGMENT_BREAK_SUBTYPES = {0x0500, 0x0600}  # pause_flag_a / pause_flag_b, family A


def _display_char(code: ScriptCode) -> str:
    ch = char_for_code(code.raw)
    if ch is not None:
        return ch
    return f"<?{code.raw:#06x}>"


@dataclass
class ScriptSegment:
    codes: list[ScriptCode]
    original: str
    translated: str
    layout_constraints: dict

    def to_dict(self) -> dict:
        return {
            "original": self.original,
            "translated": self.translated,
            "codes": [c.to_dict() for c in self.codes],
            "layout_constraints": self.layout_constraints,
        }


@dataclass
class EditableScript:
    segments: list[ScriptSegment] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"segments": [s.to_dict() for s in self.segments]}

    def to_json(self, **kwargs) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, **kwargs)


def _layout_constraints_for(codes: list[ScriptCode]) -> dict:
    char_count = sum(1 for c in codes if c.kind == CodeKind.CHARACTER)
    control_meanings = sorted(
        {c.meaning for c in codes if c.kind == CodeKind.CONTROL and c.meaning}
    )
    has_unmapped = any(
        c.kind == CodeKind.CHARACTER and char_for_code(c.raw) is None for c in codes
    )
    return {
        "character_count": char_count,
        "control_meanings_present": control_meanings,
        "has_unmapped_character_codes": has_unmapped,
    }


def to_editable(doc: ScriptDocument) -> EditableScript:
    """Convert a decoded ScriptDocument into the editable JSON layer,
    chunked into segments at pause-flag control codes (see module
    docstring for the caveat on this heuristic)."""
    script = EditableScript()
    current: list[ScriptCode] = []

    def flush() -> None:
        if not current:
            return
        text = "".join(_display_char(c) for c in current if c.kind == CodeKind.CHARACTER)
        script.segments.append(
            ScriptSegment(
                codes=list(current),
                original=text,
                translated=text,
                layout_constraints=_layout_constraints_for(current),
            )
        )
        current.clear()

    for code in doc.codes:
        current.append(code)
        is_pause = (
            code.kind == CodeKind.CONTROL
            and code.family == ControlFamily.A
            and code.subtype in SEGMENT_BREAK_SUBTYPES
        )
        if is_pause or code.kind == CodeKind.END:
            flush()

    flush()  # trailing codes with no terminating pause/end marker
    return script


def from_dict(data: dict) -> EditableScript:
    """Reconstruct an EditableScript from its `to_dict()` JSON form,
    restoring translator edits to `translated` while keeping `codes`
    (the re-encoding source of truth) intact."""
    script = EditableScript()
    for seg in data["segments"]:
        codes = [
            ScriptCode(
                offset=c["offset"],
                raw=c["raw"],
                kind=CodeKind(c["kind"]),
                family=ControlFamily(c["family"]) if "family" in c else None,
                subtype=c.get("subtype"),
                param=c.get("param"),
                meaning=c.get("meaning"),
                words_consumed=c["words_consumed"],
            )
            for c in seg["codes"]
        ]
        script.segments.append(
            ScriptSegment(
                codes=codes,
                original=seg["original"],
                translated=seg["translated"],
                layout_constraints=seg["layout_constraints"],
            )
        )
    return script
