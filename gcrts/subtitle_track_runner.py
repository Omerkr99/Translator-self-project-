"""Executes a `gcrts.overlay_action.SubtitleTrackPayload`'s cues live,
each timed relative to the track's `reference_overlay` becoming
resident (`gcrts.overlay_identity.identify_overlay`, `CONFIRMED_LIVE`).
That residency event is the track's own t=0; host wall-clock offsets
from it were validated in
`docs/renderer/MOVIE_TIME_SOURCE_INVESTIGATION.md` -- byte-for-byte
deterministic through the first ~23s of a boot/movie sequence, and
accurate enough after that for cues spanning multiple seconds (cue
timing does not need frame-exact precision the way an in-VRAM
composited overlay would).

Distinct from `gcrts.overlay_action_runner.run_overlay_action`: a
track is a sequence of cues over a potentially long window, not one
bounded show/hide action, so it gets its own runner and its own result
shape (`CueResult` per cue) instead of a single `EvidenceBundle`.

EDITING A TRACK: `load_subtitle_track` reads a plain JSON file with a
deliberately friendlier shape than `SubtitleTrackPayload.to_dict()`'s
own machine-facing format -- short key names, no `"kind"` wrapper.
Editing a subtitle track means editing this file directly:

    {
      "track_id": "op_intro",
      "reference_overlay": "MOP.EXE",
      "cues": [
        {"t": 5.0, "duration": 3.0, "text": "..."},
        {"t": 12.5, "duration": 4.0, "text": "..."}
      ]
    }
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from gcrts.overlay_action import SubtitleCue, SubtitleTrackPayload
from gcrts.overlay_identity import identify_overlay


class TrackRenderer(Protocol):
    def show(self, text: str) -> None: ...
    def pump(self) -> None: ...
    def hide(self) -> None: ...


class ReferenceTriggerTimeout(RuntimeError):
    """Raised when a track's `reference_overlay` never becomes resident
    within `reference_wait_timeout` -- distinct from a cue simply
    having no visible effect, since no cues are ever shown in this
    case at all."""


@dataclass
class CueResult:
    cue: SubtitleCue
    shown_at_t: float  # actual elapsed seconds since t_ref when this cue was shown, for comparison against cue.t_offset_seconds

    def to_dict(self) -> dict:
        return {"cue": self.cue.to_dict(), "shown_at_t": round(self.shown_at_t, 3)}


def load_subtitle_track(path: str | Path) -> SubtitleTrackPayload:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    cues = tuple(
        SubtitleCue(t_offset_seconds=c["t"], text=c["text"], duration_seconds=c["duration"])
        for c in data["cues"]
    )
    return SubtitleTrackPayload(track_id=data["track_id"], reference_overlay=data["reference_overlay"], cues=cues)


def run_subtitle_track(
    payload: SubtitleTrackPayload,
    read_memory: Callable[[int, int], "bytes | None"],
    renderer: TrackRenderer,
    *,
    reference_wait_timeout: float = 60.0,
    poll_interval: float = 0.1,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> list[CueResult]:
    """Blocks until `payload.reference_overlay` becomes resident (or
    raises `ReferenceTriggerTimeout`), then fires each cue in
    chronological order (sorted by `t_offset_seconds`, regardless of
    input order) at its configured offset from that moment, showing it
    for exactly its own `duration_seconds` before hiding and moving to
    the next."""
    deadline = now() + reference_wait_timeout
    t_ref = None
    while now() < deadline:
        overlay = identify_overlay(read_memory)
        if overlay is not None and overlay.name == payload.reference_overlay:
            t_ref = now()
            break
        sleep(poll_interval)
    if t_ref is None:
        raise ReferenceTriggerTimeout(
            f"reference overlay {payload.reference_overlay!r} never became resident within {reference_wait_timeout}s"
        )

    results: list[CueResult] = []
    for cue in sorted(payload.cues, key=lambda c: c.t_offset_seconds):
        target = t_ref + cue.t_offset_seconds
        while now() < target:
            renderer.pump()
            sleep(poll_interval)

        renderer.show(cue.text)
        shown_at_t = now() - t_ref
        show_deadline = now() + cue.duration_seconds
        while now() < show_deadline:
            renderer.pump()
            sleep(poll_interval)
        renderer.hide()

        results.append(CueResult(cue=cue, shown_at_t=shown_at_t))
    return results
