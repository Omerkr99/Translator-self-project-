"""Tests for gcrts.audio_activity_segments -- pure signal processing
against synthetic WAV data with known silence/tone patterns, no live
dependency."""
from __future__ import annotations

import wave

import numpy as np
import pytest

from gcrts.audio_activity_segments import find_activity_segments


def _write_wav(path, pattern_seconds, frame_rate=8000, amplitude=10000):
    """`pattern_seconds` is a list of (is_tone, duration) pairs."""
    chunks = []
    for is_tone, duration in pattern_seconds:
        n = int(duration * frame_rate)
        if is_tone:
            t = np.arange(n) / frame_rate
            chunk = (amplitude * np.sin(2 * np.pi * 440 * t)).astype(np.int16)
        else:
            chunk = np.zeros(n, dtype=np.int16)
        chunks.append(chunk)
    samples = np.concatenate(chunks) if chunks else np.array([], dtype=np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(frame_rate)
        w.writeframes(samples.tobytes())


def test_finds_one_segment_in_silence_tone_silence(tmp_path):
    path = tmp_path / "test.wav"
    _write_wav(path, [(False, 1.0), (True, 2.0), (False, 1.0)])

    segments = find_activity_segments(str(path))

    assert len(segments) == 1
    assert segments[0].start_seconds == pytest.approx(1.0, abs=0.1)
    assert segments[0].end_seconds == pytest.approx(3.0, abs=0.1)


def test_finds_two_separate_segments_with_long_gap(tmp_path):
    path = tmp_path / "test.wav"
    _write_wav(path, [(True, 1.0), (False, 2.0), (True, 1.0)])

    segments = find_activity_segments(str(path), min_gap_seconds=0.3)

    assert len(segments) == 2


def test_short_gap_gets_merged_into_one_segment(tmp_path):
    path = tmp_path / "test.wav"
    _write_wav(path, [(True, 1.0), (False, 0.1), (True, 1.0)])

    segments = find_activity_segments(str(path), min_gap_seconds=0.3)

    assert len(segments) == 1


def test_short_blip_is_dropped_by_min_duration(tmp_path):
    path = tmp_path / "test.wav"
    _write_wav(path, [(False, 1.0), (True, 0.1), (False, 1.0)])

    segments = find_activity_segments(str(path), min_duration_seconds=0.5)

    assert segments == []


def test_pure_silence_finds_no_segments(tmp_path):
    path = tmp_path / "test.wav"
    _write_wav(path, [(False, 2.0)])

    segments = find_activity_segments(str(path))

    assert segments == []


def test_segment_duration_property():
    from gcrts.audio_activity_segments import ActivitySegment

    seg = ActivitySegment(start_seconds=1.5, end_seconds=4.0)
    assert seg.duration_seconds == pytest.approx(2.5)


def test_rejects_non_16bit_wav(tmp_path):
    path = tmp_path / "test.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)  # 8-bit, unsupported
        w.setframerate(8000)
        w.writeframes(bytes([128] * 8000))

    with pytest.raises(ValueError, match="16-bit"):
        find_activity_segments(str(path))
