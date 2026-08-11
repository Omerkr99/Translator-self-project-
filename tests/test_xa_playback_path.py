from gcrts.xa_playback_path import (
    OLD_READN_CYCLE_STATUS,
    PLAYBACK_PATH_HYPOTHESES,
    READS_COMMAND,
    READS_EVER_OBSERVED,
    HypothesisStatus,
    reads_command_confirmed_live,
)


def test_reads_command_is_the_publicly_documented_value():
    assert READS_COMMAND == 0x1B


def test_reads_never_observed_live():
    """Across every capture this project has taken -- honestly false,
    not a placeholder."""
    assert READS_EVER_OBSERVED is False
    assert reads_command_confirmed_live() is False


def test_old_readn_cycle_is_permanently_ruled_out():
    assert OLD_READN_CYCLE_STATUS == "RULED_OUT_AS_XA_AUDIO_PATH"


def test_all_six_fallback_hypotheses_are_present():
    assert len(PLAYBACK_PATH_HYPOTHESES) == 6
    ids = [h.hypothesis_id for h in PLAYBACK_PATH_HYPOTHESES]
    assert ids == [1, 2, 3, 4, 5, 6]


def test_cdda_hypothesis_is_ruled_out_with_real_evidence():
    """The decisive finding this milestone: the real disc .cue file
    proves CD-DA is structurally impossible on this disc."""
    cdda = next(h for h in PLAYBACK_PATH_HYPOTHESES if h.hypothesis_id == 6)
    assert cdda.status == HypothesisStatus.RULED_OUT
    assert "MODE2/2352" in cdda.evidence or "track" in cdda.evidence.lower()


def test_open_hypotheses_are_not_silently_marked_resolved():
    """Regression: hypotheses 2, 4, 5 have no evidence that resolves
    them -- must stay OPEN, not be upgraded without a real finding."""
    open_ids = {2, 4, 5}
    for h in PLAYBACK_PATH_HYPOTHESES:
        if h.hypothesis_id in open_ids:
            assert h.status == HypothesisStatus.OPEN


def test_no_hypothesis_falsely_confirms_a_real_path():
    """Regression: no hypothesis may be marked RULED_OUT or DOWNGRADED
    without an evidence string backing it (guards against a future
    edit silently flipping a status without adding real support)."""
    for h in PLAYBACK_PATH_HYPOTHESES:
        if h.status in (HypothesisStatus.RULED_OUT, HypothesisStatus.DOWNGRADED):
            assert h.evidence.strip() != ""
