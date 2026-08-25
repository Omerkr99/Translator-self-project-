"""Lightweight live poller for gcrts.script_audio_association -- plain
GDB memory reads only (no exec breakpoints, so no risk of the
interpreter-slowdown problem found earlier this session with many
simultaneous breakpoints). Polls the script cursor + buffer at a low
rate while the user navigates live, and logs every moment the script
context resolves to real dialogue text -- a deterministic alternative
to output-audio fingerprint matching: read what the game itself
associates with the current line, directly.
"""
from __future__ import annotations

import json
import sys
import time

sys.path.insert(0, ".")

from gcrts.live_extract import GdbClient
from gcrts.script_audio_association import capture_script_audio_association


def watch(out_path: str, host: str = "127.0.0.1", port: int = 3334, duration: float = 90.0, poll_interval: float = 0.3):
    client = GdbClient(host, port, timeout=10)
    events = []
    t0 = time.monotonic()
    last_cursor = None
    try:
        print(f"watching for up to {duration:.0f}s (plain memory reads, {poll_interval}s interval)...", file=sys.stderr)
        while time.monotonic() - t0 < duration:
            assoc = capture_script_audio_association(client.read_memory)
            t = time.monotonic() - t0
            if assoc.script_cursor != last_cursor or assoc.dialogue_text:
                event = {"t": round(t, 2), **assoc.to_dict()}
                events.append(event)
                if assoc.dialogue_text:
                    print(f"[t={t:6.2f}s] DIALOGUE TEXT: {assoc.dialogue_text!r} confidence={assoc.confidence} audio_event={assoc.audio_event}", file=sys.stderr)
                else:
                    print(f"[t={t:6.2f}s] cursor={assoc.script_cursor} confidence={assoc.confidence}", file=sys.stderr)
                last_cursor = assoc.script_cursor
            time.sleep(poll_interval)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2, ensure_ascii=False)
        print(f"wrote {len(events)} event(s) to {out_path}", file=sys.stderr)
    finally:
        client.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("out_path")
    parser.add_argument("--duration", type=float, default=90.0)
    parser.add_argument("--poll-interval", type=float, default=0.3)
    args = parser.parse_args()
    watch(args.out_path, duration=args.duration, poll_interval=args.poll_interval)
