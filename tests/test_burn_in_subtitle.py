"""Tests for gcrts.burn_in_subtitle -- pure image manipulation, no
live/GUI dependency."""
from __future__ import annotations

import numpy as np
from PIL import Image

from gcrts.burn_in_subtitle import burn_subtitle_onto_frame


def test_returns_a_new_image_original_untouched():
    original = Image.new("RGB", (320, 240), color=(10, 20, 30))
    original_pixels = np.array(original).copy()

    result = burn_subtitle_onto_frame(original, "hello")

    assert np.array_equal(np.array(original), original_pixels), "input image must not be mutated"
    assert result is not original


def test_burning_text_actually_changes_pixels_near_the_bottom():
    frame = Image.new("RGB", (320, 240), color=(0, 0, 0))

    result = burn_subtitle_onto_frame(frame, "SUBTITLE TEXT")

    before = np.array(frame)
    after = np.array(result)
    bottom_region_before = before[-40:, :, :]
    bottom_region_after = after[-40:, :, :]
    assert not np.array_equal(bottom_region_before, bottom_region_after), "expected visible change near the bottom margin"


def test_top_of_frame_is_unaffected():
    frame = Image.new("RGB", (320, 240), color=(50, 60, 70))

    result = burn_subtitle_onto_frame(frame, "hello")

    before = np.array(frame)
    after = np.array(result)
    top_region_before = before[:100, :, :]
    top_region_after = after[:100, :, :]
    assert np.array_equal(top_region_before, top_region_after)


def test_handles_grayscale_input_without_crashing():
    frame = Image.new("L", (320, 240), color=128)

    result = burn_subtitle_onto_frame(frame, "hi")

    assert result.mode == "RGB"
    assert result.size == (320, 240)


def test_handles_empty_text_without_crashing():
    frame = Image.new("RGB", (320, 240), color=(0, 0, 0))

    result = burn_subtitle_onto_frame(frame, "")

    assert result.size == (320, 240)
