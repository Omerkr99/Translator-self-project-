from pathlib import Path
import pytest
from gcrts.asset_project import AssetProject

ROOT=Path(__file__).parents[1]/"sdb_main_menu_asset"

@pytest.mark.skipif(not (ROOT/"MENUDAT.BIN").exists(),reason="verified asset fixture not present")
def test_menudat_discovers_32_and_known_buttons():
    p=AssetProject.open(ROOT/"MENUDAT.BIN","DAT/SINKOU/MENUDAT.BIN;1")
    assert len(p.records)==32
    start=p.descriptor("main_menu.start");prepare=p.descriptor("main_menu.prepare")
    assert (start.container.block,start.container.compressed_offset,start.container.compressed_size,start.image.width,start.image.height)==(7,0x1BD4,514,100,24)
    assert (prepare.container.block,prepare.container.compressed_offset,prepare.container.compressed_size)==(8,0x1DD6,498)

@pytest.mark.skipif(not (ROOT/"MENUDAT.BIN").exists(),reason="verified asset fixture not present")
def test_menudat_unmodified_build_is_byte_identical():
    p=AssetProject.open(ROOT/"MENUDAT.BIN","DAT/SINKOU/MENUDAT.BIN;1")
    assert p.build()==(ROOT/"MENUDAT.BIN").read_bytes()

@pytest.mark.skipif(not (ROOT/"MENUDAT.BIN").exists(),reason="verified asset fixture not present")
def test_menudat_text_replacement_changes_only_requested_fixed_slot():
    p=AssetProject.open(ROOT/"MENUDAT.BIN","DAT/SINKOU/MENUDAT.BIN;1")
    p.text_overlay(7,"START",8,7,foreground_index=2,clear_existing=True)
    budget=p.budget(7)
    assert budget.safe and budget.final_size==514
    built=p.build();original=(ROOT/"MENUDAT.BIN").read_bytes()
    assert built[:0x1BD4]==original[:0x1BD4]
    assert built[0x1BD4+514:]==original[0x1BD4+514:]

@pytest.mark.skipif(not (ROOT/"PROGDAT.BIN").exists(),reason="verified asset fixture not present")
def test_progdat_has_15_streams_and_group0_layout():
    p=AssetProject.open(ROOT/"PROGDAT.BIN","DAT/SINKOU/PROGDAT.BIN;1")
    assert len(p.records)==15
    assert [(d.image.width,d.image.height) for d in p.descriptors[:5]]==[(64,240)]*5

@pytest.mark.skipif(not (ROOT/"PROGDAT.BIN").exists(),reason="verified asset fixture not present")
def test_progdat_group0_is_one_320x240_composite_and_roundtrips():
    p=AssetProject.open(ROOT/"PROGDAT.BIN","DAT/SINKOU/PROGDAT.BIN;1")
    image=p.composite_image([0,1,2,3,4])
    assert image.size==(320,240)
    p.replace_composite_png([0,1,2,3,4],image)
    rebuilt=AssetProject(p.build(),"DAT/SINKOU/PROGDAT.BIN;1")
    assert rebuilt.composite_image([0,1,2,3,4]).tobytes()==image.tobytes()
