"""Lightweight live poller for gcrts.overlay_identity -- plain GDB
memory reads only (no exec breakpoints), watching for which executable
is currently resident. Used to test the movie-detection hypothesis:
does the movie-player overlay family become resident exactly when a
movie plays, with no DMA-argument tracing needed at all.
"""
from __future__ import annotations

import json
import sys
import time

sys.path.insert(0, ".")

from gcrts.live_extract import GdbClient
from gcrts.overlay_identity import identify_overlay


def watch(out_path: str, host: str = "127.0.0.1", port: int = 3334, duration: float = 90.0, poll_interval: float = 0.5):
    client = GdbClient(host, port, timeout=10)
    events = []
    t0 = time.monotonic()
    last_name = None
    try:
        print(f"watching for up to {duration:.0f}s ({poll_interval}s interval)...", file=sys.stderr)
        while time.monotonic() - t0 < duration:
            overlay = identify_overlay(client.read_memory)
            name = overlay.name if overlay else "UNKNOWN"
            t = time.monotonic() - t0
            if name != last_name:
                events.append({"t": round(t, 2), "overlay": name})
                print(f"[t={t:6.2f}s] overlay changed -> {name}", file=sys.stderr)
                last_name = name
            time.sleep(poll_interval)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2, ensure_ascii=False)
        print(f"wrote {len(events)} transition(s) to {out_path}", file=sys.stderr)
    finally:
        client.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("out_path")
    parser.add_argument("--duration", type=float, default=90.0)
    parser.add_argument("--poll-interval", type=float, default=0.5)
    args = parser.parse_args()
    watch(args.out_path, duration=args.duration, poll_interval=args.poll_interval)
