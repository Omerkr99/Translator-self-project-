"""Generic OverlayAction executor -- Stage 3 of the staged plan
(`docs/overlay_engine/GROUNDING_ANALYSIS.md`).

`run_overlay_action` is the one function that runs ANY `OverlayAction`
whose payload kind has real support (`TextPayload` only, this stage)
through the external-overlay backend. `gcrts.live_test_runner`'s own
`run_generic_gameplay_sentence_scenario` -- Stage 2's hand-written
scenario -- is now a thin compatibility wrapper around this: it builds
an `OverlayAction` and delegates here, so Stage 2's own existing
callers/tests keep working unchanged while the actual execution path
is the same data-driven one Stage 3 calls for. This is the concrete
proof of the SDD's own §10 claim: "the same desired behavior should be
testable through both [hand-written and data-driven] paths."

Any payload kind besides `TextPayload` reports `UNSUPPORTED` rather
than silently no-op-ing or approximating a result, matching this
project's EMU-004 "degrade gracefully, never approximate" principle
applied to payload kinds.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Callable, Protocol

from gcrts.emulator_adapter import EmulatorAdapter, EmulatorCapability
from gcrts.evidence_bundle import EvidenceBundle, OverlayBackend, ValidationResult
from gcrts.overlay_action import OverlayAction, TextPayload
from gcrts.runtime_context import RuntimeContextResolver

DEFAULT_DURATION_SECONDS = 3.0


class OverlayRenderer(Protocol):
    def show(self, text: str) -> None: ...
    def pump(self) -> None: ...
    def hide(self) -> None: ...


def _unsupported(action: OverlayAction, reason: str) -> EvidenceBundle:
    return EvidenceBundle(
        scenario_name=action.id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        backend=OverlayBackend.EXTERNAL_HOST,
        result=ValidationResult.UNSUPPORTED,
        runtime_context={},
        event_log=[reason],
        notes="see event_log",
    )


def run_overlay_action(
    action: OverlayAction,
    adapter: EmulatorAdapter,
    renderer: OverlayRenderer,
    *,
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
    if not isinstance(action.payload, TextPayload):
        return _unsupported(
            action, f"payload kind {type(action.payload).__name__} has no runner implementation yet"
        )

    event_log: list[str] = []
    caps = adapter.capabilities()
    missing = caps.require(EmulatorCapability.MEMORY_READ, EmulatorCapability.SCREENSHOT)
    if missing:
        event_log.append(f"missing required capabilities: {[c.value for c in missing]}")
        return EvidenceBundle(
            scenario_name=action.id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            backend=OverlayBackend.EXTERNAL_HOST,
            result=ValidationResult.UNSUPPORTED,
            runtime_context={},
            event_log=event_log,
            notes="adapter lacks a required capability; see event_log",
        )

    resolver = RuntimeContextResolver(game_id=game_id)
    context = resolver.resolve(adapter.read_memory)
    event_log.append(f"resolved runtime context: executable={context.executable_id!r} mode={context.mode.value}")

    duration = action.duration_seconds if action.duration_seconds is not None else DEFAULT_DURATION_SECONDS

    renderer.show(action.payload.text)
    event_log.append(f"overlay shown: {action.payload.text!r}")

    deadline = now() + duration
    midpoint = now() + duration / 2
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
        scenario_name=action.id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        backend=OverlayBackend.EXTERNAL_HOST,
        result=result,
        runtime_context=context.to_dict(),
        host_screenshot_path=host_screenshot_path if captured_host is not None else None,
        emulator_screenshot_path=emulator_screenshot_path if captured_emulator is not None else None,
        event_log=event_log,
    )
