import struct

from gcrts.boundary_validation import check_boundary, check_chain
from gcrts.script_decoder import decode_script
from gcrts.script_unit import units_from_script_document


def _pack(words):
    return struct.pack(f"<{len(words)}H", *words)


def _sample_units(base_ram_address=0x801FE800):
    # unit0: "A" (0xbc) then pause_flag_a; unit1: "B" (0xbd) then end
    words = [0x00BC, 0x8500, 0x00BD, 0xFFFF]
    doc = decode_script(_pack(words))
    return units_from_script_document(doc, scene_id="scene", base_ram_address=base_ram_address)


def test_unedited_unit_reports_zero_delta_and_no_warnings():
    units = _sample_units()
    report = check_boundary(units[0])
    assert report.word_count_delta == 0
    assert not report.shifts_subsequent_units
    assert report.can_encode
    assert report.boundary_bookkeeping_ok
    assert report.warnings == []


def test_same_length_edit_does_not_shift_subsequent_units():
    # unit0's own pause_flag_a control code is intentionally stripped by
    # gcrts.live_injection.segment_from_unit for any MODIFIED unit (see
    # its docstring -- pause_flag_a/b mispositions text unpredictably),
    # so a same-character-count edit still nets a delta of -1 (the
    # dropped control word), not 0 -- correctly reflecting what actually
    # gets re-encoded, not a naive char-count comparison.
    units = _sample_units()
    units[0].edited_text = "Z"  # same char count as original "A"
    report = check_boundary(units[0])
    assert report.word_count_delta == -1
    assert report.shifts_subsequent_units
    assert any("shift" in w for w in report.warnings)


def test_length_changing_edit_is_flagged_with_correct_delta():
    # +4 words for the 1->5 character growth, minus 1 for unit0's
    # pause_flag_a being intentionally stripped on this modified unit
    # (see gcrts.live_injection.segment_from_unit's docstring) = +3 net.
    units = _sample_units()
    units[0].edited_text = "Hello"  # 1 char -> 5 chars, +4 words, -1 stripped control word
    report = check_boundary(units[0])
    assert report.word_count_delta == 3
    assert report.shifts_subsequent_units
    assert any("shift" in w for w in report.warnings)
    assert any("3" in w for w in report.warnings)


def test_last_unit_length_change_does_not_claim_to_shift_anything():
    units = _sample_units()
    last = units[-1]
    assert last.next_unit_start_offset is None
    last.edited_text = "Hello"  # would change length, but nothing follows it
    report = check_boundary(last)
    assert report.word_count_delta != 0
    assert not report.shifts_subsequent_units


def test_missing_glyph_is_reported_as_encode_failure_not_a_crash():
    units = _sample_units()
    units[0].edited_text = "é"  # not in the base font
    report = check_boundary(units[0])
    assert not report.can_encode
    assert report.new_word_count is None
    assert report.word_count_delta is None
    assert "é" in report.encode_error
    assert any("cannot encode" in w for w in report.warnings)


def test_stale_boundary_bookkeeping_is_detected():
    units = _sample_units()
    units[0].unit_end_offset += 5  # simulate drifted bookkeeping
    report = check_boundary(units[0])
    assert not report.boundary_bookkeeping_ok
    assert any("NOT contiguous" in w for w in report.warnings)


def test_check_chain_reports_no_problems_for_a_real_gapless_buffer():
    units = _sample_units()
    assert check_chain(units) == []


def test_check_chain_detects_a_real_gap_between_list_entries():
    units = _sample_units()
    units[0].unit_end_offset += 1  # now disagrees with units[1].unit_start_offset
    problems = check_chain(units)
    assert len(problems) == 1
    assert units[0].id in problems[0]
    assert units[1].id in problems[0]
