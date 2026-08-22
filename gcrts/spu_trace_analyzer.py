"""SPU Trace Analyzer: turns a raw `gcrts.spu_playback_trace` JSONL
event stream into the answer the "SPU Playback Trace" milestone
actually needs -- not "which XAPACK looks plausible," but "which real
PS1 audio path produced what the user marked as audible," classified
into exactly one of `SPU_VOICE_PLAYBACK` / `CD_AUDIO_INPUT` /
`OTHER_OR_UNKNOWN` / `NOT_YET_CLASSIFIED`, per this milestone's own
required taxonomy.

## Evidence discipline

Every classification here is a NAMED CONCLUSION traceable to specific
events actually present in the trace window -- never a bare guess.
`classify_playback_from_trace` returns both the classification AND the
`evidence` string explaining exactly which events drove it, so a
reader can check the reasoning without re-running anything.

This module does not repeat the "current LBA -> guess XAPACK -> audio
candidate" pattern this project explicitly moved away from
(`docs/status/CURRENT_SYSTEM_STATUS.md`, 2026-08-23 entry): a
`HEARTBEAT` event's `position_counter` is resolved to a real
`AudioAsset` here ONLY as correlation evidence attached to a
classification already reached from Key-write evidence, never as the
classification's own basis.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from gcrts.audio_asset_resolver import AudioAssetResolution, ResolutionConfidence, resolve_audio_asset
from gcrts.spu_audio_path import spu_internal_ram_directly_inspectable
from gcrts.spu_playback_trace import (
    HeartbeatEvent,
    MarkEvent,
    SaveStateLoadedEvent,
    SpuKeyWriteEvent,
    SpucntWriteEvent,
    TraceEvent,
)


def events_near_marker(
    events: list[TraceEvent],
    marker: MarkEvent,
    before_seconds: float = 2.0,
    after_seconds: float = 2.0,
) -> list[TraceEvent]:
    """All events (including the marker itself) with `t` in
    `[marker.t - before_seconds, marker.t + after_seconds]`. The window
    is intentionally a parameter, not a hardcoded constant -- the
    milestone brief's own MARK-2s..MARK+2s example is a default, not a
    fixed rule; a longer line needs a wider window."""
    lo, hi = marker.t - before_seconds, marker.t + after_seconds
    return [e for e in events if lo <= e.t <= hi]


def first_marker(events: list[TraceEvent]) -> MarkEvent | None:
    marks = [e for e in events if isinstance(e, MarkEvent)]
    return marks[0] if marks else None


class SpuTraceClassification(str, Enum):
    SPU_VOICE_PLAYBACK = "SPU_VOICE_PLAYBACK"
    CD_AUDIO_INPUT = "CD_AUDIO_INPUT"
    OTHER_OR_UNKNOWN = "OTHER_OR_UNKNOWN"
    NOT_YET_CLASSIFIED = "NOT_YET_CLASSIFIED"


@dataclass
class ClassificationResult:
    classification: SpuTraceClassification
    evidence: str
    meaningful_key_writes: list[SpuKeyWriteEvent]
    heartbeats: list[HeartbeatEvent]

    def to_dict(self) -> dict:
        return {
            "classification": self.classification.value,
            "evidence": self.evidence,
            "meaningful_key_write_count": len(self.meaningful_key_writes),
            "heartbeat_count": len(self.heartbeats),
        }


def classify_playback_from_trace(window_events: list[TraceEvent]) -> ClassificationResult:
    """The milestone's core question, answered from one marker window's
    worth of events.

    - No marker in the window at all (or an empty window): `NOT_YET_
      CLASSIFIED` -- a human capture is still required, this is not a
      failure state.
    - At least one `SpuKeyWriteEvent` with a nonzero (`is_meaningful`)
      voice mask in the window: `SPU_VOICE_PLAYBACK`. This is the one
      piece of evidence this project has never yet observed for this
      game's dialogue in ~10 prior armed-capture sessions
      (`gcrts.spu_audio_path.LIVE_CORRELATION_RUNS`) -- if it shows up
      here, it is genuinely new and should NOT be waved away as noise.
    - No meaningful Key writes, but at least one `HeartbeatEvent`
      showing the position counter's lifecycle state advancing (or a
      `SaveStateLoadedEvent` immediately preceding the marker, matching
      the already-observed "appears at t=0.0s after reload" pattern):
      `CD_AUDIO_INPUT` -- consistent with, not a new discovery beyond,
      `gcrts.spu_audio_path.classify_playback_backend() ->
      CD_INPUT_UNKNOWN_FORMAT`.
    - A marker exists but neither signal is present: `OTHER_OR_UNKNOWN`
      -- an honest admission, not a forced pick between the other two.
    """
    marker = first_marker(window_events)
    if marker is None:
        return ClassificationResult(
            SpuTraceClassification.NOT_YET_CLASSIFIED,
            "No MARK event in this window -- a human capture (load slot 9, play, press the marker key when the "
            "target line is heard) is still required before this can be classified.",
            [], [],
        )

    key_writes = [e for e in window_events if isinstance(e, SpuKeyWriteEvent)]
    meaningful_key_writes = [e for e in key_writes if e.is_meaningful]
    heartbeats = [e for e in window_events if isinstance(e, HeartbeatEvent)]
    save_state_loads = [e for e in window_events if isinstance(e, SaveStateLoadedEvent)]

    if meaningful_key_writes:
        voices = sorted({v for e in meaningful_key_writes for v in e.active_voices})
        return ClassificationResult(
            SpuTraceClassification.SPU_VOICE_PLAYBACK,
            f"{len(meaningful_key_writes)} meaningful Key ON/OFF write(s) in the marker window, naming voice(s) "
            f"{voices} -- this is the first time this project's tooling has observed a non-empty voice bitmask "
            "at a Key writer site during a marked-audible window (every prior armed capture found only the "
            "empty/no-op mask). Treat as SPU voice playback for this specific line.",
            meaningful_key_writes, heartbeats,
        )

    heartbeat_evidence = ""
    if any(hb.lifecycle_state_raw == 0x01 for hb in heartbeats):
        heartbeat_evidence = "at least one HEARTBEAT shows the lifecycle-state byte in its PLAYING (0x01) value"
    elif save_state_loads:
        heartbeat_evidence = "a SAVE_STATE_LOADED event falls in this window, matching the already-observed 't=0.0s' pattern for CD-input dialogue"

    if heartbeat_evidence:
        return ClassificationResult(
            SpuTraceClassification.CD_AUDIO_INPUT,
            f"No meaningful Key ON/OFF writes in the marker window (all hits, if any, carried an empty voice "
            f"mask) -- {heartbeat_evidence}. Consistent with gcrts.spu_audio_path.classify_playback_backend() "
            "-> CD_INPUT_UNKNOWN_FORMAT, this project's already-established general finding for this game's "
            "dialogue (all_spu_voices_muted_dialogue_still_audible() -> True, twice, independently).",
            [], heartbeats,
        )

    return ClassificationResult(
        SpuTraceClassification.OTHER_OR_UNKNOWN,
        "A marker exists, but neither a meaningful Key ON/OFF write nor a recognizable CD-input-lifecycle "
        "signal (PLAYING state, or a save-state-load anchor) appears in this window. Genuinely inconclusive "
        "from this trace alone -- widen the window or check for a producer gap, not a forced classification.",
        [], heartbeats,
    )


@dataclass
class CorrelatedResolution:
    heartbeat: HeartbeatEvent
    resolution: AudioAssetResolution


def correlate_heartbeats_with_resolver(window_events: list[TraceEvent], disc_bytes: bytes) -> list[CorrelatedResolution]:
    """Attaches the EXISTING, already-proven LBA resolver
    (`gcrts.audio_asset_resolver.resolve_audio_asset`) to every
    HEARTBEAT in a marker window that has a real `position_counter` --
    reused, not reimplemented. This is correlation EVIDENCE attached
    to a classification already reached from Key-write/lifecycle
    evidence above, never the classification's own basis (see module
    docstring's evidence-discipline note)."""
    results = []
    for e in window_events:
        if isinstance(e, HeartbeatEvent) and e.position_counter is not None:
            results.append(CorrelatedResolution(e, resolve_audio_asset(disc_bytes, e.position_counter)))
    return results


