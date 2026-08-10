from gcrts.runtime_asset_tracker import RuntimeAssetTracker
from gcrts.runtime_content import *

def test_full_lifecycle_and_draw_is_frame_scoped():
    t=RuntimeAssetTracker();t.begin_frame(10);a=t.loaded("twilight.menudat.block_09",compressed_ptr=0x1000,confidence=RuntimeConfidence.LIVE_EXACT_SOURCE)
    t.decompressed(a.runtime_instance_id,decoded_ptr=0x2000,decoded_size=123)
    t.uploaded(a.runtime_instance_id,VramRegion(320,0,16,32,"4bpp"),source_ptr=0x2000)
    t.draw(a.runtime_instance_id,DrawEvidence(0x3000,"POLY_FT4",(40,28,64,32),10))
    assert t.current_frame().active_assets==(a,) and a.state==RuntimeAssetState.DRAWN_THIS_FRAME
    t.begin_frame(11)
    assert not t.current_frame().active_assets and a.state==RuntimeAssetState.UPLOADED_TO_VRAM

def test_vram_overwrite_invalidates_previous_residency():
    t=RuntimeAssetTracker();a=t.loaded("a");b=t.loaded("b");t.uploaded(a.runtime_instance_id,VramRegion(10,10,20,20));t.uploaded(b.runtime_instance_id,VramRegion(15,15,5,5))
    assert a.state==RuntimeAssetState.STALE_IN_VRAM and not a.vram_regions
    assert b.state==RuntimeAssetState.UPLOADED_TO_VRAM

def test_resident_without_primitive_is_not_drawn():
    t=RuntimeAssetTracker();a=t.loaded("a");t.uploaded(a.runtime_instance_id,VramRegion(0,0,1,1));assert t.active()==[]

def test_unknown_decompression_is_preserved():
    t=RuntimeAssetTracker();a=t.loaded();t.decompressed(a.runtime_instance_id,decoded_ptr=4,decoded_size=20);assert a.asset_id is None and t.events[-1].kind=="DECOMPRESS"

def test_unloaded_clears_vram_and_decoded_state():
    t=RuntimeAssetTracker();a=t.loaded("a");t.decompressed(a.runtime_instance_id,decoded_ptr=0x2000,decoded_size=64)
    t.uploaded(a.runtime_instance_id,VramRegion(0,0,8,8))
    t.unloaded(a.runtime_instance_id,reason="evicted")
    assert a.state==RuntimeAssetState.UNLOADED and a.vram_regions==[] and a.decoded_ptr is None and a.decoded_size is None
    assert t.events[-1].kind=="UNLOAD" and t.events[-1].evidence=={"reason":"evicted"}

def test_unloaded_is_distinct_from_stale_in_vram():
    """STALE_IN_VRAM (still resident, just not drawn) and UNLOADED (caller has
    independent evidence it's fully gone) must never collapse into one state --
    see gcrts.runtime_content's module docstring on why LOADED != ACTIVE."""
    t=RuntimeAssetTracker();resident=t.loaded("resident");t.uploaded(resident.runtime_instance_id,VramRegion(0,0,4,4))
    gone=t.loaded("gone");t.uploaded(gone.runtime_instance_id,VramRegion(100,100,4,4));t.unloaded(gone.runtime_instance_id)
    assert resident.state==RuntimeAssetState.UPLOADED_TO_VRAM
    assert gone.state==RuntimeAssetState.UNLOADED
