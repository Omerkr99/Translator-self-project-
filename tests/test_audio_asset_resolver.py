from gcrts.audio_asset_resolver import (
    ResolutionConfidence,
    build_full_disc_asset_index,
    decode_audio_asset,
    export_audio_asset_wav,
    find_asset_by_id,
    find_duplicate_assets,
    load_asset_index,
    resolve_audio_asset,
    resolve_from_script_audio_association,
    save_asset_index,
)
from gcrts.xa_decoder_verify import DecoderConfidence
from gcrts.xapack import (
    AUDIO_EOF_SUBMODE,
    AUDIO_SUBMODE,
    SAMPLES_PER_CHANNEL_PER_SECTOR,
    AudioAsset,
    StreamConfidence,
    format_from_coding_info,
)

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
    """resolve_audio_asset (and resolve_from_script_audio_association)
    look the LBA up against the REAL 43-pack catalog first
    (gcrts.xapack_catalog), so a synthetic pack used with them must sit
    at a real pack's own real start_lba -- everything before it is
    padding with no valid sync pattern. Returns (disc_bytes, pack_start_lba)."""
    from gcrts.xa_disc_index import _XAPACK_TABLE

    pack_start = dict(_XAPACK_TABLE)[disc_path]
    pack_bytes = _build_synthetic_pack(channel_lengths)
    return bytes(pack_start * SECTOR_SIZE) + pack_bytes, pack_start


# --- resolve_audio_asset: real anchor cross-validation -------------------------


def test_resolve_audio_asset_matches_real_known_cue_127_channel_7():
    """Real, end-to-end regression using the actual, independently
    established live anchor already on record elsewhere in this
    project (gcrts.runtime_audio.KNOWN_CUE_SOURCES[127]): LBA 126921,
    xa_channel=7, inside XAPACK08.BIN. Builds only the real disc's
    XAPACK08.BIN region as synthetic bytes at its true absolute LBA
    offset (padding everything before it with non-sync bytes)."""
    from gcrts.xa_disc_index import _XAPACK_TABLE  # real, exact table

    pack08_start = dict(_XAPACK_TABLE)["DAT/XA1/XAPACK08.BIN"]
    # Build the real pack08 structure (8 channels, long enough to include LBA 126921)
    channel_lengths = {ch: 400 for ch in range(8)}
    pack_bytes = _build_synthetic_pack(channel_lengths)
    disc = bytes(pack08_start * SECTOR_SIZE) + pack_bytes
    resolution = resolve_audio_asset(disc, 126921)
    assert resolution.confidence == ResolutionConfidence.LIVE_LBA_MATCHED
    assert resolution.asset is not None
    assert resolution.asset.channel_number == 7
    assert resolution.asset.pack_path == "DAT/XA1/XAPACK08.BIN"


def test_resolve_audio_asset_does_not_confuse_overlapping_channel_spans():
    """Regression for the real bug this milestone caught: interleaved
    channels' [first,eof] spans overlap almost entirely, so matching
    by range containment alone (without reading the real sector's own
    channel_number) previously picked the WRONG channel."""
    disc, pack_start = _disc_with_synthetic_pack_at_real_lba("DAT/XA1/XAPACK00.BIN", {ch: 20 for ch in range(8)})
    # pack_start + 3 is channel 3's own first sector, but also falls
    # inside every other channel's overall [first,eof] span
    resolution = resolve_audio_asset(disc, pack_start + 3)
    assert resolution.asset.channel_number == 3


def test_resolve_audio_asset_unresolved_outside_any_pack():
    # LBA 1 is before every real pack's own start_lba (the first,
    # XAPACK00.BIN, starts at 2034) -- the catalog lookup fails before
    # disc_bytes is ever touched, so an empty buffer is fine here.
    resolution = resolve_audio_asset(b"", 1)
    assert resolution.confidence == ResolutionConfidence.UNRESOLVED
    assert resolution.asset is None


def test_resolve_audio_asset_pack_only_for_silence_padding_sector():
    # channel 0 has only 2 sectors; row 8 (channel 0's 2nd slot) is padding
    disc, pack_start = _disc_with_synthetic_pack_at_real_lba(
        "DAT/XA1/XAPACK00.BIN", {0: 2, 1: 10, 2: 10, 3: 10, 4: 10, 5: 10, 6: 10, 7: 10}
    )
    resolution = resolve_audio_asset(disc, pack_start + 16)  # channel 0's 3rd row -> silence
    assert resolution.confidence == ResolutionConfidence.PACK_ONLY
    assert resolution.asset is None


# --- resolve_from_script_audio_association --------------------------------------


class _FakeAssociation:
    def __init__(self, audio_event):
        self.audio_event = audio_event


def test_resolve_from_script_audio_association_uses_start_lba():
    disc, pack_start = _disc_with_synthetic_pack_at_real_lba("DAT/XA1/XAPACK00.BIN", {ch: 20 for ch in range(8)})
    association = _FakeAssociation({"start_lba": pack_start + 5})
    resolution = resolve_from_script_audio_association(disc, association)
    assert resolution.confidence == ResolutionConfidence.LIVE_LBA_MATCHED
    assert resolution.asset.channel_number == 5


