from gcrts.cdrom_setfilter import (
    KNOWN_SETFILTER_CONTEXT_CHECKS,
    KNOWN_SETFILTER_OBSERVATIONS,
    OTHER_COMMAND_WRITE_SITES,
    SETFILTER_CALL_SITE_ADDR,
    SETFILTER_COMMAND,
    SetfilterCallObservation,
    SetfilterContextCheck,
    SetfilterEvidenceConfidence,
    cross_validate_file_number,
    is_proven_event_specific,
)


def test_setfilter_command_is_the_publicly_documented_value():
    assert SETFILTER_COMMAND == 0x0D


def test_known_observation_matches_the_real_live_capture():
    """The exact values captured live, twice, identically, this session."""
    obs = KNOWN_SETFILTER_OBSERVATIONS[0]
    assert obs.call_site_addr == SETFILTER_CALL_SITE_ADDR
    assert obs.ra == 0x80081788
    assert obs.param_count == 2
    assert obs.params_ptr == 0x800A3070
    assert obs.params == (2, 1)
    assert obs.confidence == SetfilterEvidenceConfidence.LIVE_CAPTURED


def test_file_and_channel_number_properties():
    obs = KNOWN_SETFILTER_OBSERVATIONS[0]
    assert obs.file_number == 2
    assert obs.channel_number == 1


def test_file_and_channel_are_none_when_params_too_short():
    obs = SetfilterCallObservation(
        call_site_addr=SETFILTER_CALL_SITE_ADDR,
        ra=0,
        param_count=0,
        params_ptr=0,
        params=(),
        confidence=SetfilterEvidenceConfidence.UNKNOWN,
    )
    assert obs.file_number is None
    assert obs.channel_number is None


def test_other_command_write_sites_are_distinct_from_setfilter_site():
    assert SETFILTER_CALL_SITE_ADDR not in OTHER_COMMAND_WRITE_SITES
    assert len(OTHER_COMMAND_WRITE_SITES) == 2


def test_cross_validate_real_file_number_matches_real_disc_catalog():
    """file=2, the real captured value, must resolve to a real disc file --
    not just a plausible-looking small integer."""
    assert cross_validate_file_number(2) == "DAT/XA1/XAPACK02.BIN"


def test_cross_validate_rejects_out_of_range_file_number():
    assert cross_validate_file_number(99) is None


def test_round_trips_through_dict():
    obs = KNOWN_SETFILTER_OBSERVATIONS[0]
    restored = SetfilterCallObservation.from_dict(obs.to_dict())
    assert restored == obs


def test_to_dict_includes_file_and_channel_number():
    obs = KNOWN_SETFILTER_OBSERVATIONS[0]
    d = obs.to_dict()
    assert d["file_number"] == 2
    assert d["channel_number"] == 1


# --- Audio Event Isolation milestone: the "not proven event-specific" ---
# --- correction, and its regression coverage -----------------------------


def test_is_proven_event_specific_is_honestly_false():
    """Two independent simultaneous cross-checks both found the Setfilter
    firing during STOPPED with stale params -- never during an active
    PLAYING dispatch. Callers must not treat KNOWN_SETFILTER_OBSERVATIONS
    as this event's own channel without independent confirmation."""
    assert is_proven_event_specific() is False


def test_known_context_checks_all_show_stopped_state_with_stale_params():
    assert len(KNOWN_SETFILTER_CONTEXT_CHECKS) == 2
    for check in KNOWN_SETFILTER_CONTEXT_CHECKS:
        assert check.params == (2, 1)
        assert check.state_at_hit == 0x02  # STOPPED, not STARTING/PLAYING
        assert check.last_req_params_at_hit == 0x7F  # a stale, already-finished cue


def test_context_check_round_trips_through_dict():
    check = KNOWN_SETFILTER_CONTEXT_CHECKS[0]
    d = check.to_dict()
    restored = SetfilterContextCheck(
        t_seconds_after_resume=d["t_seconds_after_resume"],
        params=tuple(d["params"]),
        position_counter_at_hit=d["position_counter_at_hit"],
        state_at_hit=d["state_at_hit"],
        last_req_params_at_hit=d["last_req_params_at_hit"],
    )
    assert restored == check


# --- Regression: the wrong-stack-offset bug class must never return -----
#
# The FIRST attempt to catch a live Setfilter (a prior milestone) armed a
# breakpoint at 0x80081C00 and read the command byte from sp+0x11 -- the
# wrong stack offset (a leftover/unrelated byte from an earlier line of
# the same function). It silently returned a plausible-but-wrong 0x00
# (Sync) across three full live sessions, never crashing, never looking
# obviously broken. A static scan (not a repeat of the same live
# technique) proved the real command byte sits in $v0 directly at three
# real call sites, none of which was 0x80081C00. These assertions pin
# the corrected addresses down permanently.


def test_setfilter_call_site_is_not_the_old_wrong_address():
    """0x80081C00 was the address used by the original, buggy capture.
    The real site (0x8008182C) must never regress back to it."""
    assert SETFILTER_CALL_SITE_ADDR != 0x80081C00
    assert SETFILTER_CALL_SITE_ADDR == 0x8008182C


def test_other_command_write_sites_also_avoid_the_old_wrong_address():
    assert 0x80081C00 not in OTHER_COMMAND_WRITE_SITES


def test_setfilter_call_site_and_siblings_are_the_real_static_scan_result():
    """All 3 real command-write call sites the static scan found --
    changing any of these silently would reintroduce the exact class of
    bug this milestone fixed."""
    all_sites = {SETFILTER_CALL_SITE_ADDR, *OTHER_COMMAND_WRITE_SITES}
    assert all_sites == {0x8008182C, 0x80081AC8, 0x80081C2C}
