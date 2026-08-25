"""Tests for gcrts.output_audio_match -- the formalized emulator-output
capture -> AudioAsset identification workflow. All synthetic signals,
no dependency on the real (gitignored) disc image, per this project's
established testing convention."""
from __future__ import annotations

import numpy as np
import pytest

from gcrts.audio_fingerprint import compute_fingerprint
from gcrts.output_audio_match import (
    ContinuityRun,
    MatchClassification,
    WindowMatch,
    build_known_candidate_db,
    classify_match,
    compute_energy_profile,
    crop_excerpt,
    fast_match_with_known_candidates,
    filter_duration_plausible,
    find_speech_burst_region,
    normalize_for_matching,
    score_offset_continuity,
    sliding_window_search,
)

SR = 8000


def _steady_tone(duration: float, amplitude: float = 5000.0, sr: int = SR) -> np.ndarray:
    """Simulates steady background music: continuous, low-variance energy."""
    n = int(duration * sr)
    t = np.arange(n) / sr
    return (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.int16)


def _speech_bursts(duration: float, sr: int = SR, seed: int = 0) -> np.ndarray:
    """Simulates speech: alternating bursts of noise and near-silence."""
    rng = np.random.default_rng(seed)
    n = int(duration * sr)
    out = np.zeros(n)
    burst_len = int(0.4 * sr)
    gap_len = int(0.2 * sr)
    pos = 0
    while pos < n:
        end = min(pos + burst_len, n)
        out[pos:end] = rng.uniform(-6000, 6000, end - pos)
        pos = end + gap_len
    return out.astype(np.int16)


def test_energy_profile_distinguishes_loud_from_silent():
    loud = _steady_tone(1.0)
    silent = np.zeros(SR, dtype=np.int16)
    signal = np.concatenate([silent, loud])
    profile = compute_energy_profile(signal.astype(np.float64), SR, window_seconds=0.1)
    first_half = [w.rms for w in profile if w.t < 1.0]
    second_half = [w.rms for w in profile if w.t >= 1.0]
    assert max(first_half) < min(second_half)


def test_find_speech_burst_region_prefers_bursty_over_steady():
    music = _steady_tone(6.0)
    speech = _speech_bursts(6.0)
    more_music = _steady_tone(6.0)
    signal = np.concatenate([music, speech, more_music]).astype(np.float64)
    profile = compute_energy_profile(signal, SR, window_seconds=0.1)
    region = find_speech_burst_region(profile, search_window_seconds=4.0)
    assert region is not None
    begin, end = region
    # the detected region should fall within the speech segment (6s-12s), not the music
    assert 5.0 <= begin <= 13.0
    assert 5.0 <= end <= 13.0


def test_find_speech_burst_region_none_for_pure_silence():
    silent = np.zeros(SR * 5, dtype=np.float64)
    profile = compute_energy_profile(silent, SR, window_seconds=0.1)
    assert find_speech_burst_region(profile) is None


def test_crop_excerpt_bounds():
    samples = np.arange(SR * 4).reshape(-1, 1).astype(np.int16)
    excerpt = crop_excerpt(samples, SR, 1.0, 2.0)
    assert len(excerpt) == SR
    assert excerpt[0, 0] == SR


def test_crop_excerpt_clamps_out_of_range():
    samples = np.zeros((SR, 1), dtype=np.int16)
    excerpt = crop_excerpt(samples, SR, -5.0, 100.0)
    assert len(excerpt) == SR


def test_normalize_removes_dc_offset_and_normalizes_gain():
    samples = (np.full(1000, 100) + np.sin(np.linspace(0, 20, 1000)) * 50).reshape(-1, 1).astype(np.int16)
    normalized = normalize_for_matching(samples)
    assert abs(normalized.astype(np.float64).mean()) < abs(samples.astype(np.float64).mean())
    assert np.abs(normalized).max() > np.abs(samples).max()  # gain increased toward target peak


def test_filter_duration_plausible_excludes_short_fragments():
    pcm_short = _steady_tone(0.2).tobytes()
    pcm_long = _steady_tone(10.0).tobytes()
    db = {
        "short": compute_fingerprint("short", pcm_short, SR, 1),
        "long": compute_fingerprint("long", pcm_long, SR, 1),
    }
    filtered = filter_duration_plausible(db, query_duration=8.0, min_ratio=0.3)
    assert "long" in filtered
    assert "short" not in filtered


def test_offset_continuity_detects_coherent_real_match():
    """Builds a reference asset and a candidate that is a real slice of
    it (simulating a genuine capture of that asset playing) -- the
    continuity scorer should find a long, coherent run for it."""
    rng = np.random.default_rng(42)
    reference_signal = rng.uniform(-8000, 8000, SR * 20).astype(np.int16)
    reference_pcm = reference_signal.tobytes()
    db = {"real_asset": compute_fingerprint("real_asset", reference_pcm, SR, 1)}

    # candidate = a slice of the same signal starting at 5.0s, exactly
    # as it would appear if genuinely captured mid-playback
    candidate = reference_signal[int(5.0 * SR):int(5.0 * SR) + SR * 6].reshape(-1, 1)

    window_matches = sliding_window_search(candidate, SR, 1, db, window_sizes=(1.5,), hop_ratio=0.5)
    runs = score_offset_continuity(window_matches)
    assert len(runs) >= 1
    best = runs[0]
    assert best.asset_id == "real_asset"
    assert best.n_windows >= 3
    assert best.offset_advance_error < 0.3


