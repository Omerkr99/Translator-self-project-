from gcrts.cdrom_driver_discovery import (
    ADDITIONAL_POINTER_SET_BASES,
    DISCOVERED_SETS,
    KNOWN_POINTER_SET_ADDRS,
    CdromDriverDiscovery,
    DriverRelationship,
    additional_pointer_sets_found,
    any_new_command_driver_confirmed,
)


def test_seven_additional_pointer_sets_found():
    assert additional_pointer_sets_found() == 7
    assert len(ADDITIONAL_POINTER_SET_BASES) == 7


def test_additional_sets_are_distinct_from_the_known_set():
    for base in ADDITIONAL_POINTER_SET_BASES:
        assert base not in KNOWN_POINTER_SET_ADDRS


def test_800a31xx_cluster_present_in_additional_sets():
    """The 3 sets found in the same page as the known one -- the ones
    this pass investigated in depth."""
    assert 0x800A3140 in ADDITIONAL_POINTER_SET_BASES
    assert 0x800A3190 in ADDITIONAL_POINTER_SET_BASES
    assert 0x800A31A0 in ADDITIONAL_POINTER_SET_BASES


def test_no_new_command_driver_confirmed():
    """Honest: real additional pointer sets exist, but none was found
    to have a confirmed command-issuing writer this pass."""
    assert any_new_command_driver_confirmed() is False


def test_discovered_sets_classified_as_hw_dispatch_not_command_driver():
    assert len(DISCOVERED_SETS) == 3
    for d in DISCOVERED_SETS:
        assert d.relationship == DriverRelationship.HW_DISPATCH_TABLE_NOT_A_COMMAND_DRIVER
        assert d.has_known_writer is False


def test_discovered_sets_have_real_evidence_strings():
    """Regression: no classification may exist without a real evidence
    string explaining it."""
    for d in DISCOVERED_SETS:
        assert d.evidence.strip() != ""


def test_driver_relationship_has_the_milestones_required_taxonomy():
    names = {r.value for r in DriverRelationship}
    assert {"SAME_DRIVER_DIFFERENT_ENTRY", "SECOND_DRIVER", "OVERLAY_VARIANT"} <= names


def test_discovery_round_trips_as_dataclass_equality():
    a = CdromDriverDiscovery(0x800A3140, False, DriverRelationship.HW_DISPATCH_TABLE_NOT_A_COMMAND_DRIVER, "x")
    b = CdromDriverDiscovery(0x800A3140, False, DriverRelationship.HW_DISPATCH_TABLE_NOT_A_COMMAND_DRIVER, "x")
    assert a == b
