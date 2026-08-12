import struct

from gcrts.xa_decoder_verify import (
    GOLDEN_ASSET_VERIFICATIONS,
    GOLDEN_AUDIO_FIXTURE,
    DecoderConfidence,
    GoldenAudioFixture,
    decoder_verification_status,
    verify_decoder,
    verify_golden_fixture,
)


def _pcm(*samples: int) -> bytes:
    return b"".join(struct.pack("<h", s) for s in samples)


# --- verify_decoder --------------------------------------------------------


def test_verify_decoder_no_reference_is_structurally_valid():
    result = verify_decoder("test", 37800, 2, _pcm(1, 2, 3, 4))
    assert result.confidence == DecoderConfidence.STRUCTURALLY_VALID
    assert result.exact_pcm_match is False
    assert result.sample_count_reference is None


def test_verify_decoder_exact_match_is_reference_verified():
    pcm = _pcm(1, 2, 3, 4, 5, 6)
    result = verify_decoder("test", 37800, 2, pcm, 37800, 2, pcm)
    assert result.confidence == DecoderConfidence.REFERENCE_VERIFIED
    assert result.exact_pcm_match is True
    assert result.mismatch_count == 0
    assert result.first_mismatch_sample is None
    assert result.sample_count_match is True
    assert result.channel_count_match is True
    assert result.sample_rate_match is True


def test_verify_decoder_mismatch_reports_first_index_and_max_error():
    internal = _pcm(1, 2, 3, 4)
    reference = _pcm(1, 2, 999, 4)
    result = verify_decoder("test", 37800, 2, internal, 37800, 2, reference)
    assert result.exact_pcm_match is False
    assert result.confidence == DecoderConfidence.UNVERIFIED
    assert result.mismatch_count == 1
    assert result.first_mismatch_sample == 2
    assert result.max_absolute_error == 996


def test_verify_decoder_sample_rate_mismatch_fails_exact_match_even_if_samples_equal():
    pcm = _pcm(1, 2, 3, 4)
    result = verify_decoder("test", 37800, 2, pcm, 18900, 2, pcm)
    assert result.sample_rate_match is False
    assert result.exact_pcm_match is False


def test_verify_decoder_channel_count_mismatch_fails_exact_match():
    pcm = _pcm(1, 2, 3, 4)
    result = verify_decoder("test", 37800, 2, pcm, 37800, 1, pcm)
    assert result.channel_count_match is False
    assert result.exact_pcm_match is False


def test_verify_decoder_sample_count_mismatch_detected():
    internal = _pcm(1, 2, 3, 4)
    reference = _pcm(1, 2, 3, 4, 5, 6)
    result = verify_decoder("test", 37800, 2, internal, 37800, 2, reference)
    assert result.sample_count_match is False
    assert result.sample_count_internal == 4
    assert result.sample_count_reference == 6


def test_verify_decoder_to_dict_round_trips_key_fields():
    pcm = _pcm(1, 2)
    result = verify_decoder("myasset", 37800, 2, pcm, 37800, 2, pcm)
    d = result.to_dict()
    assert d["asset_id"] == "myasset"
    assert d["confidence"] == "REFERENCE_VERIFIED"
    assert d["exact_pcm_match"] is True


# --- decoder_verification_status / GOLDEN_ASSET_VERIFICATIONS --------------


def test_golden_asset_verifications_cover_stereo_and_mono():
    stereo_seen = any(stereo for _, stereo, _, _ in GOLDEN_ASSET_VERIFICATIONS)
    mono_seen = any(not stereo for _, stereo, _, _ in GOLDEN_ASSET_VERIFICATIONS)
    assert stereo_seen and mono_seen


def test_golden_asset_verifications_all_zero_mismatches():
    for asset_id, _, _, mismatches in GOLDEN_ASSET_VERIFICATIONS:
        assert mismatches == 0, f"{asset_id} had {mismatches} mismatches"


def test_golden_asset_verifications_span_multiple_packs():
    packs = {asset_id.split(":")[0] for asset_id, _, _, _ in GOLDEN_ASSET_VERIFICATIONS}
    assert len(packs) >= 3


def test_decoder_verification_status_is_reference_verified():
    assert decoder_verification_status() == DecoderConfidence.REFERENCE_VERIFIED


# --- GoldenAudioFixture -----------------------------------------------------


def test_golden_audio_fixture_is_the_known_dialogue_cue():
    """The golden asset must be the same one already cross-validated
    elsewhere in this project (KNOWN_CUE_SOURCES[127]: xa_channel=7,
    source XAPACK08.BIN) -- not an arbitrary asset."""
    assert GOLDEN_AUDIO_FIXTURE.asset_id == "XAPACK08:7"
    assert GOLDEN_AUDIO_FIXTURE.pack_path == "DAT/XA1/XAPACK08.BIN"
    assert GOLDEN_AUDIO_FIXTURE.channel_number == 7


def test_golden_audio_fixture_no_raw_audio_embedded():
    """Only hashes/metadata -- never raw copyrighted game audio bytes."""
    d = GOLDEN_AUDIO_FIXTURE.to_dict()
    for value in d.values():
        assert not isinstance(value, (bytes, bytearray))
    assert len(GOLDEN_AUDIO_FIXTURE.raw_sha256) == 64
    assert len(GOLDEN_AUDIO_FIXTURE.pcm_sha256) == 64


def test_verify_golden_fixture_true_for_matching_bytes():
    fixture = GoldenAudioFixture(
        asset_id="x", pack_path="p", channel_number=0, first_lba=0, eof_lba=1, sector_count=1,
        sample_rate_hz=37800, channels=2, duration_seconds=1.0,
        raw_sha256=__import__("hashlib").sha256(b"RAW").hexdigest(),
        pcm_sha256=__import__("hashlib").sha256(b"PCM").hexdigest(),
        pcm_sample_count=1, verification_source="test",
    )
    assert verify_golden_fixture(b"RAW", b"PCM", fixture) is True
    assert verify_golden_fixture(b"WRONG", b"PCM", fixture) is False
    assert verify_golden_fixture(b"RAW", b"WRONG", fixture) is False
