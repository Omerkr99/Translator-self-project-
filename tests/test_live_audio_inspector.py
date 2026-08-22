from gcrts.audio_asset_resolver import AudioAssetResolution, ResolutionConfidence
from gcrts.dialogue_database import DialogueWorkflowStatus, get_entry, save_entry
from gcrts.live_audio_inspector import (
    fandub_template_path_for_asset,
    format_now_playing,
    inspect_live_audio,
)
from gcrts.runtime_audio import AudioConfidence, AudioLifecycleState, RuntimeAudioEvent
from gcrts.semantic_label_store import save_label
from gcrts.audio_semantic import SemanticType, VerificationSource
from gcrts.xapack import AudioAsset, StreamConfidence, format_from_coding_info


def _event(start_lba=126921, state=AudioLifecycleState.PLAYING):
    return RuntimeAudioEvent(
        event_id="current", source_type="voice", script_parameter=127, audio_category=2,
        source_file="DAT/XA1/XAPACK08.BIN", xa_channel=7, start_lba=start_lba,
        resolution_method="live_lba", position_counter=start_lba, position_counter_start=start_lba,
        playback_offset_ms=None, state=state, confidence=AudioConfidence.LIVE_LBA_RESOLVED,
    )


def _asset(pack_path="DAT/XA1/XAPACK08.BIN", channel_number=7):
    fmt = format_from_coding_info(1)
    return AudioAsset(pack_path, channel_number, 126225, 129273, 382, fmt, 20.37, StreamConfidence.LIVE_CROSS_VALIDATED)


def _matched_resolver(asset):
    def resolve(disc_bytes, live_lba):
        return AudioAssetResolution(asset=asset, confidence=ResolutionConfidence.LIVE_LBA_MATCHED, evidence="stub", live_lba=live_lba)
    return resolve


def _unresolved_resolver():
    def resolve(disc_bytes, live_lba):
        return AudioAssetResolution(asset=None, confidence=ResolutionConfidence.UNRESOLVED, evidence="stub", live_lba=live_lba)
    return resolve


# --- inspect_live_audio: nothing to inspect --------------------------------


def test_inspect_live_audio_none_event_returns_none():
    assert inspect_live_audio(None, b"disc", resolve_fn=_matched_resolver(_asset())) is None


def test_inspect_live_audio_none_disc_bytes_returns_none():
    assert inspect_live_audio(_event(), None, resolve_fn=_matched_resolver(_asset())) is None


def test_inspect_live_audio_no_start_lba_returns_none():
    event = _event(start_lba=None)
    assert inspect_live_audio(event, b"disc", resolve_fn=_matched_resolver(_asset())) is None


# --- unresolved LBA: still a real, reportable result -----------------------


def test_inspect_live_audio_unresolved_lba_reports_no_asset_but_real_state(tmp_path):
    db_path = str(tmp_path / "db.json")
    inspection = inspect_live_audio(_event(), b"disc", db_path=db_path, resolve_fn=_unresolved_resolver())
    assert inspection is not None
    assert inspection.asset_id is None
    assert inspection.resolution_confidence == ResolutionConfidence.UNRESOLVED
    assert inspection.lifecycle_state == AudioLifecycleState.PLAYING
    assert inspection.database_entry is None
    assert inspection.newly_registered is False


# --- new asset: auto-registered as a real DETECTED entry -------------------


def test_inspect_live_audio_registers_new_asset(tmp_path):
    db_path = str(tmp_path / "db.json")
    label_path = str(tmp_path / "labels.json")
    asset = _asset()
    inspection = inspect_live_audio(_event(), b"disc", db_path=db_path, label_store_path=label_path, resolve_fn=_matched_resolver(asset))
    assert inspection.asset_id == "XAPACK08:7"
    assert inspection.newly_registered is True
    assert inspection.database_entry is not None
    assert inspection.database_entry.workflow_status == DialogueWorkflowStatus.DETECTED
    # actually persisted, not just returned
    assert get_entry("XAPACK08:7", path=db_path) is not None


