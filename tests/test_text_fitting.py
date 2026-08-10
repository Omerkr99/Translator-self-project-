from gcrts.control_position_risk import forced_wrap_positions, risk_lands_mid_word
from gcrts.layout_validation import FALLBACK_HALF_WIDTH_PX, _greedy_wrap, measure_pixel_width
from gcrts.script_unit import ScriptUnit
from gcrts.text_fitting import (
    EXTRA_PADDING_SPACES,
    LINE_PLANNING_SAFETY_MARGIN,
    center_line,
    fit_text_for_engine,
    fit_text_to_lines,
    pad_line_to_force_wrap,
)
from gcrts import text_fitting


def _make_unit(original_text: str, edited_text: str, control_events: list[dict], unit_start_offset: int = 0) -> ScriptUnit:
    return ScriptUnit(
        id="test_unit",
        source="live_ram",
        ram_address=None,
        unit_start_offset=unit_start_offset,
        unit_end_offset=unit_start_offset + len(original_text) + len(control_events),
        next_unit_start_offset=None,
        raw_codes=[],
        control_events=control_events,
        original_text=original_text,
        edited_text=edited_text,
        layout_constraints={},
        text_type="dialogue",
        glyphs_used=[],
        missing_glyphs=[],
    )


def test_fit_text_to_lines_never_splits_a_word():
    text = "one two three four five six seven eight"
    budget = 12 * FALLBACK_HALF_WIDTH_PX
    lines = fit_text_to_lines(text, max_width_px=budget)
    assert "".join(lines).replace(" ", "") == text.replace(" ", "")
    for line in lines:
        for word in line.split(" "):
            assert word in text.split(" ")  # no word got truncated/merged


def test_pad_line_to_force_wrap_clears_the_budget_by_a_real_margin():
    # The bare mathematical minimum that crosses the budget is often just
    # 1 space -- indistinguishable from a normal inter-word space, so it
    # does nothing (see module docstring). Padding must clear the budget
    # by a margin no reasonable single inter-word gap could produce.
    budget = 10 * FALLBACK_HALF_WIDTH_PX
    padded = pad_line_to_force_wrap("one two", max_width_px=budget)
    space_width = measure_pixel_width(" ")
    assert measure_pixel_width(padded) > budget + space_width  # more than "just 1 space" of margin
    # exactly EXTRA_PADDING_SPACES trailing spaces beyond the bare minimum
    # (the first count whose width exceeds budget) -- not unbounded
    bare_minimum = padded[: -EXTRA_PADDING_SPACES] if EXTRA_PADDING_SPACES else padded
    one_less_than_minimum = bare_minimum[:-1]
    assert measure_pixel_width(bare_minimum) > budget
    assert measure_pixel_width(one_less_than_minimum) <= budget


def test_fit_text_for_engine_matches_our_own_wrap_simulation():
    # The whole point: feeding the padded output back through the SAME
    # engine-wrap simulation gcrts.layout_validation uses should produce
    # line breaks landing at our intended word boundaries, never mid-word.
    # Use a realistically-scaled budget (proportional to the live game's
    # own, not an artificially tiny one) so the deliberate padding margin
    # doesn't dominate line length itself.
    #
    # fit_text_for_engine groups lines against a smaller PLANNING budget
    # (LINE_PLANNING_SAFETY_MARGIN of whatever budget is passed in) so even
    # the never-padded last line keeps headroom against the confirmed-but-
    # unquantified per-wrap offset (see module docstring) -- so the
    # reference grouping here must use that same reduced budget, not the
    # full one, to match what fit_text_for_engine actually produces.
    text = "If you walk by after six pm they say you can hear laughter"
    budget = 35 * FALLBACK_HALF_WIDTH_PX
    planning_budget = int(budget * LINE_PLANNING_SAFETY_MARGIN)

    intended_lines = fit_text_to_lines(text, max_width_px=planning_budget)
    engineered = fit_text_for_engine(text, max_width_px=budget)

    line_count, wrapped_mid_word = _greedy_wrap(engineered, line_budget_px=budget, atlas=None)
    assert not wrapped_mid_word
    assert line_count == len(intended_lines)


