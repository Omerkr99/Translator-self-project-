"""One-shot live VRAM residency scan for known projects."""
import argparse,json
from gcrts.asset_project import AssetProject
from gcrts.vram_asset_detector import PcsxVramProvider,VramAssetDetector
def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument("source");p.add_argument("--disc-path",required=True);p.add_argument("--base-url",default="http://127.0.0.1:8080");args=p.parse_args(argv)
    project=AssetProject.open(args.source,args.disc_path);matches=VramAssetDetector().detect_project(PcsxVramProvider(args.base_url).read(),project)
    print(json.dumps([m.__dict__ for m in matches],indent=2))
if __name__=="__main__":main()
