"""Tests for gcrts.overlay_action -- pure serialization, no runner logic."""
from __future__ import annotations

import pytest

from gcrts.overlay_action import (
    AudioEventPayload,
    DebugHudPayload,
    ImagePayload,
    OverlayAction,
    OverlayBackendPreference,
    ScreenshotRequestPayload,
    SubtitleCue,
    SubtitleTrackPayload,
    TextPayload,
)


def test_text_action_round_trips_through_dict():
    action = OverlayAction(id="generic_gameplay_sentence", payload=TextPayload("TOOLKIT TEST"), duration_seconds=3.0)
    restored = OverlayAction.from_dict(action.to_dict())
    assert restored.id == action.id
    assert isinstance(restored.payload, TextPayload)
    assert restored.payload.text == "TOOLKIT TEST"
    assert restored.duration_seconds == 3.0


def test_defaults_match_spec_defaults():
    action = OverlayAction(id="x", payload=TextPayload("hi"))
    assert action.trigger == "manual"
    assert action.start_condition == "immediate"
    assert action.backend_preference == OverlayBackendPreference.EXTERNAL_HOST
    assert action.fallback_policy == "skip_if_unsupported"
    assert action.evidence_policy == "capture_at_midpoint"


def test_target_context_survives_round_trip():
    action = OverlayAction(id="x", payload=TextPayload("hi"), target_context={"mode": "GAMEPLAY"})
    restored = OverlayAction.from_dict(action.to_dict())
    assert restored.target_context == {"mode": "GAMEPLAY"}


@pytest.mark.parametrize(
    "payload",
    [
        ImagePayload(image_path="logo.png"),
        SubtitleTrackPayload(track_id="OP_STR_01"),
        AudioEventPayload(asset_id="XAPACK22:7"),
        DebugHudPayload(fields=("mode", "executable_id")),
        ScreenshotRequestPayload(label="checkpoint"),
    ],
)
def test_every_declared_payload_kind_round_trips(payload):
    action = OverlayAction(id="x", payload=payload)
    restored = OverlayAction.from_dict(action.to_dict())
    assert restored.payload == payload


def test_subtitle_track_with_cues_round_trips_through_dict():
    payload = SubtitleTrackPayload(
        track_id="op_intro",
        reference_overlay="MOP.EXE",
        cues=(
            SubtitleCue(t_offset_seconds=5.0, text="first line", duration_seconds=3.0),
            SubtitleCue(t_offset_seconds=12.5, text="second line", duration_seconds=4.0),
        ),
    )
    action = OverlayAction(id="op_intro_track", payload=payload)
    restored = OverlayAction.from_dict(action.to_dict())
    assert restored.payload == payload
    assert restored.payload.reference_overlay == "MOP.EXE"
    assert len(restored.payload.cues) == 2
    assert restored.payload.cues[1].text == "second line"


def test_unknown_payload_kind_raises():
    with pytest.raises(ValueError):
        OverlayAction.from_dict(
            {"id": "x", "payload": {"kind": "NOT_A_REAL_KIND"}}
        )
