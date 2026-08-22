import json

import pytest

from gcrts.dialogue_database import DialogueDatabaseEntry, save_entry
from gcrts.subtitle_export import (
    SubtitleCue,
    build_subtitle_cue,
    export_subtitle_for_asset,
    format_srt_timestamp,
    subtitle_caveat,
    write_srt,
)


def _entry(**overrides):
    defaults = dict(
        asset_id="XAPACK22:7", pack_path="DAT/XA1/XAPACK22.BIN", channel_number=7,
        duration_seconds=5.386666666666667, sample_rate_hz=37800, channels=2,
        character="Yukari", translation="....Oh, right.",
    )
    defaults.update(overrides)
    return DialogueDatabaseEntry(**defaults)


# --- format_srt_timestamp ----------------------------------------------------


def test_format_srt_timestamp_zero():
    assert format_srt_timestamp(0.0) == "00:00:00,000"


def test_format_srt_timestamp_rounds_milliseconds():
    assert format_srt_timestamp(5.386666666666667) == "00:00:05,387"


def test_format_srt_timestamp_hours_minutes():
    assert format_srt_timestamp(3661.5) == "01:01:01,500"


def test_format_srt_timestamp_rejects_negative():
    with pytest.raises(ValueError):
        format_srt_timestamp(-1.0)


# --- build_subtitle_cue -------------------------------------------------------


def test_build_subtitle_cue_uses_real_duration_and_translation():
    cue = build_subtitle_cue(_entry())
    assert cue.start_seconds == 0.0
    assert cue.end_seconds == pytest.approx(5.386666666666667)
    assert cue.speaker == "Yukari"
    assert cue.text == "....Oh, right."


def test_build_subtitle_cue_respects_start_offset():
    cue = build_subtitle_cue(_entry(), start_seconds=10.0)
    assert cue.start_seconds == 10.0
    assert cue.end_seconds == pytest.approx(15.386666666666667)


def test_build_subtitle_cue_raises_without_translation():
    with pytest.raises(ValueError):
        build_subtitle_cue(_entry(translation=None))


def test_build_subtitle_cue_raises_on_empty_translation():
    with pytest.raises(ValueError):
        build_subtitle_cue(_entry(translation=""))


# --- SubtitleCue.to_srt_block --------------------------------------------------


def test_to_srt_block_includes_speaker_and_timing():
    cue = SubtitleCue(1, 0.0, 5.0, "Yukari", "....Oh, right.")
    block = cue.to_srt_block()
    assert "1\n" in block
    assert "00:00:00,000 --> 00:00:05,000" in block
    assert "Yukari: ....Oh, right." in block


def test_to_srt_block_no_speaker_omits_prefix():
    cue = SubtitleCue(1, 0.0, 5.0, None, "Hello there.")
    block = cue.to_srt_block()
    assert "Hello there." in block
    assert ":" not in block.splitlines()[-1] or block.splitlines()[-1] == "Hello there."


# --- write_srt ------------------------------------------------------------------


def test_write_srt_round_trip(tmp_path):
    path = str(tmp_path / "sub.srt")
    cue = build_subtitle_cue(_entry())
    write_srt([cue], path)
    content = open(path, encoding="utf-8").read()
    assert "Yukari: ....Oh, right." in content
    assert "00:00:00,000 --> 00:00:05,387" in content


# --- subtitle_caveat --------------------------------------------------------------


def test_subtitle_caveat_flags_unverified_transcript_and_unapproved_translation():
    caveat = subtitle_caveat(_entry(transcript_verified=False, translation_approved=False))
    assert "not yet human-verified" in caveat
    assert "draft, not yet approved" in caveat


def test_subtitle_caveat_ready_when_both_confirmed():
    caveat = subtitle_caveat(_entry(transcript_verified=True, translation_approved=True))
    assert caveat == "Transcript verified and translation approved -- ready for subtitle use."


# --- export_subtitle_for_asset ------------------------------------------------


def test_export_subtitle_for_asset_writes_srt_and_meta(tmp_path):
    db_path = str(tmp_path / "db.json")
    save_entry(_entry(japanese_transcript="ユカリ：・・・・あ、そうだ"), path=db_path)
    out_path = str(tmp_path / "sub.srt")

    export_subtitle_for_asset("XAPACK22:7", out_path, db_path=db_path)

    assert "Yukari: ....Oh, right." in open(out_path, encoding="utf-8").read()
    meta = json.loads(open(out_path + ".meta.json", encoding="utf-8").read())
    assert meta["asset_id"] == "XAPACK22:7"
    assert meta["japanese_transcript"] == "ユカリ：・・・・あ、そうだ"
    assert meta["transcript_verified"] is False
    assert "not yet human-verified" in meta["caveat"]


def test_export_subtitle_for_asset_missing_entry_raises_keyerror(tmp_path):
    db_path = str(tmp_path / "db.json")
    with pytest.raises(KeyError):
        export_subtitle_for_asset("NOPE:0", str(tmp_path / "sub.srt"), db_path=db_path)