def test_fit_text_for_engine_reserves_headroom_on_the_unpadded_last_line():
    # The last line is never padded (nothing follows it to redirect an
    # overflow into), so it's the one most exposed to the confirmed-but-
    # unquantified per-wrap offset found in live testing. Its measured
    # width should sit comfortably under the FULL nominal budget, not just
    # barely under it, precisely because it was grouped against the
    # smaller planning budget.
    text = "hear laughter after the six pm bell rings across the empty classroom hallway"
    budget = 35 * FALLBACK_HALF_WIDTH_PX

    engineered = fit_text_for_engine(text, max_width_px=budget)
    last_line = engineered.split("  ")[-1].strip()  # padded lines end in multiple spaces
    assert measure_pixel_width(last_line) <= budget * LINE_PLANNING_SAFETY_MARGIN


def test_fit_text_for_engine_is_a_noop_for_text_that_already_fits():
    text = "short line"
    result = fit_text_for_engine(text, max_width_px=1000)
    assert result == text


def test_fit_text_for_engine_corrects_forced_wrap_control_codes():
    # Reproduces (in miniature) the live-confirmed root cause: a
    # set_flag_d10 control event forces an unconditional engine-side line
    # break wherever it lands (see gcrts.control_position_risk), which can
    # land mid-word regardless of pixel budget. This scenario is engineered
    # (max_width_px chosen precisely, see below) so the naive fit groups
    # "hello world this is bad" as ["hello world", "this is bad"], and a
    # fabricated forced-wrap event lands inside "bad" -- a real risk by
    # this project's own model, not a hypothetical one.
    text = "hello world this is bad"
    max_width_px = 118  # -> planning_budget=100, padding_budget=118

    naive = fit_text_for_engine(text, max_width_px=max_width_px)
    control_events = [{"offset": 28, "words_consumed": 1, "meaning": "set_flag_d10"}]
    unit = _make_unit("A" * 30, text, control_events, unit_start_offset=0)

    risks_before = [r for r in forced_wrap_positions(unit, naive) if risk_lands_mid_word(naive, r)]
    assert risks_before  # confirm the scenario is actually risky before any fix

    corrected = fit_text_for_engine(text, max_width_px=max_width_px, unit=unit)
    risks_after = [r for r in forced_wrap_positions(unit, corrected) if risk_lands_mid_word(corrected, r)]
    assert not risks_after  # the correction must resolve it
    assert corrected != naive
    assert "bad" in corrected.split()


def test_fit_text_for_engine_forced_wrap_correction_accounts_for_centering():
    # Regression test for a real ordering bug caught live: running the
    # forced-wrap correction BEFORE centering fixes the projected
    # position against the UNCENTERED text length, but centering then
    # lengthens every line, shifting where the control event actually
    # lands in the FINAL text -- silently re-breaking the fix. This test
    # verifies the outcome that actually matters: no forced-wrap event
    # lands mid-word in the text fit_text_for_engine actually returns,
    # regardless of the internal ordering used to get there.
    text = "hello world this is bad today"
    max_width_px = 118

    control_events = [{"offset": 28, "words_consumed": 1, "meaning": "set_flag_d10"}]
    unit = _make_unit("A" * 36, text, control_events, unit_start_offset=0)

    result = fit_text_for_engine(text, max_width_px=max_width_px, unit=unit, center=True)
    risks = [r for r in forced_wrap_positions(unit, result) if risk_lands_mid_word(result, r)]
    assert not risks


