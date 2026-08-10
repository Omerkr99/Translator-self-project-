import pytest

from gcrts.editor_layout_plan import (
    EditorLayoutPlan,
    LayoutAlignment,
    LayoutLine,
    LayoutMode,
    LayoutPlanValidation,
    PageTransition,
)
from gcrts.render_mode import RenderMode


def _plan_with_two_lines():
    return EditorLayoutPlan(
        unit_id="s_line_00",
        render_mode=RenderMode.CUSTOM_ENGINE,
        language="en",
        source_text="",
        edited_text="",
        lines=[
            LayoutLine("first line", 0, 10, 10, 160, LayoutAlignment.LEFT),
            LayoutLine("second line", 11, 22, 10, 176, LayoutAlignment.LEFT),
        ],
    )


def test_layout_line_roundtrips_through_dict():
    line = LayoutLine(
        text="This is the first line.",
        start_character_index=0,
        end_character_index=22,
        x=10,
        y=160,
        alignment=LayoutAlignment.CENTER,
        max_width_px=280,
        measured_width_px=164,
    )
    restored = LayoutLine.from_dict(line.to_dict())
    assert restored == line


def test_layout_line_alignment_defaults_to_left():
    line = LayoutLine.from_dict(
        {"text": "hi", "start_character_index": 0, "end_character_index": 2, "x": 10, "y": 160}
    )
    assert line.alignment == LayoutAlignment.LEFT


def test_layout_plan_validation_ok_is_true_only_when_nothing_is_flagged():
    assert LayoutPlanValidation().ok is True
    assert LayoutPlanValidation(pixel_overflow=True).ok is False
    assert LayoutPlanValidation(missing_glyphs=["é"]).ok is False


def test_editor_layout_plan_roundtrips_through_dict():
    plan = EditorLayoutPlan(
        unit_id="scene_012_line_003",
        render_mode=RenderMode.CUSTOM_ENGINE,
        language="en",
        source_text="日本語",
        edited_text="This is the first line. This is the next line.",
        lines=[
            LayoutLine("This is the first line.", 0, 22, 10, 160, LayoutAlignment.LEFT, 280, 164),
            LayoutLine("This is the next line.", 23, 45, 10, 176, LayoutAlignment.LEFT, 280, 158),
        ],
        layout_mode=LayoutMode.MANUAL_LINES,
        paragraph_end=True,
        page_transition=PageTransition.WAIT_FOR_INPUT,
        control_events=[{"offset": 5, "meaning": "speaker_name_start"}],
        validation=LayoutPlanValidation(pixel_overflow=False),
    )

    restored = EditorLayoutPlan.from_dict(plan.to_dict())
    assert restored.unit_id == plan.unit_id
    assert restored.render_mode == RenderMode.CUSTOM_ENGINE
    assert len(restored.lines) == 2
    assert restored.lines[1].text == "This is the next line."
    assert restored.layout_mode == LayoutMode.MANUAL_LINES
    assert restored.control_events == plan.control_events
    assert restored.validation.ok is True


def test_editor_layout_plan_from_dict_tolerates_a_minimal_dict():
    # Only unit_id is truly required -- everything else should default
    # sensibly, matching how ScriptUnit.from_dict tolerates missing keys.
    plan = EditorLayoutPlan.from_dict({"unit_id": "s_line_00"})
    assert plan.render_mode == RenderMode.HOST_FITTED
    assert plan.lines == []
    assert plan.layout_mode == LayoutMode.AUTO_WORD_WRAP
    assert plan.page_transition == PageTransition.WAIT_FOR_INPUT
    assert plan.validation.ok is True


def test_editor_layout_plan_to_dict_includes_schema_version():
    plan = EditorLayoutPlan(
        unit_id="s_line_00", render_mode=RenderMode.HOST_FITTED, language="en", source_text="", edited_text=""
    )
    assert plan.to_dict()["schema_version"] == 1


def test_add_line_appends_by_default():
    plan = _plan_with_two_lines()
    plan.add_line(LayoutLine("third line", 23, 33, 10, 192, LayoutAlignment.LEFT))
    assert len(plan.lines) == 3
    assert plan.lines[2].text == "third line"


def test_add_line_inserts_at_a_given_index():
    plan = _plan_with_two_lines()
    plan.add_line(LayoutLine("inserted", 0, 8, 10, 168, LayoutAlignment.LEFT), index=1)
    assert [line.text for line in plan.lines] == ["first line", "inserted", "second line"]


def test_remove_line_removes_the_right_one():
    plan = _plan_with_two_lines()
    plan.remove_line(0)
    assert len(plan.lines) == 1
    assert plan.lines[0].text == "second line"


def test_remove_line_out_of_range_raises_index_error():
    plan = _plan_with_two_lines()
    with pytest.raises(IndexError):
        plan.remove_line(5)


def test_update_line_only_touches_given_fields():
    plan = _plan_with_two_lines()
    plan.update_line(0, x=20)
    assert plan.lines[0].x == 20
    assert plan.lines[0].y == 160  # unchanged
    assert plan.lines[0].text == "first line"  # unchanged


def test_update_line_can_change_text_and_alignment_together():
    plan = _plan_with_two_lines()
    plan.update_line(1, text="changed", alignment=LayoutAlignment.CENTER)
    assert plan.lines[1].text == "changed"
    assert plan.lines[1].alignment == LayoutAlignment.CENTER


def test_update_line_out_of_range_raises_index_error():
    plan = _plan_with_two_lines()
    with pytest.raises(IndexError):
        plan.update_line(5, x=1)
