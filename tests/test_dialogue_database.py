import pytest

from gcrts.audio_replacement import create_fandub_template, save_fandub_template
from gcrts.audio_semantic import SemanticType, VerificationSource
from gcrts.dialogue_database import (
    DialogueDatabaseEntry,
    DialogueWorkflowStatus,
    add_evidence,
    build_entry_from_asset,
    compute_workflow_status,
    dashboard_summary,
    get_entry,
    list_by_semantic_type,
    list_by_status,
    load_database,
    save_entry,
)
from gcrts.semantic_label_store import save_label
from gcrts.xapack import AudioAsset, StreamConfidence, format_from_coding_info


def _asset(asset_id_channel=7):
    fmt = format_from_coding_info(1)
    return AudioAsset("DAT/XA1/XAPACK08.BIN", asset_id_channel, 126225, 129273, 382, fmt, 20.37, StreamConfidence.LIVE_CROSS_VALIDATED)


def _bare_entry(**overrides):
    defaults = dict(
        asset_id="TEST:0", pack_path="p", channel_number=0,
        duration_seconds=5.0, sample_rate_hz=37800, channels=2,
    )
    defaults.update(overrides)
    return DialogueDatabaseEntry(**defaults)


# --- compute_workflow_status: never jumps ahead of real data ------------------


def test_compute_workflow_status_detected_by_default():
    assert compute_workflow_status(_bare_entry()) == DialogueWorkflowStatus.DETECTED


def test_compute_workflow_status_transcript_added():
    entry = _bare_entry(japanese_transcript="こんにちは")
    assert compute_workflow_status(entry) == DialogueWorkflowStatus.TRANSCRIPT_ADDED


def test_compute_workflow_status_transcript_verified():
    entry = _bare_entry(japanese_transcript="こんにちは", transcript_verified=True)
    assert compute_workflow_status(entry) == DialogueWorkflowStatus.TRANSCRIPT_VERIFIED


def test_compute_workflow_status_translation_draft_even_if_transcript_unverified():
    entry = _bare_entry(japanese_transcript="こんにちは", translation="Hello")
    assert compute_workflow_status(entry) == DialogueWorkflowStatus.TRANSLATION_DRAFT


def test_compute_workflow_status_translation_approved_requires_flag():
    entry = _bare_entry(japanese_transcript="a", translation="b", translation_approved=False)
    assert compute_workflow_status(entry) == DialogueWorkflowStatus.TRANSLATION_DRAFT
    entry.translation_approved = True
    assert compute_workflow_status(entry) == DialogueWorkflowStatus.TRANSLATION_APPROVED


def test_compute_workflow_status_ready_for_recording_requires_both_verified_and_approved():
    entry = _bare_entry(japanese_transcript="a", translation="b", translation_approved=True, transcript_verified=True)
    assert compute_workflow_status(entry) == DialogueWorkflowStatus.READY_FOR_RECORDING


def test_compute_workflow_status_does_not_regress_past_recorded():
    """Once an entry is manually marked RECORDED (an external action
    this module can't infer), recomputing must not silently demote it
    back to a translation-only status."""
    entry = _bare_entry(japanese_transcript="a", translation="b", workflow_status=DialogueWorkflowStatus.RECORDED)
    assert compute_workflow_status(entry) == DialogueWorkflowStatus.RECORDED


# --- build_entry_from_asset ----------------------------------------------------


def test_build_entry_from_asset_unconfirmed_has_unknown_semantic_type(tmp_path):
    label_store = str(tmp_path / "labels.json")
    entry = build_entry_from_asset(_asset(), label_store_path=label_store)
    assert entry.semantic_type == SemanticType.UNKNOWN
    assert entry.semantic_confirmed is False
    assert entry.workflow_status == DialogueWorkflowStatus.DETECTED


def test_build_entry_from_asset_confirmed_label_reflected(tmp_path):
    label_store = str(tmp_path / "labels.json")
    save_label("XAPACK08:7", SemanticType.DIALOGUE, VerificationSource.USER_LISTENING, "heard it", path=label_store)
    entry = build_entry_from_asset(_asset(), label_store_path=label_store)
    assert entry.semantic_type == SemanticType.DIALOGUE
    assert entry.semantic_confirmed is True


def test_build_entry_from_asset_heuristic_only_label_not_confirmed(tmp_path):
    label_store = str(tmp_path / "labels.json")
    save_label("XAPACK08:7", SemanticType.DIALOGUE, VerificationSource.HEURISTIC, path=label_store)
    entry = build_entry_from_asset(_asset(), label_store_path=label_store)
    assert entry.semantic_type == SemanticType.DIALOGUE
    assert entry.semantic_confirmed is False  # HEURISTIC alone is never "confirmed"


