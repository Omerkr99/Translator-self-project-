"""Regression guard: pcsx_lua/spu_playback_trace.lua hand-copies its
writer-site addresses from gcrts.spu_audio_path (Lua can't import
Python). This test parses the .lua source text for its WRITER_SITES
table and fails loudly if it ever drifts from the real Python
constants -- catching exactly the kind of silent divergence the Lua
script's own comment warns about."""
import re
from pathlib import Path

from gcrts.cdrom_driver_map import COMMAND_ISSUE_ROUTINE_ADDR
from gcrts.cdrom_setfilter import OTHER_COMMAND_WRITE_SITES, SETFILTER_CALL_SITE_ADDR
from gcrts.overlay_identity import KNOWN_OVERLAYS
from gcrts.spu_audio_path import KEY_WRITER_SITES, SPUCNT_WRITER_SITES

LUA_PATH = Path(__file__).resolve().parent.parent / "pcsx_lua" / "spu_playback_trace.lua"


def _lua_writer_site_pcs() -> set[int]:
    text = LUA_PATH.read_text(encoding="utf-8")
    return {int(m, 16) for m in re.findall(r"pc\s*=\s*(0x[0-9A-Fa-f]+)", text)}


def _lua_cd_command_site_pcs() -> set[int]:
    text = LUA_PATH.read_text(encoding="utf-8")
    m = re.search(r"CD_COMMAND_SITES\s*=\s*\{([^}]*)\}", text)
    assert m is not None, "CD_COMMAND_SITES table not found in the Lua script"
    return {int(x, 16) for x in re.findall(r"0x[0-9A-Fa-f]+", m.group(1))}


def test_lua_file_exists():
    assert LUA_PATH.exists()


def test_lua_writer_sites_include_every_python_writer_site_pc():
    lua_pcs = _lua_writer_site_pcs()
    python_pcs = {s.write_pc for s in SPUCNT_WRITER_SITES} | {s.write_pc for s in KEY_WRITER_SITES}
    missing = python_pcs - lua_pcs
    assert not missing, f"pcsx_lua/spu_playback_trace.lua is missing writer PC(s) present in gcrts.spu_audio_path: {[hex(x) for x in missing]}"


def test_lua_writer_sites_do_not_invent_unknown_pcs():
    lua_pcs = _lua_writer_site_pcs()
    python_pcs = {s.write_pc for s in SPUCNT_WRITER_SITES} | {s.write_pc for s in KEY_WRITER_SITES}
    extra = lua_pcs - python_pcs
    assert not extra, f"pcsx_lua/spu_playback_trace.lua arms PC(s) not present in gcrts.spu_audio_path (a fabricated or stale address?): {[hex(x) for x in extra]}"


def test_lua_cd_command_sites_match_already_verified_python_constants():
    lua_pcs = _lua_cd_command_site_pcs()
    python_pcs = {SETFILTER_CALL_SITE_ADDR, COMMAND_ISSUE_ROUTINE_ADDR, *OTHER_COMMAND_WRITE_SITES}
    assert lua_pcs == python_pcs, (
        f"pcsx_lua/spu_playback_trace.lua's CD_COMMAND_SITES ({[hex(x) for x in sorted(lua_pcs)]}) does not match "
        f"gcrts.cdrom_setfilter/gcrts.cdrom_driver_map's already-verified sites ({[hex(x) for x in sorted(python_pcs)]})"
    )


def _lua_known_overlays() -> dict[str, tuple[int, str]]:
    text = LUA_PATH.read_text(encoding="utf-8")
    m = re.search(r"KNOWN_OVERLAYS\s*=\s*\{(.*?)\n\}", text, re.DOTALL)
    assert m is not None, "KNOWN_OVERLAYS table not found in the Lua script"
    rows = re.findall(r'name\s*=\s*"([^"]+)",\s*pc0\s*=\s*(0x[0-9A-Fa-f]+),\s*sig\s*=\s*"([0-9a-f]+)"', m.group(1))
    return {name: (int(pc0, 16), sig) for name, pc0, sig in rows}


def test_lua_known_overlays_matches_python_overlay_identity_exactly():
    lua_overlays = _lua_known_overlays()
    python_overlays = {p.name: (p.pc0, p.signature.hex()) for p in KNOWN_OVERLAYS}
    assert lua_overlays == python_overlays, (
        "pcsx_lua/spu_playback_trace.lua's KNOWN_OVERLAYS has drifted from gcrts.overlay_identity.KNOWN_OVERLAYS -- "
        f"lua={lua_overlays} python={python_overlays}"
    )


def test_lua_has_safe_baseline_only_flag():
    text = LUA_PATH.read_text(encoding="utf-8")
    assert re.search(r"local\s+SAFE_BASELINE_ONLY\s*=", text), (
        "pcsx_lua/spu_playback_trace.lua must define a SAFE_BASELINE_ONLY flag guarding the overlay-dependent breakpoints"
    )
