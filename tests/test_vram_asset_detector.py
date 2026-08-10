from pathlib import Path
from gcrts.asset_project import AssetProject
from gcrts.vram_asset_detector import VramAssetDetector,packed_rows

ROOT=Path(__file__).parents[1]/"sdb_main_menu_asset"
def test_exact_packed_tim_is_found_at_arbitrary_vram_location():
    p=AssetProject.open(ROOT/"MENUDAT.BIN","DAT/SINKOU/MENUDAT.BIN;1");tim=p.tim(9);vram=bytearray(1024*512*2);x,y=700,123
    for row,data in enumerate(packed_rows(tim)):vram[(y+row)*2048+x*2:(y+row)*2048+x*2+len(data)]=data
    matches=VramAssetDetector().detect_project(bytes(vram),p)
    hit=next(m for m in matches if m.block==9);assert (hit.x_words,hit.y,hit.width_words,hit.height,hit.pixel_mode)==(700,123,16,32,"4bpp")
def test_residency_match_does_not_claim_drawn_state():
    p=AssetProject.open(ROOT/"MENUDAT.BIN","DAT/SINKOU/MENUDAT.BIN;1");vram=bytes(1024*512*2);assert VramAssetDetector().detect_project(vram,p)==[]
