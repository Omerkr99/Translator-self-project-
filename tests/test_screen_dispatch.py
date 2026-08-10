from gcrts.screen_dispatch import dispatch
from gcrts.screen_objects import *

def test_asset_routes_to_asset_inspector():
    o=InspectableScreenObject("a","A",ScreenObjectType.UI_TEXT_ASSET,ScreenBounds(0,0,1,1),{"kind":"DISC_ASSET"},{"type":"ASSET_INSPECTOR","block":7},MappingConfidence.LIVE_VERIFIED,editable=True)
    result=dispatch(o);assert result.target==EditorTargetType.ASSET_INSPECTOR and result.available

def test_renderer1_route_requires_valid_profile():
    stale=renderer_1_object(id="x",name="X",bounds=ScreenBounds(0,0,1,1),script_unit="u",line_index=0,profile_valid=False)
    assert not dispatch(stale).available

def test_unknown_routes_to_mapping_investigation():
    o=InspectableScreenObject("u","U",ScreenObjectType.UNKNOWN_REGION,ScreenBounds(0,0,1,1),{"kind":"UNKNOWN"},{"type":"MAPPING_INVESTIGATION"},MappingConfidence.UNKNOWN)
    assert dispatch(o).target==EditorTargetType.MAPPING_INVESTIGATION
