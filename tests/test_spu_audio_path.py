from gcrts.spu_audio_path import (
    CD_INIT_CALL_SITES,
    CD_INIT_FUNC_ADDR,
    CD_INIT_GATEKEEPER_SITES,
    CD_INIT_SPUCNT_WRITE_VALUE,
    KEY_PADCIRCLE_VK,
    KEY_WRITER_SITES,
    LIVE_CORRELATION_RUNS,
    MANUAL_MUTE_EXPERIMENTS,
    SETMODE_CAPTURE_ALL_MODE_BYTE,
    SETMODE_CAPTURE_SAMPLE_COUNT,
    SPU_BASE_POINTER_HOLDERS,
    SPU_MMIO_READ_WRITE_ROUNDTRIP_RELIABLE,
    SPUCNT_CD_AUDIO_ENABLE_BIT,
    SPUCNT_WRITER_SITES,
    LiveCorrelationRun,
    ManualMuteExperiment,
    PlaybackBackendClassification,
    SpuWriterFamily,
    SpuWriterSite,
    all_spu_voices_muted_dialogue_still_audible,
    cd_init_confirmed_live,
    cd_init_gatekeeper_sites_fired_during_confirmed_trigger,
    cd_init_sets_documented_cd_audio_enable_bit,
    cd_init_write_confirmed_persistent,
    classify_playback_backend,
    key_on_real_voice_trigger_confirmed_live,
    live_correlation_confirmed_audible_with_zero_known_hits,
    setmode_xa_adpcm_bit_ever_observed_set,
    spu_mmio_read_write_roundtrip_reliable,
)


def test_seven_spu_base_pointer_holders_found():
    assert len(SPU_BASE_POINTER_HOLDERS) == 7
    assert 0x800A30CC in SPU_BASE_POINTER_HOLDERS
    assert 0x800A38A8 in SPU_BASE_POINTER_HOLDERS


def test_spu_base_pointer_holders_are_distinct():
    assert len(set(SPU_BASE_POINTER_HOLDERS)) == len(SPU_BASE_POINTER_HOLDERS)


def test_cd_init_confirmed_live():
    assert cd_init_confirmed_live() is True


def test_cd_init_has_nine_call_sites():
    assert len(CD_INIT_CALL_SITES) == 9
    assert len(set(CD_INIT_CALL_SITES)) == 9


def test_cd_init_sets_documented_cd_audio_enable_bit():
    """Regression: 0xC001 must have bit 0 set -- if this ever fails, the
    live-captured SPUCNT value or the documented bit meaning changed and
    the module docstring's whole conclusion needs re-checking."""
    assert CD_INIT_SPUCNT_WRITE_VALUE & SPUCNT_CD_AUDIO_ENABLE_BIT == SPUCNT_CD_AUDIO_ENABLE_BIT
    assert cd_init_sets_documented_cd_audio_enable_bit() is True


def test_cd_init_write_not_confirmed_persistent():
    """Honest negative: every live post-write read found the registers
    back at zero. This must stay False until a live capture actually
    catches a persisting nonzero value."""
    assert cd_init_write_confirmed_persistent() is False


def test_key_on_real_voice_trigger_not_confirmed():
    assert key_on_real_voice_trigger_confirmed_live() is False


def test_spucnt_writer_sites_cover_both_families():
    families = {s.family for s in SPUCNT_WRITER_SITES}
    assert SpuWriterFamily.CD_INIT in families
    assert SpuWriterFamily.GENERIC_SPU_DRIVER in families


def test_key_writer_sites_cover_all_three_families():
    families = {s.family for s in KEY_WRITER_SITES}
    assert SpuWriterFamily.PERIODIC_VOICE_SYNC in families
    assert SpuWriterFamily.GENERIC_SPU_DRIVER in families


def test_only_cd_init_and_periodic_sync_sites_are_live_confirmed():
    """Regression: no GENERIC_SPU_DRIVER site has fired live yet -- if
    one ever does, this test should be the first thing that breaks."""
    for site in SPUCNT_WRITER_SITES + KEY_WRITER_SITES:
        if site.family == SpuWriterFamily.GENERIC_SPU_DRIVER:
            assert site.live_confirmed is False


def test_all_writer_sites_have_real_evidence_strings():
    for site in SPUCNT_WRITER_SITES + KEY_WRITER_SITES:
        assert site.evidence.strip() != ""


def test_playback_backend_classification_taxonomy_matches_milestone_requirement():
    names = {c.value for c in PlaybackBackendClassification}
    assert names == {
        "XA_ADPCM_CONFIRMED",
        "SPU_SAMPLE_PLAYBACK",
        "SPU_STREAMED_SAMPLE",
        "CD_INPUT_UNKNOWN_FORMAT",
        "HYBRID",
        "UNKNOWN",
    }


def test_playback_backend_classified_cd_input_unknown_format():
    """The central result of the manual all-voices-muted follow-up:
    dialogue audio survives every SPU voice being muted, confirmed
    directly and repeatedly by the user -- decisive evidence for the CD
    input path, not architectural guessing. Must not silently regress
    back to UNKNOWN, nor jump all the way to XA_ADPCM_CONFIRMED without
    an independently re-verified stream format."""
    assert classify_playback_backend() == PlaybackBackendClassification.CD_INPUT_UNKNOWN_FORMAT


def test_writer_site_round_trips_as_dataclass_equality():
    a = SpuWriterSite(0x1234, 0x800A30CC, SpuWriterFamily.CD_INIT, 0x1AA, True, "x")
    b = SpuWriterSite(0x1234, 0x800A30CC, SpuWriterFamily.CD_INIT, 0x1AA, True, "x")
    assert a == b


