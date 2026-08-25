"""Live Scene Identification: identify what the user is currently
seeing and hearing, from observable evidence only -- no dependency on
CAP*.EXE-specific internal RAM addresses (the deterministic
script-buffer approach was tried and abandoned this session once it
was confirmed the known addresses only apply to `PROG.EXE`, not the
`CAP*.EXE` family actually resident during real gameplay).

    what user sees + what user hears
        -> scene/line identification
        -> AudioAsset
        -> offset
        -> speaker/chapter/event
        -> database entry

Combines two independently-verified, overlay-independent evidence
sources:
  - `gcrts.screen_capture` (VRAM-backed screenshot via PCSX-Redux's
    own Web API -- no RAM address dependency at all)
  - the output-audio-capture -> fingerprint -> offset-continuity
    pipeline (`gcrts.output_audio_capture`, `gcrts.output_audio_match`),
    already validated against 3 independent real lines this session

Text/speaker recognition from the screenshot is done by direct human
(or multimodal-model) reading of the saved image, not brittle OCR --
the milestone's own instruction: "If OCR is unreliable, retain the
screenshot and use visual/context matching rather than pretending the
text was read correctly." No OCR library is wired in; `visible_text`
and `speaker` are populated by whoever reviews the screenshot, kept as
plain optional fields on the record.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class ConfidenceState(str, Enum):
    DETECTED = "DETECTED"
    CANDIDATE = "CANDIDATE"
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
    USER_VERIFIED = "USER_VERIFIED"
    REJECTED = "REJECTED"


@dataclass
class LiveDialogueEvent:
    event_id: str
    captured_at: str  # ISO-8601 UTC

    screenshot_path: str | None = None
    screenshot_sha256: str | None = None
    visible_text: str | None = None  # filled by direct reading of the screenshot, never OCR-guessed
    speaker: str | None = None
    chapter: str | None = None
    scene: str | None = None

    audio_capture_path: str | None = None
    voice_begin: float | None = None
    voice_end: float | None = None

    asset_id: str | None = None
    asset_offset_seconds: float | None = None
    fingerprint_similarity: float | None = None
    offset_continuity_windows: int | None = None
    offset_continuity_error: float | None = None

    evidence: list[str] = field(default_factory=list)
    confidence: ConfidenceState = ConfidenceState.DETECTED
    notes: str = ""

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["confidence"] = self.confidence.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "LiveDialogueEvent":
        d = dict(d)
        d["confidence"] = ConfidenceState(d.get("confidence", "DETECTED"))
        return cls(**d)


def compute_file_sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def classify_confidence(
    fingerprint_similarity: float | None,
    continuity_windows: int | None,
    continuity_error: float | None,
    has_visual_context: bool,
    user_verified: bool = False,
) -> ConfidenceState:
    """Never confirms from one weak signal alone -- combines fingerprint
    strength, offset continuity, and whether independent visual context
    exists, per this milestone's own confidence rules."""
    if user_verified:
        return ConfidenceState.USER_VERIFIED
    if fingerprint_similarity is None:
        return ConfidenceState.DETECTED
    strong_fingerprint = fingerprint_similarity >= 0.9
    strong_continuity = (continuity_windows or 0) >= 3 and (continuity_error if continuity_error is not None else 1.0) < 0.1
    if strong_fingerprint and strong_continuity and has_visual_context:
        return ConfidenceState.HIGH_CONFIDENCE
    if strong_fingerprint or strong_continuity:
        return ConfidenceState.CANDIDATE
    return ConfidenceState.DETECTED


DEFAULT_EVENT_MAP_PATH = os.path.join("audio_export", "live_scene_events.json")


def load_event_map(path: str = DEFAULT_EVENT_MAP_PATH) -> dict[str, LiveDialogueEvent]:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {eid: LiveDialogueEvent.from_dict(d) for eid, d in raw.items()}


def save_event(event: LiveDialogueEvent, path: str = DEFAULT_EVENT_MAP_PATH) -> None:
    events = load_event_map(path)
    events[event.event_id] = event
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({eid: e.to_dict() for eid, e in events.items()}, f, indent=2, ensure_ascii=False)


