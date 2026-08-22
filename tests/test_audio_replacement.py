import pytest

from gcrts.audio_replacement import (
    FandubEntry,
    ReplacementValidationStatus,
    create_fandub_template,
    load_fandub_template,
    save_fandub_template,
    scaffold_fandub_project,
    validate_replacement,
)
from gcrts.audio_semantic import SemanticType, VerificationSource
from gcrts.semantic_label_store import save_label
from gcrts.xapack import AudioAsset, StreamConfidence, format_from_coding_info


def _asset():
    fmt = format_from_coding_info(1)
    return AudioAsset("DAT/XA1/XAPACK08.BIN", 7, 126225, 129273, 382, fmt, 20.373333333333335, StreamConfidence.LIVE_CROSS_VALIDATED)


# --- create_fandub_template ---------------------------------------------------


def test_create_fandub_template_prefills_only_original_fields():
    template = create_fandub_template(_asset())
    assert template.original_asset_id == "XAPACK08:7"
    assert template.original_pack_path == "DAT/XA1/XAPACK08.BIN"
    assert template.original_channel_number == 7
    assert template.original_sample_rate_hz == 37800
    assert template.original_channels == 2
    assert template.japanese_transcript is None
    assert template.translation is None
    assert template.replacement_file is None
    assert template.validation_status == ReplacementValidationStatus.NOT_STARTED


def test_create_fandub_template_custom_language():
    template = create_fandub_template(_asset(), language="fr")
    assert template.replacement_language == "fr"


# --- save/load round trip ------------------------------------------------------


def test_save_and_load_fandub_template_round_trips(tmp_path):
    template = create_fandub_template(_asset())
    template.translation = "Hello there"
    template.speaker = "Narrator"
    path = str(tmp_path / "template.json")
    save_fandub_template(template, path)

    loaded = load_fandub_template(path)
    assert loaded.original_asset_id == template.original_asset_id
    assert loaded.translation == "Hello there"
    assert loaded.speaker == "Narrator"


# --- validate_replacement -------------------------------------------------------


def test_validate_replacement_ready_for_encode_when_all_checks_pass():
    template = create_fandub_template(_asset())
    result = validate_replacement(template, 21.0, 37800, 2, peak_amplitude=15000, silence_ratio=0.1)
    assert result.validation_status == ReplacementValidationStatus.READY_FOR_ENCODE
    assert result.replacement_duration_seconds == 21.0


def test_validate_replacement_duration_mismatch():
    template = create_fandub_template(_asset())
    result = validate_replacement(template, 40.0, 37800, 2, peak_amplitude=15000, silence_ratio=0.1)
    assert result.validation_status == ReplacementValidationStatus.DURATION_MISMATCH


def test_validate_replacement_format_mismatch_takes_priority():
    """Format mismatch is checked first -- a replacement in the wrong
    format shouldn't be reported as a duration problem instead."""
    template = create_fandub_template(_asset())
    result = validate_replacement(template, 40.0, 44100, 1, peak_amplitude=15000, silence_ratio=0.1)
    assert result.validation_status == ReplacementValidationStatus.FORMAT_MISMATCH


def test_validate_replacement_clipping_detected():
    template = create_fandub_template(_asset())
    result = validate_replacement(template, 20.0, 37800, 2, peak_amplitude=32767, silence_ratio=0.1)
    assert result.validation_status == ReplacementValidationStatus.CLIPPING_DETECTED


def test_validate_replacement_silence_detected():
    template = create_fandub_template(_asset())
    result = validate_replacement(template, 20.0, 37800, 2, peak_amplitude=100, silence_ratio=0.95)
    assert result.validation_status == ReplacementValidationStatus.SILENCE_DETECTED


def test_validate_replacement_does_not_mutate_input_entry():
    template = create_fandub_template(_asset())
    validate_replacement(template, 40.0, 37800, 2, peak_amplitude=15000, silence_ratio=0.1)
    assert template.validation_status == ReplacementValidationStatus.NOT_STARTED
    assert template.replacement_duration_seconds is None


# --- scaffold_fandub_project: gated on confirmed semantic label ---------------


def test_scaffold_fandub_project_refuses_unconfirmed_asset(tmp_path):
    label_store = str(tmp_path / "labels.json")  # empty store -- nothing confirmed
    with pytest.raises(ValueError):
        scaffold_fandub_project(_asset(), str(tmp_path / "out"), label_store_path=label_store)


def test_scaffold_fandub_project_succeeds_for_confirmed_asset(tmp_path):
    label_store = str(tmp_path / "labels.json")
    save_label("XAPACK08:7", SemanticType.DIALOGUE, VerificationSource.USER_LISTENING, "sounds like speech", path=label_store)

    out_dir = str(tmp_path / "out")
    path = scaffold_fandub_project(_asset(), out_dir, label_store_path=label_store)
    assert path.endswith("template.json")

    loaded = load_fandub_template(path)
    assert loaded.original_asset_id == "XAPACK08:7"


def test_scaffold_fandub_project_refuses_heuristic_only_confirmation(tmp_path):
    """A bare HEURISTIC candidate guess must never be enough to
    scaffold a translator-facing project -- only USER_LISTENING or
    RUNTIME_EVIDENCE count as confirmed."""
    label_store = str(tmp_path / "labels.json")
    save_label("XAPACK08:7", SemanticType.DIALOGUE, VerificationSource.HEURISTIC, path=label_store)
    with pytest.raises(ValueError):
        scaffold_fandub_project(_asset(), str(tmp_path / "out"), label_store_path=label_store)
