"""Builds Visual Inspector objects from live OT+VRAM evidence."""
from __future__ import annotations
from pathlib import Path
import urllib.request,struct,time
from gcrts.asset_project import AssetProject
from gcrts.gpu_asset_correlation import correlate
from gcrts.psx_ordering_table import parse_ot
from gcrts.renderer1_profile import SLPS00102_BASE_PROFILE,ValidationResult
from gcrts.renderer1_runtime import capture_snapshot,renderer1_screen_objects
from gcrts.runtime_asset_tracker import RuntimeAssetTracker
from gcrts.runtime_audio import SLPS00102_AUDIO_PROFILE,capture_audio_event
from gcrts.runtime_content import DrawEvidence,RuntimeConfidence,VramRegion
from gcrts.script_audio_association import capture_script_audio_association
from gcrts.audio_context import audio_context_for_association
from gcrts.audio_caption import caption_for_association
from gcrts.audio_stream_source import resolve_audio_stream_source
from gcrts.cdrom_driver_map import resolve_cdrom_driver_map
from gcrts.live_audio_inspector import inspect_live_audio
from gcrts.screen_objects import *
from gcrts.vram_asset_detector import VramAssetDetector

def _ram_slice(ram:bytes,addr:int,length:int)->bytes|None:
    start=addr&0x1fffff;end=start+length
    return ram[start:end] if end<=len(ram) else None

# GPU primitive command -> short label, for DrawEvidence.primitive_type only
# (display/provenance, not used for any detection decision).
_PRIMITIVE_TYPE_BY_COMMAND_RANGE=((0x24,0x27,"POLY_FT3"),(0x2c,0x2f,"POLY_FT4"),(0x34,0x37,"POLY_GT3"),(0x3c,0x3f,"POLY_GT4"))
def _primitive_type(command:int)->str:
    for lo,hi,name in _PRIMITIVE_TYPE_BY_COMMAND_RANGE:
        if lo<=command<=hi:return name
    return f"cmd_{command:#04x}"