@dataclass
class SampleExtractionResult:
    available: bool
    reason: str


def attempt_spu_sample_extraction(voice_index: int, start_address_units_of_8: int) -> SampleExtractionResult:
    """Only meaningful when classify_playback_from_trace() returned
    SPU_VOICE_PLAYBACK with a real voice index. Checks this project's
    own already-established, still-unreversed conclusion
    (`gcrts.spu_audio_path.spu_internal_ram_directly_inspectable`)
    before attempting anything -- refuses cleanly with an honest reason
    rather than fabricating extracted sample bytes. Do not remove this
    guard without new, independently-verified evidence that some tool
    can now read the SPU's internal 512KB sound RAM (GUI, Lua, and GDB
    were all re-checked this same milestone and remain blocked -- see
    gcrts.spu_playback_trace's module docstring for the primary-source
    Lua FFI evidence gathered this session)."""
    if not spu_internal_ram_directly_inspectable():
        return SampleExtractionResult(
            False,
            f"SPU RAM is not inspectable through any tool available to this project (voice {voice_index}, "
            f"start address {start_address_units_of_8 * 8} bytes into SPU RAM would be the target region if it "
            "were). See gcrts.spu_audio_path.SPU_RAM_INSPECTION_AVENUES_CHECKED for the full list of closed "
            "avenues (GUI Memory Editors, native SPU Debug window, PCSX-Redux's documented Lua API, GDB's SPU "
            "MMIO path) -- re-confirmed via the real Lua FFI source this session, not just prior documentation.",
        )
    # Unreachable with current tooling -- left explicit rather than omitted,
    # so a future session that finds a real SPU RAM channel has a clear
    # place to implement extraction instead of needing to rediscover this
    # function.
    raise NotImplementedError("spu_internal_ram_directly_inspectable() is True but no extraction path is implemented yet")
