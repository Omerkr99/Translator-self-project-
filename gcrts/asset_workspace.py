"""Safe working-copy model and patch journal for the Asset Inspector."""
from __future__ import annotations

import hashlib, json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def sha256(data: bytes) -> str: return hashlib.sha256(data).hexdigest().upper()


@dataclass
class AssetWorkspace:
    root: Path
    source_hashes: dict[str,str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.root=Path(self.root)
        for name in ("source","work","output","previews"):(self.root/name).mkdir(parents=True,exist_ok=True)

    def register_source(self, name: str, data: bytes) -> Path:
        path=self.root/"source"/name
        if path.exists() and path.read_bytes()!=data: raise ValueError("refusing to overwrite canonical source")
        if not path.exists(): path.write_bytes(data)
        self.source_hashes[name]=sha256(data);return path

    def write_output(self, name: str, data: bytes, asset_id: str, source_hash: str) -> Path:
        path=self.root/"output"/name;path.write_bytes(data)
        entry={"asset_id":asset_id,"source_hash":source_hash,"output_hash":sha256(data),"temporary_patch":False,
               "restored":False,"timestamp":datetime.now(timezone.utc).isoformat(),"path":str(path)}
        journal=self.root/"patch_journal.jsonl"
        with journal.open("a",encoding="utf-8") as f:f.write(json.dumps(entry,ensure_ascii=False)+"\n")
        return path
