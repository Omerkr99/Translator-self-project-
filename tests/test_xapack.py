import struct

from gcrts.xapack import (
    AUDIO_EOF_SUBMODE,
    AUDIO_SUBMODE,
    FORM2_DATA_SIZE,
    SAMPLES_PER_CHANNEL_PER_SECTOR,
    XA_ADPCM_PAYLOAD_SIZE,
    AudioAsset,
    PackFormatClassification,
    SectorClass,
    StreamConfidence,
    XaChannelStream,
    XaDecoderState,
    XaStreamFormat,
    audio_asset_from_channel_stream,
    classify_pack_format,
    classify_sector_submode,
    decode_channel_to_pcm,
    decode_xa_sector_payload,
    extract_channel_raw,
    fingerprint_bytes,
    format_from_coding_info,
    lba_falls_within_stream,
    mark_live_cross_validated,
    parse_pack_channel_streams,
    write_wav,
)
from gcrts.xapack_catalog import XaPackCatalogEntry

SYNC = b"\x00" + b"\xff" * 10 + b"\x00"
SECTOR_SIZE = 2352


def _fake_sector(file_number=1, channel_number=0, submode=0x64, coding_info=0x01, payload: bytes | None = None) -> bytes:
    header = bytes(4)
    subheader = bytes([file_number, channel_number, submode, coding_info]) + bytes(4)
    if payload is None:
        payload = bytes(SECTOR_SIZE - 12 - 4 - 8)
    else:
        payload = payload + bytes(SECTOR_SIZE - 12 - 4 - 8 - len(payload))
    return SYNC + header + subheader + payload


def _build_synthetic_pack(channel_lengths: dict[int, int], file_number: int = 1, coding_info: int = 0x01) -> bytes:
    """Builds a synthetic disc buffer (absolute LBA 0 == byte 0)
    reproducing this project's own real-disc findings: strict 8-way
    round-robin interleave, each channel ending on its own real EOF
    sector, silence padding after, one terminator sector at the very
    end."""
    max_len = max(channel_lengths.values())
    sectors: list[bytes] = []
    for row in range(max_len * 8):
        ch = row % 8
        idx_within_channel = row // 8
        ch_len = channel_lengths.get(ch, 0)
        if idx_within_channel < ch_len:
            is_last = idx_within_channel == ch_len - 1
            submode = AUDIO_EOF_SUBMODE if is_last else AUDIO_SUBMODE
            sectors.append(_fake_sector(file_number=file_number, channel_number=ch, submode=submode, coding_info=coding_info))
        else:
            sectors.append(_fake_sector(file_number=0, channel_number=ch, submode=0x00, coding_info=0x00))
    sectors.append(_fake_sector(file_number=0, channel_number=0, submode=0x80, coding_info=0x00))
    return b"".join(sectors)


def _pack_entry(disc_bytes: bytes, path="DAT/XA1/XAPACKTEST.BIN", index=0) -> XaPackCatalogEntry:
    sector_count = len(disc_bytes) // SECTOR_SIZE
    return XaPackCatalogEntry(index=index, disc_path=path, start_lba=0, end_lba=sector_count, sector_count=sector_count, byte_size=len(disc_bytes))


# --- classify_sector_submode -------------------------------------------------


def test_classify_sector_submode_audio():
    assert classify_sector_submode(0x64) == SectorClass.AUDIO


def test_classify_sector_submode_audio_eof():
    assert classify_sector_submode(0xE4) == SectorClass.AUDIO_EOF


def test_classify_sector_submode_silence_padding():
    assert classify_sector_submode(0x00) == SectorClass.SILENCE_PADDING


def test_classify_sector_submode_terminator():
    assert classify_sector_submode(0x80) == SectorClass.TERMINATOR


def test_classify_sector_submode_other_for_unexpected_audio_combo():
    assert classify_sector_submode(0x24) == SectorClass.OTHER  # Audio but not Form2 -- not the real pattern


# --- format_from_coding_info --------------------------------------------------


def test_format_from_coding_info_real_disc_value():
    fmt = format_from_coding_info(0x01)
    assert fmt.stereo is True
    assert fmt.sample_rate_hz == 37800
    assert fmt.bits_per_sample == 4
    assert fmt.emphasis is False
    assert fmt.channel_count == 2


def test_format_from_coding_info_mono_18900_8bit():
    fmt = format_from_coding_info(0b01010110)  # stereo=0(mono), rate=1(18900), bits=1(8bit), emphasis=1
    assert fmt.stereo is False
    assert fmt.sample_rate_hz == 18900
    assert fmt.bits_per_sample == 8
    assert fmt.emphasis is True
    assert fmt.channel_count == 1


