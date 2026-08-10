from gcrts.screen_objects import *

def test_screen_object_serialization_and_hit_testing():
    obj=InspectableScreenObject("x","X",ScreenObjectType.UI_TEXT_ASSET,ScreenBounds(10,20,30,40),{"kind":"DISC_ASSET"},{"type":"ASSET_INSPECTOR"},MappingConfidence.MANUAL_VERIFIED,TextRepresentation.RASTER_TEXT_ASSET,TranslationStatus.ORIGINAL,True)
    restored=InspectableScreenObject.from_dict(obj.to_dict())
    assert restored==obj and restored.hit_test(10,20) and restored.hit_test(39,59) and not restored.hit_test(40,60)

def test_bounds_overlap():
    assert ScreenBounds(0,0,10,10).overlaps(ScreenBounds(9,9,2,2))
    assert not ScreenBounds(0,0,10,10).overlaps(ScreenBounds(10,0,2,2))

def test_screen_context_roundtrip():
    c=ScreenContext("main","Game","system","menu",confidence=MappingConfidence.LIVE_VERIFIED)
    assert ScreenContext.from_dict(c.to_dict())==c

def test_renderer1_stale_profile_falls_back_safely():
    obj=renderer_1_object(id="line",name="Line",bounds=ScreenBounds(1,2,3,4),script_unit="u",line_index=0,profile_valid=False)
    assert obj.confidence==MappingConfidence.UNKNOWN and not obj.editable and not obj.metadata["detection_available"]

def test_renderer2_is_candidate_and_not_editable():
    obj=renderer_2_candidate(id="r2",name="Choice",bounds=ScreenBounds(0,0,1,1))
    assert obj.text_representation==TextRepresentation.RUNTIME_TEXT_RENDERER_2 and not obj.editable
