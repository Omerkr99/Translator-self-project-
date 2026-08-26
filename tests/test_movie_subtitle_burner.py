"""Tests for gcrts.movie_subtitle_burner's pure logic (frame-range
math and applying cues to real frame files on disk). The live
orchestration function (build_burned_in_movie, wrapping FFmpeg +
psxavenc + real disc I/O) is manually verified only -- see
docs/renderer/BURNED_IN_SUBTITLE_PIPELINE.md and
evidence/burned_in_subtitle_live_playback/ for that account."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from gcrts.overlay_action import SubtitleCue
from gcrts.movie_subtitle_burner import burn_cues_onto_frame_files, cue_to_frame_range


def test_cue_to_frame_range_at_15fps():
    cue = SubtitleCue(t_offset_seconds=10.85, text="x", duration_seconds=2.0)
    start, end = cue_to_frame_range(cue, fps=15.0)
    assert start == 162  # int(10.85 * 15)
    assert end == 192  # int(12.85 * 15)


def test_cue_to_frame_range_matches_this_session_live_verified_window():
    # The exact cue this project burned in and confirmed live
    # (evidence/burned_in_subtitle_live_playback/): text was confirmed
    # present at frames 163-193 inclusive (verified by direct visual
    # inspection AND independently by re-decoding the encoded .str).
    cue = SubtitleCue(t_offset_seconds=10.85, text="-insert text here-", duration_seconds=2.0)
    start, end = cue_to_frame_range(cue, fps=15.0)
    # cue_to_frame_range is 0-indexed; the live-verified frames were
    # 1-indexed filenames (ffmpeg's frame_%05d.png starts at 1), so the
    # 0-indexed range here is one less at each end.
    assert (start, end) == (162, 192)


def _make_frame(path, color=(0, 0, 0)):
    Image.new("RGB", (320, 240), color=color).save(path)


def test_burn_cues_onto_frame_files_modifies_only_the_right_frames(tmp_path):
    frame_paths = [tmp_path / f"frame_{i:03d}.png" for i in range(20)]
    for p in frame_paths:
        _make_frame(p)

    cue = SubtitleCue(t_offset_seconds=0.2, text="hello", duration_seconds=0.4)
    # at 10fps: start=int(0.2*10)=2, end=int(0.6*10)=6
    modified = burn_cues_onto_frame_files(frame_paths, [cue], fps=10.0)

    assert modified == [2, 3, 4, 5, 6]
    for i, p in enumerate(frame_paths):
        after = np.array(Image.open(p))
        bottom = after[-40:, :, :]
        has_text = not np.all(bottom == 0)
        assert has_text == (i in modified), f"frame {i} text presence mismatch"


def test_burn_cues_onto_frame_files_handles_multiple_non_overlapping_cues(tmp_path):
    frame_paths = [tmp_path / f"frame_{i:03d}.png" for i in range(30)]
    for p in frame_paths:
        _make_frame(p)

    cues = [
        SubtitleCue(t_offset_seconds=0.0, text="first", duration_seconds=0.5),
        SubtitleCue(t_offset_seconds=2.0, text="second", duration_seconds=0.5),
    ]
    modified = burn_cues_onto_frame_files(frame_paths, cues, fps=10.0)

    assert modified == [0, 1, 2, 3, 4, 5, 20, 21, 22, 23, 24, 25]


def test_burn_cues_onto_frame_files_ignores_out_of_range_indices(tmp_path):
    frame_paths = [tmp_path / f"frame_{i:03d}.png" for i in range(5)]
    for p in frame_paths:
        _make_frame(p)

    cue = SubtitleCue(t_offset_seconds=0.0, text="hi", duration_seconds=10.0)  # would extend well past frame 5
    modified = burn_cues_onto_frame_files(frame_paths, [cue], fps=10.0)

    assert modified == [0, 1, 2, 3, 4]  # clamped to available frames, no crash