# --- classify_pack_format ------------------------------------------------------


def test_classify_pack_format_standard_xa_for_real_pattern():
    disc = _build_synthetic_pack({ch: 10 for ch in range(8)})
    pack = _pack_entry(disc)
    result = classify_pack_format(disc, pack.start_lba, pack.end_lba)
    assert result.classification == PackFormatClassification.STANDARD_XA
    assert result.audio_eof_sector_count == 8
    assert result.terminator_sector_count == 1
    assert result.coding_info_values_seen == (1,)


def test_classify_pack_format_unknown_for_no_audio():
    disc = b"".join(_fake_sector(submode=0x00) for _ in range(5))
    result = classify_pack_format(disc, 0, 5)
    assert result.classification == PackFormatClassification.UNKNOWN


def test_classify_pack_format_mixed_for_reserved_coding_info():
    disc = _fake_sector(submode=0x64, coding_info=0b00110001)  # bits_field=3, reserved
    result = classify_pack_format(disc, 0, 1)
    assert result.classification == PackFormatClassification.MIXED


def test_classify_pack_format_xa_like_for_unexpected_submode_mixed_in():
    audio = _fake_sector(submode=0x64)
    weird = _fake_sector(submode=0x24, channel_number=1)  # Audio without Form2 -- OTHER
    disc = audio + weird
    result = classify_pack_format(disc, 0, 2)
    assert result.classification == PackFormatClassification.XA_LIKE


# --- parse_pack_channel_streams -----------------------------------------------


def test_parse_pack_channel_streams_finds_all_8_channels_with_correct_bounds():
    disc = _build_synthetic_pack({0: 5, 1: 3, 2: 5, 3: 5, 4: 5, 5: 5, 6: 5, 7: 5})
    pack = _pack_entry(disc)
    streams = parse_pack_channel_streams(disc, pack)
    assert [s.channel_number for s in streams] == list(range(8))
    ch1 = streams[1]
    assert ch1.first_lba == 1
    assert ch1.eof_lba == 1 + 8 * 2  # 3rd occurrence of channel 1 (index 2) at row 1+8*2=17
    assert ch1.sector_count == 3
    assert ch1.confidence == StreamConfidence.STRUCTURALLY_CONFIRMED


def test_parse_pack_channel_streams_handles_fewer_than_8_channels():
    """Real, confirmed variation on the disc (XAPACK42.BIN uses only 7)."""
    disc = _build_synthetic_pack({ch: 4 for ch in range(7)})
    pack = _pack_entry(disc)
    streams = parse_pack_channel_streams(disc, pack)
    assert [s.channel_number for s in streams] == list(range(7))


def test_parse_pack_channel_streams_duration_matches_sample_math():
    disc = _build_synthetic_pack({ch: 18 for ch in range(8)})
    pack = _pack_entry(disc)
    streams = parse_pack_channel_streams(disc, pack)
    stream = streams[0]
    expected = stream.sector_count * SAMPLES_PER_CHANNEL_PER_SECTOR / stream.format.sample_rate_hz
    assert stream.duration_seconds == expected


# --- lba_falls_within_stream / mark_live_cross_validated ----------------------


def test_lba_falls_within_stream_true_for_bounded_stream():
    stream = XaChannelStream("p", 0, 1, 3, first_lba=10, eof_lba=20, sector_count=2,
                              format=format_from_coding_info(1), confidence=StreamConfidence.STRUCTURALLY_CONFIRMED)
    assert lba_falls_within_stream(stream, 15) is True
    assert lba_falls_within_stream(stream, 9) is False
    assert lba_falls_within_stream(stream, 21) is False


def test_mark_live_cross_validated_upgrades_confidence_only():
    stream = XaChannelStream("p", 0, 1, 3, first_lba=10, eof_lba=20, sector_count=2,
                              format=format_from_coding_info(1), confidence=StreamConfidence.STRUCTURALLY_CONFIRMED)
    upgraded = mark_live_cross_validated(stream)
    assert upgraded.confidence == StreamConfidence.LIVE_CROSS_VALIDATED
    assert upgraded.channel_number == stream.channel_number
    assert upgraded.first_lba == stream.first_lba


# --- AudioAsset ----------------------------------------------------------------


