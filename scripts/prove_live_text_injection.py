"""Stage 4 groundwork: proves (or disproves) that a live-injected script
text edit actually renders on screen through the game's own renderer --
the first, necessary half of
`docs/status/TOOLKIT_READINESS_AUDIT.md` blocker #1
("prove one real text modification survives the full reinjection
cycle"). This script proves ONLY the rendering half; it does NOT prove
persistence across a reload/reboot -- a live GDB memory write is
inherently RAM-only and is wiped by any save-state reload or reboot.
That second half needs actual disc/executable patching (SRS PAT-001..007,
none of which exists in this project yet) and is deliberately NOT
attempted here.

Method, found empirically this session (see
`docs/overlay_engine/GROUNDING_ANALYSIS.md`'s Stage 4 section for the
full narrative): the dialogue in at least one real scene (save slot 4,
`CAP1.EXE`) auto-advances in real time once the save state is running,
fast enough that a naive "load, read, inject, screenshot" sequence
races the game and frequently lands on the wrong line by the time the
write completes. Pausing the CPU (`EmulatorAdapter.pause()`, a raw GDB
interrupt) immediately after the state load freezes it before any
further advancement, giving unlimited time to read/modify/inject the
script buffer; resuming and grabbing a screenshot shortly after reliably
catches the game rendering whatever is now in the buffer -- including
the injected text.

Usage:
    python -m scripts.prove_live_text_injection --slot 4 --unit-index 0 --text "Morning Kimika how are you" --out-dir evidence/stage4_text_injection_proof
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

from gcrts.live_injection import inject_units_live
from gcrts.pcsx_redux_adapter import PCSXReduxAdapter
from gcrts.script_unit import extract_live_script_units


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot", type=int, required=True, help="save-state slot known to have live dialogue text")
    parser.add_argument("--unit-index", type=int, default=0, help="which captured script unit to overwrite")
    parser.add_argument("--text", required=True, help="English replacement text (avoid characters missing from the game's glyph map -- see gcrts.glyph_char_map.code_for_char)")
    parser.add_argument("--out-dir", default="evidence/stage4_text_injection_proof")
    parser.add_argument("--gdb-port", type=int, default=3334)
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--resume-wait-seconds", type=float, default=0.3)
    args = parser.parse_args(argv)

    os.makedirs(args.out_dir, exist_ok=True)
    record: dict = {"timestamp": datetime.now(timezone.utc).isoformat(), "slot": args.slot, "unit_index": args.unit_index, "requested_text": args.text}

    adapter = PCSXReduxAdapter(gdb_port=args.gdb_port, api_base_url=args.api_base_url, connect=True)
    try:
        urllib.request.urlopen(f"{args.api_base_url}/api/v1/state/load?slot={args.slot}", timeout=10).read()
        adapter.pause()
        record["paused_immediately_after_load"] = True

        units = extract_live_script_units("prove_live_text_injection", port=args.gdb_port)
        if args.unit_index >= len(units):
            record["result"] = "FAIL"
            record["error"] = f"unit index {args.unit_index} out of range ({len(units)} units captured)"
            _finish(record, args.out_dir)
            return 1

        target = units[args.unit_index]
        record["original_text"] = target.original_text
        target.edited_text = args.text

        injection = inject_units_live(units, port=args.gdb_port)
        record["injection_success"] = injection.success
        record["injection_error"] = injection.error
        record["injection_warnings"] = injection.warnings
        if not injection.success:
            record["result"] = "FAIL"
            _finish(record, args.out_dir)
            return 1

        adapter.resume()
        record["resumed"] = True
        time.sleep(args.resume_wait_seconds)

        screenshot_path = os.path.join(args.out_dir, "after_injection.png")
        adapter.screenshot().save(screenshot_path)
        record["screenshot_path"] = screenshot_path
        record["result"] = "INJECTED_AND_CAPTURED"
        record["notes"] = (
            "Capturing a screenshot proves the injection call succeeded and a frame was "
            "grabbed afterward -- it does NOT by itself prove the injected text is legible "
            "on screen. Read the saved image to confirm visually; this script does not run "
            "OCR. Does NOT prove persistence across reload/reboot -- see module docstring."
        )
    finally:
        adapter.shutdown()

    _finish(record, args.out_dir)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


def _finish(record: dict, out_dir: str) -> None:
    with open(os.path.join(out_dir, "record.json"), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    raise SystemExit(main())
