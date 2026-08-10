"""Live Text Workbench, Phase 5: font/glyph experimentation layer.

Wraps the already-validated gcrts.font_extension (which does the actual
render/pack/encode/inject work, live-confirmed in NOTES.md's Phase 6)
with the workbench-facing pieces the spec asks for: listing what's
mapped, classifying a piece of edited text's glyph coverage, routing
missing characters to an existing substitute or a newly injected glyph
or an explicit unresolved state, and logging what was injected and with
what palette assumptions.

Palette convention (do not regress -- verified by test_font_workbench.py):
    background = 4, ink = 6
This module asserts those constants match gcrts.font_extension's on
every injection rather than silently trusting them, so a future edit to
font_extension.py that drifts the values gets caught immediately instead
of producing glyphs that look right in isolation but wrong in-game.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from gcrts.font_extension import (
    FONT_BACKGROUND_VALUE,
    FONT_INK_VALUE,
    inject_glyph_live,
    next_unused_code,
)
from gcrts.glyph_atlas import GlyphAtlas
from gcrts.glyph_char_map import CHAR_TO_CODE, CODE_TO_CHAR, code_for_char

# Heuristic look-alike substitutions for characters the base font doesn't
# have but that a translator is likely to type. These are a judgment call,
# not derived from any game data -- documented here rather than guessed
# at silently, so an operator can see exactly what will be swapped in.
SUBSTITUTE_CHARS: dict[str, str] = {
    ",": "、",
    "-": "―",
    "'": "’",
    '"': "”",
    ";": ":",
    "~": "〜",
}


def list_mapped_glyphs() -> dict[int, str]:
    """All character codes with a known mapping right now (base font plus
    anything injected earlier this process -- gcrts.font_extension mutates
    CODE_TO_CHAR/CHAR_TO_CODE in place on injection)."""
    return dict(CODE_TO_CHAR)


def classify_char(ch: str) -> str:
    """Return "mapped", "substitutable", or "unmapped" for one character."""
    if code_for_char(ch) is not None:
        return "mapped"
    if ch in SUBSTITUTE_CHARS and code_for_char(SUBSTITUTE_CHARS[ch]) is not None:
        return "substitutable"
    return "unmapped"


def audit_text(text: str) -> list[dict]:
    """Per-character glyph-coverage breakdown for a piece of edited text,
    for preview before resolving/injecting anything."""
    report = []
    for ch in text:
        cls = classify_char(ch)
        entry = {"char": ch, "classification": cls}
        if cls == "substitutable":
            entry["substitute"] = SUBSTITUTE_CHARS[ch]
        report.append(entry)
    return report


def resolve_text(text: str) -> str:
    """Apply known substitutions to `text`, leaving unmapped characters
    untouched (they'll still fail at encode time via MissingGlyphError
    unless injected first -- this function doesn't inject anything)."""
    return "".join(SUBSTITUTE_CHARS.get(ch, ch) if classify_char(ch) == "substitutable" else ch for ch in text)


@dataclass
class GlyphAuditEntry:
    code: int
    char: str
    background_value: int
    ink_value: int
    font_path: str
    font_size: int
    binary_mode: bool
    timestamp: str
    note: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class GlyphAuditLog:
    entries: list[GlyphAuditEntry] = field(default_factory=list)

    def record(self, entry: GlyphAuditEntry) -> None:
        self.entries.append(entry)

    def to_dict(self) -> dict:
        return {"entries": [e.to_dict() for e in self.entries]}

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)


def inject_new_glyph(
    code: int,
    ch: str,
    atlas: GlyphAtlas,
    gdb_client,
    log: GlyphAuditLog,
    font_path: str | None = None,
    font_size: int = 14,
    binary: bool = True,
    note: str = "",
) -> GlyphAuditEntry:
    """Inject one new glyph live and record it in `log`. Asserts the
    palette convention hasn't regressed before writing anything."""
    assert FONT_BACKGROUND_VALUE == 4, "background palette value regressed from the confirmed convention (4)"
    assert FONT_INK_VALUE == 6, "ink palette value regressed from the confirmed convention (6)"

    from gcrts.font_extension import DEFAULT_FONT_PATH

    used_font_path = font_path or DEFAULT_FONT_PATH
    inject_glyph_live(code, ch, atlas, gdb_client, font_path=used_font_path, font_size=font_size, binary=binary)

    entry = GlyphAuditEntry(
        code=code,
        char=ch,
        background_value=FONT_BACKGROUND_VALUE,
        ink_value=FONT_INK_VALUE,
        font_path=used_font_path,
        font_size=font_size,
        binary_mode=binary,
        timestamp=datetime.now(timezone.utc).isoformat(),
        note=note,
    )
    log.record(entry)
    return entry


@dataclass
class ResolutionReport:
    resolved_text: str
    injected: list[GlyphAuditEntry] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)


def auto_resolve_missing_glyphs(
    text: str,
    atlas: GlyphAtlas,
    gdb_client,
    log: GlyphAuditLog,
    allow_inject: bool = True,
) -> ResolutionReport:
    """Walk `text`, applying substitutions where known and injecting a
    brand-new glyph (into an unused per-scene dynamic-kanji slot -- see
    gcrts.font_extension.UNUSED_CODE_RANGE) for anything still unmapped,
    if `allow_inject` is True and a slot is free. Characters that can't be
    resolved either way are reported in `unresolved`, never silently
    dropped or guessed at."""
    resolved_chars: list[str] = []
    injected: list[GlyphAuditEntry] = []
    unresolved: list[str] = []
    already_injected_this_call: dict[str, int] = {}

    for ch in text:
        cls = classify_char(ch)
        if cls == "mapped":
            resolved_chars.append(ch)
            continue
        if cls == "substitutable":
            resolved_chars.append(SUBSTITUTE_CHARS[ch])
            continue

        # unmapped
        if ch in already_injected_this_call:
            resolved_chars.append(ch)
            continue
        if not allow_inject:
            resolved_chars.append(ch)
            unresolved.append(ch)
            continue
        try:
            code = next_unused_code(atlas, taken=set(already_injected_this_call.values()))
        except RuntimeError:
            resolved_chars.append(ch)
            unresolved.append(ch)
            continue
        entry = inject_new_glyph(code, ch, atlas, gdb_client, log, note="auto-resolved by auto_resolve_missing_glyphs")
        injected.append(entry)
        already_injected_this_call[ch] = code
        resolved_chars.append(ch)

    return ResolutionReport(resolved_text="".join(resolved_chars), injected=injected, unresolved=unresolved)
