"""Tests for gcrts.live_scene_identification -- pure functions only,
no live capture dependency."""
from __future__ import annotations

import os

import numpy as np

from gcrts.audio_fingerprint import compute_fingerprint
from gcrts.live_scene_identification import (
    ConfidenceState,
    LiveDialogueEvent,
    classify_confidence,
    identify_event_from_capture,
    load_event_map,
    new_event_id,
    save_event,
)

SR = 8000


def _speech_bursts(duration: float, sr: int = SR, seed: int = 0) -> np.ndarray:
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


def test_classify_confidence_high_when_all_signals_strong():
    result = classify_confidence(
        fingerprint_similarity=0.95, continuity_windows=5, continuity_error=0.02, has_visual_context=True
    )
    assert result == ConfidenceState.HIGH_CONFIDENCE


def test_classify_confidence_candidate_when_only_fingerprint_strong():
    result = classify_confidence(
        fingerprint_similarity=0.95, continuity_windows=1, continuity_error=0.5, has_visual_context=False
    )
    assert result == ConfidenceState.CANDIDATE


def test_classify_confidence_candidate_when_only_continuity_strong():
    result = classify_confidence(
        fingerprint_similarity=0.6, continuity_windows=4, continuity_error=0.01, has_visual_context=False
    )
    assert result == ConfidenceState.CANDIDATE


def test_classify_confidence_detected_when_all_weak():
    result = classify_confidence(
        fingerprint_similarity=0.5, continuity_windows=1, continuity_error=0.8, has_visual_context=False
    )
    assert result == ConfidenceState.DETECTED


def test_classify_confidence_detected_when_no_fingerprint_at_all():
    result = classify_confidence(
        fingerprint_similarity=None, continuity_windows=None, continuity_error=None, has_visual_context=True
    )
    assert result == ConfidenceState.DETECTED


def test_classify_confidence_user_verified_overrides_everything():
    result = classify_confidence(
        fingerprint_similarity=0.5, continuity_windows=0, continuity_error=1.0, has_visual_context=False,
        user_verified=True,
    )
    assert result == ConfidenceState.USER_VERIFIED


def test_high_confidence_requires_visual_context_too():
    """Strong fingerprint + strong continuity but NO visual context
    should not reach HIGH_CONFIDENCE -- only CANDIDATE. Combining
    multiple independent evidence sources is the whole point."""
    result = classify_confidence(
        fingerprint_similarity=0.95, continuity_windows=5, continuity_error=0.02, has_visual_context=False
    )
    assert result == ConfidenceState.CANDIDATE


def test_event_round_trip_via_dict():
    event = LiveDialogueEvent(
        event_id="e1", captured_at="2026-08-24T00:00:00Z",
        asset_id="XAPACK99:9", fingerprint_similarity=0.9,
        confidence=ConfidenceState.CANDIDATE, evidence=["audio fingerprint", "offset continuity"],
    )
    restored = LiveDialogueEvent.from_dict(event.to_dict())
    assert restored.event_id == "e1"
    assert restored.asset_id == "XAPACK99:9"
    assert restored.confidence == ConfidenceState.CANDIDATE
    assert restored.evidence == ["audio fingerprint", "offset continuity"]


def test_save_and_load_event_map_roundtrip(tmp_path):
    path = str(tmp_path / "events.json")
    event = LiveDialogueEvent(event_id="e1", captured_at="2026-08-24T00:00:00Z", asset_id="XAPACK01:0")
    save_event(event, path=path)
    loaded = load_event_map(path)
    assert "e1" in loaded
    assert loaded["e1"].asset_id == "XAPACK01:0"


def test_load_event_map_missing_file_returns_empty():
    assert load_event_map("/definitely/does/not/exist.json") == {}


def test_new_event_id_is_unique_enough():
    a = new_event_id()
    assert a.startswith("event_")
    assert len(a) > len("event_")


def test_identify_event_from_capture_finds_real_match_with_visual_context():
    """Builds a synthetic capture containing a real speech-shaped
    fragment of a known reference asset, with visual context supplied
    -- should reach HIGH_CONFIDENCE, matching the real live case this
    session (chapter title screen + strong audio continuity)."""
    rng = np.random.default_rng(5)
    reference_signal = rng.uniform(-8000, 8000, SR * 20).astype(np.int16)
    known_db = {"XAPACK13:6": compute_fingerprint("XAPACK13:6", reference_signal.tobytes(), SR, 1)}
    full_db = {}

    music = _speech_bursts(6.0, seed=1) * 0  # silence padding
    speech = reference_signal[int(3.0 * SR):int(3.0 * SR) + SR * 8]
    capture = np.concatenate([music, speech, music]).reshape(-1, 1)

    event = identify_event_from_capture(
        capture, SR, 1, known_db, full_db,
        screenshot_path="shot.png", visible_text="第二の噪", chapter="Second Rumor",
        window_sizes=(1.5,),
    )
    assert event.asset_id == "XAPACK13:6"
    assert event.confidence == ConfidenceState.HIGH_CONFIDENCE
    assert "visible scene" in event.evidence
    assert "known-candidate fast path" in event.evidence


def test_identify_event_from_capture_rejected_when_no_speech_region():
    silent = np.zeros((SR * 5, 1), dtype=np.int16)
    event = identify_event_from_capture(silent, SR, 1, {}, {})
    assert event.confidence == ConfidenceState.REJECTED
    assert event.asset_id is None


def test_identify_event_from_capture_detected_when_no_strong_match():
    rng = np.random.default_rng(9)
    speech = _speech_bursts(8.0, seed=9)
    capture = speech.reshape(-1, 1)
    unrelated_db = {
        f"unrelated_{i}": compute_fingerprint(f"u{i}", rng.uniform(-8000, 8000, SR * 6).astype(np.int16).tobytes(), SR, 1)
        for i in range(3)
    }
    event = identify_event_from_capture(capture, SR, 1, {}, unrelated_db, window_sizes=(1.5,))
    assert event.confidence in (ConfidenceState.DETECTED, ConfidenceState.CANDIDATE)
