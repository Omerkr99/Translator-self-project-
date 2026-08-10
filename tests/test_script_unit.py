import struct

from gcrts.script_decoder import decode_script
from gcrts.script_unit import units_from_script_document


def _pack(words):
    return struct.pack(f"<{len(words)}H", *words)


def test_units_split_on_pause_and_carry_metadata():
    words = [
        0x8900,  # family A, subtype 0x0900 -> speaker_name_start
        0x0001,  # character code 0x01 -> "あ"
        0x0002,  # character code 0x02 -> "い"
        0x8500,  # family A, subtype 0x0500 -> pause_flag_a (segment break)
        0x0300,  # character code 0x300 -> not in glyph_char_map (missing glyph)
        0xFFFF,  # end marker
    ]
    doc = decode_script(_pack(words))

    units = units_from_script_document(doc, scene_id="test_scene", base_ram_address=0x801FE800)

    assert len(units) == 2

    first, second = units
    assert first.id == "test_scene_line_00"
    assert second.id == "test_scene_line_01"

    assert first.original_text == "あい"
    assert first.edited_text == first.original_text
    assert not first.is_modified
    assert first.raw_codes == [0x8900, 0x0001, 0x0002, 0x8500]
    assert first.glyphs_used == [0x0001, 0x0002]
    assert first.missing_glyphs == []
    assert [e["meaning"] for e in first.control_events] == ["speaker_name_start", "pause_flag_a"]
    assert first.ram_address == 0x801FE800  # first code is at word offset 0
    assert first.text_type == "dialogue"
    assert first.source == "live_ram"

    assert second.original_text == "<?0x0300>"
    assert second.glyphs_used == [0x0300]
    assert second.missing_glyphs == [0x0300]
    assert second.ram_address == 0x801FE800 + 4 * 2  # word offset 4


def test_is_modified_reflects_edits():
    doc = decode_script(_pack([0x0001, 0xFFFF]))
    units = units_from_script_document(doc, scene_id="s")
    unit = units[0]
    assert not unit.is_modified
    unit.edited_text = "changed"
    assert unit.is_modified


def test_to_dict_formats_ram_address_as_hex_string():
    doc = decode_script(_pack([0x0001, 0xFFFF]))
    units = units_from_script_document(doc, scene_id="s", base_ram_address=0x801FE800)
    d = units[0].to_dict()
    assert d["ram_address"] == "0x801fe800"


def test_to_dict_ram_address_none_when_not_provided():
    doc = decode_script(_pack([0x0001, 0xFFFF]))
    units = units_from_script_document(doc, scene_id="s")
    d = units[0].to_dict()
    assert d["ram_address"] is None


def test_unit_boundaries_are_gapless_across_a_multi_unit_buffer():
    # three units: a two-word char run + pause (break), a control-with-param
    # + char (break), then a trailing char + end.
    words = [
        0x0001, 0x0002, 0x8500,  # unit 0: two chars then pause_flag_a (break)
        0x4d00, 0x007B, 0x0003, 0x8500,  # unit 1: 2-word control (family B, subtype 0x0d00, always-2-word) + char + pause
        0x0004, 0xFFFF,  # unit 2: char + end
    ]
    doc = decode_script(_pack(words))
    units = units_from_script_document(doc, scene_id="s")

    assert len(units) == 3

    # unit 0: offsets 0-2 inclusive (3 words), ends at 3
    assert units[0].unit_start_offset == 0
    assert units[0].unit_end_offset == 3
    assert units[0].next_unit_start_offset == 3

    # unit 1: starts at 3, control consumes 2 words (offset 3-4) + char (5) + pause (6) -> ends at 7
    assert units[1].unit_start_offset == 3
    assert units[1].unit_end_offset == 7
    assert units[1].next_unit_start_offset == 7

    # unit 2: starts at 7, char (7) + end (8) -> ends at 9, no next unit
    assert units[2].unit_start_offset == 7
    assert units[2].unit_end_offset == 9
    assert units[2].next_unit_start_offset is None

    # every unit but the last must be exactly contiguous with the next
    for unit in units:
        assert unit.contiguous_with_next()


def test_contiguous_with_next_detects_a_real_gap():
    doc = decode_script(_pack([0x0001, 0x8500, 0x0002, 0xFFFF]))
    units = units_from_script_document(doc, scene_id="s")
    assert units[0].contiguous_with_next()  # true before any tampering

    units[0].unit_end_offset += 1  # simulate a boundary-computation bug
    assert not units[0].contiguous_with_next()


