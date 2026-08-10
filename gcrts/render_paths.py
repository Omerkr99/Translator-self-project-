"""Live Text Workbench, Phase 6: multi-text-type support.

Only ONE render path has actually been reverse-engineered and
live-validated in this whole project: dialogue text, via the script
buffer at gcrts.live_extract.SCRIPT_BUF_ADDR (0x801fe800) and the
FUN_80049168 bytecode reader (see NOTES.md's Phase 5/6 confirmations).

Every other text family the workbench spec asks to discover -- menus,
system prompts, status overlays, chapter titles, and speaker labels as a
render path in their own right rather than dialogue's speaker_name_start/
end control codes -- has NOT been investigated. This module does not
pretend otherwise. It provides the adapter REGISTRY and INTERFACE the
spec asks for ("the architecture must allow multiple render-path
adapters"), with dialogue as the one real, working adapter and every
other text type registered as an explicit, honest stub. A stub raises
NotImplementedError with a pointer to the research workflow needed to
fill it in for real: capture a live sample of that text on screen, trace
its source/render path via GDB (the same breakpoint-based technique that
found the dialogue buffer -- see NOTES.md), classify it, then replace the
stub with a real adapter via register_adapter(). Guessing at a buffer
address or bytecode format without live verification would violate the
project's own "never assume text encoding" rule.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from gcrts.script_unit import ScriptUnit, extract_live_script_units


class RenderPathAdapter(Protocol):
    text_type: str

    def extract(self, scene_id: str, host: str, port: int) -> list[ScriptUnit]: ...


@dataclass
class DialogueAdapter:
    """The one real, live-validated adapter -- a thin wrapper over
    gcrts.script_unit.extract_live_script_units, which already does all
    the actual work (capture, decode, segment, normalize)."""

    text_type: str = "dialogue"

    def extract(self, scene_id: str, host: str = "127.0.0.1", port: int = 3333) -> list[ScriptUnit]:
        return extract_live_script_units(scene_id, host=host, port=port, text_type=self.text_type)


@dataclass
class UnimplementedAdapter:
    """Honest placeholder for a text family that hasn't been
    reverse-engineered yet. Registered so the workbench's coverage
    tracker can list it as known-but-unsupported -- distinct from a text
    type nobody has even thought to look for."""

    text_type: str
    research_notes: str = ""

    def extract(self, scene_id: str, host: str = "127.0.0.1", port: int = 3333) -> list[ScriptUnit]:
        raise NotImplementedError(
            f"'{self.text_type}' has not been reverse-engineered yet. Research workflow: "
            "capture a live sample of this text on screen, trace its source/render path via "
            "GDB (the same breakpoint-based technique that found the dialogue buffer -- see "
            "NOTES.md), classify it, then replace this stub with a real adapter via "
            f"register_adapter(). Notes so far: {self.research_notes or '(none)'}"
        )


# Coverage tracker: what's known about each text family the workbench
# spec asks to eventually support. "implemented" only means "confirmed
# investigated + adapter built", not "these are definitely the only text
# types that exist" -- new families found during research should be
# added here via register_adapter(), not hardcoded into this dict.
KNOWN_TEXT_TYPES: dict[str, RenderPathAdapter] = {
    "dialogue": DialogueAdapter(),
    "speaker_label": UnimplementedAdapter(
        "speaker_label",
        "Currently handled AS PART OF dialogue via speaker_name_start/end control codes "
        "(see gcrts.script_decoder's CONTROL_A_MEANINGS), not as an independent render path. "
        "Unclear whether speaker names ever render through a separate buffer/mechanism -- "
        "not investigated.",
    ),
    "menu": UnimplementedAdapter("menu"),
    "system_prompt": UnimplementedAdapter("system_prompt"),
    "status_overlay": UnimplementedAdapter("status_overlay"),
    "chapter_title": UnimplementedAdapter("chapter_title"),
}


def coverage_report() -> list[dict]:
    """One row per known text type: whether it has a real adapter yet,
    plus any research notes recorded for the still-unimplemented ones."""
    rows = []
    for text_type, adapter in KNOWN_TEXT_TYPES.items():
        row = {"text_type": text_type, "implemented": not isinstance(adapter, UnimplementedAdapter)}
        if isinstance(adapter, UnimplementedAdapter) and adapter.research_notes:
            row["notes"] = adapter.research_notes
        rows.append(row)
    return rows


def register_adapter(adapter: RenderPathAdapter) -> None:
    """Register a real adapter for a text type once it's actually been
    reverse-engineered, replacing its stub -- or register a wholly new
    text type discovered during research that wasn't anticipated here."""
    KNOWN_TEXT_TYPES[adapter.text_type] = adapter


def extract_units_for(
    text_type: str, scene_id: str, host: str = "127.0.0.1", port: int = 3333
) -> list[ScriptUnit]:
    adapter = KNOWN_TEXT_TYPES.get(text_type)
    if adapter is None:
        raise KeyError(
            f"unknown text_type {text_type!r} -- register it first via register_adapter(), "
            f"known types: {sorted(KNOWN_TEXT_TYPES)}"
        )
    return adapter.extract(scene_id, host=host, port=port)
