from gcrts.pcsx_spu_observer import (
    BACKEND_CAPABILITIES,
    CRASH_LOOP_STUCK_PC,
    KNOWN_SNAPSHOTS,
    RESERVED_INSTRUCTION_EXCEPTION_CODE,
    SPU_DEBUG_MENU_PATH,
    SPU_DEBUG_WINDOW_TITLE,
    SPUCNT_ADDR,
    SPUCNT_CD_AUDIO_ENABLE_BIT,
    SPUSTAT_ADDR,
    BackendCapability,
    ObservationBackend,
    SpuChannelObservation,
    SpuHardwareSnapshot,
    cd_audio_enable_confirmed_persistent_via_native_tool,
    crash_loop_requires_full_process_restart,
    gdb_spucnt_read_confirmed_wrong,
    single_voice_channel_isolated_for_dialogue,
    spu_mmio_reliable_backend,
    synthetic_input_reaches_game_controller,
)


def test_spu_debug_window_title_and_menu_path():
    assert SPU_DEBUG_WINDOW_TITLE == "SPU Debug"
    assert SPU_DEBUG_MENU_PATH == ("Debug", "SPU", "Show SPU debug")


def test_spucnt_and_spustat_addrs_match_psx_spx():
    assert SPUCNT_ADDR == 0x1F801DAA
    assert SPUSTAT_ADDR == 0x1F801DAE


def test_backend_capabilities_cover_gdb_and_native():
    backends = {c.backend for c in BACKEND_CAPABILITIES}
    assert ObservationBackend.GDB in backends
    assert ObservationBackend.PCSX_REDUX_NATIVE in backends


def test_gdb_backend_marked_unreliable_for_spu_mmio():
    gdb_cap = next(c for c in BACKEND_CAPABILITIES if c.backend == ObservationBackend.GDB)
    assert gdb_cap.spu_mmio_reliable is False
    assert gdb_cap.normal_ram_reliable is True


def test_native_backend_marked_reliable_for_spu_mmio():
    native_cap = next(c for c in BACKEND_CAPABILITIES if c.backend == ObservationBackend.PCSX_REDUX_NATIVE)
    assert native_cap.spu_mmio_reliable is True


def test_spu_mmio_reliable_backend_is_pcsx_redux_native():
    """Regression: must never silently fall back to GDB for SPU MMIO."""
    assert spu_mmio_reliable_backend() == ObservationBackend.PCSX_REDUX_NATIVE


def test_backend_capabilities_have_real_evidence_strings():
    for cap in BACKEND_CAPABILITIES:
        assert cap.evidence.strip() != ""


def test_known_snapshots_has_silent_and_audible_pair():
    labels = {s.label for s in KNOWN_SNAPSHOTS}
    assert "silent_baseline_post_slot9_load" in labels
    assert "user_confirmed_audible_after_trigger" in labels


def test_known_snapshots_have_real_evidence_strings():
    for s in KNOWN_SNAPSHOTS:
        assert s.evidence.strip() != ""
        assert len(s.channels) > 0


def test_cd_audio_enable_confirmed_persistent_via_native_tool():
    """The decisive reversal of the previous milestone's finding: real
    hardware state (not GDB) shows CD Audio Enable set in both the
    silent baseline AND the user-confirmed-audible capture."""
    assert cd_audio_enable_confirmed_persistent_via_native_tool() is True
    for s in KNOWN_SNAPSHOTS:
        assert s.spucnt & SPUCNT_CD_AUDIO_ENABLE_BIT == SPUCNT_CD_AUDIO_ENABLE_BIT


def test_gdb_spucnt_read_confirmed_wrong():
    assert gdb_spucnt_read_confirmed_wrong() is True


def test_single_voice_channel_not_isolated_honestly():
    """Honest negative: this pass could not attribute one specific SPU
    channel to the dialogue line, since many channels were already
    active in the silent baseline too."""
    assert single_voice_channel_isolated_for_dialogue() is False


def test_snapshot_and_channel_round_trip_as_dataclass_equality():
    a = SpuChannelObservation(0, True, False, True, 100, 100, 0, 0, 0)
    b = SpuChannelObservation(0, True, False, True, 100, 100, 0, 0, 0)
    assert a == b

    s1 = SpuHardwareSnapshot("x", 0xC081, 0, 37800, 1, 2016, 32767, 32767, (a,), "evidence")
    s2 = SpuHardwareSnapshot("x", 0xC081, 0, 37800, 1, 2016, 32767, 32767, (a,), "evidence")
    assert s1 == s2


def test_backend_capability_round_trips_as_dataclass_equality():
    a = BackendCapability(ObservationBackend.MOCK, True, True, "x")
    b = BackendCapability(ObservationBackend.MOCK, True, True, "x")
    assert a == b


def test_reserved_instruction_exception_code_matches_mips_r3000():
    assert RESERVED_INSTRUCTION_EXCEPTION_CODE == 10


def test_crash_loop_stuck_pc_documented():
    assert CRASH_LOOP_STUCK_PC == 0xA0010000


def test_crash_loop_requires_full_process_restart():
    """Regression: an in-process Hard Reset was confirmed NOT
    sufficient -- only a full process restart resolved the crash loop.
    Must not silently downgrade to a less drastic claim."""
    assert crash_loop_requires_full_process_restart() is True


def test_synthetic_input_reaches_game_controller_is_false():
    """The decisive environmental-limitation finding: synthetic
    keyboard input does not reach the emulated game's controller,
    confirmed via a real physical-vs-synthetic A/B test. Must stay
    False until a genuinely different input path (e.g. a virtual
    gamepad) is built and proven."""
    assert synthetic_input_reaches_game_controller() is False
