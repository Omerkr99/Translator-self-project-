"""Automation CLI for the same backend used by the graphical Asset Inspector."""
from __future__ import annotations
import argparse
from pathlib import Path
from gcrts.asset_project import AssetProject
from gcrts.asset_workspace import AssetWorkspace,sha256
from gcrts.pcsx_patch import PcsxReduxPatchProvider

def main(argv=None):
    ap=argparse.ArgumentParser(description="GCRTS Asset Inspector CLI");ap.add_argument("source");ap.add_argument("--disc-path",default="DAT/SINKOU/MENUDAT.BIN;1")
    sub=ap.add_subparsers(dest="command",required=True)
    sub.add_parser("list");show=sub.add_parser("show");show.add_argument("block",type=int)
    export=sub.add_parser("export");export.add_argument("block",type=int);export.add_argument("output")
    text=sub.add_parser("text");text.add_argument("block",type=int);text.add_argument("value");text.add_argument("output");text.add_argument("--x",type=int,default=5);text.add_argument("--y",type=int,default=3);text.add_argument("--index",type=int);text.add_argument("--font",default=r"C:\Windows\Fonts\consolab.ttf");text.add_argument("--font-size",type=int,default=14)
    inject=sub.add_parser("inject");inject.add_argument("file");sub.add_parser("clear-patches")
    args=ap.parse_args(argv);project=AssetProject.open(args.source,args.disc_path)
    if args.command=="list":
        for d in project.descriptors:print(f"{d.container.block:02} {d.id:42} {d.image.width:3}x{d.image.height:<3} {d.image.format:18} off=0x{d.container.compressed_offset:04X} size={d.container.compressed_size}")
    elif args.command=="show":print(project.descriptors[args.block].to_dict())
    elif args.command=="export":project.export_png(args.block,args.output)
    elif args.command=="text":
        tim=project.tim(args.block);counts=tim.usage_counts();used=[i for i,count in enumerate(counts) if count and tim.palette[i]!=0];candidates=used or [i for i,value in enumerate(tim.palette) if value!=0];index=args.index if args.index is not None else max(candidates,key=lambda i:(tim.palette[i]&31)+((tim.palette[i]>>5)&31)+((tim.palette[i]>>10)&31))
        project.text_overlay(args.block,args.value,args.x,args.y,index,args.font,args.font_size,True);budget=project.budget(args.block)
        if not budget.safe:raise SystemExit(budget.detail)
        data=project.build();Path(args.output).write_bytes(data);print(budget);print(f"SHA-256 {sha256(data)}")
    elif args.command=="inject":PcsxReduxPatchProvider().patch_disc_file(args.disc_path,Path(args.file).read_bytes())
    else:PcsxReduxPatchProvider().clear()

if __name__=="__main__":main()