def test_offset_continuity_rejects_incoherent_noise_matches():
    """Multiple unrelated short references against noise should NOT
    produce a long coherent continuity run -- this is the negative
    control for the false-lead pattern found live this session."""
    rng = np.random.default_rng(1)
    db = {
        f"frag_{i}": compute_fingerprint(f"frag_{i}", rng.uniform(-8000, 8000, int(SR * 0.3)).astype(np.int16).tobytes(), SR, 1)
        for i in range(10)
    }
    candidate = rng.uniform(-8000, 8000, SR * 6).astype(np.int16).reshape(-1, 1)
    window_matches = sliding_window_search(candidate, SR, 1, db, window_sizes=(1.5,), hop_ratio=0.5)
    runs = score_offset_continuity(window_matches)
    long_runs = [r for r in runs if r.n_windows >= 4]
    assert len(long_runs) == 0


def test_classify_voice_asset_match_found():
    runs = [ContinuityRun("asset_a", 1.5, 0.0, 6.0, 5, 0.95, 0.05)]
    assert classify_match(runs) == MatchClassification.VOICE_ASSET_MATCH_FOUND


def test_classify_multiple_plausible_matches():
    runs = [
        ContinuityRun("asset_a", 1.5, 0.0, 6.0, 5, 0.95, 0.05),
        ContinuityRun("asset_b", 1.5, 0.0, 6.0, 4, 0.90, 0.08),
    ]
    assert classify_match(runs) == MatchClassification.MULTIPLE_PLAUSIBLE_MATCHES


def test_classify_no_match_when_runs_too_weak():
    runs = [ContinuityRun("asset_a", 1.5, 0.0, 3.0, 2, 0.6, 0.5)]
    assert classify_match(runs) == MatchClassification.NO_MATCH_IN_CURRENT_ASSET_DB


def test_classify_no_match_for_empty_runs():
    assert classify_match([]) == MatchClassification.NO_MATCH_IN_CURRENT_ASSET_DB


def test_build_known_candidate_db_filters_to_confirmed_ids():
    rng = np.random.default_rng(3)
    full_db = {
        f"XAPACK{i:02d}:0": compute_fingerprint(f"a{i}", rng.uniform(-8000, 8000, SR * 5).astype(np.int16).tobytes(), SR, 1)
        for i in range(5)
    }
    known = build_known_candidate_db(full_db, ["XAPACK01:0", "XAPACK03:0", "XAPACK99:0"])
    assert set(known.keys()) == {"XAPACK01:0", "XAPACK03:0"}  # unknown id silently dropped, not KeyError


def test_fast_match_finds_strong_match_in_known_candidates_without_touching_full_db():
    rng = np.random.default_rng(7)
    target_signal = rng.uniform(-8000, 8000, SR * 20).astype(np.int16)
    known_db = {"confirmed_asset": compute_fingerprint("confirmed_asset", target_signal.tobytes(), SR, 1)}
    # full_db deliberately contains only unrelated noise -- if the fast
    # path works, it should never need to fall back to this at all
    full_db = {
        f"unrelated_{i}": compute_fingerprint(f"u{i}", rng.uniform(-8000, 8000, SR * 8).astype(np.int16).tobytes(), SR, 1)
        for i in range(5)
    }
    candidate = target_signal[int(5.0 * SR):int(5.0 * SR) + SR * 6].reshape(-1, 1)

    result = fast_match_with_known_candidates(candidate, SR, 1, known_db, full_db, window_sizes=(1.5,), hop_ratio=0.5)
    assert result.search_path == "known_candidates"
    assert result.classification == MatchClassification.VOICE_ASSET_MATCH_FOUND
    assert result.runs[0].asset_id == "confirmed_asset"


def test_fast_match_falls_back_to_full_db_when_known_candidates_dont_match():
    rng = np.random.default_rng(11)
    known_signal = rng.uniform(-8000, 8000, SR * 8).astype(np.int16)
    known_db = {"confirmed_asset": compute_fingerprint("confirmed_asset", known_signal.tobytes(), SR, 1)}

    real_target = rng.uniform(-8000, 8000, SR * 20).astype(np.int16)
    full_db = {"real_target": compute_fingerprint("real_target", real_target.tobytes(), SR, 1)}
    # candidate is actually a slice of real_target, NOT of the known signal
    candidate = real_target[int(5.0 * SR):int(5.0 * SR) + SR * 6].reshape(-1, 1)

    result = fast_match_with_known_candidates(candidate, SR, 1, known_db, full_db, window_sizes=(1.5,), hop_ratio=0.5)
    assert result.search_path == "full_database"
    assert result.classification == MatchClassification.VOICE_ASSET_MATCH_FOUND
    assert result.runs[0].asset_id == "real_target"
