from gcrts.runtime_audio import AudioConfidence, AudioLifecycleState, RuntimeAudioEvent
from gcrts.runtime_content import RuntimeAssetInstance, RuntimeAssetState, RuntimeConfidence, VramRegion
from gcrts.runtime_snapshot import (
    RuntimeSnapshot,
    capture_runtime_snapshot,
    diff_snapshots,
    load_snapshot,
    save_snapshot,
)
from gcrts.screen_objects import (
    InspectableScreenObject,
    MappingConfidence,
    ScreenBounds,
    ScreenObjectType,
    TextRepresentation,
    TranslationStatus,
    renderer_1_object,
)


def _asset(id_, asset_id, x=0, y=0, state="DRAWN_THIS_FRAME"):
    return InspectableScreenObject(
        id_, id_, ScreenObjectType.IMAGE_ASSET, ScreenBounds(x, y, 10, 10),
        {"kind": "DISC_ASSET", "asset_id": asset_id}, {"type": "ASSET_INSPECTOR"},
        MappingConfidence.LIVE_VERIFIED, TextRepresentation.NOT_TEXT, TranslationStatus.NOT_EDITABLE, True,
        {"runtime_state": state},
    )


class _FakeProvider:
    def __init__(self, instances, last_audio_event=None):
        class _Tracker:
            pass

        self.tracker = _Tracker()
        self.tracker.instances = instances
        self.last_renderer1_validation = "profile_valid"
        self.last_audio_event = last_audio_event


def _audio_event(state=AudioLifecycleState.PLAYING, script_parameter=127, position=118340) -> RuntimeAudioEvent:
    return RuntimeAudioEvent(
        event_id="current",
        source_type="voice",
        script_parameter=script_parameter,
        audio_category=2,
        source_file="DAT/XA1/XAPACK08.BIN",
        xa_channel=7,
        start_lba=126921,
        resolution_method="static_table",
        position_counter=position,
        position_counter_start=position,
        playback_offset_ms=None,
        state=state,
        confidence=AudioConfidence.STATIC_LOOKUP,
    )


def test_capture_runtime_snapshot_carries_objects_and_tracker_state():
    instance = RuntimeAssetInstance(
        runtime_instance_id="session:1", asset_id="main_menu.start", state=RuntimeAssetState.DRAWN_THIS_FRAME,
        confidence=RuntimeConfidence.LIVE_EXACT_SOURCE, created_frame=1, last_transition_frame=1,
    )
    instance.vram_regions.append(VramRegion(10, 20, 30, 40, "4bpp", generation=1))
    provider = _FakeProvider({"session:1": instance})
    objects = [_asset("runtime:main_menu.start:0:0", "main_menu.start")]

    snapshot = capture_runtime_snapshot(provider, frame=123, objects=objects)

    assert snapshot.snapshot_id == 123
    assert snapshot.active_asset_ids == {"main_menu.start"}
    assert snapshot.tracker_instances[0]["asset_id"] == "main_menu.start"
    assert snapshot.tracker_instances[0]["vram_regions"][0]["x"] == 10
    assert snapshot.renderer1_validation == "profile_valid"
    # active_movie is still an always-empty future placeholder; active_audio
    # is populated from provider.last_audio_event when present (see the
    # dedicated audio tests below) -- this fake provider has none, so it's
    # correctly empty here too, not because the field is inert.
    assert snapshot.active_movie is None and snapshot.active_audio == []


def test_snapshot_round_trips_through_json(tmp_path):
    provider = _FakeProvider({})
    objects = [_asset("a", "main_menu.start"), _asset("b", "category.photos")]
    snapshot = capture_runtime_snapshot(provider, frame=7, objects=objects)

    path = tmp_path / "snap.json"
    save_snapshot(snapshot, path)
    restored = load_snapshot(path)

    assert restored.snapshot_id == 7
    assert restored.active_asset_ids == {"main_menu.start", "category.photos"}
    assert restored == snapshot


def test_snapshot_inspectable_without_provider_after_save():
    """The whole point of 6.1: a saved snapshot is a plain dict-of-data,
    readable with nothing but the file -- no provider/connection object
    needed at read time."""
    provider = _FakeProvider({})
    snapshot = capture_runtime_snapshot(provider, frame=1, objects=[_asset("a", "main_menu.start")])
    d = snapshot.to_dict()
    assert isinstance(d, dict)
    reloaded = RuntimeSnapshot.from_dict(d)
    assert reloaded.active_asset_ids == {"main_menu.start"}


def test_diff_detects_appeared_disappeared_and_changed():
    provider = _FakeProvider({})
    a = capture_runtime_snapshot(
        provider, frame=1,
        objects=[_asset("s", "main_menu.start"), _asset("p", "main_menu.prepare")],
    )
    b = capture_runtime_snapshot(
        provider, frame=2,
        objects=[_asset("s", "main_menu.start", x=99), _asset("c", "category.photos")],
    )

    diff = diff_snapshots(a, b)

    assert diff.appeared == ["category.photos"]
    assert diff.disappeared == ["main_menu.prepare"]
    assert diff.changed == ["main_menu.start"]  # same asset, moved bounds
    assert not diff.is_empty


