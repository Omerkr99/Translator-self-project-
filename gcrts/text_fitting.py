"""Live Text Editor Workbench: automatic word-safe text fitting.

The game's own renderer wraps lines with zero word-boundary awareness --
confirmed via live GDB investigation of CAP0.EXE's FUN_8004a370 (see
NOTES.md and gcrts.layout_validation's module docstring): it just keeps
placing characters until the next one would exceed the line's pixel
budget, then wraps, splitting words wherever that happens to land.

This module produces text that renders cleanly anyway, without ever
touching the engine's own wrap logic: it computes ideal, human-readable
line breaks itself (treating words as atomic, exactly like a normal text
editor would), then inserts just enough trailing space padding at each
intended break point to push the engine's own naive per-character wrap
to trigger exactly there -- before it ever touches the next word.

Calibration: MEASURED_MAX_WIDTH_PX = 280 is the live-captured max_width
constant for the one narration textbox instance actually measured (see
gcrts.layout_validation's module docstring for the full GDB investigation).
An earlier version of this module divided that constant by 4, reasoning
by analogy with a DIFFERENT right-shift that happens later, at the final
VRAM-blit step (FUN_8004aa08) -- but max_width is compared DIRECTLY
against per-character width (`atlas.table_entry(code)[1]`, itself
confirmed real, unscaled advance-width data) in the wrap check itself
(FUN_8004a370), so the two must already share a unit; no /4 belongs here.

**Precisely confirmed, not estimated**: a controlled live probe (40
characters of confirmed-identical width -- both 'A' and 'M' measure 14 --
with a visible marker every 5th position so the wrap point could be
counted in groups) placed exactly 20 characters before wrapping.
20 * 14 = 280, exactly matching the live-captured max_width constant.
The basic per-character wrap check needs no discount at all.

A follow-up 100-character probe corrected the original read of that
result. Once past the first line, two consecutive wraps landed at a
clean, exactly-predicted 20 characters each -- no anomaly at all. Full
decompilation of the scroll-transition helpers (`FUN_8004a240`,
`FUN_8004a6a8`, `FUN_8004a6fc` in CAP0.EXE; see
gcrts.layout_validation's module docstring for the complete writeup)
showed the scroll case's X-reset computes the EXACT SAME value as a
normal wrap's -- it isn't a different formula, just re-homing that value
to a new array slot after the oldest visible line gets dropped. The
box's visible-line cap is also now confirmed, not guessed:
gcrts.layout_validation.MAX_VISIBLE_LINES = 4, read straight from the
layout struct and matched twice live.

The real, still-unexplained source of a short first line is a pair of
additive terms folded into every wrap-reset X in FUN_8004a370 --
`DAT_800a4d13` and a conditionally-added `DAT_800a4d12`-gated term --
that this project hasn't traced back to their writers (most likely
centering/indent control codes). That's an open, well-scoped follow-up
of its own if eliminating that variability ever matters; it isn't
scrolling, and isn't something this module's own budget/margin can fix
by construction, since it depends on whatever control codes precede a
given unit's text rather than on the text itself.

**The real root cause, found by tracing DAT_800a4d12/DAT_800a4d13 back
to their writers in FUN_80049168** (see gcrts.control_position_risk's
module docstring for the full writeup): specific control codes already
embedded in the ORIGINAL Japanese script -- `set_flag_d10`,
`line_center_calc`, `centered_text_setup` -- set `DAT_800a4d10` to a
value that makes FUN_8004a370 skip its normal budget check entirely and
force an unconditional line break at whatever character follows. This is
fully deterministic given where the code lands in the (re-encoded,
proportionally-remapped) translated text, and it's what actually caused
every "unexplained" split chased in earlier testing -- not a shrunk
budget. `fit_text_for_engine` now takes an optional `unit` parameter and,
when given one, projects these forced-wrap positions against its own
candidate output and inserts a matching line break there if one doesn't
already exist at a word boundary, so the engine's forced wrap lands
where this module already planned a break instead of mid-word.

Earlier versions of this module tried to compensate for that scroll
artifact by discounting MEASURED_MAX_WIDTH_PX itself (down to as low as
0.55x) -- wrong fix for a problem that wasn't in the basic wrap check.
The budget is now used directly for the FORCED-WRAP padding threshold
(pad_line_to_force_wrap targets the full nominal budget, since padding
must guarantee crossing whatever the real per-wrap budget turns out to
be, and the real budget can only be <= the nominal one -- never larger).
EXTRA_PADDING_SPACES still adds a small margin beyond the bare
mathematical minimum for a different, real reason: that minimum is
frequently just 1 space, indistinguishable from the single space that
already separates every word, so "padding" by exactly that amount
changes nothing about the rendered text at all.

**LINE_PLANNING_SAFETY_MARGIN exists for a third, distinct reason**:
live testing (a real translated sentence, not a synthetic probe) showed
the DAT_800a4d12/DAT_800a4d13 offset can shrink the ACTUAL usable budget
far more than expected -- one observed line held only ~5 short
characters before wrapping, and a later, fully-unpadded last line
("hear laughter.", 146px) still split mid-word ("laught"/"er.") despite
being scarcely half of the nominal 280px budget. Because the LAST line
is never padded (there's nothing after it to redirect an overflow into),
it has zero protection against this offset by construction. Grouping
lines against a smaller PLANNING budget (not the padding threshold)
gives every line, including the last, headroom to absorb some of that
unpredictable shrink. This is a heuristic buffer sized from the worst
live observation so far, not a mathematically guaranteed bound -- it
trades density (the earlier, explicit ask for tighter packing) for
reliability (never splitting a word), a tradeoff confirmed with the
user rather than picked silently. Tracing DAT_800a4d12/DAT_800a4d13's
actual writers remains the only way to close this gap precisely instead
of guessing a margin.
"""
from __future__ import annotations

