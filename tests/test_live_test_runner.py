"""Tests for gcrts.live_test_runner -- fake renderer and fake adapter,
no real display or emulator connection required."""
from __future__ import annotations

from gcrts.emulator_adapter import EmulatorAdapter, EmulatorCapabilities, EmulatorCapability
from gcrts.evidence_bundle import OverlayBackend, ValidationResult
from gcrts.live_test_runner import run_generic_gameplay_sentence_scenario
from gcrts.overlay_identity import KNOWN_OVERLAYS


class _FakeRenderer:
    def __init__(self):
        self.shown: list[str] = []
        self.pump_count = 0
        self.hidden = False

    def show(self, text: str) -> None:
        self.shown.append(text)

    def pump(self) -> None:
        self.pump_count += 1

    def hide(self) -> None:
        self.hidden = True


class _FakeAdapter(EmulatorAdapter):
    def __init__(self, capabilities: frozenset[EmulatorCapability], overlay_name: str = "CAP0.EXE"):
        self._capabilities = capabilities
        self._profile = next(p for p in KNOWN_OVERLAYS if p.name == overlay_name)
        self.screenshot_calls = 0

    def capabilities(self) -> EmulatorCapabilities:
        return EmulatorCapabilities(supported=self._capabilities)

    def read_memory(self, addr, length):
        if addr == self._profile.pc0 and length == len(self._profile.signature):
            return self._profile.signature
        return b"\x00" * length

    def write_memory(self, addr, data):
        return True

    def set_breakpoint(self, addr):
        return True

    def clear_breakpoint(self, addr):
        return True

    def screenshot(self):
        self.screenshot_calls += 1
        return object()

    def load_state(self, slot):
        return True

    def pause(self):
        pass

    def resume(self):
        pass


def _fake_clock():
    state = {"t": 0.0}

    def now():
        return state["t"]

    def sleep(seconds):
        state["t"] += seconds

    return now, sleep


def test_scenario_passes_and_captures_both_screenshots():
    caps = frozenset({EmulatorCapability.MEMORY_READ, EmulatorCapability.SCREENSHOT})
    adapter = _FakeAdapter(caps)
    renderer = _FakeRenderer()
    now, sleep = _fake_clock()
    saved = {}

    bundle = run_generic_gameplay_sentence_scenario(
        adapter,
        renderer,
        duration_seconds=1.0,
        screenshot_host=lambda: "host-image",
        save_host_screenshot=lambda img, path: saved.setdefault("host", (img, path)),
        save_emulator_screenshot=lambda img, path: saved.setdefault("emu", (img, path)),
        host_screenshot_path="evidence/host.png",
        emulator_screenshot_path="evidence/emu.png",
        poll_interval_seconds=0.1,
        sleep=sleep,
        now=now,
    )

    assert bundle.result == ValidationResult.PASS
    assert bundle.backend == OverlayBackend.EXTERNAL_HOST
    assert renderer.shown == ["TOOLKIT TEST"]
    assert renderer.hidden is True
    assert adapter.screenshot_calls == 1
    assert saved["host"] == ("host-image", "evidence/host.png")
    assert bundle.host_screenshot_path == "evidence/host.png"
    assert bundle.emulator_screenshot_path == "evidence/emu.png"
    assert bundle.runtime_context["executable_id"] == "CAP0.EXE"
    assert any("overlay shown" in e for e in bundle.event_log)
    assert any("overlay hidden" in e for e in bundle.event_log)


def test_scenario_reports_unsupported_when_capability_missing():
    caps = frozenset({EmulatorCapability.MEMORY_READ})  # SCREENSHOT missing
    adapter = _FakeAdapter(caps)
    renderer = _FakeRenderer()
    now, sleep = _fake_clock()

    bundle = run_generic_gameplay_sentence_scenario(adapter, renderer, sleep=sleep, now=now)

    assert bundle.result == ValidationResult.UNSUPPORTED
    assert renderer.shown == []  # never even tried to render
    assert "SCREENSHOT" in bundle.event_log[0]


def test_runtime_context_is_embedded_in_the_bundle():
    caps = frozenset({EmulatorCapability.MEMORY_READ, EmulatorCapability.SCREENSHOT})
    adapter = _FakeAdapter(caps, overlay_name="MOP.EXE")
    renderer = _FakeRenderer()
    now, sleep = _fake_clock()

    bundle = run_generic_gameplay_sentence_scenario(adapter, renderer, duration_seconds=0.5, sleep=sleep, now=now)

    assert bundle.runtime_context["executable_id"] == "MOP.EXE"
    assert bundle.runtime_context["mode"] == "MOVIE"
    assert bundle.runtime_context["movie_id"] == "OP.STR"


def test_renderer_is_pumped_during_the_wait():
    caps = frozenset({EmulatorCapability.MEMORY_READ, EmulatorCapability.SCREENSHOT})
    adapter = _FakeAdapter(caps)
    renderer = _FakeRenderer()
    now, sleep = _fake_clock()

    run_generic_gameplay_sentence_scenario(adapter, renderer, duration_seconds=1.0, poll_interval_seconds=0.1, sleep=sleep, now=now)

    assert renderer.pump_count >= 9  # ~1.0s / 0.1s poll interval
