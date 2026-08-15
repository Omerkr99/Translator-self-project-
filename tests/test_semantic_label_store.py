import pytest

from gcrts.audio_semantic import SemanticType, VerificationSource
from gcrts.semantic_label_store import get_label, is_confirmed, load_labels, save_label


def test_load_labels_missing_file_returns_empty_dict(tmp_path):
    path = str(tmp_path / "does_not_exist.json")
    assert load_labels(path) == {}


def test_save_and_get_label_round_trips(tmp_path):
    path = str(tmp_path / "labels.json")
    saved = save_label("XAPACK08:7", SemanticType.DIALOGUE, VerificationSource.USER_LISTENING, "sounds like speech", path=path)
    assert saved.asset_id == "XAPACK08:7"
    assert saved.verified_at  # a real timestamp was stamped

    loaded = get_label("XAPACK08:7", path=path)
    assert loaded is not None
    assert loaded.semantic_type == SemanticType.DIALOGUE
    assert loaded.verification_source == VerificationSource.USER_LISTENING
    assert loaded.notes == "sounds like speech"


def test_get_label_unknown_asset_returns_none(tmp_path):
    path = str(tmp_path / "labels.json")
    save_label("XAPACK08:7", SemanticType.DIALOGUE, VerificationSource.USER_LISTENING, path=path)
    assert get_label("XAPACK99:0", path=path) is None


def test_save_label_refuses_overwrite_without_explicit_flag(tmp_path):
    path = str(tmp_path / "labels.json")
    save_label("XAPACK08:7", SemanticType.DIALOGUE, VerificationSource.USER_LISTENING, path=path)
    with pytest.raises(ValueError):
        save_label("XAPACK08:7", SemanticType.MUSIC, VerificationSource.USER_LISTENING, path=path)
    # the original label must survive the rejected overwrite attempt
    assert get_label("XAPACK08:7", path=path).semantic_type == SemanticType.DIALOGUE


def test_save_label_allows_overwrite_with_explicit_flag(tmp_path):
    path = str(tmp_path / "labels.json")
    save_label("XAPACK08:7", SemanticType.DIALOGUE, VerificationSource.USER_LISTENING, path=path)
    save_label("XAPACK08:7", SemanticType.MUSIC, VerificationSource.USER_LISTENING, path=path, allow_overwrite=True)
    assert get_label("XAPACK08:7", path=path).semantic_type == SemanticType.MUSIC


def test_multiple_labels_persist_independently(tmp_path):
    path = str(tmp_path / "labels.json")
    save_label("XAPACK08:7", SemanticType.DIALOGUE, VerificationSource.USER_LISTENING, path=path)
    save_label("XAPACK04:6", SemanticType.DIALOGUE, VerificationSource.HEURISTIC, path=path)
    labels = load_labels(path)
    assert set(labels.keys()) == {"XAPACK08:7", "XAPACK04:6"}


def test_is_confirmed_true_for_user_listening_and_runtime_evidence(tmp_path):
    path = str(tmp_path / "labels.json")
    save_label("a", SemanticType.DIALOGUE, VerificationSource.USER_LISTENING, path=path)
    save_label("b", SemanticType.DIALOGUE, VerificationSource.RUNTIME_EVIDENCE, path=path)
    assert is_confirmed("a", path=path) is True
    assert is_confirmed("b", path=path) is True


def test_is_confirmed_false_for_heuristic_or_missing(tmp_path):
    path = str(tmp_path / "labels.json")
    save_label("a", SemanticType.DIALOGUE, VerificationSource.HEURISTIC, path=path)
    assert is_confirmed("a", path=path) is False
    assert is_confirmed("does-not-exist", path=path) is False