def test_inspect_live_audio_auto_register_false_leaves_no_entry(tmp_path):
    db_path = str(tmp_path / "db.json")
    asset = _asset()
    inspection = inspect_live_audio(_event(), b"disc", db_path=db_path, auto_register=False, resolve_fn=_matched_resolver(asset))
    assert inspection.asset_id == "XAPACK08:7"
    assert inspection.newly_registered is False
    assert inspection.database_entry is None
    assert get_entry("XAPACK08:7", path=db_path) is None


# --- existing asset: read, never silently overwritten ----------------------


def test_inspect_live_audio_never_overwrites_existing_entry(tmp_path):
    """Regression for the exact failure this module's own docstring
    warns about: a human-added evidence/notes on an existing entry
    must survive repeated live polling, not get silently wiped by a
    freshly rebuilt entry."""
    db_path = str(tmp_path / "db.json")
    label_path = str(tmp_path / "labels.json")
    asset = _asset()
    inspect_live_audio(_event(), b"disc", db_path=db_path, label_store_path=label_path, resolve_fn=_matched_resolver(asset))  # first poll registers it
    entry = get_entry("XAPACK08:7", path=db_path)
    entry.evidence.append("A human added this real evidence line by hand.")
    save_entry(entry, path=db_path)

    inspection = inspect_live_audio(_event(), b"disc", db_path=db_path, label_store_path=label_path, resolve_fn=_matched_resolver(asset))  # second poll
    assert inspection.newly_registered is False
    assert inspection.database_entry.evidence == ["A human added this real evidence line by hand."]


def test_inspect_live_audio_reflects_confirmed_label(tmp_path):
    db_path = str(tmp_path / "db.json")
    label_path = str(tmp_path / "labels.json")
    asset = _asset()
    save_label("XAPACK08:7", SemanticType.DIALOGUE, VerificationSource.USER_LISTENING, "heard it", path=label_path)
    inspection = inspect_live_audio(_event(), b"disc", db_path=db_path, label_store_path=label_path, resolve_fn=_matched_resolver(asset))
    assert inspection.database_entry.semantic_type == SemanticType.DIALOGUE
    assert inspection.database_entry.semantic_confirmed is True


# --- format_now_playing -----------------------------------------------------


def test_format_now_playing_no_data():
    assert format_now_playing(None) == "NOW PLAYING: (no live audio data)"


def test_format_now_playing_unresolved(tmp_path):
    db_path = str(tmp_path / "db.json")
    inspection = inspect_live_audio(_event(), b"disc", db_path=db_path, resolve_fn=_unresolved_resolver())
    text = format_now_playing(inspection)
    assert "unresolved" in text.lower() or "UNRESOLVED" in text
    assert "PLAYING" in text


def test_format_now_playing_confirmed_asset(tmp_path):
    db_path = str(tmp_path / "db.json")
    label_path = str(tmp_path / "labels.json")
    asset = _asset()
    save_label("XAPACK08:7", SemanticType.DIALOGUE, VerificationSource.USER_LISTENING, "heard it", path=label_path)
    inspection = inspect_live_audio(_event(), b"disc", db_path=db_path, label_store_path=label_path, resolve_fn=_matched_resolver(asset))
    text = format_now_playing(inspection)
    assert "XAPACK08:7" in text
    assert "DIALOGUE" in text
    assert "DETECTED" in text


def test_format_now_playing_unconfirmed_asset_marked_with_question_mark(tmp_path):
    db_path = str(tmp_path / "db.json")
    label_path = str(tmp_path / "labels.json")  # deliberately empty -- must not fall back to the real project label store
    asset = _asset()
    inspection = inspect_live_audio(_event(), b"disc", db_path=db_path, label_store_path=label_path, resolve_fn=_matched_resolver(asset))
    text = format_now_playing(inspection)
    assert "UNKNOWN?" in text  # unconfirmed semantic type is flagged, not presented as fact


# --- fandub_template_path_for_asset -----------------------------------------


def test_fandub_template_path_for_asset_replaces_colon():
    path = fandub_template_path_for_asset("XAPACK22:7")
    assert path.replace("\\", "/") == "audio_export/fandub/XAPACK22_7/template.json"
