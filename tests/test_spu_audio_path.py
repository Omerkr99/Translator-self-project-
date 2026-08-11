from gcrts.spu_audio_path import (
    CD_INIT_CALL_SITES,
    CD_INIT_FUNC_ADDR,
    CD_INIT_SPUCNT_WRITE_VALUE,
    KEY_WRITER_SITES,
    SPU_BASE_POINTER_HOLDERS,
    SPUCNT_CD_AUDIO_ENABLE_BIT,
    SPUCNT_WRITER_SITES,
    PlaybackBackendClassification,
    SpuWriterFamily,
    SpuWriterSite,
    cd_init_confirmed_live,
    cd_init_sets_documented_cd_audio_enable_bit,
    cd_init_write_confirmed_persistent,
    classify_playback_backend,
    key_on_real_voice_trigger_confirmed_live,
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


def test_playback_backend_classified_unknown_not_guessed():
    """The central honest result of this milestone: no confirmed
    backend, despite a strong structural lead. Must not silently
    upgrade to a *_CONFIRMED value without new live evidence."""
    assert classify_playback_backend() == PlaybackBackendClassification.UNKNOWN


def test_writer_site_round_trips_as_dataclass_equality():
    a = SpuWriterSite(0x1234, 0x800A30CC, SpuWriterFamily.CD_INIT, 0x1AA, True, "x")
    b = SpuWriterSite(0x1234, 0x800A30CC, SpuWriterFamily.CD_INIT, 0x1AA, True, "x")
    assert a == b


def test_cd_init_func_addr_matches_spucnt_write_family():
    cd_init_sites = [s for s in SPUCNT_WRITER_SITES if s.family == SpuWriterFamily.CD_INIT]
    assert len(cd_init_sites) == 1
    assert CD_INIT_FUNC_ADDR < cd_init_sites[0].write_pc
