"""LiveTestRunner: the external-overlay smoke-test scenario
(`docs/overlay_engine/PS1_OVERLAY_RUNTIME_SYSTEM_DESIGN.md` §4.1/§12,
`PS1_OVERLAY_RUNTIME_REQUIREMENTS.md` VAL-001/VAL-002/VAL-005).

`run_generic_gameplay_sentence_scenario` was Stage 2's own hand-written
scenario. As of Stage 3
(`docs/overlay_engine/GROUNDING_ANALYSIS.md`), it's a thin
compatibility wrapper: it builds an `OverlayAction` (data, per SRS §8)
and delegates to the generic `gcrts.overlay_action_runner.run_overlay_action`
-- the actual execution logic now lives in exactly one place, run
either from hand-written code (this function) or from a scenario
defined as pure data (`scripts/run_overlay_smoke_test.py` now does the
latter directly). This function's own signature and behavior are
unchanged from Stage 2, so existing callers/tests keep working.
"""
from __future__ import annotations

import time
from typing import Callable

from gcrts.emulator_adapter import EmulatorAdapter
from gcrts.evidence_bundle import EvidenceBundle
from gcrts.overlay_action import OverlayAction, TextPayload
from gcrts.overlay_action_runner import OverlayRenderer, run_overlay_action


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
    action = OverlayAction(
        id="generic_gameplay_sentence",
        payload=TextPayload(text=text),
        duration_seconds=duration_seconds,
    )
    return run_overlay_action(
        action,
        adapter,
        renderer,
        screenshot_host=screenshot_host,
        save_host_screenshot=save_host_screenshot,
        save_emulator_screenshot=save_emulator_screenshot,
        host_screenshot_path=host_screenshot_path,
        emulator_screenshot_path=emulator_screenshot_path,
        poll_interval_seconds=poll_interval_seconds,
        sleep=sleep,
        now=now,
        game_id=game_id,
    )
