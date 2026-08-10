"""Screen-driven Visual Inspector integrating assets and renderer objects."""
from __future__ import annotations
import argparse,subprocess,sys,time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog,messagebox,simpledialog,ttk
from PIL import Image,ImageTk
from gcrts.screen_capture import PcsxVramCaptureProvider
from gcrts.screen_dispatch import dispatch
from gcrts.screen_mapping_registry import ScreenMappingRegistry
from gcrts.screen_objects import *
from gcrts.runtime_visual_provider import RuntimeVisualProvider,open_runtime_projects
from gcrts.runtime_pages import MatchingMode,RuntimePageDetector
from gcrts.project_selection import FileProjectSelection
from gcrts.runtime_snapshot import capture_runtime_snapshot,diff_snapshots,load_snapshot,save_snapshot

COLORS={MappingConfidence.LIVE_VERIFIED:"#00bfff",MappingConfidence.MANUAL_VERIFIED:"#2389ff",MappingConfidence.STATIC_CONFIRMED:"#2389ff",MappingConfidence.HIGH_CONFIDENCE:"#00a9c7",MappingConfidence.CANDIDATE:"#ffd000",MappingConfidence.UNKNOWN:"#888888"}  # legend reference; object_color() below is what's actually drawn

# Milestone 5.2's scheme: color encodes SOURCE (runtime-confirmed vs manual)
# and, for runtime-confirmed objects, WHICH of the two unified systems --
# never confidence alone, which is why this isn't just `COLORS[obj.confidence]`.
_BLUE="#00bfff"      # runtime-confirmed image/raster asset (Milestone 2's tracker)
_CYAN="#00e5ff"       # runtime-confirmed Renderer 1 text (Milestone 1's driver)
_YELLOW="#ffd000"    # candidate / unresolved -- not yet verified either way
_GRAY="#888888"       # manual mapping fallback only, no live confirmation this frame

def object_color(obj:"InspectableScreenObject")->str:
    if obj.confidence==MappingConfidence.LIVE_VERIFIED:
        return _CYAN if obj.text_representation==TextRepresentation.RUNTIME_TEXT_RENDERER_1 else _BLUE
    if obj.confidence==MappingConfidence.CANDIDATE or obj.object_type in (ScreenObjectType.UNKNOWN_TEXTURE,ScreenObjectType.UNKNOWN_TEXT,ScreenObjectType.UNKNOWN_REGION):
        return _YELLOW
    return _GRAY

def object_status_label(obj:"InspectableScreenObject")->str:
    """Never rely on color alone (5.2) -- a short text tag alongside the
    color, legible even without color vision or on a bad screenshot."""
    if obj.confidence==MappingConfidence.LIVE_VERIFIED:
        return "R1-LIVE" if obj.text_representation==TextRepresentation.RUNTIME_TEXT_RENDERER_1 else "LIVE"
    if obj.confidence==MappingConfidence.CANDIDATE:return "CANDIDATE"
    if obj.object_type in (ScreenObjectType.UNKNOWN_TEXTURE,ScreenObjectType.UNKNOWN_TEXT,ScreenObjectType.UNKNOWN_REGION):return "UNKNOWN"
    return "MANUAL"

