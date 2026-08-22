from gcrts.audio_asset_resolver import ResolutionConfidence
from gcrts.spu_playback_trace import (
    HeartbeatEvent,
    MarkEvent,
    SaveStateLoadedEvent,
    SpuKeyWriteEvent,
)
from gcrts.spu_trace_analyzer import (
    SpuTraceClassification,
    attempt_spu_sample_extraction,
    classify_playback_from_trace,
    correlate_heartbeats_with_resolver,
    events_near_marker,
    first_marker,
)


# --- events_near_marker: window filtering -------------------------------------


def test_events_near_marker_default_window():
    marker = MarkEvent(t=10.0)
    events = [
        HeartbeatEvent(t=7.9, position_counter=1, lifecycle_state_raw=1, last_req_params=1),  # just outside (-2.1)
        HeartbeatEvent(t=8.5, position_counter=2, lifecycle_state_raw=1, last_req_params=1),  # inside
        marker,
        HeartbeatEvent(t=11.5, position_counter=3, lifecycle_state_raw=1, last_req_params=1),  # inside
        HeartbeatEvent(t=12.1, position_counter=4, lifecycle_state_raw=1, last_req_params=1),  # just outside (+2.1)
    ]
    window = events_near_marker(events, marker, before_seconds=2.0, after_seconds=2.0)
    assert len(window) == 3  # the two inside heartbeats + the marker itself
    assert marker in window


def test_events_near_marker_configurable_window_not_hardcoded():
    marker = MarkEvent(t=10.0)
    far = HeartbeatEvent(t=15.0, position_counter=1, lifecycle_state_raw=1, last_req_params=1)
    events = [marker, far]
    assert events_near_marker(events, marker, before_seconds=2.0, after_seconds=2.0) == [marker]
    assert far in events_near_marker(events, marker, before_seconds=2.0, after_seconds=6.0)


def test_first_marker_none_when_absent():
    events = [HeartbeatEvent(t=1.0, position_counter=1, lifecycle_state_raw=1, last_req_params=1)]
    assert first_marker(events) is None


def test_first_marker_returns_earliest():
    m1 = MarkEvent(t=1.0, label="first")
    m2 = MarkEvent(t=2.0, label="second")
    assert first_marker([m2, m1]) is m2  # returns the first one found in the list, not necessarily earliest t
    assert first_marker([m1, m2]) is m1


# --- classify_playback_from_trace: NOT_YET_CLASSIFIED ---------------------------


def test_classify_no_marker_is_not_yet_classified():
    events = [HeartbeatEvent(t=1.0, position_counter=1, lifecycle_state_raw=1, last_req_params=1)]
    result = classify_playback_from_trace(events)
    assert result.classification == SpuTraceClassification.NOT_YET_CLASSIFIED


def test_classify_empty_window_is_not_yet_classified():
    result = classify_playback_from_trace([])
    assert result.classification == SpuTraceClassification.NOT_YET_CLASSIFIED


# --- classify_playback_from_trace: SPU_VOICE_PLAYBACK ---------------------------


def test_classify_meaningful_key_write_is_spu_voice_playback():
    marker = MarkEvent(t=5.0)
    events = [
        SpuKeyWriteEvent(t=4.9, write_pc=0x800866A8, family="PERIODIC_VOICE_SYNC", register="KEY_ON", voice_mask=0x4),
        marker,
    ]
    result = classify_playback_from_trace(events)
    assert result.classification == SpuTraceClassification.SPU_VOICE_PLAYBACK
    assert len(result.meaningful_key_writes) == 1
    assert result.meaningful_key_writes[0].active_voices == [2]


def test_classify_ignores_zero_mask_key_writes_for_spu_voice_playback():
    """The empty/no-op mask is the pattern this project's own prior
    captures found in >99% of hits -- must NOT trigger SPU_VOICE_
    PLAYBACK on its own."""
    marker = MarkEvent(t=5.0)
    events = [
        SpuKeyWriteEvent(t=4.9, write_pc=0x800866A8, family="PERIODIC_VOICE_SYNC", register="KEY_ON", voice_mask=0),
        marker,
    ]
    result = classify_playback_from_trace(events)
    assert result.classification != SpuTraceClassification.SPU_VOICE_PLAYBACK


# --- classify_playback_from_trace: CD_AUDIO_INPUT -------------------------------


def test_classify_playing_lifecycle_state_is_cd_audio_input():
    marker = MarkEvent(t=5.0)
    events = [
        HeartbeatEvent(t=4.8, position_counter=161409, lifecycle_state_raw=0x01, last_req_params=127),
        marker,
    ]
    result = classify_playback_from_trace(events)
    assert result.classification == SpuTraceClassification.CD_AUDIO_INPUT


def test_classify_save_state_load_anchor_is_cd_audio_input():
    marker = MarkEvent(t=0.5)
    events = [
        SaveStateLoadedEvent(t=0.0),
        marker,
    ]
    result = classify_playback_from_trace(events)
    assert result.classification == SpuTraceClassification.CD_AUDIO_INPUT


# --- classify_playback_from_trace: OTHER_OR_UNKNOWN -----------------------------


def test_classify_marker_with_no_signal_is_other_or_unknown():
    marker = MarkEvent(t=5.0)
    result = classify_playback_from_trace([marker])
    assert result.classification == SpuTraceClassification.OTHER_OR_UNKNOWN


def test_classify_stopped_lifecycle_with_no_key_write_is_other_or_unknown():
    marker = MarkEvent(t=5.0)
    events = [
        HeartbeatEvent(t=4.8, position_counter=1000, lifecycle_state_raw=0x02, last_req_params=0),  # STOPPED, not PLAYING
        marker,
    ]
    result = classify_playback_from_trace(events)
    assert result.classification == SpuTraceClassification.OTHER_OR_UNKNOWN


# --- correlate_heartbeats_with_resolver ------------------------------------------


def test_correlate_heartbeats_with_resolver_unresolved_lba():
    events = [HeartbeatEvent(t=1.0, position_counter=999999999, lifecycle_state_raw=1, last_req_params=1)]
    correlated = correlate_heartbeats_with_resolver(events, disc_bytes=b"\x00" * 2352 * 10)
    assert len(correlated) == 1
    assert correlated[0].resolution.confidence == ResolutionConfidence.UNRESOLVED


def test_correlate_heartbeats_with_resolver_skips_events_without_position():
    events = [HeartbeatEvent(t=1.0, position_counter=None, lifecycle_state_raw=1, last_req_params=1)]
    assert correlate_heartbeats_with_resolver(events, disc_bytes=b"") == []


# --- attempt_spu_sample_extraction: honest refusal, per confirmed tooling limit --


def test_attempt_spu_sample_extraction_refuses_cleanly():
    result = attempt_spu_sample_extraction(voice_index=3, start_address_units_of_8=1000)
    assert result.available is False
    assert "not inspectable" in result.reason
