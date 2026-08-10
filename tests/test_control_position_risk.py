from gcrts.control_position_risk import (
    forced_wrap_positions,
    project_control_event_positions,
    risk_lands_mid_word,
    stale_position_risks,
)
from gcrts.script_unit import ScriptUnit


def _make_unit(original_text: str, edited_text: str, control_events: list[dict], unit_start_offset: int = 0) -> ScriptUnit:
    return ScriptUnit(
        id="test_unit",
        source="live_ram",
        ram_address=None,
        unit_start_offset=unit_start_offset,
        unit_end_offset=unit_start_offset + len(original_text) + len(control_events),
        next_unit_start_offset=None,
        raw_codes=[],
        control_events=control_events,
        original_text=original_text,
        edited_text=edited_text,
        layout_constraints={},
        text_type="dialogue",
        glyphs_used=[],
        missing_glyphs=[],
    )


def test_project_control_event_positions_uses_tokenized_char_count_not_len():
    # A placeholder like <?0x0119> is a 9-character escape sequence
    # representing ONE code -- len(str) would badly over-count. Original
    # text here is 4 real chars total: 'A', a placeholder, 'B', 'C'.
    original = "A<?0x0119>BC"
    control_events = [{"offset": 2, "words_consumed": 1, "meaning": "set_flag_d10"}]
    unit = _make_unit(original, "WXYZ", control_events, unit_start_offset=0)

    positions = project_control_event_positions(unit)
    assert len(positions) == 1
    # event at word-offset 2 (i.e. after 2 of the 4 original chars) maps to
    # the halfway point of the 4-character edited text.
    assert positions[0].char_index == 2


def test_forced_wrap_positions_only_returns_forced_wrap_meanings():
    control_events = [
        {"offset": 1, "words_consumed": 1, "meaning": "set_mode_ce4"},
        {"offset": 2, "words_consumed": 1, "meaning": "set_flag_d10"},
        {"offset": 3, "words_consumed": 1, "meaning": "pause_flag_b"},
    ]
    unit = _make_unit("ABCD", "ABCD", control_events)

    forced = forced_wrap_positions(unit)
    assert [r.event["meaning"] for r in forced] == ["set_flag_d10"]

    stale = stale_position_risks(unit)
    assert [r.event["meaning"] for r in stale] == ["pause_flag_b"]


def test_risk_lands_mid_word_true_only_for_strictly_interior_positions():
    from gcrts.control_position_risk import ControlPositionRisk

    text = "hello world"
    assert risk_lands_mid_word(text, ControlPositionRisk({}, 3))  # inside "hello"
    assert not risk_lands_mid_word(text, ControlPositionRisk({}, 5))  # the space itself
    assert not risk_lands_mid_word(text, ControlPositionRisk({}, 0))  # start
    assert not risk_lands_mid_word(text, ControlPositionRisk({}, len(text)))  # end


def test_project_control_event_positions_matches_the_live_confirmed_case():
    # Reproduces the live-confirmed finding (see module docstring): a
    # set_flag_d10 event projected to land exactly at the 'p' of "pm、"
    # in a real translated sentence, and the actual game render split
    # exactly there.
    original = "A" * 35  # 35 real characters (4 control words consumed separately)
    control_events = [
        {"offset": 111, "words_consumed": 1, "meaning": "set_mode_ce4"},
        {"offset": 112, "words_consumed": 1, "meaning": "set_flag_d10"},
        {"offset": 130, "words_consumed": 1, "meaning": "low_byte_passthrough"},
        {"offset": 131, "words_consumed": 1, "meaning": "pause_flag_b"},
    ]
    edited = "If you walk by the old classroom after six pm、 they say you can still hear laughter."
    unit = _make_unit(original, edited, control_events, unit_start_offset=93)

    forced = forced_wrap_positions(unit)
    assert len(forced) == 1
    assert forced[0].char_index == 43
    assert edited[43] == "p"
