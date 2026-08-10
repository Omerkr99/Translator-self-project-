import pytest

from gcrts.font_extension import FONT_BACKGROUND_VALUE, FONT_INK_VALUE
from gcrts.font_workbench import (
    GlyphAuditLog,
    SUBSTITUTE_CHARS,
    audit_text,
    auto_resolve_missing_glyphs,
    classify_char,
    inject_new_glyph,
    list_mapped_glyphs,
    resolve_text,
)
from gcrts.glyph_char_map import CHAR_TO_CODE, CODE_TO_CHAR


class _FakeAtlas:
    """Minimal stand-in for GlyphAtlas -- exposes just what
    next_unused_code/table_entry/inject_glyph_live actually touch."""

    def __init__(self, unused_codes: set[int]):
        self._unused = unused_codes  # codes that "fail to decode" (safe to repurpose)

    def table_entry(self, code):
        return (0x80000000 + code * 8, 14)

    def decode_glyph(self, code):
        return None if code in self._unused else b"x" * 128


class _FakeGdbClient:
    def __init__(self):
        self.writes: list[tuple[int, bytes]] = []

    def write_memory(self, addr, data):
        self.writes.append((addr, data))
        return True


@pytest.fixture
def cleanup_glyph_map():
    """Injection mutates the module-level CODE_TO_CHAR/CHAR_TO_CODE dicts
    in place; undo that after each test so tests don't leak state into
    each other or into unrelated test files."""
    codes_before = set(CODE_TO_CHAR)
    chars_before = set(CHAR_TO_CODE)
    yield
    for code in set(CODE_TO_CHAR) - codes_before:
        del CODE_TO_CHAR[code]
    for ch in set(CHAR_TO_CODE) - chars_before:
        del CHAR_TO_CODE[ch]


def test_palette_convention_has_not_regressed():
    assert FONT_BACKGROUND_VALUE == 4
    assert FONT_INK_VALUE == 6


def test_classify_char_mapped():
    assert classify_char("A") == "mapped"


def test_classify_char_substitutable():
    assert classify_char(",") == "substitutable"


def test_classify_char_unmapped():
    assert classify_char("€") == "unmapped"  # not in the font, not in SUBSTITUTE_CHARS


def test_audit_text_breakdown():
    report = audit_text("A,€")
    assert [r["classification"] for r in report] == ["mapped", "substitutable", "unmapped"]
    assert report[1]["substitute"] == SUBSTITUTE_CHARS[","]


def test_resolve_text_applies_substitutions_only():
    resolved = resolve_text("A,€")
    assert resolved == "A" + SUBSTITUTE_CHARS[","] + "€"  # unmapped char passes through untouched


def test_list_mapped_glyphs_matches_glyph_char_map():
    mapped = list_mapped_glyphs()
    assert mapped[CHAR_TO_CODE["A"]] == "A"


def test_inject_new_glyph_records_audit_entry_with_correct_palette(cleanup_glyph_map):
    atlas = _FakeAtlas(unused_codes={0x10D})
    client = _FakeGdbClient()
    log = GlyphAuditLog()

    entry = inject_new_glyph(0x10D, "€", atlas, client, log, note="test injection")

    assert len(client.writes) == 1
    assert entry.code == 0x10D
    assert entry.char == "€"
    assert entry.background_value == 4
    assert entry.ink_value == 6
    assert log.entries == [entry]
    assert CODE_TO_CHAR[0x10D] == "€"
    assert CHAR_TO_CODE["€"] == 0x10D


def test_auto_resolve_missing_glyphs_mixed_text(cleanup_glyph_map):
    atlas = _FakeAtlas(unused_codes={0x10D})
    client = _FakeGdbClient()
    log = GlyphAuditLog()

    report = auto_resolve_missing_glyphs("A,€", atlas, client, log)

    assert report.resolved_text == "A" + SUBSTITUTE_CHARS[","] + "€"
    assert len(report.injected) == 1
    assert report.injected[0].char == "€"
    assert report.unresolved == []


def test_auto_resolve_reports_unresolved_when_no_slots_free(cleanup_glyph_map):
    atlas = _FakeAtlas(unused_codes=set())  # no free slots at all
    client = _FakeGdbClient()
    log = GlyphAuditLog()

    report = auto_resolve_missing_glyphs("€", atlas, client, log)

    assert report.unresolved == ["€"]
    assert report.injected == []
    assert client.writes == []


def test_auto_resolve_respects_allow_inject_false(cleanup_glyph_map):
    atlas = _FakeAtlas(unused_codes={0x10D})
    client = _FakeGdbClient()
    log = GlyphAuditLog()

    report = auto_resolve_missing_glyphs("€", atlas, client, log, allow_inject=False)

    assert report.unresolved == ["€"]
    assert client.writes == []


def test_glyph_audit_log_save_roundtrip(tmp_path, cleanup_glyph_map):
    atlas = _FakeAtlas(unused_codes={0x10D})
    client = _FakeGdbClient()
    log = GlyphAuditLog()
    inject_new_glyph(0x10D, "€", atlas, client, log)

    path = str(tmp_path / "glyph_log.json")
    log.save(path)

    import json

    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    assert d["entries"][0]["char"] == "€"
    assert d["entries"][0]["background_value"] == 4
    assert d["entries"][0]["ink_value"] == 6