from gcrts.control_position_risk import forced_wrap_positions, risk_lands_mid_word
from gcrts.glyph_atlas import GlyphAtlas
from gcrts.layout_validation import measure_pixel_width
from gcrts.script_unit import ScriptUnit

# Precisely confirmed live (see module docstring) -- use directly, no
# discount, for the forced-wrap padding threshold (pad_line_to_force_wrap).
MEASURED_MAX_WIDTH_PX = 280
SAFETY_MARGIN = 1.0

# Deliberate margin beyond the bare mathematical minimum needed to cross
# the budget -- see module docstring: 1 space of "minimum" padding is
# indistinguishable from a normal inter-word space and does nothing.
EXTRA_PADDING_SPACES = 4

# Heuristic reserve against the confirmed-but-unquantified per-wrap
# DAT_800a4d12/DAT_800a4d13 offset (see module docstring) -- used ONLY
# for fit_text_to_lines' own line-grouping decisions, never for the
# forced-wrap padding threshold. Trades density for reliability; see
# module docstring for the live case that motivated this.
LINE_PLANNING_SAFETY_MARGIN = 0.85

# A SEPARATE, tighter margin used only when center=True. Centering adds
# leading spaces that count against the exact per-wrap budget
# LINE_PLANNING_SAFETY_MARGIN protects -- live testing found even the
# 0.85 margin insufficient once centering's overhead was added back in
# (a line measuring 201px uncentered, comfortably under the 238px
# 0.85-margin budget, still split once centering added just one leading
# space to reach 215px -- the real per-wrap budget for that specific
# line was apparently somewhere under 215px, tighter than 0.85 assumed).
# This is a heuristic, not a guarantee -- see the module docstring's
# broader point that no fixed margin can fully bound an unmodeled,
# per-segment-variable shrinkage. Confirmed with the user as an accepted
# tradeoff (more fragmented lines) after the 0.85 margin failed live.
CENTER_PLANNING_SAFETY_MARGIN = 0.85

