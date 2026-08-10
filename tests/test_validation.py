import struct

from gcrts.editor_state import EditorState
from gcrts.script_decoder import decode_script
from gcrts.script_unit import units_from_script_document
from gcrts.validation import ValidationStatus, auto_validate


def _pack(words):
    return struct.pack(f"<{len(words)}H", *words)


def _sample_units(base_ram_address=0x801FE800):
    # speaker_name_start, "あ" (0x01), pause_flag_a, "A" (0xbc), end
    words = [0x8900, 0x0001, 0x8500, 0x00BC, 0xFFFF]
    doc = decode_script(_pack(words))
    return units_from_script_document(doc, scene_id="scene", base_ram_address=base_ram_address)


def test_auto_validate_unedited_unit_is_unknown_pending_manual_confirmation():
    units = _sample_units()
    report = auto_validate(units[0])
    assert report.status == ValidationStatus.UNKNOWN
    assert "manual" in report.detail


def test_auto_validate_flags_missing_glyph():
    units = _sample_units()
    units[1].edited_text = "é"  # not in the base font
    report = auto_validate(units[1])
    assert report.status == ValidationStatus.MISSING_GLYPH
    assert "é" in report.detail


def test_auto_validate_passes_for_valid_edit_with_same_control_codes():
    units = _sample_units()
    units[1].edited_text = "Z"  # still a single mapped Latin char
    report = auto_validate(units[1])
    assert report.status == ValidationStatus.UNKNOWN


def test_auto_validate_catches_a_genuine_control_code_mismatch():
    # Our pipeline never actually produces this on its own (control codes
    # are always replayed verbatim) -- simulate the corruption a future
    # bug could cause, to prove the check isn't a tautology: strip the
    # pause_flag_a control word out of raw_codes so re-decoding it no
    # longer matches the control_events recorded at unit-creation time.
    units = _sample_units()
    unit = units[0]
    assert 0x8500 in unit.raw_codes
    unit.raw_codes = [w for w in unit.raw_codes if w != 0x8500]

    report = auto_validate(unit)
    assert report.status == ValidationStatus.CONTROL_ISSUE
    assert "pause_flag_a" in report.detail


def test_auto_validate_does_not_false_flag_control_issue_for_intentionally_dropped_pause_code():
    # gcrts.live_injection.segment_from_unit intentionally drops
    # pause_flag_a/pause_flag_b for MODIFIED units (see its docstring --
    # these mispositition text unpredictably using stale render state).
    # Editing unit0 (which has a real pause_flag_a) must NOT trip
    # CONTROL_ISSUE just because that intentional drop changes the
    # re-encoded signature -- auto_validate accounts for it.
    units = _sample_units()
    unit = units[0]
    unit.edited_text = "Z"  # was "あ" -- a real edit, makes is_modified True
    report = auto_validate(unit)
    assert report.status != ValidationStatus.CONTROL_ISSUE
    assert report.status == ValidationStatus.UNKNOWN


def test_editor_state_stores_and_retrieves_validation():
    state = EditorState()
    state.load_units(_sample_units())
    unit_id = state.units[0].id

    assert state.validation_status(unit_id) == "unknown"
    assert state.validation_detail(unit_id) == ""

    state.set_validation(unit_id, "ok", "confirmed on screen")
    assert state.validation_status(unit_id) == "ok"
    assert state.validation_detail(unit_id) == "confirmed on screen"


def test_editor_state_validation_survives_session_roundtrip(tmp_path):
    state = EditorState()
    state.load_units(_sample_units())
    unit_id = state.units[0].id
    state.set_validation(unit_id, "overflow", "wrapped onto a third line")

    path = str(tmp_path / "session.json")
    state.save_session(path)
    loaded = EditorState.load_session(path)

    assert loaded.validation_status(unit_id) == "overflow"
    assert loaded.validation_detail(unit_id) == "wrapped onto a third line"
