"""OverlayAction: the shared scenario data model
(`docs/overlay_engine/PS1_OVERLAY_RUNTIME_REQUIREMENTS.md` §8) that
lets a test scenario be *data* -- constructed once, run through either
backend -- rather than hand-written script code per scenario. This is
Stage 3 of the staged plan in `docs/overlay_engine/GROUNDING_ANALYSIS.md`.

Per SRS §8, an `OverlayAction`'s payload is one of six kinds: Text,
Image, SubtitleTrack, AudioEvent, DebugHUD, ScreenshotRequest. Only
`TextPayload` has a real executor behind it so far
(`gcrts.overlay_action_runner.run_overlay_action`) -- the other five
are declared here (so the data model itself is complete per the spec)
but deliberately NOT backed by any runner logic yet. Attempting to run
an action carrying one of them must report `UNSUPPORTED`, never
silently no-op or approximate a result, per EMU-004's "degrade
gracefully" principle applied to payload kinds as much as emulator
capabilities.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OverlayBackendPreference(str, Enum):
    EXTERNAL_HOST = "EXTERNAL_HOST"
    INTERNAL_PS1 = "INTERNAL_PS1"
    EITHER = "EITHER"


class PayloadKind(str, Enum):
    TEXT = "TEXT"
    IMAGE = "IMAGE"
    SUBTITLE_TRACK = "SUBTITLE_TRACK"
    AUDIO_EVENT = "AUDIO_EVENT"
    DEBUG_HUD = "DEBUG_HUD"
    SCREENSHOT_REQUEST = "SCREENSHOT_REQUEST"


@dataclass(frozen=True)
class TextPayload:
    """The only payload kind with a real runner behind it this stage."""

    text: str

    def to_dict(self) -> dict:
        return {"kind": PayloadKind.TEXT.value, "text": self.text}

    @classmethod
    def from_dict(cls, d: dict) -> "TextPayload":
        return cls(text=d["text"])


# Declared per SRS §8's content model, not yet implemented by any
# runner -- see module docstring. Each is a minimal placeholder shape;
# they're expected to gain real fields once a runner exists for them,
# not to be considered final.
@dataclass(frozen=True)
class ImagePayload:
    image_path: str

    def to_dict(self) -> dict:
        return {"kind": PayloadKind.IMAGE.value, "image_path": self.image_path}


@dataclass(frozen=True)
class SubtitleTrackPayload:
    """A sequence of timed text cues, each relative to `reference_overlay`
    becoming resident (per `gcrts.overlay_identity.identify_overlay`,
    already `CONFIRMED_LIVE`) -- that residency event is this payload's
    own t=0. Timing cues this way (host wall-clock offset from a
    detected trigger) is the mechanism validated in
    `docs/renderer/MOVIE_TIME_SOURCE_INVESTIGATION.md`: byte-for-byte
    deterministic through the first ~23s of a boot/movie sequence, and
    accurate enough after that for cues spanning multiple seconds (not
    sensitive to the sub-second drift found in that investigation).
    Real execution logic lives in `gcrts.subtitle_track_runner`, not
    `gcrts.overlay_action_runner` -- a track is a sequence over a
    potentially long window, not one bounded show/hide action, so it
    doesn't fit `run_overlay_action`'s single-`EvidenceBundle` shape."""

    track_id: str
    reference_overlay: str = ""
    cues: tuple["SubtitleCue", ...] = ()

    def to_dict(self) -> dict:
        return {
            "kind": PayloadKind.SUBTITLE_TRACK.value,
            "track_id": self.track_id,
            "reference_overlay": self.reference_overlay,
            "cues": [c.to_dict() for c in self.cues],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SubtitleTrackPayload":
        return cls(
            track_id=d["track_id"],
            reference_overlay=d.get("reference_overlay", ""),
            cues=tuple(SubtitleCue.from_dict(c) for c in d.get("cues", ())),
        )


@dataclass(frozen=True)
class SubtitleCue:
    """One timed line within a `SubtitleTrackPayload`. `t_offset_seconds`
    is measured from the track's `reference_overlay` becoming resident,
    not from track-load time or any other anchor."""

    t_offset_seconds: float
    text: str
    duration_seconds: float

    def to_dict(self) -> dict:
        return {"t_offset_seconds": self.t_offset_seconds, "text": self.text, "duration_seconds": self.duration_seconds}

    @classmethod
    def from_dict(cls, d: dict) -> "SubtitleCue":
        return cls(t_offset_seconds=d["t_offset_seconds"], text=d["text"], duration_seconds=d["duration_seconds"])


@dataclass(frozen=True)
class AudioEventPayload:
    asset_id: str

    def to_dict(self) -> dict:
        return {"kind": PayloadKind.AUDIO_EVENT.value, "asset_id": self.asset_id}


@dataclass(frozen=True)
class DebugHudPayload:
    fields: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {"kind": PayloadKind.DEBUG_HUD.value, "fields": list(self.fields)}


@dataclass(frozen=True)
class ScreenshotRequestPayload:
    label: str = ""

    def to_dict(self) -> dict:
        return {"kind": PayloadKind.SCREENSHOT_REQUEST.value, "label": self.label}


Payload = TextPayload | ImagePayload | SubtitleTrackPayload | AudioEventPayload | DebugHudPayload | ScreenshotRequestPayload

_PAYLOAD_CLASSES_BY_KIND: dict[str, type] = {
    PayloadKind.TEXT.value: TextPayload,
    PayloadKind.IMAGE.value: ImagePayload,
    PayloadKind.SUBTITLE_TRACK.value: SubtitleTrackPayload,
    PayloadKind.AUDIO_EVENT.value: AudioEventPayload,
    PayloadKind.DEBUG_HUD.value: DebugHudPayload,
    PayloadKind.SCREENSHOT_REQUEST.value: ScreenshotRequestPayload,
}


def _payload_from_dict(d: dict) -> Payload:
    kind = d["kind"]
    cls = _PAYLOAD_CLASSES_BY_KIND.get(kind)
    if cls is None:
        raise ValueError(f"unknown payload kind: {kind!r}")
    if cls is DebugHudPayload:
        return DebugHudPayload(fields=tuple(d.get("fields", ())))
    if cls is TextPayload:
        return TextPayload.from_dict(d)
    if cls is SubtitleTrackPayload:
        return SubtitleTrackPayload.from_dict(d)
    # remaining payload kinds have exactly one non-"kind" field each,
    # matching their own to_dict() shape above.
    field_name = next(k for k in d if k != "kind")
    return cls(**{field_name: d[field_name]})


@dataclass
class OverlayAction:
    id: str
    payload: Payload
    trigger: str = "manual"
    target_context: dict | None = None
    start_condition: str = "immediate"
    duration_seconds: float | None = None
    priority: int = 0
    backend_preference: OverlayBackendPreference = OverlayBackendPreference.EXTERNAL_HOST
    fallback_policy: str = "skip_if_unsupported"
    evidence_policy: str = "capture_at_midpoint"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "payload": self.payload.to_dict(),
            "trigger": self.trigger,
            "target_context": self.target_context,
            "start_condition": self.start_condition,
            "duration_seconds": self.duration_seconds,
            "priority": self.priority,
            "backend_preference": self.backend_preference.value,
            "fallback_policy": self.fallback_policy,
            "evidence_policy": self.evidence_policy,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "OverlayAction":
        return cls(
            id=d["id"],
            payload=_payload_from_dict(d["payload"]),
            trigger=d.get("trigger", "manual"),
            target_context=d.get("target_context"),
            start_condition=d.get("start_condition", "immediate"),
            duration_seconds=d.get("duration_seconds"),
            priority=d.get("priority", 0),
            backend_preference=OverlayBackendPreference(d.get("backend_preference", "EXTERNAL_HOST")),
            fallback_policy=d.get("fallback_policy", "skip_if_unsupported"),
            evidence_policy=d.get("evidence_policy", "capture_at_midpoint"),
        )
