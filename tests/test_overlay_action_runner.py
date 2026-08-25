"""Tests for gcrts.overlay_action_runner -- fake renderer and fake
adapter, no real display or emulator connection required. Mirrors
tests/test_live_test_runner.py's cases (proving the data-driven path
produces the same shape as Stage 2's hand-written scenario) plus the
new UNSUPPORTED-payload-kind path Stage 3 adds."""
from __future__ import annotations

from gcrts.emulator_adapter import EmulatorAdapter, EmulatorCapabilities, EmulatorCapability
from gcrts.evidence_bundle import OverlayBackend, ValidationResult
from gcrts.overlay_action import ImagePayload, OverlayAction, TextPayload
from gcrts.overlay_action_runner import run_overlay_action
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


def test_text_action_passes_and_matches_stage2_shape():
    caps = frozenset({EmulatorCapability.MEMORY_READ, EmulatorCapability.SCREENSHOT})
    adapter = _FakeAdapter(caps)
    renderer = _FakeRenderer()
    now, sleep = _fake_clock()
    action = OverlayAction(id="generic_gameplay_sentence", payload=TextPayload("TOOLKIT TEST"), duration_seconds=1.0)

    bundle = run_overlay_action(
        action, adapter, renderer,
        screenshot_host=lambda: "host-image",
        poll_interval_seconds=0.1, sleep=sleep, now=now,
    )

    assert bundle.result == ValidationResult.PASS
    assert bundle.backend == OverlayBackend.EXTERNAL_HOST
    assert bundle.scenario_name == "generic_gameplay_sentence"
    assert renderer.shown == ["TOOLKIT TEST"]
    assert renderer.hidden is True
    assert adapter.screenshot_calls == 1


def test_action_id_becomes_scenario_name():
    caps = frozenset({EmulatorCapability.MEMORY_READ, EmulatorCapability.SCREENSHOT})
    adapter = _FakeAdapter(caps)
    renderer = _FakeRenderer()
    now, sleep = _fake_clock()
    action = OverlayAction(id="my_custom_scenario", payload=TextPayload("HELLO"), duration_seconds=0.5)

    bundle = run_overlay_action(action, adapter, renderer, sleep=sleep, now=now)

    assert bundle.scenario_name == "my_custom_scenario"
    assert renderer.shown == ["HELLO"]


def test_missing_capability_reports_unsupported():
    caps = frozenset({EmulatorCapability.MEMORY_READ})  # SCREENSHOT missing
    adapter = _FakeAdapter(caps)
    renderer = _FakeRenderer()
    now, sleep = _fake_clock()
    action = OverlayAction(id="x", payload=TextPayload("hi"))

    bundle = run_overlay_action(action, adapter, renderer, sleep=sleep, now=now)

    assert bundle.result == ValidationResult.UNSUPPORTED
    assert renderer.shown == []


def test_unimplemented_payload_kind_reports_unsupported_without_touching_renderer():
    caps = frozenset({EmulatorCapability.MEMORY_READ, EmulatorCapability.SCREENSHOT})
    adapter = _FakeAdapter(caps)
    renderer = _FakeRenderer()
    action = OverlayAction(id="x", payload=ImagePayload(image_path="logo.png"))

    bundle = run_overlay_action(action, adapter, renderer)

    assert bundle.result == ValidationResult.UNSUPPORTED
    assert "ImagePayload" in bundle.event_log[0]
    assert renderer.shown == []
    assert adapter.screenshot_calls == 0


def test_default_duration_used_when_action_omits_it():
    caps = frozenset({EmulatorCapability.MEMORY_READ, EmulatorCapability.SCREENSHOT})
    adapter = _FakeAdapter(caps)
    renderer = _FakeRenderer()
    now, sleep = _fake_clock()
    action = OverlayAction(id="x", payload=TextPayload("hi"))  # duration_seconds left as None

    bundle = run_overlay_action(action, adapter, renderer, poll_interval_seconds=0.1, sleep=sleep, now=now)

    assert bundle.result == ValidationResult.PASS
    assert now() >= 3.0  # DEFAULT_DURATION_SECONDS
