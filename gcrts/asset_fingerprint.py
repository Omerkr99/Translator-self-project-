"""Canonical source/hash fingerprints for resolving runtime decode events."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from gcrts.asset_project import AssetProject
from gcrts.runtime_content import CanonicalAssetIdentity,RuntimeConfidence

@dataclass(frozen=True)
class AssetFingerprint:
    identity:CanonicalAssetIdentity;decoded_sha256:str;decoded_size:int;palette_sha256:str|None;compressed_prefix_hex:str

class AssetFingerprintIndex:
    def __init__(self,fingerprints=()):self.fingerprints=list(fingerprints);self.by_hash={f.decoded_sha256:f for f in self.fingerprints}
    @classmethod
    def from_project(cls,project:AssetProject):
        items=[]
        for descriptor,record in zip(project.descriptors,project.records):
            tim=project.tim(descriptor.container.block);palette=bytes().join(value.to_bytes(2,"little") for value in tim.palette)
            identity=CanonicalAssetIdentity(descriptor.id,project.disc_path,descriptor.container.type,descriptor.container.block,descriptor.container.compressed_offset,descriptor.container.compressed_size,descriptor.container.decoded_size,descriptor.image.format,descriptor.usage,descriptor.usage in {"button_label","category_label","photo_label","sound_label","system_menu","chapter_title"},descriptor.usage!="background",descriptor.usage)
            prefix=project.source[record.offset:record.offset+24].hex()
            items.append(AssetFingerprint(identity,sha256(record.decoded).hexdigest(),len(record.decoded),sha256(palette).hexdigest() if palette else None,prefix))
        return cls(items)
    def resolve_decoded(self,data:bytes):
        match=self.by_hash.get(sha256(data).hexdigest())
        return (match.identity,RuntimeConfidence.LIVE_HASH_MATCH) if match else (None,RuntimeConfidence.UNKNOWN)
    def resolve_source(self,disc_path,block):
        match=next((f for f in self.fingerprints if f.identity.disc_path==disc_path and f.identity.block==block),None)
        return (match.identity,RuntimeConfidence.LIVE_EXACT_SOURCE) if match else (None,RuntimeConfidence.UNKNOWN)
    def resolve_runtime_signature(self,compressed_prefix_hex,compressed_size,decoded_size):
        matches=[f for f in self.fingerprints if f.compressed_prefix_hex==compressed_prefix_hex.lower() and f.identity.compressed_size==compressed_size and f.decoded_size==decoded_size]
        return (matches[0].identity,RuntimeConfidence.LIVE_STRUCTURAL_MATCH) if len(matches)==1 else (None,RuntimeConfidence.UNKNOWN)
