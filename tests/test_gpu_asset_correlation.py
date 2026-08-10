from gcrts.gpu_asset_correlation import *
from gcrts.vram_asset_detector import VramAssetMatch
def test_block9_vram_region_correlates_with_4bpp_primitive():
    asset=VramAssetMatch("category.photos",9,640,96,16,32,"4bpp");primitive=GpuPrimitive(12,0x80010000,0x2c,10,0,0,96,64,32,(40,28,64,32))
    hit=correlate([primitive],[asset])[0];assert hit.asset.block==9 and hit.primitive.screen_bounds==(40,28,64,32)
def test_resident_asset_without_referencing_primitive_is_not_correlated():
    asset=VramAssetMatch("category.photos",9,640,96,16,32,"4bpp");primitive=GpuPrimitive(12,1,0x2c,9,0,0,96,64,32,(0,0,64,32));assert correlate([primitive],[asset])==[]
