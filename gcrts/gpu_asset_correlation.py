"""Correlates decoded GPU texture coordinates with exact VRAM residency matches."""
from dataclasses import dataclass
from gcrts.vram_asset_detector import VramAssetMatch

@dataclass(frozen=True)
class GpuPrimitive:
    frame_id:int;address:int;command:int;tpage:int;clut:int;u:int;v:int;uv_width:int;uv_height:int;screen_bounds:tuple[int,int,int,int]
@dataclass(frozen=True)
class AssetDrawCorrelation:
    asset:VramAssetMatch;primitive:GpuPrimitive;confidence:str="LIVE_EXACT_VRAM_GPU"
def primitive_vram_region(p:GpuPrimitive):
    mode=(p.tpage>>7)&3;pixels_per_word={0:4,1:2,2:1}.get(mode,1);page_x=(p.tpage&15)*64;page_y=((p.tpage>>4)&1)*256
    x=page_x+p.u//pixels_per_word;width=(p.u%pixels_per_word+p.uv_width+pixels_per_word-1)//pixels_per_word
    return x,page_y+p.v,width,p.uv_height,{0:"4bpp",1:"8bpp",2:"16bpp"}.get(mode,"unknown")
def correlate(primitives,assets):
    result=[]
    for primitive in primitives:
        x,y,w,h,mode=primitive_vram_region(primitive)
        for asset in assets:
            if mode==asset.pixel_mode and x<asset.x_words+asset.width_words and asset.x_words<x+w and y<asset.y+asset.height and asset.y<y+h:result.append(AssetDrawCorrelation(asset,primitive))
    return result