class CreatePageDialog(tk.Toplevel):
    """7.2: every field here is a user choice, none pre-decided by
    composition. Assets start in Required (matches "this exact snapshot"
    until the user narrows it down); moving something to Optional/Ignored
    is always an explicit action."""
    def __init__(self,parent,asset_ids,existing_name="",existing_mode=MatchingMode.BALANCED.value):
        super().__init__(parent);self.title("Create Page");self.result=None;self.transient(parent);self.grab_set()
        top=ttk.Frame(self,padding=8);top.pack(fill="x")
        ttk.Label(top,text="Name:").pack(side="left");self.name_var=tk.StringVar(value=existing_name);ttk.Entry(top,textvariable=self.name_var,width=30).pack(side="left",padx=6)
        ttk.Label(top,text="Matching mode:").pack(side="left",padx=(14,2));self.mode_var=tk.StringVar(value=existing_mode)
        ttk.Combobox(top,textvariable=self.mode_var,values=[m.value for m in MatchingMode],state="readonly",width=14).pack(side="left")
        lists=ttk.Frame(self,padding=8);lists.pack(fill="both",expand=True)
        self._sets={"Required":list(asset_ids),"Optional":[],"Ignored":[]};self.boxes={}
        for i,category in enumerate(("Required","Optional","Ignored")):
            col=ttk.Frame(lists);col.grid(row=0,column=i,padx=6,sticky="nsew");ttk.Label(col,text=category).pack()
            box=tk.Listbox(col,selectmode="extended",height=10,width=28,exportselection=False);box.pack();self.boxes[category]=box
        for i in range(3):lists.columnconfigure(i,weight=1)
        self._refresh_boxes()
        moves=ttk.Frame(self,padding=(8,0));moves.pack(fill="x");ttk.Label(moves,text="Move selected to:").pack(side="left")
        for category in ("Required","Optional","Ignored"):ttk.Button(moves,text=category,command=lambda c=category:self._move_selected(c)).pack(side="left",padx=4)
        actions=ttk.Frame(self,padding=8);actions.pack(fill="x");ttk.Button(actions,text="Create",command=self._create).pack(side="right");ttk.Button(actions,text="Cancel",command=self.destroy).pack(side="right",padx=6)
    def _refresh_boxes(self):
        for category,box in self.boxes.items():
            box.delete(0,"end")
            for item in sorted(self._sets[category]):box.insert("end",item)
    def _move_selected(self,target_category):
        moved=[]
        for category,box in self.boxes.items():
            selected=[box.get(i) for i in box.curselection()]
            if selected:self._sets[category]=[x for x in self._sets[category] if x not in selected];moved.extend(selected)
        if moved:self._sets[target_category].extend(moved)
        self._refresh_boxes()
    def _create(self):
        name=self.name_var.get().strip()
        if not name:messagebox.showerror("Name required","Enter a name for this page.",parent=self);return
        self.result=(name,frozenset(self._sets["Required"]),frozenset(self._sets["Optional"]),frozenset(self._sets["Ignored"]),self.mode_var.get());self.destroy()

