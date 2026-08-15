import os

from gcrts.audio_review import build_pack_review, runtime_lba_to_offset_seconds
from gcrts.audio_semantic import SemanticType, VerificationSource
from gcrts.semantic_label_store import save_label
from gcrts.xapack import AUDIO_EOF_SUBMODE, AUDIO_SUBMODE, StreamConfidence, XaChannelStream, format_from_coding_info

SYNC = b"\x00" + b"\xff" * 10 + b"\x00"
SECTOR_SIZE = 2352


def _fake_sector(file_number=1, channel_number=0, submode=0x64, coding_info=0x01) -> bytes:
    header = bytes(4)
    subheader = bytes([file_number, channel_number, submode, coding_info]) + bytes(4)
    payload = bytes(SECTOR_SIZE - 12 - 4 - 8)
    return SYNC + header + subheader + payload


def _build_synthetic_pack(channel_lengths: dict[int, int]) -> bytes:
    max_len = max(channel_lengths.values())
    sectors: list[bytes] = []
    for row in range(max_len * 8):
        ch = row % 8
        idx = row // 8
        ch_len = channel_lengths.get(ch, 0)
        if idx < ch_len:
            is_last = idx == ch_len - 1
            submode = AUDIO_EOF_SUBMODE if is_last else AUDIO_SUBMODE
            sectors.append(_fake_sector(channel_number=ch, submode=submode))
        else:
            sectors.append(_fake_sector(file_number=0, channel_number=ch, submode=0x00, coding_info=0x00))
    sectors.append(_fake_sector(file_number=0, channel_number=0, submode=0x80, coding_info=0x00))
    return b"".join(sectors)


def _disc_with_synthetic_pack_at_real_lba(disc_path: str, channel_lengths: dict[int, int]) -> tuple[bytes, int]:
    from gcrts.xa_disc_index import _XAPACK_TABLE

    pack_start = dict(_XAPACK_TABLE)[disc_path]
    pack_bytes = _build_synthetic_pack(channel_lengths)
    return bytes(pack_start * SECTOR_SIZE) + pack_bytes, pack_start


# --- runtime_lba_to_offset_seconds --------------------------------------------


def _stream(first_lba, eof_lba, sr=37800):
    return XaChannelStream(
        "p", 0, 1, 3, first_lba=first_lba, eof_lba=eof_lba, sector_count=(eof_lba - first_lba) // 8 + 1,
        format=format_from_coding_info(1), confidence=StreamConfidence.STRUCTURALLY_CONFIRMED,
    )


def test_runtime_lba_to_offset_seconds_within_bounds():
    s = _stream(1000, 1080)
    offset = runtime_lba_to_offset_seconds(s, 1016)  # 16 physical LBA in = 2 of this channel's own sectors
    assert offset is not None
    assert offset > 0


def test_runtime_lba_to_offset_seconds_before_first_lba_is_none():
    s = _stream(1000, 1080)
    assert runtime_lba_to_offset_seconds(s, 999) is None


def test_runtime_lba_to_offset_seconds_after_eof_lba_is_none():
    s = _stream(1000, 1080)
    assert runtime_lba_to_offset_seconds(s, 1081) is None


def test_runtime_lba_to_offset_seconds_at_first_lba_is_zero():
    s = _stream(1000, 1080)
    assert runtime_lba_to_offset_seconds(s, 1000) == 0.0


# --- build_pack_review ---------------------------------------------------------


def test_build_pack_review_produces_expected_artifacts(tmp_path):
    disc, pack_start = _disc_with_synthetic_pack_at_real_lba("DAT/XA1/XAPACK00.BIN", {ch: 20 for ch in range(8)})
    out_dir = str(tmp_path / "review_out")
    label_store = str(tmp_path / "labels.json")

    result = build_pack_review(disc, "DAT/XA1/XAPACK00.BIN", out_dir, label_store_path=label_store)

    assert len(result.entries) == 8
    assert os.path.exists(os.path.join(out_dir, "analysis.json"))
    assert os.path.exists(os.path.join(out_dir, "ranking.csv"))
    assert os.path.exists(os.path.join(out_dir, "review.html"))
    for e in result.entries:
        assert os.path.exists(os.path.join(out_dir, e.wav_filename))


def test_build_pack_review_unknown_pack_raises():
    import pytest
    with pytest.raises(ValueError):
        build_pack_review(b"", "DAT/XA1/NOPE.BIN", "/tmp/whatever")


def test_build_pack_review_surfaces_confirmed_label(tmp_path):
    disc, pack_start = _disc_with_synthetic_pack_at_real_lba("DAT/XA1/XAPACK00.BIN", {ch: 20 for ch in range(8)})
    out_dir = str(tmp_path / "review_out")
    label_store = str(tmp_path / "labels.json")

    save_label("XAPACK00:3", SemanticType.DIALOGUE, VerificationSource.USER_LISTENING, "confirmed by ear", path=label_store)

    result = build_pack_review(disc, "DAT/XA1/XAPACK00.BIN", out_dir, label_store_path=label_store)
    entry = next(e for e in result.entries if e.asset_id == "XAPACK00:3")
    assert entry.confirmed_label is not None
    assert entry.confirmed_label["semantic_type"] == "DIALOGUE"
    assert entry.confirmed_label["notes"] == "confirmed by ear"


def test_build_pack_review_no_confirmed_label_is_none(tmp_path):
    disc, pack_start = _disc_with_synthetic_pack_at_real_lba("DAT/XA1/XAPACK00.BIN", {ch: 20 for ch in range(8)})
    out_dir = str(tmp_path / "review_out")
    label_store = str(tmp_path / "labels.json")  # empty store

    result = build_pack_review(disc, "DAT/XA1/XAPACK00.BIN", out_dir, label_store_path=label_store)
    assert all(e.confirmed_label is None for e in result.entries)


def test_build_pack_review_with_runtime_anchor_populates_activity_window(tmp_path):
    disc, pack_start = _disc_with_synthetic_pack_at_real_lba("DAT/XA1/XAPACK00.BIN", {ch: 20 for ch in range(8)})
    out_dir = str(tmp_path / "review_out")
    label_store = str(tmp_path / "labels.json")

    # a real LBA inside channel 2's own bounds (first_lba = pack_start + 2)
    anchor_lba = pack_start + 2 + 16  # a couple of that channel's own sectors in
    result = build_pack_review(disc, "DAT/XA1/XAPACK00.BIN", out_dir, runtime_anchor_lba=anchor_lba, label_store_path=label_store)

    entry = next(e for e in result.entries if e.asset_id == "XAPACK00:2")
    assert entry.activity_window is not None
    assert entry.activity_window["available"] is True
