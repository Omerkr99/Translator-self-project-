from gcrts.screen_objects import (
    InspectableScreenObject,
    MappingConfidence,
    ScreenBounds,
    ScreenObjectType,
    TextRepresentation,
    TranslationStatus,
    renderer_1_object,
)
from gcrts.visual_inspector_ui import object_color, object_status_label

_BLUE = "#00bfff"
_CYAN = "#00e5ff"
_YELLOW = "#ffd000"
_GRAY = "#888888"


def _image_asset(confidence=MappingConfidence.LIVE_VERIFIED):
    return InspectableScreenObject(
        "a", "A", ScreenObjectType.IMAGE_ASSET, ScreenBounds(0, 0, 1, 1),
        {"kind": "DISC_ASSET"}, {"type": "ASSET_INSPECTOR"}, confidence,
    )


def test_live_image_asset_is_blue():
    assert object_color(_image_asset()) == _BLUE
    assert object_status_label(_image_asset()) == "LIVE"


def test_live_renderer1_text_is_cyan():
    obj = renderer_1_object(id="x", name="X", bounds=ScreenBounds(0, 0, 1, 1), script_unit="u", line_index=0, profile_valid=True)
    assert object_color(obj) == _CYAN
    assert object_status_label(obj) == "R1-LIVE"


def test_candidate_is_yellow():
    obj = _image_asset(confidence=MappingConfidence.CANDIDATE)
    assert object_color(obj) == _YELLOW
    assert object_status_label(obj) == "CANDIDATE"


def test_unknown_region_is_yellow_even_without_candidate_confidence():
    obj = InspectableScreenObject("u", "U", ScreenObjectType.UNKNOWN_REGION, ScreenBounds(0, 0, 1, 1), {"kind": "UNKNOWN"}, {"type": "MAPPING_INVESTIGATION"}, MappingConfidence.UNKNOWN)
    assert object_color(obj) == _YELLOW
    assert object_status_label(obj) == "UNKNOWN"


def test_manual_verified_asset_is_gray_not_blue():
    """A manual mapping is never colored the same as a live runtime
    confirmation, even for the same object type -- color must encode
    SOURCE, not just type."""
    obj = _image_asset(confidence=MappingConfidence.MANUAL_VERIFIED)
    assert object_color(obj) == _GRAY
    assert object_status_label(obj) == "MANUAL"


def test_stale_renderer1_profile_is_not_cyan():
    """A Renderer 1 object whose profile didn't validate must not read as
    live-confirmed -- renderer_1_object() demotes confidence when
    profile_valid=False, so it must fall through to non-cyan coloring."""
    obj = renderer_1_object(id="x", name="X", bounds=ScreenBounds(0, 0, 1, 1), script_unit="u", line_index=0, profile_valid=False)
    assert object_color(obj) != _CYAN