def test_resolve_from_script_audio_association_no_audio_event():
    association = _FakeAssociation(None)
    resolution = resolve_from_script_audio_association(b"", association)
    assert resolution.confidence == ResolutionConfidence.UNRESOLVED


def test_resolve_from_script_audio_association_no_start_lba():
    association = _FakeAssociation({"start_lba": None})
    resolution = resolve_from_script_audio_association(b"", association)
    assert resolution.confidence == ResolutionConfidence.UNRESOLVED


# --- build_full_disc_asset_index / save+load / find helpers --------------------


def test_find_asset_by_id():
    stream_fmt = format_from_coding_info(1)
    a = AudioAsset("DAT/XA1/XAPACK00.BIN", 0, 10, 20, 5, stream_fmt, 1.0, StreamConfidence.CANDIDATE)
    b = AudioAsset("DAT/XA1/XAPACK00.BIN", 1, 30, 40, 5, stream_fmt, 1.0, StreamConfidence.CANDIDATE)
    assert find_asset_by_id([a, b], "XAPACK00:1") is b
    assert find_asset_by_id([a, b], "XAPACK00:9") is None


def test_find_duplicate_assets_groups_by_content_hash():
    fmt = format_from_coding_info(1)
    a = AudioAsset("DAT/XA1/XAPACK00.BIN", 0, 10, 20, 5, fmt, 1.0, StreamConfidence.CANDIDATE, content_sha256="deadbeef")
    b = AudioAsset("DAT/XA1/XAPACK01.BIN", 0, 10, 20, 5, fmt, 1.0, StreamConfidence.CANDIDATE, content_sha256="deadbeef")
    c = AudioAsset("DAT/XA1/XAPACK02.BIN", 0, 10, 20, 5, fmt, 1.0, StreamConfidence.CANDIDATE, content_sha256="uniquehash")
    d = AudioAsset("DAT/XA1/XAPACK03.BIN", 0, 10, 20, 5, fmt, 1.0, StreamConfidence.CANDIDATE, content_sha256=None)
    dupes = find_duplicate_assets([a, b, c, d])
    assert dupes == {"deadbeef": [a, b]}


def test_save_and_load_asset_index_round_trips(tmp_path):
    fmt = format_from_coding_info(1)
    a = AudioAsset("DAT/XA1/XAPACK00.BIN", 0, 10, 20, 5, fmt, 1.0, StreamConfidence.CANDIDATE)
    path = str(tmp_path / "index.json")
    save_asset_index([a], path)
    loaded = load_asset_index(path)
    assert len(loaded) == 1
    assert loaded[0]["asset_id"] == "XAPACK00:0"


def test_build_full_disc_asset_index_smoke_test_on_undersized_disc():
    """build_full_disc_asset_index scans the REAL 43-pack catalog by
    real LBA range (up to ~183635), so a small synthetic buffer covers
    none of those real ranges -- this only checks it degrades to an
    empty list rather than crashing on out-of-range reads. Real
    coverage is exercised by the live-anchor tests above, which build
    a synthetic pack at its true real-disc LBA offset."""
    pack_bytes = _build_synthetic_pack({ch: 5 for ch in range(8)})
    index = build_full_disc_asset_index(pack_bytes)
    assert index == []


# --- decode_audio_asset / export_audio_asset_wav (Phase 21 playback backend) ---


def test_decode_audio_asset_matches_structural_sample_count():
    disc, pack_start = _disc_with_synthetic_pack_at_real_lba("DAT/XA1/XAPACK00.BIN", {ch: 6 for ch in range(8)})
    resolution = resolve_audio_asset(disc, pack_start + 3)
    asset = resolution.asset
    assert asset is not None
    assert asset.decode_confidence == DecoderConfidence.REFERENCE_VERIFIED
    assert asset.decode_supported is True

    sr, channels, pcm = decode_audio_asset(disc, asset)
    assert sr == 37800
    assert channels == 2
    assert len(pcm) // 2 == asset.pcm_sample_count  # 2 bytes/sample (16-bit)


def test_decode_audio_asset_raises_for_asset_with_no_real_pack():
    fmt = format_from_coding_info(1)
    fake_asset = AudioAsset("DAT/XA1/NOPE.BIN", 0, 10, 20, 5, fmt, 1.0, StreamConfidence.CANDIDATE)
    import pytest

    with pytest.raises(ValueError):
        decode_audio_asset(b"", fake_asset)


def test_export_audio_asset_wav_writes_a_valid_wav(tmp_path):
    disc, pack_start = _disc_with_synthetic_pack_at_real_lba("DAT/XA1/XAPACK00.BIN", {ch: 6 for ch in range(8)})
    resolution = resolve_audio_asset(disc, pack_start + 3)
    asset = resolution.asset

    out_path = str(tmp_path / "asset.wav")
    export_audio_asset_wav(disc, asset, out_path)

    import wave
    with wave.open(out_path, "rb") as w:
        assert w.getframerate() == 37800
        assert w.getnchannels() == 2
        assert w.getnframes() == asset.pcm_sample_count // 2
