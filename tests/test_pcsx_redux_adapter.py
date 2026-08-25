"""Tests for gcrts.pcsx_redux_adapter -- no live emulator connection;
GDB calls go through an injected fake client, HTTP calls are
monkeypatched, matching this project's established convention (see
tests/test_runtime_visual_provider.py)."""
from __future__ import annotations

import io

import pytest

from gcrts.emulator_adapter import EmulatorCapability
from gcrts.pcsx_redux_adapter import PCSXReduxAdapter


class _FakeGdbClient:
    def __init__(self):
        self.memory: dict[int, bytes] = {}
        self.breakpoints: set[int] = set()
        self.paused = False
        self.closed = False

    def read_memory(self, addr, length):
        return self.memory.get(addr, b"\x00" * length)

    def write_memory(self, addr, data):
        self.memory[addr] = bytes(data)
        return True

    def set_breakpoint(self, addr):
        self.breakpoints.add(addr)
        return True

    def remove_breakpoint(self, addr):
        self.breakpoints.discard(addr)
        return True

    def interrupt(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def close(self):
        self.closed = True


def _make_adapter() -> tuple[PCSXReduxAdapter, _FakeGdbClient]:
    adapter = PCSXReduxAdapter(connect=False)
    fake = _FakeGdbClient()
    adapter._client = fake
    return adapter, fake


def test_capabilities_advertise_only_proven_mechanisms():
    adapter, _ = _make_adapter()
    caps = adapter.capabilities()
    assert caps.supports(EmulatorCapability.MEMORY_READ)
    assert caps.supports(EmulatorCapability.MEMORY_WRITE)
    assert caps.supports(EmulatorCapability.BREAKPOINTS)
    assert caps.supports(EmulatorCapability.SCREENSHOT)
    assert caps.supports(EmulatorCapability.SAVE_STATE_LOAD)
    assert caps.supports(EmulatorCapability.PAUSE_RESUME)
    # deliberately NOT claimed -- no proven mechanism exists yet
    assert not caps.supports(EmulatorCapability.FRAME_COUNTER)
    assert not caps.supports(EmulatorCapability.AUDIO_CONTROL)


def test_read_write_memory_round_trip_via_fake_client():
    adapter, fake = _make_adapter()
    assert adapter.write_memory(0x80010000, b"\x01\x02\x03") is True
    assert adapter.read_memory(0x80010000, 3) == b"\x01\x02\x03"


def test_set_and_clear_breakpoint():
    adapter, fake = _make_adapter()
    assert adapter.set_breakpoint(0x8006E5E4) is True
    assert 0x8006E5E4 in fake.breakpoints
    assert adapter.clear_breakpoint(0x8006E5E4) is True
    assert 0x8006E5E4 not in fake.breakpoints


def test_pause_resume_delegate_to_client():
    adapter, fake = _make_adapter()
    adapter.pause()
    assert fake.paused is True
    adapter.resume()
    assert fake.paused is False


def test_shutdown_closes_client_and_clears_reference():
    adapter, fake = _make_adapter()
    adapter.shutdown()
    assert fake.closed is True
    assert adapter._client is None


def test_load_state_calls_expected_url(monkeypatch):
    calls = []

    class _FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(request, timeout=10):
        calls.append(request.full_url)
        return _FakeResponse()

    import gcrts.pcsx_redux_adapter as mod

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    adapter, _ = _make_adapter()
    assert adapter.load_state(6) is True
    assert calls == ["http://127.0.0.1:8080/api/v1/state/load?slot=6"]


def test_screenshot_decodes_vram_dump(monkeypatch):
    width, height = 4, 4
    raw = bytearray(1024 * 512 * 2)
    # set pixel (0,0) to a known 5-5-5 value: R=31,G=0,B=0 -> value=31
    raw[0] = 31
    raw[1] = 0

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return bytes(raw)

    def fake_urlopen(url, timeout=10):
        return _FakeResponse()

    import gcrts.pcsx_redux_adapter as mod

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    adapter, _ = _make_adapter()
    image = adapter.screenshot(region=(0, 0, width, height))
    assert image.size == (width, height)
    assert image.getpixel((0, 0)) == (255, 0, 0)
