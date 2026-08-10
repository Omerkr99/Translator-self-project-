"""Exact packed-texture residency detection; this is binary VRAM evidence, not screenshot matching."""
from __future__ import annotations
from dataclasses import dataclass
import urllib.request
from gcrts.asset_project import AssetProject

@dataclass(frozen=True)
class VramAssetMatch:
    asset_id:str;block:int;x_words:int;y:int;width_words:int;height:int;pixel_mode:str;confidence:str="LIVE_HASH_MATCH"

def packed_rows(tim):
    if tim.bpp==0:return [bytes(tim.indices[y*tim.width+x]|(tim.indices[y*tim.width+x+1]<<4) for x in range(0,tim.width,2)) for y in range(tim.height)]
    if tim.bpp==1:return [tim.indices[y*tim.width:(y+1)*tim.width] for y in range(tim.height)]
    return [b"".join(value.to_bytes(2,"little") for value in tim.direct_pixels[y*tim.width:(y+1)*tim.width]) for y in range(tim.height)]

class VramAssetDetector:
    def __init__(self,width_words=1024,height=512):self.width_words=width_words;self.height=height
    def detect_project(self,vram:bytes,project:AssetProject):
        if len(vram)!=self.width_words*self.height*2:raise ValueError("unexpected VRAM size")
        matches=[]
        for descriptor in project.descriptors:
            tim=project.tim(descriptor.container.block);rows=packed_rows(tim);anchor=max(range(len(rows)),key=lambda y:len(set(rows[y])))
            row_bytes=self.width_words*2
            for y in range(self.height):
                base=y*row_bytes;start=0
                while True:
                    offset=vram.find(rows[anchor],base+start,base+row_bytes)
                    if offset<0:break
                    x_words=(offset-base)//2;top=y-anchor
                    if top>=0 and top+tim.height<=self.height and all(vram[(top+j)*row_bytes+x_words*2:(top+j)*row_bytes+x_words*2+len(rows[j])]==rows[j] for j in range(tim.height)):
                        matches.append(VramAssetMatch(descriptor.id,descriptor.container.block,x_words,top,len(rows[0])//2,tim.height,{0:"4bpp",1:"8bpp",2:"16bpp"}[tim.bpp]))
                    start=offset-base+2
        return matches

class PcsxVramProvider:
    def __init__(self,base_url="http://127.0.0.1:8080"):self.base_url=base_url.rstrip("/")
    def read(self):
        with urllib.request.urlopen(self.base_url+"/api/v1/gpu/vram/raw",timeout=5) as response:return response.read()
