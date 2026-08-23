from gcrts.overlay_identity import (
    KNOWN_OVERLAYS,
    SIGNATURE_LENGTH,
    identify_overlay,
    overlay_covers_known_breakpoints,
)


def _fake_read_memory(overlay_name):
    """Returns a read_memory callable that reports the REAL signature
    only for one specific overlay's own pc0, and None (never even a
    plausible-looking wrong value) for everything else -- so a test
    passing can only mean the address-to-name mapping itself is
    correct, not a coincidental byte match."""
    target = next(p for p in KNOWN_OVERLAYS if p.name == overlay_name)

    def read_memory(addr, length):
        if addr == target.pc0 and length == SIGNATURE_LENGTH:
            return target.signature
        return None

    return read_memory


def test_identify_overlay_prog_exe():
    result = identify_overlay(_fake_read_memory("PROG.EXE"))
    assert result is not None
    assert result.name == "PROG.EXE"


def test_identify_overlay_cap0_exe():
    result = identify_overlay(_fake_read_memory("CAP0.EXE"))
    assert result is not None
    assert result.name == "CAP0.EXE"


def test_identify_overlay_no_match_returns_none():
    result = identify_overlay(lambda addr, length: None)
    assert result is None


def test_identify_overlay_never_guesses_from_wrong_bytes():
    """A live read that doesn't exactly match any known signature must
    never be coerced into the closest-looking profile."""
    result = identify_overlay(lambda addr, length: b"\x00" * SIGNATURE_LENGTH)
    assert result is None


def test_all_known_overlays_have_16_byte_signatures():
    for profile in KNOWN_OVERLAYS:
        assert len(profile.signature) == SIGNATURE_LENGTH, profile.name


def test_all_known_overlay_signatures_are_distinct_per_name():
    """Two overlays are allowed to share a signature (confirmed real
    for the movie-player family) but this module must never register
    the exact same (pc0, signature) pair for two DIFFERENT entries --
    that would be a genuine data-entry bug, not a real coincidence."""
    seen = {}
    for profile in KNOWN_OVERLAYS:
        key = (profile.pc0, profile.signature)
        assert key not in seen, f"{profile.name} duplicates {seen[key]}'s (pc0, signature)"
        seen[key] = profile.name


# --- overlay_covers_known_breakpoints -------------------------------------------


def test_prog_exe_does_not_cover_known_breakpoints():
    """Real, live-discovered correction: PROG.EXE's own range
    (0x80035000-0x8006a800) ends before gcrts.spu_audio_path's
    breakpoint addresses (0x800866xx+) even begin."""
    prog = next(p for p in KNOWN_OVERLAYS if p.name == "PROG.EXE")
    assert overlay_covers_known_breakpoints(prog) is False


def test_cap0_exe_covers_known_breakpoints():
    cap0 = next(p for p in KNOWN_OVERLAYS if p.name == "CAP0.EXE")
    assert overlay_covers_known_breakpoints(cap0) is True


def test_movie_player_family_does_not_cover_known_breakpoints():
    mover = next(p for p in KNOWN_OVERLAYS if p.name == "MOVER.EXE")
    assert overlay_covers_known_breakpoints(mover) is False


def test_address_range_property():
    cap0 = next(p for p in KNOWN_OVERLAYS if p.name == "CAP0.EXE")
    assert cap0.address_range == (0x80045000, 0x80045000 + 0x05F000)
