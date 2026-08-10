from gcrts.cdrom_setfilter import (
    KNOWN_SETFILTER_OBSERVATIONS,
    OTHER_COMMAND_WRITE_SITES,
    SETFILTER_CALL_SITE_ADDR,
    SETFILTER_COMMAND,
    SetfilterCallObservation,
    SetfilterEvidenceConfidence,
    cross_validate_file_number,
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
