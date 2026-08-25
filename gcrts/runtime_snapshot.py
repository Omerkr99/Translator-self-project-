"""Milestone 6: a coherent, persistable snapshot of runtime evidence-pipeline
state -- groundwork for future movie/audio/subtitle work per the master
workflow's own dependency order (runtime identification before movies,
movies before audio, audio before subtitles).

A `RuntimeSnapshot` is captured from a `RuntimeVisualProvider` immediately
after a `scan()` call (no second live connection -- see
`capture_runtime_snapshot`'s docstring) and is plain, JSON-serializable
data: every field is a dict/list/str/int/float, so a saved snapshot is
inspectable later with no PCSX-Redux connection at all, paused, running,
or closed entirely. That is the whole point of this milestone -- per its
own wording, "allow the user to inspect a saved snapshot even after
gameplay resumes. Do not require the emulator to remain frozen."

`active_movie` is no longer an always-empty placeholder: the Movie/.STR
Runtime Detection milestone (gcrts.movie_detection) resolved it by
identifying the movie-player overlay family's residency directly
(gcrts.overlay_identity), rather than tracing internal DMA arguments --
only populated while that overlay family is actually resident, `None`
otherwise. `active_audio` was the earlier case of the same idea: the
Runtime Audio Tracker milestone (gcrts.runtime_audio)
gave `RuntimeVisualProvider` a real, live-verified audio-event capture
(`_audio_event`, called every `scan()`, result cached on
`provider.last_audio_event` the same way `last_renderer1_validation`
already was). `capture_runtime_snapshot` reads that cached event -- no
second live fetch -- and includes it ONLY while its state is genuinely
active (STARTING/PLAYING), never a STOPPED or UNKNOWN event, so a
snapshot never reports stale finished audio as currently playing.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from gcrts.runtime_content import RuntimeAssetInstance


def object_identity_key(o: dict) -> str | None:
    """Canonical cross-snapshot identity for one serialized screen object.
    Deliberately NOT the object's own `id` field: both asset ids
    (`f"runtime:{asset_id}:{x}:{y}"`) and Renderer 1 ids
    (`f"runtime:renderer1:{profile}:y{y}"`) embed screen position, so a
    moved-but-still-the-same-thing object would otherwise look like one
    disappearing and an unrelated one appearing, defeating "changed"
    detection entirely. Assets use their stable `source.asset_id`.
    Renderer 1 lines have no asset_id at all -- `line_index` is the only
    available stable-ish handle (ordinal position within the textbox, not
    a persistent identity across totally different lines of dialogue, but
    good enough for this milestone's deliberately small diff scope)."""
    source = o.get("source", {})
    if source.get("asset_id"):
        return source["asset_id"]
    if source.get("kind") == "RENDERER_1":
        return f"renderer1:line{source.get('line_index')}"
    return None


def _instance_to_dict(instance: RuntimeAssetInstance) -> dict:
    return {
        "runtime_instance_id": instance.runtime_instance_id,
        "asset_id": instance.asset_id,
        "state": instance.state.value,
        "confidence": instance.confidence.value,
        "created_frame": instance.created_frame,
        "last_transition_frame": instance.last_transition_frame,
        "compressed_ptr": instance.compressed_ptr,
        "decoded_ptr": instance.decoded_ptr,
        "decoded_size": instance.decoded_size,
        "vram_regions": [
            {
                "x": r.x,
                "y": r.y,
                "width": r.width,
                "height": r.height,
                "pixel_mode": r.pixel_mode,
                "generation": r.generation,
            }
            for r in instance.vram_regions
        ],
        "draw_count": len(instance.draws),
    }


@dataclass
class RuntimeSnapshot:
    snapshot_id: int
    captured_at: float
    objects: list[dict]
    tracker_instances: list[dict]
    renderer1_profile: str
    renderer1_validation: str
    active_movie: dict | None = None
    active_audio: list[dict] = field(default_factory=list)
    cdrom_driver: dict | None = None
    last_known_setfilter: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "RuntimeSnapshot":
        return cls(
            snapshot_id=d["snapshot_id"],
            captured_at=d["captured_at"],
            objects=list(d.get("objects", [])),
            tracker_instances=list(d.get("tracker_instances", [])),
            renderer1_profile=d.get("renderer1_profile", ""),
            renderer1_validation=d.get("renderer1_validation", ""),
            active_movie=d.get("active_movie"),
            active_audio=list(d.get("active_audio", [])),
            cdrom_driver=d.get("cdrom_driver"),
            last_known_setfilter=d.get("last_known_setfilter"),
        )

    @property
    def unknown_objects(self) -> list[dict]:
        return [o for o in self.objects if str(o.get("object_type", "")).startswith("UNKNOWN")]

    @property
    def active_asset_ids(self) -> set[str]:
        """Every object this snapshot can meaningfully identify across two
        different moments -- NOT just objects with a `source.asset_id`.
        Renderer 1 lines have no asset_id at all (see
        gcrts.screen_objects.renderer_1_object's `source` shape: `kind`/
        `script_unit`/`line_index`, never `asset_id`) -- an earlier version
        of this property silently dropped every Renderer 1 object from
        identity tracking, which meant `diff_snapshots` could never report
        Renderer 1 text appearing or disappearing. Caught live (this
        session) by scripted proof against a real dialogue scene, not by
        the unit tests, which had only ever exercised asset-shaped objects
        -- see the module's own test file for the regression test this
        added."""
        return {key for o in self.objects if (key := object_identity_key(o)) is not None}


def capture_runtime_snapshot(provider, frame: int, objects: list) -> RuntimeSnapshot:
    """Build a `RuntimeSnapshot` from a `RuntimeVisualProvider` that has
    JUST returned `(frame, objects)` from its own `scan()` -- this function
    performs NO live I/O of its own; it only reads attributes `scan()`
    already populated (`provider.tracker.instances`,
    `provider.last_renderer1_validation`). Passing `frame`/`objects`
    explicitly rather than calling `provider.scan()` again keeps this a
    snapshot of the SAME moment the caller already observed, not a second,
    slightly-later one."""
    from gcrts.renderer1_profile import SLPS00102_BASE_PROFILE
    from gcrts.runtime_audio import AudioLifecycleState

    audio_event = getattr(provider, "last_audio_event", None)
    script_association = getattr(provider, "last_script_association", None)
    audio_context = getattr(provider, "last_audio_context", None)
    audio_caption = getattr(provider, "last_audio_caption", None)
    audio_stream_source = getattr(provider, "last_audio_stream_source", None)
    cdrom_driver_map = getattr(provider, "last_cdrom_driver_map", None)
    movie_detection = getattr(provider, "last_movie_detection", None)
    active_audio = []
    if audio_event is not None and audio_event.state in (AudioLifecycleState.STARTING, AudioLifecycleState.PLAYING):
        entry = audio_event.to_dict()
        # Script Context <-> Audio Dispatch Correlation milestone: attach
        # WHICH script occurrence owns this event, when known -- see
        # SCRIPT_AUDIO_ASSOCIATION.md. Never fabricated: only attached
        # when the association was actually captured this scan.
        if script_association is not None:
            entry["script_context"] = script_association.to_dict()
        # Audio Bank/Context Resolution milestone: WHY the source above
        # was selected -- see AUDIO_CONTEXT_RESOLUTION.md. Present even
        # when UNKNOWN (never silently discarded), per that milestone's
        # own instruction.
        if audio_context is not None:
            entry["audio_context"] = audio_context.to_dict()
            # Handler->Physical-Source Resolution milestone: two
            # completely independent resolution paths (live LBA position
            # vs. script-selector table lookup) can now be cross-checked
            # against each other -- real corroboration, not a tautology,
            # since neither path's code depends on the other's.
            from gcrts.audio_context import cross_validate_source

            entry["source_cross_validated"] = cross_validate_source(audio_event, audio_context)
        # Audio Caption milestone: WHAT is being heard, kept explicitly
        # separate from source/context identity -- see AUDIO_CAPTIONS.md.
        if audio_caption is not None:
            entry["caption"] = audio_caption.to_dict()
        # XA File Open / Stream Resolution follow-up: the real
        # event-start-LBA descriptor, independent of both the
        # position-counter-based resolver and the selector-table one --
        # see AUDIO_CONTEXT_RESOLUTION.md. Present even when
        # UNKNOWN/unconfirmed, never silently discarded.
        # Audio Event Isolation / Extraction milestone: report readiness
        # honestly via gcrts.audio_event_extraction.extraction_readiness
        # -- deliberately does NOT plug in the historical
        # Setfilter(file=2, channel=1) observation for whatever event
        # happens to be active. A follow-up live capture (see
        # AUDIO_EVENT_EXTRACTION.md) found that specific Setfilter fired
        # while state was STOPPED with stale, unrelated last_req_params,
        # so it is not proven to be this or any other specific event's
        # own channel selection -- silently assuming it here would be
        # exactly the kind of unproven claim this project's own
        # discipline exists to prevent.
        from gcrts.audio_event_extraction import extraction_readiness
        from gcrts.audio_stream_source import AudioStreamConfidence

        start_lba = (
            audio_stream_source.file_start_lba
            if audio_stream_source is not None and audio_stream_source.confidence == AudioStreamConfidence.LIVE_VERIFIED
            else None
        )
        entry["extraction_status"] = extraction_readiness(
            start_lba=start_lba, end_lba=None, xa_file_number=None, xa_channel=None
        ).value
        if audio_stream_source is not None:
            entry["stream_source"] = audio_stream_source.to_dict()
        active_audio.append(entry)

    # XA Channel/Filter Runtime Resolution milestone: a static,
    # code-level fact (which hardware the CD-ROM driver's pointer
    # variables resolve to), not per-event -- kept top-level rather than
    # nested in active_audio, and present even when no audio is
    # currently active (see gcrts.cdrom_driver_map's own docstring).
    cdrom_driver = cdrom_driver_map.to_dict() if cdrom_driver_map is not None else None

    # XA Channel/Filter Runtime Resolution milestone: the real,
    # live-captured Setfilter(file, channel) evidence -- see
    # gcrts.cdrom_setfilter's own docstring for why this is a historical
    # fact (captured via a live breakpoint session, not re-derivable by
    # passive polling) rather than a per-scan live value, the same
    # pattern gcrts.runtime_audio.KNOWN_CUE_SOURCES already established.
    from gcrts.cdrom_setfilter import KNOWN_SETFILTER_OBSERVATIONS

    last_known_setfilter = (
        KNOWN_SETFILTER_OBSERVATIONS[-1].to_dict() if KNOWN_SETFILTER_OBSERVATIONS else None
    )

    # Movie/.STR Runtime Detection milestone (gcrts.movie_detection):
    # active_movie is real data now, not an always-empty placeholder --
    # only populated while the movie-player overlay family is actually
    # resident (never guessed, never left stale once movie_detection
    # reports no movie active).
    active_movie = movie_detection.to_dict() if movie_detection is not None and movie_detection.movie_active else None

    return RuntimeSnapshot(
        snapshot_id=frame,
        captured_at=time.time(),
        objects=[o.to_dict() for o in objects],
        tracker_instances=[_instance_to_dict(i) for i in provider.tracker.instances.values()],
        renderer1_profile=SLPS00102_BASE_PROFILE.profile_name,
        renderer1_validation=provider.last_renderer1_validation,
        active_movie=active_movie,
        active_audio=active_audio,
        cdrom_driver=cdrom_driver,
        last_known_setfilter=last_known_setfilter,
    )


def save_snapshot(snapshot: RuntimeSnapshot, path: str | Path) -> None:
    Path(path).write_text(json.dumps(snapshot.to_dict(), indent=2), encoding="utf-8")


def load_snapshot(path: str | Path) -> RuntimeSnapshot:
    return RuntimeSnapshot.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass
class SnapshotDiff:
    appeared: list[str]
    disappeared: list[str]
    changed: list[str]

    @property
    def is_empty(self) -> bool:
        return not (self.appeared or self.disappeared or self.changed)


def diff_snapshots(a: RuntimeSnapshot, b: RuntimeSnapshot) -> SnapshotDiff:
    """6.2, kept intentionally small per the milestone's own instruction
    not to let comparison expand scope: appeared/disappeared by asset_id
    set difference, changed = present in both but a meaningfully different
    state or screen position (not e.g. a re-serialized-but-identical
    object) -- exact byte/dict equality would flag noise like a changed
    primitive_address for the same asset in the same place as "changed"
    when nothing a user would call different actually happened, so this
    compares state + bounds specifically."""
    by_id_a = {key: o for o in a.objects if (key := object_identity_key(o)) is not None}
    by_id_b = {key: o for o in b.objects if (key := object_identity_key(o)) is not None}
    ids_a, ids_b = set(by_id_a), set(by_id_b)

    appeared = sorted(ids_b - ids_a)
    disappeared = sorted(ids_a - ids_b)
    changed = sorted(
        asset_id
        for asset_id in ids_a & ids_b
        if (
            by_id_a[asset_id].get("metadata", {}).get("runtime_state")
            != by_id_b[asset_id].get("metadata", {}).get("runtime_state")
        )
        or by_id_a[asset_id].get("screen_bounds") != by_id_b[asset_id].get("screen_bounds")
    )
    return SnapshotDiff(appeared=appeared, disappeared=disappeared, changed=changed)
