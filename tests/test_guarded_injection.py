import struct

import pytest

import gcrts.guarded_injection as guarded_injection
from gcrts.editor_state import EditorState
from gcrts.guarded_injection import inject_unit_guarded
from gcrts.live_injection import InjectionResult
from gcrts.script_decoder import decode_script
from gcrts.script_unit import units_from_script_document


def _pack(words):
    return struct.pack(f"<{len(words)}H", *words)


def _sample_state(base_ram_address=0x801FE800) -> EditorState:
    # unit0: "A" (0xbc) then pause_flag_a; unit1: "B" (0xbd) then end
    words = [0x00BC, 0x8500, 0x00BD, 0xFFFF]
    doc = decode_script(_pack(words))
    units = units_from_script_document(doc, scene_id="scene", base_ram_address=base_ram_address)
    state = EditorState()
    state.load_units(units)
    return state


# --- EditorState injection history --------------------------------------


def test_record_and_query_injection_history():
    state = _sample_state()
    unit_id = state.units[0].id
    assert state.injection_history(unit_id) == []

    state.record_injection(unit_id, success=True, bytes_written=42)
    state.record_injection(unit_id, success=False, bytes_written=0, error="oops")

    history = state.injection_history(unit_id)
    assert len(history) == 2
    assert history[0]["success"] is True
    assert history[1]["error"] == "oops"
    assert all("timestamp" in e for e in history)


def test_injection_history_is_per_unit_not_global():
    state = _sample_state()
    id0, id1 = state.units[0].id, state.units[1].id
    state.record_injection(id0, success=True, bytes_written=10)
    assert len(state.injection_history(id0)) == 1
    assert len(state.injection_history(id1)) == 0
    assert len(state.all_injection_history()) == 1


def test_injection_history_survives_session_roundtrip(tmp_path):
    state = _sample_state()
    unit_id = state.units[0].id
    state.record_injection(unit_id, success=True, bytes_written=99)

    path = str(tmp_path / "session.json")
    state.save_session(path)
    loaded = EditorState.load_session(path)

    assert loaded.injection_history(unit_id)[0]["bytes_written"] == 99


# --- guarded injection ----------------------------------------------------


def test_inject_unit_guarded_unknown_id_raises():
    state = _sample_state()
    with pytest.raises(KeyError):
        inject_unit_guarded(state, "nope")


def test_inject_unit_guarded_blocks_on_missing_glyph_without_touching_network(monkeypatch):
    called = []
    monkeypatch.setattr(guarded_injection, "inject_all_live", lambda *a, **k: called.append(1))

    state = _sample_state()
    unit_id = state.units[0].id
    state.edit(unit_id, "é")  # not in the base font

    result = inject_unit_guarded(state, unit_id)

    assert not result.proceeded
    assert result.layout_status == "missing_glyph"
    assert not called  # inject_all_live must never have been called
    history = state.injection_history(unit_id)
    assert len(history) == 1
    assert not history[0]["success"]
    assert "blocked" in history[0]["error"]


def test_inject_unit_guarded_proceeds_and_logs_success_for_a_clean_edit(monkeypatch):
    fake_result = InjectionResult(success=True, bytes_written=123, error=None)
    monkeypatch.setattr(guarded_injection, "inject_all_live", lambda *a, **k: fake_result)

    state = _sample_state()
    unit_id = state.units[0].id
    state.edit(unit_id, "B")  # still a mapped, safe, same-length edit

    result = inject_unit_guarded(state, unit_id)

    assert result.proceeded
    assert result.layout_status == "ok"
    assert result.injection is fake_result
    history = state.injection_history(unit_id)
    assert len(history) == 1
    assert history[0]["success"]
    assert history[0]["bytes_written"] == 123


def test_inject_unit_guarded_warns_but_proceeds_for_pixel_overflow(monkeypatch):
    fake_result = InjectionResult(success=True, bytes_written=456, error=None)
    monkeypatch.setattr(guarded_injection, "inject_all_live", lambda *a, **k: fake_result)

    state = _sample_state()
    unit_id = state.units[0].id
    state.edit(unit_id, "This is a very very long sentence that clearly overflows")

    result = inject_unit_guarded(state, unit_id)

    assert result.proceeded  # overflow warns, does not block
    assert result.layout_status == "pixel_overflow"
    assert result.injection is fake_result


def test_inject_unit_guarded_logs_failure_when_injection_itself_fails(monkeypatch):
    fake_result = InjectionResult(success=False, bytes_written=0, error="live write failed")
    monkeypatch.setattr(guarded_injection, "inject_all_live", lambda *a, **k: fake_result)

    state = _sample_state()
    unit_id = state.units[0].id
    state.edit(unit_id, "B")

    result = inject_unit_guarded(state, unit_id)

    assert result.proceeded
    assert not result.injection.success
    history = state.injection_history(unit_id)
    assert history[0]["error"] == "live write failed"


def test_inject_unit_guarded_updates_validation_status(monkeypatch):
    monkeypatch.setattr(guarded_injection, "inject_all_live", lambda *a, **k: InjectionResult(True, 1, None))
    state = _sample_state()
    unit_id = state.units[0].id
    state.edit(unit_id, "B")

    assert state.validation_status(unit_id) == "unknown"
    inject_unit_guarded(state, unit_id)
    assert state.validation_status(unit_id) == "ok"