class VisualInspectorApp(tk.Tk):
    def __init__(self,registry_path:Path,asset_source:Path,context_id:str|None=None):
        super().__init__();self.registry_path=registry_path;self.registry=ScreenMappingRegistry.load(registry_path);self.asset_source=asset_source;self.context_id=context_id or next(iter(self.registry.contexts));self.image=None;self.photo=None;self.drag_start=None;self.selected=None;self.runtime_objects=[];self.runtime_scanned=False;self.runtime_frame=None;self.runtime_provider=RuntimeVisualProvider(open_runtime_projects());self.page_path=Path("runtime_pages.json");self.page_detector=RuntimePageDetector.load(self.page_path);self.current_page=None;self.selection_store=FileProjectSelection();self._last_synced_asset_id=None;self.viewing_snapshot=None
        if self.context_id not in self.registry.contexts:raise ValueError(f"unknown screen context: {self.context_id}")
        self.title("GCRTS Visual Inspector");self.geometry("1120x760");self._build();self.refresh_objects();self.after(750,self.poll_runtime)
    def _build(self):
        bar=ttk.Frame(self,padding=6);bar.pack(fill="x")
        ttk.Button(bar,text="Capture Current Screen",command=self.capture).pack(side="left");ttk.Button(bar,text="Load Screenshot",command=self.load).pack(side="left",padx=4)
        ttk.Button(bar,text="Save Snapshot",command=self.save_snapshot_action).pack(side="left",padx=(14,4));ttk.Button(bar,text="Load Snapshot",command=self.load_snapshot_action).pack(side="left",padx=4);ttk.Button(bar,text="Diff vs Saved...",command=self.diff_snapshot_action).pack(side="left",padx=4)
        ttk.Button(bar,text="Create Page...",command=self.create_page_action).pack(side="left",padx=(14,4))
        ttk.Label(bar,text="Context:").pack(side="left",padx=(14,2));self.context=tk.StringVar(value=self.context_id);box=ttk.Combobox(bar,textvariable=self.context,values=list(self.registry.contexts),state="readonly",width=28);box.pack(side="left");box.bind("<<ComboboxSelected>>",lambda _:self.change_context())
        self.mapping=tk.BooleanVar();ttk.Checkbutton(bar,text="Mapping Mode",variable=self.mapping).pack(side="right")
        filters=ttk.Frame(self,padding=(6,0));filters.pack(fill="x");self.translation=tk.BooleanVar();self.assets=tk.BooleanVar(value=True);self.r1=tk.BooleanVar(value=True);self.r2=tk.BooleanVar(value=True);self.unknown=tk.BooleanVar(value=True);self.manual_fallback=tk.BooleanVar(value=False)
        for label,var in (("Translation View",self.translation),("Show Assets",self.assets),("Renderer 1",self.r1),("Renderer 2",self.r2),("Unknown",self.unknown)):ttk.Checkbutton(filters,text=label,variable=var,command=self.redraw).pack(side="left",padx=4)
        ttk.Checkbutton(filters,text="Manual mapping fallback",variable=self.manual_fallback,command=self.redraw).pack(side="left",padx=4)
        self.live_tracking=tk.BooleanVar(value=True);ttk.Checkbutton(filters,text="Live runtime tracking",variable=self.live_tracking).pack(side="left",padx=4)
        pane=ttk.Panedwindow(self,orient="horizontal");pane.pack(fill="both",expand=True,padx=6,pady=6);left=ttk.Frame(pane);right=ttk.Frame(pane,padding=8);pane.add(left,weight=4);pane.add(right,weight=2)
        self.canvas=tk.Canvas(left,bg="#111",highlightthickness=0);self.canvas.pack(fill="both",expand=True);self.canvas.bind("<Configure>",lambda _:self.redraw());self.canvas.bind("<Motion>",self.motion);self.canvas.bind("<ButtonPress-1>",self.press);self.canvas.bind("<ButtonRelease-1>",self.release)
        self.heading=tk.StringVar(value="No object selected");ttk.Label(right,textvariable=self.heading,font=("Segoe UI",15,"bold")).pack(anchor="w");self.details=tk.Text(right,state="disabled",height=24,width=44,font=("Consolas",10));self.details.pack(fill="both",expand=True,pady=8)
        ttk.Button(right,text="Open Correct Inspector",command=self.open_selected).pack(fill="x");ttk.Button(right,text="Delete Manual Mapping",command=self.delete_selected).pack(fill="x",pady=4)
        # Runtime Audio Tracker milestone: minimal, read-only -- no waveform
        # editor, no per-cue controls. Just what's live in
        # RuntimeVisualProvider.last_audio_event, refreshed every poll_runtime
        # tick alongside everything else (gcrts.runtime_audio's own module
        # docstring covers what's confirmed vs not about these fields).
        audio_box=ttk.LabelFrame(right,text="Audio (live, read-only)",padding=6);audio_box.pack(fill="x",pady=(8,0))
        self.audio_status=tk.StringVar(value="(no live audio data yet)");ttk.Label(audio_box,textvariable=self.audio_status,font=("Consolas",9),foreground="#00e5ff",wraplength=380,justify="left").pack(anchor="w")
        self.status=tk.StringVar(value="Capture or load a screenshot.");ttk.Label(self,textvariable=self.status,relief="sunken",anchor="w").pack(fill="x",side="bottom")
    def change_context(self):self.context_id=self.context.get();self.refresh_objects()
    def refresh_objects(self):self.objects=self.registry.filtered(self.context_id,text_only=self.translation.get(),assets=self.assets.get(),renderer1=self.r1.get(),renderer2=self.r2.get(),unknown=self.unknown.get());self.redraw()
    def capture(self):
        try:
            self.image=PcsxVramCaptureProvider().capture_region(self.registry.contexts[self.context_id].capture_region);self.update_runtime();self.redraw()
        except Exception as e:messagebox.showerror("Capture failed",str(e))
    def load(self):
        path=filedialog.askopenfilename(filetypes=[("Images","*.png;*.jpg;*.jpeg;*.bmp")]);
        if path:self.image=Image.open(path).convert("RGB");self.status.set(path);self.redraw()
    def transform(self):
        if self.image is None:return (1,1,0,0)
        cw,ch=max(1,self.canvas.winfo_width()),max(1,self.canvas.winfo_height());scale=min(cw/self.image.width,ch/self.image.height);w,h=self.image.width*scale,self.image.height*scale;return scale,scale,(cw-w)/2,(ch-h)/2
    def redraw(self):
        if not hasattr(self,"canvas"):return
        self.refresh_objects_no_redraw();self.canvas.delete("all")
        if self.image is None:return
        sx,sy,ox,oy=self.transform();resized=self.image.resize((round(self.image.width*sx),round(self.image.height*sy)),Image.Resampling.NEAREST);self.photo=ImageTk.PhotoImage(resized);self.canvas.create_image(ox,oy,image=self.photo,anchor="nw",tags="screen")
        context=self.registry.contexts[self.context_id];rx=self.image.width/context.native_width;ry=self.image.height/context.native_height
        for obj in self.objects:
            b=obj.screen_bounds;x1=ox+b.x*rx*sx;y1=oy+b.y*ry*sy;x2=ox+(b.x+b.width)*rx*sx;y2=oy+(b.y+b.height)*ry*sy;color=object_color(obj)
            selected=self.selected is not None and obj.id==self.selected.id
            if selected:self.canvas.create_rectangle(x1-3,y1-3,x2+3,y2+3,outline="#ffffff",width=2,tags=("object",obj.id,"selection_ring"))
            self.canvas.create_rectangle(x1,y1,x2,y2,outline=color,width=5 if selected else 3,tags=("object",obj.id));self.canvas.create_text(x1+3,y1+3,text=f"{obj.display_name} [{object_status_label(obj)}]",anchor="nw",fill=color,font=("Segoe UI",10,"bold"),tags=("object",obj.id))
    def refresh_objects_no_redraw(self):
        if hasattr(self,"translation"):
            if self.runtime_scanned and not self.manual_fallback.get():
                self.objects=[o for o in self.runtime_objects if (not self.translation.get() or o.text_representation!=TextRepresentation.NOT_TEXT)]
            else:self.objects=self.registry.filtered(self.context_id,text_only=self.translation.get(),assets=self.assets.get(),renderer1=self.r1.get(),renderer2=self.r2.get(),unknown=self.unknown.get())
    def update_runtime(self):
        self.runtime_frame,self.runtime_objects=self.runtime_provider.scan();self.runtime_scanned=True;ids={o.source.get("asset_id") for o in self.runtime_objects};self.current_page,is_new=self.page_detector.observe(ids);self.page_detector.save(self.page_path);self.status.set(f"Runtime snapshot {self.runtime_frame} | Page {self.current_page.page_id}{' NEW' if is_new else ''} | {len(self.runtime_objects)} DRAWN_THIS_FRAME")
        self.audio_status.set(self._format_audio_status(self.runtime_provider.last_audio_event,self.runtime_provider.last_script_association,self.runtime_provider.last_audio_context,self.runtime_provider.last_audio_caption,self.runtime_provider.last_audio_stream_source,self.runtime_provider.last_cdrom_driver_map))
    @staticmethod
    def _format_audio_status(event,association=None,context=None,caption=None,stream_source=None,cdrom_driver=None)->str:
        from gcrts.runtime_audio import AudioLifecycleState
        from gcrts.script_audio_association import ScriptAssociationConfidence
        from gcrts.audio_context import AudioContextConfidence
        from gcrts.audio_caption import CaptionConfidence
        if event is None:return "(no audio profile match this frame -- likely a different loaded overlay)"
        if event.state in (AudioLifecycleState.STARTING,AudioLifecycleState.PLAYING):
            chan=f" ch{event.xa_channel}" if event.xa_channel is not None else " (channel not resolved -- no disc image loaded)"
            source=f"{event.source_file}{chan}" if event.source_file else "(unresolved -- position outside any known XAPACK file)"
            lines=[f"State: {event.state.value}",f"Cue: {event.script_parameter}",f"Source: {source}",
                   f"Resolved via: {event.resolution_method}",
                   f"Start LBA: {event.start_lba}",
                   f"Position: {event.position_counter} (+{event.position_counter-event.position_counter_start} since start)",
                   f"Confidence: {event.confidence.value}"]
            # Script Context <-> Audio Dispatch Correlation milestone: show
            # WHICH script occurrence owns this, not just the raw cue number
            # -- see SCRIPT_AUDIO_ASSOCIATION.md for why the cue number
            # alone is not a reliable identity.
            if association is not None and association.confidence==ScriptAssociationConfidence.SCRIPT_CONTEXT_RESOLVED:
                text_preview=(association.dialogue_text or "")[:30]
                lines.append(f"Script unit: {association.script_unit_id} (offset {association.control_code_offset:#x})")
                lines.append(f"Script text: {text_preview}...")
                lines.append(f"Association: {association.confidence.value}")
                # Audio Bank/Context Resolution milestone: WHY this source
                # was picked -- see AUDIO_CONTEXT_RESOLUTION.md.
                if context is not None and context.confidence!=AudioContextConfidence.UNKNOWN:
                    lines.append(f"Selector: {context.selector_value} -> table1={context.table1_value} -> {context.resolved_filename}" if context.resolved_filename else f"Selector: {context.selector_value} -> table1={context.table1_value}")
                    lines.append(f"Context: {context.confidence.value}")
                    from gcrts.audio_context import cross_validate_source
                    agree=cross_validate_source(event,context)
                    if agree is not None:
                        lines.append(f"Cross-checked vs. live position: {'MATCH' if agree else 'MISMATCH'}")
                else:
                    lines.append("Audio context: UNKNOWN")
                # Audio Caption milestone -- see AUDIO_CAPTIONS.md. Kept
                # visually distinct from the source/context lines above:
                # this is what's being HEARD, not where it comes from.
                if caption is not None and caption.confidence==CaptionConfidence.CONFIRMED:
                    cap_preview=(caption.caption_text or "")[:40]
                    lines.append(f"Caption ({caption.caption_source.value}): {cap_preview}...")
                else:
                    lines.append("Caption: UNKNOWN")
                # XA File Open / Stream Resolution follow-up -- the real
                # event-start-LBA descriptor, independent of the two
                # resolvers above. See AUDIO_CONTEXT_RESOLUTION.md.
                from gcrts.audio_stream_source import AudioStreamConfidence
                if stream_source is not None and stream_source.confidence==AudioStreamConfidence.LIVE_VERIFIED:
                    lines.append(f"Stream start LBA: {stream_source.file_start_lba} ({stream_source.matched_disc_path})")
                else:
                    lines.append("Stream descriptor: UNKNOWN")
                # Audio Event Isolation / Extraction milestone -- honest
                # readiness, never defaults file/channel from the
                # historical Setfilter observation (see
                # gcrts.cdrom_setfilter's "not proven event-specific"
                # correction and AUDIO_EVENT_EXTRACTION.md).
                from gcrts.audio_event_extraction import extraction_readiness
                extraction_start_lba=stream_source.file_start_lba if stream_source is not None and stream_source.confidence==AudioStreamConfidence.LIVE_VERIFIED else None
                extraction_status=extraction_readiness(start_lba=extraction_start_lba,end_lba=None,xa_file_number=None,xa_channel=None)
                lines.append(f"Extraction status: {extraction_status.value}")
                # XA Channel/Filter Runtime Resolution milestone -- the
                # low-level CD-ROM driver's own hardware register map,
                # not per-event (see gcrts.cdrom_driver_map). True XA
                # channel selection itself remains unresolved even when
                # this reads LIVE_VERIFIED -- see that module's docstring.
                from gcrts.cdrom_driver_map import CdromDriverConfidence
                if cdrom_driver is not None and cdrom_driver.confidence==CdromDriverConfidence.LIVE_VERIFIED:
                    lines.append("CD-ROM driver: LIVE_VERIFIED (ports 0x1F801800-1803 confirmed)")
                else:
                    lines.append("CD-ROM driver: UNKNOWN")
                # XA Channel/Filter Runtime Resolution milestone -- a
                # real, live-captured Setfilter(file, channel) call
                # (gcrts.cdrom_setfilter). Historical, not re-derived
                # this scan (see that module's docstring for why: it
                # required a live breakpoint session, not passive
                # polling) -- never presented as if it were this
                # specific event's own live value.
                from gcrts.cdrom_setfilter import KNOWN_SETFILTER_OBSERVATIONS
                if KNOWN_SETFILTER_OBSERVATIONS:
                    setfilter=KNOWN_SETFILTER_OBSERVATIONS[-1]
                    lines.append(f"Last known Setfilter (historical): file={setfilter.file_number} channel={setfilter.channel_number} [{setfilter.confidence.value}]")
            else:
                lines.append(f"Script context: {association.confidence.value if association else 'UNKNOWN'}")
            return "\n".join(lines)
        if event.state==AudioLifecycleState.STOPPED:return f"State: STOPPED (last cue {event.script_parameter}, position {event.position_counter})"
        return f"State: {event.state.value}"
    def save_snapshot_action(self):
        # Milestone 6: a coherent, persistable moment -- captured from
        # whatever the last scan already observed, no new live read.
        if not self.runtime_scanned:messagebox.showwarning("No runtime data","Capture/scan a live screen at least once before saving a snapshot.");return
        snapshot=capture_runtime_snapshot(self.runtime_provider,self.runtime_frame,self.runtime_objects)
        Path("runtime_snapshots").mkdir(exist_ok=True)
        default=f"runtime_snapshots/snapshot_{snapshot.snapshot_id}.json"
        path=filedialog.asksaveasfilename(initialfile=Path(default).name,initialdir="runtime_snapshots",defaultextension=".json",filetypes=[("Snapshot JSON","*.json")])
        if not path:return
        save_snapshot(snapshot,path);messagebox.showinfo("Snapshot saved",f"{path}\n{len(snapshot.objects)} objects, {len(snapshot.tracker_instances)} tracked instances.")
    def load_snapshot_action(self):
        # 6.1: viewing a saved snapshot must work with NO live connection at
        # all -- this only reads a file and stops polling, it never touches
        # self.runtime_provider.
        path=filedialog.askopenfilename(initialdir="runtime_snapshots",filetypes=[("Snapshot JSON","*.json")])
        if not path:return
        snapshot=load_snapshot(path);self.viewing_snapshot=snapshot;self.live_tracking.set(False)
        self.runtime_objects=[InspectableScreenObject.from_dict(o) for o in snapshot.objects];self.runtime_frame=snapshot.snapshot_id;self.runtime_scanned=True
        self.status.set(f"Viewing SAVED snapshot {snapshot.snapshot_id} (captured {time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(snapshot.captured_at))}) | live tracking paused | {len(self.runtime_objects)} objects")
        self.redraw()
    def diff_snapshot_action(self):
        # 6.2, deliberately small: compare whatever is currently being
        # viewed (live or a loaded snapshot) against one more file on disk.
        if not self.runtime_scanned:messagebox.showwarning("Nothing to compare","Capture/scan or load a snapshot first.");return
        base=self.viewing_snapshot or capture_runtime_snapshot(self.runtime_provider,self.runtime_frame,self.runtime_objects)
        path=filedialog.askopenfilename(initialdir="runtime_snapshots",filetypes=[("Snapshot JSON","*.json")],title="Compare against saved snapshot")
        if not path:return
        other=load_snapshot(path);diff=diff_snapshots(base,other)
        if diff.is_empty:messagebox.showinfo("Snapshot diff","No differences -- identical asset sets, states, and positions.");return
        lines=[f"Base: snapshot {base.snapshot_id}  vs  {Path(path).name}: snapshot {other.snapshot_id}",""]
        if diff.appeared:lines.append("Appeared:\n  "+"\n  ".join(diff.appeared))
        if diff.disappeared:lines.append("Disappeared:\n  "+"\n  ".join(diff.disappeared))
        if diff.changed:lines.append("Changed (state or position):\n  "+"\n  ".join(diff.changed))
        messagebox.showinfo("Snapshot diff","\n\n".join(lines))
    def create_page_action(self):
        # 7.2: "Current Runtime Snapshot -> Create Page". Never automatic --
        # this only runs when the user clicks the button, and every choice
        # inside CreatePageDialog (name, required/optional/ignored,
        # matching mode) is theirs, never inferred from composition.
        if not self.runtime_scanned:messagebox.showwarning("No runtime data","Capture/scan a live screen first.");return
        asset_ids=sorted({o.source.get("asset_id") for o in self.runtime_objects if o.source.get("asset_id")})
        if not asset_ids:messagebox.showwarning("Nothing to name","No asset-bearing objects in the current runtime snapshot (Renderer 1 text has no asset_id and isn't part of page composition).");return
        existing_page_id=self.current_page.page_id if self.current_page and self.current_page.core_assets==frozenset(asset_ids) else None
        existing_name=(self.current_page.name or "") if existing_page_id else ""
        dialog=CreatePageDialog(self,asset_ids,existing_name=existing_name)
        self.wait_window(dialog)
        if dialog.result is None:return
        name,required,optional,ignored,mode=dialog.result
        page=self.page_detector.create_named_page(asset_ids,name=name,required=required,optional=optional,ignored=ignored,matching_mode=mode,page_id=existing_page_id)
        self.page_detector.save(self.page_path)
        messagebox.showinfo("Page created",f"{page.page_id}: {page.name!r}\nrequired={sorted(page.required_assets)}\noptional={sorted(page.optional_assets)}\nignored={sorted(page.ignored_assets)}\nmode={page.matching_mode}")
    def poll_runtime(self):
        try:
            if self.live_tracking.get() and self.image is not None:self.update_runtime();self.redraw();self.sync_external_selection()
        except Exception as error:self.status.set(f"Runtime tracking unavailable: {error}")
        finally:self.after(750,self.poll_runtime)
    def sync_external_selection(self):
        current=self.selection_store.current()
        if not current:return
        asset_id=current.get("asset_id")
        if not asset_id or asset_id==self._last_synced_asset_id:return
        self._last_synced_asset_id=asset_id
        match=next((o for o in self.runtime_objects if o.source.get("asset_id")==asset_id),None)
        if match:self.select(match,publish=False)
        else:self.select(None,publish=False,not_drawn_asset_id=asset_id)  # 4.2: known elsewhere, not currently drawn here
    def native_point(self,event):
        sx,sy,ox,oy=self.transform();context=self.registry.contexts[self.context_id];return round((event.x-ox)/sx*context.native_width/self.image.width),round((event.y-oy)/sy*context.native_height/self.image.height)
    def hit(self,event):
        """Hit-tests against `self.objects` -- whatever is CURRENTLY DRAWN
        (live runtime objects when a scan succeeded, the static registry
        otherwise -- see refresh_objects_no_redraw) -- not always the static
        registry. A purely live-only object (e.g. a Renderer 1 line, which
        has no reason to ever get a manual registry entry) previously could
        never be hovered or clicked at all, since hit-testing and drawing
        used two different object lists. Smaller objects win over larger
        ones they sit on top of, matching gcrts.screen_mapping_registry's
        own hit_test ordering."""
        if self.image is None:return []
        x,y=self.native_point(event)
        return sorted((o for o in self.objects if o.screen_bounds.contains(x,y)),key=lambda o:o.screen_bounds.width*o.screen_bounds.height)
    def motion(self,event):
        hits=self.hit(event);self.status.set(self.tooltip(hits[0]) if hits else "No verified object at this point.")
    def tooltip(self,o):
        """5.3: type-appropriate fields, not the same generic line for
        everything -- a Renderer 1 line and a raster asset are identified
        by genuinely different evidence."""
        if o.text_representation==TextRepresentation.RUNTIME_TEXT_RENDERER_1:
            m=o.metadata
            return (f"Renderer 1 | line {o.source.get('line_index','—')} | script_unit={o.source.get('script_unit','unknown')} | "
                    f"pos=({o.screen_bounds.x},{o.screen_bounds.y}) | glyphs={m.get('glyph_count','—')} | "
                    f"profile={m.get('profile','—')} | {o.confidence.value}")
        m=o.metadata;vram=m.get("vram")
        if m.get("primitive_address") is not None:prim_count=1
        elif m.get("primitive_addresses"):prim_count=len(m["primitive_addresses"])
        else:prim_count="—"
        return (f"{o.display_name} | asset_id={o.source.get('asset_id',o.id)} | {o.source.get('file',o.source.get('kind'))} "
                f"block {o.source.get('block','—')} | format={(vram or {}).get('pixel_mode','—')} | "
                f"state={m.get('runtime_state','—')} | vram={vram or '—'} | prims={prim_count} | "
                f"{o.confidence.value}")
    def press(self,event):
        if self.mapping.get() and self.image is not None:self.drag_start=self.native_point(event)
        else:
            hits=self.hit(event);self.select(hits[0] if hits else None)
    def release(self,event):
        if not self.mapping.get() or self.drag_start is None:return
        x1,y1=self.drag_start;x2,y2=self.native_point(event);self.drag_start=None;x,y=min(x1,x2),min(y1,y2);w,h=abs(x2-x1),abs(y2-y1)
        if w<2 or h<2:return
        asset_id=simpledialog.askstring("Create mapping","Asset ID (for example main_menu.start), or leave blank for unknown:")
        if asset_id:
            known=next((o for items in self.registry.objects.values() for o in items if o.id==asset_id),None)
            if known:obj=InspectableScreenObject(known.id,known.display_name,known.object_type,ScreenBounds(x,y,w,h),known.source,known.editor_target,MappingConfidence.MANUAL_VERIFIED,known.text_representation,known.translation_status,known.editable,known.metadata)
            else:obj=InspectableScreenObject(asset_id,asset_id,ScreenObjectType.UNKNOWN_REGION,ScreenBounds(x,y,w,h),{"kind":"UNKNOWN"},{"type":"MAPPING_INVESTIGATION"},MappingConfidence.UNKNOWN)
        else:
            asset_id=f"manual.unknown.{len(self.registry.list_objects(self.context_id))}";obj=InspectableScreenObject(asset_id,"Unknown region",ScreenObjectType.UNKNOWN_REGION,ScreenBounds(x,y,w,h),{"kind":"UNKNOWN"},{"type":"MAPPING_INVESTIGATION"},MappingConfidence.UNKNOWN)
        try:self.registry.upsert(self.context_id,obj)
        except ValueError as error:messagebox.showerror("Protected mapping",str(error));return
        self.registry.save(self.registry_path);self.refresh_objects();self.select(obj)
    def select(self,obj,publish=True,not_drawn_asset_id=None):
        self.selected=obj
        if obj is None:
            if not_drawn_asset_id:self.heading.set(not_drawn_asset_id);text=f"Known asset -- not currently drawn.\nNo live GPU/VRAM correlation this frame ({self.runtime_frame})."
            else:self.heading.set("No object selected");text="No verified source mapping exists.\nUse Mapping Mode to create one."
        else:
            self.heading.set(obj.display_name);route=dispatch(obj);text=f"Type: {obj.object_type.value}\nText: {obj.text_representation.value}\nTranslation: {obj.translation_status.value}\nConfidence: {obj.confidence.value}\nBounds: {obj.screen_bounds}\n\nSource:\n{obj.source}\n\nEditor:\n{route.target.value}\nAvailable: {route.available}\nReason: {route.reason or 'ready'}\n\nMetadata:\n{obj.metadata}"
            if publish:self.selection_store.select_asset(obj.source.get("asset_id",obj.id),"visual_inspector")
        self.details.configure(state="normal");self.details.delete("1.0","end");self.details.insert("1.0",text);self.details.configure(state="disabled")
        if self.image is not None:self.redraw()  # 4.1: highlight must appear immediately, not wait for the next 750ms poll
    def open_selected(self):
        if self.selected is None:return
        route=dispatch(self.selected)
        if not route.available:messagebox.showwarning("Editor unavailable",route.reason);return
        if route.target==EditorTargetType.ASSET_INSPECTOR:
            block=self.selected.source.get("block",self.selected.source.get("members",[0])[0]);source=Path(self.selected.source.get("local_file",self.asset_source));command=[sys.executable,"-m","gcrts.asset_inspector_ui",str(source),"--disc-path",self.selected.source["file"],"--workspace","asset_workspace","--block",str(block)]
            if self.selected.source.get("members"):command.extend(("--composite-members",",".join(map(str,self.selected.source["members"]))))
            subprocess.Popen(command,cwd=Path.cwd())
        else:messagebox.showinfo(route.target.value,route.reason or str(route.parameters))
    def delete_selected(self):
        if self.selected is None or self.selected.confidence==MappingConfidence.LIVE_VERIFIED:messagebox.showwarning("Protected mapping","LIVE_VERIFIED mappings are not deleted from the UI.");return
        self.registry.delete(self.context_id,self.selected.id);self.registry.save(self.registry_path);self.select(None);self.refresh_objects()

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument("--registry",default="screen_mappings.json");p.add_argument("--asset-source",default="sdb_main_menu_asset/MENUDAT.BIN");p.add_argument("--screenshot");p.add_argument("--context");p.add_argument("--capture",action="store_true");a=p.parse_args(argv);app=VisualInspectorApp(Path(a.registry),Path(a.asset_source),a.context);
    if a.screenshot:app.image=Image.open(a.screenshot).convert("RGB");app.redraw()
    if a.capture:app.after(300,app.capture)
    app.mainloop()
if __name__=="__main__":main()