def test_audio_asset_from_channel_stream_and_stable_id():
    stream = XaChannelStream("DAT/XA1/XAPACK08.BIN", 8, 1, 7, first_lba=126225, eof_lba=129273, sector_count=382,
                              format=format_from_coding_info(1), confidence=StreamConfidence.LIVE_CROSS_VALIDATED)
    asset = audio_asset_from_channel_stream(stream)
    assert asset.asset_id == "XAPACK08:7"
    assert asset.confidence == StreamConfidence.LIVE_CROSS_VALIDATED
    d = asset.to_dict()
    assert d["asset_id"] == "XAPACK08:7"
    assert d["stereo"] is True


def test_audio_asset_id_stable_across_equal_reconstruction():
    stream_a = XaChannelStream("DAT/XA2/XAPACK30.BIN", 30, 1, 2, first_lba=1, eof_lba=5, sector_count=5,
                                format=format_from_coding_info(1), confidence=StreamConfidence.CANDIDATE)
    stream_b = XaChannelStream("DAT/XA2/XAPACK30.BIN", 30, 1, 2, first_lba=999, eof_lba=1999, sector_count=100,
                                format=format_from_coding_info(1), confidence=StreamConfidence.CANDIDATE)
    assert audio_asset_from_channel_stream(stream_a).asset_id == audio_asset_from_channel_stream(stream_b).asset_id


# --- extract_channel_raw -------------------------------------------------------


def test_extract_channel_raw_returns_exactly_sector_count_times_payload_size():
    disc = _build_synthetic_pack({ch: 6 for ch in range(8)})
    pack = _pack_entry(disc)
    streams = parse_pack_channel_streams(disc, pack)
    stream = streams[3]
    raw = extract_channel_raw(disc, stream)
    assert len(raw) == stream.sector_count * XA_ADPCM_PAYLOAD_SIZE


def test_extract_channel_raw_excludes_other_channels_content():
    """Regression for a real bug caught during this milestone: build
    two channels with visibly different payload bytes and confirm
    extraction never mixes them."""
    ch0_payload = bytes([0xAA]) * FORM2_DATA_SIZE
    ch1_payload = bytes([0xBB]) * FORM2_DATA_SIZE
    sectors = [
        _fake_sector(channel_number=0, submode=AUDIO_EOF_SUBMODE, payload=ch0_payload),
        _fake_sector(channel_number=1, submode=AUDIO_EOF_SUBMODE, payload=ch1_payload),
        _fake_sector(channel_number=0, submode=0x80, coding_info=0),
    ]
    disc = b"".join(sectors)
    pack = _pack_entry(disc)
    streams = parse_pack_channel_streams(disc, pack)
    ch0 = next(s for s in streams if s.channel_number == 0)
    raw0 = extract_channel_raw(disc, ch0)
    assert raw0 == bytes([0xAA]) * XA_ADPCM_PAYLOAD_SIZE


# --- ADPCM decode ---------------------------------------------------------------
#
# This layout (header byte positions, nibble/channel assignment) was
# reverse-engineered against FFmpeg's independent, open-source
# adpcm_xa decoder and verified sample-for-sample identical (100.0000%,
# zero mismatches) against real disc audio across 5 real assets
# (stereo and mono) -- see docs/audio/XA_DECODER_VERIFICATION.md. These
# fixtures reproduce the real header layout: 4 bytes unused (redundant
# copy), then 8 bytes as 4 (low-header, high-header) pairs, then 4
# more unused bytes, then 112 data bytes.


def _group_with_headers(low_range: int, low_filt: int, high_range: int, high_filt: int, low_nibble: int, high_nibble: int) -> bytes:
    low_header = (low_filt << 4) | low_range
    high_header = (high_filt << 4) | high_range
    leading = bytes(4)
    header_pairs = bytes([low_header, high_header] * 4)  # 4 iterations, same pair each
    trailing = bytes(4)
    nibble_byte = (high_nibble << 4) | low_nibble
    data = bytes([nibble_byte] * 112)
    return leading + header_pairs + trailing + data


def test_decode_xa_sector_payload_deterministic_filter_zero():
    # range=12 -> shift=12-12=0; nibble=1 -> t=1; filter=0 -> pred=0 -> sample=1*(1<<0)=1
    payload = _group_with_headers(12, 0, 12, 0, 1, 1) * 18
    state = XaDecoderState()
    left, right = decode_xa_sector_payload(payload, state)
    assert len(left) == SAMPLES_PER_CHANNEL_PER_SECTOR
    assert len(right) == SAMPLES_PER_CHANNEL_PER_SECTOR
    assert set(left) == {1}
    assert set(right) == {1}


