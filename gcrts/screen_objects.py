"""Unified visible-object model shared by assets and runtime text."""
from __future__ import annotations
from dataclasses import asdict,dataclass,field
from enum import Enum
from typing import Any

class ScreenObjectType(str,Enum):
    IMAGE_ASSET="IMAGE_ASSET";COMPOSITE_IMAGE_ASSET="COMPOSITE_IMAGE_ASSET";RUNTIME_TEXT="RUNTIME_TEXT";UI_TEXT_ASSET="UI_TEXT_ASSET";UNKNOWN_TEXTURE="UNKNOWN_TEXTURE";UNKNOWN_TEXT="UNKNOWN_TEXT";UNKNOWN_REGION="UNKNOWN_REGION"
class TextRepresentation(str,Enum):
    NOT_TEXT="NOT_TEXT";RASTER_TEXT_ASSET="RASTER_TEXT_ASSET";RUNTIME_TEXT_RENDERER_1="RUNTIME_TEXT_RENDERER_1";RUNTIME_TEXT_RENDERER_2="RUNTIME_TEXT_RENDERER_2";UNKNOWN_TEXT="UNKNOWN_TEXT"
class MappingConfidence(str,Enum):
    LIVE_VERIFIED="LIVE_VERIFIED";MANUAL_VERIFIED="MANUAL_VERIFIED";STATIC_CONFIRMED="STATIC_CONFIRMED";HIGH_CONFIDENCE="HIGH_CONFIDENCE";CANDIDATE="CANDIDATE";UNKNOWN="UNKNOWN"
class TranslationStatus(str,Enum):
    ORIGINAL="ORIGINAL";TRANSLATED="TRANSLATED";PARTIAL="PARTIAL";NEEDS_REVIEW="NEEDS_REVIEW";NOT_EDITABLE="NOT_EDITABLE";UNKNOWN="UNKNOWN"
class EditorTargetType(str,Enum):
    ASSET_INSPECTOR="ASSET_INSPECTOR";TEXT_LAYOUT_INSPECTOR="TEXT_LAYOUT_INSPECTOR";RENDERER_2_DETAILS="RENDERER_2_DETAILS";MAPPING_INVESTIGATION="MAPPING_INVESTIGATION"

@dataclass(frozen=True)
class ScreenBounds:
    x:int;y:int;width:int;height:int
    def contains(self,x:int,y:int)->bool:return self.x<=x<self.x+self.width and self.y<=y<self.y+self.height
    def overlaps(self,other:"ScreenBounds")->bool:return self.x<other.x+other.width and other.x<self.x+self.width and self.y<other.y+other.height and other.y<self.y+self.height

@dataclass(frozen=True)
class ScreenContext:
    id:str;game:str;chapter:str;screen:str;overlay:str|None=None;runtime_profile:str|None=None;confidence:MappingConfidence=MappingConfidence.UNKNOWN
    native_width:int=320;native_height:int=240;capture_region:tuple[int,int,int,int]=(0,0,320,240)
    def to_dict(self):
        d=asdict(self);d["confidence"]=self.confidence.value;d["capture_region"]=list(self.capture_region);return d
    @classmethod
    def from_dict(cls,d):return cls(**{**d,"confidence":MappingConfidence(d.get("confidence","UNKNOWN")),"capture_region":tuple(d.get("capture_region",(0,0,320,240)))})

@dataclass(frozen=True)
class InspectableScreenObject:
    id:str;display_name:str;object_type:ScreenObjectType;screen_bounds:ScreenBounds;source:dict[str,Any];editor_target:dict[str,Any];confidence:MappingConfidence
    text_representation:TextRepresentation=TextRepresentation.NOT_TEXT;translation_status:TranslationStatus=TranslationStatus.UNKNOWN;editable:bool=False;metadata:dict[str,Any]=field(default_factory=dict)
    def hit_test(self,x:int,y:int)->bool:return self.screen_bounds.contains(x,y)
    def to_dict(self):
        d=asdict(self);d["object_type"]=self.object_type.value;d["confidence"]=self.confidence.value;d["text_representation"]=self.text_representation.value;d["translation_status"]=self.translation_status.value;return d
    @classmethod
    def from_dict(cls,d):
        return cls(d["id"],d.get("display_name",d["id"]),ScreenObjectType(d["object_type"]),ScreenBounds(**d["screen_bounds"]),dict(d["source"]),dict(d["editor_target"]),MappingConfidence(d["confidence"]),TextRepresentation(d.get("text_representation","NOT_TEXT")),TranslationStatus(d.get("translation_status","UNKNOWN")),d.get("editable",False),dict(d.get("metadata",{})))

def renderer_1_object(*,id:str,name:str,bounds:ScreenBounds,script_unit:str,line_index:int,profile_valid:bool,metadata:dict|None=None)->InspectableScreenObject:
    confidence=MappingConfidence.LIVE_VERIFIED if profile_valid else MappingConfidence.UNKNOWN
    return InspectableScreenObject(id,name,ScreenObjectType.RUNTIME_TEXT,bounds,{"kind":"RENDERER_1","script_unit":script_unit,"line_index":line_index},{"type":EditorTargetType.TEXT_LAYOUT_INSPECTOR.value,"script_unit":script_unit},confidence,TextRepresentation.RUNTIME_TEXT_RENDERER_1,TranslationStatus.ORIGINAL,profile_valid,{**(metadata or {}),"profile_valid":profile_valid,"detection_available":profile_valid})

def renderer_2_candidate(*,id:str,name:str,bounds:ScreenBounds,details:str=""):
    return InspectableScreenObject(id,name,ScreenObjectType.RUNTIME_TEXT,bounds,{"kind":"RENDERER_2","status":"DETECTED_BUT_UNRESOLVED"},{"type":EditorTargetType.RENDERER_2_DETAILS.value},MappingConfidence.CANDIDATE,TextRepresentation.RUNTIME_TEXT_RENDERER_2,TranslationStatus.NOT_EDITABLE,False,{"details":details})