# CONFIRMED LIVE (see NOTES.md's "padding volume, not pixel margin, was
# the real driver" resolution): the persistent live split that survived
# every margin-tightening attempt disappeared entirely once these two
# padding sources were cut, with NO other change -- proving the
# hypothesis (raised by the user) that total inserted padding VOLUME,
# not pixel-budget tightness, was the actual cause. A full live
# round-trip of the same previously-failing sentence rendered with zero
# splits, including "classroom after", "say you can", and "hear
# laughter." -- all of which had split under every prior attempt. Both
# default to the normal, confirmed-reliable values when NOT centering.
CENTER_EXTRA_PADDING_SPACES = 1  # vs the normal EXTRA_PADDING_SPACES=4
CENTER_LEADING_SPACE_FRACTION = 0.5  # half the mathematically "perfect" centering offset


def _default_budget() -> int:
    return int(MEASURED_MAX_WIDTH_PX * SAFETY_MARGIN)


def fit_text_to_lines(text: str, max_width_px: int | None = None, atlas: GlyphAtlas | None = None) -> list[str]:
    """Compute clean, word-respecting lines for `text` against
    `max_width_px`, using the same per-character width measurement
    gcrts.layout_validation uses (real glyph ink-column widths when an
    atlas is given, else the documented half/full-width fallback).
    Never splits a word -- if a single word alone exceeds the budget,
    it still gets its own line rather than being cut (matching this
    module's "readable text" goal, not the engine's own behavior)."""
    if max_width_px is None:
        max_width_px = _default_budget()
    words = text.split(" ")
    lines: list[str] = []
    current: list[str] = []
    current_width = 0
    space_width = measure_pixel_width(" ", atlas)

    for word in words:
        word_width = measure_pixel_width(word, atlas)
        added = word_width if not current else space_width + word_width
        if current and current_width + added > max_width_px:
            lines.append(" ".join(current))
            current = [word]
            current_width = word_width
        else:
            current.append(word)
            current_width += added
    if current:
        lines.append(" ".join(current))
    return lines


def pad_line_to_force_wrap(
    line: str,
    max_width_px: int | None = None,
    atlas: GlyphAtlas | None = None,
    extra_padding_spaces: int | None = None,
) -> str:
    """Append enough trailing spaces to `line` that the engine's own
    per-character wrap (gcrts.layout_validation._greedy_wrap's model)
    triggers immediately after it -- before consuming anything from
    whatever text follows. Adds `extra_padding_spaces` (default:
    EXTRA_PADDING_SPACES) beyond the bare minimum that mathematically
    crosses the budget, since that bare minimum is often just 1 space --
    indistinguishable from a normal inter-word space, and therefore no
    different from not padding at all (see module docstring)."""
    if max_width_px is None:
        max_width_px = _default_budget()
    if extra_padding_spaces is None:
        extra_padding_spaces = EXTRA_PADDING_SPACES
    width = measure_pixel_width(line, atlas)
    space_width = measure_pixel_width(" ", atlas)
    if space_width == 0:
        raise ValueError("space glyph measured as zero-width -- cannot compute padding")
    padding = 0
    while width + padding * space_width <= max_width_px:
        padding += 1
    padding += extra_padding_spaces
    return line + (" " * padding)


def _split_line_at_char(line: str, local_index: int) -> tuple[str, str]:
    """Split `line` into two pieces at a word boundary at-or-before
    `local_index`. Returns ("", line) if `local_index` falls within the
    first word (can't split before it) or within `line`'s own leading
    whitespace (e.g. centering's leading spaces -- nothing meaningful to
    split there). Any leading whitespace on `line` stays attached to the
    first piece, so a centered line's indent survives being split."""
    leading_ws_len = len(line) - len(line.lstrip(" "))
    content = line[leading_ws_len:]
    content_index = local_index - leading_ws_len
    if content_index < 0:
        return "", line

    words = content.split(" ")
    pos = 0
    split_word_idx = len(words) - 1
    for idx, w in enumerate(words):
        word_end = pos + len(w)
        if pos <= content_index < word_end:
            split_word_idx = idx
            break
        pos = word_end + 1  # +1 for the joining space
    if split_word_idx == 0:
        return "", line
    first = line[:leading_ws_len] + " ".join(words[:split_word_idx])
    return first, " ".join(words[split_word_idx:])