def test_diff_of_identical_snapshots_is_empty():
    provider = _FakeProvider({})
    a = capture_runtime_snapshot(provider, frame=1, objects=[_asset("s", "main_menu.start")])
    b = capture_runtime_snapshot(provider, frame=2, objects=[_asset("s", "main_menu.start")])

    diff = diff_snapshots(a, b)

    assert diff.is_empty


def test_renderer1_objects_are_tracked_by_identity_despite_having_no_asset_id():
    """Regression test for a real bug caught live (not by the earlier,
    asset-only unit tests): Renderer 1 objects have no `source.asset_id`
    at all, so an identity function keyed only on asset_id silently
    dropped every Renderer 1 line from diffing -- appeared/disappeared
    could never report dialogue text, only assets."""
    provider = _FakeProvider({})
    line = renderer_1_object(id="r1", name="Line", bounds=ScreenBounds(26, 152, 100, 16), script_unit="unknown", line_index=0, profile_valid=True)

    dialogue = capture_runtime_snapshot(provider, frame=1, objects=[line])
    assert dialogue.active_asset_ids == {"renderer1:line0"}

    menu = capture_runtime_snapshot(provider, frame=2, objects=[_asset("s", "main_menu.start")])
    diff = diff_snapshots(dialogue, menu)

    assert diff.disappeared == ["renderer1:line0"]
    assert diff.appeared == ["main_menu.start"]


# --- Runtime Audio Tracker integration -----------------------------------


def test_snapshot_includes_active_audio_when_playing():
    provider = _FakeProvider({}, last_audio_event=_audio_event(state=AudioLifecycleState.PLAYING))
    snapshot = capture_runtime_snapshot(provider, frame=1, objects=[])
    assert len(snapshot.active_audio) == 1
    assert snapshot.active_audio[0]["source_file"] == "DAT/XA1/XAPACK08.BIN"
    assert snapshot.active_audio[0]["xa_channel"] == 7
    assert snapshot.active_audio[0]["state"] == "PLAYING"


def test_snapshot_includes_active_audio_when_starting():
    provider = _FakeProvider({}, last_audio_event=_audio_event(state=AudioLifecycleState.STARTING))
    snapshot = capture_runtime_snapshot(provider, frame=1, objects=[])
    assert len(snapshot.active_audio) == 1


def test_snapshot_does_not_report_stopped_audio_as_active():
    """Per the milestone's own instruction: do not retain stale finished
    audio as currently active."""
    provider = _FakeProvider({}, last_audio_event=_audio_event(state=AudioLifecycleState.STOPPED))
    snapshot = capture_runtime_snapshot(provider, frame=1, objects=[])
    assert snapshot.active_audio == []


def test_snapshot_does_not_report_unknown_audio_as_active():
    provider = _FakeProvider({}, last_audio_event=_audio_event(state=AudioLifecycleState.UNKNOWN))
    snapshot = capture_runtime_snapshot(provider, frame=1, objects=[])
    assert snapshot.active_audio == []


def test_snapshot_active_audio_empty_when_provider_has_no_audio_event():
    provider = _FakeProvider({}, last_audio_event=None)
    snapshot = capture_runtime_snapshot(provider, frame=1, objects=[])
    assert snapshot.active_audio == []


def test_snapshot_extraction_status_not_ready_without_stream_source():
    """Audio Event Isolation milestone: no live-verified AudioStreamSource
    means no confirmed start LBA, so extraction is NOT_READY -- never
    silently upgraded to a higher readiness state."""
    provider = _FakeProvider({}, last_audio_event=_audio_event(state=AudioLifecycleState.PLAYING))
    snapshot = capture_runtime_snapshot(provider, frame=1, objects=[])
    assert snapshot.active_audio[0]["extraction_status"] == "NOT_READY"


def test_snapshot_extraction_status_never_defaults_to_ready():
    """Even with a live-verified stream source giving a start LBA, this
    project's own finding (the historical Setfilter is not proven
    event-specific) means extraction_status must NOT silently reach
    READY or CHANNEL_CONFIRMED without an explicitly-supplied,
    event-specific file/channel -- only START_CONFIRMED at most."""
    from gcrts.audio_stream_source import AudioStreamConfidence, AudioStreamSource

    provider = _FakeProvider({}, last_audio_event=_audio_event(state=AudioLifecycleState.PLAYING))
    provider.last_audio_stream_source = AudioStreamSource(
        source_id="s", descriptor_ptr=0x800A60EC, file_start_lba=126218,
        file_start_lba_matches_disc=True, matched_disc_path="DAT/XA1/XAPACK08.BIN",
        field_0x08_value=129542, field_0x14_value=131841,
        confidence=AudioStreamConfidence.LIVE_VERIFIED, resolution_note="matches",
    )
    snapshot = capture_runtime_snapshot(provider, frame=1, objects=[])
    assert snapshot.active_audio[0]["extraction_status"] == "START_CONFIRMED"


def test_active_audio_round_trips_through_saved_snapshot(tmp_path):
    provider = _FakeProvider({}, last_audio_event=_audio_event())
    snapshot = capture_runtime_snapshot(provider, frame=1, objects=[])
    path = tmp_path / "with_audio.json"
    save_snapshot(snapshot, path)

    loaded = load_snapshot(path)
    assert loaded.active_audio == snapshot.active_audio
    assert loaded.active_audio[0]["script_parameter"] == 127