def test_decode_xa_sector_payload_negative_nibble_clamped():
    # range=0 -> shift=12; nibble=0b1000=8 -> signed -8; filter=0 -> pred=0
    # raw = -8*(1<<12) = -32768, exactly the int16 clamp boundary.
    payload = _group_with_headers(0, 0, 0, 0, 8, 8) * 18
    state = XaDecoderState()
    left, right = decode_xa_sector_payload(payload, state)
    assert set(left) == {-32768}
    assert set(right) == {-32768}


def test_decode_xa_sector_payload_left_right_independent_history():
    """Regression for a real bug this milestone found and fixed: Left
    and Right must decode from the SAME data byte's low/high nibble
    with INDEPENDENT history chains, not shared or cross-contaminated.
    Different nibble values with filter>0 (real history feedback) must
    diverge the two channels' output over successive samples."""
    payload = _group_with_headers(12, 1, 12, 1, 1, 7) * 18  # low_nibble=1, high_nibble=7, filter=1 (k0=60,k1=0)
    state = XaDecoderState()
    left, right = decode_xa_sector_payload(payload, state)
    assert left[0] != right[0]  # different nibble values -> different first sample
    assert left[:5] != right[:5]  # history evolves differently per channel


def test_decode_xa_sector_payload_mono_continues_single_history_chain():
    """Mono has no L/R split: both nibble-halves of each iteration
    continue the SAME history chain into one output stream (per
    FFmpeg's own xa_decode -- verified against the real mono exception
    on this disc, XAPACK42.BIN channel 6)."""
    payload = _group_with_headers(12, 1, 12, 1, 1, 1) * 18
    state = XaDecoderState()
    mono, empty = decode_xa_sector_payload(payload, state, stereo=False)
    assert empty == []
    assert len(mono) == SAMPLES_PER_CHANNEL_PER_SECTOR * 2  # 4032: no L/R split


def test_decode_xa_sector_payload_history_persists_across_sectors():
    """ADPCM is stateful -- a fresh XaDecoderState vs. a state carried
    over from a prior sector must produce different output once
    filter feedback is active, proving history genuinely threads
    across sector boundaries (not reset each call)."""
    payload = _group_with_headers(12, 1, 12, 1, 3, 3) * 18
    fresh_state = XaDecoderState()
    left_fresh, _ = decode_xa_sector_payload(payload, fresh_state)

    warmed_state = XaDecoderState()
    decode_xa_sector_payload(_group_with_headers(12, 1, 12, 1, 5, 5) * 18, warmed_state)  # prime history
    left_warmed, _ = decode_xa_sector_payload(payload, warmed_state)

    assert left_fresh[0] != left_warmed[0]


def test_decode_xa_sector_payload_rejects_short_payload():
    import pytest
    with pytest.raises(ValueError):
        decode_xa_sector_payload(b"\x00" * 100, XaDecoderState())


def test_decode_channel_to_pcm_sample_count_matches_math():
    disc = _build_synthetic_pack({ch: 18 for ch in range(8)}, coding_info=0x01)
    pack = _pack_entry(disc)
    streams = parse_pack_channel_streams(disc, pack)
    stream = streams[0]
    sr, channels, pcm = decode_channel_to_pcm(disc, stream)
    assert sr == 37800
    assert channels == 2
    expected_bytes = stream.sector_count * SAMPLES_PER_CHANNEL_PER_SECTOR * 2 * 2  # 2 channels x 2 bytes/sample
    assert len(pcm) == expected_bytes


# --- write_wav -------------------------------------------------------------------


def test_write_wav_produces_valid_riff_header(tmp_path):
    pcm = struct.pack("<hh", 100, -100) * 10
    out = tmp_path / "test.wav"
    write_wav(str(out), 37800, 2, pcm)
    data = out.read_bytes()
    assert data[0:4] == b"RIFF"
    assert data[8:12] == b"WAVE"
    assert data[12:16] == b"fmt "
    channels = struct.unpack("<H", data[22:24])[0]
    sample_rate = struct.unpack("<I", data[24:28])[0]
    assert channels == 2
    assert sample_rate == 37800
    assert data[36:40] == b"data"
    data_size = struct.unpack("<I", data[40:44])[0]
    assert data_size == len(pcm)
    assert data[44:] == pcm


# --- fingerprint_bytes -----------------------------------------------------------


def test_fingerprint_bytes_deterministic_and_distinguishes_content():
    a = fingerprint_bytes(b"hello")
    b = fingerprint_bytes(b"hello")
    c = fingerprint_bytes(b"world")
    assert a == b
    assert a != c
    assert len(a) == 64  # sha256 hex digest length
