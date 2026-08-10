from pathlib import Path
from gcrts.asset_fingerprint import AssetFingerprintIndex
from gcrts.asset_project import AssetProject
from gcrts.runtime_content import RuntimeConfidence

ROOT=Path(__file__).parents[1]/"sdb_main_menu_asset"
def test_menudat_block9_resolves_by_source_and_decoded_hash():
    p=AssetProject.open(ROOT/"MENUDAT.BIN","DAT/SINKOU/MENUDAT.BIN;1");index=AssetFingerprintIndex.from_project(p)
    identity,confidence=index.resolve_source("DAT/SINKOU/MENUDAT.BIN;1",9);assert identity.block==9 and confidence==RuntimeConfidence.LIVE_EXACT_SOURCE
    identity,confidence=index.resolve_decoded(p.records[9].decoded);assert identity.block==9 and confidence==RuntimeConfidence.LIVE_HASH_MATCH
    prefix=p.source[p.records[9].offset:p.records[9].offset+24].hex();identity,confidence=index.resolve_runtime_signature(prefix,p.records[9].consumed_size,len(p.records[9].decoded));assert identity.block==9 and confidence==RuntimeConfidence.LIVE_STRUCTURAL_MATCH
def test_unknown_hash_stays_unknown():
    p=AssetProject.open(ROOT/"MENUDAT.BIN","DAT/SINKOU/MENUDAT.BIN;1");identity,confidence=AssetFingerprintIndex.from_project(p).resolve_decoded(b"unknown");assert identity is None and confidence==RuntimeConfidence.UNKNOWN
