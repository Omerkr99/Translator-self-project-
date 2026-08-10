"""Temporary PCSX-Redux patch provider; never writes the physical disc image."""
from __future__ import annotations
import urllib.parse, urllib.request

class PcsxReduxPatchProvider:
    def __init__(self,base_url:str="http://127.0.0.1:8080"):self.base_url=base_url.rstrip("/")
    def patch_disc_file(self,disc_path:str,data:bytes)->None:
        query=urllib.parse.quote(disc_path,safe="")
        request=urllib.request.Request(f"{self.base_url}/api/v1/cd/patch?filename={query}",data=data,method="POST",headers={"Content-Type":"application/octet-stream"})
        with urllib.request.urlopen(request,timeout=15) as response:
            if response.status!=200:raise RuntimeError(f"PCSX-Redux returned HTTP {response.status}")
    def clear(self)->None:
        request=urllib.request.Request(f"{self.base_url}/api/v1/cd/ppf?function=clear",data=b"",method="POST")
        with urllib.request.urlopen(request,timeout=15) as response:
            if response.status!=200:raise RuntimeError(f"PCSX-Redux returned HTTP {response.status}")