def new_event_id() -> str:
    return "event_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def identify_event_from_capture(
    samples,
    sample_rate: int,
    channels: int,
    known_db: dict,
    full_db: dict,
    screenshot_path: str | None = None,
    visible_text: str | None = None,
    speaker: str | None = None,
    chapter: str | None = None,
    scene: str | None = None,
    event_id: str | None = None,
    window_sizes: tuple[float, ...] = (1.0, 1.5),
) -> LiveDialogueEvent:
    """The streamlined, one-call version of the workflow this session
    built step by step: localize the voice window from the capture's
    own acoustic shape, try the small known/confirmed candidate set
    before ever touching the full ~340-asset database
    (`gcrts.output_audio_match.fast_match_with_known_candidates`), and
    combine the result with whatever visual context the caller already
    has (from a screenshot review) into one record whose confidence
    reflects how many independent evidence sources actually agree --
    never a single audio score alone.

    Takes already-captured audio samples (and, optionally, already-
    reviewed screenshot text/speaker/chapter) rather than performing
    the capture itself -- keeps this orchestration pure and testable
    with synthetic data, while the actual capture calls
    (`gcrts.output_audio_capture.record_loopback`,
    `gcrts.screen_capture.PcsxVramCaptureProvider`) stay thin, separate
    I/O wrappers a caller invokes first."""
    from gcrts.output_audio_match import (
        classify_match,
        compute_energy_profile,
        crop_excerpt,
        fast_match_with_known_candidates,
        filter_duration_plausible,
        find_speech_burst_region,
        normalize_for_matching,
    )

    if event_id is None:
        event_id = new_event_id()

    mono = samples.mean(axis=1) if hasattr(samples, "mean") else samples
    profile = compute_energy_profile(mono, sample_rate)
    region = find_speech_burst_region(profile)

    has_visual_context = bool(visible_text or speaker or chapter or scene)

    if region is None:
        return LiveDialogueEvent(
            event_id=event_id, captured_at=datetime.now(timezone.utc).isoformat(),
            screenshot_path=screenshot_path, visible_text=visible_text, speaker=speaker,
            chapter=chapter, scene=scene, confidence=ConfidenceState.REJECTED,
            notes="no speech-shaped region found in the capture",
        )

    begin, end = region
    context = crop_excerpt(samples, sample_rate, begin - 2.0, end + 2.0)
    context = normalize_for_matching(context)
    query_duration = end - begin

    plausible_known = filter_duration_plausible(known_db, query_duration)
    plausible_full = filter_duration_plausible(full_db, query_duration)
    result = fast_match_with_known_candidates(context, sample_rate, channels, plausible_known, plausible_full, window_sizes=window_sizes)

    top_run = result.runs[0] if result.runs else None
    confidence = classify_confidence(
        fingerprint_similarity=top_run.mean_similarity if top_run else None,
        continuity_windows=top_run.n_windows if top_run else None,
        continuity_error=top_run.offset_advance_error if top_run else None,
        has_visual_context=has_visual_context,
    )

    evidence = []
    if top_run:
        evidence.append("audio fingerprint")
        evidence.append("offset continuity")
    if has_visual_context:
        evidence.append("visible scene")
    if result.search_path == "known_candidates":
        evidence.append("known-candidate fast path")

    return LiveDialogueEvent(
        event_id=event_id, captured_at=datetime.now(timezone.utc).isoformat(),
        screenshot_path=screenshot_path, visible_text=visible_text, speaker=speaker,
        chapter=chapter, scene=scene,
        voice_begin=begin, voice_end=end,
        asset_id=top_run.asset_id if top_run else None,
        fingerprint_similarity=top_run.mean_similarity if top_run else None,
        offset_continuity_windows=top_run.n_windows if top_run else None,
        offset_continuity_error=top_run.offset_advance_error if top_run else None,
        evidence=evidence, confidence=confidence,
        notes=f"search_path={result.search_path}; classification={result.classification.value}",
    )
