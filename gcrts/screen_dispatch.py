"""Routes one unified screen object to an existing editor/investigation path."""
from __future__ import annotations
from dataclasses import dataclass
from gcrts.screen_objects import EditorTargetType,InspectableScreenObject

@dataclass(frozen=True)
class DispatchResult:
    target:EditorTargetType;available:bool;reason:str="";parameters:dict|None=None

def dispatch(obj:InspectableScreenObject)->DispatchResult:
    target=EditorTargetType(obj.editor_target.get("type","MAPPING_INVESTIGATION"));params=dict(obj.editor_target)
    if target==EditorTargetType.ASSET_INSPECTOR:return DispatchResult(target,obj.editable,"asset is marked uneditable" if not obj.editable else "",params)
    if target==EditorTargetType.TEXT_LAYOUT_INSPECTOR:
        valid=bool(obj.metadata.get("profile_valid"));return DispatchResult(target,valid,"Renderer 1 runtime profile is unavailable or stale" if not valid else "",params)
    if target==EditorTargetType.RENDERER_2_DETAILS:return DispatchResult(target,True,"editing unavailable; investigation details only",params)
    return DispatchResult(target,True,"no verified source mapping exists",params)
