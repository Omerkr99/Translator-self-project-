"""Transport boundary. Providers emit observations; core tracking stays emulator-neutral."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol,Iterable
import urllib.request

@dataclass(frozen=True)
class RuntimeObservation:
    kind:str;frame_id:int;fields:dict

class RuntimeProbeProvider(Protocol):
    def observations(self)->Iterable[RuntimeObservation]:...

class RecordedRuntimeProbe:
    def __init__(self,events):self.events=tuple(events)
    def observations(self):return iter(self.events)

class PcsxReduxRuntimeProbe:
    """Reads observations emitted by the separately loaded observational Lua probe."""
    def __init__(self,base_url="http://127.0.0.1:8080"):self.base_url=base_url.rstrip("/")
    def observations(self):
        with urllib.request.urlopen(self.base_url+"/api/v1/lua/gcrts/runtime-events",timeout=2) as response:text=response.read().decode("utf-8")
        for line in text.splitlines():
            kind,frame,source_ptr,compressed_size,prefix,decoded_ptr,decoded_size,caller=line.split("\t")
            fields={"source_ptr":int(source_ptr,16),"compressed_size":int(compressed_size),"compressed_prefix":prefix,"decoded_ptr":int(decoded_ptr,16),"decoded_size":int(decoded_size),"caller":int(caller,16)}
            if kind=="GPU_PRIMITIVE":
                u,v,uw,vh,sx,sy,sw,sh,clut,tpage=map(int,prefix.split(","));fields.update({"primitive_address":fields["source_ptr"],"command":fields["compressed_size"],"u":u,"v":v,"uv_width":uw,"uv_height":vh,"screen_bounds":(sx,sy,sw,sh),"clut":clut,"tpage":tpage})
            yield RuntimeObservation(kind,int(frame),fields)