def test_last_unit_has_no_next_and_is_vacuously_contiguous():
    doc = decode_script(_pack([0x0001, 0xFFFF]))
    units = units_from_script_document(doc, scene_id="s")
    assert len(units) == 1
    assert units[0].next_unit_start_offset is None
    assert units[0].contiguous_with_next()


def test_boundary_fields_survive_to_dict_from_dict_roundtrip():
    doc = decode_script(_pack([0x0001, 0x8500, 0x0002, 0xFFFF]))
    units = units_from_script_document(doc, scene_id="s", base_ram_address=0x801FE800)
    original = units[0]

    from gcrts.script_unit import ScriptUnit

    restored = ScriptUnit.from_dict(original.to_dict())
    assert restored.unit_start_offset == original.unit_start_offset
    assert restored.unit_end_offset == original.unit_end_offset
    assert restored.next_unit_start_offset == original.next_unit_start_offset


def test_new_unit_defaults_to_host_fitted_with_no_layout_plan():
    # Alternative Text Engine Phase 1: a freshly extracted unit must default
    # to today's proven-reliable path, not the not-yet-implemented one.
    from gcrts.render_mode import RenderMode

    doc = decode_script(_pack([0x0001, 0xFFFF]))
    unit = units_from_script_document(doc, scene_id="s")[0]
    assert unit.render_mode == RenderMode.HOST_FITTED
    assert unit.layout_plan is None
    assert unit.preview_status == "unknown"
    assert unit.runtime_patch_status.text_buffer_injected is False


def test_render_mode_and_runtime_patch_status_survive_roundtrip():
    from gcrts.render_mode import RenderMode
    from gcrts.script_unit import ScriptUnit

    doc = decode_script(_pack([0x0001, 0xFFFF]))
    unit = units_from_script_document(doc, scene_id="s")[0]
    unit.render_mode = RenderMode.CUSTOM_ENGINE
    unit.runtime_patch_status.text_buffer_injected = True
    unit.preview_status = "stale"

    restored = ScriptUnit.from_dict(unit.to_dict())
    assert restored.render_mode == RenderMode.CUSTOM_ENGINE
    assert restored.runtime_patch_status.text_buffer_injected is True
    assert restored.preview_status == "stale"


def test_layout_plan_survives_roundtrip_when_present():
    from gcrts.editor_layout_plan import EditorLayoutPlan, LayoutLine
    from gcrts.render_mode import RenderMode
    from gcrts.script_unit import ScriptUnit

    doc = decode_script(_pack([0x0001, 0xFFFF]))
    unit = units_from_script_document(doc, scene_id="s")[0]
    unit.render_mode = RenderMode.CUSTOM_ENGINE
    unit.layout_plan = EditorLayoutPlan(
        unit_id=unit.id,
        render_mode=RenderMode.CUSTOM_ENGINE,
        language="en",
        source_text=unit.original_text,
        edited_text="Hello there.",
        lines=[LayoutLine(text="Hello there.", start_character_index=0, end_character_index=12, x=10, y=160)],
    )

    restored = ScriptUnit.from_dict(unit.to_dict())
    assert restored.layout_plan is not None
    assert restored.layout_plan.unit_id == unit.id
    assert restored.layout_plan.lines[0].text == "Hello there."


def test_a_dict_from_before_these_fields_existed_still_loads_with_defaults():
    # Simulates a session file saved before Alternative Text Engine Phase 1
    # -- no render_mode/layout_plan/runtime_patch_status/preview_status keys
    # at all. Must load exactly as HOST_FITTED with no plan, never KeyError.
    from gcrts.render_mode import RenderMode
    from gcrts.script_unit import ScriptUnit

    doc = decode_script(_pack([0x0001, 0xFFFF]))
    unit = units_from_script_document(doc, scene_id="s")[0]
    old_dict = unit.to_dict()
    for key in ("render_mode", "layout_plan", "runtime_patch_status", "preview_status"):
        del old_dict[key]

    restored = ScriptUnit.from_dict(old_dict)
    assert restored.render_mode == RenderMode.HOST_FITTED
    assert restored.layout_plan is None
    assert restored.runtime_patch_status.text_buffer_injected is False
    assert restored.preview_status == "unknown"
