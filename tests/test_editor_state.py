import struct

import pytest

from gcrts.editor_state import EditorState, UnitStatus
from gcrts.script_decoder import decode_script
from gcrts.script_unit import units_from_script_document


def _pack(words):
    return struct.pack(f"<{len(words)}H", *words)


def _sample_units():
    doc = decode_script(_pack([0x0001, 0x0002, 0x8500, 0x0300, 0xFFFF]))
    return units_from_script_document(doc, scene_id="scene")


def test_load_units_defaults_to_unmodified():
    state = EditorState()
    state.load_units(_sample_units())
    for u in state.units:
        assert state.status(u.id) == UnitStatus.UNMODIFIED


def test_edit_marks_modified_and_reset_reverts():
    state = EditorState()
    state.load_units(_sample_units())
    unit_id = state.units[0].id
    original = state.get(unit_id).original_text

    state.edit(unit_id, "something else")
    assert state.status(unit_id) == UnitStatus.MODIFIED
    assert state.get(unit_id).edited_text == "something else"

    state.reset(unit_id)
    assert state.status(unit_id) == UnitStatus.UNMODIFIED
    assert state.get(unit_id).edited_text == original


def test_editing_back_to_original_text_clears_modified_status():
    state = EditorState()
    state.load_units(_sample_units())
    unit_id = state.units[0].id
    original = state.get(unit_id).original_text

    state.edit(unit_id, "temp")
    state.edit(unit_id, original)
    assert state.status(unit_id) == UnitStatus.UNMODIFIED


def test_edit_unknown_id_raises():
    state = EditorState()
    state.load_units(_sample_units())
    with pytest.raises(KeyError):
        state.edit("nope", "x")


def test_injected_status_is_not_overwritten_by_further_edit_of_same_text():
    state = EditorState()
    state.load_units(_sample_units())
    unit_id = state.units[0].id
    state.set_status(unit_id, UnitStatus.INJECTED)
    # re-"editing" to the exact same text shouldn't silently downgrade status
    state.edit(unit_id, state.get(unit_id).edited_text)
    assert state.status(unit_id) == UnitStatus.INJECTED


def test_search_by_query_matches_id_or_text():
    state = EditorState()
    state.load_units(_sample_units())
    first_id = state.units[0].id
    results = state.search(query=first_id)
    assert [u.id for u in results] == [first_id]


def test_search_missing_glyphs_only():
    state = EditorState()
    state.load_units(_sample_units())
    results = state.search(missing_glyphs_only=True)
    assert all(u.missing_glyphs for u in results)
    assert len(results) == 1  # only the segment with code 0x300 has a missing glyph


def test_search_modified_only():
    state = EditorState()
    state.load_units(_sample_units())
    unit_id = state.units[0].id
    state.edit(unit_id, "edited")
    results = state.search(modified_only=True)
    assert [u.id for u in results] == [unit_id]


def test_note_roundtrip():
    state = EditorState()
    state.load_units(_sample_units())
    unit_id = state.units[0].id
    assert state.get_note(unit_id) == ""
    state.note(unit_id, "translator comment")
    assert state.get_note(unit_id) == "translator comment"


def test_session_save_load_roundtrip(tmp_path):
    state = EditorState()
    state.load_units(_sample_units())
    unit_id = state.units[0].id
    state.edit(unit_id, "edited text")
    state.note(unit_id, "a note")
    state.set_status(unit_id, UnitStatus.INJECTED)

    path = tmp_path / "session.json"
    state.save_session(str(path))

    loaded = EditorState.load_session(str(path))
    assert [u.id for u in loaded.units] == [u.id for u in state.units]
    assert loaded.get(unit_id).edited_text == "edited text"
    assert loaded.get_note(unit_id) == "a note"
    assert loaded.status(unit_id) == UnitStatus.INJECTED


