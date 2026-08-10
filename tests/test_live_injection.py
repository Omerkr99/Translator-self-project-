import struct

import pytest

from gcrts.editor_state import EditorState, UnitStatus
from gcrts.script_decoder import decode_script
from gcrts.script_encoder import MissingGlyphError
from gcrts.script_unit import units_from_script_document
import gcrts.live_injection as live_injection
from gcrts.live_injection import (
    encode_units,
    inject_all_live,
    inject_units_live,
    validate_encoded_units,
)


def _pack(words):
    return struct.pack(f"<{len(words)}H", *words)


def _sample_units(base_ram_address=0x801FE800):
    # speaker_name_start, "あい" (0x01,0x02), pause_flag_a, "A" (0xbc, mapped to Latin 'A'), end
    words = [0x8900, 0x0001, 0x0002, 0x8500, 0x00BC, 0xFFFF]
    doc = decode_script(_pack(words))
    return units_from_script_document(doc, scene_id="scene", base_ram_address=base_ram_address)


def test_encode_units_unmodified_is_byte_identical_to_original():
    units = _sample_units()
    original_bytes = _pack([0x8900, 0x0001, 0x0002, 0x8500, 0x00BC, 0xFFFF])
    assert encode_units(units) == original_bytes


def test_encode_units_reflects_edit():
    units = _sample_units()
    units[1].edited_text = "B"  # was "A" (code 0xbc)
    encoded = encode_units(units)
    redecoded = decode_script(encoded)
    # second segment's only character code should now be 'B' (0xbd)
    char_codes = [c.raw for c in redecoded.codes if c.offset >= 4 and c.kind.value == "character"]
    assert char_codes == [0x00BD]


def test_encode_units_raises_missing_glyph_for_unmappable_char():
    units = _sample_units()
    units[1].edited_text = "é"  # not in the base font
    with pytest.raises(MissingGlyphError):
        encode_units(units)


def test_segment_from_unit_drops_stale_position_codes_only_when_modified():
    from gcrts.live_injection import segment_from_unit

    units = _sample_units()
    unit0 = units[0]  # has speaker_name_start + pause_flag_a

    unmodified = segment_from_unit(unit0)
    assert any(c.meaning == "pause_flag_a" for c in unmodified.codes)

    unit0.edited_text = "え"  # a real edit -- makes is_modified True
    modified = segment_from_unit(unit0)
    assert not any(c.meaning == "pause_flag_a" for c in modified.codes)
    # the unrelated speaker_name_start code must survive the edit
    assert any(c.meaning == "speaker_name_start" for c in modified.codes)


def test_encode_units_omits_pause_code_bytes_for_an_edited_unit():
    units = _sample_units()
    unit0 = units[0]
    unit0.edited_text = "え"
    encoded = encode_units(units)
    words = struct.unpack(f"<{len(encoded) // 2}H", encoded)
    assert 0x8500 not in words  # the pause_flag_a raw word must not survive


def test_validate_encoded_units_warns_on_large_growth():
    units = _sample_units()
    units[1].edited_text = "B" * 50  # was 1 char -> huge growth
    encoded = encode_units(units)
    warnings = validate_encoded_units(units, encoded)
    assert any("longer than the original" in w for w in warnings)


def test_validate_encoded_units_no_warning_for_small_edit():
    units = _sample_units()
    units[1].edited_text = "Z"  # same length, still 'valid' single Latin char
    encoded = encode_units(units)
    warnings = validate_encoded_units(units, encoded)
    assert warnings == []


def test_inject_units_live_fails_closed_with_no_ram_address():
    units = _sample_units(base_ram_address=None)
    result = inject_units_live(units)
    assert not result.success
    assert "ram_address" in result.error


def test_inject_units_live_fails_closed_on_empty_list():
    result = inject_units_live([])
    assert not result.success
    assert "no units" in result.error


def test_inject_units_live_fails_closed_on_missing_glyph_without_touching_network(monkeypatch):
    called = False

    def fake_write(*args, **kwargs):
        nonlocal called
        called = True
        return True

    monkeypatch.setattr(live_injection, "write_script_buffer", fake_write)

    units = _sample_units()
    units[1].edited_text = "é"
    result = inject_units_live(units)

    assert not result.success
    assert not called  # never should have reached the network write


def test_inject_units_live_writes_encoded_bytes_via_write_script_buffer(monkeypatch):
    captured = {}

    def fake_write(encoded, host="127.0.0.1", port=3333):
        captured["encoded"] = encoded
        captured["host"] = host
        captured["port"] = port
        return True

    monkeypatch.setattr(live_injection, "write_script_buffer", fake_write)

    units = _sample_units()
    result = inject_units_live(units, host="1.2.3.4", port=9999)

    assert result.success
    assert result.bytes_written == len(captured["encoded"])
    assert captured["host"] == "1.2.3.4"
    assert captured["port"] == 9999


def test_inject_units_live_reports_failure_when_write_fails(monkeypatch):
    monkeypatch.setattr(live_injection, "write_script_buffer", lambda *a, **k: False)
    units = _sample_units()
    result = inject_units_live(units)
    assert not result.success
    assert "write failed" in result.error


def test_inject_all_live_marks_units_injected_on_success(monkeypatch):
    monkeypatch.setattr(live_injection, "write_script_buffer", lambda *a, **k: True)

    state = EditorState()
    state.load_units(_sample_units())
    unit_id = state.units[1].id
    state.edit(unit_id, "Z")

    result = inject_all_live(state)

    assert result.success
    assert all(state.status(u.id) == UnitStatus.INJECTED for u in state.units)


def test_inject_all_live_marks_edited_units_invalid_on_failure(monkeypatch):
    monkeypatch.setattr(live_injection, "write_script_buffer", lambda *a, **k: False)

    state = EditorState()
    state.load_units(_sample_units())
    unit_id = state.units[1].id
    state.edit(unit_id, "Z")

    result = inject_all_live(state)

    assert not result.success
    assert state.status(unit_id) == UnitStatus.INVALID
    # the untouched unit shouldn't be marked invalid just because another failed
    untouched_id = state.units[0].id
    assert state.status(untouched_id) == UnitStatus.UNMODIFIED