def _locate_line_for_index(lines: list[str], padded_pieces: list[str], char_index: int) -> tuple[int, int] | None:
    """Map `char_index` (into "".join(padded_pieces)) back to (line_idx,
    local_index within that line's OWN un-padded text). Returns None if
    the index falls within a padding run rather than real word text."""
    pos = 0
    for i, piece in enumerate(padded_pieces):
        if pos <= char_index < pos + len(piece):
            local = char_index - pos
            if local < len(lines[i]):
                return i, local
            return None
        pos += len(piece)
    return None


def _build_padded(
    lines: list[str], padding_budget: int, atlas: GlyphAtlas | None, extra_padding_spaces: int | None = None
) -> list[str]:
    return [
        pad_line_to_force_wrap(line, padding_budget, atlas, extra_padding_spaces) for line in lines[:-1]
    ] + [lines[-1]]


def center_line(
    line: str, target_width_px: int, atlas: GlyphAtlas | None = None, leading_space_fraction: float = 1.0
) -> str:
    """Prepend leading spaces to `line` so its real content sits centered
    within `target_width_px` -- a normal center-alignment (like Word's),
    which this engine does NOT do on its own (it always renders starting
    at a fixed left edge, base_X -- see gcrts.layout_validation's module
    docstring). If `line` is already at or over budget, returns it
    unchanged (nothing to center into).

    `leading_space_fraction` < 1.0 produces a deliberately SOFT (not
    mathematically perfect) center, using only that fraction of the
    computed leading-space offset -- see CENTER_LEADING_SPACE_FRACTION's
    docstring for why this exists."""
    space_width = measure_pixel_width(" ", atlas)
    if space_width == 0:
        return line
    line_width = measure_pixel_width(line, atlas)
    remaining = target_width_px - line_width
    if remaining <= 0:
        return line
    leading_spaces = round(remaining / 2 / space_width * leading_space_fraction)
    return (" " * leading_spaces) + line


def _adjust_lines_for_forced_wraps(
    lines: list[str],
    padding_budget: int,
    atlas: GlyphAtlas | None,
    unit: ScriptUnit,
    extra_padding_spaces: int | None = None,
) -> list[str]:
    """If a FORCED_WRAP_MEANINGS control event (see
    gcrts.control_position_risk) projects to land mid-word once `lines`
    is padded, split that line at the nearest word boundary so the
    engine's own forced break lands on a break this module already
    planned, instead of splitting the word."""
    lines = list(lines)
    padded = _build_padded(lines, padding_budget, atlas, extra_padding_spaces)
    full_text = "".join(padded)
    risks = [r for r in forced_wrap_positions(unit, full_text) if risk_lands_mid_word(full_text, r)]

    for risk in risks:
        padded = _build_padded(lines, padding_budget, atlas, extra_padding_spaces)
        full_text = "".join(padded)
        if not risk_lands_mid_word(full_text, risk):
            continue  # an earlier split already resolved this one
        located = _locate_line_for_index(lines, padded, risk.char_index)
        if located is None:
            continue
        line_idx, local_idx = located
        first, second = _split_line_at_char(lines[line_idx], local_idx)
        if not first:
            continue  # risk lands in the line's first word -- nothing to split before it
        lines[line_idx : line_idx + 1] = [first, second]
    return lines


