"""Tests for gcrts.burn_in_subtitle -- pure image manipulation, no
live/GUI dependency."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from gcrts.burn_in_subtitle import burn_subtitle_onto_frame, wrap_text_to_width


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


def _font_and_draw():
    frame = Image.new("RGB", (320, 240))
    draw = ImageDraw.Draw(frame)
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    return font, draw


def test_wrap_text_to_width_keeps_short_text_on_one_line():
    font, draw = _font_and_draw()
    lines = wrap_text_to_width("hello there", font, draw, max_width=294)
    assert lines == ["hello there"]


def test_wrap_text_to_width_splits_long_text_into_multiple_lines_that_each_fit():
    font, draw = _font_and_draw()
    long_text = "TBD -- audio-derived candidate cue, verify wording and exact boundaries by ear"
    max_width = 294  # 0.92 * 320, matching burn_subtitle_onto_frame's default

    lines = wrap_text_to_width(long_text, font, draw, max_width)

    assert len(lines) > 1, "this long placeholder text must wrap onto more than one line"
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        assert bbox[2] - bbox[0] <= max_width, f"line {line!r} exceeds max_width"
    # no words were dropped or duplicated by wrapping
    assert " ".join(lines).split() == long_text.split()


def test_wrap_text_to_width_keeps_an_overlong_single_word_whole():
    font, draw = _font_and_draw()
    lines = wrap_text_to_width("Supercalifragilisticexpialidocious", font, draw, max_width=10)
    assert lines == ["Supercalifragilisticexpialidocious"]


def test_wrap_text_to_width_empty_text_returns_no_lines():
    font, draw = _font_and_draw()
    assert wrap_text_to_width("", font, draw, max_width=200) == []


def test_wrap_text_to_width_honors_explicit_newline_as_a_forced_break():
    # Title-card style content (e.g. a title and its translated subtitle)
    # needs author-controlled line breaks, not just width-driven wrapping.
    font, draw = _font_and_draw()
    lines = wrap_text_to_width("Twilight Syndrome\nSearch Chapter", font, draw, max_width=294)
    assert lines == ["Twilight Syndrome", "Search Chapter"]


def test_wrap_text_to_width_still_wraps_a_too_wide_segment_after_a_forced_break():
    font, draw = _font_and_draw()
    long_second_line = "a very long second segment that cannot possibly fit on one line"
    lines = wrap_text_to_width(f"Title\n{long_second_line}", font, draw, max_width=100)
    assert lines[0] == "Title"
    assert len(lines) > 2, "the long second segment must still wrap across multiple lines"
    for line in lines[1:]:
        bbox = draw.textbbox((0, 0), line, font=font)
        assert bbox[2] - bbox[0] <= 100


def test_burn_subtitle_onto_frame_never_overflows_frame_width_for_long_text():
    # The real bug found live: the original implementation let long
    # placeholder text run off both edges of the 320px frame,
    # cut off and illegible. This is the regression test for that fix.
    frame = Image.new("RGB", (320, 240), color=(0, 0, 0))
    long_text = "TBD -- audio-derived candidate cue, verify wording and exact boundaries by ear"

    result = burn_subtitle_onto_frame(frame, long_text)

    arr = np.array(result.convert("L"))
    # bright (burned-in) pixels must never appear in the outermost few
    # columns on either edge -- if they did, text would be running off
    # the frame exactly like the real bug this test guards against.
    left_edge = arr[:, :2]
    right_edge = arr[:, -2:]
    assert (left_edge > 220).sum() == 0, "text bled off the left edge of the frame"
    assert (right_edge > 220).sum() == 0, "text bled off the right edge of the frame"


def test_burn_subtitle_onto_frame_multiline_stacks_above_margin():
    frame = Image.new("RGB", (320, 240), color=(0, 0, 0))
    long_text = "TBD -- audio-derived candidate cue, verify wording and exact boundaries by ear"

    result = burn_subtitle_onto_frame(frame, long_text)
    arr = np.array(result.convert("L"))
    # more than one line means bright pixels should appear across a
    # taller band near the bottom than a single line would occupy
    bottom_band = arr[-60:, :]
    assert (bottom_band > 220).sum() > 0
