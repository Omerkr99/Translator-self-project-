"""Finds candidate audio-activity segments (contiguous stretches where
sound is present above a noise floor) in a WAV file -- the "real
timing from audio, text filled in later" half of authoring a
`gcrts.subtitle_track_runner` subtitle track for a movie whose actual
dialogue this project has no transcript or translation for yet (see
`docs/renderer/SUBTITLE_TRACK_MECHANICS.md`).

HONEST SCOPE: this is amplitude-based activity detection, not speech
detection. A movie with continuous background music will report the
music as one long active segment, not isolated dialogue lines --
distinguishing speech from music from silence would need real spectral
analysis (e.g. formant structure, pitch variation), not attempted
here. Treat the output as "candidate cue boundaries a human should
verify by ear," not "confirmed dialogue timestamps."
"""
from __future__ import annotations

import wave
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ActivitySegment:
    start_seconds: float
    end_seconds: float

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds


def _read_wav_mono(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as w:
        n_channels = w.getnchannels()
        sample_width = w.getsampwidth()
        frame_rate = w.getframerate()
        raw = w.readframes(w.getnframes())
    if sample_width != 2:
        raise ValueError(f"only 16-bit PCM WAV is supported, got sample_width={sample_width}")
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1)
    return samples, frame_rate


def find_activity_segments(
    wav_path: str,
    window_seconds: float = 0.05,
    threshold_ratio: float = 0.08,
    min_gap_seconds: float = 0.3,
    min_duration_seconds: float = 0.5,
) -> list[ActivitySegment]:
    """`threshold_ratio` is relative to the file's own peak RMS window
    (not an absolute sample value), so it self-calibrates per file
    regardless of overall volume. `min_gap_seconds` bridges short
    pauses (natural gaps within one line of dialogue) into a single
    segment; `min_duration_seconds` drops isolated blips too short to
    plausibly be a real cue."""
    samples, frame_rate = _read_wav_mono(wav_path)
    window_size = max(1, int(window_seconds * frame_rate))
    n_windows = len(samples) // window_size
    if n_windows == 0:
        return []

    trimmed = samples[: n_windows * window_size].reshape(n_windows, window_size)
    rms = np.sqrt(np.mean(trimmed**2, axis=1))
    peak = rms.max()
    if peak == 0:
        return []
    threshold = peak * threshold_ratio
    active = rms >= threshold

    segments: list[ActivitySegment] = []
    seg_start_window: int | None = None
    for i, is_active in enumerate(active):
        if is_active and seg_start_window is None:
            seg_start_window = i
        elif not is_active and seg_start_window is not None:
            segments.append(ActivitySegment(seg_start_window * window_seconds, i * window_seconds))
            seg_start_window = None
    if seg_start_window is not None:
        segments.append(ActivitySegment(seg_start_window * window_seconds, n_windows * window_seconds))

    merged: list[ActivitySegment] = []
    for seg in segments:
        if merged and seg.start_seconds - merged[-1].end_seconds <= min_gap_seconds:
            merged[-1] = ActivitySegment(merged[-1].start_seconds, seg.end_seconds)
        else:
            merged.append(seg)

    return [s for s in merged if s.duration_seconds >= min_duration_seconds]
