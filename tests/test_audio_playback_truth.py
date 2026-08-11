from gcrts.audio_playback_truth import (
    OBSERVED_SETMODE_VALUE,
    READS_COMMAND,
    SETMODE_CDDA_BIT,
    SETMODE_XA_ADPCM_BIT,
    SETMODE_XA_FILTER_BIT,
    AudiblePlaybackState,
    observed_setmode_has_xa_audio_bits,
    raw_engine_state_meaning,
)


def test_reads_command_is_the_publicly_documented_value():
    """0x1B, per psx-spx: the documented command for XA-ADPCM playback --
    never observed live by this project, recorded as a fact to search
    for, not a guess."""
    assert READS_COMMAND == 0x1B


def test_observed_setmode_value_is_the_real_captured_byte():
    assert OBSERVED_SETMODE_VALUE == 0x01


def test_observed_setmode_only_has_cdda_bit_set():
    assert OBSERVED_SETMODE_VALUE & SETMODE_CDDA_BIT
    assert not (OBSERVED_SETMODE_VALUE & SETMODE_XA_ADPCM_BIT)
    assert not (OBSERVED_SETMODE_VALUE & SETMODE_XA_FILTER_BIT)


def test_observed_setmode_has_xa_audio_bits_is_false():
    """Decisive: the one real Setmode value ever captured is NOT
    configured for XA-ADPCM audio -- the repeating command cycle this
    project traced is a data read loop, not the audio path."""
    assert observed_setmode_has_xa_audio_bits() is False


def test_raw_engine_state_meaning_is_honestly_unknown():
    assert raw_engine_state_meaning() == "UNKNOWN"


def test_audible_playback_state_has_no_confirmed_states_yet():
    """Regression: this project must not invent an AUDIBLE_XA (or
    similar) enum value without live evidence backing it. Only UNKNOWN
    should exist until a future milestone actually finds the real
    signal."""
    assert list(AudiblePlaybackState) == [AudiblePlaybackState.UNKNOWN]
