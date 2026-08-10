"""Human-readable persistent contexts and verified/manual mappings."""
from __future__ import annotations
import json
from pathlib import Path
from gcrts.screen_objects import *

class ScreenMappingRegistry:
    def __init__(self,contexts=None,objects=None):self.contexts={c.id:c for c in contexts or []};self.objects={k:list(v) for k,v in (objects or {}).items()}
    def add_context(self,context):self.contexts[context.id]=context;self.objects.setdefault(context.id,[])
    def list_objects(self,context_id):return list(self.objects.get(context_id,[]))
    def upsert(self,context_id,obj):
        if context_id not in self.contexts:raise KeyError(context_id)
        items=self.objects.setdefault(context_id,[])
        existing=next((old for old in items if old.id==obj.id),None)
        if existing and existing.confidence==MappingConfidence.LIVE_VERIFIED and obj.confidence!=MappingConfidence.LIVE_VERIFIED:
            raise ValueError(f"cannot replace LIVE_VERIFIED mapping {obj.id!r} with {obj.confidence.value}")
        self.objects[context_id]=[old for old in items if old.id!=obj.id]+[obj]
    def delete(self,context_id,object_id):self.objects[context_id]=[o for o in self.objects.get(context_id,[]) if o.id!=object_id]
    def hit_test(self,context_id,x,y):
        # A label sitting on a full-screen composite must win over its background.
        return sorted((o for o in self.objects.get(context_id,[]) if o.hit_test(x,y)),key=lambda o:o.screen_bounds.width*o.screen_bounds.height)
    def filtered(self,context_id,*,text_only=False,assets=True,renderer1=True,renderer2=True,unknown=True):
        result=[]
        for o in self.objects.get(context_id,[]):
            if text_only and o.text_representation==TextRepresentation.NOT_TEXT:continue
            kind=o.source.get("kind")
            if kind=="DISC_ASSET" and not assets:continue
            if kind=="RENDERER_1" and not renderer1:continue
            if kind=="RENDERER_2" and not renderer2:continue
            if kind in ("UNKNOWN",None) and not unknown:continue
            result.append(o)
        return result
    def to_dict(self):return {"schema_version":1,"contexts":[c.to_dict() for c in self.contexts.values()],"objects":{k:[o.to_dict() for o in v] for k,v in self.objects.items()}}
    def save(self,path):Path(path).write_text(json.dumps(self.to_dict(),ensure_ascii=False,indent=2),encoding="utf-8")
    @classmethod
    def load(cls,path):
        d=json.loads(Path(path).read_text(encoding="utf-8"));contexts=[ScreenContext.from_dict(x) for x in d.get("contexts",[])];objects={k:[InspectableScreenObject.from_dict(x) for x in v] for k,v in d.get("objects",{}).items()};return cls(contexts,objects)