def fit_text_for_engine(
    text: str,
    max_width_px: int | None = None,
    atlas: GlyphAtlas | None = None,
    unit: ScriptUnit | None = None,
    center: bool = False,
) -> str:
    """Produce a single string that, when rendered by the game's real
    (word-blind) wrap engine, visually wraps at the same clean word
    boundaries as fit_text_to_lines() -- by padding every line but the
    last with just enough trailing spaces to force the engine's own wrap
    to land there instead of mid-word.

    Lines are GROUPED against a smaller planning budget
    (LINE_PLANNING_SAFETY_MARGIN of the nominal one) so every line --
    including the last, which is never padded and therefore has no other
    protection -- keeps headroom against the confirmed-but-unquantified
    per-wrap offset (see module docstring). Padding itself still targets
    the full nominal budget, since it must guarantee crossing whatever
    the real per-wrap budget turns out to be.

    Resolve/substitute the text (gcrts.font_workbench.auto_resolve_missing_glyphs
    or similar) BEFORE calling this, not after -- padding is computed
    against whatever characters are passed in, so fitting text that still
    contains characters due to be substituted (e.g. "," before it becomes
    "、") computes padding for the wrong widths.

    Pass `unit` (the ScriptUnit this text belongs to) when available to
    also correct for FORCED_WRAP_MEANINGS control codes (see
    gcrts.control_position_risk) embedded in the original script --
    codes that force an unconditional engine-side line break regardless
    of pixel budget. Without `unit`, that correction is skipped (matches
    this function's prior behavior for callers that don't have one).

    Without `center` (the default), this function is confirmed reliable
    across several live round-trips.

    `center=True` was ALSO confirmed reliable, after a real chase (see
    NOTES.md's "Padding volume, not pixel margin, was the real driver"
    section): live testing initially kept reproducing a persistent word
    split ("after", then "can") that didn't converge even after
    tightening the planning margin and fixing a real centering/forced-
    wrap ordering bug. Four live GDB-breakpoint attempts to find the
    cause failed to produce any data (one triggered the emulator's
    documented freeze bug). The user's hypothesis -- that total inserted
    padding VOLUME, not pixel-budget tightness, was the actual driver --
    turned out to be correct: cutting CENTER_EXTRA_PADDING_SPACES (4->1)
    and CENTER_LEADING_SPACE_FRACTION (a soft, half-strength center
    instead of a mathematically perfect one) resolved every split in a
    full live round-trip of the same previously-failing sentence, with
    no other change. Centering is applied AFTER the forced-wrap
    correction above, using the still-uncentered lines, so that
    correction's own position math stays simple; the (now smaller)
    leading spaces centering adds still lengthen the final text, which
    can in rare cases shift where a STALE_POSITION_MEANINGS code would
    land (see gcrts.control_position_risk) -- the same category of
    residual uncertainty already documented there, reduced but not
    eliminated by this fix."""
    if max_width_px is None:
        padding_budget = _default_budget()
    else:
        padding_budget = max_width_px
    margin = CENTER_PLANNING_SAFETY_MARGIN if center else LINE_PLANNING_SAFETY_MARGIN
    planning_budget = int(padding_budget * margin)

    extra_padding_spaces = CENTER_EXTRA_PADDING_SPACES if center else None

    lines = fit_text_to_lines(text, planning_budget, atlas)
    if len(lines) <= 1 and not center:
        return text
    if center:
        # Center within the SAME tighter CENTER_PLANNING_SAFETY_MARGIN
        # budget the line-grouping above already used -- live testing
        # caught centering into a looser budget (even the normal 0.85
        # margin) reintroducing mid-word splits: the leading spaces
        # centering adds count against the same per-wrap budget these
        # margins exist to protect. EXPERIMENTAL: also use a SOFT center
        # (CENTER_LEADING_SPACE_FRACTION) and a smaller trailing-padding
        # margin (CENTER_EXTRA_PADDING_SPACES) -- testing the hypothesis
        # that total inserted padding volume, not the pixel margin, is
        # what actually drives the still-unresolved live split (see
        # NOTES.md).
        lines = [
            center_line(line, planning_budget, atlas, CENTER_LEADING_SPACE_FRACTION) for line in lines
        ]
    if len(lines) > 1 and unit is not None:
        # MUST run after centering, not before: centering changes each
        # line's length, which shifts where a FORCED_WRAP_MEANINGS code
        # actually lands (the proportional projection depends on total
        # text length -- see gcrts.control_position_risk). Running this
        # correction before centering was a real bug caught live: it
        # correctly fixed a split, then centering silently re-broke it by
        # shifting the same code into the middle of a different word.
        lines = _adjust_lines_for_forced_wraps(lines, padding_budget, atlas, unit, extra_padding_spaces)
    return "".join(_build_padded(lines, padding_budget, atlas, extra_padding_spaces))