def test_build_entry_from_asset_pulls_fandub_template_fields(tmp_path):
    label_store = str(tmp_path / "labels.json")
    template = create_fandub_template(_asset())
    template.speaker = "Yukari"
    template.japanese_transcript = "あ、そうだ"
    template.translation = "Oh, right."
    template_path = str(tmp_path / "template.json")
    save_fandub_template(template, template_path)

    entry = build_entry_from_asset(_asset(), label_store_path=label_store, fandub_template_path=template_path)
    assert entry.character == "Yukari"
    assert entry.japanese_transcript == "あ、そうだ"
    assert entry.translation == "Oh, right."
    assert entry.workflow_status == DialogueWorkflowStatus.TRANSLATION_DRAFT


def test_build_entry_from_asset_no_template_file_leaves_fields_empty(tmp_path):
    entry = build_entry_from_asset(_asset(), fandub_template_path=str(tmp_path / "does_not_exist.json"))
    assert entry.japanese_transcript is None
    assert entry.character is None


# --- save/load/get round trip --------------------------------------------------


def test_save_and_get_entry_round_trips(tmp_path):
    path = str(tmp_path / "db.json")
    entry = _bare_entry(asset_id="XAPACK08:7")
    save_entry(entry, path=path)
    loaded = get_entry("XAPACK08:7", path=path)
    assert loaded is not None
    assert loaded.asset_id == "XAPACK08:7"


def test_get_entry_missing_returns_none(tmp_path):
    path = str(tmp_path / "db.json")
    assert get_entry("NOPE:0", path=path) is None


def test_save_entry_recomputes_workflow_status(tmp_path):
    path = str(tmp_path / "db.json")
    entry = _bare_entry(japanese_transcript="a", workflow_status=DialogueWorkflowStatus.DETECTED)
    saved = save_entry(entry, path=path)
    assert saved.workflow_status == DialogueWorkflowStatus.TRANSCRIPT_ADDED


# --- add_evidence ---------------------------------------------------------------


def test_add_evidence_appends_to_existing_entry(tmp_path):
    path = str(tmp_path / "db.json")
    save_entry(_bare_entry(asset_id="XAPACK08:7"), path=path)
    add_evidence("XAPACK08:7", "Live LBA capture confirmed this asset.", path=path)
    entry = get_entry("XAPACK08:7", path=path)
    assert entry.evidence == ["Live LBA capture confirmed this asset."]


def test_add_evidence_accumulates_multiple_lines(tmp_path):
    path = str(tmp_path / "db.json")
    save_entry(_bare_entry(asset_id="XAPACK08:7"), path=path)
    add_evidence("XAPACK08:7", "first", path=path)
    add_evidence("XAPACK08:7", "second", path=path)
    entry = get_entry("XAPACK08:7", path=path)
    assert entry.evidence == ["first", "second"]


def test_add_evidence_raises_for_missing_entry(tmp_path):
    path = str(tmp_path / "db.json")
    with pytest.raises(KeyError):
        add_evidence("NOPE:0", "evidence", path=path)


# --- query helpers ---------------------------------------------------------------


def test_list_by_status(tmp_path):
    path = str(tmp_path / "db.json")
    save_entry(_bare_entry(asset_id="A:0"), path=path)
    save_entry(_bare_entry(asset_id="B:0", japanese_transcript="x"), path=path)
    detected = list_by_status(DialogueWorkflowStatus.DETECTED, path=path)
    transcript_added = list_by_status(DialogueWorkflowStatus.TRANSCRIPT_ADDED, path=path)
    assert [e.asset_id for e in detected] == ["A:0"]
    assert [e.asset_id for e in transcript_added] == ["B:0"]


def test_list_by_semantic_type(tmp_path):
    path = str(tmp_path / "db.json")
    save_entry(_bare_entry(asset_id="A:0", semantic_type=SemanticType.DIALOGUE), path=path)
    save_entry(_bare_entry(asset_id="B:0", semantic_type=SemanticType.MUSIC), path=path)
    dialogue = list_by_semantic_type(SemanticType.DIALOGUE, path=path)
    assert [e.asset_id for e in dialogue] == ["A:0"]


# --- dashboard_summary -----------------------------------------------------------


def test_dashboard_summary_counts(tmp_path):
    path = str(tmp_path / "db.json")
    save_entry(_bare_entry(asset_id="A:0", semantic_type=SemanticType.DIALOGUE, semantic_confirmed=True), path=path)
    save_entry(_bare_entry(asset_id="B:0", semantic_type=SemanticType.MUSIC, japanese_transcript="x"), path=path)

    summary = dashboard_summary(path=path)
    assert summary["total_assets"] == 2
    assert summary["confirmed_semantic_labels"] == 1
    assert summary["by_status"]["DETECTED"] == 1
    assert summary["by_status"]["TRANSCRIPT_ADDED"] == 1
    assert summary["by_semantic_type"]["DIALOGUE"] == 1
    assert summary["by_semantic_type"]["MUSIC"] == 1


def test_dashboard_summary_empty_database(tmp_path):
    path = str(tmp_path / "db.json")
    summary = dashboard_summary(path=path)
    assert summary["total_assets"] == 0
    assert summary["by_status"] == {}