def test_saved_session_includes_current_schema_version(tmp_path):
    from gcrts.editor_state import CURRENT_SCHEMA_VERSION

    state = EditorState()
    state.load_units(_sample_units())
    path = tmp_path / "session.json"
    state.save_session(str(path))

    import json

    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    assert d["schema_version"] == CURRENT_SCHEMA_VERSION


def test_a_session_file_from_before_schema_version_existed_still_loads(tmp_path):
    # Simulates a real pre-Alternative-Text-Engine session file: no
    # schema_version key, and units with none of the new ScriptUnit fields.
    from gcrts.render_mode import RenderMode

    state = EditorState()
    state.load_units(_sample_units())
    unit_id = state.units[0].id
    state.edit(unit_id, "edited text")

    d = state.to_session_dict()
    del d["schema_version"]
    for unit_dict in d["units"]:
        for key in ("render_mode", "layout_plan", "runtime_patch_status", "preview_status"):
            unit_dict.pop(key, None)

    import json

    path = tmp_path / "old_session.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f)

    loaded = EditorState.load_session(str(path))
    assert loaded.get(unit_id).edited_text == "edited text"
    assert loaded.get(unit_id).render_mode == RenderMode.HOST_FITTED
    assert loaded.get(unit_id).layout_plan is None


def test_set_render_mode_updates_the_unit():
    from gcrts.render_mode import RenderMode

    state = EditorState()
    state.load_units(_sample_units())
    unit_id = state.units[0].id
    state.set_render_mode(unit_id, RenderMode.CUSTOM_ENGINE)
    assert state.get(unit_id).render_mode == RenderMode.CUSTOM_ENGINE


def test_set_render_mode_unknown_id_raises():
    from gcrts.render_mode import RenderMode

    state = EditorState()
    state.load_units(_sample_units())
    with pytest.raises(KeyError):
        state.set_render_mode("nope", RenderMode.CUSTOM_ENGINE)


def test_get_and_set_layout_plan_roundtrip_through_state():
    from gcrts.editor_layout_plan import EditorLayoutPlan
    from gcrts.render_mode import RenderMode

    state = EditorState()
    state.load_units(_sample_units())
    unit_id = state.units[0].id
    assert state.get_layout_plan(unit_id) is None

    plan = EditorLayoutPlan(
        unit_id=unit_id, render_mode=RenderMode.CUSTOM_ENGINE, language="en", source_text="", edited_text="hi"
    )
    state.set_layout_plan(unit_id, plan)
    assert state.get_layout_plan(unit_id) is plan

    state.set_layout_plan(unit_id, None)
    assert state.get_layout_plan(unit_id) is None


def test_layout_plan_survives_a_full_session_save_load_roundtrip(tmp_path):
    # End-to-end persistence check per the master prompt's Phase 3
    # requirement: build a plan, save the session, reload it, plan intact.
    from gcrts.editor_layout_plan import EditorLayoutPlan, LayoutAlignment, LayoutLine
    from gcrts.render_mode import RenderMode

    state = EditorState()
    state.load_units(_sample_units())
    unit_id = state.units[0].id
    state.edit(unit_id, "hello world")
    state.set_render_mode(unit_id, RenderMode.CUSTOM_ENGINE)
    state.set_layout_plan(
        unit_id,
        EditorLayoutPlan(
            unit_id=unit_id,
            render_mode=RenderMode.CUSTOM_ENGINE,
            language="en",
            source_text="",
            edited_text="hello world",
            lines=[LayoutLine("hello world", 0, 11, 10, 160, LayoutAlignment.CENTER)],
        ),
    )

    path = tmp_path / "session.json"
    state.save_session(str(path))
    loaded = EditorState.load_session(str(path))

    restored_unit = loaded.get(unit_id)
    assert restored_unit.render_mode == RenderMode.CUSTOM_ENGINE
    assert restored_unit.layout_plan is not None
    assert restored_unit.layout_plan.lines[0].text == "hello world"
    assert restored_unit.layout_plan.lines[0].alignment == LayoutAlignment.CENTER
