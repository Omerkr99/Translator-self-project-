"""PCSX-Redux VRAM-backed screenshot capture for verified screen contexts."""
from __future__ import annotations
import urllib.request
from PIL import Image

class PcsxVramCaptureProvider:
    def __init__(self,base_url="http://127.0.0.1:8080"):self.base_url=base_url.rstrip("/")
    def capture_region(self,region=(0,0,320,240))->Image.Image:
        with urllib.request.urlopen(f"{self.base_url}/api/v1/gpu/vram/raw",timeout=10) as response:raw=response.read()
        if len(raw)!=1024*512*2:raise ValueError(f"unexpected VRAM dump length {len(raw)}")
        x0,y0,width,height=region;image=Image.new("RGB",(width,height));pixels=[]
        for y in range(y0,y0+height):
            for x in range(x0,x0+width):
                p=2*(y*1024+x);value=raw[p]|raw[p+1]<<8;pixels.append(((value&31)*255//31,((value>>5)&31)*255//31,((value>>10)&31)*255//31))
        image.putdata(pixels);return image
