import array
import math
from dataclasses import replace

from gcrts.audio_semantic import (
    AudioFeatures,
    SemanticType,
    VerificationSource,
    activity_window_features,
    classify_candidate,
    compute_audio_features,
    rank_pack_channels,
)

SR = 37800


def _tone(amplitude, n_samples):
    return array.array("h", [amplitude] * n_samples)


def _silence(n_samples):
    return array.array("h", [0] * n_samples)


def _bursty_irregular(sr):
    """3 bursts of DIFFERENT lengths separated by real silence gaps --
    irregular burst lengths, speech-plausible. Burst/gap durations are
    well above the 0.5s window resolution so they reliably land in
    distinct above/below-threshold windows."""
    samples = []
    for burst_len_s, gap_len_s in [(1.0, 1.0), (2.5, 1.5), (0.5, 1.0)]:
        samples += [3000] * int(sr * burst_len_s)
        samples += [0] * int(sr * gap_len_s)
    return array.array("h", samples)


def _bursty_regular(sr):
    """4 bursts of the SAME length, evenly spaced -- regular/loop-plausible."""
    samples = []
    for _ in range(4):
        samples += [3000] * int(sr * 1.0)
        samples += [0] * int(sr * 1.0)
    return array.array("h", samples)


# --- compute_audio_features ------------------------------------------------


def test_compute_audio_features_silence_has_zero_rms():
    features = compute_audio_features("a", _silence(SR * 2), SR)
    assert features.rms_mean == 0
    assert features.silence_ratio == 1.0


def test_compute_audio_features_constant_tone_has_low_cv():
    features = compute_audio_features("a", _tone(5000, SR * 2), SR)
    assert features.rms_cv < 0.05  # perfectly steady -- near-zero coefficient of variation


def test_compute_audio_features_duration_matches_sample_count():
    features = compute_audio_features("a", _tone(1000, SR * 3), SR)
    assert math.isclose(features.duration_seconds, 3.0, rel_tol=0.05)


def test_compute_audio_features_irregular_bursts_have_high_regularity_cv():
    features = compute_audio_features("a", _bursty_irregular(SR), SR)
    assert features.burst_count >= 2
    assert features.burst_regularity_cv > 0.1


def test_compute_audio_features_regular_bursts_have_low_regularity_cv():
    features = compute_audio_features("a", _bursty_regular(SR), SR)
    assert features.burst_count >= 3
    assert features.burst_regularity_cv < 0.15


def test_compute_audio_features_to_dict_has_no_numpy_types():
    features = compute_audio_features("a", _bursty_irregular(SR), SR)
    d = features.to_dict()
    import json
    json.dumps(d)  # raises if any value isn't JSON-serializable (e.g. leftover numpy scalar)


# --- classify_candidate ------------------------------------------------------


def _make_features(asset_id, rms_mean, rms_cv, silence_ratio, burst_count, avg_burst_duration_s, burst_regularity_cv):
    return AudioFeatures(
        asset_id=asset_id, duration_seconds=5.0, sample_rate_hz=SR, window_seconds=0.5,
        rms_mean=rms_mean, rms_stdev=rms_mean * rms_cv, rms_cv=rms_cv, silence_ratio=silence_ratio,
        burst_count=burst_count, avg_burst_duration_s=avg_burst_duration_s, burst_regularity_cv=burst_regularity_cv,
        silence_gap_count=burst_count, avg_silence_gap_s=0.3, spectral_centroid_hz=2000.0,
        zero_crossing_rate=0.05, window_rms=(rms_mean,) * 10,
    )


def test_classify_candidate_silence_for_zero_rms():
    f = _make_features("a", 0, 0, 1.0, 0, 0, 0)
    result = classify_candidate(f, [_make_features("b", 500, 0.4, 0.05, 2, 1.0, 0.3)])
    assert result.semantic_type == SemanticType.SILENCE
    assert result.verification_source == VerificationSource.HEURISTIC


def test_classify_candidate_unknown_without_siblings():
    f = _make_features("a", 500, 0.6, 0.2, 2, 1.0, 0.3)
    result = classify_candidate(f, [])
    assert result.semantic_type == SemanticType.UNKNOWN


