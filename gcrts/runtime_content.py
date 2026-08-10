"""Emulator-independent runtime content and asset lifecycle models."""
from __future__ import annotations
from dataclasses import dataclass,field
from enum import Enum
from typing import Any

class RuntimeAssetState(str,Enum):
    KNOWN_ON_DISC="KNOWN_ON_DISC";LOADED="LOADED";DECOMPRESSED="DECOMPRESSED";UPLOADED_TO_VRAM="UPLOADED_TO_VRAM";DRAWN_THIS_FRAME="DRAWN_THIS_FRAME";STALE_IN_VRAM="STALE_IN_VRAM";UNLOADED="UNLOADED";UNKNOWN="UNKNOWN"

class RuntimeConfidence(str,Enum):
    LIVE_EXACT_SOURCE="LIVE_EXACT_SOURCE";LIVE_HASH_MATCH="LIVE_HASH_MATCH";LIVE_STRUCTURAL_MATCH="LIVE_STRUCTURAL_MATCH";MANUAL_VERIFIED="MANUAL_VERIFIED";CANDIDATE="CANDIDATE";UNKNOWN="UNKNOWN"

@dataclass(frozen=True)
class CanonicalAssetIdentity:
    asset_id:str;disc_path:str|None=None;container_type:str|None=None;block:int|None=None
    compressed_offset:int|None=None;compressed_size:int|None=None;decoded_size:int|None=None;format:str|None=None
    semantic:str|None=None;contains_text:bool=False;translation_relevant:bool=False;role:str|None=None

@dataclass(frozen=True)
class VramRegion:
    x:int;y:int;width:int;height:int;pixel_mode:str|None=None;generation:int=0
    def overlaps(self,other:"VramRegion")->bool:return self.x<other.x+other.width and other.x<self.x+self.width and self.y<other.y+other.height and other.y<self.y+self.height

@dataclass(frozen=True)
class DrawEvidence:
    primitive_address:int;primitive_type:str;screen_bounds:tuple[int,int,int,int];frame_id:int
    uv_bounds:tuple[int,int,int,int]|None=None;tpage:int|None=None;clut:int|None=None;ot_depth:int|None=None

@dataclass(frozen=True)
class LifecycleEvent:
    frame_id:int;instance_id:str;asset_id:str|None;state:RuntimeAssetState;kind:str;evidence:dict[str,Any]=field(default_factory=dict)

@dataclass
class RuntimeAssetInstance:
    runtime_instance_id:str;asset_id:str|None;state:RuntimeAssetState;confidence:RuntimeConfidence
    created_frame:int;last_transition_frame:int;compressed_ptr:int|None=None;decoded_ptr:int|None=None;decoded_size:int|None=None
    vram_regions:list[VramRegion]=field(default_factory=list);draws:list[DrawEvidence]=field(default_factory=list);provenance:list[dict[str,Any]]=field(default_factory=list)

@dataclass(frozen=True)
class CurrentFrameContent:
    frame_id:int;active_assets:tuple[RuntimeAssetInstance,...]=();runtime_text:tuple[Any,...]=();movies:tuple[Any,...]=();audio_events:tuple[Any,...]=();unknown_primitives:tuple[Any,...]=();page_id:str|None=None
