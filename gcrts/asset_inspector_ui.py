"""Tk desktop Asset Browser. Binary behavior lives in backend services only."""
from __future__ import annotations

import argparse
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import ImageTk

from gcrts.asset_project import AssetProject
from gcrts.asset_workspace import AssetWorkspace, sha256
from gcrts.pcsx_patch import PcsxReduxPatchProvider
from gcrts.project_selection import FileProjectSelection
from gcrts.runtime_visual_provider import RuntimeVisualProvider,open_runtime_projects


def resolve_asset_selection(project:AssetProject,composite_members:tuple[int,...],asset_id:str):
    """Pure lookup: does `asset_id` refer to something THIS project/window
    knows about, and if so as a single block or the composite? Returns
    ("block", block_number), ("composite", None), or None (unknown here --
    the correct window to react is a different one, and this one should
    silently do nothing, not guess)."""
    for d in project.descriptors:
        if d.id==asset_id:return ("block",d.container.block)
    if composite_members and asset_id==f"progdat.group{composite_members[0]//5}":return ("composite",None)
    return None

def runtime_status_text(asset_id:str,runtime_ids:set[str])->str:
    return "LIVE -- currently drawn this frame" if asset_id in runtime_ids else "Known asset -- not currently drawn"


class AssetInspectorApp(tk.Tk):
    def __init__(self,project:AssetProject,workspace:AssetWorkspace,composite_members:tuple[int,...]=()):
        super().__init__();self.project=project;self.workspace=workspace;self.selected=0;self.composite_members=composite_members;self.composite_selected=False;self._images=[];self.selection_store=FileProjectSelection();self.runtime_provider=RuntimeVisualProvider(open_runtime_projects());self.runtime_ids=set();self._cards={};self._selected_card=None;self._last_external_asset_id=None
        ttk.Style(self).configure("Selected.TButton",background="#2389ff",relief="solid",borderwidth=3)
        self.title("GCRTS Asset Inspector — MENUDAT");self.geometry("1120x720");self.minsize(900,600)
        self._build();self.refresh_runtime_badges();self.refresh_browser();self.select_composite() if composite_members else self.select(7 if len(project.descriptors)>8 else 0);self.after(1000,self.poll_runtime_badges);self.after(1000,self.poll_external_selection)

    def _build(self):
        top=ttk.Frame(self,padding=8);top.pack(fill="x")
        ttk.Label(top,text="Search:").pack(side="left");self.query=tk.StringVar();e=ttk.Entry(top,textvariable=self.query,width=32);e.pack(side="left",padx=6);e.bind("<KeyRelease>",lambda _:self.refresh_browser())
        ttk.Label(top,text=self.project.disc_path).pack(side="right")
        pane=ttk.Panedwindow(self,orient="horizontal");pane.pack(fill="both",expand=True,padx=8,pady=(0,8))
        left=ttk.Frame(pane);right=ttk.Frame(pane,padding=10);pane.add(left,weight=3);pane.add(right,weight=2)
        self.canvas=tk.Canvas(left,bg="#202020",highlightthickness=0);scroll=ttk.Scrollbar(left,orient="vertical",command=self.canvas.yview);self.canvas.configure(yscrollcommand=scroll.set);scroll.pack(side="right",fill="y");self.canvas.pack(fill="both",expand=True)
        self.grid=ttk.Frame(self.canvas);self.window=self.canvas.create_window((0,0),window=self.grid,anchor="nw");self.grid.bind("<Configure>",lambda _:self.canvas.configure(scrollregion=self.canvas.bbox("all")));self.canvas.bind("<Configure>",lambda e:self.canvas.itemconfigure(self.window,width=e.width))
        self.title_var=tk.StringVar();ttk.Label(right,textvariable=self.title_var,font=("Segoe UI",16,"bold")).pack(anchor="w")
        self.preview=ttk.Label(right);self.preview.pack(pady=10)
        self.meta=tk.Text(right,height=17,width=48,state="disabled",font=("Consolas",10));self.meta.pack(fill="x")
        ttk.Label(right,text="Palette / CLUT",font=("Segoe UI",10,"bold")).pack(anchor="w",pady=(10,2));self.palette=ttk.Frame(right);self.palette.pack(fill="x")
        edit=ttk.LabelFrame(right,text="Indexed text overlay",padding=8);edit.pack(fill="x",pady=10)
        self.overlay_text=tk.StringVar(value="START");self.x=tk.IntVar(value=8);self.y=tk.IntVar(value=6);self.color=tk.IntVar(value=1)
        self.clear_existing=tk.BooleanVar(value=True)
        ttk.Entry(edit,textvariable=self.overlay_text,width=18).grid(row=0,column=0,columnspan=2,sticky="ew")
        for col,(label,var) in enumerate((("X",self.x),("Y",self.y),("Index",self.color))):ttk.Label(edit,text=label).grid(row=1,column=col*2,sticky="e");ttk.Spinbox(edit,textvariable=var,width=5,from_=0,to=255).grid(row=1,column=col*2+1,sticky="w")
        ttk.Button(edit,text="Apply overlay",command=self.apply_overlay).grid(row=2,column=0,columnspan=6,sticky="ew",pady=(6,0))
        ttk.Checkbutton(edit,text="Clear existing pixels first",variable=self.clear_existing).grid(row=3,column=0,columnspan=6,sticky="w")
        self.budget=tk.StringVar();ttk.Label(right,textvariable=self.budget,font=("Consolas",10)).pack(anchor="w")
        actions=ttk.Frame(right);actions.pack(fill="x",pady=8)
        for text,cmd in (("Export PNG",self.export),("Replace PNG",self.replace),("Build output",self.build_output),("Test in PCSX-Redux",self.inject),("Restore",self.restore)):
            ttk.Button(actions,text=text,command=cmd).pack(fill="x",pady=2)

    def refresh_browser(self):
        for child in self.grid.winfo_children():child.destroy()
        self._images=[];self._cards={};query=self.query.get().lower()
        row_offset=0
        if self.composite_members and (not query or "composite" in query or "classroom" in query or "background" in query):
            image=self.project.composite_image(self.composite_members);image.thumbnail((360,120));photo=ImageTk.PhotoImage(image);self._images.append(photo)
            card=ttk.Button(self.grid,image=photo,text="[COMPOSITE] Classroom Background\n320x240  blocks 0–4",compound="top",command=self.select_composite);card.grid(row=0,column=0,columnspan=3,padx=6,pady=6,sticky="ew");row_offset=1
            self._cards[("composite",None)]=card
        visible=[d for d in self.project.descriptors if query in d.id.lower() or query in d.display_name.lower() or query in str(d.container.block)]
        for n,d in enumerate(visible):
            image=self.project.tim(d.container.block).to_image();image.thumbnail((180,64));photo=ImageTk.PhotoImage(image);self._images.append(photo)
            badge="  [DRAWN]" if d.id in self.runtime_ids else "";card=ttk.Button(self.grid,image=photo,text=f"[{d.container.block:02}] {d.display_name}{badge}\n{d.image.width}x{d.image.height}  {d.image.format}",compound="top",command=lambda b=d.container.block:self.select(b));card.grid(row=row_offset+n//3,column=n%3,padx=6,pady=6,sticky="nsew")
            self._cards[("block",d.container.block)]=card
        for column in range(3):self.grid.columnconfigure(column,weight=1)
        self._restyle_selected_card()

    def select(self,block:int,publish:bool=True):
        self.composite_selected=False;self.selected=block;d=self.project.descriptors[block]
        if publish:self.selection_store.select_asset(d.id,"asset_inspector")
        self._last_external_asset_id=d.id;tim=self.project.tim(block);self.title_var.set(f"{d.display_name}  [{block:02}]")
        image=tim.to_image().resize((tim.width*3,tim.height*3));self.detail_image=ImageTk.PhotoImage(image);self.preview.configure(image=self.detail_image)
        errors=d.validate();caps=[name for name,value in vars(d.capabilities).items() if value]
        status=runtime_status_text(d.id,self.runtime_ids)
        text=(f"ID:          {d.id}\nSource:      {d.source.path}\nBlock:       {block}\nOffset:      0x{d.container.compressed_offset:X}\nCompressed:  {d.container.compressed_size} bytes\nDecoded:     {d.container.decoded_size} bytes\nDimensions:  {d.image.width} x {d.image.height}\nFormat:      {d.image.format}\nPalette:     {d.image.palette_colors} colors\nSize policy: {d.encoding_policy.size_mode.value}\nSemantic:    {d.semantic_status.value}\nCapabilities:{', '.join(caps)}\nValidation:  {'OK' if not errors else '; '.join(errors)}\nRuntime:     {status}")
        self.meta.configure(state="normal");self.meta.delete("1.0","end");self.meta.insert("1.0",text);self.meta.configure(state="disabled")
        for child in self.palette.winfo_children():child.destroy()
        counts=tim.usage_counts()
        if tim.palette:
            used=[i for i,count in enumerate(counts) if count and tim.palette[i] != 0]
            candidates=used or [i for i,value in enumerate(tim.palette) if value != 0]
            self.color.set(max(candidates,key=lambda i:(tim.palette[i]&31)+((tim.palette[i]>>5)&31)+((tim.palette[i]>>10)&31)))
        for i,value in enumerate(tim.palette):
            r=(value&31)*255//31;g=((value>>5)&31)*255//31;b=((value>>10)&31)*255//31
            label=tk.Label(self.palette,bg=f"#{r:02x}{g:02x}{b:02x}",width=4,height=2,text=str(i),fg="white" if r+g+b<300 else "black");label.grid(row=i//8,column=i%8,padx=1,pady=1);label.bind("<Enter>",lambda _,i=i,v=value,c=counts[i]:self.budget.set(f"CLUT {i}: 0x{v:04X}, STP={(v>>15)&1}, usage={c}"))
        self.update_budget();self._highlight_and_reveal(("block",block))

    def select_composite(self,publish:bool=True):
        self.composite_selected=True;asset_id="progdat.group"+str(self.composite_members[0]//5)
        if publish:self.selection_store.select_asset(asset_id,"asset_inspector")
        self._last_external_asset_id=asset_id;image=self.project.composite_image(self.composite_members);self.title_var.set("Classroom Background  [COMPOSITE 0–4]")
        preview=image.copy();preview.thumbnail((640,480));self.detail_image=ImageTk.PhotoImage(preview);self.preview.configure(image=self.detail_image)
        status=runtime_status_text(asset_id,self.runtime_ids)
        text=(f"Logical asset: Classroom Background\nSource:        DAT/SINKOU/PROGDAT.BIN;1\nPhysical:      blocks 0, 1, 2, 3, 4\nLayout:        five horizontal 64x240 strips\nDimensions:    320 x 240\nFormat:        TIM 8bpp indexed per member\nView:          matches the complete VRAM composition\nRuntime:       {status}")
        self.meta.configure(state="normal");self.meta.delete("1.0","end");self.meta.insert("1.0",text);self.meta.configure(state="disabled")
        for child in self.palette.winfo_children():child.destroy()
        self.budget.set("Composite editing preserves five independent palettes and size budgets.\nExport/Replace operate on one 320x240 PNG.")
        self._highlight_and_reveal(("composite",None))

    def _highlight_and_reveal(self,key):
        """4.1: a selected card is both scrolled into view AND visually
        distinguished from the rest of the grid, whether the selection
        came from a click here or from an external window syncing in."""
        self._selected_card=key;self._restyle_selected_card()
        card=self._cards.get(key)
        if card is None:return
        self.update_idletasks();grid_h=max(1,self.grid.winfo_height())
        fraction=max(0.0,min(1.0,(card.winfo_y()-20)/grid_h))
        self.canvas.yview_moveto(fraction)
    def _restyle_selected_card(self):
        for key,card in self._cards.items():
            card.configure(style="Selected.TButton" if key==self._selected_card else "TButton")
    def refresh_runtime_badges(self):
        try:self.runtime_ids={o.source.get("asset_id") for o in self.runtime_provider.scan()[1]}
        except Exception:self.runtime_ids=set()
    def poll_runtime_badges(self):
        before=self.runtime_ids;self.refresh_runtime_badges()
        if before!=self.runtime_ids:self.refresh_browser()
        self.after(1000,self.poll_runtime_badges)
    def poll_external_selection(self):
        # No source-string check needed: `_last_external_asset_id` is set by
        # EVERY select()/select_composite() call, local click or external
        # sync alike, so an echo of our own just-published write already
        # reads back equal and is naturally skipped below -- while a
        # genuinely different window (including another AssetInspectorApp
        # instance on a different source file) still gets through.
        try:
            current=self.selection_store.current()
            asset_id=current.get("asset_id") if current else None
            if asset_id and asset_id!=self._last_external_asset_id:
                resolved=resolve_asset_selection(self.project,self.composite_members,asset_id)
                if resolved is not None:
                    kind,value=resolved
                    if kind=="composite":self.select_composite(publish=False)
                    else:self.select(value,publish=False)
        finally:self.after(1000,self.poll_external_selection)

    def update_budget(self):
        b=self.project.budget(self.selected);self.budget.set(f"Encoded: {b.raw_encoded_size} / {b.original_size}\nFinal: {b.final_size or '—'}\n{b.detail}")
    def apply_overlay(self):
        if self.composite_selected:messagebox.showinfo("Composite edit","Use Replace PNG for the complete 320x240 image, or select one physical strip for indexed text overlay.");return
        try:self.project.text_overlay(self.selected,self.overlay_text.get(),self.x.get(),self.y.get(),self.color.get(),clear_existing=self.clear_existing.get());self.select(self.selected);self.refresh_browser()
        except Exception as e:messagebox.showerror("Overlay blocked",str(e))
    def export(self):
        path=filedialog.asksaveasfilename(defaultextension=".png",filetypes=[("PNG","*.png")]);
        if path:self.project.export_composite_png(self.composite_members,path) if self.composite_selected else self.project.export_png(self.selected,path)
    def replace(self):
        path=filedialog.askopenfilename(filetypes=[("PNG","*.png")]);
        if not path:return
        try:
            if self.composite_selected:self.project.replace_composite_png(self.composite_members,path);self.select_composite()
            else:self.project.replace_png(self.selected,path);self.select(self.selected)
            self.refresh_browser()
        except Exception as e:messagebox.showerror("Replacement blocked",str(e))
    def build_output(self):
        try:
            data=self.project.build();source_hash=sha256(self.project.source);name=Path(self.project.disc_path.split(";")[0]).stem+".modified.BIN";asset_id="main_menu.classroom_background" if self.composite_selected else self.project.descriptors[self.selected].id;path=self.workspace.write_output(name,data,asset_id,source_hash);messagebox.showinfo("Output built",f"{path}\nSHA-256: {sha256(data)}")
        except Exception as e:messagebox.showerror("Build blocked",str(e))
    def inject(self):
        try:PcsxReduxPatchProvider().patch_disc_file(self.project.disc_path,self.project.build());messagebox.showinfo("Temporary patch","PCSX-Redux accepted the temporary patch. Hard-reset/reload to test it.")
        except Exception as e:messagebox.showerror("Injection failed",str(e))
    def restore(self):
        if self.composite_selected:self.project.restore_composite(self.composite_members);self.select_composite()
        else:self.project.restore(self.selected);self.select(self.selected)
        self.refresh_browser()


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument("source");parser.add_argument("--disc-path",default="DAT/SINKOU/MENUDAT.BIN;1");parser.add_argument("--workspace",default="asset_workspace");parser.add_argument("--block",type=int,default=7);parser.add_argument("--composite-members");args=parser.parse_args(argv)
    members=tuple(int(value) for value in args.composite_members.split(",")) if args.composite_members else ()
    project=AssetProject.open(args.source,args.disc_path);workspace=AssetWorkspace(Path(args.workspace));workspace.register_source(Path(args.source).name,project.source);app=AssetInspectorApp(project,workspace,members)
    if not members:app.select(args.block)
    app.mainloop()

if __name__=="__main__":main()
