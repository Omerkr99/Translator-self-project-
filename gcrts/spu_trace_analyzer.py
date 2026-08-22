"""SPU Trace Analyzer: turns a raw `gcrts.spu_playback_trace` JSONL
event stream into the answer the "smallest decisive runtime experiment"
milestone needs -- not "which XAPACK looks plausible," but "which real
PS1 audio path produced the target save-slot-9 dialogue at the exact
moment a human marked it as audible," classified into exactly one of
`SPU_VOICE_PLAYBACK` / `CD_AUDIO_INPUT` / `OTHER_OR_UNKNOWN` /
`NOT_YET_CLASSIFIED`, per this milestone's own required taxonomy.

## Evidence discipline

Every classification here is a NAMED CONCLUSION traceable to specific
events actually present in the data -- never a bare guess. Critically,
**absence of a signal is only meaningful once the instrumentation
that would have caught it is proven alive** (`assess_instrumentation_
health`) -- "no Key ON observed" is `instrumentation_not_yet_validated`
until at least one real Key-write hit (meaningful or not) and at least
one heartbeat are seen SOMEWHERE in the session, proving the relevant
breakpoints/listeners actually fired.

This module does not repeat the "current LBA -> guess XAPACK -> audio
candidate" pattern this project explicitly moved away from
(`docs/status/CURRENT_SYSTEM_STATUS.md`, 2026-08-23 entry): a
`HeartbeatEvent`'s `position_counter` is resolved to a real
`AudioAsset` here ONLY as correlation evidence attached to a
classification already reached from Key-write/CD-command/lifecycle
evidence, never as the classification's own basis.

## Two marker labels, one continuous trace

`pcsx_lua/spu_playback_trace.lua`'s marker key alternates
`TARGET_BEGIN`/`TARGET_END` on successive presses, so one continuous
recording session naturally supports repeated runs
(BEGIN/END/BEGIN/END/...) without reloading the script --
`pair_target_runs` turns that flat marker sequence into a list of
`TargetRun`s, explicitly reporting a trailing unpaired `TARGET_BEGIN`
(an odd number of marker presses) rather than silently dropping or
mis-pairing it.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from enum import Enum

from gcrts.audio_asset_resolver import AudioAssetResolution, ResolutionConfidence, resolve_audio_asset
from gcrts.runtime_audio import AudioLifecycleState
from gcrts.spu_audio_path import spu_internal_ram_directly_inspectable
from gcrts.spu_playback_trace import (
    CdCommandEvent,
    HeartbeatEvent,
    MarkEvent,
    SaveStateLoadedEvent,
    SpuKeyWriteEvent,
    SpucntWriteEvent,
    TraceEvent,
    load_trace,
)

_PLAYING_RAW = 0x01  # AudioLifecycleState.PLAYING's raw byte value, gcrts.runtime_audio


# --- single-marker window helpers (pre-existing API, unchanged signatures) ----


def events_near_marker(
    events: list[TraceEvent],
    marker: MarkEvent,
    before_seconds: float = 2.0,
    after_seconds: float = 2.0,
) -> list[TraceEvent]:
    """All events (including the marker itself) with `t` in
    `[marker.t - before_seconds, marker.t + after_seconds]`. The window
    is intentionally a parameter, not a hardcoded constant."""
    lo, hi = marker.t - before_seconds, marker.t + after_seconds
    return [e for e in events if lo <= e.t <= hi]


def first_marker(events: list[TraceEvent]) -> MarkEvent | None:
    marks = [e for e in events if isinstance(e, MarkEvent)]
    return marks[0] if marks else None


def events_in_range(events: list[TraceEvent], lo: float, hi: float) -> list[TraceEvent]:
    return [e for e in events if lo <= e.t <= hi]


# --- TARGET_BEGIN / TARGET_END pairing ------------------------------------------


@dataclass
class TargetRun:
    """One BEGIN/END pair -- one auditioned occurrence of the target
    line. `run_index` is 0-based, in the order markers were pressed."""

    run_index: int
    begin: MarkEvent
    end: MarkEvent

    @property
    def duration(self) -> float:
        return self.end.t - self.begin.t


def pair_target_runs(events: list[TraceEvent]) -> tuple[list[TargetRun], MarkEvent | None]:
    """Turns the flat, alternating TARGET_BEGIN/TARGET_END marker
    sequence into `TargetRun`s. Returns `(runs, dangling_begin)` --
    `dangling_begin` is the trailing unpaired `MarkEvent` if the total
    number of TARGET_BEGIN/TARGET_END markers is odd (the user pressed
    the marker key an odd number of times total), never silently
    dropped or paired with the wrong event. Marks with any OTHER label
    (e.g. a generic single-marker session using the older API above)
    are ignored here, not an error."""
    target_marks = [e for e in events if isinstance(e, MarkEvent) and e.label in ("TARGET_BEGIN", "TARGET_END")]
    target_marks.sort(key=lambda e: e.t)

    runs: list[TargetRun] = []
    pending_begin: MarkEvent | None = None
    run_index = 0
    for mark in target_marks:
        if mark.label == "TARGET_BEGIN":
            if pending_begin is not None:
                # Two BEGINs in a row with no END between them -- the
                # earlier BEGIN is dangling; report the LATEST one as
                # pending, don't silently discard the mismatch.
                pending_begin = mark
            else:
                pending_begin = mark
        elif mark.label == "TARGET_END":
            if pending_begin is not None:
                runs.append(TargetRun(run_index, pending_begin, mark))
                run_index += 1
                pending_begin = None
            # a TARGET_END with no preceding BEGIN is dropped silently
            # here -- genuinely ambiguous (which run does it close?),
            # and not the failure mode this function documents.
    return runs, pending_begin


def tight_window(run: TargetRun, before_ms: float = 250.0, after_ms: float = 250.0) -> tuple[float, float]:
    """`TARGET_BEGIN - before_ms` to `TARGET_END + after_ms`, in
    seconds -- for events tightly synchronized to the audible line."""
    return run.begin.t - before_ms / 1000.0, run.end.t + after_ms / 1000.0


def context_window(run: TargetRun, before_s: float = 2.0, after_s: float = 2.0) -> tuple[float, float]:
    """`TARGET_BEGIN - before_s` to `TARGET_END + after_s` -- for
    identifying setup events (buffer loads, CD seek/read commands,
    mixer changes) that precede audible playback."""
    return run.begin.t - before_s, run.end.t + after_s


@dataclass
class ControlWindows:
    silence: tuple[float, float]  # Control A: shortly before the target line
    post_dialogue: tuple[float, float]  # Control C: shortly after the target line


def control_windows(run: TargetRun, silence_seconds: float = 2.0, post_seconds: float = 2.0) -> ControlWindows:
    """Control A/C are derived automatically from the already-captured
    TARGET_BEGIN/TARGET_END markers -- no extra marker press needed,
    since the tracer already runs continuously across the whole
    session. Control B (a known, naturally-occurring SFX/UI sound) has
    no dedicated marker in this tooling -- if one occurs, it shows up
    as ordinary SPU_KEY_WRITE/CD_COMMAND activity outside the target
    run's own window and is reported as such in the human-readable
    report, not required as a separate capture step."""
    return ControlWindows(
        silence=(run.begin.t - silence_seconds, run.begin.t),
        post_dialogue=(run.end.t, run.end.t + post_seconds),
    )


# --- instrumentation health: absence is only evidence once proven alive --------


@dataclass
class InstrumentationHealth:
    heartbeat_seen: bool
    any_key_write_seen: bool  # ANY SpuKeyWriteEvent, meaningful or not -- proves the Exec breakpoint fired
    cd_command_seen: bool
    save_state_load_seen: bool
    timestamps_monotonic: bool
    issues: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """The minimum bar for treating an absence-of-signal result as
        real evidence rather than an untested hook: at least one
        heartbeat (proves the Lua tracer's main-RAM reads are alive)
        AND at least one Key-write hit of ANY kind, meaningful or not
        (proves the SPU Key ON/OFF breakpoints are actually firing --
        this project's own prior captures found the PERIODIC_VOICE_
        SYNC pair firing constantly, ~9.5 Hz, so a real session of more
        than a couple seconds with zero hits at all is itself a strong
        signal something is wrong with the hook, not with the game)."""
        return self.heartbeat_seen and self.any_key_write_seen and self.timestamps_monotonic


def assess_instrumentation_health(events: list[TraceEvent]) -> InstrumentationHealth:
    heartbeat_seen = any(isinstance(e, HeartbeatEvent) for e in events)
    any_key_write_seen = any(isinstance(e, SpuKeyWriteEvent) for e in events)
    cd_command_seen = any(isinstance(e, CdCommandEvent) for e in events)
    save_state_load_seen = any(isinstance(e, SaveStateLoadedEvent) for e in events)
    timestamps = [e.t for e in events]
    timestamps_monotonic = all(a <= b for a, b in zip(timestamps, timestamps[1:]))

    issues = []
    if not heartbeat_seen:
        issues.append("no HEARTBEAT event seen -- the per-vsync listener may not be armed, or the trace is empty")
    if not any_key_write_seen:
        issues.append(
            "no SPU_KEY_WRITE event of ANY kind seen (not even a zero-mask hit) -- the Key ON/OFF breakpoints "
            "may not have fired at all this session; prior sessions found the periodic sync pair firing "
            "constantly, so a total absence is itself suspicious"
        )
    if not timestamps_monotonic:
        issues.append("event timestamps are not monotonically non-decreasing -- check for a bad merge or clock reset")

    return InstrumentationHealth(heartbeat_seen, any_key_write_seen, cd_command_seen, save_state_load_seen, timestamps_monotonic, issues)


# --- classification --------------------------------------------------------------


class SpuTraceClassification(str, Enum):
    SPU_VOICE_PLAYBACK = "SPU_VOICE_PLAYBACK"
    CD_AUDIO_INPUT = "CD_AUDIO_INPUT"
    OTHER_OR_UNKNOWN = "OTHER_OR_UNKNOWN"
    NOT_YET_CLASSIFIED = "NOT_YET_CLASSIFIED"


class Confidence(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class ClassificationResult:
    classification: SpuTraceClassification
    evidence: str
    confidence: Confidence
    confidence_reason: str
    meaningful_key_writes: list[SpuKeyWriteEvent]
    heartbeats: list[HeartbeatEvent]

    def to_dict(self) -> dict:
        return {
            "classification": self.classification.value,
            "evidence": self.evidence,
            "confidence": self.confidence.value,
            "confidence_reason": self.confidence_reason,
            "meaningful_key_write_count": len(self.meaningful_key_writes),
            "heartbeat_count": len(self.heartbeats),
        }


def classify_playback_from_trace(
    window_events: list[TraceEvent],
    full_trace_events: list[TraceEvent] | None = None,
) -> ClassificationResult:
    """The milestone's core question, answered from one window's worth
    of events. `full_trace_events`, if given, is used ONLY for the
    instrumentation-health check (a hook can fire outside the narrow
    target window and still prove itself alive) -- defaults to
    `window_events` itself when omitted, so a self-contained window
    that already includes its own proof-of-life still classifies
    correctly.

    Rules (see module docstring for the evidence-discipline reasoning):

    - Instrumentation not validated (`assess_instrumentation_health`
      fails): `NOT_YET_CLASSIFIED`, regardless of what IS observed --
      absence of a signal from an unproven hook is not evidence.
    - No marker in the window: `NOT_YET_CLASSIFIED` -- a human capture
      is still required.
    - At least one `SpuKeyWriteEvent` with a nonzero (`is_meaningful`)
      voice mask in the window: `SPU_VOICE_PLAYBACK`.
    - No meaningful Key writes, but the position-counter lifecycle
      state is `PLAYING` (0x01) in the window, OR a
      `SaveStateLoadedEvent` falls in the window (the already-observed
      "appears at t=0.0s after reload" pattern): `CD_AUDIO_INPUT`.
    - A marker exists, instrumentation is valid, but neither signal is
      present: `OTHER_OR_UNKNOWN`.
    """
    marker = first_marker(window_events) or next(
        (e for e in window_events if isinstance(e, MarkEvent) and e.label in ("TARGET_BEGIN", "TARGET_END")), None
    )
    if marker is None:
        return ClassificationResult(
            SpuTraceClassification.NOT_YET_CLASSIFIED,
            "No MARK event in this window -- a human capture (load slot 9, play, mark TARGET_BEGIN/TARGET_END) "
            "is still required before this can be classified.",
            Confidence.LOW,
            "No marker means no confirmed target moment to evaluate evidence around.",
            [], [],
        )

    key_writes = [e for e in window_events if isinstance(e, SpuKeyWriteEvent)]
    meaningful_key_writes = [e for e in key_writes if e.is_meaningful]
    heartbeats = [e for e in window_events if isinstance(e, HeartbeatEvent)]
    save_state_loads = [e for e in window_events if isinstance(e, SaveStateLoadedEvent)]

    if meaningful_key_writes:
        # Positive, self-certifying evidence -- a real nonzero voice
        # bitmask arriving via PCSX.getRegisters() at a live Exec
        # breakpoint hit IS proof that specific hook fired; it needs no
        # separate instrumentation-health gate the way an ABSENCE of
        # signal does (see the health check below, applied only to the
        # negative/CD_AUDIO_INPUT and OTHER_OR_UNKNOWN paths).
        voices = sorted({v for e in meaningful_key_writes for v in e.active_voices})
        confidence = Confidence.HIGH if len(meaningful_key_writes) > 1 else Confidence.MEDIUM
        return ClassificationResult(
            SpuTraceClassification.SPU_VOICE_PLAYBACK,
            f"{len(meaningful_key_writes)} meaningful Key ON/OFF write(s) in the window, naming voice(s) {voices} "
            "-- the first time this project's tooling has observed a non-empty voice bitmask at a Key writer "
            "site during a marked-audible window (every prior armed capture found only the empty/no-op mask).",
            confidence,
            "Single-run evidence" if len(meaningful_key_writes) <= 1 else "Multiple consistent hits within one run",
            meaningful_key_writes, heartbeats,
        )

    # From here on, any conclusion rests on the ABSENCE of a meaningful
    # Key write -- per this milestone's own critical negative-evidence
    # rule, that absence is only meaningful once the hooks that would
    # have caught it are proven alive somewhere in the full session.
    health = assess_instrumentation_health(full_trace_events if full_trace_events is not None else window_events)
    if not health.is_valid:
        return ClassificationResult(
            SpuTraceClassification.NOT_YET_CLASSIFIED,
            "instrumentation_not_yet_validated: " + "; ".join(health.issues),
            Confidence.LOW,
            "Cannot trust an absence-of-Key-write result until the instrumentation itself is proven alive.",
            [], [],
        )

    playing_heartbeats = [hb for hb in heartbeats if hb.lifecycle_state_raw == _PLAYING_RAW]
    if playing_heartbeats or save_state_loads:
        reason = (
            f"{len(playing_heartbeats)} HEARTBEAT(s) show the lifecycle-state byte in PLAYING (0x01)"
            if playing_heartbeats
            else "a SAVE_STATE_LOADED event falls in this window, matching the already-observed t=0.0s pattern"
        )
        return ClassificationResult(
            SpuTraceClassification.CD_AUDIO_INPUT,
            f"No meaningful Key ON/OFF writes in the window (instrumentation confirmed alive) -- {reason}. "
            "Consistent with gcrts.spu_audio_path.classify_playback_backend() -> CD_INPUT_UNKNOWN_FORMAT.",
            Confidence.MEDIUM,
            "Single-run evidence; cross-run reproducibility (see correlate_runs) would raise this to HIGH.",
            [], heartbeats,
        )

    return ClassificationResult(
        SpuTraceClassification.OTHER_OR_UNKNOWN,
        "Instrumentation confirmed alive and a marker exists, but neither a meaningful Key ON/OFF write nor a "
        "recognizable CD-input-lifecycle signal (PLAYING state, or a save-state-load anchor) appears in this "
        "window.",
        Confidence.LOW,
        "Genuinely inconclusive from this window alone -- widen the window or check for a producer gap.",
        [], heartbeats,
    )


# --- correlation with the existing LBA resolver (evidence only) ----------------


@dataclass
class CorrelatedResolution:
    heartbeat: HeartbeatEvent
    resolution: AudioAssetResolution


def correlate_heartbeats_with_resolver(window_events: list[TraceEvent], disc_bytes: bytes) -> list[CorrelatedResolution]:
    """Attaches the EXISTING, already-proven LBA resolver
    (`gcrts.audio_asset_resolver.resolve_audio_asset`) to every
    HEARTBEAT in a window that has a real `position_counter` --
    correlation evidence attached to a classification already reached
    above, never the classification's own basis."""
    results = []
    for e in window_events:
        if isinstance(e, HeartbeatEvent) and e.position_counter is not None:
            results.append(CorrelatedResolution(e, resolve_audio_asset(disc_bytes, e.position_counter)))
    return results


# --- SPU sample extraction gate (still blocked, re-confirmed not re-derived) ----


@dataclass
class SampleExtractionResult:
    available: bool
    reason: str


def attempt_spu_sample_extraction(voice_index: int, start_address_units_of_8: int) -> SampleExtractionResult:
    """Only meaningful when classify_playback_from_trace() returned
    SPU_VOICE_PLAYBACK with a real voice index. Refuses cleanly per
    this project's own already-established, still-unreversed
    conclusion (`gcrts.spu_audio_path.spu_internal_ram_directly_
    inspectable`) rather than fabricating extracted sample bytes."""
    if not spu_internal_ram_directly_inspectable():
        return SampleExtractionResult(
            False,
            f"SPU RAM is not inspectable through any tool available to this project (voice {voice_index}, "
            f"start address {start_address_units_of_8 * 8} bytes into SPU RAM would be the target region). "
            "The limitation is specifically that the CURRENT PCSX-Redux Lua interface cannot access SPU RAM -- "
            "not a claim that extraction is impossible in general. See gcrts.spu_audio_path."
            "SPU_RAM_INSPECTION_AVENUES_CHECKED for what has been tried (GUI, Lua, GDB).",
        )
    raise NotImplementedError("spu_internal_ram_directly_inspectable() is True but no extraction path is implemented yet")


# --- cross-run correlation --------------------------------------------------------


@dataclass
class RunEvidence:
    run_label: str  # e.g. "trace1.jsonl run 0"
    classification: ClassificationResult
    voices: list[int]
    write_pcs: list[int]
    cd_commands: list[str]
    lba_region: str | None


def build_run_evidence(run_label: str, window_events: list[TraceEvent], full_trace_events: list[TraceEvent]) -> RunEvidence:
    result = classify_playback_from_trace(window_events, full_trace_events)
    voices = sorted({v for e in result.meaningful_key_writes for v in e.active_voices})
    write_pcs = sorted({e.write_pc for e in result.meaningful_key_writes})
    cd_commands = sorted({e.command_name for e in window_events if isinstance(e, CdCommandEvent)})
    heartbeats_with_position = [e for e in window_events if isinstance(e, HeartbeatEvent) and e.position_counter is not None]
    lba_region = f"{heartbeats_with_position[0].position_counter}-{heartbeats_with_position[-1].position_counter}" if heartbeats_with_position else None
    return RunEvidence(run_label, result, voices, write_pcs, cd_commands, lba_region)


def correlate_runs(runs: list[RunEvidence]) -> list[dict]:
    """A compact table (list of {evidence, values-per-run, stable}
    rows), comparing whether each signal is the SAME across runs --
    distinguishing deterministic behavior from incidental timing
    coincidence. `stable` is True only when every run that has a value
    for that row agrees; a row where every run reports "none" is
    stable too (a consistent negative)."""
    rows = []

    def _row(name: str, getter) -> dict:
        values = [getter(r) for r in runs]
        stable = len({repr(v) for v in values}) <= 1
        return {"evidence": name, "values": values, "stable": stable}

    rows.append(_row("classification", lambda r: r.classification.classification.value))
    rows.append(_row("Key ON voice(s)", lambda r: tuple(r.voices) if r.voices else "none"))
    rows.append(_row("Key writer PC(s)", lambda r: tuple(hex(p) for p in r.write_pcs) if r.write_pcs else "none"))
    rows.append(_row("CD command(s)", lambda r: tuple(r.cd_commands) if r.cd_commands else "none"))
    rows.append(_row("LBA region", lambda r: r.lba_region or "none"))
    return rows


# --- human-readable report ---------------------------------------------------------


def build_report(trace_paths: list[str], before_ms: float = 250.0, after_ms: float = 250.0, context_s: float = 2.0) -> str:
    """Builds the full readable report described in
    docs/audio/SPU_PLAYBACK_TRACE.md's analyzer section, across one or
    more trace files (multiple files/runs enable cross-run
    correlation)."""
    lines: list[str] = []
    all_run_evidence: list[RunEvidence] = []

    for path in trace_paths:
        events = load_trace(path)
        events.sort(key=lambda e: e.t)
        lines.append(f"=== {path} ===")

        health = assess_instrumentation_health(events)
        lines.append("-- Trace integrity --")
        lines.append(f"events: {len(events)}")
        lines.append(f"duration: {events[-1].t - events[0].t:.2f}s" if events else "duration: (empty trace)")
        lines.append(f"heartbeat count: {sum(1 for e in events if isinstance(e, HeartbeatEvent))}")
        lines.append(f"marker count: {sum(1 for e in events if isinstance(e, MarkEvent))}")
        lines.append(f"timestamps monotonic: {health.timestamps_monotonic}")
        if health.issues:
            lines.append("instrumentation issues: " + "; ".join(health.issues))

        runs, dangling = pair_target_runs(events)
        lines.append("")
        lines.append("-- Markers --")
        lines.append(f"paired TARGET_BEGIN/TARGET_END runs: {len(runs)}")
        if dangling is not None:
            lines.append(f"WARNING: dangling unpaired {dangling.label} at t={dangling.t:.2f}s -- odd number of marker presses")

        for run in runs:
            lines.append("")
            lines.append(f"--- Run {run.run_index}: TARGET_BEGIN={run.begin.t:.2f}s TARGET_END={run.end.t:.2f}s duration={run.duration:.2f}s ---")

            tight_lo, tight_hi = tight_window(run, before_ms, after_ms)
            ctx_lo, ctx_hi = context_window(run, context_s, context_s)
            tight = events_in_range(events, tight_lo, tight_hi)
            ctx = events_in_range(events, ctx_lo, ctx_hi)
            controls = control_windows(run)
            silence_events = events_in_range(events, *controls.silence)
            post_events = events_in_range(events, *controls.post_dialogue)

            lines.append("Controls:")
            lines.append(f"  Control A (silence, {controls.silence[0]:.2f}s-{controls.silence[1]:.2f}s): "
                         f"{sum(1 for e in silence_events if isinstance(e, SpuKeyWriteEvent) and e.is_meaningful)} meaningful Key writes, "
                         f"{sum(1 for e in silence_events if isinstance(e, CdCommandEvent))} CD commands")
            lines.append(f"  Control C (post-dialogue, {controls.post_dialogue[0]:.2f}s-{controls.post_dialogue[1]:.2f}s): "
                         f"{sum(1 for e in post_events if isinstance(e, SpuKeyWriteEvent) and e.is_meaningful)} meaningful Key writes, "
                         f"{sum(1 for e in post_events if isinstance(e, CdCommandEvent))} CD commands")

            result = classify_playback_from_trace(tight, events)
            lines.append("")
            lines.append("Target SPU activity (tight window):")
            for e in tight:
                if isinstance(e, SpuKeyWriteEvent):
                    lines.append(f"  t={e.t:.3f}s {e.register} mask={e.voice_mask:#08x} voices={e.active_voices} write_pc={e.write_pc:#010x}")
            lines.append("")
            lines.append("Target CD activity (context window):")
            for e in ctx:
                if isinstance(e, CdCommandEvent):
                    lines.append(f"  t={e.t:.3f}s {e.command_name} (0x{e.command_byte:02X}) a0={e.a0} a1={e.a1} @{e.call_site_addr:#010x}")

            lines.append("")
            lines.append("Mixer / control state (context window):")
            for e in ctx:
                if isinstance(e, SpucntWriteEvent):
                    lines.append(f"  t={e.t:.3f}s SPUCNT={e.value:#06x} CD_audio_enable={e.cd_audio_enable_bit_set}")

            lines.append("")
            lines.append(f"Classification: {result.classification.value}")
            lines.append(f"Evidence: {result.evidence}")
            lines.append(f"Confidence: {result.confidence.value} -- {result.confidence_reason}")

            all_run_evidence.append(build_run_evidence(f"{path} run {run.run_index}", tight, events))

        lines.append("")

    if len(all_run_evidence) > 1:
        lines.append("=== Cross-run correlation ===")
        table = correlate_runs(all_run_evidence)
        for row in table:
            lines.append(f"{row['evidence']}: {row['values']} -- stable: {row['stable']}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze one or more SPU Playback Trace JSONL files.")
    parser.add_argument("trace_paths", nargs="+", help="Path(s) to spu_playback_trace.jsonl (one per run for cross-run correlation)")
    parser.add_argument("--tight-before-ms", type=float, default=250.0)
    parser.add_argument("--tight-after-ms", type=float, default=250.0)
    parser.add_argument("--context-s", type=float, default=2.0)
    args = parser.parse_args(argv)
    print(build_report(args.trace_paths, args.tight_before_ms, args.tight_after_ms, args.context_s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
