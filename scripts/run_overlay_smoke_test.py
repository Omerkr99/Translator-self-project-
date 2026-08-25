"""Live smoke test for the overlay engine's external backend, run for
real against a live PCSX-Redux instance.

As of Stage 3 (`docs/overlay_engine/GROUNDING_ANALYSIS.md`), the
scenario itself is defined as data -- an `OverlayAction` -- and run
through the generic `gcrts.overlay_action_runner.run_overlay_action`,
not a hand-written per-scenario function. This is the concrete proof
of Stage 3's own exit criterion: the same scenario, expressed as data,
produces the same `EvidenceBundle` shape Stage 2's hand-written version
did.

Exit criterion this proves (SDD §18's O0/O1): PCSX-Redux attach +
context resolution + a timed English sentence shown via a real
transparent overlay window + a host screenshot + an emulator VRAM
screenshot + a saved EvidenceBundle -- driven by an OverlayAction, not
ad hoc script code.

Usage:
    python -m scripts.run_overlay_smoke_test --out-dir evidence/stage3_smoke
"""
from __future__ import annotations

import argparse
import os

from PIL import ImageGrab

from gcrts.external_overlay_renderer import ExternalOverlayRenderer
from gcrts.overlay_action import OverlayAction, TextPayload
from gcrts.overlay_action_runner import run_overlay_action
from gcrts.pcsx_redux_adapter import PCSXReduxAdapter


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="evidence/stage3_smoke")
    parser.add_argument("--text", default="TOOLKIT TEST")
    parser.add_argument("--duration", type=float, default=4.0)
    parser.add_argument("--gdb-port", type=int, default=3334)
    args = parser.parse_args(argv)

    os.makedirs(args.out_dir, exist_ok=True)
    host_path = os.path.join(args.out_dir, "host_screenshot.png")
    emulator_path = os.path.join(args.out_dir, "emulator_screenshot.png")
    bundle_path = os.path.join(args.out_dir, "evidence.json")

    action = OverlayAction(
        id="generic_gameplay_sentence",
        payload=TextPayload(text=args.text),
        duration_seconds=args.duration,
    )

    adapter = PCSXReduxAdapter(gdb_port=args.gdb_port)
    renderer = ExternalOverlayRenderer(position=(120, 120))
    try:
        bundle = run_overlay_action(
            action,
            adapter,
            renderer,
            screenshot_host=lambda: ImageGrab.grab(),
            save_host_screenshot=lambda img, path: img.save(path),
            save_emulator_screenshot=lambda img, path: img.save(path),
            host_screenshot_path=host_path,
            emulator_screenshot_path=emulator_path,
        )
    finally:
        adapter.shutdown()

    bundle.save(bundle_path)
    print(f"result: {bundle.result.value}")
    print(f"runtime context: {bundle.runtime_context}")
    print(f"event log:")
    for line in bundle.event_log:
        print(f"  - {line}")
    print(f"evidence bundle written to {bundle_path}")
    return 0 if bundle.result.value == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
