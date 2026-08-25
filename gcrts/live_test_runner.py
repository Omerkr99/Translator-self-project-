"""LiveTestRunner: the external-overlay smoke-test scenario
(`docs/overlay_engine/PS1_OVERLAY_RUNTIME_SYSTEM_DESIGN.md` §4.1/§12,
`PS1_OVERLAY_RUNTIME_REQUIREMENTS.md` VAL-001/VAL-002/VAL-005) --
Stage 2 of the staged plan in `docs/overlay_engine/GROUNDING_ANALYSIS.md`.

Orchestrates: resolve `RuntimeContext` via an `EmulatorAdapter`, show a
message through a renderer for a configured duration (capturing a host
screenshot and an emulator VRAM screenshot partway through), hide the
overlay, and write an `EvidenceBundle`.

Written against small duck-typed interfaces (`renderer` needs
`show`/`pump`/`hide`; `adapter` needs `capabilities`/`read_memory`/
`screenshot`; `screenshot_host` is an injected callable) precisely so
this orchestration logic -- timing, event log, PASS/FAIL/UNSUPPORTED
determination, evidence construction -- is fully testable with fakes,
with zero dependency on a real display or emulator. The actual live
proof (a real Tk window, a real PCSX-Redux connection) is a separate,
manually-run smoke test, not a pytest test, matching this project's
own established boundary between tested orchestration logic and
manually-verified live/GUI behavior.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Callable, Protocol

from gcrts.emulator_adapter import EmulatorAdapter, EmulatorCapability
from gcrts.evidence_bundle import EvidenceBundle, OverlayBackend, ValidationResult
from gcrts.runtime_context import RuntimeContextResolver


class OverlayRenderer(Protocol):
    def show(self, text: str) -> None: ...
    def pump(self) -> None: ...
    def hide(self) -> None: ...


def run_generic_gameplay_sentence_scenario(
    adapter: EmulatorAdapter,
    renderer: OverlayRenderer,
    *,
    text: str = "TOOLKIT TEST",
    duration_seconds: float = 3.0,
    screenshot_host: Callable[[], object] | None = None,
    save_host_screenshot: Callable[[object, str], None] | None = None,
    save_emulator_screenshot: Callable[[object, str], None] | None = None,
    host_screenshot_path: str | None = None,
    emulator_screenshot_path: str | None = None,
    poll_interval_seconds: float = 0.05,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
    game_id: str = "twilight_syndrome",
) -> EvidenceBundle:
    """Runs the SRS's "generic gameplay sentence" demo (SDD §13's first
    row): show `text` for `duration_seconds`, capture one host and one
    emulator screenshot partway through, then hide. Returns a filled-in
    `EvidenceBundle` -- does not save it; call `.save(path)` on the
    result if persistence is wanted, matching `EvidenceBundle`'s own
    minimal, single-purpose API."""
    event_log: list[str] = []
    caps = adapter.capabilities()
    missing = caps.require(EmulatorCapability.MEMORY_READ, EmulatorCapability.SCREENSHOT)
    if missing:
        event_log.append(f"missing required capabilities: {[c.value for c in missing]}")
        context = {}
        return EvidenceBundle(
            scenario_name="generic_gameplay_sentence",
            timestamp=datetime.now(timezone.utc).isoformat(),
            backend=OverlayBackend.EXTERNAL_HOST,
            result=ValidationResult.UNSUPPORTED,
            runtime_context=context,
            event_log=event_log,
            notes="adapter lacks a required capability; see event_log",
        )

    resolver = RuntimeContextResolver(game_id=game_id)
    context = resolver.resolve(adapter.read_memory)
    event_log.append(f"resolved runtime context: executable={context.executable_id!r} mode={context.mode.value}")

    renderer.show(text)
    event_log.append(f"overlay shown: {text!r}")

    deadline = now() + duration_seconds
    midpoint = now() + duration_seconds / 2
    captured_host = None
    captured_emulator = None
    screenshot_taken = False

    while now() < deadline:
        renderer.pump()
        if not screenshot_taken and now() >= midpoint:
            if screenshot_host is not None:
                captured_host = screenshot_host()
                event_log.append("host screenshot captured")
            try:
                captured_emulator = adapter.screenshot()
                event_log.append("emulator screenshot captured")
            except Exception as exc:  # pragma: no cover -- defensive, real IO failure path
                event_log.append(f"emulator screenshot failed: {exc}")
            screenshot_taken = True
        sleep(poll_interval_seconds)

    renderer.hide()
    event_log.append("overlay hidden")

    if captured_host is not None and save_host_screenshot is not None and host_screenshot_path is not None:
        save_host_screenshot(captured_host, host_screenshot_path)
    if captured_emulator is not None and save_emulator_screenshot is not None and emulator_screenshot_path is not None:
        save_emulator_screenshot(captured_emulator, emulator_screenshot_path)

    result = ValidationResult.PASS if screenshot_taken else ValidationResult.FAIL
    if not screenshot_taken:
        event_log.append("FAIL: no screenshot was captured during the visible window")

    return EvidenceBundle(
        scenario_name="generic_gameplay_sentence",
        timestamp=datetime.now(timezone.utc).isoformat(),
        backend=OverlayBackend.EXTERNAL_HOST,
        result=result,
        runtime_context=context.to_dict(),
        host_screenshot_path=host_screenshot_path if captured_host is not None else None,
        emulator_screenshot_path=emulator_screenshot_path if captured_emulator is not None else None,
        event_log=event_log,
    )
