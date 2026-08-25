"""Tests for gcrts.runtime_context -- pure, injected read_memory, no
live emulator dependency. Uses the real KNOWN_OVERLAYS signatures so
these tests exercise the actual overlay_identity/movie_detection
composition, not a reimplemented fake."""
from __future__ import annotations

from gcrts.overlay_identity import KNOWN_OVERLAYS
from gcrts.runtime_context import RuntimeContextResolver, RuntimeMode
from gcrts.evidence import Confidence


def _profile_named(name: str):
    return next(p for p in KNOWN_OVERLAYS if p.name == name)


def _read_memory_for(profile):
    def read_memory(addr: int, length: int) -> bytes | None:
        if addr == profile.pc0 and length == len(profile.signature):
            return profile.signature
        return b"\x00" * length

    return read_memory


def test_unknown_overlay_resolves_to_unknown_mode():
    resolver = RuntimeContextResolver()
    ctx = resolver.resolve(lambda addr, length: b"\x00" * length)
    assert ctx.executable_id is None
    assert ctx.mode == RuntimeMode.UNKNOWN
    assert ctx.claims[0].confidence == Confidence.UNKNOWN


def test_prog_exe_resolves_to_menu_inferred():
    profile = _profile_named("PROG.EXE")
    resolver = RuntimeContextResolver()
    ctx = resolver.resolve(_read_memory_for(profile))
    assert ctx.executable_id == "PROG.EXE"
    assert ctx.mode == RuntimeMode.MENU
    mode_claim = next(c for c in ctx.claims if "mode is MENU" in c.claim)
    assert mode_claim.confidence == Confidence.INFERRED


def test_cap0_resolves_to_gameplay_inferred():
    profile = _profile_named("CAP0.EXE")
    resolver = RuntimeContextResolver()
    ctx = resolver.resolve(_read_memory_for(profile))
    assert ctx.executable_id == "CAP0.EXE"
    assert ctx.mode == RuntimeMode.GAMEPLAY


def test_mop_exe_with_movie_active_resolves_to_movie_mode():
    profile = _profile_named("MOP.EXE")
    resolver = RuntimeContextResolver()
    ctx = resolver.resolve(_read_memory_for(profile))
    assert ctx.executable_id == "MOP.EXE"
    assert ctx.mode == RuntimeMode.MOVIE
    assert ctx.movie_id == "OP.STR"
    movie_claim = next(c for c in ctx.claims if "movie active" in c.claim)
    assert movie_claim.confidence == Confidence.CONFIRMED_LIVE


def test_executable_identity_claim_is_always_confirmed_live_when_matched():
    profile = _profile_named("CAP1.EXE")
    resolver = RuntimeContextResolver()
    ctx = resolver.resolve(_read_memory_for(profile))
    identity_claim = next(c for c in ctx.claims if "resident executable" in c.claim)
    assert identity_claim.confidence == Confidence.CONFIRMED_LIVE


def test_to_dict_round_trips_basic_shape():
    profile = _profile_named("MOP.EXE")
    resolver = RuntimeContextResolver()
    ctx = resolver.resolve(_read_memory_for(profile))
    d = ctx.to_dict()
    assert d["executable_id"] == "MOP.EXE"
    assert d["mode"] == "MOVIE"
    assert d["movie_id"] == "OP.STR"
    assert isinstance(d["claims"], list) and len(d["claims"]) >= 2
