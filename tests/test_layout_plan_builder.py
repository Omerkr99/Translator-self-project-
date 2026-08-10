import struct

from gcrts.editor_layout_plan import LayoutMode
from gcrts.layout_plan_builder import build_auto_layout_plan
from gcrts.render_mode import RenderMode
from gcrts.script_decoder import decode_script
from gcrts.script_unit import units_from_script_document


def _pack(words):
    return struct.pack(f"<{len(words)}H", *words)


def _unit_with_text(text):
    doc = decode_script(_pack([0x0001, 0xFFFF]))
    unit = units_from_script_document(doc, scene_id="s")[0]
    unit.edited_text = text
    return unit


def test_build_auto_layout_plan_groups_words_into_lines():
    unit = _unit_with_text("one two three four five six seven eight")
    plan = build_auto_layout_plan(unit, max_width_px=96)  # small budget forces multiple lines
    assert len(plan.lines) > 1
    assert plan.render_mode == RenderMode.CUSTOM_ENGINE
    assert plan.layout_mode == LayoutMode.AUTO_WORD_WRAP
    # no word lost, none duplicated, none split
    joined_words = " ".join(line.text for line in plan.lines).split(" ")
    assert joined_words == unit.edited_text.split(" ")


def test_build_auto_layout_plan_never_splits_a_word_across_lines():
    unit = _unit_with_text("one two three four five six seven eight")
    plan = build_auto_layout_plan(unit, max_width_px=96)
    for line in plan.lines:
        for word in line.text.split(" "):
            assert word in unit.edited_text.split(" ")


def test_build_auto_layout_plan_assigns_sequential_y_positions():
    unit = _unit_with_text("one two three four five six seven eight")
    plan = build_auto_layout_plan(unit, max_width_px=96, base_y=100, line_height=20)
    ys = [line.y for line in plan.lines]
    assert ys == [100 + i * 20 for i in range(len(plan.lines))]


def test_build_auto_layout_plan_character_indices_point_back_into_edited_text():
    unit = _unit_with_text("one two three four five six seven eight")
    plan = build_auto_layout_plan(unit, max_width_px=96)
    for line in plan.lines:
        slice_ = unit.edited_text[line.start_character_index : line.end_character_index]
        assert slice_ == line.text


def test_build_auto_layout_plan_single_short_line():
    unit = _unit_with_text("hi")
    plan = build_auto_layout_plan(unit)
    assert len(plan.lines) == 1
    assert plan.lines[0].text == "hi"
    assert plan.lines[0].start_character_index == 0
    assert plan.lines[0].end_character_index == 2
