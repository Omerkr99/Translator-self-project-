"""Live Text Editor Workbench: control-code positioning risk.

Root cause of the "unpredictable mid-word split" pattern chased across
several live probes (see NOTES.md's "Scroll-transition formula modeled
precisely" section and gcrts.text_fitting's module docstring): it was
never scrolling, and never a wrong pixel-width calibration. It's specific
control codes -- already named in gcrts.script_decoder's
CONTROL_A_MEANINGS -- whose handlers in CAP0.EXE's FUN_80049168 write to
the same small state block (DAT_800a4d10..DAT_800a4d13) that
FUN_8004a370's wrap-reset reads from. Two DISTINCT mechanisms, confirmed
from the full decompile of FUN_8004a370 (see gcrts.layout_validation's
module docstring):

- **FORCED_WRAP_MEANINGS** -- `set_flag_d10` (0x0100), `line_center_calc`
  (0x0d00), `centered_text_setup` (0x1800, and its alias 0x2800): these
  set `DAT_800a4d10` to 1 or 2. Either value makes FUN_8004a370 skip its
  normal fits-on-line budget check ENTIRELY and fall straight through to
  the unconditional wrap-reset -- i.e. the very next rendered character
  is forced onto a new line no matter how much budget remains. This is
  fully deterministic given where the code lands, and live-confirmed: a
  100-character live probe with an embedded `set_flag_d10` projected to
  land at character 43 of the padded output ('p' of "pm、"), and the
  actual render split exactly there ("...classroom after six" / "pm、
  they...") -- matching this mechanism exactly, not a budget shortfall.
- **STALE_POSITION_MEANINGS** -- `pause_flag_a` / `pause_flag_b` (0x0500
  / 0x0600): these set `DAT_800a4d11 = 1`. The next call takes a
  DIFFERENT early-return path that positions using whatever
  `DAT_800a4d13` happens to hold at that moment -- leftover state from
  wherever it was last set, possibly in a preceding unit -- rather than
  the normal accumulated cursor position. Unlike the forced-wrap case,
  this does NOT advance to a new line; it mispositions one character
  horizontally on the current line. Precisely predicting the actual
  stale value would need a whole-scene simulation this project hasn't
  built. Live-confirmed to still cause splits even after the forced-wrap
  case above was fixed and verified (fixing one revealed the other,
  landing somewhere new each time the surrounding text length changed --
  moving the split, never removing it). Given that, gcrts.live_injection
  now DROPS these codes outright for any modified unit rather than
  guessing at their effect -- see its segment_from_unit docstring. This
  loses a subtle mid-sentence pacing pause from the original Japanese,
  a tradeoff made deliberately (confirmed with the user) rather than
  silently.

Neither mechanism is content-independent: a code embedded in the
ORIGINAL Japanese script fires against whatever characters happen to sit
at its (proportionally re-mapped) position once the dialogue text is
replaced by a translation, not the original characters it was designed
against. That's why the splits kept moving to a different word each time
a padding margin was retuned in earlier testing: the margin was never
the variable that mattered.

Position projection reuses the EXACT proportional mapping
gcrts.script_encoder.encode_segment already uses in production (a
control event that followed K of a unit's N original characters lands
after `round(K / N * M)` characters in an M-character candidate text) --
this isn't a new heuristic, it's the same math the encoder already
commits to, read back out for validation/planning purposes. Projection
accepts an explicit candidate text (not just `unit.edited_text`) so
gcrts.text_fitting can project against its own pre-padding line plan
before deciding where to force additional line breaks.
"""
from __future__ import annotations

from dataclasses import dataclass

from gcrts.script_encoder import tokenize_translated_text
from gcrts.script_unit import ScriptUnit

# Confirmed from CAP0.EXE's FUN_80049168 + FUN_8004a370 (see module
# docstring): DAT_800a4d10 = 1 or 2 makes the wrap-reset unconditional --
# a deterministic forced line break at whatever character follows.
FORCED_WRAP_MEANINGS: frozenset[str] = frozenset(
    {
        "set_flag_d10",
        "line_center_calc",
        "centered_text_setup",
        "alias_of_0x1800",
    }
)

# DAT_800a4d11 = 1 -- mispositions the next character using stale
# DAT_800a4d13 state, but does NOT force a new line. Flagged, not corrected.
STALE_POSITION_MEANINGS: frozenset[str] = frozenset(
    {
        "pause_flag_a",
        "pause_flag_b",
    }
)


@dataclass
class ControlPositionRisk:
    event: dict
    char_index: int  # 0-based index into the projected text where this event lands


def project_control_event_positions(unit: ScriptUnit, text: str | None = None) -> list[ControlPositionRisk]:
    """For every control event in `unit.control_events`, compute the
    character index in `text` (default: `unit.edited_text`) it will land
    at after re-encoding, using the same proportional placement formula
    gcrts.script_encoder.encode_segment uses. Events are assumed to be in
    stream order (ascending offset), which is how ScriptUnit builds them.

    Character counts use tokenize_translated_text, NOT len(str) -- a
    `<?0xNNNN>` placeholder (for a code with no known character mapping)
    is a 9-character escape sequence representing exactly ONE code, so
    raw string length badly over-counts whenever any are present (a real
    bug caught by live-testing this very function: a 39-word unit with 4
    control words and 35 real characters measured as 147 "characters"
    via len() alone). `text` is assumed already fully resolved (no
    remaining placeholders) -- see gcrts.text_fitting's own "resolve
    before fit" note -- so its token count equals its string length and
    plain indexing into it stays valid."""
    if text is None:
        text = unit.edited_text
    total_original_chars = len(tokenize_translated_text(unit.original_text))
    total_edited_chars = len(text)
    results: list[ControlPositionRisk] = []

    if total_original_chars == 0:
        return [ControlPositionRisk(event, 0) for event in unit.control_events]

    control_words_before = 0
    for event in unit.control_events:
        chars_before = (event["offset"] - unit.unit_start_offset) - control_words_before
        char_index = round(chars_before / total_original_chars * total_edited_chars)
        char_index = max(0, min(char_index, total_edited_chars))
        results.append(ControlPositionRisk(event, char_index))
        control_words_before += event.get("words_consumed", 1)
    return results


def forced_wrap_positions(unit: ScriptUnit, text: str | None = None) -> list[ControlPositionRisk]:
    """Projected positions of FORCED_WRAP_MEANINGS events only -- these are
    deterministic (see module docstring), so callers can act on them
    directly, e.g. gcrts.text_fitting inserting a matching line break."""
    return [
        risk
        for risk in project_control_event_positions(unit, text)
        if risk.event.get("meaning") in FORCED_WRAP_MEANINGS
    ]


def stale_position_risks(unit: ScriptUnit, text: str | None = None) -> list[ControlPositionRisk]:
    """Projected positions of STALE_POSITION_MEANINGS events -- flagged as
    a risk (see module docstring), not correctable without a whole-scene
    simulation of DAT_800a4d13's actual leftover value."""
    return [
        risk
        for risk in project_control_event_positions(unit, text)
        if risk.event.get("meaning") in STALE_POSITION_MEANINGS
    ]


def risk_lands_mid_word(text: str, risk: ControlPositionRisk) -> bool:
    """True if this risk's projected position falls strictly inside a word
    in `text` (not at a space or the text's start/end) -- the dangerous
    case, since an anomalous jump or forced break there visibly splits
    the word. Landing at a space or boundary is comparatively harmless."""
    i = risk.char_index
    if i <= 0 or i >= len(text):
        return False
    return text[i - 1] != " " and text[i] != " "
