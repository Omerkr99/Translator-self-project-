"""Runs a subtitle track (`gcrts.subtitle_track_runner`) live against a
real running PCSX-Redux instance: waits for the track's reference
overlay to become resident, then shows each cue at its configured
offset/duration through a real external overlay window.

Usage:
    python -m scripts.run_subtitle_track path/to/track.json

See `docs/renderer/SUBTITLE_TRACK_MECHANICS.md` for the track file
format, how cue timing relates to the movie-time-source investigation,
and current known limits (the reference-overlay wait uses plain GDB
polling, same mechanism as scripts/live_overlay_watch.py).
"""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, ".")

from gcrts.external_overlay_renderer import ExternalOverlayRenderer
from gcrts.gdb_client import GdbClient
from gcrts.subtitle_track_runner import ReferenceTriggerTimeout, load_subtitle_track, run_subtitle_track


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("track_path")
    parser.add_argument("--gdb-port", type=int, default=3334)
    parser.add_argument("--reference-wait-timeout", type=float, default=90.0)
    parser.add_argument("--out", default=None, help="optional path to write cue results as JSON")
    args = parser.parse_args(argv)

    payload = load_subtitle_track(args.track_path)
    print(f"loaded track {payload.track_id!r}: {len(payload.cues)} cue(s), reference_overlay={payload.reference_overlay!r}", file=sys.stderr)

    client = GdbClient("127.0.0.1", args.gdb_port, timeout=10)
    renderer = ExternalOverlayRenderer()
    try:
        results = run_subtitle_track(
            payload,
            client.read_memory,
            renderer,
            reference_wait_timeout=args.reference_wait_timeout,
        )
    except ReferenceTriggerTimeout as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        client.close()

    for r in results:
        print(f"[t=+{r.shown_at_t:6.3f}s] shown {r.cue.duration_seconds:.1f}s: {r.cue.text!r}", file=sys.stderr)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"track_id": payload.track_id, "results": [r.to_dict() for r in results]}, f, indent=2, ensure_ascii=False)
        print(f"wrote results to {args.out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
