"""Tests for gcrts.subtitle_track_runner. Uses a fake clock (advanced
by the injected `sleep`) and a fake read_memory reporting the real
signature only for one target overlay (same pattern as
tests/test_overlay_identity.py's own `_fake_read_memory`) -- exercises
the actual `identify_overlay` code path, not a bypassed mock, matching
this project's own testing convention. No live emulator required."""
from __future__ import annotations

import json

import pytest

from gcrts.overlay_action import SubtitleCue, SubtitleTrackPayload
from gcrts.overlay_identity import KNOWN_OVERLAYS, SIGNATURE_LENGTH
from gcrts.subtitle_track_runner import (
    CueResult,
    ReferenceTriggerTimeout,
    load_subtitle_track,
    run_subtitle_track,
)


def _fake_read_memory(overlay_name, appears_at=None, clock=None):
    """Reports the real signature for `overlay_name`'s own pc0 only
    once `clock.t >= appears_at` (or always, if appears_at is None) --
    never a plausible-looking wrong value otherwise."""
    target = next(p for p in KNOWN_OVERLAYS if p.name == overlay_name)

    def read_memory(addr, length):
        if addr == target.pc0 and length == SIGNATURE_LENGTH:
            if appears_at is None or (clock is not None and clock.t >= appears_at):
                return target.signature
        return None

    return read_memory


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, dt):
        self.t += dt


class FakeRenderer:
    def __init__(self):
        self.events: list[tuple] = []

    def show(self, text):
        self.events.append(("show", text))

    def pump(self):
        self.events.append(("pump",))

    def hide(self):
        self.events.append(("hide",))


def test_run_subtitle_track_fires_cues_in_chronological_order_regardless_of_input_order():
    clock = FakeClock()
    read_memory = _fake_read_memory("MOP.EXE", appears_at=0.0, clock=clock)
    renderer = FakeRenderer()
    payload = SubtitleTrackPayload(
        track_id="t",
        reference_overlay="MOP.EXE",
        cues=(
            SubtitleCue(t_offset_seconds=5.0, text="second", duration_seconds=1.0),
            SubtitleCue(t_offset_seconds=1.0, text="first", duration_seconds=1.0),
        ),
    )

    results = run_subtitle_track(payload, read_memory, renderer, poll_interval=0.5, sleep=clock.sleep, now=clock.now)

    shown_texts = [e[1] for e in renderer.events if e[0] == "show"]
    assert shown_texts == ["first", "second"]
    assert [r.cue.text for r in results] == ["first", "second"]


def test_run_subtitle_track_shows_and_hides_each_cue():
    clock = FakeClock()
    read_memory = _fake_read_memory("MOP.EXE", appears_at=0.0, clock=clock)
    renderer = FakeRenderer()
    payload = SubtitleTrackPayload(
        track_id="t", reference_overlay="MOP.EXE", cues=(SubtitleCue(t_offset_seconds=0.0, text="hi", duration_seconds=2.0),)
    )

    run_subtitle_track(payload, read_memory, renderer, poll_interval=0.5, sleep=clock.sleep, now=clock.now)

    kinds = [e[0] for e in renderer.events]
    assert "show" in kinds and "hide" in kinds
    assert kinds.index("show") < kinds.index("hide")


def test_run_subtitle_track_waits_for_reference_overlay_before_first_cue():
    clock = FakeClock()
    read_memory = _fake_read_memory("MOP.EXE", appears_at=3.0, clock=clock)
    renderer = FakeRenderer()
    payload = SubtitleTrackPayload(
        track_id="t", reference_overlay="MOP.EXE", cues=(SubtitleCue(t_offset_seconds=0.0, text="hi", duration_seconds=1.0),)
    )

    results = run_subtitle_track(payload, read_memory, renderer, poll_interval=0.5, sleep=clock.sleep, now=clock.now, reference_wait_timeout=10.0)

    assert len(results) == 1
    # the reference overlay only appears at t=3.0, so the cue (t_offset=0 relative to
    # that) cannot have been shown before real elapsed time reached ~3.0
    assert clock.t >= 3.0


def test_run_subtitle_track_raises_if_reference_overlay_never_appears():
    clock = FakeClock()
    read_memory = lambda addr, length: None  # noqa: E731
    renderer = FakeRenderer()
    payload = SubtitleTrackPayload(
        track_id="t", reference_overlay="MOP.EXE", cues=(SubtitleCue(t_offset_seconds=0.0, text="hi", duration_seconds=1.0),)
    )

    with pytest.raises(ReferenceTriggerTimeout):
        run_subtitle_track(payload, read_memory, renderer, poll_interval=0.5, sleep=clock.sleep, now=clock.now, reference_wait_timeout=2.0)

    assert renderer.events == []  # no cue shown at all


def test_cue_result_to_dict():
    result = CueResult(cue=SubtitleCue(t_offset_seconds=1.5, text="hi", duration_seconds=2.0), shown_at_t=1.501)
    d = result.to_dict()
    assert d["cue"]["text"] == "hi"
    assert d["shown_at_t"] == 1.501


def test_load_subtitle_track_parses_friendly_json_shape(tmp_path):
    path = tmp_path / "track.json"
    path.write_text(
        json.dumps(
            {
                "track_id": "op_intro",
                "reference_overlay": "MOP.EXE",
                "cues": [
                    {"t": 5.0, "duration": 3.0, "text": "first"},
                    {"t": 12.5, "duration": 4.0, "text": "second"},
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = load_subtitle_track(path)

    assert payload.track_id == "op_intro"
    assert payload.reference_overlay == "MOP.EXE"
    assert len(payload.cues) == 2
    assert payload.cues[0].t_offset_seconds == 5.0
    assert payload.cues[0].duration_seconds == 3.0
    assert payload.cues[1].text == "second"
