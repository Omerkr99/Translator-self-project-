"""Alternative Text Engine, Phase 1: control-code policy models.

A formal, machine-readable classification of every NAMED control-code
meaning (gcrts.script_decoder.CONTROL_A_MEANINGS / CONTROL_B_MEANINGS),
answering one question per meaning: what should CUSTOM_ENGINE mode do with
this code when it re-encodes edited text?

This is deliberately conservative. Only two groups have an actual,
live-confirmed behavioral classification (see NOTES.md and
gcrts.control_position_risk's module docstring for the investigation this
is built on):

- `pause_flag_a`/`pause_flag_b` -- confirmed to position the next
  character using unpredictable leftover render state. Classified
  DROP_WITH_WARNING, matching gcrts.live_injection.segment_from_unit's
  existing (already-shipped) behavior of dropping these for modified
  units -- this table documents that policy formally rather than
  introducing a new one.
  `pause_flag_a` specifically has a SECOND, independently confirmed
  effect (see MODE3_TRIGGER_INVESTIGATION.md, `gcrts.control_code_index`):
  with a nonzero parameter byte, it is the script decoder's confirmed
  producer of the per-frame `Y_COLLECTION_MODE` render mode (a loop that
  collects up to `MAX_VISIBLE_LINES` valid lines' Y-positions -- see
  `FRAME_RENDER_MODES.md`). This does NOT change the policy decision --
  dropping it for edited units is still correct, since the ALREADY-known
  stale-position effect (unpredictable, parameter-independent per current
  evidence) is reason enough on its own -- but it means dropping this
  code for an edited unit also silently removes whatever role it plays in
  frame-level line-position bookkeeping. Not yet understood well enough
  to change the DROP decision; recorded so a future investigation into
  `Y_COLLECTION_MODE`'s consumer doesn't have to rediscover this link.
- `set_flag_d10`/`line_center_calc`/`centered_text_setup`/`alias_of_0x1800`
  -- confirmed to force an unconditional line break. Classified TRANSFORM:
  in CUSTOM_ENGINE mode these become an explicit line-boundary entry in
  the layout plan instead of a control code the renderer has to interpret
  at all; gcrts.text_fitting's forced-wrap correction is HOST_FITTED
  mode's equivalent handling of the same finding.
- `speaker_name_start`/`speaker_name_end` are classified PRESERVE --
  they carry real semantic meaning (bracketing a speaker name) with no
  confirmed layout side effect, so there is no reason to touch them.

Every other named meaning is classified UNRESOLVED, per this project's
explicit instruction not to claim understanding without live evidence:
a name from the decompile is not the same as a confirmed behavior. Any
meaning NOT in this table at all (including every unnamed, meaning=None
control code) resolves to UNRESOLVED via policy_for()'s default, never a
crash and never a silent guess. UNRESOLVED codes are preserved verbatim
today by gcrts.script_encoder's existing byte-exact replay -- this table
does not change that; it exists so a later phase can see, in one place,
which codes still need investigation before CUSTOM_ENGINE mode should
treat them as anything other than "preserve and don't touch."
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ControlPolicy(Enum):
    PRESERVE = "preserve"  # re-encode verbatim; no known layout effect
    TRANSFORM = "transform"  # confirmed layout effect; becomes explicit layout-plan data in CUSTOM_ENGINE mode
    HOST_ONLY = "host_only"  # meaningful only to HOST_FITTED's own padding/wrap workaround, not a real game behavior
    ENGINE_ONLY = "engine_only"  # only meaningful once CUSTOM_ENGINE mode exists; no HOST_FITTED equivalent
    DROP_WITH_WARNING = "drop_with_warning"  # confirmed unsafe/unpredictable; dropped for edited units, logged
    UNRESOLVED = "unresolved"  # named but behavior not yet confirmed -- preserved verbatim, not yet classified


@dataclass
class ControlPolicyRecord:
    policy: ControlPolicy
    reason: str
    replacement: str | None = None  # what a TRANSFORM code becomes in CUSTOM_ENGINE mode, if applicable

    def to_dict(self) -> dict:
        d = {"policy": self.policy.value, "reason": self.reason}
        if self.replacement is not None:
            d["replacement"] = self.replacement
        return d


# Confirmed via live investigation (see module docstring) -- the only two
# groups with an actual behavioral finding behind them.
_FORCED_WRAP_TRANSFORM = ControlPolicyRecord(
    ControlPolicy.TRANSFORM,
    reason="Confirmed live: forces an unconditional engine-side line break "
    "regardless of pixel budget (see gcrts.control_position_risk.FORCED_WRAP_MEANINGS).",
    replacement="explicit_line_boundary",
)
_STALE_POSITION_DROP = ControlPolicyRecord(
    ControlPolicy.DROP_WITH_WARNING,
    reason="Confirmed live: positions the next character using unpredictable leftover "
    "render state (DAT_800a4d13), not a fresh value (see "
    "gcrts.control_position_risk.STALE_POSITION_MEANINGS). Already dropped for modified "
    "units by gcrts.live_injection.segment_from_unit; this record documents that policy.",
)
_PAUSE_FLAG_A_DROP = ControlPolicyRecord(
    ControlPolicy.DROP_WITH_WARNING,
    reason="Same stale-position effect as pause_flag_b (see _STALE_POSITION_DROP), "
    "PLUS a second, independently confirmed effect specific to this code: with a "
    "nonzero parameter byte, this is the script decoder's confirmed producer of the "
    "per-frame Y_COLLECTION_MODE render mode (see MODE3_TRIGGER_INVESTIGATION.md, "
    "gcrts.control_code_index.produces_y_collection_mode). The DROP decision is "
    "unchanged -- the stale-position effect alone already justifies it -- but dropping "
    "this code for an edited unit also silently removes its frame-level line-position "
    "bookkeeping role, not just the character-position effect. Flagged so this isn't "
    "rediscovered from scratch.",
)
_PRESERVE_NO_KNOWN_EFFECT = ControlPolicyRecord(
    ControlPolicy.PRESERVE,
    reason="Carries semantic meaning with no confirmed layout side effect.",
)
_UNRESOLVED_NAMED_ONLY = ControlPolicyRecord(
    ControlPolicy.UNRESOLVED,
    reason="Named from the decompile, but no layout behavior has been live-confirmed yet. "
    "Preserved verbatim by gcrts.script_encoder today; do not assume safe or unsafe "
    "without evidence.",
)

CONTROL_POLICY_TABLE: dict[str, ControlPolicyRecord] = {
    # Forced-wrap group -- gcrts.control_position_risk.FORCED_WRAP_MEANINGS
    "set_flag_d10": _FORCED_WRAP_TRANSFORM,
    "line_center_calc": _FORCED_WRAP_TRANSFORM,
    "centered_text_setup": _FORCED_WRAP_TRANSFORM,
    "alias_of_0x1800": _FORCED_WRAP_TRANSFORM,
    # Stale-position group -- gcrts.control_position_risk.STALE_POSITION_MEANINGS
    "pause_flag_a": _PAUSE_FLAG_A_DROP,  # also confirmed to produce Y_COLLECTION_MODE when parameter != 0
    "pause_flag_b": _STALE_POSITION_DROP,
    # Speaker-name bracketing -- semantically clear, no known layout effect
    "speaker_name_start": _PRESERVE_NO_KNOWN_EFFECT,
    "speaker_name_end": _PRESERVE_NO_KNOWN_EFFECT,
    # Everything else named in gcrts.script_decoder's tables: a decompile
    # gave us a name, not a confirmed behavior. UNRESOLVED until investigated.
    "call_FUN_80048c44": _UNRESOLVED_NAMED_ONLY,
    "low_byte_passthrough": _UNRESOLVED_NAMED_ONLY,
    "set_mode_ce4": _UNRESOLVED_NAMED_ONLY,
    "set_counter_cf6": _UNRESOLVED_NAMED_ONLY,
    "call_FUN_8004a230": _UNRESOLVED_NAMED_ONLY,
    "alias_of_0x400": _UNRESOLVED_NAMED_ONLY,
    "alias_of_0x400_b": _UNRESOLVED_NAMED_ONLY,
    "portrait_or_anim_a": _UNRESOLVED_NAMED_ONLY,
    "alias_of_0x1700": _UNRESOLVED_NAMED_ONLY,
    "speaker_name_char": _UNRESOLVED_NAMED_ONLY,
    "call_FUN_8006e4bc": _UNRESOLVED_NAMED_ONLY,
    "call_FUN_8006e4b0": _UNRESOLVED_NAMED_ONLY,
    "call_FUN_8006e4ec": _UNRESOLVED_NAMED_ONLY,
    "call_FUN_8006e51c": _UNRESOLVED_NAMED_ONLY,
    "alias_of_0x8000_family_0x400_style": _UNRESOLVED_NAMED_ONLY,
    "call_FUN_800753f8": _UNRESOLVED_NAMED_ONLY,
    "sound_or_voice_cue": _UNRESOLVED_NAMED_ONLY,
    "clear_flag_cd4": _UNRESOLVED_NAMED_ONLY,
    "set_flag_cd4_2": _UNRESOLVED_NAMED_ONLY,
    "call_FUN_8004ab98": _UNRESOLVED_NAMED_ONLY,
    "kerning_or_name_slot_param": _UNRESOLVED_NAMED_ONLY,
    "call_FUN_80049e30": _UNRESOLVED_NAMED_ONLY,
    "set_flag_0x20_and_c60": _UNRESOLVED_NAMED_ONLY,
    "cue_mode_0": _UNRESOLVED_NAMED_ONLY,
    "cue_mode_1": _UNRESOLVED_NAMED_ONLY,
    "cue_mode_2": _UNRESOLVED_NAMED_ONLY,
    "set_mode_ce4_fffd": _UNRESOLVED_NAMED_ONLY,
    "call_FUN_8006d618": _UNRESOLVED_NAMED_ONLY,
    "slot_lookup_0": _UNRESOLVED_NAMED_ONLY,
    "slot_lookup_1": _UNRESOLVED_NAMED_ONLY,
    "slot_lookup_2": _UNRESOLVED_NAMED_ONLY,
    "alias_of_0x1400": _UNRESOLVED_NAMED_ONLY,
}

_UNKNOWN_MEANING_RECORD = ControlPolicyRecord(
    ControlPolicy.UNRESOLVED,
    reason="No meaning name at all (decoded with meaning=None) or not present in "
    "CONTROL_POLICY_TABLE. Never discarded -- gcrts.script_encoder preserves it "
    "verbatim regardless of policy classification.",
)


def policy_for(meaning: str | None) -> ControlPolicyRecord:
    """Look up the policy for a control event's `meaning` (as stored in
    ScriptUnit.control_events / gcrts.script_decoder.ScriptCode.meaning).
    Always returns a record -- an unknown or missing meaning resolves to
    UNRESOLVED rather than raising, so this is always safe to call from a
    validation pass over a unit's full control_events list."""
    if meaning is None:
        return _UNKNOWN_MEANING_RECORD
    return CONTROL_POLICY_TABLE.get(meaning, _UNKNOWN_MEANING_RECORD)
