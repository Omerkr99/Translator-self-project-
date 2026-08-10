from pathlib import Path
import pytest
from gcrts.screen_mapping_registry import ScreenMappingRegistry
from gcrts.screen_objects import *

ROOT=Path(__file__).parents[1]

def object_(id="a",kind="DISC_ASSET"):
    return InspectableScreenObject(id,id,ScreenObjectType.UI_TEXT_ASSET,ScreenBounds(10,20,30,40),{"kind":kind},{"type":"ASSET_INSPECTOR"},MappingConfidence.MANUAL_VERIFIED,TextRepresentation.RASTER_TEXT_ASSET,TranslationStatus.ORIGINAL,True)

def test_mapping_persistence_and_crud(tmp_path):
    r=ScreenMappingRegistry();r.add_context(ScreenContext("c","g","x","s"));r.upsert("c",object_());path=tmp_path/"map.json";r.save(path);loaded=ScreenMappingRegistry.load(path)
    assert loaded.list_objects("c")[0].id=="a"
    loaded.upsert("c",object_("a"));assert len(loaded.list_objects("c"))==1
    loaded.delete("c","a");assert loaded.list_objects("c")==[]

def test_hit_testing_returns_overlapping_objects():
    r=ScreenMappingRegistry([ScreenContext("c","g","x","s")],{"c":[object_()]})
    assert r.hit_test("c",15,25)[0].id=="a" and r.hit_test("c",0,0)==[]

def test_small_foreground_object_wins_over_composite_background():
    background=InspectableScreenObject("bg","BG",ScreenObjectType.COMPOSITE_IMAGE_ASSET,ScreenBounds(0,0,320,240),{"kind":"DISC_ASSET"},{"type":"ASSET_INSPECTOR"},MappingConfidence.LIVE_VERIFIED,editable=True)
    r=ScreenMappingRegistry([ScreenContext("c","g","x","s")],{"c":[object_(),background]})
    assert r.hit_test("c",15,25)[0].id=="a"

def test_translation_view_filters_non_text():
    background=InspectableScreenObject("bg","BG",ScreenObjectType.IMAGE_ASSET,ScreenBounds(0,0,1,1),{"kind":"DISC_ASSET"},{"type":"ASSET_INSPECTOR"},MappingConfidence.MANUAL_VERIFIED)
    r=ScreenMappingRegistry([ScreenContext("c","g","x","s")],{"c":[background,object_()]})
    assert [o.id for o in r.filtered("c",text_only=True)]==["a"]

def test_verified_main_menu_start_and_prepare_mappings():
    r=ScreenMappingRegistry.load(ROOT/"screen_mappings.json");objects={o.id:o for o in r.list_objects("twilight.main_menu")}
    assert objects["main_menu.start"].source["block"]==7
    assert objects["main_menu.prepare"].source["block"]==8
    assert objects["main_menu.start"].confidence==MappingConfidence.LIVE_VERIFIED

def test_system_menu_maps_only_its_three_visible_assets():
    r=ScreenMappingRegistry.load(ROOT/"screen_mappings.json")
    objects={o.id:o for o in r.list_objects("twilight.system_menu")}
    assert {"main_menu.classroom_background","menu.window_color","menu.view_spoils","menu.return_to_title"}<=set(objects)
    assert objects["menu.window_color"].source["block"]==1
    assert objects["menu.view_spoils"].source["block"]==0
    assert objects["menu.return_to_title"].source["block"]==2
    assert objects["main_menu.classroom_background"].source["members"]==[0,1,2,3,4]

def test_weaker_manual_mapping_cannot_replace_live_verified():
    verified=object_()
    verified=InspectableScreenObject(**{**verified.__dict__,"confidence":MappingConfidence.LIVE_VERIFIED})
    r=ScreenMappingRegistry([ScreenContext("c","g","x","s")],{"c":[verified]})
    with pytest.raises(ValueError,match="cannot replace LIVE_VERIFIED"):
        r.upsert("c",object_())

def test_spoils_photos_screen_has_verified_background_and_title():
    r=ScreenMappingRegistry.load(ROOT/"screen_mappings.json");objects={o.id:o for o in r.list_objects("twilight.spoils.photos")}
    assert objects["spoils.table_background"].source["members"]==[10,11,12,13,14]
    assert objects["category.photos"].source["block"]==9
    assert objects["category.photos"].confidence==MappingConfidence.LIVE_VERIFIED
