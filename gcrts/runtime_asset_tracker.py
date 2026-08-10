"""State machine and provenance correlation; contains no PCSX-specific code."""
from __future__ import annotations
from dataclasses import replace
from gcrts.runtime_content import *

class RuntimeAssetTracker:
    def __init__(self):self.instances={};self.events=[];self.vram=[];self.frame_id=0;self._next=0
    def _emit(self,instance,state,kind,**evidence):
        instance.state=state;instance.last_transition_frame=self.frame_id;instance.provenance.append({"kind":kind,"frame_id":self.frame_id,**evidence});self.events.append(LifecycleEvent(self.frame_id,instance.runtime_instance_id,instance.asset_id,state,kind,evidence))
    def loaded(self,asset_id=None,*,compressed_ptr=None,confidence=RuntimeConfidence.UNKNOWN,**evidence):
        self._next+=1;instance=RuntimeAssetInstance(f"session:{self._next}",asset_id,RuntimeAssetState.UNKNOWN,confidence,self.frame_id,self.frame_id,compressed_ptr=compressed_ptr);self.instances[instance.runtime_instance_id]=instance;self._emit(instance,RuntimeAssetState.LOADED,"LOAD",compressed_ptr=compressed_ptr,**evidence);return instance
    def decompressed(self,instance_id,*,decoded_ptr,decoded_size,asset_id=None,confidence=None,**evidence):
        instance=self.instances[instance_id];instance.asset_id=asset_id or instance.asset_id;instance.decoded_ptr=decoded_ptr;instance.decoded_size=decoded_size
        if confidence:instance.confidence=confidence
        self._emit(instance,RuntimeAssetState.DECOMPRESSED,"DECOMPRESS",decoded_ptr=decoded_ptr,decoded_size=decoded_size,**evidence);return instance
    def uploaded(self,instance_id,region:VramRegion,*,source_ptr=None,**evidence):
        instance=self.instances[instance_id];generation=max((r.generation for _,r in self.vram),default=0)+1;region=replace(region,generation=generation)
        survivors=[]
        for other_id,old in self.vram:
            if old.overlaps(region):
                other=self.instances[other_id];other.vram_regions=[r for r in other.vram_regions if r!=old]
                if not other.vram_regions:self._emit(other,RuntimeAssetState.STALE_IN_VRAM,"VRAM_OVERWRITE",overwritten_by=instance_id)
            else:survivors.append((other_id,old))
        self.vram=survivors+[(instance_id,region)];instance.vram_regions.append(region);self._emit(instance,RuntimeAssetState.UPLOADED_TO_VRAM,"VRAM_UPLOAD",source_ptr=source_ptr,region=region.__dict__,**evidence);return instance
    def begin_frame(self,frame_id):
        self.frame_id=frame_id
        for instance in self.instances.values():
            instance.draws=[]
            if instance.state==RuntimeAssetState.DRAWN_THIS_FRAME:instance.state=RuntimeAssetState.UPLOADED_TO_VRAM if instance.vram_regions else RuntimeAssetState.STALE_IN_VRAM
    def draw(self,instance_id,evidence:DrawEvidence):
        instance=self.instances[instance_id];instance.draws.append(evidence);self._emit(instance,RuntimeAssetState.DRAWN_THIS_FRAME,"GPU_DRAW",primitive_address=evidence.primitive_address,screen_bounds=evidence.screen_bounds);return instance
    def unloaded(self,instance_id,**evidence):
        # Distinct from STALE_IN_VRAM (still resident, just not referenced by
        # a primitive this frame): this is for a caller who has independent
        # evidence the asset's decoded buffer and VRAM residency are BOTH
        # gone -- e.g. it was resident but hasn't been referenced across many
        # frames while its VRAM region was never reclaimed by anything else
        # tracked, and the caller (not this class) decided to give up on it.
        # Never inferred automatically -- see RUNTIME_ASSET_TRACKER.md.
        instance=self.instances[instance_id];instance.vram_regions=[];instance.decoded_ptr=None;instance.decoded_size=None
        self._emit(instance,RuntimeAssetState.UNLOADED,"UNLOAD",**evidence);return instance
    def end_frame(self):return self.current_frame()
    def current_frame(self):return CurrentFrameContent(self.frame_id,tuple(i for i in self.instances.values() if i.state==RuntimeAssetState.DRAWN_THIS_FRAME))
    def active(self,state=RuntimeAssetState.DRAWN_THIS_FRAME):return [i for i in self.instances.values() if i.state==state]
