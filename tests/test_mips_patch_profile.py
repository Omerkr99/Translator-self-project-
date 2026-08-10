import pytest

from gcrts.mips_patch_profile import (
    KNOWN_EXECUTABLE_NAMES,
    NARRATIVE_EXECUTABLE_NAMES,
    PatchProfile,
    PatchProfileStatus,
    coverage_report,
    hypothesize_from_verified,
    identify_loaded_executable,
    load_registry,
    mark_stale,
    new_unverified_registry,
    record_live_confirmation,
    record_negative_finding,
    save_registry,
)


def test_new_unverified_registry_covers_every_known_executable():
    registry = new_unverified_registry()
    assert set(registry.keys()) == KNOWN_EXECUTABLE_NAMES
    assert all(p.status == PatchProfileStatus.UNVERIFIED for p in registry.values())


def test_narrative_names_are_a_subset_of_known_names():
    assert NARRATIVE_EXECUTABLE_NAMES <= KNOWN_EXECUTABLE_NAMES


def test_record_live_confirmation_sets_confirmed_status_and_fields():
    registry = new_unverified_registry()
    profile = record_live_confirmation(
        registry,
        "MYOKO.EXE",
        hook_addr=0x8004A378,
        resume_addr=0x8004A380,
        stub_region_addr=0x801AC500,
        stub_region_size=68,
        displaced_instruction_bytes=bytes.fromhex("21808000"),
        code_fingerprint_addr=0x8004A370,
        code_fingerprint_bytes=bytes.fromhex("d0ffbd27"),
    )
    assert profile.status == PatchProfileStatus.LIVE_CONFIRMED_THIS_SESSION
    assert registry["MYOKO.EXE"] is profile
    assert profile.hook_addr == 0x8004A378


def test_record_live_confirmation_accepts_optional_pointer_and_descriptor_fields():
    registry = new_unverified_registry()
    profile = record_live_confirmation(
        registry,
        "MYOKO.EXE",
        hook_addr=0x8004A378,
        resume_addr=0x8004A380,
        stub_region_addr=0x801AC500,
        stub_region_size=68,
        displaced_instruction_bytes=bytes.fromhex("21808000"),
        code_fingerprint_addr=0x8004A370,
        code_fingerprint_bytes=bytes.fromhex("d0ffbd27"),
        pointer_slot_addr=0x801AC100,
        descriptor_region_addr=0x801AC600,
        descriptor_region_size=4096,
    )
    assert profile.pointer_slot_addr == 0x801AC100
    assert profile.descriptor_region_addr == 0x801AC600
    assert profile.descriptor_region_size == 4096


def test_record_live_confirmation_defaults_pointer_and_descriptor_fields_to_none():
    registry = new_unverified_registry()
    profile = record_live_confirmation(
        registry,
        "MYOKO.EXE",
        hook_addr=0x8004A378,
        resume_addr=0x8004A380,
        stub_region_addr=0x801AC500,
        stub_region_size=68,
        displaced_instruction_bytes=bytes.fromhex("21808000"),
        code_fingerprint_addr=0x8004A370,
        code_fingerprint_bytes=bytes.fromhex("d0ffbd27"),
    )
    assert profile.pointer_slot_addr is None
    assert profile.descriptor_region_addr is None
    assert profile.descriptor_region_size is None


def test_hypothesize_from_verified_does_not_carry_pointer_or_descriptor_fields():
    registry = new_unverified_registry()
    record_live_confirmation(
        registry,
        "MYOKO.EXE",
        hook_addr=0x8004A378,
        resume_addr=0x8004A380,
        stub_region_addr=0x801AC500,
        stub_region_size=68,
        displaced_instruction_bytes=bytes.fromhex("21808000"),
        code_fingerprint_addr=0x8004A370,
        code_fingerprint_bytes=bytes.fromhex("d0ffbd27"),
        pointer_slot_addr=0x801AC100,
        descriptor_region_addr=0x801AC600,
        descriptor_region_size=4096,
    )
    hypothesis = hypothesize_from_verified(registry, "MYOKO.EXE", "MRIKA.EXE", address_delta=4)
    assert hypothesis.pointer_slot_addr is None
    assert hypothesis.descriptor_region_addr is None
    assert hypothesis.descriptor_region_size is None


def test_profile_roundtrips_through_dict():
    registry = new_unverified_registry()
    profile = record_live_confirmation(
        registry,
        "MYOKO.EXE",
        hook_addr=0x8004A378,
        resume_addr=0x8004A380,
        stub_region_addr=0x801AC500,
        stub_region_size=68,
        displaced_instruction_bytes=bytes.fromhex("21808000"),
        code_fingerprint_addr=0x8004A370,
        code_fingerprint_bytes=bytes.fromhex("d0ffbd27"),
        notes="test profile",
    )
    d = profile.to_dict()
    restored = PatchProfile.from_dict(d)
    assert restored == profile


def test_record_negative_finding_sets_confirmed_not_firing_status():
    registry = new_unverified_registry()
    profile = record_negative_finding(
        registry,
        "MRIKA.EXE",
        hook_addr=0x8004A374,
        code_fingerprint_addr=0x8004A370,
        code_fingerprint_bytes=bytes.fromhex("1800b0af"),
        notes="Polled for 45s with dialogue confirmed visible and advancing; canary never fired.",
    )
    assert profile.status == PatchProfileStatus.CONFIRMED_NOT_FIRING
    assert registry["MRIKA.EXE"] is profile
    assert profile.hook_addr == 0x8004A374