class RuntimeVisualProvider:
    """`tracker` is a `RuntimeAssetTracker` instance persisted ACROSS calls to
    `scan()` (the default, a fresh one, works too -- it just starts with no
    history). Every asset a scan correlates is fed through the tracker's real
    LOADED->UPLOADED_TO_VRAM->DRAWN_THIS_FRAME state machine (keyed by a
    stable per-asset_id instance, reused across calls) instead of every
    returned object simply being stamped with a hardcoded "DRAWN_THIS_FRAME"
    string -- so an asset that stops being correlated between two `scan()`
    calls (already happening in practice: gcrts.visual_inspector_ui polls
    this every 750ms) genuinely demotes to UPLOADED_TO_VRAM/STALE_IN_VRAM in
    `self.tracker`, inspectable independently of whatever this call returns.
    This does not change `scan()`'s own return contract (frame, objects) --
    every existing caller keeps working unmodified; `self.tracker` is a new,
    additive way to ask "what happened to X since the last scan" that plain
    per-call correlation can't answer on its own."""
    def __init__(self,projects,event_path=r"C:\tmp\gcrts-runtime-events.tsv",base_url="http://127.0.0.1:8080",tracker:RuntimeAssetTracker|None=None,disc_image_path:str|Path|None=None):
        self.projects=tuple(projects);self.event_path=Path(event_path);self.base_url=base_url.rstrip("/")
        self.tracker=tracker if tracker is not None else RuntimeAssetTracker();self._instance_by_asset_id={};self.last_renderer1_validation=ValidationResult.REIDENTIFICATION_REQUIRED.value;self.last_audio_event=None;self.last_script_association=None;self.last_audio_context=None;self.last_audio_caption=None;self.last_audio_stream_source=None;self.last_cdrom_driver_map=None;self.last_live_audio_inspection=None
        # Optional: only needed for xa_channel resolution (gcrts.xa_disc_index
        # read_sector_meta needs real sector bytes, not just the static LBA
        # table). Loaded once, lazily -- most callers never touch audio at
        # all, and the .bin is hundreds of MB, so this must never happen
        # unconditionally in __init__.
        self._disc_image_path=Path(disc_image_path) if disc_image_path is not None else None;self._disc_bytes=None
    def _tracked_instance(self,asset_id,**loaded_evidence):
        instance_id=self._instance_by_asset_id.get(asset_id)
        if instance_id is None:
            instance=self.tracker.loaded(asset_id,confidence=RuntimeConfidence.LIVE_EXACT_SOURCE,**loaded_evidence)
            instance_id=self._instance_by_asset_id[asset_id]=instance.runtime_instance_id
        return instance_id
    def _track_draw(self,asset_id,region:VramRegion,primitive):
        instance_id=self._tracked_instance(asset_id)
        self.tracker.uploaded(instance_id,region)
        self.tracker.draw(instance_id,DrawEvidence(primitive.address,_primitive_type(primitive.command),primitive.screen_bounds,primitive.frame_id,tpage=primitive.tpage,clut=primitive.clut))
        return self.tracker.instances[instance_id]
    def _roots(self,ram):
        # PROG profile: roots and code must validate together. Never use these
        # addresses after overlay drift merely because an old event log exists.
        exe=Path("sdb_main_menu_asset/PROG.EXE")
        if not exe.exists():return 0,[]
        data=exe.read_bytes();base=struct.unpack_from("<I",data,0x18)[0];start=0x80049630;size=0x4c;offset=0x800+(start-base)
        expected=data[offset:offset+size];actual=ram[start&0x1fffff:(start&0x1fffff)+size]
        if len(expected)!=size or actual!=expected:return 0,[]
        return int(time.monotonic()*1000),[0x80076a24,0x80076a64,0x80075770,0x800757b0]
    def _renderer1_objects(self,ram,snapshot_id):
        """Milestone 5: the second half of the unified surface. Independent
        of the PROG/MENUDAT asset path above -- this project's own
        overlay-drift findings (GPU_OT_RUNTIME_MAP.md) confirm the two
        never share a loaded executable, so this must never be gated behind
        `roots` being non-empty, or a real dialogue scene would silently
        report zero Renderer 1 text just because it isn't the menu."""
        snapshot=capture_snapshot(lambda addr,length:_ram_slice(ram,addr,length),SLPS00102_BASE_PROFILE)
        self.last_renderer1_validation=snapshot.validation.value  # Milestone 6: readable after scan() without a second RAM fetch
        if snapshot.validation!=ValidationResult.PROFILE_VALID:return []
        return renderer1_screen_objects(snapshot,SLPS00102_BASE_PROFILE,snapshot_id)
    def _audio_event(self,ram):
        """Runtime Audio Tracker milestone: same pattern as
        `_renderer1_objects` above -- a pure, injected `read_memory` over
        the already-fetched RAM dump, no second fetch. `prior` is this
        provider's own last event, so repeated `scan()` calls (this
        project's own 750ms poll cadence) correctly carry
        `position_counter_start` across calls within one contiguous
        PLAYING span instead of resetting it every poll -- see
        gcrts.runtime_audio.capture_audio_event's own docstring.

        `disc_bytes` (loaded once, lazily, only if a disc_image_path was
        given) enables xa_channel resolution -- source_file resolution
        works either way, since it only needs the static LBA table."""
        if self._disc_bytes is None and self._disc_image_path is not None and self._disc_image_path.exists():
            self._disc_bytes=self._disc_image_path.read_bytes()
        return capture_audio_event(lambda addr,length:_ram_slice(ram,addr,length),SLPS00102_AUDIO_PROFILE,prior=self.last_audio_event,disc_bytes=self._disc_bytes)
    def _script_association(self,ram,audio_event):
        """Script Context <-> Audio Dispatch Correlation milestone: same
        no-second-fetch pattern as the two methods above. Only meaningful
        when an audio event was actually captured this scan -- with none,
        capture_script_audio_association would still resolve script
        context but have nothing real to attach it to."""
        if audio_event is None:
            return None
        return capture_script_audio_association(lambda addr,length:_ram_slice(ram,addr,length),audio_event=audio_event)
    def _audio_context(self,ram,association):
        """Audio Bank/Context Resolution milestone: WHY the association's
        source resolves the way it does -- the confirmed selector ->
        table1 -> table2 -> handler-function dispatch chain
        (AUDIO_CONTEXT_RESOLUTION.md). Same no-second-fetch pattern."""
        return audio_context_for_association(lambda addr,length:_ram_slice(ram,addr,length),association)
    def _audio_caption(self,association):
        """Pure, no RAM access needed -- derives a caption only from
        already-decoded script data (see gcrts.audio_caption's own
        docstring: this is the ONLY caption source this project can
        honestly produce on its own, no audio listening capability
        exists in this environment)."""
        return caption_for_association(association)
    def _audio_stream_source(self,ram):
        """XA File Open / Stream Resolution follow-up
        (gcrts.audio_stream_source, AUDIO_CONTEXT_RESOLUTION.md's own
        follow-up doc): the real event-start-LBA descriptor structure,
        independent of the position-counter-based resolution. Always
        attempted (not gated on an audio event existing) since the
        descriptor pointer is a fixed global -- if nothing is currently
        dispatched it will simply come back UNKNOWN/stale, which is
        still informative."""
        return resolve_audio_stream_source(lambda addr,length:_ram_slice(ram,addr,length))
    def _cdrom_driver_map(self,ram):
        """XA Channel/Filter Runtime Resolution milestone
        (gcrts.cdrom_driver_map): confirms this game's own RAM code (not
        an opaque BIOS wrapper) is the low-level CD-ROM driver, and that
        its 4 hardware-register pointer variables still hold the real
        addresses this session found live. A static, code-level fact
        (not per-audio-event), so always attempted regardless of
        whether an audio event is currently active -- same reasoning as
        `_audio_stream_source`."""
        return resolve_cdrom_driver_map(lambda addr,length:_ram_slice(ram,addr,length))
    def _live_audio_inspection(self,audio_event):
        """Live Audio Inspector milestone (gcrts.live_audio_inspector):
        the display layer over the already-working LBA resolver +
        Dialogue Asset Database, wired in the same no-second-fetch
        pattern as the audio methods above. `self._disc_bytes` is set
        as a side effect of `_audio_event` when a disc_image_path was
        given; without one this always returns None (no disc bytes to
        resolve an asset from), same as every other audio field here."""
        return inspect_live_audio(audio_event,self._disc_bytes)
    def scan(self):
        ram=urllib.request.urlopen(self.base_url+"/api/v1/cpu/ram/raw",timeout=5).read();frame,roots=self._roots(ram)
        snapshot_id=frame or int(time.monotonic()*1000)
        self.tracker.begin_frame(snapshot_id)
        self.last_audio_event=self._audio_event(ram)
        self.last_live_audio_inspection=self._live_audio_inspection(self.last_audio_event)
        self.last_script_association=self._script_association(ram,self.last_audio_event)
        self.last_audio_context=self._audio_context(ram,self.last_script_association)
        self.last_audio_caption=self._audio_caption(self.last_script_association)
        self.last_audio_stream_source=self._audio_stream_source(ram)
        self.last_cdrom_driver_map=self._cdrom_driver_map(ram)
        objects=self._renderer1_objects(ram,snapshot_id)
        if not roots:return snapshot_id,objects
        vram=urllib.request.urlopen(self.base_url+"/api/v1/gpu/vram/raw",timeout=5).read();primitives=[]
        for root in roots:primitives.extend(parse_ot(ram,root,snapshot_id))
        frame=snapshot_id;seen=set()
        for project in self.projects:
            assets=VramAssetDetector().detect_project(vram,project);descriptors={d.container.block:d for d in project.descriptors}
            correlations=correlate(primitives,assets)
            if "PROGDAT" in project.disc_path.upper():
                for group in range(3):
                    members=range(group*5,group*5+5);hits=[hit for hit in correlations if hit.asset.block in members]
                    if not hits:continue
                    unique={hit.primitive.address:hit.primitive for hit in hits}.values();xs=[p.screen_bounds[0] for p in unique];ys=[p.screen_bounds[1] for p in unique];rights=[p.screen_bounds[0]+p.screen_bounds[2] for p in unique];bottoms=[p.screen_bounds[1]+p.screen_bounds[3] for p in unique];x,y=min(xs),min(ys);w,h=max(rights)-x,max(bottoms)-y
                    member_assets={hit.asset.block:hit.asset for hit in hits}.values();vx=min(a.x_words for a in member_assets);vy=min(a.y for a in member_assets);vregion=VramRegion(vx,vy,max(a.x_words+a.width_words for a in member_assets)-vx,max(a.y+a.height for a in member_assets)-vy,next(iter(member_assets)).pixel_mode)
                    tracked=None
                    for primitive in unique:tracked=self._track_draw(f"progdat.group{group}",vregion,primitive)
                    names={0:"Classroom Background",1:"Alternate Classroom Background",2:"Spoils Table Background"};objects.append(InspectableScreenObject(f"runtime:progdat.group{group}",names[group],ScreenObjectType.COMPOSITE_IMAGE_ASSET,ScreenBounds(x,y,w,h),{"kind":"DISC_ASSET","file":project.disc_path,"local_file":str(project.source_path),"members":list(members),"asset_id":f"progdat.group{group}"},{"type":"ASSET_INSPECTOR","asset_id":f"progdat.group{group}","members":list(members)},MappingConfidence.LIVE_VERIFIED,TextRepresentation.NOT_TEXT,TranslationStatus.NOT_EDITABLE,True,{"runtime_state":tracked.state.value,"runtime_instance_id":tracked.runtime_instance_id,"snapshot_id":frame,"primitive_addresses":[p.address for p in unique],"confidence":"LIVE_EXACT_VRAM_GPU","member_layout":"five 64x240 strips"}))
                continue
            for hit in correlations:
                key=(hit.asset.asset_id,hit.primitive.screen_bounds)
                if key in seen:continue
                seen.add(key);d=descriptors[hit.asset.block];x,y,w,h=hit.primitive.screen_bounds;text=d.usage in {"button_label","category_label","photo_label","sound_label","system_menu","chapter_title"}
                region=VramRegion(hit.asset.x_words,hit.asset.y,hit.asset.width_words,hit.asset.height,hit.asset.pixel_mode);tracked=self._track_draw(d.id,region,hit.primitive)
                objects.append(InspectableScreenObject(f"runtime:{hit.asset.asset_id}:{x}:{y}",d.display_name,ScreenObjectType.UI_TEXT_ASSET if text else ScreenObjectType.IMAGE_ASSET,ScreenBounds(x,y,w,h),{"kind":"DISC_ASSET","file":project.disc_path,"local_file":str(project.source_path) if hasattr(project,"source_path") else None,"block":hit.asset.block,"asset_id":d.id},{"type":"ASSET_INSPECTOR","asset_id":d.id,"block":hit.asset.block},MappingConfidence.LIVE_VERIFIED,TextRepresentation.RASTER_TEXT_ASSET if text else TextRepresentation.NOT_TEXT,TranslationStatus.ORIGINAL,True,{"runtime_state":tracked.state.value,"runtime_instance_id":tracked.runtime_instance_id,"snapshot_id":frame,"vram":{"x_words":hit.asset.x_words,"y":hit.asset.y,"width_words":hit.asset.width_words,"height":hit.asset.height,"pixel_mode":hit.asset.pixel_mode},"primitive_address":hit.primitive.address,"tpage":hit.primitive.tpage,"uv":(hit.primitive.u,hit.primitive.v,hit.primitive.uv_width,hit.primitive.uv_height),"confidence":"LIVE_EXACT_VRAM_GPU"}))
        return snapshot_id,objects

def open_runtime_projects(menudat="sdb_main_menu_asset/MENUDAT.BIN",progdat="sdb_main_menu_asset/PROGDAT.BIN"):
    projects=[]
    for path,disc in ((menudat,"DAT/SINKOU/MENUDAT.BIN;1"),(progdat,"DAT/SINKOU/PROGDAT.BIN;1")):
        if Path(path).exists():
            project=AssetProject.open(path,disc);project.source_path=Path(path);projects.append(project)
    return projects
