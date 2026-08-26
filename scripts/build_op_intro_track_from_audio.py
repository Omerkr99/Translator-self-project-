"""Builds subtitle_tracks/op_intro.json's real cue timing from OP.STR's
actual audio track -- the "timing from audio now, text later" approach
(see docs/renderer/SUBTITLE_TRACK_MECHANICS.md), since this project has
no transcript or translation of the movie's actual dialogue and won't
fabricate one.

Pipeline: gcrts.movie_str_audio (extract OP.STR's raw bytes from the
real disc image + demux audio via FFmpeg's psxstr, verified this
session to auto-detect this exact file correctly) ->
gcrts.audio_activity_segments (amplitude-based activity detection,
NOT speech detection -- see that module's own honest-scope docstring)
-> a real subtitle_tracks/op_intro.json with each detected segment as
one cue, text left as an explicit placeholder for a human to fill in
by ear.

Live-run result this session: 15 segments found from t=0 to ~t=48s
(short, plausibly-one-line durations, 0.5-12.5s each) -- then activity
fuses into one continuous ~80s block from ~t=72s onward, most likely
the movie's theme song rather than discrete dialogue lines (amplitude-
based detection cannot distinguish speech from continuous music).
That long fused block is deliberately EXCLUDED from the generated
track (see MAX_PLAUSIBLE_CUE_DURATION below) rather than included as
one absurd 80-second "cue" -- a human re-watching that portion with
sound and adding cues by ear is the right next step there, not this
script guessing further.
"""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, ".")

from gcrts.audio_activity_segments import find_activity_segments
from gcrts.movie_detection import MOVIE_CATALOG
from gcrts.movie_str_audio import extract_str_audio_wav, read_raw_str_bytes

MAX_PLAUSIBLE_CUE_DURATION_SECONDS = 15.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disc-path", required=True, help="path to the real, unmodified source disc image")
    parser.add_argument("--movie-name", default="OP.STR")
    parser.add_argument("--reference-overlay", default="MOP.EXE")
    parser.add_argument("--wav-out", default="op_audio_extracted.wav")
    parser.add_argument("--track-out", default="subtitle_tracks/op_intro.json")
    args = parser.parse_args(argv)

    entry = next(e for e in MOVIE_CATALOG if e.name == args.movie_name)
    print(f"extracting {entry.name}: lba={entry.lba} logical_size={entry.size}", file=sys.stderr)

    raw = read_raw_str_bytes(args.disc_path, entry.lba, entry.size)
    extract_str_audio_wav(raw, args.wav_out)
    print(f"wrote {args.wav_out}", file=sys.stderr)

    segments = find_activity_segments(args.wav_out)
    print(f"{len(segments)} raw activity segment(s) found", file=sys.stderr)

    cues = []
    excluded = []
    for seg in segments:
        if seg.duration_seconds > MAX_PLAUSIBLE_CUE_DURATION_SECONDS:
            excluded.append(seg)
            continue
        cues.append(
            {
                "t": round(seg.start_seconds, 2),
                "duration": round(seg.duration_seconds, 2),
                "text": "TBD -- audio-derived candidate cue, verify wording and exact boundaries by ear",
            }
        )

    for seg in excluded:
        print(
            f"EXCLUDED (duration {seg.duration_seconds:.1f}s > {MAX_PLAUSIBLE_CUE_DURATION_SECONDS}s, "
            f"plausibly continuous music, not a single line): {seg.start_seconds:.2f}s-{seg.end_seconds:.2f}s",
            file=sys.stderr,
        )

    track = {"track_id": "op_intro", "reference_overlay": args.reference_overlay, "cues": cues}
    with open(args.track_out, "w", encoding="utf-8") as f:
        json.dump(track, f, indent=2, ensure_ascii=False)
    print(f"wrote {len(cues)} cue(s) to {args.track_out} ({len(excluded)} segment(s) excluded as implausible single lines)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
