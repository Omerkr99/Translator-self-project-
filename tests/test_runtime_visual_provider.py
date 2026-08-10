import struct

import gcrts.runtime_visual_provider as rvp
from gcrts.renderer1_profile import SLPS00102_BASE_PROFILE
from gcrts.runtime_visual_provider import RuntimeVisualProvider
from gcrts.screen_objects import TextRepresentation

RECORD_FORMAT = "<HHHHHHH"


class _FakeResponse:
    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _pack_record(counter, font_id, x, y, terminator=0xFFFF, reserved=0, sentinel=0x7FC0):
    return struct.pack(RECORD_FORMAT, counter, reserved, font_id, sentinel, x, y, terminator)


def _synthetic_ram_with_renderer1_active_but_no_prog_profile():
    """A 2MB RAM image where PROG.EXE's profile deliberately does NOT
    validate (the region is left zeroed, and the real PROG.EXE on disk
    -- read by _roots() -- won't match zeros) but Renderer 1's fingerprint
    and one active record DO -- i.e. a synthetic dialogue-scene-like RAM
    snapshot, the case this milestone's fix is specifically for."""
    ram = bytearray(2 * 1024 * 1024)
    profile = SLPS00102_BASE_PROFILE
    fp_addr = profile.code_fingerprint_addr & 0x1FFFFF
    ram[fp_addr : fp_addr + len(profile.code_fingerprint_bytes)] = profile.code_fingerprint_bytes
    record_addr = profile.record_base_addr & 0x1FFFFF
    ram[record_addr : record_addr + 14] = _pack_record(0x00, 0x15, 26, 152)
    return bytes(ram)


def test_scan_finds_renderer1_text_even_when_prog_profile_does_not_validate(monkeypatch):
    """The real-world case confirmed in GPU_OT_RUNTIME_MAP.md: a dialogue
    scene has no PROG.EXE roots at all. Before this milestone, scan()
    returned early on `if not roots: return frame, []` and NEVER checked
    Renderer 1 -- meaning a real dialogue scene would always report zero
    runtime text. This test proves that regression can't reappear."""
    ram = _synthetic_ram_with_renderer1_active_but_no_prog_profile()

    def fake_urlopen(url, timeout=5):
        assert "ram/raw" in url  # VRAM must never be fetched when roots is empty
        return _FakeResponse(ram)

    monkeypatch.setattr(rvp.urllib.request, "urlopen", fake_urlopen)

    provider = RuntimeVisualProvider([])
    frame, objects = provider.scan()

    assert frame != 0
    assert len(objects) == 1
    assert objects[0].text_representation == TextRepresentation.RUNTIME_TEXT_RENDERER_1
    assert objects[0].screen_bounds.x == 26 and objects[0].screen_bounds.y == 152


def test_scan_returns_nothing_when_neither_system_validates(monkeypatch):
    ram = bytes(2 * 1024 * 1024)
    monkeypatch.setattr(rvp.urllib.request, "urlopen", lambda url, timeout=5: _FakeResponse(ram))

    provider = RuntimeVisualProvider([])
    frame, objects = provider.scan()

    assert objects == []
