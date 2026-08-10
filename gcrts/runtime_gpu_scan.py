"""One-shot safe correlation using logged OT roots plus external RAM/VRAM dumps."""
import argparse,urllib.request
from pathlib import Path
from gcrts.asset_project import AssetProject
from gcrts.gpu_asset_correlation import correlate
from gcrts.psx_ordering_table import parse_ot
from gcrts.vram_asset_detector import VramAssetDetector
def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument("--events",default=r"C:\tmp\gcrts-runtime-events.tsv");p.add_argument("--base-url",default="http://127.0.0.1:8080");a=p.parse_args(argv)
    lines=[line.split("\t") for line in Path(a.events).read_text().splitlines() if line.startswith("GPU_OT_ROOT")];latest=lines[-4:]
    ram=urllib.request.urlopen(a.base_url+"/api/v1/cpu/ram/raw").read();vram=urllib.request.urlopen(a.base_url+"/api/v1/gpu/vram/raw").read();project=AssetProject.open("sdb_main_menu_asset/MENUDAT.BIN","DAT/SINKOU/MENUDAT.BIN;1");assets=VramAssetDetector().detect_project(vram,project)
    primitives=[]
    for fields in latest:primitives.extend(parse_ot(ram,int(fields[2],16),int(fields[1])))
    for hit in correlate(primitives,assets):print(f"{hit.asset.asset_id}\tblock={hit.asset.block}\tstate=DRAWN_THIS_FRAME\tprimitive=0x{hit.primitive.address:08X}\tscreen={hit.primitive.screen_bounds}\tuv={(hit.primitive.u,hit.primitive.v,hit.primitive.uv_width,hit.primitive.uv_height)}\ttpage={hit.primitive.tpage}")
if __name__=="__main__":main()
