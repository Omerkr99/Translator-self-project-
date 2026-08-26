"""Movie-time-source probe -- Stage 5's other prerequisite (alongside
VRAM-write-path, see docs/renderer/VRAM_WRITE_PATH_INVESTIGATION.md).
Full account of this investigation, including a GUI-automation detour
that turned out to be the real obstacle: docs/renderer/
MOVIE_TIME_SOURCE_INVESTIGATION.md.

QUESTION THIS SCRIPT ANSWERS: is wall-clock elapsed time, measured on
the host from a fixed reset anchor, a reliable proxy for "how far into
the boot/movie sequence we are"? If playback is deterministic
frame-for-frame at a fixed real-time rate, host-side timing alone
would satisfy SDD O5's external-subtitle-sync need with zero PS1-side
hook.

ANCHOR MECHANISM: `PCSX.hardResetEmulator()` + `PCSX.resumeEmulator()`
via the Lua Console (`gcrts.pcsx_lua_console.run_lua`), NOT GUI menu
clicks. Live-tested this session: OS-level menu-click automation
(`File > Reboot`, `Emulation > Start emulation`) proved fragile --
dialogs not closing on the expected click, stale menu-tab coordinates,
and `find_window_by_process_name` ambiguously matching an open dialog
instead of the main window (both belong to the same process). The Lua
route sidesteps all of that and is now the preferred way to drive
reset/start for any live experiment in this project. Requires a disc
already loaded once via the GUI (`File > Open Disk Image` -- no Lua
equivalent exists for that specific action).

METHOD: call this once right after loading the target disc. It resets
and resumes via Lua, then captures a screenshot every `--interval`
seconds for `--duration` seconds, each recorded with elapsed wall-
clock time, a SHA-256 hash of the raw pixel bytes, AND the actual PNG
file (an earlier pass at this script only saved hashes, which meant a
detected mismatch between two runs couldn't be visually inspected
afterward -- fixed here).

Run this TWICE and diff the two output manifests offline (matching
hashes at the same `t` values across runs is the actual proof of
determinism; a single run alone cannot establish it). Where hashes
differ, open the two saved PNGs for that `t` to judge whether it's a
neighboring-frame jitter artifact or a real difference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")

from gcrts.pcsx_lua_console import run_lua
from gcrts.pcsx_redux_adapter import PCSXReduxAdapter


def probe(out_path: str, frames_dir: str, duration: float = 40.0, interval: float = 2.0, api_base_url: str = "http://127.0.0.1:8080", gdb_port: int = 3334) -> None:
    frames = Path(frames_dir)
    frames.mkdir(parents=True, exist_ok=True)

    run_lua('PCSX.hardResetEmulator() PCSX.resumeEmulator() PCSX.log("movie_time_source_probe: reset+resume")')
    t0 = time.monotonic()
    print(f"anchor t0 set, capturing for {duration:.0f}s every {interval:.1f}s...", file=sys.stderr)

    adapter = PCSXReduxAdapter(gdb_port=gdb_port, api_base_url=api_base_url, connect=False)
    events: list[dict] = []
    try:
        while time.monotonic() - t0 < duration:
            t = time.monotonic() - t0
            img = adapter.screenshot()
            digest = hashlib.sha256(img.tobytes()).hexdigest()
            frame_path = frames / f"t{t:07.3f}.png"
            img.save(frame_path)
            events.append({"t": round(t, 3), "sha256": digest, "frame": str(frame_path)})
            print(f"[t=+{t:6.3f}s] {digest[:12]}", file=sys.stderr)
            time.sleep(interval)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"events": events}, f, indent=2)
        print(f"wrote {len(events)} sample(s) to {out_path}", file=sys.stderr)
    finally:
        adapter.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out_path")
    parser.add_argument("frames_dir")
    parser.add_argument("--duration", type=float, default=40.0)
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()
    probe(args.out_path, args.frames_dir, duration=args.duration, interval=args.interval)
