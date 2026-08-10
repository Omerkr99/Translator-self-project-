import pytest

import gcrts.render_paths as render_paths
from gcrts.render_paths import (
    DialogueAdapter,
    KNOWN_TEXT_TYPES,
    UnimplementedAdapter,
    coverage_report,
    extract_units_for,
    register_adapter,
)


def test_dialogue_is_the_only_implemented_adapter():
    report = {row["text_type"]: row["implemented"] for row in coverage_report()}
    assert report["dialogue"] is True
    for text_type in ("menu", "system_prompt", "status_overlay", "chapter_title", "speaker_label"):
        assert report[text_type] is False


def test_unimplemented_adapter_raises_with_research_pointer():
    adapter = UnimplementedAdapter("menu")
    with pytest.raises(NotImplementedError, match="Research"):
        adapter.extract("scene_x")


def test_speaker_label_stub_carries_its_research_notes_in_coverage_report():
    report = {row["text_type"]: row for row in coverage_report()}
    assert "speaker_name_start" in report["speaker_label"]["notes"]


def test_extract_units_for_unknown_type_raises_keyerror():
    with pytest.raises(KeyError):
        extract_units_for("some_made_up_type", "scene_x")


def test_extract_units_for_stub_type_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        extract_units_for("menu", "scene_x")


def test_extract_units_for_dialogue_delegates_to_extract_live_script_units(monkeypatch):
    captured = {}

    def fake_extract(scene_id, host="127.0.0.1", port=3333, text_type="dialogue"):
        captured["scene_id"] = scene_id
        captured["host"] = host
        captured["port"] = port
        captured["text_type"] = text_type
        return ["fake-unit"]

    monkeypatch.setattr(render_paths, "extract_live_script_units", fake_extract)

    result = extract_units_for("dialogue", "scene_x", host="1.2.3.4", port=9999)

    assert result == ["fake-unit"]
    assert captured == {"scene_id": "scene_x", "host": "1.2.3.4", "port": 9999, "text_type": "dialogue"}


def test_register_adapter_replaces_a_stub_and_updates_coverage():
    class FakeMenuAdapter:
        text_type = "menu"

        def extract(self, scene_id, host="127.0.0.1", port=3333):
            return ["menu-unit"]

    original = KNOWN_TEXT_TYPES["menu"]
    try:
        register_adapter(FakeMenuAdapter())
        report = {row["text_type"]: row["implemented"] for row in coverage_report()}
        assert report["menu"] is True
        assert extract_units_for("menu", "scene_x") == ["menu-unit"]
    finally:
        register_adapter(original)  # restore the stub so other tests see the original state


def test_register_adapter_can_add_a_wholly_new_text_type():
    class FakeCreditsAdapter:
        text_type = "credits"

        def extract(self, scene_id, host="127.0.0.1", port=3333):
            return ["credits-unit"]

    assert "credits" not in KNOWN_TEXT_TYPES
    try:
        register_adapter(FakeCreditsAdapter())
        assert extract_units_for("credits", "scene_x") == ["credits-unit"]
    finally:
        del KNOWN_TEXT_TYPES["credits"]