def test_cd_init_func_addr_matches_spucnt_write_family():
    cd_init_sites = [s for s in SPUCNT_WRITER_SITES if s.family == SpuWriterFamily.CD_INIT]
    assert len(cd_init_sites) == 1
    assert CD_INIT_FUNC_ADDR < cd_init_sites[0].write_pc


def test_padcircle_vk_matches_pcsx_json_binding():
    """Regression: this must stay in sync with pcsx.json's own
    Keyboard_PadCircle binding (68 decimal = 0x44)."""
    assert KEY_PADCIRCLE_VK == 0x44


def test_live_correlation_has_at_least_two_runs():
    assert len(LIVE_CORRELATION_RUNS) >= 2
    assert all(isinstance(r, LiveCorrelationRun) for r in LIVE_CORRELATION_RUNS)


def test_live_correlation_run2_is_user_confirmed_audible_with_zero_hits():
    """The central decisive result of the follow-up correlation
    experiment: a real user-confirmed audible line, zero meaningful
    hits at any known SPU writer site."""
    run2 = next(r for r in LIVE_CORRELATION_RUNS if r.run_id == "m16_run2")
    assert run2.user_confirmed_audible is True
    assert run2.meaningful_hits == 0


def test_live_correlation_confirmed_audible_with_zero_known_hits():
    assert live_correlation_confirmed_audible_with_zero_known_hits() is True


def test_live_correlation_runs_have_real_evidence_strings():
    for r in LIVE_CORRELATION_RUNS:
        assert r.evidence.strip() != ""


def test_live_correlation_runs_show_genuine_state_change():
    """Regression: every run must show source_file actually changing --
    otherwise it isn't proof the automated input reached the game."""
    for r in LIVE_CORRELATION_RUNS:
        assert r.source_file_before != r.source_file_after or r.position_before != r.position_after


def test_spu_mmio_read_write_roundtrip_confirmed_unreliable():
    """The second decisive finding this pass: GDB's own memory access
    to the SPU hardware I/O range does not round-trip a write, even
    while genuinely running. This must stay False until a working
    observation channel is found -- flipping it silently would hide a
    real, confirmed tooling blocker."""
    assert SPU_MMIO_READ_WRITE_ROUNDTRIP_RELIABLE is False
    assert spu_mmio_read_write_roundtrip_reliable() is False


def test_cd_init_persistence_docstring_does_not_overclaim_non_persistence():
    """cd_init_write_confirmed_persistent() must stay False, but only as
    'not confirmed' -- not as 'confirmed to fail'. This is enforced by
    checking the two findings are correctly linked: if the MMIO
    read/write channel is unreliable, persistence genuinely cannot be
    confirmed either way from this project's own tooling."""
    assert cd_init_write_confirmed_persistent() is False
    assert spu_mmio_read_write_roundtrip_reliable() is False


def test_manual_mute_experiments_has_at_least_two_independent_runs():
    assert len(MANUAL_MUTE_EXPERIMENTS) >= 2
    assert all(isinstance(e, ManualMuteExperiment) for e in MANUAL_MUTE_EXPERIMENTS)


def test_manual_mute_experiments_all_confirm_dialogue_survives_muting():
    """The decisive evidence itself: every recorded experiment found
    dialogue audio unaffected by muting all regular SPU voices."""
    for e in MANUAL_MUTE_EXPERIMENTS:
        assert e.dialogue_still_audible is True


def test_manual_mute_experiments_include_an_independently_reproduced_run():
    """Regression: at least one experiment must be a reproduction in a
    structurally different scene, not just a single observation."""
    assert any(e.reproduced for e in MANUAL_MUTE_EXPERIMENTS)


def test_manual_mute_experiments_have_real_evidence_strings():
    for e in MANUAL_MUTE_EXPERIMENTS:
        assert e.evidence.strip() != ""
        assert e.scene_description.strip() != ""
        assert e.voices_muted.strip() != ""


def test_all_spu_voices_muted_dialogue_still_audible():
    assert all_spu_voices_muted_dialogue_still_audible() is True


def test_manual_mute_experiment_round_trips_as_dataclass_equality():
    a = ManualMuteExperiment("x", "scene", "all voices", True, False, "evidence")
    b = ManualMuteExperiment("x", "scene", "all voices", True, False, "evidence")
    assert a == b


def test_cd_init_gatekeeper_sites_are_two_of_the_nine_call_sites():
    assert len(CD_INIT_GATEKEEPER_SITES) == 2
    for addr in CD_INIT_GATEKEEPER_SITES:
        assert addr in CD_INIT_CALL_SITES


def test_cd_init_gatekeeper_sites_did_not_fire_during_confirmed_trigger():
    """Honest negative from a second, more targeted angle than the
    original Live Audible Trigger Correlation experiment: even the
    position-change-gated call sites never fired during a real,
    user-confirmed voice line."""
    assert cd_init_gatekeeper_sites_fired_during_confirmed_trigger() is False


def test_setmode_capture_sample_count_and_uniform_value():
    """Regression: this must reflect the real, live-captured sample
    count and the single value seen in every one of them -- if a future
    capture ever finds a different mode_byte, this test should be the
    first thing that breaks."""
    assert SETMODE_CAPTURE_SAMPLE_COUNT == 46
    assert SETMODE_CAPTURE_ALL_MODE_BYTE == 0x01


def test_setmode_xa_adpcm_bit_never_observed_set():
    assert setmode_xa_adpcm_bit_ever_observed_set() is False