def test_center_line_splits_the_leftover_budget_evenly():
    line = "hi"  # 2 chars * FALLBACK_HALF_WIDTH_PX(8) = 16px
    target = 10 * FALLBACK_HALF_WIDTH_PX  # 80px
    centered = center_line(line, target)

    assert centered.endswith(line)
    leading_spaces = len(centered) - len(centered.lstrip(" "))
    assert leading_spaces > 0

    line_width = measure_pixel_width(line)
    space_width = measure_pixel_width(" ")
    left_margin = leading_spaces * space_width
    right_margin = target - line_width - left_margin
    # left and right margins should be equal (within one space's width,
    # since the leading-space count is rounded to a whole number)
    assert abs(left_margin - right_margin) <= space_width


def test_center_line_returns_unchanged_when_already_at_or_over_budget():
    line = "a very long line of text that exceeds the budget entirely"
    small_target = 5 * FALLBACK_HALF_WIDTH_PX
    assert center_line(line, small_target) == line


def test_fit_text_for_engine_center_centers_every_line_including_the_last():
    # With the reduced-padding centering (CENTER_LEADING_SPACE_FRACTION),
    # a line whose shortfall rounds to 0 leading spaces is expected and
    # fine -- so this checks the core guarantee (centering changes the
    # output, and the never-padded last line is affected too) rather than
    # asserting every single line gets a nonzero visible indent.
    text = "hello there world this is quite a bad situation today my friend"
    max_width_px = 118

    uncentered = fit_text_for_engine(text, max_width_px=max_width_px)
    centered = fit_text_for_engine(text, max_width_px=max_width_px, center=True)

    assert centered != uncentered
    # centering also uses a SMALLER trailing-padding margin
    # (CENTER_EXTRA_PADDING_SPACES) than normal, so centered output isn't
    # guaranteed to be longer overall -- only that it visibly differs and
    # the never-padded last line's content survives intact.
    assert centered.rstrip(" ").endswith("friend")
    # at least one line actually got a visible leading indent -- proof
    # centering did something real, not just a no-op pass
    assert any(line.startswith(" ") for line in centered.split("  ") if line.strip())


def test_fit_text_for_engine_center_uses_meaningfully_less_padding_than_full_strength():
    # Live-confirmed fix (see NOTES.md's "padding volume, not pixel
    # margin, was the real driver"): center=True deliberately uses a
    # SMALLER trailing-padding margin (CENTER_EXTRA_PADDING_SPACES) and a
    # SOFT, half-strength leading-space offset (CENTER_LEADING_SPACE_FRACTION)
    # rather than mathematically perfect centering, because cutting total
    # inserted padding volume is what actually resolved a persistent live
    # split that margin-tuning alone never fixed. This locks in that the
    # reduction is real, not just present in the constants.
    text = "hello world this is bad today friends"
    max_width_px = 118

    actual = fit_text_for_engine(text, max_width_px=max_width_px, center=True)

    # Reconstruct what FULL-STRENGTH centering (the pre-fix behavior)
    # would have produced, using the same line grouping, to compare
    # against -- not a hardcoded byte count that would rot.
    planning_budget = int(max_width_px * text_fitting.CENTER_PLANNING_SAFETY_MARGIN)
    lines = fit_text_to_lines(text, planning_budget)
    full_strength_lines = [center_line(line, planning_budget, leading_space_fraction=1.0) for line in lines]
    full_strength = "".join(
        [pad_line_to_force_wrap(line, max_width_px, extra_padding_spaces=EXTRA_PADDING_SPACES)
         for line in full_strength_lines[:-1]]
        + [full_strength_lines[-1]]
    )

    assert len(actual) < len(full_strength)


def test_fit_text_for_engine_center_still_centers_a_single_line():
    # A single-line text is normally a pure no-op (see the non-centered
    # test above) -- but with center=True it must still get centered,
    # since nothing else will ever center it.
    text = "short"
    result = fit_text_for_engine(text, max_width_px=1000, center=True)
    assert result != text
    assert result.endswith(text)
    assert result.startswith(" ")
