from pathlib import Path

from gcrts.extractor import extract_text_runs
from gcrts.loader import RawSegment


def make_segment(data: bytes) -> RawSegment:
    return RawSegment(path=Path("synthetic.bin"), data=data)


def test_extracts_single_ascii_run():
    data = b"\x00\x00HELLO\x00\x00"
    results = extract_text_runs(make_segment(data), min_length=4)
    assert len(results) == 1
    assert results[0].text == "HELLO"
    assert results[0].offset == 2
    assert results[0].length == 5
    assert results[0].encoding == "ascii"


def test_skips_runs_shorter_than_min_length():
    data = b"\x00AB\x00CDEFG\x00"
    results = extract_text_runs(make_segment(data), min_length=4)
    assert len(results) == 1
    assert results[0].text == "CDEFG"


def test_multiple_ascii_runs():
    data = b"\x01NAME\x02\x03ITEM1\x04\x05TALK\x06"
    results = extract_text_runs(make_segment(data), min_length=4)
    texts = [r.text for r in results]
    assert texts == ["NAME", "ITEM1", "TALK"]


def test_no_printable_data():
    data = bytes([0x00, 0x01, 0x02, 0x03])
    results = extract_text_runs(make_segment(data), min_length=4)
    assert results == []


def test_run_extends_to_end_of_file():
    data = b"\x00\x00ENDRUN"
    results = extract_text_runs(make_segment(data), min_length=4)
    assert len(results) == 1
    assert results[0].text == "ENDRUN"


def test_detects_utf16le_run():
    payload = "HELLO".encode("utf-16-le")
    data = b"\x01\x02" + payload + b"\x03\x04"
    results = extract_text_runs(make_segment(data), min_length=4)
    assert len(results) == 1
    assert results[0].encoding == "utf-16le"
    assert results[0].text == "HELLO"
    assert results[0].offset == 2
    assert results[0].length == len(payload)


def test_detects_shift_jis_run():
    payload = "テスト".encode("shift_jis")
    data = b"\x00\x00" + payload + b"\x00\x00"
    results = extract_text_runs(make_segment(data), min_length=4)
    assert len(results) == 1
    assert results[0].encoding == "shift_jis"
    assert results[0].text == "テスト"
    assert results[0].offset == 2
    assert results[0].length == len(payload)


def test_shift_jis_run_can_mix_ascii_compatible_bytes():
    payload = "OK".encode("ascii") + "テスト".encode("shift_jis")
    data = b"\x00\x00" + payload + b"\x00\x00"
    results = extract_text_runs(make_segment(data), min_length=4)
    assert len(results) == 1
    assert results[0].encoding == "shift_jis"
    assert results[0].text == "OKテスト"


def test_pure_ascii_is_not_misread_as_shift_jis():
    data = b"\x00\x00HELLO WORLD\x00\x00"
    results = extract_text_runs(make_segment(data), min_length=4)
    assert len(results) == 1
    assert results[0].encoding == "ascii"


def test_detects_long_halfwidth_katakana_run():
    # Half-width katakana bytes (0xA1-0xDF) have no pairing constraint, so a
    # lone one is weak evidence (see _has_kana docstring) -- only a run long
    # enough to clear the length exemption is trusted.
    payload = "ｱｲｳｴｵｶｷｸｹｺｻｼ".encode("shift_jis")  # 13 bytes
    data = b"\x00\x00" + payload + b"\x00\x00"
    results = extract_text_runs(make_segment(data), min_length=4)
    assert len(results) == 1
    assert results[0].encoding == "shift_jis"
    assert results[0].text == "ｱｲｳｴｵｶｷｸｹｺｻｼ"
    assert results[0].length == len(payload)


def test_short_halfwidth_katakana_run_is_rejected_as_weak_evidence():
    payload = "ｱｲｳｴｵ".encode("shift_jis")  # 5 bytes, below the exemption length
    data = b"\x00\x00" + payload + b"\x00\x00"
    results = extract_text_runs(make_segment(data), min_length=4)
    assert results == []


def test_short_kanji_only_run_without_kana_is_rejected_as_noise():
    # No kana present and shorter than the exemption threshold -- this is
    # exactly the shape of the false positives found in real binary data.
    payload = "山田".encode("shift_jis")  # 4 bytes, all kanji, no kana
    data = b"\x00\x00" + payload + b"\x00\x00"
    results = extract_text_runs(make_segment(data), min_length=4)
    assert results == []


def test_long_kanji_only_run_without_kana_is_still_detected():
    payload = "東京日本語学校".encode("shift_jis")  # 14 bytes, all kanji, no kana
    data = b"\x00\x00" + payload + b"\x00\x00"
    results = extract_text_runs(make_segment(data), min_length=4)
    assert len(results) == 1
    assert results[0].encoding == "shift_jis"
    assert results[0].text == "東京日本語学校"
