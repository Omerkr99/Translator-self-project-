from gcrts.control_code_index import (
    ControlCodeIndex,
    ControlWordRecord,
    produces_y_collection_mode,
    word_family,
    word_parameter,
    word_subtype,
)


def test_word_family_classifies_correctly():
    assert word_family(0x00CF) == "direct_character"
    assert word_family(0x8500) == "control_a"
    assert word_family(0xC500) == "control_b"


def test_word_subtype_and_parameter_extraction():
    word = 0x8501
    assert word_subtype(word) == 0x0500
    assert word_parameter(word) == 1


def test_produces_y_collection_mode_requires_family_subtype_and_nonzero_param():
    assert produces_y_collection_mode(0x8501) is True
    assert produces_y_collection_mode(0x85FF) is True
    # subtype matches but parameter is zero -- confirmed NOT to trigger (WIDTH_MODE-shaped instead)
    assert produces_y_collection_mode(0x8500) is False
    # right family, wrong subtype
    assert produces_y_collection_mode(0x8901) is False
    # wrong family entirely (control_b)
    assert produces_y_collection_mode(0xC501) is False
    # direct character code
    assert produces_y_collection_mode(0x00CF) is False


def test_control_word_record_derives_fields_from_raw_word():
    rec = ControlWordRecord(raw_word=0x8501)
    assert rec.family == "control_a"
    assert rec.subtype == 0x0500
    assert rec.parameter == 1
    assert rec.meaning == "pause_flag_a"


def test_control_word_record_roundtrips_through_dict():
    rec = ControlWordRecord(
        raw_word=0x8501,
        occurrences=3,
        units=["scene_a_line_00"],
        known_decoder_output="Y_COLLECTION_MODE",
        runtime_verified=True,
    )
    restored = ControlWordRecord.from_dict(rec.to_dict())
    assert restored.raw_word == rec.raw_word
    assert restored.occurrences == rec.occurrences
    assert restored.units == rec.units
    assert restored.known_decoder_output == rec.known_decoder_output
    assert restored.runtime_verified == rec.runtime_verified


def test_index_observe_tracks_occurrences_and_units():
    index = ControlCodeIndex()
    index.observe(0x8501, unit_id="unit_a")
    index.observe(0x8501, unit_id="unit_b")
    index.observe(0x8501, unit_id="unit_a")  # duplicate unit, shouldn't double-count units list

    records = index.all_records()
    assert len(records) == 1
    rec = records[0]
    assert rec.occurrences == 3
    assert rec.units == ["unit_a", "unit_b"]


def test_index_observe_auto_classifies_y_collection_mode():
    index = ControlCodeIndex()
    rec = index.observe(0x8501)
    assert rec.known_decoder_output == "Y_COLLECTION_MODE"

    rec2 = index.observe(0x8500)  # zero parameter -- should NOT be classified
    assert rec2.known_decoder_output is None


def test_index_scan_words_skips_characters_and_terminator():
    index = ControlCodeIndex()
    words = [0x00CF, 0x00DA, 0x8501, 0x00E8, 0xFFFF, 0x8900]
    hits = index.scan_words(words, unit_id="test_unit")

    assert len(hits) == 1
    assert hits[0].raw_word == 0x8501
    # 0x8900 is after the terminator and must not be scanned
    assert index.by_subtype(0x0900) == []


def test_index_by_family_and_by_decoder_output_filters():
    index = ControlCodeIndex()
    index.observe(0x8501)
    index.observe(0xC500)
    index.observe(0x00CF)

    assert {r.raw_word for r in index.by_family("control_a")} == {0x8501}
    assert {r.raw_word for r in index.by_family("control_b")} == {0xC500}
    assert {r.raw_word for r in index.by_decoder_output("Y_COLLECTION_MODE")} == {0x8501}


def test_index_to_json_and_to_markdown_are_stable():
    index = ControlCodeIndex()
    index.observe(0x8501, unit_id="unit_a")

    data = index.to_json()
    assert len(data) == 1
    assert data[0]["raw_word"] == "0x8501"
    assert data[0]["meaning"] == "pause_flag_a"

    md = index.to_markdown()
    assert "0x8501" in md
    assert "pause_flag_a" in md
