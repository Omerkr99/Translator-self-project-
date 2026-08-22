"""Regression guard: pcsx_lua/spu_playback_trace.lua hand-copies its
writer-site addresses from gcrts.spu_audio_path (Lua can't import
Python). This test parses the .lua source text for its WRITER_SITES
table and fails loudly if it ever drifts from the real Python
constants -- catching exactly the kind of silent divergence the Lua
script's own comment warns about."""
import re
from pathlib import Path

from gcrts.spu_audio_path import KEY_WRITER_SITES, SPUCNT_WRITER_SITES

LUA_PATH = Path(__file__).resolve().parent.parent / "pcsx_lua" / "spu_playback_trace.lua"


def _lua_writer_site_pcs() -> set[int]:
    text = LUA_PATH.read_text(encoding="utf-8")
    return {int(m, 16) for m in re.findall(r"pc\s*=\s*(0x[0-9A-Fa-f]+)", text)}


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
