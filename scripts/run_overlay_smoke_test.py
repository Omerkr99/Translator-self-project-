"""Stage 2 live smoke test: the SRS's "generic gameplay sentence" demo,
run for real against a live PCSX-Redux instance.

Exit criterion this proves (`docs/overlay_engine/GROUNDING_ANALYSIS.md`
Stage 2 / SDD §18's O0): PCSX-Redux attach + context resolution + a
timed English sentence shown via a real transparent overlay window +
a host screenshot + an emulator VRAM screenshot + a saved
EvidenceBundle.

Usage:
    python -m scripts.run_overlay_smoke_test --out-dir evidence/stage2_smoke
"""
from __future__ import annotations

import argparse
import os

from PIL import ImageGrab

from gcrts.external_overlay_renderer import ExternalOverlayRenderer
from gcrts.live_test_runner import run_generic_gameplay_sentence_scenario
from gcrts.pcsx_redux_adapter import PCSXReduxAdapter


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="evidence/stage2_smoke")
    parser.add_argument("--text", default="TOOLKIT TEST")
    parser.add_argument("--duration", type=float, default=4.0)
    parser.add_argument("--gdb-port", type=int, default=3334)
    args = parser.parse_args(argv)

    os.makedirs(args.out_dir, exist_ok=True)
    host_path = os.path.join(args.out_dir, "host_screenshot.png")
    emulator_path = os.path.join(args.out_dir, "emulator_screenshot.png")
    bundle_path = os.path.join(args.out_dir, "evidence.json")

    adapter = PCSXReduxAdapter(gdb_port=args.gdb_port)
    renderer = ExternalOverlayRenderer(position=(120, 120))
    try:
        bundle = run_generic_gameplay_sentence_scenario(
            adapter,
            renderer,
            text=args.text,
            duration_seconds=args.duration,
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
