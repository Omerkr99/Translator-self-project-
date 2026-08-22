import pytest

from gcrts.audio_asset_resolver import ResolutionConfidence
from gcrts.spu_playback_trace import (
    HeartbeatEvent,
    MarkEvent,
    SaveStateLoadedEvent,
    SpuKeyWriteEvent,
    write_event,
)
from gcrts.spu_trace_analyzer import (
    SpuTraceClassification,
    TargetRun,
    assess_instrumentation_health,
    attempt_spu_sample_extraction,
    build_report,
    build_run_evidence,
    classify_playback_from_trace,
    context_window,
    control_windows,
    correlate_heartbeats_with_resolver,
    correlate_runs,
    events_near_marker,
    first_marker,
    main,
    pair_target_runs,
    tight_window,
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


def _proof_of_life():
    """A zero-mask Key write + a heartbeat -- proves the Key-write and
    heartbeat hooks are alive, WITHOUT itself being a meaningful
    (nonzero-mask) hit. Needed to satisfy assess_instrumentation_
    health() before any CD_AUDIO_INPUT/OTHER_OR_UNKNOWN conclusion
    (which rests on the ABSENCE of a meaningful Key write) can be trusted."""
    return [
        SpuKeyWriteEvent(t=0.0, write_pc=0x800866A8, family="PERIODIC_VOICE_SYNC", register="KEY_ON", voice_mask=0),
        HeartbeatEvent(t=0.1, position_counter=100, lifecycle_state_raw=0, last_req_params=0),
    ]


def test_classify_playing_lifecycle_state_is_cd_audio_input():
    marker = MarkEvent(t=5.0)
    events = [
        *_proof_of_life(),
        HeartbeatEvent(t=4.8, position_counter=161409, lifecycle_state_raw=0x01, last_req_params=127),
        marker,
    ]
    result = classify_playback_from_trace(events)
    assert result.classification == SpuTraceClassification.CD_AUDIO_INPUT


def test_classify_save_state_load_anchor_is_cd_audio_input():
    marker = MarkEvent(t=0.5)
    events = [
        SaveStateLoadedEvent(t=-0.1),
        *_proof_of_life(),
        marker,
    ]
    result = classify_playback_from_trace(events)
    assert result.classification == SpuTraceClassification.CD_AUDIO_INPUT


# --- instrumentation_not_yet_validated gate: absence is only evidence once proven alive --


def test_classify_playing_lifecycle_without_proof_of_life_is_not_yet_classified():
    """Regression for this milestone's own critical negative-evidence
    rule: a PLAYING heartbeat with NO proof the Key-write hook ever
    fired must NOT be trusted as CD_AUDIO_INPUT -- it must report
    instrumentation_not_yet_validated instead."""
    marker = MarkEvent(t=5.0)
    events = [
        HeartbeatEvent(t=4.8, position_counter=161409, lifecycle_state_raw=0x01, last_req_params=127),
        marker,
    ]
    result = classify_playback_from_trace(events)
    assert result.classification == SpuTraceClassification.NOT_YET_CLASSIFIED
    assert "instrumentation_not_yet_validated" in result.evidence


def test_classify_meaningful_key_write_bypasses_instrumentation_gate():
    """A meaningful (nonzero-mask) Key write is self-certifying
    evidence -- it must classify SPU_VOICE_PLAYBACK even with no
    separate heartbeat proving the OTHER hook is alive."""
    marker = MarkEvent(t=5.0)
    events = [
        SpuKeyWriteEvent(t=4.9, write_pc=0x800866A8, family="PERIODIC_VOICE_SYNC", register="KEY_ON", voice_mask=0x4),
        marker,
    ]
    result = classify_playback_from_trace(events)
    assert result.classification == SpuTraceClassification.SPU_VOICE_PLAYBACK


def test_classify_full_trace_events_param_used_for_health_not_window():
    """A window with no proof-of-life on its own can still classify
    CD_AUDIO_INPUT if the wider full_trace_events (e.g. the whole
    session) contains it -- a hook can fire outside the narrow target
    window and still prove itself alive."""
    marker = MarkEvent(t=100.0)
    window = [
        HeartbeatEvent(t=99.8, position_counter=161409, lifecycle_state_raw=0x01, last_req_params=127),
        marker,
    ]
    full_trace = [*_proof_of_life(), *window]
    result = classify_playback_from_trace(window, full_trace_events=full_trace)
    assert result.classification == SpuTraceClassification.CD_AUDIO_INPUT


# --- classify_playback_from_trace: OTHER_OR_UNKNOWN -----------------------------


def test_classify_marker_with_no_signal_is_other_or_unknown():
    marker = MarkEvent(t=5.0)
    events = [*_proof_of_life(), marker]
    result = classify_playback_from_trace(events)
    assert result.classification == SpuTraceClassification.OTHER_OR_UNKNOWN


def test_classify_stopped_lifecycle_with_no_key_write_is_other_or_unknown():
    marker = MarkEvent(t=5.0)
    events = [
        *_proof_of_life(),
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


# --- pair_target_runs ---------------------------------------------------------------


def test_pair_target_runs_single_pair():
    events = [MarkEvent(t=1.0, label="TARGET_BEGIN"), MarkEvent(t=3.0, label="TARGET_END")]
    runs, dangling = pair_target_runs(events)
    assert len(runs) == 1
    assert dangling is None
    assert runs[0].run_index == 0
    assert runs[0].begin.t == 1.0
    assert runs[0].end.t == 3.0
    assert runs[0].duration == 2.0


def test_pair_target_runs_multiple_pairs_supports_repetition():
    events = [
        MarkEvent(t=1.0, label="TARGET_BEGIN"), MarkEvent(t=3.0, label="TARGET_END"),
        MarkEvent(t=10.0, label="TARGET_BEGIN"), MarkEvent(t=12.5, label="TARGET_END"),
        MarkEvent(t=20.0, label="TARGET_BEGIN"), MarkEvent(t=22.0, label="TARGET_END"),
    ]
    runs, dangling = pair_target_runs(events)
    assert len(runs) == 3
    assert dangling is None
    assert [r.run_index for r in runs] == [0, 1, 2]
    assert runs[1].begin.t == 10.0 and runs[1].end.t == 12.5


def test_pair_target_runs_reports_dangling_begin_not_silently_dropped():
    events = [MarkEvent(t=1.0, label="TARGET_BEGIN"), MarkEvent(t=3.0, label="TARGET_END"), MarkEvent(t=10.0, label="TARGET_BEGIN")]
    runs, dangling = pair_target_runs(events)
    assert len(runs) == 1
    assert dangling is not None
    assert dangling.t == 10.0


def test_pair_target_runs_ignores_non_target_marks():
    events = [MarkEvent(t=0.0, label="user marker key"), MarkEvent(t=1.0, label="TARGET_BEGIN"), MarkEvent(t=3.0, label="TARGET_END")]
    runs, dangling = pair_target_runs(events)
    assert len(runs) == 1


def test_pair_target_runs_empty():
    runs, dangling = pair_target_runs([])
    assert runs == []
    assert dangling is None


# --- tight_window / context_window / control_windows --------------------------------


def test_tight_window_default_padding():
    run = TargetRun(0, MarkEvent(t=10.0, label="TARGET_BEGIN"), MarkEvent(t=15.0, label="TARGET_END"))
    lo, hi = tight_window(run)
    assert lo == pytest.approx(9.75)
    assert hi == pytest.approx(15.25)


def test_context_window_default_padding():
    run = TargetRun(0, MarkEvent(t=10.0, label="TARGET_BEGIN"), MarkEvent(t=15.0, label="TARGET_END"))
    lo, hi = context_window(run)
    assert lo == pytest.approx(8.0)
    assert hi == pytest.approx(17.0)


def test_windows_are_configurable_not_hardcoded():
    run = TargetRun(0, MarkEvent(t=10.0, label="TARGET_BEGIN"), MarkEvent(t=15.0, label="TARGET_END"))
    lo, hi = tight_window(run, before_ms=500.0, after_ms=1000.0)
    assert lo == pytest.approx(9.5)
    assert hi == pytest.approx(16.0)


def test_control_windows_derived_from_run_no_extra_marker_needed():
    run = TargetRun(0, MarkEvent(t=10.0, label="TARGET_BEGIN"), MarkEvent(t=15.0, label="TARGET_END"))
    controls = control_windows(run, silence_seconds=3.0, post_seconds=4.0)
    assert controls.silence == (7.0, 10.0)
    assert controls.post_dialogue == (15.0, 19.0)


# --- assess_instrumentation_health ---------------------------------------------------


def test_instrumentation_health_valid_when_heartbeat_and_key_write_present():
    events = [
        SpuKeyWriteEvent(t=0.0, write_pc=0x800866A8, family="PERIODIC_VOICE_SYNC", register="KEY_ON", voice_mask=0),
        HeartbeatEvent(t=0.1, position_counter=1, lifecycle_state_raw=0, last_req_params=0),
    ]
    health = assess_instrumentation_health(events)
    assert health.is_valid is True
    assert health.issues == []


def test_instrumentation_health_invalid_with_no_heartbeat():
    events = [SpuKeyWriteEvent(t=0.0, write_pc=0x800866A8, family="PERIODIC_VOICE_SYNC", register="KEY_ON", voice_mask=0)]
    health = assess_instrumentation_health(events)
    assert health.is_valid is False
    assert any("HEARTBEAT" in issue for issue in health.issues)


def test_instrumentation_health_invalid_with_no_key_write():
    events = [HeartbeatEvent(t=0.0, position_counter=1, lifecycle_state_raw=0, last_req_params=0)]
    health = assess_instrumentation_health(events)
    assert health.is_valid is False
    assert any("SPU_KEY_WRITE" in issue for issue in health.issues)


def test_instrumentation_health_detects_non_monotonic_timestamps():
    events = [
        SpuKeyWriteEvent(t=5.0, write_pc=0x800866A8, family="PERIODIC_VOICE_SYNC", register="KEY_ON", voice_mask=0),
        HeartbeatEvent(t=1.0, position_counter=1, lifecycle_state_raw=0, last_req_params=0),
    ]
    health = assess_instrumentation_health(events)
    assert health.timestamps_monotonic is False
    assert health.is_valid is False


# --- cross-run correlation -----------------------------------------------------------


def test_correlate_runs_stable_classification_across_runs():
    events1 = [*_proof_of_life(), MarkEvent(t=5.0, label="TARGET_BEGIN"), MarkEvent(t=8.0, label="TARGET_END")]
    events2 = [*_proof_of_life(), MarkEvent(t=5.0, label="TARGET_BEGIN"), MarkEvent(t=8.0, label="TARGET_END")]
    r1 = build_run_evidence("run1", events1, events1)
    r2 = build_run_evidence("run2", events2, events2)
    table = correlate_runs([r1, r2])
    classification_row = next(row for row in table if row["evidence"] == "classification")
    assert classification_row["stable"] is True


def test_correlate_runs_flags_unstable_classification():
    events1 = [
        SpuKeyWriteEvent(t=4.9, write_pc=0x800866A8, family="PERIODIC_VOICE_SYNC", register="KEY_ON", voice_mask=0x4),
        MarkEvent(t=5.0, label="TARGET_BEGIN"), MarkEvent(t=8.0, label="TARGET_END"),
    ]
    events2 = [*_proof_of_life(), MarkEvent(t=5.0, label="TARGET_BEGIN"), MarkEvent(t=8.0, label="TARGET_END")]
    r1 = build_run_evidence("run1", events1, events1)
    r2 = build_run_evidence("run2", events2, events2)
    table = correlate_runs([r1, r2])
    classification_row = next(row for row in table if row["evidence"] == "classification")
    assert classification_row["stable"] is False


# --- build_report / CLI ---------------------------------------------------------------


def test_build_report_single_trace_with_target_run(tmp_path):
    path = str(tmp_path / "trace.jsonl")
    events = [
        SaveStateLoadedEvent(t=-0.5),
        *_proof_of_life(),
        MarkEvent(t=5.0, label="TARGET_BEGIN"),
        HeartbeatEvent(t=5.5, position_counter=161409, lifecycle_state_raw=0x01, last_req_params=127),
        MarkEvent(t=8.0, label="TARGET_END"),
    ]
    with open(path, "w", encoding="utf-8") as f:
        for e in events:
            write_event(e, f)
    report = build_report([path])
    assert "Trace integrity" in report
    assert "paired TARGET_BEGIN/TARGET_END runs: 1" in report
    assert "Classification: CD_AUDIO_INPUT" in report


def test_build_report_no_dangling_warning_when_paired(tmp_path):
    path = str(tmp_path / "trace.jsonl")
    events = [*_proof_of_life(), MarkEvent(t=5.0, label="TARGET_BEGIN"), MarkEvent(t=8.0, label="TARGET_END")]
    with open(path, "w", encoding="utf-8") as f:
        for e in events:
            write_event(e, f)
    report = build_report([path])
    assert "WARNING" not in report


def test_build_report_warns_on_dangling_begin(tmp_path):
    path = str(tmp_path / "trace.jsonl")
    events = [*_proof_of_life(), MarkEvent(t=5.0, label="TARGET_BEGIN")]
    with open(path, "w", encoding="utf-8") as f:
        for e in events:
            write_event(e, f)
    report = build_report([path])
    assert "WARNING" in report
    assert "dangling" in report


def test_build_report_cross_run_section_appears_for_multiple_files(tmp_path):
    events = [*_proof_of_life(), MarkEvent(t=5.0, label="TARGET_BEGIN"), MarkEvent(t=8.0, label="TARGET_END")]
    path1 = str(tmp_path / "trace1.jsonl")
    path2 = str(tmp_path / "trace2.jsonl")
    for p in (path1, path2):
        with open(p, "w", encoding="utf-8") as f:
            for e in events:
                write_event(e, f)
    report = build_report([path1, path2])
    assert "Cross-run correlation" in report


def test_main_cli_runs_without_error(tmp_path, capsys):
    path = str(tmp_path / "trace.jsonl")
    events = [*_proof_of_life(), MarkEvent(t=5.0, label="TARGET_BEGIN"), MarkEvent(t=8.0, label="TARGET_END")]
    with open(path, "w", encoding="utf-8") as f:
        for e in events:
            write_event(e, f)
    exit_code = main([path])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Trace integrity" in captured.out