def test_classify_candidate_dialogue_for_bursty_irregular_outlier():
    target = _make_features("a", 500, 1.2, 0.3, 3, 0.5, 0.6)  # high cv, irregular bursts
    siblings = [_make_features(f"s{i}", 500, 0.4, 0.05, 1, 4.0, 0.0) for i in range(4)]
    result = classify_candidate(target, siblings)
    assert result.semantic_type == SemanticType.DIALOGUE
    assert result.verification_source == VerificationSource.HEURISTIC


def test_classify_candidate_regression_regular_loop_is_not_dialogue():
    """Real bug this milestone found and fixed: a high-cv envelope with
    MULTIPLE, REGULARLY-SPACED bursts (near-identical lengths) is a
    loop/rhythmic-SFX signature, not speech -- must classify as MUSIC,
    not DIALOGUE, even though it would pass the raw cv/silence checks."""
    target = _make_features("a", 500, 1.2, 0.3, 4, 0.5, 0.05)  # high cv, but REGULAR bursts (low regularity_cv)
    siblings = [_make_features(f"s{i}", 500, 0.4, 0.05, 1, 4.0, 0.0) for i in range(4)]
    result = classify_candidate(target, siblings)
    assert result.semantic_type == SemanticType.MUSIC
    assert "loop" in result.notes.lower() or "rhythmic" in result.notes.lower()


def test_classify_candidate_music_for_steady_low_cv_outlier():
    target = _make_features("a", 500, 0.1, 0.02, 1, 5.0, 0.0)
    siblings = [_make_features(f"s{i}", 500, 0.8, 0.3, 3, 1.0, 0.5) for i in range(4)]
    result = classify_candidate(target, siblings)
    assert result.semantic_type == SemanticType.MUSIC


def test_classify_candidate_ambience_for_quiet_channel():
    target = _make_features("a", 40, 0.5, 0.2, 1, 3.0, 0.0)
    siblings = [_make_features(f"s{i}", 500, 0.5, 0.2, 1, 3.0, 0.0) for i in range(4)]
    result = classify_candidate(target, siblings)
    assert result.semantic_type == SemanticType.AMBIENCE


def test_classify_candidate_never_returns_confirmed_provenance():
    """No matter the input, classify_candidate must never claim
    USER_LISTENING or RUNTIME_EVIDENCE provenance -- only a human or
    real runtime evidence can promote a label, never this function."""
    target = _make_features("a", 500, 1.2, 0.3, 3, 0.5, 0.6)
    siblings = [_make_features(f"s{i}", 500, 0.4, 0.05, 1, 4.0, 0.0) for i in range(4)]
    result = classify_candidate(target, siblings)
    assert result.verification_source == VerificationSource.HEURISTIC


# --- rank_pack_channels -------------------------------------------------------


def test_rank_pack_channels_sorts_dialogue_candidates_first():
    dialogue_like = _make_features("dlg", 500, 1.2, 0.3, 3, 0.5, 0.6)
    steady = [_make_features(f"s{i}", 500, 0.4, 0.05, 1, 4.0, 0.0) for i in range(4)]
    results = rank_pack_channels([dialogue_like] + steady)
    assert results[0].asset_id == "dlg"
    assert results[0].semantic_type == SemanticType.DIALOGUE


# --- activity_window_features -------------------------------------------------


def test_activity_window_features_extracts_local_window():
    window_rms = tuple([10.0] * 4 + [100.0] * 2 + [10.0] * 4)  # spike in the middle
    features = replace(_make_features("a", 40.0, 0.5, 0.2, 1, 1.0, 0.0), window_rms=window_rms)
    result = activity_window_features(features, offset_seconds=2.5, window_seconds=1.0)
    assert result["available"] is True
    assert result["relative_activity"] > 1.0  # the spike is above the whole-clip average


def test_activity_window_features_unavailable_without_window_rms():
    features = replace(_make_features("a", 40.0, 0.5, 0.2, 1, 1.0, 0.0), window_rms=())
    result = activity_window_features(features, offset_seconds=1.0)
    assert result["available"] is False