def test_negative_finding_is_distinct_from_unverified_and_hypothesized():
    registry = new_unverified_registry()
    record_negative_finding(
        registry,
        "MRIKA.EXE",
        hook_addr=0x8004A374,
        code_fingerprint_addr=0x8004A370,
        code_fingerprint_bytes=bytes.fromhex("1800b0af"),
        notes="never fired",
    )
    rows = coverage_report(registry)
    row = next(r for r in rows if r["executable_name"] == "MRIKA.EXE")
    assert row["status"] == "confirmed_not_firing"
    assert row["status"] != PatchProfileStatus.UNVERIFIED.value
    assert row["status"] != PatchProfileStatus.ADDRESSES_HYPOTHESIZED.value


def test_mark_stale_only_downgrades_confirmed_profiles():
    registry = new_unverified_registry()
    record_live_confirmation(
        registry,
        "MYOKO.EXE",
        hook_addr=0x8004A378,
        resume_addr=0x8004A380,
        stub_region_addr=0x801AC500,
        stub_region_size=68,
        displaced_instruction_bytes=bytes.fromhex("21808000"),
        code_fingerprint_addr=0x8004A370,
        code_fingerprint_bytes=bytes.fromhex("d0ffbd27"),
    )
    mark_stale(registry, "MYOKO.EXE")
    assert registry["MYOKO.EXE"].status == PatchProfileStatus.STALE_NEEDS_REVERIFICATION

    # Marking an already-unverified profile stale is a no-op, not an error.
    mark_stale(registry, "MRIKA.EXE")
    assert registry["MRIKA.EXE"].status == PatchProfileStatus.UNVERIFIED


def test_hypothesize_from_verified_shifts_addresses_but_not_scratch_region():
    registry = new_unverified_registry()
    record_live_confirmation(
        registry,
        "MYOKO.EXE",
        hook_addr=0x8004A378,
        resume_addr=0x8004A380,
        stub_region_addr=0x801AC500,
        stub_region_size=68,
        displaced_instruction_bytes=bytes.fromhex("21808000"),
        code_fingerprint_addr=0x8004A370,
        code_fingerprint_bytes=bytes.fromhex("d0ffbd27"),
    )
    hypothesis = hypothesize_from_verified(registry, "MYOKO.EXE", "MRIKA.EXE", address_delta=4)

    assert hypothesis.status == PatchProfileStatus.ADDRESSES_HYPOTHESIZED
    assert hypothesis.hook_addr == 0x8004A378 + 4
    assert hypothesis.resume_addr == 0x8004A380 + 4
    # Scratch region and fingerprint bytes are deliberately NOT carried over --
    # this session directly observed a previously-safe region become occupied
    # after a reload, so copying it forward would be exactly the mistake
    # MIPS_PATCH_PLAN.md's Phase 7 correction warns against.
    assert hypothesis.stub_region_size is None
    assert hypothesis.code_fingerprint_bytes is None


def test_hypothesize_refuses_to_build_from_an_unconfirmed_profile():
    registry = new_unverified_registry()
    with pytest.raises(ValueError):
        hypothesize_from_verified(registry, "MYOKO.EXE", "MRIKA.EXE")


def test_identify_loaded_executable_matches_on_fingerprint():
    registry = new_unverified_registry()
    record_live_confirmation(
        registry,
        "MYOKO.EXE",
        hook_addr=0x8004A378,
        resume_addr=0x8004A380,
        stub_region_addr=0x801AC500,
        stub_region_size=68,
        displaced_instruction_bytes=bytes.fromhex("21808000"),
        code_fingerprint_addr=0x8004A370,
        code_fingerprint_bytes=bytes.fromhex("d0ffbd27"),
    )

    def fake_read_memory(addr, length):
        if addr == 0x8004A370:
            return bytes.fromhex("d0ffbd27")
        return bytes(length)

    assert identify_loaded_executable(registry, fake_read_memory) == "MYOKO.EXE"


def test_identify_loaded_executable_returns_none_with_no_fingerprint_match():
    registry = new_unverified_registry()

    def fake_read_memory(addr, length):
        return bytes(length)

    assert identify_loaded_executable(registry, fake_read_memory) is None


def test_registry_roundtrips_through_a_json_file(tmp_path):
    registry = new_unverified_registry()
    record_live_confirmation(
        registry,
        "MYOKO.EXE",
        hook_addr=0x8004A378,
        resume_addr=0x8004A380,
        stub_region_addr=0x801AC500,
        stub_region_size=68,
        displaced_instruction_bytes=bytes.fromhex("21808000"),
        code_fingerprint_addr=0x8004A370,
        code_fingerprint_bytes=bytes.fromhex("d0ffbd27"),
        notes="round-trip test",
    )
    path = tmp_path / "profiles.json"
    save_registry(registry, str(path))
    restored = load_registry(str(path))
    assert restored == registry


def test_coverage_report_flags_narrative_call_sites():
    registry = new_unverified_registry()
    rows = coverage_report(registry)
    assert len(rows) == len(KNOWN_EXECUTABLE_NAMES)
    narrative_rows = [r for r in rows if r["is_narrative_call_site"]]
    assert {r["executable_name"] for r in narrative_rows} == NARRATIVE_EXECUTABLE_NAMES
    assert all(r["status"] == "unverified" for r in rows)
