"""Tests for gcrts.movie_detection -- pure classification logic, no
live capture dependency."""
from __future__ import annotations

from gcrts.movie_detection import (
    MOVIE_CATALOG,
    MovieMatchConfidence,
    classify_movie_state,
    get_movie_file,
    parse_exec_load_name,
    resolve_ambiguous_group_via_console_text,
)
from gcrts.overlay_identity import KNOWN_OVERLAYS, OverlayProfile


def _profile_named(name: str) -> OverlayProfile:
    return next(p for p in KNOWN_OVERLAYS if p.name == name)


def test_no_movie_active_when_overlay_is_none():
    result = classify_movie_state(None)
    assert result.movie_active is False
    assert result.confidence == MovieMatchConfidence.NONE
    assert result.candidate_files == ()


def test_no_movie_active_for_a_chapter_overlay():
    result = classify_movie_state(_profile_named("CAP0.EXE"))
    assert result.movie_active is False
    assert result.confidence == MovieMatchConfidence.NONE


def test_confirmed_live_match_for_mop():
    result = classify_movie_state(_profile_named("MOP.EXE"))
    assert result.movie_active is True
    assert result.candidate_files == ("OP.STR",)
    assert result.confidence == MovieMatchConfidence.CONFIRMED_LIVE


def test_mover_is_a_real_standalone_overlay_but_file_pairing_is_ambiguous():
    """MOVER.EXE is independently reachable (unlike MKUBI/MNINO/MPRO/
    MYOKO, which only ever appear grouped) -- but which of the two
    remaining unmatched files it plays isn't independently confirmed."""
    result = classify_movie_state(_profile_named("MOVER.EXE"))
    assert result.movie_active is True
    assert result.confidence == MovieMatchConfidence.AMBIGUOUS
    assert set(result.candidate_files) == {"GAI.STR", "KIKU.STR"}


def test_ambiguous_group_reports_multiple_candidates_not_a_guess():
    profile = _profile_named("MPRO.EXE (or MYOKO.EXE)")
    result = classify_movie_state(profile)
    assert result.movie_active is True
    assert result.confidence == MovieMatchConfidence.AMBIGUOUS
    assert set(result.candidate_files) == {"PRO.STR", "YOKO.STR"}


def test_ambiguous_group_kubi_nino_mrika():
    profile = _profile_named("MKUBI.EXE (or MNINO.EXE/MRIKA.EXE)")
    result = classify_movie_state(profile)
    assert result.confidence == MovieMatchConfidence.AMBIGUOUS
    assert len(result.candidate_files) >= 2


def test_movie_catalog_has_seven_real_files():
    assert len(MOVIE_CATALOG) == 7
    names = {e.name for e in MOVIE_CATALOG}
    assert names == {"GAI.STR", "KIKU.STR", "KUBI.STR", "NINO.STR", "OP.STR", "PRO.STR", "YOKO.STR"}


def test_op_str_is_the_largest_file():
    op = get_movie_file("OP.STR")
    assert op is not None
    assert all(op.size >= e.size for e in MOVIE_CATALOG)


def test_get_movie_file_returns_none_for_unknown_name():
    assert get_movie_file("NOTREAL.STR") is None


def test_every_confirmed_or_named_file_exists_in_catalog():
    from gcrts.movie_detection import OVERLAY_TO_MOVIE_FILE

    for file_name, _confidence in OVERLAY_TO_MOVIE_FILE.values():
        assert get_movie_file(file_name) is not None, f"{file_name} missing from MOVIE_CATALOG"


def test_parse_exec_load_name_from_real_captured_console_text():
    """The exact console line captured live this session (via GDB
    breakpoint at the movie overlay's entry PC, save slot 6)."""
    assert parse_exec_load_name(r"MovieLoad Exec : \MPRO.EXE;1") == "MPRO.EXE"


def test_parse_exec_load_name_plain_load_exec():
    assert parse_exec_load_name(r"Load Exec : \PROG.EXE;1") == "PROG.EXE"


def test_parse_exec_load_name_returns_none_for_unrelated_text():
    assert parse_exec_load_name("CD_init:addr=800a3108") is None


def test_resolve_ambiguous_group_confirms_mpro_not_myoko():
    result = resolve_ambiguous_group_via_console_text("MPRO.EXE (or MYOKO.EXE)", "MPRO.EXE")
    assert result == ("MPRO.EXE", "PRO.STR")


def test_resolve_ambiguous_group_rejects_name_outside_the_group():
    """MKUBI.EXE is a real exe name, but not a member of the MPRO/MYOKO
    group -- must not be resolved against the wrong group."""
    assert resolve_ambiguous_group_via_console_text("MPRO.EXE (or MYOKO.EXE)", "MKUBI.EXE") is None


def test_resolve_ambiguous_group_returns_none_for_mrika_no_name_correlation():
    """MRIKA.EXE is a real member of its group but has no name-correlated
    movie file at all -- must not be guessed."""
    result = resolve_ambiguous_group_via_console_text("MKUBI.EXE (or MNINO.EXE/MRIKA.EXE)", "MRIKA.EXE")
    assert result is None
