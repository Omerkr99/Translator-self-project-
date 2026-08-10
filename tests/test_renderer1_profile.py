from gcrts.renderer1_profile import (
    ProfileStatus,
    Renderer1Profile,
    ValidationResult,
    mark_stale,
    validate_profile,
)

FINGERPRINT_ADDR = 0x800397BC
FINGERPRINT_BYTES = bytes.fromhex("0800229600000000080002a60a002296000000000a0002a6")


def _profile(**overrides) -> Renderer1Profile:
    kwargs = dict(
        profile_name="test_profile",
        status=ProfileStatus.LIVE_CONFIRMED_THIS_SESSION,
        record_base_addr=0x800A2AD4,
        code_fingerprint_addr=FINGERPRINT_ADDR,
        code_fingerprint_bytes=FINGERPRINT_BYTES,
    )
    kwargs.update(overrides)
    return Renderer1Profile(**kwargs)


def test_validate_profile_matches_live_memory():
    profile = _profile()
    ram = {FINGERPRINT_ADDR: FINGERPRINT_BYTES}
    result = validate_profile(profile, lambda addr, length: ram.get(addr))
    assert result == ValidationResult.PROFILE_VALID


def test_validate_profile_layout_drift_when_bytes_differ():
    profile = _profile()
    different = bytes.fromhex("fc0180a0fd0180a0fe0180a0240282a0250282a0260282a0")
    result = validate_profile(profile, lambda addr, length: different)
    assert result == ValidationResult.LAYOUT_DRIFT_DETECTED


def test_validate_profile_stale_when_unreadable():
    profile = _profile()
    result = validate_profile(profile, lambda addr, length: None)
    assert result == ValidationResult.PROFILE_STALE


def test_validate_profile_requires_reidentification_without_fingerprint():
    profile = _profile(code_fingerprint_addr=None, code_fingerprint_bytes=None)
    result = validate_profile(profile, lambda addr, length: b"anything")
    assert result == ValidationResult.REIDENTIFICATION_REQUIRED


def test_validate_profile_requires_reidentification_when_unverified():
    profile = _profile(status=ProfileStatus.UNVERIFIED)
    result = validate_profile(profile, lambda addr, length: FINGERPRINT_BYTES)
    assert result == ValidationResult.REIDENTIFICATION_REQUIRED


def test_mark_stale_only_demotes_live_confirmed():
    confirmed = _profile(status=ProfileStatus.LIVE_CONFIRMED_THIS_SESSION)
    mark_stale(confirmed)
    assert confirmed.status == ProfileStatus.STALE_NEEDS_REVERIFICATION

    unverified = _profile(status=ProfileStatus.UNVERIFIED)
    mark_stale(unverified)
    assert unverified.status == ProfileStatus.UNVERIFIED


def test_profile_round_trips_through_dict():
    profile = _profile(notes="round trip check")
    restored = Renderer1Profile.from_dict(profile.to_dict())
    assert restored == profile
