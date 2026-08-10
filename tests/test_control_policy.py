from gcrts.control_policy import CONTROL_POLICY_TABLE, ControlPolicy, policy_for
from gcrts.script_decoder import CONTROL_A_MEANINGS, CONTROL_B_MEANINGS


def test_forced_wrap_meanings_are_classified_transform():
    for meaning in ("set_flag_d10", "line_center_calc", "centered_text_setup", "alias_of_0x1800"):
        record = policy_for(meaning)
        assert record.policy == ControlPolicy.TRANSFORM
        assert record.replacement == "explicit_line_boundary"


def test_stale_position_meanings_are_classified_drop_with_warning():
    for meaning in ("pause_flag_a", "pause_flag_b"):
        record = policy_for(meaning)
        assert record.policy == ControlPolicy.DROP_WITH_WARNING


def test_speaker_name_bracketing_is_preserved():
    assert policy_for("speaker_name_start").policy == ControlPolicy.PRESERVE
    assert policy_for("speaker_name_end").policy == ControlPolicy.PRESERVE


def test_unknown_meaning_resolves_to_unresolved_not_a_crash():
    assert policy_for(None).policy == ControlPolicy.UNRESOLVED
    assert policy_for("some_meaning_never_seen_before").policy == ControlPolicy.UNRESOLVED


def test_every_named_meaning_in_script_decoder_has_a_policy_record():
    # Nothing named in the decoder's own tables should fall through to the
    # generic "not in the table at all" case -- every one of them should
    # have been explicitly classified (even if that classification is
    # UNRESOLVED), so a gap is a visible test failure, not a silent one.
    all_named_meanings = set(CONTROL_A_MEANINGS.values()) | set(CONTROL_B_MEANINGS.values())
    for meaning in all_named_meanings:
        assert meaning in CONTROL_POLICY_TABLE, f"{meaning!r} has no explicit policy record"


def test_control_policy_record_to_dict_includes_replacement_only_when_present():
    transform = policy_for("set_flag_d10").to_dict()
    assert transform["replacement"] == "explicit_line_boundary"

    preserved = policy_for("speaker_name_start").to_dict()
    assert "replacement" not in preserved
